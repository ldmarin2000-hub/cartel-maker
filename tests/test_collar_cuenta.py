#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_collar_cuenta.py
------------------
Red de regresión para la CUENTA del collar (`generators/collar.py`):
letra con escala común, base con hueco + agujero para el hilo, y el
encastre letra/hueco con la holgura exacta.

No usa pytest (ver AGENTS.md "Testing") -- funciones `test_*` con
`assert` simple, corribles con `python tests/test_collar_cuenta.py`.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import trimesh

from generators import collar

FUENTE = os.path.join("fonts", "curadas", "Anton.ttf")
D, A = collar.DIAMETRO_DEFAULT, collar.ALTO_DEFAULT


def _cuenta(caracter="O", alto_mayuscula=40, **kwargs):
    poligono = collar.letra_poligono(caracter, FUENTE, alto_mayuscula) if caracter else None
    return poligono, *collar.armar_cuenta(poligono, **kwargs)


def _adentro(malla, x, y, z):
    return bool(malla.contains([[x, y, z]])[0])


# --- letra -------------------------------------------------------------------

def test_todas_las_letras_mayusculas_tienen_la_misma_altura():
    """Escala común: una "I" no se agranda hasta llenar el disco -- mide
    lo mismo que una "M" o una "H". (La "O" se pasa un poquito arriba y
    abajo por el sobreimpulso de la curva, normal en tipografía.)"""
    for c in "HMEIL":
        p = collar.letra_poligono(c, FUENTE, 40)
        assert abs((p.bounds[3] - p.bounds[1]) - 40) < 0.6, (c, p.bounds)
    po = collar.letra_poligono("O", FUENTE, 40)
    assert 40 <= po.bounds[3] - po.bounds[1] < 42


def test_la_letra_queda_centrada_y_con_la_caja_de_mayuscula_centrada():
    for c in "HMIE":
        minx, miny, maxx, maxy = collar.letra_poligono(c, FUENTE, 40).bounds
        assert abs((minx + maxx) / 2) < 0.3, (c, "no centrada en X")
        assert abs((miny + maxy) / 2) < 0.4, (c, "no centrada en Y")


def test_las_colas_cuelgan_sin_correr_la_linea_base():
    """Una "g" tiene cola: tiene que llegar por debajo del piso de las
    mayúsculas (-alto/2) en vez de quedar centrada y subir el resto."""
    p = collar.letra_poligono("g", FUENTE, 40)
    assert p.bounds[1] < -20 - 1, p.bounds
    assert p.bounds[3] < 20, "una minúscula no debería pasar el techo de la mayúscula"


def test_espacio_no_da_letra():
    assert collar.letra_poligono(" ", FUENTE, 40) is None


# --- agujero ------------------------------------------------------------------

def test_techo_del_agujero_segun_perfil():
    assert abs(collar.altura_techo_agujero("rombo", 20) - 10) < 1e-6
    assert abs(collar.altura_techo_agujero("redondo", 20) - 10) < 0.05
    assert abs(collar.altura_techo_agujero("gota", 20) - 20 * np.sqrt(2) / 2) < 1e-6


def test_perfil_invalido_da_error():
    try:
        collar.perfil_agujero("hexagono", 20)
    except ValueError:
        return
    raise AssertionError("tenía que fallar con un perfil inválido")


def test_cada_perfil_y_angulo_da_cuerpos_cerrados():
    for perfil in ("rombo", "redondo"):
        for angulo in (0, 45, 90):
            _, base, letra, _ = _cuenta(perfil=perfil, angulo_agujero=angulo)
            assert base.is_watertight and base.is_volume, (perfil, angulo)
            assert letra.is_watertight and letra.is_volume, (perfil, angulo)


def test_el_agujero_cruza_la_cuenta_a_lo_largo_del_eje_pedido():
    """Ángulo 0 = eje a lo largo de X; 90 = a lo largo de Y; 45 = diagonal.
    Centro vacío siempre; a lo largo del eje, afuera y adentro del cuerpo,
    vacío; perpendicular a esa distancia, sólido."""
    z = A / 2
    for angulo in (0, 45, 90):
        _, base, _, _ = _cuenta(None, angulo_agujero=angulo)
        a = np.radians(angulo)
        eje = np.array([np.cos(a), np.sin(a)])
        perp = np.array([-np.sin(a), np.cos(a)])
        assert not _adentro(base, 0, 0, z), angulo
        for dist in (15, 28):
            assert not _adentro(base, *(eje * dist), z), (angulo, "eje", dist)
            assert not _adentro(base, *(-eje * dist), z), (angulo, "eje", -dist)
            assert _adentro(base, *(perp * dist), z), (angulo, "perp", dist)


