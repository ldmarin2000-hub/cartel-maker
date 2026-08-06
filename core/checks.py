#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/checks.py
----------------
Chequeos específicos del pipeline de neón: radio mínimo de curvatura (para
WS2812) y fusión de trazos por el ancho del canal del LED. Devuelven listas
de avisos (strings) en vez de imprimir, para que tanto la CLI como la app
visual decidan cómo mostrarlos.
"""

import numpy as np


def radio_minimo(lineas):
    """Radio de curvatura mínimo del recorrido (circunradio de tripletas
    de puntos consecutivos) y cantidad de tramos con radio < 15 mm."""
    rmin = 1e9
    agudas = 0
    for ls in lineas:
        c = np.array(ls.coords)
        for i in range(1, len(c) - 1):
            a, b, d = c[i - 1], c[i], c[i + 1]
            ab = np.linalg.norm(a - b)
            bc = np.linalg.norm(b - d)
            area = abs((b[0] - a[0]) * (d[1] - a[1]) - (d[0] - a[0]) * (b[1] - a[1])) / 2
            if area > 1e-6:
                ca = np.linalg.norm(d - a)
                r = ab * bc * ca / (4 * area)
                rmin = min(rmin, r)
                if r < 15:
                    agudas += 1
    return rmin, agudas


def chequear_curvas_ws2812(modo_led, lineas):
    """Si el modo es WS2812 (tira rígida de costado), devuelve un aviso si
    hay curvas demasiado cerradas para que la tira las siga sin quebrarse."""
    if modo_led != "ws2812":
        return []
    rmin, agudas = radio_minimo(lineas)
    if agudas > 0:
        return [
            f"WS2812: hay {agudas} curvas con radio < 15 mm (radio mín {rmin:.1f} mm). "
            f"La tira no dobla tan cerrado de costado. Usá neón flex, una fuente más recta, "
            f"o subí el alto del texto."
        ]
    return []


def chequear_fusion_trazos(lineas, canal):
    """Devuelve un aviso si el ancho del canal del LED termina fusionando
    trazos que en el trazado original estaban separados (letras que se
    pegan entre sí)."""
    from shapely.ops import unary_union

    sin_fusionar = unary_union([ls.buffer(0.2) for ls in lineas])
    n_original = len(sin_fusionar.geoms) if sin_fusionar.geom_type == "MultiPolygon" else 1
    n_final = len(canal.geoms) if canal.geom_type == "MultiPolygon" else 1

    if n_final < n_original:
        return [
            f"El ancho del LED fusiona trazos que estaban separados "
            f"({n_original}→{n_final}). Subí el alto del texto o bajá el ancho del LED."
        ]
    return []
