#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/bambu_a1.py
-----------------
Constantes y chequeos del volumen de impresión de la Bambu Lab A1.
Lo usan todos los generadores para avisar si un modelo entra en el plato
o si conviene partirlo en módulos.
"""

# Volumen de impresión utilizable (mm). Dejamos un margen chico respecto
# de los 256x256x256 "de catálogo" para no pelear con el borde del plato.
VOLUMEN_MM = (256, 256, 256)
ANCHO_MAX_RECOMENDADO_MM = 240  # a partir de acá, conviene partir en módulos


def chequear_tamano(ancho_mm, alto_mm, profundo_mm=None, nombre="modelo"):
    """
    Compara las medidas contra el volumen de la A1. Devuelve
    (entra_sin_partir: bool, mensaje: str) para que la CLI o la app visual
    lo muestren como quieran (print, st.success/st.warning, etc.).
    """
    ax, ay, az = VOLUMEN_MM
    entra = ancho_mm <= ax and alto_mm <= ay and (profundo_mm is None or profundo_mm <= az)

    medidas = f"{ancho_mm:.0f} x {alto_mm:.0f}"
    if profundo_mm is not None:
        medidas += f" x {profundo_mm:.0f}"
    medidas += " mm"

    if not entra:
        mensaje = f"{nombre}: {medidas} NO entra en la Bambu A1 ({ax}x{ay}x{az} mm)."
    elif ancho_mm > ANCHO_MAX_RECOMENDADO_MM:
        mensaje = (f"{nombre}: {medidas} entra justo, pero supera los "
                   f"{ANCHO_MAX_RECOMENDADO_MM} mm recomendados. Conviene partir en módulos.")
    else:
        mensaje = f"{nombre}: {medidas} — entra en la Bambu A1 sin partir."

    return entra and ancho_mm <= ANCHO_MAX_RECOMENDADO_MM, mensaje
