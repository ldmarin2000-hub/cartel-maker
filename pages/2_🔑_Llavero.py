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

TIPOS_DECO = ["Lista", "Emoji/pictograma", "Símbolo/signo", "Imagen propia (PNG/JPG)", "SVG propio"]

MODOS_LOGO_LABELS = {
    "Imagotipo — texto + ícono al costado": "imagotipo",
    "Isologo — texto + ícono fusionados": "isologo",
    "Isotipo — solo ícono, sin texto": "isotipo",
    "Monograma — solo iniciales, superpuestas": "monograma",
    "Emblema — todo encerrado en un anillo": "emblema",
}

PRESET_KEYS = [
    "ll_modo_logo", "ll_nombre", "llavero_selectbox", "llavero_ruta", "ll_alto_mm",
    "ll_color_base", "ll_color_texto",
    "ll_tipo_deco", "ll_decoracion", "ll_emoji_elegido", "ll_emoji_libre",
    "ll_imagen_umbral", "ll_imagen_invertir",
    "ll_decoracion_lado", "ll_aro_lado",
    "ll_tiene_ams", "ll_decoracion_tam", "ll_deco_x", "ll_deco_y", "ll_aro_r",
    "ll_espesor_texto_mm", "ll_espesor_base_mm", "ll_borde_mm",
    "ll_espaciado_monograma", "ll_anillo_mm",
]


@st.cache_data(ttl=120, show_spinner=False)
def _preview_rapido(nombre, ruta_ttf, alto_mm, color_base, color_texto,
                     decoracion, decoracion_emoji, decoracion_lado, decoracion_tam,
                     deco_x, deco_y, aro_lado, aro_r, borde_mm,
                     modo_logo, espaciado_monograma, anillo_mm):
    return llavero.preview_rapido(
        nombre, ruta_ttf, alto_mm=alto_mm, color_base=color_base, color_texto=color_texto,
        decoracion=decoracion, decoracion_emoji=decoracion_emoji,
        decoracion_lado=decoracion_lado, decoracion_tam=decoracion_tam,
        deco_x=deco_x, deco_y=deco_y, aro_lado=aro_lado, aro_r=aro_r, borde_mm=borde_mm,
        modo_logo=modo_logo, espaciado_monograma=espaciado_monograma, anillo_mm=anillo_mm,
    )


col_form, col_preview = st.columns([1, 1.3])

