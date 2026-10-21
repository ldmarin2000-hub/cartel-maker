#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_collar_secuencia.py
------------------
Red de regresión para el resto del collar (`generators/collar.py`):
separadores (cilindro y de forma), armado de la secuencia desde el
texto, y `generar()` de punta a punta (STL por pieza distinta, cantidades,
modo sticker, alineación del armado).

La cuenta en sí está en `tests/test_collar_cuenta.py`.

No usa pytest (ver AGENTS.md "Testing") -- funciones `test_*` con
`assert` simple, corribles con `python tests/test_collar_secuencia.py`.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import trimesh
from shapely.geometry import box

from generators import collar

FUENTE = os.path.join("fonts", "curadas", "Anton.ttf")
FIXTURE_SVG = os.path.join("tests", "_fixture_escudo_union.svg")
ESTRELLA = {"tipo": "forma", "forma": {"nombre": "estrella"}}
CORAZON = {"tipo": "forma", "forma": {"nombre": "corazon"}}


def _adentro(malla, x, y, z):
    return bool(malla.contains([[x, y, z]])[0])


def _como_texto(secuencia):
    """'*' separador de forma, '-' cilindro, '.' entre palabras, y las letras tal cual
    (para leer la secuencia de un vistazo)."""
    simbolo = {"cilindro": "-", "forma": "*"}
    return "".join(i["caracter"] if i["tipo"] == "cuenta" else simbolo[i["sep"]["tipo"]] for i in secuencia)


# --- secuencia ----------------------------------------------------------------

def test_secuencia_sin_separadores_es_una_cuenta_por_letra():
    s = collar.armar_secuencia("ME RECIBI")
    assert _como_texto(s) == "MERECIBI"
    assert all(i["tipo"] == "cuenta" for i in s)


def test_secuencia_con_separadores_en_los_cuatro_lugares():
    s = collar.armar_secuencia("ME RECIBI", {
        "inicio": ESTRELLA, "final": ESTRELLA, "entre_letras": "cilindro", "entre_palabras": CORAZON})
    assert _como_texto(s) == "*M-E*R-E-C-I-B-I*"


def test_entre_palabras_igual_a_entre_letras_si_no_se_pide_otra_cosa():
    s = collar.armar_secuencia("AB CD", {"entre_letras": "cilindro"})
    assert _como_texto(s) == "A-B-C-D"
    assert [i["slot"] for i in s if i["tipo"] == "separador"] == ["entre_letras", "entre_palabras", "entre_letras"]


def test_entre_palabras_ninguno_deja_las_palabras_pegadas():
    s = collar.armar_secuencia("AB CD", {"entre_letras": "cilindro", "entre_palabras": "ninguno"})
    assert _como_texto(s) == "A-BC-D"


def test_varios_espacios_cuentan_como_uno_y_los_de_las_puntas_se_ignoran():
    assert _como_texto(collar.armar_secuencia("  AB   CD ", {"entre_palabras": ESTRELLA})) == "AB*CD"


def test_una_sola_letra_con_separadores_de_punta():
    assert _como_texto(collar.armar_secuencia("A", {"inicio": "cilindro", "final": "cilindro"})) == "-A-"


def test_secuencia_valida_los_pedidos():
    casos = [
        lambda: collar.armar_secuencia("   "),
        lambda: collar.armar_secuencia(""),
        lambda: collar.armar_secuencia("AB", {"izquierda": "cilindro"}),
        lambda: collar.armar_secuencia("AB", {"entre_letras": "bolita"}),
        lambda: collar.armar_secuencia("AB", {"entre_letras": {"tipo": "forma"}}),
        lambda: collar.armar_secuencia("AB", {"inicio": "igual"}),  # "igual" solo existe para entre_palabras
    ]
    for caso in casos:
        try:
            caso()
        except ValueError:
            continue
        raise AssertionError("tenía que fallar")


# --- separador cilindro -------------------------------------------------------

def test_separador_cilindro_es_un_tubo_con_el_agujero_a_lo_largo_del_eje():
    malla, avisos = collar.armar_separador_cilindro(28, 10, 10, "rombo", 1.0)
    assert malla.is_watertight and malla.is_volume and avisos == []
    assert abs(malla.bounds[0][2]) < 1e-6 and abs(malla.bounds[1][2] - 10) < 1e-6
    assert abs(malla.extents[0] - 28) < 0.05 and abs(malla.extents[1] - 28) < 0.05
    assert not _adentro(malla, 0, 0, 5), "el centro tiene que estar vacío (por ahí pasa el hilo)"
    assert not _adentro(malla, 0, 0, 0.2) and not _adentro(malla, 0, 0, 9.8), "el agujero no cruza de punta a punta"
    assert _adentro(malla, 11, 0, 5), "la pared del tubo tiene que ser sólida"


