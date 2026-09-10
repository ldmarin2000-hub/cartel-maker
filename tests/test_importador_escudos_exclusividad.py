#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_importador_escudos_exclusividad.py
------------------
Red de regresión para el Importador de Escudos -- Parte B: separación
excluyente por zonas (z-order para SVG, no-op para PNG) + agrupar por
color DESPUÉS de resolver exclusividad.

No usa pytest (ver AGENTS.md "Testing") -- funciones `test_*` con
`assert` simple, corribles con
`python tests/test_importador_escudos_exclusividad.py`.
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
ESCUDO_RIVER = os.path.join(_CARPETA_TEST, "_fixture_escudo_river.png")

ESCUDOS_REALES = (ESCUDO_UNION, ESCUDO_BOCA, ESCUDO_RIVER)


def test_solapamiento_cero_entre_zonas_finales():
    """Caso (1): ningún par de zonas finales comparte un píxel, en los
    3 escudos reales."""
    for ruta in ESCUDOS_REALES:
        _, _, capas = imp.cargar_escudo(ruta)
        zonas = imp.separar_zonas_excluyentes(capas)
        assert len(zonas) > 0, ruta
        for i in range(len(zonas)):
            for j in range(i + 1, len(zonas)):
                solapado = int((zonas[i][1] & zonas[j][1]).sum())
                assert solapado == 0, (
                    f"{ruta}: zonas '{zonas[i][0]}' y '{zonas[j][0]}' se solapan en {solapado} píxeles"
                )


def test_cobertura_100_por_ciento():
    """Caso (2): la unión de TODAS las zonas finales es byte-idéntica a
    la unión de TODAS las capas originales de la Parte A -- ningún
    píxel se pierde al resolver exclusividad."""
    for ruta in ESCUDOS_REALES:
        ancho_px, alto_px, capas = imp.cargar_escudo(ruta)
        zonas = imp.separar_zonas_excluyentes(capas)

        union_original = np.zeros((alto_px, ancho_px), dtype=bool)
        for _, mascara in capas:
            union_original |= mascara
        union_final = np.zeros((alto_px, ancho_px), dtype=bool)
        for _, mascara in zonas:
            union_final |= mascara

        assert np.array_equal(union_original, union_final), (
            f"{ruta}: la cobertura de las zonas finales no coincide con la original "
            f"(original={union_original.sum()}px, final={union_final.sum()}px)"
        )


def test_png_es_no_op_byte_identico():
    """Caso (3): para PNG (River), cada máscara EXCLUSIVA (antes de
    agrupar por color) es byte-idéntica a su máscara original de la
    Parte A -- no una aproximación, un no-op exacto, ya que un PNG
    cuantizado es exclusivo por construcción."""
    _, _, capas = imp.cargar_escudo(ESCUDO_RIVER)
    exclusivas = imp._resolver_exclusividad(capas)
    assert len(exclusivas) == len(capas)
    for (color_orig, mascara_orig), (color_excl, mascara_excl) in zip(capas, exclusivas):
        assert color_orig == color_excl
        assert np.array_equal(mascara_orig, mascara_excl), (
            f"River: la capa '{color_orig}' cambió al resolver exclusividad -- "
            f"debería ser un no-op exacto para PNG"
        )


def test_caso_sintetico_rojo_blanco_rojo_agrupar_despues_da_el_mordisco_correcto():
    """Caso (4): el test que prueba el RAZONAMIENTO de (c), no solo el
    resultado. 3 capas sintéticas en z-order (abajo -> arriba):
      0. rojo grande (todo el canvas)
      1. blanco (tapa la mitad IZQUIERDA del rojo)
      2. rojo chico (arriba de todo, DENTRO de la mitad izquierda que
         tapa el blanco -- clave: tiene que solaparse en el espacio con
         el blanco para que el bug de "agrupar antes" se note)

    Si se agrupara por color ANTES de resolver exclusividad (mal, lo
    que NO hace `separar_zonas_excluyentes`), el rojo chico se fundiría
    con el rojo grande en una sola forma ANCLADA en la posición de
    ABAJO -- perdiendo el hecho de que en realidad está arriba de todo
    -- y el blanco se comería también el pedacito del rojo chico.
    Agrupando DESPUÉS (lo que sí hace), el resultado correcto es: el
    rojo chico sobrevive ENTERO (nada por encima de él) y el blanco
    pierde justo ese pedacito (el rojo chico está por encima del
    blanco)."""
    alto, ancho = 100, 100
    rojo_grande = np.zeros((alto, ancho), dtype=bool)
    rojo_grande[:, :] = True  # todo el canvas

    blanco = np.zeros((alto, ancho), dtype=bool)
    blanco[:, :50] = True  # mitad izquierda

    rojo_chico = np.zeros((alto, ancho), dtype=bool)
    rojo_chico[0:20, 0:20] = True  # esquina superior IZQUIERDA -- DENTRO de la mitad que tapa el blanco

    capas = [("#ff0000", rojo_grande), ("#ffffff", blanco), ("#ff0000", rojo_chico)]
    zonas = imp.separar_zonas_excluyentes(capas)

    por_color = {color: mascara for color, mascara in zonas}
    assert set(por_color.keys()) == {"#ff0000", "#ffffff"}, por_color.keys()

    blanco_esperado = np.zeros((alto, ancho), dtype=bool)
    blanco_esperado[:, :50] = True
    blanco_esperado[0:20, 0:20] = False  # el rojo chico (encima) le come justo ese pedacito
    assert np.array_equal(por_color["#ffffff"], blanco_esperado), "el blanco debería perder el pedacito que tapa el rojo chico, ni más ni menos"

    rojo_esperado = np.zeros((alto, ancho), dtype=bool)
    rojo_esperado[:, 50:] = True  # el mordisco: el rojo grande pierde toda la mitad izquierda (tapada por el blanco)
    rojo_esperado[0:20, 0:20] = True  # + el rojo chico sobrevive ENTERO (nada por encima de él)
    assert np.array_equal(por_color["#ff0000"], rojo_esperado), "el rojo final no tiene el mordisco correcto del blanco"

    # y la prueba de que el ORDEN importa: agrupar por color ANTES de
    # resolver exclusividad da un resultado DISTINTO (peor) -- lo
    # armamos a mano para confirmar que de verdad son distintos.
    rojo_combinado_antes = rojo_grande | rojo_chico  # "mal": unir los dos rojos ya, sin exclusividad
    exclusividad_mala = imp._resolver_exclusividad([("#ff0000", rojo_combinado_antes), ("#ffffff", blanco)])
    rojo_mal = dict(exclusividad_mala)["#ff0000"]
    assert not np.array_equal(rojo_mal, por_color["#ff0000"]), (
        "agrupar antes de resolver exclusividad debería dar un resultado DISTINTO "
        "(y peor) que agrupar después -- si dan igual, el caso de prueba no sirve"
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
