#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_litofania_imagen.py
------------------
Red de regresión para L1 de la litofanía (`core/litofania.py`): imagen -> mapa de
brillo. Lo que se cuida:

  * el mapa es FIEL: sin ajustes, idéntico al gris de PIL (`convert("L")`);
  * escala a píxeles/mm respetando la proporción, recorta sin estirar y NUNCA agranda;
  * los modos de imagen (RGBA, paleta, gris con alfa, 16 bits, CMYK, bilevel...) y la
    rotación EXIF dan lo que tienen que dar -- lo que el cargador viejo de Esculturas hacía mal;
  * el negativo es el complemento exacto, no espeja y se aplica después de los ajustes;
  * `validar_imagen` sigue rechazando por defecto lo que rechazaba (Esculturas no cambia).

Las imágenes se arman en una carpeta temporal: no hay archivos binarios en el repo.
No usa pytest (ver AGENTS.md "Testing") -- funciones `test_*` con `assert` simple,
corribles con `python tests/test_litofania_imagen.py`.
"""
import contextlib
import inspect
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
from PIL import Image

from core import litofania, validation
from core.validation import ValidationError


# --- ayudas ----------------------------------------------------------------------

@contextlib.contextmanager
def _carpeta():
    with tempfile.TemporaryDirectory() as d:
        yield d


def _guardar(carpeta, nombre, imagen, **opciones):
    ruta = os.path.join(carpeta, nombre)
    imagen.save(ruta, **opciones)
    return ruta


def _gris(arr, carpeta, nombre="g.png"):
    """Guarda un array uint8 2D como PNG en grises."""
    return _guardar(carpeta, nombre, Image.fromarray(np.asarray(arr, dtype=np.uint8)))


def _nativo(ruta, **kwargs):
    """Mapa a la resolución de la foto (1 px = 1 mm): el mapa tiene los mismos píxeles que la imagen."""
    ancho_px = Image.open(ruta).size[0]
    return litofania.imagen_a_mapa_brillo(ruta, ancho_mm=ancho_px, px_por_mm=1.0, **kwargs)


def _a_8bit(brillo):
    return np.round(np.asarray(brillo) * 255.0).astype(int)


def _ruido_rgb(ancho=64, alto=48, semilla=3):
    azar = np.random.default_rng(semilla)
    return Image.fromarray(azar.integers(0, 256, size=(alto, ancho, 3), dtype=np.uint8), "RGB")


def _rampa_horizontal(ancho, alto):
    """Gradiente de 0 a 255 de izquierda a derecha."""
    return np.tile(np.linspace(0, 255, ancho), (alto, 1))


# --- brillo fiel: sin realce es exactamente el gris de PIL ---------------------------

def test_sin_ajustes_el_resultado_es_exactamente_el_convert_L_de_pil():
    with _carpeta() as d:
        for nombre, opciones in (("a.png", {}), ("a.jpg", {"quality": 90})):
            ruta = _guardar(d, nombre, _ruido_rgb(), **opciones)
            esperado = np.asarray(Image.open(ruta).convert("L")).astype(int)
            mapa = _nativo(ruta)
            assert np.array_equal(_a_8bit(mapa.brillo), esperado), f"{nombre}: el mapa no es el gris de PIL"
            # y en el valor flotante: la diferencia es solo la precisión de float32 (~1e-8), 100.000 veces
            # menos que un nivel de gris (1/255 = 0,0039)
            assert np.abs(mapa.brillo - esperado / 255.0).max() < 1e-7


def test_el_gris_es_el_rec601_de_pil_no_un_promedio():
    """Rojo, verde, azul y blanco puros dan 76, 150, 29 y 255 (Rec. 601): el "blanco y negro" que ve el ojo."""
    with _carpeta() as d:
        pixeles = np.array([[[255, 0, 0], [0, 255, 0], [0, 0, 255], [255, 255, 255]]] * 2, dtype=np.uint8)
        ruta = _guardar(d, "c.png", Image.fromarray(pixeles, "RGB"))
        assert list(_a_8bit(_nativo(ruta).brillo)[0]) == [76, 150, 29, 255]


def test_degrade_exacto_y_extremos_sin_tocar():
    with _carpeta() as d:
        rampa = np.tile(np.arange(256), (4, 1))
        mapa = _nativo(_gris(rampa, d))
        assert np.array_equal(_a_8bit(mapa.brillo), rampa)
        assert mapa.brillo.min() == 0.0 and mapa.brillo.max() == 1.0


def test_la_fila_0_es_arriba_y_el_tipo_es_float64_en_0_1():
    with _carpeta() as d:
        arr = np.zeros((6, 6), dtype=np.uint8)
        arr[0] = 255   # fila de arriba blanca, el resto negro
        mapa = _nativo(_gris(arr, d))
        assert mapa.brillo.dtype == np.float64 and mapa.brillo.shape == (6, 6)
        assert (mapa.brillo[0] == 1.0).all() and (mapa.brillo[1:] == 0.0).all()
        assert mapa.brillo.min() >= 0.0 and mapa.brillo.max() <= 1.0


def test_poco_contraste_conserva_su_rango_no_se_estira_por_defecto():
    with _carpeta() as d:
        azar = np.random.default_rng(1)
        arr = azar.integers(100, 141, size=(40, 40))
        mapa = _nativo(_gris(arr, d))
        assert np.isclose(mapa.brillo.min(), arr.min() / 255) and np.isclose(mapa.brillo.max(), arr.max() / 255)
        assert mapa.brillo.max() - mapa.brillo.min() < 0.2, "se estiró el contraste sin que se pidiera"


def test_lanczos_no_se_sale_del_rango_con_un_damero_duro():
    with _carpeta() as d:
        damero = (np.indices((200, 200)).sum(axis=0) % 2) * 255
        mapa = litofania.imagen_a_mapa_brillo(_gris(damero, d), ancho_mm=50, px_por_mm=1.0)
        assert mapa.brillo.min() >= 0.0 and mapa.brillo.max() <= 1.0


# --- tamaño, resolución, proporción ---------------------------------------------------

def test_sin_alto_la_proporcion_es_la_de_la_foto_y_la_grilla_es_mm_por_px_por_mm():
    with _carpeta() as d:
        ruta = _gris(_rampa_horizontal(400, 300), d)
        mapa = litofania.imagen_a_mapa_brillo(ruta, ancho_mm=100)      # 400x300 px a 100 mm = justo 4 px/mm
        assert abs(mapa.alto_mm - 75.0) < 1e-9
        assert mapa.brillo.shape == (300, 400) and (mapa.ancho_px, mapa.alto_px) == (400, 300)
        assert mapa.px_por_mm == 4.0 and mapa.avisos == []
        assert mapa.triangulos_estimados == 2 * 399 * 299


def test_reduce_una_foto_grande_al_tamano_pedido_conservando_los_tonos():
    with _carpeta() as d:
        ruta = _gris(_rampa_horizontal(800, 600), d)
        mapa = litofania.imagen_a_mapa_brillo(ruta, ancho_mm=100, px_por_mm=2.0)
        assert mapa.brillo.shape == (150, 200)
        assert abs(mapa.brillo.mean() - 0.5) < 0.01
        assert (np.diff(mapa.brillo, axis=1) >= -1e-9).all(), "el degradé dejó de ser creciente al reducir"


def test_la_grilla_coincide_con_el_tamano_y_los_px_por_mm_pedidos():
    with _carpeta() as d:
        grande = _gris(_rampa_horizontal(800, 600), d, "g1.png")
        cuadrada = _gris(_rampa_horizontal(1200, 1200), d, "g2.png")
        m1 = litofania.imagen_a_mapa_brillo(grande, ancho_mm=100, px_por_mm=3.0)
        assert m1.brillo.shape == (225, 300)
        m2 = litofania.imagen_a_mapa_brillo(cuadrada, ancho_mm=60, alto_mm=80, px_por_mm=5.0)   # recorta a 3:4
        assert m2.brillo.shape == (400, 300)


def test_nunca_agranda_una_foto_chica_y_avisa():
    with _carpeta() as d:
        ruta = _gris(_rampa_horizontal(100, 100), d)
        mapa = litofania.imagen_a_mapa_brillo(ruta, ancho_mm=100)      # pedía 4 px/mm, la foto tiene 1
        assert mapa.brillo.shape == (100, 100) and mapa.px_por_mm == 1.0 and mapa.px_por_mm_pedido == 4.0
        assert any("no se agranda" in a for a in mapa.avisos), mapa.avisos
        assert any("Resolución baja" in a for a in mapa.avisos), mapa.avisos
        assert np.array_equal(_a_8bit(mapa.brillo), _a_8bit(_nativo(ruta).brillo)), "inventó detalle al agrandar"


def test_recorta_centrado_cuando_la_proporcion_no_coincide():
    with _carpeta() as d:
        ruta = _gris(_rampa_horizontal(200, 100), d)                   # 2:1, degradé de 0 a 1
        mapa = litofania.imagen_a_mapa_brillo(ruta, ancho_mm=50, alto_mm=50)   # pide 1:1
        assert mapa.ancho_px == mapa.alto_px
        assert abs(mapa.brillo.min() - 0.25) < 0.02 and abs(mapa.brillo.max() - 0.75) < 0.02   # la mitad del medio
        assert any("recort" in a for a in mapa.avisos), mapa.avisos


def test_el_desplazamiento_mueve_la_ventana_de_recorte():
    with _carpeta() as d:
        ancha = _gris(_rampa_horizontal(200, 100), d, "ancha.png")
        izquierda = litofania.imagen_a_mapa_brillo(ancha, 50, 50, desplazamiento=(-1, 0)).brillo
        derecha = litofania.imagen_a_mapa_brillo(ancha, 50, 50, desplazamiento=(1, 0)).brillo
        assert izquierda.min() < 0.02 and abs(izquierda.max() - 0.5) < 0.02
        assert abs(derecha.min() - 0.5) < 0.02 and derecha.max() > 0.98
        alta = _gris(_rampa_horizontal(200, 100).T, d, "alta.png")     # degradé vertical, 1:2
        arriba = litofania.imagen_a_mapa_brillo(alta, 50, 50, desplazamiento=(0, -1)).brillo
        abajo = litofania.imagen_a_mapa_brillo(alta, 50, 50, desplazamiento=(0, 1)).brillo
        assert arriba.min() < 0.02 and abs(arriba.max() - 0.5) < 0.02
        assert abs(abajo.min() - 0.5) < 0.02 and abajo.max() > 0.98


def test_recortar_no_estira_un_circulo_sigue_siendo_circulo():
    with _carpeta() as d:
        y, x = np.indices((100, 200))
        arr = np.where((x - 100) ** 2 + (y - 50) ** 2 <= 35 ** 2, 0, 255)   # disco negro centrado en una foto 2:1
        mapa = litofania.imagen_a_mapa_brillo(_gris(arr, d), ancho_mm=50, alto_mm=50, px_por_mm=2.0)
        oscuro = mapa.brillo < 0.5
        filas, columnas = np.where(oscuro)
        alto, ancho = filas.max() - filas.min() + 1, columnas.max() - columnas.min() + 1
        assert abs(alto - ancho) <= 2, f"el disco salió {ancho}x{alto}: se estiró"


def test_misma_proporcion_no_recorta_ni_avisa():
    with _carpeta() as d:
        mapa = litofania.imagen_a_mapa_brillo(_gris(_rampa_horizontal(200, 100), d), ancho_mm=100, alto_mm=50)
        assert not any("recort" in a for a in mapa.avisos)


def test_estima_el_peso_de_la_malla_y_avisa_si_es_pesada():
    with _carpeta() as d:
        ruta = _gris(_rampa_horizontal(1200, 1600), d, "t.png")
        normal = litofania.imagen_a_mapa_brillo(ruta, ancho_mm=150, alto_mm=200, px_por_mm=4.0)
        assert normal.brillo.shape == (800, 600)
        assert normal.triangulos_estimados == 2 * 599 * 799 and abs(normal.stl_estimado_mb - 47.9) < 0.1
        assert not any("pesada" in a for a in normal.avisos)
        grande = _gris(_rampa_horizontal(2000, 2000), d, "g.png")
        pesada = litofania.imagen_a_mapa_brillo(grande, ancho_mm=200, px_por_mm=8.0)   # 1600x1600 = 5 M de triángulos
        assert pesada.stl_estimado_mb > litofania.PESO_STL_AVISO_MB
        assert any("pesada" in a for a in pesada.avisos), pesada.avisos


# --- ajustes tonales -----------------------------------------------------------------

def test_ajustes_en_su_valor_neutro_no_tocan_nada():
    with _carpeta() as d:
        ruta = _guardar(d, "r.png", _ruido_rgb())
        base = _nativo(ruta).brillo
        neutro = _nativo(ruta, brillo=0.0, contraste=1.0, gamma=1.0, auto_niveles=False,
                         realce_local=False, suavizado_mm=0.0, invertir=False).brillo
        assert np.array_equal(base, neutro)
        assert np.array_equal(_a_8bit(base), np.asarray(Image.open(ruta).convert("L")).astype(int))


def test_gamma_aclara_o_oscurece_los_medios_segun_su_valor():
    with _carpeta() as d:
        ruta = _gris(np.full((4, 4), 64), d)                           # 64/255 = 0.25098
        base = 64 / 255
        assert abs(_nativo(ruta, gamma=2.0).brillo[0, 0] - base ** 0.5) < 1e-6
        assert abs(_nativo(ruta, gamma=0.5).brillo[0, 0] - base ** 2) < 1e-6


def test_contraste_y_brillo_con_recorte_a_0_1():
    with _carpeta() as d:
        ruta = _gris(np.tile([64, 128, 192, 255], (2, 1)), d)
        valores = np.array([64, 128, 192, 255]) / 255
        con_contraste = _nativo(ruta, contraste=2.0).brillo[0]
        assert np.allclose(con_contraste, np.clip((valores - 0.5) * 2 + 0.5, 0, 1), atol=1e-6, rtol=0)
        con_brillo = _nativo(ruta, brillo=0.2).brillo[0]
        assert np.allclose(con_brillo, np.clip(valores + 0.2, 0, 1), atol=1e-6, rtol=0)
        assert 0.0 <= con_contraste.min() and con_contraste.max() <= 1.0


def test_auto_niveles_estira_entre_percentiles_y_no_rompe_una_imagen_plana():
    with _carpeta() as d:
        poco = _gris(np.tile(np.linspace(100, 140, 100), (20, 1)), d, "poco.png")
        estirado = _nativo(poco, auto_niveles=True).brillo
        assert estirado.min() < 0.02 and estirado.max() > 0.98
        plana = _gris(np.full((10, 10), 90), d, "plana.png")
        resultado = _nativo(plana, auto_niveles=True).brillo
        assert np.isfinite(resultado).all() and np.allclose(resultado, 90 / 255)


def test_realce_local_solo_actua_si_se_pide_y_altera_los_grises():
    with _carpeta() as d:
        poco = _gris(np.tile(np.linspace(100, 140, 120), (60, 1)), d)
        sin = _nativo(poco).brillo
        con = _nativo(poco, realce_local=True).brillo
        assert sin.max() - sin.min() < 0.2, "por defecto no debe estirar"
        assert con.max() - con.min() > 0.3, "el realce local no hizo nada"
        assert not np.allclose(sin, con)
        assert con.min() >= 0.0 and con.max() <= 1.0


def test_suavizado_en_mm_desenfoca_y_apagado_no_toca():
    with _carpeta() as d:
        damero = (np.indices((40, 40)).sum(axis=0) % 2) * 255
        ruta = _gris(damero, d)
        nitido, suave = _nativo(ruta).brillo, _nativo(ruta, suavizado_mm=1.0).brillo
        assert suave.std() < nitido.std() * 0.5
        assert suave.min() >= 0.0 and suave.max() <= 1.0
        assert np.array_equal(_nativo(ruta, suavizado_mm=0.0).brillo, nitido)


# --- invertir: las 5 comprobaciones -----------------------------------------------------

def test_invertir_1_es_exactamente_el_complemento():
    with _carpeta() as d:
        ruta = _guardar(d, "r.png", _ruido_rgb())
        ajustes = dict(gamma=1.5, contraste=1.2, brillo=0.05)
        normal = _nativo(ruta, **ajustes).brillo
        invertido = _nativo(ruta, invertir=True, **ajustes).brillo
        assert np.allclose(invertido, 1.0 - normal, atol=1e-12, rtol=0)


def test_invertir_2_dos_veces_devuelve_el_original():
    with _carpeta() as d:
        ruta = _guardar(d, "r.png", _ruido_rgb())
        normal = _nativo(ruta).brillo
        assert np.allclose(litofania.invertir_brillo(litofania.invertir_brillo(normal)), normal, atol=1e-15, rtol=0)
        assert np.array_equal(_nativo(ruta, invertir=True).brillo, litofania.invertir_brillo(normal))


def test_invertir_3_los_extremos_se_intercambian():
    with _carpeta() as d:
        damero = (np.indices((8, 8)).sum(axis=0) % 2) * 255
        ruta = _gris(damero, d, "d.png")
        normal, invertido = _nativo(ruta).brillo, _nativo(ruta, invertir=True).brillo
        assert set(np.unique(normal)) == {0.0, 1.0} and set(np.unique(invertido)) == {0.0, 1.0}
        assert np.array_equal(invertido, 1.0 - normal), "el negro no pasó a 1.0 y el blanco a 0.0"
        rampa = _gris(np.tile(np.arange(256), (2, 1)), d, "r.png")
        inv = _nativo(rampa, invertir=True).brillo
        assert inv[0, 0] == 1.0 and inv[0, -1] == 0.0


def test_invertir_4_no_espeja_el_marcador_sigue_en_su_esquina():
    with _carpeta() as d:
        arr = np.zeros((8, 8), dtype=np.uint8)
        arr[0, 0] = 255                                                # un píxel blanco arriba a la izquierda
        ruta = _gris(arr, d)
        normal, invertido = _nativo(ruta).brillo, _nativo(ruta, invertir=True).brillo
        assert np.argwhere(normal == 1.0).tolist() == [[0, 0]]
        assert np.argwhere(invertido == 0.0).tolist() == [[0, 0]], "el negativo movió la imagen"


def test_invertir_5_se_aplica_al_final_despues_del_gamma():
    """`1 - gamma(b)`, no `gamma(1 - b)`: el orden está fijo."""
    with _carpeta() as d:
        ruta = _gris(np.full((4, 4), 64), d)
        b = 64 / 255
        resultado = _nativo(ruta, gamma=2.0, invertir=True).brillo[0, 0]
        assert abs(resultado - (1.0 - b ** 0.5)) < 1e-6
        assert abs(resultado - (1.0 - b) ** 0.5) > 0.3


# --- modos de imagen: lo que el cargador viejo hacía mal --------------------------------

def test_png_transparente_se_aplana_sobre_blanco_no_negro():
    with _carpeta() as d:
        rgba = np.zeros((20, 20, 4), dtype=np.uint8)                   # todo transparente, RGB = 0 (negro)
        rgba[:10, 10:] = (200, 200, 200, 255)                          # un cuadrado opaco gris claro
        rgba[10:, 10:] = (0, 0, 0, 128)                                # negro a media transparencia
        mapa = _nativo(_guardar(d, "logo.png", Image.fromarray(rgba, "RGBA")))
        assert (mapa.brillo[:, :10] == 1.0).all(), "lo transparente tiene que ser blanco (pasa la luz)"
        assert np.allclose(mapa.brillo[:10, 10:], 200 / 255)
        assert np.allclose(mapa.brillo[10:, 10:], 127 / 255, atol=1.5 / 255)   # negro al 50% sobre blanco
        assert any("transparencia" in a for a in mapa.avisos)


def test_paleta_con_y_sin_transparencia():
    with _carpeta() as d:
        paleta = [0, 0, 0, 255, 0, 0, 0, 0, 255, 255, 255, 255]       # negro, rojo, azul, blanco
        indices = np.array([[0, 1, 2, 3]] * 2, dtype=np.uint8)
        img = Image.fromarray(indices, "P")
        img.putpalette(paleta + [0] * (768 - len(paleta)))
        sin = _guardar(d, "p.png", img)
        esperado = np.asarray(Image.open(sin).convert("RGB").convert("L")) / 255
        assert np.allclose(_nativo(sin).brillo, esperado)
        con = _guardar(d, "pt.png", img, transparency=0)               # el índice 0 (negro) es transparente
        resultado = _nativo(con)
        assert (resultado.brillo[:, 0] == 1.0).all(), "el índice transparente tiene que salir blanco"
        assert np.allclose(resultado.brillo[:, 1:], esperado[:, 1:])
        assert any("transparencia" in a for a in resultado.avisos)


def test_gris_con_alfa():
    with _carpeta() as d:
        la = np.zeros((4, 4, 2), dtype=np.uint8)
        la[..., 0] = 100
        la[:, :2, 1] = 0                                               # mitad transparente
        la[:, 2:, 1] = 255
        mapa = _nativo(_guardar(d, "la.png", Image.fromarray(la, "LA")))
        assert (mapa.brillo[:, :2] == 1.0).all() and np.allclose(mapa.brillo[:, 2:], 100 / 255)


def test_color_clave_transparente_en_rgb():
    with _carpeta() as d:
        rgb = np.full((6, 6, 3), 90, dtype=np.uint8)
        rgb[:, :3] = (0, 0, 0)                                         # el negro es el color transparente
        ruta = _guardar(d, "ck.png", Image.fromarray(rgb, "RGB"), transparency=(0, 0, 0))
        mapa = _nativo(ruta)
        assert (mapa.brillo[:, :3] == 1.0).all() and np.allclose(mapa.brillo[:, 3:], 90 / 255)


def test_16_bits_conservan_su_precision():
    with _carpeta() as d:
        arr = np.array([[0, 1000, 33000, 65535]] * 2, dtype=np.uint16)
        ruta = _guardar(d, "g16.png", Image.fromarray(arr))
        assert Image.open(ruta).mode.startswith("I;16")
        mapa = _nativo(ruta)
        assert np.allclose(mapa.brillo, arr / 65535.0, atol=1e-6)
        fuera_de_la_grilla_de_8_bits = np.abs(mapa.brillo - np.round(mapa.brillo * 255) / 255).max()
        assert fuera_de_la_grilla_de_8_bits > 1e-4, "se cuantizó a 8 bits"   # 1000/65535 está a 4,3e-4 del nivel 4/255


def test_cmyk_pasa_por_rgb():
    with _carpeta() as d:
        cmyk = np.zeros((16, 16, 4), dtype=np.uint8)
        cmyk[8:, :, 3] = 255                                           # arriba sin tinta (blanco), abajo negro
        ruta = _guardar(d, "c.jpg", Image.fromarray(cmyk, "CMYK"), quality=100)
        assert Image.open(ruta).mode == "CMYK"
        mapa = _nativo(ruta)
        assert mapa.brillo[:6].min() > 0.94 and mapa.brillo[10:].max() < 0.06


def test_bilevel_y_gris_plano():
    with _carpeta() as d:
        bits = (np.indices((6, 6)).sum(axis=0) % 2).astype(bool)
        mapa = _nativo(_guardar(d, "b.png", Image.fromarray(bits)))
        assert set(np.unique(mapa.brillo)) == {0.0, 1.0}
        assert np.array_equal(mapa.brillo, bits.astype(float))


# --- EXIF: la foto de celular queda derecha ------------------------------------------------

def test_exif_endereza_la_foto_en_las_8_orientaciones():
    esperados = {
        1: lambda a: a, 2: np.fliplr, 3: lambda a: np.rot90(a, 2), 4: np.flipud, 5: lambda a: a.T,
        6: lambda a: np.rot90(a, -1), 7: lambda a: np.rot90(a.T, 2), 8: lambda a: np.rot90(a, 1),
    }
    arr = (np.arange(24).reshape(4, 6) * 10).astype(np.uint8)           # 4 filas x 6 columnas, todos distintos
    with _carpeta() as d:
        for orientacion, transformar in esperados.items():
            exif = Image.Exif()
            exif[0x0112] = orientacion
            ruta = _guardar(d, f"o{orientacion}.png", Image.fromarray(arr), exif=exif)
            esperado = transformar(arr)
            mapa = litofania.imagen_a_mapa_brillo(ruta, ancho_mm=esperado.shape[1], px_por_mm=1.0)
            assert mapa.brillo.shape == esperado.shape, (orientacion, mapa.brillo.shape, esperado.shape)
            assert np.array_equal(_a_8bit(mapa.brillo), esperado.astype(int)), f"orientación EXIF {orientacion} mal enderezada"


def test_exif_en_un_jpeg_de_celular_intercambia_ancho_y_alto():
    with _carpeta() as d:
        exif = Image.Exif()
        exif[0x0112] = 6
        ruta = _guardar(d, "foto.jpg", Image.fromarray(_rampa_horizontal(120, 80).astype(np.uint8)), exif=exif, quality=95)
        assert Image.open(ruta).size == (120, 80)                      # así queda guardada: acostada
        mapa = litofania.imagen_a_mapa_brillo(ruta, ancho_mm=80, px_por_mm=1.0)
        assert mapa.brillo.shape == (120, 80), "la foto quedó acostada"


# --- errores -------------------------------------------------------------------------------

def test_archivos_invalidos_dan_validation_error():
    with _carpeta() as d:
        casos = [
            "no_existe.png",
            _guardar(d, "a.bmp", Image.fromarray(np.zeros((4, 4), dtype=np.uint8))),
        ]
        malo = os.path.join(d, "roto.png")
        with open(malo, "wb") as f:
            f.write(b"esto no es una imagen")
        casos.append(malo)
        casos.append(_gris(np.zeros((1, 1)), d, "uno.png"))            # 1x1: no hay con qué armar un mapa
        for ruta in casos:
            try:
                litofania.imagen_a_mapa_brillo(ruta, ancho_mm=50)
            except ValidationError:
                continue
            raise AssertionError(f"{ruta!r} tenía que fallar con ValidationError")
        ruta = _gris(np.zeros((10, 10)), d, "ok.png")
        try:
            litofania.imagen_a_mapa_brillo(ruta, ancho_mm=50, max_mb=1e-6)
        except ValidationError as e:
            assert "muy grande" in str(e)
        else:
            raise AssertionError("una imagen más pesada que max_mb tenía que fallar")


def test_parametros_sin_sentido_dan_value_error():
    with _carpeta() as d:
        ruta = _gris(_rampa_horizontal(40, 40), d)
        malos = [dict(ancho_mm=0), dict(ancho_mm=-5), dict(ancho_mm=50, alto_mm=0), dict(ancho_mm=50, px_por_mm=0.5),
                 dict(ancho_mm=50, px_por_mm=9), dict(ancho_mm=50, gamma=0), dict(ancho_mm=50, contraste=-1),
                 dict(ancho_mm=50, suavizado_mm=-1), dict(ancho_mm=50, desplazamiento=(1.5, 0))]
        for kwargs in malos:
            try:
                litofania.imagen_a_mapa_brillo(ruta, **kwargs)
            except ValueError:
                continue
            raise AssertionError(f"{kwargs} tenía que fallar con ValueError")
        for px in (litofania.PX_POR_MM_MIN, litofania.PX_POR_MM_MAX):    # los bordes del rango sí valen
            litofania.imagen_a_mapa_brillo(ruta, ancho_mm=5, px_por_mm=px)


def test_mapa_a_imagen_ida_y_vuelta():
    with _carpeta() as d:
        arr = np.random.default_rng(5).integers(0, 256, size=(30, 40), dtype=np.uint8)
        mapa = _nativo(_gris(arr, d))
        imagen = litofania.mapa_a_imagen(mapa)
        assert imagen.mode == "L" and np.array_equal(np.asarray(imagen), arr)


# --- Esculturas sigue igual: validar_imagen no cambió su comportamiento por defecto ---------------

def test_validar_imagen_por_defecto_sigue_rechazando_lo_chico_con_el_mismo_mensaje():
    assert inspect.signature(validation.validar_imagen).parameters["min_mb"].default == 0.05
    assert inspect.signature(validation.validar_imagen).parameters["max_mb"].default == 50.0
    with _carpeta() as d:
        chica = _gris(np.zeros((10, 10)), d, "chica.png")               # unos pocos bytes
        try:
            validation.validar_imagen(chica)
        except ValidationError as e:
            assert str(e) == "Imagen demasiado chica (<50KB). Usá algo más detallado."
        else:
            raise AssertionError("por defecto tiene que seguir rechazando imágenes de menos de 50 KB")
        assert validation.validar_imagen(chica, min_mb=0) is None       # con min_mb=0 pasa
        pesada = _guardar(d, "ruido.png", _ruido_rgb(300, 300, semilla=9))   # ruido: no comprime, pesa > 50 KB
        assert os.path.getsize(pesada) > 51200
        assert validation.validar_imagen(pesada) is None
        for ruta, texto in (("no_existe.png", "no encontrada"), (os.path.join(d, "x.bmp"), "no encontrada")):
            try:
                validation.validar_imagen(ruta)
            except ValidationError as e:
                assert texto in str(e)
            else:
                raise AssertionError("tenía que fallar")


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
