#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_decoraciones_multicolor.py
------------------
Red de regresión para `core/decoraciones.py` -- Parte 1 del ícono "a
color" del Llavero: separar un SVG/imagen en regiones por color real
(`formas_por_color_desde_archivo`/`detectar_colores_archivo`) y armar
la forma multicolor centrada/escalada (`forma_multicolor_desde_archivo`),
mismo motor que ya usa `generators/topper.py` para su decoración
multicolor, ahora accesible sin importar de otro generador.

No usa pytest (ver AGENTS.md "Testing") -- funciones `test_*` con
`assert` simple, corribles con
`python tests/test_decoraciones_multicolor.py`.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from core import decoraciones

_CARPETA_TEST = os.path.dirname(os.path.abspath(__file__))
FIXTURE_4_COLORES = os.path.join(_CARPETA_TEST, "_fixture_deco_4colores.svg")
FIXTURE_ESCUDO_UNION = os.path.join(_CARPETA_TEST, "_fixture_escudo_union.svg")
FIXTURE_ESCUDO_RIVER_PNG = os.path.join(_CARPETA_TEST, "_fixture_escudo_river.png")


def test_formas_por_color_svg_da_los_4_colores_reales():
    """El SVG sintético (4 cuadrantes de 50x50, un color puro cada uno)
    tiene que dar EXACTAMENTE 4 regiones, con los colores declarados en
    el archivo (SVG: colores exactos, no cuantizados) y área igual
    entre sí (2500 cada una, mismo tamaño de cuadrante)."""
    crudos = decoraciones.formas_por_color_desde_archivo(FIXTURE_4_COLORES)
    assert len(crudos) == 4
    colores_encontrados = {c for _, c in crudos}
    assert colores_encontrados == {"#ff0000", "#00ff00", "#0000ff", "#ffff00"}
    for poligono, _ in crudos:
        assert abs(poligono.area - 2500) < 1, poligono.area


def test_formas_por_color_imagen_rasterizada_dispatch_por_extension():
    """Con un PNG (no SVG), tiene que dispatchear a
    `imagen_import.imagen_a_poligonos_por_color` en vez del camino SVG
    -- River da varios colores reales (blanco/negro/rojo, más ruido de
    antialiasing sin fusionar, ya documentado en otros tests)."""
    crudos = decoraciones.formas_por_color_desde_archivo(FIXTURE_ESCUDO_RIVER_PNG)
    assert len(crudos) > 0
    for poligono, color_hex in crudos:
        assert color_hex.startswith("#") and len(color_hex) == 7
        assert poligono.area > 0


def test_detectar_colores_archivo_da_fracciones_que_suman_1():
    detectados = decoraciones.detectar_colores_archivo(FIXTURE_4_COLORES)
    assert len(detectados) == 4
    fracciones = [frac for _, frac in detectados]
    assert abs(sum(fracciones) - 1.0) < 1e-6
    # los 4 cuadrantes son iguales -- todas las fracciones ~25%
    for frac in fracciones:
        assert abs(frac - 0.25) < 0.01
    # ordenado de mayor a menor área (acá son todas iguales, pero el
    # contrato es "no ascendente" -- lo confirmamos igual)
    assert fracciones == sorted(fracciones, reverse=True)


def test_detectar_colores_archivo_no_rompe_con_archivo_invalido():
    assert decoraciones.detectar_colores_archivo("no_existe.svg") == []


def test_forma_multicolor_conserva_las_4_piezas_centradas_y_escaladas():
    """tam=10 -> lado mayor final tiene que ser 2*tam=20 (mismo criterio
    que forma_desde_svg/forma_desde_imagen). Centrado en el origen: el
    cuadrado combinado (100x100 crudo, ya simétrico) tiene que quedar
    con bounds simétricos alrededor de (0,0)."""
    piezas = decoraciones.forma_multicolor_desde_archivo(FIXTURE_4_COLORES, tam=10)
    assert piezas is not None and len(piezas) == 4

    from shapely.ops import unary_union
    todas = unary_union([p for p, _ in piezas])
    minx, miny, maxx, maxy = todas.bounds
    assert abs((maxx - minx) - 20) < 0.01
    assert abs((maxy - miny) - 20) < 0.01
    assert abs((minx + maxx) / 2) < 0.01, "no quedó centrado en X"
    assert abs((miny + maxy) / 2) < 0.01, "no quedó centrado en Y"

    # las 4 piezas se achican todas por el MISMO factor -- siguen siendo
    # iguales entre sí (ninguna quedó desproporcionada respecto de las otras)
    areas = [p.area for p, _ in piezas]
    for area in areas:
        assert abs(area - areas[0]) < 0.01


