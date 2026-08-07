#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pages/1_🔥_Neon.py
---------------------
Página de Streamlit para el generador de carteles de neón. Es solo la capa
visual: toda la lógica real vive en generators/neon.py (generar()), la
misma que usa la versión de consola (main.py).
"""

import os

import streamlit as st
import streamlit.components.v1 as components

from core import colores, geometry, preview3d
from generators import neon
from ui_streamlit import bloque_presets, selector_fuente

st.set_page_config(page_title="Cartel de neón · Cartel Maker", page_icon="🔥", layout="wide")

st.title("🔥 Cartel de neón (texto trazado)")
st.caption(neon.DESCRIPCION)

PRESET_KEYS = [
    "ne_texto", "neon_selectbox", "neon_ruta", "ne_color_tubo", "ne_alto_mm", "ne_modo_led",
    "ne_led_ancho_mm", "ne_led_prof_mm", "ne_redondeo_mm", "ne_fondo",
    "ne_agregar_canal_salida", "ne_cable_ancho_mm", "ne_agregar_agujeros", "ne_agujero_cable_diam_mm",
    "ne_tipo_montaje", "ne_n_orejas_montaje", "ne_ancho_pata_mm", "ne_alto_pata_mm",
]

col_form, col_preview = st.columns([1, 1.3])

with col_form:
    bloque_presets("neon", PRESET_KEYS)

    texto = st.text_input("Texto", value="Mis 15", key="ne_texto")

    ruta_ttf = selector_fuente("Fuente", key="neon", default_nombre="Monoton", texto_muestra=texto)

    color_tubo = st.selectbox(
        "Color del tubo LED (visor, no cambia el STL)", colores.NOMBRES,
        index=colores.NOMBRES.index("Rosa Fluor"), key="ne_color_tubo",
        help="Solo para ver cómo queda en el visor 3D — el LED de verdad se elige aparte al comprar la tira.",
    )

    alto_mm = st.slider("Alto del texto (mm)", min_value=20, max_value=250, value=90, step=5, key="ne_alto_mm")
    modo_led = st.radio(
        "Modo LED", ["neon", "ws2812"], horizontal=True, key="ne_modo_led",
        help="neon: tubo flex, sigue curvas cerradas. ws2812: tira rígida de costado, "
             "necesita letras más rectas.",
    )

    default_ancho_led = 6.0 if modo_led == "neon" else 10.0
    default_prof_canal = 8.0 if modo_led == "neon" else 4.0
    with st.expander("Ajustes finos"):
        led_ancho_mm = st.number_input(
            "Ancho del LED (mm)", value=default_ancho_led, step=0.5, key="ne_led_ancho_mm",
        )
        led_prof_mm = st.number_input(
            "Profundidad del canal (mm)", value=default_prof_canal, step=0.5, key="ne_led_prof_mm",
        )
        redondeo_mm = st.slider(
            "Redondeo de bordes (mm)", 0.0, 3.0, 0.5, step=0.1, key="ne_redondeo_mm",
            help="Suaviza las esquinas filosas que a veces deja el trazado en curvas cerradas "
                 "de la fuente. 0 = sin suavizar. Valores muy altos pueden achicar detalles finos.",
        )
        fondo = st.radio(
            "Placa de fondo", list(geometry.FONDOS_VALIDOS), horizontal=True, key="ne_fondo",
            help="contorno: sigue las letras, gasta poco material pero las letras separadas "
                 "quedan unidas solo por puentes finos. rect_hundido: rectángulo macizo, el canal "
                 "queda como zanja (más rígido, gasta más). rect_plano: rectángulo fino con las "
                 "letras en relieve — poco material y base bien conectada.",
        )
        st.divider()
        agregar_canal_salida = st.checkbox(
            "Agregar canalcito de salida", value=True, key="ne_agregar_canal_salida",
            help="Un canalcito recto desde la punta más conveniente del recorrido hasta "
                 "afuera de la placa, para sacar el cable de alimentación general.",
        )
        cable_ancho_mm = st.number_input(
            "Ancho del canalcito de salida (mm)", value=4.0, step=0.5,
            disabled=not agregar_canal_salida, key="ne_cable_ancho_mm",
        )
        agregar_agujeros = st.checkbox(
            "Agregar agujeros de conexión", value=True, key="ne_agregar_agujeros",
            help="Un agujerito hacia atrás en cada punta suelta del recorrido (entre letras, y "
                 "también en la salida general) para poder soldar/conectar el cable ahí — el "
                 "cable entre letras corre pegado a la parte de atrás del cartel.",
        )
        agujero_cable_diam_mm = st.number_input(
            "Diámetro de los agujeros (mm)", value=5.0, step=0.5,
            disabled=not agregar_agujeros, key="ne_agujero_cable_diam_mm",
        )
        tipo_montaje = st.radio(
            "Montaje", list(neon.TIPOS_MONTAJE), horizontal=True, key="ne_tipo_montaje",
            help="colgado: orejas arriba con agujero bocallave para un tornillo. escritorio: "
                 "una pata abajo que encastra a presión en una base impresa aparte, para que se "
                 "pare solo. ninguno: sin nada de esto.",
        )
        n_orejas_montaje = st.slider(
            "Cantidad de orejas de montaje", 1, 4, 2,
            disabled=tipo_montaje != "colgado", key="ne_n_orejas_montaje",
        )
        ancho_pata_mm = st.number_input(
            "Ancho de la pata (mm)", value=40.0, step=5.0,
            disabled=tipo_montaje != "escritorio", key="ne_ancho_pata_mm",
        )
        alto_pata_mm = st.number_input(
            "Alto de la pata (mm)", value=15.0, step=1.0,
            disabled=tipo_montaje != "escritorio", key="ne_alto_pata_mm",
        )
        st.caption("Si el cartel es más ancho que la Bambu A1, se parte en módulos con cola de milano automáticamente.")

    generar_click = st.button("Generar cartel", type="primary", use_container_width=True)

with col_preview:
    if not generar_click:
        st.info("Completá el formulario y apretá **Generar cartel**.")
    elif not texto.strip():
        st.error("Escribí algún texto primero.")
    else:
        with st.spinner("Generando el trazado y la malla 3D..."):
            try:
                r = neon.generar(
                    texto=texto, ruta_ttf=ruta_ttf, alto_mm=float(alto_mm), modo_led=modo_led,
                    led_ancho_mm=led_ancho_mm, led_prof_mm=led_prof_mm, fondo=fondo, redondeo_mm=redondeo_mm,
                    agregar_canal_salida=agregar_canal_salida, cable_ancho_mm=cable_ancho_mm,
                    agregar_agujeros=agregar_agujeros, agujero_cable_diam_mm=agujero_cable_diam_mm,
                    tipo_montaje=tipo_montaje, n_orejas_montaje=n_orejas_montaje,
                    ancho_pata_mm=ancho_pata_mm, alto_pata_mm=alto_pata_mm,
                )
            except (FileNotFoundError, ValueError) as e:
                st.error(str(e))
                r = None

        if r:
            # los módulos (si el cartel se partió) quedan en su posición real de X/Y
            # (por eso encastran con cola de milano) — combinan derecho en un solo visor.
            color_tubo_hex = colores.hex_de(color_tubo)
            piezas_visor = [
                {"ruta_stl": p["ruta_stl"], "color": color_tubo_hex, "nombre": f"modulo_{p['indice']}"}
                for p in r["piezas"]
            ]
            html_visor = preview3d.armar_html_visor(piezas_visor)
            if html_visor:
                components.html(html_visor, height=460)
                st.caption("Arrastrá para rotar, scroll para zoom.")
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
            c1.metric("Ancho total", f"{r['ancho_total_mm']:.0f} mm")
            c2.metric("Alto total", f"{r['alto_total_mm']:.0f} mm")
            c3.metric("Trazos", r["trazos"])

            for nota in r["info"]:
                st.info(nota)
            for aviso in r["avisos"]:
                st.warning(aviso)

            if r["entra_a1"]:
                st.success(r["mensaje_a1"])
            else:
                st.warning(r["mensaje_a1"])

            for p in r["piezas"]:
                etiqueta = f"Módulo {p['indice']}/{p['de']}" if p["de"] > 1 else "STL"
                if not p["watertight"]:
                    st.caption(f"{etiqueta}: no quedó perfectamente watertight (modo multi-cuerpo de respaldo), pero igual imprime bien.")
                with open(p["ruta_stl"], "rb") as f:
                    st.download_button(
                        f"⬇ Descargar {etiqueta} ({os.path.basename(p['ruta_stl'])})", f,
                        file_name=os.path.basename(p["ruta_stl"]), mime="model/stl",
                        use_container_width=True, key=p["ruta_stl"],
                    )

            if r["pieza_soporte"]:
                s = r["pieza_soporte"]
                if not s["watertight"]:
                    st.caption("Base de escritorio: no quedó perfectamente watertight, revisala antes de imprimir.")
                with open(s["ruta_stl"], "rb") as f:
                    st.download_button(
                        f"⬇ Descargar base de escritorio ({os.path.basename(s['ruta_stl'])})", f,
                        file_name=os.path.basename(s["ruta_stl"]), mime="model/stl",
                        use_container_width=True, key=s["ruta_stl"],
                    )
