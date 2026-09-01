#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pages/9_🎂_Topper.py
---------------------
Generador unificado de toppers para tortas, cupcakes, y decoraciones.
Soporta: 3D, Neón, LED, Acrílico grabado.
"""

import os
import streamlit as st
import streamlit.components.v1 as components

from core import colores, preview3d
from generators import esculturas
from ui_streamlit import bloque_presets

st.set_page_config(page_title="Topper · Cartel Maker", page_icon="🎂", layout="wide")

st.title("🎂 Topper (decoración para tortas y más)")
st.caption("Crea toppers para tortas, cupcakes, postres. Impresión 3D, Neón, LED, Acrílico.")

TIPOS_TOPPER = [
    "Topper 3D (escultura pequeña)",
    "Topper Neón (texto/símbolo LED flexible)",
    "Topper LED (iluminado con efectos)",
    "Topper Acrílico (grabado láser)",
]

PRESET_KEYS = [
    "tp_tipo", "tp_texto", "tp_tamaño_mm", "tp_estilo", "tp_material", "tp_color"
]

tipo_topper = st.radio("Tipo de topper", TIPOS_TOPPER, horizontal=True, key="tp_tipo")

col_form, col_preview = st.columns([1, 1.3])

with col_form:
    bloque_presets("topper", PRESET_KEYS)

    # Parámetros comunes
    texto = st.text_input("Texto/Diseño", "Topper", key="tp_texto",
                         help="Texto o nombre a grabar/mostrar en el topper")

    tamaño_mm = st.slider("Tamaño (mm)", 20, 200, 80, step=5, key="tp_tamaño_mm",
                         help="Altura aproximada del topper (mayor = más visible)")

    estilo = st.selectbox("Estilo", ["Minimalista", "Elegante", "Divertido", "Romántico"], key="tp_estilo")

    # Parámetros específicos por tipo
    if "3D" in tipo_topper:
        st.subheader("Parámetros 3D")
        material_3d = st.selectbox("Material", ["PLA", "PETG", "ABS", "Resin"], key="tp_material")
        color_3d = st.selectbox("Color", colores.NOMBRES, index=0, key="tp_color")
        base_tipo = st.radio("Tipo de base", ["Sólida", "Hueca", "Magnética"], horizontal=True)

    elif "Neón" in tipo_topper:
        st.subheader("Parámetros Neón")
        tipo_led = st.radio("Tipo", ["Flexible (frío)", "Rígido (cálido)", "RGB"], horizontal=True)
        grosor_tubo = st.slider("Diámetro tubo (mm)", 5, 15, 10, step=1)

    elif "LED" in tipo_topper:
        st.subheader("Parámetros LED")
        material_led = st.selectbox("Material estructura", ["PLA", "Acrílico", "Madera"])
        efecto = st.selectbox("Efecto", ["Fijo", "Parpadeo", "Secuencial", "Arcoíris"])
        baterias = st.checkbox("Incluir compartimiento para batería")

    elif "Acrílico" in tipo_topper:
        st.subheader("Parámetros Acrílico")
        espesor_acrilico = st.slider("Espesor (mm)", 2, 8, 3, step=1)
        acabado = st.selectbox("Acabado", ["Espejo", "Transparente", "Mate", "Color"])

    generar_click = st.button("Generar topper", type="primary", use_container_width=True)

with col_preview:
    if generar_click:
        if not texto.strip():
            st.error("Ingresá un texto/diseño")
        else:
            with st.spinner("Generando topper..."):
                # Placeholder: integración con generadores existentes
                if "3D" in tipo_topper:
                    st.info(f"🔄 Generando topper 3D: '{texto}' ({tamaño_mm}mm, {estilo})")
                elif "Neón" in tipo_topper:
                    st.info(f"🔄 Generando topper Neón: '{texto}' ({tamaño_mm}mm)")
                elif "LED" in tipo_topper:
                    st.info(f"🔄 Generando topper LED: '{texto}' (efecto: {efecto})")
                elif "Acrílico" in tipo_topper:
                    st.info(f"🔄 Generando topper Acrílico: '{texto}' ({espesor_acrilico}mm)")

                st.success("✓ Topper generado (próximamente: descarga STL/archivos)")

# Info
st.divider()
with st.expander("ℹ️ Información sobre toppers"):
    st.markdown("""
    **Toppers 3D:** Figuras pequeñas sólidas, imprimibles. Base firma.

    **Toppers Neón:** LED flexible en tubo, bajo voltaje, efectos de color.

    **Toppers LED:** Estructura + luces integradas, baterías, efectos secuenciales.

    **Toppers Acrílico:** Grabado láser, espejos, colores satinados.

    **Caso de uso:** Decoración de tortas, cupcakes, postres, eventos.
    """)
