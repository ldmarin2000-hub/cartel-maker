#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_preview3d_escena.py
------------------
Red de regresión para la escena del visor 3D (`core/preview3d.armar_escena`):
piezas con el MISMO nombre (la misma letra o el mismo separador repetidos en un
collar) tienen que verse todas, no solo la última -- trimesh usa el nombre como
identificador del nodo y las pisaba.

No usa pytest (ver AGENTS.md "Testing") -- funciones `test_*` con
`assert` simple, corribles con `python tests/test_preview3d_escena.py`.
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import trimesh

from core import preview3d
from generators import collar

FUENTE = os.path.join("fonts", "curadas", "Anton.ttf")


def _caja_en(x):
    caja = trimesh.creation.box([10, 10, 10])
    caja.apply_translation([x, 0, 0])
    return caja


def _ida_y_vuelta(escena):
    """Exporta a GLB y vuelve a cargar: lo que de verdad le llega al visor."""
    return trimesh.load(io.BytesIO(escena.export(file_type="glb")), file_type="glb")


def _dibujables(escena):
    """Cuántas piezas se DIBUJAN: los nodos del grafo que apuntan a una geometría. No alcanza con
    contar `escena.geometry` -- con nombres repetidos la geometría queda en el diccionario pero el
    nodo se pisa, y el visor (que dibuja nodos) muestra solo la última."""
    return len(escena.graph.nodes_geometry)


def test_piezas_con_el_mismo_nombre_se_ven_todas():
    piezas = [{"malla": _caja_en(x), "color": "#ff0000", "nombre": "letra E"} for x in (0, 20, 40)]
    escena = preview3d.armar_escena(piezas)
    assert _dibujables(escena) == 3, f"se perdieron piezas repetidas: se dibujan {_dibujables(escena)} de 3"
    vuelta = _ida_y_vuelta(escena)
    assert _dibujables(vuelta) == 3, f"al exportar al visor se dibujan {_dibujables(vuelta)} de 3"
    centros_x = sorted(round(g.bounds[:, 0].mean()) for g in vuelta.geometry.values())
    assert centros_x == [0, 20, 40], centros_x


def test_piezas_sin_nombre_tampoco_se_pisan():
    escena = preview3d.armar_escena([{"malla": _caja_en(x)} for x in (0, 20)])
    assert _dibujables(escena) == 2 and _dibujables(_ida_y_vuelta(escena)) == 2


def test_una_pieza_con_archivo_inexistente_se_saltea_y_las_demas_siguen():
    piezas = [{"malla": _caja_en(0), "nombre": "a"}, {"ruta_stl": "no_existe.stl"}, {"malla": _caja_en(20), "nombre": "a"}]
    assert _dibujables(preview3d.armar_escena(piezas)) == 2
    assert preview3d.armar_html_visor([{"ruta_stl": "no_existe.stl"}]) is None


def test_el_collar_completo_llega_entero_al_visor():
    """El caso real que fallaba: "ME RECIBI" con separadores repetidos. Cada pieza del armado
    (cuentas, letras, cilindros, estrellas, corazones) tiene que estar en la escena."""
    estrella = {"tipo": "forma", "forma": {"nombre": "estrella"}}
    corazon = {"tipo": "forma", "forma": {"nombre": "corazon"}}
    import tempfile
    with tempfile.TemporaryDirectory() as carpeta:
        r = collar.generar("ME RECIBI", FUENTE, carpeta_salida=carpeta, prefijo="t", separadores={
            "inicio": corazon, "final": corazon, "entre_letras": "cilindro", "entre_palabras": estrella})
    armado = r["armado"]
    # 8 cuentas + 8 letras + 6 cilindros + 1 estrella + 2 corazones
    assert len(armado) == 8 + 8 + 6 + 1 + 2
    escena = preview3d.armar_escena(
        [{"malla": m, "color": color_hex, "nombre": etiqueta} for m, color_hex, etiqueta in armado])
    assert _dibujables(escena) == len(armado), (_dibujables(escena), len(armado))
    vuelta = _ida_y_vuelta(escena)
    assert _dibujables(vuelta) == len(armado), (_dibujables(vuelta), len(armado))
    # y no quedó ninguna tapada por otra en el mismo lugar: los centros de las cuentas son todos distintos
    centros = [round(m.bounds[:, 0].mean(), 1) for m, _, e in armado if e.startswith("cuenta")]
    assert len(set(centros)) == 8


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
