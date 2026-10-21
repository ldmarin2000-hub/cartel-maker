#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_collar_placas.py
------------------
Red de regresión para la salida agrupada por color del collar (`generators/collar.py`,
`formato_salida="por_color"`): un STL con todas las bases, otro con todas las letras y otro
con todos los separadores, con las piezas ya acomodadas en la cama de la A1 (y partidas en
placas si no entran), más un mapa numerado de cada placa.

No usa pytest (ver AGENTS.md "Testing") -- funciones `test_*` con
`assert` simple, corribles con `python tests/test_collar_placas.py`.
"""
import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import trimesh

from generators import collar

FUENTE = os.path.join("fonts", "curadas", "Anton.ttf")
ESTRELLA = {"tipo": "forma", "forma": {"nombre": "estrella"}}
CORAZON = {"tipo": "forma", "forma": {"nombre": "corazon"}}
SEPARADORES_ME_RECIBI = {
    "inicio": ESTRELLA, "final": ESTRELLA, "entre_letras": "cilindro", "entre_palabras": CORAZON}
SEP, MARGEN, CAMA = collar.SEPARACION_PLACA_MM, collar.MARGEN_CAMA_MM, collar.CAMA_MM


def _cajas_sin_pisarse(centros_y_tamanos, tolerancia=1e-6):
    """Las cajas (cx, cy, w, h) de UNA placa no se pisan y entre vecinas queda al menos `SEP`."""
    for i, (x1, y1, w1, h1) in enumerate(centros_y_tamanos):
        for x2, y2, w2, h2 in centros_y_tamanos[i + 1:]:
            hueco_x = abs(x1 - x2) - (w1 + w2) / 2
            hueco_y = abs(y1 - y2) - (h1 + h2) / 2
            if max(hueco_x, hueco_y) < SEP - tolerancia:
                return False
    return True


def _generar(texto="ME RECIBI", **kwargs):
    """Genera en una carpeta temporal y carga lo que hace falta ANTES de que se borre."""
    kwargs.setdefault("ruta_ttf", FUENTE)
    with tempfile.TemporaryDirectory() as carpeta:
        r = collar.generar(texto, carpeta_salida=carpeta, prefijo="t", **kwargs)
        r["_nombres"] = [os.path.basename(p["ruta_stl"]) for p in r["piezas"]]
        r["_mallas"] = {os.path.basename(p["ruta_stl"]): trimesh.load(p["ruta_stl"]) for p in r["piezas"]}
        r["_mapas"] = {os.path.basename(m["ruta_png"]): os.path.getsize(m["ruta_png"]) for m in r["mapas"]}
        r["_todos_los_archivos"] = sorted(os.listdir(carpeta))
    return r


def _cuerpos(malla):
    return malla.split(only_watertight=False)


# --- acomodar_en_placas -----------------------------------------------------------

def test_acomodo_en_filas_de_izquierda_a_derecha_y_de_arriba_abajo():
    colocacion, no_entran = collar.acomodar_en_placas([(100, 100)] * 3)
    assert no_entran == []
    # el área útil mide 240: caben 2 de 100 (+4 de aire) por fila; la tercera va en la fila de abajo
    assert colocacion[0] == (1, MARGEN + 50, CAMA - MARGEN - 50)
    assert colocacion[1] == (1, MARGEN + 100 + SEP + 50, CAMA - MARGEN - 50)
    assert colocacion[2] == (1, MARGEN + 50, CAMA - MARGEN - 100 - SEP - 50)


def test_acomodo_parte_en_placas_cuando_no_entra():
    colocacion, _ = collar.acomodar_en_placas([(100, 100)] * 5)   # 4 por placa
    assert [c[0] for c in colocacion] == [1, 1, 1, 1, 2]
    assert colocacion[4][1:] == (MARGEN + 50, CAMA - MARGEN - 50), "la placa nueva arranca arriba a la izquierda"


def test_acomodo_nunca_pisa_piezas_ni_se_sale_de_la_cama_y_conserva_el_orden():
    azar = random.Random(7)
    tamanos = [(azar.uniform(8, 70), azar.uniform(8, 70)) for _ in range(60)]
    colocacion, no_entran = collar.acomodar_en_placas(tamanos)
    assert no_entran == []
    placas = {}
    for (w, h), (placa, cx, cy) in zip(tamanos, colocacion):
        assert MARGEN - 1e-9 <= cx - w / 2 and cx + w / 2 <= CAMA - MARGEN + 1e-9, "se sale de la cama en X"
        assert MARGEN - 1e-9 <= cy - h / 2 and cy + h / 2 <= CAMA - MARGEN + 1e-9, "se sale de la cama en Y"
        placas.setdefault(placa, []).append((cx, cy, w, h))
    assert len(placas) > 1, "con 60 piezas tenían que hacer falta varias placas"
    for placa, cajas in placas.items():
        assert _cajas_sin_pisarse(cajas), f"hay piezas pisadas o pegadas en la placa {placa}"
    numeros = [c[0] for c in colocacion]
    assert numeros == sorted(numeros), "las placas no respetan el orden de las piezas"


def test_acomodo_avisa_de_la_pieza_que_no_entra_pero_no_la_pierde():
    colocacion, no_entran = collar.acomodar_en_placas([(20, 20), (300, 10), (20, 20)])
    assert no_entran == [1]
    assert len(colocacion) == 3


# --- generar(formato_salida="por_color") ----------------------------------------------

def test_por_color_da_tres_archivos_con_todas_las_piezas():
    r = _generar(separadores=SEPARADORES_ME_RECIBI, formato_salida="por_color")
    assert sorted(r["_nombres"]) == ["t_bases.stl", "t_letras.stl", "t_separadores.stl"]
    assert [p["salida"] for p in r["piezas"]] == ["por_color"] * 3
    # M E R E C I B I -> 8 cuentas; * M - E ♥ R - E - C - I - B - I * -> 9 separadores (2 estrellas, 1 corazón, 6 cilindros)
    assert len(_cuerpos(r["_mallas"]["t_bases.stl"])) == 8
    assert len(_cuerpos(r["_mallas"]["t_letras.stl"])) == 8
    assert len(_cuerpos(r["_mallas"]["t_separadores.stl"])) == 9
    assert {p["tipo"]: p["cantidad"] for p in r["piezas"]} == {"bases": 8, "letras": 8, "separadores": 9}
    assert r["avisos"] == []


def test_por_color_incluye_todas_las_copias_aunque_se_pida_agrupar_repetidas():
    """Las dos E y las dos I salen cada una en su lugar: agrupar repetidas solo existe para 'por pieza'."""
    r = _generar(formato_salida="por_color", agrupar_repetidas=True)
    assert len(_cuerpos(r["_mallas"]["t_bases.stl"])) == 8
    assert len(_cuerpos(r["_mallas"]["t_letras.stl"])) == 8


def test_por_color_las_piezas_estan_en_la_cama_apoyadas_y_sin_pisarse():
    r = _generar(separadores=SEPARADORES_ME_RECIBI, formato_salida="por_color")
    for nombre, malla in r["_mallas"].items():
        assert malla.is_watertight, nombre
        assert abs(malla.bounds[0][2]) < 1e-6, f"{nombre} no apoya en Z=0"
        cajas = []
        for cuerpo in _cuerpos(malla):
            (x0, y0, z0), (x1, y1, z1) = cuerpo.bounds
            assert abs(z0) < 1e-6, f"{nombre}: una pieza flota"
            assert x0 >= MARGEN - 1e-6 and x1 <= CAMA - MARGEN + 1e-6, f"{nombre}: se sale de la cama en X"
            assert y0 >= MARGEN - 1e-6 and y1 <= CAMA - MARGEN + 1e-6, f"{nombre}: se sale de la cama en Y"
            cajas.append(((x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0))
        assert _cajas_sin_pisarse(cajas), f"{nombre}: hay piezas pisadas o demasiado juntas"


def test_por_color_cada_pieza_conserva_su_forma():
    """Acomodar no deforma: el volumen del archivo es el de las piezas sueltas sumadas."""
    suelta = _generar(separadores=SEPARADORES_ME_RECIBI, formato_salida="por_pieza")
    junta = _generar(separadores=SEPARADORES_ME_RECIBI, formato_salida="por_color")
    volumen_bases = sum(m.volume for n, m in suelta["_mallas"].items() if "_base" in n)
    volumen_letras = sum(m.volume for n, m in suelta["_mallas"].items() if "_letra" in n)
    volumen_sep = sum(m.volume for n, m in suelta["_mallas"].items() if "_separador_" in n)
    assert abs(junta["_mallas"]["t_bases.stl"].volume - volumen_bases) / volumen_bases < 1e-6
    assert abs(junta["_mallas"]["t_letras.stl"].volume - volumen_letras) / volumen_letras < 1e-6
    assert abs(junta["_mallas"]["t_separadores.stl"].volume - volumen_sep) / volumen_sep < 1e-6


def test_por_color_la_letra_queda_en_su_placa_donde_esta_su_base():
    r = _generar(formato_salida="por_color")
    bases = next(p for p in r["piezas"] if p["tipo"] == "bases")
    letras = next(p for p in r["piezas"] if p["tipo"] == "letras")
    assert bases["posiciones"] == letras["posiciones"] == [1, 2, 3, 4, 5, 6, 7, 8]
    for pos, (bx, by), (lx, ly) in zip(bases["posiciones"], bases["centros"], letras["centros"]):
        assert abs(bx - lx) < 1.0 and abs(by - ly) < 1.0, f"la letra {pos} no está sobre su base ({bx:.1f},{by:.1f} vs {lx:.1f},{ly:.1f})"


def test_por_color_la_letra_cae_dentro_de_su_base_no_solo_cerca():
    """Cada letra tiene que quedar encima del hueco de SU base: se ve en cuerpos, no en centros."""
    r = _generar("MIR", formato_salida="por_color")
    bases = sorted(_cuerpos(r["_mallas"]["t_bases.stl"]), key=lambda c: -c.bounds[1][1] * 1000 + c.bounds[0][0])
    letras = sorted(_cuerpos(r["_mallas"]["t_letras.stl"]), key=lambda c: -c.bounds[1][1] * 1000 + c.bounds[0][0])
    assert len(bases) == len(letras) == 3
    for base, letra in zip(bases, letras):
        assert base.bounds[0][0] <= letra.bounds[0][0] and letra.bounds[1][0] <= base.bounds[1][0]
        assert base.bounds[0][1] <= letra.bounds[0][1] and letra.bounds[1][1] <= base.bounds[1][1]


def test_por_color_parte_en_placas_si_no_entra_todo():
    """10 cuentas de 70 mm: entran 9 por placa (3 x 3), la décima va a la segunda. Las letras siguen la
    misma partición."""
    r = _generar("ABCDEFGHIJ", formato_salida="por_color")
    esperados = {"t_bases_placa1.stl", "t_bases_placa2.stl", "t_letras_placa1.stl", "t_letras_placa2.stl"}
    assert esperados <= set(r["_nombres"]), sorted(r["_nombres"])
    assert not {"t_bases.stl", "t_letras.stl"} & set(r["_nombres"]), "con varias placas no debería haber un archivo sin número"
    for tipo in ("bases", "letras"):
        placas = {p["placa"]: p["posiciones"] for p in r["piezas"] if p["tipo"] == tipo}
        assert placas == {1: [1, 2, 3, 4, 5, 6, 7, 8, 9], 2: [10]}, (tipo, placas)
        assert all(p["n_placas"] == 2 for p in r["piezas"] if p["tipo"] == tipo)
    assert any("no entran en una sola placa" in a and "2 placas" in a for a in r["avisos"]), r["avisos"]


def test_por_color_avisa_si_una_pieza_no_entra_en_la_cama():
    r = _generar("A", formato_salida="por_color", diametro=300, alto_letra_mm=100)
    assert any("no entra en la cama" in a for a in r["avisos"]), r["avisos"]


def test_por_color_en_modo_sticker_no_tiene_letras():
    r = _generar("ME RECIBI", modo_cuenta="sticker", rebaje_sticker_diametro=50, formato_salida="por_color",
                 separadores={"entre_letras": "cilindro"})
    assert sorted(r["_nombres"]) == ["t_bases.stl", "t_separadores.stl"]
    assert len(_cuerpos(r["_mallas"]["t_bases.stl"])) == 8


def test_por_color_sin_separadores_son_solo_bases_y_letras():
    r = _generar("AB", formato_salida="por_color")
    assert sorted(r["_nombres"]) == ["t_bases.stl", "t_letras.stl"]


def test_por_color_cada_placa_trae_su_mapa():
    r = _generar("ABCDEFGHIJ", separadores={"entre_letras": "cilindro"}, formato_salida="por_color")
    esperados = {"t_bases_placa1_mapa.png", "t_bases_placa2_mapa.png", "t_letras_placa1_mapa.png",
                 "t_letras_placa2_mapa.png", "t_separadores_mapa.png"}
    assert esperados <= set(r["_mapas"]), sorted(r["_mapas"])
    assert all(tam > 2000 for tam in r["_mapas"].values()), "algún mapa salió vacío"
    assert esperados <= set(r["_todos_los_archivos"])
    assert len(r["mapas"]) == len(r["_mapas"])


def test_por_color_los_colores_son_los_de_cada_grupo():
    r = _generar(formato_salida="por_color", color_cuenta="Azul", color_letra="Rosa", color_separador="Verde Lima",
                 separadores={"entre_letras": "cilindro"})
    por_tipo = {p["tipo"]: p["color"] for p in r["piezas"]}
    assert por_tipo == {"bases": "Azul", "letras": "Rosa", "separadores": "Verde Lima"}


# --- ambos / por_pieza / validación -------------------------------------------------------

def test_ambos_exporta_los_dos_juegos():
    r = _generar("AB", separadores={"entre_letras": "cilindro"}, formato_salida="ambos")
    por_pieza = [p for p in r["piezas"] if p["salida"] == "por_pieza"]
    por_color = [p for p in r["piezas"] if p["salida"] == "por_color"]
    assert len(por_pieza) == 2 * 2 + 1 and len(por_color) == 3
    assert {"t_bases.stl", "t_letras.stl", "t_separadores.stl"} <= set(r["_nombres"])
    assert any("_cuenta_A_base" in n for n in r["_nombres"])


def test_por_pieza_sigue_siendo_el_formato_por_defecto_y_no_genera_placas():
    r = _generar("AB", separadores={"entre_letras": "cilindro"})
    assert r["formato_salida"] == "por_pieza"
    assert all(p["salida"] == "por_pieza" for p in r["piezas"])
    assert r["mapas"] == [] and not any(n.endswith("_mapa.png") for n in r["_todos_los_archivos"])


def test_formato_de_salida_invalido_da_error():
    try:
        _generar("A", formato_salida="en_un_zip")
    except ValueError as e:
        assert "formato_salida" in str(e)
        return
    raise AssertionError("tenía que fallar con un formato inválido")


def test_por_color_funciona_con_medidas_de_pulsera_y_forma_de_letra():
    medidas = collar.medidas_de("pulsera")
    medidas["alto_letra_mm"] = 14.0
    r = _generar("RIKANDI", forma_cuenta="letra", formato_salida="por_color",
                 separadores={"inicio": CORAZON, "final": CORAZON}, **medidas)
    assert len(_cuerpos(r["_mallas"]["t_bases.stl"])) == 7
    assert len(_cuerpos(r["_mallas"]["t_letras.stl"])) == 7
    assert len(_cuerpos(r["_mallas"]["t_separadores.stl"])) == 2
    assert all(p["n_placas"] == 1 for p in r["piezas"]), "una pulsera tiene que entrar en una placa"
    assert r["avisos"] == []


# --- mapa ------------------------------------------------------------------------------

def test_color_de_texto_contrasta_con_la_pieza():
    assert collar._color_de_texto_sobre("#F4F4F2") == "#111111"   # blanco -> texto oscuro
    assert collar._color_de_texto_sobre("#1A1A1A") == "#ffffff"   # negro -> texto claro


def test_mapa_de_placa_se_dibuja_con_siluetas_con_huecos():
    caja = trimesh.creation.box([20, 20, 5])
    caja.apply_translation([30, 30, 2.5])
    anillo = trimesh.creation.annulus(r_min=4, r_max=10, height=3)   # una "O": tiene que dibujarse con su agujero
    anillo.apply_translation([70, 30, 1.5])
    with tempfile.TemporaryDirectory() as carpeta:
        ruta = os.path.join(carpeta, "mapa.png")
        salida = collar.dibujar_mapa_placa(
            ruta, [{"malla": caja, "texto": "1\nA", "color_hex": "#ffffff"},
                   {"malla": anillo, "texto": "2\nO", "color_hex": "#1a1a1a"}], "prueba")
        assert salida == ruta and os.path.getsize(ruta) > 2000
    poligonos = collar._poligonos_del_corte(anillo.section(plane_origin=[0, 0, 0.35 + anillo.bounds[0][2]], plane_normal=[0, 0, 1]))
    assert len(poligonos) == 1 and len(poligonos[0].interiors) == 1, "la O perdió su hueco"
    assert abs(poligonos[0].area - 3.14159 * (100 - 16)) < 3


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
