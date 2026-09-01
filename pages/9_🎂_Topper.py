#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pages/9_🎂_Topper.py
---------------------
Generador unificado de toppers para tortas, cupcakes, y decoraciones.
Integración 3D completa con STL export y preview interactivo.
"""

import os
import streamlit as st
import streamlit.components.v1 as components

from core import colores, preview3d
from generators import topper
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

    texto = st.text_input("Texto/Diseño", "Topper", key="tp_texto",
                         help="Texto o nombre a grabar/mostrar en el topper")

    tamaño_mm = st.slider("Tamaño (mm)", 20, 200, 80, step=5, key="tp_tamaño_mm",
                         help="Altura aproximada del topper (mayor = más visible)")

    estilo = st.selectbox("Estilo", ["Minimalista", "Elegante", "Divertido", "Romántico"], key="tp_estilo")

    # Parámetros específicos por tipo
    material_3d = "PLA"
    color_3d = "Blanco"
    base_tipo = "Sólida"
    tipo_led = "Flexible (frío)"
    grosor_tubo = 10
    material_led = "PLA"
    efecto = "Fijo"
    baterias = True
    espesor_acrilico = 3
    acabado = "Transparente"

    if "3D" in tipo_topper:
        st.subheader("Parámetros 3D")
        material_3d = st.selectbox("Material", ["PLA", "PETG", "ABS", "Resin"], key="tp_material")
        base_tipo = st.radio("Tipo de base", ["Sólida", "Hueca", "Magnética"], horizontal=True, key="tp_base")

    elif "Neón" in tipo_topper:
        st.subheader("Parámetros Neón")
        tipo_led = st.radio("Tipo", ["Flexible (frío)", "Rígido (cálido)", "RGB"], horizontal=True, key="tp_neon_tipo")
        grosor_tubo = st.slider("Diámetro tubo (mm)", 5, 15, 10, step=1, key="tp_neon_grosor")

    elif "LED" in tipo_topper:
        st.subheader("Parámetros LED")
        material_led = st.selectbox("Material estructura", ["PLA", "Acrílico", "Madera"], key="tp_led_material")
        efecto = st.selectbox("Efecto", ["Fijo", "Parpadeo", "Secuencial", "Arcoíris"], key="tp_led_efecto")
        baterias = st.checkbox("Incluir compartimiento para batería", key="tp_led_bat")

    elif "Acrílico" in tipo_topper:
        st.subheader("Parámetros Acrílico")
        espesor_acrilico = st.slider("Espesor (mm)", 2, 8, 3, step=1, key="tp_acrilico_espesor")
        acabado = st.selectbox("Acabado", ["Espejo", "Transparente", "Mate", "Color"], key="tp_acrilico_acabado")

    generar_click = st.button("Generar topper", type="primary", use_container_width=True)

with col_preview:
    if generar_click:
        if not texto.strip():
            st.error("Ingresá un texto/diseño")
        else:
            with st.spinner("Generando topper..."):
                try:
                    if "3D" in tipo_topper:
                        resultado = topper.generar_3d(
                            texto=texto,
                            tamaño_mm=tamaño_mm,
                            estilo=estilo,
                            color=color_3d,
                            base=base_tipo,
                            material=material_3d
                        )

                        # Preview 3D si existe archivo STL
                        if "ruta_stl" in resultado and os.path.exists(resultado["ruta_stl"]):
                            html_preview = preview3d.armar_html_visor([{"ruta_stl": resultado["ruta_stl"], "color": "#f4f4f2"}], height_px=500)
                            if html_preview:
                                components.html(html_preview, height=500, scrolling=False)

                        # Info y descarga
                        st.markdown(f"""
                        ### ✓ Topper 3D generado
                        - **Material:** {resultado['material']}
                        - **Tamaño:** {resultado['tamaño_mm']}mm
                        - **Estilo:** {resultado['estilo']}
                        - **Vértices:** {resultado['vertices']} | **Caras:** {resultado['caras']}
                        - **Watertight:** {"✓ Sí" if resultado['watertight'] else "✗ No"}
                        """)

                        if "ruta_stl" in resultado:
                            with open(resultado["ruta_stl"], "rb") as f:
                                st.download_button(
                                    "📥 Descargar STL",
                                    f.read(),
                                    file_name=os.path.basename(resultado["ruta_stl"]),
                                    mime="application/octet-stream"
                                )

                    elif "Neón" in tipo_topper:
                        resultado = topper.generar_neon(
                            texto=texto,
                            tamaño_mm=tamaño_mm,
                            tipo_led=tipo_led
                        )
                        st.info(f"🔄 {resultado['estado']}")
                        st.json(resultado)

                    elif "LED" in tipo_topper:
                        resultado = topper.generar_led(
                            texto=texto,
                            tamaño_mm=tamaño_mm,
                            efecto=efecto,
                            con_bateria=baterias
                        )
                        st.info(f"🔄 {resultado['estado']}")
                        st.json(resultado)

                    elif "Acrílico" in tipo_topper:
                        resultado = topper.generar_acrilico(
                            texto=texto,
                            tamaño_mm=tamaño_mm,
                            espesor_mm=espesor_acrilico,
                            acabado=acabado
                        )
                        st.info(f"🔄 {resultado['estado']}")
                        st.json(resultado)

                except Exception as e:
                    st.error(f"Error: {str(e)}")

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
