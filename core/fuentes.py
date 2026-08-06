#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/fuentes.py
------------------
Catálogo de fuentes .ttf/.otf disponibles: las del proyecto (`fonts/`) más
las instaladas en Windows (`C:\\Windows\\Fonts`), con su nombre real (no
el nombre de archivo) para poder elegirlas de una lista en vez de tener
que escribir o pegar una ruta cada vez.
"""

import glob
import os
import platform

from PIL import ImageFont

CARPETA_FUENTES_PROYECTO = "fonts"
CARPETA_FUENTES_SISTEMA_WINDOWS = r"C:\Windows\Fonts"


def _nombre_amigable(ruta):
    """Nombre real de la fuente (familia + estilo), leído del propio
    archivo. Si no se puede leer, usa el nombre de archivo como respaldo."""
    try:
        familia, estilo = ImageFont.truetype(ruta, 100).getname()
        if estilo and estilo.lower() not in ("regular", "normal"):
            return f"{familia} {estilo}"
        return familia
    except Exception:
        return os.path.splitext(os.path.basename(ruta))[0]


def listar_fuentes():
    """Junta las fuentes de `fonts/` (del proyecto) y las instaladas en
    Windows. Devuelve una lista de (nombre_amigable, ruta) ordenada por
    nombre, sin duplicados de ruta."""
    rutas = set()
    for carpeta in (CARPETA_FUENTES_PROYECTO,):
        rutas |= set(glob.glob(os.path.join(carpeta, "*.ttf")))
        rutas |= set(glob.glob(os.path.join(carpeta, "*.otf")))

    if platform.system() == "Windows" and os.path.isdir(CARPETA_FUENTES_SISTEMA_WINDOWS):
        rutas |= set(glob.glob(os.path.join(CARPETA_FUENTES_SISTEMA_WINDOWS, "*.ttf")))
        rutas |= set(glob.glob(os.path.join(CARPETA_FUENTES_SISTEMA_WINDOWS, "*.otf")))

    fuentes = [(_nombre_amigable(ruta), ruta) for ruta in rutas]
    fuentes.sort(key=lambda t: t[0].lower())
    return fuentes


def buscar_por_nombre(consulta):
    """Busca, entre todas las fuentes disponibles, la que mejor matchea
    `consulta` por nombre (no distingue mayúsculas, busca substring).
    Devuelve la ruta, o None si no encontró nada."""
    consulta = consulta.strip().lower()
    if not consulta:
        return None
    coincidencias = [(nombre, ruta) for nombre, ruta in listar_fuentes() if consulta in nombre.lower()]
    if not coincidencias:
        return None
    coincidencias.sort(key=lambda t: len(t[0]))  # preferí la coincidencia más "exacta" (nombre más corto)
    return coincidencias[0][1]
