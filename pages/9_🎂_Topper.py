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
    "tp_plano_espesor",
]

tipo_topper = st.radio("Tipo de topper", TIPOS_TOPPER, horizontal=True, key="tp_tipo")

col_form, col_preview = st.columns([1, 1.3])

with col_form:
    bloque_presets("topper", PRESET_KEYS)

    es_plano = "Plano" in tipo_topper

    if es_plano:
        st.caption("1 a 3 líneas de texto — dejá una línea vacía si no la necesitás.")
        col_l1, col_l2, col_l3 = st.columns(3)
        linea1 = col_l1.text_input("Línea 1", "Happy", key="tp_plano_l1")
        linea2 = col_l2.text_input("Línea 2", "Birthday", key="tp_plano_l2")
        linea3 = col_l3.text_input("Línea 3", "", key="tp_plano_l3")
        lineas_plano = [linea1, linea2, linea3]
        texto = " ".join(l.strip() for l in lineas_plano if l.strip()) or "Topper"
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
                help="Un aro fino alrededor del texto (Círculo/Hexágono/Pentágono). "
                     "'Ninguno' deja el texto suelto, unido solo por los puentes finos."
            )
            espesor_plano = st.slider("Espesor (mm)", 1.5, 6.0, 3.0, step=0.5, key="tp_plano_espesor")
        with col_b:
            con_palo_plano = st.checkbox("Palo para clavar en la torta", value=True, key="tp_plano_palo")
        st.caption(
            "Las letras/líneas sueltas de la fuente elegida se conectan automáticamente con "
            "puentes finos para que todo salga como una sola pieza rígida."
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
        html_preview = topper.preview_html_plano(
            lineas_plano, tamaño_mm, marco_plano, ruta_fuente, con_palo=con_palo_plano
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
                            con_palo=con_palo_plano,
                            espesor_mm=espesor_plano,
                        )

                        if "ruta_stl" in resultado and os.path.exists(resultado["ruta_stl"]):
                            html_visor = preview3d.armar_html_visor(
                                [{"ruta_stl": resultado["ruta_stl"], "color": "#d4af37"}], height_px=500
                            )
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

                        if "ruta_stl" in resultado:
                            with open(resultado["ruta_stl"], "rb") as f:
                                st.download_button(
                                    "📥 Descargar STL",
                                    f.read(),
                                    file_name=os.path.basename(resultado["ruta_stl"]),
                                    mime="application/octet-stream"
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
