#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pages/9_🎂_Topper.py
---------------------
Generador unificado de toppers para tortas, cupcakes, y decoraciones.
Integración 3D completa con STL export y preview interactivo fiel
(texto real, fuente real, tipo de base real).
"""

import os
import streamlit as st
import streamlit.components.v1 as components

from core import colores, preview3d, fuentes
from generators import topper
from ui_streamlit import bloque_presets, selector_fuente

st.set_page_config(page_title="Topper · Cartel Maker", page_icon="🎂", layout="wide")


def _resolver_archivo_subido(subido, key_uploader, prefijo_output):
    """Guarda `subido` (un UploadedFile de un file_uploader con key
    `key_uploader`) en output/ y actualiza la key "sombra"
    `<key_uploader>__ruta` en session_state -- esa key sombra (no el
    uploader en sí, que Streamlit no permite rellenar programáticamente)
    es la que se guarda/restaura en los presets. Subir un archivo nuevo
    siempre reemplaza lo que hubiera ahí, incluido lo que viniera de un
    preset recién cargado.

    Devuelve la ruta a usar: la del archivo recién subido si hay uno;
    si no, la que haya quedado en la key sombra (de un preset cargado,
    o de una subida anterior en esta misma sesión); None si no hay
    nada. Si esa ruta ya no existe en disco (se borró/movió), la
    ignora en vez de romper más adelante al intentar abrirla."""
    key_ruta = f"{key_uploader}__ruta"
    if subido is not None:
        os.makedirs("output", exist_ok=True)
        ruta = os.path.join("output", f"{prefijo_output}_{subido.name}")
        with open(ruta, "wb") as f:
            f.write(subido.getvalue())
        st.session_state[key_ruta] = ruta

    ruta = st.session_state.get(key_ruta)
    if ruta and not os.path.exists(ruta):
        ruta = None
    return ruta

st.title("🎂 Topper (decoración para tortas y más)")
st.caption("Crea toppers para tortas, cupcakes, postres. Impresión 3D, Neón, LED, Acrílico.")

TIPOS_TOPPER = [
    "Topper Plano (recortado, líneas de texto)",
    "Topper 3D (escultura pequeña)",
    "Topper Neón (texto/símbolo LED flexible)",
    "Topper LED (iluminado con efectos)",
    "Topper Acrílico (grabado láser)",
]

PRESET_KEYS = [
    "tp_tipo", "tp_texto", "tp_tamaño_mm", "tp_estilo", "tp_material", "tp_color",
    "tp_base_tipo", "tp_tema", "tp_objeto",
    "tp_plano_l1", "tp_plano_l2", "tp_plano_l3", "tp_plano_marco", "tp_plano_palo",
    "tp_plano_tam_l1", "tp_plano_tam_l2", "tp_plano_tam_l3", "tp_plano_ancho_texto",
    "tp_plano_espesor", "tp_plano_separacion", "tp_plano_palo_largo", "tp_plano_palo_ancho",
    "tp_plano_palo_solape", "tp_plano_palo_offset_x",
    "tp_plano_offset_y", "tp_plano_borde", "tp_plano_color_texto",
    "tp_plano_color_texto_2", "tp_plano_color_texto_3", "tp_plano_color_borde",
    "tp_plano_color_marco", "tp_plano_color_palo", "tp_plano_ams",
    "tp_plano_margen_marco", "tp_plano_grosor_marco", "tp_plano_texto_sobre_marco",
    "tp_plano_marco_tam_modo", "tp_plano_marco_tam_manual", "tp_plano_marco_estilo",
    "tp_plano_color_marco_borde",
    "tp_plano_decoracion_lado", "tp_plano_decoracion_tam", "tp_plano_color_decoracion",
    "tp_plano_decoracion_sobre_marco",
    "tp_plano_decoracion_offset_x", "tp_plano_decoracion_offset_y", "tp_plano_decoracion_acercar",
    "tp_plano_color_conectores",
    "tp_plano_base", "tp_plano_base_ancho_extra", "tp_plano_base_alto", "tp_plano_color_base",
    "tp_plano_marco_imagen_umbral", "tp_plano_marco_imagen_invertir",
    "tp_plano_decoracion_imagen_umbral", "tp_plano_decoracion_imagen_invertir",
    "tp_plano_decoracion_origen",
]

# Keys "sombra" (ver _resolver_archivo_subido) para los uploaders que NO
# son de "Múltiples decoraciones" -- guardan la RUTA del archivo en uso,
# no el archivo subido en sí (eso Streamlit no lo permite restaurar).
PRESET_FILE_KEYS = [
    "tp_plano_marco_svg__ruta",
    "tp_plano_marco_imagen__ruta",
    "tp_plano_decoracion_svg__ruta",
    "tp_plano_decoracion_imagen__ruta",
    "tp_plano_decoracion_multicolor_imagen__ruta",
]
PRESET_KEYS += PRESET_FILE_KEYS

# Un casillero de "Múltiples decoraciones" completo necesita las 12 --
# no alcanza con lado/tamaño/color/offsets/acercar: sin "usar" el
# casillero ni siquiera queda marcado activo, sin "tipo" no se sabe si
# mirar la key de archivo SVG o la de imagen, y "invertir"/"umbral"
# solo importan si es imagen. Cada key se agrega una sola vez -- a
# PRESET_KEYS siempre, y además a PRESET_FILE_KEYS si es una de
# archivo (termina en "__ruta").
SUFIJOS_MULTI_DEC = (
    "usar", "tipo", "svg__ruta", "imagen__ruta", "invertir", "umbral",
    "lado", "tam", "offset_x", "offset_y", "acercar", "color",
)
for _i in range(topper.MAX_COLORES_DECORACION_MULTICOLOR):
    for _sufijo in SUFIJOS_MULTI_DEC:
        _key = f"tp_plano_multi_dec_{_i}_{_sufijo}"
        PRESET_KEYS.append(_key)
        if _sufijo.endswith("__ruta"):
            PRESET_FILE_KEYS.append(_key)

tipo_topper = st.radio("Tipo de topper", TIPOS_TOPPER, horizontal=True, key="tp_tipo")

col_form, col_preview = st.columns([1, 1.3])

with col_form:
    bloque_presets("topper", PRESET_KEYS, claves_archivo=PRESET_FILE_KEYS)

    es_plano = "Plano" in tipo_topper

    if es_plano:
        st.caption("1 a 3 líneas de texto — dejá una línea vacía si no la necesitás.")
        col_l1, col_l2, col_l3 = st.columns(3)
        linea1 = col_l1.text_input("Línea 1", "Happy", key="tp_plano_l1")
        linea2 = col_l2.text_input("Línea 2", "Birthday", key="tp_plano_l2")
        linea3 = col_l3.text_input("Línea 3", "", key="tp_plano_l3")
        lineas_plano = [linea1, linea2, linea3]
        texto = " ".join(l.strip() for l in lineas_plano if l.strip()) or "Topper"

        col_m1, col_m2, col_m3 = st.columns(3)
        mult_l1_plano = col_m1.slider(
            "Tamaño línea 1", 0.5, 2.0, 1.0, step=0.1, key="tp_plano_tam_l1",
            disabled=not linea1.strip(),
            help="Multiplica el tamaño de ESTA línea respecto de las demás -- 1.0 es el tamaño "
                 "normal (el que le toca según 'Tamaño' y la cantidad de líneas). Más alto la "
                 "agranda MÁS ALLÁ de eso (el bloque completo puede crecer), no achica las otras.",
        )
        mult_l2_plano = col_m2.slider(
            "Tamaño línea 2", 0.5, 2.0, 1.0, step=0.1, key="tp_plano_tam_l2",
            disabled=not linea2.strip(),
        )
        mult_l3_plano = col_m3.slider(
            "Tamaño línea 3", 0.5, 2.0, 1.0, step=0.1, key="tp_plano_tam_l3",
            disabled=not linea3.strip(),
        )
        multiplicadores_lineas_plano = [mult_l1_plano, mult_l2_plano, mult_l3_plano]
    else:
        texto = st.text_input("Texto/Diseño", "Topper", key="tp_texto",
                             help="Texto o nombre a grabar/mostrar en el topper")

    # Fuente — selector real de las fuentes curadas/proyecto/sistema
    ruta_fuente = selector_fuente("Fuente", key="tp_fuente", texto_muestra=texto or "Topper", mostrar_preview=False)

    tamaño_mm = st.slider("Tamaño (mm)", 20, 200, 80, step=5, key="tp_tamaño_mm",
                         help="Altura aproximada del topper (mayor = más visible)")

    estilo = st.selectbox(
        "Estilo",
        list(topper.ESTILOS.keys()),
        key="tp_estilo",
        help="Controla la altura y personalidad de la silueta"
    )

    tema = st.selectbox("Tema / Categoría", topper.TEMAS, key="tp_tema")

    # Parámetros específicos por tipo
    material_3d = "PLA"
    color_3d = "Blanco"
    base_tipo = topper.BASES[0]
    objeto_decorativo = "Ninguno"
    tipo_led = "Flexible (frío)"
    grosor_tubo = 10
    material_led = "PLA"
    efecto = "Fijo"
    baterias = True
    espesor_acrilico = 3
    acabado = "Transparente"
    marco_plano = "Ninguno"
    con_palo_plano = True
    espesor_plano = 3.0

    if es_plano:
        st.subheader("Parámetros Plano")
        col_a, col_b = st.columns(2)
        with col_a:
            marco_plano = st.selectbox(
                "Marco decorativo", topper.FORMAS_MARCO, key="tp_plano_marco",
                help="Un aro fino alrededor del texto (Círculo/Hexágono/Pentágono/tu propio "
                     "SVG o imagen). 'Ninguno' deja el texto suelto, unido solo por los "
                     "puentes finos."
            )
            marco_svg_ruta = None
            marco_imagen_ruta = None
            marco_imagen_umbral_plano = 128
            marco_imagen_invertir_plano = False
            if marco_plano == "SVG propio":
                marco_svg_subido = st.file_uploader(
                    "SVG para el marco", type=["svg"], key="tp_plano_marco_svg",
                    help="Se usa la silueta del SVG como aro alrededor del texto (funciona "
                         "mejor con una silueta cerrada simple -- una estrella, un corazón, "
                         "un logo -- que con un dibujo que ya es un aro/corona)."
                )
                marco_svg_ruta = _resolver_archivo_subido(marco_svg_subido, "tp_plano_marco_svg", "_subido_tp_marco")
            elif marco_plano == "Imagen propia":
                marco_imagen_subida = st.file_uploader(
                    "Imagen (PNG/JPG) para el marco", type=["png", "jpg", "jpeg"], key="tp_plano_marco_imagen",
                    help="Un logo/ícono simple (silueta clara sobre fondo liso o transparente, "
                         "no una foto) -- se usa su silueta como aro, igual que con un SVG."
                )
                marco_imagen_ruta = _resolver_archivo_subido(marco_imagen_subida, "tp_plano_marco_imagen", "_subido_tp_marco")
                if marco_imagen_ruta:
                    marco_imagen_invertir_plano = st.checkbox(
                        "Imagen clara sobre fondo oscuro", value=False, key="tp_plano_marco_imagen_invertir",
                        help="Tildá esto si el logo es claro y el fondo oscuro (al revés del caso "
                             "típico). No hace falta si el PNG ya tiene fondo transparente."
                    )
                    marco_imagen_umbral_plano = st.slider(
                        "Sensibilidad del contorno", 0, 255, 128, key="tp_plano_marco_imagen_umbral",
                        help="Si la imagen no tiene fondo transparente: qué tan oscuro tiene que "
                             "ser un píxel para contar como parte del logo. Subilo si falta parte "
                             "del dibujo, bajalo si trae de más el fondo."
                    )
            marco_tam_modo_plano = st.radio(
                "Tamaño del marco", ["Automático", "Manual"], horizontal=True,
                disabled=marco_plano == "Ninguno", key="tp_plano_marco_tam_modo",
                help="Automático: el marco se calcula a partir del texto + 'Distancia al texto', "
                     "como siempre. Manual: elegís el tamaño en mm de abajo y el marco lo usa "
                     "directo, ignorando el texto (y la distancia, que en ese caso no aplica)."
            )
            marco_tam_automatico_plano = marco_tam_modo_plano == "Automático"
            marco_tam_manual_plano = st.slider(
                "Tamaño del marco (mm)", 20.0, 250.0, 100.0, step=5.0,
                disabled=marco_plano == "Ninguno" or marco_tam_automatico_plano,
                key="tp_plano_marco_tam_manual",
                help="Diámetro/lado mayor del marco -- solo se usa en modo Manual.",
            )
            margen_marco_plano = st.slider(
                "Distancia del marco al texto (mm)", 2.0, 30.0, 6.0, step=1.0,
                disabled=marco_plano == "Ninguno" or not marco_tam_automatico_plano,
                key="tp_plano_margen_marco",
                help="Qué tan grande es el marco respecto del texto -- más margen, más lejos "
                     "queda el aro de las letras (marco más grande). Solo aplica en modo Automático."
            )
            grosor_marco_plano = st.slider(
                "Grosor del marco (mm)", 1.0, 8.0, 3.0, step=0.5,
                disabled=marco_plano == "Ninguno", key="tp_plano_grosor_marco",
                help="Ancho de la línea del aro en sí (no confundir con la distancia al texto). "
                     "No aplica con el estilo 'Relleno' (ahí el marco es macizo, sin línea)."
            )
            marco_estilo_plano = st.radio(
                "Estilo del marco", ["Aro", "Relleno"], horizontal=True,
                disabled=marco_plano == "Ninguno", key="tp_plano_marco_estilo",
                help="Aro: solo el contorno, como siempre. Relleno: la forma completa sólida de "
                     "un color -- combinalo con 'Texto sobre el marco' para que las letras la "
                     "calen (hueco) en vez de quedar tapadas."
            )
            marco_relleno_plano = marco_estilo_plano == "Relleno"
            texto_sobre_marco_plano = st.checkbox(
                "Texto sobre el marco", value=False,
                disabled=marco_plano == "Ninguno", key="tp_plano_texto_sobre_marco",
                help="Solo importa si el texto llega a tocar el marco (con poca distancia o "
                     "texto grande). Destildado (de siempre): el marco tapa al texto donde se "
                     "crucen. Tildado: al revés, el texto queda encima y le hace un hueco al marco."
            )
            espesor_plano = st.slider("Espesor (mm)", 1.5, 6.0, 3.0, step=0.5, key="tp_plano_espesor")
            _n_lineas_activas = sum(1 for l in lineas_plano if l.strip()) or 1
            _alto_linea_base_estimado = tamaño_mm / _n_lineas_activas
            _min_separacion_lineas = float(-round(_alto_linea_base_estimado * 0.6))
            separacion_lineas_plano = st.slider(
                "Separación entre líneas (mm)", _min_separacion_lineas, 30.0, 10.0, step=1.0, key="tp_plano_separacion",
                help="Espacio entre los renglones cuando hay 2 o 3 líneas de texto. Negativo: "
                     "las líneas se acercan/superponen a propósito, sin agrandar las letras -- "
                     "se tocan y se sueldan solas (menos o ningún puente), pero el bloque de "
                     "texto completo queda más bajo que el tamaño elegido."
            )
            ancho_texto_plano = st.slider(
                "Ancho de las letras (%)", 80, 150, 100, step=5, key="tp_plano_ancho_texto",
                help="Estira (>100%) o comprime (<100%) todo el texto en horizontal -- al "
                     "ensanchar, las letras se tocan más entre sí y con las líneas de arriba/"
                     "abajo, así hacen falta menos conectores.",
            )
        with col_b:
            st.caption(
                "**Apoyo**: el palo se clava en la torta. Con 'Con base ancha' tildado, sale de "
                "una placa ancha (tipo barra en T) para que no se ladee/incline; destildado, sale "
                "derecho, clavado directo en el marco o el texto."
            )
            con_palo_plano = st.checkbox(
                "Palo para clavar en la torta", value=True, key="tp_plano_palo",
                help="El palito que se clava en la torta. Se ancla solo al marco (si hay), a la "
                     "base (si la activás abajo) o si no a la última línea de texto.",
            )
            largo_palo_plano = st.slider(
                "Largo del palo (mm)", 20.0, 100.0, 45.0, step=5.0,
                disabled=not con_palo_plano, key="tp_plano_palo_largo",
                help="Cuánto entra el palo en la torta.",
            )
            ancho_palo_plano = st.slider(
                "Ancho del palo (mm)", 3.0, 15.0, 6.0, step=1.0,
                disabled=not con_palo_plano, key="tp_plano_palo_ancho",
                help="Grosor del palo -- más ancho, más firme y menos frágil al clavarlo.",
            )
            solape_palo_plano = st.slider(
                "Solape del palo (mm)", 0.0, 8.0, 2.5, step=0.5,
                disabled=not con_palo_plano, key="tp_plano_palo_solape",
                help="Cuánto se mete el palo dentro del material real del marco/texto donde se "
                     "ancla, para soldar firme y derecho sin necesitar un puente. Si el diseño "
                     "queda flojo, subilo; si el palo se nota demasiado metido, bajalo.",
            )
            _palo_offset_max = float(max(20.0, round(tamaño_mm * 0.5)))
            palo_offset_x_plano = st.slider(
                "Ajuste horizontal del palo (mm)", -_palo_offset_max, _palo_offset_max, 0.0, step=1.0,
                disabled=not con_palo_plano, key="tp_plano_palo_offset_x",
                help="Corre el palo desde donde lo ancló automáticamente (el marco, la base, o el "
                     "mejor trazo de la última línea) -- por si preferís otro lugar a mano. 0 = "
                     "respeta el automático tal cual.",
            )
            con_base_plano = st.checkbox(
                "Con base ancha (tipo barra en T, más firme)", value=False, key="tp_plano_base",
                help="Agrega una placa ancha y fina debajo de todo el diseño -- el palo sale de "
                     "ahí, formando una especie de T para que no se ladee/incline. Sin tildar "
                     "esto, el palo sale derecho, clavado directo en el marco o el texto. También "
                     "sirve como alternativa visual al marco, para el estilo 'topper parado sobre "
                     "una base' (bautismo, casamiento)."
            )
            ancho_base_extra_plano = st.slider(
                "Ancho extra de la base (mm)", 0.0, 40.0, 10.0, step=2.0,
                disabled=not con_base_plano, key="tp_plano_base_ancho_extra",
                help="Cuánto más ancha es la placa que el diseño, a cada lado -- más ancho, más "
                     "firme el apoyo (la T queda más abierta), para que no se ladee/incline."
            )
            alto_base_plano = st.slider(
                "Alto de la base (mm)", 2.0, 15.0, 6.0, step=1.0,
                disabled=not con_base_plano, key="tp_plano_base_alto",
                help="Espesor de la placa -- más alto, más rígida, pero también más material.",
            )
        offset_vertical_plano = st.slider(
            "Mover el texto arriba/abajo (mm)", -30.0, 30.0, 0.0, step=1.0, key="tp_plano_offset_y",
            disabled=marco_plano == "Ninguno",
            help="Corre el bloque de texto hacia arriba (+) o abajo (-) DENTRO del marco, que "
                 "se queda quieto en su lugar. Sin marco no tiene efecto (no hay nada respecto "
                 "de qué descentrarlo)."
        )
        st.caption(
            "Las letras/líneas sueltas de la fuente elegida se conectan automáticamente con "
            "puentes finos para que todo salga como una sola pieza rígida."
        )

        st.markdown("**Decoración** (opcional, un dibujo/ícono propio pegado al topper)")
        # Rango del ajuste fino de posición (offset X/Y) -- relativo al tamaño del
        # diseño, compartido por la decoración simple y por cada casillero de
        # "Múltiples decoraciones" (se define acá, antes de las dos, para no duplicarlo).
        _offset_dec_max = float(max(50.0, round(tamaño_mm * 1.0)))
        # Tope de "Acercar al texto" -- más chico que el de offset X/Y a
        # propósito: acercar solo tiene que cerrar el hueco hasta tocar el
        # texto/marco, no cruzar todo el diseño. Relativo igual, para que
        # en un diseño chico (tamaño_mm mínimo) no se pueda pasar de largo
        # al otro lado del texto.
        _acercar_dec_max = float(max(10.0, round(tamaño_mm * 0.5)))
        origen_decoracion_plano = st.radio(
            "Origen", ["Ninguna", "SVG", "Imagen (un color)", "Imagen multicolor", "Múltiples decoraciones"],
            horizontal=True, key="tp_plano_decoracion_origen",
            help="Imagen multicolor: separa automáticamente hasta 4 colores reales de UNA "
                 "imagen (un logo, un escudo) en vez de una silueta de un solo color. "
                 "Múltiples decoraciones: hasta 4 dibujos DISTINTOS a la vez (ej. un corazón a "
                 "la derecha y una pata a la izquierda), cada uno con su propio lado y tamaño."
        )

        decoracion_svg_ruta = None
        decoracion_imagen_ruta = None
        decoracion_imagen_umbral_plano = 128
        decoracion_imagen_invertir_plano = False
        decoracion_multicolor_imagen_ruta = None
        indices_seleccionados_multicolor = []
        colores_asignados_decoracion = []
        decoraciones_multi = []
        colores_decoraciones_multi = []

        if origen_decoracion_plano == "SVG":
            decoracion_svg_subido = st.file_uploader(
                "SVG para la decoración", type=["svg"], key="tp_plano_decoracion_svg",
                help="Un dibujo suelto (una mariposa, un moño, un logo) que se pega al costado o "
                     "arriba del diseño -- funciona mejor con una silueta cerrada simple."
            )
            decoracion_svg_ruta = _resolver_archivo_subido(
                decoracion_svg_subido, "tp_plano_decoracion_svg", "_subido_tp_decoracion")

        elif origen_decoracion_plano == "Imagen (un color)":
            decoracion_imagen_subida = st.file_uploader(
                "Imagen (PNG/JPG) para la decoración", type=["png", "jpg", "jpeg"],
                key="tp_plano_decoracion_imagen",
                help="Un logo/ícono simple (silueta clara sobre fondo liso o transparente, no una foto)."
            )
            decoracion_imagen_ruta = _resolver_archivo_subido(
                decoracion_imagen_subida, "tp_plano_decoracion_imagen", "_subido_tp_decoracion")
            if decoracion_imagen_ruta:
                decoracion_imagen_invertir_plano = st.checkbox(
                    "Imagen clara sobre fondo oscuro", value=False, key="tp_plano_decoracion_imagen_invertir",
                )
                decoracion_imagen_umbral_plano = st.slider(
                    "Sensibilidad del contorno", 0, 255, 128, key="tp_plano_decoracion_imagen_umbral",
                    help="Si la imagen no tiene fondo transparente: qué tan oscuro tiene que ser "
                         "un píxel para contar como parte del dibujo."
                )

        elif origen_decoracion_plano == "Imagen multicolor":
            decoracion_multicolor_subida = st.file_uploader(
                "Imagen (PNG/JPG) o SVG a separar por color", type=["png", "jpg", "jpeg", "svg"],
                key="tp_plano_decoracion_multicolor_imagen",
                help="Un logo/escudo con colores bien definidos (no una foto ni degradados) -- "
                     "cada color que elijas abajo sale como su propia región, para pintarla con "
                     "el filamento real que corresponda. Si tenés el archivo en SVG (vectorial) "
                     "usá ese en vez del PNG/JPG: los colores ya vienen declarados en el archivo, "
                     "en vez de tener que adivinarlos analizando píxeles."
            )
            decoracion_multicolor_imagen_ruta = _resolver_archivo_subido(
                decoracion_multicolor_subida, "tp_plano_decoracion_multicolor_imagen", "_subido_tp_decoracion_multicolor")
            if decoracion_multicolor_imagen_ruta:
                colores_detectados_raw = topper.detectar_colores_imagen(decoracion_multicolor_imagen_ruta)
                if not colores_detectados_raw:
                    st.warning("No se pudo detectar ningún color con área en esta imagen.")
                else:
                    claves_check = [f"tp_plano_decoracion_multicolor_usar_{i}" for i in range(len(colores_detectados_raw))]
                    for i, key in enumerate(claves_check):
                        if key not in st.session_state:
                            st.session_state[key] = i < topper.MAX_COLORES_DECORACION_MULTICOLOR
                    marcados_actual = sum(1 for key in claves_check if st.session_state.get(key))

                    st.caption(
                        f"Se detectaron {len(colores_detectados_raw)} colores -- elegí hasta "
                        f"{topper.MAX_COLORES_DECORACION_MULTICOLOR} para usar (destildá los que "
                        "sean ruido de antialiasing, no colores reales del dibujo) y asignale un "
                        "filamento real a cada uno."
                    )
                    for i, (hex_detectado, frac) in enumerate(colores_detectados_raw):
                        col_check, col_swatch, col_sel = st.columns([1, 1, 3])
                        ya_marcado = st.session_state.get(claves_check[i], False)
                        deshabilitar = marcados_actual >= topper.MAX_COLORES_DECORACION_MULTICOLOR and not ya_marcado
                        usar = col_check.checkbox(
                            f"{frac * 100:.0f}%", key=claves_check[i], disabled=deshabilitar,
                            help="Destildado = no se usa este color (por ejemplo, si es ruido de "
                                 "antialiasing en vez de un color real del dibujo)."
                        )
                        col_swatch.color_picker(
                            f"tp_plano_decoracion_multicolor_muestra_{i}", value=hex_detectado, disabled=True,
                            label_visibility="collapsed", key=f"tp_plano_decoracion_multicolor_muestra_{i}",
                        )
                        sugerido = colores.nombre_mas_cercano(hex_detectado)
                        elegido = col_sel.selectbox(
                            f"tp_plano_decoracion_multicolor_color_{i}", list(colores.NOMBRES),
                            index=list(colores.NOMBRES).index(sugerido), disabled=not usar,
                            key=f"tp_plano_decoracion_multicolor_color_{i}", label_visibility="collapsed",
                        )
                        if usar:
                            indices_seleccionados_multicolor.append(i)
                            colores_asignados_decoracion.append(elegido)

        elif origen_decoracion_plano == "Múltiples decoraciones":
            st.caption(
                "Hasta 4 dibujos independientes, cada uno con su propio origen, lado y tamaño "
                "-- por ejemplo un corazón a la derecha y una pata a la izquierda."
            )
            for i in range(topper.MAX_COLORES_DECORACION_MULTICOLOR):
                with st.expander(f"Decoración {i + 1}", expanded=(i == 0)):
                    usar_slot = st.checkbox(
                        "Usar esta decoración", value=False, key=f"tp_plano_multi_dec_{i}_usar",
                    )
                    if not usar_slot:
                        continue
                    tipo_slot = st.radio(
                        "Tipo", ["SVG", "Imagen"], horizontal=True,
                        key=f"tp_plano_multi_dec_{i}_tipo",
                    )
                    item = {}
                    if tipo_slot == "SVG":
                        subido = st.file_uploader(
                            "SVG", type=["svg"], key=f"tp_plano_multi_dec_{i}_svg",
                        )
                        ruta = _resolver_archivo_subido(
                            subido, f"tp_plano_multi_dec_{i}_svg", f"_subido_tp_multidec_{i}")
                        if ruta:
                            item["svg"] = ruta
                    else:
                        subido = st.file_uploader(
                            "Imagen (PNG/JPG)", type=["png", "jpg", "jpeg"],
                            key=f"tp_plano_multi_dec_{i}_imagen",
                        )
                        ruta = _resolver_archivo_subido(
                            subido, f"tp_plano_multi_dec_{i}_imagen", f"_subido_tp_multidec_{i}")
                        if ruta:
                            item["imagen"] = ruta
                            item["invertir"] = st.checkbox(
                                "Imagen clara sobre fondo oscuro", value=False,
                                key=f"tp_plano_multi_dec_{i}_invertir",
                            )
                            item["umbral"] = st.slider(
                                "Sensibilidad del contorno", 0, 255, 128,
                                key=f"tp_plano_multi_dec_{i}_umbral",
                            )
                    col_ld, col_tm = st.columns(2)
                    item["lado"] = col_ld.selectbox(
                        "Lado", topper.LADOS_DECORACION_PLANO, key=f"tp_plano_multi_dec_{i}_lado",
                    )
                    item["tam_mm"] = col_tm.slider(
                        "Tamaño (mm)", 8.0, 150.0, 25.0, step=1.0, key=f"tp_plano_multi_dec_{i}_tam",
                    )
                    col_ox, col_oy = st.columns(2)
                    item["offset_x_mm"] = col_ox.slider(
                        "Correr horizontal (mm)", -_offset_dec_max, _offset_dec_max, 0.0, step=1.0,
                        key=f"tp_plano_multi_dec_{i}_offset_x",
                        help="Ajusta fino la posición que ya da 'Lado', sin cambiarlo -- positivo "
                             "hacia la derecha.",
                    )
                    item["offset_y_mm"] = col_oy.slider(
                        "Correr vertical (mm)", -_offset_dec_max, _offset_dec_max, 0.0, step=1.0,
                        key=f"tp_plano_multi_dec_{i}_offset_y",
                        help="Ídem, positivo hacia arriba.",
                    )
                    item["acercar_mm"] = st.slider(
                        "Acercar al texto (mm)", 0.0, _acercar_dec_max, 0.0, step=1.0,
                        key=f"tp_plano_multi_dec_{i}_acercar",
                        help="Después del Lado y de 'Correr horizontal/vertical', empuja ESTA "
                             "decoración hacia el centro del texto/marco -- lo suficiente y se "
                             "suelda sólida, sin necesitar un conector.",
                    )
                    color_slot = st.selectbox(
                        "Color", list(colores.NOMBRES),
                        index=list(colores.NOMBRES).index("Dorado"),
                        key=f"tp_plano_multi_dec_{i}_color",
                    )
                    if item.get("svg") or item.get("imagen"):
                        decoraciones_multi.append(item)
                        colores_decoraciones_multi.append(color_slot)

        hay_decoracion = (
            decoracion_svg_ruta is not None or decoracion_imagen_ruta is not None
            or bool(indices_seleccionados_multicolor) or bool(decoraciones_multi)
        )
        col_d1, col_d2 = st.columns(2)
        decoracion_lado_plano = col_d1.selectbox(
            "Lado", topper.LADOS_DECORACION_PLANO, key="tp_plano_decoracion_lado",
            disabled=not hay_decoracion or origen_decoracion_plano == "Múltiples decoraciones",
            help="Con 'Múltiples decoraciones' cada una tiene su propio lado, elegido arriba."
                 if origen_decoracion_plano == "Múltiples decoraciones" else None,
        )
        decoracion_tam_plano = col_d2.slider(
            "Tamaño (mm)", 8.0, 150.0, 25.0, step=1.0, key="tp_plano_decoracion_tam",
            disabled=not hay_decoracion or origen_decoracion_plano == "Múltiples decoraciones",
        )
        col_d3, col_d4 = st.columns(2)
        decoracion_offset_x_plano = col_d3.slider(
            "Correr horizontal (mm)", -_offset_dec_max, _offset_dec_max, 0.0, step=1.0,
            key="tp_plano_decoracion_offset_x",
            disabled=not hay_decoracion or origen_decoracion_plano == "Múltiples decoraciones",
            help="Ajusta fino la posición que ya da 'Lado', sin cambiarlo -- positivo hacia la "
                 "derecha. Útil para acercar una decoración separada hasta que toque el texto "
                 "sin tener que agrandarla.",
        )
        decoracion_offset_y_plano = col_d4.slider(
            "Correr vertical (mm)", -_offset_dec_max, _offset_dec_max, 0.0, step=1.0,
            key="tp_plano_decoracion_offset_y",
            disabled=not hay_decoracion or origen_decoracion_plano == "Múltiples decoraciones",
            help="Ídem, positivo hacia arriba.",
        )
        decoracion_acercar_plano = st.slider(
            "Acercar al texto (mm)", 0.0, _acercar_dec_max, 0.0, step=1.0,
            key="tp_plano_decoracion_acercar",
            disabled=not hay_decoracion or origen_decoracion_plano == "Múltiples decoraciones",
            help="Después del Lado y de 'Correr horizontal/vertical', empuja la decoración esa "
                 "distancia hacia el centro del texto/marco -- lo suficiente y se suelda sólida, "
                 "sin necesitar un conector.",
        )
        decoracion_sobre_marco_plano = st.checkbox(
            "Decoración sobre el marco", value=False,
            disabled=not hay_decoracion or marco_plano == "Ninguno",
            key="tp_plano_decoracion_sobre_marco",
            help="Igual que 'Texto sobre el marco' pero para la decoración. Solo importa si "
                 "llega a tocar el marco (lado/tamaño grande). Destildado (de siempre): el "
                 "marco tapa a la decoración donde se crucen. Tildado: al revés."
        )

        st.markdown("**Colores** (para imprimir con AMS multicolor, o de guía para pintar a mano)")
        borde_texto_plano = st.slider(
            "Borde del texto (mm)", 0.0, 3.0, 0.0, step=0.25, key="tp_plano_borde",
            help="Un contorno fino alrededor de cada letra, de un color distinto al del texto. 0 = sin borde."
        )
        col_t1, col_t2, col_t3 = st.columns(3)
        color_texto_plano = col_t1.selectbox(
            "Texto línea 1", list(colores.NOMBRES), index=list(colores.NOMBRES).index("Dorado"),
            key="tp_plano_color_texto",
        )
        color_texto_2_plano = col_t2.selectbox(
            "Texto línea 2", list(colores.NOMBRES), index=list(colores.NOMBRES).index("Dorado"),
            disabled=not linea2.strip(), key="tp_plano_color_texto_2",
            help="Si coincide con la línea 1 (y la 3, si hay), las tres se exportan como una "
                 "sola región de texto -- distinto solo si de verdad querés colores por línea.",
        )
        color_texto_3_plano = col_t3.selectbox(
            "Texto línea 3", list(colores.NOMBRES), index=list(colores.NOMBRES).index("Dorado"),
            disabled=not linea3.strip(), key="tp_plano_color_texto_3",
        )
        col_c1, col_c2, col_c3 = st.columns(3)
        color_borde_plano = col_c1.selectbox(
            "Borde", list(colores.NOMBRES), index=list(colores.NOMBRES).index("Negro"),
            disabled=borde_texto_plano <= 0, key="tp_plano_color_borde",
        )
        color_marco_plano = col_c2.selectbox(
            "Marco", list(colores.NOMBRES), index=list(colores.NOMBRES).index("Dorado"),
            disabled=marco_plano == "Ninguno", key="tp_plano_color_marco",
        )
        color_marco_borde_plano = col_c2.selectbox(
            "Color del borde del marco", list(colores.NOMBRES), index=list(colores.NOMBRES).index("Dorado"),
            disabled=marco_plano == "Ninguno" or not marco_relleno_plano, key="tp_plano_color_marco_borde",
            help="Solo con marco Relleno. Si coincide con 'Marco', el interior y el borde se "
                 "exportan como una sola región -- distinto solo si de verdad querés un contorno "
                 "de otro color.",
        )
        color_base_plano = col_c3.selectbox(
            "Base", list(colores.NOMBRES), index=list(colores.NOMBRES).index("Dorado"),
            disabled=not con_base_plano, key="tp_plano_color_base",
        )
        col_c4, col_c5, col_c6 = st.columns(3)
        color_palo_plano = col_c4.selectbox(
            "Palo", list(colores.NOMBRES), index=list(colores.NOMBRES).index("Dorado"),
            disabled=not con_palo_plano, key="tp_plano_color_palo",
        )
        color_decoracion_plano = col_c5.selectbox(
            "Decoración", list(colores.NOMBRES), index=list(colores.NOMBRES).index("Dorado"),
            disabled=not hay_decoracion or origen_decoracion_plano in ("Imagen multicolor", "Múltiples decoraciones"),
            key="tp_plano_color_decoracion",
            help="Con 'Imagen multicolor'/'Múltiples decoraciones' no se usa este selector -- "
                 "el color de cada región sale de lo elegido arriba, en cada dibujo."
                 if origen_decoracion_plano in ("Imagen multicolor", "Múltiples decoraciones") else None,
        )
        # En modo "Imagen multicolor"/"Múltiples decoraciones" los colores
        # salen de lo elegido arriba (uno por color detectado, o uno por
        # decoración), no de este selector -- se completa con "Dorado" si
        # por algún motivo hay menos de 4 colores asignados.
        if origen_decoracion_plano == "Imagen multicolor" and colores_asignados_decoracion:
            _colores_decoracion_final = (colores_asignados_decoracion + ["Dorado"] * 4)[:4]
        elif origen_decoracion_plano == "Múltiples decoraciones" and colores_decoraciones_multi:
            _colores_decoracion_final = (colores_decoraciones_multi + ["Dorado"] * 4)[:4]
        else:
            _colores_decoracion_final = [color_decoracion_plano, "Blanco", "Negro", "Gris Frío"]
        color_conectores_plano = col_c6.selectbox(
            "Conectores", list(colores.NOMBRES), index=list(colores.NOMBRES).index("Transparente/Natural"),
            key="tp_plano_color_conectores",
            help="Los puentes finos que sueldan letras sueltas (y el palo, si hace falta). "
                 "Un filamento transparente/natural hace que casi no se noten.",
        )
        tiene_ams_plano = st.checkbox(
            "Imprimir con AMS (multicolor)", value=False, key="tp_plano_ams",
            help="Sin esto, el STL sale en una sola pieza para imprimir de un solo color (podés "
                 "pintarlo a mano después usando la vista previa de colores como guía). Con "
                 "esto, además se genera un STL multicolor (piezas sueltas por región, para "
                 "'Partir en objetos' en Bambu Studio y asignarles color ahí) y un .3mf con los "
                 "colores pre-asignados -- este último es experimental, a veces Bambu Studio no "
                 "lo carga bien."
        )

    elif "3D" in tipo_topper:
        st.subheader("Parámetros 3D")
        col_a, col_b = st.columns(2)
        with col_a:
            material_3d = st.selectbox("Material", ["PLA", "PETG", "ABS", "Resin"], key="tp_material")
            color_3d = st.selectbox("Color", list(colores.NOMBRES), index=0, key="tp_color")
        with col_b:
            base_tipo = st.selectbox(
                "Tipo de base", topper.BASES, key="tp_base_tipo",
                help=(
                    "Elegí una forma (Redonda/Ovalada/Cuadrada/Rectangular) combinada con un "
                    "modo: Plana (se apoya), Con palo (se clava en la torta) o Con figura arriba "
                    "(agrega el objeto decorativo elegido sobre un tallo). "
                    "'Redonda (letras paradas)': cada letra parada sobre un disco. "
                    "'Sin base': solo la figura/texto, sin ninguna placa."
                )
            )
            objeto_decorativo = st.selectbox(
                "Objeto decorativo", topper.OBJETOS_DECORATIVOS, key="tp_objeto",
                help="Se agrega al costado del texto (o como figura central si la base es \"Con figura arriba\"). Cada tipo tiene su propia silueta simplificada."
            )

    elif "Neón" in tipo_topper:
        st.subheader("Parámetros Neón")
        tipo_led = st.radio("Tipo", ["Flexible (frío)", "Rígido (cálido)", "RGB"], horizontal=True, key="tp_neon_tipo")
        grosor_tubo = st.slider("Diámetro tubo (mm)", 5, 15, 10, step=1, key="tp_neon_grosor")

    elif "LED" in tipo_topper:
        st.subheader("Parámetros LED")
        material_led = st.selectbox("Material estructura", ["PLA", "Acrílico", "Madera"], key="tp_led_material")
        efecto = st.selectbox("Efecto", ["Fijo", "Parpadeo", "Secuencial", "Arcoíris"], key="tp_led_efecto")
        baterias = st.checkbox("Incluir compartimiento para batería", value=True, key="tp_led_bat")

    elif "Acrílico" in tipo_topper:
        st.subheader("Parámetros Acrílico")
        espesor_acrilico = st.slider("Espesor (mm)", 2, 8, 3, step=1, key="tp_acrilico_espesor")
        acabado = st.selectbox("Acabado", ["Espejo", "Transparente", "Mate", "Color"], key="tp_acrilico_acabado")

    generar_click = st.button("Generar topper", type="primary", use_container_width=True)

with col_preview:
    st.subheader("👁️ Vista previa")

    # Preview visual por tipo — texto y fuente reales
    if es_plano:
        if marco_plano == "SVG propio" and not marco_svg_ruta:
            st.info("Subí un SVG para el marco para ver la vista previa.")
        elif marco_plano == "Imagen propia" and not marco_imagen_ruta:
            st.info("Subí una imagen para el marco para ver la vista previa.")
        else:
            html_preview = topper.preview_html_plano(
                lineas_plano, tamaño_mm, marco_plano, ruta_fuente, marco_svg=marco_svg_ruta,
                marco_imagen=marco_imagen_ruta, marco_imagen_umbral=marco_imagen_umbral_plano,
                marco_imagen_invertir=marco_imagen_invertir_plano,
                decoracion_svg=decoracion_svg_ruta, decoracion_imagen=decoracion_imagen_ruta,
                decoracion_imagen_umbral=decoracion_imagen_umbral_plano,
                decoracion_imagen_invertir=decoracion_imagen_invertir_plano,
                decoracion_multicolor_imagen=decoracion_multicolor_imagen_ruta,
                decoracion_multicolor_indices=indices_seleccionados_multicolor,
                decoraciones=decoraciones_multi if origen_decoracion_plano == "Múltiples decoraciones" else None,
                decoracion_tam_mm=decoracion_tam_plano,
                decoracion_lado=decoracion_lado_plano, decoracion_sobre_marco=decoracion_sobre_marco_plano,
                decoracion_offset_x_mm=decoracion_offset_x_plano, decoracion_offset_y_mm=decoracion_offset_y_plano,
                decoracion_acercar_mm=decoracion_acercar_plano,
                multiplicadores_linea=multiplicadores_lineas_plano, ancho_texto_factor=ancho_texto_plano / 100.0,
                color_texto=colores.hex_de(color_texto_plano), color_texto_2=colores.hex_de(color_texto_2_plano),
                color_texto_3=colores.hex_de(color_texto_3_plano),
                color_borde=colores.hex_de(color_borde_plano),
                color_marco=colores.hex_de(color_marco_plano), color_marco_borde=colores.hex_de(color_marco_borde_plano),
                color_palo=colores.hex_de(color_palo_plano),
                color_decoracion=colores.hex_de(_colores_decoracion_final[0]),
                color_decoracion_2=colores.hex_de(_colores_decoracion_final[1]),
                color_decoracion_3=colores.hex_de(_colores_decoracion_final[2]),
                color_decoracion_4=colores.hex_de(_colores_decoracion_final[3]),
                color_conectores=colores.hex_de(color_conectores_plano),
                color_base=colores.hex_de(color_base_plano),
                separacion_lineas_mm=separacion_lineas_plano, offset_vertical_mm=offset_vertical_plano,
                borde_texto_mm=borde_texto_plano,
                margen_marco_mm=margen_marco_plano, grosor_marco_mm=grosor_marco_plano,
                texto_sobre_marco=texto_sobre_marco_plano,
                marco_tam_automatico=marco_tam_automatico_plano, marco_tam_mm=marco_tam_manual_plano,
                marco_relleno=marco_relleno_plano,
                con_palo=con_palo_plano, largo_palo_mm=largo_palo_plano, ancho_palo_mm=ancho_palo_plano,
                solape_palo_mm=solape_palo_plano, palo_offset_x_mm=palo_offset_x_plano,
                con_base=con_base_plano, ancho_base_extra_mm=ancho_base_extra_plano, alto_base_mm=alto_base_plano,
            )
            if html_preview:
                components.html(f'<div style="display:flex;justify-content:center;width:100%">{html_preview}</div>', height=320)
            else:
                st.info("Escribí al menos una línea de texto para ver la vista previa.")

    elif "3D" in tipo_topper:
        color_hex = dict(colores.PALETA).get(color_3d, "#cccccc")
        html_preview = topper.preview_html_3d(
            texto or "Topper", tamaño_mm, estilo, base_tipo, color_hex, ruta_fuente
        )
        components.html(f'<div style="display:flex;justify-content:center;width:100%">{html_preview}</div>', height=300)

    elif "Neón" in tipo_topper:
        largo_estimado = len((texto or "Topper")) * 6 + 20
        html_preview = topper.preview_html_neon(texto or "Topper", grosor_tubo, largo_estimado, ruta_fuente)
        components.html(f'<div style="display:flex;justify-content:center;width:100%;background:#111;border-radius:8px">{html_preview}</div>', height=180)

    elif "LED" in tipo_topper:
        html_preview = topper.preview_html_led(texto or "Topper", efecto, tamaño_mm, ruta_fuente)
        components.html(f'<div style="display:flex;justify-content:center;width:100%;background:#111;border-radius:8px">{html_preview}</div>', height=300)

    elif "Acrílico" in tipo_topper:
        ancho_est = tamaño_mm + 20
        alto_est = int(tamaño_mm * 0.6) + 10
        html_preview = topper.preview_html_acrilico(texto or "Topper", espesor_acrilico, ancho_est, alto_est, ruta_fuente)
        components.html(f'<div style="display:flex;justify-content:center;width:100%">{html_preview}</div>', height=200)

    st.divider()
    st.subheader("📊 Especificaciones")

    # Mostrar specs por tipo
    if es_plano:
        n_lineas = sum(1 for l in lineas_plano if l.strip())
        col_spec1, col_spec2 = st.columns(2)
        with col_spec1:
            st.metric("Tamaño", f"{tamaño_mm}mm")
            st.metric("Líneas", n_lineas)
        with col_spec2:
            st.metric("Marco", marco_plano)
            st.metric("Espesor", f"{espesor_plano}mm")
        st.caption("⚙️ Tiempo: 15-30 min | Costo material: muy bajo | Una sola pieza, se imprime plana")

    elif "3D" in tipo_topper:
        col_spec1, col_spec2 = st.columns(2)
        with col_spec1:
            st.metric("Tamaño estimado", f"{tamaño_mm}mm")
            st.metric("Material", material_3d)
            st.metric("Tema", tema)
        with col_spec2:
            st.metric("Estilo", estilo)
            st.metric("Base", base_tipo.split(" ")[0])
            st.metric("Decoración", objeto_decorativo)
        st.caption("⚙️ Tiempo: 2-6 min | Costo material: bajo")

    elif "Neón" in tipo_topper:
        col_spec1, col_spec2 = st.columns(2)
        with col_spec1:
            st.metric("Tipo LED", tipo_led.split("(")[0].strip())
            st.metric("Diámetro", f"{grosor_tubo}mm")
        with col_spec2:
            st.metric("Voltaje", "24V")
            st.metric("Consumo est.", "0.1W")
        st.caption("⚙️ Tiempo: 1-2h instalación | Costo: medio")

    elif "LED" in tipo_topper:
        col_spec1, col_spec2 = st.columns(2)
        with col_spec1:
            st.metric("Efecto", efecto)
            st.metric("Material", material_led)
        with col_spec2:
            st.metric("Voltaje", "5V USB" if baterias else "12V")
            st.metric("Consumo", {"Fijo": "5W", "Parpadeo": "4.5W", "Secuencial": "5.5W", "Arcoíris": "6W"}.get(efecto, "5W"))
        st.caption("⚙️ Tiempo: 3-4h montaje | Costo: alto")

    elif "Acrílico" in tipo_topper:
        col_spec1, col_spec2 = st.columns(2)
        with col_spec1:
            st.metric("Espesor", f"{espesor_acrilico}mm")
            st.metric("Acabado", acabado)
        with col_spec2:
            st.metric("Potencia láser", f"{espesor_acrilico * 20 * {'Espejo': 0.8, 'Transparente': 1.0, 'Mate': 1.2, 'Color': 0.9}.get(acabado, 1.0):.0f}W")
            st.metric("Tiempo corte", f"{(tamaño_mm * 2 + 40) / 5:.1f}s")
        st.caption("⚙️ Tiempo: 10-20 min | Costo: muy bajo")

    st.divider()

    if generar_click:
        if es_plano and not any(l.strip() for l in lineas_plano):
            st.error("Escribí al menos una línea de texto")
        elif es_plano and marco_plano == "SVG propio" and not marco_svg_ruta:
            st.error("Subí un SVG para el marco (o cambiá a otra forma de marco)")
        elif es_plano and marco_plano == "Imagen propia" and not marco_imagen_ruta:
            st.error("Subí una imagen para el marco (o cambiá a otra forma de marco)")
        elif es_plano and origen_decoracion_plano == "Imagen multicolor" and not decoracion_multicolor_imagen_ruta:
            st.error("Subí una imagen para la decoración multicolor (o cambiá el origen)")
        elif es_plano and origen_decoracion_plano == "Múltiples decoraciones" and not decoraciones_multi:
            st.error("Activá y subí al menos una decoración (o cambiá el origen)")
        elif not es_plano and not texto.strip():
            st.error("Ingresá un texto/diseño")
        else:
            with st.spinner("Generando topper..."):
                try:
                    if es_plano:
                        resultado = topper.generar_plano(
                            lineas=lineas_plano,
                            tamaño_mm=tamaño_mm,
                            fuente=ruta_fuente,
                            marco=marco_plano,
                            marco_svg=marco_svg_ruta,
                            marco_imagen=marco_imagen_ruta,
                            marco_imagen_umbral=marco_imagen_umbral_plano,
                            marco_imagen_invertir=marco_imagen_invertir_plano,
                            texto_sobre_marco=texto_sobre_marco_plano,
                            marco_tam_automatico=marco_tam_automatico_plano,
                            marco_tam_mm=marco_tam_manual_plano,
                            marco_relleno=marco_relleno_plano,
                            decoracion_svg=decoracion_svg_ruta,
                            decoracion_imagen=decoracion_imagen_ruta,
                            decoracion_imagen_umbral=decoracion_imagen_umbral_plano,
                            decoracion_imagen_invertir=decoracion_imagen_invertir_plano,
                            decoracion_multicolor_imagen=decoracion_multicolor_imagen_ruta,
                            decoracion_multicolor_indices=indices_seleccionados_multicolor,
                            decoraciones=decoraciones_multi if origen_decoracion_plano == "Múltiples decoraciones" else None,
                            decoracion_tam_mm=decoracion_tam_plano,
                            decoracion_lado=decoracion_lado_plano,
                            decoracion_sobre_marco=decoracion_sobre_marco_plano,
                            decoracion_offset_x_mm=decoracion_offset_x_plano,
                            decoracion_offset_y_mm=decoracion_offset_y_plano,
                            decoracion_acercar_mm=decoracion_acercar_plano,
                            multiplicadores_linea=multiplicadores_lineas_plano,
                            ancho_texto_factor=ancho_texto_plano / 100.0,
                            margen_marco_mm=margen_marco_plano,
                            grosor_marco_mm=grosor_marco_plano,
                            separacion_lineas_mm=separacion_lineas_plano,
                            offset_vertical_mm=offset_vertical_plano,
                            borde_texto_mm=borde_texto_plano,
                            con_palo=con_palo_plano,
                            largo_palo_mm=largo_palo_plano,
                            ancho_palo_mm=ancho_palo_plano,
                            solape_palo_mm=solape_palo_plano,
                            palo_offset_x_mm=palo_offset_x_plano,
                            con_base=con_base_plano,
                            ancho_base_extra_mm=ancho_base_extra_plano,
                            alto_base_mm=alto_base_plano,
                            espesor_mm=espesor_plano,
                            tiene_ams=tiene_ams_plano,
                            color_texto=color_texto_plano,
                            color_texto_2=color_texto_2_plano,
                            color_texto_3=color_texto_3_plano,
                            color_borde=color_borde_plano,
                            color_marco=color_marco_plano,
                            color_marco_borde=color_marco_borde_plano,
                            color_palo=color_palo_plano,
                            color_decoracion=_colores_decoracion_final[0],
                            color_decoracion_2=_colores_decoracion_final[1],
                            color_decoracion_3=_colores_decoracion_final[2],
                            color_decoracion_4=_colores_decoracion_final[3],
                            color_conectores=color_conectores_plano,
                            color_base=color_base_plano,
                        )

                        piezas_visor_plano = [
                            {"ruta_stl": p["ruta_stl"], "color": colores.hex_de(p["color"]), "nombre": p["clave"]}
                            for p in resultado.get("piezas_color", [])
                        ]
                        html_visor = preview3d.armar_html_visor(piezas_visor_plano, height_px=500)
                        if html_visor:
                            components.html(html_visor, height=500, scrolling=False)

                        st.markdown(f"""
                        ### ✓ Topper Plano generado
                        - **Líneas:** {" / ".join(resultado['lineas'])}
                        - **Marco:** {resultado['marco']} · **Tamaño:** {resultado['tamaño_mm']}mm
                        - **Puentes de unión:** {resultado['puentes']}
                        - **Vértices:** {resultado['vertices']} | **Caras:** {resultado['caras']}
                        - **Watertight:** {"✓ Sí" if resultado['watertight'] else "✗ No"}
                        """)

                        if resultado.get("avisos_conectores"):
                            st.warning(resultado["avisos_conectores"])

                        if "ruta_stl" in resultado:
                            with open(resultado["ruta_stl"], "rb") as f:
                                st.download_button(
                                    "📥 Descargar STL (una sola pieza/color)",
                                    f.read(),
                                    file_name=os.path.basename(resultado["ruta_stl"]),
                                    mime="application/octet-stream"
                                )

                        if resultado.get("ruta_stl_multicolor"):
                            st.caption(
                                "Para AMS (recomendado): abrí este STL en Bambu Studio, clic derecho sobre "
                                "la pieza → **\"Partir en objetos\"** → asignale el color real a cada parte "
                                "(quedan en el mismo orden que elegiste acá arriba). Un paso extra, pero anda seguro."
                            )
                            with open(resultado["ruta_stl_multicolor"], "rb") as f:
                                st.download_button(
                                    "📥 Descargar STL multicolor (para AMS, partir en objetos)",
                                    f.read(),
                                    file_name=os.path.basename(resultado["ruta_stl_multicolor"]),
                                    mime="application/octet-stream",
                                )
                        if resultado.get("ruta_3mf_multicolor"):
                            with st.expander("3MF con colores pre-asignados (experimental, puede no cargar bien)"):
                                st.caption(
                                    "Debería abrir con los colores ya puestos sin el paso de \"Partir en "
                                    "objetos\", pero Bambu Studio a veces lo rechaza parcialmente "
                                    "(\"configuración no válida\") y termina con los colores del proyecto "
                                    "actual en vez de los elegidos acá. Si te pasa eso, usá el STL de arriba."
                                )
                                if resultado.get("aviso_colores_3mf"):
                                    st.warning(resultado["aviso_colores_3mf"])
                                with open(resultado["ruta_3mf_multicolor"], "rb") as f:
                                    st.download_button(
                                        "📥 Descargar 3MF multicolor (experimental)",
                                        f.read(),
                                        file_name=os.path.basename(resultado["ruta_3mf_multicolor"]),
                                        mime="model/3mf",
                                    )

                    elif "3D" in tipo_topper:
                        resultado = topper.generar_3d(
                            texto=texto,
                            tamaño_mm=tamaño_mm,
                            estilo=estilo,
                            color=color_3d,
                            base_tipo=base_tipo,
                            material=material_3d,
                            tema=tema,
                            objeto_decorativo=objeto_decorativo,
                            fuente=ruta_fuente,
                        )

                        if "ruta_stl" in resultado and os.path.exists(resultado["ruta_stl"]):
                            html_visor = preview3d.armar_html_visor(
                                [{"ruta_stl": resultado["ruta_stl"], "color": dict(colores.PALETA).get(color_3d, "#f4f4f2")}],
                                height_px=500
                            )
                            if html_visor:
                                components.html(html_visor, height=500, scrolling=False)

                        st.markdown(f"""
                        ### ✓ Topper 3D generado
                        - **Material:** {resultado['material']} · **Color:** {resultado['color']}
                        - **Tamaño:** {resultado['tamaño_mm']}mm · **Estilo:** {resultado['estilo']}
                        - **Base:** {resultado['base']}
                        - **Tema:** {resultado['tema']} · **Decoración:** {resultado['objeto_decorativo']}
                        - **Vértices:** {resultado['vertices']} | **Caras:** {resultado['caras']}
                        - **Watertight:** {"✓ Sí" if resultado['watertight'] else "✗ No"}
                        """)

                        if "ruta_stl" in resultado:
                            with open(resultado["ruta_stl"], "rb") as f:
                                st.download_button(
                                    "📥 Descargar STL",
                                    f.read(),
                                    file_name=os.path.basename(resultado["ruta_stl"]),
                                    mime="application/octet-stream"
                                )

                    elif "Neón" in tipo_topper:
                        resultado = topper.generar_neon(
                            texto=texto, tamaño_mm=tamaño_mm, tipo_led=tipo_led,
                            grosor_tubo=grosor_tubo, fuente=ruta_fuente,
                        )

                        st.markdown(f"""
                        ### ✓ Topper Neón generado
                        - **Tipo LED:** {resultado['tipo_led']}
                        - **Largo tubo:** {resultado['largo_tubo_mm']}mm
                        - **Grosor:** {resultado['grosor_tubo']}mm
                        - **Voltaje:** {resultado['voltaje']}
                        - **Consumo:** {resultado['consumo_w']}W
                        """)

                        if "ruta_dxf" in resultado and os.path.exists(resultado["ruta_dxf"]):
                            with open(resultado["ruta_dxf"], "rb") as f:
                                st.download_button(
                                    "📥 Descargar DXF",
                                    f.read(),
                                    file_name=os.path.basename(resultado["ruta_dxf"]),
                                    mime="application/dxf"
                                )

                    elif "LED" in tipo_topper:
                        resultado = topper.generar_led(
                            texto=texto, tamaño_mm=tamaño_mm, material=material_led,
                            efecto=efecto, con_bateria=baterias, fuente=ruta_fuente,
                        )

                        if "ruta_stl" in resultado and os.path.exists(resultado["ruta_stl"]):
                            html_visor = preview3d.armar_html_visor(
                                [{"ruta_stl": resultado["ruta_stl"], "color": "#ff6b35"}], height_px=500
                            )
                            if html_visor:
                                components.html(html_visor, height=500, scrolling=False)

                        st.markdown(f"""
                        ### ✓ Topper LED generado
                        - **Material:** {resultado['material']}
                        - **Efecto:** {resultado['efecto']}
                        - **Tamaño:** {resultado['tamaño_mm']}mm
                        - **Voltaje:** {resultado['voltaje']}
                        - **Consumo:** {resultado['consumo_w']}W
                        - **Vértices:** {resultado['vertices']} | **Caras:** {resultado['caras']}
                        """)

                        if "ruta_stl" in resultado:
                            with open(resultado["ruta_stl"], "rb") as f:
                                st.download_button(
                                    "📥 Descargar STL",
                                    f.read(),
                                    file_name=os.path.basename(resultado["ruta_stl"]),
                                    mime="application/octet-stream"
                                )

                    elif "Acrílico" in tipo_topper:
                        resultado = topper.generar_acrilico(
                            texto=texto, tamaño_mm=tamaño_mm, espesor_mm=espesor_acrilico,
                            acabado=acabado, fuente=ruta_fuente,
                        )

                        st.markdown(f"""
                        ### ✓ Topper Acrílico generado
                        - **Acabado:** {resultado['acabado']}
                        - **Espesor:** {resultado['espesor_mm']}mm
                        - **Dimensiones:** {resultado['ancho']}×{resultado['alto']}mm
                        - **Potencia láser:** {resultado['potencia_w']}W
                        - **Tiempo corte:** {resultado['tiempo_corte_s']}s
                        """)

                        if "ruta_dxf" in resultado and os.path.exists(resultado["ruta_dxf"]):
                            with open(resultado["ruta_dxf"], "rb") as f:
                                st.download_button(
                                    "📥 Descargar DXF",
                                    f.read(),
                                    file_name=os.path.basename(resultado["ruta_dxf"]),
                                    mime="application/dxf"
                                )

                except Exception as e:
                    st.error(f"Error: {str(e)}")

st.divider()

# Comparativa
with st.expander("📊 Comparativa de toppers"):
    comp_data = {
        "Tipo": ["3D", "Neón", "LED", "Acrílico"],
        "Tiempo": ["2-6 min", "1-2h", "3-4h", "10-20 min"],
        "Costo": ["Bajo", "Medio", "Alto", "Muy bajo"],
        "Durabilidad": ["Excelente", "Buena", "Excelente", "Media"],
        "Interactividad": ["—", "Luz", "Luz+Efecto", "—"],
        "Reutilizable": ["Sí", "Sí", "Sí", "No"],
    }
    st.dataframe(comp_data, use_container_width=True)

# Guía de bases (nuevo)
with st.expander("🧱 Guía de tipos de base (Topper 3D)"):
    st.markdown("""
    Cada base combina una **forma** con un **modo** — 4 formas × 3 modos = 12 combinaciones,
    más 2 casos especiales:

    **Formas:** Redonda, Ovalada, Cuadrada, Rectangular.

    **Modos:**
    - **Plana (apoyada):** base clásica que se apoya sobre la torta. Estable, fácil de imprimir.
    - **Con palo (clavar en torta):** incluye un palito rígido que se clava directo en el bizcocho — típico de toppers de cumpleaños/fiesta.
    - **Con figura arriba:** la base + el objeto decorativo elegido (flores, corazón, personaje, pareja, etc.) sobre un tallo corto, al costado del texto.

    **Casos especiales:**
    - **Redonda (letras paradas):** disco de base con las letras del texto paradas individualmente sobre él — look tipo "nombre en la torta".
    - **Sin base (figura libre):** solo el texto/figura, sin ninguna base — se apoya directo sobre el fondant o la superficie.

    Ejemplos: *"Cuadrada — Con palo (clavar en torta)"*, *"Ovalada — Con figura arriba"*, *"Rectangular — Plana (apoyada)"*.
    """)

# Guía de selección
with st.expander("🎯 Guía de selección"):
    st.markdown("""
    **Elige 3D si:** querés un topper clásico impreso, presupuesto limitado, personajes/logos complejos.

    **Elige Neón si:** buscás efecto luminoso básico, evento nocturno, presupuesto medio.

    **Elige LED si:** querés efecto luminoso avanzado (parpadeo, secuencias), evento especial premium, baterías integradas.

    **Elige Acrílico si:** presupuesto muy ajustado, grabado simple, no hace falta reutilizar.
    """)

# Info detallada
with st.expander("ℹ️ Información técnica"):
    st.markdown("""
    ### Toppers 3D
    - **Material:** PLA, PETG, ABS, Resina
    - **Resolución:** 0.2mm capa
    - **Tiempo impresión:** 2-6 min (80mm)
    - **Bases:** 4 formas (Redonda/Ovalada/Cuadrada/Rectangular) × 3 modos (Plana/Con palo/Con figura arriba), + Redonda (letras paradas) y Sin base — 14 combinaciones
    - **Estilos:** Minimalista, Elegante, Divertido, Romántico, Moderno, Vintage, Geométrico, Bohemio
    - **Temas:** General, Matrimonio, Cumpleaños, Fiesta, Bebé/Baby Shower, Graduación, Aniversario, Quince Años

    ### Toppers Neón
    - **Tipo LED:** Flexible (24V frío), Rígido (12V cálido), RGB (multicolor)
    - **Consumo:** 0.05-0.2W
    - **Vida útil:** 50,000h
    - **Formato:** DXF para máquina dobladora

    ### Toppers LED
    - **Estructura:** PLA, Acrílico, Madera
    - **Efectos:** Fijo, Parpadeo (2Hz), Secuencial, Arcoíris
    - **Alimentación:** USB 5V (batería integrada)
    - **Consumo:** 4.5-6W según efecto

    ### Toppers Acrílico
    - **Material:** Acrílico 2-8mm
    - **Acabados:** Espejo, Transparente, Mate, Color
    - **Método:** Grabado láser (CO₂)
    - **Potencia:** 20-96W según espesor
    - **Nota:** No reutilizable, costo muy bajo
    """)

# Compatibilidad
with st.expander("🔗 Integración con otras herramientas"):
    st.markdown("""
    | Herramienta | 3D | Neón | LED | Acrílico |
    |---|:---:|:---:|:---:|:---:|
    | Silhueta | ✓ | — | — | — |
    | Esculturas | ✓ | — | ✓ | — |
    | Llavero | ✓ | — | — | ✓ |
    | Letras | ✓ | ✓ | ✓ | ✓ |
    | Neón SVG | — | ✓ | — | — |
    | Nombre LED | — | — | ✓ | — |

    **Exporta formatos:**
    - 3D → STL (impresoras 3D, Cura/PrusaSlicer)
    - Neón → DXF (máquinas dobladoras LED)
    - LED → STL + especificaciones
    - Acrílico → DXF (cortadoras láser, Lightburn)
    """)
