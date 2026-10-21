#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_llavero_multicolor.py
------------------
Red de regresión para el Llavero -- Parte 2 del ícono "a color":
`_armar_geometria` deja el ícono SEPARADO por color real (en vez de
fusionado en `contenido`) cuando se pasa `decoracion_multicolor_ruta`,
y `generar()` exporta cada color como su propio STL (sueltos sin AMS,
combinados en el .3mf/.stl multicolor con AMS). Solo aplica a
imagotipo/isologo -- isotipo/emblema/monograma siguen con el camino
monocromo de siempre (no se pidió, ver docstring de `_armar_geometria`).

No usa pytest (ver AGENTS.md "Testing") -- funciones `test_*` con
`assert` simple, corribles con
`python tests/test_llavero_multicolor.py`.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from core import decoraciones
from generators import llavero

_CARPETA_TEST = os.path.dirname(os.path.abspath(__file__))
FIXTURE_4_COLORES = os.path.join(_CARPETA_TEST, "_fixture_deco_4colores.svg")
FUENTE = os.path.join("fonts", "curadas", "Anton.ttf")


def _armar(modo_logo, **kwargs):
    return llavero._armar_geometria(
        "Ana", FUENTE, 20, "corazon", "derecha", 7, 0, 0, "izquierda", 2, 3, 300,
        modo_logo=modo_logo, **kwargs,
    )


def test_imagotipo_multicolor_separa_el_icono_de_contenido():
    """`contenido` tiene que ser SOLO el texto -- el ícono no se
    fusiona -- y `piezas_icono` tiene que traer las 4 piezas con sus
    colores reales."""
    contenido, base, ancho_mm, alto_mm_real, piezas_icono = _armar(
        "imagotipo", decoracion_multicolor_ruta=FIXTURE_4_COLORES)
    assert len(piezas_icono) == 4
    assert {c for _, c in piezas_icono} == {"#ff0000", "#00ff00", "#0000ff", "#ffff00"}
    # el texto solo ("Ana") no debería tocar ninguna de las piezas del ícono
    for poligono, _ in piezas_icono:
        assert not contenido.intersects(poligono) or contenido.intersection(poligono).area < 1e-6


def test_isologo_multicolor_centra_el_icono_sobre_el_texto():
    """En isologo el ícono va centrado ENCIMA del texto (mismo criterio
    que el monocromo) -- confirmamos que el centro X de la unión del
    ícono cae cerca del centro X del texto."""
    contenido, base, ancho_mm, alto_mm_real, piezas_icono = _armar(
        "isologo", decoracion_multicolor_ruta=FIXTURE_4_COLORES)
    assert len(piezas_icono) == 4
    from shapely.ops import unary_union
    union_icono = unary_union([p for p, _ in piezas_icono])
    cminx, _, cmaxx, _ = contenido.bounds
    iminx, _, imaxx, _ = union_icono.bounds
    assert abs((cminx + cmaxx) / 2 - (iminx + imaxx) / 2) < 0.5


def test_isologo_multicolor_le_resta_el_texto_a_cada_pieza():
    """Mismo choque de geometría que en el caso monocromo, pero acá
    con las 4 piezas de color real -- ninguna debería quedar
    superpuesta con el texto."""
    contenido, base, ancho_mm, alto_mm_real, piezas_icono = llavero._armar_geometria(
        "Ana", FUENTE, 20, "corazon", "derecha", 15, 0, 0, "izquierda", 2, 3, 300,
        modo_logo="isologo", decoracion_multicolor_ruta=FIXTURE_4_COLORES,
    )
    assert len(piezas_icono) == 4
    for poligono, _ in piezas_icono:
        assert poligono.intersection(contenido).area < 1e-6


