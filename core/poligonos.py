#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/poligonos.py
--------------------
Utilidad compartida: una lista de polígonos shapely sueltos (p.ej. sacados
de un contorno rasterizado o de un SVG) -> un solo polígono con huecos
donde corresponda (un contorno chico contenido adentro de uno grande se
resta como hueco, p.ej. el interior de una "o" o el agujero de una dona).
Usada por core/texto2d.py (fuentes) y core/svg_import.py (SVG/íconos).
"""

from shapely.ops import unary_union


def combinar_con_huecos(polys):
    """Devuelve un único polígono/multipolígono shapely a partir de una
    lista de polígonos sueltos, restando como hueco cualquier polígono
    contenido adentro de uno más grande. Devuelve None si `polys` está
    vacía."""
    if not polys:
        return None

    polys = sorted(polys, key=lambda p: p.area, reverse=True)
    usados = [False] * len(polys)
    piezas = []
    for i, p in enumerate(polys):
        if usados[i]:
            continue
        cuerpo = p
        usados[i] = True
        for j in range(i + 1, len(polys)):
            if usados[j]:
                continue
            if cuerpo.contains(polys[j].representative_point()):
                cuerpo = cuerpo.difference(polys[j])
                usados[j] = True
        piezas.append(cuerpo)

    return unary_union(piezas)
