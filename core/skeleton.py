#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/skeleton.py
------------------
Paso 2 del pipeline de neón: máscara -> esqueleto (skimage) -> polilíneas
(grafo de píxeles con networkx, adyacencia 8) -> poda de pelitos cortos ->
circulitos para las manchas sólidas que no dejan esqueleto (el punto de
una "i", el ojo/nariz de un dibujo trazado).
"""

from collections import Counter

import networkx as nx
import numpy as np
from scipy.ndimage import distance_transform_edt
from skimage.measure import label
from skimage.morphology import skeletonize

_VECINOS_8 = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def _vectorizar(skel):
    """Arma un grafo de píxeles del esqueleto y lo recorre en tramos entre
    nodos de grado != 2 (extremos/cruces), devolviendo una lista de
    polilíneas (listas de coordenadas de píxel)."""
    pts = set(map(tuple, np.argwhere(skel)))
    G = nx.Graph()
    G.add_nodes_from(pts)
    for (r, c) in pts:
        for dr, dc in _VECINOS_8:
            n = (r + dr, c + dc)
            if n in pts:
                G.add_edge((r, c), n)

    polys = []
    visited = set()

    def caminar(a, b):
        path = [a, b]
        visited.add(frozenset((a, b)))
        while G.degree(b) == 2:
            siguientes = [n for n in G.neighbors(b) if n != a and frozenset((b, n)) not in visited]
            if not siguientes:
                break
            a, b = b, siguientes[0]
            visited.add(frozenset((a, b)))
            path.append(b)
        return path

    for u in [n for n in G.nodes if G.degree(n) != 2]:
        for v in list(G.neighbors(u)):
            if frozenset((u, v)) not in visited:
                polys.append(caminar(u, v))

    for comp in nx.connected_components(G):  # lazos puros (o, e, 0...)
        if all(G.degree(n) == 2 for n in comp):
            s = next(iter(comp))
            vecinos = list(G.neighbors(s))
            if vecinos and frozenset((s, vecinos[0])) not in visited:
                polys.append(caminar(s, vecinos[0]))

    return polys


def _largo(p):
    a = np.array(p, float)
    return float(np.hypot(*(a[1:] - a[:-1]).T).sum()) if len(p) > 1 else 0.0


def _podar(polys, minlen):
    """Elimina recursivamente los tramos sueltos (un solo extremo libre)
    más cortos que `minlen` — los "pelitos" que deja el esqueletizado."""
    changed = True
    while changed:
        changed = False
        cnt = Counter()
        for p in polys:
            cnt[p[0]] += 1
            cnt[p[-1]] += 1
        keep = []
        for p in polys:
            if (cnt[p[0]] == 1 or cnt[p[-1]] == 1) and _largo(p) < minlen:
                changed = True
                continue
            keep.append(p)
        polys = keep
    return polys


def _manchas_sin_esqueleto(mask, polys, radio_min_px=1.5, n_puntos=16):
    """Una mancha SÓLIDA (un ojo, la nariz, el punto de una "i") no tiene
    un "medio del camino" que trazar -- su esqueleto se reduce a un
    amontonamiento de píxeles sueltos de un par de píxeles de largo, que
    ni siquiera son "puntas sueltas" para `_podar` (están todos pegados
    entre sí en un amontonamiento, no cuelgan de un trazo real) así que
    sobreviven aunque no signifiquen nada. Se los distingue de un trazo
    de verdad (aunque sea corto) comparando el largo total del esqueleto
    contra el radio inscripto de la mancha: un trazo real siempre mide
    bastante más que su propio ancho, un amontonamiento de ruido no.

    Para cada componente conexa de `mask` sin esqueleto real, arma un
    circulito centrado en el punto más "adentro" (el que queda más lejos
    de cualquier borde, vía transformada de distancia) con radio achicado
    para que el canal LED final quede adentro de la tinta original.
    Devuelve (polys_sin_el_ruido_descartado, circulos_nuevos)."""
    etiquetas, n = label(mask, connectivity=2, return_num=True)
    if n == 0:
        return polys, []

    et_por_poly = []
    largo_por_etiqueta = Counter()
    for p in polys:
        r0, c0 = p[0]
        et = etiquetas[int(round(r0)), int(round(c0))] if mask[int(round(r0)), int(round(c0))] else 0
        et_por_poly.append(et)
        if et:
            largo_por_etiqueta[et] += _largo(p)

    dist = distance_transform_edt(mask)
    circulos = []
    descartar = set()
    for et in range(1, n + 1):
        zona = etiquetas == et
        r0, c0 = np.unravel_index(np.argmax(np.where(zona, dist, -1)), dist.shape)
        radio_inscripto = dist[r0, c0]
        if largo_por_etiqueta.get(et, 0.0) > radio_inscripto:
            continue  # ya tiene un trazo de verdad, no es una mancha ciega
        descartar.add(et)
        radio = radio_inscripto * 0.6
        if radio < radio_min_px:
            continue
        angulos = np.linspace(0, 2 * np.pi, n_puntos)
        circulos.append([(r0 + radio * np.sin(t), c0 + radio * np.cos(t)) for t in angulos])

    polys_limpios = [p for p, et in zip(polys, et_por_poly) if et not in descartar]
    return polys_limpios, circulos


def obtener_polilineas(mask, poda_frac):
    """Esqueletiza la máscara y devuelve (polilineas_en_pixeles, alto_px)."""
    skel = skeletonize(mask)
    polys = _podar(_vectorizar(skel), minlen=skel.shape[0] * poda_frac)
    polys, circulos = _manchas_sin_esqueleto(mask, polys)
    return polys + circulos, skel.shape[0]
