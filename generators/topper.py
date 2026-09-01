#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generators/topper.py
--------------------
Generador unificado de toppers para tortas, cupcakes, y decoraciones.
Soporta: 3D, Neón, LED, Acrílico grabado.
"""

import os
from core import heightmap, pieza

NOMBRE = "Topper (decoración para tortas)"
DESCRIPCION = "Toppers 3D, Neón, LED, Acrílico para tortas, cupcakes, postres."

CARPETA_SALIDA = "output"

# Estilos disponibles
ESTILOS = {
    "Minimalista": {"silueta": True, "detalles": 0},
    "Elegante": {"silueta": False, "detalles": 2},
    "Divertido": {"silueta": False, "detalles": 3},
    "Romántico": {"silueta": False, "detalles": 2},
}

TIPOS_TOPPER = {
    "Topper 3D (escultura pequeña)": "3d",
    "Topper Neón (texto/símbolo LED flexible)": "neon",
    "Topper LED (iluminado con efectos)": "led",
    "Topper Acrílico (grabado láser)": "acrilico",
}


def generar_3d(texto, tamaño_mm=80, estilo="Elegante", color="Dorado", base="Sólida"):
    """Generar topper 3D imprimible."""
    config = ESTILOS.get(estilo, ESTILOS["Elegante"])

    resultado = {
        "tipo": "3d",
        "texto": texto,
        "tamaño_mm": tamaño_mm,
        "estilo": estilo,
        "material": "PLA",
        "color": color,
        "base": base,
        "estado": "Generado (próximamente: STL descargable)",
    }

    return resultado


def generar_neon(texto, tamaño_mm=80, tipo_led="Flexible (frío)"):
    """Generar topper Neón LED."""
    resultado = {
        "tipo": "neon",
        "texto": texto,
        "tamaño_mm": tamaño_mm,
        "tipo_led": tipo_led,
        "voltaje": "24V",
        "estado": "Generado (próximamente: esquema de corte)",
    }

    return resultado


def generar_led(texto, tamaño_mm=80, efecto="Fijo", con_bateria=True):
    """Generar topper LED con efectos."""
    resultado = {
        "tipo": "led",
        "texto": texto,
        "tamaño_mm": tamaño_mm,
        "material": "PLA",
        "efecto": efecto,
        "con_bateria": con_bateria,
        "estado": "Generado (próximamente: STL + esquema LED)",
    }

    return resultado


def generar_acrilico(texto, tamaño_mm=80, espesor_mm=3, acabado="Transparente"):
    """Generar topper Acrílico grabable por láser."""
    resultado = {
        "tipo": "acrilico",
        "texto": texto,
        "tamaño_mm": tamaño_mm,
        "espesor_mm": espesor_mm,
        "acabado": acabado,
        "estado": "Generado (próximamente: archivo DXF para láser)",
    }

    return resultado


def generar(tipo, texto, tamaño_mm=80, **kwargs):
    """Generador unificado de toppers."""
    if tipo == "3d":
        return generar_3d(texto, tamaño_mm, **kwargs)
    elif tipo == "neon":
        return generar_neon(texto, tamaño_mm, **kwargs)
    elif tipo == "led":
        return generar_led(texto, tamaño_mm, **kwargs)
    elif tipo == "acrilico":
        return generar_acrilico(texto, tamaño_mm, **kwargs)
    else:
        raise ValueError(f"Tipo de topper desconocido: {tipo}")
