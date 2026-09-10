#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_importador_escudos_asignacion_huecos.py
------------------
Red de regresión para el Importador de Escudos -- Parte G: asignación
de color (o "calado", sin filamento) a cada hueco interno, vía los
parámetros OPCIONALES nuevos de `armar_zonas_finales` (Parte E) y
`componer_preview_rgb` (preview F) -- `colores_por_hueco`/`colores_huecos`.

Dos frentes a cubrir, ambos delicados porque son cambios ADITIVOS a
funciones que ya tenían tests propios (Parte E/F no pueden notar el
cambio si nadie les pasa el parámetro nuevo):
1. Compatibilidad hacia atrás: sin el parámetro nuevo, byte-idéntico a
   como se comportaban antes de esta Parte.
2. El comportamiento nuevo: color por hueco + calado excluye el hueco
   de las zonas/del preview (no lo pinta con NINGÚN color real).

No usa pytest (ver AGENTS.md "Testing") -- funciones `test_*` con
`assert` simple, corribles con
`python tests/test_importador_escudos_asignacion_huecos.py`.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np

from core import colores as colores_mod
from core import importador_escudos as imp
from core import svg_import

_CARPETA_TEST = os.path.dirname(os.path.abspath(__file__))
ESCUDO_RIVER_NEGRO_ROJO = os.path.join(_CARPETA_TEST, "_fixture_escudo_river_negro_rojo.svg")


def _cargar_river_con_huecos():
    ancho, alto, capas = imp.cargar_escudo(ESCUDO_RIVER_NEGRO_ROJO)
    zonas = imp.separar_zonas_excluyentes(capas)
    huecos = imp.detectar_huecos_internos(zonas)
    assert len(huecos) == 7, f"este test asume los 7 huecos de River -- salieron {len(huecos)}"
    return ancho, alto, zonas, huecos


def test_armar_zonas_finales_sin_el_parametro_nuevo_es_byte_identico_a_antes():
    """Caso (1): `armar_zonas_finales(zonas, huecos)` sin
    `colores_por_hueco` tiene que dar EXACTAMENTE lo mismo que antes de
    la Parte G -- lo comparo a mano contra el cálculo directo con
    `color_hueco_default` uniforme (lo que hacía el código viejo)."""
    _, _, zonas, huecos = _cargar_river_con_huecos()

    resultado_nuevo = imp.armar_zonas_finales(zonas, huecos)
    esperado_viejo = imp.agrupar_por_color(list(zonas) + [(imp.COLOR_HUECO_DEFAULT, h) for h in huecos])

    assert [c for c, _ in resultado_nuevo] == [c for c, _ in esperado_viejo]
    for (c1, m1), (c2, m2) in zip(resultado_nuevo, esperado_viejo):
        assert c1 == c2
        assert np.array_equal(m1, m2), f"máscara de '{c1}' difiere sin colores_por_hueco"


def test_armar_zonas_finales_con_colores_por_hueco_mixto_y_calado():
    """Caso (2): 7 huecos de River, 3 colores reales distintos + 2
    calados -- las zonas finales tienen que reflejar exactamente eso:
    los calados NO aparecen en ninguna zona (ni la suya propia ni
    fusionados a otra), y los reales sí, agrupados por color si
    coinciden entre sí o con una zona de B."""
    _, _, zonas, huecos = _cargar_river_con_huecos()

    # 2 al rojo (ya existe como zona de B -- deberían fusionarse ahí),
    # 3 a un azul nuevo, 2 a calado (None).
    colores_por_hueco = ["#ed1c24", "#ed1c24", "#1f5fa8", "#1f5fa8", "#1f5fa8", None, None]
    huecos_calados = [huecos[5], huecos[6]]
    area_calados = sum(int(h.sum()) for h in huecos_calados)

    zonas_finales = imp.armar_zonas_finales(zonas, huecos, colores_por_hueco=colores_por_hueco)
    por_color = dict(zonas_finales)

    assert "#1f5fa8" in por_color, "el color nuevo asignado a 3 huecos no aparece"
    area_azul_esperada = sum(int(huecos[i].sum()) for i in (2, 3, 4))
    assert int(por_color["#1f5fa8"].sum()) == area_azul_esperada

    area_rojo_zona_b = int(dict(zonas)["#ed1c24"].sum())
    area_rojo_huecos = sum(int(huecos[i].sum()) for i in (0, 1))
    assert int(por_color["#ed1c24"].sum()) == area_rojo_zona_b + area_rojo_huecos, (
        "el rojo de los 2 huecos asignados a #ed1c24 debería fusionarse con la zona de B del mismo color"
    )

    tinta_total_final = sum(int(m.sum()) for _, m in zonas_finales)
    tinta_total_zonas_b = sum(int(m.sum()) for _, m in zonas)
    area_huecos_reales_asignados = sum(int(huecos[i].sum()) for i in range(5))
    assert tinta_total_final == tinta_total_zonas_b + area_huecos_reales_asignados, (
        "el total de tinta final no cuadra -- ¿algún calado se coló como zona, o se perdió un hueco real?"
    )
    for _, mascara in zonas_finales:
        for hueco_calado in huecos_calados:
            assert not (mascara & hueco_calado).any(), "un hueco calado apareció pintado en alguna zona final"
    print(f"  área calada (excluida): {area_calados}px de {sum(int(h.sum()) for h in huecos)}px totales de huecos")


