#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generators/letras.py
------------------------
Generador de letras iluminadas de pie (una letra/inicial grande, hueca
por dentro para meterle una luz LED — el hueco queda abierto atrás para
insertarla/cambiar pilas —, con la cara de adelante fina para que la luz
se vea a través). Python puro: reutiliza core/texto2d.py (letra como
polígono relleno), core/mesh3d.py (extrusión/booleanas), y el mismo
soporte de escritorio que ya usa el neón (core/geometry.py::
agregar_pata_escritorio + core/soporte.py) para las letras que no se
sostienen solas paradas.

También exporta una TAPA aparte (mismo contorno que la letra, sólida y
fina) para cerrar el hueco después de meter el LED, con un agujerito
para sacar el cable de alimentación.

Primera versión: letra + soporte + tapa con agujero de cable. El nombre
en cursiva pegado abajo y los dibujitos decorativos (referencia del
usuario) quedan para una segunda vuelta.
"""

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import trimesh
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from shapely.geometry import Point

from core import bambu_a1, geometry, mesh3d, soporte, texto2d

NOMBRE = "Letra iluminada de pie"
DESCRIPCION = "Letra/inicial grande, hueca por dentro para una luz LED — con soporte de escritorio si hace falta."

CARPETA_SALIDA = "output"


def _nombre_archivo(texto):
    limpio = "".join(c if c.isalnum() else "_" for c in texto).strip("_")
    return limpio or "letra"


def _armar_carcasa_hueca(poly, profundidad_mm, espesor_pared_mm):
    """Arma la letra como cáscara hueca: cara de adelante sólida y fina
    (`espesor_pared_mm`, para que pase la luz), paredes laterales del
    mismo espesor, atrás ABIERTO (para meter el LED/pila y poder
    cambiarla) — no un hueco "cerrado" con piso al final. Si algún trazo
    de la letra es más angosto que 2x el espesor de pared, esa parte
    queda maciza (no hay dónde hacer hueco) — no es un error."""
    piezas_afuera = mesh3d.piezas_desde_geom(poly, profundidad_mm)
    afuera = trimesh.util.concatenate(piezas_afuera) if len(piezas_afuera) > 1 else piezas_afuera[0]

    # join_style=1 (redondeado): con mitre (2) los ángulos agudos de letras como
    # la "M" generaban geometría degenerada al extruir ("Not all meshes are volumes!").
    hueco_poly = poly.buffer(-espesor_pared_mm, join_style=1)
    if hueco_poly.is_empty or hueco_poly.area < 1:
        return afuera, False  # letra/trazo muy angosto para hacerle hueco -> queda maciza

    sobresalto_mm = 5  # que el hueco sobrepase el fondo, para que quede ABIERTO atrás, no un piso ciego
    piezas_hueco = mesh3d.piezas_desde_geom(
        hueco_poly, profundidad_mm - espesor_pared_mm + sobresalto_mm, z=espesor_pared_mm
    )
    hueco = trimesh.util.concatenate(piezas_hueco) if len(piezas_hueco) > 1 else piezas_hueco[0]

    carcasa = trimesh.boolean.difference([afuera, hueco], engine="manifold")
    return carcasa, True


def _punto_agujero_cable(poly, margen_mm=6):
    """Busca un punto cerca del borde inferior de `poly`, centrado en X,
    que caiga en material SÓLIDO (no en un hueco de la letra, como el
    interior de una "O") — ahí va el agujerito del cable. Devuelve
    (x, y) o None si no encontró ningún punto sólido cerca del borde."""
    minx, miny, maxx, maxy = poly.bounds
    cx = (minx + maxx) / 2
    for dx in (0, 6, -6, 12, -12, 18, -18, 24, -24, 30, -30):
        for dy in (margen_mm, margen_mm + 4, margen_mm + 8, margen_mm + 12):
            p = Point(cx + dx, miny + dy)
            if poly.contains(p):
                return (cx + dx, miny + dy)
    return None


def _armar_tapa(poly, espesor_mm, agujero_cable_diam_mm):
    """Tapa: mismo contorno que la letra (sólida, sin hueco), fina, para
    cerrar el hueco por atrás después de meter el LED — con un
    agujerito cerca del borde inferior para sacar el cable. Devuelve
    (tapa, tiene_agujero)."""
    piezas = mesh3d.piezas_desde_geom(poly, espesor_mm)
    tapa = trimesh.util.concatenate(piezas) if len(piezas) > 1 else piezas[0]

    if agujero_cable_diam_mm <= 0:
        return tapa, False
    punto = _punto_agujero_cable(poly)
    if punto is None:
        return tapa, False  # letra muy angosta/compleja, no encontramos un lugar sólido -> sin agujero

    cx, cy = punto
    agujero = trimesh.creation.cylinder(radius=agujero_cable_diam_mm / 2, height=espesor_mm + 4, sections=32)
    agujero.apply_translation([cx, cy, espesor_mm / 2])
    tapa = trimesh.boolean.difference([tapa, agujero], engine="manifold")
    return tapa, True


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


def generar(texto, ruta_ttf, alto_mm=150, profundidad_mm=35, espesor_pared_mm=2.5,
            agregar_tapa=True, tapa_espesor_mm=3.0, agujero_cable_diam_mm=6.0,
            agregar_soporte=True, ancho_pata_mm=40, alto_pata_mm=15,
            raster_px=600, carpeta_salida=CARPETA_SALIDA):
    """Arma la letra iluminada (hueca, con soporte de escritorio si hace
    falta) y exporta el/los STL. Devuelve un dict con las rutas, medidas
    y avisos. No pregunta nada ni imprime nada — así lo puede llamar
    tanto la CLI como la app visual.

    `profundidad_mm`: cuánto sobresale la letra de la mesa (ahí adentro
    va la luz). `espesor_pared_mm`: grosor de la cara de adelante y las
    paredes — más fino deja pasar más luz pero es más frágil.
    `agregar_tapa`: exporta una tapa aparte (mismo contorno, sólida) para
    cerrar el hueco después de meter el LED, con un agujerito de
    `agujero_cable_diam_mm` cerca del borde inferior para el cable (0
    para no hacer agujero)."""
    if not os.path.exists(ruta_ttf):
        raise FileNotFoundError(f"no encuentro la fuente: {ruta_ttf}")
    if not texto.strip():
        raise ValueError("escribí al menos una letra")

    poly, ancho_texto_mm = texto2d.texto_a_poligono(texto, ruta_ttf, alto_mm, raster_px)
    if poly is None:
        raise ValueError("no se pudo extraer la letra (probá otra fuente)")

    info = []
    carcasa, quedo_hueca = _armar_carcasa_hueca(poly, profundidad_mm, espesor_pared_mm)
    if not quedo_hueca:
        info.append(
            "La letra quedó maciza (ningún trazo es más ancho que 2x el espesor de pared) — "
            "probá una letra más grande, una fuente más gruesa, o bajar el espesor de pared."
        )

    pieza_soporte = None
    if agregar_soporte:
        poly_con_pata, ancho_pata_mm = geometry.agregar_pata_escritorio(
            poly, ancho_pata_mm=ancho_pata_mm, alto_pata_mm=alto_pata_mm
        )
        pata_poly = poly_con_pata.difference(poly)
        piezas_pata = mesh3d.piezas_desde_geom(pata_poly, profundidad_mm)
        if piezas_pata:
            pata_solida = trimesh.util.concatenate(piezas_pata) if len(piezas_pata) > 1 else piezas_pata[0]
            carcasa = trimesh.boolean.union([carcasa, pata_solida], engine="manifold")
        info.append(
            f"Pata de {ancho_pata_mm:.0f}mm agregada abajo (sólida, sin hueco) para encastrar en "
            f"la base de escritorio (STL aparte) — para las letras que no se paran solas."
        )

    os.makedirs(carpeta_salida, exist_ok=True)
    base_nombre = _nombre_archivo(texto)
    ruta_stl = os.path.join(carpeta_salida, f"letra_{base_nombre}.stl")
    ruta_png = os.path.join(carpeta_salida, f"letra_{base_nombre}_preview.png")

    carcasa.export(ruta_stl)
    _guardar_preview(ruta_png, carcasa, f"Letra {texto!r}")

    if agregar_soporte:
        ruta_soporte = os.path.join(carpeta_salida, f"letra_{base_nombre}_base_escritorio.stl")
        malla_soporte = soporte.generar_base(ancho_pata_mm, profundidad_mm, alto_pata_mm)
        malla_soporte.export(ruta_soporte)
        pieza_soporte = {
            "ruta_stl": ruta_soporte,
            "vertices": len(malla_soporte.vertices),
            "watertight": malla_soporte.is_watertight,
        }

    pieza_tapa = None
    if agregar_tapa:
        malla_tapa, tiene_agujero = _armar_tapa(poly, tapa_espesor_mm, agujero_cable_diam_mm)
        ruta_tapa = os.path.join(carpeta_salida, f"letra_{base_nombre}_tapa.stl")
        malla_tapa.export(ruta_tapa)
        pieza_tapa = {
            "ruta_stl": ruta_tapa,
            "vertices": len(malla_tapa.vertices),
            "watertight": malla_tapa.is_watertight,
        }
        if tiene_agujero:
            info.append(
                f"Tapa agregada (STL aparte) para cerrar el hueco después de meter el LED, con "
                f"agujerito de {agujero_cable_diam_mm:.0f}mm cerca del borde inferior para el cable."
            )
        else:
            info.append(
                "Tapa agregada (STL aparte) para cerrar el hueco después de meter el LED — no le "
                "pude poner el agujero del cable (no encontré un lugar sólido cerca del borde); "
                "hacelo a mano con una mecha."
            )

    minx, miny, minz = carcasa.bounds[0]
    maxx, maxy, maxz = carcasa.bounds[1]
    ancho_mm, alto_total_mm, profundo_total_mm = maxx - minx, maxy - miny, maxz - minz
    entra_a1, mensaje_a1 = bambu_a1.chequear_tamano(ancho_mm, alto_total_mm, profundo_total_mm, nombre="letra")

    return {
        "texto": texto,
        "ruta_png": ruta_png,
        "ruta_stl": ruta_stl,
        "pieza_soporte": pieza_soporte,
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
    print("  Una letra/inicial grande, hueca por dentro para meterle una luz LED.")

    texto = ui.pedir_texto("Letra(s)", "B")
    nombre_fuente = ui.pedir_texto("Fuente", "Comic Sans MS")
    ruta_ttf = nombre_fuente if os.path.exists(nombre_fuente) else fuentes.buscar_por_nombre(nombre_fuente)
    ruta_ttf = ruta_ttf or nombre_fuente
    agregar_soporte = ui.pedir_si_no("¿Agregar soporte de escritorio (para que se pare sola)?", default=True)

    print(f"\n  » Letra: {texto!r}  fuente: {ruta_ttf}  soporte: {agregar_soporte}")
    print("  (armando la geometría, puede tardar unos segundos...)")

    try:
        r = generar(texto, ruta_ttf, agregar_soporte=agregar_soporte)
    except (FileNotFoundError, ValueError) as e:
        print(f"  ERROR: {e}")
        return

    print(f"  tamaño ~ {r['ancho_mm']:.0f} x {r['alto_mm']:.0f} x {r['profundidad_mm']:.0f} mm")
    for nota in r["info"]:
        print(f"  · {nota}")
    print(f"  ✓ STL -> {r['ruta_stl']}  ({r['vertices']} vért., watertight={r['watertight']})")
    if r["pieza_soporte"]:
        print(f"  ✓ STL (base escritorio) -> {r['pieza_soporte']['ruta_stl']}")
    if r["pieza_tapa"]:
        print(f"  ✓ STL (tapa) -> {r['pieza_tapa']['ruta_stl']}")
    print(f"  ✓ preview -> {r['ruta_png']}")
    print(f"  {'✓' if r['entra_a1'] else '⚠'} {r['mensaje_a1']}")
    print()
