#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pages/8_📦_Nombre_LED.py
----------------------------
Página de Streamlit para el generador de Nombre LED (palabra hueca). Es
solo la capa visual: toda la lógica real vive en generators/caja_luz.py
(generar()), la misma que usa la versión de consola (main.py).
"""

import os

import streamlit as st
import streamlit.components.v1 as components

from core import colores, preview3d
from generators import caja_luz
from ui_streamlit import bloque_presets, selector_fuente

st.set_page_config(page_title="Nombre LED · Cartel Maker", page_icon="📦", layout="wide")

st.title("📦 Nombre LED (palabra hueca)")
st.caption(caja_luz.DESCRIPCION)
st.info(
    "Escribí una palabra: sale como UNA pieza hueca, con la cara de adelante fina para que la "
    "luz del LED se difunda pareja, más una tapa aparte para cerrar el hueco después de meter la "
    "tira LED, con un agujerito para sacar el cable. Si hay letras sueltas (como la 'I'), se "
    "sueldan solas con puentes finos."
)

PRESET_KEYS = [
    "cl_texto", "cajaluz_selectbox", "cajaluz_ruta", "cl_color", "cl_color_tapa", "cl_alto_mm",
    "cl_profundidad_mm", "cl_espesor_pared_mm", "cl_agregar_tapa",
    "cl_tapa_espesor_mm", "cl_agujero_cable_diam_mm", "cl_agujero_cable_lado",
    "cl_agujero_manual", "cl_agujero_x_pct", "cl_agujero_y_pct",
]

LADOS_AGUJERO = ["atras", "arriba", "abajo", "izquierda", "derecha"]


@st.cache_data(ttl=120, show_spinner=False)
def _preview_rapido(texto, ruta_ttf, alto_mm, mostrar_agujero, espesor_pared_mm, agujero_cable_diam_mm,
                     agujero_atras_x_pct, agujero_atras_y_pct):
    return caja_luz.preview_rapido(
        texto, ruta_ttf, alto_mm, mostrar_agujero=mostrar_agujero, espesor_pared_mm=espesor_pared_mm,
        agujero_cable_diam_mm=agujero_cable_diam_mm,
        agujero_atras_x_pct=agujero_atras_x_pct, agujero_atras_y_pct=agujero_atras_y_pct,
    )


col_form, col_preview = st.columns([1, 1.3])

with col_form:
    bloque_presets("caja_luz", PRESET_KEYS)

    texto = st.text_input("Palabra", value="HOLA", key="cl_texto")
    ruta_ttf = selector_fuente("Fuente", key="cajaluz", default_nombre="Bungee", texto_muestra=texto)

    c1, c2 = st.columns(2)
    color_pieza = c1.selectbox(
        "Color base (visor)", colores.NOMBRES,
        index=colores.NOMBRES.index("Blanco"), key="cl_color",
        help="Solo para ver cómo queda en el visor 3D — el color real lo da el filamento que uses.",
    )
    color_tapa = c2.selectbox(
        "Color tapa (visor)", colores.NOMBRES,
        index=colores.NOMBRES.index("Gris Frío"), key="cl_color_tapa",
        help="Un color distinto al de la base ayuda a distinguirlas en el visor 3D.",
    )

    alto_mm = st.slider("Alto de la palabra (mm)", 30, 300, 100, step=5, key="cl_alto_mm")

    agregar_tapa = st.checkbox(
        "Agregar tapa (con agujero para el cable)", value=True, key="cl_agregar_tapa",
    )

    with st.expander("Ajustes finos"):
        profundidad_mm = st.number_input(
            "Profundidad de la caja (mm)", value=30.0, step=1.0, key="cl_profundidad_mm",
            help="Cuánto sobresale hacia atrás — ahí adentro va la tira LED.",
        )
        espesor_pared_mm = st.number_input(
            "Grosor de las paredes (mm)", value=2.5, step=0.25, key="cl_espesor_pared_mm",
            help="Grosor de la cara de adelante y de los bordes de cada letra. Más fino deja "
                 "pasar más luz pero es más frágil; trazos muy angostos para este grosor quedan "
                 "macizos (sin hueco) en vez de romperse.",
        )
        c1, c2 = st.columns(2)
        tapa_espesor_mm = c1.slider(
            "Espesor de la tapa (mm)", 1.5, 6.0, 3.0, step=0.5, disabled=not agregar_tapa, key="cl_tapa_espesor_mm",
        )
        agujero_cable_diam_mm = c2.slider(
            "Diámetro del agujero del cable (mm)", 0.0, 12.0, 4.5, step=0.5, disabled=not agregar_tapa,
            key="cl_agujero_cable_diam_mm", help="0 = sin agujero.",
        )
        agujero_cable_lado = st.radio(
            "Lado del agujero del cable", LADOS_AGUJERO, horizontal=True,
            disabled=not agregar_tapa or agujero_cable_diam_mm <= 0, key="cl_agujero_cable_lado",
            help="\"atras\": por el canto de atrás (el rebaje donde apoya la tapa). Los otros 4: "
                 "por la pared lateral de ese lado. Va siempre en la carcasa, no en la tapa.",
        )
        agujero_deshabilitado = not agregar_tapa or agujero_cable_diam_mm <= 0 or agujero_cable_lado != "atras"
        agujero_manual = st.checkbox(
            "Elegir a mano dónde va el agujero \"atras\"", value=False,
            disabled=agujero_deshabilitado, key="cl_agujero_manual",
            help="Si no, se busca un lugar automático cerca del borde de abajo. La marca celeste "
                 "en la vista rápida (a la derecha) muestra dónde va a caer.",
        )
        c1, c2 = st.columns(2)
        agujero_x_pct = c1.slider(
            "Posición X (%)", 0, 100, 50, disabled=agujero_deshabilitado or not agujero_manual,
            key="cl_agujero_x_pct",
        )
        agujero_y_pct = c2.slider(
            "Posición Y (%)", 0, 100, 5, disabled=agujero_deshabilitado or not agujero_manual,
            key="cl_agujero_y_pct",
        )

    generar_click = st.button("Generar Nombre LED", type="primary", use_container_width=True)

with col_preview:
    if texto.strip() and ruta_ttf:
        mostrar_agujero_preview = agregar_tapa and agujero_cable_diam_mm > 0 and agujero_cable_lado == "atras"
        png_rapido, ancho_rapido, alto_rapido = _preview_rapido(
            texto, ruta_ttf, float(alto_mm), mostrar_agujero_preview, float(espesor_pared_mm),
            float(agujero_cable_diam_mm),
            float(agujero_x_pct) if agujero_manual else None, float(agujero_y_pct) if agujero_manual else None,
        )
        if png_rapido:
            st.image(
                png_rapido,
                caption=f"Vista rápida (2D) — ~{ancho_rapido:.0f} x {alto_rapido:.0f} mm. "
                        f"Al generar sale la malla 3D hueca real (con tapa/agujero si hay).",
                use_container_width=True,
            )
            st.divider()

    if not generar_click:
        st.info("Completá el formulario y apretá **Generar Nombre LED**.")
    elif not texto.strip():
        st.error("Escribí alguna palabra primero.")
    else:
        with st.spinner("Armando la geometría hueca (puede tardar unos segundos)..."):
            try:
                r = caja_luz.generar(
                    texto=texto, ruta_ttf=ruta_ttf, alto_mm=float(alto_mm),
                    profundidad_mm=float(profundidad_mm), espesor_pared_mm=float(espesor_pared_mm),
                    agregar_tapa=agregar_tapa, tapa_espesor_mm=float(tapa_espesor_mm),
                    agujero_cable_diam_mm=float(agujero_cable_diam_mm), agujero_cable_lado=agujero_cable_lado,
                    agujero_atras_x_pct=float(agujero_x_pct) if agujero_manual else None,
                    agujero_atras_y_pct=float(agujero_y_pct) if agujero_manual else None,
                )
            except (FileNotFoundError, ValueError) as e:
                st.error(str(e))
                r = None

        if r:
            # la carcasa ocupa Z=[0, profundidad_mm]; la tapa se exporta en su propio
            # origen (Z=[0, tapa_espesor_mm]) para imprimirse suelta — la corremos a
            # Z=profundidad_mm para el visor, que es donde va pegada de verdad (cierra
            # el hueco abierto de atrás).
            color_hex = colores.hex_de(color_pieza)
            piezas_visor = [{"ruta_stl": r["ruta_stl"], "color": color_hex, "nombre": "cajaluz"}]
            if r["pieza_tapa"]:
                piezas_visor.append({
                    "ruta_stl": r["pieza_tapa"]["ruta_stl"], "color": colores.hex_de(color_tapa), "nombre": "tapa",
                    "offset": (0, 0, float(profundidad_mm)),
                })

            html_visor = preview3d.armar_html_visor(piezas_visor)
            if html_visor:
                components.html(html_visor, height=460)
                st.caption("Arrastrá para rotar, scroll para zoom. Palabra + tapa (si hay), en su posición real.")
            else:
                st.image(r["ruta_png"], use_container_width=True)

            c1, c2, c3 = st.columns(3)
            c1.metric("Ancho", f"{r['ancho_mm']:.0f} mm")
            c2.metric("Alto", f"{r['alto_mm']:.0f} mm")
            c3.metric("Profundidad", f"{r['profundidad_mm']:.0f} mm")

            for nota in r["info"]:
                st.info(nota)
            for aviso in r["avisos"]:
                st.warning(aviso)

            if r["entra_a1"]:
                st.success(r["mensaje_a1"])
            else:
                st.warning(r["mensaje_a1"])

            if not r["watertight"]:
                st.caption("No quedó perfectamente watertight, revisala antes de imprimir.")

            with open(r["ruta_stl"], "rb") as f:
                st.download_button(
                    "⬇ Descargar STL (palabra)", f, file_name=os.path.basename(r["ruta_stl"]),
                    mime="model/stl", use_container_width=True, type="primary",
                )

            if r["pieza_tapa"]:
                t = r["pieza_tapa"]
                if not t["watertight"]:
                    st.caption("Tapa: no quedó perfectamente watertight, revisala antes de imprimir.")
                with open(t["ruta_stl"], "rb") as f:
                    st.download_button(
                        "⬇ Descargar STL (tapa)", f, file_name=os.path.basename(t["ruta_stl"]),
                        mime="model/stl", use_container_width=True,
                    )
