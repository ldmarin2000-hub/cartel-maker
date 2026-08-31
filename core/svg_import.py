#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/svg_import.py
---------------------
SVG (cualquier ícono/logo/ilustración) -> polígono shapely relleno, con
el mismo enfoque que core/texto2d.py para texto: cada forma/subtrazado
del SVG se muestrea en una polilínea. Los huecos (core/poligonos.py) se
detectan SOLO entre subtrazados de un mismo elemento <path> — que es
donde el fill-rule de SVG (evenodd/nonzero) realmente los define, como
el agujero de una dona. Entre elementos DISTINTOS (p.ej. las 16 formas
de colores distintos de una ilustración) no se agujerea nada, solo se
unen — si no, una forma interna de otro color (como el detalle claro
adentro de una oreja) se malinterpretaría como un agujero y rompía la
malla ("Not all meshes are volumes!").

Usa `svgelements` (100% Python, no necesita instalar Cairo/GTK como sí
piden cairosvg/svglib en Windows) para leer el SVG, aplicar transforms
(incluidos los de grupos anidados) y muestrear cada curva (bezier/arco)
a puntos.
"""

from shapely.affinity import affine_transform
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union
from svgelements import SVG, Path as SvgPath, Shape, Move, Line, Close

from core.poligonos import combinar_con_huecos

PUNTOS_POR_CURVA = 24  # cuántos puntos se samplean por segmento bezier/arco


def _subpath_a_puntos(subpath, puntos_por_curva):
    """Convierte un subtrazado a una polilínea. Los tramos RECTOS
    (Move/Line/Close) usan solo su punto final -- meter puntos
    intermedios ahí no suma nada y de hecho rompe la triangulación al
    extruir (muchos puntos colineales confunden al triangulador). Las
    curvas (bezier/arco) sí necesitan muestreo denso para verse suaves."""
    pts = []
    for seg in subpath:
        if isinstance(seg, (Move, Line, Close)):
            if seg.end is not None:
                pts.append((seg.end.x, -seg.end.y))  # el eje Y de SVG va hacia abajo
        elif hasattr(seg, "point"):
            for i in range(1, puntos_por_curva):
                t = i / (puntos_por_curva - 1)
                p = seg.point(t)
                pts.append((p.x, -p.y))
    return pts


def svg_a_poligono(ruta_svg, puntos_por_curva=PUNTOS_POR_CURVA):
    """Lee un SVG y devuelve un polígono shapely relleno, centrado en el
    origen, en las unidades del SVG (sin escalar todavía — eso lo hace
    texto2d.escalar_a_alto()/escalar_a_caja() después, igual que con el
    texto). Junta todas las formas del archivo (path, rect, circle,
    polygon, etc.) con sus transforms aplicados (incluidos los de grupos
    anidados) — sea un ícono de un solo color o una ilustración de
    varios. Devuelve None si no se pudo sacar ninguna forma con área."""
    svg = SVG.parse(ruta_svg)
    piezas = []
    for el in svg.elements():
        if not isinstance(el, Shape):
            continue
        polys_elemento = []
        for subpath in SvgPath(el).as_subpaths():
            pts = _subpath_a_puntos(subpath, puntos_por_curva)
            if len(pts) < 3:
                continue
            p = Polygon(pts)
            if not p.is_valid:
                p = p.buffer(0)  # un trazo auto-cruzado (p.ej. una "porción de pizza"
                # con las puntas mal ordenadas) puede reventar en un MultiPolygon acá
            partes = p.geoms if isinstance(p, MultiPolygon) else [p]
            for parte in partes:
                if parte.is_empty or parte.area < 1e-9:
                    continue
                polys_elemento.append(parte)

        # los huecos (fill-rule evenodd/nonzero) solo tienen sentido entre
        # subtrazados del MISMO <path> -- entre <path> distintos (p.ej.
        # colores distintos de una ilustración) no se agujerea nada.
        combinado_elemento = combinar_con_huecos(polys_elemento)
        if combinado_elemento is not None and not combinado_elemento.is_empty:
            piezas.append(combinado_elemento)

    if not piezas:
        return None
    combinado = unary_union(piezas)
    if combinado.is_empty:
        return None

    minx, miny, maxx, maxy = combinado.bounds
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    return affine_transform(combinado, [1, 0, 0, 1, -cx, -cy])
