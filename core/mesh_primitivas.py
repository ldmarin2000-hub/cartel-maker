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


# Patrones decorativos para la pared del pedestal — misma técnica de
# offset radial que generators/portalapices.py (no se comparte código a
# propósito, ver docstring del módulo), pero acá se talla sobre un
# pedestal SÓLIDO: es relieve puramente superficial, no compromete la
# resistencia como sí podría hacerlo en una pared hueca fina.
# "Estriado" es el acabado clásico de columna griega/romana.
PATRONES_PEDESTAL = ["Liso", "Estriado (columna clásica)", "Diamante (rombos)", "Panal (hexágonos)", "Puntos"]


def _offset_patron_pedestal(patron, theta, z_norm, frecuencia_theta, frecuencia_z, profundidad):
    """Offset radial (mm) en el punto (theta, z_norm∈[0,1]) según el
    patrón — `theta` es un ángulo escalar acá (se llama una vez por
    vértice, no vectorizado sobre todo el anillo)."""
    if patron == "Estriado (columna clásica)":
        return profundidad * np.sin(theta * frecuencia_theta)
    if patron == "Diamante (rombos)":
        onda = np.sin(theta * frecuencia_theta) * np.sin(z_norm * frecuencia_z * np.pi)
        return profundidad * onda
    if patron == "Panal (hexágonos)":
        a = np.sin(theta * frecuencia_theta + z_norm * frecuencia_z * np.pi * 0.5)
        b = np.sin(theta * frecuencia_theta * 0.5 - z_norm * frecuencia_z * np.pi)
        return profundidad * 0.5 * (a + b)
    if patron == "Puntos":
        onda = np.cos(theta * frecuencia_theta) * np.cos(z_norm * frecuencia_z * np.pi)
        return profundidad * max(float(onda), 0.0)
    return 0.0


def cilindro_texturado(radio, altura, patron="Liso", z0=0.0, segmentos=64, anillos=48,
                        radio_top_factor=1.0, densidad=5, profundidad_mm=1.2):
    """Como `cilindro()`, pero con un patrón decorativo (PATRONES_PEDESTAL)
    tallado como relieve real en la pared exterior — mismo repertorio que
    el portalápices, aplicado acá a un pedestal de estatua. `patron="Liso"`
    delega directo a `cilindro()` (mismo resultado exacto, sin anillos de
    más, cero cambio de comportamiento para todo el código ya existente
    que no pide patrón)."""
    if patron == "Liso" or patron not in PATRONES_PEDESTAL:
        # Sin pasar `segmentos`: usa el default propio de cilindro() (28)
        # así el pedestal liso queda EXACTO al de antes de esta función
        # existir, cero cambio de comportamiento para el código ya en uso.
        return cilindro(radio, altura, z0=z0, radio_top_factor=radio_top_factor)

    theta = np.linspace(0, 2 * np.pi, segmentos, endpoint=False)
    z_vals = np.linspace(0.0, altura, anillos)
    frecuencia_theta = max(4, int(segmentos / max(densidad, 1)))
    frecuencia_z = max(2, int(anillos / max(densidad, 1) / 3))

    verts = []
    for z in z_vals:
        z_norm = z / altura if altura > 0 else 0.0
        radio_z = radio * (1.0 + (radio_top_factor - 1.0) * z_norm)
        for a in theta:
            off = _offset_patron_pedestal(patron, a, z_norm, frecuencia_theta, frecuencia_z, profundidad_mm)
            r = max(radio_z + off, radio_z * 0.5)  # nunca colapsa el radio a cero/negativo
            verts.append([r * np.cos(a), r * np.sin(a), z0 + z])

    n, m = segmentos, len(z_vals)
    idx_bottom = len(verts)
    verts.append([0.0, 0.0, z0])
    idx_top = len(verts)
    verts.append([0.0, 0.0, z0 + altura])

    faces = []
    for i in range(m - 1):
        for k in range(n):
            j2 = (k + 1) % n
            faces.append([i * n + k, i * n + j2, (i + 1) * n + j2])
            faces.append([i * n + k, (i + 1) * n + j2, (i + 1) * n + k])
    for k in range(n):
        j2 = (k + 1) % n
        faces.append([k, j2, idx_bottom])
        faces.append([(m - 1) * n + k, idx_top, (m - 1) * n + j2])

    return trimesh.Trimesh(
        vertices=np.array(verts, dtype=np.float64),
        faces=np.array(faces, dtype=np.int64), process=True,
    )


def forma_base(forma, radio, altura, z0=0.0, factor_ovalo=0.62,
                patron="Liso", densidad_patron=5, profundidad_patron=1.2):
    """Malla de un pedestal/placa según su silueta — Redonda/Ovalada/
    Cuadrada/Rectangular — todas dimensionadas por un único `radio`
    (mitad del lado/diámetro mayor). `patron` (PATRONES_PEDESTAL) solo
    aplica a Redonda/Ovalada (son las que tienen pared cilíndrica real
    donde tallar un relieve); Cuadrada/Rectangular lo ignoran y quedan
    lisas — el llamador es quien decide si avisar de esa limitación."""
    if forma == "Ovalada":
        malla = cilindro_texturado(radio, altura, patron=patron, z0=z0,
                                    densidad=densidad_patron, profundidad_mm=profundidad_patron)
        malla.apply_scale([1.0, factor_ovalo, 1.0])
        return malla
    if forma == "Cuadrada":
        lado = radio * 1.7
        return bloque(lado, lado, altura, z0=z0)
    if forma == "Rectangular":
        return bloque(radio * 2.1, radio * 1.3, altura, z0=z0)
    return cilindro_texturado(radio, altura, patron=patron, z0=z0,
                               densidad=densidad_patron, profundidad_mm=profundidad_patron)  # "Redonda"


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
