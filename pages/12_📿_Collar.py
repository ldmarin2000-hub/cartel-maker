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

st.title("📿 Collar y pulsera")
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
TIPOS_LABELS = {"Collar (cuentas grandes)": "collar", "Pulsera (cuentas chicas)": "pulsera"}
FORMATOS_SALIDA_LABELS = {
    "Agrupado por color (todas las bases, todas las letras, todos los separadores)": "por_color",
    "Una pieza por archivo": "por_pieza",
    "Los dos juegos": "ambos",
}
FORMAS_CUENTA_LABELS = {
    "Redonda": "redonda",
    "Cuadrada (esquinas redondeadas)": "cuadrada",
    "Con la forma de la letra (y un bordecito)": "letra",
}
# clave del juego de medidas (collar.PRESETS_MEDIDAS) -> key del widget que la muestra
CLAVES_MEDIDAS = {
    "diametro": "co_diametro", "alto": "co_alto", "agujero": "co_agujero", "chanfle": "co_chanfle",
    "alto_letra": "co_alto_letra", "profundidad_hueco": "co_profundidad_hueco", "holgura": "co_holgura",
    "margen_letra": "co_margen_letra", "pared_min": "co_pared_min",
    "radio_esquina": "co_radio_esquina", "borde_letra": "co_borde_letra", "rebaje_diametro": "co_rebaje_diametro",
    "sep_diametro": "co_sep_diametro", "sep_largo": "co_sep_largo", "sep_agujero": "co_sep_agujero",
    "forma_lado": "co_forma_lado", "forma_alto": "co_forma_alto", "forma_agujero": "co_forma_agujero",
}

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
    "co_tipo", "co_forma_cuenta", "co_radio_esquina", "co_borde_letra", "co_margen_letra", "co_pared_min",
    "co_muneca", "co_formato",
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


def _aplicar_medidas():
    """Al cambiar entre collar y pulsera, carga las medidas de ese tipo en todos los campos."""
    tipo = TIPOS_LABELS[st.session_state["co_tipo"]]
    for clave, key in CLAVES_MEDIDAS.items():
        st.session_state[key] = float(collar.PRESETS_MEDIDAS[tipo][clave])


for _clave, _key in CLAVES_MEDIDAS.items():
    # primera vez: medidas de collar. Siempre float (un preset viejo pudo guardar enteros y los sliders/campos
    # con rango decimal no aceptan un entero)
    st.session_state.setdefault(_key, float(collar.PRESETS_MEDIDAS["collar"][_clave]))
    st.session_state[_key] = float(st.session_state[_key])
st.session_state.setdefault("co_muneca", 16.0)
st.session_state["co_muneca"] = float(st.session_state["co_muneca"])

col_form, col_resultado = st.columns([1, 1.3])

