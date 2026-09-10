#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_importador_escudos_entrada.py
------------------
Red de regresión para el Importador de Escudos -- Parte A: entrada
unificada (SVG/PNG -> raster + capas YA limpias, ver
`core.importador_escudos.limpiar_antialiasing`). Usa los 3 escudos
reales (Unión, Boca en SVG; River en PNG) con los que ya se verificó
a mano el pipeline.

Desde el cambio de motor (renderizar el SVG con `resvg_py` en vez de
interpretarlo forma por forma con `svgelements`), esta Parte A ya NO
preserva el z-order de documento ni entrega una capa por forma vectorial
-- entrega baldes de color YA cuantizados y limpios, igual que un PNG.
Los tests que dependían de eso (orden de documento, capa 1-a-1 con
pieza vectorial) se sacaron o reescribieron -- ver
`test_importador_escudos_svg_final.py`/`_huecos.py` para las otras
piezas de esa migración.

No usa pytest (ver AGENTS.md "Testing") -- funciones `test_*` con
`assert` simple, corribles con
`python tests/test_importador_escudos_entrada.py`.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np

from core import importador_escudos as imp
from core import imagen_import

_CARPETA_TEST = os.path.dirname(os.path.abspath(__file__))
ESCUDO_UNION = os.path.join(_CARPETA_TEST, "_fixture_escudo_union.svg")
ESCUDO_BOCA = os.path.join(_CARPETA_TEST, "_fixture_escudo_boca.svg")
ESCUDO_RIVER = os.path.join(_CARPETA_TEST, "_fixture_escudo_river.png")
ESCUDO_UNION_OFICIAL = os.path.join(_CARPETA_TEST, "_fixture_escudo_union_oficial.svg")


def test_los_3_escudos_reales_cargan_sin_excepciones_con_capas_no_vacias():
    for ruta in (ESCUDO_UNION, ESCUDO_BOCA, ESCUDO_RIVER):
        ancho_px, alto_px, capas = imp.cargar_escudo(ruta)
        assert ancho_px > 0 and alto_px > 0, ruta
        assert len(capas) > 0, f"{ruta}: no se detectó ninguna capa"
        for color_hex, mascara in capas:
            assert color_hex.startswith("#") and len(color_hex) == 7, color_hex
            assert mascara.shape == (alto_px, ancho_px), (ruta, mascara.shape, (alto_px, ancho_px))
            assert mascara.any(), f"{ruta}: una capa ({color_hex}) quedó con máscara vacía"


def test_canvas_normalizado_al_lado_mayor_500px():
    for ruta in (ESCUDO_UNION, ESCUDO_BOCA, ESCUDO_RIVER):
        ancho_px, alto_px, _ = imp.cargar_escudo(ruta)
        assert max(ancho_px, alto_px) == imp.TAMANO_TRABAJO_PX, (ruta, ancho_px, alto_px)


def test_limpieza_de_antialiasing_reduce_baldes_sin_perder_ni_duplicar_tinta():
    """Reemplaza al viejo test de "capas == baldes cuantizados 1 a 1":
    desde que `cargar_escudo` aplica `limpiar_antialiasing` (fusión de
    baldes casi-iguales + reasignación espacial de baldes dudosos), la
    cantidad de capas finales es MENOR o igual a la cantidad de baldes
    crudos que cuantiza `_preparar_capas_color` (nunca mayor -- limpiar
    solo fusiona/reasigna, no puede inventar un balde nuevo), y ningún
    píxel de tinta se pierde en el camino (los únicos que se descartan
    son los que ya caían por debajo del área mínima ANTES de limpiar,
    igual que antes del cambio de motor)."""
    for ruta in (ESCUDO_UNION, ESCUDO_BOCA, ESCUDO_RIVER, ESCUDO_UNION_OFICIAL):
        fuente = imp._renderizar_svg(ruta) if imp._es_svg(ruta) else ruta
        alto_px, ancho_px, indices, paleta, mascara_valida, area_minima = imagen_import._preparar_capas_color(
            fuente, imp.TAMANO_TRABAJO_PX, imagen_import.COLORES_DETECCION_DEFAULT)
        crudas = [
            idx for idx in set(indices[mascara_valida].tolist())
            if int(((indices == idx) & mascara_valida).sum()) >= area_minima
        ]
        area_cruda_total = sum(int(((indices == idx) & mascara_valida).sum()) for idx in crudas)

        _, _, capas = imp.cargar_escudo(ruta)
        area_limpia_total = sum(int(m.sum()) for _, m in capas)

        assert len(capas) <= len(crudas), (ruta, len(capas), len(crudas))
        assert area_limpia_total == area_cruda_total, (
            f"{ruta}: la limpieza de antialiasing perdió o duplicó tinta -- "
            f"cruda={area_cruda_total}px limpia={area_limpia_total}px"
        )
        for i in range(len(capas)):
            for j in range(i + 1, len(capas)):
                assert not (capas[i][1] & capas[j][1]).any(), f"{ruta}: capas '{capas[i][0]}' y '{capas[j][0]}' se solapan"


