#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/modulos.py
------------------
Partido de la placa del neón en módulos verticales cuando el cartel es más
ancho que lo que entra en la Bambu A1. Cada junta interna lleva 2 colas de
milano (macho a la derecha del módulo, hembra a la izquierda del
siguiente) para que los módulos encastren al armar. El corte de las
paredes/canal es limpio (sin cola de milano) — el canal simplemente queda
abierto en la junta, listo para que la tira LED lo cruce al ensamblar.
"""

import math

import numpy as np
from shapely.affinity import translate
from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

DOVETAIL_ANCHO_BASE = 6.0
DOVETAIL_ANCHO_PUNTA = 10.0
DOVETAIL_PROF = 6.0
DOVETAIL_HOLGURA = 0.15
_ALTO_MIN_UNA_COLA = DOVETAIL_ANCHO_PUNTA * 1.2
_ALTO_MIN_DOS_COLAS = DOVETAIL_ANCHO_PUNTA * 2.5


def calcular_cortes(ancho_mm, ancho_max_modulo):
    """Cantidad de módulos y posiciones X ideales de corte (en el mismo
    sistema de coordenadas que la placa) para que cada módulo entre en
    `ancho_max_modulo`. Con 1 módulo devuelve una lista de cortes vacía."""
    n = max(1, math.ceil(ancho_mm / ancho_max_modulo))
    if n == 1:
        return 1, []
    minx = 0.0
    ancho_modulo = ancho_mm / n
    cortes = [minx + i * ancho_modulo for i in range(1, n)]
    return n, cortes


def ajustar_cortes(placa, cortes, ventana_mm, paso_mm=1.0):
    """Corrige cada corte ideal a la posición más cercana (dentro de
    +/- ventana_mm) donde la placa realmente tiene material, para que la
    junta no caiga en un hueco entre letras o palabras. Devuelve
    (cortes_ajustados, avisos)."""
    minx, miny, maxx, maxy = placa.bounds
    ajustados, avisos = [], []
    for x_ideal in cortes:
        encontrado = None
        for delta in np.arange(0, ventana_mm, paso_mm):
            for cand in ({x_ideal - delta, x_ideal + delta} if delta else {x_ideal}):
                linea = LineString([(cand, miny - 5), (cand, maxy + 5)])
                if placa.intersects(linea):
                    encontrado = cand
                    break
            if encontrado is not None:
                break
        if encontrado is None:
            avisos.append(
                f"No encontré material sólido cerca del corte ideal en x≈{x_ideal:.0f}mm; "
                f"revisá esa junta en el preview antes de imprimir."
            )
            encontrado = x_ideal
        ajustados.append(encontrado)
    return ajustados, avisos


def _cola_milano(cx, cy):
    """Trapecio (macho) de la cola de milano, con la base en x=cx y
    apuntando hacia +X."""
    base, punta, prof = DOVETAIL_ANCHO_BASE / 2, DOVETAIL_ANCHO_PUNTA / 2, DOVETAIL_PROF
    return Polygon([(cx, cy - base), (cx, cy + base), (cx + prof, cy + punta), (cx + prof, cy - punta)])


def _rango_y_en_x(geom, x, margen=0.5):
    franja = box(x - margen, -1e6, x + margen, 1e6)
    recorte = geom.intersection(franja)
    if recorte.is_empty:
        return None
    _, miny, _, maxy = recorte.bounds
    return miny, maxy


def _posiciones_cola(geom, x):
    """Devuelve las posiciones Y donde poner cola(s) de milano en la junta
    x, según cuánto material vertical hay ahí (2 colas, 1, o ninguna)."""
    rango = _rango_y_en_x(geom, x)
    if rango is None:
        return []
    miny, maxy = rango
    alto = maxy - miny
    if alto >= _ALTO_MIN_DOS_COLAS:
        return [miny + alto / 3, miny + 2 * alto / 3]
    if alto >= _ALTO_MIN_UNA_COLA:
        return [(miny + maxy) / 2]
    return []


def dividir_en_modulos(placa, paredes, cortes):
    """Corta `placa` (agregando cola de milano en cada junta interna) y
    `paredes` (corte limpio) en tiras verticales según `cortes`. Devuelve
    (lista_de_modulos, avisos); cada módulo es un dict con su geometría 2D
    ya trasladada para empezar en x=0 local."""
    if not cortes:
        return [{"indice": 1, "de": 1, "placa": placa, "paredes": paredes, "ancho_mm": placa.bounds[2] - placa.bounds[0]}], []

    minx, miny, maxx, maxy = placa.bounds
    limites = [minx] + cortes + [maxx]
    n = len(limites) - 1
    modulos, avisos = [], []

    for i in range(n):
        x0, x1 = limites[i], limites[i + 1]
        caja = box(x0, miny - 10, x1, maxy + 10)
        pieza_placa = placa.intersection(caja)
        pieza_paredes = paredes.intersection(caja)

        if i < n - 1:
            posiciones = _posiciones_cola(placa, x1)
            if not posiciones:
                avisos.append(f"Junta {i+1}-{i+2} (x≈{x1:.0f}mm): muy poco material para cola de milano, va a quedar a tope. Reforzala con pegamento.")
            else:
                machos = unary_union([_cola_milano(x1, cy) for cy in posiciones])
                pieza_placa = pieza_placa.union(machos)
        if i > 0:
            posiciones = _posiciones_cola(placa, x0)
            if posiciones:
                hembras = unary_union([_cola_milano(x0, cy).buffer(DOVETAIL_HOLGURA, join_style=2) for cy in posiciones])
                pieza_placa = pieza_placa.difference(hembras)

        modulos.append({
            "indice": i + 1,
            "de": n,
            "placa": translate(pieza_placa, xoff=-x0),
            "paredes": translate(pieza_paredes, xoff=-x0),
            "ancho_mm": x1 - x0,
        })

    return modulos, avisos
