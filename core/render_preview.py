#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/render_preview.py
-------------------------
Renderizado 2D "tipo estudio fotográfico" de una malla 3D — sombreado
real por cara (dos luces: key cálida + fill fría, no un solo color
plano), sombra de contacto en el piso, y fondo con leve viñeta — mismo
lenguaje visual para el preview de Esculturas (relieve) y Estatua 3D
(TripoSR), en vez de cada uno con su propio criterio de shading.

Importable tanto desde el venv principal (generators/esculturas.py)
como desde el venv de IA aparte (core/triposr_worker.py corre por
subprocess con cwd en la raíz del proyecto, así que `core` es
importable igual — matplotlib ya es dependencia de ambos)."""

import numpy as np


def _normalizar(v):
    v = np.array(v, dtype=np.float64)
    return v / max(np.linalg.norm(v), 1e-9)


# Dos luces fijas (en el espacio de la malla, no de cámara — así el
# sombreado no rota con la vista, como una pieza iluminada de verdad
# en una mesa): key cálida desde arriba-adelante-costado, fill fría y
# tenue desde el lado opuesto (rellena las sombras sin aplanarlas del
# todo, técnica clásica de 2 luces).
_LUZ_KEY = _normalizar([0.45, -0.55, 0.85])
_LUZ_FILL = _normalizar([-0.5, 0.35, 0.4])
_TINTE_KEY = np.array([1.05, 1.0, 0.90])
_TINTE_FILL = np.array([0.86, 0.92, 1.08])


def colores_por_cara(face_normals, base_rgb):
    """Color final por cara (Nx3, en [0,1]) a partir de sus normales —
    2 luces + piso ambient, con un tinte cálido/frío sutil según qué
    luz domina en cada cara (no un multiplicador de gris plano)."""
    base_rgb = np.array(base_rgb, dtype=np.float64)
    key = np.clip(face_normals @ _LUZ_KEY, 0, 1)
    fill = np.clip(face_normals @ _LUZ_FILL, 0, 1)
    intensidad = 0.22 + 0.78 * key + 0.22 * fill
    intensidad = np.clip(intensidad, 0.0, 1.22)

    peso_fill_rel = (0.22 * fill) / np.maximum(intensidad, 1e-6)
    peso_fill_rel = np.clip(peso_fill_rel, 0, 1)[:, np.newaxis]
    tinte = _TINTE_KEY * (1 - peso_fill_rel) + _TINTE_FILL * peso_fill_rel

    return np.clip(base_rgb[np.newaxis, :] * intensidad[:, np.newaxis] * tinte, 0, 1)


def _agregar_sombra_contacto(ax, cx, cy, z, radio):
    """Sombra de contacto falsa (3 elipses concéntricas semitransparentes
    en el piso, radio decreciente) — ancla visualmente la pieza al plano
    en vez de quedar "flotando" sobre un fondo liso."""
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    theta = np.linspace(0, 2 * np.pi, 40)
    for factor, alpha in ((1.35, 0.10), (1.0, 0.16), (0.65, 0.22)):
        r = radio * factor
        xs = cx + r * np.cos(theta)
        ys = cy + r * np.sin(theta) * 0.55  # elipse achatada, look de sombra proyectada
        verts = [list(zip(xs, ys, [z] * len(theta)))]
        sombra = Poly3DCollection(verts, facecolor="#000000", edgecolor="none", alpha=alpha)
        ax.add_collection3d(sombra)


def render_multivista(destino, malla, titulo, vistas, base_rgb=(0.83, 0.70, 0.52),
                       fondo_fig="#0d0d0f", fondo_ejes="#151517", dpi=130, max_tris=14000):
    """Guarda un preview PNG multi-panel de `malla` — sombreado real,
    sombra de contacto, fondo con viñeta sutil. `vistas`: lista de
    (elev, azim, subtítulo) — cada generador pasa sus propios ángulos
    ya calibrados para su convención de ejes (relieve vs. figura 3D),
    esta función solo se encarga de que se vea bien."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    tris_full = malla.vertices[malla.faces]
    if len(tris_full) > max_tris:
        step = len(tris_full) // max_tris
        indices = np.arange(0, len(tris_full), step)
        tris = tris_full[indices]
        normales = malla.face_normals[indices]
    else:
        tris = tris_full
        normales = malla.face_normals

    colores = colores_por_cara(normales, base_rgb)

    (minx, miny, minz), (maxx, maxy, maxz) = malla.bounds
    dx, dy, dz = max(maxx - minx, 1e-6), max(maxy - miny, 1e-6), max(maxz - minz, 1e-6)
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    radio_sombra = max(dx, dy) / 2

    n_vistas = len(vistas)
    fig = plt.figure(figsize=(5.6 * n_vistas, 5.6), facecolor=fondo_fig)

    for i, (elev, azim, sub) in enumerate(vistas):
        ax = fig.add_subplot(1, n_vistas, i + 1, projection="3d")
        _agregar_sombra_contacto(ax, cx, cy, minz, radio_sombra)

        poly = Poly3DCollection(tris, facecolor=colores, edgecolor="#00000018", linewidths=0.06)
        ax.add_collection3d(poly)

        ax.set_xlim(minx, maxx)
        ax.set_ylim(miny, maxy)
        ax.set_zlim(minz, maxz)
        ax.view_init(elev=elev, azim=azim)
        ax.set_title(sub, color="#d8d8d8", fontsize=10, pad=2)
        ax.set_box_aspect((dx, dy, dz))
        ax.set_axis_off()
        ax.set_facecolor(fondo_ejes)
        for pane in (ax.xaxis.pane, ax.yaxis.pane, ax.zaxis.pane):
            pane.set_alpha(0.0)

    fig.suptitle(titulo, color="#e8e8e8", fontsize=13, y=0.98)
    fig.savefig(destino, dpi=dpi, facecolor=fondo_fig, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
