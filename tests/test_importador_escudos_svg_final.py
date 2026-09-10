#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_importador_escudos_svg_final.py
------------------
Red de regresión para el Importador de Escudos -- Parte E: construcción
del SVG final. ESTA ES LA MILESTONE: prueba el pipeline COMPLETO de
punta a punta -- cargar -> separar zonas -> detectar huecos -> asignar
color default -> vectorizar -> escribir SVG -> RELEER con el lector
real del Topper (`core.svg_import.svg_a_poligonos_por_color`, no un
mock) -- confirmando que el ida y vuelta cierra con apilado ~0 y que
los huecos (River) aparecen con su color default.

No usa pytest (ver AGENTS.md "Testing") -- funciones `test_*` con
`assert` simple, corribles con
`python tests/test_importador_escudos_svg_final.py`.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np

from core import importador_escudos as imp
from core import svg_import

_CARPETA_TEST = os.path.dirname(os.path.abspath(__file__))
ESCUDO_UNION = os.path.join(_CARPETA_TEST, "_fixture_escudo_union.svg")
ESCUDO_BOCA = os.path.join(_CARPETA_TEST, "_fixture_escudo_boca.svg")
ESCUDO_RIVER_NEGRO_ROJO = os.path.join(_CARPETA_TEST, "_fixture_escudo_river_negro_rojo.svg")
ESCUDO_UNION_OFICIAL = os.path.join(_CARPETA_TEST, "_fixture_escudo_union_oficial.svg")

# Umbrales HOLGADOS (mismo criterio que C y D): importa "sigue siendo
# ~0", no un decimal exacto.
UMBRAL_APILADO_PCT = 2.0
UMBRAL_DIFERENCIA_COBERTURA_PCT = 10.0


def _pipeline_completo(ruta, carpeta_tmp):
    """cargar -> separar -> huecos -> armar zonas finales -> escribir
    SVG -> releer con el lector REAL del Topper. Devuelve
    (zonas_finales, ancho, alto, leido)."""
    ancho, alto, capas = imp.cargar_escudo(ruta)
    zonas = imp.separar_zonas_excluyentes(capas)
    huecos = imp.detectar_huecos_internos(zonas)
    zonas_finales = imp.armar_zonas_finales(zonas, huecos)

    ruta_svg = os.path.join(carpeta_tmp, os.path.basename(ruta) + "_final.svg")
    imp.escribir_svg(zonas_finales, ancho, alto, ruta_svg)
    leido = svg_import.svg_a_poligonos_por_color(ruta_svg)
    return zonas_finales, ancho, alto, leido


def _apilado_y_diferencia(zonas_finales, ancho, alto, leido):
    """Rasteriza lo releído (con el offset que introduce la doble
    inversión de Y entre `core.importador_escudos` y `core.svg_import`,
    ver el plan de la Parte E) y compara contra las zonas originales."""
    transformar = lambda pt: (pt[0], alto - (pt[1] + alto))
    reconstruidas = [(color, imp._rasterizar_poligono(p, ancho, alto, transformar)) for p, color in leido]

    apilado = 0
    for i in range(len(reconstruidas)):
        for j in range(i + 1, len(reconstruidas)):
            apilado += int((reconstruidas[i][1] & reconstruidas[j][1]).sum())

    union_original = np.zeros((alto, ancho), dtype=bool)
    for _, m in zonas_finales:
        union_original |= m
    union_releida = np.zeros((alto, ancho), dtype=bool)
    for _, m in reconstruidas:
        union_releida |= m

    tinta = int(union_original.sum())
    apilado_pct = 100 * apilado / tinta
    diferencia_pct = 100 * int((union_original ^ union_releida).sum()) / tinta
    return apilado_pct, diferencia_pct, reconstruidas


