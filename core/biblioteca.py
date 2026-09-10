#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/biblioteca.py
------------------
Biblioteca de escudos/SVGs reutilizables para decoraciones (Topper, y
en el futuro cualquier generador que quiera ofrecer "elegí de una
colección" en vez de subir un archivo cada vez) -- puro, sin Streamlit,
así se puede testear directo. Desde el Importador de Escudos (Parte H,
`pages/10_🛡️_Importador_Escudos.py`) ya hay UI para guardar ACÁ --
`ruta_para_nombre` es la mitad "dónde" de ese guardado (E, en
`core.importador_escudos.escribir_svg`, escribe el archivo en sí).

OJO, esta es la carpeta BUENA -- `biblioteca/escudos/` (PLURAL). Existe
también una `biblioteca/escudo/` (singular) que NO es esto: quedaron
ahí, de sesiones viejas, los SVGs OFICIALES de clubes que se usaron
como fuente para armar fixtures de test (`tests/_fixture_escudo_*`) --
el Topper nunca la lee, no se guarda nada nuevo ahí.
"""

import glob
import os
import re

CARPETA_BIBLIOTECA = os.path.join("biblioteca", "escudos")


def _nombre_lindo(nombre_archivo):
    """"union_europea.svg" -> "Union Europea" -- separa "_"/"-" en
    espacios y capitaliza cada palabra, para mostrar en el selector en
    vez del nombre de archivo crudo."""
    base = os.path.splitext(nombre_archivo)[0]
    palabras = base.replace("_", " ").replace("-", " ").split()
    return " ".join(p.capitalize() for p in palabras) or base


def listar_escudos():
    """[(nombre_lindo, ruta)] de los .svg en `biblioteca/escudos/`,
    ordenados alfabéticamente por nombre lindo -- [] si la carpeta no
    existe todavía (no hace falta crearla a mano de antemano)."""
    if not os.path.isdir(CARPETA_BIBLIOTECA):
        return []
    pares = [
        (_nombre_lindo(os.path.basename(ruta)), ruta)
        for ruta in sorted(glob.glob(os.path.join(CARPETA_BIBLIOTECA, "*.svg")))
    ]
    return sorted(pares, key=lambda par: par[0])


def ruta_para_nombre(nombre_mostrado):
    """"Club Atlético River Plate" -> "biblioteca/escudos/club_atlético_river_plate.svg"
    -- inversa APROXIMADA de `_nombre_lindo` (no es un round-trip
    perfecto para cualquier entrada: "de"/"la" quedan capitalizadas al
    volver, "CABJ" vuelve como "Cabj" -- son límites ya existentes de
    `_nombre_lindo`, no algo nuevo que agregue esto). Minúsculas,
    espacios/guiones colapsados a un solo "_", fuera los caracteres que
    no sean letra/número/espacio/guion -- pero CONSERVA acentos (son
    válidos en el nombre de archivo en cualquier filesystem que use el
    proyecto, y así el nombre listado después vuelve a coincidir con lo
    tipeado). No crea la carpeta ni escribe nada -- solo calcula la
    ruta; quien llama decide si `os.path.exists(ruta)` amerita avisar
    antes de sobreescribir."""
    base = re.sub(r"[^\w\s-]", "", nombre_mostrado.strip().lower(), flags=re.UNICODE)
    slug = re.sub(r"[\s-]+", "_", base) or "escudo"
    return os.path.join(CARPETA_BIBLIOTECA, f"{slug}.svg")
