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

Formato del atributo `paint_color`: no hay spec pública, pero el motor
que lo lee/escribe SÍ es open-source (BambuStudio, GPLv3) --
`TriangleSelector::serialize()` en `src/libslic3r/TriangleSelector.cpp`
y `FacetsAnnotation::get_triangle_as_string()` en
`src/libslic3r/Model.cpp`. Cada triángulo (sin subdividir, que es
nuestro caso: pintamos el triángulo ENTERO de un color, no una parte)
codifica su estado (`EnforcerBlockerType`, donde Extruder1=1,
Extruder2=2, Extruder3=3, ...) en grupos de 4 bits (un dígito hex cada
uno), armados así:
  - 2 bits siempre en cero (marcan "sin subdividir")
  - si el extruder es 1 o 2: 2 bits más con el valor (1 o 2) -- un
    único dígito hex de resultado: "4" para extruder 1, "8" para
    extruder 2 (esto SÍ se confirmó mirando un .3mf de 2 colores real:
    todos sus triángulos tenían "4" u "8", nada más).
  - si el extruder es 3 o más: 2 bits en "11" (marcador de "valor
    extendido"), y el `extruder - 3` se agrega en grupos de 4 bits
    adicionales (con relleno "F" cada vez que ese resto pasa de 15) --
    para extruder 3..17 da dos dígitos hex: la unidad primero, "C" fijo
    después (ej. extruder 3 = "0C", extruder 4 = "1C", ..., extruder 17
    = "EC"). Ver `_paint_color_code()` más abajo.

Probé antes una fórmula más simple (extruder × 4 en decimal) que
coincidía por casualidad para 1-2 colores pero rompía el archivo entero
con 3 o más (Bambu Studio los rechazaba con "configuración no válida")
-- quedó reemplazada por esta, derivada directo del código fuente en
vez de adivinada.

El resto del paquete (Content_Types, .rels, namespaces) es el
boilerplate estándar de Bambu Studio, copiado de un .3mf de referencia.
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


def _paint_color_code(numero_extruder):
    """Código hex que espera `paint_color` para un triángulo ENTERO
    (sin subdividir) pintado con el extruder `numero_extruder` (1 =
    primer color/slot). Ver la nota de formato al principio del
    archivo -- extruder 1 y 2 son casos de un solo dígito ("4" y "8"),
    del 3 en adelante son dos dígitos."""
    if numero_extruder == 1:
        return "4"
    if numero_extruder == 2:
        return "8"
    resto = numero_extruder - 3
    relleno = ""
    while resto >= 15:
        relleno += "F"
        resto -= 15
    return f"{resto:X}{relleno}C"


def exportar_pintado(piezas, ruta_3mf):
    """`piezas`: lista de trimesh.Trimesh ya en su posición real
    ensamblada, cada una de un color/extruder distinto (mismo contrato
    que core/pieza.py::exportar_multicolor). Escribe un único .3mf con
    UNA sola malla combinada, cada triángulo pintado según de qué pieza
    vino (`_paint_color_code`) — así Bambu Studio lo abre con los
    colores ya puestos, sin dividir nada. Devuelve la cantidad total de
    triángulos escritos."""
    partes_vertices = []
    lineas_triangulos = []
    offset = 0
    for i, malla in enumerate(piezas):
        paint_color = _paint_color_code(i + 1)
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
