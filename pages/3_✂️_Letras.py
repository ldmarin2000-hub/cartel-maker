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

from core import carcasa_hueca, colores, decoraciones, preview3d
from generators import letras
from ui_streamlit import bloque_presets, selector_fuente

TIPOS_DECO = ["Lista", "Emoji/pictograma", "Símbolo/signo"]

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

PRESET_KEYS = [
    "le_texto", "letras_letra_selectbox", "letras_letra_ruta", "le_color_letra", "le_color_tapa", "le_alto_mm",
    "le_agregar_soporte", "le_agregar_tapa",
    "le_agregar_nombre", "le_texto_nombre", "letras_nombre_selectbox", "letras_nombre_ruta", "le_alto_nombre_mm",
    "le_color_nombre", "le_profundidad_nombre_mm", "le_nombre_tiene_ams",
    "le_n_decoraciones",
    *[f"deco_tipo_{i}" for i in range(4)], *[f"deco_forma_{i}" for i in range(4)],
    *[f"deco_emoji_elegido_{i}" for i in range(4)], *[f"deco_emoji_libre_{i}" for i in range(4)],
    *[f"deco_tam_{i}" for i in range(4)],
    *[f"deco_x_{i}" for i in range(4)], *[f"deco_y_{i}" for i in range(4)],
    "le_profundidad_decoracion_mm", "le_decoraciones_tiene_ams",
    "le_profundidad_mm", "le_espesor_pared_mm", "le_tapa_espesor_mm", "le_agujero_cable_diam_mm",
    "le_espesor_cara_mm", "le_soporte_tapa_mm", "le_holgura_tapa_mm", "le_tapa_offset_mm", "le_agujero_cable_lado",
    "le_agujero_manual", "le_agujero_x_pct", "le_agujero_y_pct",
    "le_ancho_pata_mm", "le_alto_pata_mm",
]


@st.cache_data(ttl=120, show_spinner=False)
def _preview_rapido(texto, ruta_ttf, alto_mm, color_letra,
                     agregar_nombre, texto_nombre, ruta_ttf_nombre, alto_nombre_mm, color_nombre, decos_tuple,
                     mostrar_agujero, espesor_pared_mm, agujero_cable_diam_mm,
                     agujero_atras_x_pct, agujero_atras_y_pct, soporte_tapa_mm, holgura_tapa_mm):
    decos = [
        {"nombre": n, "tam_mm": t, "x_pct": x, "y_pct": y, "emoji": e}
        for (n, t, x, y, e) in decos_tuple
    ]
    return letras.preview_rapido(
        texto, ruta_ttf, alto_mm=alto_mm, color_letra=color_letra,
        agregar_nombre=agregar_nombre, texto_nombre=texto_nombre,
        ruta_ttf_nombre=ruta_ttf_nombre, alto_nombre_mm=alto_nombre_mm, color_nombre=color_nombre,
        decoraciones_frente=decos,
        mostrar_agujero=mostrar_agujero, espesor_pared_mm=espesor_pared_mm,
        agujero_cable_diam_mm=agujero_cable_diam_mm,
        agujero_atras_x_pct=agujero_atras_x_pct, agujero_atras_y_pct=agujero_atras_y_pct,
        soporte_tapa_mm=soporte_tapa_mm, holgura_tapa_mm=holgura_tapa_mm,
    )


col_form, col_preview = st.columns([1, 1.3])

