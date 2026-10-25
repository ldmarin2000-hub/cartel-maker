#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_collar_agujero_separadores.py
------------------
Red de regresión para el agujero de los SEPARADORES del collar (`generators/collar.py`): tiene
su propio tamaño y su propia forma, independientes de los de la cuenta -- el cilindro con
`sep_agujero`/`sep_perfil`, y los separadores de forma (estrella, corazón...) con
`forma_agujero`/`forma_perfil`.

No usa pytest (ver AGENTS.md "Testing") -- funciones `test_*` con
`assert` simple, corribles con `python tests/test_collar_agujero_separadores.py`.
"""
import inspect
import os
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
SEPARADORES = {"entre_letras": "cilindro", "final": ESTRELLA}


def _hueco(malla, x, y, z):
    """True si en ese punto NO hay material (adentro del agujero)."""
    return not bool(malla.contains([[x, y, z]])[0])


def _generar(medidas, **kwargs):
    """Genera 'AB' con cilindro y estrella y devuelve las mallas por pieza: cuenta, cilindro, estrella."""
    with tempfile.TemporaryDirectory() as carpeta:
        r = collar.generar("AB", FUENTE, carpeta_salida=carpeta, prefijo="t", separadores=SEPARADORES,
                           formato_salida="por_pieza", **medidas, **kwargs)
        return {p["etiqueta"]: trimesh.load(p["ruta_stl"]) for p in r["piezas"]}, r


# --- medidas ---------------------------------------------------------------------

def test_los_presets_traen_un_agujero_propio_para_cada_separador():
    for tipo in collar.TIPOS_PIEZA:
        m = collar.PRESETS_MEDIDAS[tipo]
        assert m["sep_perfil"] in collar.PERFILES_AGUJERO_SEPARADOR, tipo
        assert m["forma_perfil"] in collar.PERFILES_AGUJERO, tipo
    collar_, pulsera = collar.PRESETS_MEDIDAS["collar"], collar.PRESETS_MEDIDAS["pulsera"]
    assert (collar_["sep_agujero"], collar_["forma_agujero"]) == (10.0, 8.0)       # el collar sigue como estaba
    assert (collar_["sep_perfil"], collar_["forma_perfil"]) == ("rombo", "rombo")
    # pulsera: el cilindro (se imprime parado) va redondo y 0,3 mm más grande que la cuenta; las formas, acostadas, en rombo
    assert pulsera["sep_perfil"] == "redondo" and abs(pulsera["sep_agujero"] - (pulsera["agujero"] + 0.3)) < 1e-9
    assert pulsera["forma_perfil"] == "rombo" and pulsera["forma_agujero"] == pulsera["agujero"]


def test_las_medidas_de_cada_tipo_llegan_a_generar_con_su_forma_de_agujero():
    parametros = set(inspect.signature(collar.generar).parameters)
    for tipo in collar.TIPOS_PIEZA:
        medidas = collar.medidas_de(tipo)
        assert {"sep_perfil", "forma_perfil", "sep_agujero", "forma_agujero"} <= set(medidas)
        assert set(medidas) <= parametros


# --- tamaño propio ---------------------------------------------------------------

def test_cada_agujero_tiene_su_tamano_en_la_pulsera():
    """Cuenta de 2,5 mm (rombo), cilindro de 2,8 mm (redondo), estrella de 2,5 mm (rombo). Se sondea con
    puntos: a 1,15 mm del eje hay hueco en la cuenta y en la estrella (radio 1,25), a 1,4 ya es material; en el
    cilindro el hueco llega a 1,3 mm (radio 1,4) -- un punto que sería material si tuviera el tamaño de la cuenta."""
    mallas, _ = _generar(collar.medidas_de("pulsera"))
    z = 3.5
    cuenta, estrella = mallas["cuenta A"], mallas["separador estrella"]
    assert _hueco(cuenta, 0, 1.15, z) and not _hueco(cuenta, 0, 1.4, z)
    assert _hueco(estrella, 0, 1.15, z) and not _hueco(estrella, 0, 1.4, z)
    cilindro = mallas["separador cilindro"]
    zc = cilindro.extents[2] / 2
    assert _hueco(cilindro, 1.3, 0, zc), "el agujero del cilindro no tiene su tamaño propio (2,8 mm)"
    assert not _hueco(cilindro, 1.55, 0, zc)


def test_el_agujero_del_cilindro_cambia_aunque_no_cambie_el_de_la_cuenta():
    base = collar.medidas_de("pulsera")
    chico, _ = _generar({**base, "sep_agujero": 2.0})
    grande, _ = _generar({**base, "sep_agujero": 3.4})
    for malla, esperado in ((chico, 1.0), (grande, 1.7)):
        cil = malla["separador cilindro"]
        zc = cil.extents[2] / 2
        assert _hueco(cil, esperado - 0.12, 0, zc) and not _hueco(cil, esperado + 0.2, 0, zc), esperado
        assert _hueco(malla["cuenta A"], 0, 1.15, 3.5) and not _hueco(malla["cuenta A"], 0, 1.4, 3.5), "la cuenta no se tocó"


def test_el_agujero_de_la_forma_cambia_aunque_no_cambie_el_de_la_cuenta():
    base = collar.medidas_de("pulsera")
    estrella_chica, _ = _generar({**base, "forma_agujero": 2.0, "forma_lado": 30.0})
    estrella_grande, _ = _generar({**base, "forma_agujero": 3.4, "forma_lado": 30.0})
    z = base["forma_alto"] / 2
    assert _hueco(estrella_chica["separador estrella"], 0, 0.9, z) and not _hueco(estrella_chica["separador estrella"], 0, 1.2, z)
    assert _hueco(estrella_grande["separador estrella"], 0, 1.6, z) and not _hueco(estrella_grande["separador estrella"], 0, 1.9, z)


# --- forma propia ----------------------------------------------------------------

def test_cilindro_con_agujero_redondo_o_rombo():
    """Mismo tamaño (2,8 mm): el redondo llena el círculo de radio 1,4 y el rombo solo la diagonal."""
    redondo, _ = collar.armar_separador_cilindro(7, 3, 2.8, "redondo", 0.4, pared_min=0.8)
    rombo, _ = collar.armar_separador_cilindro(7, 3, 2.8, "rombo", 0.4, pared_min=0.8)
    punto = (0.9, 0.9, 1.5)   # a 1,27 mm del centro, en diagonal
    assert _hueco(redondo, *punto), "el agujero redondo no llega a la diagonal"
    assert not _hueco(rombo, *punto), "el agujero en rombo no debería llegar a la diagonal"


def test_la_forma_del_agujero_de_la_estrella_es_propia_y_distinta_de_la_de_la_cuenta():
    """Cuenta en rombo y estrella en gota (apenas más alta: la punta de la gota sube 1,41 x el radio)."""
    base = collar.medidas_de("collar")          # agujero de la estrella: 8 mm, centro a 15 mm
    con_gota, _ = _generar({**base, "forma_perfil": "gota"}, perfil="rombo")
    con_rombo, _ = _generar({**base, "forma_perfil": "rombo"}, perfil="rombo")
    z_dentro_de_la_punta = 15 + 5.0              # la punta de la gota llega a 15 + 5,66; la del rombo, a 15 + 4
    assert _hueco(con_gota["separador estrella"], 0, 0, z_dentro_de_la_punta)
    assert not _hueco(con_rombo["separador estrella"], 0, 0, z_dentro_de_la_punta)
    # la cuenta no se enteró: sigue en rombo en los dos casos
    assert not _hueco(con_gota["cuenta A"], 0, 0, 15 + 11) and not _hueco(con_rombo["cuenta A"], 0, 0, 15 + 11)


def test_sin_forma_perfil_las_formas_siguen_usando_la_de_la_cuenta():
    """Compatibilidad: si no se pide `forma_perfil`, la estrella usa el `perfil` de la cuenta, como antes."""
    base = collar.medidas_de("collar")
    base.pop("forma_perfil")
    con_gota, _ = _generar(base, perfil="gota")
    con_rombo, _ = _generar(base, perfil="rombo")
    assert _hueco(con_gota["separador estrella"], 0, 0, 15 + 5.0)
    assert not _hueco(con_rombo["separador estrella"], 0, 0, 15 + 5.0)


def test_forma_perfil_invalido_da_error():
    for malo in ("cuadrado", "hexagono"):    # el cuadrado solo existe para el cilindro (parado)
        try:
            _generar({**collar.medidas_de("pulsera"), "forma_perfil": malo})
        except ValueError as e:
            assert "forma_perfil" in str(e)
            continue
        raise AssertionError(f"forma_perfil={malo!r} tenía que fallar")


def test_el_collar_por_defecto_sale_igual_que_antes():
    """Con el preset de collar los separadores siguen siendo: cilindro de 10 mm en rombo y estrella de 8 mm en rombo."""
    mallas, r = _generar(collar.medidas_de("collar"))
    cil = mallas["separador cilindro"]
    assert _hueco(cil, 0, 4.5, 5) and not _hueco(cil, 0, 5.5, 5)       # rombo de 10: a lo largo del eje, la diagonal llega a 5
    assert not _hueco(cil, 3.0, 3.0, 5), "el rombo no llega a la diagonal"
    assert _hueco(mallas["separador estrella"], 0, 3.6, 15) and not _hueco(mallas["separador estrella"], 0, 4.4, 15)
    assert r["avisos"] == []


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