def test_separador_cilindro_acepta_los_tres_perfiles():
    for perfil in collar.PERFILES_AGUJERO_SEPARADOR:
        malla, _ = collar.armar_separador_cilindro(28, 10, 10, perfil)
        assert malla.is_watertight and malla.is_volume, perfil
        assert not _adentro(malla, 0, 0, 5), perfil


def test_separador_cilindro_agujero_que_no_entra_da_error_y_pared_fina_avisa():
    try:
        collar.armar_separador_cilindro(28, 10, 30)
    except ValueError:
        pass
    else:
        raise AssertionError("un agujero más grande que el cuerpo tenía que fallar")
    _, avisos = collar.armar_separador_cilindro(28, 10, 24, "redondo")
    assert avisos == [], "pared de 2 mm: justa pero alcanza, no debería avisar"
    _, avisos = collar.armar_separador_cilindro(28, 10, 26, "redondo")
    assert avisos, "pared de 1 mm tenía que dar aviso"


# --- contorno de forma / separador de forma -----------------------------------

def test_contorno_forma_mide_lo_pedido_y_queda_centrado():
    for nombre in ("estrella", "corazon", "flor"):
        c = collar.contorno_forma(80, nombre=nombre)
        minx, miny, maxx, maxy = c.bounds
        assert abs(max(maxx - minx, maxy - miny) - 80) < 0.01, nombre
        assert abs((minx + maxx) / 2) < 0.01 and abs((miny + maxy) / 2) < 0.01, nombre


def test_contorno_forma_sin_material_en_el_centro_se_recentra_para_que_pase_el_agujero():
    """La luna es un creciente: el centro de su caja cae en el hueco. El origen
    (por donde pasa el hilo) tiene que quedar sobre material igual."""
    from shapely.geometry import Point
    luna = collar.contorno_forma(80, nombre="luna")
    assert luna.contains(Point(0, 0))
    assert abs(max(luna.bounds[2] - luna.bounds[0], luna.bounds[3] - luna.bounds[1]) - 80) < 0.01
    malla, _ = collar.armar_separador_forma(luna, 30, 6, angulo_agujero=0)
    assert malla.is_watertight and malla.is_volume
    assert not _adentro(malla, 0, 0, 15), "el hilo no pasa por la luna"


def test_contorno_forma_desde_svg_y_pedido_invalido():
    c = collar.contorno_forma(60, ruta_svg=FIXTURE_SVG)
    minx, miny, maxx, maxy = c.bounds
    assert abs(max(maxx - minx, maxy - miny) - 60) < 0.01
    assert abs((minx + maxx) / 2) < 0.01 and abs((miny + maxy) / 2) < 0.01
    assert collar.contorno_forma(50, nombre="ninguno") is None
    try:
        collar.contorno_forma(50)
    except ValueError:
        return
    raise AssertionError("sin nombre ni svg tenía que fallar")


def test_ancho_minimo_en_el_paso():
    rect = box(-20, -5, 20, 5)  # 40 x 10
    assert abs(collar.ancho_minimo_en_el_paso(rect, 0) - 10) < 1e-6      # el agujero corre a lo largo: ancho 10
    assert collar.ancho_minimo_en_el_paso(rect, 90) > 39                 # cruza el lado corto: ancho 40
    from shapely.geometry import Point
    circulo = Point(0, 0).buffer(15, quad_segs=32)
    for ang in (0, 45, 90):
        assert collar.ancho_minimo_en_el_paso(circulo, ang) > 8, ang  # al borde se angosta, pero es el círculo


def test_separador_de_forma_es_una_cuenta_con_otro_contorno():
    contorno = collar.contorno_forma(80, nombre="corazon")
    malla, avisos = collar.armar_separador_forma(contorno, alto=30, agujero=8, angulo_agujero=0)
    assert malla.is_watertight and malla.is_volume and avisos == []
    assert abs(malla.bounds[0][2]) < 1e-6 and abs(malla.bounds[1][2] - 30) < 1e-6
    assert not _adentro(malla, 0, 0, 15), "el centro tiene que estar vacío"
    assert not _adentro(malla, 20, 0, 15) and not _adentro(malla, -20, 0, 15), "el agujero cruza a lo largo de X"
    assert _adentro(malla, 0, 0, 28), "arriba del agujero hay material"


