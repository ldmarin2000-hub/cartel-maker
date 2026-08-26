#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/texto2d.py
------------------
Texto (con una fuente .ttf) -> polígono shapely RELLENO (el contorno de
la tinta, con huecos donde corresponda — la "o", la "a", etc.), a
diferencia de core/skeleton.py que saca la línea central para el neón. Lo
usa el llavero, que necesita el texto como una forma sólida para hacer
relieve, no un canal para un LED.
"""

from shapely.affinity import affine_transform
from shapely.geometry import Polygon
from skimage import measure

from core import raster
from core.poligonos import combinar_con_huecos


def _contornos_a_poligono(mask):
    """Vectoriza una máscara booleana con marching squares y arma un
    polígono shapely con huecos (los contornos chicos contenidos adentro
    de uno grande se restan como huecos, p.ej. el interior de una "o")."""
    contornos = measure.find_contours(mask.astype(float), level=0.5)
    alto_px = mask.shape[0]

    polys = []
    for c in contornos:
        if len(c) < 4:
            continue
        pts = [(col, alto_px - row) for row, col in c]  # flip Y: fila 0 = arriba
        p = Polygon(pts)
        if not p.is_valid:
            p = p.buffer(0)
        if p.is_empty or p.area < 1:
            continue
        polys.append(p)

    return combinar_con_huecos(polys)


def escalar_a_alto(poligono, alto_mm):
    """Escala (uniforme) y traslada `poligono` para que mida exactamente
    `alto_mm` de alto, con la esquina inferior izquierda en (0,0). Sirve
    para cualquier polígono (texto o una decoración de
    core/decoraciones.py), no solo texto. Devuelve (poligono_escalado,
    ancho_mm)."""
    minx, miny, maxx, maxy = poligono.bounds
    alto_real = maxy - miny
    if alto_real <= 0:
        return None, 0
    escala = alto_mm / alto_real
    poligono_mm = affine_transform(poligono, [escala, 0, 0, escala, -minx * escala, -miny * escala])
    ancho_mm = (maxx - minx) * escala
    return poligono_mm, ancho_mm


def escalar_a_caja(poligono, ancho_mm, alto_mm):
    """Escala X e Y POR SEPARADO (no uniforme — estira o achica cada eje
    lo que haga falta) para que `poligono` entre exacto en una caja de
    `ancho_mm` x `alto_mm`, con la esquina inferior izquierda en (0,0).
    Esto es justo lo que hace la técnica del ambigrama: fuerza a los dos
    lados a la MISMA caja, aunque eso distorsione las proporciones
    naturales del contenido (por eso avisamos aparte cuando la
    distorsión es grande). Devuelve el polígono escalado, o None."""
    minx, miny, maxx, maxy = poligono.bounds
    ancho_real, alto_real = maxx - minx, maxy - miny
    if ancho_real <= 0 or alto_real <= 0:
        return None
    esc_x, esc_y = ancho_mm / ancho_real, alto_mm / alto_real
    return affine_transform(poligono, [esc_x, 0, 0, esc_y, -minx * esc_x, -miny * esc_y])


def texto_a_poligono_crudo(texto, ruta_ttf, raster_px=400, pad=24, espaciado_relativo=0.0):
    """Rasteriza y vectoriza `texto` SIN escalar (queda en unidades de
    píxel arbitrarias) — para cuando el escalado final lo va a hacer otra
    cosa (p.ej. escalar_a_caja(), como en el ambigrama). `espaciado_relativo`
    ajusta la separación entre letras (negativo = más juntas, hasta
    tocarse/superponerse — ver core/raster.py::rasterizar_con_espaciado).
    Devuelve el polígono shapely, o None."""
    if espaciado_relativo:
        mask = raster.rasterizar_con_espaciado(texto, ruta_ttf, raster_px, espaciado_relativo, pad)
    else:
        mask = raster.rasterizar(texto, ruta_ttf, raster_px, pad)
    return _contornos_a_poligono(mask)


SIMPLIFY_MM = 0.15  # tolerancia para sacar puntos redundantes del trazado de marching squares


def texto_a_poligono(texto, ruta_ttf, alto_mm, raster_px=400, pad=24):
    """Rasteriza y vectoriza `texto`, y lo devuelve como polígono shapely
    ya escalado (uniforme) para medir `alto_mm` de alto — medido de
    verdad sobre la geometría, no estimado como hace OpenSCAD. Devuelve
    (poligono, ancho_mm) o (None, 0) si no se pudo extraer nada.

    El contorno de marching squares (`_contornos_a_poligono`) deja MUCHOS
    puntos casi-colineales sobre curvas suaves (miles para una sola
    letra) -- simplificar con una tolerancia chica (`SIMPLIFY_MM`) los
    saca sin cambiar la forma (el área prácticamente no se mueve), pero
    baja la cantidad de triángulos finísimos que deja después una
    extrusión/booleana sobre ese contorno (se nota sobre todo en cáscaras
    huecas de poca profundidad, como letras.py/caja_luz.py: sin esto, la
    malla queda con un montón de triángulos "flacos" apilados en los
    bordes redondeados, que algunos visores muestran como un remolino
    de facetas raro aunque la pieza sea watertight y imprima bien)."""
    poligono = texto_a_poligono_crudo(texto, ruta_ttf, raster_px, pad)
    if poligono is None or poligono.is_empty:
        return None, 0
    poligono_mm, ancho_mm = escalar_a_alto(poligono, alto_mm)
    if poligono_mm is None:
        return None, 0
    return poligono_mm.simplify(SIMPLIFY_MM, preserve_topology=True), ancho_mm
