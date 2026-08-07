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

# Los 5 formatos clásicos de identidad visual (Pictórico/Isotipo,
# Monográfico/Monograma, Combinado/Imagotipo-Isologo, Emblema — de los 7 de
# la infografía típica de "tipos de logo", los otros 2 -Abstracto y
# Mascota- son sobre QUÉ ícono elegís, no sobre la estructura, ya cubiertos
# por la lista de formas + emoji/símbolo + SVG/imagen propia), todos
# armados con la misma geometría (texto + ícono + borde + aro) pero
# combinados distinto:
# - imagotipo: texto e ícono, uno al lado del otro (independientes entre sí,
#   se podrían usar por separado) — el comportamiento de siempre.
# - isologo: texto e ícono, pero fusionados en una sola unidad (el ícono
#   centrado ENCIMA del texto en vez de al costado).
# - isotipo: solo el ícono, sin texto — no todo logo necesita nombre.
# - monograma: solo texto (2-3 iniciales), superpuestas/entrelazadas con
#   espaciado negativo (misma técnica que ya usa el ambigrama para achicar
#   palabras largas en cajas angostas), con un anillo circular opcional.
# - emblema: texto y/o ícono (como isologo, o isotipo si no hay texto)
#   encerrados en un anillo circular tipo insignia (Starbucks, Warner
#   Bros) — mismo anillo que monograma, `_agregar_marco`.
MODOS_LOGO = ("imagotipo", "isologo", "isotipo", "monograma", "emblema")


def _posicion_decoracion(minx, maxx, maxy, cy, decoracion_lado, decoracion_tam):
    if decoracion_lado == "izquierda":
        return minx - decoracion_tam - 3, cy
    elif decoracion_lado == "arriba":
        return (minx + maxx) / 2, maxy + decoracion_tam * 0.4
    else:  # derecha
        return maxx + decoracion_tam + 1, cy


def _resolver_forma_decoracion(decoracion, decoracion_tam, decoracion_svg, decoracion_emoji,
                                decoracion_imagen=None, imagen_umbral=128, imagen_invertir=False):
    """Devuelve el polígono de la decoración elegida (SVG > imagen propia >
    emoji > lista), o None si es "ninguno". Centrada en el origen en los 4
    casos (mismo contrato que core/decoraciones.py::forma*)."""
    if decoracion_svg:
        forma_deco = decoraciones.forma_desde_svg(decoracion_svg, decoracion_tam)
        if forma_deco is None:
            raise ValueError(f"no se pudo sacar ninguna forma con área del SVG: {decoracion_svg}")
        return forma_deco
    if decoracion_imagen:
        forma_deco = decoraciones.forma_desde_imagen(
            decoracion_imagen, decoracion_tam, umbral=imagen_umbral, invertir=imagen_invertir
        )
        if forma_deco is None:
            raise ValueError(
                f"no se pudo sacar ninguna forma con área de la imagen: {decoracion_imagen} "
                f"(probá tocar el umbral o tildar \"invertir\")"
            )
        return forma_deco
    if decoracion_emoji:
        forma_deco = decoraciones.forma_desde_emoji(decoracion_emoji, decoracion_tam)
        if forma_deco is None:
            raise ValueError(f"no encontré el emoji/símbolo {decoracion_emoji!r} en la fuente — probá otro")
        return forma_deco
    if decoracion != "ninguno":
        return decoraciones.forma(decoracion, decoracion_tam)
    return None


def _agregar_marco(contenido, anillo_mm):
    """Encierra `contenido` en un anillo circular tipo insignia/emblema de
    `anillo_mm` de grosor (Starbucks, Warner Bros) — o lo devuelve tal
    cual si `anillo_mm <= 0`."""
    if anillo_mm <= 0:
        return contenido
    minx, miny, maxx, maxy = contenido.bounds
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    radio_ext = max(maxx - minx, maxy - miny) / 2 + anillo_mm * 2.2
    anillo = Point(cx, cy).buffer(radio_ext, resolution=64).difference(
        Point(cx, cy).buffer(radio_ext - anillo_mm, resolution=64)
    )
    return unary_union([contenido, anillo])


def _armar_base_con_aro(contenido, aro_lado, aro_r, borde_mm):
    """Borde + orejas de aro alrededor de `contenido` — el mismo cierre
    final para los 4 modos de logo, la parte que no cambia entre uno y
    otro."""
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
    return base