def test_2_colores_reales_en_los_4_escudos_con_antialiasing_fuerte():
    """El caso concreto que motivó el cambio de motor: Unión oficial
    (rayas por STROKE) y Boca (con el color de sombra `#F6BB60` que
    queda tapado al renderizar) tienen que dar exactamente 2 colores
    limpios cada uno -- no un balde de sombra ni una decena de tonos de
    borde por antialiasing. Confirma además que Unión oficial (con
    strokes) da la MISMA proporción rojo/blanco que Unión limpio (sin
    strokes, relleno puro) -- prueba de que renderizar resuelve bien el
    caso que `svgelements` no podía leer."""
    TOLERANCIA_PROPORCION_PCT = 3.0

    def _proporciones(ruta):
        _, _, capas = imp.cargar_escudo(ruta)
        assert len(capas) == 2, (ruta, [c for c, _ in capas])
        total = sum(int(m.sum()) for _, m in capas)
        return {color: 100 * int(m.sum()) / total for color, m in capas}

    prop_limpio = _proporciones(ESCUDO_UNION)
    prop_oficial = _proporciones(ESCUDO_UNION_OFICIAL)
    print(f"  Unión limpio: {prop_limpio}")
    print(f"  Unión oficial (strokes): {prop_oficial}")
    for color in prop_limpio:
        assert color in prop_oficial, f"color {color} de Unión limpio no aparece en Unión oficial"
        diferencia = abs(prop_limpio[color] - prop_oficial[color])
        assert diferencia < TOLERANCIA_PROPORCION_PCT, (
            f"proporción de {color} difiere {diferencia:.1f}pp entre Unión limpio y oficial"
        )

    prop_boca = _proporciones(ESCUDO_BOCA)
    print(f"  Boca: {prop_boca}")
    assert "#f6bb60" not in [c.lower() for c in prop_boca], "el color de sombra de Boca no debería sobrevivir"


def test_detalle_chico_desconectado_sobrevive_al_render_y_downscale():
    """El pedido de fondo del viejo test de "letras internas chicas"
    (una letra/número no puede perderse al pasar de vector a raster),
    adaptado al nuevo pipeline: en un escudo real, una letra interna
    comparte el color de una de las 2 zonas principales (no es su
    propio balde -- confirmado por `test_2_colores_reales...` de
    arriba, los 4 escudos reales dan exactamente 2 colores pese a tener
    letras internas) -- así que el riesgo real no es que el umbral de
    confianza se la coma (ya tiene un balde grande del mismo color),
    sino que se le PIERDA GEOMETRÍA al bajar de la resolución de
    render (2000px) a la de trabajo (500px). Se arma un SVG sintético
    con un fondo grande y un detalle chico DESCONECTADO del mismo color
    (como una letra sola, lejos del resto) y se confirma que sigue
    apareciendo como su propio componente conexo (`scipy.ndimage.label`)
    con un área cercana a la esperada -- no fusionado a la nada ni
    encogido a un puñado de píxeles."""
    import tempfile

    from scipy import ndimage

    ANCHO_DETALLE = 30  # ~0.36% del canvas de 500x500 -- justo por encima del piso de
    # área mínima (`imagen_import.AREA_MINIMA_FRACCION` = 0.3%), para que sobrevivir o
    # no dependa de la fidelidad del render+downscale, no de ese piso.
    AREA_DETALLE_ESPERADA = ANCHO_DETALLE * ANCHO_DETALLE

    svg_sintetico = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 500">'
        '<rect x="0" y="0" width="500" height="500" fill="#1f5fa8"/>'
        '<rect x="20" y="20" width="200" height="200" fill="#f4c430"/>'
        f'<rect x="440" y="440" width="{ANCHO_DETALLE}" height="{ANCHO_DETALLE}" fill="#f4c430"/>'
        '</svg>'
    )
    with tempfile.TemporaryDirectory() as carpeta_tmp:
        ruta = os.path.join(carpeta_tmp, "sintetico.svg")
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(svg_sintetico)

        _, _, capas = imp.cargar_escudo(ruta)
        mascara_amarilla = dict(capas).get("#f4c430")
        assert mascara_amarilla is not None, f"el amarillo desapareció -- colores: {[c for c, _ in capas]}"

        etiquetas, n = ndimage.label(mascara_amarilla)
        areas = sorted((int((etiquetas == lbl).sum()) for lbl in range(1, n + 1)), reverse=True)
        print(f"  componentes amarillos: {areas} (detalle esperado ~{AREA_DETALLE_ESPERADA}px)")
        assert n == 2, f"esperaba 2 componentes conexos (rect grande + detalle chico), salieron {n}: {areas}"

        area_detalle_real = areas[-1]
        diferencia_relativa = abs(area_detalle_real - AREA_DETALLE_ESPERADA) / AREA_DETALLE_ESPERADA
        assert diferencia_relativa < 0.30, (
            f"detalle chico sobrevivió con {area_detalle_real}px vs esperado ~{AREA_DETALLE_ESPERADA}px "
            f"({diferencia_relativa*100:.1f}% de diferencia)"
        )


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
