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
import streamlit.components.v1 as components

from core import colores, decoraciones, preview3d
from generators import llavero
from ui_streamlit import bloque_presets, selector_fuente

st.set_page_config(page_title="Llavero · Cartel Maker", page_icon="🔑", layout="wide")

st.title("🔑 Llavero")
st.caption(llavero.DESCRIPCION)

TIPOS_DECO = ["Lista", "Emoji/pictograma", "Símbolo/signo", "SVG propio"]

PRESET_KEYS = [
    "ll_nombre", "llavero_selectbox", "llavero_ruta", "ll_alto_mm",
    "ll_color_base", "ll_color_texto",
    "ll_tipo_deco", "ll_decoracion", "ll_emoji_elegido", "ll_emoji_libre",
    "ll_decoracion_lado", "ll_aro_lado",
    "ll_tiene_ams", "ll_decoracion_tam", "ll_deco_x", "ll_deco_y", "ll_aro_r",
    "ll_espesor_texto_mm", "ll_espesor_base_mm", "ll_borde_mm",
]


@st.cache_data(ttl=120, show_spinner=False)
def _preview_rapido(nombre, ruta_ttf, alto_mm, color_base, color_texto,
                     decoracion, decoracion_emoji, decoracion_lado, decoracion_tam,
                     deco_x, deco_y, aro_lado, aro_r, borde_mm):
    return llavero.preview_rapido(
        nombre, ruta_ttf, alto_mm=alto_mm, color_base=color_base, color_texto=color_texto,
        decoracion=decoracion, decoracion_emoji=decoracion_emoji,
        decoracion_lado=decoracion_lado, decoracion_tam=decoracion_tam,
        deco_x=deco_x, deco_y=deco_y, aro_lado=aro_lado, aro_r=aro_r, borde_mm=borde_mm,
    )


col_form, col_preview = st.columns([1, 1.3])

with col_form:
    bloque_presets("llavero", PRESET_KEYS)

    nombre = st.text_input("Nombre / texto", value="Bianca", key="ll_nombre")

    ruta_ttf = selector_fuente("Fuente", key="llavero", default_nombre="Lobster", texto_muestra=nombre)

    alto_mm = st.slider("Alto del texto (mm)", 10, 60, 20, key="ll_alto_mm")

    c1, c2 = st.columns(2)
    color_base = c1.selectbox(
        "Color base (filamento)", llavero.COLORES, index=llavero.COLORES.index("Blanco"), key="ll_color_base",
    )
    color_texto = c2.selectbox(
        "Color texto (filamento)", llavero.COLORES, index=llavero.COLORES.index("Rosa Fluor"), key="ll_color_texto",
    )
    c1.markdown(
        f'<div style="height:22px;border-radius:4px;background:{colores.hex_de(color_base)};'
        f'border:1px solid #0003"></div>', unsafe_allow_html=True,
    )
    c2.markdown(
        f'<div style="height:22px;border-radius:4px;background:{colores.hex_de(color_texto)};'
        f'border:1px solid #0003"></div>', unsafe_allow_html=True,
    )

    tipo_deco = st.radio("Decoración", TIPOS_DECO, horizontal=True, key="ll_tipo_deco")
    decoracion, decoracion_svg, decoracion_emoji, svg_subido = "ninguno", None, None, None
    if tipo_deco == "Lista":
        decoracion = st.selectbox(
            "Forma", llavero.DECORACIONES, index=llavero.DECORACIONES.index("corazon"), key="ll_decoracion",
        )
    elif tipo_deco in ("Emoji/pictograma", "Símbolo/signo"):
        curados = decoraciones.EMOJIS_CURADOS if tipo_deco == "Emoji/pictograma" else decoraciones.SIGNOS_CURADOS
        c1, c2 = st.columns([1, 1])
        elegido = c1.selectbox("Elegí uno", curados, key="ll_emoji_elegido")
        libre = c2.text_input(
            "...o pegá cualquier otro", value="", key="ll_emoji_libre", max_chars=4,
            help="Cualquier emoji o símbolo unicode — si escribís acá, esto gana sobre lo elegido a la izquierda.",
        )
        decoracion_emoji = libre.strip() or elegido
    else:
        svg_subido = st.file_uploader(
            "SVG propio", type=["svg"],
            help="Funciona con casi cualquier ícono simple (un solo color, sin fotos ni "
                 "degradados). No entra en el preset ni en la vista rápida — solo en el llavero generado.",
        )
        if svg_subido is not None:
            os.makedirs("output", exist_ok=True)
            decoracion_svg = os.path.join("output", f"_subido_{svg_subido.name}")
            with open(decoracion_svg, "wb") as f:
                f.write(svg_subido.getvalue())
    decoracion_lado = st.radio(
        "Lado de la decoración", llavero.LADOS_DECO, horizontal=True, key="ll_decoracion_lado",
    )

    aro_lado = st.radio(
        "Aro (para colgar del llavero)", llavero.LADOS_ARO, horizontal=True, key="ll_aro_lado",
    )

    tiene_ams = st.checkbox(
        "Tengo AMS (impresora multicolor)", value=False, key="ll_tiene_ams",
        help="Con AMS, la pieza de texto se exporta ya alineada sobre la base (importás las "
             "2 juntas en Bambu Studio, sin moverlas, un color por objeto, y las imprimís en "
             "un solo trabajo — sin pegar nada a mano). Sin AMS, cada pieza sale apoyada en "
             "el suelo para imprimirlas por separado y pegarlas después.",
    )

    with st.expander("Ajustes finos"):
        decoracion_tam = st.slider("Tamaño de la decoración", 3, 20, 7, key="ll_decoracion_tam")
        deco_x = st.slider("Ajuste horizontal de la decoración", -40, 40, 0, key="ll_deco_x")
        deco_y = st.slider("Ajuste vertical de la decoración", -40, 40, 0, key="ll_deco_y")
        aro_r = st.slider("Radio del agujero del aro (mm)", 1.0, 5.0, 2.0, step=0.25, key="ll_aro_r")
        espesor_texto_mm = st.slider(
            "Espesor del texto/decoración (mm)", 1.0, 6.0, 2.0, step=0.5, key="ll_espesor_texto_mm",
        )
        espesor_base_mm = st.slider("Espesor de la base (mm)", 1.0, 8.0, 3.0, step=0.5, key="ll_espesor_base_mm")
        borde_mm = st.slider("Margen del borde (mm)", 1.0, 10.0, 3.0, step=0.5, key="ll_borde_mm")

    generar_click = st.button("Generar llavero", type="primary", use_container_width=True)

