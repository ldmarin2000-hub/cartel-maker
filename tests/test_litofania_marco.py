#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_litofania_marco.py
-----------------------------
Red de regresión para L8 de la litofanía: el marco (`core/litofania_marco.py` y `generators/marco_litofania.py`).
Son dos piezas, la PLACA (la litofanía con una banda opaca) y el MARCO (ventana del tamaño de la imagen + bolsillo
atrás con holgura). Todo se mide sobre las MALLAS con rayos (numpy puro, verticales y horizontales), sin mirar
cómo se armaron. Lo que se cuida:

  * la ventana es la imagen EXACTA: rayos dentro de la ventana no pegan en el marco, justo afuera dan la ceja; y
    con la placa puesta, el marco no pisa la foto (el grosor de la imagen es el de L4, intacto);
  * entre la placa y el bolsillo hay `holgura` por lado (rayos horizontales), y con holgura = 0 la intersección
    booleana placa ∩ marco tiene volumen 0 (con una placa corrida de más, no);
  * las dos piezas son watertight (y el volumen del marco es el de la fórmula) y los STL de impresión son el
    ensamble girado (ceja contra la cama);
  * A1 por pieza (el marco manda), `main.py` lo lista, `ejecutar()` corre, los errores no escriben nada;
  * L1-L5 y L7 no dependen del marco.

