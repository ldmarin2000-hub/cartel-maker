#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_llavero_aro.py
------------------
Red de regresión para `generators/llavero.py::_armar_base_con_aro` --
en particular las opciones nuevas "arriba"/"abajo" (agujero centrado en
X, pegado al borde superior/inferior del bounding box), agregadas junto
a las 4 que ya existían (izquierda/derecha/ambos/ninguno).

No usa pytest (ver AGENTS.md "Testing") -- funciones `test_*` con
`assert` simple, corribles con
`python tests/test_llavero_aro.py`.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from shapely.geometry import Point, box

from generators import llavero

# Rectángulo sintético 30x10 (simula el bounding box de un nombre corto)
# -- no hace falta texto real para probar la geometría del aro, que no
# le importa el CONTENIDO, solo su bounding box.
CONTENIDO = box(0, 0, 30, 10)
ARO_R = 2.0
BORDE_MM = 3.0


def _hay_agujero_en(base, x, y, radio=ARO_R):
    """El agujero es un `difference` -- confirmamos que el centro
    esperado NO tiene material (está afuera de `base`)."""
    return not base.contains(Point(x, y))


def test_arriba_agrega_agujero_centrado_en_x_por_encima_del_contenido():
    base = llavero._armar_base_con_aro(CONTENIDO, "arriba", ARO_R, BORDE_MM)
    cminx, cminy, cmaxx, cmaxy = CONTENIDO.bounds
    ccx = (cminx + cmaxx) / 2
    ry_esperado = cmaxy + ARO_R + 3

    minx, miny, maxx, maxy = base.bounds
    assert maxy > cmaxy, "la base tiene que crecer hacia arriba para incluir la oreja del aro"
    assert abs((minx + maxx) / 2 - ccx) < 0.5, "la oreja de arriba tiene que quedar centrada en X"
    assert _hay_agujero_en(base, ccx, ry_esperado), "no se encontró el agujero en la posición esperada (arriba)"
    # no debe haber agregado nada a los lados (izquierda/derecha intactos)
    assert abs(minx - (cminx - BORDE_MM)) < 0.5, "arriba no debería ensanchar la base a la izquierda"
    assert abs(maxx - (cmaxx + BORDE_MM)) < 0.5, "arriba no debería ensanchar la base a la derecha"


def test_abajo_agrega_agujero_centrado_en_x_por_debajo_del_contenido():
    base = llavero._armar_base_con_aro(CONTENIDO, "abajo", ARO_R, BORDE_MM)
    cminx, cminy, cmaxx, cmaxy = CONTENIDO.bounds
    ccx = (cminx + cmaxx) / 2
    ry_esperado = cminy - ARO_R - 3

    minx, miny, maxx, maxy = base.bounds
    assert miny < cminy, "la base tiene que crecer hacia abajo para incluir la oreja del aro"
    assert abs((minx + maxx) / 2 - ccx) < 0.5, "la oreja de abajo tiene que quedar centrada en X"
    assert _hay_agujero_en(base, ccx, ry_esperado), "no se encontró el agujero en la posición esperada (abajo)"


def test_arriba_y_abajo_son_geometricamente_simetricos():
    """Mismo aro_r/borde -- el "alto" que agrega la oreja de arriba tiene
    que ser igual al que agrega la de abajo (mismo esquema, eje
    reflejado)."""
    base_arriba = llavero._armar_base_con_aro(CONTENIDO, "arriba", ARO_R, BORDE_MM)
    base_abajo = llavero._armar_base_con_aro(CONTENIDO, "abajo", ARO_R, BORDE_MM)
    cminy, cmaxy = CONTENIDO.bounds[1], CONTENIDO.bounds[3]

    crecimiento_arriba = base_arriba.bounds[3] - cmaxy
    crecimiento_abajo = cminy - base_abajo.bounds[1]
    assert abs(crecimiento_arriba - crecimiento_abajo) < 0.01, (
        crecimiento_arriba, crecimiento_abajo
    )


