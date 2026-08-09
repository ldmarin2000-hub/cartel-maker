#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/storage.py
---------------
Gestión de almacenamiento: compresión de archivos, cleanup de temporales,
cache de modelos descargados, monitoreo de espacio en disco.
"""

import os
import glob
import time
from pathlib import Path


def limpiar_temporales(carpeta="output", dias_antiguedad=7):
    """Borrar archivos subidos/temporales más viejos que N días.
    Deja STL y PNG generados. Solo limpia _subido_*.
    Devuelve cantidad de archivos borrados."""
    edad_min_seg = dias_antiguedad * 86400
    ahora = time.time()
    borrados = 0

    patron = os.path.join(carpeta, "_subido_*")
    for ruta in glob.glob(patron):
        try:
            edad = ahora - os.path.getmtime(ruta)
            if edad > edad_min_seg:
                os.remove(ruta)
                borrados += 1
        except OSError:
            pass

    return borrados


def comprimir_png(ruta_png, nivel=9):
    """Comprimir PNG a máximo nivel sin perder calidad (lossless).
    Reduce tamaño típicamente 20-40% (preview es lo que consume espacio)."""
    try:
        from PIL import Image
        img = Image.open(ruta_png)
        img.save(ruta_png, "PNG", optimize=True)
    except Exception:
        pass


def verificar_espacio_disco(ruta="C:\\", min_gb=5.0):
    """Chequear si hay al menos N GB libres. Devuelve (tiene_espacio, gb_libres)."""
    try:
        import shutil
        stat = shutil.disk_usage(ruta)
        gb_libres = stat.free / (1024**3)
        return gb_libres >= min_gb, gb_libres
    except Exception:
        return True, float('inf')


def cache_dir_modelos():
    """Directorio cache para modelos Shap-E descargados.
    Por default Hugging Face usa ~/.cache/huggingface/hub.
    Retorna path, crea si no existe."""
    cache = os.path.expanduser("~/.cache/huggingface/hub")
    os.makedirs(cache, exist_ok=True)
    return cache


def tamaño_cache_modelos():
    """Tamaño total en GB de modelos Shap-E descargados."""
    cache = cache_dir_modelos()
    total_bytes = 0
    try:
        for root, dirs, files in os.walk(cache):
            for f in files:
                total_bytes += os.path.getsize(os.path.join(root, f))
    except OSError:
        pass
    return total_bytes / (1024**3)


def estadisticas_almacenamiento(carpeta_salida="output"):
    """Devuelve dict con stats: stl_count, png_count, tamaño_total_mb, cache_modelos_gb."""
    stats = {
        "stl_count": 0,
        "png_count": 0,
        "tamaño_total_mb": 0,
        "cache_modelos_gb": tamaño_cache_modelos(),
    }

    try:
        for ruta in glob.glob(os.path.join(carpeta_salida, "*.stl")):
            stats["stl_count"] += 1
            stats["tamaño_total_mb"] += os.path.getsize(ruta) / (1024**2)
        for ruta in glob.glob(os.path.join(carpeta_salida, "*_preview.png")):
            stats["png_count"] += 1
            stats["tamaño_total_mb"] += os.path.getsize(ruta) / (1024**2)
    except OSError:
        pass

    return stats
