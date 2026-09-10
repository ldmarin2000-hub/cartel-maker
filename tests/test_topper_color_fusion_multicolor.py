#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_topper_color_fusion_multicolor.py
------------------
Red de regresión para 7C-E: asignación de color por sub-pieza y fusión
por color de 2 niveles (casillero × sub-color) en `generar_plano`.

El pedido original: varios escudos que comparten colores reales tienen
que pesar como POCOS filamentos, no uno por escudo -- acá se prueba
específicamente que la fusión por color CRUZA casilleros distintos
(no solo sub-colores dentro del mismo casillero, eso ya lo cubre
7C-A/7C-B a nivel de claves).

No usa pytest (ver AGENTS.md "Testing") -- funciones `test_*` con
`assert` simple, corribles con
`python tests/test_topper_color_fusion_multicolor.py`.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from core import colores
from generators import topper

FUENTE = os.path.join("fonts", "curadas", "Anton.ttf")
_CARPETA_TEST = os.path.dirname(os.path.abspath(__file__))
_DECO_MULTICOLOR_SVG = os.path.join(_CARPETA_TEST, "_fixture_deco_4colores.svg")


def _crear_fixture_svg_4_colores():
    if not os.path.exists(_DECO_MULTICOLOR_SVG):
        with open(_DECO_MULTICOLOR_SVG, "w", encoding="utf-8") as f:
            f.write(
                '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">'
                '<rect x="0" y="0" width="50" height="50" fill="#ff0000"/>'
                '<rect x="50" y="0" width="50" height="50" fill="#00ff00"/>'
                '<rect x="0" y="50" width="50" height="50" fill="#0000ff"/>'
                '<rect x="50" y="50" width="50" height="50" fill="#ffff00"/>'
                "</svg>"
            )
    return _DECO_MULTICOLOR_SVG


def _claves_decoracion_de(dic):
    return sorted(k for k in dic if k == "decoracion" or k.startswith("decoracion_"))


def test_casillero_multicolor_usa_nombre_mas_cercano_del_hex_real():
    """Caso (2): sin `colores_decoracion_extra`, cada sub-pieza de un
    casillero multicolor toma el color de la paleta más cercano a su
    hex real detectado -- no el selector "Color" de siempre."""
    deco_svg = _crear_fixture_svg_4_colores()
    decoraciones = [{"svg": deco_svg, "lado": "Arriba", "tam_mm": 30.0, "multicolor": True}]
    resultado = topper.generar_plano(
        lineas=["Hola"], tamaño_mm=70, fuente=FUENTE, marco="Ninguno",
        decoraciones=decoraciones, tiene_ams=False,
    )
    claves = _claves_decoracion_de(resultado["colores"])
    assert claves == ["decoracion", "decoracion_col2", "decoracion_col3", "decoracion_col4"], claves

    hex_reales = [h for _, h in topper._colores_desde_archivo(deco_svg)]
    esperados = {
        "decoracion": colores.nombre_mas_cercano(hex_reales[0]),
        "decoracion_col2": colores.nombre_mas_cercano(hex_reales[1]),
        "decoracion_col3": colores.nombre_mas_cercano(hex_reales[2]),
        "decoracion_col4": colores.nombre_mas_cercano(hex_reales[3]),
    }
    for clave, nombre_esperado in esperados.items():
        assert resultado["colores"][clave] == nombre_esperado, (
            f"{clave}: esperaba '{nombre_esperado}' (de {hex_reales}), salió '{resultado['colores'][clave]}'"
        )
    # el selector "Color" de siempre (color_decoracion="Dorado" por
    # default) tiene que quedar completamente ignorado para este
    # casillero -- ninguna de las 4 claves debería terminar "Dorado"
    # salvo que la paleta real lo sugiriera (no es el caso acá).
    assert "Dorado" not in esperados.values()