def test_opciones_preexistentes_sin_regresion():
    """izquierda/derecha/ambos/ninguno tienen que dar EXACTAMENTE los
    mismos bounds que antes de agregar arriba/abajo -- calculados a
    mano con la misma fórmula que ya usaba el código (no cambié esas
    ramas, esto confirma que no rompí nada al tocar la función)."""
    cminx, cminy, cmaxx, cmaxy = CONTENIDO.bounds

    base_izq = llavero._armar_base_con_aro(CONTENIDO, "izquierda", ARO_R, BORDE_MM)
    rx_izq = cminx - ARO_R - 3
    assert abs(base_izq.bounds[0] - (rx_izq - (ARO_R + 2))) < 0.5

    base_der = llavero._armar_base_con_aro(CONTENIDO, "derecha", ARO_R, BORDE_MM)
    rx_der = cmaxx + ARO_R + 3
    assert abs(base_der.bounds[2] - (rx_der + (ARO_R + 2))) < 0.5

    base_ambos = llavero._armar_base_con_aro(CONTENIDO, "ambos", ARO_R, BORDE_MM)
    assert base_ambos.bounds[0] == base_izq.bounds[0]
    assert base_ambos.bounds[2] == base_der.bounds[2]

    base_ninguno = llavero._armar_base_con_aro(CONTENIDO, "ninguno", ARO_R, BORDE_MM)
    esperado_sin_aro = CONTENIDO.buffer(BORDE_MM, join_style=1, cap_style=1)
    assert base_ninguno.equals(esperado_sin_aro)
    # y "ninguno" no debería tocar ni arriba ni abajo tampoco
    assert abs(base_ninguno.bounds[1] - (cminy - BORDE_MM)) < 0.5
    assert abs(base_ninguno.bounds[3] - (cmaxy + BORDE_MM)) < 0.5


def test_lados_aro_incluye_las_6_opciones():
    assert llavero.LADOS_ARO == ["izquierda", "derecha", "arriba", "abajo", "ambos", "ninguno"]


def test_aro_x_aro_y_cero_es_identico_a_sin_offset():
    """`aro_x=aro_y=0` (el default) tiene que dar EXACTAMENTE lo mismo
    que no pasar esos parámetros -- nadie que ya usaba la función antes
    de este agregado nota el cambio."""
    for lado in llavero.LADOS_ARO:
        sin_offset = llavero._armar_base_con_aro(CONTENIDO, lado, ARO_R, BORDE_MM)
        con_offset_cero = llavero._armar_base_con_aro(CONTENIDO, lado, ARO_R, BORDE_MM, aro_x=0, aro_y=0)
        assert sin_offset.equals(con_offset_cero), lado


def test_aro_x_aro_y_mueve_el_agujero_a_la_posicion_esperada():
    """Para cada lado con un solo agujero, aplicar un offset tiene que
    mover el agujero EXACTAMENTE a `posicion_default + (aro_x, aro_y)`
    -- y la posición vieja (sin offset) ya no debe tener agujero ahí
    (confirma que se movió, no que se agregó un segundo)."""
    cminx, cminy, cmaxx, cmaxy = CONTENIDO.bounds
    ccx, ccy = (cminx + cmaxx) / 2, (cminy + cmaxy) / 2
    aro_x, aro_y = 5.0, -3.0

    casos = {
        "izquierda": (cminx - ARO_R - 3, ccy),
        "derecha": (cmaxx + ARO_R + 3, ccy),
        "arriba": (ccx, cmaxy + ARO_R + 3),
        "abajo": (ccx, cminy - ARO_R - 3),
    }
    for lado, (px_default, py_default) in casos.items():
        base = llavero._armar_base_con_aro(CONTENIDO, lado, ARO_R, BORDE_MM, aro_x=aro_x, aro_y=aro_y)
        assert _hay_agujero_en(base, px_default + aro_x, py_default + aro_y), (
            f"{lado}: no se encontró el agujero desplazado a ({px_default + aro_x}, {py_default + aro_y})"
        )
        assert base.geom_type == "Polygon" and len(base.interiors) == 1, (
            f"{lado}: se esperaba UN solo agujero (movido), salió geom_type={base.geom_type} "
            f"interiores={len(base.interiors) if base.geom_type == 'Polygon' else '?'}"
        )


