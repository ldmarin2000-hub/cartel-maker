#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generators/llavero.py
-------------------------
Generador de llaveros paramétricos — en Python puro (shapely + trimesh),
sin depender de OpenSCAD. Arma el texto como polígono relleno
(core/texto2d.py), le agrega una decoración (core/decoraciones.py) y un
borde con aros para colgar, y extruye/exporta con core/mesh3d.py — el
mismo pipeline que ya usa el generador de neón.
"""

import io
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from shapely.affinity import translate
from shapely.geometry import LineString, Point
from shapely.ops import unary_union

from core import bambu_a1, colores, decoraciones, fuentes, mesh3d, pieza, texto2d, ui

NOMBRE = "Llavero"
DESCRIPCION = "Llavero paramétrico (texto + decoración + aro), en Python puro. STL por color."

CARPETA_SALIDA = "output"

COLORES = colores.NOMBRES
DECORACIONES = list(decoraciones.NOMBRES_VALIDOS)
LADOS_DECO = ["izquierda", "derecha", "arriba"]
LADOS_ARO = ["izquierda", "derecha", "ambos", "ninguno"]


def _posicion_decoracion(minx, maxx, maxy, cy, decoracion_lado, decoracion_tam):
    if decoracion_lado == "izquierda":
        return minx - decoracion_tam - 3, cy
    elif decoracion_lado == "arriba":
        return (minx + maxx) / 2, maxy + decoracion_tam * 0.4
    else:  # derecha
        return maxx + decoracion_tam + 1, cy


def _armar_geometria(nombre, ruta_ttf, alto_mm, decoracion, decoracion_lado, decoracion_tam,
                      deco_x, deco_y, aro_lado, aro_r, borde_mm, raster_px,
                      decoracion_svg=None, decoracion_emoji=None):
    """Arma la geometría 2D del llavero (contenido = texto+deco, y base =
    contenido con borde + orejas de aro). Devuelve (contenido, base,
    ancho_mm, alto_mm_real). Si `decoracion_svg` (ruta a un .svg) o
    `decoracion_emoji` (un carácter, ej. "✈") vienen seteados, se usa esa
    forma en vez de una de la lista `decoracion` -en ese orden de
    prioridad si por error vinieran los dos."""
    texto_poly, ancho_mm = texto2d.texto_a_poligono(nombre, ruta_ttf, alto_mm, raster_px)
    if texto_poly is None:
        raise ValueError("no se pudo extraer el texto (probá otra fuente o subí la resolución)")

    minx, miny, maxx, maxy = texto_poly.bounds
    cy = (miny + maxy) / 2

    contenido = texto_poly
    if decoracion_svg:
        forma_deco = decoraciones.forma_desde_svg(decoracion_svg, decoracion_tam)
        if forma_deco is None:
            raise ValueError(f"no se pudo sacar ninguna forma con área del SVG: {decoracion_svg}")
    elif decoracion_emoji:
        forma_deco = decoraciones.forma_desde_emoji(decoracion_emoji, decoracion_tam)
        if forma_deco is None:
            raise ValueError(f"no encontré el emoji/símbolo {decoracion_emoji!r} en la fuente — probá otro")
    elif decoracion != "ninguno":
        forma_deco = decoraciones.forma(decoracion, decoracion_tam)
    else:
        forma_deco = None

    if forma_deco is not None:
        cx_deco, cy_deco = _posicion_decoracion(minx, maxx, maxy, cy, decoracion_lado, decoracion_tam)
        forma_deco = translate(forma_deco, xoff=cx_deco + deco_x, yoff=cy_deco + deco_y)
        contenido = unary_union([contenido, forma_deco])

    cminx, cminy, cmaxx, cmaxy = contenido.bounds
    ccy = (cminy + cmaxy) / 2

    base = contenido.buffer(borde_mm, join_style=1, cap_style=1)

    tabs, huecos = [], []
    if aro_lado in ("izquierda", "ambos"):
        rx = cminx - aro_r - 3
        tabs.append(LineString([(rx, ccy), (cminx, ccy)]).buffer(aro_r + 2, cap_style=1))
        huecos.append(Point(rx, ccy).buffer(aro_r, resolution=32))
    if aro_lado in ("derecha", "ambos"):
        rx = cmaxx + aro_r + 3
        tabs.append(LineString([(rx, ccy), (cmaxx, ccy)]).buffer(aro_r + 2, cap_style=1))
        huecos.append(Point(rx, ccy).buffer(aro_r, resolution=32))

    if tabs:
        base = unary_union([base] + tabs)
    if huecos:
        base = base.difference(unary_union(huecos))

    return contenido, base, ancho_mm, (maxy - miny)


def _guardar_preview(ruta_png, base, contenido, color_base, color_texto, nombre):
    minx, miny, maxx, maxy = base.bounds
    w, h = max(maxx - minx, 1), max(maxy - miny, 1)
    fig, ax = plt.subplots(figsize=(8, 8 * h / w + 1))

    def dibujar(geom, color):
        pols = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
        for pg in pols:
            xs, ys = pg.exterior.xy
            ax.fill(xs, ys, color=color)
            for anillo in pg.interiors:
                xr, yr = anillo.xy
                ax.fill(xr, yr, color="white")

    dibujar(base, colores.hex_de(color_base))
    dibujar(contenido, colores.hex_de(color_texto))
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(nombre, color="#333")
    fig.savefig(ruta_png, dpi=130, bbox_inches="tight", facecolor="#f5f5dc")
    plt.close(fig)


def preview_rapido(nombre, ruta_ttf, alto_mm=20,
                    color_base="Blanco", color_texto="Rosa Fluor",
                    decoracion="corazon", decoracion_lado="derecha", decoracion_tam=7,
                    decoracion_emoji=None,
                    deco_x=0, deco_y=0, aro_lado="izquierda", aro_r=2, borde_mm=3):
    """Preview 2D instantáneo — solo la geometría plana (texto + decoración
    + borde + aro, `_armar_geometria`), SIN mesh3d ni booleanas 3D — para
    ver el resultado mientras se ajustan los parámetros, antes de tocar
    "Generar llavero" (que sí arma la malla 3D real y tarda más). No
    soporta ícono propio en SVG (`decoracion_svg`): esa ruta cambia con
    cada archivo subido y no vale la pena cachear. Devuelve
    (png_bytes, ancho_mm, alto_mm) o (None, 0, 0) si no se pudo generar."""
    if not os.path.exists(ruta_ttf):
        return None, 0, 0
    if not decoracion_emoji and decoracion not in decoraciones.NOMBRES_VALIDOS:
        return None, 0, 0
    try:
        contenido, base, ancho_mm, alto_mm_real = _armar_geometria(
            nombre, ruta_ttf, alto_mm, decoracion, decoracion_lado, decoracion_tam,
            deco_x, deco_y, aro_lado, aro_r, borde_mm, raster_px=250, decoracion_emoji=decoracion_emoji,
        )
    except (ValueError, FileNotFoundError):
        return None, 0, 0

    buf = io.BytesIO()
    _guardar_preview(buf, base, contenido, color_base, color_texto, nombre)
    return buf.getvalue(), ancho_mm, alto_mm_real


def generar(nombre, ruta_ttf, alto_mm=20,
            color_base="Blanco", color_texto="Rosa Fluor",
            decoracion="corazon", decoracion_lado="derecha", decoracion_tam=7,
            decoracion_svg=None, decoracion_emoji=None,
            deco_x=0, deco_y=0,
            aro_lado="izquierda", aro_r=2,
            espesor_texto_mm=2, espesor_base_mm=3, borde_mm=3,
            tiene_ams=False, raster_px=400,
            carpeta_salida=CARPETA_SALIDA):
    """Arma el llavero (texto + decoración + borde + aro) directamente con
    shapely/trimesh y devuelve un dict con las rutas, medidas (reales,
    medidas sobre la geometría) y avisos. No pregunta nada ni imprime
    nada — así lo puede llamar tanto la CLI como la app visual.

    `decoracion_svg`: ruta a un .svg propio del usuario (ícono/logo
    simple). `decoracion_emoji`: un emoji/pictograma/signo (un carácter,
    ej. "✈", core/decoraciones.py::forma_desde_emoji). Cualquiera de los
    dos, si viene seteado, se usa en vez de `decoracion` (que en ese caso
    se ignora) — SVG tiene prioridad sobre emoji si por error vinieran
    los dos."""
    if not os.path.exists(ruta_ttf):
        raise FileNotFoundError(f"no encuentro la fuente: {ruta_ttf}")
    if decoracion_svg:
        if not os.path.exists(decoracion_svg):
            raise FileNotFoundError(f"no encuentro el SVG: {decoracion_svg}")
    elif not decoracion_emoji and decoracion not in decoraciones.NOMBRES_VALIDOS:
        raise ValueError(f"decoracion debe ser una de {decoraciones.NOMBRES_VALIDOS}, recibí {decoracion!r}")

    contenido, base, ancho_texto_mm, alto_texto_mm = _armar_geometria(
        nombre, ruta_ttf, alto_mm, decoracion, decoracion_lado, decoracion_tam,
        deco_x, deco_y, aro_lado, aro_r, borde_mm, raster_px,
        decoracion_svg=decoracion_svg, decoracion_emoji=decoracion_emoji,
    )

    os.makedirs(carpeta_salida, exist_ok=True)
    base_nombre = pieza.nombre_archivo(nombre, default="llavero")
    ruta_png = os.path.join(carpeta_salida, f"{base_nombre}_preview.png")
    ruta_stl_base = os.path.join(carpeta_salida, f"{base_nombre}_base.stl")
    ruta_stl_texto = os.path.join(carpeta_salida, f"{base_nombre}_texto.stl")

    _guardar_preview(ruta_png, base, contenido, color_base, color_texto, nombre)

    piezas_base = mesh3d.piezas_desde_geom(base, espesor_base_mm)
    malla_base = mesh3d.unir_y_exportar(piezas_base, ruta_stl_base)

    z_texto = espesor_base_mm if tiene_ams else 0.0
    piezas_texto = mesh3d.piezas_desde_geom(contenido, espesor_texto_mm, z=z_texto)
    malla_texto = mesh3d.unir_y_exportar(piezas_texto, ruta_stl_texto)

    minx, miny, maxx, maxy = base.bounds
    ancho_mm, alto_total_mm = maxx - minx, maxy - miny
    entra_a1, mensaje_a1 = bambu_a1.chequear_tamano(
        ancho_mm, alto_total_mm, espesor_base_mm + espesor_texto_mm, nombre="llavero"
    )

    ruta_stl_multicolor = None
    if tiene_ams:
        # Los slicers (Bambu Studio incluido) re-acomodan cada STL que importás por
        # separado, así que 2 archivos sueltos NO quedan alineados aunque el archivo
        # diga que van pegados. La solución: un solo STL con las 2 piezas ya adentro
        # (sin fusionar, cada una como su propio cuerpo) — al ser un solo import no hay
        # reacomodo, y en Bambu Studio "Partir en objetos" las separa para pintarlas.
        ruta_stl_multicolor = os.path.join(carpeta_salida, f"{base_nombre}_multicolor.stl")
        pieza.exportar_multicolor([malla_base, malla_texto], ruta_stl_multicolor)
        info = [
            "Con AMS: descargá el STL multicolor (ya trae las 2 piezas pegadas en su "
            "posición real). En Bambu Studio: clic derecho sobre el objeto → \"Partir en "
            "objetos\", seleccioná las piezas del texto/decoración y asignales un color, "
            "y la base el otro — un solo trabajo de impresión, sin pegar nada a mano."
        ]
    else:
        info = [
            "Sin AMS: cada STL está apoyado en el suelo para imprimirse por separado — "
            "después hay que pegar la pieza de texto sobre la base a mano."
        ]

    return {
        "nombre": nombre,
        "ruta_png": ruta_png,
        "ruta_stl_base": ruta_stl_base,
        "ruta_stl_texto": ruta_stl_texto,
        "ruta_stl_multicolor": ruta_stl_multicolor,
        "ancho_mm": ancho_mm,
        "alto_mm": alto_total_mm,
        "vertices_base": len(malla_base.vertices), "watertight_base": malla_base.is_watertight,
        "vertices_texto": len(malla_texto.vertices), "watertight_texto": malla_texto.is_watertight,
        "info": info,
        "avisos": [],
        "entra_a1": entra_a1,
        "mensaje_a1": mensaje_a1,
    }


# ---------------------------------------------------------------------------
#  Interfaz de consola (menú de main.py)
# ---------------------------------------------------------------------------
def _elegir_fuente():
    catalogo = fuentes.listar_fuentes()
    if not catalogo:
        return ui.pedir_texto("Ruta a la fuente .ttf", "fonts/Pacifico.ttf")
    print("  Fuentes: escribí un nombre (ej. 'Comic Sans MS') o dejá vacío para 'Lily Script One'.")
    eleccion = ui.pedir_texto("Fuente", "Lily Script One")
    if os.path.exists(eleccion):
        return eleccion
    encontrada = fuentes.buscar_por_nombre(eleccion)
    if encontrada:
        print(f"    -> usando {encontrada}")
        return encontrada
    return eleccion


def ejecutar():
    print(f"\n{NOMBRE}")

    nombre = ui.pedir_texto("Nombre / texto", "Bianca")
    ruta_ttf = _elegir_fuente()
    decoracion = ui.pedir_opcion("Decoración", DECORACIONES, "corazon")
    decoracion_lado = ui.pedir_opcion("Lado de la decoración", LADOS_DECO, "derecha")
    aro_lado = ui.pedir_opcion("Lado del aro (para el llavero)", LADOS_ARO, "izquierda")
    tiene_ams = ui.pedir_si_no("¿Tenés AMS (impresora multicolor)?", default=False)

    print(f"\n  » Nombre: {nombre!r}  fuente: {ruta_ttf}  decoración: {decoracion} ({decoracion_lado})  aro: {aro_lado}")

    try:
        r = generar(nombre, ruta_ttf, decoracion=decoracion,
                    decoracion_lado=decoracion_lado, aro_lado=aro_lado, tiene_ams=tiene_ams)
    except (FileNotFoundError, ValueError) as e:
        print(f"  ERROR: {e}")
        return

    print(f"  tamaño ~ {r['ancho_mm']:.0f} x {r['alto_mm']:.0f} mm")
    for nota in r["info"]:
        print(f"  · {nota}")
    for aviso in r["avisos"]:
        print(f"  ⚠ {aviso}")
    print(f"  ✓ preview -> {r['ruta_png']}")
    print(f"  ✓ STL (base)  -> {r['ruta_stl_base']}  ({r['vertices_base']} vért., watertight={r['watertight_base']})")
    print(f"  ✓ STL (texto) -> {r['ruta_stl_texto']}  ({r['vertices_texto']} vért., watertight={r['watertight_texto']})")
    if r["ruta_stl_multicolor"]:
        print(f"  ✓ STL (multicolor, para AMS) -> {r['ruta_stl_multicolor']}")
    print(f"  {'✓' if r['entra_a1'] else '⚠'} {r['mensaje_a1']}")
    print()
