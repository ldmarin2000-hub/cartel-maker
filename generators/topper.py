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


def generar_neon(texto, tamaño_mm=80, tipo_led="Flexible (frío)", grosor_tubo=10):
    """Generar topper Neón LED flexible con DXF."""
    os.makedirs(CARPETA_SALIDA, exist_ok=True)

    # Estimar longitud de tubo según ancho del texto (aprox. 0.6mm por letra)
    largo_texto_mm = len(texto) * 6 + 20  # +20 para conexiones
    altura_tubo = grosor_tubo + 2  # Margen para tubo rígido de soporte

    # Crear rectángulo en DXF para representar el recorrido del tubo
    try:
        import dxf  # pip install ezdxf
    except ImportError:
        # Fallback: crear DXF simple sin ezdxf
        dxf_content = f"""SECTION
  2
ENTITIES
  0
LWPOLYLINE
  5
1F
100
AcDbEntity
  8
TUBO_LED
100
AcDbLwPolyline
 90
4
 70
1
 10
0.0
 20
0.0
 10
{largo_texto_mm}
 20
0.0
 10
{largo_texto_mm}
 20
{altura_tubo}
 10
0.0
 20
{altura_tubo}
ENDSEC
  0
EOF"""
    else:
        # Usar ezdxf si disponible
        from ezdxf import new
        doc = new("R2010")
        msp = doc.modelspace()
        msp.add_lwpolyline([
            (0, 0), (largo_texto_mm, 0),
            (largo_texto_mm, altura_tubo), (0, altura_tubo)
        ], dxfattribs={"layer": "TUBO_LED"})
        dxf_content = doc.export()

    base_nombre = pieza.nombre_archivo(texto, default="topper")
    ruta_dxf = os.path.join(CARPETA_SALIDA, f"neon_{base_nombre}_{tipo_led.replace(' ', '_')}.dxf")

    with open(ruta_dxf, "w", encoding="utf-8") as f:
        f.write(dxf_content)

    # Calcular consumo energético (LED flexible: ~1.5W/m)
    consumo_w = (largo_texto_mm / 1000) * 1.5
    voltaje = "24V" if tipo_led.startswith("Flexible") else "5V"

    resultado = {
        "tipo": "neon",
        "texto": texto,
        "tamaño_mm": tamaño_mm,
        "tipo_led": tipo_led,
        "grosor_tubo": grosor_tubo,
        "largo_tubo_mm": largo_texto_mm,
        "voltaje": voltaje,
        "consumo_w": round(consumo_w, 1),
        "ruta_dxf": ruta_dxf,
        "estado": "✓ Generado",
    }
    return resultado


def generar_led(texto, tamaño_mm=80, material="PLA", efecto="Fijo", con_bateria=True):
    """Generar topper LED con estructura e integración LED."""
    os.makedirs(CARPETA_SALIDA, exist_ok=True)

    # Crear cilindro LED: estructura más grande que 3D para albergar LEDs
    base_radio = 20  # mm
    base_altura = 4  # mm

    # Generar cilindro de base
    vertices_base = []
    faces_base = []

    theta = np.linspace(0, 2*np.pi, 16, endpoint=False)
    for i, angle in enumerate(theta):
        x = base_radio * np.cos(angle)
        y = base_radio * np.sin(angle)
        vertices_base.append([x, y, 0])
        vertices_base.append([x, y, base_altura])

    idx_center_bottom = len(vertices_base)
    vertices_base.append([0, 0, 0])
    idx_center_top = len(vertices_base)
    vertices_base.append([0, 0, base_altura])

    # Generar caras
    n = len(theta)
    for i in range(n):
        i_next = (i + 1) % n
        faces_base.append([i*2, (i_next)*2, idx_center_bottom])
        faces_base.append([i*2+1, idx_center_top, (i_next)*2+1])
        faces_base.append([i*2, (i_next)*2, (i_next)*2+1])
        faces_base.append([i*2, (i_next)*2+1, i*2+1])

    # Crear cilindro LED: estructura hueca para LED strip
    led_radio = 28  # mm
    led_altura = 20  # Más alto para espacio de LEDs

    offset_z = base_altura

    vertices_led = []
    for i, angle in enumerate(theta):
        x = led_radio * np.cos(angle)
        y = led_radio * np.sin(angle)
        vertices_led.append([x, y, offset_z])
        vertices_led.append([x*0.9, y*0.9, offset_z + led_altura])

    idx_top_center = len(vertices_led)
    vertices_led.append([0, 0, offset_z + led_altura])

    faces_led = []
    for i in range(n):
        i_next = (i + 1) % n
        faces_led.append([i*2, (i_next)*2, (i_next)*2+1])
        faces_led.append([i*2, (i_next)*2+1, i*2+1])
        faces_led.append([i*2+1, idx_top_center, (i_next)*2+1])

    # Combinar vértices
    all_vertices = np.array(vertices_base + vertices_led, dtype=np.float64)
    offset_led_faces = len(vertices_base)

    all_faces = faces_base.copy()
    for face in faces_led:
        all_faces.append(tuple([v + offset_led_faces for v in face]))

    malla = trimesh.Trimesh(vertices=all_vertices, faces=np.array(all_faces, dtype=np.int64), process=True)
    malla.fix_normals()

    # Escalar
    escala = tamaño_mm / max(malla.extents[:2].max(), 1e-6)
    malla.apply_scale(escala)

    # Exportar STL
    base_nombre = pieza.nombre_archivo(texto, default="topper")
    ruta_stl = os.path.join(CARPETA_SALIDA, f"led_{base_nombre}_{efecto}.stl")
    malla.export(ruta_stl)

    # Especificaciones LED
    consumo_w = {"Fijo": 5.0, "Parpadeo": 4.5, "Secuencial": 5.5, "Arcoíris": 6.0}.get(efecto, 5.0)
    voltaje = "5V USB" if con_bateria else "12V"

    resultado = {
        "tipo": "led",
        "texto": texto,
        "tamaño_mm": tamaño_mm,
        "material": material,
        "efecto": efecto,
        "con_bateria": con_bateria,
        "consumo_w": consumo_w,
        "voltaje": voltaje,
        "ruta_stl": ruta_stl,
        "vertices": len(malla.vertices),
        "caras": len(malla.faces),
        "estado": "✓ Generado",
    }
    return resultado


