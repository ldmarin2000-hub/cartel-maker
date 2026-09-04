#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/pieza.py
---------------
Mecánica compartida entre generadores — la parte de "armar el objeto
final" que se repetía casi textual en neon.py/llavero.py/letras.py:
sanitizar un nombre de archivo, exportar piezas sueltas vs. un STL
multicolor combinado (truco AMS: concatenate sin fusionar, cada pieza
queda como su propio cuerpo — Bambu Studio las separa con "Partir en
objetos"), exportar la base de escritorio (core/soporte.py), y medir +
chequear contra la Bambu A1 (core/bambu_a1.py) a partir de una malla ya
armada.

Cada función es un primitivo chico e independiente — la POLÍTICA (qué
exportar sueltas, qué combinar, cuándo agregar soporte) sigue viviendo
en cada generators/*.py, que es donde varía de verdad; acá solo vive el
mecanismo que se repetía igual. Un generador nuevo (lámpara, accesorio,
lo que sea) arranca con esto ya resuelto en vez de reinventarlo.
"""

import os

import trimesh

from core import bambu_a1, exportar_3mf, soporte


def nombre_archivo(texto, default="pieza"):
    """Sanitiza `texto` para usarlo como nombre de archivo (solo
    alfanumérico, separado por _). Devuelve `default` si no queda nada
    aprovechable (texto vacío o solo símbolos)."""
    limpio = "".join(c if c.isalnum() else "_" for c in texto).strip("_")
    return limpio or default


def exportar_multicolor(piezas, ruta_stl):
    """`piezas`: lista de trimesh.Trimesh ya en su posición real
    ensamblada, cada una de un color/pieza distinta. Las concatena SIN
    fusionar (cada una queda como su propio cuerpo en el STL — no una
    unión booleana) y exporta un solo archivo: un solo import a Bambu
    Studio, sin que el slicer reacomode piezas sueltas y las desalinee.
    Devuelve la malla combinada."""
    malla = trimesh.util.concatenate(piezas)
    malla.export(ruta_stl)
    return malla


def exportar_multicolor_3mf(piezas, ruta_3mf, colores_hex=None):
    """`piezas`: lista de trimesh.Trimesh ya en su posición real
    ensamblada, cada una de un color/pieza distinta (mismo contrato que
    exportar_multicolor). Exporta un .3mf con la malla ya PINTADA por
    triángulo según la pieza de origen (core/exportar_3mf.py) — abre
    directo en Bambu Studio con los colores puestos, sin que el usuario
    tenga que dividir el objeto (lo que resultó frágil con el STL
    combinado: a veces Bambu Studio ni lo dividía bien).

    `colores_hex`: opcional, un "#RRGGBB" por pieza (mismo orden que
    `piezas`) -- sin esto, Bambu Studio muestra cada slot con el color
    que ya tuviera configurado el proyecto, no necesariamente el que se
    buscaba. Devuelve la cantidad de triángulos escritos."""
    return exportar_3mf.exportar_pintado(piezas, ruta_3mf, colores_hex=colores_hex)


def exportar_piezas_sueltas(piezas_con_nombre, carpeta_salida, prefijo):
    """`piezas_con_nombre`: lista de (malla, nombre_sufijo) — cada una ya
    posicionada como se quiera imprimir (apoyada en el suelo, etc.).
    Exporta un STL por pieza para pegarlas a mano después. Devuelve una
    lista de dicts `{"ruta_stl", "nombre", "vertices", "watertight"}`."""
    os.makedirs(carpeta_salida, exist_ok=True)
    resultado = []
    for malla, nombre in piezas_con_nombre:
        ruta = os.path.join(carpeta_salida, f"{prefijo}_{nombre}.stl")
        malla.export(ruta)
        resultado.append({
            "ruta_stl": ruta, "nombre": nombre,
            "vertices": len(malla.vertices), "watertight": malla.is_watertight,
        })
    return resultado


def exportar_base_escritorio(ancho_pata_mm, espesor_mm, alto_pata_mm, base_nombre, carpeta_salida):
    """Genera y exporta la base de escritorio (ranura a presión para la
    pata — core/soporte.py, el mismo accesorio que ya usan el cartel de
    neón y la letra iluminada). Devuelve el dict de pieza
    `{"ruta_stl", "vertices", "watertight"}`."""
    os.makedirs(carpeta_salida, exist_ok=True)
    ruta = os.path.join(carpeta_salida, f"{base_nombre}_base_escritorio.stl")
    malla = soporte.generar_base(ancho_pata_mm, espesor_mm, alto_pata_mm)
    malla.export(ruta)
    return {"ruta_stl": ruta, "vertices": len(malla.vertices), "watertight": malla.is_watertight}


def chequear_desde_malla(malla, nombre="modelo"):
    """Mide `malla` por sus bounds y chequea si entra en la Bambu A1 sin
    partir (core/bambu_a1.py). Devuelve (ancho_mm, alto_mm, profundo_mm,
    entra_a1, mensaje_a1)."""
    (minx, miny, minz), (maxx, maxy, maxz) = malla.bounds
    ancho_mm, alto_mm, profundo_mm = maxx - minx, maxy - miny, maxz - minz
    entra_a1, mensaje_a1 = bambu_a1.chequear_tamano(ancho_mm, alto_mm, profundo_mm, nombre=nombre)
    return ancho_mm, alto_mm, profundo_mm, entra_a1, mensaje_a1
