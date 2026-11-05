#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_paginas_cargan.py
------------------
Red de regresión para que la app NO se rompa al abrir una página. Nació de un error real:
la página de Silueta con Nombre pedía por defecto el color "Gris", que ya no existe en la paleta
(`core/colores.py` tiene "Gris Frío" y "Gris Oscuro"), y la página entera se caía con
`ValueError: 'Gris' is not in list`. Dos protecciones:

  1. los nombres de color escritos a mano en páginas y generadores (`colores.NOMBRES.index("...")`,
     parámetros `color_...="..."`) existen en la paleta -- rápido y con el archivo y la línea;
  2. TODAS las páginas de `pages/` cargan sin excepción (con `streamlit.testing.AppTest`, sin abrir
     navegador ni servidor): atrapa ese error y cualquier otro que rompa una página al abrirla.

No usa pytest (ver AGENTS.md "Testing") -- funciones `test_*` con `assert` simple,
corribles con `python tests/test_paginas_cargan.py`.
"""
import ast
import glob
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
os.chdir(RAIZ)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from core import colores

ARCHIVOS = sorted(glob.glob("pages/*.py") + glob.glob("generators/*.py") + ["ui_streamlit.py"])
LISTAS_DE_COLORES = ("NOMBRES", "COLORES")    # colores.NOMBRES y llavero.COLORES (que es la misma paleta)


def _nombres_de_color_escritos_a_mano(fuente):
    """[(linea, nombre)] de cada nombre de color literal: `X.NOMBRES.index("Rojo")`, el valor por defecto de un
    parámetro `color_...="Rojo"` y un argumento `color_...="Rojo"` en una llamada. Los hex ("#...") no cuentan."""
    arbol = ast.parse(fuente)
    hallazgos = []
    for nodo in ast.walk(arbol):
        if (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute) and nodo.func.attr == "index"
                and isinstance(nodo.func.value, ast.Attribute) and nodo.func.value.attr in LISTAS_DE_COLORES
                and nodo.args and isinstance(nodo.args[0], ast.Constant) and isinstance(nodo.args[0].value, str)):
            hallazgos.append((nodo.args[0].lineno, nodo.args[0].value))
        if isinstance(nodo, ast.Call):
            for kw in nodo.keywords:
                if kw.arg and kw.arg.startswith("color_") and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                    hallazgos.append((kw.value.lineno, kw.value.value))
        if isinstance(nodo, ast.FunctionDef):
            argumentos = nodo.args.args + nodo.args.kwonlyargs
            valores = [None] * (len(nodo.args.args) - len(nodo.args.defaults)) + list(nodo.args.defaults) + list(nodo.args.kw_defaults)
            for arg, valor in zip(argumentos, valores):
                if arg.arg.startswith("color_") and isinstance(valor, ast.Constant) and isinstance(valor.value, str):
                    hallazgos.append((valor.lineno, valor.value))
    return [(linea, nombre) for linea, nombre in hallazgos if not nombre.startswith("#")]


def test_los_colores_escritos_a_mano_existen_en_la_paleta():
    inexistentes = []
    revisados = 0
    for ruta in ARCHIVOS:
        with open(ruta, encoding="utf-8") as f:
            for linea, nombre in _nombres_de_color_escritos_a_mano(f.read()):
                revisados += 1
                if nombre not in colores.NOMBRES:
                    inexistentes.append(f"{ruta}:{linea}  {nombre!r}")
    assert revisados > 30, f"solo encontré {revisados} nombres de color: el buscador dejó de encontrar casi todo"
    assert not inexistentes, ("estos colores no están en core/colores.py (la página se rompe o cae en un color de reserva): "
                              + "; ".join(inexistentes))


def test_el_buscador_de_colores_encuentra_los_tres_usos_y_distingue_lo_valido():
    fuente = (
        'index = colores.NOMBRES.index("Blanco")\n'
        'otra = llavero.COLORES.index("Inventado")\n'
        'def f(color_base="Gris", color_hex="#ff0000", otro="Rojo"):\n    pass\n'
        'f(color_texto="Marrón")\n')
    assert _nombres_de_color_escritos_a_mano(fuente) == [(1, "Blanco"), (2, "Inventado"), (3, "Gris"), (5, "Marrón")] \
        or sorted(_nombres_de_color_escritos_a_mano(fuente)) == sorted([(1, "Blanco"), (2, "Inventado"), (3, "Gris"), (5, "Marrón")])


def test_todas_las_paginas_cargan_sin_excepcion():
    from streamlit.testing.v1 import AppTest
    paginas = sorted(glob.glob("pages/*.py"))
    assert len(paginas) >= 12, f"solo encontré {len(paginas)} páginas"
    fallas = []
    for ruta in paginas:
        at = AppTest.from_file(os.path.abspath(ruta), default_timeout=120).run()
        if len(at.exception):
            fallas.append(f"{os.path.basename(ruta).encode('ascii', 'replace').decode()}: {str(at.exception[0].value)[:150]}")
    assert not fallas, "estas páginas se rompen al abrirlas: " + " | ".join(fallas)


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
