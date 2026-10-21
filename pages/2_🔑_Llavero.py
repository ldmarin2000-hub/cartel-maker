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
from ui_streamlit import bloque_presets, resolver_archivo_subido, resolver_biblioteca, selector_fuente

st.set_page_config(page_title="Llavero · Cartel Maker", page_icon="🔑", layout="wide")

st.title("🔑 Llavero")
st.caption(llavero.DESCRIPCION)

TIPOS_DECO = [
    "Lista", "Emoji/pictograma", "Símbolo/signo", "Imagen propia (PNG/JPG)", "SVG propio",
    "Imagen/SVG a color",
]
MAX_COLORES_ICONO = 4  # tope de colores reales a usar del ícono "a color" -- mismo criterio
# que generators/topper.py::MAX_COLORES_DECORACION_MULTICOLOR, sin motivo para que el
# llavero cuantice/limite distinto.

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
    "ll_tiene_ams", "ll_decoracion_tam", "ll_deco_x", "ll_deco_y", "ll_aro_r", "ll_aro_x", "ll_aro_y",
    "ll_espesor_texto_mm", "ll_espesor_base_mm", "ll_borde_mm",
    "ll_espaciado_monograma", "ll_anillo_mm",
]


@st.cache_data(ttl=120, show_spinner=False)
def _preview_rapido(nombre, ruta_ttf, alto_mm, color_base, color_texto,
                     decoracion, decoracion_emoji, decoracion_lado, decoracion_tam,
                     deco_x, deco_y, aro_lado, aro_r, borde_mm,
                     modo_logo, espaciado_monograma, anillo_mm, aro_x, aro_y):
    return llavero.preview_rapido(
        nombre, ruta_ttf, alto_mm=alto_mm, color_base=color_base, color_texto=color_texto,
        decoracion=decoracion, decoracion_emoji=decoracion_emoji,
        decoracion_lado=decoracion_lado, decoracion_tam=decoracion_tam,
        deco_x=deco_x, deco_y=deco_y, aro_lado=aro_lado, aro_r=aro_r, borde_mm=borde_mm,
        modo_logo=modo_logo, espaciado_monograma=espaciado_monograma, anillo_mm=anillo_mm,
        aro_x=aro_x, aro_y=aro_y,
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
    decoracion_color_ruta = None
    indices_seleccionados_color, colores_asignados_icono = [], []
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
        elif tipo_deco == "SVG propio":
            svg_subido = st.file_uploader(
                "SVG propio", type=["svg"], key="ll_svg_subido",
                help="Funciona con casi cualquier ícono simple (un solo color, sin fotos ni "
                     "degradados). No entra en el preset ni en la vista rápida — solo en el llavero generado.",
            )
            decoracion_svg = resolver_archivo_subido(svg_subido, "ll_svg_subido", "_subido_ll_svg")
            decoracion_svg = resolver_biblioteca("ll_svg_biblioteca") or decoracion_svg
            if decoracion_svg and svg_subido is None:
                svg_subido = True  # solo para `archivo_subido` más abajo -- gana el mismo trato que un upload

        else:  # "Imagen/SVG a color"
            color_subido = st.file_uploader(
                "Imagen (PNG/JPG) o SVG a separar por color", type=["png", "jpg", "jpeg", "svg"],
                key="ll_color_subido",
                help="Un logo/escudo con colores bien definidos (no una foto ni degradados) -- "
                     "cada color que elijas abajo sale como su propia región, para pintarla con el "
                     "filamento real que corresponda. Si tenés el archivo en SVG (vectorial) usá "
                     "ese en vez del PNG/JPG: los colores ya vienen declarados en el archivo.",
            )
            decoracion_color_ruta = resolver_archivo_subido(color_subido, "ll_color_subido", "_subido_ll_color")
            decoracion_color_ruta = resolver_biblioteca("ll_color_biblioteca") or decoracion_color_ruta

            if decoracion_color_ruta:
                svg_subido = True  # cuenta como "archivo subido" más abajo (sin vista rápida)
                colores_detectados_raw = decoraciones.detectar_colores_archivo(decoracion_color_ruta)
                if not colores_detectados_raw:
                    st.warning("No se pudo detectar ningún color con área en este archivo.")
                else:
                    claves_check = [f"ll_color_usar_{i}" for i in range(len(colores_detectados_raw))]
                    for i, key in enumerate(claves_check):
                        if key not in st.session_state:
                            st.session_state[key] = i < MAX_COLORES_ICONO
                    marcados_actual = sum(1 for key in claves_check if st.session_state.get(key))

                    st.caption(
                        f"Se detectaron {len(colores_detectados_raw)} colores -- elegí hasta "
                        f"{MAX_COLORES_ICONO} para usar (destildá los que sean ruido de "
                        "antialiasing, no colores reales del dibujo) y asignale un filamento real "
                        "a cada uno."
                    )
                    for i, (hex_detectado, frac) in enumerate(colores_detectados_raw):
                        col_check, col_swatch, col_sel = st.columns([1, 1, 3])
                        ya_marcado = st.session_state.get(claves_check[i], False)
                        deshabilitar = marcados_actual >= MAX_COLORES_ICONO and not ya_marcado
                        usar = col_check.checkbox(
                            f"{frac * 100:.0f}%", key=claves_check[i], disabled=deshabilitar,
                            help="Destildado = no se usa este color (por ejemplo, si es ruido de "
                                 "antialiasing en vez de un color real del dibujo).",
                        )
                        col_swatch.color_picker(
                            f"ll_color_muestra_{i}", value=hex_detectado, disabled=True,
                            label_visibility="collapsed", key=f"ll_color_muestra_{i}",
                        )
                        sugerido = colores.nombre_mas_cercano(hex_detectado)
                        elegido = col_sel.selectbox(
                            f"ll_color_filamento_{i}", list(colores.NOMBRES),
                            index=list(colores.NOMBRES).index(sugerido), disabled=not usar,
                            key=f"ll_color_filamento_{i}", label_visibility="collapsed",
                        )
                        if usar:
                            indices_seleccionados_color.append(i)
                            colores_asignados_icono.append(elegido)

                    if modo_logo == "emblema":
                        st.caption(
                            "🚧 En modo Emblema el ícono todavía sale en un solo color (el de "
                            "\"Color texto\") -- los colores reales por ahora no incluyen el anillo."
                        )
                    elif not indices_seleccionados_color:
                        st.caption("Elegí al menos un color arriba para separar el ícono por color real.")

                # Respaldo monocromo: se usa SIEMPRE que el modo sea Emblema (no soporta
                # colores reales todavía), o si no quedó ningún color tildado arriba -- en
                # Imagotipo/Isologo/Isotipo con al menos un color elegido, `generar()` ignora esto
                # y arma el ícono separado por color real (ver decoracion_multicolor_ruta más abajo).
                if decoracion_color_ruta.lower().endswith(".svg"):
                    decoracion_svg = decoracion_color_ruta
                else:
                    decoracion_imagen = decoracion_color_ruta
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
    aro_x, aro_y = 0, 0
    espaciado_monograma, anillo_mm = -0.15, 0.0
    with st.expander("Ajustes finos"):
        if es_monograma:
            espaciado_monograma = st.slider(
                "Superposición de las iniciales", -0.5, 0.1, -0.15, step=0.05, key="ll_espaciado_monograma",
                help="Más negativo = las letras se superponen/entrelazan más. 0 = espaciado normal.",
            )
        if not es_isotipo or tiene_icono:
            if not es_monograma:
                decoracion_tam = st.slider("Tamaño de la decoración", 3, 40, 7, key="ll_decoracion_tam")
                deco_x = st.slider("Ajuste horizontal de la decoración", -40, 40, 0, key="ll_deco_x")
                deco_y = st.slider("Ajuste vertical de la decoración", -40, 40, 0, key="ll_deco_y")
        if es_monograma or es_emblema:
            anillo_mm = st.slider(
                "Anillo circular (mm de grosor, 0 = sin anillo)", 0.0, 6.0, 2.0, step=0.5, key="ll_anillo_mm",
            )
        aro_r = st.slider("Radio del agujero del aro (mm)", 1.0, 5.0, 2.0, step=0.25, key="ll_aro_r")
        if aro_lado != "ninguno":
            aro_x = st.slider("Ajuste horizontal del aro", -40, 40, 0, key="ll_aro_x")
            aro_y = st.slider("Ajuste vertical del aro", -40, 40, 0, key="ll_aro_y")
        espesor_texto_mm = st.slider(
            "Espesor del texto/decoración (mm)", 1.0, 6.0, 2.0, step=0.5, key="ll_espesor_texto_mm",
        )
        espesor_base_mm = st.slider("Espesor de la base (mm)", 1.0, 8.0, 3.0, step=0.5, key="ll_espesor_base_mm")
        borde_mm = st.slider("Margen del borde (mm)", 0.0, 10.0, 3.0, step=0.5, key="ll_borde_mm")

    generar_click = st.button("Generar llavero", type="primary", use_container_width=True)

with col_preview:
    puede_preview = (es_isotipo or es_emblema or es_monograma or nombre.strip()) and not archivo_subido
    if puede_preview:
        png_rapido, ancho_rapido, alto_rapido = _preview_rapido(
            nombre, ruta_ttf, float(alto_mm), color_base, color_texto,
            decoracion, decoracion_emoji, decoracion_lado, decoracion_tam, deco_x, deco_y, aro_lado, aro_r, borde_mm,
            modo_logo, espaciado_monograma, anillo_mm, aro_x, aro_y,
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
                    aro_lado=aro_lado, aro_r=aro_r, aro_x=aro_x, aro_y=aro_y,
                    espesor_texto_mm=espesor_texto_mm, espesor_base_mm=espesor_base_mm, borde_mm=borde_mm,
                    tiene_ams=tiene_ams,
                    modo_logo=modo_logo, espaciado_monograma=espaciado_monograma, anillo_mm=anillo_mm,
                    # Ícono "a color" (Parte 2) -- solo si quedó al menos un color elegido; si el
                    # archivo no dio ningún color detectable, decoracion_svg/decoracion_imagen ya
                    # tienen el respaldo monocromo de la Parte 1 y esto se deja en None para no
                    # forzar el camino multicolor con nada que separar.
                    decoracion_multicolor_ruta=decoracion_color_ruta if indices_seleccionados_color else None,
                    decoracion_multicolor_indices=indices_seleccionados_color or None,
                    colores_asignados_icono=colores_asignados_icono or None,
                )
            except (FileNotFoundError, ValueError) as e:
                st.error(str(e))
                r = None

        if r:
            color_base_hex = colores.hex_de(color_base)
            color_texto_hex = colores.hex_de(color_texto)
            piezas_icono_visor = [
                {"ruta_stl": ruta, "color": color_hex, "nombre": f"icono_{i + 1}"}
                for i, (ruta, color_hex) in enumerate(zip(r["rutas_stl_icono"], r["colores_icono"]))
            ]
            hay_texto = r["ruta_stl_texto"] is not None
            if tiene_ams:
                # con AMS todas las piezas ya están en su posición real (una arriba de la otra) —
                # se puede mostrar el conjunto armado en un solo visor.
                piezas_visor = [{"ruta_stl": r["ruta_stl_base"], "color": color_base_hex, "nombre": "base"}]
                if hay_texto:
                    piezas_visor.append({"ruta_stl": r["ruta_stl_texto"], "color": color_texto_hex, "nombre": "texto"})
                html_visor = preview3d.armar_html_visor(piezas_visor + piezas_icono_visor)
                if html_visor:
                    components.html(html_visor, height=490)
                    st.caption("Arrastrá para rotar, scroll para zoom.")
                else:
                    st.image(r["ruta_png"], use_container_width=True)
            else:
                # sin AMS cada pieza se exporta apoyada en el suelo por separado (para
                # imprimirlas sueltas) — mostrarlas juntas se verían superpuestas, así que
                # van en columnas lado a lado (una para el texto, si lo hay -- un isotipo
                # 100% a color no tiene pieza de texto -- y otra para el ícono a color).
                n_columnas = 1 + (1 if hay_texto else 0) + (1 if piezas_icono_visor else 0)
                columnas = st.columns(n_columnas)
                idx_col = 0
                html_base = preview3d.armar_html_visor([{"ruta_stl": r["ruta_stl_base"], "color": color_base_hex}])
                with columnas[idx_col]:
                    st.caption("Base")
                    if html_base:
                        components.html(html_base, height=320)
                idx_col += 1

                html_texto = None
                if hay_texto:
                    html_texto = preview3d.armar_html_visor(
                        [{"ruta_stl": r["ruta_stl_texto"], "color": color_texto_hex}])
                    with columnas[idx_col]:
                        st.caption("Texto/decoración")
                        if html_texto:
                            components.html(html_texto, height=320)
                    idx_col += 1

                html_icono = None
                if piezas_icono_visor:
                    html_icono = preview3d.armar_html_visor(piezas_icono_visor)
                    with columnas[idx_col]:
                        st.caption("Ícono (a color)")
                        if html_icono:
                            components.html(html_icono, height=320)

                if not html_base or (hay_texto and not html_texto) or (piezas_icono_visor and not html_icono):
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

            if r["ruta_3mf_multicolor"]:
                with open(r["ruta_3mf_multicolor"], "rb") as f:
                    st.download_button(
                        "⬇ 3MF multicolor (para AMS, recomendado)", f, file_name=os.path.basename(r["ruta_3mf_multicolor"]),
                        mime="model/3mf", use_container_width=True, type="primary",
                    )
                st.caption(
                    "Abre directo en Bambu Studio con los colores ya puestos (base y "
                    "texto/decoración) — no hace falta dividir nada."
                )
            if r["ruta_stl_multicolor"]:
                with open(r["ruta_stl_multicolor"], "rb") as f:
                    st.download_button(
                        "⬇ STL multicolor (respaldo, para otro slicer)", f, file_name=os.path.basename(r["ruta_stl_multicolor"]),
                        mime="model/stl", use_container_width=True,
                    )
                st.caption("O si preferís, las piezas sueltas de siempre:")

            if hay_texto:
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
            else:
                with open(r["ruta_stl_base"], "rb") as f:
                    st.download_button(
                        "⬇ STL base", f, file_name=os.path.basename(r["ruta_stl_base"]),
                        mime="model/stl", use_container_width=True,
                    )

            if r["rutas_stl_icono"]:
                dcols_icono = st.columns(len(r["rutas_stl_icono"]))
                for i, ruta_icono in enumerate(r["rutas_stl_icono"]):
                    with open(ruta_icono, "rb") as f:
                        dcols_icono[i].download_button(
                            f"⬇ STL ícono {i + 1}", f, file_name=os.path.basename(ruta_icono),
                            mime="model/stl", use_container_width=True, key=f"ll_download_icono_{i}",
                        )
