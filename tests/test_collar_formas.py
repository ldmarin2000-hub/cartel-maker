#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_collar_formas.py
------------------
Red de regresión para las formas de cuenta y la pulsera (`generators/collar.py`):
cuenta redonda / cuadrada con esquinas redondeadas / con la forma de la letra y un
borde, chanfle por capas, paso del hilo por varios tramos de material, medidas de
pulsera y ajuste al largo de la muñeca.

La cuenta redonda de collar está en `tests/test_collar_cuenta.py` y la secuencia en
`tests/test_collar_secuencia.py`.

No usa pytest (ver AGENTS.md "Testing") -- funciones `test_*` con
`assert` simple, corribles con `python tests/test_collar_formas.py`.
"""
import inspect
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import trimesh
from shapely.geometry import Point, box

from generators import collar

FUENTE = os.path.join("fonts", "curadas", "Anton.ttf")
P = collar.PRESETS_MEDIDAS["pulsera"]
CORAZON = {"tipo": "forma", "forma": {"nombre": "corazon"}}


def _adentro(malla, x, y, z):
    return bool(malla.contains([[x, y, z]])[0])


def _letra(c="E", alto_mm=14.0):
    return collar.letra_poligono(c, FUENTE, alto_mm)


def _pulsera(poligono, **kwargs):
    """armar_cuenta con las medidas de pulsera (y lo que se quiera pisar)."""
    args = dict(diametro=P["diametro"], alto=P["alto"], agujero=P["agujero"], chanfle=P["chanfle"],
                profundidad_hueco=P["profundidad_hueco"], holgura=P["holgura"], pared_min=P["pared_min"])
    args.update(kwargs)
    return collar.armar_cuenta(poligono, **args)


# --- contornos ------------------------------------------------------------------

def test_contorno_redondo_y_cuadrado_miden_lo_pedido():
    redondo = collar.contorno_cuenta("redonda", 12)
    assert abs(redondo.area - np.pi * 36) / (np.pi * 36) < 0.002
    cuadrado = collar.contorno_cuenta("cuadrada", 12, radio_esquina=0)
    assert abs(cuadrado.area - 144) < 1e-6
    redondeado = collar.contorno_cuenta("cuadrada", 12, radio_esquina=3)
    assert tuple(round(v, 3) for v in redondeado.bounds) == (-6, -6, 6, 6)
    assert redondeado.area < 144 and abs(redondeado.area - (144 - (4 - np.pi) * 9)) < 0.05
    por_defecto = collar.contorno_cuenta("cuadrada", 12)
    assert abs(por_defecto.area - collar.contorno_cuenta("cuadrada", 12, radio_esquina=3).area) < 1e-6  # 25% del lado


def test_cuadrado_con_radio_exagerado_se_limita_a_un_circulo():
    c = collar.contorno_cuenta("cuadrada", 12, radio_esquina=50)
    assert abs(c.area - np.pi * 36) / (np.pi * 36) < 0.01


def test_contorno_con_forma_de_letra_la_envuelve_con_el_borde_pedido():
    letra = _letra("E", 14)
    borde = 1.5
    contorno = collar.contorno_cuenta("letra", 12, letra, borde_letra=borde)
    assert contorno.contains(letra)
    # todo punto de la letra queda al menos `borde` (menos tolerancia) de la orilla, y la orilla no se aleja más que eso
    assert contorno.contains(letra.buffer(borde * 0.98))
    assert letra.buffer(borde * 1.02).contains(contorno)


def test_contorno_forma_invalida_o_sin_letra_da_error():
    for args in (("hexagono", 12), ("letra", 12)):
        try:
            collar.contorno_cuenta(*args)
        except ValueError:
            continue
        raise AssertionError(f"{args} tenía que fallar")


def test_contorno_de_letra_en_pedazos_da_un_error_claro():
    """Una "i" minúscula es un trazo y un punto sueltos: con un borde chico quedan separados y la
    cuenta no puede ser una sola pieza."""
    i = collar.letra_poligono("i", FUENTE, 14)
    try:
        collar.contorno_cuenta("letra", 12, i, borde_letra=0.1)
    except ValueError as e:
        assert "pedazos" in str(e)
    else:
        raise AssertionError("tenía que fallar con la letra en pedazos")
    assert collar.contorno_cuenta("letra", 12, i, borde_letra=2.0).geom_type == "Polygon"


# --- cuenta cuadrada --------------------------------------------------------------

def test_cuenta_cuadrada_mide_lo_pedido_y_es_un_cuerpo_cerrado():
    base, _, info = _pulsera(None, forma_cuenta="cuadrada")
    assert base.is_watertight and base.is_volume
    assert [round(float(v), 3) for v in base.extents] == [12.0, 12.0, 7.0]
    # sin letra no hay hueco: la pared es la que queda entre el techo del agujero (3,5 + 1,25) y la tapa (7)
    assert abs(info["pared_mm"] - 2.25) < 1e-6 and info["avisos"] == []


def test_cuenta_cuadrada_esquinas_redondeadas_y_chanfle_por_capas():
    z = P["alto"]
    con, _, _ = _pulsera(None, forma_cuenta="cuadrada", radio_esquina=3.0, chanfle=0.4)
    recta, _, _ = _pulsera(None, forma_cuenta="cuadrada", radio_esquina=0.0, chanfle=0.0)
    esquina = (5.9, 5.9, z / 2 + 1.0)
    assert _adentro(recta, *esquina) and not _adentro(con, *esquina), "la esquina no está redondeada"
    borde_arriba = (5.95, 3.0, z - 0.05)
    assert _adentro(recta, *borde_arriba) and not _adentro(con, *borde_arriba), "el borde de arriba no tiene chanfle"
    borde_abajo = (5.95, 3.0, 0.05)
    assert not _adentro(con, *borde_abajo), "el borde de abajo no tiene chanfle"
    assert _adentro(con, 5.95, 3.0, z / 2 + 1.0), "el chanfle se comió el lado entero"
    assert con.volume < recta.volume


def test_chanfle_por_capas_no_cambia_el_alto_ni_deja_agujeros_en_el_cuerpo():
    for chanfle in (0.2, 0.4, 1.0):
        cuerpo = collar._cuerpo_por_capas(collar.contorno_cuenta("cuadrada", 12), 7.0, chanfle)
        assert cuerpo.is_watertight and cuerpo.is_volume, chanfle
        assert abs(cuerpo.bounds[0][2]) < 1e-6 and abs(cuerpo.bounds[1][2] - 7.0) < 1e-6, chanfle
        assert len(cuerpo.split(only_watertight=False)) == 1, f"el chanfle {chanfle} partió el cuerpo"


def test_cuenta_cuadrada_con_letra_encastra_con_la_holgura_exacta():
    prof, holgura = 1.0, 0.1
    letra = _letra("E", 7)
    sin, _, _ = _pulsera(None, forma_cuenta="cuadrada")
    base, pieza, info = _pulsera(letra, forma_cuenta="cuadrada", profundidad_hueco=prof, holgura=holgura)
    hueco = letra.buffer(holgura, join_style="round")
    quitado = sin.volume - base.volume
    assert abs(quitado - hueco.area * prof) / (hueco.area * prof) < 0.03, (quitado, hueco.area * prof)
    assert abs(pieza.volume - letra.area * prof) / (letra.area * prof) < 0.01
    inter = trimesh.boolean.intersection([base, pieza], engine="manifold")
    assert (inter.volume if len(inter.faces) else 0.0) < 1e-3


# --- cuenta con forma de letra ----------------------------------------------------

def test_cuenta_con_forma_de_letra_envuelve_la_letra_y_encastra_la_pieza():
    for c in "EOAIMR":
        letra = _letra(c, 14)
        base, pieza, info = _pulsera(letra, forma_cuenta="letra", borde_letra=1.5)
        assert base.is_watertight and base.is_volume, c
        assert pieza.is_watertight and pieza.is_volume, c
        assert len(base.split(only_watertight=False)) == 1, f"la cuenta {c} quedó en pedazos"
        assert info["avisos"] == [], (c, info["avisos"])
        # el cuerpo es la letra + 1,5 mm de borde, no un disco: es más alto que ancho y mide el borde de más
        ancho = letra.bounds[2] - letra.bounds[0]
        assert abs(base.extents[0] - (ancho + 3.0)) < 0.2, (c, base.extents[0], ancho)
        assert base.extents[0] < base.extents[1] or c == "M"


def test_cuenta_con_forma_de_letra_tiene_borde_alrededor_de_la_letra_y_agujero_al_medio():
    letra = _letra("I", 14)   # un palo: fácil de razonar
    base, pieza, _ = _pulsera(letra, forma_cuenta="letra", borde_letra=1.5)
    z_tapa = P["alto"] - 0.3
    ancho = letra.bounds[2] - letra.bounds[0]
    assert not _adentro(base, 0, 4.0, z_tapa), "la letra no tiene hueco en la tapa"
    assert _adentro(base, ancho / 2 + 0.75, 4.0, z_tapa), "falta el borde alrededor de la letra"
    assert not _adentro(base, ancho / 2 + 2.0, 4.0, z_tapa), "el cuerpo se pasa del borde pedido"
    assert not _adentro(base, 0, 0, P["alto"] / 2), "el agujero no cruza por el medio"
    assert _adentro(base, 0, 4.0, P["alto"] / 2), "el agujero no debería ser tan alto"
    assert _adentro(pieza, 0, 4.0, P["alto"] - 0.3), "la letra suelta no está en su hueco"


def test_cuenta_con_forma_de_letra_avisa_si_el_agujero_no_cabe_en_un_trazo():
    """Una E chica con muy poco borde tiene la barra del medio justo donde pasa el hilo: el agujero
    de 2,5 mm no cabe con paredes y tiene que avisar."""
    letra = collar.letra_poligono("E", FUENTE, 7)
    _, _, info = _pulsera(letra, forma_cuenta="letra", borde_letra=0.3)
    assert any("se angosta" in a for a in info["avisos"]), info["avisos"]
    _, _, bien = _pulsera(_letra("E", 14), forma_cuenta="letra", borde_letra=1.5)
    assert bien["avisos"] == []


def test_forma_de_letra_sin_letra_o_en_sticker_da_error():
    try:
        collar.armar_cuenta(None, forma_cuenta="letra")
    except ValueError:
        pass
    else:
        raise AssertionError("forma letra sin letra tenía que fallar")
    try:
        collar.generar("AB", FUENTE, modo_cuenta="sticker", forma_cuenta="letra", carpeta_salida=tempfile.gettempdir())
    except ValueError as e:
        assert "sticker" in str(e)
    else:
        raise AssertionError("forma letra en modo sticker tenía que fallar")


# --- paso del hilo por varios tramos de material ------------------------------------

def test_ancho_en_el_paso_mide_todos_los_tramos_de_material():
    dos_bloques = box(-10, -5, -6, 5).union(box(6, -1, 10, 1))  # uno ancho y uno finito, con aire en el medio
    assert abs(collar.ancho_minimo_en_el_paso(dos_bloques, 0) - 2) < 1e-6
    assert collar.ancho_minimo_en_el_paso(box(-5, 10, 5, 12), 0) is None   # el camino no toca nada


def test_ancho_en_el_paso_de_un_tramo_corto_mide_su_parte_de_adentro():
    """Un tramo de 3 mm (una letra chica) no se mide una sola vez por el medio: una E de 7 mm tiene el
    palo de 7 mm de alto y, pegada a él, la barra del medio de 1,7 mm. Medir solo el centro caía en el
    palo y la barra fina pasaba sin avisar."""
    palo_y_barra = box(-1.7, -3.5, -0.4, 3.5).union(box(-0.4, -0.85, 1.7, 0.85))   # una "E" recortada a lo importante
    assert abs(collar.ancho_minimo_en_el_paso(palo_y_barra, 0) - 1.7) < 1e-6
    assert abs(collar.ancho_minimo_en_el_paso(box(-1.5, -4, 1.5, 4), 0) - 8) < 1e-6
    assert abs(collar.ancho_minimo_en_el_paso(box(-1.5, -0.5, 1.5, 0.5), 0) - 1) < 1e-6


# --- pared mínima, letra chica, separadores con chanfle -------------------------------

def test_pared_minima_es_un_parametro():
    kw = dict(diametro=12, alto=6, agujero=2.5, rebaje_sticker_diametro=8, rebaje_sticker_profundidad=1.0)
    _, _, estricto = collar.armar_cuenta(None, pared_min=0.8, **kw)    # pared real: 0,75 mm
    _, _, tolerante = collar.armar_cuenta(None, pared_min=0.7, **kw)
    assert abs(estricto["pared_mm"] - 0.75) < 1e-6
    assert estricto["avisos"] and tolerante["avisos"] == []


def test_letra_chica_conserva_su_forma_y_la_grande_queda_como_siempre():
    """La tolerancia de simplificado se escala con el tamaño: una "O" de 7 mm tiene que tener (casi) la
    misma forma que la de 42 mm achicada, no quedar facetada por una tolerancia pensada para 42 mm."""
    grande, chica = collar.letra_poligono("O", FUENTE, 42), collar.letra_poligono("O", FUENTE, 7)
    assert abs(chica.area * 36 / grande.area - 1) < 0.02, chica.area * 36 / grande.area
    assert abs(len(chica.exterior.coords) - len(grande.exterior.coords)) <= 4   # misma cantidad de puntos: mismo detalle


def test_separador_de_forma_con_chanfle_por_capas():
    contorno = collar.contorno_forma(14, nombre="corazon")
    liso, _ = collar.armar_separador_forma(contorno, 7, 2.5, pared_min=0.8, chanfle=0.0)
    chanflado, avisos = collar.armar_separador_forma(contorno, 7, 2.5, pared_min=0.8, chanfle=0.4)
    assert chanflado.is_watertight and chanflado.is_volume and avisos == []
    assert chanflado.volume < liso.volume
    assert abs(chanflado.extents[2] - 7) < 1e-6


# --- medidas, muñeca -----------------------------------------------------------------

def test_medidas_de_cada_tipo_se_pueden_pasar_directo_a_generar():
    parametros = set(inspect.signature(collar.generar).parameters)
    for tipo in collar.TIPOS_PIEZA:
        for sticker in (False, True):
            medidas = collar.medidas_de(tipo, sticker=sticker)
            assert set(medidas) <= parametros, set(medidas) - parametros
            assert ("rebaje_sticker_diametro" in medidas) == sticker
    assert collar.medidas_de("pulsera")["diametro"] < collar.medidas_de("collar")["diametro"]
    try:
        collar.medidas_de("anillo")
    except ValueError:
        return
    raise AssertionError("un tipo desconocido tenía que fallar")


def test_el_preset_de_collar_es_el_de_siempre():
    c = collar.PRESETS_MEDIDAS["collar"]
    assert (c["diametro"], c["alto"], c["agujero"], c["chanfle"]) == (70.0, 30.0, 20.0, 1.0)
    assert (c["holgura"], c["pared_min"], c["margen_letra"]) == (0.15, 1.2, 5.0)


def test_ajuste_a_la_muneca():
    justa = collar.ajuste_a_muneca(175, 16, 17)
    assert justa["estado"] == "justa" and abs(justa["objetivo_cm"] - 17.5) < 1e-9
    corta = collar.ajuste_a_muneca(140, 16, 17)
    assert corta["estado"] == "corta" and corta["diferencia_cm"] < 0 and "faltan" in corta["mensaje"]
    assert "pieza" in corta["mensaje"]
    larga = collar.ajuste_a_muneca(210, 16, 17)
    assert larga["estado"] == "larga" and "sobran" in larga["mensaje"]
    assert collar.ajuste_a_muneca(140, 16)["estado"] == "corta"   # sin n_piezas también anda
    try:
        collar.ajuste_a_muneca(150, 0)
    except ValueError:
        return
    raise AssertionError("una muñeca de 0 cm tenía que fallar")


# --- generar() con medidas de pulsera ---------------------------------------------------

def _generar_pulsera(forma, texto="RIKANDI", **kwargs):
    medidas = collar.medidas_de("pulsera")
    medidas.update(kwargs.pop("medidas", {}))
    with tempfile.TemporaryDirectory() as carpeta:
        r = collar.generar(texto, FUENTE, forma_cuenta=forma, carpeta_salida=carpeta, prefijo="t", **medidas, **kwargs)
        r["_mallas"] = [trimesh.load(p["ruta_stl"]) for p in r["piezas"]]
    return r


def test_generar_pulsera_en_las_tres_formas():
    for forma, alto_letra in (("redonda", 7.0), ("cuadrada", 7.0), ("letra", 14.0)):
        r = _generar_pulsera(forma, separadores={"inicio": CORAZON, "final": CORAZON},
                             medidas={"alto_letra_mm": alto_letra})
        assert r["n_cuentas"] == 7 and r["n_separadores"] == 2, forma
        assert len(r["piezas"]) == 7 * 2 + 2, forma
        assert all(p["watertight"] for p in r["piezas"]), forma
        assert r["avisos"] == [], (forma, r["avisos"])
        assert 80 < r["largo_mm"] < 160, (forma, r["largo_mm"])  # una pulsera, no un collar
        bases = [(p, m) for p, m in zip(r["piezas"], r["_mallas"]) if p["tipo"] == "cuenta"]
        assert all(abs(m.extents[2] - 7.0) < 1e-6 for _, m in bases), forma


def test_generar_pulsera_con_forma_de_letra_las_cuentas_tienen_el_ancho_de_cada_letra():
    r = _generar_pulsera("letra", texto="MI", medidas={"alto_letra_mm": 14.0})
    anchos = {p["etiqueta"]: p["ancho_mm"] for p in r["piezas"] if p["tipo"] == "cuenta"}
    assert anchos["cuenta M"] > 2 * anchos["cuenta I"], anchos   # la M es mucho más ancha que la I


def test_generar_pulsera_el_armado_enfila_todo_sobre_el_mismo_hilo():
    for forma, alto_letra in (("cuadrada", 7.0), ("letra", 14.0)):
        r = _generar_pulsera(forma, texto="EA", separadores={"entre_letras": "cilindro", "final": CORAZON},
                             medidas={"alto_letra_mm": alto_letra})
        z = P["alto"] / 2
        anterior_fin = None
        for malla, _, etiqueta in r["armado"]:
            if etiqueta.startswith("letra"):
                continue
            cx = (malla.bounds[0][0] + malla.bounds[1][0]) / 2
            assert not _adentro(malla, cx, 0, z), f"{forma}: {etiqueta} no tiene el hilo en su eje"
            if anterior_fin is not None:
                assert abs(malla.bounds[0][0] - anterior_fin) < 1e-6, f"{forma}: {etiqueta} no está pegada a la anterior"
            anterior_fin = malla.bounds[1][0]


def test_generar_cuadrada_achica_las_letras_con_el_margen_de_la_pulsera():
    """En una cuenta cuadrada de 12 mm con 1 mm de margen, una letra de 20 mm no entra: se achican todas
    y se avisa."""
    r = _generar_pulsera("cuadrada", texto="MW", medidas={"alto_letra_mm": 20.0})
    assert any("achiqué" in a for a in r["avisos"]), r["avisos"]
    cuentas = [m for p, m in zip(r["piezas"], r["_mallas"]) if p["tipo"] == "letra"]
    assert all(max(m.extents[:2]) <= 12 - 2 * 1.0 + 1e-6 for m in cuentas)


def test_generar_sticker_en_cuadrada_con_rebaje_de_pulsera():
    r = _generar_pulsera("cuadrada", texto="AB", modo_cuenta="sticker", rebaje_sticker_diametro=9.0)
    assert r["_nombres"] if "_nombres" in r else True
    base = r["_mallas"][0]
    assert not _adentro(base, 0, 3.0, P["alto"] - 0.25), "falta el rebaje del sticker"
    assert _adentro(base, 0, 5.5, P["alto"] - 0.25), "el rebaje se comió el borde"


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
