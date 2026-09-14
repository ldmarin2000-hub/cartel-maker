#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/deteccion_imagen.py
---------------------------
Clasificación básica de qué hay en una foto (persona / animal /
vehículo / objeto) — pensado para sugerir automáticamente el
tipo_estilo correcto en Esculturas (ver pages/5_🗿_Esculturas.py), no
para forzar ni reemplazar la elección del usuario.

Dos motores combinados, los dos 100% locales y gratis:

- **Persona**: los mismos Haar Cascade de OpenCV que ya usa
  generators/esculturas.py::_detectar_rostro (rostro + silueta de
  cuerpo entero) — ya vienen con la instalación, sin descargar nada.
  Si detecta cara o cuerpo, es "persona" con alta confianza.

- **Animal / vehículo / objeto**: MobileNetV2 (ONNX, ImageNet-1000) —
  se descarga solo la PRIMERA vez que se usa esta función (~13MB los
  pesos + un archivo chico de etiquetas), igual que ya hacen los
  modelos de rembg/TripoSR en este proyecto — desde el ONNX Model Zoo
  oficial (github.com/onnx/models). Clasifica en 1000 categorías; acá
  se agrupan en 3 baldes:
  - "animal": índices 0-397 — en el orden estándar de ImageNet-1000
    ese es exactamente el bloque de fauna (peces/aves/reptiles/
    mamíferos/insectos), verificado contra las 1000 etiquetas reales.
  - "vehiculo": lista curada a mano (ImageNet no agrupa autos/camiones/
    motos/trenes en un bloque contiguo como sí hace con los animales).
  - "objeto": todo el resto (ropa, muebles, comida, herramientas, etc.)

Límite honesto: ImageNet-1000 NO tiene una clase "persona" (por eso la
detección de persona va por Haar Cascade, no por acá) NI una clase
"escudo"/heráldica — no hay forma confiable de detectar escudos con
este modelo, y no se inventa un balde para eso.
"""

import os

import numpy as np

CARPETA_MODELOS = os.path.join(os.path.dirname(__file__), "modelos")
RUTA_MODELO = os.path.join(CARPETA_MODELOS, "mobilenetv2-12.onnx")
RUTA_CLASES = os.path.join(CARPETA_MODELOS, "imagenet_classes.txt")

URL_MODELO = "https://github.com/onnx/models/raw/main/validated/vision/classification/mobilenet/model/mobilenetv2-12.onnx"
URL_CLASES = "https://raw.githubusercontent.com/pytorch/hub/master/imagenet_classes.txt"

# Vehículos — índices verificados a mano contra imagenet_classes.txt
# (autos, camiones, motos, bicis, buses, trenes). ImageNet no los
# agrupa en un rango contiguo como sí hace con los animales (0-397),
# así que van listados uno por uno.
INDICES_VEHICULO = {
    403, 407, 436, 444, 468, 511, 547, 555, 561, 565, 569, 575, 603, 609,
    627, 654, 656, 665, 670, 675, 690, 705, 717, 734, 751, 779, 803, 817,
    820, 829, 864, 866, 867, 870, 874,
}

CATEGORIAS = ["persona", "animal", "vehiculo", "objeto", "incierto"]

_sesion = None
_etiquetas = None
_cascada_rostro = None
_cascada_cuerpo = None


def modelo_descargado():
    """True si ya se bajó el clasificador (no requiere que esté
    cargado en memoria, solo que los archivos existan en disco)."""
    return os.path.exists(RUTA_MODELO) and os.path.exists(RUTA_CLASES)


def descargar_modelo(timeout_seg=120):
    """Baja el clasificador (~13MB) + etiquetas (~10KB) del ONNX Model
    Zoo oficial si todavía no están — se llama sola desde `clasificar()`
    la primera vez, pero también se puede llamar a mano (ej. desde la
    UI, para mostrar un spinner/progreso antes del primer uso)."""
    if modelo_descargado():
        return
    import urllib.request

    os.makedirs(CARPETA_MODELOS, exist_ok=True)
    if not os.path.exists(RUTA_MODELO):
        tmp = RUTA_MODELO + ".tmp"
        urllib.request.urlretrieve(URL_MODELO, tmp)
        os.replace(tmp, RUTA_MODELO)
    if not os.path.exists(RUTA_CLASES):
        tmp = RUTA_CLASES + ".tmp"
        urllib.request.urlretrieve(URL_CLASES, tmp)
        os.replace(tmp, RUTA_CLASES)


def _cargar():
    global _sesion, _etiquetas
    if _sesion is None:
        descargar_modelo()
        import onnxruntime as ort
        _sesion = ort.InferenceSession(RUTA_MODELO, providers=["CPUExecutionProvider"])
        with open(RUTA_CLASES, encoding="utf-8") as f:
            _etiquetas = f.read().splitlines()
    return _sesion, _etiquetas


def _hay_persona(ruta_imagen):
    """Cara o silueta de cuerpo entero (Haar Cascade, local, sin
    descargas) — mismo motor que esculturas._detectar_rostro para la
    cara, más un detector de cuerpo entero como respaldo (fotos de
    perfil, o donde la cara no se ve clara pero sí la silueta)."""
    global _cascada_rostro, _cascada_cuerpo
    import cv2
    from PIL import Image

    with Image.open(ruta_imagen) as img:
        gris = np.array(img.convert("L"))

    if _cascada_rostro is None:
        _cascada_rostro = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        _cascada_cuerpo = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_fullbody.xml")

    if len(_cascada_rostro.detectMultiScale(gris, 1.1, 5, minSize=(50, 50))) > 0:
        return True
    if len(_cascada_cuerpo.detectMultiScale(gris, 1.1, 3, minSize=(60, 120))) > 0:
        return True
    return False


def clasificar(ruta_imagen):
    """Devuelve un dict {"categoria", "detalle", "confianza"} —
    categoria es una de CATEGORIAS. Nunca lanza excepción por falta de
    imagen/modelo/dependencias: ante cualquier problema devuelve
    categoria="incierto" (el llamador decide qué hacer, típicamente no
    sugerir nada en vez de mostrar un error)."""
    if not ruta_imagen or not os.path.exists(ruta_imagen):
        return {"categoria": "incierto", "detalle": "no encuentro la imagen", "confianza": 0.0}

    try:
        if _hay_persona(ruta_imagen):
            return {"categoria": "persona", "detalle": "rostro o silueta de cuerpo detectada", "confianza": 0.9}
    except Exception:
        pass

    try:
        from PIL import Image
        sesion, etiquetas = _cargar()

        img = Image.open(ruta_imagen).convert("RGB").resize((224, 224), Image.BILINEAR)
        arr = np.asarray(img, dtype=np.float32) / 255.0
        media = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        desvio = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        arr = ((arr - media) / desvio).transpose(2, 0, 1)[None, ...]

        salida = sesion.run(None, {"input": arr})[0][0]
        exp = np.exp(salida - salida.max())
        probs = exp / exp.sum()
        idx = int(probs.argmax())
        confianza = float(probs[idx])
        etiqueta = etiquetas[idx]

        if confianza < 0.15:
            return {"categoria": "incierto", "detalle": etiqueta, "confianza": confianza}
        if idx < 398:
            return {"categoria": "animal", "detalle": etiqueta, "confianza": confianza}
        if idx in INDICES_VEHICULO:
            return {"categoria": "vehiculo", "detalle": etiqueta, "confianza": confianza}
        return {"categoria": "objeto", "detalle": etiqueta, "confianza": confianza}
    except Exception:
        return {"categoria": "incierto", "detalle": "no se pudo clasificar", "confianza": 0.0}
