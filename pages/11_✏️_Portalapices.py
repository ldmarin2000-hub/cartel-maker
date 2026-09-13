#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pages/11_✏️_Portalapices.py
-----------------------------
Generador paramétrico de recipientes cilíndricos huecos (portalápices,
vasos, maceteros) — geometría de precisión, no reconstrucción de IA desde
foto. Paredes rectas reales, hueco real, patrón decorativo tallado tipo
knurling (rombos/panal/rayado/puntos) en una franja de altura ajustable.
"""

import os
import streamlit as st
import streamlit.components.v1 as components

from core import colores, preview3d
from generators import portalapices
from ui_streamlit import bloque_presets

st.set_page_config(page_title="Portalápices · Cartel Maker", page_icon="✏️", layout="wide")

st.title("✏️ Portalápices / Vasos / Maceteros")
st.caption(
    "Recipiente cilíndrico hueco con paredes rectas reales, generado por geometría de precisión "
    "(no por IA a partir de una foto) — para eso está el modo Relieve/Estatua de Esculturas."
)

PRESET_KEYS = [
    "pl_texto", "pl_diametro", "pl_altura", "pl_espesor", "pl_espesor_base",
    "pl_forma", "pl_patron", "pl_franja_ini", "pl_franja_fin",
    "pl_densidad", "pl_profundidad", "pl_color",
]

col_form, col_preview = st.columns([1, 1.3])

with col_form:
    bloque_presets("portalapices", PRESET_KEYS)

    texto = st.text_input(
        "Nombre (opcional, solo para el archivo)", "",
        key="pl_texto",
        help="No se graba en la pieza — es solo para nombrar el STL descargado."
    )

    col_a, col_b = st.columns(2)
    with col_a:
        diametro_mm = st.slider("Diámetro externo (mm)", 40, 200, 80, step=5, key="pl_diametro")
        espesor_mm = st.slider("Espesor de pared (mm)", 1.2, 8.0, 2.4, step=0.2, key="pl_espesor")
    with col_b:
        altura_mm = st.slider("Altura (mm)", 30, 250, 90, step=5, key="pl_altura")
        espesor_base_mm = st.slider("Espesor de base (mm)", 1.5, 10.0, 3.0, step=0.5, key="pl_espesor_base")

    forma = st.selectbox("Forma", portalapices.FORMAS, key="pl_forma")
    color = st.selectbox("Color", list(colores.NOMBRES), index=1, key="pl_color")

    st.subheader("Patrón decorativo")
    patron = st.selectbox("Patrón", portalapices.PATRONES, key="pl_patron")

    if patron != "Liso":
        col_c, col_d = st.columns(2)
        with col_c:
            franja_ini = st.slider("Franja decorada — inicio (%)", 0, 100, 50, step=5, key="pl_franja_ini")
        with col_d:
            franja_fin = st.slider("Franja decorada — fin (%)", 0, 100, 100, step=5, key="pl_franja_fin")
        if franja_ini >= franja_fin:
            st.error("El inicio de la franja debe ser menor que el fin")
        col_e, col_f = st.columns(2)
        with col_e:
            densidad_patron = st.slider("Densidad (repeticiones)", 2, 12, 5, key="pl_densidad")
        with col_f:
            profundidad_patron = st.slider("Profundidad del relieve (mm)", 0.2, 2.5, 0.9, step=0.1, key="pl_profundidad")
    else:
        franja_ini, franja_fin = 0, 100
        densidad_patron, profundidad_patron = 5, 0.9

    generar_click = st.button("Generar portalápices", type="primary", use_container_width=True)

with col_preview:
    st.subheader("📊 Especificaciones")
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        st.metric("Diámetro", f"{diametro_mm}mm")
        st.metric("Espesor pared", f"{espesor_mm}mm")
    with col_s2:
        st.metric("Altura", f"{altura_mm}mm")
        st.metric("Forma", forma.split(" ")[0])
    st.caption(f"⚙️ Patrón: {patron}" + (f" ({franja_ini}%-{franja_fin}%)" if patron != "Liso" else ""))

    st.divider()

    if generar_click:
        if patron != "Liso" and franja_ini >= franja_fin:
            st.error("Corregí la franja del patrón antes de generar")
        else:
            with st.spinner("Generando portalápices..."):
                try:
                    resultado = portalapices.generar(
                        texto=texto,
                        diametro_mm=diametro_mm,
                        altura_mm=altura_mm,
                        espesor_mm=espesor_mm,
                        espesor_base_mm=espesor_base_mm,
                        forma=forma,
                        patron=patron,
                        franja_patron=(franja_ini, franja_fin),
                        densidad_patron=densidad_patron,
                        profundidad_patron=profundidad_patron,
                    )

                    if "ruta_stl" in resultado and os.path.exists(resultado["ruta_stl"]):
                        html_visor = preview3d.armar_html_visor(
                            [{"ruta_stl": resultado["ruta_stl"], "color": dict(colores.PALETA).get(color, "#333333")}],
                            height_px=500
                        )
                        if html_visor:
                            components.html(html_visor, height=500, scrolling=False)

                    st.markdown(f"""
                    ### ✓ Portalápices generado
                    - **Diámetro:** {resultado['diametro_mm']}mm · **Altura:** {resultado['altura_mm']}mm
                    - **Espesor pared:** {resultado['espesor_mm']}mm
                    - **Forma:** {resultado['forma']} · **Patrón:** {resultado['patron']}
                    - **Vértices:** {resultado['vertices']} | **Caras:** {resultado['caras']}
                    - **Watertight:** {"✓ Sí" if resultado['watertight'] else "✗ No"}
                    - **Volumen material:** {resultado['volumen_cm3']} cm³
                    """)

                    if "ruta_stl" in resultado:
                        with open(resultado["ruta_stl"], "rb") as f:
                            st.download_button(
                                "📥 Descargar STL",
                                f.read(),
                                file_name=os.path.basename(resultado["ruta_stl"]),
                                mime="application/octet-stream"
                            )

                except Exception as e:
                    st.error(f"Error: {str(e)}")

st.divider()

with st.expander("ℹ️ ¿Por qué esto y no 'Esculturas' con una foto?"):
    st.markdown("""
    **Esculturas → Relieve:** convierte el brillo de una foto en altura sobre una placa PLANA
    (bajorrelieve). Sirve para retratos/logos grabados, no reconstruye la forma 3D del objeto
    fotografiado — nunca te va a dar un cilindro hueco a partir de la foto de un portalápices.

    **Esculturas → Estatua 3D (IA):** intenta una reconstrucción volumétrica real con IA generativa,
    pero el resultado es aproximado/orgánico — no geometría de precisión con paredes rectas.

    **Portalápices (esta herramienta):** genera el cilindro hueco por matemática exacta —
    diámetro, altura y espesor de pared reales, patrón decorativo tallado de verdad en la
    superficie. Es la opción correcta cuando necesitás un recipiente funcional imprimible.
    """)
