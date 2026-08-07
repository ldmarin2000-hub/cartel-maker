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


def imagen_a_poligono_crudo(ruta_imagen, umbral=128, invertir=False):
    """Vectoriza `ruta_imagen` (cualquier formato que abra PIL — PNG,
    JPG, etc) a un polígono shapely SIN escalar (unidades de píxel) —
    usa el canal alfa como máscara si la imagen tiene transparencia (PNG
    recortado, lo más común para un logo), si no umbraliza por
    luminosidad (oscuro = forma, sobre fondo claro; `invertir=True` para
    el caso contrario, forma clara sobre fondo oscuro). Devuelve None si
    no se pudo sacar ninguna forma con área."""
    mascara = _mascara_desde_imagen(ruta_imagen, umbral, invertir)
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
