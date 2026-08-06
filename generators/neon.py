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
import os

from core import bambu_a1, checks, fuentes, geometry, mesh3d, modulos, preview, raster, skeleton, soporte, ui

TIPOS_MONTAJE = ("colgado", "escritorio", "ninguno")

NOMBRE = "Cartel de neón (texto trazado)"
DESCRIPCION = "Texto + fuente .ttf -> canal LED que dibuja las letras. STL + preview."

CARPETA_FUENTES = "fonts"
CARPETA_SALIDA = "output"

VENTANA_AJUSTE_CORTE_MM = 40  # cuánto se puede correr un corte para no caer en un hueco


def _nombre_archivo(texto):
    limpio = "".join(c if c.isalnum() else "_" for c in texto).strip("_")
    return limpio or "salida"


def generar(texto, ruta_ttf, alto_mm, modo_led,
            led_ancho_mm=None, led_prof_mm=None, fondo="contorno",
            holgura_mm=0.4, pared_mm=2.4, placa_mm=3.0, fondo_margen=8,
            raster_px=320, poda_frac=0.06, simplify_mm=0.4, redondeo_mm=0.5,
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

    if not os.path.exists(ruta_ttf):
        raise FileNotFoundError(f"no encuentro la fuente: {ruta_ttf}")

    mask = raster.rasterizar(texto, ruta_ttf, raster_px)
    polys, alto_px = skeleton.obtener_polilineas(mask, poda_frac)
    if not polys:
        raise ValueError("no se pudo extraer el recorrido (probá otra fuente o subí la resolución)")

    lineas, ancho_mm = geometry.escalar_a_mm(polys, alto_px, alto_mm, simplify_mm)

    avisos = list(checks.chequear_curvas_ws2812(modo_led, lineas))

    canal, placa, paredes = geometry.construir_canal_y_placa(
        lineas, led_ancho_mm, holgura_mm, pared_mm, fondo, fondo_margen, redondeo_mm
    )
    avisos += checks.chequear_fusion_trazos(lineas, canal)

    info = []

    if fondo == "contorno":
        placa, n_puentes = geometry.conectar_componentes(placa, cable_ancho_mm, pared_mm)
        paredes = placa.difference(canal)
        if n_puentes:
            info.append(f"Se agregaron {n_puentes} puente(s) para unir las letras sueltas en una sola pieza imprimible.")

    if agregar_canal_salida:
        salida = geometry.punto_salida_cable(lineas, placa.bounds)
        if salida:
            punto_exit, borde = salida
            canal, placa, paredes = geometry.agregar_salida_cable(
                canal, placa, paredes, punto_exit, borde, cable_ancho_mm, pared_mm
            )
            info.append(f"Salida de cable agregada hacia el borde '{borde}'.")

    if agregar_agujeros:
        # Agujero en TODAS las puntas sueltas del recorrido (incluida la de la salida de
        # cable si está activa: el canalcito lateral saca el cable afuera, pero no alcanza
        # para soldar/fijar la ficha — hace falta un agujero de verdad ahí también).
        placa, n_agujeros = geometry.agregar_agujeros_cable(
            placa, lineas, diametro_mm=agujero_cable_diam_mm, pared_min_mm=pared_mm
        )
        if n_agujeros:
            info.append(
                f"{n_agujeros} agujero(s) hacia atrás para soldar/conectar el cable en cada punta "
                f"del recorrido (el cable entre letras corre pegado a la parte de atrás del cartel)."
            )

    placa_final = placa
    if tipo_montaje == "colgado":
        placa_final = geometry.agregar_orejas_de_montaje(placa, n_orejas=n_orejas_montaje)
        info.append(f"{n_orejas_montaje} oreja(s) de montaje con agujero bocallave agregadas arriba.")
    elif tipo_montaje == "escritorio":
        placa_final, ancho_pata_mm = geometry.agregar_pata_escritorio(
            placa, ancho_pata_mm=ancho_pata_mm, alto_pata_mm=alto_pata_mm
        )
        info.append(
            f"Pata de {ancho_pata_mm:.0f}mm agregada abajo para encastrar en la base de "
            f"escritorio (STL aparte)."
        )

    minx, miny, maxx, maxy = placa_final.bounds
    ancho_total_mm, alto_total_mm = maxx - minx, maxy - miny

    n_modulos, cortes = modulos.calcular_cortes(ancho_total_mm, ancho_max_modulo_mm)
    cortes_locales = [c + minx for c in cortes]  # cortes de calcular_cortes son relativos a x=0
    if cortes_locales:
        cortes_locales, avisos_corte = modulos.ajustar_cortes(placa_final, cortes_locales, VENTANA_AJUSTE_CORTE_MM)
        avisos += avisos_corte
    mods, avisos_dovetail = modulos.dividir_en_modulos(placa_final, paredes, cortes_locales)
    avisos += avisos_dovetail
    if len(mods) > 1:
        info.append(f"Cartel partido en {len(mods)} módulos (con cola de milano) porque supera los {ancho_max_modulo_mm:.0f} mm.")

    os.makedirs(carpeta_salida, exist_ok=True)
    base = _nombre_archivo(texto)

    piezas_resultado = []
    for m in mods:
        piezas3d = mesh3d.piezas_desde_geom(m["placa"], placa_mm)
        piezas3d += mesh3d.piezas_desde_geom(m["paredes"], led_prof_mm, z=placa_mm)
        sufijo = f"_modulo{m['indice']}de{m['de']}" if m["de"] > 1 else ""
        ruta_stl = os.path.join(carpeta_salida, f"{base}{sufijo}.stl")
        malla = mesh3d.unir_y_exportar(piezas3d, ruta_stl)
        piezas_resultado.append({
            "indice": m["indice"], "de": m["de"], "ruta_stl": ruta_stl,
            "ancho_mm": m["ancho_mm"], "vertices": len(malla.vertices), "watertight": malla.is_watertight,
        })

    pieza_soporte = None
    if tipo_montaje == "escritorio":
        ruta_soporte = os.path.join(carpeta_salida, f"{base}_base_escritorio.stl")
        malla_soporte = soporte.generar_base(ancho_pata_mm, placa_mm, alto_pata_mm)
        malla_soporte.export(ruta_soporte)
        pieza_soporte = {
            "ruta_stl": ruta_soporte, "vertices": len(malla_soporte.vertices),
            "watertight": malla_soporte.is_watertight,
        }

    ruta_png = os.path.join(carpeta_salida, f"{base}_preview.png")
    preview.guardar_preview(ruta_png, placa_final, canal, lineas, texto, ancho_total_mm, alto_total_mm,
                             modo_led, cortes=cortes_locales, paredes=paredes)

    ancho_pieza_mm = max(m["ancho_mm"] for m in mods) if len(mods) > 1 else ancho_total_mm
    entra_a1, mensaje_a1 = bambu_a1.chequear_tamano(
        ancho_pieza_mm, alto_total_mm, placa_mm + led_prof_mm,
        nombre="cartel" if len(mods) == 1 else "cada módulo",
    )

    return {
        "texto": texto,
        "ancho_mm": ancho_mm, "alto_mm": alto_mm,
        "ancho_total_mm": ancho_total_mm, "alto_total_mm": alto_total_mm,
        "trazos": len(lineas),
        "piezas": piezas_resultado,
        "pieza_soporte": pieza_soporte,
        "ruta_png": ruta_png,
        "avisos": avisos,
        "info": info,
        "entra_a1": entra_a1,
        "mensaje_a1": mensaje_a1,
    }


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
