#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_litofania_simulacion.py
------------------
Red de regresión para L5 de la litofanía (`core/litofania_simulacion.py`): simulación a contraluz. Lo que se cuida:

  * usa EXACTAMENTE el modelo de L2 (`luz_transmitida`): un test con `ast` exige la llamada y prohíbe una
    fórmula propia (ningún `exp`), y otro exige igualdad exacta con ella, también con capas;
  * el ida y vuelta brillo -> grosor -> luz -> brillo es exacto (~1e-15) sin capas, y con capas el error
    queda dentro de las cotas medidas (0,2 mm: 0,09; 0,12 mm: 0,055; 0,08 mm: 0,04 de brillo);
  * lo que se ve es lo que SALE y no un ideal: el negro es el piso `luz_minima` (un gris de ~0,25 con 5 %),
    las capas dan bandas, sin compensar el medio queda más oscuro;
  * un degradé da luz monótona y subir `luz_minima` aclara las sombras sin tocar las luces;
  * la cuantización que deja un punto más fino que `grosor_min` se recorta y se cuenta;
  * no modifica el mapa, valida el tipo, y 800x1000 puntos se simulan en una fracción de segundo.

Las fórmulas de referencia (sRGB, Beer-Lambert) están escritas acá aparte, sin importar las del módulo.
No usa pytest (ver AGENTS.md "Testing") -- funciones `test_*` con `assert` simple,
corribles con `python tests/test_litofania_simulacion.py`.
"""
import ast
import contextlib
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
from PIL import Image

from core import litofania as lf
from core import litofania_simulacion as sim_mod
from core.litofania_simulacion import (SimulacionLuz, brillo_desde_luz, oetf_srgb, simular_contraluz,
                                       simulacion_a_imagen)

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RANGOS = [(0.8, 2.8), (0.4, 3.2), (1.0, 1.5), (0.51, 2.52)]
LUCES_MINIMAS = [0.005, 0.02, 0.05, 0.1, 0.3, 0.5]
COTAS_CAPAS = {0.2: (0.09, 0.028), 0.12: (0.055, 0.017), 0.08: (0.04, 0.012)}   # (error máximo, error medio) de brillo


def _srgb_a_lineal(v):
    v = np.asarray(v, dtype=np.float64)
    return np.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)


def _lineal_a_srgb(x):
    x = np.asarray(x, dtype=np.float64)
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * x ** (1 / 2.4) - 0.055)


@contextlib.contextmanager
def _carpeta():
    with tempfile.TemporaryDirectory() as d:
        yield d


def _degrade(d, ancho=256, alto=8, nombre="degrade.png"):
    """Negro a la izquierda, blanco a la derecha, 256 grises distintos si ancho = 256."""
    return _guardar(d, nombre, np.tile(np.linspace(0, 255, ancho).round().astype(np.uint8), (alto, 1)))


def _guardar(d, nombre, array):
    ruta = os.path.join(d, nombre)
    Image.fromarray(array).save(ruta)
    return ruta


def _mapas(d, ancho_mm=64, px_por_mm=4.0, **kw):
    """(MapaBrillo, MapaGrosor) de un degradé de 256 grises, 1 columna por nivel."""
    mb = lf.imagen_a_mapa_brillo(_degrade(d), ancho_mm, px_por_mm=px_por_mm)
    return mb, lf.brillo_a_grosor(mb, **kw)


def _levanta(excepcion, f, *a, **kw):
    try:
        f(*a, **kw)
    except excepcion as e:
        return e
    except Exception as e:
        raise AssertionError(f"se esperaba {excepcion.__name__} y salió {type(e).__name__}: {e}")
    raise AssertionError(f"se esperaba {excepcion.__name__} y no falló")


# ---------------------------------------------------------------------------
#  (1) Ida y vuelta: brillo -> grosor -> luz -> brillo
# ---------------------------------------------------------------------------

def test_ida_y_vuelta_exacta_sin_capas_en_todos_los_rangos_y_luces_minimas():
    b = np.concatenate([np.linspace(0, 1, 1001), np.random.default_rng(7).random(2000)])
    peor = 0.0
    for gmin, gmax in RANGOS:
        for c in LUCES_MINIMAS:
            g = lf.grosor_desde_brillo(b, gmin, gmax, c)
            luz = lf.luz_transmitida(g, gmin, gmax, c)
            err = np.abs(brillo_desde_luz(luz, c) - b).max()
            peor = max(peor, err)
            assert err < 1e-12, (gmin, gmax, c, err)
    assert peor < 1e-12


def test_ida_y_vuelta_exacta_por_el_pipeline_completo():
    with _carpeta() as d:
        for c in (0.02, 0.05, 0.2):
            mb, mg = _mapas(d, luz_minima=c)
            sim = simular_contraluz(mg)
            assert np.abs(brillo_desde_luz(sim.luz, c) - mb.brillo).max() < 1e-12
            assert sim.px_saturados == 0
            assert abs(sim.luz.max() - 1.0) < 1e-15 and abs(sim.luz.min() - c) < 1e-15   # blanco = 1, negro = el piso


def test_con_capas_el_error_de_brillo_queda_dentro_de_las_cotas_y_es_peor_que_sin_capas():
    with _carpeta() as d:
        mb, mg = _mapas(d)
        sin_capas = np.abs(brillo_desde_luz(simular_contraluz(mg).luz, 0.05) - mb.brillo).max()
        for capa, (cota_max, cota_medio) in COTAS_CAPAS.items():
            mb, mg = _mapas(d, capa_mm=capa)
            err = np.abs(brillo_desde_luz(simular_contraluz(mg).luz, 0.05) - mb.brillo)
            assert err.max() < cota_max and err.mean() < cota_medio, (capa, err.max(), err.mean())
            assert err.max() > 100 * sin_capas                 # la cuantización SÍ se nota: la simulación muestra lo que sale
        # y capas más finas son más fieles
        errores = []
        for capa in (0.2, 0.12, 0.08):
            mb, mg = _mapas(d, capa_mm=capa)
            errores.append(np.abs(brillo_desde_luz(simular_contraluz(mg).luz, 0.05) - mb.brillo).max())
        assert errores[0] > errores[1] > errores[2]


def test_el_negro_se_ve_gris_y_el_blanco_blanco():
    with _carpeta() as d:
        _, mg = _mapas(d, luz_minima=0.05)
        sim = simular_contraluz(mg)
        assert abs(sim.vista[0, 0] - _lineal_a_srgb(0.05)) < 1e-12 and 0.24 < sim.vista[0, 0] < 0.26
        assert sim.vista[0, -1] == 1.0
        img = simulacion_a_imagen(sim)
        assert img.getpixel((0, 0)) == round(float(_lineal_a_srgb(0.05)) * 255) == 63 and img.getpixel((255, 0)) == 255


def test_las_capas_gruesas_dan_bandas_en_la_luz_simulada():
    with _carpeta() as d:
        _, fina = _mapas(d)
        _, gruesa = _mapas(d, capa_mm=0.2)
        niveles_fina = len(np.unique(simular_contraluz(fina).luz[0]))
        niveles_gruesa = len(np.unique(simular_contraluz(gruesa).luz[0]))
        assert niveles_fina == 256 and niveles_gruesa == gruesa.niveles == 11


def test_sin_compensar_el_medio_se_ve_mas_oscuro_que_la_foto():
    with _carpeta() as d:
        mb, mg = _mapas(d, compensar=False)
        recuperado = brillo_desde_luz(simular_contraluz(mg).luz, 0.05)
        i = 128                                                # brillo ~0,5
        assert abs(mb.brillo[0, i] - 0.5) < 0.01 and abs(recuperado[0, i] - 0.465) < 0.01
        assert recuperado[0, i] < mb.brillo[0, i] - 0.03


# ---------------------------------------------------------------------------
#  (2) Usa luz_transmitida de L2, no una fórmula propia
# ---------------------------------------------------------------------------

def test_el_ast_exige_la_llamada_a_luz_transmitida_y_prohibe_una_formula_propia():
    ruta = os.path.join(RAIZ, "core", "litofania_simulacion.py")
    arbol = ast.parse(open(ruta, encoding="utf-8").read())
    funcion = next(n for n in ast.walk(arbol) if isinstance(n, ast.FunctionDef) and n.name == "simular_contraluz")
    llamadas = [n for n in ast.walk(funcion) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and isinstance(n.func.value, ast.Name) and n.func.value.id == "lf" and n.func.attr == "luz_transmitida"]
    assert len(llamadas) == 1, "simular_contraluz tiene que llamar a lf.luz_transmitida exactamente una vez"
    # ninguna exponencial ni logaritmo en todo el módulo: el modelo físico vive solo en L2
    prohibidas = {"exp", "expm1", "log", "log1p", "log2", "log10"}
    for n in ast.walk(arbol):
        if isinstance(n, ast.Call):
            f = n.func
            nombre = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
            assert nombre not in prohibidas, f"fórmula propia ({nombre}) en litofania_simulacion.py"
        assert not (isinstance(n, ast.BinOp) and isinstance(n.op, ast.Pow) and isinstance(n.right, ast.UnaryOp)
                    and isinstance(n.right.op, ast.USub)), "potencia negativa: parece una fórmula propia"


def test_la_luz_es_exactamente_la_de_luz_transmitida_con_y_sin_capas():
    with _carpeta() as d:
        for kw in (dict(), dict(capa_mm=0.12), dict(capa_mm=0.2), dict(grosor_min=0.85, grosor_max=2.75, capa_mm=0.2),
                   dict(grosor_min=0.4, grosor_max=3.2, luz_minima=0.1), dict(compensar=False)):
            _, mg = _mapas(d, **kw)
            sim = simular_contraluz(mg)
            esperado = np.clip(lf.luz_transmitida(mg.grosor, mg.grosor_min, mg.grosor_max, mg.luz_minima), 0.0, 1.0)
            assert np.array_equal(sim.luz, esperado), kw
            assert np.array_equal(sim.vista, _lineal_a_srgb(esperado)) or np.allclose(sim.vista, _lineal_a_srgb(esperado), atol=1e-15)


def test_usa_el_grosor_que_se_imprime_y_los_parametros_pedidos_no_los_efectivos():
    with _carpeta() as d:
        _, mg = _mapas(d, capa_mm=0.12)                      # con capa de 0,12 los extremos efectivos no son los pedidos
        assert abs(mg.grosor_max_efectivo - mg.grosor_max) > 1e-3
        sim = simular_contraluz(mg)
        k = np.log(1 / 0.05) / 2.0                           # Beer-Lambert escrito acá aparte, con los grosores PEDIDOS
        assert np.allclose(sim.luz, np.clip(np.exp(-k * (mg.grosor - 0.8)), 0, 1), atol=1e-12, rtol=0)
        assert (sim.grosor_min, sim.grosor_max, sim.luz_minima) == (0.8, 2.8, 0.05)


def test_la_luz_de_generar_de_L4_es_la_misma_que_la_de_la_simulacion():
    from generators import litofania as gen
    with _carpeta() as d:
        r = gen.generar(_degrade(d, 400, 100), ancho_mm=80, carpeta_salida=d, verificar=False, capa_mm=0.12)
        sim = simular_contraluz(r["mapa_grosor"])
        assert np.array_equal(sim.luz, np.clip(lf.luz_transmitida(r["mapa_grosor"].grosor, 0.8, 2.8, 0.05), 0, 1))
        assert (sim.ancho_px, sim.alto_px) == (r["ancho_px"], r["alto_px"])


# ---------------------------------------------------------------------------
#  (3) Monotonía y efecto de luz_minima
# ---------------------------------------------------------------------------

def test_un_degrade_da_luz_monotona():
    with _carpeta() as d:
        mb, mg = _mapas(d)
        sim = simular_contraluz(mg)
        for fila in (sim.luz[0], sim.vista[0]):
            assert (np.diff(fila) > 0).all()                 # 256 grises distintos -> 256 luces estrictamente crecientes
        # y ante cualquier par de puntos: más brillo en la foto = más luz
        orden = np.argsort(mb.brillo.ravel(), kind="stable")
        assert (np.diff(sim.luz.ravel()[orden]) >= 0).all()
        # mapa 2D: sube con las columnas Y con las filas
        rampa = np.clip(np.add.outer(np.linspace(0, .5, 50), np.linspace(0, .5, 60)), 0, 1)
        mg2 = lf.brillo_a_grosor(lf.MapaBrillo(rampa, 60, 50, 60, 50, 1.0, 1.0, 2 * 59 * 49, 0.0, []))
        luz = simular_contraluz(mg2).luz
        assert (np.diff(luz, axis=0) > 0).all() and (np.diff(luz, axis=1) > 0).all()


def test_subir_luz_minima_aclara_las_sombras_y_no_toca_las_luces():
    with _carpeta() as d:
        sombras, medias_sombras, vistas = [], [], []
        for c in (0.01, 0.02, 0.05, 0.1, 0.2, 0.4):
            mb, mg = _mapas(d, luz_minima=c)
            sim = simular_contraluz(mg)
            assert abs(sim.luz[0, 0] - c) < 1e-15            # el negro de la foto es exactamente el piso
            assert sim.luz[0, -1] == 1.0                     # el blanco no cambia
            oscuras = mb.brillo[0] < 0.3
            medias_sombras.append(sim.luz[0][oscuras].mean())
            vistas.append(sim.vista[0][oscuras].mean())
            sombras.append(sim.luz[0, 0])
        assert all(np.diff(sombras) > 0) and all(np.diff(medias_sombras) > 0) and all(np.diff(vistas) > 0)


def test_la_luz_relativa_solo_depende_de_luz_minima_no_de_los_grosores_absolutos():
    # Beer-Lambert relativo a grosor_min: luz = luz_minima ** ((grosor - grosor_min) / (grosor_max - grosor_min)),
    # y como L2 reparte los grosores en ese mismo rango, el rango (0,8-2,8 o 1,8-3,8 o 0,8-4,0) no cambia la luz
    with _carpeta() as d:
        _, base = _mapas(d)
        luz_base = simular_contraluz(base).luz
        for kw in (dict(grosor_max=4.0), dict(grosor_min=1.8, grosor_max=3.8), dict(grosor_min=0.3, grosor_max=1.1)):
            _, otro = _mapas(d, **kw)
            assert np.allclose(simular_contraluz(otro).luz, luz_base, atol=1e-12, rtol=0), kw
        _, mas_denso = _mapas(d, luz_minima=0.01)
        assert (simular_contraluz(mas_denso).luz[0, 1:-1] < luz_base[0, 1:-1]).all()       # plástico más denso: más oscuro


# ---------------------------------------------------------------------------
#  Saturación, entradas, imagen, velocidad
# ---------------------------------------------------------------------------

def test_la_cuantizacion_que_deja_un_punto_mas_fino_que_grosor_min_se_recorta_y_se_cuenta():
    with _carpeta() as d:
        _, mg = _mapas(d, grosor_min=0.85, capa_mm=0.2)       # el nivel de capa más cercano a 0,85 es 0,8: más fino
        sim = simular_contraluz(mg)
        crudo = lf.luz_transmitida(mg.grosor, 0.85, 2.8, 0.05)
        assert crudo.max() > 1.0 and sim.luz.max() == 1.0
        assert sim.px_saturados == int((mg.grosor < 0.85).sum()) > 0
        assert sim.px_saturados == int((crudo > 1.0).sum())
        # una capa que cae justo en grosor_min pero un bit por debajo (0,9199999999999999) no es "luz de más"
        _, justo = _mapas(d, grosor_min=0.92, grosor_max=2.92, capa_mm=0.12)
        assert (justo.grosor < 0.92).any() and lf.luz_transmitida(justo.grosor, 0.92, 2.92, 0.05).max() > 1.0
        assert simular_contraluz(justo).px_saturados == 0
        # sin capas, ningún punto satura aunque el blanco dé exactamente 1,0 (el límite no cuenta)
        _, sin = _mapas(d)
        assert simular_contraluz(sin).px_saturados == 0 and simular_contraluz(sin).luz.max() == 1.0


def test_no_modifica_el_mapa_y_devuelve_copias():
    with _carpeta() as d:
        _, mg = _mapas(d, capa_mm=0.12)
        antes = mg.grosor.copy()
        sim = simular_contraluz(mg)
        assert np.array_equal(mg.grosor, antes)
        sim.luz[:] = 0.0
        sim.vista[:] = 0.0
        assert np.array_equal(mg.grosor, antes) and not np.shares_memory(sim.luz, mg.grosor)
        assert not np.shares_memory(sim.luz, sim.vista)


def test_solo_acepta_un_mapa_de_grosor():
    with _carpeta() as d:
        mb, mg = _mapas(d)
        for malo in (mb, mg.grosor, None, "x", 3.0):
            _levanta(TypeError, simular_contraluz, malo)


def test_campos_y_forma_coinciden_con_el_mapa_de_grosor():
    with _carpeta() as d:
        _, mg = _mapas(d, ancho_mm=64, px_por_mm=2.0)
        sim = simular_contraluz(mg)
        assert isinstance(sim, SimulacionLuz)
        assert sim.luz.shape == sim.vista.shape == mg.grosor.shape == (sim.alto_px, sim.ancho_px)
        assert (sim.ancho_mm, sim.alto_mm, sim.px_por_mm) == (mg.ancho_mm, mg.alto_mm, mg.px_por_mm)
        _, otro = _mapas(d, grosor_min=0.4, grosor_max=3.2, luz_minima=0.1)
        sim = simular_contraluz(otro)
        assert (sim.grosor_min, sim.grosor_max, sim.luz_minima) == (0.4, 3.2, 0.1)    # los pedidos, no los defaults
        assert sim.luz.dtype == sim.vista.dtype == np.float64
        assert sim.luz.min() >= 0.0 and sim.luz.max() <= 1.0 and sim.vista.min() >= 0.0 and sim.vista.max() <= 1.0


def test_la_imagen_es_pil_de_8_bits_con_el_tamano_y_los_valores_de_la_vista():
    with _carpeta() as d:
        _, mg = _mapas(d, capa_mm=0.12)
        sim = simular_contraluz(mg)
        img = simulacion_a_imagen(sim)
        assert img.mode == "L" and img.size == (sim.ancho_px, sim.alto_px)
        assert np.array_equal(np.asarray(img), np.round(sim.vista * 255).astype(np.uint8))   # redondeo, no truncado
        assert not np.array_equal(np.asarray(img), np.round(sim.luz * 255).astype(np.uint8))  # y es la vista sRGB, no la luz lineal
        assert np.array_equal(np.asarray(simulacion_a_imagen(sim.vista)), np.asarray(img))   # acepta también el array
        assert np.asarray(simulacion_a_imagen(np.array([[-1.0, 2.0]]))).tolist() == [[0, 255]]


def test_oetf_es_la_inversa_de_la_eotf_de_L2_y_coincide_con_la_formula_aparte():
    v = np.linspace(0, 1, 2001)
    assert np.abs(oetf_srgb(lf.eotf_srgb(v)) - v).max() < 1e-12
    x = np.concatenate([np.linspace(0, 0.01, 500), np.linspace(0, 1, 1001)])
    assert np.abs(lf.eotf_srgb(oetf_srgb(x)) - x).max() < 1e-12
    assert np.abs(oetf_srgb(x) - _lineal_a_srgb(x)).max() < 1e-12
    assert oetf_srgb(np.array([-0.5, 0.0, 2.0])).tolist() == [0.0, 0.0, 1.0]            # fuera de [0, 1] se recorta
    assert oetf_srgb(0.0) == 0.0 and oetf_srgb(1.0) == 1.0 and abs(float(oetf_srgb(0.5)) - 0.7354) < 1e-4


def test_brillo_desde_luz_valida_y_recorta():
    for malo in (-0.1, 1.0, 2.0, float("nan")):
        _levanta(ValueError, brillo_desde_luz, np.array([0.5]), malo)
    assert brillo_desde_luz(np.array([0.0, 1.0, 5.0]), 0.05).tolist() == [0.0, 1.0, 1.0]    # bajo el piso -> 0, sobre 1 -> 1
    assert abs(float(brillo_desde_luz(0.05, 0.05))) == 0.0 and float(brillo_desde_luz(1.0, 0.05)) == 1.0


def test_800_por_1000_puntos_se_simulan_rapido():
    mapa = lf.MapaBrillo(np.random.default_rng(1).random((1000, 800)), 200, 250, 800, 1000, 4.0, 4.0, 0, 0.0, [])
    mg = lf.brillo_a_grosor(mapa)
    t0 = time.perf_counter()
    sim = simular_contraluz(mg)
    img = simulacion_a_imagen(sim)
    assert time.perf_counter() - t0 < 1.0 and img.size == (800, 1000)


def test_foto_real_de_punta_a_punta():
    from skimage import data
    with _carpeta() as d:
        ruta = _guardar(d, "astronauta.png", data.astronaut())
        mb = lf.imagen_a_mapa_brillo(ruta, 100, px_por_mm=4.0)
        mg = lf.brillo_a_grosor(mb)
        sim = simular_contraluz(mg)
        assert np.abs(brillo_desde_luz(sim.luz, 0.05) - mb.brillo).max() < 1e-12
        assert sim.vista.min() >= _lineal_a_srgb(0.05) - 1e-12           # nada más oscuro que el piso de la placa
        assert simulacion_a_imagen(sim).size == (400, 400)


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
