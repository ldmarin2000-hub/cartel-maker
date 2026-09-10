#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_importador_escudos_huecos.py
------------------
Red de regresión para el Importador de Escudos -- Parte C: detección
de huecos internos (vacío + scipy.ndimage.label + filtro de área, sin
depender de la fusión de colores casi-iguales -- idea 14 aparte).

No usa pytest (ver AGENTS.md "Testing") -- funciones `test_*` con
`assert` simple, corribles con
`python tests/test_importador_escudos_huecos.py`.
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
ESCUDO_RIVER_PNG = os.path.join(_CARPETA_TEST, "_fixture_escudo_river.png")
ESCUDO_RIVER_NEGRO_ROJO = os.path.join(_CARPETA_TEST, "_fixture_escudo_river_negro_rojo.svg")
ESCUDO_UNION_OFICIAL = os.path.join(_CARPETA_TEST, "_fixture_escudo_union_oficial.svg")

# Umbral HOLGADO a propósito -- lo que importa es "7 huecos, todos
# grandes/significativos", no un área exacta que se rompa si el
# rasterizado cambia unos pocos píxeles por una actualización de
# librería. El más chico de los 7 reales medido fue ~430px sobre un
# canvas de ~74000px de tinta (~0.6%) -- pido bastante menos que eso.
AREA_MINIMA_HUECO_SIGNIFICATIVO = 300


def _cargar_zonas(ruta):
    _, _, capas = imp.cargar_escudo(ruta)
    return imp.separar_zonas_excluyentes(capas)


def test_river_negro_rojo_da_7_huecos_internos_grandes():
    """Caso (1) de la distinción: el escudo NO trae el fondo (blanco)
    como forma -- el blanco es el vacío interno encerrado por el anillo
    C-A-R-P. Eran 6 con el motor viejo (rasterizado directo por PIL, sin
    antialiasing, "engordaba" el trazo -- ver el módulo); con el motor
    de render (`resvg_py`, mismo tratamiento raster que un PNG) salió un
    7mo hueco real, TAMBIÉN significativo (por encima del piso de área)
    -- no ruido nuevo, más fidelidad: el trazo ya no se infla y deja ver
    un hueco angosto que antes quedaba tapado."""
    zonas = _cargar_zonas(ESCUDO_RIVER_NEGRO_ROJO)
    huecos = imp.detectar_huecos_internos(zonas)
    assert len(huecos) == 7, f"esperaba 7 huecos internos, salieron {len(huecos)}"
    areas = sorted((int(h.sum()) for h in huecos), reverse=True)
    print("  áreas de los 7 huecos:", areas)
    for area in areas:
        assert area >= AREA_MINIMA_HUECO_SIGNIFICATIVO, (
            f"hueco de {area}px por debajo del piso de 'significativo' ({AREA_MINIMA_HUECO_SIGNIFICATIVO}px)"
        )


def test_river_png_sin_huecos_el_fondo_ya_es_zona():
    """Caso (2): el PNG ya tiene el blanco como su propia zona (más el
    ruido de antialiasing sin fusionar, idea 14 aparte) -- 0 huecos
    internos, el filtro de área descarta las ~205 motitas."""
    zonas = _cargar_zonas(ESCUDO_RIVER_PNG)
    huecos = imp.detectar_huecos_internos(zonas)
    assert huecos == [], f"esperaba 0 huecos, salieron {len(huecos)}"


def test_union_sin_huecos_internos():
    zonas = _cargar_zonas(ESCUDO_UNION)
    huecos = imp.detectar_huecos_internos(zonas)
    assert huecos == [], f"esperaba 0 huecos en Unión, salieron {len(huecos)}"


def test_boca_sin_huecos_internos():
    zonas = _cargar_zonas(ESCUDO_BOCA)
    huecos = imp.detectar_huecos_internos(zonas)
    assert huecos == [], f"esperaba 0 huecos en Boca, salieron {len(huecos)}"


def test_union_oficial_con_strokes_sin_huecos_internos():
    """El escudo OFICIAL (rayas por stroke, no por relleno) tiene que
    dar el mismo resultado que la versión limpia: 0 huecos -- confirma
    que renderizar resuelve bien el stroke ANTES de que huecos entre en
    juego (C ni se entera de cómo se generaron las zonas de B)."""
    zonas = _cargar_zonas(ESCUDO_UNION_OFICIAL)
    huecos = imp.detectar_huecos_internos(zonas)
    assert huecos == [], f"esperaba 0 huecos en Unión oficial, salieron {len(huecos)}"


def test_chequeo_de_sanidad_huecos_no_tocan_zona_ni_borde():
    """Caso (4): para cada hueco detectado (en el único escudo que
    tiene, River negro+rojo) -- (a) no comparte NINGÚN píxel con
    ninguna zona de B (es de verdad "vacío"), y (b) no toca ninguno de
    los 4 bordes del canvas (si tocara, sería "aire", no un hueco
    interno)."""
    zonas = _cargar_zonas(ESCUDO_RIVER_NEGRO_ROJO)
    huecos = imp.detectar_huecos_internos(zonas)
    assert len(huecos) > 0, "este chequeo necesita al menos un hueco real para tener sentido"

    tinta = np.zeros_like(huecos[0])
    for _, mascara in zonas:
        tinta |= mascara

    for i, hueco in enumerate(huecos):
        assert not (hueco & tinta).any(), f"hueco #{i} se solapa con una zona de B"
        toca_borde = hueco[0, :].any() or hueco[-1, :].any() or hueco[:, 0].any() or hueco[:, -1].any()
        assert not toca_borde, f"hueco #{i} toca el borde del canvas -- debería ser 'aire', no interno"


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
