#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_litofania_calibracion.py
-----------------------------------
Red de regresión para L6 de la litofanía: la placa de calibración (`core/litofania_calibracion.py` y
`generators/calibracion_litofania.py`). Lo que se cuida:

  * cada franja MIDE su grosor sobre la malla, con rayos verticales (numpy puro, sin mirar cómo se armó la
    grilla), y la malla es watertight; el marco, los separadores y la tira de etiquetas quedan al grosor máximo;
  * los grosores son ascendentes, cubren exactamente el rango pedido y respetan las capas con `capa_mm`;
  * las etiquetas de 7 segmentos SE LEEN: el test las decodifica mirando la grilla (sin usar la tabla de
    segmentos del código) y coinciden con el grosor REAL de la franja de arriba; también sobre la malla
    espejada de `cara_visible="plana"`;
  * `calibrar_luz_minima` recupera `k` exacto en la ida y vuelta, no depende de la exposición, descarta
    franjas saturadas o en el ruido (con sus umbrales exactos), exige 3 útiles, avisa con R² bajo y con
    un luz mínimo fuera de rango, y usa las funciones de L2;
  * entra en la A1 (o avisa) y `main.py` lo lista; `ejecutar()` corre con `input` simulado.

No usa pytest (ver AGENTS.md "Testing") -- funciones `test_*` con `assert` simple,
corribles con `python tests/test_litofania_calibracion.py`.
"""
import builtins
import contextlib
import io
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import trimesh
from scipy import ndimage

from core import litofania as lf
from core import litofania_calibracion as cal
from core.litofania_simulacion import oetf_srgb, simular_contraluz
from generators import calibracion_litofania as gen

ESCALERA = (0.6, 1.0, 1.4, 1.8, 2.2, 2.6, 3.0)


# --- ayudas ---------------------------------------------------------------------------------

@contextlib.contextmanager
def _carpeta():
    with tempfile.TemporaryDirectory() as d:
        yield d


_CACHE = {}


def _generar(**kw):
    """`generar()` en una carpeta temporal (la malla se carga del STL: es lo que se imprime). Cachea por argumentos."""
    clave = tuple(sorted(kw.items()))
    if clave not in _CACHE:
        with _carpeta() as d:
            r = gen.generar(carpeta_salida=d, **kw)
            malla = trimesh.load(r["ruta_stl"])
        _CACHE[clave] = (r, malla)
    return _CACHE[clave]


def _espesor_por_rayos(malla, puntos_xy):
    """Grosor de la placa en cada (x, y): un rayo vertical contra TODOS los triángulos, distancia entre el primer
    y el último impacto; exige exactamente 2 impactos por rayo. Numpy puro (misma técnica que test_litofania_malla)."""
    puntos = np.asarray(puntos_xy, dtype=float)
    tri = malla.triangles
    a, b, c = tri[:, 0], tri[:, 1], tri[:, 2]
    v1, v0 = b[:, :2] - a[:, :2], c[:, :2] - a[:, :2]
    d = v1[:, 0] * v0[:, 1] - v1[:, 1] * v0[:, 0]
    no_vertical = np.abs(d) > 1e-12
    v2 = puntos[:, None, :] - a[None, :, :2]
    with np.errstate(divide="ignore", invalid="ignore"):
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


def _a_salvo(x, y, px):
    """Corre el punto un poquito hasta que no caiga sobre una arista ni una diagonal de la grilla (ahí un rayo da 3
    impactos en vez de 2): la medición vertical es exacta en cualquier otro punto."""
    for _ in range(200):
        fx, fy = (x * px) % 1.0, (y * px) % 1.0
        if min(fx, 1 - fx, fy, 1 - fy, abs(fx - fy), abs(fx + fy - 1)) > 0.03:
            return x, y
        x += 0.0137
    raise AssertionError("no encontré un punto a salvo")


def _medir(malla, puntos, px=4.0):
    return _espesor_por_rayos(malla, [_a_salvo(x, y, px) for x, y in puntos])


# Geometría por defecto, escrita acá aparte (en mm, y desde ABAJO): borde 3, franjas de 18 x 30, separadores de 3,
# tira de etiquetas de 10 mm debajo de las franjas.
DIGITO_ANCHO_MM = 3.6
BORDE, FW, FH, SEP, ET = 3.0, 18.0, 30.0, 3.0, 10.0
Y_FRANJA0 = BORDE + ET + SEP                         # borde inferior de las franjas, desde abajo
Y_ETIQUETA0 = BORDE                                  # borde inferior de la tira de etiquetas


def _x_franja(k, fw=FW, sep=SEP, borde=BORDE):
    return borde + k * (fw + sep)


def _centro_franja(k, dx=0.11, dy=0.07):
    """Un punto adentro de la franja k (corrido del centro para no caer justo sobre una arista de la malla)."""
    return (_x_franja(k) + FW / 2 + dx, Y_FRANJA0 + FH / 2 + dy)


def _esperado_con_capas(pedidos, capa, primera):
    """Niveles de capa escritos acá aparte: el más cercano a `primera + m * capa`, m >= 0."""
    pedidos = np.asarray(pedidos, dtype=float)
    return np.array([primera + max(0, int(np.floor((t - primera) / capa + 0.5 + 1e-9))) * capa for t in pedidos])


# ---------------------------------------------------------------------------
#  (1) cada franja mide su grosor sobre la malla (con rayos) y es watertight
# ---------------------------------------------------------------------------

def test_cada_franja_mide_su_grosor_sobre_la_malla_con_rayos():
    r, malla = _generar()
    assert len(r["escalones"]) == 7
    medidos = _medir(malla, [_centro_franja(k) for k in range(7)])
    assert np.abs(medidos - np.array(ESCALERA)).max() < 1e-6, (medidos, ESCALERA)
    assert np.all(np.diff(medidos) > 0.3)                       # ascendentes, izquierda -> derecha, saltos de 0,4
    # y tampoco es solo el centro: varios puntos de cada franja, cerca de sus bordes
    for k in range(7):
        puntos = [(_x_franja(k) + dx, Y_FRANJA0 + dy) for dx in (0.6, 9.13, 17.4, 17.9) for dy in (0.1, 0.6, 15.07, 29.4, 29.9)]   # incluye la última celda de cada borde
        assert np.abs(_medir(malla, puntos) - ESCALERA[k]).max() < 1e-6, k


def test_la_malla_es_watertight_por_las_cuatro_vias():
    r, malla = _generar()
    v = r["verificacion"]
    assert r["watertight"] is True and v["ok"] and v["watertight"] and v["euler"] == 2
    assert v["aristas_con_dos_caras"] and v["caras_degeneradas"] == 0 and v["caras_duplicadas"] == 0
    assert malla.is_watertight and malla.is_winding_consistent and malla.volume > 0
    assert lf.verificar_malla(malla)["ok"]
    # y el volumen coincide con el de las franjas: sale de la grilla, no de una cuenta propia (cota independiente)
    assert abs(malla.volume - r["placa"].grosor.mean() * r["ancho_mm"] * r["alto_mm"]) < 0.05 * malla.volume


def test_medidas_exactas_de_la_placa_y_de_la_malla():
    r, malla = _generar()
    assert (r["ancho_mm"], r["alto_mm"], r["profundidad_mm"]) == (150.0, 49.0, 3.0)
    (x0, y0, z0), (x1, y1, z1) = malla.bounds
    assert (x0, y0, z0) == (0.0, 0.0, 0.0) and abs(x1 - 150.0) < 1e-9 and abs(y1 - 49.0) < 1e-9 and abs(z1 - 3.0) < 1e-9
    assert r["caras"] == len(malla.faces) == 239976 and r["vertices"] == len(malla.vertices)
    # otro tamaño: 5 franjas de 12 x 20 con separador de 2 -> 6 + 60 + 8 = 74 de ancho, 6 + 20 + 2 + 10 = 38 de alto
    r2, _ = _generar(n_franjas=5, ancho_franja=12.0, alto_franja=20.0, separador_mm=2.0, borde_mm=3.0, px_por_mm=2.0)
    assert (r2["ancho_mm"], r2["alto_mm"]) == (74.0, 38.0)


def test_los_escalones_dicen_donde_esta_cada_franja_en_mm_y_en_vertices():
    p = cal.placa_de_calibracion()
    assert (p.ancho_px, p.alto_px, p.px_por_mm) == (601, 197, 4.0) and p.grosor.shape == (197, 601)
    for k, e in enumerate(p.escalones):
        assert (e["x0_mm"], e["x1_mm"]) == (_x_franja(k), _x_franja(k) + FW), k
        assert (e["y0_mm"], e["y1_mm"]) == (Y_FRANJA0, Y_FRANJA0 + FH), k
        assert (e["col0"], e["col1"]) == (int(_x_franja(k) * 4), int((_x_franja(k) + FW) * 4))
        assert (e["fila1"] - e["fila0"], e["etiqueta_fila1"] - e["etiqueta_fila0"]) == (int(FH * 4), int(ET * 4))
        assert (p.grosor[e["fila0"]: e["fila1"] + 1, e["col0"]: e["col1"] + 1] == e["grosor"]).all()
    r, _ = _generar()
    assert (r["ancho_px"], r["alto_px"], r["px_por_mm"]) == (601, 197, 4.0)


def test_el_marco_los_separadores_y_la_tira_quedan_al_grosor_maximo():
    r, malla = _generar()
    ancho, alto = r["ancho_mm"], r["alto_mm"]
    puntos = [
        (1.3, 1.3), (ancho - 1.3, 1.3), (1.3, alto - 1.3), (ancho - 1.3, alto - 1.3),             # las 4 esquinas del borde
        (ancho / 2 + 0.11, 1.4), (ancho / 2 + 0.11, alto - 1.4), (1.4, alto / 2 + 0.07),          # lados del borde
    ]
    puntos += [(_x_franja(k) + FW + SEP / 2 + 0.07, Y_FRANJA0 + 15.11) for k in range(6)]         # separadores entre franjas
    puntos += [(_x_franja(k) + FW + SEP / 2 + 0.07, Y_ETIQUETA0 + 5.11) for k in range(6)]         # entre etiquetas
    puntos += [(_x_franja(k) + 0.9, Y_ETIQUETA0 + 0.9) for k in range(7)]                          # tira, sin dígitos
    puntos += [(_x_franja(k) + FW / 2 + 0.11, Y_FRANJA0 - SEP / 2 + 0.07) for k in range(7)]       # banda entre franja y tira
    medidos = _medir(malla, puntos)
    assert np.abs(medidos - 3.0).max() < 1e-6, medidos.min()
    assert abs(r["placa"].grosor_marco - 3.0) < 1e-12


# ---------------------------------------------------------------------------
#  (2) los grosores: ascendentes, el rango exacto, las capas
# ---------------------------------------------------------------------------

def test_los_grosores_cubren_el_rango_pedido_con_cualquier_cantidad():
    for n, gmin, gmax in ((3, 0.6, 3.0), (4, 0.8, 2.8), (5, 1.0, 2.0), (10, 0.6, 3.0), (20, 0.5, 4.0)):
        p = cal.placa_de_calibracion(n_franjas=n, grosor_min=gmin, grosor_max=gmax, px_por_mm=2.0)
        g = np.array([e["grosor"] for e in p.escalones])
        assert len(g) == n and abs(g[0] - gmin) < 1e-12 and abs(g[-1] - gmax) < 1e-12
        assert np.allclose(np.diff(g), (gmax - gmin) / (n - 1), atol=1e-12), (n, g)
        assert [e["indice"] for e in p.escalones] == list(range(n))
        assert p.grosor.max() == gmax and p.grosor.min() == gmin
    # medido sobre una malla: 4 franjas de 0,8 a 2,8
    r, malla = _generar(n_franjas=4, grosor_min=0.8, grosor_max=2.8, px_por_mm=2.0)
    centros = [(_x_franja(k) + FW / 2 + 0.11, Y_FRANJA0 + FH / 2 + 0.07) for k in range(4)]
    assert np.abs(_medir(malla, centros, 2.0) - np.linspace(0.8, 2.8, 4)).max() < 1e-6


def test_con_capa_los_grosores_pasan_a_niveles_de_capa_y_se_miden_asi():
    esperado = _esperado_con_capas(ESCALERA, 0.12, 0.2)
    assert np.allclose(esperado, (0.56, 1.04, 1.40, 1.76, 2.24, 2.60, 2.96))
    r, malla = _generar(capa_mm=0.12)
    assert np.allclose(r["grosores"], esperado, atol=1e-9)
    assert np.allclose([e["grosor_pedido"] for e in r["escalones"]], ESCALERA)           # lo pedido se conserva aparte
    assert np.abs(_medir(malla, [_centro_franja(k) for k in range(7)]) - esperado).max() < 1e-6
    assert abs(r["profundidad_mm"] - 2.96) < 1e-9 and abs(r["placa"].grosor_marco - 2.96) < 1e-9     # el marco sigue al máximo real
    assert abs(r["placa"].grosor_digito - 0.56) < 1e-9
    # otra capa y otra primera capa, y las capas NO se aplican si no se piden
    r2, _ = _generar(capa_mm=0.2, primera_capa_mm=0.3, n_franjas=5, px_por_mm=2.0)
    assert np.allclose(r2["grosores"], _esperado_con_capas(np.linspace(0.6, 3.0, 5), 0.2, 0.3))
    r3, _ = _generar(n_franjas=5, px_por_mm=2.0)
    assert np.allclose(r3["grosores"], np.linspace(0.6, 3.0, 5), atol=1e-12)


def test_avisa_si_dos_franjas_caen_en_el_mismo_nivel_de_capa():
    p = cal.placa_de_calibracion(n_franjas=7, grosor_min=0.6, grosor_max=1.0, capa_mm=0.4, px_por_mm=2.0)
    assert len(set(e["grosor"] for e in p.escalones)) < 7
    assert any("mismo nivel" in a for a in p.avisos), p.avisos
    assert not cal.placa_de_calibracion(px_por_mm=2.0, capa_mm=0.12).avisos
    assert not cal.placa_de_calibracion(px_por_mm=2.0).avisos


def test_avisa_si_la_franja_mas_fina_es_fragil_y_no_si_no():
    r, _ = _generar(grosor_min=0.4, grosor_max=3.0, px_por_mm=2.0)
    assert any("frágil" in a and "0.40" in a for a in r["avisos"]), r["avisos"]
    r, _ = _generar(px_por_mm=2.0)
    assert not [a for a in r["avisos"] if "frágil" in a]
    r, _ = _generar(grosor_min=0.6, px_por_mm=2.0, capa_mm=0.2, primera_capa_mm=0.2)       # 0,6 es exacto en capas de 0,2
    assert not [a for a in r["avisos"] if "frágil" in a]


# ---------------------------------------------------------------------------
#  (3) las etiquetas de 7 segmentos son legibles: se decodifican leyendo la grilla
# ---------------------------------------------------------------------------

# patrón de segmentos encendidos (a arriba, b arriba-der, c abajo-der, d abajo, e abajo-izq, f arriba-izq, g medio)
# -> dígito. Escrito acá aparte, de la forma estándar de un display de 7 segmentos.
DIGITOS = {"abcdef": "0", "bc": "1", "abdeg": "2", "abcdg": "3", "bcfg": "4", "acdfg": "5", "acdefg": "6",
           "abc": "7", "abcdefg": "8", "abcdfg": "9"}


def _decodificar_celda(celda_grabada):
    """Lee el texto de una celda (matriz booleana: True = grabado). Cada dígito es una mancha conexa; el punto es
    la mancha baja. De cada dígito se miran 7 puntos (uno por segmento) dentro de su caja."""
    etiquetas, n = ndimage.label(celda_grabada)
    manchas = []
    for i in range(1, n + 1):
        filas, cols = np.where(etiquetas == i)
        manchas.append((cols.min(), cols.max() + 1, filas.min(), filas.max() + 1))
    manchas.sort()
    alto_max = max(f1 - f0 for _, _, f0, f1 in manchas)
    texto = ""
    for c0, c1, f0, f1 in manchas:
        alto, ancho = f1 - f0, c1 - c0
        if alto < 0.5 * alto_max:
            assert f1 == max(m[3] for m in manchas), "el punto tiene que estar en la línea de base"
            texto += "."
            continue
        sub = celda_grabada[f0:f1, c0:c1]
        if ancho <= 0.35 * alto:                                        # una barra angosta y alta: el 1
            assert sub.all(), "el 1 es una barra llena"
            texto += "1"
            continue
        h, w = sub.shape
        sondas = {"a": (0.08, 0.5), "g": (0.5, 0.5), "d": (0.92, 0.5), "f": (0.25, 0.08), "b": (0.25, 0.92),
                  "e": (0.75, 0.08), "c": (0.75, 0.92)}
        encendidos = "".join(sorted(s for s, (fy, fx) in sondas.items() if sub[int(fy * h), min(w - 1, int(fx * w))]))
        assert encendidos in DIGITOS, f"patrón que no es un dígito: {encendidos!r}"
        texto += DIGITOS[encendidos]
    return texto


def _celda_grabada(placa, k, fw=FW):
    """Matriz booleana de lo grabado en la celda de etiqueta de la franja k, según la grilla y la geometría en mm
    de este test (no los índices que guarda `escalones`)."""
    px = placa.px_por_mm
    c0, c1 = int(round(_x_franja(k, fw) * px)), int(round((_x_franja(k, fw) + fw) * px))
    f0, f1 = int(round((placa.alto_mm - (Y_ETIQUETA0 + ET)) * px)), int(round((placa.alto_mm - Y_ETIQUETA0) * px))
    celda = placa.grosor[f0:f1 + 1, c0:c1 + 1]
    return celda < placa.grosor_marco - 1e-9


def _etiquetas_leidas(placa, fw=FW):
    return [_decodificar_celda(_celda_grabada(placa, k, fw)) for k in range(len(placa.escalones))]


def test_las_etiquetas_se_leen_y_coinciden_con_el_grosor_de_cada_franja():
    p = cal.placa_de_calibracion()
    assert _etiquetas_leidas(p) == ["0.6", "1.0", "1.4", "1.8", "2.2", "2.6", "3.0"]
    assert [e["etiqueta"] for e in p.escalones] == _etiquetas_leidas(p)
    for e, leida in zip(p.escalones, _etiquetas_leidas(p)):
        assert abs(float(leida) - e["grosor"]) < 0.051                      # la etiqueta ES el grosor de SU franja


def test_las_etiquetas_muestran_el_grosor_real_con_capas_y_dos_decimales():
    p = cal.placa_de_calibracion(capa_mm=0.12)
    leidas = _etiquetas_leidas(p)
    assert leidas == ["0.56", "1.04", "1.40", "1.76", "2.24", "2.60", "2.96"], leidas
    assert all(abs(float(t) - g) < 0.0051 for t, g in zip(leidas, _esperado_con_capas(ESCALERA, 0.12, 0.2)))
    # capa de 0,2 con la primera de 0,2: los grosores caen en décimas (0,6 1,0 1,4 ...) -> 1 decimal
    assert _etiquetas_leidas(cal.placa_de_calibracion(capa_mm=0.2)) == ["0.6", "1.0", "1.4", "1.8", "2.2", "2.6", "3.0"]


def test_etiquetas_legibles_con_otros_rangos_cantidades_y_resoluciones():
    for kw in (dict(n_franjas=5, grosor_min=0.8, grosor_max=2.8), dict(n_franjas=3, grosor_min=1.0, grosor_max=9.0),
               dict(n_franjas=9, grosor_min=0.5, grosor_max=4.5), dict(n_franjas=4, grosor_min=0.7, grosor_max=1.3),
               dict(n_franjas=7, grosor_min=0.6, grosor_max=3.0, px_por_mm=3.0),
               dict(n_franjas=7, grosor_min=0.6, grosor_max=3.0, px_por_mm=6.0),
               dict(n_franjas=6, grosor_min=0.6, grosor_max=3.0, px_por_mm=2.0, ancho_franja=16.0),
               dict(n_franjas=7, grosor_min=8.0, grosor_max=9.99)):
        p = cal.placa_de_calibracion(**kw)
        esperadas = [f"{e['grosor']:.{1 if all(abs(x['grosor'] * 10 - round(x['grosor'] * 10)) < 1e-6 for x in p.escalones) else 2}f}"
                     for e in p.escalones]
        leidas = _etiquetas_leidas(p, kw.get("ancho_franja", FW))
        assert leidas == esperadas, (kw, leidas, esperadas)
    # sobre todos los dígitos: una placa cuyas etiquetas recorren 0..9 (con 2 decimales: 1.23, 4.56, 7.89, 0.xx)
    p = cal.placa_de_calibracion(n_franjas=3, grosor_min=1.23, grosor_max=7.89, px_por_mm=4.0)
    assert _etiquetas_leidas(p) == ["1.23", "4.56", "7.89"]
    p = cal.placa_de_calibracion(n_franjas=3, grosor_min=0.99, grosor_max=9.97, px_por_mm=4.0)
    assert _etiquetas_leidas(p) == ["0.99", "5.48", "9.97"], _etiquetas_leidas(p)
    assert set("".join(_etiquetas_leidas(cal.placa_de_calibracion(n_franjas=3, grosor_min=0.5, grosor_max=9.0))).replace(".", "")) \
        <= set("0123456789")


def test_todos_los_digitos_se_decodifican_a_si_mismos():
    """Los diez dígitos, uno por uno, desde la grilla: ninguno se confunde con otro (el 8 y el 0 difieren en el
    medio, el 6 y el 5 en abajo-izquierda, el 9 y el 3 en arriba-izquierda...)."""
    vistos = {}
    for gmin, gmax in ((1.23, 4.56), (4.56, 7.89), (7.89, 9.90), (0.50, 0.80), (0.60, 6.00)):
        p = cal.placa_de_calibracion(n_franjas=3, grosor_min=gmin, grosor_max=gmax)
        for e, leida in zip(p.escalones, _etiquetas_leidas(p)):
            vistos[e["etiqueta"]] = leida
    assert all(k == v for k, v in vistos.items()), vistos
    assert set("".join(vistos).replace(".", "")) == set("0123456789"), sorted(set("".join(vistos)))


def test_las_etiquetas_quedan_adentro_de_su_celda_y_grabadas_hasta_el_minimo():
    p = cal.placa_de_calibracion()
    px = p.px_por_mm
    for k, e in enumerate(p.escalones):
        grab = _celda_grabada(p, k)
        filas, cols = np.where(grab)
        assert cols.min() >= int(0.3 * px) and cols.max() <= grab.shape[1] - 1 - int(0.3 * px), "toca el borde lateral"
        assert filas.min() >= int(1.0 * px) and filas.max() <= grab.shape[0] - 1 - int(1.0 * px), "toca el borde de la tira"
        centro = (cols.min() + cols.max()) / 2
        assert abs(centro - (grab.shape[1] - 1) / 2) <= 0.5 * DIGITO_ANCHO_MM * px, "el texto no está centrado"  # el 1 va a la derecha de su caja
    f0, f1 = int(round(p.alto_mm * px)) - int(round((Y_ETIQUETA0 + ET) * px)), int(round(p.alto_mm * px)) - int(round(Y_ETIQUETA0 * px))
    tira = p.grosor[f0:f1 + 1, :]
    assert set(np.round(np.unique(tira), 9)) == {0.6, 3.0}, np.unique(tira)       # solo el marco y el fondo del grabado
    for k in range(7):                                                              # la tira de una celda no toca la de otra
        c0, c1 = int(round(_x_franja(k) * px)), int(round((_x_franja(k) + FW) * px))
        sep = p.grosor[f0:f1 + 1, c1 + 1: c1 + int(SEP * px)]
        assert k == 6 or (sep == 3.0).all()


def test_un_digito_grabado_se_mide_con_rayos_a_la_profundidad_del_minimo():
    r, malla = _generar()
    p = r["placa"]
    px = p.px_por_mm
    puntos = []
    for k in range(7):
        grab = _celda_grabada(p, k)
        f0 = int(round((p.alto_mm - (Y_ETIQUETA0 + ET)) * px))
        c0 = int(round(_x_franja(k) * px))
        # un bloque de 2x2 vértices grabados: su celda entera está en la profundidad del grabado
        ok = grab[:-1, :-1] & grab[1:, :-1] & grab[:-1, 1:] & grab[1:, 1:]
        filas, cols = np.where(ok)
        j = len(filas) // 2
        fila, col = f0 + filas[j], c0 + cols[j]
        puntos.append(((col + 0.37) / px, (p.alto_px - 1 - fila - 0.41) / px))
    medidos = _medir(malla, puntos)
    assert np.abs(medidos - 0.6).max() < 1e-6, medidos


def test_con_cara_plana_la_malla_se_espeja_y_las_franjas_siguen_midiendo_lo_mismo():
    r, malla = _generar(cara_visible="plana")
    ancho = r["ancho_mm"]
    centros = [(ancho - _centro_franja(k)[0], _centro_franja(k)[1]) for k in range(7)]
    assert np.abs(_medir(malla, centros) - np.array(ESCALERA)).max() < 1e-6
    assert r["verificacion"]["ok"] and r["watertight"]
    assert any("lisa" in n for n in r["info"]) and not any("con relieve" in n for n in r["info"])
    # y NO queda igual que la de relieve (es otra malla): la franja fina está del otro lado
    r0, malla0 = _generar()
    assert not np.allclose(_medir(malla0, centros), _medir(malla, centros))


# ---------------------------------------------------------------------------
#  Errores, A1, contrato
# ---------------------------------------------------------------------------

def _falla(f, *args, texto=None, **kw):
    try:
        f(*args, **kw)
    except ValueError as e:
        assert texto is None or texto in str(e), (texto, str(e))
        return
    raise AssertionError(f"tenía que fallar con ValueError: {args} {kw}")


def test_parametros_absurdos_fallan_con_valueerror_claro():
    P = cal.placa_de_calibracion
    _falla(P, n_franjas=2, texto="n_franjas")
    _falla(P, n_franjas=21, texto="n_franjas")
    _falla(P, n_franjas=2.5, texto="n_franjas")
    _falla(P, n_franjas=7.0, texto="n_franjas")
    _falla(P, grosor_min=0, texto="mayor que 0")
    _falla(P, grosor_min=-1, texto="mayor que 0")
    _falla(P, grosor_min=3.0, grosor_max=3.0, texto="grosor_max")
    _falla(P, grosor_min=3.0, grosor_max=2.0, texto="grosor_max")
    _falla(P, grosor_max=10.0, texto="9.99")
    _falla(P, grosor_max=float("nan"))
    _falla(P, grosor_min=float("nan"))
    _falla(P, px_por_mm=1.9, texto="px_por_mm")
    _falla(P, px_por_mm=8.1, texto="px_por_mm")
    _falla(P, separador_mm=0.5, texto="1 mm")
    _falla(P, borde_mm=0.5, texto="1 mm")
    _falla(P, alto_franja=4.9, texto="alto_franja")
    _falla(P, alto_etiqueta=7.9, texto="alto_etiqueta")
    _falla(P, ancho_franja=10.0, texto="ancho_franja")
    _falla(P, ancho_franja=11.0, texto="ancho_franja")          # el texto entra justo pero sin margen: no alcanza
    P(ancho_franja=12.0)
    _falla(P, capa_mm=0, texto="capa_mm")
    _falla(P, capa_mm=-0.1, texto="capa_mm")
    _falla(P, capa_mm=0.12, primera_capa_mm=0, texto="primera_capa_mm")
    # y los límites exactos SÍ andan
    P(n_franjas=3, px_por_mm=2.0)
    P(n_franjas=20, px_por_mm=2.0)
    P(px_por_mm=8.0, grosor_max=9.99)
    P(px_por_mm=2.0, separador_mm=1.0, borde_mm=1.0, alto_franja=5.0, alto_etiqueta=8.0)
    with _carpeta() as d:
        _falla(gen.generar, cara_visible="atras", carpeta_salida=d, texto="cara_visible")
        _falla(gen.generar, diagonal="xx", carpeta_salida=d, texto="diagonal")
        _falla(gen.generar, media_luz_supuesta=0, carpeta_salida=d, texto="media_luz")
        _falla(gen.generar, n_franjas=1, carpeta_salida=d, texto="n_franjas")
        assert not os.listdir(d)                                          # nada se escribió


def test_entra_en_la_a1_y_avisa_si_no_con_la_geometria_ordenada():
    r, _ = _generar()
    assert r["entra_a1"] is True and "entra en la Bambu A1" in r["mensaje_a1"] and "150 x 49 x 3" in r["mensaje_a1"]
    assert not [a for a in r["avisos"] if "A1" in a]
    # 11 franjas: 234 mm; 12: 255 (entra pero pasa de los 240 recomendados); 13: 276 (no entra)
    ancho = lambda n: 2 * BORDE + n * FW + (n - 1) * SEP
    for n, entra, texto in ((11, True, "sin partir"), (12, False, "justo"), (13, False, "NO entra")):
        r, _ = _generar(n_franjas=n, px_por_mm=2.0)
        assert r["ancho_mm"] == ancho(n) and r["entra_a1"] is entra, (n, r["mensaje_a1"])
        assert texto in r["mensaje_a1"], r["mensaje_a1"]
        assert bool([a for a in r["avisos"] if "Achicá" in a]) == (not entra), (n, r["avisos"])
    # el lado MAYOR es el que cuenta, sea el ancho o el alto: franjas muy largas
    r, _ = _generar(n_franjas=3, alto_franja=200.0, px_por_mm=2.0)
    assert r["alto_mm"] == 219.0 and r["entra_a1"] is True
    r, _ = _generar(n_franjas=3, alto_franja=250.0, px_por_mm=2.0)
    assert r["alto_mm"] == 269.0 and r["entra_a1"] is False and "NO entra" in r["mensaje_a1"]
    assert any("A1" in a and "Achicá" in a for a in r["avisos"])


def test_el_resultado_cumple_el_contrato_del_proyecto():
    r, malla = _generar()
    for clave in ("ruta_stl", "ancho_mm", "alto_mm", "profundidad_mm", "vertices", "caras", "watertight", "info",
                  "avisos", "entra_a1", "mensaje_a1", "escalones", "grosores", "etiquetas", "stl_mb", "verificacion",
                  "tiempos", "tabla_prediccion", "mapa_grosor", "placa", "guia"):
        assert clave in r, clave
    assert isinstance(r["watertight"], bool) and isinstance(r["entra_a1"], bool)
    assert all(isinstance(x, str) for x in r["info"] + r["avisos"]) and isinstance(r["mensaje_a1"], str)
    assert r["etiquetas"] == ["0.6", "1.0", "1.4", "1.8", "2.2", "2.6", "3.0"] and r["grosores"] == [e["grosor"] for e in r["escalones"]]
    assert os.path.basename(r["ruta_stl"]) == "placa_calibracion_litofania.stl"
    assert abs(r["stl_mb"] * 1e6 - (84 + 50 * r["caras"])) < 1.0                         # STL binario: 84 + 50 por triángulo
    assert len(r["guia"]) >= 5 and all(g in r["info"] for g in r["guia"])
    assert any("0.6, 1.0, 1.4, 1.8, 2.2, 2.6, 3.0" in n for n in r["info"])
    assert not r["avisos"], r["avisos"]                                                    # una placa por defecto no avisa nada
    with _carpeta() as d:
        r1 = gen.generar(carpeta_salida=d, prefijo="mi placa", px_por_mm=2.0)
        r2 = gen.generar(carpeta_salida=d, prefijo="mi placa", px_por_mm=2.0)
        assert os.path.basename(r1["ruta_stl"]) == "mi_placa.stl"
        assert open(r1["ruta_stl"], "rb").read() == open(r2["ruta_stl"], "rb").read()        # determinista
        rs = gen.generar(carpeta_salida=d, px_por_mm=2.0, verificar=False)
        assert rs["verificacion"] is None and rs["watertight"] is True


def test_la_tabla_de_prediccion_sale_de_l2_y_la_simulacion_de_l5_la_confirma():
    r, _ = _generar()
    media = np.log(2.0) / (np.log(1 / 0.05) / (2.8 - 0.8))                              # la supuesta por L2: 0,05 de 0,8 a 2,8
    assert abs(r["media_luz_supuesta"] - media) < 1e-12
    esperadas = [100 * 0.5 ** ((t - 0.6) / media) for t in ESCALERA]
    assert np.allclose([f["luz_pct"] for f in r["tabla_prediccion"]], esperadas, rtol=1e-9)
    assert [f["etiqueta"] for f in r["tabla_prediccion"]] == r["etiquetas"]
    assert abs(r["tabla_prediccion"][0]["luz_pct"] - 100.0) < 1e-9 and np.all(np.diff([f["luz_pct"] for f in r["tabla_prediccion"]]) < 0)
    assert any("100 %" in n and "0.6 mm" in n for n in r["info"])
    # L5: la simulación del mapa de la placa deja pasar en cada franja justo eso
    mg = r["mapa_grosor"]
    assert isinstance(mg, lf.MapaGrosor) and abs(mg.media_luz_mm - media) < 1e-9
    sim = simular_contraluz(mg)
    px = r["px_por_mm"]
    centros = [(int(round((r["alto_mm"] - (Y_FRANJA0 + FH / 2)) * px)), int(round((_x_franja(k) + FW / 2) * px))) for k in range(7)]
    luz = np.array([sim.luz[f, c] for f, c in centros]) * 100
    assert np.allclose(luz, esperadas, rtol=1e-9) and np.all(np.diff(luz) < 0), luz
    assert np.all(np.diff([sim.vista[f, c] for f, c in centros]) < 0) and sim.px_saturados == 0
    # otra media luz supuesta cambia la tabla; una que sale del rango de L2 no rompe nada
    r2, _ = _generar(media_luz_supuesta=1.0, px_por_mm=2.0)
    assert abs(r2["tabla_prediccion"][-1]["luz_pct"] - 100 * 0.5 ** (2.4 / 1.0)) < 1e-9
    r3, _ = _generar(media_luz_supuesta=0.1, px_por_mm=2.0)
    assert r3["tabla_prediccion"] is None and r3["mapa_grosor"] is None and any("no hay tabla" in n for n in r3["info"])


def test_la_tabla_usa_los_grosores_reales_con_capas_y_los_avisos_de_la_placa_llegan():
    r, _ = _generar(capa_mm=0.12)
    media = r["media_luz_supuesta"]
    real = np.array(r["grosores"])
    assert np.allclose([f["luz_pct"] for f in r["tabla_prediccion"]], 100 * 0.5 ** ((real - real[0]) / media), rtol=1e-9)
    assert [f["grosor"] for f in r["tabla_prediccion"]] == r["grosores"]
    assert not any("Sin altura de capa" in n for n in r["info"])             # con capa, la nota de "sin capa" no va
    assert any("Sin altura de capa" in n for n in _generar()[0]["info"])
    r2, _ = _generar(n_franjas=7, grosor_min=0.6, grosor_max=1.0, capa_mm=0.4, px_por_mm=2.0)
    assert any("mismo nivel" in a for a in r2["avisos"]), r2["avisos"]       # el aviso de la placa sale en el resultado


def test_la_diagonal_y_el_watertight_del_resultado_salen_de_la_malla_de_verdad():
    with _carpeta() as d:
        a = gen.generar(carpeta_salida=d, px_por_mm=2.0, diagonal="adaptativa", prefijo="a")
        f = gen.generar(carpeta_salida=d, px_por_mm=2.0, diagonal="fija", prefijo="f")
        assert open(a["ruta_stl"], "rb").read() != open(f["ruta_stl"], "rb").read()
        assert a["watertight"] and f["watertight"] and a["caras"] == f["caras"]
        # el watertight es el que mide la verificación (o la malla), no una constante: se simula una malla abierta
        original_mesh, original_ver = lf.malla_desde_grilla_grosor, lf.verificar_malla
        try:
            def abierta(*a_, **k_):
                m = original_mesh(*a_, **k_)
                return trimesh.Trimesh(m.vertices, m.faces[:-1], process=False)
            lf.malla_desde_grilla_grosor = abierta
            lf.verificar_malla = lambda m: {"watertight": False, "ok": False}
            assert gen.generar(carpeta_salida=d, px_por_mm=2.0, prefijo="x")["watertight"] is False
            lf.verificar_malla = original_ver
            assert gen.generar(carpeta_salida=d, px_por_mm=2.0, prefijo="y", verificar=False)["watertight"] is False
        finally:
            lf.malla_desde_grilla_grosor, lf.verificar_malla = original_mesh, original_ver


def test_mapa_grosor_de_la_placa_es_coherente_con_l2():
    p = cal.placa_de_calibracion(px_por_mm=2.0)
    mg = cal.mapa_grosor_de_la_placa(p, 0.5)
    assert np.array_equal(mg.grosor, p.grosor) and mg.grosor is not None
    assert (mg.grosor_min, mg.grosor_max) == (0.6, 3.0) and mg.media_luz_mm == lf.media_luz_mm(mg.luz_minima, 0.6, 3.0)
    assert abs(mg.luz_minima - 0.5 ** (2.4 / 0.5)) < 1e-12
    assert abs(mg.coeficiente_atenuacion - np.log(2) / 0.5) < 1e-9 and mg.compensado is False
    assert abs(mg.media_luz_mm - 0.5) < 1e-9
    assert (mg.ancho_mm, mg.alto_mm, mg.ancho_px, mg.alto_px) == (p.ancho_mm, p.alto_mm, p.ancho_px, p.alto_px)
    _falla(cal.mapa_grosor_de_la_placa, p, 0.1)                       # luz mínima fuera de lo que admite L2


# ---------------------------------------------------------------------------
#  (4) main.py la lista y ejecutar() corre
# ---------------------------------------------------------------------------

def test_main_lista_la_placa_y_cumple_el_contrato():
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


def test_ejecutar_genera_el_stl_y_calibra_con_input_simulado():
    with _carpeta() as d:
        out = _ejecutar(["4", "0.8", "2.8", "0", ""], d)                         # 4 franjas 0,8-2,8, sin capa, sin grises
        stl = os.path.join(d, "placa_calibracion_litofania.stl")
        assert os.path.isfile(stl) and "watertight=True" in out and "ERROR" not in out 
        assert "0.80, 1.47, 2.13, 2.80" in out, out
        assert lf.verificar_malla(trimesh.load(stl))["ok"]
        # con capa: la placa cambia
        antes = open(stl, "rb").read()
        _ejecutar(["4", "0.8", "2.8", "0.12", ""], d)
        assert open(stl, "rb").read() != antes
        # ahora con los grises de una foto "perfecta" (media luz 0,5 mm): calibra y la recupera
        t = np.linspace(0.8, 2.8, 4)
        grises = np.round(oetf_srgb(0.8 * 0.5 ** ((t - 0.8) / 0.5)) * 255)
        out = _ejecutar(["4", "0.8", "2.8", "0", ",".join(f"{g:g}" for g in grises)], d)
        assert re.search(r"media luz = 0\.(49|50)\d", out) and "R²" in out and "luz mínima para 0.8-2.8 mm" in out and "ERROR" not in out, out
        assert re.search(r"luz mínima para 0\.8-2\.8 mm: 6\.[0-3]\d %", out), out         # 0,5^(2/0,5) = 6,25 %


def test_ejecutar_no_se_cae_con_entradas_malas():
    with _carpeta() as d:
        out = _ejecutar(["2", "", "", "", ""], d)
        assert "ERROR" in out and "n_franjas" in out and not os.listdir(d)
        out = _ejecutar(["", "3", "2", "", ""], d)                               # grosor_max menor que grosor_min
        assert "ERROR" in out and not os.listdir(d)
        out = _ejecutar(["4", "0.8", "2.8", "0", "100, 90"], d)                  # 2 grises para 4 franjas
        assert "ERROR" in out and "escribiste 2 grises" in out
        out = _ejecutar(["4", "0.8", "2.8", "0", "a, b, c, d"], d)
        assert "ERROR" in out and "números" in out
        out = _ejecutar(["4", "0.8", "2.8", "0", "255, 255, 255, 255"], d)       # todas saturadas
        assert "ERROR" in out and "franjas útiles" in out


# ---------------------------------------------------------------------------
#  (5) calibrar_luz_minima
# ---------------------------------------------------------------------------

def _grises(grosores, media, exposicion=0.8):
    """Los grises (float, sin redondear) que daría la foto de franjas de esos grosores con ese plástico: luz de
    Beer-Lambert -> sRGB -> 0-255. `exposicion` = la luz de la franja más fina (el brillo de la lámpara)."""
    grosores = np.asarray(grosores, dtype=float)
    return oetf_srgb(exposicion * 0.5 ** ((grosores - grosores[0]) / media)) * 255.0


def test_calibrar_recupera_k_exacto_en_la_ida_y_vuelta():
    t = np.array(ESCALERA)
    for media in (0.3, 0.4628, 0.8, 1.5):
        c = cal.calibrar_luz_minima(t, _grises(t, media), 0.6, 3.0)
        assert abs(c.k - np.log(2) / media) < 1e-9 * (np.log(2) / media), (media, c.k)
        assert abs(c.media_luz_mm - media) < 1e-9 * media
        assert c.r2 > 1 - 1e-12 and c.usadas == list(range(7)) and c.descartadas == [] and c.motivos == {}
        esperada = lf.luz_minima_desde_media_luz(media, 0.6, 3.0)
        assert abs(c.luz_minima - esperada) < 1e-9 * esperada
        if c.luz_minima_en_rango:
            assert abs(lf.coeficiente_atenuacion(c.luz_minima, 0.6, 3.0) - c.k) < 1e-9 * c.k
    # el mismo plástico da el mismo k con cualquier rango de grosores; el luz_minima cambia con el rango
    t2 = np.array([0.8, 1.2, 1.6, 2.0, 2.4, 2.8])
    c1 = cal.calibrar_luz_minima(t2, _grises(t2, 0.6), 0.8, 2.8)
    c2 = cal.calibrar_luz_minima(t2, _grises(t2, 0.6), 0.6, 3.0)
    assert abs(c1.k - c2.k) < 1e-12 and abs(c1.k - np.log(2) / 0.6) < 1e-9
    assert abs(c1.luz_minima - 0.5 ** (2.0 / 0.6)) < 1e-12 and abs(c2.luz_minima - 0.5 ** (2.4 / 0.6)) < 1e-12 and c2.luz_minima < c1.luz_minima
    assert (c1.grosor_min, c1.grosor_max) == (0.8, 2.8)
    # el supuesto de L2 (5 % de 0,8 a 2,8) se recupera tal cual
    media_l2 = lf.media_luz_mm(0.05, 0.8, 2.8)
    c = cal.calibrar_luz_minima(t2, _grises(t2, media_l2), 0.8, 2.8)
    assert abs(c.luz_minima - 0.05) < 1e-9 and c.luz_minima_en_rango and not c.avisos


def test_calibrar_con_grises_de_8_bits_queda_cerca_y_con_la_placa_simulada_por_l5():
    r, _ = _generar()
    for media in (0.4, 0.7):
        mg = cal.mapa_grosor_de_la_placa(r["placa"], media)
        sim = simular_contraluz(mg)
        px = r["px_por_mm"]
        grises = [np.round(sim.vista[int(round((r["alto_mm"] - (Y_FRANJA0 + FH / 2)) * px)), int(round((_x_franja(k) + FW / 2) * px))] * 255)
                  for k in range(7)]
        c = cal.calibrar_luz_minima(r["grosores"], grises, 0.6, 3.0)
        assert abs(c.media_luz_mm - media) / media < 0.04, (media, c.media_luz_mm, grises)
        assert c.r2 > 0.995
        # la franja de 0,6 mm se ve blanca (255) en la simulación y se descarta: son L5 y L6 de acuerdo
        assert grises[0] == 255 and 0 in c.descartadas and "saturada" in c.motivos[0]


def test_calibrar_no_depende_de_la_exposicion_de_la_foto():
    t = np.array(ESCALERA)
    base = cal.calibrar_luz_minima(t, _grises(t, 0.5, exposicion=0.9), 0.6, 3.0)
    for expo in (0.7, 0.4, 0.1 * 8.0):
        if expo * 0.5 ** (2.4 / 0.5) * 12.92 * 255 < 6:
            continue
        c = cal.calibrar_luz_minima(t, _grises(t, 0.5, exposicion=min(expo, 0.95)), 0.6, 3.0)
        assert abs(c.k - base.k) < 1e-9 * base.k and abs(c.luz_minima - base.luz_minima) < 1e-9
    c = cal.calibrar_luz_minima(t, _grises(t, 0.5, exposicion=0.35), 0.6, 3.0)
    assert abs(c.k - base.k) < 1e-9 * base.k


def test_calibrar_descarta_las_saturadas_y_las_del_ruido_con_sus_umbrales_exactos():
    t = np.array(ESCALERA)
    g = _grises(t, 0.5, exposicion=0.8)
    k_real = np.log(2) / 0.5
    # saturadas: con una lámpara que sobreexpone, las dos franjas más finas salen blancas (255, recortadas) y las
    # otras son la curva verdadera: se descartan las dos y el k sale exacto; sin descartarlas se arruina
    g_clip = oetf_srgb(np.minimum(2.0 * 0.5 ** ((t - 0.6) / 0.5), 1.0)) * 255.0
    assert g_clip[0] == g_clip[1] == 255.0 and g_clip[2] < 250
    c = cal.calibrar_luz_minima(t, g_clip, 0.6, 3.0)
    assert c.descartadas == [0, 1] and c.usadas == list(range(2, 7)) and abs(c.k - k_real) < 1e-9 * k_real
    assert all("saturada" in c.motivos[i] for i in (0, 1)) and any("Se descartaron 2 de 7" in a for a in c.avisos)
    c_mal = cal.calibrar_luz_minima(t, g_clip, 0.6, 3.0, gris_saturado=256, gris_ruido=-1)
    assert abs(c_mal.k - k_real) > 0.1 * k_real and c_mal.descartadas == []
    # el umbral: 250 se descarta (>=), 249 se usa
    for gris, descartada in ((250.0, True), (249.0, False), (249.99, False)):
        c = cal.calibrar_luz_minima(np.array([0.2, 0.6, 1.0, 1.4, 1.8]), np.array([gris, 200.0, 150.0, 110.0, 80.0]), 0.6, 1.8)
        assert (0 in c.descartadas) == descartada, (gris, c.descartadas)
    # ruido: 5 se descarta (<=), 6 se usa
    for gris, descartada in ((5.0, True), (6.0, False), (0.0, True)):
        c = cal.calibrar_luz_minima(np.array([0.6, 1.0, 1.4, 1.8, 2.2]), np.array([200.0, 150.0, 110.0, 80.0, gris]), 0.6, 2.2)
        assert (4 in c.descartadas) == descartada, (gris, c.descartadas)
        if descartada:
            assert "oscura" in c.motivos[4] and "ruido" in c.motivos[4]
    # los umbrales se pueden cambiar
    c = cal.calibrar_luz_minima(t, g, 0.6, 3.0, gris_saturado=g[1] + 1e-9, gris_ruido=g[-1] - 1)
    assert c.descartadas == [0], c.descartadas


def test_calibrar_pide_al_menos_tres_franjas_utiles():
    t = np.array(ESCALERA)
    g = _grises(t, 0.5)
    g_malo = g.copy()
    g_malo[0] = 255.0
    g_malo[1:5] = 255.0                                                           # 5 saturadas -> quedan 2 útiles
    _falla(cal.calibrar_luz_minima, t, g_malo, 0.6, 3.0, texto="2 franjas útiles")
    g_justo = g.copy()
    g_justo[:4] = 255.0                                                           # quedan 3: justo
    c = cal.calibrar_luz_minima(t, g_justo, 0.6, 3.0)
    assert len(c.usadas) == 3 and abs(c.k - np.log(2) / 0.5) < 1e-9 and any("poco robusto" in a for a in c.avisos)
    _falla(cal.calibrar_luz_minima, t, g_justo, 0.6, 3.0, min_franjas=4, texto="al menos 4")
    _falla(cal.calibrar_luz_minima, t[:2], g[:2], 0.6, 3.0, texto="franjas útiles")
    _falla(cal.calibrar_luz_minima, t, np.full(7, 255.0), 0.6, 3.0, texto="saturada")
    _falla(cal.calibrar_luz_minima, t, np.zeros(7), 0.6, 3.0, texto="oscura")


def test_calibrar_avisa_con_r2_bajo_y_no_si_es_exponencial():
    t = np.array(ESCALERA)
    c = cal.calibrar_luz_minima(t, _grises(t, 0.5), 0.6, 3.0)
    assert c.r2 > 0.999999 and not c.avisos
    # un plástico que dispersa: la luz cae como 1/(1 + 3·(t - 0,6)), muy lejos de una exponencial
    luz = 0.9 / (1.0 + (t - 0.6) * 3.0)
    g = oetf_srgb(luz) * 255.0
    assert g.min() > 5 and g.max() < 250
    c = cal.calibrar_luz_minima(t, g, 0.6, 3.0)
    y = np.log(lf.eotf_srgb(g / 255.0))
    r2_aparte = np.corrcoef(t, y)[0, 1] ** 2                                      # en una recta, R² = r²: cuenta independiente
    assert abs(c.r2 - r2_aparte) < 1e-9 and c.r2 < 0.98, c.r2
    assert any("R²" in a and f"{c.r2:.3f}" in a and "exponencial" in a for a in c.avisos), c.avisos
    # el umbral es el pedido: justo en el límite
    c_ok = cal.calibrar_luz_minima(t, g, 0.6, 3.0, r2_minimo=c.r2 - 1e-6)
    c_mal = cal.calibrar_luz_minima(t, g, 0.6, 3.0, r2_minimo=c.r2 + 1e-6)
    assert not [a for a in c_ok.avisos if "R²" in a] and [a for a in c_mal.avisos if "R²" in a]
    # ruido de la foto (±3 niveles): R² un poco menor, sigue siendo buena y recupera k a ~2 %
    ruido = np.array([2.0, -3.0, 1.0, 3.0, -2.0, 2.0, -1.0])
    c = cal.calibrar_luz_minima(t, _grises(t, 0.5) + ruido, 0.6, 3.0)
    assert 0.98 < c.r2 < 0.999 and abs(c.media_luz_mm - 0.5) / 0.5 < 0.05
    assert not [a for a in c.avisos if "R²" in a]                                  # buena aunque no perfecta: sin aviso


def test_calibrar_avisa_si_el_luz_minima_cae_fuera_de_lo_que_admite_el_generador():
    t = np.array([0.6, 0.9, 1.2, 1.6])
    c = cal.calibrar_luz_minima(t, _grises(t, 0.2), 0.6, 3.0)                    # media luz 0,2 mm: 0,5^12 = 0,02 %
    assert abs(c.media_luz_mm - 0.2) < 1e-9 and c.luz_minima_en_rango is False and c.luz_minima < lf.LUZ_MINIMA_RANGO[0]
    assert any("fuera" in a and "0.02" in a for a in c.avisos), c.avisos
    c2 = cal.calibrar_luz_minima(t, _grises(t, 0.2), 0.6, 1.0)                   # el mismo plástico en un rango angosto: bien
    assert c2.luz_minima_en_rango and not [a for a in c2.avisos if "fuera" in a]
    t3 = np.array([0.6, 1.0, 1.4, 1.8])
    c3 = cal.calibrar_luz_minima(t3, _grises(t3, 30.0), 0.6, 3.0)                # casi transparente: luz mínima 94 %
    assert c3.luz_minima_en_rango is False and c3.luz_minima > lf.LUZ_MINIMA_RANGO[1] and any("fuera" in a for a in c3.avisos)
    # en los bordes del rango: un pelo adentro (<= 50 %, >= 0,5 %) cuenta como en rango y un pelo afuera no
    t5 = np.array([0.6, 1.2, 1.8, 2.4, 3.0])
    for objetivo, en_rango in ((0.499, True), (0.501, False), (0.0051, True), (0.0049, False)):
        media = (3.0 - 0.6) / np.log2(1 / objetivo)
        c = cal.calibrar_luz_minima(t5, _grises(t5, media, 0.9), 0.6, 3.0)
        assert abs(c.luz_minima - objetivo) < 1e-9 and c.luz_minima_en_rango is en_rango, (objetivo, c.luz_minima)


def test_calibrar_rechaza_datos_que_no_sirven_y_no_modifica_lo_que_recibe():
    t = np.array(ESCALERA)
    g = _grises(t, 0.5)
    C = cal.calibrar_luz_minima
    _falla(C, t, g[:6], 0.6, 3.0, texto="7 grosores y 6 grises")
    _falla(C, t, np.append(g[:6], np.nan), 0.6, 3.0, texto="números")
    _falla(C, np.append(t[:6], np.inf), g, 0.6, 3.0, texto="números")
    _falla(C, t, np.append(g[:6], 256.0), 0.6, 3.0, texto="entre 0 y 255")
    _falla(C, t, np.append(g[:6], -1.0), 0.6, 3.0, texto="entre 0 y 255")
    _falla(C, np.append(t[:6], 0.0), g, 0.6, 3.0, texto="mayores que 0")
    _falla(C, t, g, 3.0, 0.6, texto="grosor_max")
    _falla(C, t, g, 0.0, 3.0, texto="grosor_min")
    _falla(C, np.full(7, 1.0), g, 0.6, 3.0, texto="mismo grosor")
    _falla(C, t, g[::-1], 0.6, 3.0, texto="no baja")                               # grises en orden inverso: la luz SUBE con el grosor
    _falla(C, t, np.full(7, 128.0), 0.6, 3.0, texto="no baja")                     # todo igual: pendiente 0
    _falla(C, np.array([1.0, 2.0, 3.0]), np.full(3, 128.0), 0.6, 3.0, texto="no baja")
    _falla(C, t, 128.0 + 0.001 * np.arange(7)[::-1], 0.6, 3.0, texto="no baja")      # baja una milésima: ruido, no medida
    _falla(C, np.array([1.0, 1.01, 1.02]), np.array([128.0, 127.98, 127.96]), 0.6, 3.0, texto="no baja")  # pendiente grande pero caída total mínima
    C(np.array([1.0, 1.01, 1.02]), np.array([128.0, 126.0, 124.0]), 0.6, 3.0)                              # una caída medible sí se acepta
    entrada_t, entrada_g = t.copy(), g.copy()
    C(t, g, 0.6, 3.0)
    assert np.array_equal(t, entrada_t) and np.array_equal(g, entrada_g)
    c = C(list(t), list(np.round(g)), 0.6, 3.0)                                    # acepta listas
    assert abs(c.media_luz_mm - 0.5) / 0.5 < 0.03
    c = C(t[::-1], g[::-1], 0.6, 3.0)                                              # y el orden de las franjas no importa (se ajusta una recta)
    assert abs(c.k - np.log(2) / 0.5) < 1e-9
    c = cal.calibrar_luz_minima(t, g)                                              # rango por defecto: el de L2 (0,8-2,8)
    assert (c.grosor_min, c.grosor_max) == (lf.GROSOR_MIN_DEFAULT, lf.GROSOR_MAX_DEFAULT)


def test_calibrar_usa_la_curva_srgb_y_no_trata_el_gris_como_luz_lineal():
    """El gris de una foto es sRGB: tratarlo como lineal subestima k (la cámara ya comprimió). Con grises generados
    con la curva sRGB el resultado es exacto; con otra interpretación NO lo sería."""
    t = np.array(ESCALERA)
    g = _grises(t, 0.5)
    c = cal.calibrar_luz_minima(t, g, 0.6, 3.0)
    k_lineal = -np.polyfit(t, np.log(g / 255.0), 1)[0]                              # lo que daría si se tomara el gris como luz
    assert abs(c.k - np.log(2) / 0.5) < 1e-9 and abs(k_lineal - c.k) > 0.1 * c.k


# ---------------------------------------------------------------------------
#  L1-L5 no se tocaron
# ---------------------------------------------------------------------------

def test_los_modulos_de_l1_a_l5_no_dependen_del_nuevo():
    for ruta in ("core/litofania.py", "core/litofania_simulacion.py", "generators/litofania.py"):
        txt = open(ruta, encoding="utf-8").read()
        assert "calibracion" not in txt, ruta
    assert os.path.isfile("core/litofania_calibracion.py")


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
