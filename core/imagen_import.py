#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/imagen_import.py
------------------------
Imagen rasterizada (PNG/JPG, un logo/ícono cualquiera) -> polígono
shapely relleno, con el mismo enfoque que core/texto2d.py para texto y
core/svg_import.py para SVG: se vectoriza por contorno (marching
squares vía scikit-image, huecos con core/poligonos.py). No hace falta
ninguna librería nueva — reusa PIL + numpy + scikit-image, que el
proyecto ya usa para el texto.

Pensado para logos/íconos simples (silueta clara sobre fondo liso o
transparente, sin fotos ni degradados) — no es un rastreador general de
fotografías; una foto real da un contorno enorme y probablemente
inservible para imprimir.
"""

import numpy as np
from PIL import Image
from shapely.geometry import Polygon
from skimage import measure

from core.poligonos import combinar_con_huecos

TAMANO_TRABAJO_PX = 500  # se reescala a esto (lado mayor) antes de vectorizar
AREA_MINIMA_PX = 4  # contornos más chicos que esto se descartan como ruido (antialiasing, JPG)


def _mascara_desde_imagen(ruta_imagen, umbral, invertir):
    img = Image.open(ruta_imagen)

    ancho, alto = img.size
    escala = TAMANO_TRABAJO_PX / max(ancho, alto)
    if escala < 1:
        img = img.resize((max(1, int(ancho * escala)), max(1, int(alto * escala))), Image.LANCZOS)

    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        img = img.convert("RGBA")
        alfa = np.array(img)[:, :, 3]
        mascara = alfa > 16  # cualquier pixel no-transparente cuenta como "tinta"
    else:
        gris = np.array(img.convert("L"))
        mascara = gris < umbral  # oscuro = tinta, sobre fondo claro (el caso típico de un logo)

    if invertir:
        mascara = ~mascara
    return mascara


def _mascara_a_poligono(mascara):
    """Vectoriza una máscara booleana (marching squares) a un polígono
    shapely con huecos -- el paso compartido entre
    `imagen_a_poligono_crudo` (una máscara) e
    `imagen_a_poligonos_por_color` (una máscara por color detectado)."""
    contornos = measure.find_contours(mascara.astype(float), level=0.5)
    alto_px = mascara.shape[0]

    polys = []
    for c in contornos:
        if len(c) < 4:
            continue
        pts = [(col, alto_px - row) for row, col in c]  # flip Y: fila 0 = arriba
        p = Polygon(pts)
        if not p.is_valid:
            p = p.buffer(0)
        if p.is_empty or p.area < AREA_MINIMA_PX:
            continue
        polys.append(p)

    return combinar_con_huecos(polys)


def imagen_a_poligono_crudo(ruta_imagen, umbral=128, invertir=False):
    """Vectoriza `ruta_imagen` (cualquier formato que abra PIL — PNG,
    JPG, etc) a un polígono shapely SIN escalar (unidades de píxel) —
    usa el canal alfa como máscara si la imagen tiene transparencia (PNG
    recortado, lo más común para un logo), si no umbraliza por
    luminosidad (oscuro = forma, sobre fondo claro; `invertir=True` para
    el caso contrario, forma clara sobre fondo oscuro). Devuelve None si
    no se pudo sacar ninguna forma con área."""
    mascara = _mascara_desde_imagen(ruta_imagen, umbral, invertir)
    return _mascara_a_poligono(mascara)


def imagen_a_poligonos_por_color(ruta_imagen, max_colores=4):
    """Separa `ruta_imagen` en hasta `max_colores` regiones por color
    real (cuantización, PIL Image.quantize) en vez de una silueta de un
    solo color -- pensado para un logo/escudo con varios colores bien
    definidos (rojo/blanco/etc), no para una foto. Usa el canal alfa
    para ignorar el fondo transparente si la imagen lo tiene; si no,
    cuantiza la imagen completa (el fondo sólido puede salir como uno
    de los colores detectados -- normal, el que llama puede optar por
    no usar ese color). Sin escalar (unidades de píxel), en el MISMO
    sistema de coordenadas entre sí (a diferencia de vectorizar cada
    color por separado con `imagen_a_poligono_crudo`, que perdería la
    posición relativa entre colores).

    Devuelve una lista de (polígono, "#rrggbb") ordenada de mayor a
    menor área, o lista vacía si no se pudo sacar nada."""
    img = Image.open(ruta_imagen)
    ancho, alto = img.size
    escala = TAMANO_TRABAJO_PX / max(ancho, alto)
    if escala < 1:
        img = img.resize((max(1, int(ancho * escala)), max(1, int(alto * escala))), Image.LANCZOS)

    tiene_alfa = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
    img_rgba = img.convert("RGBA")
    alfa = np.array(img_rgba)[:, :, 3]
    mascara_valida = alfa > 16 if tiene_alfa else np.ones(alfa.shape, dtype=bool)

    cuantizada = img_rgba.convert("RGB").quantize(colors=max_colores, method=Image.Quantize.MEDIANCUT)
    paleta = cuantizada.getpalette()
    indices = np.array(cuantizada)

    candidatos = []
    for idx in sorted(set(indices[mascara_valida].tolist())):
        mascara_color = (indices == idx) & mascara_valida
        area_px = int(mascara_color.sum())
        if area_px < AREA_MINIMA_PX:
            continue
        poligono = _mascara_a_poligono(mascara_color)
        if poligono is None or poligono.is_empty:
            continue
        r, g, b = paleta[idx * 3], paleta[idx * 3 + 1], paleta[idx * 3 + 2]
        candidatos.append((area_px, poligono, f"#{r:02x}{g:02x}{b:02x}"))

    candidatos.sort(key=lambda t: t[0], reverse=True)
    return [(poligono, color_hex) for _, poligono, color_hex in candidatos]
