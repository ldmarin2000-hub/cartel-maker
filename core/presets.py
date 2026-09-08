#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/presets.py
------------------
Guardar/cargar combinaciones de parámetros por generador — para no
tener que reescribir texto+fuente+color+decoración cada vez que se
quiere repetir o retocar algo parecido a un diseño anterior. Puro, no
depende de Streamlit, así que main.py también podría usarlo algún día
si hiciera falta.

Dos formatos conviven:

- VIEJO (de antes de que los presets pudieran guardar archivos
  subidos): un .json suelto en `presets/<generador>/<nombre>.json` con
  el dict de valores tal cual, sin ningún archivo -- lo que hoy carga
  bien sigue cargando igual, ninguna key nueva rompe nada porque
  simplemente no está en ese JSON.
- NUEVO: una carpeta `presets/<generador>/<nombre>/` con `preset.json`
  (el mismo dict de siempre) MÁS una copia propia de cada archivo
  subido que estuviera en uso al guardar (marco SVG, una decoración,
  etc.) -- el preset queda autocontenido: no depende de que un archivo
  temporal en `output/` siga existiendo, y borrar la carpeta borra todo
  junto.

`guardar()` siempre escribe en formato NUEVO. `cargar()`/`listar()`/
`borrar()` entienden los dos formatos sin que quien llama necesite
saber cuál es cuál.
"""

import glob
import json
import os
import shutil

CARPETA_PRESETS = "presets"


def _nombre_archivo(nombre):
    limpio = "".join(c if c.isalnum() else "_" for c in nombre).strip("_")
    return limpio or "preset"


def _ruta_json_viejo(generador, nombre):
    """Ruta del .json suelto (formato viejo, sin carpeta ni archivos)."""
    return os.path.join(CARPETA_PRESETS, generador, f"{_nombre_archivo(nombre)}.json")


def _carpeta_preset(generador, nombre):
    """Carpeta propia del preset (formato nuevo) -- `preset.json` +
    archivos adentro. No la crea; eso lo hace `guardar()`."""
    return os.path.join(CARPETA_PRESETS, generador, _nombre_archivo(nombre))


def _ruta_json_nuevo(generador, nombre):
    return os.path.join(_carpeta_preset(generador, nombre), "preset.json")


def guardar(generador, nombre, valores, claves_archivo=()):
    """Guarda `valores` (dict serializable) como preset `nombre` del
    generador `generador`, en formato NUEVO (carpeta propia). Para
    cada key en `claves_archivo` que esté presente en `valores` con un
    path a un archivo que existe de verdad, copia ESE archivo adentro
    de la carpeta del preset (nombrado como la key + la extensión
    ORIGINAL -- importa preservarla tal cual, algunas partes de la app
    deciden qué tipo de archivo es mirando la extensión) y reescribe
    `valores[key]` con la ruta nueva antes de guardar el JSON -- así el
    preset apunta a su propia copia, no al archivo temporal de donde
    vino. Si el archivo de origen y el de destino ya son el mismo
    (re-guardar un preset sin volver a subir nada), no copia nada."""
    carpeta = _carpeta_preset(generador, nombre)
    os.makedirs(carpeta, exist_ok=True)

    valores = dict(valores)  # no mutar el dict del que llama
    for clave in claves_archivo:
        origen = valores.get(clave)
        if not origen or not os.path.exists(origen):
            continue
        _, extension = os.path.splitext(origen)
        destino = os.path.join(carpeta, f"{clave}{extension}")
        if os.path.abspath(origen) != os.path.abspath(destino):
            shutil.copyfile(origen, destino)
        valores[clave] = destino

    with open(_ruta_json_nuevo(generador, nombre), "w", encoding="utf-8") as f:
        json.dump(valores, f, ensure_ascii=False, indent=2)

    # si había un preset VIEJO (.json suelto) con el mismo nombre, lo
    # saco de encima -- que no queden dos presets iguales en formatos
    # distintos confundiendo a listar()/cargar().
    ruta_vieja = _ruta_json_viejo(generador, nombre)
    if os.path.exists(ruta_vieja):
        os.remove(ruta_vieja)


def listar(generador):
    """Nombres de los presets guardados para `generador` (de los dos
    formatos, viejo y nuevo), ordenados sin duplicados."""
    carpeta = os.path.join(CARPETA_PRESETS, generador)
    if not os.path.isdir(carpeta):
        return []

    nombres = set()
    for ruta in glob.glob(os.path.join(carpeta, "*.json")):
        nombres.add(os.path.splitext(os.path.basename(ruta))[0])
    for ruta in glob.glob(os.path.join(carpeta, "*", "preset.json")):
        nombres.add(os.path.basename(os.path.dirname(ruta)))
    return sorted(nombres)


def cargar(generador, nombre):
    """Devuelve el dict de valores del preset `nombre`, o None si no
    existe -- primero busca el formato NUEVO (carpeta con preset.json),
    si no existe cae al formato VIEJO (.json suelto, sin archivos)."""
    ruta_nueva = _ruta_json_nuevo(generador, nombre)
    if os.path.exists(ruta_nueva):
        with open(ruta_nueva, "r", encoding="utf-8") as f:
            return json.load(f)

    ruta_vieja = _ruta_json_viejo(generador, nombre)
    if os.path.exists(ruta_vieja):
        with open(ruta_vieja, "r", encoding="utf-8") as f:
            return json.load(f)

    return None


def borrar(generador, nombre):
    """Borra el preset `nombre` -- la carpeta entera si es formato
    nuevo (con sus archivos), o el .json suelto si es formato viejo."""
    carpeta = _carpeta_preset(generador, nombre)
    if os.path.isdir(carpeta):
        shutil.rmtree(carpeta)

    ruta_vieja = _ruta_json_viejo(generador, nombre)
    if os.path.exists(ruta_vieja):
        os.remove(ruta_vieja)
