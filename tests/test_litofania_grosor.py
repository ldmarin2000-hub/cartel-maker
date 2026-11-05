#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_litofania_grosor.py
------------------
Red de regresión para L2 de la litofanía (`core/litofania.py`): brillo -> grosor, con la
compensación de que el plástico atenúa la luz de forma exponencial (Beer-Lambert). Lo que se cuida:

  * los extremos son EXACTOS: brillo 1 -> grosor_min, brillo 0 -> grosor_max, con y sin compensación;
  * la curva es fiel: la luz que pasa por el grosor calculado es
    luz_minima + (1 - luz_minima)·EOTF_sRGB(brillo) -- lo que daría una pantalla con ese gris;
  * la compensación corrige en los DOS sentidos: con un plástico denso (luz_minima chica) afina los
    medios tonos respecto del lineal, con uno translúcido (luz_minima grande) los engrosa, y cerca de
    ~7 % casi no hay diferencia;
  * el cuantizado a capas cae en niveles reales con error de media capa como máximo;
  * L1 queda intacto: la entrada no se modifica.

La EOTF y el modelo de referencia están reescritos acá, a mano, para no validar el código con sí mismo.
No usa pytest (ver AGENTS.md "Testing") -- funciones `test_*` con `assert` simple,
corribles con `python tests/test_litofania_grosor.py`.
"""
import contextlib
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
from PIL import Image

from core import litofania as lf

BRILLO = np.linspace(0.0, 1.0, 4001)                       # una grilla fina de 0 a 1 (incluye 0, 1 y el codo de la EOTF)
LUCES_MINIMAS = (0.005, 0.02, 0.05, 0.1, 0.2, 0.5)
# incluye rangos "feos" para el punto flotante: con (0.51, 2.52) la forma ingenua  tmin + (tmax - tmin)·1  da
# 2.5199999999999996 y no 2.52; el código usa  tmin·(1 - f) + tmax·f,  que es exacto en 0 y en 1
RANGOS = ((0.8, 2.8), (0.84, 3.1), (1.0, 2.0), (0.6, 4.5), (0.51, 2.52), (0.51, 2.65))


# --- referencias independientes ----------------------------------------------------------

def _eotf(b):
    """sRGB -> luz lineal, escrita a mano, tramo por tramo (no usa la del módulo)."""
    b = np.asarray(b, dtype=float)
    salida = np.empty_like(b)
    bajo = b <= 0.04045
    salida[bajo] = b[bajo] / 12.92
    salida[~bajo] = ((b[~bajo] + 0.055) / 1.055) ** 2.4
    return salida


def _luz_objetivo(b, c):
    return c + (1.0 - c) * _eotf(b)


def _l_estrella(y):
    """Luminosidad percibida CIE L* de una luz relativa y (0..1)."""
    y = np.asarray(y, dtype=float)
    return np.where(y > 216 / 24389, 116 * np.cbrt(y) - 16, 24389 / 27 * y)


def _grosor(b, tmin=0.8, tmax=2.8, c=0.05, **kwargs):
    return lf.grosor_desde_brillo(np.asarray(b, dtype=float), tmin, tmax, c, **kwargs)


def _cruce(b=0.5, tmin=0.8, tmax=2.8):
    """La luz_minima donde el grosor lineal ya coincide con el compensado en el brillo `b` (bisección)."""
    def f(c):
        return float(_grosor(b, tmin, tmax, c)) - float(_grosor(b, tmin, tmax, c, compensar=False))
    bajo, alto = 0.03, 0.2
    assert f(bajo) < 0 < f(alto), "no hay cruce en el rango esperado"
    for _ in range(60):
        medio = (bajo + alto) / 2
        bajo, alto = (medio, alto) if f(medio) < 0 else (bajo, medio)
    return (bajo + alto) / 2


@contextlib.contextmanager
def _carpeta():
    with tempfile.TemporaryDirectory() as d:
        yield d


def _mapa_brillo(carpeta, ancho=64, alto=32):
    """Un MapaBrillo real (de L1) a partir de un degradé horizontal de 0 a 255."""
    ruta = os.path.join(carpeta, "rampa.png")
    Image.fromarray(np.tile(np.linspace(0, 255, ancho).round().astype(np.uint8), (alto, 1))).save(ruta)
    return lf.imagen_a_mapa_brillo(ruta, ancho_mm=ancho, px_por_mm=1.0)


# --- 1. extremos exactos ---------------------------------------------------------------------

def test_extremos_exactos_con_y_sin_compensacion():
    for tmin, tmax in RANGOS:
        for c in LUCES_MINIMAS:
            for compensar in (True, False):
                t = _grosor([1.0, 0.0], tmin, tmax, c, compensar=compensar)
                assert t[0] == tmin, f"brillo 1 dio {t[0]!r}, tenía que ser exactamente {tmin!r} (C={c}, compensar={compensar})"
                assert t[1] == tmax, f"brillo 0 dio {t[1]!r}, tenía que ser exactamente {tmax!r} (C={c}, compensar={compensar})"


def test_todo_el_resultado_queda_entre_los_dos_extremos():
    for tmin, tmax in RANGOS:
        for c in LUCES_MINIMAS:
            for compensar in (True, False):
                t = _grosor(BRILLO, tmin, tmax, c, compensar=compensar)
                assert t.min() >= tmin and t.max() <= tmax, (tmin, tmax, c, compensar)


def test_es_monotona_estrictamente_decreciente_con_el_brillo():
    """Más brillo = más fino. Estricto, también cerca de 0 donde la EOTF cambia de tramo (b = 0,04045)."""
    for c in LUCES_MINIMAS:
        for compensar in (True, False):
            t = _grosor(BRILLO, c=c, compensar=compensar)
            assert (np.diff(t) < 0).all(), f"no es estrictamente decreciente (C={c}, compensar={compensar})"


# --- 2. fidelidad ------------------------------------------------------------------------------

def test_la_luz_que_pasa_es_la_de_una_pantalla_con_error_menor_a_1e9():
    """luz_transmitida(grosor(b)) = C + (1 - C)·EOTF(b), para todos los brillos, C y rangos."""
    for tmin, tmax in RANGOS:
        for c in LUCES_MINIMAS:
            t = _grosor(BRILLO, tmin, tmax, c)
            luz = lf.luz_transmitida(t, tmin, tmax, c)
            error = np.abs(luz - _luz_objetivo(BRILLO, c)).max()
            assert error < 1e-9, f"error {error:.2e} (C={c}, grosores {tmin}-{tmax})"


def test_fidelidad_tambien_con_los_256_niveles_de_8_bits():
    niveles = np.arange(256) / 255.0
    t = _grosor(niveles)
    assert np.abs(lf.luz_transmitida(t) - _luz_objetivo(niveles, 0.05)).max() < 1e-9


def test_el_lineal_sin_compensar_no_cumple_la_fidelidad():
    """Si el test de fidelidad no distinguiera, no protegería nada: el lineal se aparta claramente."""
    for c in (0.02, 0.2):
        lineal = _grosor(BRILLO, c=c, compensar=False)
        error = np.abs(lf.luz_transmitida(lineal, 0.8, 2.8, c) - _luz_objetivo(BRILLO, c)).max()
        assert error > 0.02, f"con C={c} el lineal se aparta solo {error:.4f}: el test de fidelidad no discrimina"


def test_valores_de_referencia_de_la_curva_por_defecto():
    """Los números del plan aprobado: placa de 0,8 a 2,8 mm con 5 % de luz mínima."""
    pedidos = {1.0: 0.800, 0.9: 0.951, 0.75: 1.204, 0.5: 1.717, 0.25: 2.348, 0.1: 2.684, 0.0: 2.800}
    for b, esperado in pedidos.items():
        assert abs(float(_grosor(b)) - esperado) < 0.0015, (b, float(_grosor(b)), esperado)
    lineal = {1.0: 0.8, 0.9: 1.0, 0.75: 1.3, 0.5: 1.8, 0.25: 2.3, 0.1: 2.6, 0.0: 2.8}
    for b, esperado in lineal.items():
        assert abs(float(_grosor(b, compensar=False)) - esperado) < 1e-12


# --- 3. la compensación corrige en los dos sentidos -----------------------------------------------

def test_con_plastico_denso_los_medios_se_afinan_y_con_translucido_se_engrosan():
    """Gris medio (b = 0,5), placa de 0,8 a 2,8 mm: el lineal da 1,80 mm. Compensado: C=2 % afina,
    C=20 % engrosa."""
    lineal = float(_grosor(0.5, compensar=False))
    assert abs(lineal - 1.8) < 1e-12
    denso = float(_grosor(0.5, c=0.02))
    translucido = float(_grosor(0.5, c=0.2))
    assert denso < lineal - 0.15, f"C=2 %: {denso:.3f} mm no afina los medios respecto de {lineal}"
    assert translucido > lineal + 0.15, f"C=20 %: {translucido:.3f} mm no engrosa los medios respecto de {lineal}"
    for c, esperado in ((0.02, 1.55), (0.03, 1.62), (0.05, 1.72), (0.10, 1.87), (0.20, 2.03)):
        assert abs(float(_grosor(0.5, c=c)) - esperado) < 0.006, (c, float(_grosor(0.5, c=c)), esperado)


def test_cerca_de_7_por_ciento_el_lineal_ya_casi_coincide():
    c_cruce = _cruce()
    assert 0.070 < c_cruce < 0.078, f"el cruce está en C={c_cruce:.4f}, se esperaba ~7,4 %"
    diferencia = abs(float(_grosor(0.5, c=c_cruce)) - float(_grosor(0.5, c=c_cruce, compensar=False)))
    assert diferencia < 1e-6
    for c in (0.07, 0.08):
        assert abs(float(_grosor(0.5, c=c)) - 1.8) < 0.03, f"con C={c} los medios deberían estar cerca del lineal"


def test_la_luz_del_lineal_se_ve_mas_oscura_o_mas_clara_que_el_objetivo_segun_c():
    """En luminosidad percibida (L*): el lineal oscurece los medios si C es chica y los lava si C es grande;
    la curva compensada reproduce el objetivo."""
    b = 0.5
    for c, signo in ((0.02, -1), (0.2, +1)):
        objetivo = float(_l_estrella(_luz_objetivo(b, c)))
        luz_lineal = float(lf.luz_transmitida(_grosor(b, c=c, compensar=False), 0.8, 2.8, c))
        luz_compensada = float(lf.luz_transmitida(_grosor(b, c=c), 0.8, 2.8, c))
        assert signo * (float(_l_estrella(luz_lineal)) - objetivo) > 5, f"C={c}: el lineal no se aparta del objetivo en el sentido esperado"
        assert abs(float(_l_estrella(luz_compensada)) - objetivo) < 1e-6


def test_la_correccion_maxima_es_la_del_plan_y_chica_con_capas_de_02():
    """Con C=5 % la compensación mueve como mucho ~0,11 mm (la mitad de una capa de 0,2); con C=2 %, ~0,25 mm."""
    for c, maximo in ((0.05, 0.11), (0.02, 0.25), (0.2, 0.28)):
        dif = np.abs(_grosor(BRILLO, c=c) - _grosor(BRILLO, c=c, compensar=False)).max()
        assert abs(dif - maximo) < 0.01, f"C={c}: corrección máxima {dif:.3f} mm, se esperaba ~{maximo}"
    # con la curva por defecto (C = 5 %) la corrección máxima es ~0,53 de una capa de 0,2: menos de una capa entera,
    # así que con capas de 0,2 la compensación casi no se ve; con 0,12 son ~0,9 capas y con 0,08, ~1,3
    maxima = np.abs(_grosor(BRILLO) - _grosor(BRILLO, compensar=False)).max()
    assert 0.4 < maxima / 0.2 < 0.6 and maxima < 0.2
    assert 0.8 < maxima / 0.12 < 1.0 and 1.2 < maxima / 0.08 < 1.4


# --- 4. cuantizado --------------------------------------------------------------------------------

def test_el_cuantizado_cae_en_niveles_reales_con_error_de_media_capa():
    for capa in (0.08, 0.12, 0.2):
        continuo = _grosor(BRILLO)
        cuantizado = lf.cuantizar_a_capas(continuo, capa, 0.2)
        indice = (cuantizado - 0.2) / capa
        assert np.abs(indice - np.round(indice)).max() < 1e-9, f"capa {capa}: hay grosores fuera de un nivel de capa"
        assert np.abs(cuantizado - continuo).max() <= capa / 2 + 1e-9, f"capa {capa}: error mayor que media capa"
        assert (cuantizado >= 0.2 - 1e-12).all()


def test_el_cuantizado_es_idempotente_y_conserva_el_orden():
    continuo = _grosor(BRILLO)
    for capa in (0.08, 0.12, 0.2):
        q = lf.cuantizar_a_capas(continuo, capa, 0.2)
        assert np.array_equal(lf.cuantizar_a_capas(q, capa, 0.2), q)
        assert (np.diff(q) <= 1e-12).all(), "el cuantizado rompió el orden (el brillo creciente tiene que dar grosor no creciente)"


def test_el_cuantizado_redondea_al_mas_cercano_no_hacia_abajo():
    """Niveles con capa de 0,12 y primera de 0,2: 0,20 / 0,32 / 0,44 / 0,56."""
    q = lf.cuantizar_a_capas(np.array([0.2, 0.25, 0.27, 0.29, 0.31, 0.49]), 0.12, 0.2)
    assert np.allclose(q, [0.2, 0.2, 0.32, 0.32, 0.32, 0.44])     # 0,27 está más cerca de 0,32 que de 0,20
    cerca_de_abajo, cerca_de_arriba = lf.cuantizar_a_capas(np.array([0.32 + 0.059, 0.32 + 0.061]), 0.12, 0.2)
    assert abs(cerca_de_abajo - 0.32) < 1e-9 and abs(cerca_de_arriba - 0.44) < 1e-9
    empate = float(lf.cuantizar_a_capas(0.2 + 1.5 * 0.12, 0.12, 0.2))                 # justo a mitad de camino: va al de arriba
    assert abs(empate - (0.2 + 2 * 0.12)) < 1e-9


def test_los_niveles_de_capa_cuentan_la_primera_capa():
    """0,8 con capas de 0,12 y primera de 0,2 cae justo en un nivel (0,2 + 5·0,12); sin contar la primera
    capa (múltiplos de 0,12) no cae."""
    assert abs(float(lf.cuantizar_a_capas(0.8, 0.12, 0.2)) - 0.8) < 1e-9
    assert abs(float(lf.cuantizar_a_capas(2.8, 0.12, 0.2)) - 2.84) < 1e-9      # 2,8 pasa a 2,84 (m = 22)


def test_brillo_a_grosor_con_capa_informa_extremos_efectivos_y_niveles():
    with _carpeta() as d:
        mapa = _mapa_brillo(d)
        g = lf.brillo_a_grosor(mapa, capa_mm=0.12)
        assert abs(g.grosor_min_efectivo - 0.8) < 1e-9 and abs(g.grosor_max_efectivo - 2.84) < 1e-9
        assert g.grosor.min() == g.grosor_min_efectivo and g.grosor.max() == g.grosor_max_efectivo
        assert g.niveles == 18 and g.capa_mm == 0.12 and g.primera_capa_mm == 0.2     # (2,84 - 0,8)/0,12 + 1
        assert any("pediste 0.80 y 2.80" in a for a in g.avisos), g.avisos
        niveles_reales = np.unique(np.round((g.grosor - 0.2) / 0.12)).size
        assert niveles_reales <= g.niveles


def test_avisa_cuando_hay_pocos_niveles_de_gris():
    with _carpeta() as d:
        mapa = _mapa_brillo(d)
        con_02 = lf.brillo_a_grosor(mapa, capa_mm=0.2)
        assert con_02.niveles == 11 and any("bandas" in a for a in con_02.avisos), con_02.avisos
        for capa in (0.12, 0.08):
            sin_aviso = lf.brillo_a_grosor(mapa, capa_mm=capa)
            assert sin_aviso.niveles >= lf.NIVELES_POCOS_AVISO
            assert not any("bandas" in a for a in sin_aviso.avisos), (capa, sin_aviso.avisos)


def test_avisa_si_grosor_min_es_menor_que_la_primera_capa():
    with _carpeta() as d:
        g = lf.brillo_a_grosor(_mapa_brillo(d), grosor_min=0.1, grosor_max=2.0, capa_mm=0.12)
        assert any("primera capa" in a for a in g.avisos), g.avisos
        assert g.grosor.min() >= 0.2 - 1e-9


def test_sin_capa_no_se_cuantiza_nada():
    with _carpeta() as d:
        mapa = _mapa_brillo(d)
        g = lf.brillo_a_grosor(mapa)
        assert g.capa_mm is None and g.niveles is None and g.primera_capa_mm is None
        assert np.array_equal(g.grosor, _grosor(mapa.brillo))
        assert g.grosor_min_efectivo == 0.8 and g.grosor_max_efectivo == 2.8 and g.avisos == []
        assert np.unique(g.grosor).size > 40, "sin capa el grosor tiene que ser continuo"


# --- 5. L1 intacto, entrada intacta, metadatos ---------------------------------------------------------

def test_la_entrada_no_se_modifica_y_la_salida_es_otro_array():
    with _carpeta() as d:
        mapa = _mapa_brillo(d)
        antes = mapa.brillo.copy()
        avisos_antes = list(mapa.avisos)
        for kwargs in ({}, {"compensar": False}, {"capa_mm": 0.12}):
            g = lf.brillo_a_grosor(mapa, **kwargs)
            assert np.array_equal(mapa.brillo, antes), f"se modificó el mapa de brillo de L1 con {kwargs}"
            assert g.grosor is not mapa.brillo and not np.shares_memory(g.grosor, mapa.brillo)
        g.grosor[:] = 0.0
        assert np.array_equal(mapa.brillo, antes) and mapa.avisos == avisos_antes
        solo_array = antes.copy()
        lf.grosor_desde_brillo(solo_array)
        assert np.array_equal(solo_array, antes)


def test_el_mapa_de_grosor_conserva_la_grilla_y_la_informacion_del_modelo():
    with _carpeta() as d:
        mapa = _mapa_brillo(d, ancho=64, alto=32)
        g = lf.brillo_a_grosor(mapa, grosor_min=0.8, grosor_max=2.8, luz_minima=0.05)
        assert g.grosor.shape == mapa.brillo.shape == (g.alto_px, g.ancho_px) == (32, 64)
        assert (g.ancho_mm, g.alto_mm, g.px_por_mm) == (mapa.ancho_mm, mapa.alto_mm, mapa.px_por_mm)
        assert g.compensado is True and g.luz_minima == 0.05
        assert abs(g.coeficiente_atenuacion - np.log(20) / 2.0) < 1e-12                # k = ln(1/C)/Δ = 1,498 /mm
        assert abs(g.media_luz_mm - 0.4627) < 0.001 and abs(g.media_luz_mm - np.log(2) / g.coeficiente_atenuacion) < 1e-12
        # un degradé de izquierda (negro) a derecha (blanco): el grosor baja de izquierda a derecha, de grosor_max a grosor_min
        fila = g.grosor[0]
        assert fila[0] == 2.8 and fila[-1] == 0.8 and (np.diff(fila) < 0).all()


def test_de_punta_a_punta_los_pixeles_oscuros_son_mas_gruesos_y_el_negativo_lo_invierte():
    with _carpeta() as d:
        ruta = os.path.join(d, "mitad.png")
        arr = np.zeros((20, 40), dtype=np.uint8)
        arr[:, 20:] = 255                                                     # izquierda negra, derecha blanca
        Image.fromarray(arr).save(ruta)
        normal = lf.brillo_a_grosor(lf.imagen_a_mapa_brillo(ruta, ancho_mm=40, px_por_mm=1.0)).grosor
        negativo = lf.brillo_a_grosor(lf.imagen_a_mapa_brillo(ruta, ancho_mm=40, px_por_mm=1.0, invertir=True)).grosor
        assert (normal[:, :20] == 2.8).all() and (normal[:, 20:] == 0.8).all()
        assert (negativo[:, :20] == 0.8).all() and (negativo[:, 20:] == 2.8).all()


# --- modelo físico: conversiones y luz transmitida -----------------------------------------------------

def test_el_modelo_directo_es_beer_lambert():
    t = np.linspace(0.8, 2.8, 41)
    luz = lf.luz_transmitida(t)
    assert luz[0] == 1.0 and abs(luz[-1] - 0.05) < 1e-12
    assert (np.diff(luz) < 0).all()
    # multiplicativo: sumar espesor = multiplicar luz
    k = lf.coeficiente_atenuacion(0.05, 0.8, 2.8)
    assert abs(float(lf.luz_transmitida(0.8 + 0.3 + 0.5)) - float(lf.luz_transmitida(0.8 + 0.3)) * float(lf.luz_transmitida(0.8 + 0.5))) < 1e-12
    assert abs(float(lf.luz_transmitida(0.8 + np.log(2) / k)) - 0.5) < 1e-12        # a la media luz pasa la mitad


def test_conversion_entre_luz_minima_y_espesor_de_media_luz():
    for c, esperado in ((0.02, 0.35), (0.05, 0.46), (0.10, 0.60), (0.20, 0.86)):
        assert abs(lf.media_luz_mm(c, 0.8, 2.8) - esperado) < 0.005, (c, lf.media_luz_mm(c, 0.8, 2.8))
        for tmin, tmax in RANGOS:
            assert abs(lf.luz_minima_desde_media_luz(lf.media_luz_mm(c, tmin, tmax), tmin, tmax) - c) < 1e-12
    # con el mismo filamento, más rango de grosor = más oscuro lo más grueso
    media = lf.media_luz_mm(0.05, 0.8, 2.8)
    assert lf.luz_minima_desde_media_luz(media, 0.8, 3.8) < 0.05 < lf.luz_minima_desde_media_luz(media, 0.8, 2.3)


def test_eotf_srgb_valores_conocidos_y_continuidad():
    assert float(lf.eotf_srgb(0.0)) == 0.0 and float(lf.eotf_srgb(1.0)) == 1.0
    assert abs(float(lf.eotf_srgb(128 / 255)) - 0.2158605) < 1e-6                 # el gris 128 de sRGB es 21,6 % de luz
    assert abs(float(lf.eotf_srgb(0.04045)) - 0.04045 / 12.92) < 1e-12            # el codo
    antes, despues = float(lf.eotf_srgb(0.04045 - 1e-9)), float(lf.eotf_srgb(0.04045 + 1e-9))
    assert abs(antes - despues) < 1e-8, "la EOTF no es continua en el codo"
    assert np.allclose(lf.eotf_srgb(BRILLO), _eotf(BRILLO), atol=1e-15, rtol=0)


# --- errores -----------------------------------------------------------------------------------------

def test_parametros_invalidos_dan_value_error():
    with _carpeta() as d:
        mapa = _mapa_brillo(d)
        malos = [
            dict(grosor_min=0), dict(grosor_min=-1), dict(grosor_max=0.8), dict(grosor_max=0.5),
            dict(luz_minima=0.004), dict(luz_minima=0.51), dict(luz_minima=0), dict(luz_minima=float("nan")),
            dict(capa_mm=0), dict(capa_mm=-0.1), dict(capa_mm=2.0), dict(capa_mm=0.12, primera_capa_mm=0),
        ]
        for kwargs in malos:
            try:
                lf.brillo_a_grosor(mapa, **kwargs)
            except ValueError:
                continue
            raise AssertionError(f"{kwargs} tenía que fallar con ValueError")
        for luz in (0.005, 0.5):                                                   # los bordes del rango sí valen
            lf.brillo_a_grosor(mapa, luz_minima=luz)


def test_brillo_invalido_da_error_y_la_entrada_tiene_que_ser_un_mapa_de_brillo():
    for malo in (np.array([0.5, float("nan")]), np.array([0.5, float("inf")]), np.array([0.5, 1.5]), np.array([-0.1, 0.5])):
        try:
            lf.grosor_desde_brillo(malo)
        except ValueError:
            continue
        raise AssertionError(f"{malo} tenía que fallar con ValueError")
    lf.grosor_desde_brillo(np.array([1.0 + 1e-12, -1e-12]))                          # el ruido de punto flotante se tolera
    try:
        lf.brillo_a_grosor(np.zeros((4, 4)))
    except TypeError:
        return
    raise AssertionError("brillo_a_grosor necesita un MapaBrillo")


def test_cuantizar_a_capas_valida_sus_parametros():
    for capa, primera in ((0, 0.2), (-0.1, 0.2), (0.12, 0), (0.12, -0.2)):
        try:
            lf.cuantizar_a_capas(np.array([1.0]), capa, primera)
        except ValueError:
            continue
        raise AssertionError(f"capa={capa}, primera={primera} tenía que fallar")


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
