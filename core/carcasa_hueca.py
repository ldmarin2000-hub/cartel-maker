#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/carcasa_hueca.py
-------------------------
Mecánica compartida de "letra/palabra hueca con luz adentro": cáscara
hueca con rebaje donde encastra una tapa aparte, la tapa en sí, y el
agujero para pasar el cable de alimentación (por la pared lateral o por
el canto de atrás). Usada por generators/letras.py (una letra/inicial) y
generators/caja_luz.py (una palabra entera) — a ninguna de las dos le
importa si `poly` es un solo carácter o varios, es geometría shapely
genérica.
"""

import trimesh
from shapely.geometry import Point

from core import mesh3d

LEDGE_ANCHO_MM = 2.0  # contorno interno (rebaje) donde apoya/encastra la tapa


def ledge_activo(espesor_pared_mm):
    """El rebaje (LEDGE_ANCHO_MM) solo funciona como tope real si es más
    angosto que la pared normal — si no, no hay escalón donde la tapa
    pueda topar (y directamente no hay margen para separarla de la
    pared principal). Devuelve si hay margen suficiente."""
    return espesor_pared_mm > LEDGE_ANCHO_MM + 0.2


def shrink_tapa(espesor_pared_mm, holgura_mm):
    """Cuánto achicar el contorno para la tapa. Tiene que quedar MÁS
    CHICA que la abertura del rebaje (`LEDGE_ANCHO_MM`, para poder
    entrar) pero MÁS GRANDE que la abertura del hueco principal
    (`espesor_pared_mm`, para que el escalón la frene y no siga de largo
    hacia adentro) — si no hay margen entre esos dos valores, la tapa
    queda simple (pegada por afuera, sin encastrar)."""
    if not ledge_activo(espesor_pared_mm):
        return holgura_mm
    margen_disponible = espesor_pared_mm - LEDGE_ANCHO_MM
    return LEDGE_ANCHO_MM + min(holgura_mm, margen_disponible * 0.6)


def armar_carcasa_hueca(poly, profundidad_mm, espesor_pared_mm, tapa_espesor_mm):
    """Arma la cáscara hueca: cara de adelante sólida y fina
    (`espesor_pared_mm`, para que pase la luz), paredes laterales del
    mismo espesor, atrás ABIERTO (para meter el LED/pila y poder
    cambiarla). Justo antes del borde de atrás, en los últimos
    `tapa_espesor_mm` de profundidad, el hueco se ensancha hasta dejar
    un REBAJE de `LEDGE_ANCHO_MM` (en vez de `espesor_pared_mm`) — un
    escalón donde apoya/encastra la tapa (como una tapa de caja con
    rebajo), no un simple tope a tope. Si algún trazo es más angosto que
    2x el espesor de pared, esa parte queda maciza (no hay dónde hacer
    hueco) — no es un error, pero si es solo una parte (no toda la
    palabra/letra) puede pasar desapercibido: una cola/rulito fino de una
    fuente cursiva, por ejemplo, queda maciza mientras el resto se ve
    perfecto hueco, y en el visor 3D esa parte sólida puede tapar
    visualmente el hueco de atrás si se superpone en la proyección.
    Devuelve (malla, quedo_hueca, avisos) — `avisos` es una lista (vacía
    si no hay nada que avisar)."""
    avisos = []
    piezas_afuera = mesh3d.piezas_desde_geom(poly, profundidad_mm)
    afuera = trimesh.util.concatenate(piezas_afuera) if len(piezas_afuera) > 1 else piezas_afuera[0]

    # join_style=1 (redondeado): con mitre (2) los ángulos agudos de letras como
    # la "M" generaban geometría degenerada al extruir ("Not all meshes are volumes!").
    hueco_poly = poly.buffer(-espesor_pared_mm, join_style=1)
    if hueco_poly.is_empty or hueco_poly.area < 1:
        return afuera, False, avisos  # trazo muy angosto para hacerle hueco -> queda macizo

    # zona de `poly` que quedó lejos de cualquier punto hueco -- ahí no hay luz
    # adentro por más profundo que sea el hueco en otras partes.
    zona_maciza = poly.difference(hueco_poly.buffer(espesor_pared_mm + 0.5, join_style=1))
    if zona_maciza.area > max(30.0, poly.area * 0.03):
        avisos.append(
            "Una parte del trazo (probablemente un detalle fino, como la cola de una fuente "
            "cursiva) quedó maciza porque es más angosta que 2x el espesor de pared — no le "
            "va a llegar luz ahí, y en el visor puede parecer que 'tapa' el hueco del resto. "
            "Bajá el espesor de pared o subí el tamaño si querés que se vea iluminada también."
        )

    z_ledge = max(profundidad_mm - tapa_espesor_mm, espesor_pared_mm)
    sobresalto_mm = 5  # que el hueco sobrepase el fondo, para que quede ABIERTO atrás, no un piso ciego
    piezas_hueco = mesh3d.piezas_desde_geom(hueco_poly, z_ledge - espesor_pared_mm, z=espesor_pared_mm)

    if ledge_activo(espesor_pared_mm):
        ledge_poly = poly.buffer(-LEDGE_ANCHO_MM, join_style=1)
        if not ledge_poly.is_empty and ledge_poly.area >= 1:
            piezas_hueco += mesh3d.piezas_desde_geom(
                ledge_poly, profundidad_mm - z_ledge + sobresalto_mm, z=z_ledge
            )
    else:
        piezas_hueco += mesh3d.piezas_desde_geom(hueco_poly, profundidad_mm - z_ledge + sobresalto_mm, z=z_ledge)

    hueco = trimesh.util.concatenate(piezas_hueco) if len(piezas_hueco) > 1 else piezas_hueco[0]

    carcasa = trimesh.boolean.difference([afuera, hueco], engine="manifold")
    avisos.append(
        "Ojo al laminar: como la pieza queda abierta atrás a propósito, algunos laminadores "
        "(Bambu Studio incluido, es un bug conocido y reportado en su foro) le agregan solas "
        "capas de relleno sólido ahí, tapando el hueco (y el agujero del cable) sin avisar y "
        "sin que el STL tenga nada raro (la geometría del hueco está bien). En Bambu Studio, "
        "por \"Configuración por objeto\" de esa pieza probá, en este orden: 1) Strength → "
        "\"Top shell layers\" en 0, 2) \"Solid infill threshold area\" en 0, 3) desactivar "
        "\"Ensure vertical shell thickness\" — ninguno de los tres anda garantizado siempre "
        "(hay reportes de gente a la que no le funcionó ninguno). Si no se soluciona con eso, "
        "agujerear la pieza a mano después de imprimir es un camino tan válido como cualquier "
        "otro, no un parche de emergencia."
    )
    return carcasa, True, avisos


def punto_y_direccion_pared(poly, lado, margen_mm=8):
    """Punto sobre el borde exterior de `poly` y la dirección (hacia
    afuera) para perforar un agujero RADIAL a través de la pared lateral
    — no a través de la tapa. `lado`: "arriba", "abajo", "izquierda" o
    "derecha" (a través de la pared del extremo elegido, cerca de ese
    borde). Devuelve (x, y, dx, dy) con (dx, dy) vector unitario hacia
    afuera."""
    minx, miny, maxx, maxy = poly.bounds
    zona = (maxy - miny) * 0.25
    if lado == "izquierda":
        return minx, min(miny + margen_mm, miny + zona), -1.0, 0.0
    elif lado == "derecha":
        return maxx, min(miny + margen_mm, miny + zona), 1.0, 0.0
    elif lado == "arriba":
        return (minx + maxx) / 2, max(maxy - margen_mm, maxy - zona), 0.0, 1.0
    else:  # abajo
        return (minx + maxx) / 2, miny, 0.0, -1.0


def punto_agujero_atras(poly, radio_mm, espesor_pared_mm, filas_y_mm=(0.0, 6.0, 12.0, 20.0, 30.0),
                         min_cobertura_pared=0.35):
    """Punto cerca del borde de abajo donde el agujero de radio `radio_mm`
    ENTRA COMPLETO sin salirse del contorno exterior Y corta de verdad
    pared sólida (no solo "no se sale", que es un chequeo insuficiente:
    en un trazo ANCHO, un círculo puede caber entero adentro de `poly`
    cayendo casi todo en la zona YA hueca del medio -- apenas rozando el
    anillo sólido de la pared -- y terminar siendo un agujero de mentira
    que no atraviesa nada. Por eso acá se exige ADEMÁS que una fracción
    mínima (`min_cobertura_pared`) del área del círculo realmente se
    superponga con la pared sólida (`poly` menos el hueco principal,
    inset `espesor_pared_mm`) -- si no, no cuenta como un punto válido
    aunque el círculo entero quede "adentro" del contorno. Se valida
    contra la pared de `espesor_pared_mm` (no el rebaje angosto de la
    tapa, `LEDGE_ANCHO_MM`) porque el agujero "atras" ahora atraviesa
    TODA la profundidad desde justo detrás de la cara de adelante (ver
    `armar_agujero_pared`) -- esa banda ancha es la que existe en casi
    toda la profundidad; el rebaje angosto de la tapa es apenas los
    últimos milímetros.

    Prueba varias FILAS (cada una `filas_y_mm[i]` más arriba del borde de
    abajo) y en cada una desliza en X buscando un lugar que entre -- una
    palabra angosta justo en el centro-abajo (como el trazo fino de una
    cursiva) puede no tener lugar en la fila más baja pero sí un poco más
    arriba. Devuelve (x, y) o None si ninguna fila encontró un punto."""
    minx, miny, maxx, maxy = poly.bounds
    cx = (minx + maxx) / 2
    ancho = maxx - minx
    paso = max(radio_mm * 0.5, 2.0)
    n_pasos = int(ancho / (2 * paso)) + 1
    offsets = [0.0]
    for i in range(1, n_pasos + 1):
        offsets += [i * paso, -i * paso]

    hueco_poly = poly.buffer(-espesor_pared_mm, join_style=1)
    pared_solida = poly.difference(hueco_poly)
    area_minima = radio_mm * radio_mm * 3.14159265 * min_cobertura_pared

    for y_extra in filas_y_mm:
        y = miny + radio_mm + 1.0 + y_extra
        if y >= maxy - radio_mm:
            break
        for dx in offsets:
            p = Point(cx + dx, y)
            circulo = p.buffer(radio_mm, resolution=24)
            if not poly.contains(circulo):
                continue
            if circulo.intersection(pared_solida).area < area_minima:
                continue
            return (cx + dx, y)
    return None


def punto_pct_a_xy(poly, x_pct, y_pct):
    """Convierte una posición relativa (0-100%, X de izquierda a derecha,
    Y de abajo a arriba) dentro de la caja de `poly` a coordenadas (mm)
    absolutas — para el control manual de posición del agujero "atras"
    (el slider no depende del tamaño real de la letra/palabra)."""
    minx, miny, maxx, maxy = poly.bounds
    return minx + (x_pct / 100.0) * (maxx - minx), miny + (y_pct / 100.0) * (maxy - miny)


def punto_atras_corta_algo(poly, punto, radio_mm, espesor_pared_mm, min_cobertura_pared=0.35):
    """Para el punto manual (que no se valida al generar — "el que elige a
    mano se hace cargo"): dice si ESE punto puntual realmente va a cortar
    pared sólida o si el agujero va a caer vacío (circulo.contains falla,
    o cae casi todo adentro del hueco principal). Solo para avisar en la
    vista rápida antes de generar, no bloquea nada."""
    circulo = Point(punto).buffer(radio_mm, resolution=24)
    if not poly.contains(circulo):
        return False
    hueco_poly = poly.buffer(-espesor_pared_mm, join_style=1)
    pared_solida = poly.difference(hueco_poly)
    area_minima = radio_mm * radio_mm * 3.14159265 * min_cobertura_pared
    return circulo.intersection(pared_solida).area >= area_minima


def armar_agujero_pared(poly, espesor_pared_mm, agujero_cable_diam_mm, lado, profundidad_mm, tapa_espesor_mm,
                         punto_manual=None):
    """Cilindro para perforar la carcasa con el agujero del cable — no en
    la tapa. "arriba"/"abajo"/"izquierda"/"derecha": RADIAL, a través de
    la pared lateral, a mitad de profundidad. "atras": AXIAL, por el
    canto de atrás, de afuera hacia adentro en el eje Z, atravesando TODA
    la pared exterior desde justo detrás de la cara de adelante
    (`espesor_pared_mm`) hasta pasar el borde de atrás -- no solo el
    rebaje angosto de la tapa (`LEDGE_ANCHO_MM`), que son apenas los
    últimos milímetros de la profundidad. Si el cilindro arrancara ahí
    (como antes), con `profundidad_mm` chico terminaba antes de z=0 y de
    rebote agujereaba por accidente la cara de adelante entera (por eso
    "andaba" con poca profundidad); con `profundidad_mm` grande el
    cilindro ya no llegaba a la banda ancha de pared sólida que existe en
    el resto de la profundidad y el agujero no cortaba nada real ahí. Si
    se pasa `punto_manual` (x, y) se taladra ahí directamente (el que
    elige a mano se hace cargo de que entre; no se valida), si no se
    busca automático con `punto_agujero_atras`. Devuelve el cilindro, o
    None si "atras" no encontró/no tiene un punto válido (trazo muy
    angosto ahí)."""
    radio = agujero_cable_diam_mm / 2
    if lado == "atras":
        if not ledge_activo(espesor_pared_mm):
            return None
        punto = punto_manual if punto_manual is not None else punto_agujero_atras(poly, radio, espesor_pared_mm)
        if punto is None:
            return None
        x, y = punto
        z_afuera = profundidad_mm + 4
        z_adentro = espesor_pared_mm
        return trimesh.creation.cylinder(radius=radio, segment=[(x, y, z_afuera), (x, y, z_adentro)], sections=32)

    x, y, dx, dy = punto_y_direccion_pared(poly, lado)
    z = profundidad_mm * 0.5
    margen_afuera, margen_adentro = 3.0, espesor_pared_mm + 4.0
    p1 = (x + dx * margen_afuera, y + dy * margen_afuera, z)
    p2 = (x - dx * margen_adentro, y - dy * margen_adentro, z)
    return trimesh.creation.cylinder(radius=radio, segment=[p1, p2], sections=32)


def armar_tapa(poly, espesor_mm, espesor_pared_mm, holgura_mm=1.0):
    """Tapa: contorno achicado (`shrink_tapa` — para que entre en el
    rebaje de `armar_carcasa_hueca` y tope ahí, en vez de seguir de largo
    hacia el hueco principal), sólida y fina, para cerrar el hueco por
    atrás después de meter el LED. Sin agujero de cable — ese va en la
    carcasa (`armar_agujero_pared`), no acá."""
    tapa_poly = poly.buffer(-shrink_tapa(espesor_pared_mm, holgura_mm), join_style=1)
    piezas = mesh3d.piezas_desde_geom(tapa_poly, espesor_mm)
    return trimesh.util.concatenate(piezas) if len(piezas) > 1 else piezas[0]