def test_aro_x_aro_y_mueve_todo_el_sistema_como_un_bloque_rigido():
    """El bug real que reportó la usuaria: el agujero se movía pero la
    "oreja" que lo conecta al borde quedaba anclada en el lugar viejo
    -- quedaba una diagonal rara, o directamente se veía el aro
    flotando separado de la pieza. Confirmamos acá que el punto de
    anclaje contra `contenido` se traslada EXACTAMENTE lo mismo que el
    agujero (todo el sistema rígido, no solo el agujero) -- para eso
    hay que mirar el tab (LineString buffereada) ANTES de la unión con
    la base, no solo el resultado final."""
    from shapely.affinity import translate as _translate
    from shapely.geometry import LineString as _LineString

    cminx, cminy, cmaxx, cmaxy = CONTENIDO.bounds
    ccx, ccy = (cminx + cmaxx) / 2, (cminy + cmaxy) / 2
    aro_x, aro_y = 5.0, 5.0

    casos = {
        "izquierda": ((cminx, ccy), (cminx - ARO_R - 3, ccy)),
        "derecha": ((cmaxx, ccy), (cmaxx + ARO_R + 3, ccy)),
        "arriba": ((ccx, cmaxy), (ccx, cmaxy + ARO_R + 3)),
        "abajo": ((ccx, cminy), (ccx, cminy - ARO_R - 3)),
    }
    for lado, (punto_borde, punto_aro) in casos.items():
        tab_esperado = _translate(
            _LineString([punto_aro, punto_borde]).buffer(ARO_R + 2, cap_style=1), xoff=aro_x, yoff=aro_y
        )
        base_con_offset = llavero._armar_base_con_aro(CONTENIDO, lado, ARO_R, BORDE_MM, aro_x=aro_x, aro_y=aro_y)
        base_sin_aro = CONTENIDO.buffer(BORDE_MM, join_style=1, cap_style=1)
        # la base final es la UNIÓN de (base sin aro) y el tab -- si el
        # tab está bien trasladado, unirlo a mano tiene que dar EXACTAMENTE
        # el mismo resultado (antes del difference del agujero) que lo
        # que devuelve la función real.
        from shapely.ops import unary_union as _unary_union
        esperado_sin_hueco = _unary_union([base_sin_aro, tab_esperado])
        hueco_esperado = _translate(Point(punto_aro).buffer(ARO_R, resolution=32), xoff=aro_x, yoff=aro_y)
        esperado = esperado_sin_hueco.difference(hueco_esperado)
        assert base_con_offset.equals(esperado), f"{lado}: el aro no se movió como bloque rígido"


def test_offset_moderado_sigue_conectado_offset_grande_puede_despegar():
    """Con un offset RAZONABLE (5mm en una pieza de 30x10) la oreja
    sigue tocando la base -- pieza única. Con uno EXAGERADO (más del
    tamaño de la pieza) puede llegar a despegarse -- mismo riesgo ya
    aceptado que tienen `deco_x`/`deco_y` (podés empujar una decoración
    tan lejos que quede fuera de la pieza): es la usuaria quien decide
    cuánto mover, esto documenta el límite, no lo prohíbe."""
    for lado in ("izquierda", "derecha", "arriba", "abajo"):
        moderado = llavero._armar_base_con_aro(CONTENIDO, lado, ARO_R, BORDE_MM, aro_x=5.0, aro_y=5.0)
        assert moderado.geom_type == "Polygon", f"{lado}: un offset de 5mm no debería despegar el aro"

    exagerado = llavero._armar_base_con_aro(CONTENIDO, "derecha", ARO_R, BORDE_MM, aro_x=15.0, aro_y=10.0)
    assert exagerado.geom_type == "MultiPolygon", (
        "un offset exagerado debería poder despegar el aro (riesgo aceptado, como con deco_x/deco_y) -- "
        "si esto ya no pasa, no hace falta este test, pero confirmá que no se está limitando el offset en secreto"
    )


def test_ambos_aplica_el_mismo_offset_a_los_2_agujeros():
    cminx, cminy, cmaxx, cmaxy = CONTENIDO.bounds
    ccy = (cminy + cmaxy) / 2
    aro_x, aro_y = -4.0, 6.0

    base = llavero._armar_base_con_aro(CONTENIDO, "ambos", ARO_R, BORDE_MM, aro_x=aro_x, aro_y=aro_y)
    px_izq, py_izq = cminx - ARO_R - 3 + aro_x, ccy + aro_y
    px_der, py_der = cmaxx + ARO_R + 3 + aro_x, ccy + aro_y
    assert _hay_agujero_en(base, px_izq, py_izq), "agujero izquierdo no está en la posición desplazada esperada"
    assert _hay_agujero_en(base, px_der, py_der), "agujero derecho no está en la posición desplazada esperada"


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
