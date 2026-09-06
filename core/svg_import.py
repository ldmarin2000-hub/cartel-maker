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

from core.colores import fusionar_colores_cercanos
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


def _color_de_forma(el):
    """Color de relleno resuelto para el elemento `el` -- `svgelements`
    ya resuelve solo el atributo `fill` directo, `style="fill:..."`, la
    herencia desde un `<g fill="...">`, y las clases de un `<style>`
    CSS (`class="st0"` + `.st0{fill:...}`, típico de un SVG exportado
    de Illustrator) -- no hace falta parsear nada de eso a mano. Si el
    elemento no tiene relleno (`fill="none"`, común en esos mismos
    archivos para un detalle dibujado solo con contorno) pero sí tiene
    `stroke`, se usa el color del contorno como si fuera el relleno --
    para poder separarlo igual como su propia región de color. None si
    no hay ni fill ni stroke (nada que pintar)."""
    fill = el.fill
    if fill is not None and fill.hexrgb:
        return fill.hexrgb.lower()  # .hexrgb ya viene con "#" -- no anteponer otro
    stroke = el.stroke
    if stroke is not None and stroke.hexrgb:
        return stroke.hexrgb.lower()
    return None


def _poligonos_por_elemento(svg, puntos_por_curva):
    """Itera los `Shape` de `svg` y por cada uno devuelve (polígono,
    color_hex_o_None) -- el polígono ya combinado con sus huecos
    internos (ver docstring de módulo: los huecos de fill-rule solo
    tienen sentido DENTRO de un mismo elemento, entre elementos
    distintos no se agujerea nada). Elementos sin ningún área o sin
    ningún color resoluble (`_color_de_forma`) no se devuelven. Paso
    compartido entre `svg_a_poligono` (ignora el color, une todo) y
    `svg_a_poligonos_por_color` (agrupa por color)."""
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

        combinado_elemento = combinar_con_huecos(polys_elemento)
        if combinado_elemento is None or combinado_elemento.is_empty:
            continue
        yield combinado_elemento, _color_de_forma(el)


def svg_a_poligono(ruta_svg, puntos_por_curva=PUNTOS_POR_CURVA):
    """Lee un SVG y devuelve un polígono shapely relleno, centrado en el
    origen, en las unidades del SVG (sin escalar todavía — eso lo hace
    texto2d.escalar_a_alto()/escalar_a_caja() después, igual que con el
    texto). Junta todas las formas del archivo (path, rect, circle,
    polygon, etc.) con sus transforms aplicados (incluidos los de grupos
    anidados) — sea un ícono de un solo color o una ilustración de
    varios. Devuelve None si no se pudo sacar ninguna forma con área."""
    svg = SVG.parse(ruta_svg)
    piezas = [p for p, _ in _poligonos_por_elemento(svg, puntos_por_curva)]

    if not piezas:
        return None
    combinado = unary_union(piezas)
    if combinado.is_empty:
        return None

    minx, miny, maxx, maxy = combinado.bounds
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    return affine_transform(combinado, [1, 0, 0, 1, -cx, -cy])


def svg_a_poligonos_por_color(ruta_svg, puntos_por_curva=PUNTOS_POR_CURVA):
    """Como `svg_a_poligono`, pero separa el SVG en una región por cada
    color de relleno declarado en las formas -- pensado para un logo o
    escudo vectorial con colores bien definidos (ver `_color_de_forma`
    para qué cuenta como "el color" de una forma, incluido el caso
    `fill:none` + `stroke`).

    A diferencia de `imagen_import.imagen_a_poligonos_por_color` (que
    tiene que ADIVINAR los colores cuantizando píxeles, con ruido de
    antialiasing y fondo de por medio a filtrar), acá el color de cada
    forma ya viene declarado en el archivo -- no hace falta cuantizar
    ni umbralizar nada. Igual puede pasar que el mismo color "visual"
    aparezca dos veces con un hex apenas distinto (dos objetos con el
    mismo color nominal pero redondeado distinto al exportar el SVG) --
    se resuelve igual que con la imagen, con
    `core.colores.fusionar_colores_cercanos`.

    Los huecos de fill-rule solo se resuelven DENTRO de cada elemento
    (ver `_poligonos_por_elemento`) -- entre formas de un mismo color
    se UNEN sin agujerear, así una letra calada de otro color (una
    inicial cortada en el medio de un escudo) no se malinterpreta como
    un agujero de ese color.

    Devuelve una lista de (polígono, "#rrggbb") en las unidades propias
    del SVG (sin centrar ni escalar -- eso lo hace quien llama, igual
    que con la imagen), ordenada de mayor a menor área. Lista vacía si
    no se pudo sacar ningún color con área."""
    svg = SVG.parse(ruta_svg)

    poligonos_por_color = {}
    for poligono, color_hex in _poligonos_por_elemento(svg, puntos_por_curva):
        if color_hex is None:
            continue
        poligonos_por_color.setdefault(color_hex, []).append(poligono)

    candidatos = []
    for color_hex, poligonos in poligonos_por_color.items():
        poligono = unary_union(poligonos) if len(poligonos) > 1 else poligonos[0]
        if poligono.is_empty or poligono.area <= 0:
            continue
        candidatos.append((poligono.area, poligono, color_hex))

    candidatos = fusionar_colores_cercanos(candidatos)
    return [(poligono, color_hex) for _, poligono, color_hex in candidatos]
