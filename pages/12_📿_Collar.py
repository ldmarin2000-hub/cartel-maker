#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pages/12_📿_Collar.py
-------------------------
Página de Streamlit para el generador de collares de cuentas. Es solo la
capa visual: toda la lógica real vive en generators/collar.py (generar()),
la misma que usa la versión de consola (main.py). Python puro.
"""

import io
import os
import shutil
import zipfile

import streamlit as st
import streamlit.components.v1 as components

from core import colores, decoraciones, pieza, preview3d
from generators import collar
from ui_streamlit import bloque_presets, resolver_archivo_subido, selector_fuente

st.set_page_config(page_title="Collar · Cartel Maker", page_icon="📿", layout="wide")

st.title("📿 Collar")
st.caption(collar.DESCRIPCION)

CARPETA_COLLAR = os.path.join("output", "collar")

MODOS_CUENTA_LABELS = {
    "Con letra encastrada (cada letra es una pieza aparte)": "letra",
    "Lisa para sticker (sin letra, con rebaje opcional)": "sticker",
}
PERFILES_LABELS = {
    "Rombo — imprime sin soportes (recomendado)": "rombo",
    "Gota — imprime sin soportes": "gota",
    "Redondo — el techo necesita soporte": "redondo",
}
PERFILES_SEPARADOR_LABELS = {"Rombo": "rombo", "Cuadrado": "cuadrado", "Redondo": "redondo"}
TIPOS_SEP_LABELS = {
    "ninguno": "Nada",
    "igual": "Igual que entre letras",
    "cilindro": "Cilindro corto",
    "forma": "Forma (estrella, corazón, SVG...)",
}
SLOTS_UI = [
    # (slot, título, opciones, tipo por defecto, forma por defecto)
    ("entre_letras", "Entre letras", ["ninguno", "cilindro", "forma"], "cilindro", "estrella"),
    ("entre_palabras", "Entre palabras (donde hay un espacio)", ["igual", "ninguno", "cilindro", "forma"],
     "igual", "corazon"),
    ("inicio", "Al principio", ["ninguno", "cilindro", "forma"], "ninguno", "estrella"),
    ("final", "Al final", ["ninguno", "cilindro", "forma"], "ninguno", "estrella"),
]
FORMAS = [n for n in decoraciones.NOMBRES_VALIDOS if n != "ninguno"]

PRESET_KEYS = [
    "co_texto", "co_modo_cuenta", "collar_selectbox", "collar_ruta",
    "co_alto_letra", "co_profundidad_hueco", "co_holgura", "co_relieve",
    "co_rebaje_diametro", "co_rebaje_profundidad",
    "co_diametro", "co_alto", "co_agujero", "co_chanfle", "co_perfil", "co_angulo",
    "co_sep_entre_letras", "co_sep_entre_palabras", "co_sep_inicio", "co_sep_final",
    "co_origen_entre_letras", "co_origen_entre_palabras", "co_origen_inicio", "co_origen_final",
    "co_forma_entre_letras", "co_forma_entre_palabras", "co_forma_inicio", "co_forma_final",
    "co_sep_diametro", "co_sep_largo", "co_sep_agujero", "co_sep_perfil",
    "co_forma_lado", "co_forma_alto", "co_forma_agujero",
    "co_color_cuenta", "co_color_letra", "co_color_separador", "co_agrupar",
]
# Los SVG propios de cada separador no se pueden guardar en el preset como archivo subido (Streamlit no
# lo permite): se guarda la ruta "sombra" y el preset copia el archivo adentro de su carpeta.
CLAVES_ARCHIVO = [f"co_svg_{slot}__ruta" for slot, *_ in SLOTS_UI]
PRESET_KEYS += CLAVES_ARCHIVO


def _swatch(columna, nombre_color):
    columna.markdown(
        f'<div style="height:22px;border-radius:4px;background:{colores.hex_de(nombre_color)};'
        f'border:1px solid #0003"></div>', unsafe_allow_html=True,
    )


def _selector_separador(slot, titulo, opciones, tipo_default, forma_default):
    """Una posición del collar: nada / cilindro corto / forma. Devuelve el dict que espera
    `collar.generar(separadores=...)`."""
    etiquetas = [TIPOS_SEP_LABELS[o] for o in opciones]
    etiqueta = st.selectbox(titulo, etiquetas, index=opciones.index(tipo_default), key=f"co_sep_{slot}")
    tipo = opciones[etiquetas.index(etiqueta)]
    if tipo != "forma":
        return {"tipo": tipo}

    origen = st.radio("De dónde sale la forma", ["Lista", "SVG propio"], horizontal=True, key=f"co_origen_{slot}")
    if origen == "Lista":
        nombre = st.selectbox("Forma", FORMAS, index=FORMAS.index(forma_default), key=f"co_forma_{slot}")
        return {"tipo": "forma", "forma": {"nombre": nombre}}

    subido = st.file_uploader("SVG de la forma", type=["svg"], key=f"co_svg_{slot}")
    ruta = resolver_archivo_subido(subido, f"co_svg_{slot}", f"_subido_co_{slot}")
    if ruta is None:
        return {"tipo": "forma", "forma": None}  # falta el archivo: se avisa al generar
    return {"tipo": "forma", "forma": {"svg": ruta}}


col_form, col_resultado = st.columns([1, 1.3])

with col_form:
    bloque_presets("collar", PRESET_KEYS, claves_archivo=CLAVES_ARCHIVO)

    texto = st.text_input(
        "Texto del collar", value="ME RECIBI", key="co_texto",
        help="Una cuenta por cada letra. Los espacios separan palabras: ahí va el separador "
             "\"entre palabras\".",
    )

    modo_label = st.radio("Tipo de cuenta", list(MODOS_CUENTA_LABELS.keys()), key="co_modo_cuenta")
    modo_cuenta = MODOS_CUENTA_LABELS[modo_label]

    ruta_ttf = None
    alto_letra, profundidad_hueco, holgura, relieve = None, collar.PROFUNDIDAD_HUECO_DEFAULT, collar.HOLGURA_DEFAULT, 0.0
    rebaje_diametro, rebaje_profundidad = None, collar.REBAJE_PROFUNDIDAD_DEFAULT

    if modo_cuenta == "letra":
        ruta_ttf = selector_fuente("Fuente", key="collar", default_nombre="Anton", texto_muestra=texto or "Aa")
        alto_letra = float(st.slider(
            "Alto de la letra (mm)", 10, 65, 42, key="co_alto_letra",
            help="Altura de la mayúscula, igual para todas las letras. Si alguna no entra en la cuenta "
                 "con su margen, se achican todas juntas y te lo aviso.",
        ))
        with st.expander("Encastre de la letra"):
            profundidad_hueco = st.slider(
                "Profundidad del hueco (mm)", 1.0, 6.0, collar.PROFUNDIDAD_HUECO_DEFAULT, step=0.5,
                key="co_profundidad_hueco", help="Lo que entra la letra en la tapa. Más hondo = más firme, "
                                                 "pero queda menos pared sobre el agujero del hilo.")
            holgura = st.slider(
                "Holgura por lado (mm)", 0.0, 0.5, collar.HOLGURA_DEFAULT, step=0.05, key="co_holgura",
                help="Espacio entre la letra y su hueco. 0,15 es lo típico: si queda muy suelta o muy "
                     "justa en tu impresora, ajustalo acá.")
            relieve = st.slider(
                "Relieve (mm)", 0.0, 2.0, 0.0, step=0.1, key="co_relieve",
                help="0 = la letra queda al ras de la tapa. Más que 0 = sobresale.")
    else:
        rebaje_diametro = st.number_input(
            "Diámetro del sticker (mm) — 0 = tapa lisa, sin rebaje", min_value=0.0, max_value=65.0,
            value=50.0, step=1.0, key="co_rebaje_diametro",
            help="Hace un rebaje circular en la tapa para que el sticker quede al ras. Medí tu sticker: "
                 "se le suma la holgura por lado.")
        rebaje_diametro = rebaje_diametro if rebaje_diametro > 0 else None
        if rebaje_diametro:
            rebaje_profundidad = st.slider(
                "Profundidad del rebaje (mm)", 0.2, 2.0, collar.REBAJE_PROFUNDIDAD_DEFAULT, step=0.1,
                key="co_rebaje_profundidad")
            holgura = st.slider("Holgura por lado (mm)", 0.0, 0.5, collar.HOLGURA_DEFAULT, step=0.05, key="co_holgura")

    st.subheader("Cuenta y agujero del hilo")
    c1, c2 = st.columns(2)
    diametro = float(c1.number_input("Diámetro (mm)", 30.0, 120.0, collar.DIAMETRO_DEFAULT, step=1.0, key="co_diametro"))
    alto = float(c2.number_input("Alto (mm)", 10.0, 60.0, collar.ALTO_DEFAULT, step=1.0, key="co_alto"))
    c3, c4 = st.columns(2)
    agujero = float(c3.number_input("Agujero (mm)", 3.0, 40.0, collar.AGUJERO_DEFAULT, step=1.0, key="co_agujero"))
    chanfle = float(c4.number_input("Chanfle (mm)", 0.0, 5.0, collar.CHANFLE_DEFAULT, step=0.5, key="co_chanfle"))
    perfil_label = st.selectbox("Forma del agujero", list(PERFILES_LABELS.keys()), key="co_perfil",
                                help="La cuenta se imprime acostada: el techo de un agujero redondo es un puente "
                                     "largo que se cae. El rombo y la gota tienen las paredes a 45° y no "
                                     "necesitan soportes.")
    perfil = PERFILES_LABELS[perfil_label]
    angulo = float(st.slider(
        "Ángulo del agujero respecto de la letra (grados)", 0, 180, 0, step=5, key="co_angulo",
        help="0° = el hilo corre a lo largo de la lectura (letras derechas). 90° = entra por arriba y abajo "
             "de la letra. 45° = las letras cuelgan inclinadas. Con rombo o gota imprime sin soportes en "
             "cualquier ángulo.",
    ))

    st.subheader("Separadores")
    separadores = {}
    for slot, titulo, opciones, tipo_default, forma_default in SLOTS_UI:
        separadores[slot] = _selector_separador(slot, titulo, opciones, tipo_default, forma_default)

    with st.expander("Medidas de los separadores"):
        st.caption("Cilindro corto (el hilo lo atraviesa a lo largo del eje; se imprime parado)")
        s1, s2, s3 = st.columns(3)
        sep_diametro = float(s1.number_input("Diámetro (mm)", 10.0, 80.0, collar.SEP_DIAMETRO_DEFAULT, step=1.0, key="co_sep_diametro"))
        sep_largo = float(s2.number_input("Largo (mm)", 3.0, 60.0, collar.SEP_LARGO_DEFAULT, step=1.0, key="co_sep_largo"))
        sep_agujero = float(s3.number_input("Agujero (mm)", 2.0, 40.0, collar.SEP_AGUJERO_DEFAULT, step=1.0, key="co_sep_agujero"))
        sep_perfil_label = st.selectbox("Forma del agujero del cilindro", list(PERFILES_SEPARADOR_LABELS.keys()), key="co_sep_perfil")
        sep_perfil = PERFILES_SEPARADOR_LABELS[sep_perfil_label]
        st.caption("Forma (estrella, corazón...): una pieza plana con el agujero cruzándola, igual que una cuenta")
        f1, f2, f3 = st.columns(3)
        forma_lado = float(f1.number_input("Lado mayor (mm)", 20.0, 200.0, collar.FORMA_LADO_DEFAULT, step=5.0, key="co_forma_lado"))
        forma_alto = float(f2.number_input("Alto (mm)", 8.0, 60.0, collar.FORMA_ALTO_DEFAULT, step=1.0, key="co_forma_alto"))
        forma_agujero = float(f3.number_input("Agujero (mm)", 2.0, 40.0, collar.FORMA_AGUJERO_DEFAULT, step=1.0, key="co_forma_agujero"))

    st.subheader("Colores (filamento)")
    c1, c2, c3 = st.columns(3)
    color_cuenta = c1.selectbox("Cuenta", colores.NOMBRES, index=colores.NOMBRES.index("Blanco"), key="co_color_cuenta")
    color_letra = c2.selectbox("Letra", colores.NOMBRES, index=colores.NOMBRES.index("Negro"), key="co_color_letra",
                               disabled=(modo_cuenta == "sticker"))
    color_separador = c3.selectbox("Separadores", colores.NOMBRES, index=colores.NOMBRES.index("Naranja"), key="co_color_separador")
    for col, nombre_color in ((c1, color_cuenta), (c2, color_letra), (c3, color_separador)):
        _swatch(col, nombre_color)

    agrupar_repetidas = st.checkbox(
        "Agrupar las piezas repetidas (un solo archivo con la cantidad, ej. _x7)", value=False, key="co_agrupar",
        help="Apagado (lo normal): sale un STL por cada pieza del collar, numerado en el orden en que va, con las "
             "letras y los separadores repetidos incluidos. Prendido: cada pieza idéntica sale una sola vez y la "
             "cantidad a imprimir va en el nombre del archivo.")

    generar_click = st.button("Generar collar", type="primary", use_container_width=True)


def _zip_de_piezas(piezas):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for p in piezas:
            z.write(p["ruta_stl"], arcname=os.path.basename(p["ruta_stl"]))
    return buffer.getvalue()


def _generar():
    """Corre `collar.generar` y deja el resultado (o el error) en session_state: así los botones
    de descarga y cualquier otro cambio de la página no lo hacen desaparecer."""
    if not texto.strip():
        return None, "Escribí algún texto primero."
    for slot, cfg in separadores.items():
        if cfg["tipo"] == "forma" and not cfg.get("forma"):
            titulo = next(t for s, t, *_ in SLOTS_UI if s == slot)
            return None, f"Subí el SVG para el separador «{titulo}», o elegí una forma de la lista."

    carpeta = os.path.join(CARPETA_COLLAR, pieza.nombre_archivo(texto, default="collar"))
    shutil.rmtree(carpeta, ignore_errors=True)  # sin STL viejos de otra corrida mezclados
    try:
        r = collar.generar(
            texto, ruta_ttf, modo_cuenta=modo_cuenta,
            diametro=diametro, alto=alto, agujero=agujero, chanfle=chanfle, perfil=perfil, angulo_agujero=angulo,
            alto_letra_mm=alto_letra, profundidad_hueco=profundidad_hueco, holgura=holgura, relieve=relieve,
            rebaje_sticker_diametro=rebaje_diametro, rebaje_sticker_profundidad=rebaje_profundidad,
            separadores=separadores, sep_diametro=sep_diametro, sep_largo=sep_largo,
            sep_agujero=sep_agujero, sep_perfil=sep_perfil,
            forma_lado=forma_lado, forma_alto=forma_alto, forma_agujero=forma_agujero,
            color_cuenta=color_cuenta, color_letra=color_letra, color_separador=color_separador,
            carpeta_salida=carpeta, agrupar_repetidas=agrupar_repetidas,
        )
    except (FileNotFoundError, ValueError) as e:
        return None, str(e)
    return r, None


if generar_click:
    with st.spinner("Generando las piezas..."):
        r_nuevo, error = _generar()
    st.session_state["co_resultado"] = r_nuevo
    st.session_state["co_error"] = error

with col_resultado:
    r = st.session_state.get("co_resultado")
    error = st.session_state.get("co_error")

    if error:
        st.error(error)
    elif not r:
        st.info("Completá el formulario y apretá **Generar collar**.")
    else:
        html_visor = preview3d.armar_html_visor(
            [{"malla": m, "color": color_hex, "nombre": etiqueta} for m, color_hex, etiqueta in r["armado"]],
            height_px=360,
        )
        if html_visor:
            components.html(html_visor, height=370)
            st.caption("El collar armado y acostado, como se ve sobre la mesa. Arrastrá para rotar, scroll para zoom.")

        m1, m2, m3 = st.columns(3)
        m1.metric("Largo del collar", f"{r['largo_mm'] / 10:.0f} cm")
        m2.metric("Cuentas", r["n_cuentas"])
        m3.metric("Separadores", r["n_separadores"])

        for nota in r["info"]:
            st.info(nota)
        for aviso in r["avisos"]:
            st.warning(aviso)

        st.subheader("Piezas para imprimir")
        if r["piezas"] and r["piezas"][0].get("posicion"):
            st.caption("Una pieza por cada lugar del collar, numeradas en el orden en que van (de izquierda a derecha).")
        else:
            st.caption("Cada pieza distinta sale una sola vez: imprimí tantas copias como indica la cantidad.")
        for i, p in enumerate(r["piezas"]):
            c_nombre, c_cant, c_med, c_desc = st.columns([3, 1.2, 2, 2])
            c_nombre.markdown(
                f'<span style="display:inline-block;width:12px;height:12px;border-radius:3px;'
                f'background:{p["color_hex"]};border:1px solid #0004;margin-right:6px"></span>{p["etiqueta"]}'
                f'<br><small>{p["color"]}</small>', unsafe_allow_html=True)
            c_cant.markdown(f"**Nº {p['posicion']}**" if p.get("posicion") else f"× **{p['cantidad']}**")
            c_med.caption(f"{p['ancho_mm']:.0f} × {p['alto_mm']:.0f} × {p['espesor_mm']:.0f} mm")
            with open(p["ruta_stl"], "rb") as f:
                c_desc.download_button(
                    "⬇ STL", f, file_name=os.path.basename(p["ruta_stl"]), mime="model/stl",
                    key=f"co_descarga_{i}", use_container_width=True, on_click="ignore",
                )
            if not p["watertight"]:
                c_nombre.caption("⚠ no quedó perfectamente cerrada (watertight)")

        st.download_button(
            "⬇ Todas las piezas (.zip)", _zip_de_piezas(r["piezas"]),
            file_name=f"{pieza.nombre_archivo(r['texto'], default='collar')}_collar.zip",
            mime="application/zip", use_container_width=True, type="primary", on_click="ignore",
        )
