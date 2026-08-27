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
from shapely.ops import unary_union

from core import bambu_a1, carcasa_hueca, colores, decoraciones, geometry, mesh3d, pieza, preview3d, texto2d

NOMBRE = "Letra iluminada de pie"
DESCRIPCION = "Letra/inicial grande, hueca por dentro para una luz LED — con soporte de escritorio si hace falta."

CARPETA_SALIDA = "output"

DECORACIONES = [n for n in decoraciones.NOMBRES_VALIDOS if n != "ninguno"]

# La cáscara hueca (con rebaje para la tapa), la tapa y el agujero de cable son
# mecánica compartida con generators/caja_luz.py -- viven en core/carcasa_hueca.py.
_armar_carcasa_hueca = carcasa_hueca.armar_carcasa_hueca
_armar_agujero_pared = carcasa_hueca.armar_agujero_pared
_armar_tapa = carcasa_hueca.armar_tapa


def _armar_nombre_cursiva(poly_letra, texto_nombre, ruta_ttf_nombre, alto_nombre_mm, raster_px, solape_mm=3.0):
    """Arma el polígono 2D del nombre (fuente cursiva/script, sin luz),
    centrado en X y pegado al borde inferior de `poly_letra` con
    `solape_mm` de superposición (para que la unión con la pata/base
    suelde bien, y para que quede un poco "encastrado" contra la letra —
    misma idea que la ranura de la referencia, pero sin cortar un hueco:
    acá alcanza con superponer un poco los dos sólidos). Devuelve
    (poligono, ancho_mm), o (None, 0) si no se pudo extraer el texto."""
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


def _forma_decoracion(d):
    """Resuelve la forma 2D de una decoración `{"nombre", "tam_mm",
    "x_pct", "y_pct", "emoji" (opcional)}` — un emoji/pictograma/signo
    (core/decoraciones.py::forma_desde_emoji) si trae `"emoji"`, si no
    una de la lista predefinida por `"nombre"`. Devuelve None si no se
    pudo generar (nombre no reconocido, o el emoji no está en la
    fuente)."""
    if d.get("emoji"):
        return decoraciones.forma_desde_emoji(d["emoji"], d["tam_mm"])
    return decoraciones.forma(d["nombre"], d["tam_mm"])


