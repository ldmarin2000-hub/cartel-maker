#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_litofania_camara.py
------------------------------
Red de regresión para L9 de la litofanía: la cámara de luz (`core/litofania_camara.py`, `core/litofania_luz.py` y
`generators/camara_litofania.py`). Son cuatro piezas: la PLACA y el MARCO de L8 (el marco con cuatro clavijas), la
CÁMARA (brida con abertura, agujeros de clavijas y del cable) y la TAPA. Todo se mide sobre las MALLAS con rayos
(numpy puro) y con booleanas, sin mirar cómo se armaron. Lo que se cuida:

  * la abertura de la brida contiene la ventana (rayos sobre la foto no pegan en la cámara) y cubre >= 0,8 mm de banda;
  * el apilamiento en z no tiene juego (ceja | placa | brida contiguas) y las intersecciones booleanas entre las
    piezas dan volumen 0 (y con una cámara corrida o una clavija gorda, no);
  * las clavijas caen dentro de la corona del marco con el margen y el juego pedidos, y L8 da SALIDA IDÉNTICA con las
    clavijas apagadas (contra una copia de la construcción original y contra los hashes de los STL de L8);
  * el modelo de luz contra las fórmulas cerradas (una fuente, E = d²/(d²+ρ²)²) y contra una suma escrita acá;
  * las cuatro piezas son watertight, A1 por pieza (el marco manda), `main.py` las lista y L1-L5 / L8 no dependen de L9.

