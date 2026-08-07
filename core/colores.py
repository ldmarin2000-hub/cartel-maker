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
]

NOMBRES = [nombre for nombre, _ in PALETA]
_HEX_POR_NOMBRE = dict(PALETA)


def hex_de(nombre, default="#CCCCCC"):
    """Hex del color curado `nombre`, o `default` si no está en la
    paleta (por si llega un nombre viejo de una sesión anterior)."""
    return _HEX_POR_NOMBRE.get(nombre, default)