def _armar_decoraciones_frente(poly_letra, decoraciones_lista, profundidad_decoracion_mm, overlap_mm=1.0):
    """Arma una malla 3D por cada decoración (`{"nombre", "tam_mm",
    "x_pct", "y_pct"}`, o `{"emoji", "tam_mm", "x_pct", "y_pct"}`),
    pegada al frente de la letra: protruye hacia el que mira el cartel
    (Z negativo, delante de la cara de adelante en Z=0) y se soldará ahí
    porque se mete `overlap_mm` para adentro de la pared sólida. Devuelve
    una lista de (malla, dict_decoracion) — salta (sin agregar nada) las
    decoraciones que no se pudieron generar."""
    piezas = []
    for d in decoraciones_lista:
        forma_deco = _forma_decoracion(d)
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
                    color_nombre="Blanco", decoraciones_frente=None,
                    mostrar_agujero=False, agujero_cable_diam_mm=4.5,
                    agujero_atras_x_pct=None, agujero_atras_y_pct=None,
                    soporte_tapa_mm=carcasa_hueca.SOPORTE_TAPA_MM_DEFAULT):
    """Preview 2D instantáneo — solo polígonos shapely (letra + nombre si
    hay + decoraciones posicionadas), SIN el hueco/cáscara/booleanas 3D
    de `_armar_carcasa_hueca` — para ver el resultado (tamaño, posición
    de las decoraciones) mientras se ajustan los parámetros, antes de
    tocar "Generar letra" (que sí arma la malla 3D real y tarda más). El
    nombre se dibuja en su propio color (`color_nombre`) — es una pieza
    aparte, no del mismo color que la letra. Devuelve (png_bytes,
    ancho_mm, alto_mm) o (None, 0, 0)."""
    if not os.path.exists(ruta_ttf) or not texto.strip():
        return None, 0, 0
    poly, _ = texto2d.texto_a_poligono(texto, ruta_ttf, alto_mm, raster_px=250)
    if poly is None:
        return None, 0, 0

    nombre_poly = None
    if agregar_nombre and texto_nombre.strip() and ruta_ttf_nombre and os.path.exists(ruta_ttf_nombre):
        nombre_poly, _ = _armar_nombre_cursiva(poly, texto_nombre, ruta_ttf_nombre, alto_nombre_mm, raster_px=250)

    decos = []
    for d in (decoraciones_frente or []):
        forma_deco = _forma_decoracion(d)
        if forma_deco is None:
            continue
        x, y = _posicion_decoracion_libre(poly, d.get("x_pct", 50), d.get("y_pct", 85))
        decos.append(translate(forma_deco, xoff=x, yoff=y))

    minx, miny, maxx, maxy = poly.bounds
    for extra in ([nombre_poly] if nombre_poly is not None else []) + decos:
        eminx, eminy, emaxx, emaxy = extra.bounds
        minx, miny = min(minx, eminx), min(miny, eminy)
        maxx, maxy = max(maxx, emaxx), max(maxy, emaxy)
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
    dibujar(ax, poly, colores.hex_de(color_letra))
    if nombre_poly is not None:
        dibujar(ax, nombre_poly, colores.hex_de(color_nombre))
    for i, dec in enumerate(decos):
        dibujar(ax, dec, preview3d.color_decoracion(i))

    if mostrar_agujero and agujero_cable_diam_mm > 0:
        radio = agujero_cable_diam_mm / 2
        es_manual = agujero_atras_x_pct is not None and agujero_atras_y_pct is not None
        if es_manual:
            punto = carcasa_hueca.punto_pct_a_xy(poly, agujero_atras_x_pct, agujero_atras_y_pct)
        else:
            punto = carcasa_hueca.punto_agujero_atras(poly, radio, soporte_tapa_mm)
        if punto is not None:
            corta_algo = not es_manual or carcasa_hueca.punto_atras_corta_algo(poly, punto, radio, soporte_tapa_mm)
            color = "#38bdf8" if corta_algo else "#f97316"
            ax.add_patch(plt.Circle(punto, radio, facecolor=color, edgecolor="white", linewidth=1.5, zorder=5))
            if not corta_algo:
                ax.text(
                    punto[0], punto[1] - radio - 4, "ahí no corta pared, no va a hacer nada",
                    color="#f97316", ha="center", fontsize=8, zorder=5,
                )
        else:
            ax.text(
                (minx + maxx) / 2, miny + 3, "sin lugar para el agujero ahí",
                color="#38bdf8", ha="center", fontsize=8, zorder=5,
            )

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
            agregar_tapa=True, tapa_espesor_mm=3.0, agujero_cable_diam_mm=4.5, agujero_cable_lado="atras",
            agujero_atras_x_pct=None, agujero_atras_y_pct=None,
            soporte_tapa_mm=carcasa_hueca.SOPORTE_TAPA_MM_DEFAULT, holgura_tapa_mm=carcasa_hueca.HOLGURA_TAPA_MM_DEFAULT,
            espesor_cara_mm=carcasa_hueca.ESPESOR_CARA_MM_DEFAULT, tapa_offset_mm=0.0,
            agregar_soporte=True, ancho_pata_mm=40, alto_pata_mm=15,
            agregar_nombre=False, texto_nombre="", ruta_ttf_nombre=None, alto_nombre_mm=30,
            profundidad_nombre_mm=10.0, nombre_tiene_ams=False,
            decoraciones_frente=None, profundidad_decoracion_mm=4.0, decoraciones_tiene_ams=False,
            raster_px=600, carpeta_salida=CARPETA_SALIDA):
    """Arma la letra iluminada (hueca, con soporte de escritorio si hace
    falta) y exporta el/los STL. Devuelve un dict con las rutas, medidas
    y avisos. No pregunta nada ni imprime nada — así lo puede llamar
    tanto la CLI como la app visual.

    `profundidad_mm`: cuánto sobresale la letra de la mesa (ahí adentro
    va la luz). `espesor_pared_mm`: cuánto crece la silueta hacia AFUERA
    del trazo de la fuente (la silueta final es más grande que la letra
    tal cual sale del boceto, no igual) — grosor de la pared lateral.
    `espesor_cara_mm`: grosor de la cara de ADELANTE (fina, para que se
    difunda la luz) — valor aparte, no tiene que ver con el espesor de
    pared. `agregar_tapa`: exporta una tapa aparte (contorno de la letra
    achicado por `holgura_tapa_mm`) para cerrar el hueco después de
    meter el LED — encastra en un escalón que se forma achicando el
    hueco principal por `soporte_tapa_mm` (tiene que ser más grande que
    `holgura_tapa_mm`), ver `_armar_carcasa_hueca`. El agujero para el
    cable (`agujero_cable_diam_mm`, 0 = sin agujero) va en la CARCASA, no
    en la tapa — `agujero_cable_lado` elige por dónde: "atras" (por el
    canto de atrás, el escalón donde apoya la tapa), "arriba", "abajo",
    "izquierda" o "derecha" (por la pared lateral del lado elegido).

    `agregar_nombre`/`texto_nombre`/`ruta_ttf_nombre`/`alto_nombre_mm`:
    nombre en cursiva pegado abajo de la letra — macizo, sin hueco (no
    lleva luz), como PIEZA APARTE (`profundidad_nombre_mm`, más fina que
    la letra — es una placa, no necesita todo el volumen) para poder
    pintarla de otro color, como en las referencias de este tipo de
    lámpara. `nombre_tiene_ams=True` exporta un .3mf combinado con la
    letra ya pintado por triángulo (abre listo en Bambu Studio, ver
    core/exportar_3mf.py); si no, un STL aparte para pegar a mano. La
    pata del soporte de escritorio (si hay) sale de la pieza que quede
    más abajo del conjunto (el nombre, si está agregado; si no, la
    letra), para que el que se apoya en la mesa sea justo eso.

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

    carcasa, quedo_hueca, info = _armar_carcasa_hueca(
        poly, profundidad_mm, espesor_pared_mm, tapa_espesor_mm, soporte_tapa_mm, espesor_cara_mm, tapa_offset_mm
    )
    if not quedo_hueca:
        info.append(
            "La letra quedó maciza (ningún trazo es más ancho que 2x el soporte de la tapa) — "
            "probá una letra más grande, una fuente más gruesa, o bajar el soporte de la tapa."
        )
    elif agregar_tapa and agujero_cable_diam_mm > 0 and agujero_cable_lado != "ninguno":
        punto_manual = None
        if agujero_cable_lado == "atras" and agujero_atras_x_pct is not None and agujero_atras_y_pct is not None:
            punto_manual = carcasa_hueca.punto_pct_a_xy(poly, agujero_atras_x_pct, agujero_atras_y_pct)
        agujero = _armar_agujero_pared(
            poly, espesor_pared_mm, agujero_cable_diam_mm, agujero_cable_lado, profundidad_mm, tapa_espesor_mm,
            soporte_tapa_mm=soporte_tapa_mm, espesor_cara_mm=espesor_cara_mm, tapa_offset_mm=tapa_offset_mm,
            punto_manual=punto_manual,
        )
        if agujero is None:
            if agujero_cable_lado == "atras":
                info.append(
                    f"No pude ubicar el agujero \"atras\" de {agujero_cable_diam_mm:.0f}mm: el "
                    f"escalón donde apoya la tapa mide {soporte_tapa_mm:.1f}mm de ancho, y en ningún lugar de la "
                    f"letra el agujero entra ahí sin salirse del contorno o sin quedar "
                    f"prácticamente flotando en el hueco. Opciones: bajá el diámetro del agujero, subí "
                    f"el soporte de la tapa, probá un lado radial (arriba/abajo/izquierda/derecha — esos sí "
                    f"cortan toda la pared, no solo el escalón, y aguantan agujeros más grandes), o hacelo "
                    f"a mano con una mecha."
                )
            else:
                info.append(
                    f"No pude ubicar el agujero del cable \"{agujero_cable_lado}\" (letra muy angosta "
                    f"ahí, o la pared queda muy fina para el rebaje) — probá otro lado, o hacelo a "
                    f"mano con una mecha."
                )
        else:
            carcasa = trimesh.boolean.difference([carcasa, agujero], engine="manifold")
            info.append(
                f"Agujero de {agujero_cable_diam_mm:.0f}mm para el cable en la pared "
                f"({agujero_cable_lado}) — la tapa queda lisa, solo para cerrar."
            )

    contenido_2d = poly
    malla_nombre = None
    if agregar_nombre and texto_nombre.strip():
        nombre_poly, _ = _armar_nombre_cursiva(poly, texto_nombre, ruta_ttf_nombre, alto_nombre_mm, raster_px)
        if nombre_poly is None:
            info.append(f"No se pudo extraer el nombre {texto_nombre!r} (probá otra fuente) — sigo sin él.")
        else:
            contenido_2d = unary_union([contenido_2d, nombre_poly])
            piezas_nombre = mesh3d.piezas_desde_geom(nombre_poly, profundidad_nombre_mm)
            malla_nombre = trimesh.util.concatenate(piezas_nombre) if len(piezas_nombre) > 1 else piezas_nombre[0]

    # La pata (si hay soporte) se suelda a la pieza que quede más abajo del conjunto
    # (el nombre, si está agregado — normalmente termina siendo el borde inferior de
    # todo; si no, la letra) — así lo que se apoya en la mesa es esa misma pieza.
    pieza_soporte = None
    if agregar_soporte:
        poly_con_pata, ancho_pata_mm = geometry.agregar_pata_escritorio(
            contenido_2d, ancho_pata_mm=ancho_pata_mm, alto_pata_mm=alto_pata_mm
        )
        pata_poly = poly_con_pata.difference(contenido_2d)
        profundidad_pata_mm = profundidad_nombre_mm if malla_nombre is not None else profundidad_mm
        piezas_pata = mesh3d.piezas_desde_geom(pata_poly, profundidad_pata_mm)
        if piezas_pata:
            pata_solida = trimesh.util.concatenate(piezas_pata) if len(piezas_pata) > 1 else piezas_pata[0]
            if malla_nombre is not None:
                malla_nombre = trimesh.boolean.union([malla_nombre, pata_solida], engine="manifold")
            else:
                carcasa = trimesh.boolean.union([carcasa, pata_solida], engine="manifold")
        info.append(
            f"Pata de {ancho_pata_mm:.0f}mm agregada abajo (sólida, sin hueco) para encastrar en "
            f"la base de escritorio (STL aparte) — para las letras que no se paran solas."
        )
    else:
        profundidad_pata_mm = profundidad_mm

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
    piezas_preview = [carcasa] + [m for m, _ in piezas_deco] + ([malla_nombre] if malla_nombre is not None else [])
    if len(piezas_preview) > 1:
        _guardar_preview(ruta_png, trimesh.util.concatenate(piezas_preview), f"Letra {texto!r}")
    else:
        _guardar_preview(ruta_png, carcasa, f"Letra {texto!r}")

    pieza_nombre = None
    ruta_3mf_nombre = None
    if malla_nombre is not None:
        ruta_nombre = os.path.join(carpeta_salida, f"letra_{base_nombre}_nombre.stl")
        malla_nombre.export(ruta_nombre)
        pieza_nombre = {
            "ruta_stl": ruta_nombre,
            "vertices": len(malla_nombre.vertices),
            "watertight": malla_nombre.is_watertight,
        }
        if nombre_tiene_ams:
            ruta_3mf_nombre = os.path.join(carpeta_salida, f"letra_{base_nombre}_con_nombre.3mf")
            pieza.exportar_multicolor_3mf([carcasa, malla_nombre], ruta_3mf_nombre)
            info.append(
                "Nombre + letra combinados en un .3mf ya pintado por color (abre directo en "
                "Bambu Studio) — para imprimir de un saque con AMS."
            )
        else:
            info.append(
                f"Nombre exportado como STL aparte ({os.path.basename(ruta_nombre)}) para pegar "
                f"a mano de otro color después de imprimir."
            )

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
            ancho_pata_mm, profundidad_pata_mm, alto_pata_mm, f"letra_{base_nombre}", carpeta_salida
        )

    pieza_tapa = None
    if agregar_tapa:
        malla_tapa = _armar_tapa(poly, tapa_espesor_mm, holgura_tapa_mm)
        ruta_tapa = os.path.join(carpeta_salida, f"letra_{base_nombre}_tapa.stl")
        malla_tapa.export(ruta_tapa)
        pieza_tapa = {
            "ruta_stl": ruta_tapa,
            "vertices": len(malla_tapa.vertices),
            "watertight": malla_tapa.is_watertight,
        }
        info.append(
            "Tapa agregada (STL aparte) para cerrar el hueco después de meter el LED — encastra "
            "en el rebaje de la carcasa."
        )

    minx, miny, minz = carcasa.bounds[0]
    maxx, maxy, maxz = carcasa.bounds[1]
    piezas_para_bounds = [m for m, _ in piezas_deco] + ([malla_nombre] if malla_nombre is not None else [])
    for m in piezas_para_bounds:
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
        "pieza_nombre": pieza_nombre,
        "ruta_3mf_nombre": ruta_3mf_nombre,
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
    if r["pieza_nombre"]:
        print(f"  ✓ STL (nombre) -> {r['pieza_nombre']['ruta_stl']}")
    if r["ruta_3mf_nombre"]:
        print(f"  ✓ 3MF (letra + nombre, para AMS) -> {r['ruta_3mf_nombre']}")
    if r["ruta_stl_decoraciones_multicolor"]:
        print(f"  ✓ STL (decoraciones multicolor) -> {r['ruta_stl_decoraciones_multicolor']}")
    for d in r["decoraciones"]:
        print(f"  ✓ STL (decoración {d['nombre']}) -> {d['ruta_stl']}")
    print(f"  ✓ preview -> {r['ruta_png']}")
    print(f"  {'✓' if r['entra_a1'] else '⚠'} {r['mensaje_a1']}")
    print()