with col_form:
    bloque_presets("collar", PRESET_KEYS, claves_archivo=CLAVES_ARCHIVO)

    st.radio(
        "Qué vas a hacer", list(TIPOS_LABELS.keys()), horizontal=True, key="co_tipo", on_change=_aplicar_medidas,
        help="Cambiarlo carga las medidas de ese tipo (cuenta, agujero, letra, separadores). Después podés "
             "ajustar todo a mano.",
    )
    tipo_pieza = TIPOS_LABELS[st.session_state["co_tipo"]]
    es_pulsera = tipo_pieza == "pulsera"

    texto = st.text_input(
        "Texto", value="ME RECIBI", key="co_texto",
        help="Una cuenta por cada letra. Los espacios separan palabras: ahí va el separador "
             "\"entre palabras\".",
    )

    modo_label = st.radio("Tipo de cuenta", list(MODOS_CUENTA_LABELS.keys()), key="co_modo_cuenta")
    modo_cuenta = MODOS_CUENTA_LABELS[modo_label]

    formas_disponibles = [e for e, f in FORMAS_CUENTA_LABELS.items() if not (f == "letra" and modo_cuenta == "sticker")]
    if st.session_state.get("co_forma_cuenta") not in formas_disponibles:
        st.session_state["co_forma_cuenta"] = formas_disponibles[0]  # p. ej. venía "letra" y ahora es sticker
    forma_label = st.radio(
        "Forma de la cuenta", formas_disponibles, key="co_forma_cuenta",
        help="Redonda y cuadrada llevan la letra encastrada en la tapa. La tercera hace que la cuenta tenga la "
             "forma de la letra con un bordecito (la letra encastrada va encima, en otro color).",
    )
    forma_cuenta = FORMAS_CUENTA_LABELS[forma_label]

    radio_esquina, borde_letra = None, collar.BORDE_LETRA_DEFAULT
    if forma_cuenta == "cuadrada":
        radio_esquina = float(st.number_input(
            "Radio de las esquinas (mm)", 0.0, 60.0, step=0.5, key="co_radio_esquina",
            help="0 = esquinas vivas. Con la mitad del lado la cuenta queda redonda."))
    elif forma_cuenta == "letra":
        borde_letra = float(st.number_input(
            "Borde alrededor de la letra (mm)", 0.2, 20.0, step=0.5, key="co_borde_letra",
            help="Cuánto sobresale el cuerpo de la cuenta alrededor de la letra."))
        st.caption(
            "💡 Para esta forma usá una **fuente gruesa** (Bungee, Passion One, Shrikhand, Righteous, Poppins Bold) "
            "y una letra grande: el agujero tiene que caber en los trazos. En pulsera, unos 12–16 mm de alto de "
            "letra. Si no entra, te aviso.")

    ruta_ttf = None
    alto_letra, profundidad_hueco, holgura, relieve = None, collar.PROFUNDIDAD_HUECO_DEFAULT, collar.HOLGURA_DEFAULT, 0.0
    rebaje_diametro, rebaje_profundidad = None, collar.REBAJE_PROFUNDIDAD_DEFAULT

    if modo_cuenta == "letra":
        ruta_ttf = selector_fuente("Fuente", key="collar", default_nombre="Anton", texto_muestra=texto or "Aa")
        alto_letra = float(st.slider(
            "Alto de la letra (mm)", 4.0, 65.0, step=0.5, key="co_alto_letra",
            help="Altura de la mayúscula, igual para todas las letras. Si alguna no entra en la cuenta "
                 "con su margen, se achican todas juntas y te lo aviso.",
        ))
        with st.expander("Encastre de la letra"):
            profundidad_hueco = st.slider(
                "Profundidad del hueco (mm)", 0.4, 6.0, step=0.1,
                key="co_profundidad_hueco", help="Lo que entra la letra en la tapa. Más hondo = más firme, "
                                                 "pero queda menos pared sobre el agujero del hilo.")
            holgura = st.slider(
                "Holgura por lado (mm)", 0.0, 0.5, step=0.05, key="co_holgura",
                help="Espacio entre la letra y su hueco. 0,15 es lo típico en collar y 0,1 en pulsera: si queda "
                     "muy suelta o muy justa en tu impresora, ajustalo acá.")
            relieve = st.slider(
                "Relieve (mm)", 0.0, 2.0, 0.0, step=0.1, key="co_relieve",
                help="0 = la letra queda al ras de la tapa. Más que 0 = sobresale.")
    else:
        rebaje_diametro = st.number_input(
            "Diámetro del sticker (mm) — 0 = tapa lisa, sin rebaje", min_value=0.0, max_value=65.0,
            step=0.5, key="co_rebaje_diametro",
            help="Hace un rebaje circular en la tapa para que el sticker quede al ras. Medí tu sticker: "
                 "se le suma la holgura por lado.")
        rebaje_diametro = rebaje_diametro if rebaje_diametro > 0 else None
        if rebaje_diametro:
            rebaje_profundidad = st.slider(
                "Profundidad del rebaje (mm)", 0.2, 2.0, collar.REBAJE_PROFUNDIDAD_DEFAULT, step=0.1,
                key="co_rebaje_profundidad")
            holgura = st.slider("Holgura por lado (mm)", 0.0, 0.5, step=0.05, key="co_holgura")

    st.subheader("Cuenta y agujero del hilo")
    etiqueta_tam = "Lado (mm)" if forma_cuenta == "cuadrada" else "Diámetro (mm)"
    c1, c2 = st.columns(2)
    diametro = float(c1.number_input(
        etiqueta_tam, 6.0, 120.0, step=0.5, key="co_diametro",
        disabled=(forma_cuenta == "letra"),
        help="Con la forma de la letra el tamaño sale de la letra y el borde." if forma_cuenta == "letra" else None))
    alto = float(c2.number_input("Alto (mm)", 3.0, 60.0, step=0.5, key="co_alto"))
    c3, c4 = st.columns(2)
    agujero = float(c3.number_input("Agujero (mm)", 1.0, 40.0, step=0.5, key="co_agujero"))
    chanfle = float(c4.number_input("Chanfle (mm)", 0.0, 5.0, step=0.1, key="co_chanfle"))
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
    with st.expander("Márgenes y paredes"):
        margen_letra = float(st.number_input(
            "Margen entre la letra y el borde de la cuenta (mm)", 0.0, 20.0, step=0.5, key="co_margen_letra",
            help="Si una letra no entra con este margen, se achican todas juntas."))
        pared_min = float(st.number_input(
            "Pared mínima (mm)", 0.3, 5.0, step=0.1, key="co_pared_min",
            help="Menos que esto sobre el agujero o alrededor de él y te aviso de que la pieza queda frágil. "
                 "1,2 va bien en un collar; en una pulsera de cuentas chicas, 0,8 (dos perímetros de boquilla 0,4)."))

    st.subheader("Separadores")
    separadores = {}
    for slot, titulo, opciones, tipo_default, forma_default in SLOTS_UI:
        separadores[slot] = _selector_separador(slot, titulo, opciones, tipo_default, forma_default)

    with st.expander("Medidas de los separadores"):
        st.caption("Cilindro corto (el hilo lo atraviesa a lo largo del eje; se imprime parado)")
        s1, s2, s3 = st.columns(3)
        sep_diametro = float(s1.number_input("Diámetro (mm)", 4.0, 80.0, step=0.5, key="co_sep_diametro"))
        sep_largo = float(s2.number_input("Largo (mm)", 1.0, 60.0, step=0.5, key="co_sep_largo"))
        sep_agujero = float(s3.number_input("Agujero (mm)", 1.0, 40.0, step=0.5, key="co_sep_agujero"))
        sep_perfil_label = st.selectbox("Forma del agujero del cilindro", list(PERFILES_SEPARADOR_LABELS.keys()), key="co_sep_perfil")
        sep_perfil = PERFILES_SEPARADOR_LABELS[sep_perfil_label]
        st.caption("Forma (estrella, corazón...): una pieza plana con el agujero cruzándola, igual que una cuenta")
        f1, f2, f3 = st.columns(3)
        forma_lado = float(f1.number_input("Lado mayor (mm)", 8.0, 200.0, step=1.0, key="co_forma_lado"))
        forma_alto = float(f2.number_input("Alto (mm)", 3.0, 60.0, step=0.5, key="co_forma_alto"))
        forma_agujero = float(f3.number_input("Agujero (mm)", 1.0, 40.0, step=0.5, key="co_forma_agujero"))

    st.subheader("Colores (filamento)")
    c1, c2, c3 = st.columns(3)
    color_cuenta = c1.selectbox("Cuenta", colores.NOMBRES, index=colores.NOMBRES.index("Blanco"), key="co_color_cuenta")
    color_letra = c2.selectbox("Letra", colores.NOMBRES, index=colores.NOMBRES.index("Negro"), key="co_color_letra",
                               disabled=(modo_cuenta == "sticker"))
    color_separador = c3.selectbox("Separadores", colores.NOMBRES, index=colores.NOMBRES.index("Naranja"), key="co_color_separador")
    for col, nombre_color in ((c1, color_cuenta), (c2, color_letra), (c3, color_separador)):
        _swatch(col, nombre_color)

    muneca_cm = 0.0
    if es_pulsera:
        muneca_cm = float(st.number_input(
            "Largo de tu muñeca (cm) — 0 = no comparar", 0.0, 40.0, step=0.5, key="co_muneca",
            help="Después de generar te digo si la pulsera queda corta o larga (se le suma 1,5 cm de holgura)."))

    formato_label = st.radio(
        "Cómo exportar", list(FORMATOS_SALIDA_LABELS.keys()), key="co_formato",
        help="Agrupado por color: 3 STL (bases, letras y separadores, que es lo que se imprime de un mismo color) con "
             "las piezas ya acomodadas en la cama de la A1; si no entran en una placa se parten en varias, y cada "
             "placa trae un mapa numerado. Una pieza por archivo: un STL por cada cuenta, letra y separador.")
    formato_salida = FORMATOS_SALIDA_LABELS[formato_label]
    agrupar_repetidas = st.checkbox(
        "Agrupar las piezas repetidas (un solo archivo con la cantidad, ej. _x7)", value=False, key="co_agrupar",
        disabled=(formato_salida == "por_color"),
        help="Solo para 'una pieza por archivo'. Apagado (lo normal): un STL por cada pieza, numerado en el orden en "
             "que va, con las letras y los separadores repetidos incluidos. Prendido: cada pieza idéntica sale una "
             "sola vez y la cantidad a imprimir va en el nombre del archivo. En el agrupado por color siempre salen "
             "todas las copias.")

    generar_click = st.button(f"Generar {tipo_pieza}", type="primary", use_container_width=True)


