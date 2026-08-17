#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/raster_svg.py
---------------------
Paso 1 del pipeline de neón desde SVG: dibujo/ícono (SVG) -> máscara
binaria (numpy), mismo contrato que core/raster.py::rasterizar() (texto)
para que el resto del pipeline (core/skeleton.py en adelante) no note la
diferencia entre "vino de una fuente" o "vino de un SVG".

Reutiliza core/svg_import.py (que ya sabe leer cualquier SVG con sus
huecos/fill-rule bien resueltos) y rasteriza el polígono resultante con
PIL. Los SVG trazados a mano (p.ej. "Trazar mapa de bits" de Inkscape
sobre un dibujo escaneado) suelen dejar manchitas de ruido de 1-2 píxeles
sueltas -- se descartan con remove_small_objects antes de esqueletizar.

También se tapan los huequitos de 1-2 píxeles que quedan cuando dos
subformas del mismo trazo se dibujan casi-pero-no-perfectamente pegadas
(típico en un SVG con muchos subtrazados, como el asa o el borde de un
dibujo trazado a mano) -- si no se tapan, el esqueletizado rodea cada
huequito y deja una unión fea/abultada justo ahí en vez de una línea
lisa (se ve como una "facetita" en el STL final).

Los componentes se dibujan de MÁS GRANDE a MÁS CHICO: es válido que el
agujero de una pieza (p.ej. el hueco de un anillo) tenga otra pieza
sólida SEPARADA flotando adentro (p.ej. un detalle/trazo que cruza por el
medio) -- core/poligonos.py ya resuelve bien esa geometría, pero si se
dibujara la pieza chica (el detalle) ANTES que la grande (el anillo), el
agujero del anillo la taparía de nuevo. Dibujando de grande a chico, el
detalle siempre se pinta último y queda arriba.
"""

import numpy as np
from PIL import Image, ImageDraw
from skimage.morphology import remove_small_holes, remove_small_objects

from core import svg_import

MIN_OBJETO_PX = 12  # descarta componentes conexas más chicas que esto (ruido de trazado)
MIN_HUECO_PX = 12  # tapa huequitos internos más chicos que esto (costuras entre subformas)


def rasterizar(ruta_svg, resolucion_px, pad=24, min_objeto_px=MIN_OBJETO_PX, min_hueco_px=MIN_HUECO_PX):
    """Lee el SVG, lo rellena (con huecos correctos) y lo rasteriza a una
    máscara booleana con `resolucion_px` píxeles de alto -- mismo
    significado que el tamaño de fuente en core/raster.py::rasterizar().
    Devuelve una máscara booleana (True = tinta) con margen `pad` px."""
    poligono = svg_import.svg_a_poligono(ruta_svg)
    if poligono is None:
        raise ValueError(f"no se pudo sacar ninguna forma con área del SVG: {ruta_svg}")

    minx, miny, maxx, maxy = poligono.bounds
    alto = maxy - miny
    ancho = maxx - minx
    if alto <= 0 or ancho <= 0:
        raise ValueError(f"el SVG no tiene área (¿está vacío?): {ruta_svg}")

    escala = resolucion_px / alto
    ancho_px = max(int(round(ancho * escala)) + 2 * pad, 1)
    alto_px = int(round(resolucion_px)) + 2 * pad

    img = Image.new("L", (ancho_px, alto_px), 0)
    draw = ImageDraw.Draw(img)

    def a_px(punto):
        x, y = punto
        return ((x - minx) * escala + pad, (maxy - y) * escala + pad)

    geoms = poligono.geoms if hasattr(poligono, "geoms") else [poligono]
    geoms = sorted(geoms, key=lambda p: p.area, reverse=True)
    for p in geoms:
        if p.is_empty:
            continue
        draw.polygon([a_px(pt) for pt in p.exterior.coords], fill=255)
        for interior in p.interiors:
            draw.polygon([a_px(pt) for pt in interior.coords], fill=0)

    mask = np.array(img) > 128
    if min_objeto_px > 0:
        mask = remove_small_objects(mask, min_size=min_objeto_px)
    if min_hueco_px > 0:
        mask = remove_small_holes(mask, area_threshold=min_hueco_px)
    return mask
