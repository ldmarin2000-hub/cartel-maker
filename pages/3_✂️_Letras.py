#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pages/3_✂️_Letras.py
-------------------------
Página de Streamlit para el generador de letras iluminadas de pie. Es
solo la capa visual: toda la lógica real vive en generators/letras.py
(generar()), la misma que usa la versión de consola (main.py).
"""

import os

import streamlit as st

from core import fuentes
from generators import letras

st.set_page_config(page_title="Letras · Cartel Maker", page_icon="✂️", layout="wide")

st.title("✂️ Letra iluminada de pie")
st.caption(letras.DESCRIPCION)
st.info(
    "Una letra/inicial grande, hueca por dentro (cara de adelante fina para que pase la luz "
    "de un LED, atrás abierto para meterla/cambiar pilas) + una tapa aparte para cerrar el "
    "hueco después, con un agujerito para sacar el cable. Si la letra sola no se para bien "
    "(por su forma o por lo angosta que es de profundidad), activá el soporte de escritorio: "
    "sale una base aparte con una ranura donde encastra a presión."
)


@st.cache_data(ttl=600)
def _fuentes_disponibles():
    return fuentes.listar_fuentes()


col_form, col_preview = st.columns([1, 1.3])

with col_form:
    texto = st.text_input("Letra(s)", value="B", max_chars=3)

    catalogo = _fuentes_disponibles()
    OTRA_RUTA = "✏️ Otra ruta..."
    opciones = [n for n, _ in catalogo] + [OTRA_RUTA]
    idx = opciones.index("Comic Sans MS") if "Comic Sans MS" in opciones else 0
    elegida = st.selectbox(f"Fuente ({len(catalogo)} instaladas + las de fonts/)", opciones, index=idx)
    if elegida == OTRA_RUTA:
        ruta_ttf = st.text_input("Ruta a la fuente .ttf", value="fonts/Pacifico.ttf")
    else:
        ruta_ttf = dict(catalogo)[elegida]

    alto_mm = st.slider("Alto de la letra (mm)", 50, 250, 150, step=5)

    agregar_soporte = st.checkbox(
        "Agregar soporte de escritorio", value=True,
        help="Base aparte con una ranura donde encastra a presión una pata que sale de la "
             "letra — para las letras que no se paran solas.",
    )

    agregar_tapa = st.checkbox(
        "Agregar tapa (con agujero para el cable)", value=True,
        help="Mismo contorno que la letra, sólida y fina, para cerrar el hueco después de "
             "meter el LED — con un agujerito cerca del borde inferior para sacar el cable.",
    )

    with st.expander("Ajustes finos"):
        profundidad_mm = st.slider("Profundidad (mm, ahí adentro va la luz)", 15, 60, 35, step=5)
        espesor_pared_mm = st.slider(
            "Espesor de pared (mm)", 1.5, 5.0, 2.5, step=0.25,
            help="Más fino deja pasar más luz pero es más frágil. Si un trazo de la letra es "
                 "más angosto que 2x este valor, esa parte queda maciza (avisamos).",
        )
        c1, c2 = st.columns(2)
        tapa_espesor_mm = c1.slider("Espesor de la tapa (mm)", 1.5, 6.0, 3.0, step=0.5, disabled=not agregar_tapa)
        agujero_cable_diam_mm = c2.slider(
            "Diámetro del agujero del cable (mm)", 0.0, 12.0, 6.0, step=0.5, disabled=not agregar_tapa,
            help="0 = sin agujero.",
        )
        c1, c2 = st.columns(2)
        ancho_pata_mm = c1.slider("Ancho de la pata (mm)", 15, 80, 40, step=5, disabled=not agregar_soporte)
        alto_pata_mm = c2.slider("Alto de la pata (mm)", 5, 30, 15, step=1, disabled=not agregar_soporte)

    generar_click = st.button("Generar letra", type="primary", use_container_width=True)

with col_preview:
    if not generar_click:
        st.info("Completá el formulario y apretá **Generar letra**.")
    elif not texto.strip():
        st.error("Escribí al menos una letra.")
    else:
        with st.spinner("Armando la geometría 3D (letra hueca + booleanas)..."):
            try:
                r = letras.generar(
                    texto, ruta_ttf, alto_mm=float(alto_mm), profundidad_mm=float(profundidad_mm),
                    espesor_pared_mm=float(espesor_pared_mm),
                    agregar_tapa=agregar_tapa, tapa_espesor_mm=float(tapa_espesor_mm),
                    agujero_cable_diam_mm=float(agujero_cable_diam_mm),
                    agregar_soporte=agregar_soporte, ancho_pata_mm=ancho_pata_mm, alto_pata_mm=alto_pata_mm,
                )
            except (FileNotFoundError, ValueError) as e:
                st.error(str(e))
                r = None

        if r:
            st.image(r["ruta_png"], use_column_width=True)

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
                    "⬇ Descargar STL (letra)", f, file_name=os.path.basename(r["ruta_stl"]),
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

            if r["pieza_soporte"]:
                s = r["pieza_soporte"]
                if not s["watertight"]:
                    st.caption("Base de escritorio: no quedó perfectamente watertight, revisala antes de imprimir.")
                with open(s["ruta_stl"], "rb") as f:
                    st.download_button(
                        "⬇ Descargar STL (base de escritorio)", f, file_name=os.path.basename(s["ruta_stl"]),
                        mime="model/stl", use_container_width=True,
                    )