def test_isologo_monocromo_con_color_icono_hex_separa_el_icono_de_contenido():
    """El bug real que reportó la usuaria: en isologo, un ícono opaco
    centrado ENCIMA del texto, fusionado en una sola pieza de un solo
    color, tapa el texto por completo (no se ve). Con `color_icono_hex`
    seteado, el ícono queda en su propia pieza, separado de `contenido`
    (que pasa a ser SOLO el texto) -- y, más importante, SIN
    superponerse geométricamente con el texto (si no, aunque sean 2
    colores distintos, chocarían en el mismo plano y el texto se
    seguiría sin ver -- ahora por geometría en vez de por color)."""
    # círculo grande a propósito -- tiene que CUBRIR el texto por completo
    # para reproducir el caso real (si no se solaparan, el test no probaría nada).
    contenido, base, ancho_mm, alto_mm_real, piezas_icono = llavero._armar_geometria(
        "Ana", FUENTE, 20, "circulo", "derecha", 25, 0, 0, "izquierda", 2, 3, 300,
        modo_logo="isologo", color_icono_hex="#123456",
    )
    assert len(piezas_icono) == 1
    assert piezas_icono[0][1] == "#123456"
    icono_final = piezas_icono[0][0]
    assert not contenido.equals(icono_final), "el ícono no debería ser la misma geometría que el texto"
    assert icono_final.intersection(contenido).area < 1e-6, (
        "el ícono todavía se superpone con el texto -- chocarían en el mismo plano al imprimir"
    )
    # y la UNIÓN de las 2 piezas tiene que seguir siendo el círculo completo (no se perdió área
    # del ícono al recortarle el texto -- el hueco de texto lo rellena la pieza de texto).
    from shapely.ops import unary_union
    forma_circulo_sola = decoraciones.forma("circulo", 25)
    from shapely.affinity import translate as _translate
    forma_circulo_centrada = _translate(forma_circulo_sola, xoff=(contenido.bounds[0] + contenido.bounds[2]) / 2,
                                         yoff=(contenido.bounds[1] + contenido.bounds[3]) / 2)
    assert abs(unary_union([icono_final, contenido]).area - forma_circulo_centrada.area) < 1.0


def test_isologo_monocromo_sin_color_icono_hex_sigue_fusionando_como_antes():
    """Regresión: sin `color_icono_hex` (default `None`, lo que sigue
    usando cualquier llamador viejo -- CLI incluida), isologo se
    comporta EXACTAMENTE como antes de este fix -- ícono fusionado en
    `contenido`, `piezas_icono` vacío."""
    contenido, base, ancho_mm, alto_mm_real, piezas_icono = _armar("isologo")
    assert piezas_icono == []
    assert contenido.area > 0


def test_imagotipo_no_separa_el_icono_aunque_se_pase_color_icono_hex():
    """El fix es SOLO para isologo (ícono al costado en imagotipo no se
    superpone al texto, no hace falta separarlo) -- si por error se
    pasara `color_icono_hex` en imagotipo, no debería hacer nada."""
    contenido, base, ancho_mm, alto_mm_real, piezas_icono = _armar(
        "imagotipo", color_icono_hex="#123456")
    assert piezas_icono == []


def test_generar_isologo_usa_color_base_para_el_icono_por_default():
    """End-to-end: `generar()` en isologo con un ícono de la lista
    (sin `decoracion_multicolor_ruta`) tiene que separar el ícono a su
    propio STL, coloreado con el hex de "Color base" -- sin que la
    página tenga que pasar ningún parámetro nuevo."""
    import tempfile
    from core import colores
    with tempfile.TemporaryDirectory() as carpeta_tmp:
        r = llavero.generar(
            nombre="Ana", ruta_ttf=FUENTE, alto_mm=20, modo_logo="isologo",
            color_base="Azul", color_texto="Rosa Fluor",
            tiene_ams=False, carpeta_salida=carpeta_tmp,
        )
        assert r["colores_icono"] == [colores.hex_de("Azul")]
        assert len(r["rutas_stl_icono"]) == 1
        assert os.path.isfile(r["rutas_stl_icono"][0])
        assert r["ruta_stl_texto"] is not None and os.path.isfile(r["ruta_stl_texto"])