def test_armar_zonas_finales_valida_largo_de_colores_por_hueco():
    """Sanity: pasar una lista de largo distinto al de `huecos` tiene
    que fallar fuerte (AssertionError), no ignorar en silencio ni
    reventar más abajo con un error confuso de índices."""
    _, _, zonas, huecos = _cargar_river_con_huecos()
    try:
        imp.armar_zonas_finales(zonas, huecos, colores_por_hueco=["#ffffff"])
        assert False, "debería haber fallado con largos distintos"
    except AssertionError:
        pass


def test_componer_preview_sin_el_parametro_nuevo_es_byte_identico_a_antes():
    """Caso (1) del lado del preview: sin `colores_huecos`, magenta
    uniforme -- el comportamiento de F, sin cambios."""
    ancho, alto, zonas, huecos = _cargar_river_con_huecos()
    preview_nuevo = imp.componer_preview_rgb(zonas, ancho, alto, huecos)

    esperado = np.zeros((alto, ancho, 3), dtype=np.uint8)
    esperado[:, :] = colores_mod._rgb(imp.COLOR_FONDO_PREVIEW)
    for color_hex, mascara in zonas:
        esperado[mascara] = colores_mod._rgb(color_hex)
    for hueco in huecos:
        esperado[hueco] = colores_mod._rgb(imp.COLOR_HUECO_PREVIEW)

    assert np.array_equal(preview_nuevo, esperado)


def test_componer_preview_con_colores_huecos_pinta_cada_uno_y_calado_como_fondo():
    """Caso (2) del lado del preview: cada hueco con su color asignado,
    y un calado pintado igual que el FONDO (ni magenta ni un filamento)
    -- así en pantalla "se ve la torta" en vez de un color inventado."""
    ancho, alto, zonas, huecos = _cargar_river_con_huecos()
    colores_huecos = ["#1f5fa8"] * 6 + [None]

    preview = imp.componer_preview_rgb(zonas, ancho, alto, huecos, colores_huecos)

    for hueco in huecos[:6]:
        assert np.array_equal(preview[hueco], np.tile(colores_mod._rgb("#1f5fa8"), (int(hueco.sum()), 1))), (
            "un hueco con color asignado no se pintó con ese color"
        )
    hueco_calado = huecos[6]
    assert np.array_equal(preview[hueco_calado], np.tile(colores_mod._rgb(imp.COLOR_FONDO_PREVIEW), (int(hueco_calado.sum()), 1))), (
        "el hueco calado debería pintarse igual que el fondo, no con magenta ni un color real"
    )
    # ningún píxel de hueco quedó en magenta (ni el calado ni los asignados)
    magenta = np.array(colores_mod._rgb(imp.COLOR_HUECO_PREVIEW))
    for hueco in huecos:
        assert not np.all(preview[hueco] == magenta, axis=-1).any(), "quedó un hueco en magenta pese a tener colores_huecos"


def test_pipeline_completo_g_hasta_e_con_asignacion_mixta_relee_bien():
    """Milestone de G: el flujo completo -- cargar -> separar -> huecos
    -> asignación mixta (colores reales + calado) -> armar zonas
    finales -> escribir SVG -> RELEER con el lector real del Topper --
    los colores asignados aparecen, y el calado NO deja un `<path>`
    fantasma (el hueco calado queda como área vacía real)."""
    import tempfile

    ancho, alto, zonas, huecos = _cargar_river_con_huecos()
    colores_por_hueco = ["#1f5fa8"] * 4 + [None] * 3
    zonas_finales = imp.armar_zonas_finales(zonas, huecos, colores_por_hueco=colores_por_hueco)

    with tempfile.TemporaryDirectory() as carpeta_tmp:
        ruta_svg = os.path.join(carpeta_tmp, "river_asignado.svg")
        imp.escribir_svg(zonas_finales, ancho, alto, ruta_svg)
        leido = svg_import.svg_a_poligonos_por_color(ruta_svg)

    colores_leidos = [c for _, c in leido]
    assert "#1f5fa8" in colores_leidos, "el color asignado a los huecos no relee del SVG final"
    assert len(leido) == len(zonas_finales), "se perdió o sobró una región al escribir/releer"

    area_azul_esperada = sum(int(huecos[i].sum()) for i in range(4))
    area_azul_svg = [p.area for p, c in leido if c == "#1f5fa8"][0]
    diferencia_pct = 100 * abs(area_azul_svg - area_azul_esperada) / area_azul_esperada
    print(f"  azul esperado={area_azul_esperada}px azul en SVG releído={area_azul_svg:.0f}px ({diferencia_pct:.2f}% dif)")
    assert diferencia_pct < 10.0, f"área del azul asignado difiere {diferencia_pct:.1f}% al releer"


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