with col_preview:
    if nombre.strip() and not svg_subido:
        png_rapido, ancho_rapido, alto_rapido = _preview_rapido(
            nombre, ruta_ttf, float(alto_mm), color_base, color_texto,
            decoracion, decoracion_emoji, decoracion_lado, decoracion_tam, deco_x, deco_y, aro_lado, aro_r, borde_mm,
        )
        if png_rapido:
            st.image(
                png_rapido,
                caption=f"Vista rápida (2D) — ~{ancho_rapido:.0f} x {alto_rapido:.0f} mm. "
                        f"Al generar sale la malla 3D real (con volumen, para imprimir).",
                use_container_width=True,
            )
            st.divider()

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
                    decoracion_svg=decoracion_svg, decoracion_emoji=decoracion_emoji,
                    deco_x=deco_x, deco_y=deco_y,
                    aro_lado=aro_lado, aro_r=aro_r,
                    espesor_texto_mm=espesor_texto_mm, espesor_base_mm=espesor_base_mm, borde_mm=borde_mm,
                    tiene_ams=tiene_ams,
                )
            except (FileNotFoundError, ValueError) as e:
                st.error(str(e))
                r = None

        if r:
            color_base_hex = colores.hex_de(color_base)
            color_texto_hex = colores.hex_de(color_texto)
            if tiene_ams:
                # con AMS las 2 piezas ya están en su posición real (una arriba de la otra) —
                # se puede mostrar el conjunto armado en un solo visor.
                html_visor = preview3d.armar_html_visor([
                    {"ruta_stl": r["ruta_stl_base"], "color": color_base_hex, "nombre": "base"},
                    {"ruta_stl": r["ruta_stl_texto"], "color": color_texto_hex, "nombre": "texto"},
                ])
                if html_visor:
                    components.html(html_visor, height=490)
                    st.caption("Arrastrá para rotar, scroll para zoom.")
                else:
                    st.image(r["ruta_png"], use_container_width=True)
            else:
                # sin AMS cada pieza se exporta apoyada en el suelo por separado (para
                # imprimirlas sueltas) — mostrarlas juntas se verían superpuestas, así que
                # van en 2 visores lado a lado.
                vcol1, vcol2 = st.columns(2)
                html_base = preview3d.armar_html_visor([{"ruta_stl": r["ruta_stl_base"], "color": color_base_hex}])
                html_texto = preview3d.armar_html_visor([{"ruta_stl": r["ruta_stl_texto"], "color": color_texto_hex}])
                with vcol1:
                    st.caption("Base")
                    if html_base:
                        components.html(html_base, height=320)
                with vcol2:
                    st.caption("Texto/decoración")
                    if html_texto:
                        components.html(html_texto, height=320)
                if not html_base or not html_texto:
                    st.image(r["ruta_png"], use_container_width=True)

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
