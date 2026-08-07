#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/presets.py
------------------
Guardar/cargar combinaciones de parámetros por generador — para no
tener que reescribir texto+fuente+color+decoración cada vez que se
quiere repetir o retocar algo parecido a un diseño anterior. Un preset
es un .json chico en `presets/<generador>/<nombre>.json` con los
valores de los widgets que importan (los `key=` de Streamlit) — puro,
no depende de Streamlit, así que main.py también podría usarlo algún
día si hiciera falta.
"""

import glob
import json
import os

CARPETA_PRESETS = "presets"


def _nombre_archivo(nombre):
    limpio = "".join(c if c.isalnum() else "_" for c in nombre).strip("_")
    return limpio or "preset"


def _ruta(generador, nombre):
    carpeta = os.path.join(CARPETA_PRESETS, generador)
    os.makedirs(carpeta, exist_ok=True)
    return os.path.join(carpeta, f"{_nombre_archivo(nombre)}.json")


def guardar(generador, nombre, valores):
    """Guarda `valores` (dict serializable) como preset `nombre` del
    generador `generador`."""
    with open(_ruta(generador, nombre), "w", encoding="utf-8") as f:
        json.dump(valores, f, ensure_ascii=False, indent=2)


def listar(generador):
    """Nombres de los presets guardados para `generador`, ordenados."""
    carpeta = os.path.join(CARPETA_PRESETS, generador)
    if not os.path.isdir(carpeta):
        return []
    return sorted(os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(carpeta, "*.json")))


def cargar(generador, nombre):
    """Devuelve el dict de valores del preset `nombre`, o None si no existe."""
    ruta = _ruta(generador, nombre)
    if not os.path.exists(ruta):
        return None
    with open(ruta, "r", encoding="utf-8") as f:
        return json.load(f)


def borrar(generador, nombre):
    ruta = _ruta(generador, nombre)
    if os.path.exists(ruta):
        os.remove(ruta)
