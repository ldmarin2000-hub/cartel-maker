#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generators/caja_luz.py
--------------------------
Generador de "caja de luz": una palabra (una o más letras, no una sola
inicial como generators/letras.py) convertida en UNA pieza hueca —
paredes de tu grosor alrededor de cada trazo, cara de adelante fina para
que la luz del LED se difunda pareja. Si la palabra tiene letras sueltas
(que no se tocan entre sí, como la "I" de "ISKRA"), se sueldan con
puentes finos (core/geometry.py::conectar_componentes, ya usado por el
neón) para que salga como una sola pieza imprimible.

También exporta una TAPA aparte (mismo contorno, sólida y fina) para
cerrar el hueco después de meter el LED, con un agujerito para sacar el
cable de alimentación — mismo mecanismo que generators/letras.py (que a
su vez comparte con este la cáscara/tapa/agujero, ver
core/carcasa_hueca.py: a esa lógica no le importa si el polígono es una
sola letra o una palabra entera).
"""

import io
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import trimesh
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

from core import bambu_a1, carcasa_hueca, geometry, pieza, texto2d

NOMBRE = "Caja de luz (palabra hueca)"
DESCRIPCION = "Una palabra -> caja hueca con paredes de tu grosor, con tapa y agujero para el cable. STL + preview."

CARPETA_SALIDA = "output"


def preview_rapido(texto, ruta_ttf, alto_mm=100, raster_px=250):
    """Preview 2D instantáneo — solo el polígono relleno de la palabra,
    SIN el hueco/cáscara/booleanas 3D (que tarda más). Devuelve
    (png_bytes, ancho_mm, alto_mm) o (None, 0, 0)."""
    if not os.path.exists(ruta_ttf) or not texto.strip():
        return None, 0, 0
    poly, ancho_mm = texto2d.texto_a_poligono(texto, ruta_ttf, alto_mm, raster_px)
    if poly is None:
        return None, 0, 0

    minx, miny, maxx, maxy = poly.bounds
    w, h = max(maxx - minx, 1), max(maxy - miny, 1)

    fig, ax = plt.subplots(figsize=(6, 6 * h / w + 1))
    pols = list(poly.geoms) if poly.geom_type == "MultiPolygon" else [poly]
    for pg in pols:
        xs, ys = pg.exterior.xy
        ax.fill(xs, ys, color="#ff2d6f")
        for anillo in pg.interiors:
            xr, yr = anillo.xy
            ax.fill(xr, yr, color="#1a1a1a")
    ax.set_xlim(minx - 2, maxx + 2)
    ax.set_ylim(miny - 2, maxy + 2)
    ax.set_aspect("equal")
    ax.axis("off")

    buf = io.BytesIO()
    fig.savefig(buf, dpi=120, bbox_inches="tight", facecolor="#1a1a1a")
    plt.close(fig)
    return buf.getvalue(), ancho_mm, h


def _guardar_preview(ruta_png, malla, titulo):
    tris = malla.vertices[malla.faces]
    (minx, miny, minz), (maxx, maxy, maxz) = malla.bounds
    dx, dy, dz = max(maxx - minx, 1), max(maxy - miny, 1), max(maxz - minz, 1)

    fig = plt.figure(figsize=(11, 6))
    vistas = [(90, -90, "De frente (encendida)"), (20, -100, "De costado (se ve el hueco)")]
    for i, (elev, azim, sub) in enumerate(vistas):
        ax = fig.add_subplot(1, 2, i + 1, projection="3d")
        ax.add_collection3d(Poly3DCollection(tris, facecolor="#fff2c8", edgecolor="#c9a94f", linewidths=0.1))
        ax.set_xlim(minx, maxx)
        ax.set_ylim(miny, maxy)
        ax.set_zlim(minz, maxz)
        ax.view_init(elev=elev, azim=azim)
        ax.set_title(sub)
        ax.set_box_aspect((dx, dy, dz))
        ax.set_axis_off()
    fig.suptitle(titulo)
    fig.savefig(ruta_png, dpi=110, facecolor="#222")
    plt.close(fig)


def generar(texto, ruta_ttf, alto_mm=100, profundidad_mm=30, espesor_pared_mm=2.5,
            agregar_tapa=True, tapa_espesor_mm=3.0, agujero_cable_diam_mm=6.0, agujero_cable_lado="atras",
            ancho_puente_mm=4.0, raster_px=500, carpeta_salida=CARPETA_SALIDA):
    """Arma la caja de luz y exporta el/los STL. Devuelve un dict con las
    rutas, medidas y avisos. No pregunta nada ni imprime nada — así lo
    puede llamar tanto la CLI como la app visual.

    `profundidad_mm`: cuánto sobresale la caja hacia atrás (ahí adentro va
    la tira LED). `espesor_pared_mm`: grosor de la cara de adelante y las
    paredes — más fino deja pasar más luz pero es más frágil.
    `ancho_puente_mm`: ancho de los puentes que sueldan letras sueltas
    (como la "I" de una palabra) en una sola pieza imprimible.

    `agregar_tapa`: exporta una tapa aparte (mismo contorno achicado con
    holgura) para cerrar el hueco después de meter el LED — encastra en
    un REBAJE de la propia carcasa que la frena (no sigue de largo hacia
    el hueco principal), ver core/carcasa_hueca.py. El agujero para el
    cable (`agujero_cable_diam_mm`, 0 = sin agujero) va en la CARCASA, no
    en la tapa — `agujero_cable_lado` elige por dónde: "atras" (por el
    canto de atrás, el rebaje donde apoya la tapa), "arriba", "abajo",
    "izquierda" o "derecha" (por la pared lateral del lado elegido)."""
    if not os.path.exists(ruta_ttf):
        raise FileNotFoundError(f"no encuentro la fuente: {ruta_ttf}")
    if not texto.strip():
        raise ValueError("escribí al menos una letra")

    poly, ancho_texto_mm = texto2d.texto_a_poligono(texto, ruta_ttf, alto_mm, raster_px)
    if poly is None:
        raise ValueError("no se pudo extraer el texto (probá otra fuente)")

    info = []
    if poly.geom_type == "MultiPolygon" and len(poly.geoms) > 1:
        poly, n_puentes = geometry.conectar_componentes(poly, ancho_puente_mm, espesor_pared_mm)
        if n_puentes:
            info.append(f"Se agregaron {n_puentes} puente(s) para unir las letras sueltas en una sola pieza imprimible.")

    carcasa, quedo_hueca, avisos_carcasa = carcasa_hueca.armar_carcasa_hueca(
        poly, profundidad_mm, espesor_pared_mm, tapa_espesor_mm
    )
    info += avisos_carcasa
    if not quedo_hueca:
        info.append(
            "La palabra quedó maciza (ningún trazo es más ancho que 2x el espesor de pared) — "
            "probá una fuente más gruesa, más grande, o bajar el espesor de pared."
        )
    elif agregar_tapa and agujero_cable_diam_mm > 0:
        agujero = carcasa_hueca.armar_agujero_pared(
            poly, espesor_pared_mm, agujero_cable_diam_mm, agujero_cable_lado, profundidad_mm, tapa_espesor_mm
        )
        if agujero is None:
            info.append(
                f"No pude ubicar el agujero del cable \"{agujero_cable_lado}\" (palabra muy angosta "
                f"ahí, o la pared queda muy fina para el rebaje) — probá otro lado, o hacelo a "
                f"mano con una mecha."
            )
        else:
            carcasa = trimesh.boolean.difference([carcasa, agujero], engine="manifold")
            info.append(
                f"Agujero de {agujero_cable_diam_mm:.0f}mm para el cable en la pared "
                f"({agujero_cable_lado}) — la tapa queda lisa, solo para cerrar."
            )

    os.makedirs(carpeta_salida, exist_ok=True)
    base_nombre = pieza.nombre_archivo(texto, default="palabra")
    ruta_stl = os.path.join(carpeta_salida, f"cajaluz_{base_nombre}.stl")
    ruta_png = os.path.join(carpeta_salida, f"cajaluz_{base_nombre}_preview.png")

    carcasa.export(ruta_stl)
    _guardar_preview(ruta_png, carcasa, f"Caja de luz {texto!r}")

    pieza_tapa = None
    if agregar_tapa:
        malla_tapa = carcasa_hueca.armar_tapa(poly, tapa_espesor_mm, espesor_pared_mm)
        ruta_tapa = os.path.join(carpeta_salida, f"cajaluz_{base_nombre}_tapa.stl")
        malla_tapa.export(ruta_tapa)
        pieza_tapa = {
            "ruta_stl": ruta_tapa,
            "vertices": len(malla_tapa.vertices),
            "watertight": malla_tapa.is_watertight,
        }
        info.append(
            "Tapa agregada (STL aparte, 1mm de holgura) para cerrar el hueco después de meter "
            "el LED — encastra en el rebaje de la carcasa."
        )

    minx, miny, minz = carcasa.bounds[0]
    maxx, maxy, maxz = carcasa.bounds[1]
    ancho_mm, alto_total_mm, profundo_total_mm = maxx - minx, maxy - miny, maxz - minz
    entra_a1, mensaje_a1 = bambu_a1.chequear_tamano(ancho_mm, alto_total_mm, profundo_total_mm, nombre="caja de luz")

    return {
        "texto": texto,
        "ruta_png": ruta_png,
        "ruta_stl": ruta_stl,
        "pieza_tapa": pieza_tapa,
        "ancho_mm": ancho_mm,
        "alto_mm": alto_total_mm,
        "profundidad_mm": profundo_total_mm,
        "vertices": len(carcasa.vertices),
        "watertight": carcasa.is_watertight,
        "info": info,
        "avisos": [],
        "entra_a1": entra_a1,
        "mensaje_a1": mensaje_a1,
    }


# ---------------------------------------------------------------------------
#  Interfaz de consola (menú de main.py)
# ---------------------------------------------------------------------------
def ejecutar():
    from core import fuentes, ui

    print(f"\n{NOMBRE}")
    print("  Una palabra hueca, con paredes de tu grosor, con tapa aparte y agujero para el cable.")

    texto = ui.pedir_texto("Palabra", "HOLA")
    nombre_fuente = ui.pedir_texto("Fuente", "Comic Sans MS")
    ruta_ttf = nombre_fuente if os.path.exists(nombre_fuente) else fuentes.buscar_por_nombre(nombre_fuente)
    ruta_ttf = ruta_ttf or nombre_fuente
    alto_mm = ui.pedir_float("Alto de la palabra (mm)", 100)
    profundidad_mm = ui.pedir_float("Profundidad de la caja (mm)", 30)
    espesor_pared_mm = ui.pedir_float("Grosor de las paredes (mm)", 2.5)
    agujero_cable_lado = ui.pedir_opcion(
        "Lado del agujero para el cable", ["atras", "arriba", "abajo", "izquierda", "derecha"], "atras",
    )

    print(f"\n  » Palabra: {texto!r}  fuente: {ruta_ttf}")
    print("  (armando la geometría, puede tardar unos segundos...)")

    try:
        r = generar(
            texto, ruta_ttf, alto_mm=alto_mm, profundidad_mm=profundidad_mm, espesor_pared_mm=espesor_pared_mm,
            agujero_cable_lado=agujero_cable_lado,
        )
    except (FileNotFoundError, ValueError) as e:
        print(f"  ERROR: {e}")
        return

    print(f"  tamaño ~ {r['ancho_mm']:.0f} x {r['alto_mm']:.0f} x {r['profundidad_mm']:.0f} mm")
    for nota in r["info"]:
        print(f"  · {nota}")
    print(f"  ✓ STL -> {r['ruta_stl']}  ({r['vertices']} vért., watertight={r['watertight']})")
    if r["pieza_tapa"]:
        print(f"  ✓ STL (tapa) -> {r['pieza_tapa']['ruta_stl']}")
    print(f"  ✓ preview -> {r['ruta_png']}")
    print(f"  {'✓' if r['entra_a1'] else '⚠'} {r['mensaje_a1']}")
    print()