def test_forma_multicolor_con_indices_seleccionados_filtra_y_recentra():
    """Si se seleccionan solo 2 de los 4 cuadrantes (los de la mitad
    izquierda, ej. rojo y azul), el resultado tiene que tener solo esas
    2 piezas -- Y recentrarse/reescalar sobre la UNIÓN de esas 2 nomás,
    no sobre las 4 originales (mismo criterio que ya usa
    `generators/topper.py`: un color descartado no debe descuadrar el
    tamaño/centro del resto)."""
    crudos = decoraciones.formas_por_color_desde_archivo(FIXTURE_4_COLORES)
    colores_por_indice = {i: c for i, (_, c) in enumerate(crudos)}
    indices_izquierda = [i for i, c in colores_por_indice.items() if c in ("#ff0000", "#0000ff")]
    assert len(indices_izquierda) == 2

    piezas = decoraciones.forma_multicolor_desde_archivo(
        FIXTURE_4_COLORES, tam=10, indices_seleccionados=indices_izquierda)
    assert len(piezas) == 2
    assert {c for _, c in piezas} == {"#ff0000", "#0000ff"}

    from shapely.ops import unary_union
    todas = unary_union([p for p, _ in piezas])
    minx, miny, maxx, maxy = todas.bounds
    # la mitad izquierda original (50x100 -- más angosta que alta) escalada a
    # lado mayor 2*tam=20 tiene que dar un rectángulo de 10x20, no 20x20
    assert abs((maxx - minx) - 10) < 0.01, (maxx - minx)
    assert abs((maxy - miny) - 20) < 0.01, (maxy - miny)


def test_forma_multicolor_indices_vacio_o_invalido_da_none():
    assert decoraciones.forma_multicolor_desde_archivo(FIXTURE_4_COLORES, tam=10, indices_seleccionados=[]) is None
    assert decoraciones.forma_multicolor_desde_archivo(FIXTURE_4_COLORES, tam=10, indices_seleccionados=[99]) is None


def test_forma_multicolor_svg_sin_formas_da_none():
    """Igual que `forma_desde_svg`: un archivo que EXISTE pero no tiene
    ninguna forma con área da `None`, no una excepción -- la
    inexistencia del archivo en sí queda afuera de este contrato (se
    chequea upstream, en `generar()`/`preview_rapido()`, igual que ya
    hace el llavero para SVG/imagen de un solo color)."""
    import tempfile
    with tempfile.TemporaryDirectory() as carpeta_tmp:
        ruta_vacia = os.path.join(carpeta_tmp, "vacio.svg")
        with open(ruta_vacia, "w", encoding="utf-8") as f:
            f.write('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"></svg>')
        assert decoraciones.forma_multicolor_desde_archivo(ruta_vacia, tam=10) is None


def test_forma_multicolor_escudo_real_da_2_colores_bien_proporcionados():
    """Sanity con un escudo real (Unión limpio, rojo/blanco ~50/50) --
    2 piezas, proporción de área similar entre sí (dentro de un margen
    holgado, no exacto, para no atarse a un rasterizado específico)."""
    piezas = decoraciones.forma_multicolor_desde_archivo(FIXTURE_ESCUDO_UNION, tam=10)
    assert piezas is not None
    assert len(piezas) == 2
    areas = sorted((p.area for p, _ in piezas), reverse=True)
    proporcion = areas[1] / areas[0]
    # holgado a propósito -- lo que importa es "ningún color se comió casi
    # todo el área" (svg_a_poligonos_por_color no es el motor de render de
    # el Importador de Escudos, puede no dar exactamente 50/50 en Unión)
    assert proporcion > 0.4, f"proporción {proporcion:.2f} -- se esperaba algo cercano a 50/50 (Unión rojo/blanco)"


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