with col_form:
    bloque_presets("letras", PRESET_KEYS)

    texto = st.text_input("Letra(s)", value="B", max_chars=3, key="le_texto")

    ruta_ttf = selector_fuente("Fuente", key="letras_letra", default_nombre="Anton", texto_muestra=texto)

    c1, c2 = st.columns(2)
    color_letra = c1.selectbox(
        "Color letra (visor)", colores.NOMBRES,
        index=colores.NOMBRES.index("Amarillo"), key="le_color_letra",
    )
    color_tapa = c2.selectbox(
        "Color tapa (visor)", colores.NOMBRES,
        index=colores.NOMBRES.index("Gris Frío"), key="le_color_tapa",
        help="Un color distinto ayuda a distinguirla de la letra en el visor 3D.",
    )

    alto_mm = st.slider("Alto de la letra (mm)", 50, 250, 150, step=5, key="le_alto_mm")

    agregar_soporte = st.checkbox(
        "Agregar soporte de escritorio", value=True, key="le_agregar_soporte",
        help="Base aparte con una ranura donde encastra a presión una pata que sale de la "
             "letra — para las letras que no se paran solas.",
    )

    agregar_tapa = st.checkbox(
        "Agregar tapa (con agujero para el cable)", value=True, key="le_agregar_tapa",
        help="Mismo contorno que la letra, sólida y fina, para cerrar el hueco después de "
             "meter el LED — con un agujerito cerca del borde inferior para sacar el cable.",
    )

    st.divider()
    agregar_nombre = st.checkbox(
        "Agregar nombre en cursiva abajo", value=False, key="le_agregar_nombre",
        help="Texto macizo (sin luz, sin hueco), pegado al borde de abajo de la letra — como "
             "PIEZA APARTE, para pintarlo de otro color distinto de la letra.",
    )
    texto_nombre, ruta_ttf_nombre, alto_nombre_mm = "", None, 30.0
    color_nombre, profundidad_nombre_mm, nombre_tiene_ams = "Blanco", 10.0, False
    if agregar_nombre:
        texto_nombre = st.text_input("Nombre", value="Bianca", max_chars=20, key="le_texto_nombre")
        ruta_ttf_nombre = selector_fuente(
            "Fuente del nombre", key="letras_nombre", default_nombre="Sacramento", texto_muestra=texto_nombre,
        )
        c1, c2 = st.columns(2)
        alto_nombre_mm = c1.slider("Alto del nombre (mm)", 10, 60, 30, step=2, key="le_alto_nombre_mm")
        color_nombre = c2.selectbox(
            "Color del nombre (visor, no cambia el STL)", colores.NOMBRES,
            index=colores.NOMBRES.index("Blanco"), key="le_color_nombre",
        )
        profundidad_nombre_mm = st.slider(
            "Espesor del nombre (mm)", 3.0, 20.0, 10.0, step=1.0, key="le_profundidad_nombre_mm",
            help="Grosor de la placa del nombre (no necesita ser tan gruesa como la letra — es "
                 "maciza, no hueca).",
        )
        nombre_tiene_ams = st.checkbox(
            "Tengo AMS (impresora multicolor) para el nombre", value=False, key="le_nombre_tiene_ams",
            help="Con AMS: un .3mf combinado (letra + nombre) ya pintado por color, listo para "
                 "imprimir de un saque. Sin AMS: STL aparte para pegar a mano.",
        )

    st.divider()
    n_decoraciones = st.number_input(
        "Decoraciones sueltas en el frente", min_value=0, max_value=4, value=0, step=1, key="le_n_decoraciones",
        help="Protruyen de la cara de adelante, en piezas sueltas (para pintar de otro color) "
             "— ej. avión, nubes, estrellas pegados sobre la letra encendida.",
    )
    decoraciones_frente = []
    decoraciones_tiene_ams = False
    profundidad_decoracion_mm = 4.0
    if n_decoraciones:
        for i in range(int(n_decoraciones)):
            with st.expander(f"Decoración {i + 1}", expanded=True):
                tipo_deco = st.radio("Tipo", TIPOS_DECO, horizontal=True, key=f"deco_tipo_{i}")
                nombre_deco, emoji_deco = "corazon", None
                if tipo_deco == "Lista":
                    nombre_deco = st.selectbox("Forma", letras.DECORACIONES, key=f"deco_forma_{i}")
                else:
                    curados = decoraciones.EMOJIS_CURADOS if tipo_deco == "Emoji/pictograma" else decoraciones.SIGNOS_CURADOS
                    ce1, ce2 = st.columns(2)
                    elegido = ce1.selectbox("Elegí uno", curados, key=f"deco_emoji_elegido_{i}")
                    libre = ce2.text_input(
                        "...o pegá otro", value="", key=f"deco_emoji_libre_{i}", max_chars=4,
                    )
                    emoji_deco = libre.strip() or elegido
                c1, c2 = st.columns(2)
                tam_mm = c1.slider("Tamaño (mm)", 5, 60, 20, step=1, key=f"deco_tam_{i}")
                x_pct = c2.slider("Posición X (%)", 0, 100, 50, step=5, key=f"deco_x_{i}")
                y_pct = st.slider("Posición Y (%)", 0, 100, 85, step=5, key=f"deco_y_{i}")
                decoraciones_frente.append({
                    "nombre": emoji_deco or nombre_deco, "emoji": emoji_deco,
                    "tam_mm": float(tam_mm), "x_pct": float(x_pct), "y_pct": float(y_pct),
                })
        profundidad_decoracion_mm = st.slider(
            "Cuánto protruyen las decoraciones (mm)", 1.0, 10.0, 4.0, step=0.5, key="le_profundidad_decoracion_mm",
        )
        decoraciones_tiene_ams = st.checkbox(
            "Tengo AMS (impresora multicolor) para las decoraciones", value=False, key="le_decoraciones_tiene_ams",
            help="Con AMS: un solo STL multicolor con todas las decoraciones ya en su posición "
                 "real. Sin AMS: un STL por decoración para pegar a mano después de imprimir.",
        )

    with st.expander("Ajustes finos"):
        profundidad_mm = st.slider(
            "Profundidad (mm, ahí adentro va la luz)", 15, 60, 35, step=5, key="le_profundidad_mm",
        )
        espesor_pared_mm = st.slider(
            "Espesor de pared (mm)", 1.5, 5.0, 2.5, step=0.25, key="le_espesor_pared_mm",
            help="Cuánto crece la silueta hacia AFUERA del trazo tal cual sale de la fuente — la "
                 "letra final queda más grande que lo que se ve en la vista rápida, no del mismo "
                 "tamaño. No afecta el hueco ni la cara de adelante (eso es aparte, más abajo).",
        )
        c1, c2 = st.columns(2)
        tapa_espesor_mm = c1.slider(
            "Espesor de la tapa (mm)", 1.5, 6.0, 3.0, step=0.5, disabled=not agregar_tapa, key="le_tapa_espesor_mm",
        )
        agujero_cable_diam_mm = c2.slider(
            "Diámetro del agujero del cable (mm)", 0.0, 12.0, 4.5, step=0.5, disabled=not agregar_tapa,
            key="le_agujero_cable_diam_mm", help="0 = sin agujero.",
        )
        espesor_cara_mm = st.number_input(
            "Espesor de la cara de adelante (mm)", value=2.5, step=0.25, min_value=0.5, disabled=not agregar_tapa,
            key="le_espesor_cara_mm",
            help="Grosor de la cara fina de ADELANTE, por donde se difunde la luz. Más fino deja "
                 "pasar más luz pero es más frágil. No tiene que ver con el espesor de pared de "
                 "arriba. Si un trazo de la letra es más angosto que 2x el soporte de la tapa, esa "
                 "parte queda maciza (avisamos).",
        )
        soporte_tapa_mm = st.number_input(
            "Soporte de la tapa (mm)", value=2.0, step=0.25, min_value=0.25, disabled=not agregar_tapa,
            key="le_soporte_tapa_mm",
            help="Cuánto se achica el hueco principal para formar el escalón donde apoya la tapa "
                 "(y por donde sale el agujero \"atras\"). Tiene que ser mayor que la holgura de la "
                 "tapa, si no la tapa no tiene contra qué topar.",
        )
        holgura_tapa_mm = st.number_input(
            "Holgura de la tapa (mm)", value=1.0, step=0.25, min_value=0.0, disabled=not agregar_tapa,
            key="le_holgura_tapa_mm",
            help="Define el tamaño real de la tapa (achicada esto respecto del contorno). Tiene "
                 "que ser MENOR que el soporte de la tapa, si no la tapa entra derecho sin topar "
                 "contra nada.",
        )
        tapa_offset_mm = st.number_input(
            "Cuánto sobresale/entra la tapa (mm)", value=0.0, step=0.5, disabled=not agregar_tapa,
            key="le_tapa_offset_mm",
            help="0 = tapa exacto al ras del borde de atrás. Positivo = sobresale esos mm por "
                 "atrás. Negativo = entra esos mm, queda un poco adentro (con un marquito de la "
                 "carcasa alrededor).",
        )
        LADOS_AGUJERO = ["atras", "arriba", "abajo", "izquierda", "derecha", "ninguno"]
        agujero_cable_lado = st.radio(
            "Lado del agujero del cable", LADOS_AGUJERO, horizontal=True,
            disabled=not agregar_tapa or agujero_cable_diam_mm <= 0, key="le_agujero_cable_lado",
            help="\"atras\": por el canto de atrás (el rebaje donde apoya la tapa). Los otros 4: "
                 "por la pared lateral de ese lado. Va siempre en la carcasa, no en la tapa.",
        )
        agujero_deshabilitado = not agregar_tapa or agujero_cable_diam_mm <= 0 or agujero_cable_lado != "atras"
        agujero_manual = st.checkbox(
            "Elegir a mano dónde va el agujero \"atras\"", value=False,
            disabled=agujero_deshabilitado, key="le_agujero_manual",
            help="Si no, se busca un lugar automático cerca del borde de abajo. La marca celeste "
                 "en la vista rápida (a la derecha) muestra dónde va a caer.",
        )
        c1, c2 = st.columns(2)
        agujero_x_pct = c1.slider(
            "Posición X (%)", 0, 100, 50, disabled=agujero_deshabilitado or not agujero_manual,
            key="le_agujero_x_pct",
        )
        agujero_y_pct = c2.slider(
            "Posición Y (%)", 0, 100, 5, disabled=agujero_deshabilitado or not agujero_manual,
            key="le_agujero_y_pct",
        )
        c1, c2 = st.columns(2)
        ancho_pata_mm = c1.slider(
            "Ancho de la pata (mm)", 15, 80, 40, step=5, disabled=not agregar_soporte, key="le_ancho_pata_mm",
        )
        alto_pata_mm = c2.slider(
            "Alto de la pata (mm)", 5, 30, 15, step=1, disabled=not agregar_soporte, key="le_alto_pata_mm",
        )

    generar_click = st.button("Generar letra", type="primary", use_container_width=True)