def test_dos_casilleros_multicolor_que_comparten_color_se_fusionan_cruzando_casilleros():
    """Caso (3), EL TEST CLAVE: dos casilleros multicolor, cada uno con
    2 de los 4 colores del mismo SVG (mismos 2 colores reales en
    ambos) -- tienen que fusionarse en una sola región POR COLOR,
    cruzando casilleros (no solo dentro del mismo casillero). Uso solo
    2 colores por casillero (4 sub-piezas en total) para no pisar el
    tope global de 4 que todavía existe (lo saca 7D) -- no es una
    limitación de la fusión en sí."""
    deco_svg = _crear_fixture_svg_4_colores()
    decoraciones = [
        {"svg": deco_svg, "lado": "Arriba", "tam_mm": 20.0, "multicolor": True, "multicolor_indices": [0, 1]},
        {"svg": deco_svg, "lado": "Derecha", "tam_mm": 20.0, "multicolor": True, "multicolor_indices": [0, 1]},
    ]
    espesor_mm = 3.0
    resultado = topper.generar_plano(
        lineas=["Hola"], tamaño_mm=70, fuente=FUENTE, marco="Ninguno",
        decoraciones=decoraciones, tiene_ams=False, espesor_mm=espesor_mm,
    )

    piezas_deco = [p for p in resultado["piezas_color"] if p["clave"] == "decoracion" or p["clave"].startswith("decoracion_")]
    claves_finales = sorted(p["clave"] for p in piezas_deco)
    assert claves_finales == ["decoracion", "decoracion_col2"], (
        f"esperaba que los 4 sub-piezas (2 por casillero) se fusionen en 2 regiones "
        f"(una por color real compartido), salió {claves_finales}"
    )

    # nota: `resultado["colores"]` (a diferencia de `piezas_color`) NO
    # es la fuente de verdad de "qué sobrevivió" -- por diseño, ya desde
    # antes de 7C-E, incluye TODAS las claves posibles con su color
    # asignado aunque su geometría se haya fusionado hacia otra (mismo
    # comportamiento que "texto_2"/"marco_borde" siguen apareciendo ahí
    # con su color aunque se hayan fusionado en "texto"/"marco") -- la
    # prueba real de qué sobrevivió es `piezas_color`, ya verificada
    # arriba con `claves_finales`.

    hex_reales = [h for _, h in topper._colores_desde_archivo(deco_svg)][:2]
    nombres_esperados = {colores.nombre_mas_cercano(h) for h in hex_reales}
    colores_finales = {p["color"] for p in piezas_deco}
    assert colores_finales == nombres_esperados, (colores_finales, nombres_esperados)

    # prueba geométrica de que la fusión de verdad UNIÓ las piezas de
    # los DOS casilleros (no descartó una) -- el área de la región
    # fusionada tiene que ser la SUMA de las dos piezas que la
    # componen (no se superponen: "Arriba" vs "Derecha").
    regiones_crudas, _, _, _ = topper._armar_regiones_plano(
        lineas=["Hola"], tamaño_mm=70, fuente=FUENTE, marco="Ninguno", decoraciones=decoraciones)
    for clave_sobreviviente, clave_del_casillero_2 in (("decoracion", "decoracion_2"), ("decoracion_col2", "decoracion_2_col2")):
        area_esperada = regiones_crudas[clave_sobreviviente].area + regiones_crudas[clave_del_casillero_2].area
        malla = [p for p in resultado["piezas_color"] if p["clave"] == clave_sobreviviente][0]
        import trimesh
        area_real = trimesh.load(malla["ruta_stl"]).volume / espesor_mm
        # tolerancia relativa laxa -- no es un test de precisión
        # geométrica exacta (ver el artefacto de simplify() de 7B),
        # es para confirmar que se sumaron las DOS piezas, no una sola.
        assert area_esperada > 0
        assert abs(area_real - area_esperada) / area_esperada < 0.01, (
            f"{clave_sobreviviente}: área real {area_real:.2f} vs esperada (suma de ambos casilleros) {area_esperada:.2f}"
        )


