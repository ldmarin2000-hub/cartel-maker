#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/geometry.py
------------------
Paso 3 del pipeline de neón: polilíneas en píxeles -> geometría en mm
(shapely): recorrido simplificado, canal del LED y placa de fondo.
"""

import networkx as nx
import numpy as np
from shapely.geometry import LineString, Point, box
from shapely.ops import nearest_points, unary_union

_DIRECCIONES_BORDE = {"izquierda": (-1, 0), "derecha": (1, 0), "abajo": (0, -1), "arriba": (0, 1)}
FONDOS_VALIDOS = ("contorno", "rect_hundido", "rect_plano")


def escalar_a_mm(polys, alto_px, alto_mm, simplify_mm):
    """Convierte las polilíneas de píxeles a mm (con flip de Y) y las
    simplifica. Devuelve (lineas_shapely, ancho_mm)."""
    todos = np.concatenate([np.array(p) for p in polys])
    escala = alto_mm / (todos[:, 0].max() - todos[:, 0].min())
    a_mm = lambda p: [(c * escala, (alto_px - r) * escala) for (r, c) in np.array(p, float)]
    lineas = [LineString(a_mm(p)).simplify(simplify_mm) for p in polys if len(p) >= 2]
    ancho_mm = (todos[:, 1].max() - todos[:, 1].min()) * escala
    return lineas, ancho_mm


def _redondear(geom, radio_mm):
    """Suaviza los bordes de `geom`: cierre morfológico (redondea esquinas
    convexas y rellena hendiduras chiquitas) seguido de apertura (redondea
    esquinas cóncavas y saca puntas filosas) — el mismo truco que "expandir
    y volver a achicar" que usan los editores de imagen para suavizar un
    contorno. `radio_mm` es cuánto se suaviza; 0 no hace nada."""
    if radio_mm <= 0 or geom.is_empty:
        return geom
    cerrado = geom.buffer(radio_mm, join_style=1, cap_style=1).buffer(-radio_mm, join_style=1, cap_style=1)
    abierto = cerrado.buffer(-radio_mm, join_style=1, cap_style=1).buffer(radio_mm, join_style=1, cap_style=1)
    return abierto


def construir_canal_y_placa(lineas, led_ancho_mm, holgura_mm, pared_mm, fondo, fondo_margen, redondeo_mm=0.0):
    """Arma el canal del LED (unión de buffers sobre las líneas) y la placa
    de fondo. Devuelve (canal, placa, paredes) donde `paredes` es lo que se
    extruye por encima de la placa (placa_mm..placa_mm+led_prof_mm).

    `fondo`:
      - "contorno":     la base sigue el contorno de las letras (gasta poco
                         material, pero las letras separadas quedan como
                         piezas sueltas — ver conectar_componentes()).
      - "rect_hundido":  base rectangular maciza; el canal queda como una
                         zanja hundida en un bloque macizo (gasta más
                         material/tiempo, pero es una sola pieza rígida).
      - "rect_plano":    base rectangular pero FINA; las paredes del canal
                         solo suben donde están las letras, como un relieve
                         que sobresale de una placa plana (mismo gasto de
                         paredes que "contorno", pero con el respaldo
                         rectangular conectado de "rect_hundido").

    `redondeo_mm` suaviza las esquinas filosas que a veces deja el trazado
    del esqueleto (giros bruscos en curvas cerradas de la fuente).
    """
    if fondo not in FONDOS_VALIDOS:
        raise ValueError(f"fondo debe ser uno de {FONDOS_VALIDOS}, recibí {fondo!r}")

    canal = unary_union([
        ls.buffer(led_ancho_mm / 2 + holgura_mm, cap_style=1, join_style=1) for ls in lineas
    ])
    contorno_paredes = unary_union([
        ls.buffer(led_ancho_mm / 2 + pared_mm, cap_style=1, join_style=1) for ls in lineas
    ])

    if redondeo_mm > 0:
        canal = _redondear(canal, redondeo_mm)
        contorno_paredes = _redondear(contorno_paredes, redondeo_mm)

    if fondo == "contorno":
        placa = contorno_paredes
        paredes = placa.difference(canal)
    else:
        minx, miny, maxx, maxy = canal.bounds
        placa = box(minx - fondo_margen, miny - fondo_margen, maxx + fondo_margen, maxy + fondo_margen)
        if fondo == "rect_hundido":
            paredes = placa.difference(canal)
        else:  # rect_plano
            paredes = contorno_paredes.difference(canal)

    return canal, placa, paredes


def conectar_componentes(placa, ancho_mm, pared_mm):
    """Si `placa` quedó con piezas sueltas (p.ej. letras separadas en modo
    "contorno"), las une con puentes finos — solo estructurales, para que
    imprima como una sola pieza. (El cable entre letras se resuelve aparte,
    con agujeros hacia atrás en cada punta — ver agregar_agujeros_cable().)
    Conecta todas las piezas con el mínimo largo total de puentes posible
    (árbol de expansión mínima). Devuelve (placa, cantidad_de_puentes)."""
    piezas = list(placa.geoms) if placa.geom_type == "MultiPolygon" else [placa]
    if len(piezas) <= 1:
        return placa, 0

    grafo = nx.Graph()
    grafo.add_nodes_from(range(len(piezas)))
    segmentos_por_arista = {}
    for i in range(len(piezas)):
        for j in range(i + 1, len(piezas)):
            p1, p2 = nearest_points(piezas[i], piezas[j])
            distancia = p1.distance(p2)
            grafo.add_edge(i, j, weight=distancia)
            segmentos_por_arista[(i, j)] = LineString([p1, p2])

    arbol = nx.minimum_spanning_tree(grafo)
    puentes = [segmentos_por_arista[tuple(sorted(arista))] for arista in arbol.edges()]

    placa2 = unary_union([placa] + [p.buffer(ancho_mm / 2 + pared_mm, cap_style=1, join_style=1) for p in puentes])
    return placa2, len(puentes)


def _agrupar_puntos_cercanos(puntos, distancia_min_mm):
    """Agrupa puntos que están a menos de `distancia_min_mm` entre sí (para
    que dos agujeros no queden pegados, con una pared de plástico
    demasiado fina entre uno y otro) y devuelve un representante (el
    centro) por cada grupo. Usa buffer+union para agrupar en cadena
    (si A está cerca de B y B cerca de C, los 3 quedan en el mismo grupo
    aunque A y C no estén cerca directamente)."""
    if not puntos:
        return []
    burbujas = unary_union([Point(p).buffer(distancia_min_mm / 2) for p in puntos])
    grupos = list(burbujas.geoms) if burbujas.geom_type == "MultiPolygon" else [burbujas]
    return [(g.centroid.x, g.centroid.y) for g in grupos]


def agregar_agujeros_cable(placa, lineas, diametro_mm=5.0, pared_min_mm=2.4):
    """Perfora la placa de lado a lado (0..placa_mm, hacia atrás) en cada
    punta suelta del recorrido — ahí es donde termina o empieza cada tramo
    de LED, así que es donde hace falta soldar/conectar el cable. Se
    accede desde atrás del cartel, y el cable entre letras corre pegado a
    la parte de atrás (que igual queda contra la pared al colgarlo).

    Si dos puntas quedan más cerca que `diametro_mm + pared_min_mm` (el
    mismo grosor de pared que se usa para el canal), se agrupan en un solo
    agujero en vez de dejar dos agujeros pegados con una pared finita y
    frágil entre ellos."""
    puntos = extremos_libres(lineas)
    if not puntos:
        return placa, 0

    puntos = _agrupar_puntos_cercanos(puntos, diametro_mm + pared_min_mm)

    agujeros = unary_union([Point(p).buffer(diametro_mm / 2, resolution=24) for p in puntos])
    return placa.difference(agujeros), len(puntos)


# ---------------------------------------------------------------------------
#  Salida de cable
# ---------------------------------------------------------------------------
def extremos_libres(lineas, tol=1.0):
    """Puntas sueltas del recorrido: extremos de línea que no coinciden con
    el extremo de ninguna otra línea (o sea, no son un cruce/empalme).
    Ahí es donde lógicamente "empieza" o "termina" la tira LED."""
    extremos = []
    for i, ls in enumerate(lineas):
        c = list(ls.coords)
        extremos.append((i, c[0]))
        extremos.append((i, c[-1]))

    libres = []
    for i, p in extremos:
        compartido = any(
            j != i and np.hypot(p[0] - q[0], p[1] - q[1]) < tol
            for j, q in extremos
        )
        if not compartido:
            libres.append(p)
    return libres


def punto_salida_cable(lineas, bounds):
    """Elige por dónde sacar el cable: el extremo suelto del recorrido más
    cercano a un borde de la placa (así el canalcito es lo más corto
    posible). Si no hay extremos sueltos (p.ej. una letra como "O" es un
    lazo cerrado), usa el vértice más cercano a un borde como respaldo.
    Devuelve (punto, nombre_del_borde) o None si no hay líneas."""
    minx, miny, maxx, maxy = bounds
    candidatos = extremos_libres(lineas)
    if not candidatos:
        candidatos = [c for ls in lineas for c in ls.coords]
    if not candidatos:
        return None

    mejor, mejor_dist = None, None
    for (x, y) in candidatos:
        distancias = {"izquierda": x - minx, "derecha": maxx - x, "abajo": y - miny, "arriba": maxy - y}
        borde, dist = min(distancias.items(), key=lambda kv: kv[1])
        if mejor_dist is None or dist < mejor_dist:
            mejor_dist, mejor = dist, ((x, y), borde)
    return mejor


def agregar_salida_cable(canal, placa, paredes, punto, borde, ancho_mm, pared_mm, margen_mm=6):
    """Agrega un canalcito recto desde `punto` hasta más allá del borde
    `borde` de la placa, para sacar el cable de alimentación. Devuelve
    (canal, placa, paredes) con el canalcito ya unido.

    OJO: `paredes` se actualiza sumándole el área del canalcito en vez de
    recalcularla como `placa.difference(canal)` — esa fórmula solo vale
    para "rect_hundido"; en "contorno"/"rect_plano" las paredes no cubren
    toda la placa, y recalcularlas así perdería ese relieve angosto."""
    dx, dy = _DIRECCIONES_BORDE[borde]
    x0, y0 = punto
    minx, miny, maxx, maxy = placa.bounds
    dist_borde = {"izquierda": x0 - minx, "derecha": maxx - x0, "abajo": y0 - miny, "arriba": maxy - y0}[borde]
    largo = dist_borde + margen_mm
    segmento = LineString([(x0, y0), (x0 + dx * largo, y0 + dy * largo)])

    canal2 = canal.union(segmento.buffer(ancho_mm / 2, cap_style=1, join_style=1))
    placa2 = placa.union(segmento.buffer(ancho_mm / 2 + pared_mm, cap_style=1, join_style=1))
    paredes2 = paredes.union(segmento.buffer(ancho_mm / 2 + pared_mm, cap_style=1, join_style=1)).difference(canal2)
    return canal2, placa2, paredes2


# ---------------------------------------------------------------------------
#  Agujeros de montaje (bocallave)
# ---------------------------------------------------------------------------
def _bocallave(cx, cy_abajo, diam_grande, diam_chico, largo_slot):
    """Ojo de cerradura: círculo grande ABAJO (para meter la cabeza del
    tornillo) + ranura angosta hacia ARRIBA (donde el tornillo queda
    trabado sosteniendo el peso). Al colgar, la cabeza del tornillo entra
    por el círculo grande y la pieza se desliza hacia abajo hasta que el
    tornillo topa contra el tope de arriba de la ranura -- si fuera al
    revés (grande arriba, ranura hacia abajo) no habría tope: el peso
    empujaría la pieza hacia el círculo grande, que es más ancho que la
    cabeza del tornillo, y se saldría."""
    circulo_grande = Point(cx, cy_abajo).buffer(diam_grande / 2, resolution=32)
    y_arriba = cy_abajo + largo_slot
    ranura = LineString([(cx, cy_abajo), (cx, y_arriba)]).buffer(
        diam_chico / 2, cap_style=1, join_style=1
    )
    return unary_union([circulo_grande, ranura])


def _mejor_punto_vertical(placa, x_ideal, ventana_mm, borde="arriba", paso_mm=2.0):
    """Cerca de `x_ideal`, busca el X con más altura de material vertical
    (para no caer en un hueco entre letras en modo "contorno") y devuelve
    (x, y_del_borde_local) — el borde superior si `borde="arriba"`
    (orejas de montaje) o el inferior si `borde="abajo"` (pata de
    escritorio)."""
    mejor_x, mejor_borde, mejor_alto = x_ideal, None, -1.0
    for delta in np.arange(0, ventana_mm, paso_mm):
        for x in ({x_ideal - delta, x_ideal + delta} if delta else {x_ideal}):
            franja = box(x - 1, -1e6, x + 1, 1e6)
            recorte = placa.intersection(franja)
            if recorte.is_empty:
                continue
            _, ymin, _, ymax = recorte.bounds
            alto = ymax - ymin
            if alto > mejor_alto:
                mejor_alto, mejor_x = alto, x
                mejor_borde = ymax if borde == "arriba" else ymin
    if mejor_borde is None:
        mejor_borde = placa.bounds[3] if borde == "arriba" else placa.bounds[1]
    return mejor_x, mejor_borde


def agregar_orejas_de_montaje(placa, n_orejas=2, radio_oreja=11, solape_mm=5,
                               diam_grande=8.5, diam_chico=4.5, largo_slot=9):
    """Agrega `n_orejas` orejas circulares arriba de la placa, cada una con
    un agujero bocallave para colgar de un tornillo. Cada oreja se hunde
    `solape_mm` en el punto más alto de placa disponible cerca de su
    posición ideal, para que quede realmente soldada (no flotando con un
    huequito de aire entre la oreja y la placa, que no sostiene nada) --
    pero por eso mismo el agujero bocallave puede terminar cayendo justo
    donde ya había pared de una letra. Acá solo se resta de la placa
    (capa baja); la pared alta del canal (`paredes`, capa aparte que se
    calculó ANTES de esto) no se entera y le queda tapando un pedacito
    del agujero por arriba si se solapan. Por eso devuelve también los
    huecos (sin restar todavía) — quien llama tiene que restarlos
    también de `paredes` para que el agujero quede libre de punta a
    punta. Devuelve (placa_con_orejas_y_huecos, huecos_sin_restar)."""
    minx, _, maxx, maxy = placa.bounds
    ancho = maxx - minx
    if n_orejas <= 1:
        xs_ideales = [(minx + maxx) / 2]
    else:
        xs_ideales = [minx + ancho * 0.18 + i * (ancho * 0.64) / (n_orejas - 1) for i in range(n_orejas)]

    ventana = max(ancho * 0.12, radio_oreja)
    orejas, huecos = [], []
    for x_ideal in xs_ideales:
        x, y_top_local = _mejor_punto_vertical(placa, x_ideal, ventana, borde="arriba")
        y_centro = y_top_local + radio_oreja - solape_mm
        orejas.append(Point(x, y_centro).buffer(radio_oreja, resolution=32))
        huecos.append(_bocallave(x, y_centro - radio_oreja * 0.35, diam_grande, diam_chico, largo_slot))

    huecos_poly = unary_union(huecos)
    placa_con_orejas = unary_union([placa] + orejas)
    return placa_con_orejas.difference(huecos_poly), huecos_poly


# ---------------------------------------------------------------------------
#  Base de escritorio (alternativa a colgar)
# ---------------------------------------------------------------------------
def agregar_pata_escritorio(placa, ancho_pata_mm=40, alto_pata_mm=15, solape_mm=5):
    """Agrega una pata rectangular que sobresale del borde INFERIOR de la
    placa, cerca del centro, en el punto con más material disponible (para
    que la pata quede bien pegada y no en un hueco entre letras). Esa pata
    encastra después en la ranura de una base de escritorio impresa aparte
    (ver core/soporte.py). Devuelve (placa, ancho_pata_mm)."""
    minx, _, maxx, _ = placa.bounds
    ancho = maxx - minx
    x_ideal = (minx + maxx) / 2
    ventana = max(ancho * 0.3, ancho_pata_mm)

    x, y_bottom_local = _mejor_punto_vertical(placa, x_ideal, ventana, borde="abajo")
    y_top_pata = y_bottom_local + solape_mm
    pata = box(x - ancho_pata_mm / 2, y_bottom_local - alto_pata_mm, x + ancho_pata_mm / 2, y_top_pata)

    return unary_union([placa, pata]), ancho_pata_mm
