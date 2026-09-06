#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/colores.py
------------------
Paleta de colores curada — nombres y hex que se corresponden con
filamentos PLA reales (tonos típicos de Bambu Lab PLA Basic/Matte y
equivalentes), en vez de nombres CSS genéricos (HotPink, SkyBlue) que
no dicen qué filamento comprar. Un solo lugar para toda la app: el
llavero la usa para elegir el color real de cada pieza, y el resto de
los generadores la usa como referencia de color en el visor 3D
(core/preview3d.py) — no cambia la geometría, es para que el preview
se parezca a lo que vas a imprimir.
"""

TOLERANCIA_FUSION_COLOR = 40  # distancia RGB para fusionar dos colores detectados que en la práctica son el mismo

PALETA = [
    ("Blanco", "#F4F4F2"),
    ("Negro", "#1A1A1A"),
    ("Gris Frío", "#8E9089"),
    ("Plata", "#C4C7C9"),
    ("Beige", "#E8DCC8"),
    ("Marrón", "#7A5230"),
    ("Rojo", "#C0392B"),
    ("Naranja", "#E8720C"),
    ("Amarillo", "#F4C430"),
    ("Verde Lima", "#A6CE39"),
    ("Verde Bosque", "#1E5631"),
    ("Turquesa", "#1BB4A4"),
    ("Celeste", "#4FA8D8"),
    ("Azul", "#1F5FA8"),
    ("Azul Marino", "#0B2E59"),
    ("Púrpura", "#7B4FA0"),
    ("Magenta", "#C2338D"),
    ("Rosa", "#F27BB8"),
    ("Rosa Fluor", "#FF3D8A"),
    ("Dorado", "#C9A94F"),
    ("Cobre", "#B87333"),
    ("Transparente/Natural", "#DCE8E8"),
    ("Cian", "#00BCD4"),
    ("Verde Menta", "#26A69A"),
    ("Naranja Oscuro", "#D2691E"),
    ("Rojo Óxido", "#A0522D"),
    ("Gris Oscuro", "#404040"),
    ("Azul Cielo", "#87CEEB"),
    ("Violeta Oscuro", "#663399"),
    ("Coral", "#FF7F50"),
    ("Teal", "#008080"),
]

NOMBRES = [nombre for nombre, _ in PALETA]
_HEX_POR_NOMBRE = dict(PALETA)


def hex_de(nombre, default="#CCCCCC"):
    """Hex del color curado `nombre`, o `default` si no está en la
    paleta (por si llega un nombre viejo de una sesión anterior)."""
    return _HEX_POR_NOMBRE.get(nombre, default)


def _rgb(hex_color):
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


def nombre_mas_cercano(hex_color):
    """Nombre de la paleta cuyo color se parece más a `hex_color`
    (distancia euclídea en RGB) -- para sugerir un color real de
    filamento a partir de un color detectado automáticamente (ej. al
    separar una imagen por colores)."""
    try:
        objetivo = _rgb(hex_color)
    except (ValueError, IndexError):
        return NOMBRES[0]
    mejor_nombre, mejor_dist = NOMBRES[0], float("inf")
    for nombre, hex_pal in PALETA:
        r, g, b = _rgb(hex_pal)
        dist = (r - objetivo[0]) ** 2 + (g - objetivo[1]) ** 2 + (b - objetivo[2]) ** 2
        if dist < mejor_dist:
            mejor_nombre, mejor_dist = nombre, dist
    return mejor_nombre


def fusionar_colores_cercanos(candidatos, tolerancia=TOLERANCIA_FUSION_COLOR):
    """`candidatos`: lista de (area, polígono, "#rrggbb") -- el área en
    cualquier unidad consistente entre sí (píxeles para una imagen,
    unidades del SVG para un vector), no hace falta que sea real. Dos
    fuentes de color detectado automáticamente (cuantizar una imagen
    por píxel, o leer el `fill` de las formas de un SVG) pueden dar
    colores que en la práctica son "el mismo" pero no coinciden exacto
    -- antialiasing/compresión en una imagen ("#fefefe" vs "#ffffff"),
    o simplemente dos objetos con el mismo color nominal pero un
    redondeo distinto en el archivo original. Se fusionan los que estén
    a menos de `tolerancia` de distancia RGB entre sí, sumando su área
    y uniendo su geometría, y quedándose con el color del más grande
    del grupo. Devuelve la lista ya fusionada, ordenada de mayor a
    menor área.

    Importa shapely recién acá adentro (no al nivel del módulo) --
    core/colores.py lo usan casi todas las páginas solo para nombres/hex
    de la paleta, sin necesitar geometría; si shapely llegara a romperse
    en el entorno (pasó una vez en Streamlit Cloud), no hace falta que
    se caigan esas páginas por una función que ni siquiera llaman."""
    from shapely.ops import unary_union

    grupos = []
    for area, poligono, color_hex in candidatos:
        rgb = _rgb(color_hex)
        grupo_encontrado = None
        for grupo in grupos:
            dist = sum((a - b) ** 2 for a, b in zip(rgb, grupo["rgb"])) ** 0.5
            if dist < tolerancia:
                grupo_encontrado = grupo
                break
        if grupo_encontrado is not None:
            grupo_encontrado["area"] += area
            grupo_encontrado["poligono"] = unary_union([grupo_encontrado["poligono"], poligono])
        else:
            grupos.append({"area": area, "poligono": poligono, "color_hex": color_hex, "rgb": rgb})

    grupos.sort(key=lambda g: g["area"], reverse=True)
    return [(g["area"], g["poligono"], g["color_hex"]) for g in grupos]
