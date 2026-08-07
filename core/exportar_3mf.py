#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/exportar_3mf.py
-----------------------
Exportador de .3mf con la malla PINTADA por triángulo (`paint_color`),
la misma técnica que usa la función nativa "pintar colores" de Bambu
Studio — no depende de que el usuario divida un STL con cuerpos sueltos
en objetos dentro del slicer (core/pieza.py::exportar_multicolor), que
en la práctica resultó frágil (a veces ni divide bien, ver charla con el
usuario). Con esto el archivo abre listo, con los colores ya asignados,
sin pasos extra.

Formato deducido leyendo un .3mf real exportado por Bambu Studio (no hay
spec pública de esta extensión particular): cada `<triangle>` lleva un
atributo `paint_color="N"` donde N = número de extruder (1, 2, 3...) x 4
— confirmado empíricamente: un archivo de referencia con 2 colores tenía
SOLO los valores "4" y "8" en TODOS sus triángulos, sin excepción (ni uno
sin pintar). El resto del paquete (Content_Types, .rels, namespaces) es
el boilerplate estándar de Bambu Studio, copiado tal cual de ese mismo
archivo de referencia.
"""

import zipfile

import numpy as np

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
 <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
 <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
</Types>
"""

_RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Target="/3D/3dmodel.model" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>
"""

_MODEL_HEADER = """<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" xmlns:BambuStudio="http://schemas.bambulab.com/package/2021" xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06" requiredextensions="p">
 <resources>
  <object id="1" type="model">
   <mesh>
    <vertices>
"""

_MODEL_ENTRE_VERTICES_Y_TRIANGULOS = """    </vertices>
    <triangles>
"""

_MODEL_FOOTER = """    </triangles>
   </mesh>
  </object>
 </resources>
 <build>
  <item objectid="1" printable="1"/>
 </build>
</model>
"""


def exportar_pintado(piezas, ruta_3mf):
    """`piezas`: lista de trimesh.Trimesh ya en su posición real
    ensamblada, cada una de un color/extruder distinto (mismo contrato
    que core/pieza.py::exportar_multicolor). Escribe un único .3mf con
    UNA sola malla combinada, cada triángulo pintado según de qué pieza
    vino (`paint_color = (índice + 1) * 4`) — así Bambu Studio lo abre
    con los colores ya puestos, sin dividir nada. Devuelve la cantidad
    total de triángulos escritos."""
    partes_vertices = []
    lineas_triangulos = []
    offset = 0
    for i, malla in enumerate(piezas):
        paint_color = (i + 1) * 4
        verts = malla.vertices
        partes_vertices.append(verts)
        for f in malla.faces:
            v1, v2, v3 = f[0] + offset, f[1] + offset, f[2] + offset
            lineas_triangulos.append(
                f'     <triangle v1="{v1}" v2="{v2}" v3="{v3}" paint_color="{paint_color}"/>\n'
            )
        offset += len(verts)

    todos_los_vertices = np.concatenate(partes_vertices, axis=0)
    lineas_vertices = [
        f'     <vertex x="{x:.6f}" y="{y:.6f}" z="{z:.6f}"/>\n' for x, y, z in todos_los_vertices
    ]

    modelo_xml = (
        _MODEL_HEADER
        + "".join(lineas_vertices)
        + _MODEL_ENTRE_VERTICES_Y_TRIANGULOS
        + "".join(lineas_triangulos)
        + _MODEL_FOOTER
    )

    with zipfile.ZipFile(ruta_3mf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CONTENT_TYPES)
        z.writestr("_rels/.rels", _RELS)
        z.writestr("3D/3dmodel.model", modelo_xml)

    return len(lineas_triangulos)
