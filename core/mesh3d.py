#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/mesh3d.py
----------------
Paso 4 del pipeline de neón: geometría shapely -> malla 3D (trimesh):
extrude por polígono, unión watertight con manifold3d (fallback a
concatenate) y export a STL.
"""

import os
import tempfile

import networkx as nx
import numpy as np
import trimesh
from trimesh.creation import extrude_polygon

# Matrices verificadas a mano (con formas asimétricas + render 3D) para que un
# polígono 2D (x horizontal, y vertical/arriba) quede orientado bien derecho —
# sin espejar — al extruirlo a lo largo de cada eje. Las dos son rotaciones
# propias (determinante +1), por eso no espejan nada.
_MATRIZ_EXTRUSION_FRENTE = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], dtype=float)   # mirando a lo largo de +Y
_MATRIZ_EXTRUSION_COSTADO = np.array([[0, 0, 1], [1, 0, 0], [0, 1, 0]], dtype=float)   # mirando a lo largo de +X


def _extruir_orientado(geom, profundidad, matriz):
    piezas = piezas_desde_geom(geom, profundidad)
    if not piezas:
        return None
    malla = trimesh.util.concatenate(piezas) if len(piezas) > 1 else piezas[0]
    T4 = np.eye(4)
    T4[:3, :3] = matriz
    malla.apply_transform(T4)
    malla.apply_translation([0, 0, -malla.bounds[0][2]])  # que la altura arranque en Z=0
    return malla


def extruir_de_frente(geom, profundidad):
    """Extruye `geom` (polígono 2D, x=horizontal, y=arriba) a lo largo del
    eje Y, de forma que mirando la pieza a lo largo de +Y se vea `geom`
    bien derecho (sin espejar). Para el lado "de frente" del ambigrama."""
    return _extruir_orientado(geom, profundidad, _MATRIZ_EXTRUSION_FRENTE)


def extruir_de_costado(geom, profundidad):
    """Extruye `geom` a lo largo del eje X, de forma que mirando la pieza
    a lo largo de +X se vea `geom` bien derecho. Para el lado "de costado"
    del ambigrama — perpendicular a extruir_de_frente()."""
    return _extruir_orientado(geom, profundidad, _MATRIZ_EXTRUSION_COSTADO)


def extruir_vertical(geom, profundidad):
    """Extruye `geom` derecho a lo largo del eje Z (sin rotar — `geom` ya
    queda con x=horizontal, y=arriba tal cual, como un molde de
    cortante). Para el lado del ambigrama que se lee mirando desde ARRIBA
    o desde ABAJO, no de costado."""
    piezas = piezas_desde_geom(geom, profundidad)
    if not piezas:
        return None
    return trimesh.util.concatenate(piezas) if len(piezas) > 1 else piezas[0]


def piezas_desde_geom(geom, altura, z=0.0):
    """Extruye cada polígono de una geometría shapely (Polygon o
    MultiPolygon) por separado, para que la unión booleana no tenga
    problemas con huecos/agujeros compartidos."""
    pols = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
    piezas = []
    for pg in pols:
        if pg.is_empty or pg.area < 1e-6:
            continue
        m = extrude_polygon(pg, height=altura)
        if z:
            m.apply_translation([0, 0, z])
        piezas.append(m)
    return piezas


def _ancho_en_borde_y(malla, y_borde, es_min, banda_mm=3.0):
    """Ancho en X que tiene la malla cerca del borde Y indicado (una franja
    de `banda_mm`) — sirve para detectar el extremo más angosto (p.ej. la
    punta de un corazón) y enganchar el aro ahí en vez de en un borde fijo."""
    verts = malla.vertices
    mask = (verts[:, 1] <= y_borde + banda_mm) if es_min else (verts[:, 1] >= y_borde - banda_mm)
    xs = verts[mask, 0]
    return (xs.max() - xs.min()) if xs.size else float("inf")


def _punta_solida_en_z(malla, es_max, umbral_ancho_mm, banda_mm=0.5):
    """Busca una punta angosta CON MATERIAL REAL pegada al extremo Z
    indicado (p.ej. la punta de un corazón puesto "de frente", que
    siempre queda en Z máximo). Si en esa banda hay una superficie ancha
    (no una punta) o no hay nada (la punta quedó fragmentada por una
    intersección, como pasa cuando el corazón va "de arriba"), devuelve
    None — para que el que llama use el respaldo del disco plano de
    borde. Devuelve (x, y, z) del punto de anclaje si encuentra una punta
    válida."""
    (minx, miny, minz), (maxx, maxy, maxz) = malla.bounds
    z_borde = maxz if es_max else minz
    verts = malla.vertices
    mask = (verts[:, 2] >= z_borde - banda_mm) if es_max else (verts[:, 2] <= z_borde + banda_mm)
    sub = verts[mask]
    if sub.shape[0] == 0:
        return None
    ancho_x = sub[:, 0].max() - sub[:, 0].min()
    ancho_y = sub[:, 1].max() - sub[:, 1].min()
    if max(ancho_x, ancho_y) > umbral_ancho_mm:
        return None
    x = (sub[:, 0].min() + sub[:, 0].max()) / 2
    y = (sub[:, 1].min() + sub[:, 1].max()) / 2
    return (x, y, z_borde)


def _centro_en_borde_z(malla, es_max, banda_mm=0.5):
    """Centro (x, y) de TODO el material pegado al borde Z indicado, sin
    filtro de angostura (a diferencia de `_punta_solida_en_z`) — para
    cuando el usuario fuerza el aro a ese extremo a mano, sea una punta
    angosta o una cara ancha. Devuelve (x, y, z) o None si no hay nada
    pegado a ese borde exacto (no debería pasar, es un borde real de la
    malla)."""
    (minx, miny, minz), (maxx, maxy, maxz) = malla.bounds
    z_borde = maxz if es_max else minz
    verts = malla.vertices
    mask = (verts[:, 2] >= z_borde - banda_mm) if es_max else (verts[:, 2] <= z_borde + banda_mm)
    sub = verts[mask]
    if sub.shape[0] == 0:
        return None
    x = (sub[:, 0].min() + sub[:, 0].max()) / 2
    y = (sub[:, 1].min() + sub[:, 1].max()) / 2
    return (x, y, z_borde)


def _agregar_loop_vertical(malla, punta_xyz, radio_hueco, radio_tab, espesor_tab, solape_mm, crece_hacia_arriba=True):
    """Agrega un aro PARADO (agujero horizontal, eje X) que nace de
    `punta_xyz` y sigue hacia arriba (o hacia abajo, si
    `crece_hacia_arriba=False` — para un extremo Z mínimo) — para que se
    vea como una continuación de la punta (p.ej. de un corazón), no un
    disco plano pegado al costado."""
    x, y, z = punta_xyz
    signo = 1 if crece_hacia_arriba else -1
    aro = trimesh.creation.annulus(r_min=radio_hueco, r_max=radio_tab, height=espesor_tab, sections=48)
    aro.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0]))
    aro.apply_translation([x, y, z + signo * (radio_tab - solape_mm)])
    return trimesh.boolean.union([malla, aro], engine="manifold")


def agregar_aro_3d(malla, radio_hueco=2.0, radio_tab=6.0, espesor_tab=4.0, solape_mm=2.0,
                    banda_deteccion_mm=3.0, borde="auto"):
    """Agrega un aro para colgar de un llavero, en uno de los 4 extremos
    de la caja compartida del ambigrama — hundido `solape_mm` para quedar
    bien soldado (no flotando).

    `borde`:
    - "auto" (default): intenta primero un LOOP PARADO que nace de una
      punta angosta en Z máximo (p.ej. la de un corazón puesto "de
      frente" — ver `_punta_solida_en_z`), porque ahí la punta siempre
      tiene soporte sólido real sin importar el otro lado. Si esa zona no
      tiene una punta clara con material real (p.ej. un corazón puesto
      "de arriba", donde la intersección con el otro contenido deja la
      punta fragmentada), cae al disco plano en el borde Y más angosto
      (auto-detectado).
    - "y_min"/"y_max": fuerza a mano el disco plano de borde (Y mínimo o
      máximo) — para el contenido "de arriba".
    - "z_min"/"z_max": fuerza a mano el loop parado (abajo o arriba) —
      para el contenido "de frente", sea o no una punta angosta (usa el
      centro de lo que haya en ese borde)."""
    (minx, miny, minz), (maxx, maxy, maxz) = malla.bounds

    if borde in ("z_min", "z_max"):
        es_max = borde == "z_max"
        centro = _centro_en_borde_z(malla, es_max=es_max, banda_mm=banda_deteccion_mm)
        if centro is not None:
            return _agregar_loop_vertical(malla, centro, radio_hueco, radio_tab, espesor_tab, solape_mm,
                                           crece_hacia_arriba=es_max)
        borde = "auto"  # borde vacío (no debería pasar) — usamos el respaldo de siempre

    if borde == "auto":
        punta = _punta_solida_en_z(malla, es_max=True, umbral_ancho_mm=2 * radio_tab)
        if punta is not None:
            return _agregar_loop_vertical(malla, punta, radio_hueco, radio_tab, espesor_tab, solape_mm,
                                           crece_hacia_arriba=True)
        ancho_miny = _ancho_en_borde_y(malla, miny, es_min=True, banda_mm=banda_deteccion_mm)
        ancho_maxy = _ancho_en_borde_y(malla, maxy, es_min=False, banda_mm=banda_deteccion_mm)
        usar_min = ancho_miny < ancho_maxy
    else:
        usar_min = borde == "y_min"

    cx = (minx + maxx) / 2
    cy = (miny + solape_mm - radio_tab) if usar_min else (maxy - solape_mm + radio_tab)
    cz = maxz - espesor_tab / 2

    aro = trimesh.creation.annulus(r_min=radio_hueco, r_max=radio_tab, height=espesor_tab, sections=48)
    aro.apply_translation([cx, cy, cz])

    return trimesh.boolean.union([malla, aro], engine="manifold")


def _un_paso_de_puentes(malla, piezas, radio_puente):
    """Une TODAS las piezas de una tirada con puentes cilíndricos (árbol
    de expansión mínima). Cada puente PENETRA de verdad en ambas piezas
    (no solo las toca) para que la unión booleana las fusione. Devuelve
    (malla_con_puentes, cantidad_de_puentes) — o (malla, 0) si algún par
    de piezas da una geometría degenerada (distancia NaN) y no se puede
    calcular el puente con confianza."""
    grafo = nx.Graph()
    grafo.add_nodes_from(range(len(piezas)))
    segmentos = {}
    for i in range(len(piezas)):
        for j in range(i + 1, len(piezas)):
            cercanos, distancias, _ = trimesh.proximity.closest_point(piezas[j], piezas[i].vertices)
            idx = int(np.nanargmin(distancias)) if np.isfinite(distancias).any() else None
            if idx is None or not np.isfinite(distancias[idx]):
                continue  # geometría degenerada para este par; no forzamos un puente a ciegas
            p1, p2 = piezas[i].vertices[idx], cercanos[idx]
            grafo.add_edge(i, j, weight=distancias[idx])
            segmentos[(i, j)] = (p1, p2)

    if grafo.number_of_edges() == 0:
        return malla, 0

    arbol = nx.minimum_spanning_tree(grafo)
    margen = radio_puente * 1.2  # tocar en un punto no alcanza, hace falta superponerse
    puentes = []
    for i, j in arbol.edges():
        p1, p2 = segmentos[tuple(sorted((i, j)))]
        vec = p2 - p1
        dist = np.linalg.norm(vec)
        direccion = (vec / dist) if dist > 1e-6 else np.array([0.0, 0.0, 1.0])
        p1e, p2e = p1 - direccion * margen, p2 + direccion * margen
        puentes.append(trimesh.creation.cylinder(radius=radio_puente, segment=[p1e, p2e], sections=16))

    if not puentes:
        return malla, 0

    try:
        soldada = trimesh.boolean.union([malla] + puentes, engine="manifold")
    except Exception:
        soldada = trimesh.util.concatenate([malla] + puentes)
    return soldada, len(puentes)


def _piezas_segun_stl(malla):
    """Cuenta las piezas tal cual las va a ver el slicer: exporta a STL y
    lo vuelve a cargar. El STL no guarda vértices compartidos, así que a
    veces una malla que en memoria es "una sola pieza" queda con shells
    separados (aunque se toquen a distancia 0) después de este viaje de
    ida y vuelta — por eso conviene verificar así, no solo con
    malla.split() en memoria."""
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as tmp:
        ruta_tmp = tmp.name
    try:
        malla.export(ruta_tmp)
        return trimesh.load(ruta_tmp).split(only_watertight=False)
    finally:
        os.remove(ruta_tmp)


def conectar_componentes_3d(malla, radio_puente=1.5, max_intentos=5):
    """Si `malla` quedó con partes sueltas (p.ej. letras que la
    intersección booleana del ambigrama dejó sin tocarse entre sí, o sin
    tocar la base), las suelda con puentes cilíndricos finos, igual que
    core/geometry.py::conectar_componentes pero en 3D. Reintenta varias
    veces sobre lo que vaya quedando (a veces un puente no alcanza a
    fusionar del todo), verificando primero en memoria y al final con un
    viaje de ida y vuelta por STL (lo mismo que va a ver el slicer — un
    STL no guarda vértices compartidos, así que a veces algo que en
    memoria ya es una sola pieza queda separado en shells que se tocan a
    distancia 0, inofensivo para imprimir pero lo intentamos igual).
    Devuelve (malla_soldada, cantidad_total_de_puentes)."""
    total_puentes = 0
    for _ in range(max_intentos):
        piezas = malla.split(only_watertight=False)
        if len(piezas) <= 1:
            break
        malla, agregados = _un_paso_de_puentes(malla, piezas, radio_puente)
        total_puentes += agregados
        if agregados == 0:
            break

    # última pasada: verificar como lo va a ver el slicer (STL de ida y vuelta)
    try:
        piezas_stl = _piezas_segun_stl(malla)
        if len(piezas_stl) > 1:
            malla, agregados = _un_paso_de_puentes(malla, piezas_stl, radio_puente)
            total_puentes += agregados
    except Exception:
        pass  # si la verificación falla, nos quedamos con lo que ya soldamos arriba

    return malla, total_puentes


def unir_y_exportar(piezas, ruta_stl):
    """Une las piezas en un sólido watertight (manifold3d); si la unión
    booleana falla, hace un fallback a concatenate (multi-cuerpo, pero
    igual imprime bien)."""
    try:
        malla = trimesh.boolean.union(piezas, engine="manifold")
        assert malla.is_watertight
    except Exception:
        malla = trimesh.util.concatenate(piezas)
    malla.export(ruta_stl)
    return malla
