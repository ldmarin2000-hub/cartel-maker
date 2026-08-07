#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pages/4_🔀_Ambigrama.py
---------------------------
Página de Streamlit para el generador de ambigramas. Es solo la capa
visual: toda la lógica real vive en generators/ambigrama.py (generar()),
la misma que usa la versión de consola (main.py).
"""

import os

import streamlit as st
import streamlit.components.v1 as components

from core import colores, preview3d
from generators import ambigrama
from ui_streamlit import bloque_presets, selector_fuente

st.set_page_config(page_title="Ambigrama · Cartel Maker", page_icon="🔀", layout="wide")

st.title("🔀 Ambigrama (2 caras)")
st.caption(ambigrama.DESCRIPCION)
st.info(
    "El lado \"de arriba\" se lee mirando el objeto desde ARRIBA o ABAJO; el lado \"de "
    "frente\" mirándolo de frente — el aro para colgar queda arriba, sin tapar ninguna de "
    "las 2 lecturas. Los dos lados se fuerzan a la MISMA caja compartida y se respeta tal cual "
    "la pongas. Si una palabra no entra cómoda, usá el espaciado entre letras (negativo) para "
    "juntarlas — ojo: palabras muy largas en una caja angosta tienen un límite físico y pueden "
    "quedar ilegibles por más que ajustes el espaciado."
)

PRESET_KEYS = [
    "frente_tipo", "frente_valor", "ambigrama_frente_selectbox", "ambigrama_frente_ruta",
    "frente_espaciado", "frente_forma",
    "costado_tipo", "costado_valor", "ambigrama_costado_selectbox", "ambigrama_costado_ruta",
    "costado_espaciado", "costado_forma",
    "am_ancho_mm", "am_profundidad_mm", "am_alto_mm", "am_agregar_aro",
    "am_aro_radio_hueco", "am_aro_radio_tab", "am_aro_borde_label", "am_color_pieza",
]


@st.cache_data(ttl=120, show_spinner=False)
def _preview_rapido(tipo_f, valor_f, tipo_c, valor_c, ttf_f, ttf_c, esp_f, esp_c,
                     ancho_mm, profundidad_mm, alto_mm):
    return ambigrama.preview_rapido(
        tipo_f, valor_f, tipo_c, valor_c, ruta_ttf_frente=ttf_f, ruta_ttf_costado=ttf_c,
        espaciado_frente=esp_f, espaciado_costado=esp_c,
        ancho_mm=ancho_mm, profundidad_mm=profundidad_mm, alto_mm=alto_mm,
    )


def _form_lado(etiqueta, key_prefix, default_texto, default_forma):
    st.subheader(etiqueta)
    tipo = st.radio("Tipo", ambigrama.TIPOS_CONTENIDO, horizontal=True, key=f"{key_prefix}_tipo")
    if tipo == "texto":
        valor = st.text_input("Texto", value=default_texto, key=f"{key_prefix}_valor")
        ruta_ttf = selector_fuente(
            "Fuente", key=f"ambigrama_{key_prefix}", default_nombre="Bungee", texto_muestra=valor,
        )
        espaciado = st.slider(
            "Espaciado entre letras", -0.4, 0.4, 0.0, step=0.05, key=f"{key_prefix}_espaciado",
            help="Negativo junta las letras (hasta tocarse/superponerse) para que una palabra "
                 "larga entre mejor en una caja angosta. 0 = espaciado normal de la fuente.",
        )
        return tipo, valor, ruta_ttf, espaciado
    elif tipo == "svg":
        subido = st.file_uploader(
            "Ícono/logo (SVG)", type=["svg"], key=f"{key_prefix}_svg",
            help="Funciona con casi cualquier ícono simple (un solo color, sin fotos ni degradados).",
        )
        valor = None
        if subido is not None:
            os.makedirs("output", exist_ok=True)
            valor = os.path.join("output", f"_subido_{key_prefix}_{subido.name}")
            with open(valor, "wb") as f:
                f.write(subido.getvalue())
        return tipo, valor, None, 0.0
    else:
        valor = st.selectbox("Forma", ambigrama.DECORACIONES, index=ambigrama.DECORACIONES.index(default_forma),
                              key=f"{key_prefix}_forma")
        return tipo, valor, None, 0.0


col_form, col_preview = st.columns([1, 1.3])

with col_form:
    bloque_presets("ambigrama", PRESET_KEYS)

    c1, c2 = st.columns(2)
    with c1:
        tipo_f, valor_f, ttf_f, esp_f = _form_lado("De arriba/abajo", "frente", "Mia", "corazon")
    with c2:
        tipo_c, valor_c, ttf_c, esp_c = _form_lado("De frente", "costado", "Mia", "estrella")

    with st.expander("Ajustes finos"):
        st.caption("La caja compartida a la que se fuerzan los 2 lados (como el 55x20x55 del original):")
        c1, c2, c3 = st.columns(3)
        ancho_mm = c1.number_input("Ancho (mm)", value=55.0, step=5.0, key="am_ancho_mm")
        profundidad_mm = c2.number_input("Profundidad (mm)", value=20.0, step=5.0, key="am_profundidad_mm")
        alto_mm = c3.number_input("Alto (mm)", value=55.0, step=5.0, key="am_alto_mm")
        agregar_aro = st.checkbox("Agregar aro para colgar", value=True, key="am_agregar_aro")
        c1, c2 = st.columns(2)
        aro_radio_hueco = c1.number_input(
            "Radio del agujero (mm)", value=2.0, step=0.25, disabled=not agregar_aro, key="am_aro_radio_hueco",
        )
        aro_radio_tab = c2.number_input(
            "Radio del aro (mm)", value=6.0, step=0.5, disabled=not agregar_aro, key="am_aro_radio_tab",
        )
        aro_borde_label = st.radio(
            "Dónde va el aro",
            [
                "Automático (recomendado)",
                "Lado de arriba/abajo — borde 1 (disco)",
                "Lado de arriba/abajo — borde 2 (disco)",
                "Lado de frente — abajo (loop)",
                "Lado de frente — arriba (loop)",
            ],
            disabled=not agregar_aro, key="am_aro_borde_label",
            help="Automático prueba primero un loop parado que nace de una punta (p.ej. la de "
                 "un corazón puesto \"de frente\") y si no hay una punta sólida ahí, cae a un "
                 "disco plano en el borde más angosto del contenido \"de arriba\". Los otros 4 "
                 "extremos son manuales: los 2 discos van en un borde del contenido \"de "
                 "arriba/abajo\", los 2 loops nacen del contenido \"de frente\" (arriba o abajo). "
                 "Probá varios y volvé a generar para comparar.",
        )
        aro_borde = {
            "Automático (recomendado)": "auto",
            "Lado de arriba/abajo — borde 1 (disco)": "y_min",
            "Lado de arriba/abajo — borde 2 (disco)": "y_max",
            "Lado de frente — abajo (loop)": "z_min",
            "Lado de frente — arriba (loop)": "z_max",
        }[aro_borde_label]

    color_pieza = st.selectbox(
        "Color de filamento (visor, no cambia el STL)", colores.NOMBRES,
        index=colores.NOMBRES.index("Dorado"), key="am_color_pieza",
    )

    generar_click = st.button("Generar ambigrama", type="primary", use_container_width=True)

with col_preview:
    if tipo_f != "svg" and tipo_c != "svg":
        png_rapido = _preview_rapido(
            tipo_f, valor_f, tipo_c, valor_c, ttf_f, ttf_c, esp_f, esp_c,
            float(ancho_mm), float(profundidad_mm), float(alto_mm),
        )
        if png_rapido:
            st.image(
                png_rapido,
                caption="Vista rápida (2D) de cada lado por separado — NO es el resultado final "
                        "(que es la intersección de los dos). Al generar sale la pieza 3D real.",
                use_container_width=True,
            )
            st.divider()

    if not generar_click:
        st.info("Completá el formulario y apretá **Generar ambigrama**.")
    elif tipo_f == "texto" and not valor_f.strip():
        st.error("Escribí el texto de arriba/abajo.")
    elif tipo_c == "texto" and not valor_c.strip():
        st.error("Escribí el texto de frente.")
    elif tipo_f == "svg" and not valor_f:
        st.error("Subí un SVG para el lado de arriba/abajo.")
    elif tipo_c == "svg" and not valor_c:
        st.error("Subí un SVG para el lado de frente.")
    else:
        with st.spinner("Armando la geometría 3D y haciendo la intersección (puede tardar)..."):
            try:
                r = ambigrama.generar(
                    tipo_f, valor_f, tipo_c, valor_c,
                    ruta_ttf_frente=ttf_f, ruta_ttf_costado=ttf_c,
                    espaciado_frente=esp_f, espaciado_costado=esp_c,
                    ancho_mm=float(ancho_mm), profundidad_mm=float(profundidad_mm), alto_mm=float(alto_mm),
                    agregar_aro=agregar_aro, aro_radio_hueco=aro_radio_hueco, aro_radio_tab=aro_radio_tab,
                    aro_borde=aro_borde,
                )
            except (FileNotFoundError, ValueError) as e:
                st.error(str(e))
                r = None

        if r:
            html_visor = preview3d.armar_html_visor(
                [{"ruta_stl": r["ruta_stl"], "color": colores.hex_de(color_pieza), "nombre": "ambigrama"}]
            )
            if html_visor:
                components.html(html_visor, height=460)
                st.caption("Arrastrá para rotar, scroll para zoom — girá para ver las 2 lecturas.")
            else:
                st.image(r["ruta_png"], use_container_width=True)

            c1, c2, c3 = st.columns(3)
            c1.metric("Ancho", f"{r['ancho_mm']:.0f} mm")
            c2.metric("Profundidad", f"{r['profundidad_mm']:.0f} mm")
            c3.metric("Alto", f"{r['alto_mm']:.0f} mm")

            for nota in r["info"]:
                st.info(nota)
            for aviso in r["avisos"]:
                st.warning(aviso)

            if r["entra_a1"]:
                st.success(r["mensaje_a1"])
            else:
                st.warning(r["mensaje_a1"])

            if not r["watertight"]:
                st.caption("No quedó perfectamente watertight, revisalo antes de imprimir.")

            with open(r["ruta_stl"], "rb") as f:
                st.download_button(
                    "⬇ Descargar STL", f, file_name=os.path.basename(r["ruta_stl"]),
                    mime="model/stl", use_container_width=True,
                )
