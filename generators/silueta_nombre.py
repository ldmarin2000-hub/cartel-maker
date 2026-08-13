#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generators/silueta_nombre.py
------------------------------
Generador "Silueta con Nombre": subís un SVG o una imagen (silueta de
corazón, estrella, osito, etc.), escribís un texto, y el generador lo
recorta, funde o talla sobre la silueta.

Tres modos de operación:
  · interseccion — el texto queda recortado por la forma de la silueta
    (solo se ve el texto donde coincide con la silueta).
  · union        — la silueta y el texto se funden en una sola pieza.
  · diferencia   — la silueta queda con el texto huecado (como un sello).

Opcionalmente se le puede agregar un borde alrededor y un aro de
llavero. Todo en Python puro (shapely + trimesh), sin software externo.
"""

import io
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from shapely.affinity import affine_transform, translate
from shapely.geometry import LineString, Point
from shapely.ops import unary_union

from core import bambu_a1, colores, imagen_import, mesh3d, pieza, svg_import, texto2d, ui

NOMBRE = "Silueta con Nombre"
DESCRIPCION = "Silueta personalizada (SVG/imagen) + texto: interseccion, union o sello. Con borde y aro opcionales."

CARPETA_SALIDA = "output"

MODOS = ("interseccion", "union", "diferencia")
LADOS_ARO = ("ninguno", "izquierda", "derecha", "ambos")


def _cargar_silueta(ruta, alto_mm):
    """Carga un SVG o imagen y devuelve el polígono escalado a `alto_mm` y
centrado en el origen."""
    ext = os.path.splitext(ruta)[1].lower()
    if ext == ".svg":
        silueta = svg_import.svg_a_poligono(ruta)
    else:
        silueta = imagen_import.imagen_a_poligono_crudo(ruta)

    if silueta is None or silueta.is_empty:
        raise ValueError(f"no se pudo cargar la silueta: {ruta}")

    minx, miny, maxx, maxy = silueta.bounds
    alto_real = maxy - miny
    if alto_real <= 0:
        raise ValueError("la silueta no tiene altura")

    escala = alto_mm / alto_real
    silueta = affine_transform(silueta, [escala, 0, 0, escala, 0, 0])

    # centrar en origen
    minx, miny, maxx, maxy = silueta.bounds
    silueta = translate(silueta, xoff=-(minx + maxx) / 2, yoff=-(miny + maxy) / 2)
    return silueta, (maxx - minx) * escala


def _texto_centardo(texto, ruta_ttf, alto_mm, raster_px):
    """Texto como polígono shapely, centrado en el origen."""
    poly, _ = texto2d.texto_a_poligono(texto, ruta_ttf, alto_mm, raster_px)
    if poly is None or poly.is_empty:
        raise ValueError("no se pudo extraer el texto (probá otra fuente o subí la resolución)")
    minx, miny, maxx, maxy = poly.bounds
    return translate(poly, xoff=-(minx + maxx) / 2, yoff=-(miny + maxy) / 2)


def _aplicar_modo(silueta, texto_poly, modo):
    if modo == "interseccion":
        return texto_poly.intersection(silueta)
    elif modo == "union":
        return unary_union([silueta, texto_poly])
    elif modo == "diferencia":
        return silueta.difference(texto_poly)
    else:
        raise ValueError(f"modo debe ser uno de {MODOS}, recibí {modo!r}")


def _agregar_borde_y_aro(forma, borde_mm, aro_lado, aro_r):
    """Borde + orejas de aro alrededor de `forma`. Devuelve la forma
extendida (o la original si no hay borde ni aro)."""
    if borde_mm <= 0 and aro_lado == "ninguno":
        return forma

    base = forma.buffer(borde_mm, join_style=1, cap_style=1) if borde_mm > 0 else forma

    cminx, cminy, cmaxx, cmaxy = forma.bounds
    ccy = (cminy + cmaxy) / 2

    tabs, huecos = [], []
    if aro_lado in ("izquierda", "ambos"):
        rx = cminx - aro_r - 3 - (borde_mm if borde_mm > 0 else 0)
        tabs.append(LineString([(rx, ccy), (cminx, ccy)]).buffer(aro_r + 2, cap_style=1))
        huecos.append(Point(rx, ccy).buffer(aro_r, resolution=32))
    if aro_lado in ("derecha", "ambos"):
        rx = cmaxx + aro_r + 3 + (borde_mm if borde_mm > 0 else 0)
        tabs.append(LineString([(rx, ccy), (cmaxx, ccy)]).buffer(aro_r + 2, cap_style=1))
        huecos.append(Point(rx, ccy).buffer(aro_r, resolution=32))

    if tabs:
        base = unary_union([base] + tabs)
    if huecos:
        base = base.difference(unary_union(huecos))
    return base


def _guardar_preview(destino, silueta, texto_poly, resultado, color_silueta, color_texto, color_resultado, titulo):
    """Renderiza la vista 2D: silueta (gris, semitransparente), texto
