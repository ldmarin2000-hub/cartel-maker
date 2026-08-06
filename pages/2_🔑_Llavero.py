#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pages/2_🔑_Llavero.py
-------------------------
Página de Streamlit para el generador de llaveros. Es solo la capa visual:
toda la lógica real vive en generators/llavero.py (generar()), la misma
que usa la versión de consola (main.py). Python puro (sin OpenSCAD).
"""

import os

import streamlit as st

from core import fuentes
from generators import llavero

st.set_page_config(page_title="Llavero · Cartel Maker", page_icon="🔑", layout="wide")

st.title("🔑 Llavero")
st.caption(llavero.DESCRIPCION)


@st.cache_data(ttl=600)
def _fuentes_disponibles():
    return fuentes.listar_fuentes()


col_form, col_preview = st.columns([1, 1.3])

with col_form:
    nombre = st.text_input("Nombre / texto", value="Bianca")

    catalogo = _fuentes_disponibles()
    OTRA_RUTA = "✏️ Otra ruta..."
    opciones = [n for n, _ in catalogo] + [OTRA_RUTA]
    indice_default = opciones.index("Lily Script One") if "Lily Script One" in opciones else 0
    elegida = st.selectbox(f"Fuente ({len(catalogo)} instaladas + las de fonts/)", opciones, index=indice_default)
    if elegida == OTRA_RUTA:
        ruta_ttf = st.text_input("Ruta a la fuente .ttf", value="fonts/Pacifico.ttf")
    else:
        ruta_ttf = dict(catalogo)[elegida]

    alto_mm = st.slider("Alto del texto (mm)", 10, 60, 20)

    c1, c2 = st.columns(2)
    color_base = c1.selectbox("Color base (preview)", llavero.COLORES, index=llavero.COLORES.index("White"))
    color_texto = c2.selectbox("Color texto (preview)", llavero.COLORES, index=llavero.COLORES.index("HotPink"))

    decoracion = st.selectbox("Decoración", llavero.DECORACIONES, index=llavero.DECORACIONES.index("corazon"))
    svg_subido = st.file_uploader(
        "...o subí tu propio ícono/logo (SVG, opcional)", type=["svg"],
        help="Si subís un SVG, reemplaza a la decoración de la lista de arriba. Funciona con "
             "casi cualquier ícono simple (un solo color, sin fotos ni degradados).",
    )
    decoracion_svg = None
    if svg_subido is not None:
        os.makedirs("output", exist_ok=True)
        decoracion_svg = os.path.join("output", f"_subido_{svg_subido.name}")
        with open(decoracion_svg, "wb") as f:
            f.write(svg_subido.getvalue())
    decoracion_lado = st.radio("Lado de la decoración", llavero.LADOS_DECO, horizontal=True)

    aro_lado = st.radio("Aro (para colgar del llavero)", llavero.LADOS_ARO, horizontal=True)

    tiene_ams = st.checkbox(
        "Tengo AMS (impresora multicolor)", value=False,
        help="Con AMS, la pieza de texto se exporta ya alineada sobre la base (importás las "
             "2 juntas en Bambu Studio, sin moverlas, un color por objeto, y las imprimís en "
             "un solo trabajo — sin pegar nada a mano). Sin AMS, cada pieza sale apoyada en "
             "el suelo para imprimirlas por separado y pegarlas después.",
    )

    with st.expander("Ajustes finos"):
        decoracion_tam = st.slider("Tamaño de la decoración", 3, 20, 7)
        deco_x = st.slider("Ajuste horizontal de la decoración", -40, 40, 0)
        deco_y = st.slider("Ajuste vertical de la decoración", -40, 40, 0)
        aro_r = st.slider("Radio del agujero del aro (mm)", 1.0, 5.0, 2.0, step=0.25)
        espesor_texto_mm = st.slider("Espesor del texto/decoración (mm)", 1.0, 6.0, 2.0, step=0.5)
        espesor_base_mm = st.slider("Espesor de la base (mm)", 1.0, 8.0, 3.0, step=0.5)
        borde_mm = st.slider("Margen del borde (mm)", 1.0, 10.0, 3.0, step=0.5)

    generar_click = st.button("Generar llavero", type="primary", use_container_width=True)

with col_preview:
    if not generar_click:
        st.info("Completá el formulario y apretá **Generar llavero**.")
    elif not nombre.strip():
        st.error("Escribí algún nombre/texto primero.")
    else:
        with st.spinner("Generando el texto y la malla 3D..."):
            try:
                r = llavero.generar(
                    nombre=nombre, ruta_ttf=ruta_ttf, alto_mm=float(alto_mm),
                    color_base=color_base, color_texto=color_texto,
                    decoracion=decoracion, decoracion_lado=decoracion_lado, decoracion_tam=decoracion_tam,
                    decoracion_svg=decoracion_svg,
                    deco_x=deco_x, deco_y=deco_y,
                    aro_lado=aro_lado, aro_r=aro_r,
                    espesor_texto_mm=espesor_texto_mm, espesor_base_mm=espesor_base_mm, borde_mm=borde_mm,
                    tiene_ams=tiene_ams,
                )
            except (FileNotFoundError, ValueError) as e:
                st.error(str(e))
                r = None

        if r:
            st.image(r["ruta_png"], use_column_width=True)

            c1, c2 = st.columns(2)
            c1.metric("Ancho", f"{r['ancho_mm']:.0f} mm")
            c2.metric("Alto", f"{r['alto_mm']:.0f} mm")

            for nota in r["info"]:
                st.info(nota)
            for aviso in r["avisos"]:
                st.warning(aviso)

            if r["entra_a1"]:
                st.success(r["mensaje_a1"])
            else:
                st.warning(r["mensaje_a1"])

            if not r["watertight_base"] or not r["watertight_texto"]:
                st.caption("Alguna pieza no quedó perfectamente watertight (modo multi-cuerpo de respaldo), pero igual imprime bien.")

            if r["ruta_stl_multicolor"]:
                with open(r["ruta_stl_multicolor"], "rb") as f:
                    st.download_button(
                        "⬇ STL multicolor (para AMS)", f, file_name=os.path.basename(r["ruta_stl_multicolor"]),
                        mime="model/stl", use_container_width=True, type="primary",
                    )
                st.caption("O si preferís, las piezas sueltas de siempre:")

            dcol1, dcol2 = st.columns(2)
            with open(r["ruta_stl_base"], "rb") as f:
                dcol1.download_button(
                    "⬇ STL base", f, file_name=os.path.basename(r["ruta_stl_base"]),
                    mime="model/stl", use_container_width=True,
                )
            with open(r["ruta_stl_texto"], "rb") as f:
                dcol2.download_button(
                    "⬇ STL texto", f, file_name=os.path.basename(r["ruta_stl_texto"]),
                    mime="model/stl", use_container_width=True,
                )
