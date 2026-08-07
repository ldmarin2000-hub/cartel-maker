#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ui_streamlit.py
------------------
Widgets de Streamlit compartidos entre páginas (capa visual — a
diferencia de core/, que es puro y lo usan tanto la app como main.py,
esto SOLO lo usa la app visual). Vive en la raíz, no en pages/, porque
Streamlit trata cada .py suelto adentro de pages/ como una página
nueva del menú — un helper ahí adentro rompería el menú.

Por ahora: el selector de fuente agrupado por categoría (curadas
primero) con preview en vivo, que se repetía igual en las 4 páginas
(neón, llavero, letras -dos veces-, ambigrama -dos veces-).
"""

import streamlit as st
import streamlit.components.v1 as components

from core import fuentes

OTRA_RUTA = "✏️ Otra ruta..."


@st.cache_data(ttl=600)
def _catalogo_agrupado():
    return fuentes.listar_fuentes_agrupadas()


def _etiqueta(nombre, categoria, emoji):
    if categoria in ("Sistema", "Tus fuentes"):
        return f"{emoji} {nombre}"
    return f"{emoji} {categoria} — {nombre}"


def selector_fuente(label, key, default_nombre="Comic Sans MS", texto_muestra=None, mostrar_preview=True):
    """Selector de fuente agrupado (Script/Manuscrita/Display/Redondeada
    curadas primero, después las del usuario en `fonts/`, después las
    de Windows) + preview en vivo tipeado de verdad en la fuente
    elegida (no una imagen genérica) — usa `texto_muestra` si viene
    (ej. el texto que el usuario ya escribió) o un ejemplo genérico si
    no. `key` tiene que ser único por selector (una página puede tener
    más de uno, ej. letras.py: fuente de la letra + fuente del nombre).
    Devuelve la ruta al .ttf/.otf elegido."""
    catalogo = _catalogo_agrupado()
    opciones = {_etiqueta(nombre, cat, emoji): ruta for nombre, ruta, cat, emoji in catalogo}
    etiquetas = list(opciones.keys()) + [OTRA_RUTA]

    idx = 0
    for i, (nombre, _, _, _) in enumerate(catalogo):
        if nombre == default_nombre:
            idx = i
            break

    elegida = st.selectbox(label, etiquetas, index=idx, key=f"{key}_selectbox")
    if elegida == OTRA_RUTA:
        ruta_ttf = st.text_input("Ruta a la fuente .ttf", value="fonts/Pacifico.ttf", key=f"{key}_ruta")
    else:
        ruta_ttf = opciones[elegida]

    if mostrar_preview:
        muestra = (texto_muestra or "").strip() or "Cartel Maker Aa 123"
        html_preview = fuentes.html_preview_fuente(ruta_ttf, texto_muestra=muestra)
        if html_preview:
            components.html(html_preview, height=60)

    return ruta_ttf