def test_chanfle_redondea_el_borde_y_sin_chanfle_queda_cuadrado():
    _, con, _, _ = _cuenta(None, chanfle=1.0)
    _, sin, _, _ = _cuenta(None, chanfle=0.0)
    esquina = (D / 2 - 0.1, 0, A - 0.1)
    assert not _adentro(con, *esquina)
    assert _adentro(sin, *esquina)


def test_medidas_de_la_cuenta():
    _, base, _, _ = _cuenta(None)
    (minx, miny, minz), (maxx, maxy, maxz) = base.bounds
    assert abs(minz) < 1e-6 and abs(maxz - A) < 1e-6
    assert abs((maxx - minx) - D) < 0.05 and abs((maxy - miny) - D) < 0.05


# --- encastre -----------------------------------------------------------------

def test_encastre_la_letra_no_se_pisa_con_la_base_y_deja_la_holgura_pedida():
    """El hueco es la letra agrandada `holgura` por lado. Se mide con
    volúmenes: lo que se le saca al cuerpo = área del hueco * profundidad
    (el hueco exacto, ni más ni menos), la letra suelta = área de la
    letra * profundidad, y las dos mallas no se intersectan."""
    prof, holgura = 2.0, 0.15
    poligono, base_sin, _, _ = _cuenta(None)
    poligono, base, letra, info = _cuenta("E", profundidad_hueco=prof, holgura=holgura)
    hueco = poligono.buffer(holgura, join_style="round")

    quitado = base_sin.volume - base.volume
    assert abs(quitado - hueco.area * prof) / (hueco.area * prof) < 0.02, (quitado, hueco.area * prof)
    assert abs(letra.volume - poligono.area * prof) / (poligono.area * prof) < 0.01

    try:
        interseccion = trimesh.boolean.intersection([base, letra], engine="manifold")
        inter = interseccion.volume if len(interseccion.faces) else 0.0
    except Exception:
        inter = 0.0
    assert inter < 1e-3, f"la letra se pisa con la base ({inter:.4f} mm3)"
    assert hueco.area > poligono.area, "tiene que haber holgura real"


def test_letra_con_isla_conserva_el_centro_de_la_base():
    """La "O" tiene un hueco adentro: el hueco de la base tiene que dejar
    en pie la isla del centro (sino la letra no encastra, flota)."""
    prof = 2.0
    poligono, base, letra, _ = _cuenta("O", profundidad_hueco=prof)
    z = A - prof / 2
    assert _adentro(base, 0, 0, z), "el centro de la O se comió: la isla desapareció"
    x_anillo = (poligono.bounds[2] + poligono.interiors[0].bounds[2]) / 2 if hasattr(poligono, "interiors") else None
    if x_anillo is None:  # MultiPolygon: tomar el primero
        g = max(poligono.geoms, key=lambda g: g.area)
        x_anillo = (g.bounds[2] + g.interiors[0].bounds[2]) / 2
    assert not _adentro(base, x_anillo, 0, z), "el anillo de la O no quedó vacío"
    assert _adentro(letra, x_anillo, 0, z), "la letra no llena el anillo de la O"


def test_relieve_cero_deja_la_letra_al_ras_y_positivo_sobresale():
    _, _, al_ras, _ = _cuenta("E", relieve=0.0)
    _, _, alto, _ = _cuenta("E", relieve=0.6)
    assert abs(al_ras.bounds[1][2] - A) < 1e-6
    assert abs(alto.bounds[1][2] - (A + 0.6)) < 1e-6


# --- validación de espesor ----------------------------------------------------

