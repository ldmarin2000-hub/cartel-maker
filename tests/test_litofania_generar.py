#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_litofania_generar.py
------------------
Red de regresión para L4 de la litofanía (`generators/litofania.py`): imagen -> STL de punta a punta. Lo que se cuida:

  * `generar()` da un STL watertight (se vuelve a leer del disco y se verifica por separado) y un dict con
    el contrato del proyecto (las mismas claves que Esculturas, menos el PNG), coherente con el archivo;
  * es la cadena L1 -> L2 -> L3 sin atajos: con los mismos parámetros sale la misma malla que armada a mano;
  * los avisos saltan cuando deben y SOLO entonces: placa que no entra en la A1 (en las dos orientaciones),
    resolución que la boquilla no aprovecha, grosor frágil, bandas por capa gruesa, peso real del STL, y los
    avisos de L1/L2 reenviados sin repetirse; una litofanía sana no avisa nada;
  * un archivo o parámetro inválido da FileNotFoundError / ValueError (nunca ValidationError) y no deja
    archivos a medias;
  * `main.py` lista "Litofanía" y `ejecutar()` corre de punta a punta (con `input` simulado).

Fotos: gradientes y tableros generados acá, y `skimage.data.astronaut()` (dominio público) como foto real.
No usa pytest (ver AGENTS.md "Testing") -- funciones `test_*` con `assert` simple,
corribles con `python tests/test_litofania_generar.py`.
"""
import ast
import builtins
import contextlib
import inspect
import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import trimesh
from PIL import Image

from core import litofania as lf
from generators import litofania as gen

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLAVES_ESCULTURAS_SIN_PNG = {"ruta_stl", "ancho_mm", "alto_mm", "profundidad_mm", "vertices", "caras",
                             "watertight", "info", "avisos", "entra_a1", "mensaje_a1"}


@contextlib.contextmanager
def _carpeta():
    with tempfile.TemporaryDirectory() as d:
        yield d


def _guardar(d, nombre, array):
    ruta = os.path.join(d, nombre)
    Image.fromarray(array).save(ruta)
    return ruta


def _degrade(d, ancho=600, alto=400, nombre="degrade.png"):
    """Negro a la izquierda, blanco a la derecha."""
    return _guardar(d, nombre, np.tile(np.linspace(0, 255, ancho).astype(np.uint8), (alto, 1)))


def _tablero(d, celdas=8, lado=480, nombre="tablero.png"):
    f = np.arange(lado) // (lado // celdas)
    return _guardar(d, nombre, (((f[:, None] + f[None, :]) % 2) * 255).astype(np.uint8))


def _astronauta(d):
    from skimage import data
    return _guardar(d, "astronauta.png", data.astronaut())


def _generar(ruta, d, **kw):
    kw.setdefault("carpeta_salida", d)
    kw.setdefault("verificar", False)
    return gen.generar(ruta, **kw)


def _cargar_stl(ruta):
    return trimesh.load(ruta, force="mesh")


def _levanta(excepcion, f, *a, **kw):
    try:
        f(*a, **kw)
    except excepcion as e:
        return e
    except Exception as e:  # otra clase de error: no es lo que se promete
        raise AssertionError(f"se esperaba {excepcion.__name__} y salió {type(e).__name__}: {e}")
    raise AssertionError(f"se esperaba {excepcion.__name__} y no falló")


def _con(texto, avisos):
    return [a for a in avisos if texto in a]


# ---------------------------------------------------------------------------
#  (1) De punta a punta: STL watertight y dict con el contrato del proyecto
# ---------------------------------------------------------------------------

def test_degrade_de_punta_a_punta_da_stl_watertight_que_se_verifica_al_releerlo():
    with _carpeta() as d:
        r = gen.generar(_degrade(d), ancho_mm=100, carpeta_salida=d, verificar=True)
        assert os.path.isfile(r["ruta_stl"]) and r["ruta_stl"].endswith("_litofania.stl")
        m = _cargar_stl(r["ruta_stl"])                       # lo que va a ver el laminador, no lo que armamos en memoria
        v = lf.verificar_malla(m)
        assert v["ok"] and v["watertight"] and v["euler"] == 2 and v["volumen_positivo"], v
        assert r["watertight"] is True and r["verificacion"]["ok"] is True
        assert len(m.faces) == r["caras"] and len(m.vertices) == r["vertices"]


def test_el_dict_tiene_las_claves_de_esculturas_y_las_propias():
    claves = set()
    src = open(os.path.join(RAIZ, "generators", "esculturas.py"), encoding="utf-8").read()
    for nodo in ast.walk(ast.parse(src)):
        if isinstance(nodo, ast.FunctionDef) and nodo.name == "generar":
            for ret in ast.walk(nodo):
                if isinstance(ret, ast.Return) and isinstance(ret.value, ast.Dict):
                    claves |= {k.value for k in ret.value.keys if isinstance(k, ast.Constant)}
    assert CLAVES_ESCULTURAS_SIN_PNG <= claves, "cambió el contrato de Esculturas: revisar L4"
    with _carpeta() as d:
        r = _generar(_degrade(d), d)
        faltan = (claves - {"ruta_png"}) - set(r)
        assert not faltan, f"faltan claves del contrato: {faltan}"
        for k in ("ancho_px", "alto_px", "px_por_mm", "grosor_min", "grosor_max", "niveles", "luz_minima",
                  "media_luz_mm", "stl_mb", "verificacion", "tiempos", "mapa_brillo", "mapa_grosor"):
            assert k in r, k
        assert isinstance(r["info"], list) and isinstance(r["avisos"], list)
        assert isinstance(r["entra_a1"], bool) and isinstance(r["watertight"], bool)
        assert all(isinstance(t, str) for t in r["info"] + r["avisos"] + [r["mensaje_a1"]])
        assert "ruta_png" not in r                            # sin preview: la simulación a contraluz es L5


def test_el_dict_coincide_con_el_archivo_exportado():
    with _carpeta() as d:
        r = _generar(_degrade(d, 600, 400), d, ancho_mm=120, px_por_mm=3.0)
        m = _cargar_stl(r["ruta_stl"])
        (minx, miny, minz), (maxx, maxy, maxz) = m.bounds
        assert abs(r["ancho_mm"] - (maxx - minx)) < 1e-4 and abs(r["alto_mm"] - (maxy - miny)) < 1e-4
        assert abs(r["profundidad_mm"] - (maxz - minz)) < 1e-4
        assert abs(r["ancho_mm"] - 120) < 1e-4 and abs(r["alto_mm"] - 80) < 1e-4      # el alto sale de la foto (3:2)
        assert r["stl_mb"] == os.path.getsize(r["ruta_stl"]) / 1e6                     # medido del archivo, no estimado
        assert os.path.getsize(r["ruta_stl"]) == 84 + 50 * r["caras"]                  # STL binario
        assert r["ancho_px"] == r["mapa_grosor"].ancho_px == 360 and r["alto_px"] == 240
        assert abs(r["profundidad_mm"] - lf.GROSOR_MAX_DEFAULT) < 1e-5


def test_foto_real_de_punta_a_punta_sin_avisos():
    with _carpeta() as d:
        r = gen.generar(_astronauta(d), ancho_mm=100, carpeta_salida=d, verificar=True)
        assert r["verificacion"]["ok"] and r["watertight"]
        assert r["entra_a1"] is True
        assert r["avisos"] == [], r["avisos"]                  # una litofanía sana no avisa nada
        assert r["ancho_px"] == r["alto_px"] == 400            # 512 px de foto a 100 mm: 5,12 px/mm disponibles, pide 4
        m = _cargar_stl(r["ruta_stl"])
        assert lf.verificar_malla(m)["ok"]
        assert 0.8 - 1e-6 <= r["mapa_grosor"].grosor.min() and r["mapa_grosor"].grosor.max() <= 2.8 + 1e-6
        assert set(r["tiempos"]) >= {"imagen_a_brillo", "brillo_a_grosor", "grosor_a_malla", "verificacion", "exportacion"}


def test_tablero_de_punta_a_punta_tiene_solo_los_dos_grosores_extremos():
    with _carpeta() as d:
        r = gen.generar(_tablero(d), ancho_mm=80, px_por_mm=4.0, carpeta_salida=d, verificar=True)
        assert r["watertight"] and r["verificacion"]["ok"]
        g = r["mapa_grosor"].grosor
        assert abs(g.min() - 0.8) < 1e-9 and abs(g.max() - 2.8) < 1e-9
        # el centro de cada casilla (8x8, de 40 px) es solo negro (2,8) o solo blanco (0,8), como en la foto
        centros = (np.arange(8) * 40 + 20)
        centro = g[np.ix_(centros, centros)]
        assert np.isclose(np.sort(np.unique(np.round(centro, 6))), [0.8, 2.8]).all()
        assert (np.isclose(centro, 0.8) | np.isclose(centro, 2.8)).all()
        assert abs(np.isclose(centro, 2.8).mean() - 0.5) < 1e-9          # la mitad negras, la mitad blancas
        assert np.isclose(centro[0, 0], 2.8) and np.isclose(centro[0, 1], 0.8)    # arriba a la izquierda la foto es negra


def test_es_la_cadena_L1_L2_L3_sin_atajos_misma_malla_que_a_mano():
    with _carpeta() as d:
        ruta = _astronauta(d)
        kw = dict(ancho_mm=60, alto_mm=45, px_por_mm=3.0, grosor_min=0.9, grosor_max=3.0, luz_minima=0.08,
                  compensar=True, invertir=True, cara_visible="plana", capa_mm=0.12, primera_capa_mm=0.2,
                  desplazamiento=(0.3, -0.2), brillo=0.05, contraste=1.2, gamma=0.9, auto_niveles=True,
                  suavizado_mm=0.2, diagonal="fija")
        r = _generar(ruta, d, **kw)
        mb = lf.imagen_a_mapa_brillo(ruta, 60, 45, px_por_mm=3.0, desplazamiento=(0.3, -0.2), brillo=0.05,
                                     contraste=1.2, gamma=0.9, auto_niveles=True, suavizado_mm=0.2, invertir=True)
        mg = lf.brillo_a_grosor(mb, 0.9, 3.0, 0.08, True, 0.12, 0.2)
        a_mano = lf.malla_desde_grosor(mg, cara_visible="plana", diagonal="fija")
        assert np.array_equal(r["mapa_brillo"].brillo, mb.brillo) and np.array_equal(r["mapa_grosor"].grosor, mg.grosor)
        m = _cargar_stl(r["ruta_stl"])
        assert len(m.faces) == len(a_mano.faces)
        # el STL guarda float32: mismas coordenadas a esa precisión
        assert np.allclose(np.sort(m.vertices, axis=0), np.sort(a_mano.vertices, axis=0), atol=1e-4)
        # y las MISMAS caras (incluida la diagonal de cada celda): cada centroide tiene su par en la otra malla
        from scipy.spatial import cKDTree
        ca, cb = m.triangles.mean(axis=1), a_mano.triangles.mean(axis=1)
        assert cKDTree(cb).query(ca)[0].max() < 1e-3 and cKDTree(ca).query(cb)[0].max() < 1e-3
        assert abs(m.volume - a_mano.volume) / a_mano.volume < 1e-5


def test_el_generador_llama_a_las_tres_etapas_y_a_la_verificacion():
    arbol = ast.parse(inspect.getsource(gen.generar))
    llamadas = {n.func.attr for n in ast.walk(arbol) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and isinstance(n.func.value, ast.Name) and n.func.value.id == "lf"}
    assert {"imagen_a_mapa_brillo", "brillo_a_grosor", "malla_desde_grosor", "verificar_malla"} <= llamadas, llamadas


def test_los_defaults_son_los_de_la_litofania_y_las_opciones_se_respetan():
    p = inspect.signature(gen.generar).parameters
    assert p["px_por_mm"].default == lf.PX_POR_MM_DEFAULT and p["grosor_min"].default == lf.GROSOR_MIN_DEFAULT
    assert p["grosor_max"].default == lf.GROSOR_MAX_DEFAULT and p["luz_minima"].default == lf.LUZ_MINIMA_DEFAULT
    assert p["primera_capa_mm"].default == lf.PRIMERA_CAPA_DEFAULT
    assert p["compensar"].default is True and p["verificar"].default is True and p["invertir"].default is False
    assert p["cara_visible"].default == "relieve" and p["diagonal"].default == "adaptativa"
    assert p["capa_mm"].default is None and p["boquilla_mm"].default == 0.4 and p["ancho_mm"].default == 100.0
    with _carpeta() as d:
        r = _generar(_degrade(d), d)
        mg = r["mapa_grosor"]
        assert (mg.grosor_min, mg.grosor_max, mg.luz_minima, mg.compensado) == (0.8, 2.8, 0.05, True)
        assert abs(r["px_por_mm"] - 4.0) < 1e-9


def test_compensar_invertir_y_cara_visible_llegan_a_la_malla():
    with _carpeta() as d:
        ruta = _degrade(d, 200, 100)
        a = _generar(ruta, d, ancho_mm=50, px_por_mm=2.0, prefijo="a")
        b = _generar(ruta, d, ancho_mm=50, px_por_mm=2.0, prefijo="b", compensar=False)
        assert a["mapa_grosor"].compensado is True and b["mapa_grosor"].compensado is False
        assert not np.allclose(a["mapa_grosor"].grosor, b["mapa_grosor"].grosor)
        # sin compensar es lineal: el medio del degradé queda justo en el medio del rango
        medio = b["mapa_grosor"].grosor[:, b["mapa_grosor"].ancho_px // 2].mean()
        assert abs(medio - 1.8) < 0.05

        # el degradé va de negro (izq.) a blanco (der.): oscuro = grueso. Con invertir, al revés.
        g = a["mapa_grosor"].grosor
        assert g[:, 0].mean() > 2.7 and g[:, -1].mean() < 0.9
        i = _generar(ruta, d, ancho_mm=50, px_por_mm=2.0, prefijo="i", invertir=True)["mapa_grosor"].grosor
        assert i[:, 0].mean() < 0.9 and i[:, -1].mean() > 2.7

        # en el STL: la cara "relieve" se lee derecha desde +Z; con "plana" se espeja X
        def z_frente(r):
            m = _cargar_stl(r["ruta_stl"])
            v = m.vertices[m.vertices[:, 2] > 0.5]                  # solo el frente
            izq, der = v[v[:, 0] < 5][:, 2].mean(), v[v[:, 0] > 45][:, 2].mean()
            return izq, der
        izq, der = z_frente(a)
        assert izq > der + 1.0
        izq, der = z_frente(_generar(ruta, d, ancho_mm=50, px_por_mm=2.0, prefijo="p", cara_visible="plana"))
        assert der > izq + 1.0


def test_px_por_mm_y_las_medidas_pedidas_se_respetan():
    with _carpeta() as d:
        ruta = _degrade(d, 1200, 800)
        for px in (2.0, 3.0, 5.0):
            r = _generar(ruta, d, ancho_mm=100, px_por_mm=px, prefijo=f"p{px:g}")
            assert r["ancho_px"] == round(100 * px) and abs(r["px_por_mm"] - px) < 1e-9, (px, r["ancho_px"])
        # alto pedido con otra proporción: se recorta, y la placa mide lo pedido (no lo de la foto)
        r = _generar(ruta, d, ancho_mm=100, alto_mm=100, px_por_mm=2.0, prefijo="cuad")
        assert abs(r["ancho_mm"] - 100) < 1e-4 and abs(r["alto_mm"] - 100) < 1e-4
        assert _con("recort", r["avisos"])


def test_el_nombre_del_archivo_sale_de_la_imagen_o_del_prefijo():
    with _carpeta() as d:
        ruta = _degrade(d, 100, 80, nombre="mi foto (1).png")
        assert os.path.basename(_generar(ruta, d, px_por_mm=1.0)["ruta_stl"]) == "mi_foto__1_litofania.stl"
        assert os.path.basename(_generar(ruta, d, px_por_mm=1.0, prefijo="x y")["ruta_stl"]) == "x_y_litofania.stl"
        sub = os.path.join(d, "no", "existe", "todavia")
        r = _generar(ruta, d, px_por_mm=1.0, carpeta_salida=sub)
        assert os.path.isfile(r["ruta_stl"]) and os.path.dirname(r["ruta_stl"]) == sub


def test_verificar_se_puede_apagar():
    with _carpeta() as d:
        ruta = _degrade(d, 100, 80)
        r = _generar(ruta, d, px_por_mm=1.0, verificar=False)
        assert r["verificacion"] is None and "verificacion" not in r["tiempos"] and r["watertight"] is True
        r = gen.generar(ruta, px_por_mm=1.0, carpeta_salida=d)       # el default es verificar
        assert r["verificacion"]["ok"] is True and "verificacion" in r["tiempos"]


# ---------------------------------------------------------------------------
#  (2) Los avisos saltan cuando deben y SOLO entonces
# ---------------------------------------------------------------------------

def _proporcional(d, ancho_mm, alto_mm, nombre="prop.png"):
    """Foto con la proporción exacta de la placa (3 px/mm: alcanza para pedir 2 sin que L1 avise nada)."""
    return _degrade(d, int(ancho_mm * 3), int(alto_mm * 3), nombre)


def test_placa_que_no_entra_en_la_a1_avisa_en_las_dos_orientaciones():
    with _carpeta() as d:
        horizontal = _generar(_proporcional(d, 300, 100), d, ancho_mm=300, alto_mm=100, px_por_mm=2.0, prefijo="h")
        vertical = _generar(_proporcional(d, 100, 300), d, ancho_mm=100, alto_mm=300, px_por_mm=2.0, prefijo="v")
        for r in (horizontal, vertical):
            assert r["entra_a1"] is False and "NO entra" in r["mensaje_a1"]
            assert len(r["avisos"]) == 1 and "NO entra" in r["avisos"][0], r["avisos"]
            assert "módulos" in r["avisos"][0] and "máximo es 256" in r["avisos"][0] and "conviene" not in r["avisos"][0]
        assert horizontal["mensaje_a1"].split(":")[1] == vertical["mensaje_a1"].split(":")[1]   # mismas medidas ordenadas
        # y una placa de 200 x 100 sí entra, en las dos orientaciones, sin ningún aviso
        for ancho, alto in ((200, 100), (100, 200)):
            r = _generar(_proporcional(d, ancho, alto), d, ancho_mm=ancho, alto_mm=alto, px_por_mm=2.0)
            assert r["entra_a1"] is True and r["avisos"] == [], (ancho, alto, r["avisos"])


def test_umbrales_de_la_a1_240_256():
    with _carpeta() as d:
        r = _generar(_proporcional(d, 240, 100), d, ancho_mm=240, alto_mm=100, px_por_mm=2.0)
        assert r["entra_a1"] is True and r["avisos"] == []                         # 240 justo: todavía recomendado
        for ancho, alto in ((250, 100), (100, 250), (256, 100)):
            r = _generar(_proporcional(d, ancho, alto), d, ancho_mm=ancho, alto_mm=alto, px_por_mm=2.0)
            assert r["entra_a1"] is False and "NO entra" not in r["mensaje_a1"]
            assert len(r["avisos"]) == 1 and "entra justo" in r["avisos"][0] and "módulos" in r["avisos"][0], (ancho, alto)
            assert "conviene achicar" in r["avisos"][0] and "máximo es" not in r["avisos"][0]
        r = _generar(_proporcional(d, 257, 100), d, ancho_mm=257, alto_mm=100, px_por_mm=2.0)
        assert r["entra_a1"] is False and len(r["avisos"]) == 1 and "NO entra" in r["avisos"][0]
        assert "máximo es 256" in r["avisos"][0]
        # el lado menor también cuenta: 257 de alto no entra aunque el ancho sí
        r = _generar(_proporcional(d, 100, 257), d, ancho_mm=100, alto_mm=257, px_por_mm=2.0)
        assert r["entra_a1"] is False and "NO entra" in r["avisos"][0]


def test_resolucion_mayor_que_la_que_aprovecha_la_boquilla_avisa_y_solo_entonces():
    with _carpeta() as d:
        ruta = _degrade(d, 800, 600)                                               # 16 px/mm disponibles a 50 mm
        for px in (2.0, 4.0, 5.0):
            r = _generar(ruta, d, ancho_mm=50, px_por_mm=px)
            assert r["avisos"] == [], (px, r["avisos"])
        for px in (5.5, 6.0, 8.0):
            r = _generar(ruta, d, ancho_mm=50, px_por_mm=px)
            assert len(r["avisos"]) == 1 and "boquilla" in r["avisos"][0] and "0.4" in r["avisos"][0].replace(",", "."), (px, r["avisos"])
        # la boquilla cambia el umbral: 0,6 mm aprovecha 3,3 px/mm; 0,2 mm aprovecha 10
        assert len(_generar(ruta, d, ancho_mm=50, px_por_mm=4.0, boquilla_mm=0.6)["avisos"]) == 1
        assert _generar(ruta, d, ancho_mm=50, px_por_mm=8.0, boquilla_mm=0.2)["avisos"] == []


def test_grosor_fragil_avisa_por_debajo_de_0_6_mm_y_solo_entonces():
    with _carpeta() as d:
        ruta = _degrade(d, 200, 100)
        kw = dict(ancho_mm=50, px_por_mm=2.0)
        for gmin in (0.6, 0.8, 1.0):
            assert _generar(ruta, d, grosor_min=gmin, **kw)["avisos"] == [], gmin
        for gmin in (0.59, 0.4, 0.3):
            av = _generar(ruta, d, grosor_min=gmin, **kw)["avisos"]
            assert len(av) == 1 and "frágil" in av[0], (gmin, av)
        # por debajo de la primera capa hay dos problemas distintos y se avisan los dos, una vez cada uno
        av = _generar(ruta, d, grosor_min=0.1, **kw)["avisos"]
        assert len(_con("frágil", av)) == 1 and len(_con("primera capa", av)) == 1 and len(av) == 2, av
        av = _generar(ruta, d, grosor_min=0.1, capa_mm=0.2, **kw)["avisos"]            # con capa lo avisa L2: sin repetir
        assert len(_con("primera capa", av)) == 1, av
        # con capa, lo que cuenta es el grosor que de verdad sale (0,55 -> 0,6: ya no es frágil)
        av = _generar(ruta, d, grosor_min=0.55, capa_mm=0.2, **kw)["avisos"]
        assert not _con("frágil", av), av


def test_capas_gruesas_avisan_bandas_y_las_finas_no():
    with _carpeta() as d:
        ruta = _degrade(d, 200, 100)
        gruesa = _generar(ruta, d, ancho_mm=50, px_por_mm=2.0, capa_mm=0.2)
        assert gruesa["niveles"] == 11 and len(_con("bandas", gruesa["avisos"])) == 1, gruesa["avisos"]
        fina = _generar(ruta, d, ancho_mm=50, px_por_mm=2.0, capa_mm=0.08)
        assert fina["niveles"] == 26 and not _con("bandas", fina["avisos"]), fina["avisos"]
        sin = _generar(ruta, d, ancho_mm=50, px_por_mm=2.0)
        assert sin["niveles"] is None and sin["avisos"] == []


def test_peso_real_del_stl_avisa_con_los_numeros_reales_y_una_sola_vez():
    with _carpeta() as d:
        ruta = _degrade(d, 400, 300)
        original = lf.PESO_STL_AVISO_MB
        try:
            lf.PESO_STL_AVISO_MB = 0.05
            r = _generar(ruta, d, ancho_mm=60, px_por_mm=4.0)
        finally:
            lf.PESO_STL_AVISO_MB = original
        pesadas = _con("pesada", r["avisos"])
        assert len(pesadas) == 1, r["avisos"]                  # el de L1 es una estimación: se reemplaza, no se suma
        assert f"{r['stl_mb']:.0f} MB" in pesadas[0] and f"{r['caras'] / 1e6:.1f} millones" in pesadas[0]
        r = _generar(ruta, d, ancho_mm=60, px_por_mm=4.0)
        assert r["avisos"] == []


def test_los_avisos_de_L1_y_L2_se_reenvian_sin_repetirse():
    with _carpeta() as d:
        # foto chica para el tamaño: L1 avisa que no la agranda y que la resolución es baja
        r = _generar(_degrade(d, 100, 80), d, ancho_mm=100, px_por_mm=4.0)
        assert len(_con("no se agranda", r["avisos"])) == 1 and len(_con("Resolución baja", r["avisos"])) == 1, r["avisos"]
        assert len(set(r["avisos"])) == len(r["avisos"])
        assert r["avisos"] == r["mapa_brillo"].avisos
        # transparencia
        rgba = np.zeros((60, 80, 4), np.uint8)
        rgba[..., :3] = 128
        rgba[:30, :, 3] = 255
        ruta = _guardar(d, "t.png", rgba)
        r = _generar(ruta, d, ancho_mm=20, px_por_mm=2.0)
        assert len(_con("transparencia", r["avisos"])) == 1, r["avisos"]
        # L2: grosores que no caen en capas
        r = _generar(_degrade(d, 200, 100), d, ancho_mm=50, px_por_mm=2.0, capa_mm=0.12)
        assert _con("caen en", r["avisos"]) and set(r["mapa_grosor"].avisos) <= set(r["avisos"])


def test_la_litofania_sana_no_avisa_nada():
    with _carpeta() as d:
        for ruta in (_degrade(d, 600, 400), _tablero(d), _astronauta(d)):
            r = gen.generar(ruta, ancho_mm=100, carpeta_salida=d, verificar=True)
            assert r["avisos"] == [] and r["entra_a1"] is True, (ruta, r["avisos"])
            assert r["info"], "las notas informativas no son avisos y siempre vienen"


def test_las_notas_dicen_las_medidas_reales_y_la_orientacion():
    with _carpeta() as d:
        r = _generar(_degrade(d, 600, 400), d, ancho_mm=100)
        texto = "\n".join(r["info"])
        assert "100.0 x 66.7 mm" in texto and "0.80 a 2.80" in texto and f"{r['stl_mb']:.1f} MB" in texto
        assert "acostada" in texto and "derecha mirando la cara con relieve" in texto
        r = _generar(_degrade(d, 600, 400), d, ancho_mm=100, cara_visible="plana", prefijo="p")
        assert "cara lisa" in "\n".join(r["info"]) and "con relieve." not in "\n".join(r["info"])


def test_el_redondeo_de_pixeles_no_dispara_el_aviso_de_resolucion_en_el_limite():
    with _carpeta() as d:
        ruta = _degrade(d, 800, 400)
        r = _generar(ruta, d, ancho_mm=100.3, px_por_mm=5.0)           # 501,5 px -> 502: 5,005 px/mm, el límite pedido
        assert r["px_por_mm"] > 5.0 and r["avisos"] == [], r["avisos"]


def test_el_grosor_total_tambien_cuenta_para_la_a1():
    with _carpeta() as d:
        r = _generar(_proporcional(d, 40, 30), d, ancho_mm=40, alto_mm=30, px_por_mm=2.0, grosor_max=300.0)
        assert r["entra_a1"] is False and r["profundidad_mm"] > 256 and "NO entra" in r["avisos"][0], r["avisos"]


def test_si_la_malla_no_cierra_el_dict_lo_dice_y_no_miente():
    from trimesh import Trimesh
    original = lf.malla_desde_grosor

    def rota(*a, **k):
        m = original(*a, **k)
        return Trimesh(vertices=m.vertices, faces=m.faces[:-3], process=False)      # le falta un pedazo de la trasera

    lf.malla_desde_grosor = rota
    try:
        with _carpeta() as d:
            ruta = _degrade(d, 100, 80)
            for verificar in (True, False):
                r = _generar(ruta, d, px_por_mm=1.0, verificar=verificar)
                assert r["watertight"] is False, verificar
            assert gen.generar(ruta, px_por_mm=1.0, carpeta_salida=d)["verificacion"]["ok"] is False
    finally:
        lf.malla_desde_grosor = original


# ---------------------------------------------------------------------------
#  (3) Un archivo o parámetro inválido da ValueError / FileNotFoundError, no tira la página
# ---------------------------------------------------------------------------

def _sin_archivos(d):
    return [f for f in os.listdir(d)]


def test_imagen_inexistente_da_filenotfounderror():
    with _carpeta() as d:
        e = _levanta(FileNotFoundError, gen.generar, os.path.join(d, "no_existe.png"), carpeta_salida=d)
        assert "no encuentro la imagen" in str(e)
        _levanta(FileNotFoundError, gen.generar, "", carpeta_salida=d)
        _levanta(FileNotFoundError, gen.generar, None, carpeta_salida=d)
        assert _sin_archivos(d) == []


def test_archivo_invalido_da_valueerror_y_nunca_validationerror():
    from core.validation import ValidationError
    with _carpeta() as d:
        txt = os.path.join(d, "notas.txt")
        open(txt, "w").write("no soy una imagen")
        roto = os.path.join(d, "roto.png")
        open(roto, "wb").write(b"\x89PNG\r\n\x1a\n" + os.urandom(300))
        chico = _guardar(d, "uno.png", np.zeros((1, 50), np.uint8))
        antes = set(_sin_archivos(d))
        for ruta in (txt, roto, chico):
            e = _levanta(ValueError, gen.generar, ruta, carpeta_salida=d)
            assert not isinstance(e, ValidationError) and str(e), ruta
        assert set(_sin_archivos(d)) == antes                 # no dejó un STL a medias


def test_parametros_sin_sentido_dan_valueerror_antes_de_exportar():
    with _carpeta() as d:
        ruta = _degrade(d, 100, 80)
        antes = set(_sin_archivos(d))
        malos = [dict(ancho_mm=0), dict(ancho_mm=-5), dict(alto_mm=0), dict(px_por_mm=100), dict(px_por_mm=0.1),
                 dict(grosor_min=3.0, grosor_max=2.0), dict(grosor_min=0), dict(luz_minima=0), dict(luz_minima=2),
                 dict(cara_visible="atras"), dict(diagonal="zigzag"), dict(boquilla_mm=0), dict(boquilla_mm=-0.4),
                 dict(capa_mm=-0.1), dict(capa_mm=5.0), dict(desplazamiento=(2, 0)), dict(gamma=0)]
        for kw in malos:
            _levanta(ValueError, gen.generar, ruta, carpeta_salida=d, verificar=False, **kw)
        assert set(_sin_archivos(d)) == antes


# ---------------------------------------------------------------------------
#  (4) main.py lista "Litofanía" y ejecutar() corre
# ---------------------------------------------------------------------------

def test_main_lista_litofania_y_cumple_el_contrato():
    import main
    with contextlib.redirect_stdout(io.StringIO()):
        generadores = main._descubrir_generadores()
    nombres = [g.NOMBRE for g in generadores]
    assert "Litofanía" in nombres, nombres
    g = generadores[nombres.index("Litofanía")]
    assert g is gen and isinstance(g.DESCRIPCION, str) and len(g.DESCRIPCION) > 10 and callable(g.ejecutar)


@contextlib.contextmanager
def _teclas(respuestas):
    cola = iter(respuestas)
    original = builtins.input
    builtins.input = lambda *_a, **_k: next(cola, "")
    try:
        yield
    finally:
        builtins.input = original


def _ejecutar(respuestas, d):
    original = gen.CARPETA_SALIDA
    gen.CARPETA_SALIDA = d
    salida = io.StringIO()
    try:
        with _teclas(respuestas), contextlib.redirect_stdout(salida):
            gen.ejecutar()
    finally:
        gen.CARPETA_SALIDA = original
    return salida.getvalue()


def test_ejecutar_corre_de_punta_a_punta_con_input_simulado():
    with _carpeta() as d:
        ruta = _degrade(d, 400, 300, "foto.png")
        # ruta, ancho, px/mm, grosor claro, grosor oscuro, luz %, invertir, cara, capa
        out = _ejecutar([ruta, "60", "3", "0.8", "2.8", "5", "n", "relieve", "0.12"], d)
        stl = os.path.join(d, "foto_litofania.stl")
        assert os.path.isfile(stl), out
        assert "watertight=True" in out and "STL ->" in out and "ERROR" not in out
        assert lf.verificar_malla(_cargar_stl(stl))["ok"]
        out = _ejecutar([ruta, "", "", "", "", "", "s", "plana", ""], d)           # todo por defecto, invertida y cara plana
        assert "watertight=True" in out and "ERROR" not in out
        # las respuestas llegan al STL: cada variante da un archivo distinto
        def stl(*resp):
            _ejecutar([ruta, "50", "2", *resp], d)
            return open(os.path.join(d, "foto_litofania.stl"), "rb").read()
        base = stl("", "", "", "n", "relieve", "")
        assert stl("", "", "", "s", "relieve", "") != base                          # invertir
        assert stl("", "", "", "n", "plana", "") != base                            # cara visible
        assert stl("", "", "", "n", "relieve", "0.2") != base                       # capa
        assert stl("1.2", "", "", "n", "relieve", "") != base                       # grosor claro
        assert stl("", "3.2", "", "n", "relieve", "") != base                       # grosor oscuro
        assert stl("", "", "20", "n", "relieve", "") != base                        # luz mínima (en %, no en fracción)
        assert stl("", "", "", "n", "relieve", "") == base                          # y es determinista


def test_ejecutar_no_se_cae_con_entradas_malas():
    with _carpeta() as d:
        out = _ejecutar([os.path.join(d, "nada.png")], d)
        assert "ERROR" in out and "no encuentro" in out
        out = _ejecutar([""], d)
        assert "ERROR" in out
        txt = os.path.join(d, "x.txt")
        open(txt, "w").write("hola")
        out = _ejecutar([txt], d)
        assert "ERROR" in out
        ruta = _degrade(d, 100, 80)
        out = _ejecutar([ruta, "-5"], d)                       # ancho negativo: ValueError atrapado
        assert "ERROR" in out and "mayores que 0" in out
        assert not [f for f in os.listdir(d) if f.endswith(".stl")]


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
