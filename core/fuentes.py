#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/fuentes.py
------------------
Catálogo de fuentes .ttf/.otf disponibles: las curadas del proyecto
(`fonts/curadas/`, Google Fonts bajadas y categorizadas a mano — ver
`CATEGORIAS_CURADAS`), las que el usuario puso sueltas en `fonts/`, y
las instaladas en Windows (`C:\\Windows\\Fonts`) — con su nombre real
(no el nombre de archivo) para poder elegirlas de una lista en vez de
tener que escribir o pegar una ruta cada vez.
"""

import base64
import glob
import os
import platform

from PIL import ImageFont

CARPETA_FUENTES_PROYECTO = "fonts"
CARPETA_FUENTES_CURADAS = "fonts/curadas"
CARPETA_FUENTES_SISTEMA_WINDOWS = r"C:\Windows\Fonts"

# Nombre amigable (el que devuelve _nombre_amigable) -> (categoría, emoji).
# Google Fonts (licencia OFL, ver fonts/curadas/LICENSES/)
# 45+ fuentes elegidas para cubrir estilos bien distintos entre sí
CATEGORIAS_CURADAS = {
    # Script/Cursiva — 14 opciones
    "Pacifico": ("Script", "🖋️"),
    "Sacramento": ("Script", "🖋️"),
    "Lobster": ("Script", "🖋️"),
    "Great Vibes": ("Script", "🖋️"),
    "Dancing Script": ("Script", "🖋️"),
    "Caveat": ("Script", "🖋️"),
    "Permanent Marker": ("Script", "🖋️"),
    "Satisfy": ("Script", "🖋️"),
    "Allura": ("Script", "🖋️"),
    "Handlee": ("Script", "🖋️"),
    "Courgette": ("Script", "🖋️"),
    "Aloha": ("Script", "🖋️"),
    "Dawning of a New Day": ("Script", "🖋️"),
    "Over the Rainbow": ("Script", "🖋️"),
    # Manuscrita — 4 opciones
    "Kalam Bold": ("Manuscrita", "✍️"),
    "Indie Flower": ("Manuscrita", "✍️"),
    "Playpen Sans": ("Manuscrita", "✍️"),
    "Fredoka": ("Manuscrita", "✍️"),
    # Display — 8 opciones
    "Bangers": ("Display", "💥"),
    "Bungee": ("Display", "💥"),
    "Anton": ("Display", "💥"),
    "Righteous": ("Display", "💥"),
    "Passion One Bold": ("Display", "💥"),
    "Amatic SC Bold": ("Display", "💥"),
    "Shrikhand": ("Display", "💥"),
    "Fredericka the Great": ("Display", "💥"),
    # Redondeada — 2 opciones
    "Poppins Bold": ("Redondeada", "⚪"),
    "Quicksand Bold": ("Redondeada", "⚪"),
    # Condensada — 2 opciones
    "Bebas Neue": ("Condensada", "📏"),
    "Oswald": ("Condensada", "📏"),
    # Elegante — 3 opciones
    "Playfair Display": ("Elegante", "🎩"),
    "Abril Fatface": ("Elegante", "🎩"),
    "Cinzel": ("Elegante", "🎩"),
    # Geométrica — 2 opciones
    "Montserrat Bold": ("Geométrica", "🔷"),
    "DM Sans Bold": ("Geométrica", "🔷"),
    # Retro/Neón — 3 opciones
    "Monoton": ("Retro/Neón", "🕹️"),
    "Courier Prime": ("Retro/Neón", "🕹️"),
    "Boogaloo": ("Retro/Neón", "🕹️"),
    # Futurista — 1 opción
    "Orbitron": ("Futurista", "🚀"),
}

ORDEN_CATEGORIAS = [
    "Script", "Manuscrita", "Display", "Redondeada", "Condensada", "Elegante",
    "Geométrica", "Retro/Neón", "Futurista", "Tus fuentes", "Sistema",
]


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


def _glob_ttf_otf(carpeta):
    return set(glob.glob(os.path.join(carpeta, "*.ttf"))) | set(glob.glob(os.path.join(carpeta, "*.otf")))


def listar_fuentes():
    """Junta las fuentes curadas, las de `fonts/` (del proyecto) y las
    instaladas en Windows. Devuelve una lista de (nombre_amigable, ruta)
    ordenada por nombre, sin duplicados de ruta."""
    rutas = _glob_ttf_otf(CARPETA_FUENTES_CURADAS) | _glob_ttf_otf(CARPETA_FUENTES_PROYECTO)

    if platform.system() == "Windows" and os.path.isdir(CARPETA_FUENTES_SISTEMA_WINDOWS):
        rutas |= _glob_ttf_otf(CARPETA_FUENTES_SISTEMA_WINDOWS)

    fuentes = [(_nombre_amigable(ruta), ruta) for ruta in rutas]
    fuentes.sort(key=lambda t: t[0].lower())
    return fuentes


def _categoria_de(nombre_amigable, ruta):
    if nombre_amigable in CATEGORIAS_CURADAS:
        categoria, emoji = CATEGORIAS_CURADAS[nombre_amigable]
        return categoria, emoji
    ruta_norm = ruta.replace("\\", "/")
    if CARPETA_FUENTES_SISTEMA_WINDOWS.replace("\\", "/").lower() in ruta_norm.lower():
        return "Sistema", "🔤"
    return "Tus fuentes", "📁"


def listar_fuentes_agrupadas():
    """Como `listar_fuentes()`, pero con la categoría de cada una
    (`_categoria_de`) para armar un selector agrupado — curadas primero
    (por estilo), después las que el usuario puso en `fonts/`, y al
    final las instaladas en Windows (suelen ser cientos, quedan
    últimas). Devuelve una lista de (nombre_amigable, ruta, categoria,
    emoji), ordenada por categoría (orden de `ORDEN_CATEGORIAS`) y
    dentro de cada una por nombre."""
    fuentes = listar_fuentes()
    con_categoria = [(nombre, ruta, *_categoria_de(nombre, ruta)) for nombre, ruta in fuentes]

    def orden(item):
        _, _, categoria, _ = item
        idx = ORDEN_CATEGORIAS.index(categoria) if categoria in ORDEN_CATEGORIAS else len(ORDEN_CATEGORIAS)
        return (idx, item[0].lower())

    con_categoria.sort(key=orden)
    return con_categoria


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


def html_preview_fuente(ruta_ttf, texto_muestra="Cartel Maker Aa 123", tam_px=42, color_texto="#eee"):
    """HTML de una línea de texto tipeada de verdad en `ruta_ttf` (no una
    imagen pre-renderizada): embebe el .ttf como @font-face en base64, así
    se ve exactamente la fuente elegida antes de generar nada — incluye
    los acentos/símbolos reales que vaya a tener el texto del usuario, no
    un "Aa" genérico. Devuelve None si no se pudo leer el archivo."""
    try:
        with open(ruta_ttf, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
    except OSError:
        return None
    formato = "opentype" if ruta_ttf.lower().endswith(".otf") else "truetype"
    return f"""
<style>
  @font-face {{
    font-family: "vista-previa-fuente";
    src: url(data:font/{formato};base64,{b64}) format("{formato}");
  }}
  .vista-previa-fuente {{
    font-family: "vista-previa-fuente", sans-serif;
    font-size: {tam_px}px;
    color: {color_texto};
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    line-height: 1.3;
  }}
</style>
<div class="vista-previa-fuente">{texto_muestra}</div>
"""
