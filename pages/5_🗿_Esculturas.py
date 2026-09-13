#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pages/5_🗿_Esculturas.py
----------------------------
Página de Streamlit para el generador de esculturas/relieve. Es solo la
capa visual: toda la lógica real vive en generators/esculturas.py
(generar()), la misma que usa la versión de consola (main.py).
"""

import os

import streamlit as st
import streamlit.components.v1 as components

from core import colores, heightmap, ia3d, preview3d, storage, validation
from generators import esculturas
from ui_streamlit import bloque_presets

st.set_page_config(page_title="Esculturas · Cartel Maker", page_icon="🗿", layout="wide")

st.title("🗿 Escultura (relieve o estatua completa desde imagen)")
st.caption(esculturas.DESCRIPCION)

MODOS = [
    "Relieve (rápido, sin IA)",
    "Estatua 3D completa (IA local)",
    "Estatua 3D completa (API externa)",
]

CALIDADES = {
    "Rápida (menos detalle, STL liviano)": 70,
    "Normal": esculturas.RESOLUCION_DEFAULT_PX,
    "Alta (más detalle, tarda más y pesa más)": esculturas.RESOLUCION_ALTA_PX,
}

PRESET_KEYS = [
    "es_ancho_mm", "es_espesor_base_mm", "es_relieve_mm",
    "es_oscuro_alto", "es_segmentar_sujeto", "es_suavizado_px", "es_calidad", "es_color",
    "es_ia_calidad", "es_ia_quitar_fondo",
]


@st.cache_data(ttl=120, show_spinner=False)
def _preview_rapido(ruta_imagen, ancho_mm, alto_mm, espesor_base_mm, relieve_mm, suavizado_px, oscuro_alto):
    return esculturas.preview_rapido(
        ruta_imagen, ancho_mm=ancho_mm, alto_mm=alto_mm,
        espesor_base_mm=espesor_base_mm, relieve_mm=relieve_mm,
        suavizado_px=suavizado_px, oscuro_alto=oscuro_alto,
    )


modo = st.radio("Modo", MODOS, horizontal=True, key="es_modo")

if modo == "Relieve (rápido, sin IA)":
    st.info(
        "Subís una foto/logo/dibujo y el brillo de cada zona se convierte en altura — un relieve "
        "3D tallado de verdad (no una silueta plana, no una nube de puntos), sólido y watertight, "
        "listo para imprimir. Funciona mejor con buen contraste; una imagen muy plana en brillo da "
        "un relieve casi sin relieve."
    )
elif modo == "Estatua 3D completa (IA local)":
    st.info(
        "Reconstruye un VOLUMEN completo que sigue la pose del sujeto (no una sola cara en "
        "relieve) con TripoSR, corriendo en tu máquina, gratis y sin mandar la imagen a ningún "
        "lado. A diferencia de un generador difuso, TripoSR reconstruye en una sola pasada "
        "siguiendo la foto de verdad — ~1-2 min en CPU (sin GPU), buena fidelidad de pose y "
        "proporciones. Mejor con la foto de UN sujeto claro, fondo simple."
    )
    if not ia3d.entorno_local_disponible():
        st.warning(
            "Todavía no está instalado el entorno de IA local. Corré **setup_ia3d.bat** "
            "(en la carpeta del proyecto) una vez — ocupa 3-4GB en el disco C: y después la "
            "primera generación descarga los pesos del modelo (~150MB más)."
        )
else:
    st.info(
        "Manda la imagen a un servicio externo pago (Tripo3D o Meshy) — mejor fidelidad a la "
        "pose y proporciones que el modelo local, y más rápido, pero necesitás una cuenta con "
        "crédito en ese servicio y tu foto sale de tu máquina."
    )
    st.warning(
        "Integración todavía no armada del lado del proveedor (solo queda conectar la key) — "
        "por ahora esta opción no genera nada."
    )

col_form, col_preview = st.columns([1, 1.3])

with col_form:
    bloque_presets("esculturas", PRESET_KEYS)

    combinar_imagenes = False
    if modo != "Estatua 3D completa (API externa)":
        combinar_imagenes = st.checkbox(
            "🖼️ Combinar varias imágenes en una misma escultura", value=False, key="es_combinar",
            help=(
                "Modo Relieve: hasta 4 fotos talladas juntas en una sola placa (collage). "
                "Modo Estatua 3D: cada foto se reconstruye como su propia figura 3D (TripoSR) y "
                "todas quedan paradas sobre un pedestal compartido — una familia, mascota + "
                "dueño, etc., en una sola pieza imprimible."
            ),
        )

    ruta_imagen = None
    rutas_imagenes = []
    layout_collage = "Lado a lado"

    if combinar_imagenes:
        archivos_subidos = st.file_uploader(
            "Imágenes (2 a 4, PNG/JPG)", type=["png", "jpg", "jpeg"], accept_multiple_files=True,
            help="Subí entre 2 y 4 imágenes. No entran en el preset.",
        )
        if archivos_subidos:
            os.makedirs("output", exist_ok=True)
            for arch in archivos_subidos[:4]:
                ruta = os.path.join("output", f"_subido_{arch.name}")
                with open(ruta, "wb") as f:
                    f.write(arch.getvalue())
                rutas_imagenes.append(ruta)
            ruta_imagen = rutas_imagenes[0]  # se usa para calcular proporción/preview de referencia
            if len(rutas_imagenes) < 2:
                st.warning("Subí al menos 2 imágenes para combinar.")

        if modo == "Relieve (rápido, sin IA)":
            layout_collage = st.radio("Cómo combinarlas", esculturas.LAYOUTS_COLLAGE, horizontal=True, key="es_layout_collage")
    else:
        imagen_subida = st.file_uploader(
            "Imagen (PNG/JPG)", type=["png", "jpg", "jpeg"],
            help="Foto, logo o dibujo — mejor con buen contraste entre las zonas que querés que "
                 "sobresalgan y las que no. No entra en el preset (el archivo no se puede pre-cargar).",
        )
        if imagen_subida is not None:
            os.makedirs("output", exist_ok=True)
            ruta_imagen = os.path.join("output", f"_subido_{imagen_subida.name}")
            with open(ruta_imagen, "wb") as f:
                f.write(imagen_subida.getvalue())

    ancho_mm = st.slider("Ancho (mm)" if not combinar_imagenes else "Ancho / tamaño de referencia (mm)", 30, 200, 80, step=5, key="es_ancho_mm")
    alto_mm = ancho_mm
    if combinar_imagenes:
        if modo == "Relieve (rápido, sin IA)":
            st.caption("El alto sale del layout elegido (el collage se arma cuadrado/rectangular según cómo combines las fotos).")
        else:
            st.caption("Cada figura mantiene su propia proporción — este valor es la altura de la figura principal.")
    elif ruta_imagen:
        _, alto_mm = heightmap.ajustar_caja_a_proporcion(ruta_imagen, float(ancho_mm))
        st.caption(f"Alto calculado según la proporción real de la imagen: **{alto_mm:.0f} mm**.")

    espesor_base_mm = relieve_mm = 0.0
    oscuro_alto = True
    segmentar_sujeto = False
    forma_medallon = "Rectangular"
    suavizado_px = 1.0
    resolucion_px = esculturas.RESOLUCION_DEFAULT_PX
    ia_calidad_label = api_key = ""
    ia_quitar_fondo = True
    api_proveedor = "Tripo3D"
    forma_pedestal = "Redonda"
    texto_placa = ""

    if modo == "Relieve (rápido, sin IA)":
        c1, c2 = st.columns(2)
        espesor_base_mm = c1.slider(
            "Espesor de la base (mm)", 1.0, 8.0, 3.0, step=0.5, key="es_espesor_base_mm",
            help="El piso mínimo — para que sea imprimible y no se rompa donde el relieve es más bajo.",
        )
        relieve_mm = c2.slider(
            "Relieve (mm)", 1.0, 25.0, 8.0, step=0.5, key="es_relieve_mm",
            help="Cuánto sobresale la parte más alta por encima de la base.",
        )

        oscuro_alto_label = st.radio(
            "Qué queda más alto", ["Zonas oscuras", "Zonas claras"], horizontal=True, key="es_oscuro_alto",
            help="\"Zonas oscuras\" da el relieve escultórico típico (como una moneda o medallón) — "
                 "las sombras/detalles oscuros de la foto sobresalen.",
        )
        oscuro_alto = oscuro_alto_label == "Zonas oscuras"

        segmentar_sujeto = st.checkbox(
            "Relieve escultórico diferenciado (el sujeto resalta del fondo)", value=False,
            key="es_segmentar_sujeto",
            help="Separa el sujeto (persona/objeto principal) del fondo con IA liviana (rembg) — "
                 "el sujeto queda con más relieve y el fondo casi plano, como un relieve escultórico "
                 "real (la figura 'sale' de la placa) en vez de un relieve uniforme por brillo solo. "
                 "Tarda unos segundos más la primera vez (descarga un modelo chico de segmentación).",
        )

        forma_medallon = st.radio(
            "Forma del relieve", esculturas.FORMAS_MEDALLON, horizontal=True, key="es_forma_medallon",
            help="\"Circular\"/\"Ovalada\" recortan la foto tallada dentro de esa silueta (medallón), "
                 "con el resto de la placa lisa alrededor — como un camafeo o medallón conmemorativo.",
        )

        with st.expander("Ajustes finos"):
            suavizado_px = st.slider(
                "Suavizado (px)", 0.0, 4.0, 1.0, step=0.5, key="es_suavizado_px",
                help="Desenfoca la imagen antes de tallar el relieve — saca ruido/artefactos de JPG "
                     "que quedarían como picos feos. 0 = sin suavizar.",
            )
            calidad_label = st.radio("Calidad (detalle de la grilla)", list(CALIDADES.keys()), key="es_calidad")
            resolucion_px = CALIDADES[calidad_label]

    elif modo == "Estatua 3D completa (IA local)":
        ia_calidad_label = st.radio(
            "Calidad (resolución de la malla)", list(ia3d.CALIDADES_LOCAL.keys()), key="es_ia_calidad",
            help="TripoSR reconstruye en una sola pasada (rápido) — la calidad depende de la "
                 "resolución con la que se extrae la malla del volumen, no de 'pasos' como los "
                 "modelos difusos. Más resolución = más triángulos/detalle real, más lento.",
        )
        ia_quitar_fondo = st.checkbox(
            "Recortar el sujeto del fondo automáticamente", value=True, key="es_ia_quitar_fondo",
            help="Saca el fondo de la foto (rembg) antes de mandarla al modelo — ayuda mucho si "
                 "la foto no tiene fondo liso.",
        )

        con_pedestal = combinar_imagenes or st.checkbox(
            "Agregar pedestal + placa de nombre", value=False, key="es_con_pedestal",
            help="La figura sola queda parada apoyada directo — con esta opción se agrega una base "
                 "(pedestal) debajo y, si escribís algo, una placa con el texto grabado al frente. "
                 "En 'Combinar varias imágenes' el pedestal es obligatorio (es lo que sostiene a "
                 "todas las figuras juntas).",
        )
        if con_pedestal:
            c1, c2 = st.columns(2)
            forma_pedestal = c1.selectbox(
                "Forma del pedestal", ["Redonda", "Ovalada", "Cuadrada", "Rectangular"], key="es_forma_pedestal",
            )
            texto_placa = c2.text_input("Texto de la placa (opcional)", "", key="es_texto_placa")

    else:
        api_proveedor = st.selectbox("Servicio", list(ia3d.PROVEEDORES_API.keys()))
        api_key = st.text_input(
            "API key", type="password",
            help="Se usa solo en esta sesión del navegador, no se guarda en disco ni se sube al repo.",
        )
        st.caption(f"Doc del proveedor: {ia3d.PROVEEDORES_API[api_proveedor]['doc']}")

    color_pieza = st.selectbox(
        "Color de filamento (visor, no cambia el STL)", colores.NOMBRES,
        index=colores.NOMBRES.index("Dorado"), key="es_color",
    )

    etiqueta_boton = "Generar escultura" if modo == "Relieve (rápido, sin IA)" else "Generar estatua"
    generar_click = st.button(etiqueta_boton, type="primary", use_container_width=True)

with col_preview:
    if ruta_imagen and modo == "Relieve (rápido, sin IA)":
        png_rapido = _preview_rapido(
            ruta_imagen, float(ancho_mm), float(alto_mm), float(espesor_base_mm), float(relieve_mm),
            float(suavizado_px), oscuro_alto,
        )
        if png_rapido:
            st.image(
                png_rapido,
                caption=f"Vista rápida — ~{ancho_mm:.0f} x {alto_mm:.0f} x "
                        f"{espesor_base_mm + relieve_mm:.0f} mm. Al generar sale la malla real, "
                        f"con más detalle y el visor 3D interactivo.",
                use_container_width=True,
            )
            st.divider()

    r = None
    combo_activo = combinar_imagenes and len(rutas_imagenes) >= 2
    if not generar_click:
        st.info(f"Subí {'2 a 4 imágenes' if combinar_imagenes else 'una imagen'} y apretá **{etiqueta_boton}**.")
    elif combinar_imagenes and len(rutas_imagenes) < 2:
        st.error("Subí al menos 2 imágenes para combinar.")
    elif not ruta_imagen:
        st.error("Subí una imagen primero.")
    elif modo == "Relieve (rápido, sin IA)":
        # Validación antes de generar
        try:
            validation.validar_imagen(ruta_imagen)
            validation.validar_dimensiones_relieve(float(ancho_mm), float(alto_mm),
                                                   float(espesor_base_mm), float(relieve_mm))
        except validation.ValidationError as e:
            st.error(f"❌ {str(e)}")
        else:
            # Avisos (no errores)
            avisos = validation.avisos_en_relieve(float(ancho_mm), float(alto_mm), float(suavizado_px))
            for aviso in avisos:
                st.warning(aviso)

            spinner_msg = f"Combinando {len(rutas_imagenes)} imágenes y tallando el relieve..." if combo_activo else "Tallando el relieve (puede tardar unos segundos)..."
            with st.spinner(spinner_msg):
                try:
                    if combo_activo:
                        r = esculturas.generar_combinado(
                            rutas_imagenes, layout=layout_collage,
                            ancho_mm=float(ancho_mm), alto_mm=float(alto_mm),
                            espesor_base_mm=float(espesor_base_mm), relieve_mm=float(relieve_mm),
                            resolucion_px=resolucion_px, suavizado_px=float(suavizado_px),
                            oscuro_alto=oscuro_alto, segmentar_sujeto=segmentar_sujeto,
                        )
                    else:
                        r = esculturas.generar(
                            ruta_imagen, ancho_mm=float(ancho_mm), alto_mm=float(alto_mm),
                            espesor_base_mm=float(espesor_base_mm), relieve_mm=float(relieve_mm),
                            resolucion_px=resolucion_px, suavizado_px=float(suavizado_px),
                            oscuro_alto=oscuro_alto, segmentar_sujeto=segmentar_sujeto,
                            forma_medallon=forma_medallon,
                        )
                except (FileNotFoundError, ValueError) as e:
                    st.error(str(e))
    elif modo == "Estatua 3D completa (IA local)":
        resolucion_malla = ia3d.CALIDADES_LOCAL[ia_calidad_label]
        # Validación antes de generar
        try:
            validation.validar_imagen(ruta_imagen)
            validation.validar_dimensiones_estatua(float(ancho_mm))
        except validation.ValidationError as e:
            st.error(f"❌ {str(e)}")
        else:
            # Avisos (no errores)
            avisos = validation.avisos_en_estatua(resolucion_malla)
            for aviso in avisos:
                st.warning(aviso)

            if combo_activo:
                spinner_msg = f"Reconstruyendo {len(rutas_imagenes)} figuras (TripoSR, una por una) y armando la escena..."
            else:
                spinner_msg = f"Reconstruyendo el volumen (TripoSR, malla {resolucion_malla}³, ~1-2 min en CPU)..."

            with st.spinner(spinner_msg):
                try:
                    if combo_activo:
                        r = esculturas.generar_grupo_3d(
                            rutas_imagenes, alto_mm_principal=float(ancho_mm),
                            resolucion_malla=resolucion_malla, quitar_fondo=ia_quitar_fondo,
                            forma_base=forma_pedestal, texto_placa=texto_placa,
                        )
                    else:
                        r = ia3d.generar_local(
                            ruta_imagen, ancho_mm=float(ancho_mm), resolucion_malla=resolucion_malla,
                            quitar_fondo=ia_quitar_fondo,
                        )
                        if con_pedestal:
                            ruta_con_pedestal, malla_pedestal = esculturas.agregar_pedestal(
                                r["ruta_stl"], forma_base=forma_pedestal, texto=texto_placa,
                            )
                            r["ruta_stl"] = ruta_con_pedestal
                            r["vertices"] = len(malla_pedestal.vertices)
                            r["caras"] = len(malla_pedestal.faces)
                            r["watertight"] = malla_pedestal.is_watertight
                except (FileNotFoundError, ValueError, RuntimeError) as e:
                    st.error(str(e))
    else:
        try:
            r = ia3d.generar_api(ruta_imagen, api_key, proveedor=api_proveedor, ancho_mm=float(ancho_mm))
        except (ValueError, NotImplementedError) as e:
            st.error(str(e))

    if r:
        html_visor = preview3d.armar_html_visor(
            [{"ruta_stl": r["ruta_stl"], "color": colores.hex_de(color_pieza), "nombre": "escultura"}]
        )
        if html_visor:
            components.html(html_visor, height=460)
            st.caption("Arrastrá para rotar, scroll para zoom.")
        else:
            st.image(r["ruta_png"], use_container_width=True)

        c1, c2, c3 = st.columns(3)
        c1.metric("Ancho", f"{r['ancho_mm']:.0f} mm")
        c2.metric("Alto", f"{r['alto_mm']:.0f} mm")
        c3.metric("Grosor máx.", f"{r['profundidad_mm']:.1f} mm")

        for nota in r["info"]:
            st.info(nota)
        for aviso in r["avisos"]:
            st.warning(aviso)

        if r["entra_a1"]:
            st.success(r["mensaje_a1"])
        else:
            st.warning(r["mensaje_a1"])

        st.caption(f"{r['vertices']} vértices, {r['caras']} caras.")

        with open(r["ruta_stl"], "rb") as f:
            st.download_button(
                "⬇ Descargar STL", f, file_name=os.path.basename(r["ruta_stl"]),
                mime="model/stl", use_container_width=True, type="primary",
            )

# Stats de almacenamiento (opcional, siempre visible)
st.divider()
with st.expander("📊 Almacenamiento"):
    stats = storage.estadisticas_almacenamiento()
    col1, col2 = st.columns(2)
    col1.metric("Esculturas generadas", f"{stats['stl_count']} STL")
    col1.metric("Previews", f"{stats['png_count']} PNG")
    col2.metric("Espacio usado", f"{stats['tamaño_total_mb']:.0f} MB")
    col2.metric("Modelos descargados", f"{stats['cache_modelos_gb']:.1f} GB")
    st.caption("Los archivos temporales se limpian automáticamente cada 7 días.")
