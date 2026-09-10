#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/importador_escudos.py
------------------
Importador de escudos -- Parte A: entrada unificada.

Normaliza un escudo (SVG o PNG) a un formato de trabajo común: un
canvas raster de `ancho_px` x `alto_px` más una lista `capas` de
(color_hex, máscara_booleana) del mismo tamaño -- UN SOLO camino para
los dos formatos, ambos terminan pasando por
`core.imagen_import._preparar_capas_color` (resize + cuantización):

- SVG: se RENDERIZA completo con `resvg_py` (Rust, sin dependencia de
  Cairo/GTK nativo -- a diferencia de `cairosvg`, que en este Windows
  tira `OSError: no library called "cairo-2"`) a un PNG en memoria, que
  después se recorta al contenido real y se trata IGUAL que un PNG
  subido (ver `_renderizar_svg`). Reemplaza el enfoque anterior
  (`svgelements`, forma por forma, preservando z-order) que no podía
  resolver bien escudos oficiales reales: rayas definidas por STROKE en
  vez de relleno (Unión oficial), o un color de sombra que en el
  renderizado final queda tapado por el z-order (Boca) -- renderizar
  resuelve ambos casos gratis, porque es lo que hace cualquier visor.
  `core/svg_import.py` (el lector forma-por-forma) NO se toca -- lo
  sigue usando tal cual la decoración multicolor del Topper.
- PNG: un PNG ya cuantizado es exclusivo por construcción (cada píxel
  tiene UN solo índice de color).

El precio de renderizar es que el antialiasing dejar píxeles "mezcla"
en los bordes entre colores, que cuantizan como su PROPIO balde de
color (a veces con un RGB lejos de los dos colores reales que se
mezclaron) -- `limpiar_antialiasing` (más abajo) resuelve esto DESPUÉS
de armar las capas, para los dos formatos por igual.

