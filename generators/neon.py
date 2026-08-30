#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generators/neon.py
---------------------
Generador de carteles de NEÓN trazado: texto + fuente .ttf -> esqueleto ->
canal para la tira LED. Orquesta core/raster, core/skeleton, core/geometry,
core/modulos, core/mesh3d, core/preview y core/checks.

`generar()` es la función pura (sin input()/print()) que usan tanto la CLI
(`ejecutar()`, más abajo) como la app visual de Streamlit. `generar()` tira
FileNotFoundError/ValueError si algo sale mal; cada interfaz decide cómo
mostrar el error.
"""

import glob
import io
import os

from core import bambu_a1, fuentes, geometry, neon_pipeline, pieza, preview, raster, ui

TIPOS_MONTAJE = neon_pipeline.TIPOS_MONTAJE

NOMBRE = "Cartel de neón (texto trazado)"
DESCRIPCION = "Texto + fuente .ttf -> canal LED que dibuja las letras. STL + preview."

CARPETA_FUENTES = "fonts"
CARPETA_SALIDA = "output"


def _armar_2d(texto, ruta_ttf, alto_mm, modo_led,
              led_ancho_mm, holgura_mm, pared_mm, fondo, fondo_margen, redondeo_mm,
              raster_px, poda_frac, simplify_mm,
              agregar_canal_salida, cable_ancho_mm,
              agregar_agujeros, agujero_cable_diam_mm,
              tipo_montaje, n_orejas_montaje, ancho_pata_mm, alto_pata_mm,
              ancho_max_modulo_mm, espaciado_relativo=0.0, puentes_altura_completa=True):
    """Pipeline 2D puro (raster -> esqueleto -> geometría), SIN mesh3d ni
    STL — compartido entre `generar()` y `preview_rapido()`. Es la parte
    cara en tiempo de fuente/trazado pero barata en cómputo (nada de
    booleanas 3D), así que sirve de vista rápida sin esperar el export.
    Devuelve un dict con todo lo que necesita cada uno para seguir. El
    resto del pipeline (esqueleto -> canal -> placa -> montaje -> cortes)
    es compartido con generators/neon_svg.py y vive en core/neon_pipeline.py.

    `espaciado_relativo` acerca/aleja las letras entre sí antes de
    trazarlas (negativo = más juntas, hasta tocarse/superponerse — ver
    core/raster.py::rasterizar_con_espaciado) -- si las letras quedan
    tocándose, el trazado sale de una sola pieza y no hace falta ningún
    puente."""
    if not os.path.exists(ruta_ttf):
        raise FileNotFoundError(f"no encuentro la fuente: {ruta_ttf}")

    if espaciado_relativo:
        mask = raster.rasterizar_con_espaciado(texto, ruta_ttf, raster_px, espaciado_relativo)
    else:
        mask = raster.rasterizar(texto, ruta_ttf, raster_px)
    return neon_pipeline.armar_2d(
        mask, alto_mm, modo_led, led_ancho_mm, holgura_mm, pared_mm, fondo, fondo_margen, redondeo_mm,
        poda_frac, simplify_mm, agregar_canal_salida, cable_ancho_mm, agregar_agujeros, agujero_cable_diam_mm,
        tipo_montaje, n_orejas_montaje, ancho_pata_mm, alto_pata_mm, ancho_max_modulo_mm,
        puentes_altura_completa=puentes_altura_completa,
    )


def preview_rapido(texto, ruta_ttf, alto_mm, modo_led,
                    led_ancho_mm=None, fondo="contorno",
                    holgura_mm=0.4, pared_mm=2.4, fondo_margen=8,
                    raster_px=220, poda_frac=0.06, simplify_mm=0.4, redondeo_mm=0.5,
                    agregar_canal_salida=True, cable_ancho_mm=4.0,
                    agregar_agujeros=True, agujero_cable_diam_mm=5.0,
                    tipo_montaje="colgado", n_orejas_montaje=2,
                    ancho_pata_mm=40.0, alto_pata_mm=15.0, ancho_max_modulo_mm=None,
                    espaciado_relativo=0.0, puentes_altura_completa=True):
    """Preview 2D instantáneo — el mismo trazado/placa que ve `generar()`
    (`_armar_2d`, ni un paso menos: orejas, agujeros, salida de cable,
    líneas de corte, todo), pero SIN mesh3d ni export a STL, que es la
    parte lenta. Devuelve (png_bytes, ancho_mm, alto_mm) o (None, 0, 0)
    si no se pudo generar."""
    if led_ancho_mm is None:
        led_ancho_mm = 6.0 if modo_led == "neon" else 10.0
    if ancho_max_modulo_mm is None:
        ancho_max_modulo_mm = bambu_a1.ANCHO_MAX_RECOMENDADO_MM
    if not os.path.exists(ruta_ttf) or not texto.strip():
        return None, 0, 0
    try:
        d = _armar_2d(
            texto, ruta_ttf, alto_mm, modo_led, led_ancho_mm, holgura_mm, pared_mm, fondo, fondo_margen,
            redondeo_mm, raster_px, poda_frac, simplify_mm, agregar_canal_salida, cable_ancho_mm,
            agregar_agujeros, agujero_cable_diam_mm, tipo_montaje, n_orejas_montaje, ancho_pata_mm,
            alto_pata_mm, ancho_max_modulo_mm, espaciado_relativo=espaciado_relativo,
            puentes_altura_completa=puentes_altura_completa,
        )
    except (ValueError, FileNotFoundError):
        return None, 0, 0

    buf = io.BytesIO()
    preview.guardar_preview(
        buf, d["placa_final"], d["canal"], d["lineas"], texto,
        d["ancho_total_mm"], d["alto_total_mm"], modo_led, cortes=d["cortes_locales"], paredes=d["paredes"],
    )
    return buf.getvalue(), d["ancho_total_mm"], d["alto_total_mm"]


def generar(texto, ruta_ttf, alto_mm, modo_led,
            led_ancho_mm=None, led_prof_mm=None, fondo="contorno",
            holgura_mm=0.4, pared_mm=2.4, placa_mm=3.0, fondo_margen=8,
            raster_px=320, poda_frac=0.06, simplify_mm=0.4, redondeo_mm=0.5,
            agregar_canal_salida=True, cable_ancho_mm=4.0,
            agregar_agujeros=True, agujero_cable_diam_mm=5.0,
            tipo_montaje="colgado", n_orejas_montaje=2,
            ancho_pata_mm=40.0, alto_pata_mm=15.0,
            ancho_max_modulo_mm=None,
            espaciado_relativo=0.0, puentes_altura_completa=True,
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
        texto, ruta_ttf, alto_mm, modo_led, led_ancho_mm, holgura_mm, pared_mm, fondo, fondo_margen,
        redondeo_mm, raster_px, poda_frac, simplify_mm, agregar_canal_salida, cable_ancho_mm,
        agregar_agujeros, agujero_cable_diam_mm, tipo_montaje, n_orejas_montaje, ancho_pata_mm,
        alto_pata_mm, ancho_max_modulo_mm, espaciado_relativo=espaciado_relativo,
        puentes_altura_completa=puentes_altura_completa,
    )
    base = pieza.nombre_archivo(texto, default="salida")
    r = neon_pipeline.armar_3d_y_exportar(
        d, texto, base, modo_led, placa_mm, led_prof_mm, tipo_montaje, alto_pata_mm,
        ancho_max_modulo_mm, carpeta_salida,
    )
    r["texto"] = texto
    r["alto_mm"] = alto_mm
    return r


# ---------------------------------------------------------------------------
#  Interfaz de consola (menú de main.py)
# ---------------------------------------------------------------------------
def _elegir_fuente():
    ttfs_proyecto = sorted(glob.glob(os.path.join(CARPETA_FUENTES, "*.ttf")))
    if ttfs_proyecto:
        print("  Fuentes en fonts/:")
        for i, f in enumerate(ttfs_proyecto, 1):
            print(f"    {i}) {os.path.basename(f)}")
        print("  (o escribí el nombre de una fuente instalada en Windows, ej: 'Comic Sans MS')")
        eleccion = input(f"  Elegí un número, un nombre, o una ruta [1]: ").strip()
        if not eleccion:
            return ttfs_proyecto[0]
        if eleccion.isdigit() and 1 <= int(eleccion) <= len(ttfs_proyecto):
            return ttfs_proyecto[int(eleccion) - 1]
    else:
        eleccion = ui.pedir_texto(
            "Nombre de una fuente instalada en Windows (ej: 'Comic Sans MS') o ruta a un .ttf",
            "Comic Sans MS",
        )

    if os.path.exists(eleccion):
        return eleccion
    encontrada = fuentes.buscar_por_nombre(eleccion)
    if encontrada:
        print(f"    -> usando {encontrada}")
        return encontrada
    return eleccion  # no se encontró; generar() va a avisar que no existe


def ejecutar():
    print(f"\n{NOMBRE}")

    texto = ui.pedir_texto("Texto", "Mis 15")
    ruta_ttf = _elegir_fuente()
    alto_mm = ui.pedir_float("Alto del texto (mm)", 90)
    modo_led = ui.pedir_opcion("Modo LED", ["neon", "ws2812"], "neon")

    default_ancho_led = 6.0 if modo_led == "neon" else 10.0
    default_prof_canal = 8.0 if modo_led == "neon" else 4.0
    led_ancho_mm = ui.pedir_float("Ancho del LED (mm)", default_ancho_led)
    led_prof_mm = ui.pedir_float("Profundidad del canal (mm)", default_prof_canal)
    print("  Placa de fondo: 'contorno' (sigue las letras, gasta poco material),")
    print("    'rect_hundido' (rectángulo macizo, el canal queda como zanja — más rígido y más material),")
    print("    'rect_plano' (rectángulo fino con las letras en relieve — poco material, base conectada)")
    fondo = ui.pedir_opcion("Placa de fondo", list(geometry.FONDOS_VALIDOS), "contorno")

    print(f"\n  » Texto: {texto!r}  fuente: {ruta_ttf}  modo: {modo_led}  LED {led_ancho_mm}mm")

    try:
        r = generar(texto, ruta_ttf, alto_mm, modo_led, led_ancho_mm, led_prof_mm, fondo)
    except (FileNotFoundError, ValueError) as e:
        print(f"  ERROR: {e}")
        return

    print(f"  tamaño del texto ~ {r['ancho_mm']:.0f} x {r['alto_mm']:.0f} mm   trazos: {r['trazos']}")
    print(f"  tamaño total del cartel ~ {r['ancho_total_mm']:.0f} x {r['alto_total_mm']:.0f} mm")
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
