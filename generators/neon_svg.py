#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generators/neon_svg.py
--------------------------
Generador de carteles de NEÓN a partir de un SVG/dibujo de línea (en vez
de texto con una fuente): SVG -> máscara -> esqueleto -> canal para la
tira LED. Mismo resultado final que generators/neon.py (texto trazado) —
la única diferencia es el primer paso (cómo se consigue la máscara de
entrada); el resto del pipeline vive en core/neon_pipeline.py y es
literalmente el mismo código.

Sirve para "dibujar con luz" cualquier ícono/logo/dibujo de línea (un
cafecito, un corazón, una firma escaneada y vectorizada, etc.) siguiendo
el mismo trazado que las letras: se marca el medio de cada trazo del
dibujo y ahí va el canal del LED.

`generar()` es la función pura (sin input()/print()) que usan tanto la CLI
(`ejecutar()`, más abajo) como la app visual de Streamlit.
"""

import io
import os

from core import bambu_a1, geometry, neon_pipeline, pieza, preview, raster_svg, ui

TIPOS_MONTAJE = neon_pipeline.TIPOS_MONTAJE

NOMBRE = "Cartel de neón (desde SVG/dibujo)"
DESCRIPCION = "SVG/dibujo de línea -> canal LED que sigue el trazo. STL + preview."

CARPETA_SALIDA = "output"


def _armar_2d(ruta_svg, alto_mm, modo_led,
              led_ancho_mm, holgura_mm, pared_mm, fondo, fondo_margen, redondeo_mm,
              raster_px, min_objeto_px, poda_frac, simplify_mm,
              agregar_canal_salida, cable_ancho_mm,
              agregar_agujeros, agujero_cable_diam_mm,
              tipo_montaje, n_orejas_montaje, ancho_pata_mm, alto_pata_mm,
              ancho_max_modulo_mm):
    """Pipeline 2D puro (SVG -> máscara -> esqueleto -> geometría), SIN
    mesh3d ni STL — compartido entre `generar()` y `preview_rapido()`.
    Devuelve un dict con todo lo que necesita cada uno para seguir."""
    if not os.path.exists(ruta_svg):
        raise FileNotFoundError(f"no encuentro el SVG: {ruta_svg}")

    mask = raster_svg.rasterizar(ruta_svg, raster_px, min_objeto_px=min_objeto_px)
    return neon_pipeline.armar_2d(
        mask, alto_mm, modo_led, led_ancho_mm, holgura_mm, pared_mm, fondo, fondo_margen, redondeo_mm,
        poda_frac, simplify_mm, agregar_canal_salida, cable_ancho_mm, agregar_agujeros, agujero_cable_diam_mm,
        tipo_montaje, n_orejas_montaje, ancho_pata_mm, alto_pata_mm, ancho_max_modulo_mm,
    )


def preview_rapido(ruta_svg, alto_mm, modo_led,
                    led_ancho_mm=None, fondo="contorno",
                    holgura_mm=0.4, pared_mm=2.4, fondo_margen=8,
                    raster_px=400, min_objeto_px=12, poda_frac=0.06, simplify_mm=0.4, redondeo_mm=0.5,
                    agregar_canal_salida=True, cable_ancho_mm=4.0,
                    agregar_agujeros=True, agujero_cable_diam_mm=5.0,
                    tipo_montaje="colgado", n_orejas_montaje=2,
                    ancho_pata_mm=40.0, alto_pata_mm=15.0, ancho_max_modulo_mm=None):
    """Preview 2D instantáneo — el mismo trazado/placa que ve `generar()`,
    pero SIN mesh3d ni export a STL. Devuelve (png_bytes, ancho_mm,
    alto_mm) o (None, 0, 0) si no se pudo generar."""
    if led_ancho_mm is None:
        led_ancho_mm = 6.0 if modo_led == "neon" else 10.0
    if ancho_max_modulo_mm is None:
        ancho_max_modulo_mm = bambu_a1.ANCHO_MAX_RECOMENDADO_MM
    if not ruta_svg or not os.path.exists(ruta_svg):
        return None, 0, 0
    try:
        d = _armar_2d(
            ruta_svg, alto_mm, modo_led, led_ancho_mm, holgura_mm, pared_mm, fondo, fondo_margen,
            redondeo_mm, raster_px, min_objeto_px, poda_frac, simplify_mm, agregar_canal_salida, cable_ancho_mm,
            agregar_agujeros, agujero_cable_diam_mm, tipo_montaje, n_orejas_montaje, ancho_pata_mm,
            alto_pata_mm, ancho_max_modulo_mm,
        )
    except (ValueError, FileNotFoundError):
        return None, 0, 0

    etiqueta = os.path.splitext(os.path.basename(ruta_svg))[0]
    buf = io.BytesIO()
    preview.guardar_preview(
        buf, d["placa_final"], d["canal"], d["lineas"], etiqueta,
        d["ancho_total_mm"], d["alto_total_mm"], modo_led, cortes=d["cortes_locales"], paredes=d["paredes"],
    )
    return buf.getvalue(), d["ancho_total_mm"], d["alto_total_mm"]


def generar(ruta_svg, alto_mm, modo_led,
            led_ancho_mm=None, led_prof_mm=None, fondo="contorno",
            holgura_mm=0.4, pared_mm=2.4, placa_mm=3.0, fondo_margen=8,
            raster_px=500, min_objeto_px=12, poda_frac=0.06, simplify_mm=0.4, redondeo_mm=0.5,
            agregar_canal_salida=True, cable_ancho_mm=4.0,
            agregar_agujeros=True, agujero_cable_diam_mm=5.0,
            tipo_montaje="colgado", n_orejas_montaje=2,
            ancho_pata_mm=40.0, alto_pata_mm=15.0,
            ancho_max_modulo_mm=None,
            carpeta_salida=CARPETA_SALIDA):
    """Corre el pipeline completo y devuelve un dict con las rutas, medidas
    y avisos. No pregunta nada ni imprime nada — así lo puede llamar tanto
    la CLI como la app visual."""
    if led_ancho_mm is None:
        led_ancho_mm = 6.0 if modo_led == "neon" else 10.0
    if led_prof_mm is None:
        led_prof_mm = 8.0 if modo_led == "neon" else 4.0
    if ancho_max_modulo_mm is None:
        ancho_max_modulo_mm = bambu_a1.ANCHO_MAX_RECOMENDADO_MM
    if tipo_montaje not in TIPOS_MONTAJE:
        raise ValueError(f"tipo_montaje debe ser uno de {TIPOS_MONTAJE}, recibí {tipo_montaje!r}")

    d = _armar_2d(
        ruta_svg, alto_mm, modo_led, led_ancho_mm, holgura_mm, pared_mm, fondo, fondo_margen,
        redondeo_mm, raster_px, min_objeto_px, poda_frac, simplify_mm, agregar_canal_salida, cable_ancho_mm,
        agregar_agujeros, agujero_cable_diam_mm, tipo_montaje, n_orejas_montaje, ancho_pata_mm,
        alto_pata_mm, ancho_max_modulo_mm,
    )
    etiqueta = os.path.splitext(os.path.basename(ruta_svg))[0]
    base = pieza.nombre_archivo(etiqueta, default="dibujo")
    r = neon_pipeline.armar_3d_y_exportar(
        d, etiqueta, base, modo_led, placa_mm, led_prof_mm, tipo_montaje, alto_pata_mm,
        ancho_max_modulo_mm, carpeta_salida,
    )
    r["svg"] = etiqueta
    r["alto_mm"] = alto_mm
    return r


# ---------------------------------------------------------------------------
#  Interfaz de consola (menú de main.py)
# ---------------------------------------------------------------------------
def ejecutar():
    print(f"\n{NOMBRE}")

    ruta_svg = ui.pedir_texto("Ruta al archivo SVG", "")
    alto_mm = ui.pedir_float("Alto del dibujo (mm)", 90)
    modo_led = ui.pedir_opcion("Modo LED", ["neon", "ws2812"], "neon")

    default_ancho_led = 6.0 if modo_led == "neon" else 10.0
    default_prof_canal = 8.0 if modo_led == "neon" else 4.0
    led_ancho_mm = ui.pedir_float("Ancho del LED (mm)", default_ancho_led)
    led_prof_mm = ui.pedir_float("Profundidad del canal (mm)", default_prof_canal)
    print("  Placa de fondo: 'contorno' (sigue el dibujo, gasta poco material),")
    print("    'rect_hundido' (rectángulo macizo, el canal queda como zanja — más rígido y más material),")
    print("    'rect_plano' (rectángulo fino con el dibujo en relieve — poco material, base conectada)")
    fondo = ui.pedir_opcion("Placa de fondo", list(geometry.FONDOS_VALIDOS), "contorno")

    print(f"\n  » SVG: {ruta_svg!r}  modo: {modo_led}  LED {led_ancho_mm}mm")

    try:
        r = generar(ruta_svg, alto_mm, modo_led, led_ancho_mm, led_prof_mm, fondo)
    except (FileNotFoundError, ValueError) as e:
        print(f"  ERROR: {e}")
        return

    print(f"  tamaño total del cartel ~ {r['ancho_total_mm']:.0f} x {r['alto_total_mm']:.0f} mm   trazos: {r['trazos']}")
    for nota in r["info"]:
        print(f"  · {nota}")
    for aviso in r["avisos"]:
        print(f"  ⚠ {aviso}")
    for p in r["piezas"]:
        etiqueta = f" (módulo {p['indice']}/{p['de']})" if p["de"] > 1 else ""
        print(f"  ✓ STL{etiqueta} -> {p['ruta_stl']}  ({p['vertices']} vért., watertight={p['watertight']})")
    if r["pieza_soporte"]:
        s = r["pieza_soporte"]
        print(f"  ✓ STL (base de escritorio) -> {s['ruta_stl']}  ({s['vertices']} vért., watertight={s['watertight']})")
    print(f"  ✓ preview -> {r['ruta_png']}")
    print(f"  {'✓' if r['entra_a1'] else '⚠'} {r['mensaje_a1']}")
    print()