def test_indices_seleccionados_filtra_los_colores_del_icono():
    contenido, base, ancho_mm, alto_mm_real, piezas_icono = _armar(
        "imagotipo", decoracion_multicolor_ruta=FIXTURE_4_COLORES, decoracion_multicolor_indices=[0, 2])
    assert len(piezas_icono) == 2
    assert {c for _, c in piezas_icono} == {"#ff0000", "#0000ff"}


def test_base_incluye_el_icono_para_el_aro_y_el_borde():
    """`base` (con aro/borde) tiene que cubrir TAMBIÉN el ícono
    multicolor, no solo el texto -- si no, el aro/borde quedarían mal
    calculados (referenciando solo el texto)."""
    contenido, base, ancho_mm, alto_mm_real, piezas_icono = _armar(
        "imagotipo", decoracion_multicolor_ruta=FIXTURE_4_COLORES)
    from shapely.ops import unary_union
    todo = unary_union([contenido] + [p for p, _ in piezas_icono])
    tminx, tminy, tmaxx, tmaxy = todo.bounds
    bminx, bminy, bmaxx, bmaxy = base.bounds
    # base = todo + borde/aro -- tiene que ser AL MENOS tan grande como todo
    assert bminx <= tminx and bminy <= tminy and bmaxx >= tmaxx and bmaxy >= tmaxy


def test_isotipo_multicolor_deja_todo_en_piezas_icono_y_contenido_none():
    """Isotipo SÍ soporta colores reales (no hay texto que fusionar,
    es el caso más simple): `contenido` sale `None` (nada para el
    color de "texto") y las 4 piezas quedan en `piezas_icono`."""
    contenido, base, ancho_mm, alto_mm_real, piezas_icono = llavero._armar_geometria(
        "", FUENTE, 20, "ninguno", "derecha", 7, 0, 0, "izquierda", 2, 3, 300,
        modo_logo="isotipo", decoracion_multicolor_ruta=FIXTURE_4_COLORES,
    )
    assert contenido is None
    assert len(piezas_icono) == 4
    assert {c for _, c in piezas_icono} == {"#ff0000", "#00ff00", "#0000ff", "#ffff00"}
    assert ancho_mm > 0 and alto_mm_real > 0
    # base (con aro/borde) tiene que cubrir el ícono igual, aunque no haya "contenido"
    from shapely.ops import unary_union
    todo = unary_union([p for p, _ in piezas_icono])
    tminx, tminy, tmaxx, tmaxy = todo.bounds
    bminx, bminy, bmaxx, bmaxy = base.bounds
    assert bminx <= tminx and bminy <= tminy and bmaxx >= tmaxx and bmaxy >= tmaxy


def test_generar_isotipo_multicolor_no_exporta_stl_de_texto():
    """`contenido is None` (isotipo 100% a color) tiene que traducirse
    en `ruta_stl_texto=None`/`vertices_texto=None` en el resultado de
    `generar()` -- no un STL vacío ni una excepción."""
    import tempfile
    with tempfile.TemporaryDirectory() as carpeta_tmp:
        r = llavero.generar(
            nombre="", ruta_ttf=FUENTE, alto_mm=20, modo_logo="isotipo",
            decoracion_multicolor_ruta=FIXTURE_4_COLORES,
            colores_asignados_icono=["Rojo", "Verde Lima", "Azul", "Amarillo"],
            tiene_ams=False, carpeta_salida=carpeta_tmp,
        )
        assert r["ruta_stl_texto"] is None
        assert r["vertices_texto"] is None
        assert r["watertight_texto"] is True
        assert len(r["rutas_stl_icono"]) == 4
        assert os.path.isfile(r["ruta_stl_base"])


