#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generators/portalapices.py
---------------------------
Generador paramétrico de recipientes cilíndricos huecos (portalápices,
vasos, maceteros, organizadores) — geometría de precisión (paredes rectas,
hueco real, base sólida), no reconstrucción de IA desde una foto. Para eso
está core/heightmap.py (relieve) o el modo "Estatua 3D" de Esculturas.

Incluye patrones decorativos procedurales tipo "knurling" (rombos, panal,
rayado, puntos) tallados como relieve real en la pared exterior, en una
franja de altura configurable — igual que un portalápices texturizado
impreso en PLA.
"""

import os
import numpy as np
import trimesh

from core import pieza

CARPETA_SALIDA = "output"

PATRONES = ["Liso", "Diamante (rombos)", "Panal (hexágonos)", "Rayado vertical", "Puntos"]

FORMAS = ["Cilíndrico (recto)", "Cónico (más ancho arriba)", "Cónico (más angosto arriba)"]


def _offset_patron(patron, theta, z_rel, frecuencia_theta, frecuencia_z, profundidad):
    """Devuelve el offset radial (mm, puede ser negativo) para el punto
    (theta, z_rel) según el patrón elegido — z_rel en [0,1] dentro de la
    franja decorada. `profundidad` es el relieve máximo en mm."""
    if patron == "Diamante (rombos)":
        onda = np.sin(theta * frecuencia_theta) * np.sin(z_rel * frecuencia_z * np.pi)
        return profundidad * onda
    if patron == "Panal (hexágonos)":
        a = np.sin(theta * frecuencia_theta + z_rel * frecuencia_z * np.pi * 0.5)
        b = np.sin(theta * frecuencia_theta * 0.5 - z_rel * frecuencia_z * np.pi)
        return profundidad * 0.5 * (a + b)
    if patron == "Rayado vertical":
        return profundidad * np.sin(theta * frecuencia_theta)
    if patron == "Puntos":
        onda = np.cos(theta * frecuencia_theta) * np.cos(z_rel * frecuencia_z * np.pi)
        return profundidad * np.clip(onda, 0, None)
    return np.zeros_like(theta) if hasattr(theta, "shape") else 0.0


def generar(texto="", diametro_mm=80, altura_mm=90, espesor_mm=2.4, espesor_base_mm=3.0,
            forma="Cilíndrico (recto)", patron="Diamante (rombos)",
            franja_patron=("50%", "100%"), densidad_patron=5, profundidad_patron=0.9,
            segmentos=96, anillos=140):
    """Genera un recipiente cilíndrico hueco (portalápices/vaso/macetero)
    con paredes rectas reales y patrón decorativo tallado por relieve.

    `franja_patron`: tupla (inicio%, fin%) de la altura donde va el patrón
    (0%=base, 100%=borde superior) — ej. (50,100) decora solo la mitad
    superior, como un portalápices con banda texturizada arriba y liso abajo.
    """
    os.makedirs(CARPETA_SALIDA, exist_ok=True)

    radio_ext = diametro_mm / 2.0
    radio_int = radio_ext - espesor_mm
    if radio_int <= 1.0:
        raise ValueError("Espesor de pared demasiado grande para este diámetro")

    frac_ini = float(str(franja_patron[0]).replace("%", "")) / 100.0
    frac_fin = float(str(franja_patron[1]).replace("%", "")) / 100.0

    theta = np.linspace(0, 2 * np.pi, segmentos, endpoint=False)
    z_vals = np.linspace(0, altura_mm, anillos)

    factor_conico = {
        "Cónico (más ancho arriba)": 1.0,
        "Cónico (más angosto arriba)": -1.0,
    }.get(forma, 0.0)

    frecuencia_theta = max(4, int(segmentos / max(densidad_patron, 1)))
    frecuencia_z_total = max(2, int(anillos / max(densidad_patron, 1) / 3))

    verts_ext = []
    verts_int = []
    for z in z_vals:
        z_norm = z / altura_mm  # 0..1, usado para el cono
        radio_z = radio_ext * (1.0 + factor_conico * 0.18 * z_norm)
        radio_z_int = radio_int * (1.0 + factor_conico * 0.18 * z_norm)

        en_franja = frac_ini <= z_norm <= frac_fin
        z_rel = (z_norm - frac_ini) / max(frac_fin - frac_ini, 1e-6) if en_franja else 0.0

        for a in theta:
            off = _offset_patron(patron, a, z_rel, frecuencia_theta, frecuencia_z_total, profundidad_patron) if en_franja and patron != "Liso" else 0.0
            r = radio_z + off
            verts_ext.append([r * np.cos(a), r * np.sin(a), z])
            # Interior remapeado de forma continua entre espesor_base_mm y
            # altura_mm (nunca clampeado — un clamp crearía muchos anillos
            # duplicados en el mismo Z, con caras degeneradas de área cero
            # que rompen el watertight).
            z_int = espesor_base_mm + (altura_mm - espesor_base_mm) * z_norm
            verts_int.append([radio_z_int * np.cos(a), radio_z_int * np.sin(a), z_int])

    verts_ext = np.array(verts_ext)
    verts_int = np.array(verts_int)
    n = segmentos
    m = anillos

    faces = []

    def idx_ext(i, j):
        return i * n + j

    def idx_int(i, j):
        return m * n + i * n + j

    # Pared exterior (con relieve del patrón)
    for i in range(m - 1):
        for j in range(n):
            j2 = (j + 1) % n
            faces.append([idx_ext(i, j), idx_ext(i + 1, j), idx_ext(i + 1, j2)])
            faces.append([idx_ext(i, j), idx_ext(i + 1, j2), idx_ext(i, j2)])

    # Pared interior (lisa, orientación invertida — mira hacia adentro)
    for i in range(m - 1):
        for j in range(n):
            j2 = (j + 1) % n
            faces.append([idx_int(i, j2), idx_int(i + 1, j2), idx_int(i + 1, j)])
            faces.append([idx_int(i, j2), idx_int(i + 1, j), idx_int(i, j)])

    # Base sólida (disco entre el centro y el radio exterior, en z=0)
    centro_base_idx = len(verts_ext) + len(verts_int)
    verts_base_centro = np.array([[0.0, 0.0, 0.0]])
    for j in range(n):
        j2 = (j + 1) % n
        faces.append([idx_ext(0, j), centro_base_idx, idx_ext(0, j2)])

    # Borde superior (anillo que cierra exterior con interior en z=altura)
    for j in range(n):
        j2 = (j + 1) % n
        faces.append([idx_ext(m - 1, j), idx_ext(m - 1, j2), idx_int(m - 1, j2)])
        faces.append([idx_ext(m - 1, j), idx_int(m - 1, j2), idx_int(m - 1, j)])

    # Fondo interior (tapa el hueco desde adentro, a la altura de la base)
    idx_fondo_centro = centro_base_idx + 1
    verts_fondo_centro = np.array([[0.0, 0.0, espesor_base_mm]])
    for j in range(n):
        j2 = (j + 1) % n
        faces.append([idx_int(0, j2), idx_fondo_centro, idx_int(0, j)])

    all_verts = np.vstack([verts_ext, verts_int, verts_base_centro, verts_fondo_centro])
    malla = trimesh.Trimesh(vertices=all_verts, faces=np.array(faces, dtype=np.int64), process=True)
    malla.fix_normals()

    base_nombre = pieza.nombre_archivo(texto, default="portalapices")
    patron_slug = "".join(c if c.isalnum() else "_" for c in patron).strip("_")
    ruta_stl = os.path.join(CARPETA_SALIDA, f"portalapices_{base_nombre}_{patron_slug}.stl")
    malla.export(ruta_stl)

    return {
        "texto": texto,
        "diametro_mm": diametro_mm,
        "altura_mm": altura_mm,
        "espesor_mm": espesor_mm,
        "forma": forma,
        "patron": patron,
        "ruta_stl": ruta_stl,
        "vertices": len(malla.vertices),
        "caras": len(malla.faces),
        "watertight": malla.is_watertight,
        "volumen_cm3": round(malla.volume / 1000, 1) if malla.is_watertight else None,
        "estado": "✓ Generado",
    }
