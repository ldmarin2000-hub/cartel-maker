#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/neon_pipeline.py
------------------------
Pipeline compartido "máscara -> esqueleto -> canal LED -> placa -> piezas
3D" que usan generators/neon.py (texto+fuente) y generators/neon_svg.py
(SVG/dibujo trazado): la única diferencia entre ambos es CÓMO se consigue
la máscara binaria de entrada (raster de texto con una fuente vs. raster
de un SVG) — desde ahí (esqueletizado, canal, placa, agujeros, montaje,
partido en módulos, export a STL) el pipeline es idéntico, así que vive
acá una sola vez.
"""

import os

from core import bambu_a1, checks, geometry, mesh3d, modulos, pieza, preview, skeleton

TIPOS_MONTAJE = ("colgado", "escritorio", "ninguno")

VENTANA_AJUSTE_CORTE_MM = 40  # cuánto se puede correr un corte para no caer en un hueco


def armar_2d(mask, alto_mm, modo_led,
             led_ancho_mm, holgura_mm, pared_mm, fondo, fondo_margen, redondeo_mm,
             poda_frac, simplify_mm,
             agregar_canal_salida, cable_ancho_mm,
             agregar_agujeros, agujero_cable_diam_mm,
             tipo_montaje, n_orejas_montaje, ancho_pata_mm, alto_pata_mm,
             ancho_max_modulo_mm, puentes_altura_completa=True):
    """Pipeline 2D puro (esqueleto -> geometría), SIN mesh3d ni STL, a
    partir de una máscara booleana ya armada (da igual si salió de
    rasterizar texto o un SVG). Devuelve un dict con todo lo que necesita
    cada uno para seguir (preview rápido o export final).

    `puentes_altura_completa`: los puentes que sueldan partes sueltas
    (ver `geometry.conectar_componentes`) quedan incluidos en `paredes`
    igual que el resto del trazado, así que por defecto salen con la
    altura completa del cartel (`placa_mm + led_prof_mm`, se nota el
    puente como una pared más). En `False`, se los saca de `paredes`
    antes de calcularla -- quedan solo con la altura de la base
    (`placa_mm`), igual que ya quedan las orejas de montaje (que se
    agregan recién después de calcular `paredes`, por eso nunca tuvieron
    este problema) -- se notan mucho menos."""
    polys, alto_px = skeleton.obtener_polilineas(mask, poda_frac)
    if not polys:
        raise ValueError("no se pudo extraer el recorrido (probá otra resolución/fuente, o revisá el dibujo)")

    lineas, ancho_mm = geometry.escalar_a_mm(polys, alto_px, alto_mm, simplify_mm)

    avisos = list(checks.chequear_curvas_ws2812(modo_led, lineas))

    canal, placa, paredes = geometry.construir_canal_y_placa(
        lineas, led_ancho_mm, holgura_mm, pared_mm, fondo, fondo_margen, redondeo_mm
    )
    avisos += checks.chequear_fusion_trazos(lineas, canal)

    info = []

    if fondo == "contorno":
        placa_sin_puentes = placa
        placa, n_puentes = geometry.conectar_componentes(placa, cable_ancho_mm, pared_mm)
        if puentes_altura_completa or not n_puentes:
            paredes = placa.difference(canal)
        else:
            paredes = placa_sin_puentes.difference(canal)
            info.append("Los puentes quedaron bajitos (altura de la base), no se notan tanto.")
        if n_puentes:
            info.append(f"Se agregaron {n_puentes} puente(s) para unir las partes sueltas en una sola pieza imprimible.")

    if agregar_canal_salida:
        salida = geometry.punto_salida_cable(lineas, placa.bounds)
        if salida:
            punto_exit, borde = salida
            canal, placa, paredes = geometry.agregar_salida_cable(
                canal, placa, paredes, punto_exit, borde, cable_ancho_mm, pared_mm
            )
            info.append(f"Salida de cable agregada hacia el borde '{borde}'.")

    agujeros_cable_poly = None
    if agregar_agujeros:
        # Agujero en TODAS las puntas sueltas del recorrido (incluida la de la salida de
        # cable si está activa: el canalcito lateral saca el cable afuera, pero no alcanza
        # para soldar/fijar la ficha — hace falta un agujero de verdad ahí también).
        placa, n_agujeros, agujeros_cable_poly = geometry.agregar_agujeros_cable(
            placa, lineas, diametro_mm=agujero_cable_diam_mm, pared_min_mm=pared_mm
        )
        if n_agujeros:
            info.append(
                f"{n_agujeros} agujero(s) hacia atrás para soldar/conectar el cable en cada punta "
                f"del recorrido (el cable entre tramos corre pegado a la parte de atrás del cartel)."
            )

    placa_final = placa
    if tipo_montaje == "colgado":
        placa_final, huecos_orejas, huecos_forzados = geometry.agregar_orejas_de_montaje(
            placa, paredes, agujeros_a_evitar=agujeros_cable_poly, n_orejas=n_orejas_montaje
        )
        if huecos_forzados is not None:
            # no se pudo correr del todo (letra muy compacta ahí) -- se resta de paredes
            # como último recurso para que el bocallave quede libre igual, aunque eso deje
            # un tajo visible en la pared en vez de una oreja bien despejada.
            paredes = paredes.difference(huecos_forzados)
            avisos.append(
                "Una oreja de montaje quedó muy pegada a una letra o a un agujero de cable — no "
                "encontré cómo correrla sin despegarla de la placa, así que le corté un pedacito "
                "de la pared ahí para que el agujero del tornillo quede libre igual. Puede quedar "
                "un tajo visible; si molesta, probá con menos orejas o en otra posición de texto."
            )
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

    return {
        "placa_final": placa_final, "canal": canal, "paredes": paredes, "lineas": lineas,
        "cortes_locales": cortes_locales, "ancho_mm": ancho_mm, "ancho_pata_mm": ancho_pata_mm,
        "ancho_total_mm": ancho_total_mm, "alto_total_mm": alto_total_mm,
        "avisos": avisos, "info": info,
    }


def armar_3d_y_exportar(d, etiqueta, base, modo_led, placa_mm, led_prof_mm,
                         tipo_montaje, alto_pata_mm, ancho_max_modulo_mm, carpeta_salida):
    """Parte 3D + export: divide en módulos si hace falta, extruye,
    exporta STL(s) + preview + base de escritorio si corresponde, y arma
    el dict de resultado final. `etiqueta` es lo que se muestra como
    título en el preview PNG (el texto, o el nombre del SVG)."""
    placa_final, canal, paredes, lineas = d["placa_final"], d["canal"], d["paredes"], d["lineas"]
    cortes_locales, avisos, info = d["cortes_locales"], list(d["avisos"]), list(d["info"])
    ancho_mm, ancho_pata_mm = d["ancho_mm"], d["ancho_pata_mm"]
    ancho_total_mm, alto_total_mm = d["ancho_total_mm"], d["alto_total_mm"]

    mods, avisos_dovetail = modulos.dividir_en_modulos(placa_final, paredes, cortes_locales)
    avisos += avisos_dovetail
    if len(mods) > 1:
        info.append(f"Cartel partido en {len(mods)} módulos (con cola de milano) porque supera los {ancho_max_modulo_mm:.0f} mm.")

    os.makedirs(carpeta_salida, exist_ok=True)

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
        pieza_soporte = pieza.exportar_base_escritorio(ancho_pata_mm, placa_mm, alto_pata_mm, base, carpeta_salida)

    ruta_png = os.path.join(carpeta_salida, f"{base}_preview.png")
    preview.guardar_preview(ruta_png, placa_final, canal, lineas, etiqueta, ancho_total_mm, alto_total_mm,
                             modo_led, cortes=cortes_locales, paredes=paredes)

    ancho_pieza_mm = max(m["ancho_mm"] for m in mods) if len(mods) > 1 else ancho_total_mm
    entra_a1, mensaje_a1 = bambu_a1.chequear_tamano(
        ancho_pieza_mm, alto_total_mm, placa_mm + led_prof_mm,
        nombre="cartel" if len(mods) == 1 else "cada módulo",
    )

    return {
        "ancho_mm": ancho_mm,
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
