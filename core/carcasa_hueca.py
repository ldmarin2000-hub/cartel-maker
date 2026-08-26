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


def punto_agujero_atras(poly, radio_mm, filas_y_mm=(0.0, 6.0, 12.0, 20.0, 30.0)):
    """Punto cerca del borde de abajo donde el agujero de radio `radio_mm`
    ENTRA COMPLETO sin salirse del contorno exterior -- ahí se taladra el
    agujero axial "atras" (por el canto de atrás, el rebaje donde apoya
    la tapa). Ojo: el rebaje (`LEDGE_ANCHO_MM`, 2mm) casi siempre es más
    angosto que el agujero pedido (6mm por default) -- si solo se
    chequeara que el CENTRO cae en el rebaje (como antes), el agujero se
    salía del contorno y abría una muesca fea en el borde visible en vez
    de un agujero limpio. Acá se exige que el CÍRCULO ENTERO quede adentro
    de `poly` (no hace falta que quede todo dentro del rebaje angosto: la
    parte que cae en el hueco principal ya está vacía, no hay problema).

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
    for y_extra in filas_y_mm:
        y = miny + radio_mm + 1.0 + y_extra
        if y >= maxy - radio_mm:
            break
        for dx in offsets:
            p = Point(cx + dx, y)
            circulo = p.buffer(radio_mm, resolution=24)
            if poly.contains(circulo):
                return (cx + dx, y)
    return None


def armar_agujero_pared(poly, espesor_pared_mm, agujero_cable_diam_mm, lado, profundidad_mm, tapa_espesor_mm):
    """Cilindro para perforar la carcasa con el agujero del cable — no en
    la tapa. "arriba"/"abajo"/"izquierda"/"derecha": RADIAL, a través de
    la pared lateral, a mitad de profundidad. "atras": AXIAL, por el
    canto de atrás (el rebaje donde apoya la tapa), de afuera hacia
    adentro en el eje Z. Devuelve el cilindro, o None si "atras" no
    encontró un punto válido en el rebaje (trazo muy angosto ahí)."""
    radio = agujero_cable_diam_mm / 2
    if lado == "atras":
        if not ledge_activo(espesor_pared_mm):
            return None
        punto = punto_agujero_atras(poly, radio)
        if punto is None:
            return None
        x, y = punto
        z_afuera = profundidad_mm + 4
        z_adentro = profundidad_mm - tapa_espesor_mm - 4
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
