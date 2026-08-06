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
import streamlit.components.v1 as components

from core import fuentes, preview3d
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

    st.divider()
    agregar_nombre = st.checkbox(
        "Agregar nombre en cursiva abajo", value=False,
        help="Texto macizo (sin luz, sin hueco), soldado como una sola pieza pegada al borde "
             "de abajo de la letra — mismo color que la letra.",
    )
    texto_nombre, ruta_ttf_nombre, alto_nombre_mm = "", None, 30.0
    if agregar_nombre:
        texto_nombre = st.text_input("Nombre", value="Bianca", max_chars=20)
        idx_cursiva = opciones.index("Lily Script One") if "Lily Script One" in opciones else 0
        elegida_nombre = st.selectbox("Fuente del nombre", opciones, index=idx_cursiva, key="fuente_nombre")
        if elegida_nombre == OTRA_RUTA:
            ruta_ttf_nombre = st.text_input("Ruta a la fuente del nombre .ttf", value="fonts/Pacifico.ttf")
        else:
            ruta_ttf_nombre = dict(catalogo)[elegida_nombre]
        alto_nombre_mm = st.slider("Alto del nombre (mm)", 10, 60, 30, step=2)

    st.divider()
    n_decoraciones = st.number_input(
        "Decoraciones sueltas en el frente", min_value=0, max_value=4, value=0, step=1,
        help="Protruyen de la cara de adelante, en piezas sueltas (para pintar de otro color) "
             "— ej. avión, nubes, estrellas pegados sobre la letra encendida.",
    )
    decoraciones_frente = []
    decoraciones_tiene_ams = False
    profundidad_decoracion_mm = 4.0
    if n_decoraciones:
        for i in range(int(n_decoraciones)):
            with st.expander(f"Decoración {i + 1}", expanded=True):
                nombre_deco = st.selectbox("Forma", letras.DECORACIONES, key=f"deco_forma_{i}")
                c1, c2 = st.columns(2)
                tam_mm = c1.slider("Tamaño (mm)", 5, 60, 20, step=1, key=f"deco_tam_{i}")
                x_pct = c2.slider("Posición X (%)", 0, 100, 50, step=5, key=f"deco_x_{i}")
                y_pct = st.slider("Posición Y (%)", 0, 100, 85, step=5, key=f"deco_y_{i}")
                decoraciones_frente.append(
                    {"nombre": nombre_deco, "tam_mm": float(tam_mm), "x_pct": float(x_pct), "y_pct": float(y_pct)}
                )
        profundidad_decoracion_mm = st.slider("Cuánto protruyen las decoraciones (mm)", 1.0, 10.0, 4.0, step=0.5)
        decoraciones_tiene_ams = st.checkbox(
            "Tengo AMS (impresora multicolor) para las decoraciones", value=False,
            help="Con AMS: un solo STL multicolor con todas las decoraciones ya en su posición "
                 "real. Sin AMS: un STL por decoración para pegar a mano después de imprimir.",
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
    elif agregar_nombre and not texto_nombre.strip():
        st.error("Escribí el nombre, o desactivá \"Agregar nombre en cursiva abajo\".")
    else:
        with st.spinner("Armando la geometría 3D (letra hueca + booleanas)..."):
            try:
                r = letras.generar(
                    texto, ruta_ttf, alto_mm=float(alto_mm), profundidad_mm=float(profundidad_mm),
                    espesor_pared_mm=float(espesor_pared_mm),
                    agregar_tapa=agregar_tapa, tapa_espesor_mm=float(tapa_espesor_mm),
                    agujero_cable_diam_mm=float(agujero_cable_diam_mm),
                    agregar_soporte=agregar_soporte, ancho_pata_mm=ancho_pata_mm, alto_pata_mm=alto_pata_mm,
                    agregar_nombre=agregar_nombre, texto_nombre=texto_nombre,
                    ruta_ttf_nombre=ruta_ttf_nombre, alto_nombre_mm=float(alto_nombre_mm),
                    decoraciones_frente=decoraciones_frente,
                    profundidad_decoracion_mm=float(profundidad_decoracion_mm),
                    decoraciones_tiene_ams=decoraciones_tiene_ams,
                )
            except (FileNotFoundError, ValueError) as e:
                st.error(str(e))
                r = None

        if r:
            # la letra (carcasa) ocupa Z=[0, profundidad_mm]; la tapa se exporta en su
            # propio origen (Z=[0, tapa_espesor_mm]) para imprimirse suelta — la corremos
            # a Z=profundidad_mm para el visor, que es donde va pegada de verdad (cierra
            # el hueco abierto de atrás). El soporte de escritorio va rotado 90° respecto
            # de la letra (encastra desde abajo) — mostrarlo "pegado" sin esa rotación
            # daría una posición falsa, así que va en su propio visor aparte.
            piezas_visor = [{"ruta_stl": r["ruta_stl"], "color": "#f5deb3", "nombre": "letra"}]
            if r["pieza_tapa"]:
                piezas_visor.append({
                    "ruta_stl": r["pieza_tapa"]["ruta_stl"], "color": "#9a9a9a", "nombre": "tapa",
                    "offset": (0, 0, float(profundidad_mm)),
                })
            if r["ruta_stl_decoraciones_multicolor"]:
                piezas_visor.append({"ruta_stl": r["ruta_stl_decoraciones_multicolor"], "multicolor": True})
            for i, d in enumerate(r["decoraciones"]):
                piezas_visor.append(
                    {"ruta_stl": d["ruta_stl"], "color": preview3d.color_decoracion(i), "nombre": d["nombre"]}
                )

            html_visor = preview3d.armar_html_visor(piezas_visor)
            if html_visor:
                components.html(html_visor, height=460)
                st.caption("Arrastrá para rotar, scroll para zoom. Letra + tapa (si hay) + decoraciones, en su color real de posición.")
            else:
                st.image(r["ruta_png"], use_container_width=True)

            if r["pieza_soporte"]:
                html_soporte = preview3d.armar_html_visor(
                    [{"ruta_stl": r["pieza_soporte"]["ruta_stl"], "color": "#4a4a4a", "nombre": "soporte"}]
                )
                if html_soporte:
                    st.caption("Base de escritorio (pieza aparte, encastra con la pata desde abajo):")
                    components.html(html_soporte, height=260)

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

            if r["ruta_stl_decoraciones_multicolor"]:
                with open(r["ruta_stl_decoraciones_multicolor"], "rb") as f:
                    st.download_button(
                        "⬇ Descargar STL (decoraciones, multicolor)", f,
                        file_name=os.path.basename(r["ruta_stl_decoraciones_multicolor"]),
                        mime="model/stl", use_container_width=True,
                    )
            for d in r["decoraciones"]:
                with open(d["ruta_stl"], "rb") as f:
                    st.download_button(
                        f"⬇ Descargar STL (decoración: {d['nombre']})", f, file_name=os.path.basename(d["ruta_stl"]),
                        mime="model/stl", use_container_width=True, key=f"dl_{d['ruta_stl']}",
                    )
