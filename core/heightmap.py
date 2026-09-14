#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/heightmap.py
--------------------
Imagen rasterizada -> relieve 3D (escultura/litofanía): a diferencia de
core/imagen_import.py (que saca el CONTORNO de la imagen, una silueta
plana), esto usa el BRILLO de cada píxel para modular la ALTURA de una
grilla — cada zona clara/oscura de la foto queda más alta o más baja,
como un relieve tallado. Watertight de verdad (superficie de arriba +
piso plano + 4 paredes laterales cerrando el volumen), no una nube de
puntos ni una superficie abierta.

No hace falta ninguna librería nueva: PIL para leer/re-muestrear la
imagen, numpy para la grilla, trimesh para armar la malla — todo ya es
dependencia del proyecto.
"""

import numpy as np
import trimesh
from PIL import Image, ImageFilter
from skimage import exposure, filters

RESOLUCION_MAX_PX = 180  # lado más largo de la grilla de trabajo — más = más detalle, más lento y más pesado


def _mascara_sujeto(ruta_imagen, resolucion_px, suavizado_borde_px=2.0):
    """Segmenta sujeto/fondo con rembg (modelo liviano U2Net, corre rápido
    en CPU) y devuelve una máscara 2D en [0,1] del mismo tamaño que la
    grilla de trabajo — 1.0 = sujeto, 0.0 = fondo, con un degradé suave en
    el borde (para que el relieve no tenga un escalón brusco entre sujeto
    y fondo). Devuelve None si rembg no está instalado o falla (el llamador
    debe tratar eso como "sin segmentación disponible", no como error)."""
    try:
        import rembg
    except ImportError:
        return None

    try:
        img = Image.open(ruta_imagen).convert("RGBA")
        recortada = rembg.remove(img)
        alpha = np.asarray(recortada.split()[-1], dtype=np.float64) / 255.0
    except Exception:
        return None

    alpha_img = Image.fromarray((alpha * 255).astype(np.uint8))
    ancho_px, alto_px = alpha_img.size
    lado_mayor = max(ancho_px, alto_px)
    escala = resolucion_px / lado_mayor
    nw, nh = max(2, round(ancho_px * escala)), max(2, round(alto_px * escala))
    alpha_img = alpha_img.resize((nw, nh), Image.LANCZOS)

    if suavizado_borde_px > 0:
        alpha_img = alpha_img.filter(ImageFilter.GaussianBlur(suavizado_borde_px))

    return np.asarray(alpha_img, dtype=np.float64) / 255.0


def _grilla_de_alturas(ruta_imagen, resolucion_px=RESOLUCION_MAX_PX, suavizado_px=1.0, usar_clahe=True, usar_bilateral=False):
    """Lee `ruta_imagen`, la pasa a escala de grises y la re-muestrea a una
    grilla de como mucho `resolucion_px` de lado (mantiene la proporción
    real de la imagen). Optimizaciones:
    - CLAHE (contrast-limited adaptive histogram equalization) si usar_clahe=True
    - Bilateral filtering DESHABILITADO por default (muy lento); reemplazado por median filter más rápido
    Devuelve un array 2D de floats en [0, 1] — 0 = negro, 1 = blanco."""
    img = Image.open(ruta_imagen).convert("L")

    # Re-muestrear PRIMERO (imagen más chica = procesos posteriores más rápidos)
    ancho_px, alto_px = img.size
    lado_mayor = max(ancho_px, alto_px)
    escala = resolucion_px / lado_mayor
    nw, nh = max(2, round(ancho_px * escala)), max(2, round(alto_px * escala))
    img = img.resize((nw, nh), Image.LANCZOS)

    img_arr = np.asarray(img, dtype=np.float64) / 255.0

    # CLAHE: mejora contraste adaptativo sin perder detalles (rápido)
    if usar_clahe:
        img_arr = exposure.equalize_adapthist(img_arr, clip_limit=0.03, nbins=128)

    # Bilateral filter: muy lento, reemplazado por median filter (alternativa rápida, preserva edges)
    if usar_bilateral:
        img_arr = filters.median(img_arr)

    # Gaussian blur para artefactos JPG
    if suavizado_px > 0:
        img_pil = Image.fromarray((np.clip(img_arr * 255, 0, 255)).astype(np.uint8))
        img_pil = img_pil.filter(ImageFilter.GaussianBlur(suavizado_px))
        img_arr = np.asarray(img_pil, dtype=np.float64) / 255.0

    return img_arr


FORMAS_MEDALLON_CON_MARCO = ("Circular", "Ovalada", "Hexagonal")


def _distancia_forma(nh, nw, forma):
    """Campo [nh,nw] de "distancia" normalizada al centro de la silueta
    (0=centro, 1.0=borde exacto, >1=fuera) — mismo campo usado tanto
    para recortar el medallón (`_mascara_medallon`) como para ubicar el
    reborde decorativo (`_mapa_marco_mm`), así ambos quedan perfectamente
    alineados con el mismo borde."""
    ys, xs = np.mgrid[0:nh, 0:nw].astype(np.float64)
    cy, cx = (nh - 1) / 2, (nw - 1) / 2
    if forma == "Circular":
        # círculo real (mismo radio físico en ambos ejes — la grilla ya
        # respeta la proporción real de la imagen, 1 unidad de grilla =
        # misma distancia física en X que en Y): usa el semieje menor,
        # así el círculo queda siempre inscripto sin recortarse.
        rx = ry = min(nh, nw) / 2
        x, y = (xs - cx) / rx, (ys - cy) / ry
        return np.sqrt(x ** 2 + y ** 2)
    if forma == "Ovalada":  # elipse inscripta en todo el rectángulo de la grilla
        ry, rx = nh / 2, nw / 2
        x, y = (xs - cx) / rx, (ys - cy) / ry
        return np.sqrt(x ** 2 + y ** 2)
    if forma == "Hexagonal":
        # hexágono regular (orientación "punta a la izq/der") — distancia
        # tipo Chebyshev sobre 3 ejes a 60°, el mismo truco que separa un
        # hexágono en 3 franjas paralelas por par de lados opuestos.
        r = min(nh, nw) / 2
        x, y = (xs - cx) / r, (ys - cy) / r
        return np.maximum(np.abs(x), np.maximum(np.abs(0.5 * x + 0.8660254 * y), np.abs(0.5 * x - 0.8660254 * y)))
    return None  # "Rectangular" — sin silueta propia, todo el rectángulo


def _mascara_medallon(nh, nw, forma="Rectangular", suavizado_borde=0.06):
    """Máscara [0,1] (nh,nw) para recortar el relieve dentro de una
    silueta — "Circular"/"Ovalada"/"Hexagonal" dejan un medallón con la
    foto tallada adentro y el marco alrededor liso (a nivel de la
    base), en vez de ocupar todo el rectángulo. "Rectangular" devuelve
    None (sin recorte — comportamiento clásico). El borde tiene un
    degradé suave (no un escalón brusco) para que la transición se
    imprima limpia."""
    dist = _distancia_forma(nh, nw, forma)
    if dist is None:
        return None
    mascara = np.clip((1.0 - dist) / suavizado_borde, 0.0, 1.0)
    return mascara


def _mapa_marco_mm(nh, nw, forma, marco_mm, ancho_marco_frac=0.08):
    """Mapa de altura EXTRA (mm), del mismo tamaño que la grilla —
    reborde decorativo levantado justo dentro del borde de la silueta
    (perfil tipo "burbuja": 0 en el centro del medallón, sube a
    `marco_mm` a mitad de la banda, vuelve a 0 en el borde exterior),
    como el reborde levantado de una moneda o medalla. Solo tiene
    sentido con formas que tienen silueta propia (ver
    FORMAS_MEDALLON_CON_MARCO) — para "Rectangular" (sin margen propio,
    la foto ocupa toda la placa) devuelve None. `ancho_marco_frac`:
    ancho de la banda como fracción del radio/semieje de la silueta."""
    if marco_mm <= 0 or ancho_marco_frac <= 0 or forma not in FORMAS_MEDALLON_CON_MARCO:
        return None
    dist = _distancia_forma(nh, nw, forma)
    d0 = max(0.0, 1.0 - ancho_marco_frac)
    t = np.clip((dist - d0) / max(1.0 - d0, 1e-6), 0.0, 1.0)
    perfil = np.sin(t * np.pi)  # 0 en t=0 (interior), 1 en t=0.5 (cresta), 0 en t=1 (borde exterior)
    return np.where(dist <= 1.0 + 1e-6, marco_mm * perfil, 0.0)


def _malla_desde_grilla(alturas_norm, ancho_mm, alto_mm, espesor_base_mm, relieve_mm, oscuro_alto=True,
                         mapa_relieve_mm=None, forma_medallon="Rectangular",
                         marco_mm=0.0, ancho_marco_frac=0.08):
    """Arma una malla watertight a partir de una grilla de alturas
    normalizadas [0,1] (`alturas_norm`, fila 0 = arriba de la imagen):
    superficie de arriba con Z variable (`espesor_base_mm` +
    `relieve_mm` * altura), piso plano en Z=0, y las 4 paredes laterales
    cerrando el volumen — un bloque sólido con la foto tallada arriba,
    no una cáscara abierta. `oscuro_alto=True` -> las zonas oscuras
    quedan más altas (relieve "escultórico" típico); en falso, las
    claras quedan más altas (más parecido a una litofanía vista a
    trasluz, aunque litofanía de verdad es al revés en grosor, no en
    altura — esto es una escultura de relieve, no un difusor).

    `mapa_relieve_mm`: si se pasa (array 2D del mismo tamaño que
    `alturas_norm`, en mm), reemplaza al `relieve_mm` escalar — el
    relieve máximo pasa a variar por píxel (ej. mayor sobre el sujeto,
    menor sobre el fondo, ver `_mapa_relieve_sujeto_fondo`).

    `forma_medallon`: "Rectangular" (clásico, ocupa todo) / "Circular" /
    "Ovalada" — recorta el relieve dentro de esa silueta, con el resto
    de la placa lisa (a nivel de base) alrededor, como un medallón."""
    nh, nw = alturas_norm.shape
    h = 1.0 - alturas_norm if oscuro_alto else alturas_norm

    mascara = _mascara_medallon(nh, nw, forma_medallon)
    if mascara is not None:
        h = h * mascara

    relieve_efectivo = mapa_relieve_mm if mapa_relieve_mm is not None else relieve_mm
    z_top = espesor_base_mm + h * relieve_efectivo

    mapa_marco = _mapa_marco_mm(nh, nw, forma_medallon, marco_mm, ancho_marco_frac)
    if mapa_marco is not None:
        z_top = z_top + mapa_marco

    xs = np.linspace(0, ancho_mm, nw)
    ys = np.linspace(alto_mm, 0, nh)  # fila 0 (arriba de la imagen) -> Y más alto
    xx, yy = np.meshgrid(xs, ys)

    top = np.column_stack([xx.ravel(), yy.ravel(), z_top.ravel()])
    bottom = np.column_stack([xx.ravel(), yy.ravel(), np.zeros(nh * nw)])
    offset = nh * nw

    def idx(r, c):
        return r * nw + c

    faces = []
    for r in range(nh - 1):
        for c in range(nw - 1):
            a, b, cc, d = idx(r, c), idx(r, c + 1), idx(r + 1, c), idx(r + 1, c + 1)
            faces.append((a, b, d))
            faces.append((a, d, cc))
            faces.append((a + offset, d + offset, b + offset))
            faces.append((a + offset, cc + offset, d + offset))

    # las 4 paredes laterales — cada una conecta el borde de arriba con el de abajo
    for c in range(nw - 1):
        a, b = idx(0, c), idx(0, c + 1)
        faces.append((a, b, b + offset))
        faces.append((a, b + offset, a + offset))
        a, b = idx(nh - 1, c), idx(nh - 1, c + 1)
        faces.append((a, b, b + offset))
        faces.append((a, b + offset, a + offset))
    for r in range(nh - 1):
        a, b = idx(r, 0), idx(r + 1, 0)
        faces.append((a, b, b + offset))
        faces.append((a, b + offset, a + offset))
        a, b = idx(r, nw - 1), idx(r + 1, nw - 1)
        faces.append((a, b, b + offset))
        faces.append((a, b + offset, a + offset))

    verts = np.vstack([top, bottom])
    malla = trimesh.Trimesh(vertices=verts, faces=np.array(faces), process=True)
    # la orientación de cada cara de arriba está fijada a mano, pero la de las
    # paredes no se derivó -no hace falta: fix_normals() propaga una
    # orientación consistente hacia afuera para TODA la malla en base a la
    # conectividad, así no hay que resolver a mano el signo de cada pared.
    malla.fix_normals()
    return malla


def escultura_desde_imagen(ruta_imagen, ancho_mm=80.0, alto_mm=80.0,
                            espesor_base_mm=3.0, relieve_mm=8.0,
                            resolucion_px=RESOLUCION_MAX_PX, suavizado_px=1.0,
                            oscuro_alto=True, usar_clahe=True, usar_bilateral=True,
                            segmentar_sujeto=False, factor_relieve_sujeto=1.4, factor_relieve_fondo=0.35,
                            forma_medallon="Rectangular", marco_mm=0.0, ancho_marco_frac=0.08):
    """Imagen -> malla 3D de relieve/escultura, lista para exportar.
    Mejoras de calidad: CLAHE (contrast equalization) + bilateral filtering.
    `usar_clahe`: aplica adaptive histogram equalization (True por default).
    `usar_bilateral`: aplica edge-aware smoothing (True por default).

    `segmentar_sujeto=True`: relieve escultórico "diferenciado" — separa
    sujeto/fondo con rembg y el relieve máximo (`relieve_mm`) se escala
    por `factor_relieve_sujeto` sobre la persona/objeto (>1, resalta) y
    por `factor_relieve_fondo` sobre el fondo (<1, queda casi plano) — el
    resultado se lee más como un relieve escultórico real (la figura
    "sale" del fondo) que el relieve uniforme por brillo solo. Si rembg
    no está disponible o falla la segmentación, cae de vuelta al relieve
    uniforme de siempre (no rompe el modo clásico).

    `forma_medallon`: "Rectangular" (clásico) / "Circular" / "Ovalada" /
    "Hexagonal" — recorta el relieve dentro de esa silueta (medallón),
    con el marco alrededor liso a nivel de base. `marco_mm` (>0, solo
    con formas no-Rectangular): agrega un reborde decorativo levantado
    justo dentro del borde de la silueta, tipo moneda/medalla —
    `ancho_marco_frac` controla qué tan ancha es esa banda."""
    alturas = _grilla_de_alturas(ruta_imagen, resolucion_px, suavizado_px, usar_clahe, usar_bilateral)

    mapa_relieve_mm = None
    if segmentar_sujeto:
        mascara = _mascara_sujeto(ruta_imagen, resolucion_px)
        if mascara is not None and mascara.shape == alturas.shape:
            mapa_relieve_mm = relieve_mm * (
                factor_relieve_fondo + (factor_relieve_sujeto - factor_relieve_fondo) * mascara
            )

    malla = _malla_desde_grilla(alturas, ancho_mm, alto_mm, espesor_base_mm, relieve_mm, oscuro_alto,
                                 mapa_relieve_mm, forma_medallon, marco_mm, ancho_marco_frac)

    if not malla.is_watertight:
        trimesh.repair.fill_holes(malla)
        malla.fix_normals()

    return malla


def ajustar_caja_a_proporcion(ruta_imagen, ancho_mm):
    """Devuelve (ancho_mm, alto_mm) manteniendo la proporción real de
    `ruta_imagen` para un ancho pedido — así el relieve no sale
    estirado/aplastado. Si no se puede leer la imagen, devuelve
    (ancho_mm, ancho_mm) como respaldo (cuadrado)."""
    try:
        with Image.open(ruta_imagen) as img:
            w, h = img.size
        if w <= 0:
            return ancho_mm, ancho_mm
        return ancho_mm, ancho_mm * h / w
    except OSError:
        return ancho_mm, ancho_mm
