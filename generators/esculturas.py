#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generators/esculturas.py
----------------------------
Escultura/relieve 3D a partir de una imagen — Python puro
(core/heightmap.py: el brillo de cada píxel modula la altura de una
grilla, en vez de sacar solo el contorno plano como hace
core/imagen_import.py). El resultado es un bloque sólido con la foto
"tallada" arriba: watertight, con piso plano y paredes laterales, listo
para imprimir — no una silueta ni una nube de puntos.

Pensado para logos/fotos/dibujos con contraste razonable: una foto muy
plana en brillo (todo gris parejo) da un relieve casi sin relieve.
"""

import io
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

from core import heightmap, pieza

NOMBRE = "Escultura (relieve desde imagen)"
DESCRIPCION = "Imagen -> relieve 3D tallado (el brillo de cada zona modula la altura). STL watertight."

CARPETA_SALIDA = "output"

RESOLUCION_RAPIDA_PX = 45
RESOLUCION_DEFAULT_PX = 120
RESOLUCION_ALTA_PX = 180


def _guardar_preview_sombreado(destino, malla, titulo):
    tris = malla.vertices[malla.faces]
    (minx, miny, minz), (maxx, maxy, maxz) = malla.bounds
    dx, dy, dz = max(maxx - minx, 1), max(maxy - miny, 1), max(maxz - minz, 1)

    fig = plt.figure(figsize=(11, 6))
    vistas = [(55, -80, "3/4"), (20, -90, "De costado (se ve el relieve)")]
    for i, (elev, azim, sub) in enumerate(vistas):
        ax = fig.add_subplot(1, 2, i + 1, projection="3d")
        ax.add_collection3d(Poly3DCollection(tris, facecolor="#c9a876", edgecolor="#00000022", linewidths=0.05))
        ax.set_xlim(minx, maxx)
        ax.set_ylim(miny, maxy)
        ax.set_zlim(minz, maxz)
        ax.view_init(elev=elev, azim=azim)
        ax.set_title(sub, color="#ccc")
        ax.set_box_aspect((dx, dy, dz))
        ax.set_axis_off()
    fig.suptitle(titulo, color="#ccc")
    fig.savefig(destino, dpi=110, facecolor="#1a1a1a")
    plt.close(fig)


def preview_rapido(ruta_imagen, ancho_mm=80.0, alto_mm=80.0,
                    espesor_base_mm=3.0, relieve_mm=8.0,
                    suavizado_px=1.0, oscuro_alto=True):
    """Preview instantáneo — la MISMA técnica que `generar()` pero a
    resolución baja (`RESOLUCION_RAPIDA_PX`, ~0.3-0.5s en vez de varios
    segundos) y renderizada como imagen sombreada 2D (no el visor 3D
    interactivo, que se muestra recién después de generar) — para
    juzgar el relieve mientras se ajustan los parámetros. Devuelve
    png_bytes, o None si no se pudo leer la imagen."""
    if not ruta_imagen or not os.path.exists(ruta_imagen):
        return None
    try:
        malla = heightmap.escultura_desde_imagen(
            ruta_imagen, ancho_mm=ancho_mm, alto_mm=alto_mm,
            espesor_base_mm=espesor_base_mm, relieve_mm=relieve_mm,
            resolucion_px=RESOLUCION_RAPIDA_PX, suavizado_px=suavizado_px,
            oscuro_alto=oscuro_alto,
        )
    except (OSError, ValueError):
        return None

    buf = io.BytesIO()
    _guardar_preview_sombreado(buf, malla, "Vista rápida")
    return buf.getvalue()


def generar(ruta_imagen, ancho_mm=80.0, alto_mm=80.0,
            espesor_base_mm=3.0, relieve_mm=8.0,
            resolucion_px=RESOLUCION_DEFAULT_PX, suavizado_px=1.0,
            oscuro_alto=True,
            carpeta_salida=CARPETA_SALIDA):
    """Arma la escultura/relieve y exporta el STL. Devuelve un dict con
    la ruta, medidas y avisos. No pregunta nada ni imprime nada — así lo
    puede llamar tanto la CLI como la app visual.

    `resolucion_px`: detalle de la grilla (lado más largo) — más alto
    es más fiel a la imagen pero más lento y más pesado el STL.
    `espesor_base_mm`: piso mínimo (para que no se rompa). `relieve_mm`:
    cuánto sobresale la parte más alta por encima del piso.
    `oscuro_alto=True`: las zonas oscuras de la imagen quedan más altas
    (relieve escultórico típico) — en falso, al revés."""
    if not os.path.exists(ruta_imagen):
        raise FileNotFoundError(f"no encuentro la imagen: {ruta_imagen}")
    if espesor_base_mm <= 0:
        raise ValueError("el espesor de la base tiene que ser mayor a 0 (si no, no hay piso)")

    malla = heightmap.escultura_desde_imagen(
        ruta_imagen, ancho_mm=ancho_mm, alto_mm=alto_mm,
        espesor_base_mm=espesor_base_mm, relieve_mm=relieve_mm,
        resolucion_px=resolucion_px, suavizado_px=suavizado_px,
        oscuro_alto=oscuro_alto,
    )

    os.makedirs(carpeta_salida, exist_ok=True)
    base_nombre = pieza.nombre_archivo(os.path.splitext(os.path.basename(ruta_imagen))[0], default="escultura")
    ruta_stl = os.path.join(carpeta_salida, f"escultura_{base_nombre}.stl")
    ruta_png = os.path.join(carpeta_salida, f"escultura_{base_nombre}_preview.png")

    malla.export(ruta_stl)
    _guardar_preview_sombreado(ruta_png, malla, "Escultura")

    ancho_final_mm, alto_final_mm, profundo_final_mm, entra_a1, mensaje_a1 = pieza.chequear_desde_malla(
        malla, nombre="escultura"
    )

    info = [
        f"Relieve de {relieve_mm:.1f}mm sobre una base de {espesor_base_mm:.1f}mm — "
        f"grosor total en la parte más alta: {espesor_base_mm + relieve_mm:.1f}mm."
    ]
    avisos = []
    if not malla.is_watertight:
        avisos.append("No quedó perfectamente watertight, revisala antes de imprimir.")

    return {
        "ruta_stl": ruta_stl,
        "ruta_png": ruta_png,
        "ancho_mm": ancho_final_mm, "alto_mm": alto_final_mm, "profundidad_mm": profundo_final_mm,
        "vertices": len(malla.vertices), "caras": len(malla.faces),
        "watertight": malla.is_watertight,
        "info": info,
        "avisos": avisos,
        "entra_a1": entra_a1,
        "mensaje_a1": mensaje_a1,
    }


# ---------------------------------------------------------------------------
#  Interfaz de consola (menú de main.py)
# ---------------------------------------------------------------------------
def ejecutar():
    from core import ui

    print(f"\n{NOMBRE}")
    print("  Convierte una imagen (foto/logo/dibujo) en un relieve 3D tallado.")

    ruta_imagen = ui.pedir_texto("Ruta a la imagen (PNG/JPG)", "")
    if not ruta_imagen or not os.path.exists(ruta_imagen):
        print(f"  ERROR: no encuentro la imagen: {ruta_imagen!r}")
        return

    ancho_mm = ui.pedir_float("Ancho (mm)", 80.0)
    alto_mm = ui.pedir_float("Alto (mm)", 80.0)
    relieve_mm = ui.pedir_float("Relieve (mm, cuánto sobresale lo más alto)", 8.0)
    espesor_base_mm = ui.pedir_float("Espesor de la base (mm)", 3.0)
    oscuro_alto = ui.pedir_si_no("¿Las zonas OSCURAS quedan más altas?", default=True)

    print(f"\n  » {ruta_imagen}  {ancho_mm:.0f}x{alto_mm:.0f}mm  relieve {relieve_mm:.0f}mm")
    print("  (armando la grilla y la malla, puede tardar unos segundos...)")

    try:
        r = generar(
            ruta_imagen, ancho_mm=ancho_mm, alto_mm=alto_mm,
            espesor_base_mm=espesor_base_mm, relieve_mm=relieve_mm, oscuro_alto=oscuro_alto,
        )
    except (FileNotFoundError, ValueError) as e:
        print(f"  ERROR: {e}")
        return

    print(f"  tamaño ~ {r['ancho_mm']:.0f} x {r['alto_mm']:.0f} x {r['profundidad_mm']:.0f} mm")
    for nota in r["info"]:
        print(f"  · {nota}")
    for aviso in r["avisos"]:
        print(f"  ⚠ {aviso}")
    print(f"  ✓ STL -> {r['ruta_stl']}  ({r['vertices']} vért., watertight={r['watertight']})")
    print(f"  ✓ preview -> {r['ruta_png']}")
    print(f"  {'✓' if r['entra_a1'] else '⚠'} {r['mensaje_a1']}")
    print()
