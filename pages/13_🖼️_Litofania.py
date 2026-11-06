#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pages/13_🖼️_Litofania.py
-------------------------
Página de Streamlit para el generador de litofanías (placa plana). Es solo la capa visual: toda la lógica
vive en generators/litofania.py (construir_mapas / avisos_y_notas / generar), core/litofania.py (L1-L3) y
core/litofania_simulacion.py (L5), la misma que usa la versión de consola (main.py). Python puro.

La vista principal es la SIMULACIÓN A CONTRALUZ: cómo se va a ver la placa encendida con los parámetros
actuales, se recalcula al mover cualquier control (sin armar la malla). El STL se arma al apretar "Generar STL".
"""

import hashlib
import json
import os

import streamlit as st
import streamlit.components.v1 as components

from core import colores, litofania as lf, litofania_simulacion as simulacion, pieza, preview3d
from generators import litofania as gen
from ui_streamlit import bloque_presets, resolver_archivo_subido

st.set_page_config(page_title="Litofanía · Cartel Maker", page_icon="🖼️", layout="wide")

st.title("🖼️ Litofanía")
st.caption(gen.DESCRIPCION)

CARPETA_SALIDA = os.path.join("output", "litofania")
RESOLUCION_VISTA_3D = 1.5      # px/mm de la malla que muestra el visor: liviana (~2 MB); el STL descargable es el completo

ALTO_FOTO, ALTO_FIJO = "El de la foto", "Fijarlo"
CAPAS_LABELS = {"Sin ajustar a capas": None, "0,08 mm": 0.08, "0,12 mm": 0.12, "0,16 mm": 0.16, "0,20 mm": 0.2}
CARAS_LABELS = {
    "Relieve — la foto se lee mirando el lado del relieve": "relieve",
    "Lisa — la foto se lee mirando el lado liso": "plana",
}
DIAGONALES_LABELS = {"Adaptativa (recomendada)": "adaptativa", "Fija": "fija"}

# valor por defecto de cada widget (y keys que guardan los presets). Los números van SIEMPRE como float: un
# preset viejo pudo guardar enteros y los campos con rango decimal no los aceptan.
DEFAULTS = {
    "lf_ancho": 100.0, "lf_alto_modo": ALTO_FOTO, "lf_alto": 100.0, "lf_dx": 0.0, "lf_dy": 0.0,
    "lf_px": float(lf.PX_POR_MM_DEFAULT),
    "lf_grosor_min": float(lf.GROSOR_MIN_DEFAULT), "lf_grosor_max": float(lf.GROSOR_MAX_DEFAULT),
    "lf_luz_pct": float(lf.LUZ_MINIMA_DEFAULT * 100),
    "lf_invertir": False, "lf_cara": list(CARAS_LABELS)[0], "lf_capa": list(CAPAS_LABELS)[0],
    "lf_brillo": 0.0, "lf_contraste": 1.0, "lf_gamma": 1.0, "lf_auto_niveles": False, "lf_realce_local": False,
    "lf_suavizado": 0.0,
    "lf_compensar": True, "lf_diagonal": list(DIAGONALES_LABELS)[0], "lf_boquilla": float(gen.BOQUILLA_DEFAULT_MM),
    "lf_verificar": True,
    "lf_color_visor": "Blanco",
}
PRESET_KEYS = list(DEFAULTS)    # la foto subida NO entra en el preset (igual que en el resto de las páginas)

for _key, _valor in DEFAULTS.items():
    st.session_state.setdefault(_key, _valor)
    if isinstance(_valor, float):
        st.session_state[_key] = float(st.session_state[_key])
if st.session_state["lf_color_visor"] not in colores.NOMBRES:     # un preset con un color que ya no existe
    st.session_state["lf_color_visor"] = DEFAULTS["lf_color_visor"]


@st.cache_data(show_spinner="Simulando la luz...", max_entries=24)
def _vista_previa(ruta, firma_archivo, kw_mapas, cara_visible, boquilla_mm):
    """L1 -> L2 -> L5 (sin armar la malla): la simulación a contraluz, la foto en grises y los avisos. `firma_archivo`
    no se usa adentro: está para que un archivo distinto en la misma ruta no devuelva el preview del anterior."""
    try:
        mapa_brillo, mapa_grosor, tiempos = gen.construir_mapas(ruta, **kw_mapas)
    except (ValueError, FileNotFoundError) as e:
        return {"error": str(e)}
    sim = simulacion.simular_contraluz(mapa_grosor)
    analisis = gen.avisos_y_notas(mapa_brillo, mapa_grosor, cara_visible=cara_visible, boquilla_mm=boquilla_mm)
    return {
        "error": None,
        "imagen_luz": simulacion.simulacion_a_imagen(sim),
        "imagen_brillo": lf.mapa_a_imagen(mapa_brillo),
        "analisis": analisis,
        "ancho_mm": mapa_grosor.ancho_mm, "alto_mm": mapa_grosor.alto_mm,
        "ancho_px": mapa_grosor.ancho_px, "alto_px": mapa_grosor.alto_px, "px_por_mm": mapa_grosor.px_por_mm,
        "niveles": mapa_grosor.niveles, "px_saturados": sim.px_saturados,
        "grosor_min": mapa_grosor.grosor_min_efectivo, "grosor_max": mapa_grosor.grosor_max_efectivo,
        "media_luz_mm": mapa_grosor.media_luz_mm,
    }


def _firma_de_archivo(ruta):
    with open(ruta, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def _prefijo_de(ruta):
    """El nombre de la foto subida, sin el prefijo con el que la guarda `resolver_archivo_subido`."""
    base = os.path.splitext(os.path.basename(ruta))[0].replace("_subido_lf_", "", 1)
    return pieza.nombre_archivo(base, default="litofania")


col_form, col_resultado = st.columns([1, 1.4])

with col_form:
    bloque_presets("litofania", PRESET_KEYS)

    foto_subida = st.file_uploader(
        "Foto (PNG o JPG)", type=["png", "jpg", "jpeg"], key="lf_foto",
        help="Una foto con buen contraste. La proporción de la foto fija la de la placa (o se recorta). "
             "No entra en el preset: al cargar uno hay que volver a subirla.",
    )
    ruta_foto = resolver_archivo_subido(foto_subida, "lf_foto", "_subido_lf")

    st.subheader("Tamaño")
    st.number_input("Ancho de la placa (mm)", 10.0, 400.0, step=5.0, key="lf_ancho",
                    help="La A1 imprime hasta 256 mm; más de 240 ya es justo. Si pasás, te aviso.")
    alto_modo = st.radio("Alto", [ALTO_FOTO, ALTO_FIJO], horizontal=True, key="lf_alto_modo",
                         help="'El de la foto' respeta su proporción. Si lo fijás con otra proporción, la foto se "
                              "recorta (nunca se estira).")
    alto_mm, desplazamiento = None, (0.0, 0.0)
    if alto_modo == ALTO_FIJO:
        alto_mm = float(st.number_input("Alto de la placa (mm)", 10.0, 400.0, step=5.0, key="lf_alto"))
        cx, cy = st.columns(2)
        dx = cx.slider("Mover el recorte ← →", -1.0, 1.0, step=0.05, key="lf_dx")
        dy = cy.slider("Mover el recorte ↑ ↓", -1.0, 1.0, step=0.05, key="lf_dy")
        desplazamiento = (float(dx), float(dy))
    st.slider("Resolución (píxeles por mm)", float(lf.PX_POR_MM_MIN), float(lf.PX_POR_MM_MAX), step=0.5, key="lf_px",
              help="4 px/mm (0,25 mm por píxel) ya aprovecha todo el detalle de una boquilla de 0,4 mm. Más no se "
                   "ve y el archivo pesa mucho más.")

    st.subheader("Grosor y luz")
    g1, g2 = st.columns(2)
    g1.slider("Grosor de lo más claro (mm)", 0.2, 3.0, step=0.05, key="lf_grosor_min", format="%.2f",
              help="Donde la foto es blanca: la zona más fina, la que deja pasar más luz. Menos de 0,6 mm es frágil.")
    g2.slider("Grosor de lo más oscuro (mm)", 1.0, 8.0, step=0.1, key="lf_grosor_max", format="%.1f",
              help="Donde la foto es negra: la zona más gruesa.")
    st.slider("Luz que deja pasar lo más grueso (% de lo más fino)", 0.5, 50.0, step=0.5, key="lf_luz_pct",
              format="%.1f%%",
              help="Cuánta luz se filtra por la zona más gruesa, respecto de la más fina. Es una SUPOSICIÓN del "
                   "plástico hasta calibrarla con una placa de prueba: menos % = un negro más profundo.")
    luz_minima = float(st.session_state["lf_luz_pct"]) / 100.0
    try:
        st.caption(f"Equivale a que {lf.media_luz_mm(luz_minima, st.session_state['lf_grosor_min'], st.session_state['lf_grosor_max']):.2f} mm "
                   f"de este plástico dejen pasar la mitad de la luz.")
    except ValueError:
        pass

    st.subheader("Impresión")
    invertir = st.checkbox("Invertir la imagen (negativo)", key="lf_invertir")
    cara_label = st.radio("Qué cara se mira", list(CARAS_LABELS), key="lf_cara")
    capa_label = st.selectbox("Altura de capa de tu perfil", list(CAPAS_LABELS), key="lf_capa",
                              help="Ajusta los grosores a las capas reales de la impresora: la simulación muestra "
                                   "las bandas que va a tener. Con capas gruesas hay pocos grises.")

    with st.expander("Ajustes de imagen"):
        st.caption("Todos apagados por defecto: sin ellos la placa sigue la foto tal cual.")
        a1, a2, a3 = st.columns(3)
        a1.slider("Brillo", -1.0, 1.0, step=0.05, key="lf_brillo")
        a2.slider("Contraste", 0.2, 3.0, step=0.05, key="lf_contraste")
        a3.slider("Gamma", 0.3, 3.0, step=0.05, key="lf_gamma", help="Más de 1 aclara los medios.")
        st.checkbox("Auto-niveles (estirar entre los percentiles 2 y 98)", key="lf_auto_niveles")
        st.checkbox("Realce local (CLAHE: para fotos a contraluz o con niebla; altera la escala de grises)",
                    key="lf_realce_local")
        st.slider("Suavizado (mm)", 0.0, 2.0, step=0.05, key="lf_suavizado", help="Desenfoque en mm (no en píxeles).")

    with st.expander("Avanzado"):
        st.checkbox("Compensar la atenuación del plástico (recomendado)", key="lf_compensar",
                    help="Reparte los grosores para que a contraluz se vea como la foto en una pantalla. Apagado, el "
                         "grosor es lineal con el brillo y los medios salen más oscuros.")
        st.selectbox("Diagonal de la malla", list(DIAGONALES_LABELS), key="lf_diagonal")
        st.number_input("Boquilla (mm)", 0.2, 1.0, step=0.05, key="lf_boquilla",
                        help="Para avisar si la resolución pedida supera lo que esa boquilla imprime.")
        st.checkbox("Verificar la malla al generar (unos segundos más en placas grandes)", key="lf_verificar")

cara_visible = CARAS_LABELS[cara_label]
kw_mapas = dict(
    ancho_mm=float(st.session_state["lf_ancho"]), alto_mm=alto_mm, px_por_mm=float(st.session_state["lf_px"]),
    grosor_min=float(st.session_state["lf_grosor_min"]), grosor_max=float(st.session_state["lf_grosor_max"]),
    luz_minima=luz_minima, compensar=bool(st.session_state["lf_compensar"]), invertir=bool(invertir),
    capa_mm=CAPAS_LABELS[capa_label], desplazamiento=desplazamiento,
    brillo=float(st.session_state["lf_brillo"]), contraste=float(st.session_state["lf_contraste"]),
    gamma=float(st.session_state["lf_gamma"]), auto_niveles=bool(st.session_state["lf_auto_niveles"]),
    realce_local=bool(st.session_state["lf_realce_local"]), suavizado_mm=float(st.session_state["lf_suavizado"]),
)
boquilla_mm = float(st.session_state["lf_boquilla"])
diagonal = DIAGONALES_LABELS[st.session_state["lf_diagonal"]]

with col_resultado:
    if not ruta_foto:
        st.info("Subí una foto para ver cómo se vería a contraluz. La simulación se actualiza sola al mover los controles.")
    else:
        firma_archivo = _firma_de_archivo(ruta_foto)
        vp = _vista_previa(ruta_foto, firma_archivo, kw_mapas, cara_visible, boquilla_mm)
        if vp["error"]:
            st.error(vp["error"])
        else:
            tab_luz, tab_foto = st.tabs(["💡 A contraluz", "🖼️ Foto en grises"])
            with tab_luz:
                st.image(vp["imagen_luz"], width="stretch", output_format="PNG",
                         caption=f"Así se vería encendida (luz mínima {luz_minima * 100:g} %). "
                                 f"Se recalcula al mover los controles.")
                st.caption("El negro sale gris: la zona más gruesa siempre deja pasar la luz mínima. Es lo que va a hacer "
                           "la placa real, no un defecto de la simulación; por eso no es idéntica a la foto.")
            with tab_foto:
                st.image(vp["imagen_brillo"], width="stretch", output_format="PNG",
                         caption="La foto en grises con tus ajustes: lo que lee el generador para decidir los grosores.")

            m1, m2 = st.columns(2)
            m1.metric("Placa", f"{vp['ancho_mm']:.0f} x {vp['alto_mm']:.0f} mm")
            m2.metric("Grosor", f"{vp['grosor_min']:.2f} – {vp['grosor_max']:.2f} mm")
            m3, m4 = st.columns(2)
            m3.metric("Mapa", f"{vp['ancho_px']} x {vp['alto_px']} px")
            m4.metric("Grises distintos", "continuo" if vp["niveles"] is None else f"{vp['niveles']} niveles")
            if vp["px_saturados"]:
                st.caption(f"{vp['px_saturados']} puntos quedan más finos que el grosor pedido por el ajuste a capas "
                           f"(salen apenas más claros: la simulación los recorta).")

            analisis = vp["analisis"]
            for aviso in analisis["avisos"]:
                st.warning(aviso)
            if analisis["entra_a1"]:
                st.success(analisis["mensaje_a1"])
            with st.expander("Notas de impresión"):
                for nota in analisis["info"]:
                    st.write(f"· {nota}")

            st.divider()
            generar_click = st.button("Generar STL", type="primary", width="stretch",
                                      help="Arma la malla 3D completa y el archivo para descargar.")
            firma_actual = json.dumps(
                [firma_archivo, kw_mapas, cara_visible, diagonal, boquilla_mm, bool(st.session_state["lf_verificar"])],
                sort_keys=True, default=str)

            if generar_click:
                try:
                    with st.spinner("Armando la malla 3D..."):
                        os.makedirs(CARPETA_SALIDA, exist_ok=True)
                        resultado = gen.generar(
                            ruta_foto, cara_visible=cara_visible, diagonal=diagonal, boquilla_mm=boquilla_mm,
                            verificar=bool(st.session_state["lf_verificar"]), carpeta_salida=CARPETA_SALIDA,
                            prefijo=_prefijo_de(ruta_foto), **kw_mapas)
                        ruta_vista, px_vista = resultado["ruta_stl"], resultado["px_por_mm"]
                        if resultado["px_por_mm"] > RESOLUCION_VISTA_3D + 1e-9:
                            vista = gen.generar(
                                ruta_foto, cara_visible=cara_visible, diagonal=diagonal, boquilla_mm=boquilla_mm,
                                verificar=False, carpeta_salida=CARPETA_SALIDA, prefijo="vista3d_simplificada",
                                **dict(kw_mapas, px_por_mm=RESOLUCION_VISTA_3D))
                            ruta_vista, px_vista = vista["ruta_stl"], vista["px_por_mm"]
                    st.session_state["lf_resultado"] = {
                        "firma": firma_actual, "ruta_stl": resultado["ruta_stl"], "ruta_vista": ruta_vista,
                        "px_vista": px_vista, "px_por_mm": resultado["px_por_mm"], "stl_mb": resultado["stl_mb"],
                        "caras": resultado["caras"], "watertight": resultado["watertight"],
                        "verificacion": resultado["verificacion"], "ancho_mm": resultado["ancho_mm"],
                        "alto_mm": resultado["alto_mm"], "profundidad_mm": resultado["profundidad_mm"],
                    }
                except (FileNotFoundError, ValueError) as e:
                    st.error(str(e))

            res = st.session_state.get("lf_resultado")
            if res and os.path.exists(res["ruta_stl"]) and os.path.exists(res["ruta_vista"]):
                if res["firma"] != firma_actual:
                    st.warning("Cambiaste algo desde que generaste este STL: lo que ves y descargás abajo es la "
                               "**versión anterior**. Volvé a apretar «Generar STL».")
                color_visor = st.selectbox("Color del filamento (visor)", colores.NOMBRES, key="lf_color_visor")
                html_visor = preview3d.armar_html_visor([
                    {"ruta_stl": res["ruta_vista"], "color": colores.hex_de(color_visor), "nombre": "litofania"},
                ])
                if html_visor:
                    components.html(html_visor, height=460)
                    st.caption("Arrastrá para rotar, scroll para zoom.")
                st.caption(f"Vista 3D simplificada ({res['px_vista']:g} px/mm) para que el visor sea liviano. "
                           f"El STL que descargás es el completo: {res['px_por_mm']:.1f} px/mm, "
                           f"{res['caras']:,} triángulos, {res['stl_mb']:.1f} MB.".replace(",", "."))
                c1, c2, c3 = st.columns(3)
                c1.metric("Ancho", f"{res['ancho_mm']:.1f} mm")
                c2.metric("Alto", f"{res['alto_mm']:.1f} mm")
                c3.metric("Alto máx. (relieve)", f"{res['profundidad_mm']:.2f} mm")
                if res["verificacion"] is not None:
                    st.caption("✓ Malla verificada: cierra (watertight), caras hacia afuera y sin triángulos degenerados."
                               if res["verificacion"]["ok"] else "⚠ La verificación de la malla encontró un problema: "
                               "revisala antes de imprimir.")
                else:
                    st.caption(f"watertight={res['watertight']} (sin la verificación completa)")
                with open(res["ruta_stl"], "rb") as f:
                    st.download_button(
                        "⬇ Descargar STL", f, file_name=os.path.basename(res["ruta_stl"]),
                        mime="model/stl", width="stretch", type="primary",
                    )