Esta capa NO resuelve exclusividad entre capas que se pisen (eso es la
Parte B) -- para SVG renderizado o PNG cuantizado ya llegan exclusivas
por construcción (cada píxel un solo índice), así que en la práctica B
es un no-op para los dos -- pero igual se llama, no hay rama especial.
"""

import datetime
import io

import numpy as np
import resvg_py
from PIL import Image, ImageDraw
from scipy import ndimage

from core import colores, imagen_import

TAMANO_TRABAJO_PX = 500  # lado mayor del canvas final -- verificado a mano (500-600px) en Unión/River/Boca
RENDER_ANCHO_PX = 2000  # ancho del renderizado INTERNO de un SVG, bien por encima de TAMANO_TRABAJO_PX --
# el viewBox/width/height declarados en el archivo no siempre encierran ajustado el dibujo (un SVG
# "mal formado" puede declarar un ancho/alto que no guarda la proporción del viewBox, ver el caso real
# de River: resvg lo resuelve con letterboxing, dejando margen transparente de sobra) -- 2000px de
# margen de sobra ANTES de recortar al contenido real (ver `_renderizar_svg`) evita perder resolución
# efectiva por ese margen; después se reescala al tamaño final igual que un PNG subido.


def _es_svg(ruta):
    return ruta.lower().endswith(".svg")


def cargar_escudo(ruta, resolucion_px=TAMANO_TRABAJO_PX):
    """Normaliza `ruta` (SVG o PNG) a `(ancho_px, alto_px, capas)` --
    `capas`: lista de (color_hex, máscara_booleana) de forma
    `(alto_px, ancho_px)` cada una (convención numpy/PIL: filas =
    alto), YA limpias de ruido de antialiasing (`limpiar_antialiasing`).
    `resolucion_px` es el lado MAYOR del canvas final -- default 500,
    pero el importador puede pedir más (600-700) si a 500 se pierden
    detalles finos (letras internas chicas)."""
    fuente = _renderizar_svg(ruta) if _es_svg(ruta) else ruta
    if fuente is None:
        return resolucion_px, resolucion_px, []

    alto_px, ancho_px, indices, paleta, mascara_valida, area_minima = imagen_import._preparar_capas_color(
        fuente, resolucion_px, imagen_import.COLORES_DETECCION_DEFAULT)
    if indices is None:
        return ancho_px, alto_px, []

    capas = []
    for idx in sorted(set(indices[mascara_valida].tolist())):
        mascara_color = (indices == idx) & mascara_valida
        if int(mascara_color.sum()) < area_minima:
            continue
        r, g, b = paleta[idx * 3], paleta[idx * 3 + 1], paleta[idx * 3 + 2]
        capas.append((f"#{r:02x}{g:02x}{b:02x}", mascara_color))
    return ancho_px, alto_px, limpiar_antialiasing(capas)


def _renderizar_svg(ruta_svg, render_px=RENDER_ANCHO_PX):
    """SVG -> buffer PNG en memoria (BytesIO), recortado al contenido
    real -- listo para pasar por el MISMO camino que un PNG subido
    (`imagen_import._preparar_capas_color`). `None` si el render no dejó
    ningún píxel con tinta (archivo vacío/roto).

    El recorte al bounding box real (canal alfa > 16) es necesario, no
    cosmético: `resvg_py.svg_to_bytes(width=...)` respeta el
    `viewBox`/`width`/`height` declarados en el archivo (con
    letterboxing si no guardan la misma proporción entre sí, caso real
    encontrado en un SVG de River) -- sin recortar, ese margen le resta
    resolución efectiva al escudo en vez de a un fondo vacío."""
    datos_png = bytes(resvg_py.svg_to_bytes(svg_path=ruta_svg, width=render_px))
    imagen = Image.open(io.BytesIO(datos_png)).convert("RGBA")
    alfa = np.array(imagen)[:, :, 3]
    tinta = alfa > 16
    if not tinta.any():
        return None

    filas, columnas = np.where(tinta)
    recorte = imagen.crop((int(columnas.min()), int(filas.min()), int(columnas.max()) + 1, int(filas.max()) + 1))
    buffer = io.BytesIO()
    recorte.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


UMBRAL_CONFIANZA_COLOR = 0.05  # fracción del área total de tinta bajo la cual un color cuantizado
# se considera "dudoso" (ruido de antialiasing/cuantización, no un color real del diseño) -- ver
# `limpiar_antialiasing`. Validado a mano contra los 3 escudos oficiales: separa bien el ruido sin
# comerse ningún color chico real en esos casos.


def limpiar_antialiasing(capas, umbral_confianza=UMBRAL_CONFIANZA_COLOR, tolerancia_fusion=colores.TOLERANCIA_FUSION_COLOR):
    """`capas`: [(color_hex, máscara), ...] EXCLUYENTES entre sí, recién
    cuantizadas (SVG renderizado o PNG). Necesario para separar bien los
    colores de un escudo RENDERIZADO: el antialiasing entre dos colores
    reales deja una franja de píxeles "mezcla" que la cuantización
    agrupa como su PROPIO balde de color -- a veces un tono casi
    idéntico a uno de los dos reales (simple ruido de cuantización,
    ej. `#ef1f26` al lado de `#ed1c24`), pero a veces una mezcla que en
    RGB queda más lejos de AMBOS colores reales que cualquier tolerancia
    seguía de fusión (medido en Unión oficial: la mezcla rojo-blanco
    cae a ~124 de distancia del rojo y ~192 del blanco). Se resuelve en
    dos pasadas, EN ESTE ORDEN (importa cuál va primero -- ver más
    abajo):

    1. Fusión por color: agrupa por distancia RGB (mismo criterio que
       `core.colores.fusionar_colores_cercanos`, pero a nivel máscara
       en vez de polígono -- acá todavía no se vectorizó, eso es la
       Parte D). Va PRIMERO porque un color cuantizado puede partirse
       en varios baldes casi idénticos por puro ruido de cuantización
       (Unión oficial dio 7 baldes de rojo, todos a menos de 17 de
       distancia RGB entre sí) -- si se filtrara por confianza ANTES de
       fusionar, cada balde chico se trataría como "dudoso" por
       separado y se reasignaría por cercanía espacial en vez de por
       ser, ya de por sí, el mismo color: en Unión oficial esto hacía
       que ~9 puntos porcentuales de rojo genuino terminaran mal
       reasignados a blanco (49.8% real bajaba a 45.2%) -- fusionando
       primero da 50.4%/49.6%, la proporción esperada.
    2. Confianza + reasignación espacial: de lo que quedó tras fusionar,
       un color cuya máscara cubre menos de `umbral_confianza` del área
       total de tinta se considera "dudoso" -- ya no ruido de
       cuantización (eso lo resolvió el paso 1), sino una mezcla real
       de antialiasing. Cada píxel dudoso se reasigna al color
       CONFIABLE espacialmente más cercano
       (`scipy.ndimage.distance_transform_edt`, mismo enfoque que
       `imagen_import._detectar_fondo_solido`) -- resuelve la mezcla
       sin importar su RGB, porque el ruido de antialiasing siempre
       está pegado a la zona real de la que es borde."""
    if not capas:
        return capas
    fusionadas = _fusionar_capas_cercanas(capas, tolerancia_fusion)
    area_total = sum(int(m.sum()) for _, m in fusionadas)
    if area_total == 0:
        return fusionadas

    confiables = [(c, m.copy()) for c, m in fusionadas if m.sum() >= umbral_confianza * area_total]
    dudosas = [(c, m) for c, m in fusionadas if m.sum() < umbral_confianza * area_total]

    if not dudosas:
        return fusionadas
    if not confiables:
        # caso degenerado (no debería pasar en un escudo real: significa
        # que NINGÚN color junta un 5% del área) -- no hay a quién
        # reasignar, se deja como está para no perder tinta.
        return fusionadas

    alto, ancho = confiables[0][1].shape
    etiquetas = np.zeros((alto, ancho), dtype=np.int32)
    for i, (_, m) in enumerate(confiables, start=1):
        etiquetas[m] = i
    sin_etiqueta = etiquetas == 0
    _, (filas, columnas) = ndimage.distance_transform_edt(sin_etiqueta, return_indices=True)
    etiquetas_cercanas = etiquetas[filas, columnas]

    mascara_dudosa_total = np.zeros((alto, ancho), dtype=bool)
    for _, m in dudosas:
        mascara_dudosa_total |= m
    for i in range(len(confiables)):
        confiables[i][1][mascara_dudosa_total & (etiquetas_cercanas == i + 1)] = True

    confiables.sort(key=lambda cm: -int(cm[1].sum()))
    return confiables


def _fusionar_capas_cercanas(capas, tolerancia):
    """Análogo a `core.colores.fusionar_colores_cercanos` pero a nivel
    máscara (antes de vectorizar) en vez de polígono. El ancla de cada
    grupo es SIEMPRE la máscara más grande -- a diferencia de la
    función de la que es análoga (que ancla en el primer candidato que
    abre el grupo, sea grande o chico, ver su propio docstring), acá se
    ordena por área ANTES de agrupar: como el primer miembro que abre
    cada grupo ya es el más grande, el ancla sale bien sin tener que
    promediar ni reemplazar nada después."""
    capas_ordenadas = sorted(capas, key=lambda cm: -int(cm[1].sum()))
    grupos = []
    for color_hex, mascara in capas_ordenadas:
        rgb = colores._rgb(color_hex)
        grupo_encontrado = None
        for grupo in grupos:
            dist = sum((a - b) ** 2 for a, b in zip(rgb, grupo["rgb"])) ** 0.5
            if dist < tolerancia:
                grupo_encontrado = grupo
                break
        if grupo_encontrado is not None:
            grupo_encontrado["mascara"] = grupo_encontrado["mascara"] | mascara
        else:
            grupos.append({"mascara": mascara.copy(), "color_hex": color_hex, "rgb": rgb})
    grupos.sort(key=lambda g: -int(g["mascara"].sum()))
    return [(g["color_hex"], g["mascara"]) for g in grupos]


def _rasterizar_poligono(poligono, ancho_px, alto_px, transformar):
    """Rellena `poligono` (shapely, puede tener agujeros e incluir
    varias partes si es Multi) sobre una máscara booleana de
    `alto_px` x `ancho_px` -- PIL alcanza para esto, no hace falta
    `rasterio`. Los agujeros del polígono (huecos por fill-rule DENTRO
    de un mismo elemento SVG, ver `core.svg_import`) se pintan en 0
    después del relleno.

    Cada parte de un MultiPolygon se rasteriza en su PROPIO canvas
    limpio y se combinan con OR (numpy) -- NUNCA todas sobre un mismo
    canvas compartido, dibujando una tras otra. Si se comparte el
    canvas, el agujero de una parte que geométricamente encierra a OTRA
    parte disjunta (ej. una zona-anillo grande, tipo el contorno de un
    escudo, cuyo hueco contiene islas más chicas de la misma zona) borra
    esa otra parte al pintar el agujero en 0 -- aunque como formas
    FINALES sean disjuntas entre sí, el canvas compartido no lo sabe
    hasta que ya es tarde. Encontrado al validar la Parte D (ida y
    vuelta vectorización) sobre una zona real de Unión con 8 partes."""
    partes = poligono.geoms if hasattr(poligono, "geoms") else [poligono]
    mascara = np.zeros((alto_px, ancho_px), dtype=bool)
    for parte in partes:
        if parte.is_empty:
            continue
        img = Image.new("1", (ancho_px, alto_px), 0)
        draw = ImageDraw.Draw(img)
        draw.polygon([transformar(pt) for pt in parte.exterior.coords], fill=1)
        for interior in parte.interiors:
            draw.polygon([transformar(pt) for pt in interior.coords], fill=0)
        mascara |= np.array(img, dtype=bool)
    return mascara


# ---------------------------------------------------------------------------
# Parte B: separación excluyente por zonas
# ---------------------------------------------------------------------------

def separar_zonas_excluyentes(capas):
    """Capas de la Parte A (en z-order) -> zonas EXCLUYENTES por color
    final, listas para asignarles hueco/filamento (Parte C/G). Resuelve
    el apilado real de un SVG (para PNG es un no-op, ver
    `_resolver_exclusividad`) y DESPUÉS agrupa por color -- nunca al
    revés, ver `agrupar_por_color`."""
    return agrupar_por_color(_resolver_exclusividad(capas))


def _resolver_exclusividad(capas):
    """Cada capa se queda con su máscara MENOS la unión de las capas
    que están ENCIMA (índice mayor = dibujada después = más arriba en
    z-order). Recorre de ATRÁS para ADELANTE acumulando "lo que hay
    encima" para no recalcular esa unión en cada paso.

    Para PNG (Parte A ya las entrega mutuamente excluyentes, cada
    píxel con un solo índice de color) esto es un NO-OP matemático: la
    máscara de cualquier capa nunca comparte un píxel con una de índice
    mayor, así que `mascara & ~encima == mascara` siempre -- no hay una
    rama especial para PNG, pasa por acá igual."""
    if not capas:
        return []
    encima = np.zeros_like(capas[0][1])
    exclusivas = [None] * len(capas)
    for i in range(len(capas) - 1, -1, -1):
        color, mascara = capas[i]
        exclusivas[i] = (color, mascara & ~encima)
        encima = encima | mascara
    return exclusivas


def agrupar_por_color(capas_exclusivas):
    """Une en una sola zona todas las capas EXCLUYENTES que terminaron
    del mismo color -- SIEMPRE después de resolver exclusividad (nunca
    antes): si dos formas del mismo color están separadas en el
    documento por una forma de OTRO color en el medio (rojo, blanco,
    rojo), agrupar antes calcularía mal qué hay "encima" de cada una
    (el blanco quedaría adentro de un rojo combinado en vez de encima
    de una de sus partes). Como las máscaras excluyentes ya son
    disjuntas entre sí (ninguna comparte un píxel con otra, sea del
    color que sea), unir las de un mismo color nunca genera
    solapamiento con una zona de otro color. Descarta capas que hayan
    quedado sin ningún píxel (tapadas del todo). Orden: primera
    aparición en `capas_exclusivas` (de atrás/abajo del z-order)."""
    zonas, orden = {}, []
    for color, mascara in capas_exclusivas:
        if not mascara.any():
            continue
        if color not in zonas:
            zonas[color] = mascara.copy()
            orden.append(color)
        else:
            zonas[color] = zonas[color] | mascara
    return [(color, zonas[color]) for color in orden]


# ---------------------------------------------------------------------------
# Parte C: detección de huecos internos
# ---------------------------------------------------------------------------

def detectar_huecos_internos(zonas):
    """Sobre las zonas EXCLUYENTES de B: arma el "vacío" (píxeles sin
    ninguna zona asignada), lo separa en componentes conexas
    (`scipy.ndimage.label`) y devuelve solo los huecos INTERNOS -- los
    que no tocan el borde del canvas (fondo real del escudo, ej. el
    blanco de un SVG que no lo trae como forma propia, solo lo deja
    como hueco encerrado) -- descartando tanto el AIRE (toca el borde,
    es el afuera del escudo) como el ruido de antialiasing.

    El ruido se filtra con el MISMO criterio ya establecido en
    `core.imagen_import` (`AREA_MINIMA_FRACCION` del área de tinta,
    con piso en `AREA_MINIMA_PX`) -- NO hace falta resolver la fusión
    de colores casi-iguales (idea 14) antes de esto: se comprobó que
    ese ruido son píxeles que nunca llegaron a tener zona asignada (no
    zonas separadas que haya que fusionar), así que un filtro de
    tamaño alcanza.

    Devuelve una lista de máscaras booleanas, una por hueco interno
    significativo, de mayor a menor área -- [] si no hay ninguno (caso
    en que el escudo ya trae su fondo como zona propia)."""
    if not zonas:
        return []
    alto, ancho = zonas[0][1].shape
    tinta = np.zeros((alto, ancho), dtype=bool)
    for _, mascara in zonas:
        tinta |= mascara
    vacio = ~tinta

    area_minima = max(imagen_import.AREA_MINIMA_PX, int(tinta.sum()) * imagen_import.AREA_MINIMA_FRACCION)

    etiquetas, n_etiquetas = ndimage.label(vacio)
    etiquetas_borde = (
        set(etiquetas[0, :].tolist()) | set(etiquetas[-1, :].tolist())
        | set(etiquetas[:, 0].tolist()) | set(etiquetas[:, -1].tolist())
    ) - {0}

    huecos = [
        etiquetas == lbl
        for lbl in range(1, n_etiquetas + 1)
        if lbl not in etiquetas_borde and int((etiquetas == lbl).sum()) >= area_minima
    ]
    huecos.sort(key=lambda m: -int(m.sum()))
    return huecos


# ---------------------------------------------------------------------------
# Parte D: vectorización con evenodd
# ---------------------------------------------------------------------------

def vectorizar_zonas(zonas):
    """`zonas`: [(color_hex, máscara), ...] -- de B (zonas excluyentes),
    o de B + los huecos de C ya asignados a un color en la UI (Parte
    G). Devuelve [(color_hex, polígono_shapely), ...] -- cada polígono
    ya resuelto con sus agujeros REALES (fill-rule evenodd) vía
    `core.imagen_import._mascara_a_poligono` (marching squares +
    `core.poligonos.combinar_con_huecos`) -- reusado tal cual, D no
    reimplementa la vectorización, solo la aplica por color. Una zona
    con varias piezas separadas (ej. las franjas de un escudo) da un
    `MultiPolygon`, cada parte con sus propios agujeros -- no una unión
    rellena. Descarta colores cuya máscara no haya dado ningún polígono
    con área (no debería pasar viniendo de B/C, pero por las dudas)."""
    resultado = []
    for color, mascara in zonas:
        poligono = imagen_import._mascara_a_poligono(mascara)
        if poligono is not None and not poligono.is_empty and poligono.area > 0:
            resultado.append((color, poligono))
    return resultado


# ---------------------------------------------------------------------------
# Parte E: construcción del SVG final
# ---------------------------------------------------------------------------

COLOR_HUECO_DEFAULT = "#ffffff"  # el fondo real de un escudo (el hueco) suele ser blanco --
# confirmado que "el color de mayor área ya existente" da MAL en River (dio negro en vez
# de blanco) -- ver plan de Parte E. La usuaria lo cambia en la UI real (Parte G).


def armar_zonas_finales(zonas, huecos, color_hueco_default=COLOR_HUECO_DEFAULT, colores_por_hueco=None):
    """Zonas EXCLUYENTES de B + huecos internos de C, con un color
    ASIGNADO a cada hueco. Vuelve a pasar por `agrupar_por_color` (reusa
    B, no reinventa la fusión) por si un color asignado coincide con una
    zona que ya existe -- no duplica `<path>` en ese caso.

    `colores_por_hueco`: opcional, lista PARALELA a `huecos` (mismo
    orden, mismo largo) con lo que eligió la usuaria en la UI real
    (Parte G) para CADA hueco -- un hex, o `None` para "calado" (sin
    filamento: ese hueco NO se agrega como zona, queda geometría vacía
    de verdad en el SVG final, no una zona de color). Si no se pasa
    (default `None`), se comporta EXACTAMENTE como antes de la Parte G:
    todos los huecos van a `color_hueco_default` -- ningún llamador
    existente (ni sus tests) nota el cambio."""
    if colores_por_hueco is not None:
        assert len(colores_por_hueco) == len(huecos), "colores_por_hueco debe ser paralela a huecos"
        con_color = list(zonas) + [
            (color, hueco) for color, hueco in zip(colores_por_hueco, huecos) if color is not None
        ]
    else:
        con_color = list(zonas) + [(color_hueco_default, hueco) for hueco in huecos]
    return agrupar_por_color(con_color)


def _poligono_a_path_svg(poligono, alto_px):
    """(Multi)Polygon shapely -> el contenido del atributo `d` de un
    `<path>` SVG -- un subtrazado "M ... Z" por cada anillo (exterior +
    agujeros) de cada parte, para que `fill-rule="evenodd"` los pinte
    bien en cualquier visor Y para que el LECTOR propio del proyecto
    (`core.svg_import`, que resuelve huecos por sentido de giro, no por
    el atributo evenodd) los reconstruya igual: invertir Y acá voltea
    el sentido de giro de TODOS los anillos por igual, así la relación
    relativa exterior/agujero (que es lo único que le importa al
    lector) se conserva -- verificado con el escudo real de River.

    Coordenadas: `(x, alto_px - y)` -- MISMA convención que
    `_rasterizar_poligono`, no la de `generators/topper.py` (que usa
    otro sistema, para su propio preview) -- así el `viewBox` de este
    módulo queda en píxeles derechos, sin coordenadas negativas."""
    partes = poligono.geoms if hasattr(poligono, "geoms") else [poligono]
    trozos = []
    for parte in partes:
        if parte.is_empty:
            continue
        for anillo in [parte.exterior] + list(parte.interiors):
            coords = list(anillo.coords)
            if len(coords) < 2:
                continue
            pts = [(x, alto_px - y) for x, y in coords]
            d = f"M {pts[0][0]:.2f},{pts[0][1]:.2f} " + " ".join(
                f"L {x:.2f},{y:.2f}" for x, y in pts[1:]
            ) + " Z"
            trozos.append(d)
    return " ".join(trozos)


def escribir_svg(zonas_finales, ancho_px, alto_px, ruta_salida):
    """Vectoriza `zonas_finales` (ver `armar_zonas_finales`) y escribe
    un SVG "limpio" -- un `<path>` por color, `fill="#rrggbb"` directo
    (sin clases, sin `style`, sin stroke) y `fill-rule="evenodd"` --
    del tipo que `core.svg_import`/el Topper ya leen bien. Incluye un
    comentario XML mínimo de trazabilidad (que el importador lo generó,
    y cuándo) -- `svgelements` lo ignora al leer, no afecta nada."""
    poligonos = vectorizar_zonas(zonas_finales)
    paths = "".join(
        f'<path d="{_poligono_a_path_svg(poligono, alto_px)}" fill="{color}" fill-rule="evenodd"/>'
        for color, poligono in poligonos
    )
    fecha = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    contenido = (
        f"<!-- generado por el Importador de Escudos ({fecha}) -->"
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {ancho_px} {alto_px}">'
        f"{paths}</svg>"
    )
    with open(ruta_salida, "w", encoding="utf-8") as f:
        f.write(contenido)


# ---------------------------------------------------------------------------
# Preview (Parte F/G): pura presentación de zonas/huecos ya calculados,
# sin ningún análisis nuevo -- por eso vive acá y no en la página.
# ---------------------------------------------------------------------------

COLOR_FONDO_PREVIEW = "#1a1a1a"
COLOR_HUECO_PREVIEW = "#ff00ff"  # magenta -- bien distintivo de cualquier color real de escudo


def componer_preview_rgb(zonas, ancho_px, alto_px, huecos=None, colores_huecos=None,
                          color_fondo=COLOR_FONDO_PREVIEW, color_huecos=COLOR_HUECO_PREVIEW):
    """Arma una imagen RGB (numpy `alto_px x ancho_px x 3`, lista para
    `st.image`) pintando cada zona con su propio color real -- sin
    recalcular nada, solo visualiza lo que B/C/G ya armaron.

    Si se pasan `huecos` (lista de máscaras de la Parte C) SIN
    `colores_huecos`, se pintan ENCIMA con `color_huecos` (magenta por
    default) para que se distingan a simple vista del resto del escudo
    -- el comportamiento de F, útil para confirmar a ojo que se detectó
    el fondo real (y no ruido) ANTES de poder asignarles un color de
    verdad en G.

    `colores_huecos`: opcional, lista PARALELA a `huecos` (mismo orden,
    mismo largo) con lo que eligió la usuaria en la UI real (Parte G)
    para CADA hueco -- un hex, o `None` para "calado". Si se pasa, cada
    hueco se pinta con SU color asignado (o con `color_fondo` si es
    calado, para que en el preview "se vea la torta" -- ni magenta ni
    un filamento, el mismo tratamiento visual que el resto del fondo).
    Si no se pasa (default `None`), magenta uniforme como siempre --
    ningún llamador existente nota el cambio."""
    img = np.zeros((alto_px, ancho_px, 3), dtype=np.uint8)
    img[:, :] = colores._rgb(color_fondo)
    for color_hex, mascara in zonas:
        img[mascara] = colores._rgb(color_hex)
    if colores_huecos is not None:
        assert len(colores_huecos) == len(huecos or []), "colores_huecos debe ser paralela a huecos"
        for color_hueco, hueco in zip(colores_huecos, huecos):
            img[hueco] = colores._rgb(color_hueco) if color_hueco is not None else colores._rgb(color_fondo)
    else:
        for hueco in (huecos or []):
            img[hueco] = colores._rgb(color_huecos)
    return img
