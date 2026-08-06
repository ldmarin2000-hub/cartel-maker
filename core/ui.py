#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/ui.py
------------
Helpers de consola para pedirle parámetros al usuario con un default,
para que el menú sea usable sin ser programador. Los va a usar cualquier
generador (neón, letras, llavero) que necesite preguntar parámetros.
"""


def pedir_texto(mensaje, default):
    valor = input(f"  {mensaje} [{default}]: ").strip()
    return valor if valor else default


def pedir_float(mensaje, default):
    valor = input(f"  {mensaje} [{default}]: ").strip()
    if not valor:
        return default
    try:
        return float(valor)
    except ValueError:
        print("    valor inválido, uso el default.")
        return default


def pedir_opcion(mensaje, opciones, default):
    """`opciones` es una lista de strings válidos; devuelve la elegida."""
    valor = input(f"  {mensaje} ({'/'.join(opciones)}) [{default}]: ").strip().lower()
    return valor if valor in opciones else default


def pedir_si_no(mensaje, default=False):
    etiqueta = "S/n" if default else "s/N"
    valor = input(f"  {mensaje} ({etiqueta}): ").strip().lower()
    if not valor:
        return default
    return valor in ("s", "si", "sí", "y", "yes")
