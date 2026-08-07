#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pages/5_🗿_Esculturas.py
----------------------------
Página de Streamlit para el generador de esculturas/relieve. Es solo la
capa visual: toda la lógica real vive en generators/esculturas.py
(generar()), la misma que usa la versión de consola (main.py).
"""

import os

import streamlit as st
import streamlit.components.v1 as components

from core import colores, heightmap, preview3d
from generators import esculturas
from ui_streamlit import bloque_presets

st.set_page_config(page_title="Esculturas · Cartel Maker", page_icon="🗿", layout="wide")

st.title("🗿 Escultura (relieve desde imagen)")
st.caption(esculturas.DESCRIPCION)
st.info(
    "Subís una foto/logo/dibujo y el brillo de cada zona se convierte en altura — un relieve "
    "3D tallado de verdad (no una silueta plana, no una nube de puntos), sólido y watertight, "
    "listo para imprimir. Funciona mejor con buen contraste; una imagen muy plana en brillo da "
    "un relieve casi sin relieve."
)

CALIDADES = {
    "Rápida (menos detalle, STL liviano)": 70,
    "Normal": esculturas.RESOLUCION_DEFAULT_PX,
    "Alta (más detalle, tarda más y pesa más)": esculturas.RESOLUCION_ALTA_PX,
}

PRESET_KEYS = [
    "es_ancho_mm", "es_espesor_base_mm", "es_relieve_mm",
    "es_oscuro_alto", "es_suavizado_px", "es_calidad", "es_color",
]


@st.cache_data(ttl=120, show_spinner=False)
def _preview_rapido(ruta_imagen, ancho_mm, alto_mm, espesor_base_mm, relieve_mm, suavizado_px, oscuro_alto):
    return esculturas.preview_rapido(
        ruta_imagen, ancho_mm=ancho_mm, alto_mm=alto_mm,
        espesor_base_mm=espesor_base_mm, relieve_mm=relieve_mm,
        suavizado_px=suavizado_px, oscuro_alto=oscuro_alto,
    )


col_form, col_preview = st.columns([1, 1.3])

with col_form:
    bloque_presets("esculturas", PRESET_KEYS)

    imagen_subida = st.file_uploader(
        "Imagen (PNG/JPG)", type=["png", "jpg", "jpeg"],
        help="Foto, logo o dibujo — mejor con buen contraste entre las zonas que querés que "
             "sobresalgan y las que no. No entra en el preset (el archivo no se puede pre-cargar).",
    )
    ruta_imagen = None
    if imagen_subida is not None:
        os.makedirs("output", exist_ok=True)
        ruta_imagen = os.path.join("output", f"_subido_{imagen_subida.name}")
        with open(ruta_imagen, "wb") as f:
            f.write(imagen_subida.getvalue())

    ancho_mm = st.slider("Ancho (mm)", 30, 200, 80, step=5, key="es_ancho_mm")
    alto_mm = ancho_mm
    if ruta_imagen:
        _, alto_mm = heightmap.ajustar_caja_a_proporcion(ruta_imagen, float(ancho_mm))
        st.caption(f"Alto calculado según la proporción real de la imagen: **{alto_mm:.0f} mm**.")

    c1, c2 = st.columns(2)
    espesor_base_mm = c1.slider(
        "Espesor de la base (mm)", 1.0, 8.0, 3.0, step=0.5, key="es_espesor_base_mm",
        help="El piso mínimo — para que sea imprimible y no se rompa donde el relieve es más bajo.",
    )
    relieve_mm = c2.slider(
        "Relieve (mm)", 1.0, 25.0, 8.0, step=0.5, key="es_relieve_mm",
        help="Cuánto sobresale la parte más alta por encima de la base.",
    )

    oscuro_alto_label = st.radio(
        "Qué queda más alto", ["Zonas oscuras", "Zonas claras"], horizontal=True, key="es_oscuro_alto",
        help="\"Zonas oscuras\" da el relieve escultórico típico (como una moneda o medallón) — "
             "las sombras/detalles oscuros de la foto sobresalen.",
    )
    oscuro_alto = oscuro_alto_label == "Zonas oscuras"

    color_pieza = st.selectbox(
        "Color de filamento (visor, no cambia el STL)", colores.NOMBRES,
        index=colores.NOMBRES.index("Dorado"), key="es_color",
    )

    with st.expander("Ajustes finos"):
        suavizado_px = st.slider(
            "Suavizado (px)", 0.0, 4.0, 1.0, step=0.5, key="es_suavizado_px",
            help="Desenfoca la imagen antes de tallar el relieve — saca ruido/artefactos de JPG "
                 "que quedarían como picos feos. 0 = sin suavizar.",
        )
        calidad_label = st.radio("Calidad (detalle de la grilla)", list(CALIDADES.keys()), key="es_calidad")
        resolucion_px = CALIDADES[calidad_label]

    generar_click = st.button("Generar escultura", type="primary", use_container_width=True)

with col_preview:
    if ruta_imagen:
        png_rapido = _preview_rapido(
            ruta_imagen, float(ancho_mm), float(alto_mm), float(espesor_base_mm), float(relieve_mm),
            float(suavizado_px), oscuro_alto,
        )
        if png_rapido:
            st.image(
                png_rapido,
                caption=f"Vista rápida — ~{ancho_mm:.0f} x {alto_mm:.0f} x "
                        f"{espesor_base_mm + relieve_mm:.0f} mm. Al generar sale la malla real, "
                        f"con más detalle y el visor 3D interactivo.",
                use_container_width=True,
            )
            st.divider()

    if not generar_click:
        st.info("Subí una imagen y apretá **Generar escultura**.")
    elif not ruta_imagen:
        st.error("Subí una imagen primero.")
    else:
        with st.spinner("Tallando el relieve (puede tardar unos segundos)..."):
            try:
                r = esculturas.generar(
                    ruta_imagen, ancho_mm=float(ancho_mm), alto_mm=float(alto_mm),
                    espesor_base_mm=float(espesor_base_mm), relieve_mm=float(relieve_mm),
                    resolucion_px=resolucion_px, suavizado_px=float(suavizado_px),
                    oscuro_alto=oscuro_alto,
                )
            except (FileNotFoundError, ValueError) as e:
                st.error(str(e))
                r = None

        if r:
            html_visor = preview3d.armar_html_visor(
                [{"ruta_stl": r["ruta_stl"], "color": colores.hex_de(color_pieza), "nombre": "escultura"}]
            )
            if html_visor:
                components.html(html_visor, height=460)
                st.caption("Arrastrá para rotar, scroll para zoom.")
            else:
                st.image(r["ruta_png"], use_container_width=True)

            c1, c2, c3 = st.columns(3)
            c1.metric("Ancho", f"{r['ancho_mm']:.0f} mm")
            c2.metric("Alto", f"{r['alto_mm']:.0f} mm")
            c3.metric("Grosor máx.", f"{r['profundidad_mm']:.1f} mm")

            for nota in r["info"]:
                st.info(nota)
            for aviso in r["avisos"]:
                st.warning(aviso)

            if r["entra_a1"]:
                st.success(r["mensaje_a1"])
            else:
                st.warning(r["mensaje_a1"])

            st.caption(f"{r['vertices']} vértices, {r['caras']} caras.")

            with open(r["ruta_stl"], "rb") as f:
                st.download_button(
                    "⬇ Descargar STL", f, file_name=os.path.basename(r["ruta_stl"]),
                    mime="model/stl", use_container_width=True, type="primary",
                )
