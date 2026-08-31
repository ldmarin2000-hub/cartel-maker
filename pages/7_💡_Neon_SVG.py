#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pages/7_💡_Neon_SVG.py
---------------------------
Página de Streamlit para el generador de carteles de neón a partir de un
SVG/dibujo de línea (en vez de texto con fuente). Es solo la capa visual:
toda la lógica real vive en generators/neon_svg.py (generar()), la misma
que usa la versión de consola (main.py).
"""

import os

import streamlit as st
import streamlit.components.v1 as components

from core import colores, geometry, preview3d
from generators import neon_svg
from ui_streamlit import bloque_presets

st.set_page_config(page_title="Neón desde SVG · Cartel Maker", page_icon="💡", layout="wide")

st.title("💡 Cartel de neón (desde SVG/dibujo)")
st.caption(neon_svg.DESCRIPCION)
st.info(
    "Subí un SVG de línea (un ícono, un logo, una firma o dibujo vectorizado) — se marca el "
    "medio de cada trazo del dibujo y ahí va el canal del LED, igual que con las letras. "
    "Funciona mejor con dibujos de trazo más o menos parejo (como un ícono lineal); una "
    "ilustración con áreas rellenas grandes (una silueta sólida) no da un buen resultado, "
    "porque no tiene un 'medio del camino' claro para seguir."
)

PRESET_KEYS = [
    "nsvg_color_tubo", "nsvg_alto_mm", "nsvg_modo_led",
    "nsvg_led_ancho_mm", "nsvg_led_prof_mm", "nsvg_redondeo_mm", "nsvg_fondo",
    "nsvg_raster_px", "nsvg_min_objeto_px", "nsvg_poda_frac",
    "nsvg_agregar_canal_salida", "nsvg_cable_ancho_mm", "nsvg_agregar_agujeros", "nsvg_agujero_cable_diam_mm",
    "nsvg_tipo_montaje", "nsvg_n_orejas_montaje", "nsvg_ancho_pata_mm", "nsvg_alto_pata_mm",
    "nsvg_puentes_bajitos", "nsvg_permitir_corte",
]


@st.cache_data(ttl=120, show_spinner=False)
def _preview_rapido(ruta_svg, alto_mm, modo_led, led_ancho_mm, fondo, redondeo_mm,
                     raster_px, min_objeto_px, poda_frac,
                     agregar_canal_salida, cable_ancho_mm, agregar_agujeros, agujero_cable_diam_mm,
                     tipo_montaje, n_orejas_montaje, ancho_pata_mm, alto_pata_mm,
                     puentes_altura_completa, ancho_max_modulo_mm):
    return neon_svg.preview_rapido(
        ruta_svg, alto_mm, modo_led, led_ancho_mm=led_ancho_mm, fondo=fondo, redondeo_mm=redondeo_mm,
        raster_px=raster_px, min_objeto_px=min_objeto_px, poda_frac=poda_frac,
        agregar_canal_salida=agregar_canal_salida, cable_ancho_mm=cable_ancho_mm,
        agregar_agujeros=agregar_agujeros, agujero_cable_diam_mm=agujero_cable_diam_mm,
        tipo_montaje=tipo_montaje, n_orejas_montaje=n_orejas_montaje,
        ancho_pata_mm=ancho_pata_mm, alto_pata_mm=alto_pata_mm,
        puentes_altura_completa=puentes_altura_completa, ancho_max_modulo_mm=ancho_max_modulo_mm,
    )


col_form, col_preview = st.columns([1, 1.3])

with col_form:
    bloque_presets("neon_svg", PRESET_KEYS)

    subido = st.file_uploader("Dibujo (SVG)", type=["svg"], key="nsvg_svg")
    ruta_svg = None
    if subido is not None:
        os.makedirs("output", exist_ok=True)
        ruta_svg = os.path.join("output", f"_subido_nsvg_{subido.name}")
        with open(ruta_svg, "wb") as f:
            f.write(subido.getvalue())

    color_tubo = st.selectbox(
        "Color del tubo LED (visor, no cambia el STL)", colores.NOMBRES,
        index=colores.NOMBRES.index("Rosa Fluor"), key="nsvg_color_tubo",
        help="Solo para ver cómo queda en el visor 3D — el LED de verdad se elige aparte al comprar la tira.",
    )

    alto_mm = st.slider("Alto del dibujo (mm)", min_value=20, max_value=250, value=100, step=5, key="nsvg_alto_mm")
    modo_led = st.radio(
        "Modo LED", ["neon", "ws2812"], horizontal=True, key="nsvg_modo_led",
        help="neon: tubo flex, sigue curvas cerradas. ws2812: tira rígida de costado, "
             "necesita trazos más rectos.",
    )

    default_ancho_led = 6.0 if modo_led == "neon" else 10.0
    default_prof_canal = 8.0 if modo_led == "neon" else 4.0
    with st.expander("Ajustes finos"):
        led_ancho_mm = st.number_input(
            "Ancho del LED (mm)", value=default_ancho_led, step=0.5, key="nsvg_led_ancho_mm",
        )
        led_prof_mm = st.number_input(
            "Profundidad del canal (mm)", value=default_prof_canal, step=0.5, key="nsvg_led_prof_mm",
        )
        redondeo_mm = st.slider(
            "Redondeo de bordes (mm)", 0.0, 3.0, 0.5, step=0.1, key="nsvg_redondeo_mm",
            help="Suaviza las esquinas filosas que a veces deja el trazado en curvas cerradas. "
                 "0 = sin suavizar. Valores muy altos pueden achicar detalles finos.",
        )
        fondo = st.radio(
            "Placa de fondo", list(geometry.FONDOS_VALIDOS), horizontal=True, key="nsvg_fondo",
            help="contorno: sigue el dibujo, gasta poco material pero las partes separadas "
                 "quedan unidas solo por puentes finos. rect_hundido: rectángulo macizo, el canal "
                 "queda como zanja (más rígido, gasta más). rect_plano: rectángulo fino con el "
                 "dibujo en relieve — poco material y base bien conectada.",
        )
        puentes_bajitos = st.checkbox(
            "Puentes bajitos (como las orejas de montaje)", value=False,
            disabled=fondo != "contorno", key="nsvg_puentes_bajitos",
            help="Los puentes que sueldan partes sueltas salen por defecto con la altura "
                 "completa del cartel (se notan como una pared más). Tildando esto, quedan solo "
                 "con la altura de la base — se notan mucho menos, igual que ya pasa con las "
                 "orejas de montaje.",
        )
        st.divider()
        raster_px = st.slider(
            "Resolución de trazado (px)", 150, 800, 500, step=50, key="nsvg_raster_px",
            help="Cuántos píxeles de alto se usan para 'leer' el SVG antes de sacarle el "
                 "esqueleto. Más resolución = trazos más suaves y detalle más fino, pero tarda "
                 "más. Subila si un dibujo con curvas finas sale con escalones/entrecortado.",
        )
        min_objeto_px = st.slider(
            "Descartar manchitas de ruido (px)", 0, 60, 12, step=2, key="nsvg_min_objeto_px",
            help="Los SVG trazados desde un dibujo escaneado a veces dejan puntitos sueltos "
                 "(ruido del trazado). Se descarta cualquier mancha con menos píxeles que esto. "
                 "Si al dibujo le faltan detalles chicos que sí querés, bajalo.",
        )
        poda_frac = st.slider(
            "Sensibilidad a detalles chicos (%)", 0.5, 8.0, 2.0, step=0.5, key="nsvg_poda_frac",
            help="Un trazo más corto que este % del ALTO TOTAL del dibujo se descarta por "
                 "'pelito' del esqueletizado. Si el dibujo mezcla partes grandes y chicas (un "
                 "logo con un emblema grande y texto chico, por ejemplo), las partes chicas "
                 "pueden quedar por debajo del umbral y faltar en el resultado — bajá este "
                 "valor en ese caso. Subilo si aparecen pelitos/ruido de más.",
        ) / 100
        st.divider()
        agregar_canal_salida = st.checkbox(
            "Agregar canalcito de salida", value=True, key="nsvg_agregar_canal_salida",
            help="Un canalcito recto desde la punta más conveniente del recorrido hasta "
                 "afuera de la placa, para sacar el cable de alimentación general.",
        )
        cable_ancho_mm = st.number_input(
            "Ancho del canalcito de salida (mm)", value=4.0, step=0.5,
            disabled=not agregar_canal_salida, key="nsvg_cable_ancho_mm",
        )
        agregar_agujeros = st.checkbox(
            "Agregar agujeros de conexión", value=True, key="nsvg_agregar_agujeros",
            help="Un agujerito hacia atrás en cada punta suelta del recorrido para poder "
                 "soldar/conectar el cable ahí — el cable entre tramos corre pegado a la parte "
                 "de atrás del cartel.",
        )
        agujero_cable_diam_mm = st.number_input(
            "Diámetro de los agujeros (mm)", value=5.0, step=0.5,
            disabled=not agregar_agujeros, key="nsvg_agujero_cable_diam_mm",
        )
        tipo_montaje = st.radio(
            "Montaje", list(neon_svg.TIPOS_MONTAJE), horizontal=True, key="nsvg_tipo_montaje",
            help="colgado: orejas arriba con agujero bocallave para un tornillo. escritorio: "
                 "una pata abajo que encastra a presión en una base impresa aparte, para que se "
                 "pare solo. ninguno: sin nada de esto.",
        )
        n_orejas_montaje = st.slider(
            "Cantidad de orejas de montaje", 1, 4, 2,
            disabled=tipo_montaje != "colgado", key="nsvg_n_orejas_montaje",
        )
        ancho_pata_mm = st.number_input(
            "Ancho de la pata (mm)", value=40.0, step=5.0,
            disabled=tipo_montaje != "escritorio", key="nsvg_ancho_pata_mm",
        )
        alto_pata_mm = st.number_input(
            "Alto de la pata (mm)", value=15.0, step=1.0,
            disabled=tipo_montaje != "escritorio", key="nsvg_alto_pata_mm",
        )
        permitir_corte = st.checkbox(
            "Partir en módulos si no entra en la cama", value=True, key="nsvg_permitir_corte",
            help="Si el cartel es más ancho que la Bambu A1, se parte en módulos con cola de "
                 "milano para que entren en la cama. Destildando esto, se imprime en una sola "
                 "pieza sin importar el tamaño (vas a tener que cortarlo/imprimirlo vos por otro lado).",
        )
        st.caption("Si el cartel es más ancho que la Bambu A1, se parte en módulos con cola de milano automáticamente.")

    generar_click = st.button("Generar cartel", type="primary", use_container_width=True)

with col_preview:
    if ruta_svg:
        png_rapido, ancho_rapido, alto_rapido = _preview_rapido(
            ruta_svg, float(alto_mm), modo_led, led_ancho_mm, fondo, redondeo_mm,
            raster_px, min_objeto_px, poda_frac,
            agregar_canal_salida, cable_ancho_mm, agregar_agujeros, agujero_cable_diam_mm,
            tipo_montaje, n_orejas_montaje, ancho_pata_mm, alto_pata_mm,
            not puentes_bajitos, None if permitir_corte else float("inf"),
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
        st.info("Subí un SVG y apretá **Generar cartel**.")
    elif not ruta_svg:
        st.error("Subí un archivo SVG primero.")
    else:
        with st.spinner("Trazando el dibujo y generando la malla 3D..."):
            try:
                r = neon_svg.generar(
                    ruta_svg=ruta_svg, alto_mm=float(alto_mm), modo_led=modo_led,
                    led_ancho_mm=led_ancho_mm, led_prof_mm=led_prof_mm, fondo=fondo, redondeo_mm=redondeo_mm,
                    raster_px=raster_px, min_objeto_px=min_objeto_px, poda_frac=poda_frac,
                    agregar_canal_salida=agregar_canal_salida, cable_ancho_mm=cable_ancho_mm,
                    agregar_agujeros=agregar_agujeros, agujero_cable_diam_mm=agujero_cable_diam_mm,
                    tipo_montaje=tipo_montaje, n_orejas_montaje=n_orejas_montaje,
                    ancho_pata_mm=ancho_pata_mm, alto_pata_mm=alto_pata_mm,
                    puentes_altura_completa=not puentes_bajitos,
                    ancho_max_modulo_mm=None if permitir_corte else float("inf"),
                )
            except (FileNotFoundError, ValueError) as e:
                st.error(str(e))
                r = None

        if r:
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