with col_form:
    bloque_presets("llavero", PRESET_KEYS)

    modo_logo_label = st.selectbox(
        "Tipo de logo", list(MODOS_LOGO_LABELS.keys()), key="ll_modo_logo",
        help="Imagotipo e isologo llevan texto + ícono (uno al lado del otro, o fusionados). "
             "Isotipo es el ícono solo. Monograma son las iniciales solas, superpuestas.",
    )
    modo_logo = MODOS_LOGO_LABELS[modo_logo_label]
    es_isotipo = modo_logo == "isotipo"
    es_monograma = modo_logo == "monograma"
    es_emblema = modo_logo == "emblema"

    if es_isotipo:
        nombre = ""
    else:
        if es_monograma:
            label_nombre, default_val, max_chars = "Iniciales (2-3 letras)", "BM", 3
        elif es_emblema:
            label_nombre, default_val, max_chars = "Nombre / texto (opcional)", "Bianca", None
        else:
            label_nombre, default_val, max_chars = "Nombre / texto", "Bianca", None
        nombre = st.text_input(label_nombre, value=default_val, key="ll_nombre", max_chars=max_chars)

    ruta_ttf = selector_fuente("Fuente", key="llavero", default_nombre="Lobster", texto_muestra=nombre or "Aa")

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

    decoracion, decoracion_svg, decoracion_emoji, svg_subido = "ninguno", None, None, None
    decoracion_imagen, imagen_subida, imagen_umbral, imagen_invertir = None, None, 128, False
    decoracion_lado = "derecha"
    if not es_monograma:
        if es_isotipo:
            label_deco = "Ícono (obligatorio para el isotipo)"
        elif es_emblema:
            label_deco = "Ícono (opcional — el emblema necesita texto y/o ícono)"
        else:
            label_deco = "Decoración (opcional)"
        tipo_deco = st.radio(label_deco, TIPOS_DECO, horizontal=True, key="ll_tipo_deco")
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
        elif tipo_deco == "Imagen propia (PNG/JPG)":
            imagen_subida = st.file_uploader(
                "Imagen (PNG/JPG)", type=["png", "jpg", "jpeg"],
                help="Logo/ícono simple — silueta clara sobre fondo liso o transparente, no una "
                     "foto. Se vectoriza por contorno (mismo método que el texto). No entra en "
                     "el preset ni en la vista rápida — solo en el llavero generado.",
            )
            if imagen_subida is not None:
                os.makedirs("output", exist_ok=True)
                decoracion_imagen = os.path.join("output", f"_subido_{imagen_subida.name}")
                with open(decoracion_imagen, "wb") as f:
                    f.write(imagen_subida.getvalue())
                c1, c2 = st.columns([2, 1])
                imagen_umbral = c1.slider(
                    "Umbral (más alto = capta grises más claros como parte del logo)",
                    0, 255, 128, key="ll_imagen_umbral",
                )
                imagen_invertir = c2.checkbox(
                    "Invertir", key="ll_imagen_invertir",
                    help="Tildá si el logo es claro sobre fondo oscuro (por default asume oscuro "
                         "sobre claro, salvo que el PNG tenga transparencia).",
                )
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
        if modo_logo == "imagotipo":
            decoracion_lado = st.radio(
                "Lado de la decoración", llavero.LADOS_DECO, horizontal=True, key="ll_decoracion_lado",
            )

    tiene_icono = bool(decoracion_svg or decoracion_imagen or decoracion_emoji or decoracion != "ninguno")
    archivo_subido = svg_subido or imagen_subida

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

    decoracion_tam, deco_x, deco_y = 7, 0, 0
    espaciado_monograma, anillo_mm = -0.15, 0.0
    with st.expander("Ajustes finos"):
        if es_monograma:
            espaciado_monograma = st.slider(
                "Superposición de las iniciales", -0.5, 0.1, -0.15, step=0.05, key="ll_espaciado_monograma",
                help="Más negativo = las letras se superponen/entrelazan más. 0 = espaciado normal.",
            )
        if not es_isotipo or tiene_icono:
            if not es_monograma:
                decoracion_tam = st.slider("Tamaño de la decoración", 3, 20, 7, key="ll_decoracion_tam")
                deco_x = st.slider("Ajuste horizontal de la decoración", -40, 40, 0, key="ll_deco_x")
                deco_y = st.slider("Ajuste vertical de la decoración", -40, 40, 0, key="ll_deco_y")
        if es_monograma or es_emblema:
            anillo_mm = st.slider(
                "Anillo circular (mm de grosor, 0 = sin anillo)", 0.0, 6.0, 2.0, step=0.5, key="ll_anillo_mm",
            )
        aro_r = st.slider("Radio del agujero del aro (mm)", 1.0, 5.0, 2.0, step=0.25, key="ll_aro_r")
        espesor_texto_mm = st.slider(
            "Espesor del texto/decoración (mm)", 1.0, 6.0, 2.0, step=0.5, key="ll_espesor_texto_mm",
        )
        espesor_base_mm = st.slider("Espesor de la base (mm)", 1.0, 8.0, 3.0, step=0.5, key="ll_espesor_base_mm")
        borde_mm = st.slider("Margen del borde (mm)", 1.0, 10.0, 3.0, step=0.5, key="ll_borde_mm")

    generar_click = st.button("Generar llavero", type="primary", use_container_width=True)

with col_preview:
    puede_preview = (es_isotipo or es_emblema or es_monograma or nombre.strip()) and not archivo_subido
    if puede_preview:
        png_rapido, ancho_rapido, alto_rapido = _preview_rapido(
            nombre, ruta_ttf, float(alto_mm), color_base, color_texto,
            decoracion, decoracion_emoji, decoracion_lado, decoracion_tam, deco_x, deco_y, aro_lado, aro_r, borde_mm,
            modo_logo, espaciado_monograma, anillo_mm,
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
    elif es_isotipo and not tiene_icono:
        st.error("Elegí una decoración, imagen, emoji/símbolo o SVG para el isotipo (no lleva texto).")
    elif es_emblema and not tiene_icono and not nombre.strip():
        st.error("El emblema necesita texto y/o una decoración/imagen/emoji/SVG.")
    elif modo_logo not in ("isotipo", "emblema") and not nombre.strip():
        st.error("Escribí algún nombre/texto primero.")
    else:
        with st.spinner("Generando la geometría y la malla 3D..."):
            try:
                r = llavero.generar(
                    nombre=nombre, ruta_ttf=ruta_ttf, alto_mm=float(alto_mm),
                    color_base=color_base, color_texto=color_texto,
                    decoracion=decoracion, decoracion_lado=decoracion_lado, decoracion_tam=decoracion_tam,
                    decoracion_svg=decoracion_svg, decoracion_emoji=decoracion_emoji,
                    decoracion_imagen=decoracion_imagen, imagen_umbral=imagen_umbral, imagen_invertir=imagen_invertir,
                    deco_x=deco_x, deco_y=deco_y,
                    aro_lado=aro_lado, aro_r=aro_r,
                    espesor_texto_mm=espesor_texto_mm, espesor_base_mm=espesor_base_mm, borde_mm=borde_mm,
                    tiene_ams=tiene_ams,
                    modo_logo=modo_logo, espaciado_monograma=espaciado_monograma, anillo_mm=anillo_mm,
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