No usa pytest (ver AGENTS.md "Testing") -- funciones `test_*` con `assert` simple,
corribles con `python tests/test_litofania_marco.py`.
"""
import builtins
import contextlib
import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import trimesh
from PIL import Image

from core import litofania as lf
from core import litofania_marco as marco
from generators import marco_litofania as gen

TOL = 1e-5            # los STL guardan float32


# --- ayudas ---------------------------------------------------------------------------------

@contextlib.contextmanager
def _carpeta():
    with tempfile.TemporaryDirectory() as d:
        yield d


def _imagen(d, ancho_px=80, alto_px=60, nombre="foto.png"):
    """Una imagen con relieve (degradé más una mancha): que el grosor cambie de punto en punto."""
    y, x = np.mgrid[0:alto_px, 0:ancho_px]
    g = 255 * (0.15 + 0.7 * x / (ancho_px - 1)) * (0.6 + 0.4 * np.cos(y / 5.0))
    ruta = os.path.join(d, nombre)
    Image.fromarray(np.clip(g, 0, 255).astype(np.uint8)).save(ruta)
    return ruta


_CACHE = {}


def _armar(**kw):
    """`generar()` de una foto chica en una carpeta temporal y las mallas en las coordenadas del ENSAMBLE:
    `(r, placa_ensamblada, marco_ensamblado)`. Cachea por argumentos. Es rápido (40 x 30 mm a 2 px/mm)."""
    kw = dict(dict(ancho_mm=40.0, px_por_mm=2.0), **kw)
    clave = tuple(sorted(kw.items()))
    if clave not in _CACHE:
        with _carpeta() as d:
            r = gen.generar(_imagen(d), carpeta_salida=d, **kw)
            placa = trimesh.load(r["ruta_stl_placa"])
            impresion = trimesh.load(r["ruta_stl_marco"])
        geo = r["geometria"]
        placa_ens = marco.ensamblar_placa(placa, geo, kw.get("cara_visible", "relieve"))
        marco_ens = marco.malla_del_marco(geo)
        _CACHE[clave] = (r, placa_ens, marco_ens, placa, impresion)
    return _CACHE[clave]


_PERM = {0: (1, 2, 0), 1: (2, 0, 1), 2: (0, 1, 2)}


def _golpes(malla, eje, a, b):
    """z de todos los impactos de un rayo paralelo a `eje` contra TODOS los triángulos, ordenados. El rayo pasa por
    (a, b) en los otros dos ejes (ciclo x -> y -> z: eje 0: (y, z); eje 1: (z, x); eje 2: (x, y)). Numpy puro, misma
    técnica que tests/test_litofania_malla.py: un rayo corta un triángulo en el punto cuya proyección cae adentro
    de la del triángulo, y se interpola. Los triángulos paralelos al rayo se descartan."""
    p0, p1, p2 = _PERM[eje]
    tri = malla.triangles[:, :, [p0, p1, p2]]
    A, B, C = tri[:, 0], tri[:, 1], tri[:, 2]
    v1, v0 = B[:, :2] - A[:, :2], C[:, :2] - A[:, :2]
    d = v1[:, 0] * v0[:, 1] - v1[:, 1] * v0[:, 0]
    ok = np.abs(d) > 1e-12
    w = np.array([a, b]) - A[:, :2]
    with np.errstate(divide="ignore", invalid="ignore"):
        s = (w[:, 0] * v0[:, 1] - w[:, 1] * v0[:, 0]) / d
        t = (v1[:, 0] * w[:, 1] - v1[:, 1] * w[:, 0]) / d
        dentro = ok & (s >= -1e-12) & (t >= -1e-12) & (s + t <= 1 + 1e-12)
        z = A[:, 2] + s * (B[:, 2] - A[:, 2]) + t * (C[:, 2] - A[:, 2])
    return np.sort(z[dentro])


def _vertical(malla, x, y):
    return _golpes(malla, 2, x, y)


def _espesor(malla, x, y):
    h = _vertical(malla, x, y)
    assert len(h) == 2, f"el rayo en {(x, y)} dio {len(h)} impactos: {h}"
    return h[1] - h[0]


def _bandas(placa, ancho=40.0, alto=30.0):
    """Banda en X y en Y de la placa, medida sobre su malla (la banda se redondea al píxel y puede diferir un poco)."""
    ext = placa.bounds[1] - placa.bounds[0]
    return (ext[0] - ancho) / 2, (ext[1] - alto) / 2


def _juntas(*mallas):
    return trimesh.util.concatenate(list(mallas))


def _volumen_interseccion(a, b):
    r = trimesh.boolean.intersection([a, b], engine="manifold")
    if r is None or len(r.faces) == 0:
        return 0.0
    with np.errstate(all="ignore"):
        v = float(r.volume)
    return v if np.isfinite(v) else 0.0


# ---------------------------------------------------------------------------
#  (1) la ventana es la imagen exacta y el marco no pisa la foto
# ---------------------------------------------------------------------------

def test_la_ventana_es_la_imagen_exacta_rayos_adentro_no_pegan_y_justo_afuera_dan_la_ceja():
    r, placa, marco_ens, _, _ = _armar()
    W, H = 40.0, 30.0                                                     # lo pedido: la imagen mide 40 x 30 mm
    bx, by = _bandas(placa)                                              # medidas sobre la placa, no sacadas del código
    x0, y0, x1, y1 = bx, by, bx + W, by + H                              # la ventana tiene que ser justo esto
    D, profundidad, ceja = 4.0, 2.8, 1.2
    rng = np.random.default_rng(0)
    for _ in range(300):                                                  # adentro: nada de marco
        x, y = rng.uniform(x0 + 0.01, x1 - 0.01), rng.uniform(y0 + 0.01, y1 - 0.01)
        assert len(_vertical(marco_ens, x, y)) == 0, (x, y)
    e = 0.05                                                              # justo adentro de cada borde: nada
    for x, y in ((x0 + e, 15.3), (x1 - e, 15.3), (20.1, y0 + e), (20.1, y1 - e), (x0 + e, y0 + e), (x1 - e, y1 - e)):
        assert len(_vertical(marco_ens, x, y)) == 0, (x, y)
    for x, y in ((x0 - e, 15.3), (x1 + e, 15.3), (20.1, y0 - e), (20.1, y1 + e), (x0 - e, y0 - e), (x1 + e, y1 + e)):
        h = _vertical(marco_ens, x, y)                                    # justo afuera: la ceja
        assert len(h) == 2 and abs(h[0] - profundidad) < TOL and abs(h[1] - D) < TOL, (x, y, h)
        assert abs((h[1] - h[0]) - ceja) < TOL
    # y el borde queda en su lugar: con 0,05 mm de margen a cada lado, la ventana mide 40 x 30 (no 39,9 ni 40,1)
    xs = np.linspace(x0 - 1, x1 + 1, 4001)
    abierto = [len(_vertical(marco_ens, x, 15.3)) == 0 for x in xs]
    ancho_abierto = xs[np.array(abierto)].max() - xs[np.array(abierto)].min()
    assert abs(ancho_abierto - W) < 2 * (xs[1] - xs[0]), ancho_abierto


def test_el_marco_no_pisa_la_foto_y_el_grosor_de_la_imagen_es_el_de_l4():
    r, placa, marco_ens, _, _ = _armar()
    junto = _juntas(placa, marco_ens)
    bx, by = _bandas(placa)
    l4 = lf.malla_desde_grosor(r["mapa_grosor"])                         # la placa de L4, sin banda ni marco
    rng = np.random.default_rng(1)
    for _ in range(200):
        x, y = rng.uniform(0.02, 39.98), rng.uniform(0.02, 29.98)
        e_junto = _espesor(junto, bx + x, by + y)                   # placa + marco: solo 2 impactos, los de la placa
        assert abs(e_junto - _espesor(l4, x, y)) < TOL, (x, y)
    # la banda es opaca (al grosor máximo) y ahí SÍ está el marco encima (2 impactos de la placa + 2 de la ceja)
    for x, y in ((bx / 2 + 0.0371, 15.0713), (bx + 40.0 + bx / 2 + 0.0371, 15.3713), (20.1371, by / 2 + 0.0713), (20.1371, by + 30.0 + by / 2 + 0.0713)):
        assert abs(_espesor(placa, x, y) - 2.8) < TOL
        assert len(_vertical(junto, x, y)) == 4
    # la ceja apoya sobre la banda: toca la placa justo en su cara de arriba
    h = _vertical(junto, bx / 2 + 0.0371, 15.0713)
    assert abs(h[1] - 2.8) < TOL and abs(h[2] - 2.8) < TOL and abs(h[3] - 4.0) < TOL


def test_con_cara_plana_la_placa_queda_dada_vuelta_y_la_foto_igual_de_libre():
    r, placa, marco_ens, _, _ = _armar(cara_visible="plana")
    r0, placa0, _, _, _ = _armar()
    junto = _juntas(placa, marco_ens)
    bx, by = _bandas(placa)
    rng = np.random.default_rng(2)
    for _ in range(120):
        x, y = rng.uniform(bx + 0.02, bx + 39.98), rng.uniform(by + 0.02, by + 29.98)
        h = _vertical(junto, x, y)                                        # la cara lisa contra la ceja: arriba en el fondo del bolsillo
        t = _espesor(placa0, x, y)                                        # y de la imagen, lo mismo que con relieve
        assert len(h) == 2 and abs(h[1] - 2.8) < TOL and abs(h[1] - h[0] - t) < TOL, (x, y, h, t)
    assert r["watertight"] and r["verificacion"]["placa"]["ok"]
    assert np.abs(placa.bounds - np.array([[0, 0, 0], [placa.bounds[1][0], placa.bounds[1][1], 2.8]])).max() < TOL
    assert any("dada vuelta" in n for n in r["info"])


# ---------------------------------------------------------------------------
#  (2) la holgura
# ---------------------------------------------------------------------------

def _huecos(placa, marco_ens, eje, a, b):
    """Con un rayo horizontal por el medio del bolsillo: los impactos son pared exterior, pared del bolsillo, placa,
    placa, pared del bolsillo, pared exterior. Devuelve (juego_a_un_lado, juego_al_otro, ancho_del_bolsillo, ancho_de_placa)."""
    h = _golpes(_juntas(placa, marco_ens), eje, a, b)
    assert len(h) == 6, h
    return h[2] - h[1], h[4] - h[3], h[4] - h[1], h[3] - h[2]


def test_entre_la_placa_y_el_bolsillo_hay_dos_veces_la_holgura_en_cada_eje():
    for holgura in (0.25, 0.5, 1.0, 0.1):
        r, placa, marco_ens, _, _ = _armar(holgura=holgura)
        z = 0.4                                                            # por debajo del grosor mínimo (0,8): solo las paredes
        izq, der, ancho_bolsillo, ancho_placa = _huecos(placa, marco_ens, 0, 17.3, z)            # rayo en X, a y = 17,3
        assert abs(izq - holgura) < TOL and abs(der - holgura) < TOL, (holgura, izq, der)
        assert abs((ancho_bolsillo - ancho_placa) - 2 * holgura) < TOL
        assert abs(ancho_placa - (40.0 + 2 * r["banda_x"])) < TOL
        aba, arr, alto_bolsillo, alto_placa = _huecos(placa, marco_ens, 1, z, 21.7)               # rayo en Y, a x = 21,7
        assert abs(aba - holgura) < TOL and abs(arr - holgura) < TOL, (holgura, aba, arr)
        assert abs((alto_bolsillo - alto_placa) - 2 * holgura) < TOL


def test_con_holgura_cero_la_interseccion_placa_marco_es_volumen_cero_y_con_una_placa_corrida_no():
    for kw in (dict(holgura=0.0), dict(holgura=0.25), dict(holgura=0.25, cara_visible="plana"), dict(holgura=0.0, ancho_borde=12.0)):
        r, placa, marco_ens, _, _ = _armar(**kw)
        assert _volumen_interseccion(placa, marco_ens) < 1e-9, kw
    # con holgura 0 las paredes de la placa y del bolsillo coinciden (rayo horizontal: juego 0)
    r, placa, marco_ens, _, _ = _armar(holgura=0.0)
    izq, der, _, _ = _huecos(placa, marco_ens, 0, 17.3, 0.4)
    assert abs(izq) < TOL and abs(der) < TOL
    # control positivo: el test SÍ detecta una superposición (placa corrida más que la holgura contra la pared)
    r, placa, marco_ens, _, _ = _armar(holgura=0.25)
    corrida = placa.copy()
    corrida.apply_translation([0.4, 0, 0])
    assert _volumen_interseccion(corrida, marco_ens) > 1.0
    corrida.apply_translation([-0.4 + 0.25, 0, 0])                         # justo hasta tocar la pared: sigue sin superponerse
    assert _volumen_interseccion(corrida, marco_ens) < 1e-9
    # y el relieve queda hasta la ceja: la placa al ras del dorso y contra el techo del bolsillo
    assert abs(placa.bounds[0][2]) < TOL and abs(placa.bounds[1][2] - r["geometria"].profundidad_bolsillo) < TOL


# ---------------------------------------------------------------------------
#  (3) las dos piezas son watertight; los STL de impresión
# ---------------------------------------------------------------------------

def test_las_dos_piezas_son_watertight_por_las_cuatro_vias():
    r, placa, marco_ens, placa_stl, marco_stl = _armar()
    assert r["watertight"] is True and r["watertight_placa"] is True and r["watertight_marco"] is True
    for nombre, v, malla, euler in (("placa", r["verificacion"]["placa"], placa_stl, 2), ("marco", r["verificacion"]["marco"], marco_stl, 0)):
        assert v["watertight"] and v["euler"] == euler, nombre          # la placa es una esfera topológica; el marco, un anillo (toro: 0)
        assert v["aristas_con_dos_caras"] and v["caras_degeneradas"] == 0 and v["caras_duplicadas"] == 0, nombre
        assert malla.is_watertight and malla.is_winding_consistent and malla.volume > 0, nombre
    assert lf.verificar_malla(placa_stl)["ok"] and lf.verificar_malla(placa)["ok"]
    assert lf.verificar_malla(marco_ens)["watertight"] and lf.verificar_malla(marco_ens)["euler"] == 0


def test_el_volumen_del_marco_es_el_de_la_formula():
    r, placa, marco_ens, _, marco_stl = _armar()
    g = r["geometria"]
    area = lambda rect: (rect[2] - rect[0]) * (rect[3] - rect[1])
    # caja exterior - ventana pasante - (bolsillo - ventana) a la profundidad del bolsillo
    esperado = (area(g.exterior) * g.profundidad_total - area(g.ventana) * g.profundidad_total
                - (area(g.bolsillo) - area(g.ventana)) * g.profundidad_bolsillo)
    assert abs(marco_ens.volume - esperado) < 1e-6 * esperado
    # lo mismo con medidas escritas acá aparte (imagen 40 x 30, borde 8, ceja 1,2, banda b, holgura 0,25, profundidad 2,8)
    b, h = r["banda_x"], 0.25
    ext = (40 + 16) * (30 + 16)                                            # (banda_y ~ banda_x: dentro de la media centésima)
    assert abs(g.ancho_marco - 56.0) < 1e-9 and abs(g.alto_marco - 46.0) < 1e-9 and abs(ext - area(g.exterior)) < 1e-9
    assert abs(marco_stl.volume - marco_ens.volume) < 1e-4 * marco_ens.volume
    assert abs(r["profundidad_mm"] - 4.0) < 1e-9


def test_los_stl_de_impresion_son_el_ensamble_con_la_ceja_contra_la_cama():
    r, placa, marco_ens, placa_stl, marco_stl = _armar()
    g = r["geometria"]
    assert np.abs(marco_stl.bounds[0]).max() < TOL                                      # en el origen
    assert np.abs(marco_stl.bounds[1] - [56.0, 46.0, 4.0]).max() < TOL
    assert np.abs(placa_stl.bounds[0]).max() < TOL and abs(placa_stl.bounds[1][2] - 2.8) < TOL    # la placa, como L4: dorso contra la cama
    # con la ceja contra la cama: en la ceja el material va de z = 0 a 1,2, y el bolsillo queda abierto hacia arriba (z = 1,2 a 4)
    ex0 = g.banda_x - 8.0                                                               # esquina del marco, en el ensamble
    y = 23.0
    h = _vertical(marco_stl, 2.0, y)                                                    # la pared: a todo el alto
    assert len(h) == 2 and abs(h[0]) < TOL and abs(h[1] - 4.0) < TOL, h
    x_pared_bolsillo = -0.25 - ex0                                                      # la pared del bolsillo, en coordenadas de impresión
    h = _vertical(marco_stl, x_pared_bolsillo + 0.5, y)                                 # adentro del bolsillo, bajo la ceja
    assert len(h) == 2 and abs(h[0]) < TOL and abs(h[1] - 1.2) < TOL, h
    assert len(_vertical(marco_stl, 8.0 + 20.0, y)) == 0                                # la ventana sigue abierta
    # y los volúmenes de los STL son los del ensamble
    assert abs(placa_stl.volume - placa.volume) < 1e-4 * placa.volume


# ---------------------------------------------------------------------------
#  la banda (core)
# ---------------------------------------------------------------------------

def _mapa(alto=20, ancho=30, mm=0.5, grosor_max=2.8, semilla=3, mm_y=None):
    mm_y = mm if mm_y is None else mm_y
    g = 0.8 + 2.0 * np.random.default_rng(semilla).random((alto, ancho))
    return lf.MapaGrosor(g, (ancho - 1) * mm, (alto - 1) * mm_y, ancho, alto, 1 / mm, 0.8, grosor_max, 0.8, grosor_max,
                         0.05, 1.0, 0.5, True)


def test_la_banda_rodea_la_imagen_al_grosor_maximo_y_no_la_toca():
    m = _mapa()
    copia = m.grosor.copy()
    grilla, bx, by = marco.grilla_con_banda(m, 2.0)
    assert np.array_equal(m.grosor, copia)                                              # no modifica el mapa
    pad = 4                                                                             # 2,0 mm a 0,5 mm por píxel
    assert grilla.shape == (20 + 2 * pad, 30 + 2 * pad) and abs(bx - 2.0) < 1e-12 and abs(by - 2.0) < 1e-12
    assert np.array_equal(grilla[pad:-pad, pad:-pad], m.grosor)                         # la imagen, idéntica
    banda = np.ones(grilla.shape, bool)
    banda[pad:-pad, pad:-pad] = False
    assert (grilla[banda] == 2.8).all()                                                 # y la banda, al máximo
    # un máximo efectivo mayor que el de la imagen manda; un píxel de la imagen más grueso que el efectivo, también
    m2 = _mapa(grosor_max=3.3)
    assert marco.grilla_con_banda(m2, 2.0)[0][0, 0] == 3.3
    m3 = _mapa(grosor_max=1.0)
    assert marco.grilla_con_banda(m3, 2.0)[0][0, 0] == m3.grosor.max()
    # píxeles no cuadrados: la banda en X (0,5 mm por píxel) son 4 píxeles y en Y (0,25 mm por píxel) 8
    mn = _mapa(mm=0.5, mm_y=0.25)
    grilla, bx, by = marco.grilla_con_banda(mn, 2.0)
    assert grilla.shape == (20 + 16, 30 + 8) and abs(bx - 2.0) < 1e-12 and abs(by - 2.0) < 1e-12
    assert np.array_equal(grilla[8:-8, 4:-4], mn.grosor)
    grilla, bx, by = marco.grilla_con_banda(_mapa(mm=0.5, mm_y=0.4), 2.0)                  # 4 px en X y 5 en Y
    assert grilla.shape == (20 + 10, 30 + 8) and abs(bx - 2.0) < 1e-12 and abs(by - 2.0) < 1e-12
    # el ancho de banda se redondea al píxel y se informa el real
    _, bx, by = marco.grilla_con_banda(_mapa(mm=0.3), 1.0)
    assert abs(bx - 0.9) < 1e-12 and abs(by - 0.9) < 1e-12 or abs(bx - 1.2) < 1e-12
    _falla(marco.grilla_con_banda, m, 0, texto="margen_encastre")
    _falla(marco.grilla_con_banda, m, -1.0, texto="margen_encastre")
    try:
        marco.grilla_con_banda(m.grosor, 2.0)
    except TypeError:
        pass
    else:
        raise AssertionError("tenía que fallar con TypeError")


def test_ensamblar_placa_valida_la_cara_y_no_modifica_la_malla():
    r, placa, _, placa_stl, _ = _armar()
    antes = placa_stl.vertices.copy()
    _falla(marco.ensamblar_placa, placa_stl, r["geometria"], "atras", texto="cara_visible")
    for cara in lf.CARAS_VISIBLES:
        marco.ensamblar_placa(placa_stl, r["geometria"], cara)
    assert np.array_equal(placa_stl.vertices, antes)


def test_la_geometria_pone_la_ventana_la_placa_el_bolsillo_y_el_exterior_en_su_lugar():
    g = marco.geometria_del_marco(40.0, 30.0, 2.0, 2.0, 2.8)
    assert g.ventana == (2.0, 2.0, 42.0, 32.0) and g.placa == (0.0, 0.0, 44.0, 34.0)
    assert g.bolsillo == (-0.25, -0.25, 44.25, 34.25) and g.exterior == (-6.0, -6.0, 50.0, 40.0)
    assert (g.profundidad_bolsillo, g.profundidad_total, g.grosor_ceja) == (2.8, 4.0, 1.2)
    assert abs(g.pared - 5.75) < 1e-12 and abs(g.apoyo - 1.75) < 1e-12
    assert (g.ancho_marco, g.alto_marco) == (56.0, 46.0)
    g = marco.geometria_del_marco(100.0, 50.0, 2.1, 1.9, 3.0, ancho_borde=10.0, grosor_ceja=2.0, holgura=0.5)
    assert g.ventana == (2.1, 1.9, 102.1, 51.9) and abs(g.ancho_placa - 104.2) < 1e-12 and abs(g.alto_placa - 53.8) < 1e-12
    assert g.bolsillo == (-0.5, -0.5, 104.7, 54.3)
    assert abs(g.exterior[0] - (2.1 - 10)) < 1e-12 and abs(g.exterior[3] - (1.9 + 50 + 10)) < 1e-12
    assert abs(g.pared - (10 - 2.1 - 0.5)) < 1e-12 and abs(g.apoyo - (1.9 - 0.5)) < 1e-12 and g.profundidad_total == 5.0


def _falla(f, *args, texto=None, **kw):
    try:
        f(*args, **kw)
    except ValueError as e:
        assert texto is None or texto in str(e), (texto, str(e))
        return
    raise AssertionError(f"tenía que fallar con ValueError: {args} {kw}")


def test_parametros_absurdos_o_inimprimibles_fallan_con_valueerror_claro():
    G = marco.geometria_del_marco
    base = (40.0, 30.0, 2.0, 2.0, 2.8)
    _falla(G, 0, 30.0, 2.0, 2.0, 2.8, texto="imagen")
    _falla(G, 40.0, -1, 2.0, 2.0, 2.8, texto="imagen")
    _falla(G, 40.0, 30.0, 0, 2.0, 2.8, texto="banda")
    _falla(G, 40.0, 30.0, 2.0, 0, 2.8, texto="banda")
    _falla(G, *base[:4], 0, texto="grosor_placa")
    _falla(G, *base, ancho_borde=0, texto="ancho_borde")
    _falla(G, *base, ancho_borde=3.4, texto="pared")                       # pared = 3,4 - 2 - 0,25 = 1,15 < 1,2
    G(*base, ancho_borde=3.45)                                             # = 1,2: justo
    _falla(G, *base, grosor_ceja=0.7, texto="grosor_ceja")
    G(*base, grosor_ceja=0.8)
    _falla(G, *base, holgura=-0.1, texto="holgura")
    _falla(G, *base, holgura=2.1, texto="holgura")
    _falla(G, 40.0, 30.0, 4.0, 4.0, 2.8, ancho_borde=10.0, holgura=2.1, texto="entre 0 y 2")     # con banda de sobra: solo la holgura máxima
    G(40.0, 30.0, 4.0, 4.0, 2.8, ancho_borde=10.0, holgura=2.0)                                  # y 2,0 justo sí
    G(*base, ancho_borde=3.5, holgura=0.3)                                                       # pared exactamente 1,2: sí
    _falla(G, *base, holgura=1.1, texto="apoya")                           # la ceja apoyaría 0,9 < 1
    G(*base, holgura=1.0)
    _falla(G, 40.0, 30.0, 2.0, 1.5, 2.8, holgura=0.6, texto="apoya")       # cuenta la banda más chica
    _falla(G, 40.0, 30.0, 1.5, 2.0, 2.8, holgura=0.6, texto="apoya")
    _falla(G, 40.0, 30.0, 4.0, 2.0, 2.8, ancho_borde=5.0, texto="pared")   # la pared del eje X no alcanza (5 - 4 - 0,25)
    _falla(G, 40.0, 30.0, 2.0, 4.0, 2.8, ancho_borde=5.0, texto="pared")
    with _carpeta() as d:
        ruta = _imagen(d)
        sal = os.path.join(d, "sal")
        for kw, texto in ((dict(ancho_borde=3.0), "pared"), (dict(grosor_ceja=0.5), "ceja"), (dict(holgura=-1), "holgura"),
                          (dict(margen_encastre=0), "margen"), (dict(margen_encastre=1.0, holgura=0.5), "apoya"),
                          (dict(cara_visible="atras"), "cara_visible"), (dict(diagonal="x"), "diagonal"),
                          (dict(grosor_max=0.5), "grosor")):
            _falla(gen.generar, ruta, ancho_mm=40.0, px_por_mm=2.0, carpeta_salida=sal, **kw, texto=texto)
        assert not os.path.exists(sal)                                      # y no escribió nada
        try:
            gen.generar(os.path.join(d, "no_existe.png"), carpeta_salida=sal)
        except FileNotFoundError:
            pass
        else:
            raise AssertionError("tenía que fallar con FileNotFoundError")


# ---------------------------------------------------------------------------
#  (4) A1 por pieza (el marco manda), contrato y main.py
# ---------------------------------------------------------------------------

def test_a1_se_chequea_por_pieza_y_el_marco_manda():
    r, *_ = _armar()
    assert r["entra_a1"] is True and r["entra_placa_a1"] is True and r["entra_marco_a1"] is True
    assert "marco: 56 x 46 x 4 mm" in r["mensaje_a1"] and "placa: 44 x 34 x 3 mm" in r["mensaje_a1"]
    assert r["entran_juntas"] is True and not r["avisos"], r["avisos"]
    assert (r["ancho_mm"], r["alto_mm"], r["profundidad_mm"]) == (56.0, 46.0, 4.0)                 # las medidas son las del MARCO
    with _carpeta() as d:
        ruta = _imagen(d)
        # imagen de 228 mm: la placa mide 232 (entra) y el marco 244 (pasa de los 240 recomendados): NO entra el conjunto
        r = gen.generar(ruta, ancho_mm=228.0, px_por_mm=1.0, carpeta_salida=d, verificar=False)
        assert r["entra_placa_a1"] is True and r["entra_marco_a1"] is False and r["entra_a1"] is False
        assert abs(r["marco"]["ancho_mm"] - 244.0) < 1e-6 and r["placa"]["ancho_mm"] < 240 and r["entran_juntas"] is False
        assert any("marco" in a and "Achicá" in a for a in r["avisos"]), r["avisos"]
        assert "marco: 244" in r["mensaje_a1"] and "entra justo" in r["mensaje_a1"]
        # 250 mm: ni la placa (254) entra sin partir; con 260 pasa de los 256 y NO entra
        r = gen.generar(ruta, ancho_mm=260.0, px_por_mm=1.0, carpeta_salida=d, verificar=False)
        assert r["entra_placa_a1"] is False and r["entra_marco_a1"] is False and "NO entra" in r["mensaje_a1"]
        assert not any("todavía no se parte" in a and "litofanía:" in a for a in r["avisos"]), r["avisos"]          # el chequeo de L4 (sin marco) no se duplica
        assert sum("NO entra" in a for a in r["avisos"]) == 2                                                    # uno por pieza
        # el lado MAYOR es el que cuenta: una imagen alta
        r = gen.generar(ruta, ancho_mm=50.0, alto_mm=230.0, px_por_mm=1.0, carpeta_salida=d, verificar=False)
        assert r["alto_mm"] == 246.0 and r["entra_marco_a1"] is False and r["entra_placa_a1"] is True
        # un borde más fino sí entra
        r = gen.generar(ruta, ancho_mm=228.0, px_por_mm=1.0, ancho_borde=5.0, carpeta_salida=d, verificar=False)
        assert r["entra_marco_a1"] is True and r["entra_a1"] is True and abs(r["ancho_mm"] - 238.0) < 1e-6
    # las dos juntas en la cama: 56 + 10 + 44 = 110 de ancho entran; dos piezas de 130 en cada eje no
    assert gen.entran_juntas_en_la_cama((56, 46), (44, 34)) is True
    assert gen.entran_juntas_en_la_cama((130, 130), (130, 130)) is False
    assert gen.entran_juntas_en_la_cama((120, 200), (130, 200)) is False           # en X: 120 + 10 + 130 = 260; en Y: 410
    assert gen.entran_juntas_en_la_cama((100, 200), (100, 100)) is True            # 100 + 10 + 100 = 210 de ancho, alto 200
    assert gen.entran_juntas_en_la_cama((100, 100), (100, 150)) is True            # en X: 100 + 10 + 100 = 210 sí
    assert gen.entran_juntas_en_la_cama((200, 100), (200, 140)) is True            # en X no (410); en Y: 100 + 10 + 140 = 250 sí
    assert gen.entran_juntas_en_la_cama((200, 120), (200, 130)) is False           # en Y: 260 NO
    assert gen.entran_juntas_en_la_cama((100, 100), (100, 300)) is False           # en X sumaría 210 pero la segunda no entra de alto
    assert gen.entran_juntas_en_la_cama((100, 100), (300, 100)) is False           # en Y sumaría 210 pero la segunda no entra de ancho
    assert gen.entran_juntas_en_la_cama((100, 300), (100, 100)) is False


def test_el_resultado_cumple_el_contrato_del_proyecto():
    r, placa, marco_ens, placa_stl, marco_stl = _armar()
    for clave in ("ruta_stl", "ruta_stl_placa", "ruta_stl_marco", "ancho_mm", "alto_mm", "profundidad_mm", "vertices", "caras",
                  "watertight", "info", "avisos", "entra_a1", "mensaje_a1", "placa", "marco", "geometria", "banda_x", "banda_y",
                  "stl_mb", "verificacion", "tiempos", "guia", "mapa_brillo", "mapa_grosor"):
        assert clave in r, clave
    assert isinstance(r["watertight"], bool) and isinstance(r["entra_a1"], bool)
    assert all(isinstance(x, str) for x in r["info"] + r["avisos"]) and isinstance(r["mensaje_a1"], str)
    assert r["vertices"] == len(placa_stl.vertices) + len(marco_stl.vertices)
    assert r["caras"] == len(placa_stl.faces) + len(marco_stl.faces) == r["placa"]["caras"] + r["marco"]["caras"]
    assert r["placa"]["caras"] == len(placa_stl.faces) and r["marco"]["caras"] == len(marco_stl.faces)
    assert r["ruta_stl"] == r["ruta_stl_placa"] != r["ruta_stl_marco"]
    assert r["tiempos"] and all(v >= 0 for v in r["tiempos"].values())
    texto = "\n".join(r["info"])
    for frase in ("OPACO", "translúcido", "DESDE ATRÁS", "0.25 mm de holgura", "hasta 0.25 mm de borde de la foto", "cámara de luz",
                  "ventana de 40.0 x 30.0 mm, el tamaño de la imagen", "MARCO de 56.0 x 46.0 x 4.0 mm", "PLACA de"):
        assert frase in texto, frase
    assert abs(r["stl_mb"] - (r["placa"]["stl_mb"] + r["marco"]["stl_mb"])) < 1e-12
    with _carpeta() as d:
        ruta = _imagen(d)
        r1 = gen.generar(ruta, ancho_mm=30.0, px_por_mm=2.0, carpeta_salida=d, prefijo="mi lito")
        assert os.path.basename(r1["ruta_stl_placa"]) == "mi_lito_placa.stl" and os.path.basename(r1["ruta_stl_marco"]) == "mi_lito_marco.stl"
        assert sorted(os.listdir(d)) == ["foto.png", "mi_lito_marco.stl", "mi_lito_placa.stl"]
        r2 = gen.generar(ruta, ancho_mm=30.0, px_por_mm=2.0, carpeta_salida=d, prefijo="mi lito")
        assert open(r1["ruta_stl_placa"], "rb").read() == open(r2["ruta_stl_placa"], "rb").read()      # determinista
        gen.generar(ruta, ancho_mm=30.0, px_por_mm=2.0, carpeta_salida=d)
        assert os.path.isfile(os.path.join(d, "foto_placa.stl")) and os.path.isfile(os.path.join(d, "foto_marco.stl"))
        rs = gen.generar(ruta, ancho_mm=30.0, px_por_mm=2.0, carpeta_salida=d, verificar=False)
        assert rs["verificacion"] is None and rs["watertight"] is True


def test_el_watertight_del_resultado_sale_de_cada_malla_y_el_conjunto_es_el_y_de_las_dos():
    """Se simulan mallas abiertas / verificaciones fallidas para ver que el resultado las mira de verdad (y por pieza)."""
    def abierta(m):
        return trimesh.Trimesh(m.vertices, m.faces[:-1], process=False)
    original_ver, original_mesh, original_imp = lf.verificar_malla, lf.malla_desde_grilla_grosor, marco.marco_para_imprimir
    try:
        with _carpeta() as d:
            ruta = _imagen(d, 40, 30)
            for (wp, wm) in ((True, False), (False, True), (False, False), (True, True)):
                llamadas = []
                def falsa(m, llamadas=llamadas, wp=wp, wm=wm):
                    llamadas.append(1)
                    return {"watertight": (wp, wm)[len(llamadas) - 1], "ok": True, "euler": 2}
                lf.verificar_malla = falsa
                r = gen.generar(ruta, ancho_mm=20.0, px_por_mm=2.0, carpeta_salida=d)
                assert (r["watertight_placa"], r["watertight_marco"], r["watertight"]) == (wp, wm, wp and wm), (wp, wm, r["watertight"])
            lf.verificar_malla = original_ver
            lf.malla_desde_grilla_grosor = lambda *a, **k: abierta(original_mesh(*a, **k))
            r = gen.generar(ruta, ancho_mm=20.0, px_por_mm=2.0, carpeta_salida=d, verificar=False)
            assert (r["watertight_placa"], r["watertight_marco"], r["watertight"]) == (False, True, False)
            lf.malla_desde_grilla_grosor = original_mesh
            marco.marco_para_imprimir = lambda m, g: abierta(original_imp(m, g))
            r = gen.generar(ruta, ancho_mm=20.0, px_por_mm=2.0, carpeta_salida=d, verificar=False)
            assert (r["watertight_placa"], r["watertight_marco"], r["watertight"]) == (True, False, False)
            marco.marco_para_imprimir = original_imp
            r = gen.generar(ruta, ancho_mm=20.0, px_por_mm=2.0, carpeta_salida=d, verificar=False)
            assert (r["watertight_placa"], r["watertight_marco"], r["watertight"]) == (True, True, True)
    finally:
        lf.verificar_malla, lf.malla_desde_grilla_grosor, marco.marco_para_imprimir = original_ver, original_mesh, original_imp


def test_la_diagonal_llega_a_la_malla_de_la_placa():
    with _carpeta() as d:
        ruta = _imagen(d)
        a = gen.generar(ruta, ancho_mm=40.0, px_por_mm=2.0, carpeta_salida=d, diagonal="adaptativa", prefijo="a")
        f = gen.generar(ruta, ancho_mm=40.0, px_por_mm=2.0, carpeta_salida=d, diagonal="fija", prefijo="f")
        assert open(a["ruta_stl_placa"], "rb").read() != open(f["ruta_stl_placa"], "rb").read()
        assert open(a["ruta_stl_marco"], "rb").read() == open(f["ruta_stl_marco"], "rb").read()      # el marco no depende de la diagonal
        assert a["watertight"] and f["watertight"] and a["caras"] == f["caras"]
        assert "verificacion" in a["tiempos"]
        assert "verificacion" not in gen.generar(ruta, ancho_mm=40.0, px_por_mm=2.0, carpeta_salida=d, verificar=False)["tiempos"]


def test_los_parametros_del_marco_llegan_al_resultado_y_la_imagen_a_la_placa():
    with _carpeta() as d:
        ruta = _imagen(d)
        r = gen.generar(ruta, ancho_mm=40.0, px_por_mm=2.0, carpeta_salida=d, ancho_borde=10.0, grosor_ceja=2.0, holgura=0.5,
                        margen_encastre=3.0)
        g = r["geometria"]
        assert abs(r["ancho_mm"] - (40 + 2 * 10)) < 1e-9 and abs(r["profundidad_mm"] - (2.8 + 2.0)) < 1e-9
        assert g.holgura == 0.5 and g.grosor_ceja == 2.0 and abs(g.banda_x - 3.0) < 0.26
        placa = trimesh.load(r["ruta_stl_placa"])
        assert abs((placa.bounds[1][0] - placa.bounds[0][0]) - (40 + 2 * g.banda_x)) < TOL
        # los parámetros de imagen y grosor llegan a la placa (como en L4)
        r2 = gen.generar(ruta, ancho_mm=40.0, px_por_mm=2.0, carpeta_salida=d, grosor_max=2.0, prefijo="b", invertir=True)
        assert abs(r2["profundidad_mm"] - (2.0 + 1.2)) < 1e-9
        assert open(r["ruta_stl_placa"], "rb").read() != open(r2["ruta_stl_placa"], "rb").read()
        # y los de L4 (capas) también: los grosores de la imagen son niveles de capa
        r3 = gen.generar(ruta, ancho_mm=40.0, px_por_mm=2.0, carpeta_salida=d, capa_mm=0.2, prefijo="c")
        grilla, _, _ = marco.grilla_con_banda(r3["mapa_grosor"], 2.0)
        niveles = 0.2 + 0.2 * np.arange(20)
        assert np.abs(grilla[:, :, None] - niveles).min(axis=2).max() < 1e-9


def test_main_lista_el_marco_y_cumple_el_contrato():
    import main
    with contextlib.redirect_stdout(io.StringIO()):
        generadores = main._descubrir_generadores()
    nombres = [g.NOMBRE for g in generadores]
    assert gen.NOMBRE in nombres and "Litofanía" in nombres, nombres
    g = generadores[nombres.index(gen.NOMBRE)]
    assert g is gen and isinstance(g.DESCRIPCION, str) and len(g.DESCRIPCION) > 10 and callable(g.ejecutar)
    assert len(set(nombres)) == len(nombres)


@contextlib.contextmanager
def _teclas(respuestas):
    cola = iter(respuestas)
    original = builtins.input
    builtins.input = lambda *_a, **_k: next(cola, "")
    try:
        yield
    finally:
        builtins.input = original


def _ejecutar(respuestas, d):
    original = gen.CARPETA_SALIDA
    gen.CARPETA_SALIDA = d
    salida = io.StringIO()
    try:
        with _teclas(respuestas), contextlib.redirect_stdout(salida):
            gen.ejecutar()
    finally:
        gen.CARPETA_SALIDA = original
    return salida.getvalue()


def test_ejecutar_genera_los_dos_stl_con_input_simulado_y_no_se_cae_con_entradas_malas():
    with _carpeta() as d:
        ruta = _imagen(d)
        # ruta, ancho, px/mm, grosor claro, grosor oscuro, luz %, invertir, cara, capa, borde, ceja, banda, holgura
        out = _ejecutar([ruta, "40", "2", "0.8", "2.8", "5", "n", "relieve", "0", "10", "1.5", "2.5", "0.3"], d)
        placa, marco_ = os.path.join(d, "foto_placa.stl"), os.path.join(d, "foto_marco.stl")
        assert os.path.isfile(placa) and os.path.isfile(marco_) and "ERROR" not in out, out
        assert "watertight_placa" not in out and out.count("watertight=True") == 2 and "holgura 0.3 mm" in out
        pl = trimesh.load(placa)
        assert abs((pl.bounds[1][0] - pl.bounds[0][0]) - (40 + 2 * 2.5)) < 0.3                                       # la banda pedida (2,5)
        m = trimesh.load(marco_)
        assert abs(m.bounds[1][0] - m.bounds[0][0] - (40 + 20)) < TOL and abs(m.bounds[1][2] - (2.8 + 1.5)) < TOL     # borde 10 y ceja 1,5
        antes = open(marco_, "rb").read()
        _ejecutar([ruta, "40", "2", "", "", "", "n", "relieve", "", "10", "1.5", "2.5", "0.6"], d)
        assert open(marco_, "rb").read() != antes                                                                    # la holgura llega
        # entradas malas
        out = _ejecutar([os.path.join(d, "nada.png")], d)
        assert "ERROR" in out and "no encuentro" in out
        out = _ejecutar([ruta, "40", "2", "0.8", "2.8", "5", "n", "relieve", "0", "2", "", "", ""], d)               # borde que no alcanza
        assert "ERROR" in out and "pared" in out
        out = _ejecutar([ruta, "40", "2", "0.8", "2.8", "5", "n", "relieve", "0", "", "0.3", "", ""], d)             # ceja muy fina
        assert "ERROR" in out and "ceja" in out


# ---------------------------------------------------------------------------
#  (5) L1-L5 y L7 no se tocaron
# ---------------------------------------------------------------------------

def test_l1_a_l5_y_l7_no_dependen_del_marco():
    for ruta in ("core/litofania.py", "core/litofania_simulacion.py", "core/litofania_calibracion.py", "generators/litofania.py",
                 "generators/calibracion_litofania.py"):
        txt = open(ruta, encoding="utf-8").read()
        assert "marco_litofania" not in txt and "litofania_marco" not in txt, ruta
    for ruta in sorted(os.listdir("pages")):
        if "Litofania" in ruta:
            assert "marco" not in open(os.path.join("pages", ruta), encoding="utf-8").read().lower().replace("marcos", "")


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
