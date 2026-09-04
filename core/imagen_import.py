#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/imagen_import.py
------------------------
Imagen rasterizada (PNG/JPG, un logo/ícono cualquiera) -> polígono
shapely relleno, con el mismo enfoque que core/texto2d.py para texto y
core/svg_import.py para SVG: se vectoriza por contorno (marching
squares vía scikit-image, huecos con core/poligonos.py). No hace falta
ninguna librería nueva — reusa PIL + numpy + scikit-image, que el
proyecto ya usa para el texto.

Pensado para logos/íconos simples (silueta clara sobre fondo liso o
transparente, sin fotos ni degradados) — no es un rastreador general de
fotografías; una foto real da un contorno enorme y probablemente
inservible para imprimir.
"""

import numpy as np
from PIL import Image
from scipy import ndimage
from shapely.geometry import Polygon
from shapely.ops import unary_union
from skimage import measure

from core.poligonos import combinar_con_huecos

TAMANO_TRABAJO_PX = 500  # se reescala a esto (lado mayor) antes de vectorizar
AREA_MINIMA_PX = 4  # contornos más chicos que esto se descartan como ruido (antialiasing, JPG)
COLORES_DETECCION_DEFAULT = 12  # cuántos colores se cuantizan puertas adentro (más que los 4 que se van a usar)
AREA_MINIMA_FRACCION = 0.003  # candidatos con menos de esta fracción del área total se descartan (motitas de antialiasing)
TOLERANCIA_FONDO = 24  # distancia RGB para considerar un píxel del borde "del color de fondo"
TOLERANCIA_FUSION_COLOR = 40  # distancia RGB para fusionar dos colores detectados que en la práctica son el mismo


def _detectar_fondo_solido(arr_rgb, tolerancia=TOLERANCIA_FONDO):
    """Para imágenes SIN transparencia (típico: un logo bajado de la web
    con fondo blanco sólido en vez de recortado): arma una máscara de
    "es fondo" mirando qué color predomina en el borde de la imagen y
    marcando esos píxeles -- pero SOLO los que están conectados al
    borde (`scipy.ndimage.label`), no cualquier píxel de ese color en
    cualquier lado. Así un detalle real del mismo color que el fondo
    pero ENCERRADO adentro del dibujo (ej. una franja blanca dentro de
    un escudo) no se confunde con fondo y se sigue pudiendo usar como
    su propio color."""
    borde = np.concatenate([arr_rgb[0, :], arr_rgb[-1, :], arr_rgb[:, 0], arr_rgb[:, -1]]).astype(float)
    color_fondo = np.median(borde, axis=0)
    distancia = np.sqrt(((arr_rgb.astype(float) - color_fondo) ** 2).sum(axis=2))
    es_color_fondo = distancia < tolerancia

    etiquetas, _ = ndimage.label(es_color_fondo)
    etiquetas_borde = set(etiquetas[0, :].tolist()) | set(etiquetas[-1, :].tolist()) \
        | set(etiquetas[:, 0].tolist()) | set(etiquetas[:, -1].tolist())
    etiquetas_borde.discard(0)
    if not etiquetas_borde:
        return np.zeros(arr_rgb.shape[:2], dtype=bool)
    return np.isin(etiquetas, list(etiquetas_borde))


def _fusionar_colores_cercanos(candidatos, tolerancia=TOLERANCIA_FUSION_COLOR):
    """`candidatos`: lista de (area_px, polígono, "#rrggbb"). Antialiasing
    o compresión JPG/PNG a veces hacen que un mismo color visual (ej. el
    blanco de un escudo) caiga en dos baldes de cuantización casi
    iguales ("#fefefe" y "#ffffff") en vez de uno -- se fusionan los que
    estén a menos de `tolerancia` de distancia RGB entre sí, sumando su
    área y uniendo su geometría, y quedándose con el color del más
    grande del grupo. Devuelve la lista ya fusionada, ordenada de mayor
    a menor área."""
    grupos = []
    for area_px, poligono, color_hex in candidatos:
        rgb = tuple(int(color_hex[i:i + 2], 16) for i in (1, 3, 5))
        grupo_encontrado = None
        for grupo in grupos:
            dist = sum((a - b) ** 2 for a, b in zip(rgb, grupo["rgb"])) ** 0.5
            if dist < tolerancia:
                grupo_encontrado = grupo
                break
        if grupo_encontrado is not None:
            grupo_encontrado["area_px"] += area_px
            grupo_encontrado["poligono"] = unary_union([grupo_encontrado["poligono"], poligono])
        else:
            grupos.append({"area_px": area_px, "poligono": poligono, "color_hex": color_hex, "rgb": rgb})

    grupos.sort(key=lambda g: g["area_px"], reverse=True)
    return [(g["area_px"], g["poligono"], g["color_hex"]) for g in grupos]


def _mascara_desde_imagen(ruta_imagen, umbral, invertir):
    img = Image.open(ruta_imagen)

    ancho, alto = img.size
    escala = TAMANO_TRABAJO_PX / max(ancho, alto)
    if escala < 1:
        img = img.resize((max(1, int(ancho * escala)), max(1, int(alto * escala))), Image.LANCZOS)

    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        img = img.convert("RGBA")
        alfa = np.array(img)[:, :, 3]
        mascara = alfa > 16  # cualquier pixel no-transparente cuenta como "tinta"
    else:
        gris = np.array(img.convert("L"))
        mascara = gris < umbral  # oscuro = tinta, sobre fondo claro (el caso típico de un logo)

    if invertir:
        mascara = ~mascara
    return mascara


def _limpiar_mascara(mascara):
    """Suaviza una máscara booleana antes de vectorizarla: saca motitas
    sueltas de 1-2 píxeles y rellena agujeritos chicos (`binary_opening`
    + `binary_closing`, scipy.ndimage) -- el antialiasing de los bordes
    entre colores deja franjas de píxeles "de transición" que si no se
    limpian, vectorizan como un borde en zigzag ("movimientos" que
    después no cortan bien en el laminador) en vez de una línea prolija."""
    estructura = np.ones((3, 3), dtype=bool)
    limpia = ndimage.binary_opening(mascara, structure=estructura)
    limpia = ndimage.binary_closing(limpia, structure=estructura)
    return limpia


def _mascara_a_poligono(mascara):
    """Vectoriza una máscara booleana (marching squares) a un polígono
    shapely con huecos -- el paso compartido entre
    `imagen_a_poligono_crudo` (una máscara) e
    `imagen_a_poligonos_por_color` (una máscara por color detectado)."""
    contornos = measure.find_contours(mascara.astype(float), level=0.5)
    alto_px = mascara.shape[0]

    polys = []
    for c in contornos:
        if len(c) < 4:
            continue
        pts = [(col, alto_px - row) for row, col in c]  # flip Y: fila 0 = arriba
        p = Polygon(pts)
        if not p.is_valid:
            p = p.buffer(0)
        if p.is_empty or p.area < AREA_MINIMA_PX:
            continue
        polys.append(p)

    return combinar_con_huecos(polys)


def imagen_a_poligono_crudo(ruta_imagen, umbral=128, invertir=False):
    """Vectoriza `ruta_imagen` (cualquier formato que abra PIL — PNG,
    JPG, etc) a un polígono shapely SIN escalar (unidades de píxel) —
    usa el canal alfa como máscara si la imagen tiene transparencia (PNG
    recortado, lo más común para un logo), si no umbraliza por
    luminosidad (oscuro = forma, sobre fondo claro; `invertir=True` para
    el caso contrario, forma clara sobre fondo oscuro). Devuelve None si
    no se pudo sacar ninguna forma con área."""
    mascara = _mascara_desde_imagen(ruta_imagen, umbral, invertir)
    return _mascara_a_poligono(mascara)


def imagen_a_poligonos_por_color(ruta_imagen, colores_deteccion=COLORES_DETECCION_DEFAULT):
    """Separa `ruta_imagen` en regiones por color real (cuantización,
    PIL Image.quantize) en vez de una silueta de un solo color --
    pensado para un logo/escudo con varios colores bien definidos (rojo/
    blanco/etc), no para una foto. Cuantiza a `colores_deteccion`
    colores PUERTAS ADENTRO -- a propósito más de los 4 que se vayan a
    usar al final (ver MAX_COLORES_DECORACION_MULTICOLOR en
    generators/topper.py): con solo 4 casilleros de cuantización, un
    logo con antialiasing fuerte (escudos con degradés/sombreado, como
    el de la AFA) puede terminar mezclando dos colores reales en un
    solo balde, o quedándose con un color "mezcla" de borde en vez de
    uno real -- pedir más y dejar que el que llama filtre cuáles usar da
    mejor resultado que forzar la cantidad final acá. Cada máscara de
    color se limpia con `_limpiar_mascara` antes de vectorizar (saca el
    ruido de antialiasing que si no queda como un borde en zigzag).

    Usa el canal alfa para ignorar el fondo transparente si la imagen lo
    tiene; si NO tiene transparencia, intenta detectar un fondo sólido
    liso mirando los bordes de la imagen (`_detectar_fondo_solido`) y lo
    ignora igual -- muy común bajar un logo de la web con fondo blanco
    en vez de recortado. Sin escalar (unidades de píxel), en el MISMO
    sistema de coordenadas entre sí (a diferencia de vectorizar cada
    color por separado con `imagen_a_poligono_crudo`, que perdería la
    posición relativa entre colores). Descarta candidatos con menos de
    `AREA_MINIMA_FRACCION` del área total (motitas de antialiasing que
    quedaron como su propio balde de color), y fusiona los que salgan
    con un color casi idéntico entre sí (`_fusionar_colores_cercanos`).

    Devuelve una lista de (polígono, "#rrggbb") ordenada de mayor a
    menor área, o lista vacía si no se pudo sacar nada."""
    img = Image.open(ruta_imagen)
    ancho, alto = img.size
    escala = TAMANO_TRABAJO_PX / max(ancho, alto)
    if escala < 1:
        img = img.resize((max(1, int(ancho * escala)), max(1, int(alto * escala))), Image.LANCZOS)

    tiene_alfa = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
    img_rgba = img.convert("RGBA")
    arr_rgba = np.array(img_rgba)
    if tiene_alfa:
        mascara_valida = arr_rgba[:, :, 3] > 16
    else:
        mascara_valida = ~_detectar_fondo_solido(arr_rgba[:, :, :3])
    area_total = int(mascara_valida.sum())
    if area_total == 0:
        return []
    area_minima = max(AREA_MINIMA_PX, area_total * AREA_MINIMA_FRACCION)

    cuantizada = img_rgba.convert("RGB").quantize(colors=colores_deteccion, method=Image.Quantize.MEDIANCUT)
    paleta = cuantizada.getpalette()
    indices = np.array(cuantizada)

    candidatos = []
    for idx in sorted(set(indices[mascara_valida].tolist())):
        mascara_color = (indices == idx) & mascara_valida
        area_px = int(mascara_color.sum())
        if area_px < area_minima:
            continue
        mascara_color = _limpiar_mascara(mascara_color)
        poligono = _mascara_a_poligono(mascara_color)
        if poligono is None or poligono.is_empty or poligono.area < area_minima:
            continue
        r, g, b = paleta[idx * 3], paleta[idx * 3 + 1], paleta[idx * 3 + 2]
        candidatos.append((area_px, poligono, f"#{r:02x}{g:02x}{b:02x}"))

    candidatos = _fusionar_colores_cercanos(candidatos)
    return [(poligono, color_hex) for _, poligono, color_hex in candidatos]
