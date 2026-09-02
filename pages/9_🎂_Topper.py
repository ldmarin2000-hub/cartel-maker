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
    st.subheader("📊 Especificaciones")

    # Mostrar specs por tipo
    if "3D" in tipo_topper:
        col_spec1, col_spec2 = st.columns(2)
        with col_spec1:
            st.metric("Tamaño estimado", f"{tamaño_mm}mm")
            st.metric("Material", material_3d)
        with col_spec2:
            st.metric("Estilo", estilo)
            st.metric("Base", base_tipo)
        st.caption("⚙️ Tiempo: 2-5 min | Costo material: bajo")

    elif "Neón" in tipo_topper:
        col_spec1, col_spec2 = st.columns(2)
        with col_spec1:
            st.metric("Tipo LED", tipo_led.split("(")[0].strip())
            st.metric("Diámetro", f"{grosor_tubo}mm")
        with col_spec2:
            st.metric("Voltaje", "24V")
            st.metric("Consumo est.", "0.1W")
        st.caption("⚙️ Tiempo: 1-2h instalación | Costo: medio")

    elif "LED" in tipo_topper:
        col_spec1, col_spec2 = st.columns(2)
        with col_spec1:
            st.metric("Efecto", efecto)
            st.metric("Material", material_led)
        with col_spec2:
            st.metric("Voltaje", "5V USB" if baterias else "12V")
            st.metric("Consumo", {"Fijo": "5W", "Parpadeo": "4.5W", "Secuencial": "5.5W", "Arcoíris": "6W"}.get(efecto, "5W"))
        st.caption("⚙️ Tiempo: 3-4h montaje | Costo: alto")

    elif "Acrílico" in tipo_topper:
        col_spec1, col_spec2 = st.columns(2)
        with col_spec1:
            st.metric("Espesor", f"{espesor_acrilico}mm")
            st.metric("Acabado", acabado)
        with col_spec2:
            st.metric("Potencia láser", f"{espesor_acrilico * 20 * {'Espejo': 0.8, 'Transparente': 1.0, 'Mate': 1.2, 'Color': 0.9}.get(acabado, 1.0):.0f}W")
            st.metric("Tiempo corte", f"{(tamaño_mm * 2 + 40) / 5:.1f}s")
        st.caption("⚙️ Tiempo: 10-20 min | Costo: muy bajo")

    st.divider()

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
                            tipo_led=tipo_led,
                            grosor_tubo=grosor_tubo
                        )

                        st.markdown(f"""
                        ### ✓ Topper Neón generado
                        - **Tipo LED:** {resultado['tipo_led']}
                        - **Largo tubo:** {resultado['largo_tubo_mm']}mm
                        - **Grosor:** {resultado['grosor_tubo']}mm
                        - **Voltaje:** {resultado['voltaje']}
                        - **Consumo:** {resultado['consumo_w']}W
                        """)

                        if "ruta_dxf" in resultado and os.path.exists(resultado["ruta_dxf"]):
                            with open(resultado["ruta_dxf"], "rb") as f:
                                st.download_button(
                                    "📥 Descargar DXF",
                                    f.read(),
                                    file_name=os.path.basename(resultado["ruta_dxf"]),
                                    mime="application/dxf"
                                )

                    elif "LED" in tipo_topper:
                        resultado = topper.generar_led(
                            texto=texto,
                            tamaño_mm=tamaño_mm,
                            material=material_led,
                            efecto=efecto,
                            con_bateria=baterias
                        )

                        # Preview 3D
                        if "ruta_stl" in resultado and os.path.exists(resultado["ruta_stl"]):
                            html_preview = preview3d.armar_html_visor([{"ruta_stl": resultado["ruta_stl"], "color": "#ff6b35"}], height_px=500)
                            if html_preview:
                                components.html(html_preview, height=500, scrolling=False)

                        st.markdown(f"""
                        ### ✓ Topper LED generado
                        - **Material:** {resultado['material']}
                        - **Efecto:** {resultado['efecto']}
                        - **Tamaño:** {resultado['tamaño_mm']}mm
                        - **Voltaje:** {resultado['voltaje']}
                        - **Consumo:** {resultado['consumo_w']}W
                        - **Vértices:** {resultado['vertices']} | **Caras:** {resultado['caras']}
                        """)

                        if "ruta_stl" in resultado:
                            with open(resultado["ruta_stl"], "rb") as f:
                                st.download_button(
                                    "📥 Descargar STL",
                                    f.read(),
                                    file_name=os.path.basename(resultado["ruta_stl"]),
                                    mime="application/octet-stream"
                                )

                    elif "Acrílico" in tipo_topper:
                        resultado = topper.generar_acrilico(
                            texto=texto,
                            tamaño_mm=tamaño_mm,
                            espesor_mm=espesor_acrilico,
                            acabado=acabado
                        )

                        st.markdown(f"""
                        ### ✓ Topper Acrílico generado
                        - **Acabado:** {resultado['acabado']}
                        - **Espesor:** {resultado['espesor_mm']}mm
                        - **Dimensiones:** {resultado['ancho']}×{resultado['alto']}mm
                        - **Potencia láser:** {resultado['potencia_w']}W
                        - **Tiempo corte:** {resultado['tiempo_corte_s']}s
                        """)

                        if "ruta_dxf" in resultado and os.path.exists(resultado["ruta_dxf"]):
                            with open(resultado["ruta_dxf"], "rb") as f:
                                st.download_button(
                                    "📥 Descargar DXF",
                                    f.read(),
                                    file_name=os.path.basename(resultado["ruta_dxf"]),
                                    mime="application/dxf"
                                )

                except Exception as e:
                    st.error(f"Error: {str(e)}")

