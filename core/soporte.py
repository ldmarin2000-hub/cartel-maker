#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/soporte.py
------------------
Base de escritorio: una pieza aparte, con una ranura donde encastra la
"pata" que sobresale del borde inferior del cartel (ver
core/geometry.py::agregar_pata_escritorio), para que el cartel se pare
solo en un escritorio en vez de colgar de la pared.
"""

import trimesh


def generar_base(ancho_pata_mm, espesor_pata_mm, alto_pata_mm,
                  holgura_mm=0.4, margen_mm=12, profundidad_mm=32, piso_mm=4):
    """Devuelve la malla 3D de la base de escritorio: un bloque con una
    ranura rectangular en el medio donde entra la pata a presión."""
    alto_ranura = alto_pata_mm - 2  # deja ~2mm de pata sin encastrar, por las dudas
    alto_base = piso_mm + alto_ranura

    ancho_base = ancho_pata_mm + 2 * margen_mm
    bloque = trimesh.creation.box(extents=[ancho_base, profundidad_mm, alto_base])
    bloque.apply_translation([0, 0, alto_base / 2])

    ranura = trimesh.creation.box(extents=[
        ancho_pata_mm + holgura_mm, espesor_pata_mm + holgura_mm, alto_ranura + 2
    ])
    ranura.apply_translation([0, 0, alto_base - alto_ranura / 2])

    try:
        base = trimesh.boolean.difference([bloque, ranura], engine="manifold")
    except Exception as e:
        raise RuntimeError(f"no pude generar la ranura de la base de escritorio: {e}")
    return base
