#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generators/topper.py
--------------------
Generador unificado de toppers para tortas, cupcakes, y decoraciones.
Integración 3D completa con STL export y previsualizaciones.
"""

import os
import io
import numpy as np
import trimesh
from PIL import Image, ImageDraw, ImageFont

from core import pieza

NOMBRE = "Topper (decoración para tortas)"
DESCRIPCION = "Toppers 3D, Neón, LED, Acrílico para tortas, cupcakes, postres."

CARPETA_SALIDA = "output"

# Estilos disponibles
ESTILOS = {
    "Minimalista": {"silueta": True, "detalles": 0, "altura_mm": 8},
    "Elegante": {"silueta": False, "detalles": 2, "altura_mm": 12},
    "Divertido": {"silueta": False, "detalles": 3, "altura_mm": 15},
    "Romántico": {"silueta": False, "detalles": 2, "altura_mm": 10},
}


def generar_3d(texto, tamaño_mm=80, estilo="Elegante", color="Dorado", base="Sólida", material="PLA"):
    """Generar topper 3D imprimible con STL export."""
    os.makedirs(CARPETA_SALIDA, exist_ok=True)

    config = ESTILOS.get(estilo, ESTILOS["Elegante"])
    altura_mm = config["altura_mm"]

    # Crear base simple: cilindro con altura variable
    # Base: cilindro de 30mm diámetro, altura 3mm
    base_radio = 15  # mm
    base_altura = 3  # mm

    # Generar cilindro de base
    vertices_base = []
    faces_base = []

    theta = np.linspace(0, 2*np.pi, 16, endpoint=False)
    for i, angle in enumerate(theta):
        x = base_radio * np.cos(angle)
        y = base_radio * np.sin(angle)
        # Parte inferior (Z=0)
        vertices_base.append([x, y, 0])
        # Parte superior (Z=base_altura)
        vertices_base.append([x, y, base_altura])

    # Centro inferior y superior
    idx_center_bottom = len(vertices_base)
    vertices_base.append([0, 0, 0])
    idx_center_top = len(vertices_base)
    vertices_base.append([0, 0, base_altura])

    # Generar caras
    n = len(theta)
    for i in range(n):
        i_next = (i + 1) % n
        # Lado inferior
        faces_base.append([i*2, (i_next)*2, idx_center_bottom])
        # Lado superior
        faces_base.append([i*2+1, idx_center_top, (i_next)*2+1])
        # Lado (lateral)
        faces_base.append([i*2, (i_next)*2, (i_next)*2+1])
        faces_base.append([i*2, (i_next)*2+1, i*2+1])

    # Crear cilindro de topper: radio 25mm, altura variable según estilo
    topper_radio = 25  # mm
    topper_altura = altura_mm

    offset_z = base_altura  # Topper va encima de la base

    vertices_topper = []
    for i, angle in enumerate(theta):
        x = topper_radio * np.cos(angle)
        y = topper_radio * np.sin(angle)
        # Parte inferior del topper
        vertices_topper.append([x, y, offset_z])
        # Parte superior (pico)
        vertices_topper.append([x*0.8, y*0.8, offset_z + topper_altura])

    idx_top_center = len(vertices_topper)
    vertices_topper.append([0, 0, offset_z + topper_altura])

    faces_topper = []
    for i in range(n):
        i_next = (i + 1) % n
        # Base del topper (conecta con base)
        faces_topper.append([i*2, (i_next)*2, (i_next)*2+1])
        faces_topper.append([i*2, (i_next)*2+1, i*2+1])
        # Pico del topper
        faces_topper.append([i*2+1, idx_top_center, (i_next)*2+1])

    # Combinar vértices y caras
    all_vertices = np.array(vertices_base + vertices_topper, dtype=np.float64)
    offset_topper_faces = len(vertices_base)

    # Reconstruir con offset correcto
    all_faces = faces_base.copy()
    for face in faces_topper:
        all_faces.append(tuple([v + offset_topper_faces for v in face]))

    malla = trimesh.Trimesh(vertices=all_vertices, faces=np.array(all_faces, dtype=np.int64), process=True)
    malla.fix_normals()

    # Escalar para que encaje en tamaño deseado
    escala = tamaño_mm / max(malla.extents[:2].max(), 1e-6)
    malla.apply_scale(escala)

    # Exportar STL
    base_nombre = pieza.nombre_archivo(texto, default="topper")
    ruta_stl = os.path.join(CARPETA_SALIDA, f"topper_{base_nombre}_{estilo}.stl")
    malla.export(ruta_stl)

    resultado = {
        "tipo": "3d",
        "texto": texto,
        "tamaño_mm": tamaño_mm,
        "estilo": estilo,
        "material": material,
        "color": color,
        "base": base,
        "ruta_stl": ruta_stl,
        "vertices": len(malla.vertices),
        "caras": len(malla.faces),
        "watertight": malla.is_watertight,
        "estado": "✓ Generado",
    }

    return resultado


def generar_neon(texto, tamaño_mm=80, tipo_led="Flexible (frío)"):
    """Generar topper Neón LED (próximamente)."""
    resultado = {
        "tipo": "neon",
        "texto": texto,
        "tamaño_mm": tamaño_mm,
        "tipo_led": tipo_led,
        "voltaje": "24V",
        "estado": "Próximamente: esquema de corte DXF",
    }
    return resultado


def generar_led(texto, tamaño_mm=80, efecto="Fijo", con_bateria=True):
    """Generar topper LED con efectos (próximamente)."""
    resultado = {
        "tipo": "led",
        "texto": texto,
        "tamaño_mm": tamaño_mm,
        "material": "PLA",
        "efecto": efecto,
        "con_bateria": con_bateria,
        "estado": "Próximamente: STL + esquema LED",
    }
    return resultado


def generar_acrilico(texto, tamaño_mm=80, espesor_mm=3, acabado="Transparente"):
    """Generar topper Acrílico (próximamente)."""
    resultado = {
        "tipo": "acrilico",
        "texto": texto,
        "tamaño_mm": tamaño_mm,
        "espesor_mm": espesor_mm,
        "acabado": acabado,
        "estado": "Próximamente: archivo DXF para láser",
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
