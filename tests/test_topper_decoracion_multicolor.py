#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_topper_decoracion_multicolor.py
------------------
Red de regresión para 7C-C (idea 19 -- "Contenida en el marco" -- cruzada
con 7C-B -- multicolor dentro de un casillero de "Múltiples decoraciones").

Contexto: 7C-C no agregó código nuevo -- el recorte "Contenida" ya
funcionaba para las sub-piezas de un casillero multicolor como efecto
colateral de que `contenida_por_pieza` (generators/topper.py) se llena
por POSICIÓN en una lista plana, sin importar si esa posición vino de
un casillero de un solo color o de varias sub-piezas separadas por
color. Este archivo existe para que, si en el futuro alguien toca
`contenida_por_pieza` o el paso de recorte (intersección contra
`marco_silueta_solida`), una regresión se note acá en vez de en
silencio.

No usa pytest (el proyecto no lo tiene como dependencia, ver
AGENTS.md "Testing") -- son funciones `test_*` con `assert` simple,
compatibles con pytest si algún día se agrega, y corribles ya mismo
con `python tests/test_topper_decoracion_multicolor.py`.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from generators import topper

FUENTE = os.path.join("fonts", "curadas", "Anton.ttf")
_CARPETA_TEST = os.path.dirname(os.path.abspath(__file__))
_DECO_MULTICOLOR_SVG = os.path.join(_CARPETA_TEST, "_fixture_deco_4colores.svg")


def _crear_fixture_svg_4_colores():
    """SVG de 4 cuadrantes de colores distintos -- separa limpio en 4
    sub-piezas vía `_colores_desde_archivo`, sin ambigüedad de bordes."""
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


def _claves_decoracion(regiones):
    return sorted(k for k in regiones if k == "decoracion" or k.startswith("decoracion_"))


def test_flag_multicolor_apagado_no_agrega_sufijos_col():
    """Caso (1): con 1 a 4 casilleros de UN SOLO color (el flag
    "multicolor" apagado, el caso de siempre), las claves de decoración
    tienen que seguir siendo "decoracion"/"decoracion_2"/"_3"/"_4" -- sin
    ningún sufijo "_colN" (eso solo debe aparecer cuando un casillero SÍ
    pide separarse por color) -- y ninguna pieza puede ser None (nada
    que pudiera vaciarlas: sin marco, sin "Contenida")."""
    deco_svg = _crear_fixture_svg_4_colores()  # sirve igual como SVG de 1 color acá
    for n in (1, 2, 3, 4):
        decoraciones = [
            {"svg": deco_svg, "lado": ["Derecha", "Izquierda", "Arriba", "Arriba derecha"][i], "tam_mm": 20.0}
            for i in range(n)
        ]
        regiones, n_puentes, avisos, _colores_sugeridos = topper._armar_regiones_plano(
            lineas=["Hola"], tamaño_mm=70, fuente=FUENTE, marco="Ninguno",
            decoraciones=decoraciones,
        )
        claves = _claves_decoracion(regiones)
        assert len(claves) == n, f"con {n} casillero(s) de 1 color, esperaba {n} claves, salió {claves}"
        assert all("_col" not in c for c in claves), f"no debería haber sufijos _col con multicolor apagado: {claves}"
        assert all(regiones[c] is not None for c in claves)


def test_contenida_recorta_cada_subpieza_contra_silueta_llena_del_marco():
    """Casos (2): un casillero multicolor (4 sub-piezas) más grande que
    el marco, con "Contenida" tildado -- cada sub-pieza tiene que quedar
    EXACTAMENTE (`cruda ∩ marco_pristino`, no una aproximación) recortada
    a la silueta LLENA del marco (`marco` ∪ `marco_borde`, calculada de
    un run SIN decoraciones para no contaminarse con el "sobre el marco"
    -- ver Nota de precisión más abajo), y las que caen enteras afuera
    tienen que directamente no aparecer (tratadas como None)."""
    deco_svg = _crear_fixture_svg_4_colores()
    _verificar_contenida_contra_silueta_llena(deco_svg, marco="Círculo", marco_relleno=True)


