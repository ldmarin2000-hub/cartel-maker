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

El criterio para "es hueco" es el SENTIDO DE GIRO (orientación) de cada
contorno relativo a su contenedor INMEDIATO (el más chico que lo contiene),
no solo si queda geométricamente adentro -- así es como funciona la regla
real de relleno de SVG/fuentes (nonzero winding): un contorno con el MISMO
sentido que su contenedor SUMA como sólido, el sentido OPUESTO resta como
hueco. Se arma el árbol de anidado (cada contorno con su contenedor
inmediato) y se resuelve de adentro hacia afuera, así un detalle sólido
anidado DENTRO de un hueco (p.ej. un garabato/trazo que cruza por el medio
de un ícono en forma de anillo) vuelve a "perforar" ese hueco en vez de
desaparecer -- sumar/restar todo contra el contorno más grande sin
respetar el anidado real borraría ese detalle."""

from shapely.ops import unary_union


def combinar_con_huecos(polys):
    """Devuelve un único polígono/multipolígono shapely a partir de una
    lista de polígonos sueltos, resolviendo el anidado real (sentido de
    giro relativo al contenedor inmediato, de adentro hacia afuera).
    Devuelve None si `polys` está vacía."""
    if not polys:
        return None

    polys = sorted(polys, key=lambda p: p.area, reverse=True)
    n = len(polys)
    signos = [1 if p.exterior.is_ccw else -1 for p in polys]
    puntos = [p.representative_point() for p in polys]

    padre = [None] * n
    for i in range(n):
        mejor = None
        for j in range(n):
            if j == i or polys[j].area <= polys[i].area:
                continue
            if not polys[j].contains(puntos[i]):
                continue
            if mejor is None or polys[j].area < polys[mejor].area:
                mejor = j
        padre[i] = mejor

    hijos = [[] for _ in range(n)]
    raices = []
    for i in range(n):
        if padre[i] is None:
            raices.append(i)
        else:
            hijos[padre[i]].append(i)

    def resolver(i):
        resultado = polys[i]
        for h in hijos[i]:
            sub = resolver(h)
            resultado = resultado.union(sub) if signos[h] == signos[i] else resultado.difference(sub)
        return resultado

    piezas = [resolver(r) for r in raices]
    return unary_union(piezas)
