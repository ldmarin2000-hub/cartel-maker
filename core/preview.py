#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/preview.py
-----------------
Genera la vista previa PNG (matplotlib) del cartel: placa, canal del LED,
el recorrido que dibuja el LED encima y, si el cartel se partió en
módulos, las líneas de corte entre ellos.
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def _dibujar_poligono(ax, geom, **kw):
    pols = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
    for pg in pols:
        xs, ys = pg.exterior.xy
        ax.fill(xs, ys, **kw)
        for anillo in pg.interiors:
            xr, yr = anillo.xy
            ax.fill(xr, yr, color="white")


def guardar_preview(ruta_png, placa, canal, lineas, texto, ancho_mm, alto_mm, modo_led, cortes=None, paredes=None):
    """`paredes` es opcional: si se pasa, se dibuja en un gris más claro
    para distinguir la parte que sobresale en relieve (paredes) de la
    placa de fondo plana — útil sobre todo para ver de un vistazo la
    diferencia entre "rect_hundido" (relieve = casi toda la placa) y
    "rect_plano" (relieve = solo las letras)."""
    minx, miny, maxx, maxy = placa.bounds
    w, h = max(maxx - minx, 1), max(maxy - miny, 1)

    fig, ax = plt.subplots(figsize=(10, 10 * h / w + 1))
    _dibujar_poligono(ax, placa, color="#222")
    if paredes is not None:
        _dibujar_poligono(ax, paredes, color="#555")  # relieve (paredes del canal)
    _dibujar_poligono(ax, canal, color="#111")
    for ls in lineas:
        x, y = ls.xy
        ax.plot(x, y, color="#ff2d6f", lw=2)  # recorrido del LED

    if cortes:
        for x in cortes:
            ax.plot([x, x], [miny - 3, maxy + 3], color="#38bdf8", lw=1.5, linestyle="--")

    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(f"{texto}  ·  {ancho_mm:.0f}x{alto_mm:.0f}mm  ·  {modo_led}", color="#333")
    fig.savefig(ruta_png, dpi=120, bbox_inches="tight", facecolor="#f5f5dc")
    plt.close(fig)