def _zip_de_piezas(piezas, mapas=()):
    """Todos los STL y los mapas de placa en un .zip."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for p in piezas:
            z.write(p["ruta_stl"], arcname=os.path.basename(p["ruta_stl"]))
        for m in mapas:
            z.write(m["ruta_png"], arcname=os.path.basename(m["ruta_png"]))
    return buffer.getvalue()


def _fila_de_pieza(i, p):
    """Una fila de la lista de archivos: color, nombre, cantidad o número, medidas y descarga."""
    c_nombre, c_cant, c_med, c_desc = st.columns([3, 1.2, 2, 2])
    c_nombre.markdown(
        f'<span style="display:inline-block;width:12px;height:12px;border-radius:3px;'
        f'background:{p["color_hex"]};border:1px solid #0004;margin-right:6px"></span>{p["etiqueta"]}'
        f'<br><small>{p["color"]}</small>', unsafe_allow_html=True)
    if p["salida"] == "por_color":
        c_cant.markdown(f"**{p['cantidad']}** pieza(s)")
    else:
        c_cant.markdown(f"**Nº {p['posicion']}**" if p.get("posicion") else f"× **{p['cantidad']}**")
    c_med.caption(f"{p['ancho_mm']:.0f} × {p['alto_mm']:.0f} × {p['espesor_mm']:.0f} mm")
    with open(p["ruta_stl"], "rb") as f:
        c_desc.download_button(
            "⬇ STL", f, file_name=os.path.basename(p["ruta_stl"]), mime="model/stl",
            key=f"co_descarga_{i}", use_container_width=True, on_click="ignore",
        )
    if not p["watertight"]:
        c_nombre.caption("⚠ no quedó perfectamente cerrada (watertight)")


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
            forma_cuenta=forma_cuenta, radio_esquina=radio_esquina, borde_letra=borde_letra,
            margen_letra=margen_letra, pared_min=pared_min, formato_salida=formato_salida,
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
        st.info(f"Completá el formulario y apretá **Generar {tipo_pieza}**.")
    else:
        html_visor = preview3d.armar_html_visor(
            [{"malla": m, "color": color_hex, "nombre": etiqueta} for m, color_hex, etiqueta in r["armado"]],
            height_px=360,
        )
        if html_visor:
            components.html(html_visor, height=370)
            st.caption("El collar armado y acostado, como se ve sobre la mesa. Arrastrá para rotar, scroll para zoom.")

        m1, m2, m3 = st.columns(3)
        m1.metric(f"Largo de la {tipo_pieza}", f"{r['largo_mm'] / 10:.1f} cm")
        m2.metric("Cuentas", r["n_cuentas"])
        m3.metric("Separadores", r["n_separadores"])

        if es_pulsera and muneca_cm > 0:
            ajuste = collar.ajuste_a_muneca(r["largo_mm"], muneca_cm, r["n_cuentas"] + r["n_separadores"])
            (st.success if ajuste["estado"] == "justa" else st.warning)(ajuste["mensaje"])

        for nota in r["info"]:
            st.info(nota)
        for aviso in r["avisos"]:
            st.warning(aviso)

        indexadas = list(enumerate(r["piezas"]))
        por_color = [(i, p) for i, p in indexadas if p["salida"] == "por_color"]
        por_pieza = [(i, p) for i, p in indexadas if p["salida"] == "por_pieza"]

        if por_color:
            st.subheader("Para imprimir, agrupado por color")
            st.caption("Cada archivo trae todas las piezas de un color, ya acomodadas en la cama de la A1 y apoyadas. "
                       "Las letras quedan en su placa en el mismo lugar que su base.")
            for i, p in por_color:
                _fila_de_pieza(i, p)
            if r["mapas"]:
                with st.expander("🗺️ Mapa de cada placa (qué número es cada pieza)", expanded=True):
                    st.caption("Los números son el orden de la pieza en el collar, de izquierda a derecha.")
                    for m in r["mapas"]:
                        st.image(m["ruta_png"], use_container_width=True)

        if por_pieza:
            st.subheader("Una pieza por archivo")
            if por_pieza[0][1].get("posicion"):
                st.caption("Una pieza por cada lugar, numeradas en el orden en que van (de izquierda a derecha).")
            else:
                st.caption("Cada pieza distinta sale una sola vez: imprimí tantas copias como indica la cantidad.")
            for i, p in por_pieza:
                _fila_de_pieza(i, p)

        st.download_button(
            "⬇ Todo (.zip)", _zip_de_piezas(r["piezas"], r["mapas"]),
            file_name=f"{pieza.nombre_archivo(r['texto'], default='collar')}_collar.zip",
            mime="application/zip", use_container_width=True, type="primary", on_click="ignore",
        )