def test_isotipo_emblema_monograma_ignoran_multicolor_sin_romper():
    """Emblema/monograma: no soportado todavía (ver docstring) -- pasar
    `decoracion_multicolor_ruta` no debe romper nada, simplemente no lo
    usa (`piezas_icono` vacío)."""
    _, _, _, _, piezas_monograma = llavero._armar_geometria(
        "AB", FUENTE, 20, "ninguno", "derecha", 7, 0, 0, "izquierda", 2, 3, 300,
        modo_logo="monograma", decoracion_multicolor_ruta=FIXTURE_4_COLORES,
    )
    assert piezas_monograma == []

    _, _, _, _, piezas_emblema = llavero._armar_geometria(
        "AB", FUENTE, 20, "ninguno", "derecha", 7, 0, 0, "izquierda", 2, 3, 300,
        decoracion_svg=FIXTURE_4_COLORES, modo_logo="emblema",
        decoracion_multicolor_ruta=FIXTURE_4_COLORES,
    )
    assert piezas_emblema == []


def test_sin_multicolor_sigue_dando_piezas_icono_vacio():
    """Regla de no-regresión explícita: sin `decoracion_multicolor_ruta`,
    `piezas_icono` es SIEMPRE `[]` -- el ícono (de la lista, en este
    caso "corazon") sigue fusionado en `contenido` como siempre."""
    contenido, base, ancho_mm, alto_mm_real, piezas_icono = _armar("imagotipo")
    assert piezas_icono == []
    assert contenido.area > 0


def test_generar_sin_ams_exporta_un_stl_por_color_del_icono():
    import tempfile
    with tempfile.TemporaryDirectory() as carpeta_tmp:
        r = llavero.generar(
            nombre="Ana", ruta_ttf=FUENTE, alto_mm=20,
            decoracion_multicolor_ruta=FIXTURE_4_COLORES,
            colores_asignados_icono=["Rojo", "Verde Lima", "Azul", "Amarillo"],
            tiene_ams=False, carpeta_salida=carpeta_tmp,
        )
        assert len(r["rutas_stl_icono"]) == 4
        assert r["colores_icono"] == ["#ff0000", "#00ff00", "#0000ff", "#ffff00"]
        for ruta in r["rutas_stl_icono"]:
            assert os.path.isfile(ruta) and os.path.getsize(ruta) > 0
        assert os.path.isfile(r["ruta_stl_base"])
        assert os.path.isfile(r["ruta_stl_texto"])
        assert r["ruta_stl_multicolor"] is None and r["ruta_3mf_multicolor"] is None
        assert any("4 STL suelto" in nota for nota in r["info"])


def test_generar_con_ams_combina_base_texto_e_icono_en_el_3mf():
    import tempfile
    with tempfile.TemporaryDirectory() as carpeta_tmp:
        r = llavero.generar(
            nombre="Ana", ruta_ttf=FUENTE, alto_mm=20,
            decoracion_multicolor_ruta=FIXTURE_4_COLORES, decoracion_multicolor_indices=[0, 1],
            colores_asignados_icono=["Rojo", "Verde Lima"],
            tiene_ams=True, carpeta_salida=carpeta_tmp,
        )
        assert r["ruta_3mf_multicolor"] and os.path.isfile(r["ruta_3mf_multicolor"])
        assert r["ruta_stl_multicolor"] and os.path.isfile(r["ruta_stl_multicolor"])
        assert len(r["rutas_stl_icono"]) == 2
        assert "e ícono" in r["info"][0]


def test_generar_sin_decoracion_multicolor_es_identico_a_antes():
    """Regresión de la Parte 2 sobre el caso de siempre (sin ícono a
    color): `rutas_stl_icono`/`colores_icono` vacíos, sin mención de
    ícono en el aviso -- ídem comportamiento previo a esta Parte."""
    import tempfile
    with tempfile.TemporaryDirectory() as carpeta_tmp:
        r = llavero.generar(nombre="Bianca", ruta_ttf=FUENTE, alto_mm=20, tiene_ams=False, carpeta_salida=carpeta_tmp)
        assert r["rutas_stl_icono"] == []
        assert r["colores_icono"] == []
        assert not any("ícono" in nota for nota in r["info"])
        assert os.path.isfile(r["ruta_stl_base"]) and os.path.isfile(r["ruta_stl_texto"])


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
