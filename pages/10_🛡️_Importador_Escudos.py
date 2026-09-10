#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pages/10_🛡️_Importador_Escudos.py
---------------------
Página de Streamlit para el Importador de Escudos -- Partes F+G+H: subir
un escudo (SVG o PNG), ver el preview de las zonas excluyentes que
detecta el motor, asignarle un color/filamento (o "calado", sin
filamento) a cada hueco interno detectado, y guardar el resultado en
`biblioteca/escudos/` (core/biblioteca.py) para elegirlo después desde
el Topper con un clic. Toda la lógica real vive en
`core/importador_escudos.py`/`core/biblioteca.py` (Partes A-E y el
guardado ya probados con tests permanentes) -- esta página solo llama,
arma la UI y vuelve a pintar el preview, no analiza ni escribe nada por
su cuenta que no sea orquestar esas dos llamadas.
"""

import os

import streamlit as st

from core import biblioteca, colores, importador_escudos

OPCION_CALADO = "🕳️ Calado (sin filamento)"
OPCIONES_COLOR_HUECO = [OPCION_CALADO] + list(colores.NOMBRES)
_INDICE_DEFAULT_BLANCO = OPCIONES_COLOR_HUECO.index("Blanco")


def _color_de_opcion(opcion):
    """Nombre de la paleta curada -> hex, o `None` si es el sentinel de
    calado -- `armar_zonas_finales`/`componer_preview_rgb` (Parte
    E/preview) ya saben tratar `None` como "sin filamento"."""
    return None if opcion == OPCION_CALADO else colores.hex_de(opcion)


st.set_page_config(page_title="Importador de Escudos · Cartel Maker", page_icon="🛡️", layout="wide")

st.title("🛡️ Importador de Escudos")
st.caption(
    "Subí un escudo (SVG o PNG) una sola vez, prepáralo acá, y después elegilo desde la "
    "biblioteca en el Topper con un clic -- sin tener que subirlo cada vez."
)

archivo = st.file_uploader("Escudo", type=["svg", "png"])

if archivo is not None:
    os.makedirs("output", exist_ok=True)
    ruta = os.path.join("output", f"_importador_{archivo.name}")
    with open(ruta, "wb") as f:
        f.write(archivo.getvalue())

    try:
        ancho, alto, capas = importador_escudos.cargar_escudo(ruta)
        zonas = importador_escudos.separar_zonas_excluyentes(capas)
        huecos = importador_escudos.detectar_huecos_internos(zonas)
    except Exception as e:
        st.error(f"No se pudo procesar el archivo: {e}")
    else:
        if not zonas:
            st.warning("No se detectó ninguna zona con color en este archivo.")
        else:
            colores_huecos = None

            if huecos:
                st.markdown(f"**Huecos internos detectados: {len(huecos)}**")
                opcion_global = st.selectbox(
                    "Color para todos los huecos", OPCIONES_COLOR_HUECO,
                    index=_INDICE_DEFAULT_BLANCO, key="tp_importador_hueco_color_global",
                )
                colores_huecos = [_color_de_opcion(opcion_global)] * len(huecos)

                por_separado = st.checkbox(
                    "Asignar cada hueco por separado", key="tp_importador_huecos_por_separado",
                    help="Para el caso raro en que no todos los huecos van al mismo color.",
                )
                if por_separado:
                    colores_huecos = []
                    for i, hueco in enumerate(huecos):
                        opcion_i = st.selectbox(
                            f"Hueco #{i + 1} ({int(hueco.sum())}px)", OPCIONES_COLOR_HUECO,
                            index=_INDICE_DEFAULT_BLANCO, key=f"tp_importador_hueco_color_{i}",
                        )
                        colores_huecos.append(_color_de_opcion(opcion_i))

            preview = importador_escudos.componer_preview_rgb(zonas, ancho, alto, huecos, colores_huecos)
            st.image(preview, caption=f"{len(zonas)} zona(s) detectada(s)")

            if huecos:
                n_calados = sum(1 for c in colores_huecos if c is None)
                if n_calados == len(huecos):
                    st.info(f"🕳️ Los {len(huecos)} hueco(s) van como calado (sin filamento).")
                elif n_calados == 0:
                    st.success(f"Los {len(huecos)} hueco(s) tienen un color/filamento asignado.")
                else:
                    st.info(f"{n_calados} de {len(huecos)} hueco(s) van como calado, el resto con filamento.")
            else:
                st.success("No se detectaron huecos internos -- este escudo ya trae su fondo como color propio.")

            st.divider()
            st.markdown("**Guardar en la biblioteca**")
            nombre_escudo = st.text_input(
                "Nombre para guardar en la biblioteca", key="tp_importador_nombre_biblioteca",
                placeholder="Ej: River Plate",
            )
            nombre_limpio = nombre_escudo.strip()
            ruta_biblioteca = biblioteca.ruta_para_nombre(nombre_limpio) if nombre_limpio else None
            ya_existe = ruta_biblioteca is not None and os.path.exists(ruta_biblioteca)
            if ya_existe:
                st.warning(f"Ya existe un escudo **{nombre_limpio}** en la biblioteca -- guardar lo sobrescribe.")

            if st.button("💾 Sobrescribir en biblioteca" if ya_existe else "💾 Guardar en biblioteca"):
                if not nombre_limpio:
                    st.error("Ponele un nombre al escudo antes de guardar.")
                else:
                    zonas_finales = importador_escudos.armar_zonas_finales(
                        zonas, huecos, colores_por_hueco=colores_huecos)
                    os.makedirs(biblioteca.CARPETA_BIBLIOTECA, exist_ok=True)
                    importador_escudos.escribir_svg(zonas_finales, ancho, alto, ruta_biblioteca)
                    st.success(f"Guardado como **{nombre_limpio}** -- ya disponible en el Topper.")