No usa pytest (ver AGENTS.md "Testing") -- funciones `test_*` con `assert` simple,
corribles con `python tests/test_litofania_camara.py`.
"""
import builtins
import contextlib
import hashlib
import io
import math
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

from core import carcasa_hueca as ch
from core import litofania as lf
from core import litofania_camara as cam_
from core import litofania_luz as luz
from core import litofania_marco as marco
from generators import camara_litofania as gen
from generators import marco_litofania as gen_l8

TOL = 1e-5            # los STL guardan float32
PIEZAS = ("placa", "marco", "camara", "tapa")


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
    """`generar()` de una foto chica (40 x 30 mm a 2 px/mm, la tira a 25 mm) en una carpeta temporal y las cuatro mallas en
    las coordenadas del ENSAMBLE: `(r, ens, stl)` con `ens` y `stl` dicts por pieza (`stl` = lo que se exportó, de
    impresión). Cachea por argumentos."""
    kw = dict(dict(ancho_mm=40.0, px_por_mm=2.0, distancia_led=25.0), **kw)
    clave = tuple(sorted(kw.items()))
    if clave not in _CACHE:
        with _carpeta() as d:
            r = gen.generar(_imagen(d), carpeta_salida=d, **kw)
            stl = {n: trimesh.load(r["ruta_stl_" + n]) for n in PIEZAS}
        geo, c = r["geometria"], r["camara_geometria"]
        ens = {"placa": marco.ensamblar_placa(stl["placa"], geo, kw.get("cara_visible", "relieve")),
               "marco": marco.malla_del_marco(geo, [(x, y, c.clavija_diam, c.clavija_largo) for x, y in c.clavijas]),
               "camara": cam_.malla_de_la_camara(c), "tapa": cam_.malla_de_la_tapa(c)}
        _CACHE[clave] = (r, ens, stl)
    return _CACHE[clave]


_PERM = {0: (1, 2, 0), 1: (2, 0, 1), 2: (0, 1, 2)}


def _golpes(malla, eje, a, b):
    """Coordenadas (sobre `eje`) de todos los impactos de un rayo paralelo a `eje` contra TODOS los triángulos, ordenadas.
    El rayo pasa por (a, b) en los otros dos ejes (ciclo x -> y -> z: eje 0: (y, z); eje 1: (z, x); eje 2: (x, y)). Numpy
    puro, misma técnica que tests/test_litofania_marco.py."""
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


def _bandas(placa, ancho=40.0, alto=30.0):
    """Banda en X y en Y de la placa, medida sobre su malla."""
    ext = placa.bounds[1] - placa.bounds[0]
    return (ext[0] - ancho) / 2, (ext[1] - alto) / 2


def _volumen_interseccion(a, b):
    r = trimesh.boolean.intersection([a, b], engine="manifold")
    if r is None or len(r.faces) == 0:
        return 0.0
    with np.errstate(all="ignore"):
        v = float(r.volume)
    return v if np.isfinite(v) else 0.0


def _movida(malla, dx=0.0, dy=0.0, dz=0.0):
    m = malla.copy()
    m.apply_translation([dx, dy, dz])
    return m


def _falla(f, *args, texto=None, **kw):
    try:
        f(*args, **kw)
    except ValueError as e:
        assert texto is None or texto in str(e), (texto, str(e))
        return
    raise AssertionError(f"tenía que fallar con ValueError: {args} {kw}")


def _poligono(r, n=32):
    """Área de un polígono regular de `n` lados inscripto en un círculo de radio `r` (lo que dibuja un cilindro de trimesh)."""
    return n / 2 * r * r * math.sin(2 * math.pi / n)


def _geo(ancho=40.0, alto=30.0, banda=2.0, grosor=2.8, **kw):
    return marco.geometria_del_marco(ancho, alto, banda, banda, grosor, **kw)


# ---------------------------------------------------------------------------
#  (1) la abertura de la brida contiene la ventana y cubre la banda
# ---------------------------------------------------------------------------

def test_la_abertura_contiene_la_ventana_rayos_sobre_la_foto_no_pegan_en_la_camara():
    r, ens, _ = _armar()
    camara, placa = ens["camara"], ens["placa"]
    bx, by = _bandas(placa)                                              # medidas sobre la placa, no sacadas del código
    x0, y0, x1, y1 = bx, by, bx + 40.0, by + 30.0                        # la imagen
    E, m = 4.5, 0.5
    rng = np.random.default_rng(1)
    for _ in range(300):                                                  # sobre la foto: la cámara no está
        x, y = rng.uniform(x0 + 0.01, x1 - 0.01), rng.uniform(y0 + 0.01, y1 - 0.01)
        assert len(_vertical(camara, x, y)) == 0, (x, y)
    e = 0.01
    for x, y in ((x0 + e, y0 + e), (x1 - e, y0 + e), (x0 + e, y1 - e), (x1 - e, y1 - e)):    # las cuatro esquinas de la foto
        assert len(_vertical(camara, x, y)) == 0, (x, y)
    for x, y in ((x0 - m + 0.01, 15.3), (x1 + m - 0.01, 15.3), (20.1, y0 - m + 0.01), (20.1, y1 + m - 0.01)):   # el margen de la abertura
        assert len(_vertical(camara, x, y)) == 0, (x, y)
    for x, y in ((x0 - m - 0.05, 15.3), (x1 + m + 0.05, 15.3), (20.1, y0 - m - 0.05), (20.1, y1 + m + 0.05)):   # justo afuera: la brida
        h = _vertical(camara, x, y)
        assert len(h) == 2 and abs(h[0] + E) < TOL and abs(h[1]) < TOL, (x, y, h)
    # los bordes de la abertura, con rayos horizontales dentro de la brida (z = -1), lejos de las clavijas
    ym, xm = (y0 + y1) / 2, (x0 + x1) / 2
    hx = _golpes(camara, 0, ym + 5.13, -1.0)
    hy = _golpes(camara, 1, -1.0, xm - 5.37)
    assert len(hx) == 4 and len(hy) == 4, (hx, hy)
    assert abs(hx[1] - (x0 - m)) < TOL and abs(hx[2] - (x1 + m)) < TOL, hx
    assert abs(hy[1] - (y0 - m)) < TOL and abs(hy[2] - (y1 + m)) < TOL, hy
    assert abs(hx[0] - (-6.0 + (bx - 2.0))) < 1e-4 and abs(hx[3] - (x1 + 8.0)) < 1e-4       # la huella es la del marco (borde de 8)


def test_la_brida_cubre_al_menos_08_mm_de_banda_aun_con_la_placa_corrida():
    r, ens, _ = _armar()
    camara, placa, geo, c = ens["camara"], ens["placa"], r["geometria"], r["camara_geometria"]
    bx, by = _bandas(placa)
    ym, xm = by + 15.0, bx + 20.0
    hx = _golpes(camara, 0, ym + 5.13, -1.0)
    hy = _golpes(camara, 1, -1.0, xm - 5.37)
    px0, py0, px1, py1 = placa.bounds[0][0], placa.bounds[0][1], placa.bounds[1][0], placa.bounds[1][1]
    cubre = {"izq": hx[1] - px0, "der": px1 - hx[2], "abajo": hy[1] - py0, "arriba": py1 - hy[2]}
    for lado, v in cubre.items():
        assert v - geo.holgura >= cam_.COBERTURA_BANDA_MIN - 1e-6, (lado, v)       # con la placa corrida hasta tocar el bolsillo
        assert abs(v - (bx - 0.5)) < 0.05 + abs(bx - by), (lado, v)                  # y es la banda menos el margen de la abertura
    assert abs(c.cobertura_banda - (min(bx, by) - 0.5 - geo.holgura)) < 0.1 and c.cobertura_banda >= 0.8
    # con la placa corrida `holgura` hacia un lado, la brida sigue cubriendo >= 0,8 mm de ese lado y no tapa nada de la foto
    corrida = _movida(placa, dx=geo.holgura)
    assert hx[1] - corrida.bounds[0][0] >= 0.8                                       # la brida cubre >= 0,8 mm de la banda del lado al que se corrió
    assert _volumen_interseccion(corrida, ens["marco"]) < 1e-9 and _volumen_interseccion(corrida, ens["camara"]) < 1e-9   # y no pisa a nadie


# ---------------------------------------------------------------------------
#  (2) apilamiento en z sin juego y booleanas
# ---------------------------------------------------------------------------

def test_el_apilamiento_en_z_no_tiene_juego_ceja_placa_brida_contiguas():
    r, ens, _ = _armar()
    placa = ens["placa"]
    bx, by = _bandas(placa)
    T, D, E = 2.8, 4.0, 4.5
    ym, xm = by + 15.0, bx + 20.0
    puntos = ((bx / 2, ym + 3.3137), (bx + 40.0 + bx / 2, ym - 3.1291), (xm - 3.1731, by / 2), (xm + 3.3419, by + 30.0 + by / 2))   # las cuatro bandas
    for x, y in puntos:
        for k in range(60):                                                     # sin pegarle justo a una arista de la malla (que cuenta dos impactos)
            xk, yk = x + 0.0137 * k, y + 0.0091 * k
            hp, hc, hm = _vertical(placa, xk, yk), _vertical(ens["camara"], xk, yk), _vertical(ens["marco"], xk, yk)
            if len(hp) == 2:
                break
        assert len(hp) == 2 and len(hc) == 2 and len(hm) == 2, (x, y, hp, hc, hm)
        assert abs(hc[0] + E) < TOL and abs(hc[1]) < TOL, hc                       # brida: de -4,5 a 0
        assert abs(hp[0]) < TOL and abs(hp[1] - T) < TOL, hp                       # placa (banda al grosor máximo): de 0 a 2,8
        assert abs(hm[0] - T) < TOL and abs(hm[1] - D) < TOL, hm                   # ceja: de 2,8 a 4
        assert abs(hc[1] - hp[0]) < TOL and abs(hp[1] - hm[0]) < TOL                # contiguas: ni juego ni solape
    # en el centro de la foto no hay brida ni ceja: la placa sola (el relieve nunca pasa de la ceja)
    h = _vertical(placa, xm, ym)
    assert len(_vertical(ens["camara"], xm, ym)) == 0 and len(_vertical(ens["marco"], xm, ym)) == 0 and h[1] <= T + TOL


def test_las_intersecciones_booleanas_entre_las_piezas_dan_volumen_cero():
    r, ens, _ = _armar()
    nombres = list(ens)
    for i, a in enumerate(nombres):
        for b in nombres[i + 1:]:
            assert _volumen_interseccion(ens[a], ens[b]) < 1e-9, (a, b)
    # y no es porque el chequeo no mire: una cámara 0,3 mm adelantada pisa a la placa y al marco; una clavija gorda, al agujero
    assert _volumen_interseccion(_movida(ens["camara"], dz=0.3), ens["placa"]) > 1.0
    assert _volumen_interseccion(_movida(ens["camara"], dz=0.3), ens["marco"]) > 1.0
    geo, c = r["geometria"], r["camara_geometria"]
    gorda = marco.malla_del_marco(geo, [(x, y, 3.2, c.clavija_largo) for x, y in c.clavijas])
    assert _volumen_interseccion(gorda, ens["camara"]) > 1.0
    assert _volumen_interseccion(_movida(ens["tapa"], dz=0.3), ens["camara"]) > 1.0          # la tapa sobre el escalón: pisaría


def test_la_tapa_entra_en_el_rebaje_con_su_holgura_y_apoya_en_el_escalon():
    r, ens, _ = _armar()
    c = r["camara_geometria"]
    P, zl, h, p = c.profundidad, c.z_ledge, c.holgura_tapa, c.pared
    ex = r["geometria"].exterior
    tapa, camara = ens["tapa"], ens["camara"]
    assert abs(P - (25.0 + 3.0 + 2.0)) < 1e-9 and abs(zl - 28.0) < 1e-9                       # distancia + tira + tapa
    assert np.abs(tapa.bounds[:, 2] - [-P, -zl]).max() < TOL                                  # la tapa ocupa los últimos 2 mm
    assert np.abs(camara.bounds[:, 2] - [-P, 0.0]).max() < TOL
    y = (ex[1] + ex[3]) / 2 + 5.13
    z = -P + 1.0                                                                              # a mitad del espesor de la tapa
    hc, ht = _golpes(camara, 0, y, z), _golpes(tapa, 0, y, z)
    assert len(hc) == 4 and len(ht) == 2, (hc, ht)
    assert abs(hc[0] - ex[0]) < TOL and abs(hc[1] - (ex[0] + p)) < TOL and abs(hc[2] - (ex[2] - p)) < TOL and abs(hc[3] - ex[2]) < TOL
    assert abs((ht[0] - hc[1]) - h) < TOL and abs((hc[2] - ht[1]) - h) < TOL                # holgura de la tapa a cada lado
    x = ex[0] + p + 1.0                                                                       # sobre el escalón (entre la pared y la cavidad)
    hc, ht = _vertical(camara, x, y), _vertical(tapa, x, y)
    assert len(hc) == 2 and len(ht) == 2, (hc, ht)
    assert abs(hc[0] + zl) < TOL and abs(hc[1]) < TOL and abs(ht[0] + P) < TOL and abs(ht[1] + zl) < TOL    # la tapa apoya en el escalón
    esperado = (56.0 - 2 * (p + h)) * (46.0 - 2 * (p + h)) * c.tapa_espesor                  # la tapa es un rectángulo
    assert abs(tapa.volume - esperado) < 1e-6 * esperado


# ---------------------------------------------------------------------------
#  (3) las clavijas: dentro de la corona, con el juego pedido, y L8 intacto sin ellas
# ---------------------------------------------------------------------------

def test_las_clavijas_estan_en_la_corona_del_marco_con_el_margen_pedido():
    r, ens, _ = _armar()
    geo, c, marco_ens = r["geometria"], r["camara_geometria"], ens["marco"]
    ex, b = geo.exterior, geo.bolsillo
    assert len(c.clavijas) == 4 and c.clavija_diam == 2.5 and c.clavija_largo == 3.0
    ym = (ex[1] + ex[3]) / 2
    for x, y in c.clavijas:
        # la clavija, medida SOBRE LA MALLA del marco a z = -1 (donde solo hay clavijas): su diámetro y su centro
        sobre_x, sobre_y = _golpes(marco_ens, 0, y, -1.0), _golpes(marco_ens, 1, -1.0, x)
        mia_x = [v for v in sobre_x if abs(v - x) < 1.3]
        mia_y = [v for v in sobre_y if abs(v - y) < 1.3]
        assert len(mia_x) == 2 and len(mia_y) == 2, (x, y, sobre_x, sobre_y)
        assert abs((mia_x[1] - mia_x[0]) - 2.5) < 0.02 and abs((mia_x[0] + mia_x[1]) / 2 - x) < 1e-4
        assert abs((mia_y[1] - mia_y[0]) - 2.5) < 0.02 and abs((mia_y[0] + mia_y[1]) / 2 - y) < 1e-4
        # la corona donde está (rayos horizontales a z = +1, dentro del marco: borde exterior y pared del bolsillo)
        if abs(y - ym) < 1e-6:                                          # corona izquierda o derecha: se mide en x
            ex0, bo0, bo1, ex1 = _golpes(marco_ens, 0, y, 1.0)
            assert abs(ex0 - ex[0]) < TOL and abs(bo0 - b[0]) < TOL and abs(bo1 - b[2]) < TOL and abs(ex1 - ex[2]) < TOL
            izq, der = (ex0, bo0) if x < (ex0 + ex1) / 2 else (bo1, ex1)
            ancho = mia_x
        else:                                                           # corona de abajo o de arriba: se mide en y
            ey0, by0, by1, ey1 = _golpes(marco_ens, 1, 1.0, x)
            assert abs(ey0 - ex[1]) < TOL and abs(by0 - b[1]) < TOL and abs(by1 - b[3]) < TOL and abs(ey1 - ex[3]) < TOL
            izq, der = (ey0, by0) if y < (ey0 + ey1) / 2 else (by1, ey1)
            ancho = mia_y
        assert ancho[0] - izq >= cam_.MARGEN_CLAVIJA_MIN - 0.02 and der - ancho[1] >= cam_.MARGEN_CLAVIJA_MIN - 0.02, (x, y)
        assert abs((ancho[0] - izq) - (der - ancho[1])) < 0.02                                    # centrada en la corona
        # sale hacia atrás: la punta en z = -largo, y por el otro lado no asoma (el marco tapa su extremo en z = D)
        h = _vertical(marco_ens, x, y)
        assert len(h) == 2 and abs(h[0] + 3.0) < TOL and abs(h[1] - 4.0) < TOL, (x, y, h)
    # una clavija en cada corona (izquierda, derecha, abajo, arriba); las de abajo y arriba corridas: la cámara solo entra de una manera
    assert sum(abs(p[1] - ym) < 1e-6 for p in c.clavijas) == 2
    assert abs(c.clavijas[2][0] - c.clavijas[3][0]) < 1e-9 and abs(c.clavijas[2][0] - ((ex[0] + ex[2]) / 2 + 56.0 / 6)) < 1e-9
    assert c.clavijas[2][1] < ym < c.clavijas[3][1] and c.clavijas[0][0] < c.clavijas[1][0]


def test_los_agujeros_de_la_brida_dan_el_juego_pedido_y_no_atraviesan_la_brida():
    for kw, (diam, juego, largo) in (({}, (2.5, 0.15, 3.0)), (dict(clavija_diam=3.0, juego_clavija=0.3, clavija_largo=2.0), (3.0, 0.3, 2.0))):
        r, ens, _ = _armar(**kw)
        c, camara, marco_ens = r["camara_geometria"], ens["camara"], ens["marco"]
        rad = diam / 2                                                            # lo pedido, no lo que dice la geometría del resultado
        for x, y in c.clavijas:
            hc = _golpes(camara, 0, y, -1.0)                                 # a z = -1, a lo largo de x, por el centro de la clavija
            hm = _golpes(marco_ens, 0, y, -1.0)
            # el agujero (dos impactos de la cámara alrededor de la clavija) y la clavija (dos impactos del marco)
            en_agujero = [v for v in hc if abs(v - x) < rad + juego + 0.05]
            en_clavija = [v for v in hm if abs(v - x) < rad + 0.05]
            assert len(en_agujero) == 2 and len(en_clavija) == 2, (x, y, hc, hm)
            assert abs((en_clavija[0] - en_agujero[0]) - juego) < 0.02 and abs((en_agujero[1] - en_clavija[1]) - juego) < 0.02, (kw, hc, hm)
            assert abs((en_agujero[1] - en_agujero[0]) - (2 * rad + 2 * juego)) < 0.03
            # el agujero es ciego: a (x, y) la cámara tiene el techo del agujero a `largo + 0,5` y el fondo de la brida a -4,5
            h = _vertical(camara, x, y)                                               # el agujero es CIEGO: techo a `largo + 0,5`, y atrás hay material
            assert len(h) == 2 and abs(h[1] + (largo + 0.5)) < TOL, (x, y, h)
            assert abs(h[0] + c.z_ledge) < TOL or abs(h[0] + c.espesor_brida) < TOL, (x, y, h)   # hasta el escalón (la clavija cae sobre él)
            assert abs((-largo) - (h[1] + 0.5)) < TOL                                 # la punta de la clavija queda 0,5 mm antes del techo
            assert (h[1] - h[0]) >= cam_.TECHO_AGUJERO_MIN - 1e-9                     # y hay material sobre el agujero


_GOLDEN_L8 = {
    "base": ("59eea902be95483e4b626d645618e253255d78a783b705a7cdc5bf3302a6e34c", "174f6dd03051137c89bce3fdbe5930bf5863b8b41f523f14ff8649e8f5b61ab3",
             "0283fc3a91adf3f0ec4e10a186a69e7309bd345c6d532bde5e09ee3d75e4b2be", {}),
    "plana": ("9c836afed1e04c0d2e8dd70d59689bd1f035bb7836fdc5b27832c6cecdcb98f6", "174f6dd03051137c89bce3fdbe5930bf5863b8b41f523f14ff8649e8f5b61ab3",
              "ad319eaa50a8a3ba68282457c38142d3ebeeca5a6aac56f29d0f9c320485992e", {"cara_visible": "plana"}),
    "h0": ("59eea902be95483e4b626d645618e253255d78a783b705a7cdc5bf3302a6e34c", "a49b2a98884861261322cc3df92875fd2449dea2269dd3f2a63d0bbee12d6712",
           "118b8057baf9eb80d4d745f243bc6803748d55b59bb4032adae4097996c92428", {"holgura": 0.0}),
    "borde10": ("f68f616ed0e94f75850248a625833cf0ddf3ce88444a3114cd13f574b2f9b547", "9b152a83d588cd45d99ad791d228db578ebca2f54b9cfd42969a0af142084fa7",
                "099c8a8530ca686f827885843d37cb8edc6563e24ae11387a08d77d78943be9c",
                {"ancho_borde": 10.0, "grosor_ceja": 1.5, "margen_encastre": 2.5, "holgura": 0.4}),
}


def _sha(ruta):
    return hashlib.sha256(open(ruta, "rb").read()).hexdigest()


def test_l8_da_salida_identica_con_las_clavijas_apagadas():
    # 1) la malla del marco sin clavijas es la construcción ORIGINAL de L8 (caja - ventana - bolsillo), bit a bit
    for kw in ({}, dict(ancho_borde=10.0, grosor_ceja=1.5, holgura=0.4), dict(holgura=0.0)):
        geo = _geo(**kw)
        ex, v, b = geo.exterior, geo.ventana, geo.bolsillo
        caja = lambda x0, y0, z0, x1, y1, z1: _movida(trimesh.creation.box(extents=[x1 - x0, y1 - y0, z1 - z0]),
                                                      (x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)
        original = trimesh.boolean.difference([caja(ex[0], ex[1], 0.0, ex[2], ex[3], geo.profundidad_total),
                                               caja(v[0], v[1], -1.0, v[2], v[3], geo.profundidad_total + 1.0)], engine="manifold")
        original = trimesh.boolean.difference([original, caja(b[0], b[1], -1.0, b[2], b[3], geo.profundidad_bolsillo)], engine="manifold")
        for clavijas in (None, [], ()):
            m = marco.malla_del_marco(geo) if clavijas is None else marco.malla_del_marco(geo, clavijas)
            assert np.array_equal(m.vertices, original.vertices) and np.array_equal(m.faces, original.faces), (kw, clavijas)
        assert marco.malla_del_marco(geo, None).vertices.shape == marco.malla_del_marco(geo).vertices.shape
    # 2) y con clavijas la malla es OTRA (si no, no se probaría nada)
    geo = _geo()
    con = marco.malla_del_marco(geo, cam_.clavijas_del_marco(geo))
    assert len(con.faces) > len(marco.malla_del_marco(geo).faces) and con.bounds[0][2] < -2.9
    # 3) el generador de L8 da los mismos STL con y sin `clavijas` apagado, y son los de antes de L9 (hashes escritos acá)
    with _carpeta() as d:
        ruta = _imagen(d)
        for nombre, (hp, hm, hi, kw) in _GOLDEN_L8.items():
            a = gen_l8.generar(ruta, ancho_mm=40.0, px_por_mm=2.0, carpeta_salida=d, prefijo=nombre, **kw)
            assert _sha(a["ruta_stl_placa"]) == hp and _sha(a["ruta_stl_marco"]) == hm, nombre
            assert hashlib.sha256("\n".join(a["info"] + a["avisos"]).encode()).hexdigest() == hi, nombre
            b = gen_l8.generar(ruta, ancho_mm=40.0, px_por_mm=2.0, carpeta_salida=d, prefijo=nombre + "_n", clavijas=None, **kw)
            assert _sha(b["ruta_stl_marco"]) == hm and _sha(b["ruta_stl_placa"]) == hp and b["info"] == a["info"] and b["avisos"] == a["avisos"]
        c = gen_l8.generar(ruta, ancho_mm=40.0, px_por_mm=2.0, carpeta_salida=d, prefijo="con", clavijas=lambda g: cam_.clavijas_del_marco(g))
        assert _sha(c["ruta_stl_marco"]) != _GOLDEN_L8["base"][1] and _sha(c["ruta_stl_placa"]) == _GOLDEN_L8["base"][0]


def test_las_clavijas_validan_la_corona_y_los_parametros():
    g = _geo()
    cl = cam_.clavijas_del_marco(g)
    assert len(cl) == 4 and all(len(t) == 4 and t[2] == 2.5 and t[3] == 3.0 for t in cl)
    assert cam_.posiciones_de_clavijas(g) == tuple((x, y) for x, y, _, _ in cl)
    assert cam_.clavijas_del_marco(g, 3.4, 5.0)[0][2:] == (3.4, 5.0)
    _falla(cam_.clavijas_del_marco, g, diametro=0, texto="diámetro")
    _falla(cam_.clavijas_del_marco, g, largo=0, texto="largo")
    _falla(cam_.clavijas_del_marco, g, juego=0, texto="juego")
    _falla(cam_.clavijas_del_marco, g, juego=-0.1, texto="juego")
    # la corona de este marco mide 5,75: 2,5 + 2·0,15 + 2·1,0 = 4,8 entra; hasta 6,0 - 0,3 - 2,0 -> diámetro 3,45 sí, 3,5 no
    assert cam_.clavijas_del_marco(g, diametro=3.4)
    _falla(cam_.clavijas_del_marco, g, diametro=3.5, texto="corona")
    _falla(cam_.clavijas_del_marco, _geo(ancho_borde=5.0), texto="subí ancho_borde")


# ---------------------------------------------------------------------------
#  (4) el modelo de luz contra las fórmulas cerradas
# ---------------------------------------------------------------------------

def test_iluminancia_de_una_fuente_es_d2_sobre_d2_mas_rho2_al_cuadrado():
    f = np.array([[0.0, 0.0]])
    for d in (5.0, 12.0, 20.0):
        for rho in (0.0, 3.0, 4.0, 10.0, 25.0):
            esperado = d * d / (d * d + rho * rho) ** 2
            assert abs(luz.iluminancia(rho, 0.0, f, d) - esperado) < 1e-15 * max(1.0, esperado)
    assert abs(luz.iluminancia(3.0, 4.0, f, 5.0) - 0.01) < 1e-15                         # d = 5, rho = 5: 25 / 50² = 0,01
    assert abs(luz.iluminancia(0.0, 0.0, f, 4.0) - 1 / 16.0) < 1e-15                      # en el eje: 1 / d²
    # simetría y superposición: dos fuentes suman; mover todo no cambia nada; el eje x y el y valen lo mismo
    dos = np.array([[-7.0, 2.0], [5.0, -1.0]])
    for x, y in ((0.0, 0.0), (3.0, 4.0), (-9.0, 8.0)):
        suma = sum(luz.iluminancia(x, y, np.array([p]), 10.0) for p in dos)
        assert abs(luz.iluminancia(x, y, dos, 10.0) - suma) < 1e-15
        assert abs(luz.iluminancia(x + 100, y - 50, dos + [100, -50], 10.0) - suma) < 1e-14
    assert abs(luz.iluminancia(3.0, 0.0, f, 7.0) - luz.iluminancia(0.0, 3.0, f, 7.0)) < 1e-18
    e = luz.iluminancia(np.array([[0.0, 1.0], [2.0, 3.0]]), np.array([[0.0, 0.0], [1.0, 1.0]]), f, 5.0)     # arrays: misma forma
    assert e.shape == (2, 2) and e[0, 0] == luz.iluminancia(0.0, 0.0, f, 5.0)
    _falla(luz.iluminancia, 0.0, 0.0, f, 0.0, texto="distancia")
    _falla(luz.iluminancia, 0.0, 0.0, f, -1.0, texto="distancia")


def test_las_fuentes_de_la_tira_son_una_grilla_centrada_y_simetrica():
    f = luz.fuentes_de_la_tira(33.4, 16.7, 16.7, 16.7)
    assert f.shape == (6, 2) and abs(f.mean(axis=0)).max() < 1e-12
    assert sorted(set(np.round(f[:, 0], 6))) == [-16.7, 0.0, 16.7] and sorted(set(np.round(f[:, 1], 6))) == [-8.35, 8.35]
    f = luz.fuentes_de_la_tira(0.5, 0.5, 16.7, 16.7)                                     # no entra ni uno entero: una sola fuente, en el centro
    assert f.shape == (1, 2) and abs(f).max() == 0.0
    f = luz.fuentes_de_la_tira(108.0, 83.0, 16.7, 20.0)                                  # 6 pasos de 16,7 = 100,2 <= 108: 7 columnas; 4 de 20: 5 filas
    assert f.shape == (35, 2) and abs(f[:, 0].max() - 50.1) < 1e-9 and abs(f[:, 1].max() - 40.0) < 1e-9
    f = luz.fuentes_de_la_tira(50.0, 50.0, 10.0, 10.0)                                   # justo 5 pasos: 6 por lado, el redondeo no se come uno
    assert f.shape == (36, 2)
    assert luz.fuentes_de_la_tira(0.3, 0.3, 0.1, 0.1).shape == (16, 2)                    # 0,3 / 0,1 da 2,9999999999999996: son 3 pasos, 4 LED por lado
    _falla(luz.fuentes_de_la_tira, 0, 10, 5, 5)
    _falla(luz.fuentes_de_la_tira, 10, 0, 5, 5)
    _falla(luz.fuentes_de_la_tira, 10, 10, 0, 5)
    _falla(luz.fuentes_de_la_tira, 10, 10, 5, 0)


def test_uniformidad_de_una_sola_fuente_es_la_formula_cerrada():
    # una sola fuente (la cámara no alcanza a tener dos LED): el máximo es en el eje (1/d²) y el mínimo en la esquina
    for d, p, s, w, h in ((20.0, 16.7, 16.7, 100.0, 75.0), (12.0, 10.0, 25.0, 40.0, 30.0), (7.0, 16.7, 8.3, 60.0, 60.0)):
        u = luz.uniformidad_de_luz(d, p, s, ancho_camara=0.5, alto_camara=0.5, ancho_imagen=w, alto_imagen=h)
        assert u.n_leds == 1
        e_esq = lambda rho2: d * d / (d * d + rho2) ** 2
        # borde/centro: la esquina de la imagen contra el centro
        esperado_bc = e_esq((w / 2) ** 2 + (h / 2) ** 2) / (1 / d ** 2)
        assert abs(u.borde_centro - esperado_bc) < 1e-12, (u.borde_centro, esperado_bc)
        # rizado: la esquina de la celda p x s contra el centro
        emin, emax = e_esq((p / 2) ** 2 + (s / 2) ** 2), 1 / d ** 2
        assert abs(u.rizado_local - (emax - emin) / (emax + emin)) < 1e-12, (u.rizado_local, d, p, s)
        assert (u.distancia, u.paso_led, u.separacion_filas) == (d, p, s)
    # la suma escrita acá: 2 x 2 fuentes, el punto del centro (a 8,35 mm de cada una en x e y: rho² = 2·8,35²) y el de una fuente
    d, p = 20.0, 16.7
    f = luz.fuentes_de_la_tira(p, p, p, p)
    assert f.shape == (4, 2)
    caso = lambda x, y: sum(d * d / (d * d + (x - fx) ** 2 + (y - fy) ** 2) ** 2 for fx, fy in [(-p / 2, -p / 2), (p / 2, -p / 2), (-p / 2, p / 2), (p / 2, p / 2)])
    for x, y in ((0.0, 0.0), (p / 2, p / 2), (3.0, -4.0), (p / 2, 0.0)):
        assert abs(luz.iluminancia(x, y, f, d) - caso(x, y)) < 1e-15
    u = luz.uniformidad_de_luz(d, p, p, ancho_camara=p, alto_camara=p, ancho_imagen=p, alto_imagen=p, resolucion=101)
    # el máximo y el mínimo de la celda, por fuerza bruta con bucles de Python sobre la misma grilla de 101 x 101
    valores = [caso(-p / 2 + p * i / 100, -p / 2 + p * j / 100) for i in range(101) for j in range(101)]
    emax, emin = max(valores), min(valores)
    assert emin < emax and abs(emax - caso(0.0, 0.0)) < 1e-15                                   # con la tira más corta que la distancia, el máximo es el centro
    assert abs(u.rizado_local - (emax - emin) / (emax + emin)) < 1e-12 and u.n_leds == 4
    assert abs(u.borde_centro - emin / emax) < 1e-12


def test_el_modelo_baja_el_rizado_al_alejar_la_tira_y_da_los_numeros_conocidos():
    # tira de 60 LED/m en filas separadas lo mismo, cámara de 108 x 108 y foto de 100 x 100
    esperado = {12.0: (0.130, 0.66), 16.0: (0.035, 0.63), 20.0: (0.011, 0.56), 25.0: (0.005, 0.51)}
    anterior = None
    for d, (rizado, borde) in esperado.items():
        u = luz.uniformidad_de_luz(d, 16.7, 16.7, 108.0, 108.0, 100.0, 100.0)
        assert abs(u.rizado_local - rizado) < 0.006 and abs(u.borde_centro - borde) < 0.011, (d, u.rizado_local, u.borde_centro)
        if anterior:
            assert u.rizado_local < anterior.rizado_local and u.borde_centro < anterior.borde_centro                 # puntos bajan, bordes también
        anterior = u
    u1 = luz.uniformidad_de_luz(20.0, 8.3, 25.0, 108.0, 108.0, 100.0, 100.0)                  # tira de 120 LED/m en filas más separadas
    assert abs(u1.rizado_local - 0.046) < 0.006 and u1.rizado_local > luz.uniformidad_de_luz(20.0, 8.3, 8.3, 108.0, 108.0, 100.0, 100.0).rizado_local
    # la regla: con la distancia >= ~1,0 - 1,2 veces el mayor entre el paso de los LED y la separación de las filas, no se ven puntos
    assert luz.uniformidad_de_luz(1.2 * 16.7, 16.7, 16.7, 108.0, 108.0, 100.0, 100.0).rizado_local < 0.03
    assert luz.uniformidad_de_luz(0.5 * 16.7, 16.7, 16.7, 108.0, 108.0, 100.0, 100.0).rizado_local > 0.3
    assert luz.uniformidad_de_luz(16.0, 16.7, 16.7, 108.0, 108.0, 100.0, 100.0, resolucion=51).n_leds == 49
    _falla(luz.uniformidad_de_luz, 0.0, texto="distancia")
    _falla(luz.uniformidad_de_luz, 10.0, paso_led=0.0, texto="paso_led")
    _falla(luz.uniformidad_de_luz, 10.0, separacion_filas=0.0, texto="separacion_filas")
    _falla(luz.uniformidad_de_luz, 10.0, ancho_imagen=0.0, texto="imagen")
    _falla(luz.uniformidad_de_luz, 10.0, alto_imagen=0.0, texto="imagen")
    _falla(luz.uniformidad_de_luz, 10.0, resolucion=2, texto="resolucion")
    _falla(luz.uniformidad_de_luz, 10.0, resolucion=5.5, texto="resolucion")


def test_distancia_minima_y_separacion_maxima_son_las_inversas_del_modelo():
    for p, s in ((16.7, 16.7), (8.3, 25.0), (16.7, 8.3)):
        dm = luz.distancia_minima(p, s, 0.05, 108.0, 108.0)
        assert abs(luz.uniformidad_de_luz(dm, p, s, 108.0, 108.0, 10.0, 10.0).rizado_local - 0.05) < 1e-4, (p, s, dm)
        assert luz.uniformidad_de_luz(dm - 0.2, p, s, 108.0, 108.0, 10.0, 10.0).rizado_local > 0.05
        assert luz.uniformidad_de_luz(dm + 0.2, p, s, 108.0, 108.0, 10.0, 10.0).rizado_local < 0.05
    dm = luz.distancia_minima(16.7, 16.7, 0.05, 108.0, 108.0)
    assert 0.8 * 16.7 < dm < 1.0 * 16.7                                                   # el 5 % es un poco menos que "1,0 veces"
    assert luz.distancia_minima(16.7, 16.7, 0.02, 108.0, 108.0) > dm                       # pedir menos puntos aleja la tira
    sm = luz.separacion_maxima_de_filas(20.0, 16.7, 0.05, 108.0, 108.0)
    assert abs(luz.uniformidad_de_luz(20.0, 16.7, sm, 108.0, 108.0, 10.0, 10.0).rizado_local - 0.05) < 1e-4
    assert luz.separacion_maxima_de_filas(30.0, 16.7, 0.05, 108.0, 108.0) > sm              # más lejos, filas más separadas
    assert luz.distancia_minima() == luz.distancia_minima(luz.PASO_LED_DEFAULT, luz.PASO_LED_DEFAULT, luz.RIZADO_MAX_DEFAULT, 100.0, 100.0)
    _falla(luz.distancia_minima, 16.7, 16.7, 0.0, texto="rizado_max")
    _falla(luz.distancia_minima, 16.7, 16.7, 1.0, texto="rizado_max")
    _falla(luz.distancia_minima, 0.0, 16.7, 0.05, texto="paso_led")
    _falla(luz.separacion_maxima_de_filas, 20.0, 16.7, 0.0, texto="rizado_max")
    _falla(luz.separacion_maxima_de_filas, 20.0, 16.7, 1.5, texto="rizado_max")
    _falla(luz.separacion_maxima_de_filas, 0.0, texto="distancia")
    _falla(luz.separacion_maxima_de_filas, 3.0, 16.7, 0.05, texto="paso del LED")             # a 3 mm con LED cada 16,7 no hay separación que alcance


def test_los_avisos_de_luz_saltan_justo_pasado_el_limite():
    U = luz.UniformidadLuz
    ok = U(20.0, 16.7, 16.7, 49, luz.RIZADO_MAX_DEFAULT, luz.BORDE_CENTRO_MIN_DEFAULT)
    assert luz.avisos_de_luz(ok) == []                                                    # justo en el límite: no avisa
    assert luz.RIZADO_MAX_DEFAULT == 0.05 and luz.BORDE_CENTRO_MIN_DEFAULT == 0.5 and luz.PASO_LED_DEFAULT == 16.7
    a = luz.avisos_de_luz(U(10.0, 16.7, 16.7, 49, 0.0501, 0.9), ancho_camara=108.0, alto_camara=108.0)
    assert len(a) == 1 and "10 mm de la placa" in a[0] and "puntos" in a[0] and "5.0 %" in a[0] and "5 %" in a[0]
    minima = luz.distancia_minima(16.7, 16.7, 0.05, 108.0, 108.0)
    assert f"{minima:.0f} mm o más" in a[0]
    b = luz.avisos_de_luz(U(60.0, 16.7, 16.7, 49, 0.001, 0.4999))
    assert len(b) == 1 and "bordes" in b[0] and "paredes blancas" in b[0] and "50 %" in b[0]
    assert "se tolera 50 %" in b[0]
    c = luz.avisos_de_luz(U(10.0, 16.7, 16.7, 49, 0.2, 0.2), ancho_camara=108.0, alto_camara=108.0)
    assert len(c) == 2                                                                    # los dos a la vez
    assert luz.avisos_de_luz(U(10.0, 16.7, 16.7, 49, 0.04, 0.45), rizado_max=0.03, borde_centro_min=0.4, ancho_camara=108.0, alto_camara=108.0)[0].count("3 %") >= 1
    assert luz.avisos_de_luz(U(10.0, 16.7, 16.7, 49, 0.04, 0.45), rizado_max=0.05, borde_centro_min=0.4) == []
    # con un modelo real: 100 x 100 a 25 mm está bien; a 8 mm se ven puntos; a 60 mm los bordes quedan oscuros
    assert luz.avisos_de_luz(luz.uniformidad_de_luz(25.0, 16.7, 16.7, 108.0, 108.0, 100.0, 100.0), ancho_camara=108.0, alto_camara=108.0) == []
    assert len(luz.avisos_de_luz(luz.uniformidad_de_luz(8.0, 16.7, 16.7, 108.0, 108.0, 100.0, 100.0), ancho_camara=108.0, alto_camara=108.0)) >= 1
    assert any("bordes" in x for x in luz.avisos_de_luz(luz.uniformidad_de_luz(20.0, 16.7, 16.7, 40.0, 40.0, 100.0, 100.0), ancho_camara=40.0, alto_camara=40.0))


# ---------------------------------------------------------------------------
#  la geometría de la cámara (core)
# ---------------------------------------------------------------------------

def test_la_geometria_pone_la_abertura_la_cavidad_y_la_profundidad_en_su_lugar():
    g = _geo()
    c = cam_.geometria_de_la_camara(g)
    assert (c.distancia_led, c.grosor_tira, c.pared, c.espesor_brida, c.soporte_tapa, c.tapa_espesor, c.holgura_tapa, c.margen_abertura) == \
        (20.0, 3.0, 2.0, 4.5, 2.0, 2.0, 0.3, 0.5)
    assert (c.lado_cable, c.cable_diam, c.clavija_diam, c.clavija_largo, c.juego_clavija) == ("abajo", 5.0, 2.5, 3.0, 0.15)
    assert abs(c.profundidad - 25.0) < 1e-12 and abs(c.z_ledge - 23.0) < 1e-12
    assert c.abertura == (1.5, 1.5, 42.5, 32.5) and c.cavidad == (-2.0, -2.0, 46.0, 36.0)
    assert c.interior == (48.0, 38.0) and abs(c.cobertura_banda - 1.25) < 1e-12 and c.geo is g
    assert c.clavijas == cam_.posiciones_de_clavijas(g)
    c2 = cam_.geometria_de_la_camara(g, distancia_led=30.0, grosor_tira=4.0, tapa_espesor=3.0, margen_abertura=0.2, pared=2.5, soporte_tapa=2.5)
    assert abs(c2.profundidad - 37.0) < 1e-12 and abs(c2.z_ledge - 34.0) < 1e-12
    assert c2.abertura == (1.8, 1.8, 42.2, 32.2) and c2.cavidad == (-1.0, -1.0, 45.0, 35.0) and abs(c2.cobertura_banda - 1.55) < 1e-12
    try:
        cam_.geometria_de_la_camara(object())
        raise AssertionError("tenía que fallar con TypeError")
    except TypeError:
        pass


def test_parametros_absurdos_o_inimprimibles_de_la_camara_fallan_con_valueerror_claro():
    g = _geo()
    C = cam_.geometria_de_la_camara
    _falla(C, g, distancia_led=0, texto="distancia_led")
    _falla(C, g, distancia_led=-5, texto="distancia_led")
    _falla(C, g, grosor_tira=0, texto="grosor_tira")
    _falla(C, g, pared=1.1, texto="pared")
    assert C(g, pared=1.2)                                                                # justo en el mínimo
    _falla(C, g, tapa_espesor=1.1, texto="tapa")
    assert C(g, tapa_espesor=1.2)
    _falla(C, g, holgura_tapa=-0.1, texto="holgura_tapa")
    _falla(C, g, soporte_tapa=1.2, holgura_tapa=0.3, texto="apoya solo")                  # 0,9 de rebaje: menos del mínimo
    assert C(g, soporte_tapa=1.3, holgura_tapa=0.3)                                       # exactamente 1,0
    assert C(g, holgura_tapa=0.0)
    _falla(C, g, margen_abertura=-0.1, texto="margen_abertura")
    assert C(g, margen_abertura=0.0)
    _falla(C, g, lado_cable="atras", texto="lado_cable")
    _falla(C, g, cable_diam=0, texto="cable_diam")
    _falla(C, g, clavija_diam=0, texto="diámetro")
    _falla(C, g, clavija_largo=0, texto="largo")
    _falla(C, g, juego_clavija=0, texto="juego")
    _falla(C, g, espesor_brida=4.2, texto="brida")                                        # 3 + 0,5 + 0,8 = 4,3: con 4,2 no
    assert C(g, espesor_brida=4.3)
    _falla(C, g, margen_abertura=1.0, texto="cubre solo")                                 # banda 2 - 1 - 0,25 = 0,75 < 0,8
    assert C(g, margen_abertura=0.95)                                                     # 0,8 justo
    _falla(C, g, distancia_led=4.4, grosor_tira=12.0, texto="no entra la tira")          # distancia < espesor de la brida (4,5)
    assert C(g, distancia_led=4.5, grosor_tira=12.0)                                      # justo: la tira entra de punta a punta
    _falla(C, g, pared=2.0, soporte_tapa=5.6, texto="no entra en la cavidad")             # 7,6 de pared + soporte > los 7,5 de borde a la abertura
    assert C(g, pared=2.0, soporte_tapa=5.5)
    _falla(C, g, cable_diam=30.0, texto="agujero del cable")
    _falla(C, _geo(ancho_borde=5.0), texto="subí ancho_borde")                           # las clavijas no entran en la corona


def test_si_la_carcasa_queda_maciza_o_el_cable_no_encuentra_pared_falla_claro():
    g = _geo()
    c = cam_.geometria_de_la_camara(g)
    original, original_agujero = ch.armar_carcasa_hueca, ch.armar_agujero_pared
    try:
        ch.armar_carcasa_hueca = lambda *a, **k: (trimesh.creation.box(), False, [])
        _falla(cam_.malla_de_la_camara, c, texto="maciza")
        ch.armar_carcasa_hueca = original
        ch.armar_agujero_pared = lambda *a, **k: None
        _falla(cam_.malla_de_la_camara, c, texto="agujero del cable")
    finally:
        ch.armar_carcasa_hueca, ch.armar_agujero_pared = original, original_agujero
    assert cam_.malla_de_la_camara(c).is_watertight


# ---------------------------------------------------------------------------
#  la cámara: forma y volumen
# ---------------------------------------------------------------------------

def test_la_camara_tiene_la_huella_del_marco_las_paredes_y_el_volumen_de_la_formula():
    r, ens, _ = _armar()
    c, camara = r["camara_geometria"], ens["camara"]
    ex = r["geometria"].exterior
    assert np.abs(camara.bounds[:, :2] - np.array(ex).reshape(2, 2)).max() < 1e-4                # la misma huella que el marco
    W, H, P, E, p, s, zl = 56.0, 46.0, c.profundidad, c.espesor_brida, c.pared, c.soporte_tapa, c.z_ledge
    # paredes y cavidad medidas con rayos: a media profundidad, por donde no hay agujeros (la pared mide pared + soporte)
    ym = (ex[1] + ex[3]) / 2
    z = -(E + zl) / 2
    h = _golpes(camara, 0, ym + 5.13, z)
    assert len(h) == 4 and abs((h[1] - h[0]) - (p + s)) < TOL and abs((h[3] - h[2]) - (p + s)) < TOL, h
    hv = _golpes(camara, 1, z, (ex[0] + ex[2]) / 2 - 12.3)
    assert len(hv) == 4 and abs((hv[1] - hv[0]) - (p + s)) < TOL and abs((hv[3] - hv[2]) - (p + s)) < TOL, hv
    # el dorso está abierto: rayos verticales dentro de la cavidad no pegan en nada, y sobre la pared dan frente + escalón
    assert len(_vertical(camara, ym, 20.0)) == 0
    # volumen: formula cerrada (círculos de 64 lados de las esquinas redondeadas, 32 lados de los cilindros)
    gon = lambda rad, n: n / 2 * rad * rad * math.sin(2 * math.pi / n)
    a_ext = W * H - 4 * p * p + gon(p, 64)
    a_rebaje, a_cav = (W - 2 * p) * (H - 2 * p), (W - 2 * p - 2 * s) * (H - 2 * p - 2 * s)
    a_abertura = (c.abertura[2] - c.abertura[0]) * (c.abertura[3] - c.abertura[1])
    huecos = 4 * gon(c.clavija_diam / 2 + c.juego_clavija, 32) * (c.clavija_largo + 0.5)
    cable = gon(c.cable_diam / 2, 32) * (p + s)
    esperado = a_ext * P - a_cav * (zl - E) - a_rebaje * (P - zl) - a_abertura * E - huecos - cable
    assert abs(camara.volume - esperado) < 0.5, (camara.volume, esperado)


def test_el_cable_sale_por_el_lado_pedido_visto_de_frente_a_la_foto():
    for lado in cam_.LADOS_CABLE:
        r, ens, _ = _armar(lado_cable=lado)
        camara, c = ens["camara"], r["camara_geometria"]
        ex = r["geometria"].exterior
        xm, ym = (ex[0] + ex[2]) / 2, (ex[1] + ex[3]) / 2
        z = -c.profundidad / 2                                                                   # el agujero va a media profundidad
        # la pared con el agujero se atraviesa sin pegar en nada; la opuesta (y cualquier punto lejos del agujero) tiene pared
        if lado in ("abajo", "arriba"):
            h, lejos = _golpes(camara, 1, z, xm), _golpes(camara, 1, z, xm + 15.0)
            extremo = ex[1] if lado == "abajo" else ex[3]
            pared_opuesta = (h[0] > ym and abs(h[1] - ex[3]) < TOL) if lado == "abajo" else (h[1] < ym and abs(h[0] - ex[1]) < TOL)
        else:
            h, lejos = _golpes(camara, 0, ym, z), _golpes(camara, 0, ym + 15.0, z)
            extremo = ex[0] if lado == "izquierda" else ex[2]
            pared_opuesta = (h[0] > xm and abs(h[1] - ex[2]) < TOL) if lado == "izquierda" else (h[1] < xm and abs(h[0] - ex[0]) < TOL)
        assert len(h) == 2 and pared_opuesta, (lado, h)               # solo queda la pared del lado de enfrente
        assert len(lejos) == 4, (lado, lejos)                         # lejos del agujero hay las dos
        # el agujero mide su diámetro: en z, dentro de la pared del cable (frente | techo del agujero | piso | escalón)
        sentido = 1.0 if lado in ("abajo", "izquierda") else -1.0
        dentro = extremo + sentido * 1.0
        hz = _vertical(camara, xm, dentro) if lado in ("abajo", "arriba") else _vertical(camara, dentro, ym)
        assert len(hz) == 4, (lado, hz)
        assert abs((hz[2] - hz[1]) - 5.0) < 0.05 and abs((hz[1] + hz[2]) / 2 - z) < 1e-4, (lado, hz)       # Ø5 a media profundidad
        # y a lo ancho también mide 5 (rayo horizontal a media profundidad, cruzando el agujero de costado)
        ancho = _golpes(camara, 0, dentro, z + 0.0137) if lado in ("abajo", "arriba") else _golpes(camara, 1, z + 0.0137, dentro)
        hueco = [v for v in ancho if abs(v - (xm if lado in ("abajo", "arriba") else ym)) < 3.0]
        assert len(hueco) == 2 and abs((hueco[1] - hueco[0]) - 5.0) < 0.05, (lado, ancho)
    # un lado distinto cambia la cámara y el resto no (los mismos agujeros de las clavijas, la misma tapa)
    base, ens0, _ = _armar(lado_cable="abajo")
    r, ens1, _ = _armar(lado_cable="derecha")
    assert not np.array_equal(ens0["camara"].vertices, ens1["camara"].vertices) and abs(ens0["camara"].volume - ens1["camara"].volume) < 1.0
    assert np.array_equal(ens0["tapa"].vertices, ens1["tapa"].vertices) and np.array_equal(ens0["marco"].vertices, ens1["marco"].vertices)


# ---------------------------------------------------------------------------
#  (5) cuatro piezas watertight, impresión, A1, main, contrato
# ---------------------------------------------------------------------------

def test_las_cuatro_piezas_son_watertight_por_las_cuatro_vias():
    r, ens, stl = _armar()
    assert r["watertight"] is True and all(r["watertight_" + n] is True for n in PIEZAS)
    v = r["verificacion"]
    assert set(v) == set(PIEZAS)
    for nombre, euler in (("placa", 2), ("marco", 0)):
        assert v[nombre]["watertight"] and v[nombre]["euler"] == euler, nombre
    for nombre in PIEZAS:
        assert v[nombre]["watertight"] and v[nombre]["aristas_con_dos_caras"] and v[nombre]["caras_degeneradas"] == 0, nombre
        assert v[nombre]["caras_duplicadas"] == 0, nombre
        m = stl[nombre]
        assert m.is_watertight and m.is_winding_consistent and m.volume > 0, nombre
        assert lf.verificar_malla(ens[nombre])["watertight"], nombre
    # la tapa es un prisma (euler 2); la cámara tiene agujeros que la atraviesan (la abertura: euler 0) y los ciegos no cuentan
    assert v["tapa"]["euler"] == 2 and v["camara"]["euler"] in (0, -2, 2) and lf.verificar_malla(ens["camara"])["euler"] == v["camara"]["euler"]
    with _carpeta() as d:
        rs = gen.generar(_imagen(d), ancho_mm=30.0, px_por_mm=2.0, distancia_led=25.0, carpeta_salida=d, verificar=False)
    assert rs["verificacion"] is None and rs["watertight"] is True and rs["watertight_camara"] is True and rs["watertight_tapa"] is True


def test_los_stl_de_impresion_son_el_ensamble_girado_y_estan_en_el_origen():
    r, ens, stl = _armar()
    geo, c = r["geometria"], r["camara_geometria"]
    ex = geo.exterior
    for nombre in ("camara", "tapa", "marco", "placa"):
        assert np.abs(stl[nombre].bounds[0]).max() < 1e-4, nombre                                # todas en el origen
    cm, tp = stl["camara"], stl["tapa"]
    assert np.abs(cm.bounds[1] - [56.0, 46.0, c.profundidad]).max() < 1e-4
    assert np.abs(tp.bounds[1] - [51.4, 41.4, 2.0]).max() < 1e-4                                  # 56 - 2·(2 + 0,3) x 46 - 2·(2 + 0,3)
    # la cámara se imprime con la brida contra la cama y el dorso abierto hacia arriba
    h = _vertical(cm, 1.0, 20.13)                                                                # pared exterior: maciza de punta a punta
    assert len(h) == 2 and abs(h[0]) < TOL and abs(h[1] - c.profundidad) < TOL, h
    h = _vertical(cm, 3.0, 20.13)                                                                # sobre el escalón: de la brida hasta el escalón
    assert len(h) == 2 and abs(h[0]) < TOL and abs(h[1] - c.z_ledge) < TOL, h
    h = _vertical(cm, (1.5 - ex[0]) - 0.5, 20.13)                                                # la brida junto a la abertura
    assert len(h) == 2 and abs(h[0]) < TOL and abs(h[1] - c.espesor_brida) < TOL, h
    assert len(_vertical(cm, (ex[2] - ex[0]) / 2, 20.13)) == 0                                   # la abertura: pasante
    # y son el ensamble: el mismo volumen, y deshaciendo el giro caen sobre la malla del ensamble
    for nombre, deshacer in (("camara", lambda v: np.column_stack([v[:, 0] + ex[0], ex[3] - v[:, 1], -v[:, 2]])),
                             ("tapa", lambda v: np.column_stack([v[:, 0] + ex[0] + 2.3, ex[3] - 2.3 - v[:, 1], -v[:, 2] - c.z_ledge]))):
        v = deshacer(np.array(stl[nombre].vertices))
        assert abs(stl[nombre].volume - ens[nombre].volume) < 1e-4 * ens[nombre].volume, nombre
        assert np.abs(v.min(axis=0) - ens[nombre].bounds[0]).max() < 1e-4 and np.abs(v.max(axis=0) - ens[nombre].bounds[1]).max() < 1e-4, nombre
    assert abs(stl["marco"].bounds[1][2] - (4.0 + 3.0)) < 1e-4                                   # el marco: ceja contra la cama y las clavijas hacia arriba


def test_a1_se_chequea_por_pieza_y_el_marco_manda():
    r, *_ = _armar()
    assert r["entra_a1"] is True and all(r[f"entra_{n}_a1"] is True for n in PIEZAS)
    for frase in ("marco: 56 x 46 x 7 mm", "cámara: 56 x 46 x 30 mm", "placa: 44 x 34 x 3 mm", "tapa: 51 x 41 x 2 mm"):
        assert frase in r["mensaje_a1"], (frase, r["mensaje_a1"])
    assert not r["avisos"], r["avisos"]
    assert (r["ancho_mm"], r["alto_mm"]) == (56.0, 46.0) and abs(r["profundidad_mm"] - 30.0) < 1e-4       # huella del MARCO; la más alta, la cámara
    assert abs(r["marco"]["profundidad_mm"] - 7.0) < 1e-4 and abs(r["camara"]["profundidad_mm"] - 30.0) < 1e-4
    with _carpeta() as d:
        ruta = _imagen(d)
        # imagen de 228 mm: el marco y la cámara miden 244 (pasan de los 240 recomendados) y la placa (232) y la tapa entran
        r = gen.generar(ruta, ancho_mm=228.0, px_por_mm=1.0, distancia_led=25.0, carpeta_salida=d, verificar=False)
        assert r["entra_marco_a1"] is False and r["entra_camara_a1"] is False and r["entra_placa_a1"] is True and r["entra_tapa_a1"] is True
        assert r["entra_a1"] is False and abs(r["ancho_mm"] - 244.0) < 1e-6
        assert any("marco" in a and "Achicá" in a for a in r["avisos"]) and any("cámara" in a and "Achicá" in a for a in r["avisos"]), r["avisos"]
        assert sum("todavía no se parte" in a for a in r["avisos"]) == 2, r["avisos"]
        assert "marco: 244" in r["mensaje_a1"] and "cámara: 244" in r["mensaje_a1"] and "entra justo" in r["mensaje_a1"]
        # el marco de L8 también avisaría por la placa y el marco: no se duplican
        assert len([a for a in r["avisos"] if a.startswith("marco:")]) == 1 and len([a for a in r["avisos"] if a.startswith("placa:")]) == 0
        # una cámara muy profunda no entra aunque el marco sí: gana la pieza que no entra
        r = gen.generar(ruta, ancho_mm=40.0, px_por_mm=2.0, distancia_led=300.0, carpeta_salida=d, verificar=False)
        assert r["entra_camara_a1"] is False and r["entra_marco_a1"] is True and r["entra_placa_a1"] and r["entra_a1"] is False
        assert abs(r["profundidad_mm"] - 305.0) < 1e-4 and "cámara: 56 x 46 x 305 mm NO entra" in r["mensaje_a1"]
        assert any(a.startswith("cámara:") and "NO entra" in a for a in r["avisos"])
        # una imagen alta: el lado MAYOR es el que cuenta
        r = gen.generar(ruta, ancho_mm=50.0, alto_mm=230.0, px_por_mm=1.0, distancia_led=25.0, ancho_borde=9.5, carpeta_salida=d, verificar=False)
        assert r["alto_mm"] == 249.0 and r["entra_marco_a1"] is False and r["entra_placa_a1"] is True


def test_el_resultado_cumple_el_contrato_del_proyecto():
    r, ens, stl = _armar()
    for clave in ("ruta_stl", "ruta_stl_placa", "ruta_stl_marco", "ruta_stl_camara", "ruta_stl_tapa", "ancho_mm", "alto_mm", "profundidad_mm",
                  "vertices", "caras", "watertight", "info", "avisos", "entra_a1", "mensaje_a1", "placa", "marco", "camara", "tapa",
                  "geometria", "camara_geometria", "luz", "separacion_maxima_filas", "distancia_minima_led", "banda_x", "banda_y",
                  "stl_mb", "verificacion", "tiempos", "guia", "mapa_brillo", "mapa_grosor"):
        assert clave in r, clave
    assert isinstance(r["watertight"], bool) and isinstance(r["entra_a1"], bool) and "entran_juntas" not in r
    assert all(isinstance(x, str) for x in r["info"] + r["avisos"]) and isinstance(r["mensaje_a1"], str)
    assert r["vertices"] == sum(len(stl[n].vertices) for n in PIEZAS) and r["caras"] == sum(len(stl[n].faces) for n in PIEZAS)
    for n in PIEZAS:
        assert r[n]["caras"] == len(stl[n].faces) and r[n]["vertices"] == len(stl[n].vertices) and r[n]["stl_mb"] > 0, n
        assert os.path.basename(r["ruta_stl_" + n]).endswith(f"_{n}.stl")
    assert r["ruta_stl"] == r["ruta_stl_placa"] and len({r["ruta_stl_" + n] for n in PIEZAS}) == 4
    assert abs(r["stl_mb"] - sum(r[n]["stl_mb"] for n in PIEZAS)) < 1e-12
    assert r["tiempos"] and all(v >= 0 for v in r["tiempos"].values()) and "camara" in r["tiempos"]
    assert r["guia"] == r["info"][-len(r["guia"]):] and len(r["info"]) == 5 + 3 + len(r["guia"])
    texto = "\n".join(r["info"])
    for frase in ("MARCO de 56.0 x 46.0 x 4.0 mm", "PLACA de", "CÁMARA de 56.0 x 46.0 x 30.0 mm", "TAPA de 51.4 x 41.4 x 2.0 mm",
                  "4 clavijas de Ø2.5 x 3 mm", "0.15 mm de juego", "abertura de 41.0 x 31.0 mm", "cubre 1.28 mm de la banda",
                  "Luz: tira a 25 mm", "9 LED", "ignora las reflexiones"):
        assert frase in texto, frase
    u = r["luz"]
    esperado = luz.uniformidad_de_luz(25.0, 16.7, 16.7, 48.0, 38.0, 40.0, 30.0)
    assert (u.rizado_local, u.borde_centro, u.n_leds) == (esperado.rizado_local, esperado.borde_centro, esperado.n_leds)
    assert abs(r["separacion_maxima_filas"] - luz.separacion_maxima_de_filas(25.0, 16.7, ancho_camara=48.0, alto_camara=38.0)) < 1e-9
    assert abs(r["distancia_minima_led"] - luz.distancia_minima(16.7, 16.7, ancho_camara=48.0, alto_camara=38.0)) < 1e-9
    with _carpeta() as d:
        ruta = _imagen(d)
        r1 = gen.generar(ruta, ancho_mm=30.0, px_por_mm=2.0, distancia_led=25.0, carpeta_salida=d, prefijo="mi lito")
        assert sorted(os.listdir(d)) == ["foto.png", "mi_lito_camara.stl", "mi_lito_marco.stl", "mi_lito_placa.stl", "mi_lito_tapa.stl"]
        r2 = gen.generar(ruta, ancho_mm=30.0, px_por_mm=2.0, distancia_led=25.0, carpeta_salida=d, prefijo="mi lito")
        for n in PIEZAS:
            assert open(r1["ruta_stl_" + n], "rb").read() == open(r2["ruta_stl_" + n], "rb").read(), n          # determinista
        gen.generar(ruta, ancho_mm=30.0, px_por_mm=2.0, distancia_led=25.0, carpeta_salida=d)
        assert all(os.path.isfile(os.path.join(d, f"foto_{n}.stl")) for n in PIEZAS)
        rs = gen.generar(ruta, ancho_mm=30.0, px_por_mm=2.0, distancia_led=25.0, carpeta_salida=d, verificar=False)
        assert rs["verificacion"] is None and rs["watertight"] is True


def test_la_guia_dice_los_limites_que_no_se_pueden_verificar():
    r, *_ = _armar()
    texto = "\n".join(r["guia"])
    for frase in ("sin soportes", "OPACO", "dejan pasar luz", "±0,1 mm", "no se puede verificar desde acá", "cinta", "reflexiones", "difusión",
                  "no es una garantía".replace("no es una", "es una guía, no una"), "Bambu Studio", "clavijas del marco", "por DENTRO de la tapa",
                  "filas de tira separadas", "El cable sale por el lado abajo", "suelta", "ceja"):
        assert frase in texto, frase
    assert f"{r['separacion_maxima_filas']:.0f} mm como máximo" in texto and f"{r['distancia_minima_led']:.0f} mm." in texto
    assert "cubre 1.28 mm de su banda" in texto and "cavidad de 48 x 38 mm" in texto and "a 25 mm de la placa" in texto
    # los avisos de la carcasa de las letras (laminador que tapa lo abierto) están en la guía tal cual los da carcasa_hueca
    _, _, avisos = ch.armar_carcasa_hueca(cam_._poly_de_la_carcasa(r["camara_geometria"]), 30.0, 2.0, 2.0)
    assert avisos and all(a in r["guia"] for a in avisos)


def test_los_parametros_de_la_camara_llegan_a_las_piezas_y_a_la_luz():
    base, ens0, _ = _armar()
    # distancia: la profundidad sale de distancia + tira + tapa; y la luz usa esa distancia
    r, ens, _ = _armar(distancia_led=35.0, grosor_tira=4.0, tapa_espesor=2.5)
    assert abs(r["camara_geometria"].profundidad - 41.5) < 1e-9 and np.abs(ens["camara"].bounds[:, 2] - [-41.5, 0]).max() < TOL
    assert r["luz"].distancia == 35.0 and abs(r["profundidad_mm"] - 41.5) < 1e-4
    assert np.abs(ens["tapa"].bounds[:, 2] - [-41.5, -39.0]).max() < TOL
    # el espesor de la brida, el margen de la abertura, la pared
    r, ens, _ = _armar(espesor_brida=6.0, margen_abertura=0.3, pared_camara=2.5)
    h = _vertical(ens["camara"], 1.0, 20.13)
    assert len(h) == 2 and abs(h[0] + 6.0) < TOL
    assert r["camara_geometria"].abertura[0] == r["geometria"].ventana[0] - 0.3 and abs(r["camara_geometria"].cobertura_banda - (2.03 - 0.3 - 0.25)) < 0.02
    # las clavijas y el juego
    r, ens, stl = _armar(clavija_diam=3.0, clavija_largo=2.0, juego_clavija=0.3)
    assert abs(stl["marco"].bounds[1][2] - (4.0 + 2.0)) < 1e-4 and r["camara_geometria"].clavija_diam == 3.0 and "Ø3 x 2 mm" in "\n".join(r["info"])
    # paso del LED y separación de filas: solo afectan a la luz
    r, ens, _ = _armar(paso_led=8.3, separacion_filas=25.0)
    assert r["luz"].paso_led == 8.3 and r["luz"].separacion_filas == 25.0 and r["luz"].n_leds != base["luz"].n_leds
    assert np.array_equal(ens["camara"].vertices, ens0["camara"].vertices)
    # los de L8 llegan a la placa y al marco
    r, ens, stl = _armar(ancho_borde=10.0, holgura=0.4, margen_encastre=2.5, grosor_ceja=1.5)
    assert abs(stl["marco"].bounds[1][0] - 60.0) < 1e-4 and r["geometria"].holgura == 0.4 and abs(r["camara_geometria"].abertura[2] - r["camara_geometria"].abertura[0] - 41.0) < 1e-9
    assert np.abs(ens["camara"].bounds[:, :2] - np.array(r["geometria"].exterior).reshape(2, 2)).max() < 1e-4
    # cara plana: la placa va dada vuelta y el resto no cambia
    r, ens, stl = _armar(cara_visible="plana")
    assert abs(_vertical(ens["placa"], 20.0, 20.0)[0]) < 5 and np.array_equal(ens["camara"].vertices, ens0["camara"].vertices)
    # los avisos de luz salen en `avisos`
    r, *_ = _armar(distancia_led=10.0)
    assert any("se van a ver los puntos" in a for a in r["avisos"]) and r["luz"].rizado_local > 0.05
    aviso = [x for x in r["avisos"] if "se van a ver los puntos" in x][0]
    assert f"{luz.distancia_minima(16.7, 16.7, 0.05, 48.0, 38.0):.0f} mm o más" in aviso                       # con la cavidad real (48 x 38), no la de 100 x 100
    assert f"{luz.distancia_minima(16.7, 16.7, 0.05, 100.0, 100.0):.0f} mm o más" not in aviso
    assert r["separacion_maxima_filas"] is None and "no alcanza con juntar las filas" in " ".join(r["guia"])   # a 10 mm no hay separación que sirva
    r, *_ = _armar(distancia_led=25.0)
    assert not any("puntos" in a for a in r["avisos"])


def test_los_errores_no_escriben_nada():
    with _carpeta() as d:
        ruta = _imagen(d)
        base = dict(ancho_mm=40.0, px_por_mm=2.0, carpeta_salida=d)
        for kw, texto in ((dict(lado_cable="atras"), "lado_cable"), (dict(clavija_diam=5.0), "corona"), (dict(margen_abertura=1.2), "cubre solo"),
                          (dict(distancia_led=2.0), "no entra la tira"), (dict(paso_led=0.0), "paso_led"), (dict(separacion_filas=-1.0), "separacion_filas"),
                          (dict(cable_diam=40.0), "agujero del cable"), (dict(ancho_borde=2.0), "pared"), (dict(pared_camara=0.5), "pared"),
                          (dict(grosor_ceja=0.3), "ceja"), (dict(tapa_espesor=0.5), "tapa"), (dict(cara_visible="nada"), "cara_visible")):
            _falla(gen.generar, ruta, texto=texto, **dict(base, **kw))
            assert os.listdir(d) == ["foto.png"], (kw, os.listdir(d))
        try:
            gen.generar(os.path.join(d, "nada.png"), **base)
            raise AssertionError("tenía que fallar con FileNotFoundError")
        except FileNotFoundError:
            pass
        assert os.listdir(d) == ["foto.png"]


def test_main_lista_la_camara_y_cumple_el_contrato():
    import main
    with contextlib.redirect_stdout(io.StringIO()):
        generadores = main._descubrir_generadores()
    nombres = [g.NOMBRE for g in generadores]
    assert gen.NOMBRE in nombres and gen_l8.NOMBRE in nombres and "Litofanía" in nombres, nombres
    g = generadores[nombres.index(gen.NOMBRE)]
    assert g is gen and isinstance(g.DESCRIPCION, str) and len(g.DESCRIPCION) > 10 and callable(g.ejecutar)
    assert len(set(nombres)) == len(nombres) and gen.NOMBRE == "Litofanía: cámara de luz"


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


def test_ejecutar_genera_los_cuatro_stl_con_input_simulado_y_no_se_cae_con_entradas_malas():
    with _carpeta() as d:
        ruta = _imagen(d)
        # ruta, ancho, px/mm, grosor claro, grosor oscuro, luz %, invertir, cara, capa, borde, holgura, distancia, paso LED, lado
        out = _ejecutar([ruta, "40", "2", "0.8", "2.8", "5", "n", "relieve", "0", "10", "0.3", "30", "20", "izquierda"], d)
        for n in PIEZAS:
            assert os.path.isfile(os.path.join(d, f"foto_{n}.stl")), n
        assert "ERROR" not in out and out.count("watertight=True") == 4 and "LED a 30 mm" in out and "cable por izquierda" in out, out
        assert "filas cada 20 mm" in out and "LED cada 20 mm" in out and "0.3 mm de holgura" in out, out
        cm = trimesh.load(os.path.join(d, "foto_camara.stl"))
        assert abs(cm.bounds[1][2] - 35.0) < 1e-4 and abs(cm.bounds[1][0] - 60.0) < 1e-4                  # 30 + 3 + 2; 40 + 2·10
        antes = open(os.path.join(d, "foto_camara.stl"), "rb").read()
        _ejecutar([ruta, "40", "2", "", "", "", "n", "relieve", "", "10", "0.3", "30", "16.7", "derecha"], d)
        assert open(os.path.join(d, "foto_camara.stl"), "rb").read() != antes                              # el lado llega
        out = _ejecutar([ruta, "40", "2", "", "", "", "n", "relieve", "", "", "", "10", "16.7", ""], d)    # con 10 mm se ven los puntos
        assert "se van a ver los puntos" in out
        # entradas malas
        out = _ejecutar([os.path.join(d, "nada.png")], d)
        assert "ERROR" in out and "no encuentro" in out
        out = _ejecutar([ruta, "40", "2", "", "", "", "n", "relieve", "", "2", "", "", "", ""], d)         # borde que no alcanza
        assert "ERROR" in out and "pared" in out
        out = _ejecutar([ruta, "40", "2", "", "", "", "n", "relieve", "", "", "", "3", "", ""], d)         # tira que no entra
        assert "ERROR" in out and "no entra la tira" in out


# ---------------------------------------------------------------------------
#  L1-L5, L7 y L8 no se tocaron
# ---------------------------------------------------------------------------

def test_l1_a_l5_l7_y_l8_no_dependen_de_la_camara():
    for ruta in ("core/litofania.py", "core/litofania_simulacion.py", "core/litofania_calibracion.py", "generators/litofania.py",
                 "generators/calibracion_litofania.py", "core/litofania_marco.py", "generators/marco_litofania.py"):
        txt = open(ruta, encoding="utf-8").read()
        assert "camara_litofania" not in txt and "litofania_camara" not in txt and "litofania_luz" not in txt, ruta
    for ruta in sorted(os.listdir("pages")):
        if "Litofania" in ruta:
            t = open(os.path.join("pages", ruta), encoding="utf-8").read().lower()
            assert "camara_litofania" not in t and "litofania_camara" not in t
    # la única diferencia de L8 con las clavijas apagadas es el parámetro opcional (se ve en la firma)
    import inspect
    assert inspect.signature(marco.malla_del_marco).parameters["clavijas"].default is None
    assert inspect.signature(gen_l8.generar).parameters["clavijas"].default is None


# ---------------------------------------------------------------------------
#  segunda tanda (sobrevivientes del mutation testing)
# ---------------------------------------------------------------------------

def test_la_luz_contra_fuerza_bruta_con_un_arreglo_no_cuadrado_y_casos_de_borde():
    # cámara de 40 x 50 (4 x 3 LED, paso 12 y filas cada 20), foto de 30 x 44: todo con bucles de Python escritos acá
    d, p, s, cw, ch_, iw, ih, R = 15.0, 12.0, 20.0, 40.0, 50.0, 30.0, 44.0, 41
    nx, ny = int(cw // p) + 1, int(ch_ // s) + 1
    xs = [(i - (nx - 1) / 2) * p for i in range(nx)]
    ys = [(j - (ny - 1) / 2) * s for j in range(ny)]
    E = lambda x, y: sum(d * d / (d * d + (x - a) ** 2 + (y - b) ** 2) ** 2 for a in xs for b in ys)
    celda = [E(-p / 2 + p * i / (R - 1), -s / 2 + s * j / (R - 1)) for i in range(R) for j in range(R)]
    foto = [E(-iw / 2 + iw * i / (R - 1), -ih / 2 + ih * j / (R - 1)) for i in range(R) for j in range(R)]
    u = luz.uniformidad_de_luz(d, p, s, cw, ch_, iw, ih, resolucion=R)
    assert (nx, ny) == (4, 3) and u.n_leds == 12
    assert abs(u.rizado_local - (max(celda) - min(celda)) / (max(celda) + min(celda))) < 1e-12
    assert abs(u.borde_centro - min(foto) / max(foto)) < 1e-12
    # distinta de la misma cuenta con la foto o la cámara dadas vuelta (no es simétrica)
    for otro in (luz.uniformidad_de_luz(d, p, s, cw, ch_, ih, iw, resolucion=R), luz.uniformidad_de_luz(d, p, s, ch_, cw, iw, ih, resolucion=R),
                 luz.uniformidad_de_luz(d, s, p, cw, ch_, iw, ih, resolucion=R)):
        assert abs(otro.rizado_local - u.rizado_local) > 1e-4 or abs(otro.borde_centro - u.borde_centro) > 1e-4
    # la resolución por defecto es la de la constante, y con 3 puntos todavía anda
    assert luz.RESOLUCION_DEFAULT == 101
    a, b = luz.uniformidad_de_luz(20.0, 16.7, 16.7, 108.0, 108.0, 100.0, 100.0), luz.uniformidad_de_luz(20.0, 16.7, 16.7, 108.0, 108.0, 100.0, 100.0, resolucion=101)
    assert (a.rizado_local, a.borde_centro) == (b.rizado_local, b.borde_centro)
    assert luz.uniformidad_de_luz(20.0, 16.7, 16.7, 108.0, 108.0, 100.0, 100.0, resolucion=3).n_leds == 49
    # un valor escalar da un escalar (0-d), no un arreglo de uno
    assert luz.iluminancia(1.0, 2.0, np.array([[0.0, 0.0]]), 5.0).shape == ()
    # los mensajes de error dicen qué parámetro es
    _falla(luz.uniformidad_de_luz, 10.0, paso_led=0.0, texto="paso_led tiene que ser mayor que 0")
    _falla(luz.uniformidad_de_luz, 10.0, separacion_filas=0.0, texto="separacion_filas tiene que ser mayor que 0")
    _falla(luz.uniformidad_de_luz, 0.0, texto="la distancia a la placa tiene que ser mayor que 0")


def test_distancia_minima_y_separacion_maxima_con_camaras_no_cuadradas_y_casos_extremos():
    for p, s in ((16.7, 16.7), (8.3, 25.0), (16.7, 8.3)):
        dm = luz.distancia_minima(p, s, 0.05, 108.0, 60.0)
        f = lambda x: luz.uniformidad_de_luz(x, p, s, 108.0, 60.0, 10.0, 10.0).rizado_local
        assert abs(f(dm) - 0.05) < 1e-4 and f(dm) <= 0.05                                       # justo del lado bueno
    assert abs(luz.distancia_minima(8.3, 25.0, 0.05, 108.0, 60.0) - luz.distancia_minima(25.0, 8.3, 0.05, 108.0, 60.0)) > 0.5   # el orden importa
    d = luz.distancia_minima(5.0, 400.0, 0.05, 100.0, 100.0)                                  # la raíz queda más allá de 20 veces el LED, no de la fila
    assert abs(d - 882.44) < 0.05
    _falla(luz.distancia_minima, 16.7, 16.7, 1e-12, 100.0, 100.0, texto="ni a una distancia enorme")
    sm = luz.separacion_maxima_de_filas(20.0, 16.7, 0.5, 108.0, 108.0)
    assert sm > 40.0 and abs(luz.uniformidad_de_luz(20.0, 16.7, sm, 108.0, 108.0, 10.0, 10.0).rizado_local - 0.5) < 1e-4    # pasa de 2 veces la distancia
    assert luz.separacion_maxima_de_filas(20.0, 16.7, 0.9995, 108.0, 108.0) == 400.0         # tan permisivo que vale el tope (20 veces la distancia)
    assert 100.0 < luz.separacion_maxima_de_filas(20.0, 16.7, 0.99, 108.0, 108.0) < 400.0
    assert luz.uniformidad_de_luz(20.0, 16.7, luz.separacion_maxima_de_filas(20.0, 16.7, 0.05, 108.0, 60.0), 108.0, 60.0, 10.0, 10.0).rizado_local <= 0.05 + 1e-4


def test_los_avisos_de_luz_dicen_los_numeros_justos():
    U = luz.UniformidadLuz
    a = luz.avisos_de_luz(U(10.0, 8.3, 25.0, 12, 0.0501, 0.9), ancho_camara=108.0, alto_camara=60.0)
    esperado = luz.distancia_minima(8.3, 25.0, 0.05, 108.0, 60.0)
    assert len(a) == 1 and f"{esperado:.0f} mm o más" in a[0]
    assert f"{luz.distancia_minima(25.0, 8.3, 0.05, 108.0, 60.0):.0f} mm o más" not in a[0]          # con el paso y las filas en su lugar
    assert f"{luz.distancia_minima(8.3, 25.0, 0.05, 20.0, 20.0):.0f} mm o más" not in a[0]           # y con la cámara que es
    assert "A 10 mm de la placa" in a[0] and "rizado de 5.0 %" in a[0] and "más que el 5 % tolerado" in a[0]
    b = luz.avisos_de_luz(U(60.0, 16.7, 16.7, 49, 0.001, 0.4999))
    assert "recibir solo el 50 % de la luz del centro" in b[0] and "(se tolera 50 %)" in b[0]
    c = luz.avisos_de_luz(U(60.0, 16.7, 16.7, 49, 0.001, 0.31), borde_centro_min=0.4)
    assert "recibir solo el 31 % de la luz" in c[0] and "(se tolera 40 %)" in c[0]


def test_las_clavijas_en_el_limite_de_la_corona_y_el_volumen_del_marco_con_clavijas():
    g = _geo()
    assert cam_.clavijas_del_marco(g, 2.5, 3.0, 0.625)                                           # 2,5 + 1,25 + 2 = 5,75: justo lo que mide la corona
    _falla(cam_.clavijas_del_marco, g, 2.5, 3.0, 0.63, texto="corona")
    r, ens, _ = _armar()
    geo = r["geometria"]
    area = lambda rect: (rect[2] - rect[0]) * (rect[3] - rect[1])
    sin = (area(geo.exterior) * geo.profundidad_total - area(geo.ventana) * geo.profundidad_total
           - (area(geo.bolsillo) - area(geo.ventana)) * geo.profundidad_bolsillo)
    pines = 4 * _poligono(1.25) * 3.0                                                            # el tramo que sale por detrás (el resto queda adentro del marco)
    assert abs(ens["marco"].volume - (sin + pines)) < 1e-6 * sin


def test_la_geometria_valida_los_bordes_de_cada_chequeo():
    g = _geo()
    C = cam_.geometria_de_la_camara
    _falla(C, g, distancia_led=0, texto="distancia_led tiene que ser mayor que 0")
    _falla(C, g, grosor_tira=0, texto="grosor_tira tiene que ser mayor que 0")
    # banda distinta en x y en y: manda la más fina
    g2 = marco.geometria_del_marco(40.0, 30.0, 3.0, 2.0, 2.8, ancho_borde=9.0)
    assert abs(C(g2).cobertura_banda - (2.0 - 0.5 - 0.25)) < 1e-12
    _falla(C, g2, margen_abertura=1.0, texto="cubre solo")
    # sin cavidad: una pared y un soporte que se comen el interior, en un eje o en los dos
    _falla(C, _geo(ancho=40.0, alto=1.0), soporte_tapa=6.5, texto="no tiene cavidad")
    _falla(C, _geo(ancho=1.0, alto=30.0), soporte_tapa=6.5, texto="no tiene cavidad")
    _falla(C, _geo(ancho=1.0, alto=1.0), soporte_tapa=6.5, texto="no tiene cavidad")
    assert C(_geo(ancho=1.0, alto=1.0), soporte_tapa=5.5)
    # el agujero del cable, justo contra la brida (a media profundidad) y justo contra la tapa
    assert C(g, cable_diam=16.0)                                                                  # 12,5 - 8 = 4,5 = la brida
    _falla(C, g, cable_diam=16.2, texto="agujero del cable")
    assert C(g, tapa_espesor=6.0, cable_diam=17.0)                                                # 14,5 + 8,5 = 23 = donde arranca la tapa
    _falla(C, g, tapa_espesor=6.0, cable_diam=18.0, texto="agujero del cable")


def test_el_generador_pasa_cada_parametro_y_arma_los_textos_con_los_datos_correctos():
    r, ens, stl = _armar(paso_led=8.3, separacion_filas=25.0, margen_encastre=2.5, holgura_tapa=0.5, soporte_tapa=2.5, cable_diam=6.0)
    c, geo = r["camara_geometria"], r["geometria"]
    # la banda pedida llega a la placa y la cámara (cavidad = pared + soporte desde el borde: 47 x 37)
    assert abs(r["banda_x"] - 2.5) < 0.3 and c.soporte_tapa == 2.5 and c.holgura_tapa == 0.5 and c.cable_diam == 6.0
    assert c.interior == (47.0, 37.0)
    ex = geo.exterior
    h = _golpes(ens["camara"], 0, (ex[1] + ex[3]) / 2 + 5.13, -(c.espesor_brida + c.z_ledge) / 2)
    assert abs((h[1] - h[0]) - 4.5) < TOL                                                          # pared (2) + soporte (2,5)
    assert np.abs(stl["tapa"].bounds[1] - [56.0 - 2 * 2.5, 46.0 - 2 * 2.5, 2.0]).max() < 1e-4       # tapa: 2 de pared + 0,5 de holgura por lado
    # la luz, con la cámara y la foto en su lugar (arreglo no simétrico)
    esperado = luz.uniformidad_de_luz(25.0, 8.3, 25.0, 47.0, 37.0, 40.0, 30.0)
    u = r["luz"]
    assert (u.rizado_local, u.borde_centro, u.n_leds, u.paso_led, u.separacion_filas) == (esperado.rizado_local, esperado.borde_centro, esperado.n_leds, 8.3, 25.0)
    assert r["separacion_maxima_filas"] == luz.separacion_maxima_de_filas(25.0, 8.3, ancho_camara=47.0, alto_camara=37.0)
    assert r["distancia_minima_led"] == luz.distancia_minima(8.3, 25.0, ancho_camara=47.0, alto_camara=37.0)
    assert r["separacion_maxima_filas"] != luz.separacion_maxima_de_filas(25.0, 25.0, ancho_camara=47.0, alto_camara=37.0)
    texto = "\n".join(r["info"])
    assert f"rizado entre LED de {u.rizado_local * 100:.1f} %" in texto and f"bordes con el {u.borde_centro * 100:.0f} % de la luz del centro" in texto
    assert f"{u.n_leds} LED en la cavidad de 47 x 37 mm" in texto and "LED cada 8.3 mm, filas cada 25 mm" in texto
    assert f"filas de tira separadas {r['separacion_maxima_filas']:.0f} mm como máximo (con un LED cada 8.3 mm)" in texto
    assert f"no acerques la tira a menos de {r['distancia_minima_led']:.0f} mm." in texto
    assert "agujero de Ø6 mm" in texto and "cubre 1.75 mm de su banda" in texto or "cubre" in texto
    assert abs(r["marco"]["ancho_mm"] - 56.0) < 1e-4 and abs(r["marco"]["alto_mm"] - 46.0) < 1e-4 and abs(r["marco"]["profundidad_mm"] - 7.0) < 1e-4
    r0, *_ = _armar()
    t0 = "\n".join(r0["guia"])
    assert "las 4 clavijas del marco" in t0 and "agujero de Ø5 mm" in t0 and "(con un LED cada 16.7 mm)" in t0
    with _carpeta() as d:
        rs = gen.generar(_imagen(d), ancho_mm=30.0, px_por_mm=2.0, distancia_led=25.0, carpeta_salida=d, verificar=False)
        assert "verificacion" not in rs["tiempos"]
        rv = gen.generar(_imagen(d), ancho_mm=30.0, px_por_mm=2.0, distancia_led=25.0, carpeta_salida=d, verificar=True)
        assert rv["tiempos"]["verificacion"] > 0
    # el orden de los avisos de A1: el marco primero, después la cámara, la placa y la tapa
    with _carpeta() as d:
        r = gen.generar(_imagen(d), ancho_mm=300.0, px_por_mm=1.0, distancia_led=25.0, ancho_borde=12.0, carpeta_salida=d, verificar=False)
        pre = [a.split(":")[0] for a in r["avisos"] if "NO entra" in a]
        assert pre[:2] == ["marco", "cámara"] or pre[:3] == ["marco", "cámara", "placa"], pre
        assert r["avisos"][0].startswith("marco:") and r["avisos"][1].startswith("cámara:"), r["avisos"][:3]


def _sin_una_cara(malla):
    m = malla.copy()
    m.update_faces(np.arange(len(m.faces)) != 0)
    return m


def test_el_watertight_del_resultado_sale_de_cada_malla_y_el_conjunto_es_el_y_de_las_cuatro():
    original_c, original_t = cam_.camara_para_imprimir, cam_.tapa_para_imprimir
    try:
        for verificar in (True, False):
            with _carpeta() as d:
                ruta = _imagen(d)
                cam_.camara_para_imprimir = lambda m, g: _sin_una_cara(original_c(m, g))
                r = gen.generar(ruta, ancho_mm=30.0, px_por_mm=2.0, distancia_led=25.0, carpeta_salida=d, verificar=verificar)
                assert r["watertight_camara"] is False and r["watertight_tapa"] is True and r["watertight_placa"] and r["watertight_marco"]
                assert r["watertight"] is False
                cam_.camara_para_imprimir = original_c
                cam_.tapa_para_imprimir = lambda m, c: _sin_una_cara(original_t(m, c))
                r = gen.generar(ruta, ancho_mm=30.0, px_por_mm=2.0, distancia_led=25.0, carpeta_salida=d, verificar=verificar)
                assert r["watertight_tapa"] is False and r["watertight_camara"] is True and r["watertight"] is False
                cam_.tapa_para_imprimir = original_t
                r = gen.generar(ruta, ancho_mm=30.0, px_por_mm=2.0, distancia_led=25.0, carpeta_salida=d, verificar=verificar)
                assert r["watertight"] is True
    finally:
        cam_.camara_para_imprimir, cam_.tapa_para_imprimir = original_c, original_t


def test_carcasa_hueca_con_hueco_unido_no_deja_la_membrana_y_sin_el_es_la_de_siempre():
    import shapely.geometry as sg
    poly = sg.box(0.0, 0.0, 40.0, 30.0)
    m0, ok0, av0 = ch.armar_carcasa_hueca(poly, 20.0, 2.0, 2.0)                                     # por defecto: como siempre
    m1, _, _ = ch.armar_carcasa_hueca(poly, 20.0, 2.0, 2.0, hueco_unido=False)
    m2, ok2, av2 = ch.armar_carcasa_hueca(poly, 20.0, 2.0, 2.0, hueco_unido=True)
    assert ok0 and ok2 and av0 == av2
    assert np.array_equal(m0.vertices, m1.vertices) and np.array_equal(m0.faces, m1.faces)
    assert not (len(m2.faces) == len(m0.faces) and np.array_equal(m2.vertices, m0.vertices))
    h0, h2 = _vertical(m0, 20.3, 15.1), _vertical(m2, 20.3, 15.1)
    assert len(h0) == 4 and abs(h0[2] - 18.0) < TOL and abs(h0[3] - 18.0) < TOL, h0               # la membrana: dos impactos en z = 18
    assert len(h2) == 2 and abs(h2[0]) < TOL and abs(h2[1] - 2.5) < TOL, h2                       # solo el frente
    assert m2.is_watertight and abs(m2.volume - m0.volume) < 1e-6 * m0.volume


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
            if os.environ.get("FALLA_RAPIDO"):             # para el mutation testing: con una falla alcanza
                break
    print()
    if fallas:
        print(f"{fallas} de {len(tests)} tests fallaron.")
        sys.exit(1)
    print(f"Los {len(tests)} tests pasaron.")
