#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/raster.py
---------------
Paso 1 del pipeline de neón: texto + fuente .ttf -> máscara binaria (numpy).
"""

import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def rasterizar(texto, ruta_ttf, resolucion_px, pad=24):
    """Dibuja el texto con la fuente dada y devuelve una máscara booleana
    (True = tinta) con un margen `pad` de píxeles alrededor."""
    if not os.path.exists(ruta_ttf):
        raise FileNotFoundError(f"no encuentro la fuente: {ruta_ttf}")
    font = ImageFont.truetype(ruta_ttf, resolucion_px)
    b = ImageDraw.Draw(Image.new("L", (4, 4))).textbbox((0, 0), texto, font=font)
    w, h = b[2] - b[0] + 2 * pad, b[3] - b[1] + 2 * pad
    img = Image.new("L", (w, h), 0)
    ImageDraw.Draw(img).text((pad - b[0], pad - b[1]), texto, fill=255, font=font)
    return np.array(img) > 128


def rasterizar_con_espaciado(texto, ruta_ttf, resolucion_px, espaciado_relativo=0.0, pad=24):
    """Como rasterizar(), pero dibuja letra por letra con un espaciado
    ajustable entre caracteres: `espaciado_relativo` es una fracción de
    `resolucion_px` que se SUMA al avance natural de cada letra — negativo
    las acerca (hasta tocarse/superponerse), positivo las separa más."""
    if not os.path.exists(ruta_ttf):
        raise FileNotFoundError(f"no encuentro la fuente: {ruta_ttf}")
    if not texto:
        raise ValueError("no hay texto para rasterizar")

    font = ImageFont.truetype(ruta_ttf, resolucion_px)
    espaciado_px = espaciado_relativo * resolucion_px

    anchos = [font.getlength(c) for c in texto]
    b_completo = ImageDraw.Draw(Image.new("L", (4, 4))).textbbox((0, 0), texto, font=font)
    alto = b_completo[3] - b_completo[1]
    ancho_total = sum(anchos) + espaciado_px * (len(texto) - 1)

    w = max(int(ancho_total) + 2 * pad, 1)
    h = max(int(alto) + 2 * pad, 1)
    img = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(img)

    x = float(pad)
    y = pad - b_completo[1]
    for c, ancho_c in zip(texto, anchos):
        draw.text((x, y), c, fill=255, font=font)
        x += ancho_c + espaciado_px
    return np.array(img) > 128