def test_separador_de_forma_avisa_si_el_agujero_revienta_el_costado():
    estrella = collar.contorno_forma(80, nombre="estrella")
    _, bien = collar.armar_separador_forma(estrella, 30, 8, angulo_agujero=0)
    _, punta = collar.armar_separador_forma(estrella, 30, 8, angulo_agujero=90)  # sale por una punta
    _, grande = collar.armar_separador_forma(estrella, 30, 14, angulo_agujero=0)
    assert bien == []
    assert punta and "angosta" in punta[0]
    assert grande and "angosta" in grande[0]


def test_separador_de_forma_avisa_si_el_agujero_se_come_el_alto():
    corazon = collar.contorno_forma(80, nombre="corazon")
    _, avisos = collar.armar_separador_forma(corazon, alto=12, agujero=10)
    assert any("pared arriba o abajo" in a for a in avisos)


def test_separador_de_forma_orientado_a_45_grados_cruza_en_diagonal():
    contorno = collar.contorno_forma(80, nombre="corazon")
    d = 8 / np.sqrt(2) * 1.5
    en_diagonal, _ = collar.armar_separador_forma(contorno, 30, 8, angulo_agujero=45)
    en_horizontal, _ = collar.armar_separador_forma(contorno, 30, 8, angulo_agujero=0)
    assert en_diagonal.is_watertight and en_diagonal.is_volume
    assert not _adentro(en_diagonal, d, d, 15), "el agujero tiene que pasar por la diagonal"
    assert _adentro(en_horizontal, d, d, 15), "(control) a 0° ese punto es material"


# --- generar() de punta a punta -----------------------------------------------

def _generar(texto="ME RECIBI", **kwargs):
    with tempfile.TemporaryDirectory() as carpeta:
        kwargs.setdefault("ruta_ttf", FUENTE)
        r = collar.generar(texto, carpeta_salida=carpeta, prefijo="t", **kwargs)
        # leer las mallas ANTES de que se borre la carpeta
        r["_mallas"] = [trimesh.load(p["ruta_stl"]) for p in r["piezas"]]
        r["_nombres"] = [os.path.basename(p["ruta_stl"]) for p in r["piezas"]]
        return r


def test_generar_agrupado_deduplica_y_cuenta():
    r = _generar(agrupar_repetidas=True, separadores={
        "inicio": ESTRELLA, "final": ESTRELLA, "entre_letras": "cilindro", "entre_palabras": CORAZON})
    assert r["n_cuentas"] == 8 and r["n_separadores"] == 9
    por_nombre = dict(zip(r["_nombres"], r["piezas"]))
    # M E R E C I B I -> 6 letras distintas (E x2, I x2), cada una con base y letra
    for nombre in ("t_cuenta_02_E_base_x2.stl", "t_cuenta_02_E_letra_x2.stl",
                   "t_cuenta_05_I_base_x2.stl", "t_cuenta_05_I_letra_x2.stl",
                   "t_cuenta_01_M_base.stl", "t_cuenta_01_M_letra.stl"):
        assert nombre in por_nombre, (nombre, sorted(por_nombre))
    assert por_nombre["t_separador_cilindro_x6.stl"]["cantidad"] == 6   # M-E R-E E-C C-I I-B B-I
    assert por_nombre["t_separador_estrella_x2.stl"]["cantidad"] == 2
    assert por_nombre["t_separador_corazon.stl"]["cantidad"] == 1
    assert len(r["piezas"]) == 6 * 2 + 3
    assert r["avisos"] == []


def test_generar_todas_las_piezas_son_watertight_y_apoyan_en_la_cama():
    r = _generar(separadores={"inicio": ESTRELLA, "entre_letras": "cilindro", "entre_palabras": CORAZON})
    for pieza, malla in zip(r["piezas"], r["_mallas"]):
        assert pieza["watertight"] and malla.is_watertight, pieza["etiqueta"]
        assert abs(malla.bounds[0][2]) < 1e-6, f"{pieza['etiqueta']} no apoya en Z=0"


def test_generar_largo_del_collar_es_la_suma_de_las_piezas():
    r = _generar("AB", diametro=70, separadores={"entre_letras": "cilindro"}, sep_largo=10)
    assert abs(r["largo_mm"] - (70 + 10 + 70)) < 0.1