def _armar_geometria(nombre, ruta_ttf, alto_mm, decoracion, decoracion_lado, decoracion_tam,
                      deco_x, deco_y, aro_lado, aro_r, borde_mm, raster_px,
                      decoracion_svg=None, decoracion_emoji=None,
                      decoracion_imagen=None, imagen_umbral=128, imagen_invertir=False,
                      modo_logo="imagotipo", espaciado_monograma=-0.15, anillo_mm=0.0):
    """Arma la geometría 2D del llavero/logo — contenido según `modo_logo`
    (ver MODOS_LOGO) y base = contenido con borde + orejas de aro
    (`_armar_base_con_aro`, igual en los 5 modos). Devuelve (contenido,
    base, ancho_mm, alto_mm_real).

    - "imagotipo"/"isologo": texto (`nombre`) + ícono opcional (SVG >
      imagen propia > emoji > `decoracion` de la lista,
      `_resolver_forma_decoracion`) — en imagotipo el ícono va al
      costado (`decoracion_lado`), en isologo centrado encima del texto
      (fusionados).
    - "isotipo": solo el ícono (`nombre` se ignora) — hace falta elegir
      uno (SVG, imagen, emoji o de la lista; "ninguno" no alcanza).
    - "monograma": solo `nombre` (pensado para 2-3 iniciales), con
      `espaciado_monograma` (negativo = se superponen/entrelazan, misma
      técnica que el espaciado del ambigrama) y un anillo circular de
      `anillo_mm` de grosor si es > 0 (`_agregar_marco`).
    - "emblema": como isologo (o isotipo si no hay `nombre`), pero
      siempre encerrado en el anillo de `_agregar_marco` — el formato
      insignia (Starbucks, Warner Bros)."""
    forma_deco_kwargs = dict(
        decoracion_svg=decoracion_svg, decoracion_emoji=decoracion_emoji,
        decoracion_imagen=decoracion_imagen, imagen_umbral=imagen_umbral, imagen_invertir=imagen_invertir,
    )

    if modo_logo == "isotipo":
        forma_deco = _resolver_forma_decoracion(decoracion, decoracion_tam, **forma_deco_kwargs)
        if forma_deco is None:
            raise ValueError("elegí una decoración, imagen, emoji o SVG para el isotipo (no lleva texto)")
        contenido = translate(forma_deco, xoff=deco_x, yoff=deco_y)
        minx, miny, maxx, maxy = contenido.bounds
        ancho_mm, alto_mm_real = maxx - minx, maxy - miny

    elif modo_logo == "monograma":
        crudo = texto2d.texto_a_poligono_crudo(nombre, ruta_ttf, raster_px, espaciado_relativo=espaciado_monograma)
        if crudo is None:
            raise ValueError("no se pudo extraer las iniciales (probá otra fuente)")
        contenido, ancho_mm = texto2d.escalar_a_alto(crudo, alto_mm)
        alto_mm_real = contenido.bounds[3] - contenido.bounds[1]
        contenido = _agregar_marco(contenido, anillo_mm)

    elif modo_logo == "emblema":
        texto_poly = None
        if nombre.strip():
            texto_poly, _ = texto2d.texto_a_poligono(nombre, ruta_ttf, alto_mm, raster_px)
            if texto_poly is None:
                raise ValueError("no se pudo extraer el texto (probá otra fuente o subí la resolución)")
        forma_deco = _resolver_forma_decoracion(decoracion, decoracion_tam, **forma_deco_kwargs)
        if texto_poly is None and forma_deco is None:
            raise ValueError("el emblema necesita texto y/o una decoración/imagen/emoji/SVG")

        if texto_poly is not None and forma_deco is not None:
            minx, miny, maxx, maxy = texto_poly.bounds
            cy = (miny + maxy) / 2
            forma_deco = translate(forma_deco, xoff=(minx + maxx) / 2 + deco_x, yoff=cy + deco_y)
            contenido = unary_union([texto_poly, forma_deco])
        elif texto_poly is not None:
            contenido = texto_poly
        else:
            contenido = translate(forma_deco, xoff=deco_x, yoff=deco_y)

        minx, miny, maxx, maxy = contenido.bounds
        ancho_mm, alto_mm_real = maxx - minx, maxy - miny
        contenido = _agregar_marco(contenido, anillo_mm if anillo_mm > 0 else 3.0)

    else:  # imagotipo / isologo
        texto_poly, ancho_mm = texto2d.texto_a_poligono(nombre, ruta_ttf, alto_mm, raster_px)
        if texto_poly is None:
            raise ValueError("no se pudo extraer el texto (probá otra fuente o subí la resolución)")
        minx, miny, maxx, maxy = texto_poly.bounds
        cy = (miny + maxy) / 2
        alto_mm_real = maxy - miny

        contenido = texto_poly
        forma_deco = _resolver_forma_decoracion(decoracion, decoracion_tam, **forma_deco_kwargs)
        if forma_deco is not None:
            if modo_logo == "isologo":
                cx_deco, cy_deco = (minx + maxx) / 2, cy
            else:
                cx_deco, cy_deco = _posicion_decoracion(minx, maxx, maxy, cy, decoracion_lado, decoracion_tam)
            forma_deco = translate(forma_deco, xoff=cx_deco + deco_x, yoff=cy_deco + deco_y)
            contenido = unary_union([contenido, forma_deco])

    base = _armar_base_con_aro(contenido, aro_lado, aro_r, borde_mm)
    return contenido, base, ancho_mm, alto_mm_real


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
                    deco_x=0, deco_y=0, aro_lado="izquierda", aro_r=2, borde_mm=3,
                    modo_logo="imagotipo", espaciado_monograma=-0.15, anillo_mm=0.0):
    """Preview 2D instantáneo — solo la geometría plana (`_armar_geometria`),
    SIN mesh3d ni booleanas 3D — para ver el resultado mientras se ajustan
    los parámetros, antes de tocar "Generar llavero" (que sí arma la malla
    3D real y tarda más). No soporta ícono propio en SVG/imagen
    (`decoracion_svg`/`decoracion_imagen`): esas rutas cambian con cada
    archivo subido y no vale la pena cachearlas. Devuelve (png_bytes,
    ancho_mm, alto_mm) o (None, 0, 0) si no se pudo generar."""
    sin_texto_ok = modo_logo in ("isotipo", "emblema")
    if not os.path.exists(ruta_ttf):
        return None, 0, 0
    if not sin_texto_ok and not nombre.strip():
        return None, 0, 0
    if not sin_texto_ok and not decoracion_emoji and decoracion not in decoraciones.NOMBRES_VALIDOS:
        return None, 0, 0
    try:
        contenido, base, ancho_mm, alto_mm_real = _armar_geometria(
            nombre, ruta_ttf, alto_mm, decoracion, decoracion_lado, decoracion_tam,
            deco_x, deco_y, aro_lado, aro_r, borde_mm, raster_px=250, decoracion_emoji=decoracion_emoji,
            modo_logo=modo_logo, espaciado_monograma=espaciado_monograma, anillo_mm=anillo_mm,
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
            decoracion_imagen=None, imagen_umbral=128, imagen_invertir=False,
            deco_x=0, deco_y=0,
            aro_lado="izquierda", aro_r=2,
            espesor_texto_mm=2, espesor_base_mm=3, borde_mm=3,
            tiene_ams=False, raster_px=400,
            modo_logo="imagotipo", espaciado_monograma=-0.15, anillo_mm=0.0,
            carpeta_salida=CARPETA_SALIDA):
    """Arma el llavero/logo directamente con shapely/trimesh y devuelve un
    dict con las rutas, medidas (reales, medidas sobre la geometría) y
    avisos. No pregunta nada ni imprime nada — así lo puede llamar tanto
    la CLI como la app visual.

    `modo_logo` (ver MODOS_LOGO y `_armar_geometria`): "imagotipo"
    (default, texto + ícono al costado, independientes), "isologo"
    (texto + ícono fusionados, centrado uno sobre el otro), "isotipo"
    (solo ícono, sin texto), "monograma" (solo texto/iniciales,
    superpuestas con `espaciado_monograma`, anillo circular opcional de
    `anillo_mm`), "emblema" (texto y/o ícono encerrados en el anillo,
    tipo insignia — no lleva texto obligatorio, como isotipo).

    `decoracion_svg`: ruta a un .svg propio del usuario (ícono/logo
    simple). `decoracion_imagen`: ruta a una imagen rasterizada (PNG/JPG
    — un logo/ícono simple, silueta clara, no una foto;
    core/imagen_import.py la vectoriza por contorno igual que el texto;
    `imagen_umbral`/`imagen_invertir` para logos claros sobre fondo
    oscuro o con umbral de luminosidad distinto). `decoracion_emoji`: un
    emoji/pictograma/signo (un carácter, ej. "✈",
    core/decoraciones.py::forma_desde_emoji). Los tres son excluyentes,
    en ese orden de prioridad si por error vinieran varios a la vez —
    si ninguno viene seteado, se usa `decoracion` de la lista."""
    if not os.path.exists(ruta_ttf):
        raise FileNotFoundError(f"no encuentro la fuente: {ruta_ttf}")
    if modo_logo not in MODOS_LOGO:
        raise ValueError(f"modo_logo debe ser uno de {MODOS_LOGO}, recibí {modo_logo!r}")
    if decoracion_svg:
        if not os.path.exists(decoracion_svg):
            raise FileNotFoundError(f"no encuentro el SVG: {decoracion_svg}")
    elif decoracion_imagen:
        if not os.path.exists(decoracion_imagen):
            raise FileNotFoundError(f"no encuentro la imagen: {decoracion_imagen}")
    elif not decoracion_emoji and decoracion not in decoraciones.NOMBRES_VALIDOS:
        raise ValueError(f"decoracion debe ser una de {decoraciones.NOMBRES_VALIDOS}, recibí {decoracion!r}")
    if modo_logo not in ("isotipo", "emblema") and not nombre.strip():
        raise ValueError("escribí un nombre/texto (o cambiá a modo Isotipo/Emblema)")

    contenido, base, ancho_texto_mm, alto_texto_mm = _armar_geometria(
        nombre, ruta_ttf, alto_mm, decoracion, decoracion_lado, decoracion_tam,
        deco_x, deco_y, aro_lado, aro_r, borde_mm, raster_px,
        decoracion_svg=decoracion_svg, decoracion_emoji=decoracion_emoji,
        decoracion_imagen=decoracion_imagen, imagen_umbral=imagen_umbral, imagen_invertir=imagen_invertir,
        modo_logo=modo_logo, espaciado_monograma=espaciado_monograma, anillo_mm=anillo_mm,
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
    ruta_3mf_multicolor = None
    if tiene_ams:
        # El .3mf pintado (ver core/exportar_3mf.py) es la opción recomendada: abre
        # directo en Bambu Studio con los colores ya puestos. El .stl combinado queda
        # como respaldo (por si alguien lo necesita en otro slicer) — los slicers
        # re-acomodan cada STL que importás por separado, así que 2 archivos sueltos NO
        # quedan alineados aunque el archivo diga que van pegados; con el combinado, al
        # menos queda un solo import con las piezas en su lugar, aunque dividirlo en
        # objetos para pintarlas resultó frágil en la práctica.
        ruta_3mf_multicolor = os.path.join(carpeta_salida, f"{base_nombre}_multicolor.3mf")
        pieza.exportar_multicolor_3mf([malla_base, malla_texto], ruta_3mf_multicolor)
        ruta_stl_multicolor = os.path.join(carpeta_salida, f"{base_nombre}_multicolor.stl")
        pieza.exportar_multicolor([malla_base, malla_texto], ruta_stl_multicolor)
        info = [
            "Con AMS: descargá el .3mf multicolor — abre directo en Bambu Studio con los "
            "colores ya asignados (base y texto/decoración), sin dividir nada a mano. Si "
            "preferís el STL combinado (para otro slicer), también está: clic derecho → "
            "\"Partir en objetos\" y asignales color ahí."
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
        "ruta_3mf_multicolor": ruta_3mf_multicolor,
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
    if r["ruta_3mf_multicolor"]:
        print(f"  ✓ 3MF (multicolor, para AMS, recomendado) -> {r['ruta_3mf_multicolor']}")
    if r["ruta_stl_multicolor"]:
        print(f"  ✓ STL (multicolor, respaldo) -> {r['ruta_stl_multicolor']}")
    print(f"  {'✓' if r['entra_a1'] else '⚠'} {r['mensaje_a1']}")
    print()
