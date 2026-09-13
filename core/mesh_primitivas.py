#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/mesh_primitivas.py
--------------------------
Primitivas 3D reutilizables (pedestales, texto grabado en volumen,
figuras decorativas simples) — mismo patrón geométrico probado en
generators/topper.py, pero en un módulo aparte e independiente (no
comparte estado ni se importa desde topper.py) para no arriesgar
regresiones en esa herramienta ya en producción.

Usado por generators/esculturas.py para pedestales/placas de nombre en
estatuas 3D (TripoSR) y escenas grupales con varias figuras.

shapely/matplotlib.textpath se importan on-demand (no al cargar el
módulo): si el entorno tiene una instalación de shapely rota, un import
a nivel de módulo tumba toda la página que lo usa — con el import
diferido, solo falla (con error controlado) la función que
efectivamente necesita texto grabado."""

import numpy as np
import trimesh

_sg = None
_so = None
_TextPath = None
_FontProperties = None


def _shapely():
    global _sg, _so
    if _sg is None:
        import shapely.geometry as sg
        import shapely.ops as so
        _sg, _so = sg, so
    return _sg, _so


def _textpath():
    global _TextPath, _FontProperties
    if _TextPath is None:
        from matplotlib.textpath import TextPath
        from matplotlib.font_manager import FontProperties
        _TextPath, _FontProperties = TextPath, FontProperties
    return _TextPath, _FontProperties


FORMAS_BASE = ["Redonda", "Ovalada", "Cuadrada", "Rectangular"]

# Rotación que convierte "arriba" en mi convención local (eje Z, como un
# molde/cortante visto desde arriba) al eje "arriba" que espera el visor
# glTF/model-viewer (eje Y) — así la base queda abajo y la pieza arriba
# en la vista "Frente" del visor (misma matriz probada en topper.py).
_MATRIZ_ARRIBA_VISOR = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], dtype=float)


def orientar_para_visor(malla):
    T4 = np.eye(4)
    T4[:3, :3] = _MATRIZ_ARRIBA_VISOR
    malla.apply_transform(T4)
    return malla


def cilindro(radio, altura, z0=0.0, segmentos=28, radio_top_factor=1.0):
    """Cilindro (o tronco de cono si radio_top_factor != 1) sólido, watertight."""
    theta = np.linspace(0, 2 * np.pi, segmentos, endpoint=False)
    verts = []
    for angle in theta:
        x, y = radio * np.cos(angle), radio * np.sin(angle)
        verts.append([x, y, z0])
        verts.append([x * radio_top_factor, y * radio_top_factor, z0 + altura])
    idx_bottom = len(verts)
    verts.append([0, 0, z0])
    idx_top = len(verts)
    verts.append([0, 0, z0 + altura])

    faces = []
    n = segmentos
    for i in range(n):
        j = (i + 1) % n
        faces.append([i * 2, j * 2, idx_bottom])
        faces.append([i * 2 + 1, idx_top, j * 2 + 1])
        faces.append([i * 2, j * 2, j * 2 + 1])
        faces.append([i * 2, j * 2 + 1, i * 2 + 1])

    return trimesh.Trimesh(vertices=np.array(verts, dtype=np.float64), faces=np.array(faces, dtype=np.int64), process=True)


def bloque(ancho, profundidad, altura, cx=0.0, cy=0.0, z0=0.0):
    caja = trimesh.creation.box(extents=[ancho, profundidad, altura])
    caja.apply_translation([cx, cy, z0 + altura / 2])
    return caja


def forma_base(forma, radio, altura, z0=0.0, factor_ovalo=0.62):
    """Malla de un pedestal/placa según su silueta — Redonda/Ovalada/
    Cuadrada/Rectangular — todas dimensionadas por un único `radio`
    (mitad del lado/diámetro mayor)."""
    if forma == "Ovalada":
        malla = cilindro(radio, altura, z0=z0)
        malla.apply_scale([1.0, factor_ovalo, 1.0])
        return malla
    if forma == "Cuadrada":
        lado = radio * 1.7
        return bloque(lado, lado, altura, z0=z0)
    if forma == "Rectangular":
        return bloque(radio * 2.1, radio * 1.3, altura, z0=z0)
    return cilindro(radio, altura, z0=z0)  # "Redonda" (default)


def texto_a_poligono(texto, fuente_ttf=None, tam_fuente=100):
    """Convierte `texto` en un shapely (Multi)Polygon con agujeros reales
    (la "o" tiene hueco, etc.) usando los contornos vectoriales de la
    fuente elegida — texto real, no una aproximación de bloques."""
    sg, so = _shapely()
    TextPath, FontProperties = _textpath()
    try:
        fp = FontProperties(fname=fuente_ttf) if fuente_ttf else FontProperties()
        tp = TextPath((0, 0), texto, size=tam_fuente, prop=fp)
    except Exception:
        tp = TextPath((0, 0), texto, size=tam_fuente, prop=FontProperties())

    contornos = [sg.Polygon(p) for p in tp.to_polygons() if len(p) >= 3]
    contornos = [p for p in contornos if p.is_valid and p.area > 1e-6]
    if not contornos:
        return None

    contornos.sort(key=lambda p: p.area, reverse=True)
    usados = [False] * len(contornos)
    resultado = []
    for i, p in enumerate(contornos):
        if usados[i]:
            continue
        huecos = []
        for j in range(i + 1, len(contornos)):
            if usados[j]:
                continue
            if p.contains(contornos[j]):
                huecos.append(list(contornos[j].exterior.coords))
                usados[j] = True
        resultado.append(sg.Polygon(p.exterior.coords, huecos))

    return so.unary_union(resultado)


def texto_a_malla3d(texto, altura, fuente_ttf=None, z0=0.0, grosor=None):
    """Malla 3D del texto (letras reales, con sus huecos) parada de pie:
    X=ancho, Z=altura visual, Y=grosor del material (mirando hacia la
    cámara "Frente" tras orientar_para_visor) — centrada en X e Y=0,
    apoyada desde z0. None si el texto queda vacío."""
    if grosor is None:
        grosor = max(2.5, altura * 0.3)
    texto_limpio = (texto or "").strip()
    if not texto_limpio:
        return None

    multi = texto_a_poligono(texto_limpio, fuente_ttf, tam_fuente=100)
    if multi is None or multi.is_empty:
        return None

    piezas = multi.geoms if hasattr(multi, "geoms") else [multi]
    mallas = [trimesh.creation.extrude_polygon(p, height=grosor)
              for p in piezas if p.is_valid and p.area > 0]
    if not mallas:
        return None

    malla = trimesh.util.concatenate(mallas)
    alto_actual = max(malla.extents[1], 1e-9)
    factor = altura / alto_actual
    malla.apply_scale([factor, factor, 1.0])

    # Roto 90° en X: el alto del glifo (viejo Y) pasa a ser la altura
    # vertical real (Z), y el grosor (viejo Z) pasa a Y.
    R = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]], dtype=float)
    T4 = np.eye(4)
    T4[:3, :3] = R
    malla.apply_transform(T4)

    bounds = malla.bounds
    cx = (bounds[0][0] + bounds[1][0]) / 2
    cy = (bounds[0][1] + bounds[1][1]) / 2
    z_min = bounds[0][2]
    malla.apply_translation([-cx, -cy, z0 - z_min])
    return malla


def combinar(mallas):
    """Concatena mallas (sin booleana real, solo unión de geometría para
    export STL — suficiente para imprimir como piezas fusionadas visualmente)."""
    validas = [m for m in mallas if m is not None and len(m.vertices) > 0]
    if not validas:
        raise ValueError("No hay geometría para combinar")
    return trimesh.util.concatenate(validas)