def test_casillero_de_un_color_mas_uno_multicolor_sin_cruce():
    """Caso (4): un casillero de un solo color (con un color explícito
    que NO coincide con ninguno de los sugeridos por el multicolor) más
    uno multicolor -- cada camino calcula su color de forma
    independiente, sin pisarse."""
    deco_svg = _crear_fixture_svg_4_colores()
    decoraciones = [
        {"svg": deco_svg, "lado": "Izquierda", "tam_mm": 15.0},  # un solo color, sin "multicolor"
        {"svg": deco_svg, "lado": "Arriba", "tam_mm": 20.0, "multicolor": True, "multicolor_indices": [0, 1]},
    ]
    resultado = topper.generar_plano(
        lineas=["Hola"], tamaño_mm=70, fuente=FUENTE, marco="Ninguno",
        decoraciones=decoraciones, color_decoracion="Turquesa", tiene_ams=False,
    )
    claves = _claves_decoracion_de(resultado["colores"])
    assert claves == ["decoracion", "decoracion_2", "decoracion_2_col2"], claves
    assert resultado["colores"]["decoracion"] == "Turquesa", "el casillero de un color debe respetar su selector, sin cruzarse"

    hex_reales = [h for _, h in topper._colores_desde_archivo(deco_svg)][:2]
    assert resultado["colores"]["decoracion_2"] == colores.nombre_mas_cercano(hex_reales[0])
    assert resultado["colores"]["decoracion_2_col2"] == colores.nombre_mas_cercano(hex_reales[1])
    # nada se fusionó -- los 3 colores son distintos entre sí.
    assert len({resultado["colores"][c] for c in claves}) == 3


def test_multicolor_colores_de_la_pagina_reasigna_sin_conocer_claves_internas():
    """7C-F: la vía que usa la página -- `item["multicolor_colores"]",
    una lista de nombres de color en el MISMO orden que
    `multicolor_indices` -- tiene que pisar el color sugerido, sin que
    quien arma `decoraciones` (la página) necesite saber nada sobre
    `_clave_decoracion_independiente` ni el esquema de nombres de
    región. También confirma que dos casilleros con la reasignación
    explícita a un MISMO nombre se fusionan igual que si coincidiera
    por sugerencia (7C-E no distingue el origen del nombre)."""
    deco_svg = _crear_fixture_svg_4_colores()
    decoraciones = [
        {"svg": deco_svg, "lado": "Arriba", "tam_mm": 20.0, "multicolor": True,
         "multicolor_indices": [0, 1], "multicolor_colores": ["Rosa Fluor", "Cian"]},
        {"svg": deco_svg, "lado": "Derecha", "tam_mm": 20.0, "multicolor": True,
         "multicolor_indices": [0, 1], "multicolor_colores": ["Rosa Fluor", "Teal"]},
    ]
    resultado = topper.generar_plano(
        lineas=["Hola"], tamaño_mm=70, fuente=FUENTE, marco="Ninguno",
        decoraciones=decoraciones, tiene_ams=False,
    )
    piezas_deco = [p for p in resultado["piezas_color"] if p["clave"] == "decoracion" or p["clave"].startswith("decoracion_")]
    por_clave = {p["clave"]: p["color"] for p in piezas_deco}

    # "Rosa Fluor" pedido a mano en AMBOS casilleros -> se fusionan
    # (ignorando que el hex real sugeriría "Rojo") -- sobrevive
    # "decoracion" (menor índice).
    assert "decoracion" in por_clave and por_clave["decoracion"] == "Rosa Fluor"
    assert "decoracion_2" not in por_clave, "debería haberse fusionado dentro de 'decoracion'"

    # "Cian" (casillero 0) y "Teal" (casillero 1) NO coinciden -> quedan
    # sueltas, cada una con el nombre pedido a mano.
    assert por_clave.get("decoracion_col2") == "Cian"
    assert por_clave.get("decoracion_2_col2") == "Teal"


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]
    fallas = 0
    for t in tests:
        try:
            t()
            print(f"OK   {t.__name__}")
        except AssertionError as e:
            fallas += 1
            print(f"FALLA {t.__name__}: {e}")
    print()
    if fallas:
        print(f"{fallas} de {len(tests)} tests fallaron.")
        sys.exit(1)
    print(f"Los {len(tests)} tests pasaron.")