st.divider()

# Comparativa
with st.expander("📊 Comparativa de toppers"):
    comp_data = {
        "Tipo": ["3D", "Neón", "LED", "Acrílico"],
        "Tiempo": ["2-5 min", "1-2h", "3-4h", "10-20 min"],
        "Costo": ["Bajo", "Medio", "Alto", "Muy bajo"],
        "Durabilidad": ["Excelente", "Buena", "Excelente", "Media"],
        "Interactividad": ["—", "Luz", "Luz+Efecto", "—"],
        "Reutilizable": ["Sí", "Sí", "Sí", "No"],
    }
    st.dataframe(comp_data, use_container_width=True)

# Guía de selección
with st.expander("🎯 Guía de selección"):
    st.markdown("""
    **Elige 3D si:**
    - Quieres un topper clásico impreso
    - Presupuesto limitado
    - Personajes/logos complejos

    **Elige Neón si:**
    - Buscas efecto luminoso básico
    - Evento nocturno
    - Presupuesto medio

    **Elige LED si:**
    - Quieres efecto luminoso avanzado (parpadeo, secuencias)
    - Evento especial premium
    - Baterías integradas

    **Elige Acrílico si:**
    - Presupuesto muy ajustado
    - Grabado simple
    - No es reutilizable (ok)
    """)

# Info detallada
with st.expander("ℹ️ Información técnica"):
    st.markdown("""
    ### Toppers 3D
    - **Material:** PLA, PETG, ABS, Resina
    - **Resolución:** 0.2mm capa
    - **Tiempo impresión:** 2-5 min (80mm)
    - **Bases:** Sólida (estable), Hueca (ahorro), Magnética (reutilizable)

    ### Toppers Neón
    - **Tipo LED:** Flexible (24V frío), Rígido (12V cálido), RGB (multicolor)
    - **Consumo:** 0.05-0.2W
    - **Vida útil:** 50,000h
    - **Formato:** DXF para máquina dobladora

    ### Toppers LED
    - **Estructura:** PLA, Acrílico, Madera
    - **Efectos:** Fijo, Parpadeo (2Hz), Secuencial, Arcoíris
    - **Alimentación:** USB 5V (batería integrada)
    - **Consumo:** 4.5-6W según efecto

    ### Toppers Acrílico
    - **Material:** Acrílico 2-8mm
    - **Acabados:** Espejo, Transparente, Mate, Color
    - **Método:** Grabado láser (CO₂)
    - **Potencia:** 20-96W según espesor
    - **Nota:** No reutilizable, costo muy bajo
    """)

# Compatibilidad
with st.expander("🔗 Integración con otras herramientas"):
    st.markdown("""
    | Herramienta | 3D | Neón | LED | Acrílico |
    |---|:---:|:---:|:---:|:---:|
    | Silhueta | ✓ | — | — | — |
    | Esculturas | ✓ | — | ✓ | — |
    | Llavero | ✓ | — | — | ✓ |
    | Letras | ✓ | ✓ | ✓ | ✓ |
    | Neón SVG | — | ✓ | — | — |
    | Nombre LED | — | — | ✓ | — |

    **Exporta formatos:**
    - 3D → STL (impresoras 3D, Cura/PrusaSlicer)
    - Neón → DXF (máquinas dobladoras LED)
    - LED → STL + especificaciones
    - Acrílico → DXF (cortadoras láser, Lightburn)
    """)
