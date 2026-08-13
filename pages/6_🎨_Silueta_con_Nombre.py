#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pages/6_🎨_Silueta_con_Nombre.py
----------------------------------
Página de Streamlit para el generador "Silueta con Nombre".
Subís un SVG o una imagen (silueta de corazón, estrella, osito, etc.),
escribís un texto, y el generador lo recorta, funde o talla sobre la
silueta. Solo la capa visual: la lógica real vive en
generators/silueta_nombre.py.
"""

import os

import streamlit as st
import streamlit.components.v1 as components

from core import colores, preview3d
from generators import silueta_nombre
from ui_streamlit import bloque_presets, selector_fuente

st.set_page_config(page_title="Silueta con Nombre · Cartel Maker", page_icon="🎨", layout="wide")

st.title("🎨 Silueta con Nombre")
st.caption(silueta_nombre.DESCRIPCION)

MODOS_LABELS = {
    "Intersección — el texto queda recortado por la silueta": "interseccion",
    "Unión — la silueta y el texto se funden en una sola pieza": "union",
    "Diferencia — la silueta queda con el texto huecado (sello)": "diferencia",
}

PRESET_KEYS = [
    "sn_texto", "sn_fuente_selectbox", "sn_fuente_ruta",
    "sn_modo", "sn_alto_silueta", "sn_escala_texto",
    "sn_offset_x", "sn_offset_y", "sn_borde", "sn_aro_lado",
    "sn_aro_r", "sn_espesor", "sn_color_silueta", "sn_color_texto",
    "sn_color_resultado",
]


@st.cache_data(ttl=120, show_spinner=False)
def _preview_rapido(ruta_silueta, texto, ruta_ttf, alto_silueta, modo,
                    escala_texto, offset_x, offset_y, borde, aro_lado, aro_r,
                    color_silueta, color_texto, color_resultado):
    return silueta_nombre.preview_rapido(
        ruta_silueta, texto, ruta_ttf,
        alto_silueta_mm=float(alto_silueta), modo=modo,
        escala_texto_pct=float(escala_texto),
        offset_x_mm=float(offset_x), offset_y_mm=float(offset_y),
        borde_mm=float(borde), aro_lado=aro_lado, aro_r=float(aro_r),
        color_silueta=color_silueta, color_texto=color_texto, color_resultado=color_resultado,
    )


col_form, col_preview = st.columns([1, 1.3])

with col_form:
    bloque_presets("silueta_nombre", PRESET_KEYS)

    silueta_subida = st.file_uploader(
        "Silueta (SVG, PNG o JPG)", type=["svg", "png", "jpg", "jpeg"],
        help="Una silueta clara: corazón, estrella, animal, etc. Si es imagen, mejor que tenga "
             "contraste fuerte (fondo claro, forma oscura) o transparencia (PNG). No entra en el preset.",
    )
    ruta_silueta = None
    if silueta_subida is not None:
        os.makedirs("output", exist_ok=True)
        ruta_silueta = os.path.join("output", f"_subido_{silueta_subida.name}")
        with open(ruta_silueta, "wb") as f:
            f.write(silueta_subida.getvalue())

    texto = st.text_input("Texto", value="Monica", key="sn_texto")

    ruta_ttf = selector_fuente("Fuente", key="sn_fuente", default_nombre="Lobster", texto_muestra=texto)

    modo_label = st.radio(
        "Modo", list(MODOS_LABELS.keys()), key="sn_modo",
        help="Intersección = el texto solo se ve donde toca la silueta. "
             "Unión = la silueta y el texto se funden. "
             "Diferencia = la silueta queda con el texto como hueco.",
    )
    modo = MODOS_LABELS[modo_label]

    alto_silueta = st.slider("Alto de la silueta (mm)", 20, 150, 55, key="sn_alto_silueta")

    c1, c2 = st.columns(2)
    color_silueta = c1.selectbox(
        "Color silueta (visor)", colores.NOMBRES, index=colores.NOMBRES.index("Gris"), key="sn_color_silueta",
    )
    color_texto = c2.selectbox(
        "Color texto (visor)", colores.NOMBRES, index=colores.NOMBRES.index("Rosa Fluor"), key="sn_color_texto",
    )
    color_resultado = st.selectbox(
        "Color resultado (visor)", colores.NOMBRES, index=colores.NOMBRES.index("Blanco"), key="sn_color_resultado",
    )

    escala_texto = st.slider(
        "Escala del texto (% del alto de la silueta)", 20, 150, 100, key="sn_escala_texto",
    )

    aro_lado = st.radio(
        "Aro de llavero", silueta_nombre.LADOS_ARO, horizontal=True, key="sn_aro_lado",
    )

    with st.expander("Ajustes finos"):
        cx, cy = st.columns(2)
        offset_x = cx.slider("Offset horizontal del texto", -50, 50, 0, key="sn_offset_x")
        offset_y = cy.slider("Offset vertical del texto", -50, 50, 0, key="sn_offset_y")
        borde = st.slider("Borde alrededor (mm, 0 = sin borde)", 0.0, 10.0, 0.0, step=0.5, key="sn_borde")
        aro_r = st.slider("Radio del agujero del aro (mm)", 1.0, 5.0, 2.0, step=0.25, key="sn_aro_r")
        espesor = st.slider("Espesor de la pieza (mm)", 1.0, 10.0, 4.0, step=0.5, key="sn_espesor")

    generar_click = st.button("Generar pieza", type="primary", use_container_width=True)

with col_preview:
    if ruta_silueta and texto.strip():
        png_rapido, ancho_rapido, alto_rapido = _preview_rapido(
            ruta_silueta, texto, ruta_ttf, float(alto_silueta), modo,
            float(escala_texto), float(offset_x), float(offset_y),
            float(borde), aro_lado, float(aro_r),
            color_silueta, color_texto, color_resultado,
        )
        if png_rapido:
            st.image(
                png_rapido,
                caption=f"Vista rápida (2D) — ~{ancho_rapido:.0f} x {alto_rapido:.0f} mm. "
                        f"Al generar sale la malla 3D real (con volumen, para imprimir).",
                use_container_width=True,
            )
            st.divider()
        else:
            st.warning("No se pudo generar la vista rápida — probá otra fuente o revisá la silueta.")

    r = None
    if not generar_click:
        st.info("Subí una silueta, escribí un texto y apretá **Generar pieza**.")
    elif not ruta_silueta:
        st.error("Subí una silueta primero (SVG, PNG o JPG).")
    elif not texto.strip():
        st.error("Escribí un texto primero.")
    else:
        with st.spinner("Generando la geometría y la malla 3D..."):
            try:
                r = silueta_nombre.generar(
                    ruta_silueta=ruta_silueta, texto=texto, ruta_ttf=ruta_ttf,
                    alto_silueta_mm=float(alto_silueta), modo=modo,
                    escala_texto_pct=float(escala_texto),
                    offset_x_mm=float(offset_x), offset_y_mm=float(offset_y),
                    borde_mm=float(borde), aro_lado=aro_lado, aro_r=float(aro_r),
                    espesor_mm=float(espesor),
                    color_silueta=color_silueta, color_texto=color_texto, color_resultado=color_resultado,
                )
            except (FileNotFoundError, ValueError) as e:
                st.error(str(e))
                r = None

    if r:
        color_hex = colores.hex_de(color_resultado)
        html_visor = preview3d.armar_html_visor([
            {"ruta_stl": r["ruta_stl"], "color": color_hex, "nombre": "silueta"},
        ])
        if html_visor:
            components.html(html_visor, height=460)
            st.caption("Arrastrá para rotar, scroll para zoom.")
        else:
            st.image(r["ruta_png"], use_container_width=True)

        c1, c2, c3 = st.columns(3)
        c1.metric("Ancho", f"{r['ancho_mm']:.0f} mm")
        c2.metric("Alto", f"{r['alto_mm']:.0f} mm")
        c3.metric("Espesor", f"{r['espesor_mm']:.0f} mm")

        for nota in r["info"]:
            st.info(nota)
        for aviso in r["avisos"]:
            st.warning(aviso)

        if r["entra_a1"]:
            st.success(r["mensaje_a1"])
        else:
            st.warning(r["mensaje_a1"])

        st.caption(f"{r['vertices']} vértices — watertight={r['watertight']}")

        with open(r["ruta_stl"], "rb") as f:
            st.download_button(
                "⬇ Descargar STL", f, file_name=os.path.basename(r["ruta_stl"]),
                mime="model/stl", use_container_width=True, type="primary",
            )