with col_preview:
    if texto.strip():
        decos_tuple = tuple(
            (d["nombre"], d["tam_mm"], d["x_pct"], d["y_pct"], d.get("emoji")) for d in decoraciones_frente
        )
        mostrar_agujero_preview = agregar_tapa and agujero_cable_diam_mm > 0 and agujero_cable_lado == "atras"
        png_rapido, ancho_rapido, alto_rapido = _preview_rapido(
            texto, ruta_ttf, float(alto_mm), color_letra,
            agregar_nombre, texto_nombre, ruta_ttf_nombre, float(alto_nombre_mm), color_nombre, decos_tuple,
            mostrar_agujero_preview, float(espesor_pared_mm), float(agujero_cable_diam_mm),
            float(agujero_x_pct) if agujero_manual else None, float(agujero_y_pct) if agujero_manual else None,
            float(soporte_tapa_mm), float(holgura_tapa_mm),
        )
        if png_rapido:
            st.image(
                png_rapido,
                caption=f"Vista rápida (2D) — ~{ancho_rapido:.0f} x {alto_rapido:.0f} mm. "
                        f"Al generar sale la malla 3D real (hueca, con soporte/tapa si hay).",
                use_container_width=True,
            )
            st.divider()

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
                    agujero_cable_diam_mm=float(agujero_cable_diam_mm), agujero_cable_lado=agujero_cable_lado,
                    agujero_atras_x_pct=float(agujero_x_pct) if agujero_manual else None,
                    agujero_atras_y_pct=float(agujero_y_pct) if agujero_manual else None,
                    espesor_cara_mm=float(espesor_cara_mm), soporte_tapa_mm=float(soporte_tapa_mm),
                    holgura_tapa_mm=float(holgura_tapa_mm), tapa_offset_mm=float(tapa_offset_mm),
                    agregar_soporte=agregar_soporte, ancho_pata_mm=ancho_pata_mm, alto_pata_mm=alto_pata_mm,
                    agregar_nombre=agregar_nombre, texto_nombre=texto_nombre,
                    ruta_ttf_nombre=ruta_ttf_nombre, alto_nombre_mm=float(alto_nombre_mm),
                    profundidad_nombre_mm=float(profundidad_nombre_mm), nombre_tiene_ams=nombre_tiene_ams,
                    decoraciones_frente=decoraciones_frente,
                    profundidad_decoracion_mm=float(profundidad_decoracion_mm),
                    decoraciones_tiene_ams=decoraciones_tiene_ams,
                )
            except (FileNotFoundError, ValueError) as e:
                st.error(str(e))
                r = None

        if r:
            # la letra (carcasa) ocupa Z=[0, profundidad_mm]; la tapa se exporta en su
            # propio origen (Z=[0, tapa_espesor_mm]) para imprimirse suelta -- la corremos
            # al mismo Z donde arranca el escalón/rebaje (calcular_z_ledge), que es donde
            # encastra de verdad (no siempre al ras del borde de atrás: tapa_offset_mm
            # puede hacer que sobresalga o quede un poco adentro). El soporte de
            # escritorio va rotado 90° respecto de la letra (encastra desde abajo) —
            # mostrarlo "pegado" sin esa rotación daría una posición falsa, así que va en
            # su propio visor aparte.
            z_tapa = carcasa_hueca.calcular_z_ledge(
                float(profundidad_mm), float(espesor_cara_mm), float(tapa_espesor_mm), float(tapa_offset_mm)
            )
            piezas_visor = [{"ruta_stl": r["ruta_stl"], "color": colores.hex_de(color_letra), "nombre": "letra"}]
            if r["pieza_tapa"]:
                piezas_visor.append({
                    "ruta_stl": r["pieza_tapa"]["ruta_stl"], "color": colores.hex_de(color_tapa), "nombre": "tapa",
                    "offset": (0, 0, z_tapa),
                })
            if r["pieza_nombre"]:
                piezas_visor.append({
                    "ruta_stl": r["pieza_nombre"]["ruta_stl"], "color": colores.hex_de(color_nombre), "nombre": "nombre",
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
                st.caption("Arrastrá para rotar, scroll para zoom. Letra + tapa/nombre/decoraciones (si hay), en su color real de posición.")
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

            if r["ruta_3mf_nombre"]:
                with open(r["ruta_3mf_nombre"], "rb") as f:
                    st.download_button(
                        "⬇ 3MF (letra + nombre, para AMS, recomendado)", f, file_name=os.path.basename(r["ruta_3mf_nombre"]),
                        mime="model/3mf", use_container_width=True, type="primary",
                    )
                st.caption("Abre directo en Bambu Studio con los colores ya puestos — no hace falta dividir nada.")
            if r["pieza_nombre"]:
                n = r["pieza_nombre"]
                if not n["watertight"]:
                    st.caption("Nombre: no quedó perfectamente watertight, revisalo antes de imprimir.")
                with open(n["ruta_stl"], "rb") as f:
                    st.download_button(
                        "⬇ Descargar STL (nombre)", f, file_name=os.path.basename(n["ruta_stl"]),
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
