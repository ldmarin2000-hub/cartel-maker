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
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

from core import imagen_import, svg_import, texto2d

NOMBRES_VALIDOS = (
    "ninguno",
    "corazon", "estrella", "flor", "gato", "rayo", "luna", "rombo", "circulo",
    # abstracto
    "triangulo", "hexagono", "cruz", "escudo", "onda", "infinito", "engranaje",
    # mascota
    "perro", "pajaro", "pez", "oso", "conejo",
)

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


# --- Set "abstracto" (logo geométrico, sin figura reconocible) ---------

def _triangulo(t):
    return Polygon([(0, t), (t * 0.87, -t * 0.5), (-t * 0.87, -t * 0.5)])


def _hexagono(t):
    return Polygon([(t * math.cos(math.radians(60 * i)), t * math.sin(math.radians(60 * i))) for i in range(6)])


def _cruz(t):
    brazo = t * 0.32
    h = Polygon([(-t, brazo), (t, brazo), (t, -brazo), (-t, -brazo)])
    v = Polygon([(brazo, t), (brazo, -t), (-brazo, -t), (-brazo, t)])
    return unary_union([h, v])


def _escudo(t):
    """Escudo/blasón: arriba ancho y plano, termina en punta abajo — pensado
    para el modo "emblema" (texto/ícono adentro, en vez del anillo circular
    default)."""
    pts = [
        (-t, t), (t, t), (t, t * 0.1),
        (0, -t * 1.1),
        (-t, t * 0.1),
    ]
    base = Polygon(pts)
    return base.buffer(t * 0.06, join_style="round").buffer(-t * 0.06, join_style="round")


def _onda(t):
    """Cinta en forma de S — una curva senoidal engrosada, logo abstracto
    tipo "onda/flujo"."""
    xs = [i / 60 * 2 * math.pi for i in range(61)]
    centro = [(t * (x / (2 * math.pi) * 2 - 1), t * 0.45 * math.sin(x)) for x in xs]
    return LineString(centro).buffer(t * 0.16, cap_style="round", join_style="round")


def _infinito(t):
    r_ext, r_int, dx = t * 0.55, t * 0.28, t * 0.5
    anillo_izq = Point(-dx, 0).buffer(r_ext, resolution=32).difference(Point(-dx, 0).buffer(r_int, resolution=32))
    anillo_der = Point(dx, 0).buffer(r_ext, resolution=32).difference(Point(dx, 0).buffer(r_int, resolution=32))
    return unary_union([anillo_izq, anillo_der])


def _engranaje(t):
    n_dientes = 8
    r_ext, r_int, r_eje = t, t * 0.72, t * 0.32
    pts = []
    for i in range(n_dientes * 4):
        frac = (i % 4) / 4
        a = math.radians(i * (360 / (n_dientes * 4)))
        r = r_ext if frac < 0.5 else r_int
        pts.append((r * math.cos(a), r * math.sin(a)))
    cuerpo = Polygon(pts).buffer(0)
    eje = Point(0, 0).buffer(r_eje, resolution=32)
    return cuerpo.difference(eje)


# --- Set "mascota" (animal estilizado, para logos tipo mascota) --------

def _perro(t):
    cabeza = Point(0, 0).buffer(t * 0.75, resolution=32)
    orejas = []
    for m in (-1, 1):
        orejas.append(
            Point(m * t * 0.62, t * 0.15).buffer(t * 0.32, resolution=24)
            .intersection(Polygon([(m * t * 2, t * 2), (m * t * 2, -t * 2), (0, -t * 2), (0, t * 2)]))
        )
    hocico = Point(0, -t * 0.55).buffer(t * 0.38, resolution=24)
    return unary_union([cabeza] + orejas + [hocico])


def _pajaro(t):
    cuerpo = Point(-t * 0.1, 0).buffer(t * 0.62, resolution=32)
    ala = Polygon([(-t * 0.15, t * 0.1), (t * 0.05, t * 0.75), (t * 0.35, t * 0.05)])
    pico = Polygon([(t * 0.45, 0.05 * t), (t * 1.05, 0), (t * 0.45, -0.15 * t)])
    return unary_union([cuerpo, ala, pico])


def _pez(t):
    cuerpo = Point(-t * 0.15, 0).buffer(t * 0.6, resolution=32)
    cola = Polygon([(t * 0.3, t * 0.5), (t * 0.95, 0), (t * 0.3, -t * 0.5)])
    return unary_union([cuerpo, cola])


def _oso(t):
    cabeza = Point(0, 0).buffer(t * 0.8, resolution=32)
    orejas = [Point(m * t * 0.55, t * 0.62).buffer(t * 0.26, resolution=24) for m in (-1, 1)]
    hocico = Point(0, -t * 0.35).buffer(t * 0.4, resolution=24)
    return unary_union([cabeza] + orejas + [hocico])


def _conejo(t):
    cabeza = Point(0, -t * 0.15).buffer(t * 0.62, resolution=32)
    orejas = []
    for m in (-1, 1):
        orejas.append(
            affine_transform(
                Point(0, 0).buffer(t * 0.2, resolution=20),
                [1, 0, 0, 1.9, m * t * 0.28, t * 0.85],
            )
        )
    return unary_union([cabeza] + orejas)


_FORMAS = {
    "corazon": _corazon,
    "estrella": _estrella,
    "flor": _flor,
    "gato": _gato,
    "rayo": _rayo,
    "luna": _luna,
    "rombo": _rombo,
    "circulo": _circulo,
    "triangulo": _triangulo,
    "hexagono": _hexagono,
    "cruz": _cruz,
    "escudo": _escudo,
    "onda": _onda,
    "infinito": _infinito,
    "engranaje": _engranaje,
    "perro": _perro,
    "pajaro": _pajaro,
    "pez": _pez,
    "oso": _oso,
    "conejo": _conejo,
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


def forma_desde_imagen(ruta_imagen, tam, umbral=128, invertir=False):
    """Como forma_desde_svg(), pero para una imagen rasterizada (PNG,
    JPG, etc — un logo/ícono simple, silueta clara sobre fondo liso o
    transparente, no una foto) en vez de un SVG (core/imagen_import.py).
    `invertir=True` si el logo es claro sobre fondo oscuro (por default
    asume oscuro sobre claro, o usa el canal alfa si el PNG tiene
    transparencia). Mismo resultado final que las demás formas: centrado
    en el origen, escalado para que su lado más largo mida `2*tam`.
    Devuelve None si no se pudo sacar ninguna forma con área."""
    crudo = imagen_import.imagen_a_poligono_crudo(ruta_imagen, umbral=umbral, invertir=invertir)
    if crudo is None:
        return None
    minx, miny, maxx, maxy = crudo.bounds
    lado_mayor = max(maxx - minx, maxy - miny)
    if lado_mayor <= 0:
        return None
    escala = (2 * tam) / lado_mayor
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    return affine_transform(crudo, [escala, 0, 0, escala, -cx * escala, -cy * escala])


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