def test_contenida_con_marco_aro_usa_silueta_llena_no_el_aro_fino():
    """Caso (3): mismo chequeo que el anterior, pero con el marco en
    modo Aro (fino) -- "Contenida" tiene que seguir recortando contra la
    silueta LLENA (el disco completo), NO contra el aro visible (que
    dejaría casi toda sub-pieza vacía) -- ver idea 19 original."""
    deco_svg = _crear_fixture_svg_4_colores()
    _verificar_contenida_contra_silueta_llena(deco_svg, marco="Círculo", marco_relleno=False)

    # Chequeo extra, específico del modo Aro: confirmar que el resultado
    # NO coincide con "recortar contra el aro fino" -- si coincidiera,
    # el test de arriba podría estar pasando por casualidad (ej. si el
    # aro y la silueta llena dieran áreas parecidas para estos tamaños).
    kwargs_base = dict(
        lineas=["Hi"], tamaño_mm=40, fuente=FUENTE, marco="Círculo", marco_relleno=False,
        grosor_marco_mm=3.0, margen_marco_mm=6.0,
    )
    regiones_sin_deco, _, _, _ = topper._armar_regiones_plano(**kwargs_base)
    aro_fino = regiones_sin_deco["marco"]  # en modo Aro, "marco" ES el aro visible

    item_base = {"svg": deco_svg, "lado": "Arriba", "tam_mm": 80.0, "multicolor": True,
                 "sobre_marco": True, "contenida": True}
    regiones_contenida, _, _, _ = topper._armar_regiones_plano(decoraciones=[item_base], **kwargs_base)

    hubo_alguna_distinta_del_aro = False
    for clave in _claves_decoracion(regiones_contenida):
        real = regiones_contenida[clave]
        if real is None:
            continue
        if real.symmetric_difference(real.intersection(aro_fino)).area > 1e-6:
            hubo_alguna_distinta_del_aro = True
    assert hubo_alguna_distinta_del_aro, (
        "ninguna sub-pieza contenida difiere de 'recortar contra el aro fino' -- "
        "el test no está distinguiendo silueta llena vs. aro"
    )


def _verificar_contenida_contra_silueta_llena(deco_svg, marco, marco_relleno):
    kwargs_base = dict(
        lineas=["Hi"], tamaño_mm=40, fuente=FUENTE, marco=marco, marco_relleno=marco_relleno,
        grosor_marco_mm=3.0, margen_marco_mm=6.0,
    )

    # Marco PRÍSTINO (silueta LLENA, no el aro visible): de un run SIN
    # decoraciones (nada puede haberlo carvado -- "sobre el marco"
    # modifica el marco durante el loop de decoraciones si se usa en el
    # mismo run que las piezas) y CON marco_relleno=True sin importar el
    # `marco_relleno` que se esté probando -- en modo Aro,
    # `regiones["marco"]` es solo el aro fino, y comparar contra eso
    # repetiría el mismo error que "Contenida" existe para evitar (ver
    # idea 19). El radio/centro del marco no dependen de `marco_relleno`
    # (mismo texto, mismo margen), así que esta referencia vale para
    # cualquiera de los dos estilos.
    kwargs_referencia = dict(kwargs_base, marco_relleno=True)
    regiones_sin_deco, _, _, _ = topper._armar_regiones_plano(**kwargs_referencia)
    marco_pristino = regiones_sin_deco["marco"].union(regiones_sin_deco["marco_borde"])
    assert marco_pristino.area > 0

    item_base = {"svg": deco_svg, "lado": "Arriba", "tam_mm": 80.0, "multicolor": True, "sobre_marco": True}

    # "cruda": posicionada, SIN contenida, con sobre_marco=True -- así
    # la pieza en sí no se vuelve a tocar por el paso de marco-vs-
    # decoración (solo el marco se talla, ver idea 19), y queda
    # exactamente la forma post-posicionamiento, pre-recorte.
    regiones_cruda, _, _, _ = topper._armar_regiones_plano(
        decoraciones=[dict(item_base, contenida=False)], **kwargs_base)
    regiones_contenida, _, _, _ = topper._armar_regiones_plano(
        decoraciones=[dict(item_base, contenida=True)], **kwargs_base)

    claves_crudas = _claves_decoracion(regiones_cruda)
    assert len(claves_crudas) == 4, f"esperaba 4 sub-piezas del SVG de 4 colores, salió {claves_crudas}"

    hubo_alguna_vacia = False
    hubo_alguna_con_area = False
    for clave in claves_crudas:
        cruda = regiones_cruda[clave]
        esperado = cruda.intersection(marco_pristino)
        real = regiones_contenida.get(clave)

        if esperado.is_empty or esperado.area < 1e-9:
            hubo_alguna_vacia = True
            assert real is None, f"{clave}: cae entera afuera del marco, debería ser None, salió area={None if real is None else real.area}"
        else:
            hubo_alguna_con_area = True
            assert real is not None, f"{clave}: se esperaba área {esperado.area:.3f}, salió None"
            diferencia = real.symmetric_difference(esperado).area
            assert diferencia < 1e-6, f"{clave}: geometría recortada no coincide con cruda∩marco_pristino (diff área={diferencia:.6f})"

    # el propio diseño del test (sub-piezas mucho más grandes que el
    # marco) tiene que producir AMBOS casos -- si no, no se está
    # probando de verdad ni el recorte ni el descarte a None.
    assert hubo_alguna_vacia, "el escenario de prueba debería dejar al menos una sub-pieza totalmente afuera"
    assert hubo_alguna_con_area, "el escenario de prueba debería dejar al menos una sub-pieza parcialmente adentro"


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
