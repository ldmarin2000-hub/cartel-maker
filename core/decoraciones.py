#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/decoraciones.py
-----------------------
Formas de decoración para el llavero, porteadas 1:1 de las fórmulas
paramétricas de scad/llaveros.scad (mismas proporciones, ahora en shapely
en vez de OpenSCAD).
"""

import math

from shapely.affinity import affine_transform
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

from core import svg_import, texto2d

NOMBRES_VALIDOS = ("ninguno", "corazon", "estrella", "flor", "gato", "rayo", "luna", "rombo", "circulo")

# Emojis/pictogramas y signos/símbolos como decoración: mismo pipeline que el
# texto (core/texto2d.py), con una fuente MONOCROMA de contorno vectorizable
# -no una fuente de emoji a color (Noto Color Emoji, Apple Color Emoji, etc,
# que son bitmap/COLR y no se pueden sacar como contorno)-. Noto Emoji cubre
# el set completo de emoji en blanco y negro; Noto Sans Symbols 2 cubre
# dingbats/símbolos clásicos (☺ ☂ ☀ ⚙ etc) que no son "emoji" en sentido
# estricto pero sirven igual de pictograma/signo. Viven en fonts/simbolos/,
# NO en fonts/curadas/ -esa carpeta la escanea core/fuentes.py para el
# selector general de fuentes de TEXTO; si estuvieran ahí, "Noto Emoji"
# aparecería mezclada entre las opciones para tipear el nombre de un llavero.
FUENTE_EMOJI = "fonts/simbolos/NotoEmoji.ttf"
FUENTE_SIGNOS = "fonts/simbolos/NotoSansSymbols2.ttf"

# Curados a mano (verificados: se vectorizan con área > 0 en las fuentes de
# arriba) para el selector rápido de la UI — el usuario también puede tipear
# o pegar cualquier otro emoji/símbolo unicode, esto es solo un atajo.
EMOJIS_CURADOS = [
    "✈", "🎂", "🌙", "⭐", "❤", "⚡", "🎈", "🎁", "🐱", "🐶", "🌸", "🦋",
    "🎵", "☕", "🌈", "🚀", "⚓", "🔥", "💎", "👑", "🦄", "🐾", "🌻", "🍀",
]
SIGNOS_CURADOS = ["★", "☺", "☂", "☀", "❄", "♫", "☮", "☯", "✉", "⚙", "⌚", "☑", "✂", "☎", "⚔", "☠", "♛", "⚖"]


def _corazon(t):
    s = t / 1.4
    c1 = Point(-0.5 * s, 0).buffer(0.5 * s, resolution=32)
    c2 = Point(0.5 * s, 0).buffer(0.5 * s, resolution=32)
    tri = Polygon([(-0.98 * s, 0.12 * s), (0.98 * s, 0.12 * s), (0, -1.15 * s)])
    return unary_union([c1, c2, tri])


def _star_pts(n, ro, ri):
    pts = []
    for i in range(2 * n):
        a = math.radians(90 + i * 180 / n)
        r = ro if i % 2 == 0 else ri
        pts.append((r * math.cos(a), r * math.sin(a)))
    return pts


def _estrella(t):
    return Polygon(_star_pts(5, t, t * 0.5))


def _flor(t):
    petalos = []
    for i in range(6):
        a = math.radians(i * 60)
        cx, cy = t * 0.55 * math.cos(a), t * 0.55 * math.sin(a)
        petalos.append(Point(cx, cy).buffer(t * 0.45, resolution=24))
    centro = Point(0, 0).buffer(t * 0.5, resolution=24)
    return unary_union(petalos + [centro])


def _gato(t):
    cabeza = Point(0, 0).buffer(t * 0.8, resolution=32)
    orejas = []
    for m in (-1, 1):
        pts = [
            (m * (t * 0.5 - t * 0.28), t * 0.5),
            (m * (t * 0.5 + t * 0.28), t * 0.5),
            (m * t * 0.5, t * 0.5 + t * 0.55),
        ]
        orejas.append(Polygon(pts))
    return unary_union([cabeza] + orejas)


def _rayo(t):
    pts = [(0.15, 1), (-0.45, 0.05), (-0.05, 0.05), (-0.2, -1), (0.5, 0.0), (0.1, 0.0)]
    return Polygon([(x * t, y * t) for x, y in pts])


def _luna(t):
    grande = Point(0, 0).buffer(t, resolution=32)
    chico = Point(t * 0.55, 0).buffer(t * 0.92, resolution=32)
    return grande.difference(chico)


def _rombo(t):
    return Polygon([(0, t), (t * 0.7, 0), (0, -t), (-t * 0.7, 0)])


def _circulo(t):
    return Point(0, 0).buffer(t, resolution=32)


_FORMAS = {
    "corazon": _corazon,
    "estrella": _estrella,
    "flor": _flor,
    "gato": _gato,
    "rayo": _rayo,
    "luna": _luna,
    "rombo": _rombo,
    "circulo": _circulo,
}


def forma(nombre, tam):
    """Devuelve el polígono shapely de la decoración `nombre` (centrado en
    el origen, tamaño `tam`), o None si es "ninguno" o no se reconoce."""
    fn = _FORMAS.get(nombre)
    return fn(tam) if fn else None


def forma_desde_svg(ruta_svg, tam):
    """Como forma(), pero para un ícono/SVG cualquiera que suba el
    usuario en vez de una de las decoraciones predefinidas de la lista —
    mismo resultado final (polígono centrado en el origen, escalado para
    que su lado más largo mida `2*tam`, en línea con el tamaño de las
    demás decoraciones), así se puede usar igual en el resto del
    pipeline (llavero, ambigrama). Devuelve None si el SVG no tiene
    ninguna forma con área."""
    crudo = svg_import.svg_a_poligono(ruta_svg)
    if crudo is None:
        return None
    minx, miny, maxx, maxy = crudo.bounds
    lado_mayor = max(maxx - minx, maxy - miny)
    if lado_mayor <= 0:
        return None
    escala = (2 * tam) / lado_mayor
    return affine_transform(crudo, [escala, 0, 0, escala, 0, 0])


def forma_desde_emoji(caracter, tam, ruta_ttf=None):
    """Como forma(), pero para un emoji/pictograma/signo (un solo
    carácter unicode, ej. "✈", "🎂", "★") en vez de una decoración de la
    lista o un SVG — se vectoriza con el mismo pipeline que el texto
    (core/texto2d.py: rasterizar + contornear), usando una fuente
    monocroma de contorno (`FUENTE_EMOJI` por default; pasá
    `FUENTE_SIGNOS` para dingbats clásicos que no están en la fuente de
    emoji). Mismo resultado final que `forma_desde_svg`: centrado en el
    origen, escalado para que su lado más largo mida `2*tam`. Devuelve
    None si el carácter no existe en la fuente o no se pudo extraer
    nada con área."""
    ruta_ttf = ruta_ttf or FUENTE_EMOJI
    crudo, _ = texto2d.texto_a_poligono(caracter, ruta_ttf, alto_mm=100, raster_px=200)
    if crudo is None:
        return None
    minx, miny, maxx, maxy = crudo.bounds
    lado_mayor = max(maxx - minx, maxy - miny)
    if lado_mayor <= 0:
        return None
    escala = (2 * tam) / lado_mayor
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    return affine_transform(crudo, [escala, 0, 0, escala, -cx * escala, -cy * escala])
