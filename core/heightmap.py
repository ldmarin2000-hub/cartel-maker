#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/heightmap.py
--------------------
Imagen rasterizada -> relieve 3D (escultura/litofanía): a diferencia de
core/imagen_import.py (que saca el CONTORNO de la imagen, una silueta
plana), esto usa el BRILLO de cada píxel para modular la ALTURA de una
grilla — cada zona clara/oscura de la foto queda más alta o más baja,
como un relieve tallado. Watertight de verdad (superficie de arriba +
piso plano + 4 paredes laterales cerrando el volumen), no una nube de
puntos ni una superficie abierta.

No hace falta ninguna librería nueva: PIL para leer/re-muestrear la
imagen, numpy para la grilla, trimesh para armar la malla — todo ya es
dependencia del proyecto.
"""

import numpy as np
import trimesh
from PIL import Image, ImageFilter
from skimage import exposure, filters

RESOLUCION_MAX_PX = 180  # lado más largo de la grilla de trabajo — más = más detalle, más lento y más pesado


def _grilla_de_alturas(ruta_imagen, resolucion_px=RESOLUCION_MAX_PX, suavizado_px=1.0, usar_clahe=True, usar_bilateral=False):
    """Lee `ruta_imagen`, la pasa a escala de grises y la re-muestrea a una
    grilla de como mucho `resolucion_px` de lado (mantiene la proporción
    real de la imagen). Optimizaciones:
    - CLAHE (contrast-limited adaptive histogram equalization) si usar_clahe=True
    - Bilateral filtering DESHABILITADO por default (muy lento); reemplazado por median filter más rápido
    Devuelve un array 2D de floats en [0, 1] — 0 = negro, 1 = blanco."""
    img = Image.open(ruta_imagen).convert("L")

    # Re-muestrear PRIMERO (imagen más chica = procesos posteriores más rápidos)
    ancho_px, alto_px = img.size
    lado_mayor = max(ancho_px, alto_px)
    escala = resolucion_px / lado_mayor
    nw, nh = max(2, round(ancho_px * escala)), max(2, round(alto_px * escala))
    img = img.resize((nw, nh), Image.LANCZOS)

    img_arr = np.asarray(img, dtype=np.float64) / 255.0

    # CLAHE: mejora contraste adaptativo sin perder detalles (rápido)
    if usar_clahe:
        img_arr = exposure.equalize_adapthist(img_arr, clip_limit=0.03, nbins=128)

    # Bilateral filter: muy lento, reemplazado por median filter (alternativa rápida)
    if usar_bilateral:
        img_arr = filters.median(filters.sobel(img_arr))

    # Gaussian blur para artefactos JPG
    if suavizado_px > 0:
        img_pil = Image.fromarray((np.clip(img_arr * 255, 0, 255)).astype(np.uint8))
        img_pil = img_pil.filter(ImageFilter.GaussianBlur(suavizado_px))
        img_arr = np.asarray(img_pil, dtype=np.float64) / 255.0

    return img_arr


def _malla_desde_grilla(alturas_norm, ancho_mm, alto_mm, espesor_base_mm, relieve_mm, oscuro_alto=True):
    """Arma una malla watertight a partir de una grilla de alturas
    normalizadas [0,1] (`alturas_norm`, fila 0 = arriba de la imagen):
    superficie de arriba con Z variable (`espesor_base_mm` +
    `relieve_mm` * altura), piso plano en Z=0, y las 4 paredes laterales
    cerrando el volumen — un bloque sólido con la foto tallada arriba,
    no una cáscara abierta. `oscuro_alto=True` -> las zonas oscuras
    quedan más altas (relieve "escultórico" típico); en falso, las
    claras quedan más altas (más parecido a una litofanía vista a
    trasluz, aunque litofanía de verdad es al revés en grosor, no en
    altura — esto es una escultura de relieve, no un difusor)."""
    nh, nw = alturas_norm.shape
    h = 1.0 - alturas_norm if oscuro_alto else alturas_norm
    z_top = espesor_base_mm + h * relieve_mm

    xs = np.linspace(0, ancho_mm, nw)
    ys = np.linspace(alto_mm, 0, nh)  # fila 0 (arriba de la imagen) -> Y más alto
    xx, yy = np.meshgrid(xs, ys)

    top = np.column_stack([xx.ravel(), yy.ravel(), z_top.ravel()])
    bottom = np.column_stack([xx.ravel(), yy.ravel(), np.zeros(nh * nw)])
    offset = nh * nw

    def idx(r, c):
        return r * nw + c

    faces = []
    for r in range(nh - 1):
        for c in range(nw - 1):
            a, b, cc, d = idx(r, c), idx(r, c + 1), idx(r + 1, c), idx(r + 1, c + 1)
            faces.append((a, b, d))
            faces.append((a, d, cc))
            faces.append((a + offset, d + offset, b + offset))
            faces.append((a + offset, cc + offset, d + offset))

    # las 4 paredes laterales — cada una conecta el borde de arriba con el de abajo
    for c in range(nw - 1):
        a, b = idx(0, c), idx(0, c + 1)
        faces.append((a, b, b + offset))
        faces.append((a, b + offset, a + offset))
        a, b = idx(nh - 1, c), idx(nh - 1, c + 1)
        faces.append((a, b, b + offset))
        faces.append((a, b + offset, a + offset))
    for r in range(nh - 1):
        a, b = idx(r, 0), idx(r + 1, 0)
        faces.append((a, b, b + offset))
        faces.append((a, b + offset, a + offset))
        a, b = idx(r, nw - 1), idx(r + 1, nw - 1)
        faces.append((a, b, b + offset))
        faces.append((a, b + offset, a + offset))

    verts = np.vstack([top, bottom])
    malla = trimesh.Trimesh(vertices=verts, faces=np.array(faces), process=True)
    # la orientación de cada cara de arriba está fijada a mano, pero la de las
    # paredes no se derivó -no hace falta: fix_normals() propaga una
    # orientación consistente hacia afuera para TODA la malla en base a la
    # conectividad, así no hay que resolver a mano el signo de cada pared.
    malla.fix_normals()
    return malla


def escultura_desde_imagen(ruta_imagen, ancho_mm=80.0, alto_mm=80.0,
                            espesor_base_mm=3.0, relieve_mm=8.0,
                            resolucion_px=RESOLUCION_MAX_PX, suavizado_px=1.0,
                            oscuro_alto=True, usar_clahe=True, usar_bilateral=True):
    """Imagen -> malla 3D de relieve/escultura, lista para exportar.
    Mejoras de calidad: CLAHE (contrast equalization) + bilateral filtering.
    `usar_clahe`: aplica adaptive histogram equalization (True por default).
    `usar_bilateral`: aplica edge-aware smoothing (True por default)."""
    alturas = _grilla_de_alturas(ruta_imagen, resolucion_px, suavizado_px, usar_clahe, usar_bilateral)
    malla = _malla_desde_grilla(alturas, ancho_mm, alto_mm, espesor_base_mm, relieve_mm, oscuro_alto)

    if not malla.is_watertight:
        trimesh.repair.fill_holes(malla)
        malla.fix_normals()

    return malla


def ajustar_caja_a_proporcion(ruta_imagen, ancho_mm):
    """Devuelve (ancho_mm, alto_mm) manteniendo la proporción real de
    `ruta_imagen` para un ancho pedido — así el relieve no sale
    estirado/aplastado. Si no se puede leer la imagen, devuelve
    (ancho_mm, ancho_mm) como respaldo (cuadrado)."""
    try:
        with Image.open(ruta_imagen) as img:
            w, h = img.size
        if w <= 0:
            return ancho_mm, ancho_mm
        return ancho_mm, ancho_mm * h / w
    except OSError:
        return ancho_mm, ancho_mm
