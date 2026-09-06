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

Con el paint_color ya bien codificado, Bambu Studio SEGUÍA rechazando
el archivo con el mismo error ("El archivo 3mf tiene una configuración
no válida, carga solo los datos de geometría"). La causa: nuestro .3mf
no tenía ningún `<metadata>` en el <model>, y `_handle_end_metadata()`
en bbs_3mf.cpp solo marca el archivo como "`is_bbl_3mf`" (uno propio de
Bambu Studio, con soporte completo de paint_color y demás extensiones)
si encuentra `<metadata name="Application">` con un valor que empiece
con "BambuStudio-" -- sin esa marca, Bambu Studio lo trata como un .3mf
GENÉRICO de otro programa, y para esos no confía/interpreta el
paint_color -- de ahí el "carga solo los datos de geometría" (ignora
todo lo que no sea la malla). Agregamos esas dos líneas de metadata
(mismos nombres/valores que escribe `save_model_to_file()` en
bbs_3mf.cpp) al principio del <model>.

El resto del paquete (Content_Types, .rels, namespaces) es el
boilerplate estándar de Bambu Studio, copiado de un .3mf de referencia.

IMPORTANTE -- lo que el paint_color NO hace: solo dice "este triángulo
es del extruder/slot N", no lleva ningún color adentro. El color de
verdad que se VE sale de `filament_colour` en `Metadata/
project_settings.config` (un JSON plano, ver `ConfigBase::save_to_json`
en Config.cpp -- claves = nombre de la opción, arrays para las que
tienen un valor por extruder). Sin ese archivo, Bambu Studio pinta cada
slot con lo que sea que ya tenga configurado ese número de extruder en
el proyecto actual -- por eso probamos un .3mf con 4 colores elegidos
(dorado/blanco/negro/etc.) y salió con OTROS colores (los que ya
estaban puestos en esos slots), aunque cada región sí se distinguía
bien de las demás. `exportar_pintado(..., colores_hex=[...])` ahora
también escribe ese archivo -- ver `_project_config_json()`.
"""

import json
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
<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" xmlns:BambuStudio="http://schemas.bambulab.com/package/2021">
 <metadata name="Application">BambuStudio-01.09.05.51</metadata>
 <metadata name="BambuStudio:3mfVersion">1</metadata>
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


def _normalizar_hex(hex_color):
    """"#C9A94F", "c9a94f", " #C9A94F " -> todos "#c9a94f" -- así dos
    regiones que llegan con el mismo color pero distinta may/minúscula
    (o sin el "#") no cuentan como colores distintos al deduplicar."""
    h = hex_color.strip().lower()
    if not h.startswith("#"):
        h = "#" + h
    return h


def _project_config_json(colores_hex_unicos):
    """`Metadata/project_settings.config` mínimo (mismo formato JSON
    plano que escribe ConfigBase::save_to_json) -- alcanza con
    `filament_colour`/`filament_type`, UN valor por extrusor/slot REAL
    (ya deduplicado -- ver `exportar_pintado`), en el mismo orden que
    `indice_por_color` le asignó a cada uno (slot 1 = primer color
    único visto, etc.). Sin esto el color de cada slot queda librado a
    lo que ya tuviera configurado el proyecto donde se abra el
    archivo. Declarar más slots que colores únicos reales es lo que
    hacía que la A1 (AMS lite, 4 filamentos) rechazara el archivo con
    "configuración no válida" ante un diseño de pocos colores repetidos
    en muchas regiones."""
    n = len(colores_hex_unicos)
    return json.dumps({
        "version": "01.09.05.51",
        "name": "project_settings",
        "from": "project",
        "filament_colour": list(colores_hex_unicos),
        "filament_type": ["PLA"] * n,
        "filament_settings_id": [""] * n,
    }, ensure_ascii=False, indent=1)


LIMITE_FILAMENTOS_A1_AMS_LITE = 4


def _aviso_limite_colores(etiquetas):
    """Aviso para la UI si `etiquetas` (nombres o hex, uno por color
    ÚNICO) supera lo que soporta un AMS lite de 4 filamentos -- el
    archivo se genera igual (no se recorta nada acá), es solo
    informativo. None si entra sin problema."""
    n = len(etiquetas)
    if n <= LIMITE_FILAMENTOS_A1_AMS_LITE:
        return None
    return (
        f"Este diseño usa {n} colores ({', '.join(etiquetas)}). "
        f"La A1 con AMS lite soporta {LIMITE_FILAMENTOS_A1_AMS_LITE}. "
        "Unificá regiones al mismo color hasta llegar a "
        f"{LIMITE_FILAMENTOS_A1_AMS_LITE} o menos."
    )


def exportar_pintado(piezas, ruta_3mf, colores_hex=None, nombres_colores=None):
    """`piezas`: lista de trimesh.Trimesh ya en su posición real
    ensamblada (mismo contrato que core/pieza.py::exportar_multicolor).
    Escribe un único .3mf con UNA sola malla combinada, cada triángulo
    pintado según a qué COLOR ÚNICO pertenece su pieza de origen
    (`_paint_color_code`) — así Bambu Studio lo abre con los colores ya
    puestos, sin dividir nada.

    `colores_hex`: opcional, un "#RRGGBB" por pieza (mismo orden y
    misma cantidad que `piezas` -- puede repetirse: varias piezas/
    regiones distintas con el mismo color real). Antes de armar nada,
    se normaliza cada hex (minúscula, con "#") y se deduplica -- dos
    regiones "Dorado"/"#C9A94F" y "#c9a94f" cuentan como UN solo color,
    y todas las piezas que compartan color quedan pintadas con el MISMO
    índice de extrusor (`indice_por_color`). Esto es lo que evita
    declarar más filamentos que colores reales en
    `Metadata/project_settings.config` (la causa de que la A1 con AMS
    lite -- 4 filamentos -- rechazara como "configuración no válida"
    un diseño con, por ejemplo, 8 regiones pero solo 5 colores reales
    repetidos entre ellas). Sin `colores_hex` (llavero/letras, que no
    pasan colores a esta función) no hay forma de saber qué piezas
    comparten color -- se sigue pintando una por su propio índice, como
    antes.

    `nombres_colores`: opcional, un nombre legible (`core/colores.py`)
    por pieza, mismo orden que `colores_hex` -- solo se usa para armar
    el aviso de límite de filamentos con nombres en vez de hex crudo
    (ej. "Dorado" en vez de "#c9a94f"); si falta o no calza en longitud,
    el aviso cae a mostrar el hex.

    Devuelve SIEMPRE un dict `{"triangulos", "colores_unicos", "aviso"}`
    -- `colores_unicos` es la cantidad de colores reales distintos (o
    la cantidad de piezas si no se pasó `colores_hex`); `aviso` es el
    mensaje de límite de AMS lite si superan 4, si no `None`. El
    archivo se genera igual en cualquier caso -- este dict es solo
    informativo, no recorta nada."""
    if colores_hex:
        colores_hex_norm = [_normalizar_hex(h) for h in colores_hex]
        colores_unicos_hex = list(dict.fromkeys(colores_hex_norm))
        indice_por_color = {hex_: i + 1 for i, hex_ in enumerate(colores_unicos_hex)}

        nombre_por_hex = {}
        if nombres_colores and len(nombres_colores) == len(colores_hex_norm):
            for hex_, nombre in zip(colores_hex_norm, nombres_colores):
                nombre_por_hex.setdefault(hex_, nombre)
        etiquetas = [nombre_por_hex.get(hex_, hex_) for hex_ in colores_unicos_hex]
    else:
        colores_hex_norm = None
        colores_unicos_hex = None
        indice_por_color = None
        etiquetas = [f"pieza {i + 1}" for i in range(len(piezas))]

    partes_vertices = []
    lineas_triangulos = []
    offset = 0
    for i, malla in enumerate(piezas):
        indice_extrusor = indice_por_color[colores_hex_norm[i]] if colores_hex_norm else i + 1
        paint_color = _paint_color_code(indice_extrusor)
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
        if colores_unicos_hex:
            z.writestr("Metadata/project_settings.config", _project_config_json(colores_unicos_hex))

    return {
        "triangulos": len(lineas_triangulos),
        "colores_unicos": len(colores_unicos_hex) if colores_unicos_hex else len(piezas),
        "aviso": _aviso_limite_colores(etiquetas),
    }
