#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_imagen_import_borde.py
------------------
Red de regresión para un bug preexistente encontrado al validar la
Parte D del Importador de Escudos: `core.imagen_import._mascara_a_poligono`
llamaba a `skimage.measure.find_contours` SIN margen -- una forma que
toca el borde de la máscara (fila 0/-1 o columna 0/-1) no puede cerrar
su contorno ahí (no hay nada "afuera" contra qué cruzar el nivel 0.5) y
sale FRAGMENTADA (contornos abiertos, ínfimos, en vez del polígono
completo) en vez de romper con un error visible.

Esto afecta producción, no solo el importador: cualquier decoración
"Imagen" del Topper cuyo dibujo toque el borde de su propio recorte
podía salir mal vectorizada. El fix (1px de margen antes de trazar,
offset de vuelta después) está en `_mascara_a_poligono` -- este archivo
prueba específicamente el caso que el bug rompía.

No usa pytest (ver AGENTS.md "Testing") -- funciones `test_*` con
`assert` simple, corribles con
`python tests/test_imagen_import_borde.py`.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np

from core import imagen_import
from core import importador_escudos as imp

_CARPETA_TEST = os.path.dirname(os.path.abspath(__file__))
ESCUDO_UNION = os.path.join(_CARPETA_TEST, "_fixture_escudo_union.svg")


def test_franjas_que_tocan_arriba_y_abajo_del_canvas_vectorizan_completas():
    """El caso mínimo que destapó el bug: 3 franjas verticales que
    tocan la fila 0 Y la fila -1 (todo el alto del canvas) -- antes del
    fix, `find_contours` solo encontraba las líneas divisorias entre
    franjas (contornos degenerados), no las 3 franjas completas."""
    alto, ancho = 200, 400
    mascara = np.zeros((alto, ancho), dtype=bool)
    mascara[:, 0:50] = True
    mascara[:, 100:150] = True
    mascara[:, 200:250] = True

    poligono = imagen_import._mascara_a_poligono(mascara)
    assert poligono is not None, "no debería dar None -- hay 3 franjas con área de sobra"

    partes = poligono.geoms if hasattr(poligono, "geoms") else [poligono]
    assert len(partes) == 3, f"esperaba 3 franjas completas, salieron {len(partes)} partes"

    for p in partes:
        # cada franja es 50x200=10000px -- con margen de 1px alrededor
        # el área vectorial puede variar un poco, pero tiene que
        # acercarse mucho a 10000, no quedar en una fracción rota.
        assert 9000 < p.area < 11000, f"área de una franja fuera de rango: {p.area}"
        assert len(p.interiors) == 0

    area_total = sum(p.area for p in partes)
    assert abs(area_total - mascara.sum()) / mascara.sum() < 0.05, (
        f"área total vectorizada ({area_total}) debería acercarse a los píxeles de la máscara ({mascara.sum()})"
    )


def test_forma_que_toca_un_solo_borde_tambien_cierra_bien():
    """Variante: toca SOLO el borde izquierdo (columna 0), no arriba/
    abajo -- confirma que el fix no depende de qué borde específico se
    toque."""
    alto, ancho = 150, 150
    mascara = np.zeros((alto, ancho), dtype=bool)
    mascara[40:110, 0:60] = True  # toca la columna 0, no toca fila 0 ni fila -1

    poligono = imagen_import._mascara_a_poligono(mascara)
    assert poligono is not None
    partes = poligono.geoms if hasattr(poligono, "geoms") else [poligono]
    assert len(partes) == 1
    assert abs(partes[0].area - mascara.sum()) / mascara.sum() < 0.05


def test_franjas_de_union_ida_y_vuelta_sin_apilado_con_el_fix():
    """El caso REAL que destapó todo esto: las franjas rojas de Unión
    (que sí tocan el borde superior/inferior del escudo). Con el fix,
    el ida-y-vuelta (vectorizar la zona roja de B y re-rasterizarla)
    tiene que dar prácticamente la máscara original -- antes del fix,
    la mitad de las franjas se perdían/desplazaban."""
    from core import imagen_import as ii

    ancho, alto, capas = imp.cargar_escudo(ESCUDO_UNION)
    zonas = imp.separar_zonas_excluyentes(capas)
    color_rojo, mascara_rojo = [z for z in zonas if z[0] == "#ed1c24"][0]

    poligono = ii._mascara_a_poligono(mascara_rojo)
    transformar = lambda pt: (pt[0], alto - pt[1])
    reconstruida = imp._rasterizar_poligono(poligono, ancho, alto, transformar)

    diferencia = int((mascara_rojo ^ reconstruida).sum())
    porcentaje = 100 * diferencia / int(mascara_rojo.sum())
    print(f"  rojo Unión: original={mascara_rojo.sum()}px reconstruida={reconstruida.sum()}px "
          f"diferencia={diferencia}px ({porcentaje:.2f}%)")
    assert porcentaje < 10, (
        f"el ida-y-vuelta de la zona roja de Unión difiere {porcentaje:.1f}% -- "
        f"esperado <10% (ruido normal de rasterización), el bug de borde daría >100%"
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
