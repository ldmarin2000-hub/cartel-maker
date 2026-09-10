#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_importador_escudos_vectorizacion.py
------------------
Red de regresión para el Importador de Escudos -- Parte D:
vectorización con evenodd (zonas de B -> polígonos shapely con
agujeros reales, vía `core.imagen_import._mascara_a_poligono`).

No usa pytest (ver AGENTS.md "Testing") -- funciones `test_*` con
`assert` simple, corribles con
`python tests/test_importador_escudos_vectorizacion.py`.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np

from core import importador_escudos as imp

_CARPETA_TEST = os.path.dirname(os.path.abspath(__file__))
ESCUDO_UNION = os.path.join(_CARPETA_TEST, "_fixture_escudo_union.svg")
ESCUDO_BOCA = os.path.join(_CARPETA_TEST, "_fixture_escudo_boca.svg")
ESCUDO_RIVER_NEGRO_ROJO = os.path.join(_CARPETA_TEST, "_fixture_escudo_river_negro_rojo.svg")
ESCUDO_UNION_OFICIAL = os.path.join(_CARPETA_TEST, "_fixture_escudo_union_oficial.svg")

# Umbrales HOLGADOS a propósito (mismo criterio que ya usamos en C):
# lo que importa es "sigue siendo ~0", no un decimal exacto que se
# rompa por un cambio de 1px en el rasterizado de una librería.
UMBRAL_APILADO_PCT = 2.0
UMBRAL_DIFERENCIA_COBERTURA_PCT = 10.0


def _ida_y_vuelta(ruta):
    """zonas de B -> vectorizar (D) -> re-rasterizar (reusando el
    rasterizador de A) -- devuelve (apilado_pct, diferencia_pct)."""
    ancho, alto, capas = imp.cargar_escudo(ruta)
    zonas = imp.separar_zonas_excluyentes(capas)
    poligonos = imp.vectorizar_zonas(zonas)

    transformar = lambda pt: (pt[0], alto - pt[1])
    reconstruidas = [(color, imp._rasterizar_poligono(p, ancho, alto, transformar)) for color, p in poligonos]

    apilado = 0
    for i in range(len(reconstruidas)):
        for j in range(i + 1, len(reconstruidas)):
            apilado += int((reconstruidas[i][1] & reconstruidas[j][1]).sum())

    union_original = np.zeros((alto, ancho), dtype=bool)
    for _, m in zonas:
        union_original |= m
    union_reconstruida = np.zeros((alto, ancho), dtype=bool)
    for _, m in reconstruidas:
        union_reconstruida |= m

    area_tinta = int(union_original.sum())
    apilado_pct = 100 * apilado / area_tinta
    diferencia_pct = 100 * int((union_original ^ union_reconstruida).sum()) / area_tinta
    return apilado_pct, diferencia_pct, len(zonas), len(poligonos)


def test_ida_y_vuelta_union_boca_river_apilado_y_cobertura_dentro_de_umbral():
    """Caso (1): los escudos SVG, incluido el OFICIAL de Unión (rayas
    por stroke) -- River.png queda afuera a propósito (no es SVG, no
    ejercita el camino de render)."""
    for nombre, ruta in (
        ("Unión", ESCUDO_UNION),
        ("Unión oficial (strokes)", ESCUDO_UNION_OFICIAL),
        ("Boca", ESCUDO_BOCA),
        ("River negro+rojo", ESCUDO_RIVER_NEGRO_ROJO),
    ):
        apilado_pct, diferencia_pct, n_zonas, n_poligonos = _ida_y_vuelta(ruta)
        print(f"  {nombre}: {n_zonas} zonas -> {n_poligonos} polígonos | "
              f"apilado={apilado_pct:.3f}% diferencia={diferencia_pct:.3f}%")
        assert n_poligonos == n_zonas, f"{nombre}: se perdió una zona entera al vectorizar"
        assert apilado_pct < UMBRAL_APILADO_PCT, f"{nombre}: apilado {apilado_pct:.2f}% >= {UMBRAL_APILADO_PCT}%"
        assert diferencia_pct < UMBRAL_DIFERENCIA_COBERTURA_PCT, (
            f"{nombre}: diferencia de cobertura {diferencia_pct:.2f}% >= {UMBRAL_DIFERENCIA_COBERTURA_PCT}%"
        )


def test_zona_anillo_vectoriza_con_agujero_no_rellena():
    """Caso (2): una zona en forma de anillo (como el borde/marco de un
    escudo) tiene que dar un polígono CON agujero real -- no una unión
    rellena que "tape" el agujero."""
    alto, ancho = 200, 200
    yy, xx = np.mgrid[0:alto, 0:ancho]
    dist = np.sqrt((yy - 100) ** 2 + (xx - 100) ** 2)
    anillo = (dist < 80) & (dist > 40)

    zonas = [("#ff0000", anillo)]
    poligonos = imp.vectorizar_zonas(zonas)
    assert len(poligonos) == 1
    color, poligono = poligonos[0]
    assert color == "#ff0000"
    assert not hasattr(poligono, "geoms"), "una sola pieza no debería salir como MultiPolygon"
    assert len(poligono.interiors) == 1, "el anillo tiene que tener EXACTAMENTE 1 agujero"
    assert abs(poligono.area - int(anillo.sum())) < 5, (
        f"área del polígono ({poligono.area}) debería coincidir con los píxeles del anillo ({anillo.sum()})"
    )


def test_zona_multipieza_da_multipoligono_cada_una_con_sus_agujeros():
    """Caso (b) del plan: una zona con 2 piezas disjuntas -- una anillo
    (con agujero) y una disco sólido (sin agujero) -- tiene que dar un
    MultiPolygon de 2 partes, cada una con la cantidad de agujeros que
    le corresponde (no que se mezclen o se pierda el agujero de una)."""
    alto, ancho = 200, 400
    yy, xx = np.mgrid[0:alto, 0:ancho]
    dist1 = np.sqrt((yy - 100) ** 2 + (xx - 100) ** 2)
    dist2 = np.sqrt((yy - 100) ** 2 + (xx - 300) ** 2)
    mascara = ((dist1 < 60) & (dist1 > 30)) | (dist2 < 50)

    zonas = [("#00ff00", mascara)]
    poligonos = imp.vectorizar_zonas(zonas)
    color, poligono = poligonos[0]
    assert hasattr(poligono, "geoms"), "2 piezas disjuntas deberían dar MultiPolygon"
    partes = list(poligono.geoms)
    assert len(partes) == 2
    interiors_por_parte = sorted(len(p.interiors) for p in partes)
    assert interiors_por_parte == [0, 1], f"esperaba una pieza sin agujero y otra con 1, salió {interiors_por_parte}"


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