def test_milestone_river_con_huecos_blanco_presente_y_apilado_bajo():
    """Caso (1), LA MILESTONE: River negro+rojo (7 huecos reales con el
    motor de render, ver `test_importador_escudos_huecos.py`) ->
    pipeline completo -> el SVG releído por el lector REAL del Topper
    tiene una región #ffffff con área ≈ la suma de los 7 huecos, y
    apilado por debajo del umbral."""
    with tempfile.TemporaryDirectory() as carpeta_tmp:
        ancho, alto, capas = imp.cargar_escudo(ESCUDO_RIVER_NEGRO_ROJO)
        zonas = imp.separar_zonas_excluyentes(capas)
        huecos = imp.detectar_huecos_internos(zonas)
        assert len(huecos) == 7, f"este test asume los 7 huecos de River -- salieron {len(huecos)}"
        area_huecos_esperada = sum(int(h.sum()) for h in huecos)

        zonas_finales, ancho, alto, leido = _pipeline_completo(ESCUDO_RIVER_NEGRO_ROJO, carpeta_tmp)
        colores_leidos = [c for _, c in leido]
        assert "#ffffff" in colores_leidos, f"no apareció el blanco de los huecos -- colores leídos: {colores_leidos}"

        apilado_pct, diferencia_pct, reconstruidas = _apilado_y_diferencia(zonas_finales, ancho, alto, leido)
        area_blanco_releida = [m for c, m in reconstruidas if c == "#ffffff"][0].sum()
        print(f"  River: blanco releído={area_blanco_releida}px (esperado ~{area_huecos_esperada}px) "
              f"apilado={apilado_pct:.3f}% diferencia={diferencia_pct:.3f}%")

        diferencia_blanco_pct = 100 * abs(int(area_blanco_releida) - area_huecos_esperada) / area_huecos_esperada
        assert diferencia_blanco_pct < UMBRAL_DIFERENCIA_COBERTURA_PCT, (
            f"área del blanco releído difiere {diferencia_blanco_pct:.1f}% de los huecos originales"
        )
        assert apilado_pct < UMBRAL_APILADO_PCT, f"apilado {apilado_pct:.2f}% >= {UMBRAL_APILADO_PCT}%"
        assert diferencia_pct < UMBRAL_DIFERENCIA_COBERTURA_PCT, f"diferencia {diferencia_pct:.2f}%"


def test_union_y_boca_sin_huecos_siguen_dando_igual_de_bien():
    """Caso (2), control: Unión (limpio y oficial con strokes) y Boca no
    tienen huecos internos -- el paso nuevo (armar_zonas_finales con
    huecos=[]) no debería cambiar nada respecto de vectorizar directo
    las zonas de B (Parte D)."""
    with tempfile.TemporaryDirectory() as carpeta_tmp:
        for nombre, ruta in (("Unión", ESCUDO_UNION), ("Unión oficial", ESCUDO_UNION_OFICIAL), ("Boca", ESCUDO_BOCA)):
            ancho, alto, capas = imp.cargar_escudo(ruta)
            zonas = imp.separar_zonas_excluyentes(capas)
            huecos = imp.detectar_huecos_internos(zonas)
            assert huecos == [], f"{nombre}: este test asume 0 huecos"

            zonas_finales, ancho, alto, leido = _pipeline_completo(ruta, carpeta_tmp)
            assert len(leido) == len(zonas), f"{nombre}: se perdió o sobró una región"

            apilado_pct, diferencia_pct, _ = _apilado_y_diferencia(zonas_finales, ancho, alto, leido)
            print(f"  {nombre}: apilado={apilado_pct:.3f}% diferencia={diferencia_pct:.3f}%")
            assert apilado_pct < UMBRAL_APILADO_PCT, f"{nombre}: apilado {apilado_pct:.2f}%"
            assert diferencia_pct < UMBRAL_DIFERENCIA_COBERTURA_PCT, f"{nombre}: diferencia {diferencia_pct:.2f}%"


def test_comentario_de_trazabilidad_presente_y_no_rompe_la_lectura():
    """El comentario XML de trazabilidad está en el archivo Y
    `svg_a_poligonos_por_color` lo ignora sin problema (ya lo prueban
    los tests de arriba indirectamente, este lo hace explícito)."""
    with tempfile.TemporaryDirectory() as carpeta_tmp:
        ancho, alto, capas = imp.cargar_escudo(ESCUDO_UNION)
        zonas = imp.separar_zonas_excluyentes(capas)
        zonas_finales = imp.armar_zonas_finales(zonas, [])
        ruta_svg = os.path.join(carpeta_tmp, "con_comentario.svg")
        imp.escribir_svg(zonas_finales, ancho, alto, ruta_svg)

        contenido = open(ruta_svg, encoding="utf-8").read()
        assert "<!--" in contenido and "Importador de Escudos" in contenido
        leido = svg_import.svg_a_poligonos_por_color(ruta_svg)
        assert len(leido) == len(zonas_finales)


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