(contorno punteado) y resultado (color sólido)."""
    minx, miny, maxx, maxy = silueta.bounds
    for g in (texto_poly, resultado):
        if g is not None and not g.is_empty:
            b = g.bounds
            minx, miny = min(minx, b[0]), min(miny, b[1])
            maxx, maxy = max(maxx, b[2]), max(maxy, b[3])

    w, h = max(maxx - minx, 1), max(maxy - miny, 1)
    fig, ax = plt.subplots(figsize=(8, 8 * h / w + 0.5))

    def dibujar(geom, color, alpha=1.0, linestyle=None):
        if geom is None or geom.is_empty:
            return
        pols = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
        for pg in pols:
            xs, ys = pg.exterior.xy
            ax.fill(xs, ys, color=color, alpha=alpha)
            for anillo in pg.interiors:
                xr, yr = anillo.xy
                ax.fill(xr, yr, color="#1a1a1a", alpha=alpha)
            if linestyle:
                ax.plot(xs, ys, color=color, linestyle=linestyle, linewidth=1.5, alpha=0.7)

    # silueta de fondo (tenue)
    dibujar(silueta, colores.hex_de(color_silueta), alpha=0.25)
    # texto (contorno punteado)
    dibujar(texto_poly, colores.hex_de(color_texto), alpha=0.0, linestyle="--")
    # resultado (sólido)
    dibujar(resultado, colores.hex_de(color_resultado), alpha=1.0)

    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(titulo, color="#ccc")
    fig.savefig(destino, dpi=130, bbox_inches="tight", facecolor="#1a1a1a")
    plt.close(fig)


# ---------------------------------------------------------------------------
#  Preview rápido (solo 2D, sin extrusión ni booleanas 3D)
# ---------------------------------------------------------------------------
def preview_rapido(ruta_silueta, texto, ruta_ttf,
                   alto_silueta_mm=55, modo="interseccion",
                   escala_texto_pct=100, offset_x_mm=0, offset_y_mm=0,
                   borde_mm=0, aro_lado="ninguno", aro_r=2,
                   color_silueta="Gris", color_texto="Rosa Fluor", color_resultado="Blanco"):
    """Preview 2D instantáneo — solo operaciones shapely 2D. Devuelve
(png_bytes, ancho_mm, alto_mm) o (None, 0, 0)."""
    if not texto.strip() or not os.path.exists(ruta_ttf):
        return None, 0, 0
    if not ruta_silueta or not os.path.exists(ruta_silueta):
        return None, 0, 0

    try:
        silueta, _ = _cargar_silueta(ruta_silueta, alto_silueta_mm)
        texto_poly = _texto_centardo(texto, ruta_ttf, alto_silueta_mm * escala_texto_pct / 100.0, 250)
        texto_poly = translate(texto_poly, xoff=offset_x_mm, yoff=offset_y_mm)
        resultado = _aplicar_modo(silueta, texto_poly, modo)
        if resultado.is_empty:
            return None, 0, 0
        resultado = _agregar_borde_y_aro(resultado, borde_mm, aro_lado, aro_r)
    except (ValueError, FileNotFoundError):
        return None, 0, 0

    buf = io.BytesIO()
    _guardar_preview(buf, silueta, texto_poly, resultado,
                     color_silueta, color_texto, color_resultado,
                     f"{texto} · {modo}")
    minx, miny, maxx, maxy = resultado.bounds
    return buf.getvalue(), maxx - minx, maxy - miny


# ---------------------------------------------------------------------------
#  Generación completa (2D + extrusión 3D + export)
# ---------------------------------------------------------------------------
def generar(ruta_silueta, texto, ruta_ttf,
            alto_silueta_mm=55, modo="interseccion",
            escala_texto_pct=100, offset_x_mm=0, offset_y_mm=0,
            borde_mm=0, aro_lado="ninguno", aro_r=2,
            espesor_mm=4, tiene_ams=False,
            color_silueta="Gris", color_texto="Rosa Fluor", color_resultado="Blanco",
            raster_px=400, carpeta_salida=CARPETA_SALIDA):
    """Arma la pieza y exporta el STL. Devuelve un dict con rutas, medidas