def test_generar_el_armado_enfila_todo_sobre_el_mismo_hilo():
    """Cuentas y separadores quedan en fila a lo largo de X con el agujero
    alineado: el hilo (recta Y=0, Z=alto/2) no choca con ninguna pieza."""
    r = _generar("AB", separadores={"inicio": ESTRELLA, "entre_letras": "cilindro", "final": CORAZON})
    z = collar.ALTO_DEFAULT / 2
    x_prev_fin = None
    for malla, _, etiqueta in r["armado"]:
        if etiqueta.startswith("letra"):
            continue
        centro_x = (malla.bounds[0][0] + malla.bounds[1][0]) / 2
        assert not _adentro(malla, centro_x, 0, z), f"{etiqueta}: el hilo choca en su centro"
        assert abs((malla.bounds[0][1] + malla.bounds[1][1]) / 2) < 0.5, f"{etiqueta} no está centrada en Y"
        if x_prev_fin is not None:
            assert abs(malla.bounds[0][0] - x_prev_fin) < 1e-6, f"{etiqueta}: hueco o solape con la anterior"
        x_prev_fin = malla.bounds[1][0]


def test_generar_el_armado_con_angulo_acuesta_el_agujero_a_lo_largo_del_hilo():
    """Con el agujero a 45° respecto de la letra, en el armado la cuenta se
    gira para que el agujero corra a lo largo de X (y la letra gira con ella)."""
    r = _generar("A", angulo_agujero=45)
    base = next(m for m, _, e in r["armado"] if e.startswith("cuenta"))
    letra = next(m for m, _, e in r["armado"] if e.startswith("letra"))
    cx, z = (base.bounds[0][0] + base.bounds[1][0]) / 2, collar.ALTO_DEFAULT / 2
    assert not _adentro(base, cx, 0, z) and not _adentro(base, cx + 30, 0, z)
    assert _adentro(base, cx, 20, z) and _adentro(base, cx, -20, z)
    # la letra sigue pegada a su cuenta: dentro de la huella de la base
    assert base.bounds[0][0] - 1e-6 <= letra.bounds[0][0] and letra.bounds[1][0] <= base.bounds[1][0] + 1e-6


def test_generar_misma_letra_en_mayuscula_y_minuscula_no_pisa_archivos():
    """Windows no distingue mayúsculas de minúsculas en nombres de archivo:
    "e" y "E" no pueden terminar en el mismo STL."""
    r = _generar("Ee")
    nombres = [n.lower() for n in r["_nombres"]]
    assert len(nombres) == len(set(nombres)), nombres
    assert len(r["piezas"]) == 4


def test_generar_modo_sticker_agrupado_es_una_sola_pieza_repetida():
    r = _generar("ME RECIBI", modo_cuenta="sticker", rebaje_sticker_diametro=50, agrupar_repetidas=True)
    assert r["n_cuentas"] == 8
    assert len(r["piezas"]) == 1 and r["piezas"][0]["cantidad"] == 8
    assert r["_nombres"] == ["t_cuenta_lisa_x8.stl"]
    base = r["_mallas"][0]
    assert not _adentro(base, 0, 0, collar.ALTO_DEFAULT - 0.25), "el rebaje no está"
    assert all(e.startswith("cuenta") for _, _, e in r["armado"]), "el modo sticker no debería tener letras"


def test_generar_modo_sticker_sin_fuente_y_sin_rebaje_deja_la_tapa_lisa():
    r = _generar("AB", modo_cuenta="sticker", ruta_ttf=None)
    base = r["_mallas"][0]
    assert _adentro(base, 0, 0, collar.ALTO_DEFAULT - 0.25)


def test_generar_achica_todas_las_letras_juntas_si_no_entran():
    r = _generar("MW", alto_letra_mm=100)
    assert any("achiqué" in a for a in r["avisos"]), r["avisos"]
    alturas = [m.extents[1] for p, m in zip(r["piezas"], r["_mallas"]) if p["tipo"] == "letra"]
    assert max(alturas) <= 70, alturas
    # el factor fue común: la M y la W miden lo mismo de alto (sin contar el sobreimpulso)
    assert abs(alturas[0] - alturas[1]) < 1.0, alturas


def test_generar_junta_los_avisos_de_las_piezas():
    r = _generar("A", separadores={"inicio": ESTRELLA}, forma_agujero=14)
    assert any("Separador 'estrella'" in a and "angosta" in a for a in r["avisos"]), r["avisos"]


def test_generar_valida_los_parametros():
    casos = [
        (lambda: _generar("A", modo_cuenta="pegatina"), ValueError),
        (lambda: _generar("A", ruta_ttf="no/existe.ttf"), FileNotFoundError),
        (lambda: _generar("A", ruta_ttf=None), FileNotFoundError),
        (lambda: _generar("   "), ValueError),
        (lambda: _generar("A", sep_perfil="gota"), ValueError),
    ]
    for caso, error in casos:
        try:
            caso()
        except error:
            continue
        raise AssertionError(f"tenía que fallar con {error.__name__}")


# --- generar(): muestra completa (una pieza por lugar del collar) ----------------

