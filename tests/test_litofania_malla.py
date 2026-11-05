#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_litofania_malla.py
------------------
Red de regresión para L3 de la litofanía (`core/litofania.py`): grosor -> malla 3D. Lo que se cuida:

  * la malla CIERRA, comprobado por 4 vías independientes: `is_watertight` (+ winding + volumen > 0),
    Euler V-E+F = 2, toda arista usada por exactamente 2 caras, y sin caras degeneradas ni duplicadas;
  * el grosor medido sobre la malla con RAYOS VERTICALES (sin mirar cómo se construyó) es el pedido, y
    de punta a punta (L1 -> L2 -> L3) lo oscuro queda grueso/alto;
  * el volumen es el esperado, contra fórmulas escritas acá aparte;
  * la placa mide exactamente lo pedido y la imagen se lee derecha desde el lado del relieve (o desde
    el lado plano con `cara_visible="plana"`);
  * es VECTORIZADA: un test con `ast` verifica que no hay un solo bucle, y que 800x1000 puntos se arma en
    segundos con memoria acotada;
  * la placa sigue siendo watertight al pegarle un marco y hacerle un agujero (lo que hará L8), y sobrevive
    a una ida y vuelta por STL.

No usa pytest (ver AGENTS.md "Testing") -- funciones `test_*` con `assert` simple,
corribles con `python tests/test_litofania_malla.py`.
"""
import ast
import contextlib
import os
import sys
import tempfile
import time
import tracemalloc

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import trimesh
from PIL import Image

from core import litofania as lf

FORMAS = ((2, 2), (2, 7), (7, 2), (3, 3), (17, 33), (40, 60))      # (alto_px, ancho_px); incluye los mínimos


# --- ayudas ---------------------------------------------------------------------------------

def _grosor_al_azar(alto, ancho, semilla=0):
    return 0.8 + 2.0 * np.random.default_rng(semilla).random((alto, ancho))


def _suave(alto, ancho, semilla=0):
    """Un relieve suave (como una foto), no ruido punto a punto."""
    from scipy.ndimage import gaussian_filter
    g = gaussian_filter(np.random.default_rng(semilla).random((alto, ancho)), sigma=max(alto, ancho) / 12)
    return 0.8 + 2.0 * (g - g.min()) / (g.max() - g.min())


def _malla(alto=20, ancho=30, ancho_mm=15.0, alto_mm=10.0, semilla=1, **kwargs):
    return lf.malla_desde_grilla_grosor(_grosor_al_azar(alto, ancho, semilla), ancho_mm, alto_mm, **kwargs)


@contextlib.contextmanager
def _carpeta():
    with tempfile.TemporaryDirectory() as d:
        yield d


def _perimetro_cuenta(alto, ancho):
    return 2 * (alto + ancho) - 4


def _caras_del_frente(alto, ancho):
    return 2 * (alto - 1) * (ancho - 1)


def _espesor_por_rayos(malla, puntos_xy):
    """Grosor de la placa en cada (x, y): un rayo vertical de arriba hacia abajo contra TODOS los triángulos,
    y se mide la distancia entre el primer y el último impacto. Exige exactamente 2 impactos por rayo (la cara
    de arriba y la trasera).

    Es numpy puro a propósito, sin `trimesh.ray`: esa ruta necesita `rtree`, que no todos los entornos tienen,
    y así el test no depende del código de rayos de otra librería. Un rayo vertical corta un triángulo en el
    punto cuya proyección en XY cae adentro de la del triángulo: se calculan sus coordenadas baricéntricas (s, t)
    y se interpola la altura. Las paredes (verticales) se proyectan a un segmento y quedan afuera."""
    puntos = np.asarray(puntos_xy, dtype=float)
    tri = malla.triangles                                           # (T, 3, 3)
    a, b, c = tri[:, 0], tri[:, 1], tri[:, 2]
    v1, v0 = b[:, :2] - a[:, :2], c[:, :2] - a[:, :2]               # lados desde el vértice a, en XY
    d = v1[:, 0] * v0[:, 1] - v1[:, 1] * v0[:, 0]                   # 2 x el área firmada de la proyección
    no_vertical = np.abs(d) > 1e-12                                 # una pared se proyecta a un segmento: d = 0
    v2 = puntos[:, None, :] - a[None, :, :2]                        # (R, T, 2): del vértice a hasta cada punto
    with np.errstate(divide="ignore", invalid="ignore"):            # las paredes dan d = 0 -> NaN/inf, y se descartan
        s = (v2[..., 0] * v0[None, :, 1] - v2[..., 1] * v0[None, :, 0]) / d[None, :]
        t = (v1[None, :, 0] * v2[..., 1] - v1[None, :, 1] * v2[..., 0]) / d[None, :]
        adentro = no_vertical[None, :] & (s >= -1e-12) & (t >= -1e-12) & (s + t <= 1 + 1e-12)
        z = a[None, :, 2] + s * (b[None, :, 2] - a[None, :, 2]) + t * (c[None, :, 2] - a[None, :, 2])
    impactos = adentro.sum(axis=1)
    malos = np.where(impactos != 2)[0]
    assert malos.size == 0, f"el rayo en {puntos[malos[0]]} dio {impactos[malos[0]]} impactos, tenían que ser 2"
    z_alto = np.where(adentro, z, -np.inf).max(axis=1)
    z_bajo = np.where(adentro, z, np.inf).min(axis=1)
    return z_alto - z_bajo


def _z_esperado(grosor, j, i, u, v, diagonal):
    """Altura de la superficie en el punto (u, v) de la celda (j, i): u = fracción desde la izquierda,
    v = desde arriba. Interpolación plana del triángulo que lo contiene, escrita acá aparte."""
    za, zb, zc, zd = grosor[j, i], grosor[j, i + 1], grosor[j + 1, i], grosor[j + 1, i + 1]
    usa_ad = diagonal == "fija" or abs(za - zd) <= abs(zb - zc)
    if usa_ad:
        return za + (zd - zc) * u + (zc - za) * v if v >= u else za + (zb - za) * u + (zd - zb) * v
    return za + (zb - za) * u + (zc - za) * v if u + v <= 1 else zd + (zc - zd) * (1 - u) + (zb - zd) * (1 - v)


# --- 1. watertight: 4 vías independientes ---------------------------------------------------------

def test_cierra_por_las_cuatro_vias_independientes():
    for alto, ancho in FORMAS:
        for diagonal in lf.DIAGONALES:
            for cara in lf.CARAS_VISIBLES:
                m = lf.malla_desde_grilla_grosor(_grosor_al_azar(alto, ancho), 15.0, 10.0, cara_visible=cara, diagonal=diagonal)
                nombre = f"{ancho}x{alto} {diagonal} {cara}"
                # (1) trimesh
                assert m.is_watertight and m.is_winding_consistent and m.volume > 0, nombre
                # (2) Euler: V - E + F = 2 (esfera topológica: sin agujeros ni asas)
                aristas = np.sort(m.edges, axis=1)
                _, usos = np.unique(aristas, axis=0, return_counts=True)
                assert len(m.vertices) - len(usos) + len(m.faces) == 2, f"{nombre}: Euler"
                # (3) toda arista en exactamente 2 caras
                assert (usos == 2).all(), f"{nombre}: hay aristas con {sorted(set(usos))} caras"
                # (4) sin caras de área cero ni duplicadas
                assert (m.area_faces > 0).all(), f"{nombre}: caras degeneradas"
                assert len(np.unique(np.sort(m.faces, axis=1), axis=0)) == len(m.faces), f"{nombre}: caras duplicadas"
                assert lf.verificar_malla(m)["ok"], nombre


def test_cantidad_de_vertices_y_caras():
    """V = puntos + perímetro + 1 centro; F = 2 por celda + 2 por tramo de pared + 1 por tramo de abanico."""
    for alto, ancho in FORMAS:
        m = _malla(alto, ancho)
        per = _perimetro_cuenta(alto, ancho)
        assert len(m.vertices) == alto * ancho + per + 1, (alto, ancho)
        assert len(m.faces) == _caras_del_frente(alto, ancho) + 3 * per, (alto, ancho)


def test_el_verificador_detecta_mallas_rotas():
    """Si `verificar_malla` no distinguiera, los demás tests no protegerían nada."""
    buena = _malla(12, 16)
    assert lf.verificar_malla(buena)["ok"]

    def con_caras(caras):
        return trimesh.Trimesh(vertices=buena.vertices, faces=caras, process=False)

    sin_una = con_caras(buena.faces[:-1])                                       # un agujero
    r = lf.verificar_malla(sin_una)
    assert not r["ok"] and not r["watertight"] and not r["aristas_con_dos_caras"]
    dada_vuelta = buena.faces.copy()
    dada_vuelta[5] = dada_vuelta[5][::-1]                                        # una cara con el sentido invertido
    r = lf.verificar_malla(con_caras(dada_vuelta))
    assert not r["ok"] and not r["winding_consistente"]
    r = lf.verificar_malla(con_caras(np.vstack([buena.faces, buena.faces[:1]])))  # una cara duplicada
    assert not r["ok"] and r["caras_duplicadas"] == 1 and not r["aristas_con_dos_caras"]
    colapsada = buena.faces.copy()
    colapsada[3] = colapsada[3][[0, 0, 1]]                                       # un triángulo de área cero
    r = lf.verificar_malla(con_caras(colapsada))
    assert not r["ok"] and r["caras_degeneradas"] >= 1
    sobrante = lf.verificar_malla(trimesh.Trimesh(vertices=np.vstack([buena.vertices, [[0, 0, 0]]]), faces=buena.faces, process=False))
    assert sobrante["euler"] == 3 and not sobrante["ok"]                          # un vértice suelto rompe Euler


# --- 2. grosor medido sobre la malla -------------------------------------------------------------

def test_los_vertices_tienen_el_grosor_pedido_y_el_fondo_es_plano():
    for alto, ancho in ((20, 30), (2, 9)):
        g = _grosor_al_azar(alto, ancho, 4)
        m = lf.malla_desde_grilla_grosor(g, 15.0, 10.0)
        assert np.array_equal(m.vertices[: alto * ancho, 2], g.ravel())          # exacto
        assert (m.vertices[alto * ancho:, 2] == 0.0).all()                        # el resto (trasera) en z = 0
        xs, ys = np.linspace(0, 15.0, ancho), np.linspace(10.0, 0, alto)
        x, y = np.meshgrid(xs, ys)
        assert np.array_equal(m.vertices[: alto * ancho, 0], x.ravel()) and np.array_equal(m.vertices[: alto * ancho, 1], y.ravel())


def test_el_grosor_medido_con_rayos_verticales_es_el_pedido():
    """Sin mirar la construcción: rayos de arriba abajo en los vértices interiores (con un desvío mínimo
    para no pegarle a una arista) y en puntos al azar dentro de las celdas."""
    alto, ancho, w, h = 18, 25, 12.0, 8.5
    g = _suave(alto, ancho, 3)
    dx, dy = w / (ancho - 1), h / (alto - 1)
    for diagonal in lf.DIAGONALES:
        m = lf.malla_desde_grilla_grosor(g, w, h, diagonal=diagonal)
        # vértices interiores
        puntos, esperado = [], []
        for j in range(1, alto - 1):
            for i in range(1, ancho - 1):
                puntos.append((i * dx + 3e-6, h - j * dy - 2e-6))
                esperado.append(g[j, i])
        medido = _espesor_por_rayos(m, puntos)
        assert np.abs(medido - np.array(esperado)).max() < 1e-3, f"{diagonal}: error en los vértices"
        # puntos al azar dentro de las celdas, lejos de las diagonales: se compara con la interpolación del triángulo
        azar = np.random.default_rng(7)
        puntos, esperado = [], []
        while len(puntos) < 300:
            j, i = azar.integers(0, alto - 1), azar.integers(0, ancho - 1)
            u, v = azar.random(2) * 0.9 + 0.05
            if abs(u - v) < 0.05 or abs(u + v - 1) < 0.05:
                continue
            puntos.append((i * dx + u * dx, h - j * dy - v * dy))
            esperado.append(_z_esperado(g, j, i, u, v, diagonal))
        medido = _espesor_por_rayos(m, puntos)
        assert np.abs(medido - np.array(esperado)).max() < 1e-9, f"{diagonal}: error dentro de las celdas"


def test_de_punta_a_punta_lo_oscuro_es_grueso_y_alto_L1_L2_L3():
    with _carpeta() as d:
        ruta = os.path.join(d, "mitad.png")
        arr = np.full((20, 40), 255, dtype=np.uint8)
        arr[:, :20] = 0                                                           # izquierda NEGRA, derecha BLANCA
        Image.fromarray(arr).save(ruta)
        grosor = lf.brillo_a_grosor(lf.imagen_a_mapa_brillo(ruta, ancho_mm=40, px_por_mm=1.0))
        relieve = lf.malla_desde_grosor(grosor)                                   # cara_visible="relieve"
        izq, der = _espesor_por_rayos(relieve, [(10.0, 10.0), (30.0, 10.0)])
        assert abs(izq - 2.8) < 1e-6 and abs(der - 0.8) < 1e-6, (izq, der)        # lo negro, grueso; lo blanco, fino
        v = relieve.vertices[: 20 * 40]
        assert v[v[:, 0] < 15, 2].min() > v[v[:, 0] > 25, 2].max(), "los vértices oscuros no están más altos"
        plana = lf.malla_desde_grosor(grosor, cara_visible="plana")               # espejada en X
        izq, der = _espesor_por_rayos(plana, [(10.0, 10.0), (30.0, 10.0)])
        assert abs(izq - 0.8) < 1e-6 and abs(der - 2.8) < 1e-6, (izq, der)
        negativo = lf.brillo_a_grosor(lf.imagen_a_mapa_brillo(ruta, ancho_mm=40, px_por_mm=1.0, invertir=True))
        izq, der = _espesor_por_rayos(lf.malla_desde_grosor(negativo), [(10.0, 10.0), (30.0, 10.0)])
        assert abs(izq - 0.8) < 1e-6 and abs(der - 2.8) < 1e-6, "el negativo no invirtió el relieve"


# --- 3. volumen -----------------------------------------------------------------------------------

def test_volumen_exacto_en_plano_constante_e_inclinados():
    w, h, ancho, alto = 15.0, 10.0, 60, 40
    constante = lf.malla_desde_grilla_grosor(np.full((alto, ancho), 1.7), w, h)
    assert abs(constante.volume - w * h * 1.7) < 1e-9
    x = np.linspace(0, w, ancho)
    inclinado_x = lf.malla_desde_grilla_grosor(np.tile(0.8 + 2.0 * x / w, (alto, 1)), w, h)
    assert abs(inclinado_x.volume - w * h * 1.8) < 1e-9                           # un plano se triangula sin error
    y = np.linspace(h, 0, alto)                                                    # fila 0 = arriba = y alto
    inclinado_y = lf.malla_desde_grilla_grosor(np.tile((0.8 + 2.0 * y / h)[:, None], (1, ancho)), w, h)
    assert abs(inclinado_y.volume - w * h * 1.8) < 1e-9


def test_volumen_de_una_superficie_irregular_contra_la_formula_por_triangulo():
    w, h = 15.0, 10.0
    g = _suave(40, 60, 5)
    za, zb, zc, zd = g[:-1, :-1], g[:-1, 1:], g[1:, :-1], g[1:, 1:]
    area_media = (w / 59) * (h / 39) / 2
    v_ad = area_media * ((za + zc + zd) / 3 + (za + zd + zb) / 3)
    v_bc = area_media * ((za + zc + zb) / 3 + (zb + zc + zd) / 3)
    for diagonal in lf.DIAGONALES:
        usar_ad = np.ones_like(za, dtype=bool) if diagonal == "fija" else np.abs(za - zd) <= np.abs(zb - zc)
        esperado = np.where(usar_ad, v_ad, v_bc).sum()
        m = lf.malla_desde_grilla_grosor(g, w, h, diagonal=diagonal)
        assert abs(m.volume - esperado) < 1e-9 * esperado, diagonal
        trapecio = (w / 59) * (h / 39) * ((za + zb + zc + zd) / 4).sum()           # y la regla del trapecio está muy cerca
        assert abs(m.volume - trapecio) / trapecio < 1e-3


# --- 4. dimensiones y orientación ---------------------------------------------------------------------

def test_la_placa_mide_exactamente_lo_pedido():
    for alto, ancho in FORMAS:
        g = _grosor_al_azar(alto, ancho)
        m = lf.malla_desde_grilla_grosor(g, 37.5, 22.25)
        assert np.array_equal(m.bounds[0], [0.0, 0.0, 0.0])
        assert np.array_equal(m.bounds[1], [37.5, 22.25, g.max()])
        assert (m.vertices[:, 2] >= 0).all() and m.vertices[:, 2].min() == 0.0


def test_las_normales_miran_hacia_afuera():
    for diagonal in lf.DIAGONALES:
        alto, ancho = 17, 25
        m = lf.malla_desde_grilla_grosor(_suave(alto, ancho, 2), 12.0, 8.5, diagonal=diagonal)
        frente, per = _caras_del_frente(alto, ancho), _perimetro_cuenta(alto, ancho)
        n = m.face_normals
        assert (n[:frente, 2] > 0).all(), "el frente tiene que mirar a +Z"
        assert np.allclose(n[-per:, 2], -1.0) and np.allclose(n[-per:, :2], 0.0), "la trasera tiene que mirar a -Z"
        paredes = slice(frente, frente + 2 * per)
        assert np.allclose(n[paredes, 2], 0.0), "las paredes son verticales"
        centro = np.array([6.0, 4.25])
        hacia_afuera = ((m.triangles_center[paredes, :2] - centro) * n[paredes, :2]).sum(axis=1)
        assert (hacia_afuera > 0).all(), "hay paredes que miran hacia adentro"


def test_cara_visible_relieve_no_espeja_y_plana_espeja_x():
    g = np.full((6, 8), 1.0)
    g[0, 0] = 2.5                                                                   # un marcador grueso: esquina superior izquierda de la foto
    for cara, x_esperado in (("relieve", 0.0), ("plana", 8.0)):
        m = lf.malla_desde_grilla_grosor(g, 8.0, 6.0, cara_visible=cara)
        marcado = m.vertices[: 6 * 8][m.vertices[: 6 * 8, 2] > 2.0]
        assert marcado.shape == (1, 3) and marcado[0, 0] == x_esperado and marcado[0, 1] == 6.0, (cara, marcado)


def test_la_fila_0_queda_arriba_y_no_se_invierte_en_vertical():
    g = np.full((6, 8), 1.0)
    g[0, :] = 2.5                                                                   # la fila de arriba de la foto
    m = lf.malla_desde_grilla_grosor(g, 8.0, 6.0)
    alto = m.vertices[: 48][m.vertices[: 48, 2] > 2.0]
    assert alto.shape == (8, 3) and (alto[:, 1] == 6.0).all()


def test_la_diagonal_adaptativa_sigue_la_cresta_y_la_fija_no():
    #  a b       Los vértices son a=0, b=1, c=2, d=3. Se elige la diagonal con MENOR salto de altura:
    #  c d       a-d si |a - d| <= |b - c|, y b-c si no.
    por_a_d = np.array([[2.0, 1.0], [3.0, 2.0]])        # a = d (salto 0) frente a |b - c| = 2: va por a-d
    por_b_c = np.array([[1.0, 2.0], [2.0, 3.0]])        # b = c (salto 0) frente a |a - d| = 2: va por b-c
    empate = np.array([[1.0, 2.0], [2.0, 1.0]])         # los dos saltos valen 0: gana a-d
    por_a_d_caras, por_b_c_caras = ({0, 2, 3}, {0, 3, 1}), ({0, 2, 1}, {1, 2, 3})
    for g, esperadas in ((por_a_d, por_a_d_caras), (por_b_c, por_b_c_caras), (empate, por_a_d_caras)):
        m = lf.malla_desde_grilla_grosor(g, 1.0, 1.0, diagonal="adaptativa")
        assert [set(map(int, c)) for c in m.faces[:2]] == list(esperadas), g
    fija = lf.malla_desde_grilla_grosor(por_b_c, 1.0, 1.0, diagonal="fija")           # la fija ignora la cresta
    assert [set(map(int, c)) for c in fija.faces[:2]] == list(por_a_d_caras)


# --- 5. vectorizado: cero bucles y rendimiento -------------------------------------------------------------

FUNCIONES_VECTORIZADAS = ("_validar_grilla_grosor", "_caras_del_frente", "_perimetro", "malla_desde_grilla_grosor",
                          "malla_desde_grosor", "verificar_malla")
PROHIBIDOS = (ast.For, ast.AsyncFor, ast.While, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


def _construcciones_prohibidas(fuente, nombres):
    arbol = ast.parse(fuente)
    funciones = {n.name: n for n in ast.walk(arbol) if isinstance(n, ast.FunctionDef)}
    faltan = [n for n in nombres if n not in funciones]
    assert not faltan, f"no encuentro las funciones {faltan}: el test no estaría comprobando nada"
    encontrados = []
    for nombre in nombres:
        for nodo in ast.walk(funciones[nombre]):
            if isinstance(nodo, PROHIBIDOS):
                encontrados.append((nombre, type(nodo).__name__, nodo.lineno))
    return encontrados


def test_no_hay_ningun_bucle_en_el_codigo_de_la_malla():
    with open("core/litofania.py", encoding="utf-8") as f:
        fuente = f.read()
    assert _construcciones_prohibidas(fuente, FUNCIONES_VECTORIZADAS) == []


def test_el_chequeo_de_bucles_de_verdad_detecta_bucles():
    """Que el test de arriba no pase en vacío: sobre código con bucles tiene que saltar."""
    con_bucles = (
        "def f(x):\n    for i in x:\n        pass\n"
        "def g(x):\n    while x:\n        x -= 1\n"
        "def h(x):\n    return [i for i in x]\n"
        "def k(x):\n    return sum(i for i in x)\n"
        "def limpia(x):\n    return x + 1\n")
    encontrados = _construcciones_prohibidas(con_bucles, ("f", "g", "h", "k", "limpia"))
    assert sorted({nombre for nombre, _, _ in encontrados}) == ["f", "g", "h", "k"], encontrados


def test_800x1000_se_arma_en_segundos_con_memoria_acotada():
    g = _suave(1000, 800, 1)
    lf.malla_desde_grilla_grosor(_suave(50, 40), 10.0, 12.0)                    # calienta imports
    tracemalloc.start()
    t0 = time.perf_counter()
    m = lf.malla_desde_grilla_grosor(g, 200.0, 250.0)
    segundos = time.perf_counter() - t0
    pico_mb = tracemalloc.get_traced_memory()[1] / 1e6
    tracemalloc.stop()
    assert len(m.faces) == _caras_del_frente(1000, 800) + 3 * _perimetro_cuenta(1000, 800) == 1_607_190
    assert segundos < 5.0, f"armar 800x1000 tardó {segundos:.2f} s (medido en desarrollo: ~0,07 s; el cargador viejo, minutos)"
    assert pico_mb < 600, f"el pico de memoria fue {pico_mb:.0f} MB (medido en desarrollo: ~130 MB)"


def test_el_tiempo_crece_linealmente_con_los_puntos_no_con_su_cuadrado():
    """16 veces más puntos no pueden costar mucho más de 16 veces (un bucle por píxel o algo O(n²) lo rompería)."""
    chica, grande = _suave(250, 200, 1), _suave(1000, 800, 1)
    lf.malla_desde_grilla_grosor(chica, 50.0, 62.5)

    def mejor_tiempo(g, w, h):
        tiempos = []
        for _ in range(3):
            t0 = time.perf_counter()
            lf.malla_desde_grilla_grosor(g, w, h)
            tiempos.append(time.perf_counter() - t0)
        return min(tiempos)
    t_chica, t_grande = mejor_tiempo(chica, 50.0, 62.5), mejor_tiempo(grande, 200.0, 250.0)
    assert t_grande < 60 * max(t_chica, 1e-3), f"{t_chica:.4f}s -> {t_grande:.4f}s para 16x los puntos"


def test_verificar_la_malla_grande_tambien_cierra():
    m = lf.malla_desde_grilla_grosor(_suave(1000, 800, 2), 200.0, 250.0)
    r = lf.verificar_malla(m)
    assert r["ok"] and r["euler"] == 2 and r["caras"] == 1_607_190


# --- 6. STL y booleanas (lo que viene después) ---------------------------------------------------------------

def test_ida_y_vuelta_por_stl_sigue_cerrada_con_el_mismo_volumen():
    m = lf.malla_desde_grilla_grosor(_suave(80, 100, 6), 25.0, 20.0)
    with _carpeta() as d:
        ruta = os.path.join(d, "placa.stl")
        m.export(ruta)
        assert os.path.getsize(ruta) == 84 + 50 * len(m.faces)                       # STL binario: 84 bytes + 50 por triángulo
        leida = trimesh.load(ruta)
        assert leida.is_watertight and leida.is_winding_consistent
        assert abs(leida.volume - m.volume) / m.volume < 1e-5                         # float32 al exportar
        assert lf.verificar_malla(leida)["ok"]


def test_sigue_cerrada_al_pegarle_un_marco_y_hacerle_un_agujero():
    """Lo que hará L8: unión y resta booleana (manifold) con la placa, incluido el abanico del fondo."""
    w, h, t = 15.0, 20.0, 1.7
    placa = lf.malla_desde_grilla_grosor(np.full((80, 60), t), w, h)
    marco = trimesh.creation.box(extents=[w + 4, h + 4, 0.6])
    marco.apply_translation([w / 2, h / 2, 0.3])                                       # se superpone con el fondo de la placa
    union = trimesh.boolean.union([placa, marco], engine="manifold")
    assert union.is_watertight
    esperado_union = placa.volume + marco.volume - w * h * 0.6                           # intersección: la placa por debajo de z = 0,6
    assert abs(union.volume - esperado_union) < 1e-6 * esperado_union                    # manifold trabaja en float32
    cilindro = trimesh.creation.cylinder(radius=1.5, height=10)
    cilindro.apply_translation([w / 2, h / 2, 1.0])
    con_agujero = trimesh.boolean.difference([placa, cilindro], engine="manifold")
    assert con_agujero.is_watertight
    esperado_resta = placa.volume - cilindro.volume / 10 * t                             # el cilindro atraviesa todo el espesor
    assert abs(con_agujero.volume - esperado_resta) < 1e-6 * esperado_resta
    irregular = lf.malla_desde_grilla_grosor(_suave(120, 90, 3), 22.0, 30.0)
    marco2 = trimesh.creation.box(extents=[26, 34, 0.8])
    marco2.apply_translation([11.0, 15.0, 0.4])
    assert trimesh.boolean.union([irregular, marco2], engine="manifold").is_watertight


# --- 7. errores, entrada intacta, integración ---------------------------------------------------------------

def test_entradas_invalidas_dan_error():
    bueno = _grosor_al_azar(5, 6)
    malos = [
        dict(grosor=np.ones((1, 6))), dict(grosor=np.ones((6, 1))), dict(grosor=np.ones(6)), dict(grosor=np.ones((3, 3, 3))),
        dict(grosor=np.where(bueno > 0, np.nan, 0)), dict(grosor=np.where(bueno > 0, np.inf, 0)),
        dict(grosor=bueno - 5.0), dict(grosor=np.zeros((5, 6))),
        dict(grosor=bueno, ancho_mm=0), dict(grosor=bueno, alto_mm=-1),
        dict(grosor=bueno, cara_visible="atras"), dict(grosor=bueno, diagonal="doble"),
    ]
    for kwargs in malos:
        args = dict(grosor=bueno, ancho_mm=10.0, alto_mm=10.0)
        args.update(kwargs)
        try:
            lf.malla_desde_grilla_grosor(**args)
        except ValueError:
            continue
        raise AssertionError(f"{ {k: (v.shape if hasattr(v, 'shape') else v) for k, v in kwargs.items()} } tenía que fallar con ValueError")
    try:
        lf.malla_desde_grosor(bueno)
    except TypeError:
        return
    raise AssertionError("malla_desde_grosor necesita un MapaGrosor")


def test_la_entrada_no_se_modifica():
    g = _grosor_al_azar(20, 30)
    antes = g.copy()
    for cara in lf.CARAS_VISIBLES:
        for diagonal in lf.DIAGONALES:
            lf.malla_desde_grilla_grosor(g, 15.0, 10.0, cara_visible=cara, diagonal=diagonal)
            assert np.array_equal(g, antes), f"se modificó el grosor con {cara}/{diagonal}"
    with _carpeta() as d:
        ruta = os.path.join(d, "r.png")
        Image.fromarray(np.tile(np.linspace(0, 255, 40).astype(np.uint8), (20, 1))).save(ruta)
        mapa = lf.brillo_a_grosor(lf.imagen_a_mapa_brillo(ruta, ancho_mm=40, px_por_mm=1.0))
        grosor_antes = mapa.grosor.copy()
        m = lf.malla_desde_grosor(mapa, cara_visible="plana")
        assert np.array_equal(mapa.grosor, grosor_antes)
        m.vertices[:] = 0.0                                                            # tocar la malla no toca el mapa
        assert np.array_equal(mapa.grosor, grosor_antes)


def test_malla_desde_grosor_usa_el_tamano_del_mapa_de_L2():
    with _carpeta() as d:
        ruta = os.path.join(d, "r.png")
        Image.fromarray(np.tile(np.linspace(0, 255, 80).astype(np.uint8), (40, 1))).save(ruta)
        mapa_brillo = lf.imagen_a_mapa_brillo(ruta, ancho_mm=80, alto_mm=40, px_por_mm=1.0)
        mapa = lf.brillo_a_grosor(mapa_brillo, grosor_min=0.84, grosor_max=3.1, capa_mm=0.12)
        m = lf.malla_desde_grosor(mapa)
        assert np.array_equal(m.bounds[1], [mapa.ancho_mm, mapa.alto_mm, mapa.grosor.max()])
        assert lf.verificar_malla(m)["ok"]
        assert abs(m.vertices[: 40 * 80, 2].max() - mapa.grosor_max_efectivo) < 1e-12


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]
    fallas = 0
    for t in tests:
        try:
            t()
            print(f"OK   {t.__name__}")
        except AssertionError as e:
            fallas += 1
            print(f"FALLA {t.__name__}: {e}")
    print()
    if fallas:
        print(f"{fallas} de {len(tests)} tests fallaron.")
        sys.exit(1)
    print(f"Los {len(tests)} tests pasaron.")