y avisos."""
    if not texto.strip():
        raise ValueError("escribí un texto")
    if not os.path.exists(ruta_ttf):
        raise FileNotFoundError(f"no encuentro la fuente: {ruta_ttf}")
    if not ruta_silueta or not os.path.exists(ruta_silueta):
        raise FileNotFoundError(f"no encuentro la silueta: {ruta_silueta}")
    if modo not in MODOS:
        raise ValueError(f"modo debe ser uno de {MODOS}, recibí {modo!r}")

    silueta, ancho_silueta = _cargar_silueta(ruta_silueta, alto_silueta_mm)
    texto_poly = _texto_centardo(texto, ruta_ttf, alto_silueta_mm * escala_texto_pct / 100.0, raster_px)
    texto_poly = translate(texto_poly, xoff=offset_x_mm, yoff=offset_y_mm)

    resultado_2d = _aplicar_modo(silueta, texto_poly, modo)
    if resultado_2d.is_empty:
        raise ValueError("el resultado quedó vacío — probá otro modo o ajustá la posición/escala del texto")

    resultado_2d = _agregar_borde_y_aro(resultado_2d, borde_mm, aro_lado, aro_r)

    os.makedirs(carpeta_salida, exist_ok=True)
    base_nombre = pieza.nombre_archivo(texto, default="silueta")
    ruta_png = os.path.join(carpeta_salida, f"silueta_{base_nombre}_preview.png")
    ruta_stl = os.path.join(carpeta_salida, f"silueta_{base_nombre}.stl")

    _guardar_preview(ruta_png, silueta, texto_poly, resultado_2d,
                     color_silueta, color_texto, color_resultado,
                     f"{texto} · {modo}")

    piezas = mesh3d.piezas_desde_geom(resultado_2d, espesor_mm)
    malla = mesh3d.unir_y_exportar(piezas, ruta_stl)

    minx, miny, maxx, maxy = resultado_2d.bounds
    ancho_mm, alto_mm = maxx - minx, maxy - miny
    entra_a1, mensaje_a1 = bambu_a1.chequear_tamano(ancho_mm, alto_mm, espesor_mm, nombre="silueta")

    info = []
    if modo == "interseccion":
        info.append("Modo intersección: el texto quedó recortado por la silueta.")
    elif modo == "union":
        info.append("Modo unión: la silueta y el texto se fusionaron en una sola pieza.")
    else:
        info.append("Modo diferencia: la silueta quedó con el texto huecado (tipo sello).")

    if aro_lado != "ninguno":
        info.append(f"Aro de llavero agregado al lado: {aro_lado}.")

    return {
        "texto": texto,
        "ruta_png": ruta_png,
        "ruta_stl": ruta_stl,
        "ancho_mm": ancho_mm,
        "alto_mm": alto_mm,
        "espesor_mm": espesor_mm,
        "vertices": len(malla.vertices),
        "watertight": malla.is_watertight,
        "info": info,
        "avisos": [],
        "entra_a1": entra_a1,
        "mensaje_a1": mensaje_a1,
    }


# ---------------------------------------------------------------------------
#  Interfaz de consola (menú de main.py)
# ---------------------------------------------------------------------------
def _elegir_fuente():
    from core import fuentes
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
    print("  Silueta personalizada (SVG o imagen) + texto.")

    ruta_silueta = ui.pedir_texto("Ruta a la silueta (SVG/PNG/JPG)", "svg/corazon.svg")
    texto = ui.pedir_texto("Texto", "Monica")
    ruta_ttf = _elegir_fuente()
    modo = ui.pedir_opcion("Modo", list(MODOS), "interseccion")
    alto_silueta = ui.pedir_float("Alto de la silueta (mm)", 55.0)
    escala_texto = ui.pedir_float("Escala del texto (% del alto de la silueta)", 100.0)
    borde = ui.pedir_float("Borde alrededor (mm, 0 = sin borde)", 0.0)
    aro = ui.pedir_opcion("Aro de llavero", list(LADOS_ARO), "ninguno")

    print(f"\n  » Silueta: {ruta_silueta}  texto: {texto!r}  modo: {modo}")
    print("  (armando la geometría...)")

    try:
        r = generar(ruta_silueta, texto, ruta_ttf,
                    alto_silueta_mm=alto_silueta, modo=modo,
                    escala_texto_pct=escala_texto, borde_mm=borde, aro_lado=aro)
    except (FileNotFoundError, ValueError) as e:
        print(f"  ERROR: {e}")
        return

    print(f"  tamaño ~ {r['ancho_mm']:.0f} x {r['alto_mm']:.0f} x {r['espesor_mm']:.0f} mm")
    for nota in r["info"]:
        print(f"  · {nota}")
    print(f"  ✓ preview -> {r['ruta_png']}")
    print(f"  ✓ STL -> {r['ruta_stl']}  ({r['vertices']} vért., watertight={r['watertight']})")
    print(f"  {'✓' if r['entra_a1'] else '⚠'} {r['mensaje_a1']}")
    print()