def generar_acrilico(texto, tamaño_mm=80, espesor_mm=3, acabado="Transparente"):
    """Generar topper Acrílico para grabado láser con DXF."""
    os.makedirs(CARPETA_SALIDA, exist_ok=True)

    # Crear forma simple de topper: rectángulo + círculos de esquina
    ancho = tamaño_mm + 20
    alto = int(tamaño_mm * 0.6) + 10
    radio_esquina = 5

    # DXF básico para topper acrílico
    dxf_content = f"""SECTION
  2
ENTITIES
  0
LWPOLYLINE
  5
1F
100
AcDbEntity
  8
CORTE
100
AcDbLwPolyline
 90
4
 70
1
 10
{radio_esquina}
 20
0.0
 10
{ancho - radio_esquina}
 20
0.0
 10
{ancho}
 20
{radio_esquina}
 10
{ancho}
 20
{alto - radio_esquina}
 10
{ancho - radio_esquina}
 20
{alto}
 10
{radio_esquina}
 20
{alto}
 10
0.0
 20
{alto - radio_esquina}
 10
0.0
 20
{radio_esquina}
  0
TEXT
  5
20
100
AcDbEntity
  8
GRABADO
100
AcDbText
 10
{ancho/2}
 20
{alto/2}
 40
6.0
  1
{texto}
ENDSEC
  0
EOF"""

    base_nombre = pieza.nombre_archivo(texto, default="topper")
    ruta_dxf = os.path.join(CARPETA_SALIDA, f"acrilico_{base_nombre}_{acabado.replace(' ', '_')}.dxf")

    with open(ruta_dxf, "w", encoding="utf-8") as f:
        f.write(dxf_content)

    # Calcular potencia láser basada en espesor y acabado
    potencia_base = espesor_mm * 20  # W
    potencia_grabado = {"Espejo": potencia_base * 0.8, "Transparente": potencia_base * 1.0,
                        "Mate": potencia_base * 1.2, "Color": potencia_base * 0.9}.get(acabado, potencia_base)

    # Tiempo estimado de corte (aprox. 5mm/s en acrílico)
    perimetro = 2 * (ancho + alto)
    tiempo_corte = perimetro / 5  # segundos

    resultado = {
        "tipo": "acrilico",
        "texto": texto,
        "tamaño_mm": tamaño_mm,
        "espesor_mm": espesor_mm,
        "acabado": acabado,
        "ancho": ancho,
        "alto": alto,
        "potencia_w": int(potencia_grabado),
        "tiempo_corte_s": round(tiempo_corte, 1),
        "ruta_dxf": ruta_dxf,
        "estado": "✓ Generado",
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
