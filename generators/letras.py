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

Segunda vuelta: nombre en cursiva pegado abajo (macizo, sin luz —
soldado a la letra, mismo color) y decoraciones sueltas pegadas al
frente (protruyen hacia el que mira el cartel, en el mismo estilo que
las decoraciones del llavero — core/decoraciones.py —, con export
multicolor para AMS o un STL por pieza para pegar a mano).
"""

import io
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import trimesh
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from shapely.affinity import translate
from shapely.geometry import Point
from shapely.ops import unary_union

from core import bambu_a1, colores, decoraciones, geometry, mesh3d, pieza, preview3d, texto2d

NOMBRE = "Letra iluminada de pie"
DESCRIPCION = "Letra/inicial grande, hueca por dentro para una luz LED — con soporte de escritorio si hace falta."

CARPETA_SALIDA = "output"

DECORACIONES = [n for n in decoraciones.NOMBRES_VALIDOS if n != "ninguno"]


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


def _armar_nombre_cursiva(poly_letra, texto_nombre, ruta_ttf_nombre, alto_nombre_mm, raster_px, solape_mm=3.0):
    """Arma el polígono 2D del nombre (fuente cursiva/script, sin luz),
    centrado en X y pegado al borde inferior de `poly_letra` con
    `solape_mm` de superposición (para que la unión booleana suelde bien,
    no quede apenas tocándose). Devuelve (poligono, ancho_mm), o (None, 0)
    si no se pudo extraer el texto."""
    nombre_poly, ancho_nombre_mm = texto2d.texto_a_poligono(texto_nombre, ruta_ttf_nombre, alto_nombre_mm, raster_px)
    if nombre_poly is None:
        return None, 0
    nminx, nminy, nmaxx, nmaxy = nombre_poly.bounds
    lminx, lminy, lmaxx, lmaxy = poly_letra.bounds
    dx = (lminx + lmaxx) / 2 - (nminx + nmaxx) / 2
    dy = (lminy + solape_mm) - nmaxy
    return translate(nombre_poly, xoff=dx, yoff=dy), ancho_nombre_mm


def _posicion_decoracion_libre(poly_letra, x_pct, y_pct):
    """Convierte una posición relativa (0-100%, X de izquierda a derecha,
    Y de abajo a arriba) dentro de la caja de `poly_letra` a coordenadas
    (mm) absolutas — así el slider de la UI no depende del tamaño real de
    la letra."""
    minx, miny, maxx, maxy = poly_letra.bounds
    return minx + (x_pct / 100.0) * (maxx - minx), miny + (y_pct / 100.0) * (maxy - miny)


def _armar_decoraciones_frente(poly_letra, decoraciones_lista, profundidad_decoracion_mm, overlap_mm=1.0):
    """Arma una malla 3D por cada decoración (`{"nombre", "tam_mm",
    "x_pct", "y_pct"}`), pegada al frente de la letra: protruye hacia el
    que mira el cartel (Z negativo, delante de la cara de adelante en
    Z=0) y se soldará ahí porque se mete `overlap_mm` para adentro de la
    pared sólida. Devuelve una lista de (malla, dict_decoracion) — salta
    (sin agregar nada) las decoraciones con nombre no reconocido."""
    piezas = []
    for d in decoraciones_lista:
        forma_deco = decoraciones.forma(d["nombre"], d["tam_mm"])
        if forma_deco is None:
            continue
        x, y = _posicion_decoracion_libre(poly_letra, d.get("x_pct", 50), d.get("y_pct", 85))
        forma_deco = translate(forma_deco, xoff=x, yoff=y)
        trozos = mesh3d.piezas_desde_geom(
            forma_deco, profundidad_decoracion_mm + overlap_mm, z=-profundidad_decoracion_mm
        )
        if not trozos:
            continue
        malla = trimesh.util.concatenate(trozos) if len(trozos) > 1 else trozos[0]
        piezas.append((malla, d))
    return piezas


def preview_rapido(texto, ruta_ttf, alto_mm=150, color_letra="Amarillo",
                    agregar_nombre=False, texto_nombre="", ruta_ttf_nombre=None, alto_nombre_mm=30,
                    decoraciones_frente=None):
    """Preview 2D instantáneo — solo polígonos shapely (letra + nombre si
    hay + decoraciones posicionadas), SIN el hueco/cáscara/booleanas 3D
    de `_armar_carcasa_hueca` — para ver el resultado (tamaño, posición
    de las decoraciones) mientras se ajustan los parámetros, antes de
    tocar "Generar letra" (que sí arma la malla 3D real y tarda más).
    Devuelve (png_bytes, ancho_mm, alto_mm) o (None, 0, 0)."""
    if not os.path.exists(ruta_ttf) or not texto.strip():
        return None, 0, 0
    poly, _ = texto2d.texto_a_poligono(texto, ruta_ttf, alto_mm, raster_px=250)
    if poly is None:
        return None, 0, 0

    contenido = poly
    if agregar_nombre and texto_nombre.strip() and ruta_ttf_nombre and os.path.exists(ruta_ttf_nombre):
        nombre_poly, _ = _armar_nombre_cursiva(poly, texto_nombre, ruta_ttf_nombre, alto_nombre_mm, raster_px=250)
        if nombre_poly is not None:
            contenido = unary_union([contenido, nombre_poly])

    decos = []
    for d in (decoraciones_frente or []):
        forma_deco = decoraciones.forma(d["nombre"], d["tam_mm"])
        if forma_deco is None:
            continue
        x, y = _posicion_decoracion_libre(poly, d.get("x_pct", 50), d.get("y_pct", 85))
        decos.append(translate(forma_deco, xoff=x, yoff=y))

    minx, miny, maxx, maxy = contenido.bounds
    for dec in decos:
        dminx, dminy, dmaxx, dmaxy = dec.bounds
        minx, miny = min(minx, dminx), min(miny, dminy)
        maxx, maxy = max(maxx, dmaxx), max(maxy, dmaxy)
    w, h = max(maxx - minx, 1), max(maxy - miny, 1)

    def dibujar(ax, geom, color):
        pols = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
        for pg in pols:
            xs, ys = pg.exterior.xy
            ax.fill(xs, ys, color=color)
            for anillo in pg.interiors:
                xr, yr = anillo.xy
                ax.fill(xr, yr, color="#1a1a1a")

    fig, ax = plt.subplots(figsize=(6, 6 * h / w + 1))
    dibujar(ax, contenido, colores.hex_de(color_letra))
    for i, dec in enumerate(decos):
        dibujar(ax, dec, preview3d.color_decoracion(i))
    ax.set_xlim(minx - 2, maxx + 2)
    ax.set_ylim(miny - 2, maxy + 2)
    ax.set_aspect("equal")
    ax.axis("off")

    buf = io.BytesIO()
    fig.savefig(buf, dpi=120, bbox_inches="tight", facecolor="#1a1a1a")
    plt.close(fig)
    return buf.getvalue(), maxx - minx, maxy - miny


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
            agregar_nombre=False, texto_nombre="", ruta_ttf_nombre=None, alto_nombre_mm=30,
            decoraciones_frente=None, profundidad_decoracion_mm=4.0, decoraciones_tiene_ams=False,
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
    para no hacer agujero).

    `agregar_nombre`/`texto_nombre`/`ruta_ttf_nombre`/`alto_nombre_mm`:
    nombre en cursiva pegado abajo de la letra — macizo, sin hueco (no
    lleva luz), soldado como una sola pieza (mismo color que la letra).
    Si también hay soporte de escritorio, la pata sale del borde de abajo
    del conjunto letra+nombre, no de la letra sola.

    `decoraciones_frente`: lista de dicts `{"nombre", "tam_mm", "x_pct",
    "y_pct"}` (una de core.decoraciones.NOMBRES_VALIDOS, posición 0-100%
    dentro de la caja de la letra) — protruyen del frente, en piezas
    sueltas para pintar de otro color. `decoraciones_tiene_ams=True`
    exporta un solo STL multicolor (como el llavero); si no, un STL por
    decoración para pegar a mano."""
    if not os.path.exists(ruta_ttf):
        raise FileNotFoundError(f"no encuentro la fuente: {ruta_ttf}")
    if not texto.strip():
        raise ValueError("escribí al menos una letra")
    if agregar_nombre and texto_nombre.strip() and not (ruta_ttf_nombre and os.path.exists(ruta_ttf_nombre)):
        raise FileNotFoundError(f"no encuentro la fuente del nombre: {ruta_ttf_nombre}")

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

    contenido_2d = poly
    if agregar_nombre and texto_nombre.strip():
        nombre_poly, _ = _armar_nombre_cursiva(poly, texto_nombre, ruta_ttf_nombre, alto_nombre_mm, raster_px)
        if nombre_poly is None:
            info.append(f"No se pudo extraer el nombre {texto_nombre!r} (probá otra fuente) — sigo sin él.")
        else:
            contenido_2d = unary_union([contenido_2d, nombre_poly])
            piezas_nombre = mesh3d.piezas_desde_geom(nombre_poly, profundidad_mm)
            malla_nombre = trimesh.util.concatenate(piezas_nombre) if len(piezas_nombre) > 1 else piezas_nombre[0]
            carcasa = trimesh.boolean.union([carcasa, malla_nombre], engine="manifold")
            info.append(f"Nombre {texto_nombre!r} agregado abajo, macizo (sin luz), soldado a la letra.")

    pieza_soporte = None
    if agregar_soporte:
        poly_con_pata, ancho_pata_mm = geometry.agregar_pata_escritorio(
            contenido_2d, ancho_pata_mm=ancho_pata_mm, alto_pata_mm=alto_pata_mm
        )
        pata_poly = poly_con_pata.difference(contenido_2d)
        piezas_pata = mesh3d.piezas_desde_geom(pata_poly, profundidad_mm)
        if piezas_pata:
            pata_solida = trimesh.util.concatenate(piezas_pata) if len(piezas_pata) > 1 else piezas_pata[0]
            carcasa = trimesh.boolean.union([carcasa, pata_solida], engine="manifold")
        info.append(
            f"Pata de {ancho_pata_mm:.0f}mm agregada abajo (sólida, sin hueco) para encastrar en "
            f"la base de escritorio (STL aparte) — para las letras que no se paran solas."
        )

    piezas_deco = []
    if decoraciones_frente:
        piezas_deco = _armar_decoraciones_frente(poly, decoraciones_frente, profundidad_decoracion_mm)
        if len(piezas_deco) < len(decoraciones_frente):
            info.append("Alguna decoración no se pudo generar (nombre no reconocido) y se salteó.")

    os.makedirs(carpeta_salida, exist_ok=True)
    base_nombre = pieza.nombre_archivo(texto, default="letra")
    ruta_stl = os.path.join(carpeta_salida, f"letra_{base_nombre}.stl")
    ruta_png = os.path.join(carpeta_salida, f"letra_{base_nombre}_preview.png")

    carcasa.export(ruta_stl)
    if piezas_deco:
        malla_preview = trimesh.util.concatenate([carcasa] + [m for m, _ in piezas_deco])
        _guardar_preview(ruta_png, malla_preview, f"Letra {texto!r}")
    else:
        _guardar_preview(ruta_png, carcasa, f"Letra {texto!r}")

    decoraciones_export = []
    ruta_stl_decoraciones_multicolor = None
    if piezas_deco:
        if decoraciones_tiene_ams:
            ruta_stl_decoraciones_multicolor = os.path.join(
                carpeta_salida, f"letra_{base_nombre}_decoraciones_multicolor.stl"
            )
            pieza.exportar_multicolor([m for m, _ in piezas_deco], ruta_stl_decoraciones_multicolor)
            info.append(
                f"{len(piezas_deco)} decoración(es) agregadas al frente — STL multicolor aparte "
                f"(con AMS: clic derecho → \"Partir en objetos\" en Bambu Studio para pintar cada una)."
            )
        else:
            decoraciones_export = pieza.exportar_piezas_sueltas(
                [(m, f"deco{i}_{d['nombre']}") for i, (m, d) in enumerate(piezas_deco, start=1)],
                carpeta_salida, f"letra_{base_nombre}",
            )
            for exportada, (_, d) in zip(decoraciones_export, piezas_deco):
                exportada["nombre"] = d["nombre"]
            info.append(
                f"{len(piezas_deco)} decoración(es) agregadas al frente — un STL por pieza para "
                f"pegarlas a mano después de imprimir la letra."
            )

    if agregar_soporte:
        pieza_soporte = pieza.exportar_base_escritorio(
            ancho_pata_mm, profundidad_mm, alto_pata_mm, f"letra_{base_nombre}", carpeta_salida
        )

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
    for m, _ in piezas_deco:
        (dminx, dminy, dminz), (dmaxx, dmaxy, dmaxz) = m.bounds
        minx, miny, minz = min(minx, dminx), min(miny, dminy), min(minz, dminz)
        maxx, maxy, maxz = max(maxx, dmaxx), max(maxy, dmaxy), max(maxz, dmaxz)
    ancho_mm, alto_total_mm, profundo_total_mm = maxx - minx, maxy - miny, maxz - minz
    entra_a1, mensaje_a1 = bambu_a1.chequear_tamano(ancho_mm, alto_total_mm, profundo_total_mm, nombre="letra")

    return {
        "texto": texto,
        "ruta_png": ruta_png,
        "ruta_stl": ruta_stl,
        "pieza_soporte": pieza_soporte,
        "pieza_tapa": pieza_tapa,
        "decoraciones": decoraciones_export,
        "ruta_stl_decoraciones_multicolor": ruta_stl_decoraciones_multicolor,
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

    agregar_nombre = ui.pedir_si_no("¿Agregar un nombre en cursiva pegado abajo (sin luz)?", default=False)
    texto_nombre, ruta_ttf_nombre, alto_nombre_mm = "", None, 30
    if agregar_nombre:
        texto_nombre = ui.pedir_texto("Nombre", "Bianca")
        nombre_fuente_nombre = ui.pedir_texto("Fuente del nombre", "Lily Script One")
        ruta_ttf_nombre = (
            nombre_fuente_nombre if os.path.exists(nombre_fuente_nombre)
            else fuentes.buscar_por_nombre(nombre_fuente_nombre)
        )
        ruta_ttf_nombre = ruta_ttf_nombre or nombre_fuente_nombre
        alto_nombre_mm = ui.pedir_float("Alto del nombre (mm)", 30)

    print(f"\n  » Letra: {texto!r}  fuente: {ruta_ttf}  soporte: {agregar_soporte}")
    print("  (armando la geometría, puede tardar unos segundos...)")

    try:
        r = generar(
            texto, ruta_ttf, agregar_soporte=agregar_soporte,
            agregar_nombre=agregar_nombre, texto_nombre=texto_nombre,
            ruta_ttf_nombre=ruta_ttf_nombre, alto_nombre_mm=alto_nombre_mm,
        )
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
    if r["ruta_stl_decoraciones_multicolor"]:
        print(f"  ✓ STL (decoraciones multicolor) -> {r['ruta_stl_decoraciones_multicolor']}")
    for d in r["decoraciones"]:
        print(f"  ✓ STL (decoración {d['nombre']}) -> {d['ruta_stl']}")
    print(f"  ✓ preview -> {r['ruta_png']}")
    print(f"  {'✓' if r['entra_a1'] else '⚠'} {r['mensaje_a1']}")
    print()