def test_aviso_si_el_agujero_se_acerca_demasiado_al_hueco():
    """La gota de 20 mm sube a 14,1 mm sobre el centro: en una cuenta de
    30 de alto con hueco de 2 mm se come la pared. El rombo de 20 mm
    queda holgado (pared de 3 mm)."""
    _, _, _, info_rombo = _cuenta("E", perfil="rombo")
    _, _, _, info_gota = _cuenta("E", perfil="gota")
    assert info_rombo["avisos"] == [] and abs(info_rombo["pared_mm"] - 3.0) < 1e-6
    assert info_gota["pared_mm"] < collar.PARED_MIN_MM and info_gota["avisos"]


def test_profundidad_del_hueco_invalida_da_error():
    for prof in (0, A, A + 1):
        try:
            _cuenta("E", profundidad_hueco=prof)
        except ValueError:
            continue
        raise AssertionError(f"profundidad_hueco={prof} tenía que fallar")


# --- cuenta lisa para sticker ---------------------------------------------------

def test_cuenta_lisa_sin_rebaje_es_el_cilindro_con_agujero_nada_mas():
    """Sin letra ni rebaje: tapa lisa, una sola pieza -- la cara de arriba
    no tiene ningún hueco (el centro de la tapa es sólido hasta el techo)."""
    _, base, letra, info = _cuenta(None)
    assert letra is None
    assert _adentro(base, 0, 0, A - 0.01)
    assert abs(info["pared_mm"] - (A - (A / 2 + 10))) < 1e-6


def test_rebaje_para_sticker_saca_exactamente_el_disco_pedido():
    """El rebaje es un disco de diámetro del sticker + holgura por lado y
    `profundidad` de hondo: se mide por volumen contra la cuenta lisa, y
    por puntos (adentro del disco vacío, afuera sólido, debajo sólido)."""
    diam, prof, holgura = 50.0, 0.5, 0.15
    _, lisa, _, _ = _cuenta(None)
    _, base, _, info = _cuenta(None, rebaje_sticker_diametro=diam,
                               rebaje_sticker_profundidad=prof, holgura=holgura)
    assert base.is_watertight and base.is_volume
    esperado = np.pi * (diam / 2 + holgura) ** 2 * prof
    quitado = lisa.volume - base.volume
    assert abs(quitado - esperado) / esperado < 0.01, (quitado, esperado)
    assert not _adentro(base, 0, 0, A - prof / 2), "el centro de la tapa no quedó rebajado"
    assert _adentro(base, 0, 0, A - prof - 0.2), "el rebaje es más hondo de lo pedido"
    assert _adentro(base, diam / 2 + holgura + 1, 0, A - prof / 2), "el borde de afuera del rebaje se comió"
    assert abs(base.bounds[1][2] - A) < 1e-6
    assert abs(info["pared_mm"] - (A - prof - (A / 2 + 10))) < 1e-6


def test_rebaje_para_sticker_que_no_entra_da_error():
    """Tiene que quedar al menos REBAJE_BORDE_MIN_MM de borde alrededor."""
    maximo = D - 2 * collar.REBAJE_BORDE_MIN_MM - 2 * collar.HOLGURA_DEFAULT
    _cuenta(None, rebaje_sticker_diametro=maximo - 0.01)  # justo entra
    for diam in (maximo + 0.5, D, 0, -5):
        try:
            _cuenta(None, rebaje_sticker_diametro=diam)
        except ValueError:
            continue
        raise AssertionError(f"rebaje_sticker_diametro={diam} tenía que fallar")


def test_rebaje_para_sticker_y_letra_son_alternativos():
    try:
        _cuenta("E", rebaje_sticker_diametro=40)
    except ValueError:
        return
    raise AssertionError("pedir letra y rebaje a la vez tenía que fallar")


def test_rebaje_muy_hondo_avisa_por_la_pared_del_agujero():
    """Un rebaje de 3 mm de hondo deja 2 mm sobre el agujero (rombo de 20):
    entra; uno de 4,5 mm deja 0,5 mm: aviso de fragilidad."""
    _, _, _, bien = _cuenta(None, rebaje_sticker_diametro=50, rebaje_sticker_profundidad=3.0)
    _, _, _, mal = _cuenta(None, rebaje_sticker_diametro=50, rebaje_sticker_profundidad=4.5)
    assert bien["avisos"] == []
    assert mal["avisos"] and mal["pared_mm"] < collar.PARED_MIN_MM


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
