#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/skeleton.py
------------------
Paso 2 del pipeline de neón: máscara -> esqueleto (skimage) -> polilíneas
(grafo de píxeles con networkx, adyacencia 8) -> poda de pelitos cortos.
"""

from collections import Counter

import networkx as nx
import numpy as np
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


def obtener_polilineas(mask, poda_frac):
    """Esqueletiza la máscara y devuelve (polilineas_en_pixeles, alto_px)."""
    skel = skeletonize(mask)
    polys = _podar(_vectorizar(skel), minlen=skel.shape[0] * poda_frac)
    return polys, skel.shape[0]
