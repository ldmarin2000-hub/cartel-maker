#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_biblioteca_escudos.py
------------------
Red de regresión para 7C-D (idea 20 -- biblioteca de escudos).

`core/biblioteca.py` es puro (sin Streamlit) -- se testea listando una
carpeta de prueba (nunca la `biblioteca/escudos/` real del proyecto,
que puede estar vacía o tener contenido real del usuario) mediante
monkeypatch de `biblioteca.CARPETA_BIBLIOTECA`. La parte de UI (el
selector, la regla "biblioteca gana sobre upload", el fallback a
"Ninguno" si el preset apunta a un escudo borrado) vive en
pages/9_🎂_Topper.py y no tiene forma de testearse sin un runner de
Streamlit -- lo que SÍ se prueba acá, a nivel `_armar_regiones_plano`,
es que una ruta "como si viniera de la biblioteca" (una ruta de archivo
cualquiera, biblioteca o no -- el generador no distingue) combinada con
`item["multicolor"]=True` (7C-B) separa por color correctamente.

No usa pytest (ver AGENTS.md "Testing") -- funciones `test_*` con
`assert` simple, corribles con
`python tests/test_biblioteca_escudos.py`.
"""
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np

from core import biblioteca
from core import importador_escudos as imp
from generators import topper

_CARPETA_TEST = os.path.dirname(os.path.abspath(__file__))
_FIXTURE_BIBLIOTECA = os.path.join(_CARPETA_TEST, "_fixture_biblioteca_escudos")
FUENTE = os.path.join("fonts", "curadas", "Anton.ttf")


def _con_biblioteca_de_prueba(carpeta):
    """Monkeypatch de `biblioteca.CARPETA_BIBLIOTECA` -- devuelve el
    valor original para restaurarlo (nunca dejar el módulo apuntando a
    una carpeta de test entre test y test)."""
    original = biblioteca.CARPETA_BIBLIOTECA
    biblioteca.CARPETA_BIBLIOTECA = carpeta
    return original


def _crear_fixture_svgs():
    """Carpeta de prueba con 3 SVGs (nombres con "_"/"-"/mayúsculas
    para probar `_nombre_lindo`) + 1 archivo no-SVG que debe ignorarse."""
    if os.path.isdir(_FIXTURE_BIBLIOTECA):
        shutil.rmtree(_FIXTURE_BIBLIOTECA)
    os.makedirs(_FIXTURE_BIBLIOTECA)
    svg_minimo = '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10" fill="#000"/></svg>'
    for nombre in ("union_europea.svg", "escudo-argentino.svg", "LOGO.svg"):
        with open(os.path.join(_FIXTURE_BIBLIOTECA, nombre), "w", encoding="utf-8") as f:
            f.write(svg_minimo)
    with open(os.path.join(_FIXTURE_BIBLIOTECA, "notas.txt"), "w", encoding="utf-8") as f:
        f.write("esto no es un SVG, listar_escudos() no debe devolverlo")
    return _FIXTURE_BIBLIOTECA


def test_listar_escudos_carpeta_inexistente_da_lista_vacia():
    """Caso (1a): sin la carpeta creada (proyecto recién clonado, nadie
    copió escudos todavía), no debe romper -- lista vacía."""
    original = _con_biblioteca_de_prueba(os.path.join(_CARPETA_TEST, "_carpeta_que_no_existe"))
    try:
        assert biblioteca.listar_escudos() == []
    finally:
        biblioteca.CARPETA_BIBLIOTECA = original


def test_listar_escudos_devuelve_pares_correctos_ordenados_sin_no_svg():
    """Caso (1b): con SVGs de verdad -- nombres lindos correctos,
    orden alfabético por nombre lindo, el .txt no aparece."""
    carpeta = _crear_fixture_svgs()
    original = _con_biblioteca_de_prueba(carpeta)
    try:
        escudos = biblioteca.listar_escudos()
        nombres = [nombre for nombre, _ in escudos]
        assert nombres == sorted(nombres), "tiene que venir ordenado alfabéticamente"
        assert set(nombres) == {"Union Europea", "Escudo Argentino", "Logo"}
        assert len(escudos) == 3, "el .txt no-SVG no debe aparecer"
        for nombre, ruta in escudos:
            assert ruta.endswith(".svg")
            assert os.path.exists(ruta)
    finally:
        biblioteca.CARPETA_BIBLIOTECA = original
        shutil.rmtree(carpeta)


def test_nombre_lindo_casos():
    assert biblioteca._nombre_lindo("union_europea.svg") == "Union Europea"
    assert biblioteca._nombre_lindo("escudo-argentino.svg") == "Escudo Argentino"
    assert biblioteca._nombre_lindo("LOGO.svg") == "Logo"
    assert biblioteca._nombre_lindo("sin_extension") == "Sin Extension"


def test_ruta_de_biblioteca_con_multicolor_separa_por_color():
    """Caso (5): una ruta "como si viniera de la biblioteca" (el
    generador no distingue el origen -- es solo una ruta de archivo) en
    un casillero con `item["multicolor"]=True` tiene que separarse por
    color igual que un SVG subido -- mismo camino de 7C-B, sin código
    pegamento extra. No se prueba la UI (el checkbox "multicolor" en
    cada casillero es 7C-F, todavía no existe)."""
    carpeta = _crear_fixture_svgs()
    ruta_multicolor = os.path.join(_CARPETA_TEST, "_fixture_deco_4colores.svg")
    if not os.path.exists(ruta_multicolor):
        with open(ruta_multicolor, "w", encoding="utf-8") as f:
            f.write(
                '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">'
                '<rect x="0" y="0" width="50" height="50" fill="#ff0000"/>'
                '<rect x="50" y="0" width="50" height="50" fill="#00ff00"/>'
                '<rect x="0" y="50" width="50" height="50" fill="#0000ff"/>'
                '<rect x="50" y="50" width="50" height="50" fill="#ffff00"/>'
                "</svg>"
            )
    try:
        # simula "el usuario eligió este escudo de la biblioteca" -- la
        # ruta resuelta por _resolver_biblioteca sería exactamente esto.
        decoraciones = [{"svg": ruta_multicolor, "lado": "Arriba", "tam_mm": 30.0, "multicolor": True}]
        regiones, n_puentes, avisos, _colores_sugeridos = topper._armar_regiones_plano(
            lineas=["Hola"], tamaño_mm=70, fuente=FUENTE, marco="Ninguno", decoraciones=decoraciones)

        claves = sorted(k for k in regiones if k == "decoracion" or k.startswith("decoracion_"))
        assert claves == ["decoracion", "decoracion_col2", "decoracion_col3", "decoracion_col4"], claves

        colores_reales = sorted(c for _, c in topper._colores_desde_archivo(ruta_multicolor))
        assert colores_reales == ["#0000ff", "#00ff00", "#ff0000", "#ffff00"]
        for clave in claves:
            assert regiones[clave] is not None and regiones[clave].area > 0
    finally:
        shutil.rmtree(carpeta)


def test_ruta_para_nombre_casos_basicos():
    """Parte H: nombre tipeado por la usuaria -> ruta de archivo dentro
    de `CARPETA_BIBLIOTECA` -- minúsculas, espacios colapsados a "_",
    signos raros afuera, acentos conservados."""
    original = _con_biblioteca_de_prueba(os.path.join("biblioteca", "escudos"))
    try:
        assert biblioteca.ruta_para_nombre("River Plate") == os.path.join("biblioteca", "escudos", "river_plate.svg")
        assert biblioteca.ruta_para_nombre("  Boca Juniors  ") == os.path.join("biblioteca", "escudos", "boca_juniors.svg")
        assert biblioteca.ruta_para_nombre("Unión de Santa Fe") == os.path.join("biblioteca", "escudos", "unión_de_santa_fe.svg")
        assert biblioteca.ruta_para_nombre("Escudo #1 (nuevo)") == os.path.join("biblioteca", "escudos", "escudo_1_nuevo.svg")
    finally:
        biblioteca.CARPETA_BIBLIOTECA = original


def test_ruta_para_nombre_round_trip_con_nombre_lindo_en_casos_normales():
    """El nombre que ve la usuaria después en el selector del Topper
    (`_nombre_lindo` sobre el nombre de archivo) tiene que reproducir lo
    que tipeó, PARA NOMBRES NORMALES (sin preposiciones en minúscula ni
    siglas en mayúscula -- esos son límites ya existentes de
    `_nombre_lindo`, no algo que `ruta_para_nombre` deba resolver)."""
    for nombre in ("River Plate", "Boca Juniors", "Club Atlético River Plate"):
        ruta = biblioteca.ruta_para_nombre(nombre)
        nombre_archivo = os.path.basename(ruta)
        assert biblioteca._nombre_lindo(nombre_archivo) == nombre, (nombre, nombre_archivo)


def test_guardar_via_escribir_svg_queda_disponible_en_listar_escudos():
    """Milestone de H: el flujo real -- zonas sintéticas (2 colores) ->
    `armar_zonas_finales` -> `ruta_para_nombre` -> `escribir_svg` (Parte
    E, sin tocarla) -- el archivo aparece en `listar_escudos()` con el
    nombre lindo esperado, en la carpeta de la biblioteca (no en
    cualquier lado)."""
    carpeta = os.path.join(_CARPETA_TEST, "_fixture_biblioteca_guardado")
    if os.path.isdir(carpeta):
        shutil.rmtree(carpeta)
    original = _con_biblioteca_de_prueba(carpeta)
    try:
        alto, ancho = 100, 100
        zona_a = np.zeros((alto, ancho), dtype=bool)
        zona_a[:, :50] = True
        zona_b = np.zeros((alto, ancho), dtype=bool)
        zona_b[:, 50:] = True
        zonas = [("#ff0000", zona_a), ("#ffffff", zona_b)]

        zonas_finales = imp.armar_zonas_finales(zonas, huecos=[])
        ruta_destino = biblioteca.ruta_para_nombre("Escudo de Prueba")
        os.makedirs(biblioteca.CARPETA_BIBLIOTECA, exist_ok=True)
        imp.escribir_svg(zonas_finales, ancho, alto, ruta_destino)

        assert os.path.isfile(ruta_destino)
        escudos = biblioteca.listar_escudos()
        assert ("Escudo De Prueba", ruta_destino) in escudos, escudos
    finally:
        biblioteca.CARPETA_BIBLIOTECA = original
        if os.path.isdir(carpeta):
            shutil.rmtree(carpeta)


def test_ruta_para_nombre_no_pisa_sin_querer_nombres_distintos():
    """Sanity chica: dos nombres visiblemente distintos no deberían
    colisionar en la misma ruta -- si esto fallara, `ruta_para_nombre`
    estaría siendo demasiado agresiva sacando caracteres."""
    original = _con_biblioteca_de_prueba(os.path.join("biblioteca", "escudos"))
    try:
        assert biblioteca.ruta_para_nombre("River Plate") != biblioteca.ruta_para_nombre("River Plate 2")
        assert biblioteca.ruta_para_nombre("Boca") != biblioteca.ruta_para_nombre("Boca Juniors")
    finally:
        biblioteca.CARPETA_BIBLIOTECA = original


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
