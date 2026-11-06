#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_pagina_litofania.py
------------------
Prueba en pantalla SIN pantalla de la página de la litofanía (`pages/13_🖼️_Litofania.py`), con
`streamlit.testing.AppTest` (el mismo mecanismo de tests/test_paginas_cargan.py): se le inyecta la foto por la
key "sombra" del uploader (`lf_foto__ruta`), así que no hace falta subir nada. Complementa la prueba manual:

  * sin foto muestra el aviso y nada más; con foto dibuja la simulación a contraluz y la foto en grises;
  * la simulación CAMBIA al mover la luz mínima, el grosor y la capa (la imagen que se muestra es otra);
  * los avisos de L4 aparecen MIENTRAS se mueven los controles, sin generar: no entra en la A1, grosor frágil,
    bandas por capa gruesa, resolución de más; y una litofanía sana no avisa nada;
  * "Generar STL" crea el archivo, muestra el botón de descarga, y al mover un parámetro marca "versión anterior";
  * un archivo inválido o parámetros imposibles muestran el error en pantalla, sin excepción;
  * los presets guardan y cargan (también uno viejo con enteros) y cubren todos los controles.

Todo corre en una carpeta temporal (la página escribe en `output/` y `presets/` relativos al directorio actual).
No usa pytest -- funciones `test_*` con `assert` simple, corribles con `python tests/test_pagina_litofania.py`.
"""
import contextlib
import glob
import os
import re
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
os.chdir(RAIZ)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
from PIL import Image
from streamlit.testing.v1 import AppTest

PAGINA = os.path.join(RAIZ, "pages", "13_🖼️_Litofania.py")


@contextlib.contextmanager
def _entorno():
    """Carpeta temporal como directorio actual (output/ y presets/ de la página caen ahí) + la foto de prueba."""
    anterior = os.getcwd()
    with tempfile.TemporaryDirectory() as d:
        os.chdir(d)
        try:
            yield d
        finally:
            os.chdir(anterior)


def _foto(d, nombre="astro.png"):
    from skimage import data
    ruta = os.path.join(d, nombre)
    Image.fromarray(data.astronaut()).save(ruta)
    return ruta


def _pagina(ruta_foto=None):
    at = AppTest.from_file(PAGINA, default_timeout=120)
    if ruta_foto:
        at.session_state["lf_foto__ruta"] = ruta_foto
    return at.run()


def _sin_excepciones(at):
    assert not at.exception, [e.value for e in at.exception]


def _imagenes(at):
    return [e.proto.imgs[0].url for e in at.get("image")]


def _textos(elementos):
    return [e.value for e in elementos]


def _con(texto, elementos):
    return [t for t in _textos(elementos) if texto in t]


# ---------------------------------------------------------------------------

def test_sin_foto_pide_la_foto_y_no_dibuja_nada():
    with _entorno():
        at = _pagina()
        _sin_excepciones(at)
        assert _con("Subí una foto", at.info) and not _imagenes(at)
        assert not [b for b in at.button if b.label == "Generar STL"]
        assert not at.warning and not at.error


def test_con_foto_dibuja_la_simulacion_y_la_foto_en_grises_sin_avisos():
    with _entorno() as d:
        at = _pagina(_foto(d))
        _sin_excepciones(at)
        assert len(_imagenes(at)) == 2 and len(set(_imagenes(at))) == 2          # a contraluz y en grises: distintas
        assert [t.label for t in at.tabs] == ["💡 A contraluz", "🖼️ Foto en grises"]
        assert not at.warning and not at.error, _textos(at.warning)               # una litofanía sana no avisa nada
        assert _con("entra en la Bambu A1", at.success)
        metricas = {m.label: m.value for m in at.metric}
        assert metricas["Placa"] == "100 x 100 mm" and metricas["Mapa"] == "400 x 400 px"
        assert [b.label for b in at.button if b.label == "Generar STL"]


def test_la_simulacion_cambia_al_mover_luz_minima_grosores_y_capa():
    with _entorno() as d:
        at = _pagina(_foto(d))
        base = _imagenes(at)[0]
        at.slider(key="lf_luz_pct").set_value(20.0).run()
        _sin_excepciones(at)
        assert _imagenes(at)[0] != base                                          # más luz filtrada: sombras más claras
        at.slider(key="lf_luz_pct").set_value(5.0).run()
        assert _imagenes(at)[0] == base                                          # y vuelve a lo mismo (determinista)
        at.selectbox(key="lf_capa").select("0,20 mm").run()
        assert _imagenes(at)[0] != base                                          # las bandas de la capa gruesa se ven
        at.selectbox(key="lf_capa").select("Sin ajustar a capas").run()
        at.checkbox(key="lf_invertir").check().run()
        assert _imagenes(at)[0] != base and _imagenes(at)[1] != _imagenes(at)[0]
        at.checkbox(key="lf_invertir").uncheck().run()
        at.checkbox(key="lf_compensar").uncheck().run()
        assert _imagenes(at)[0] != base                                          # sin compensar los medios salen más oscuros


def test_los_avisos_de_L4_aparecen_en_vivo_y_solo_cuando_corresponde():
    with _entorno() as d:
        at = _pagina(_foto(d))
        assert not at.warning
        at.number_input(key="lf_ancho").set_value(300.0).run()                   # no entra en la A1
        _sin_excepciones(at)
        assert len(_con("NO entra", at.warning)) == 1 and not at.success
        at.number_input(key="lf_ancho").set_value(250.0).run()                   # entra justo
        assert len(_con("entra justo", at.warning)) == 1 and not _con("NO entra", at.warning)
        at.number_input(key="lf_ancho").set_value(100.0).run()
        assert not at.warning
        at.slider(key="lf_grosor_min").set_value(0.4).run()                      # frágil
        assert len(_con("frágil", at.warning)) == 1 and len(at.warning) == 1
        at.slider(key="lf_grosor_min").set_value(0.8).run()
        at.selectbox(key="lf_capa").select("0,20 mm").run()                      # pocos niveles
        assert len(_con("bandas", at.warning)) == 1
        at.selectbox(key="lf_capa").select("0,08 mm").run()
        assert not _con("bandas", at.warning)
        at.selectbox(key="lf_capa").select("Sin ajustar a capas").run()
        at.slider(key="lf_px").set_value(5.0).run()                              # 5 px/mm todavía se aprovecha...
        assert not at.warning
        at.slider(key="lf_px").set_value(8.0).run()                              # ...8 no: la foto tiene 5,1 y no se agranda
        assert len(_con("no se agranda", at.warning)) == 1 and len(_con("boquilla", at.warning)) == 1   # (5,1 > 5)


def test_resolucion_de_mas_avisa_con_una_foto_que_la_tiene():
    with _entorno() as d:
        grande = os.path.join(d, "grande.png")
        Image.fromarray(np.tile(np.linspace(0, 255, 1600).astype(np.uint8), (1200, 1))).save(grande)
        at = _pagina(grande)
        at.number_input(key="lf_ancho").set_value(100.0).run()
        at.slider(key="lf_px").set_value(7.0).run()
        _sin_excepciones(at)
        assert len(_con("boquilla", at.warning)) == 1
        at.number_input(key="lf_boquilla").set_value(0.2).run()                  # una boquilla de 0,2 sí aprovecha 7 px/mm
        assert not _con("boquilla", at.warning)


def test_alto_fijo_con_otra_proporcion_recorta_y_avisa():
    with _entorno() as d:
        at = _pagina(_foto(d))
        at.radio(key="lf_alto_modo").set_value("Fijarlo").run()
        at.number_input(key="lf_alto").set_value(60.0).run()
        _sin_excepciones(at)
        assert _con("recort", at.warning) and {m.label: m.value for m in at.metric}["Placa"] == "100 x 60 mm"
        antes = _imagenes(at)[0]
        at.slider(key="lf_dy").set_value(1.0).run()                              # correr el recorte cambia lo que se ve
        assert _imagenes(at)[0] != antes


def test_generar_crea_el_stl_muestra_la_descarga_y_marca_la_version_anterior():
    with _entorno() as d:
        at = _pagina(_foto(d))
        at.button[[b.label for b in at.button].index("Generar STL")].click().run()
        _sin_excepciones(at)
        assert not at.error, _textos(at.error)
        res = at.session_state["lf_resultado"]
        assert os.path.isfile(res["ruta_stl"]) and res["ruta_stl"].endswith("astro_litofania.stl")
        assert os.path.dirname(os.path.abspath(res["ruta_stl"])) == os.path.join(os.path.realpath(d), "output", "litofania") \
            or os.path.dirname(os.path.abspath(res["ruta_stl"])) == os.path.join(d, "output", "litofania")
        assert os.path.getsize(res["ruta_stl"]) == 84 + 50 * res["caras"]
        # el visor usa la malla simplificada y el archivo para descargar es el completo
        assert res["px_vista"] == 1.5 and res["px_por_mm"] == 4.0 and os.path.getsize(res["ruta_vista"]) < os.path.getsize(res["ruta_stl"]) / 4
        assert len(at.get("download_button")) == 1
        assert _con("Vista 3D simplificada", at.caption) and _con("Malla verificada", at.caption)
        assert not _con("versión anterior", at.warning)
        # el resultado sobrevive a mover un control, marcado como versión anterior; al regenerar, se actualiza
        at.slider(key="lf_luz_pct").set_value(10.0).run()
        assert len(_con("versión anterior", at.warning)) == 1 and len(at.get("download_button")) == 1
        at.button[[b.label for b in at.button].index("Generar STL")].click().run()
        assert not _con("versión anterior", at.warning)
        # cambiar solo el color del visor no invalida el STL
        at.selectbox(key="lf_color_visor").select("Gris Frío").run()
        assert not _con("versión anterior", at.warning)


def test_generar_con_foto_chica_no_hace_una_segunda_malla_para_el_visor():
    with _entorno() as d:
        chica = os.path.join(d, "chica.png")
        Image.fromarray(np.tile(np.linspace(0, 255, 100).astype(np.uint8), (80, 1))).save(chica)
        at = _pagina(chica)
        at.slider(key="lf_px").set_value(1.0).run()
        at.button[[b.label for b in at.button].index("Generar STL")].click().run()
        _sin_excepciones(at)
        res = at.session_state["lf_resultado"]
        assert res["ruta_vista"] == res["ruta_stl"]                              # ya es liviana: se muestra la misma


def test_archivo_invalido_y_parametros_imposibles_se_ven_como_error_sin_excepcion():
    with _entorno() as d:
        txt = os.path.join(d, "notas.txt")
        open(txt, "w").write("no soy una imagen")
        at = _pagina(txt)
        _sin_excepciones(at)
        assert len(at.error) == 1 and "no soportado" in at.error[0].value and not _imagenes(at)
        assert not [b for b in at.button if b.label == "Generar STL"]
        roto = os.path.join(d, "roto.png")
        open(roto, "wb").write(b"\x89PNG\r\n\x1a\n" + os.urandom(200))
        at = _pagina(roto)
        _sin_excepciones(at)
        assert len(at.error) == 1
        # la foto se borró del disco después de subirla: no tira la página
        at = _pagina(os.path.join(d, "ya_no_existe.png"))
        _sin_excepciones(at)
        assert _con("Subí una foto", at.info)
        # parámetros que L2 rechaza: mensaje en pantalla, no un traceback
        at = _pagina(_foto(d))
        at.slider(key="lf_grosor_min").set_value(2.0).run()
        at.slider(key="lf_grosor_max").set_value(1.5).run()
        _sin_excepciones(at)
        assert len(_con("grosor_max tiene que ser mayor", at.error)) == 1 and not _imagenes(at)
        at.slider(key="lf_grosor_max").set_value(4.0).run()
        assert not at.error and len(_imagenes(at)) == 2
        at.selectbox(key="lf_capa").select("0,20 mm").run()
        at.slider(key="lf_grosor_min").set_value(2.0).run()
        at.slider(key="lf_grosor_max").set_value(2.1).run()                      # capa mayor que el rango
        _sin_excepciones(at)
        assert len(at.error) == 1 and "capa" in at.error[0].value


def test_la_foto_se_reemplaza_sin_quedarse_con_el_preview_anterior():
    with _entorno() as d:
        a = _foto(d, "a.png")
        at = _pagina(a)
        antes = _imagenes(at)[0]
        Image.fromarray(255 - np.asarray(Image.open(a))).save(a)                  # otro contenido en la MISMA ruta
        at.run()
        assert _imagenes(at)[0] != antes


def test_presets_guardan_cargan_y_aceptan_uno_viejo_con_enteros():
    from core import presets
    with _entorno() as d:
        at = _pagina(_foto(d))
        at.number_input(key="lf_ancho").set_value(150.0)
        at.slider(key="lf_luz_pct").set_value(12.0)
        at.selectbox(key="lf_capa").select("0,12 mm")
        at.checkbox(key="lf_invertir").check()
        at.run()
        at.text_input(key="litofania_preset_nombre").input("mi lito").run()
        at.button(key="litofania_preset_guardar").click().run()
        _sin_excepciones(at)
        guardado = presets.cargar("litofania", "mi lito")
        assert guardado["lf_ancho"] == 150.0 and guardado["lf_luz_pct"] == 12.0 and guardado["lf_invertir"] is True
        assert guardado["lf_capa"] == "0,12 mm" and "lf_foto" not in guardado and "lf_foto__ruta" not in guardado

        at.number_input(key="lf_ancho").set_value(80.0)
        at.checkbox(key="lf_invertir").uncheck()
        at.run()
        assert presets.listar("litofania") == ["mi_lito"]                       # el nombre se limpia al guardar
        at.selectbox(key="litofania_preset_elegido").select("mi_lito").run()
        at.button(key="litofania_preset_cargar").click().run()
        _sin_excepciones(at)
        assert at.session_state["lf_ancho"] == 150.0 and at.session_state["lf_invertir"] is True
        assert at.session_state["lf_capa"] == "0,12 mm" and at.session_state["lf_luz_pct"] == 12.0

        presets.guardar("litofania", "viejo", {"lf_ancho": 120, "lf_px": 3, "lf_grosor_min": 1, "lf_luz_pct": 8,
                                               "lf_color_visor": "Un color que ya no existe", "lf_clave_ajena": 1})
        at = _pagina(_foto(d))
        at.selectbox(key="litofania_preset_elegido").select("viejo").run()
        at.button(key="litofania_preset_cargar").click().run()
        _sin_excepciones(at)
        assert at.session_state["lf_ancho"] == 120.0 and isinstance(at.session_state["lf_ancho"], float)
        assert isinstance(at.session_state["lf_px"], float) and at.session_state["lf_grosor_min"] == 1.0
        assert "lf_clave_ajena" not in at.session_state and not at.error
        assert {m.label: m.value for m in at.metric}["Placa"] == "120 x 120 mm"


def test_los_presets_cubren_todos_los_controles_y_no_la_foto():
    fuente = open(PAGINA, encoding="utf-8").read()
    keys_widgets = set(re.findall(r'key="(lf_[a-z_]+)"', fuente))
    # el contenido de DEFAULTS es el de PRESET_KEYS (PRESET_KEYS = list(DEFAULTS))
    assert "PRESET_KEYS = list(DEFAULTS)" in fuente
    declaradas = set(re.findall(r'^    "(lf_[a-z_]+)":', fuente.split("DEFAULTS = {")[1].split("\n}\n")[0], flags=re.M)
                     + re.findall(r'"(lf_[a-z_]+)":', fuente.split("DEFAULTS = {")[1].split("\n}\n")[0]))
    assert keys_widgets - {"lf_foto"} == declaradas, (keys_widgets - {"lf_foto"} ^ declaradas)
    assert "lf_foto" not in declaradas                                            # el uploader no se guarda


def test_la_pagina_esta_numerada_y_no_pisa_a_otra():
    numeros = [int(os.path.basename(p).split("_")[0]) for p in glob.glob(os.path.join(RAIZ, "pages", "*.py"))]
    assert len(numeros) == len(set(numeros)) and 13 in numeros


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