SEPARADORES_ME_RECIBI = {
    "inicio": ESTRELLA, "final": ESTRELLA, "entre_letras": "cilindro", "entre_palabras": CORAZON}


def test_generar_completo_exporta_cada_pieza_del_collar_incluidas_las_repetidas():
    """Por defecto no se agrupa nada: M E R E C I B I son 8 cuentas con su letra
    (16 archivos), más los 9 separadores uno por uno (2 estrellas, 1 corazón y
    6 cilindros). Numerados en el orden en que van en el collar."""
    r = _generar(separadores=SEPARADORES_ME_RECIBI)
    assert r["n_cuentas"] == 8 and r["n_separadores"] == 9
    assert len(r["piezas"]) == 8 * 2 + 9
    assert all(p["cantidad"] == 1 for p in r["piezas"])
    nombres = set(r["_nombres"])
    # *M-E♥R-E-C-I-B-I*  ->  1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17
    esperados = {
        "t_01_separador_estrella.stl", "t_17_separador_estrella.stl",      # la estrella repetida: las dos
        "t_05_separador_corazon.stl",
        "t_03_separador_cilindro.stl", "t_07_separador_cilindro.stl", "t_09_separador_cilindro.stl",
        "t_11_separador_cilindro.stl", "t_13_separador_cilindro.stl", "t_15_separador_cilindro.stl",
        "t_04_cuenta_E_base.stl", "t_04_cuenta_E_letra.stl",               # la E repetida: las dos
        "t_08_cuenta_E_base.stl", "t_08_cuenta_E_letra.stl",
        "t_12_cuenta_I_base.stl", "t_12_cuenta_I_letra.stl",               # la I repetida: las dos
        "t_16_cuenta_I_base.stl", "t_16_cuenta_I_letra.stl",
        "t_02_cuenta_M_base.stl", "t_02_cuenta_M_letra.stl",
    }
    assert esperados <= nombres, sorted(esperados - nombres)
    assert len(nombres) == len(r["piezas"]), "hay dos piezas con el mismo nombre de archivo"
    assert r["avisos"] == []


def test_generar_completo_las_copias_son_identicas_y_cada_una_esta_en_su_lugar():
    r = _generar(separadores=SEPARADORES_ME_RECIBI)
    por_nombre = dict(zip(r["_nombres"], zip(r["piezas"], r["_mallas"])))
    (pieza_a, malla_a), (pieza_b, malla_b) = por_nombre["t_04_cuenta_E_base.stl"], por_nombre["t_08_cuenta_E_base.stl"]
    assert abs(malla_a.volume - malla_b.volume) < 1e-6
    assert (pieza_a["posicion"], pieza_b["posicion"]) == (4, 8)
    est_a, est_b = por_nombre["t_01_separador_estrella.stl"][1], por_nombre["t_17_separador_estrella.stl"][1]
    assert abs(est_a.volume - est_b.volume) < 1e-6
    assert por_nombre["t_01_separador_estrella.stl"][0]["posicion"] == 1


def test_generar_completo_sticker_da_una_cuenta_lisa_por_lugar():
    r = _generar("ME RECIBI", modo_cuenta="sticker", rebaje_sticker_diametro=50)
    assert r["_nombres"] == [f"t_0{i}_cuenta_lisa.stl" for i in range(1, 9)]
    assert all(p["cantidad"] == 1 for p in r["piezas"])


def test_generar_completo_la_numeracion_sigue_el_orden_del_armado():
    """El armado (visor 3D) y los archivos numerados cuentan la misma historia: la
    posición N de los archivos es la N-ésima pieza del collar enfilado."""
    r = _generar("AB", separadores={"inicio": ESTRELLA, "entre_letras": "cilindro", "final": CORAZON})
    en_archivos = [(p["posicion"], p["etiqueta"]) for p in r["piezas"] if p["tipo"] != "letra"]
    en_armado = [e for _, _, e in r["armado"] if not e.startswith("letra")]
    assert [e for _, e in en_archivos] == en_armado
    assert [pos for pos, _ in en_archivos] == [1, 2, 3, 4, 5]


def test_generar_completo_no_repite_el_mismo_aviso_por_cada_copia():
    """Una cuenta de 300 mm no entra en la A1: el aviso sale una vez por tipo de pieza, no
    una por cada copia de la letra."""
    r = _generar("EE", diametro=300, alto_letra_mm=100)
    assert len(r["piezas"]) == 4
    avisos_cuenta_e = [a for a in r["avisos"] if "cuenta E" in a and "256" in a]
    assert len(avisos_cuenta_e) == 1, r["avisos"]


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
