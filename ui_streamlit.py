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

- `selector_fuente`: selector de fuente agrupado por categoría (curadas
  primero) con preview en vivo, que se repetía igual en las 4 páginas
  (neón, llavero, letras -dos veces-, ambigrama -dos veces-).
- `bloque_presets`: cargar/guardar/borrar combinaciones de parámetros
  guardadas (core/presets.py) — funciona pisando `st.session_state` de
  los widgets del formulario, así que esos widgets necesitan `key=`
  explícito (los mismos `key` que se le pasan a `bloque_presets`).
- `resolver_archivo_subido`/`resolver_biblioteca`: el patrón de "subí un
  archivo O elegí de la biblioteca de escudos" -- vivían privadas
  adentro de `pages/9_🎂_Topper.py` (única página que los necesitaba
  hasta ahora); se extraen acá al hacer falta en una segunda página
  (Llavero) para el ícono "a color" -- el Topper las sigue usando
  igual, ahora importadas en vez de definidas dos veces.
"""

import os

import streamlit as st
import streamlit.components.v1 as components

from core import biblioteca, fuentes, presets

OTRA_RUTA = "✏️ Otra ruta..."
_OPCION_BIBLIOTECA_NINGUNO = "— Ninguno —"


def resolver_archivo_subido(subido, key_uploader, prefijo_output):
    """Guarda `subido` (un UploadedFile de un file_uploader con key
    `key_uploader`) en output/ y actualiza la key "sombra"
    `<key_uploader>__ruta` en session_state -- esa key sombra (no el
    uploader en sí, que Streamlit no permite rellenar programáticamente)
    es la que se guarda/restaura en los presets. Subir un archivo nuevo
    siempre reemplaza lo que hubiera ahí, incluido lo que viniera de un
    preset recién cargado.

    Devuelve la ruta a usar: la del archivo recién subido si hay uno;
    si no, la que haya quedado en la key sombra (de un preset cargado,
    o de una subida anterior en esta misma sesión); None si no hay
    nada. Si esa ruta ya no existe en disco (se borró/movió), la
    ignora en vez de romper más adelante al intentar abrirla."""
    key_ruta = f"{key_uploader}__ruta"
    if subido is not None:
        os.makedirs("output", exist_ok=True)
        ruta = os.path.join("output", f"{prefijo_output}_{subido.name}")
        with open(ruta, "wb") as f:
            f.write(subido.getvalue())
        st.session_state[key_ruta] = ruta

    ruta = st.session_state.get(key_ruta)
    if ruta and not os.path.exists(ruta):
        ruta = None
    return ruta


def resolver_biblioteca(key_biblioteca, label="O elegí de la biblioteca"):
    """Selector de la biblioteca de escudos (core/biblioteca.py) --
    devuelve la ruta elegida, o None si está en "— Ninguno —". Regla de
    convivencia con "subir archivo" (la aplica quien llama): mientras
    este selector no esté en "— Ninguno —", esa ruta gana sobre lo
    subido -- para volver a un archivo propio hay que poner el selector
    de vuelta en "— Ninguno —". Nunca toca el session_state de OTRO
    widget (evita el StreamlitAPIException de tocar uno ya instanciado
    en esta corrida) -- si un preset restaurado apunta a un escudo que
    ya no está en la carpeta, cae a "Ninguno" ANTES de instanciar este
    MISMO widget, en vez de romper el selectbox con un valor fuera de
    sus propias opciones."""
    escudos = biblioteca.listar_escudos()
    opciones = [_OPCION_BIBLIOTECA_NINGUNO] + [nombre for nombre, _ in escudos]
    if st.session_state.get(key_biblioteca) not in opciones:
        st.session_state[key_biblioteca] = opciones[0]
    elegido = st.selectbox(label, opciones, key=key_biblioteca)
    if elegido == _OPCION_BIBLIOTECA_NINGUNO:
        return None
    return dict(escudos).get(elegido)


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

    # El índice se busca entre las etiquetas que SE MUESTRAN, no por posición en el catálogo: si hay
    # una fuente repetida (mismo nombre en dos carpetas), `opciones` la colapsa y los índices del
    # catálogo quedarían corridos -- el selector arrancaría en la fuente de al lado.
    idx = 0
    for nombre, _, categoria, emoji in catalogo:
        if nombre == default_nombre:
            idx = etiquetas.index(_etiqueta(nombre, categoria, emoji))
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


def bloque_presets(generador, keys, claves_archivo=()):
    """Cargar/guardar/borrar combinaciones de parámetros guardadas para
    `generador` (ej. "llavero") — un preset guarda el valor actual de
    cada `key` en `keys` (los mismos `key=` que le diste a los widgets
    del formulario) y, al cargarlo, los pisa en `st.session_state` y
    fuerza un `st.rerun()` para que el próximo render de esos widgets
    ya salga con esos valores. Funciona en cualquier lugar de la
    página (no hace falta que esté antes de los widgets — el rerun se
    encarga de eso).

    `claves_archivo`: subconjunto de `keys` cuyo VALOR es un path a un
    archivo en disco (no un archivo subido en sí -- eso Streamlit no
    lo permite guardar/restaurar, ver la key "sombra" `<key>__ruta` que
    arma cada página) -- `core.presets.guardar` copia esos archivos
    adentro de la carpeta propia del preset en vez de guardar solo la
    ruta, para que el preset quede autocontenido."""
    with st.expander("💾 Presets guardados"):
        existentes = presets.listar(generador)

        c1, c2 = st.columns([2, 1])
        elegido = c1.selectbox(
            "Cargar preset", ["—"] + existentes, key=f"{generador}_preset_elegido",
        )
        if c2.button(
            "Cargar", key=f"{generador}_preset_cargar",
            disabled=(elegido == "—"), use_container_width=True,
        ):
            valores = presets.cargar(generador, elegido)
            if valores:
                for k, v in valores.items():
                    if k in keys:
                        st.session_state[k] = v
                st.rerun()

        c3, c4 = st.columns([2, 1])
        nombre_nuevo = c3.text_input(
            "Guardar como", key=f"{generador}_preset_nombre", placeholder="ej: Cumple de Bianca",
        )
        if c4.button(
            "Guardar", key=f"{generador}_preset_guardar",
            disabled=not nombre_nuevo.strip(), use_container_width=True,
        ):
            valores = {k: st.session_state[k] for k in keys if k in st.session_state}
            presets.guardar(generador, nombre_nuevo.strip(), valores, claves_archivo=claves_archivo)
            st.success(f"Preset '{nombre_nuevo}' guardado.")
            st.rerun()

        if existentes and elegido != "—":
            if st.button(f"🗑️ Borrar '{elegido}'", key=f"{generador}_preset_borrar"):
                presets.borrar(generador, elegido)
                st.rerun()
