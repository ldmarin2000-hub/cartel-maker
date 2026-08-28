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

Modelo geométrico (replica el flujo manual en Fusion 360, para que las
piezas salgan iguales a como se venían haciendo a mano):

  C0        = `poly`, el contorno tal cual sale del boceto/fuente — NO
              es la silueta final, es la referencia de la que salen
              todos los demás contornos por desfasaje (offset).
  C_afuera  = C0 CRECIDO hacia afuera por `espesor_pared_mm` -- esta sí
              es la silueta exterior real de la pieza (más grande que
              C0, no igual).
  C_cavidad = C0 achicado hacia adentro por `soporte_tapa_mm` -- el
              límite del hueco principal (cuerpo de la letra) y, por
              consecuencia, dónde se forma el escalón para la tapa.
  C_tapa    = C0 achicado hacia adentro por `holgura_tapa_mm` (menor que
              `soporte_tapa_mm`) -- el contorno de la tapa en sí.

Con esto, un trazo angosto NUNCA queda macizo sin querer por culpa del
espesor de pared (que ahora solo suma material hacia afuera) — lo único
que puede angostar el hueco es `soporte_tapa_mm`, y si un trazo es más
angosto que 2x ese valor, esa parte queda maciza (se avisa, ver
`armar_carcasa_hueca`).
"""

import trimesh
from shapely.geometry import LineString, Point

from core import mesh3d

SOPORTE_TAPA_MM_DEFAULT = 2.0
HOLGURA_TAPA_MM_DEFAULT = 1.0
ESPESOR_CARA_MM_DEFAULT = 2.5


def calcular_z_ledge(profundidad_mm, espesor_cara_mm, tapa_espesor_mm, tapa_offset_mm=0.0):
    """Dónde (en Z) arranca el escalón/rebaje donde apoya la tapa.
    `tapa_offset_mm`: en 0 (default) la tapa queda EXACTO al ras del
    borde de atrás de la carcasa. Positivo = el escalón queda más cerca
    del borde de atrás (rebaje más CORTO que `tapa_espesor_mm`) → la
    tapa, al no entrar entera, SOBRESALE esos mm por atrás. Negativo =
    el escalón queda más lejos del borde de atrás (rebaje más LARGO) →
    la tapa entra más y queda UN POCO ADENTRO. La usa también el visor
    3D para poner la pieza de la tapa en su posición real (encastrada,
    no pegada después del borde de atrás)."""
    z_ledge = max(profundidad_mm - tapa_espesor_mm + tapa_offset_mm, espesor_cara_mm)
    return min(z_ledge, profundidad_mm - 0.5)


def armar_carcasa_hueca(poly, profundidad_mm, espesor_pared_mm, tapa_espesor_mm,
                         soporte_tapa_mm=SOPORTE_TAPA_MM_DEFAULT, espesor_cara_mm=ESPESOR_CARA_MM_DEFAULT,
                         tapa_offset_mm=0.0):
    """Arma la cáscara hueca: silueta exterior = `poly` CRECIDO hacia
    afuera por `espesor_pared_mm` (C_afuera, ver docstring del módulo),
    cara de adelante sólida y fina (`espesor_cara_mm`, para que pase la
    luz), atrás ABIERTO (para meter el LED/pila y poder cambiarla).
    Justo antes del borde de atrás, en los últimos `tapa_espesor_mm` de
    profundidad (corridos por `tapa_offset_mm`), el hueco se ensancha
    hasta el propio contorno de `poly` (en vez de quedar achicado por
    `soporte_tapa_mm`) — un escalón donde apoya/encastra la tapa (como
    una tapa de caja con rebajo), no un simple tope a tope.

    Si algún trazo es más angosto que 2x `soporte_tapa_mm`, esa parte
    queda maciza (no hay dónde hacer hueco) — no es un error, pero si es
    solo una parte (no toda la palabra/letra) puede pasar desapercibido:
    una cola/rulito fino de una fuente cursiva, por ejemplo, queda
    maciza mientras el resto se ve perfecto hueco, y en el visor 3D esa
    parte sólida puede tapar visualmente el hueco de atrás si se
    superpone en la proyección. Devuelve (malla, quedo_hueca, avisos) —
    `avisos` es una lista (vacía si no hay nada que avisar)."""
    avisos = []
    afuera_poly = poly.buffer(espesor_pared_mm, join_style=1)
    piezas_afuera = mesh3d.piezas_desde_geom(afuera_poly, profundidad_mm)
    afuera = trimesh.util.concatenate(piezas_afuera) if len(piezas_afuera) > 1 else piezas_afuera[0]

    # join_style=1 (redondeado): con mitre (2) los ángulos agudos de letras como
    # la "M" generaban geometría degenerada al extruir ("Not all meshes are volumes!").
    cavidad_poly = poly.buffer(-soporte_tapa_mm, join_style=1)
    if cavidad_poly.is_empty or cavidad_poly.area < 1:
        return afuera, False, avisos  # trazo muy angosto para hacerle hueco -> queda macizo

    # zona de `poly` que quedó lejos de cualquier punto hueco -- ahí no hay luz
    # adentro por más profundo que sea el hueco en otras partes.
    zona_maciza = poly.difference(cavidad_poly.buffer(soporte_tapa_mm + 0.5, join_style=1))
    if zona_maciza.area > max(30.0, poly.area * 0.03):
        avisos.append(
            "Una parte del trazo (probablemente un detalle fino, como la cola de una fuente "
            "cursiva) quedó maciza porque es más angosta que 2x el soporte de la tapa — no le "
            "va a llegar luz ahí, y en el visor puede parecer que 'tapa' el hueco del resto. "
            "Bajá el soporte de la tapa o subí el tamaño si querés que se vea iluminada también."
        )

    z_ledge = calcular_z_ledge(profundidad_mm, espesor_cara_mm, tapa_espesor_mm, tapa_offset_mm)
    sobresalto_mm = 5  # que el hueco sobrepase el fondo, para que quede ABIERTO atrás, no un piso ciego
    piezas_hueco = mesh3d.piezas_desde_geom(cavidad_poly, z_ledge - espesor_cara_mm, z=espesor_cara_mm)
    piezas_hueco += mesh3d.piezas_desde_geom(poly, profundidad_mm - z_ledge + sobresalto_mm, z=z_ledge)
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


def punto_y_direccion_pared(poly, lado, radio_mm, min_cobertura_pared=0.35):
    """Busca un punto sobre el borde EXTERIOR real de `poly` (C0), cerca
    del lado pedido, donde el agujero de radio `radio_mm` realmente
    atraviese pared sólida -- no el punto medio ciego del recuadro
    completo (que en una palabra con espacios entre letras, o el hueco
    de una "O"/"D", puede caer en el aire y no cortar nada).

    Para "izquierda"/"derecha" desliza en Y, para "arriba"/"abajo"
    desliza en X, arrancando del centro del rango y probando hacia los
    dos lados -- en cada posición traza una línea perpendicular al lado
    elegido, la cruza con `poly` para encontrar dónde está el borde REAL
    ahí (no asume que coincide con el máximo/mínimo global), y valida
    que un círculo centrado ahí caiga mayormente adentro de `poly` (si
    no, esa posición cae en un hueco/espacio entre letras).

    Devuelve (x, y, dx, dy) con (dx, dy) vector unitario hacia afuera, o
    None si no encontró ningún lugar."""
    minx, miny, maxx, maxy = poly.bounds
    if lado == "izquierda":
        eje_fijo, extremo, dx, dy = "x", minx, -1.0, 0.0
    elif lado == "derecha":
        eje_fijo, extremo, dx, dy = "x", maxx, 1.0, 0.0
    elif lado == "arriba":
        eje_fijo, extremo, dx, dy = "y", maxy, 0.0, 1.0
    else:  # abajo
        eje_fijo, extremo, dx, dy = "y", miny, 0.0, -1.0

    rango_min, rango_max = (miny, maxy) if eje_fijo == "x" else (minx, maxx)
    centro = (rango_min + rango_max) / 2
    paso = max(radio_mm * 0.6, 3.0)
    n_pasos = int((rango_max - rango_min) / (2 * paso)) + 1
    offsets = [0.0]
    for i in range(1, n_pasos + 1):
        offsets += [i * paso, -i * paso]

    fuera_del_rango = max(maxx - minx, maxy - miny) + 10
    area_minima = radio_mm * radio_mm * 3.14159265 * min_cobertura_pared

    for off in offsets:
        pos = centro + off
        if pos <= rango_min + radio_mm or pos >= rango_max - radio_mm:
            continue
        if eje_fijo == "x":
            linea = LineString([(extremo - fuera_del_rango, pos), (extremo + fuera_del_rango, pos)])
        else:
            linea = LineString([(pos, extremo - fuera_del_rango), (pos, extremo + fuera_del_rango)])
        inter = poly.intersection(linea)
        if inter.is_empty:
            continue
        coords = []
        if inter.geom_type == "LineString":
            coords = list(inter.coords)
        elif inter.geom_type == "MultiLineString":
            for seg in inter.geoms:
                coords += list(seg.coords)
        if not coords:
            continue
        eje_dir = dx if eje_fijo == "x" else dy
        x, y = max(coords, key=lambda c: (c[0] if eje_fijo == "x" else c[1]) * eje_dir)
        circulo = Point(x, y).buffer(radio_mm, resolution=24)
        if circulo.intersection(poly).area < area_minima:
            continue
        return (x, y, dx, dy)
    return None


def punto_agujero_atras(poly, radio_mm, espesor_pared_mm, soporte_tapa_mm=SOPORTE_TAPA_MM_DEFAULT, margen_mm=0.3):
    """Punto DENTRO de la banda de pared donde el agujero de radio
    `radio_mm` entra con margen de sobra por los dos lados -- ni tan
    afuera que toque la silueta exterior real (`poly` crecido hacia
    afuera por `espesor_pared_mm`, no `poly` mismo), ni tan adentro que
    toque el hueco principal (mismo criterio que ya usa
    `core/geometry.py::agregar_agujeros_cable` para el neón, que taladra
    la placa de lado a lado en cualquier lugar de la pared que le entre,
    no solo en una franja angosta fija).

    A diferencia del escalón (que mide siempre `soporte_tapa_mm` de
    ancho, angosto), la banda de pared completa mide
    `espesor_pared_mm + soporte_tapa_mm` -- mucho más lugar para agujeros
    grandes. Concretamente: `zona_segura` = la silueta exterior real
    achicada por `radio_mm + margen_mm` (así el círculo entero, con
    margen, queda adentro de la pared) MENOS el hueco principal
    agrandado por lo mismo (así el círculo entero, con margen, queda
    afuera del hueco). Si esa zona no está vacía, cualquier punto
    adentro sirve -- se elige el de la parte más grande, más cerca del
    borde de abajo.

    Devuelve (x, y) o None si no hay NINGÚN lugar en toda la letra donde
    el agujero entre con ese margen (diámetro demasiado grande para el
    ancho de pared actual, `espesor_pared_mm + soporte_tapa_mm`)."""
    afuera_poly = poly.buffer(espesor_pared_mm, join_style=1)
    cavidad_poly = poly.buffer(-soporte_tapa_mm, join_style=1)
    margen = radio_mm + margen_mm
    zona_segura = afuera_poly.buffer(-margen, join_style=1).difference(cavidad_poly.buffer(margen, join_style=1))
    if zona_segura.is_empty:
        return None

    partes = list(zona_segura.geoms) if zona_segura.geom_type == "MultiPolygon" else [zona_segura]
    partes = [p for p in partes if p.area > 0.5]
    if not partes:
        return None
    partes.sort(key=lambda p: p.centroid.y)
    punto = partes[0].representative_point()
    return (punto.x, punto.y)


def punto_pct_a_xy(poly, x_pct, y_pct):
    """Convierte una posición relativa (0-100%, X de izquierda a derecha,
    Y de abajo a arriba) dentro de la caja de `poly` a coordenadas (mm)
    absolutas — para el control manual de posición del agujero "atras"
    (el slider no depende del tamaño real de la letra/palabra)."""
    minx, miny, maxx, maxy = poly.bounds
    return minx + (x_pct / 100.0) * (maxx - minx), miny + (y_pct / 100.0) * (maxy - miny)


def armar_agujero_pared(poly, espesor_pared_mm, agujero_cable_diam_mm, lado, profundidad_mm, tapa_espesor_mm,
                         soporte_tapa_mm=SOPORTE_TAPA_MM_DEFAULT, espesor_cara_mm=ESPESOR_CARA_MM_DEFAULT,
                         tapa_offset_mm=0.0, punto_manual=None):
    """Cilindro para perforar la carcasa con el agujero del cable — no en
    la tapa. "arriba"/"abajo"/"izquierda"/"derecha": RADIAL, a través de
    la pared lateral, a mitad de profundidad. "atras": AXIAL, de afuera
    hacia adentro en el eje Z, por un punto DENTRO de la banda de pared
    (ver `punto_agujero_atras`) -- taladra desde justo detrás de la cara
    de adelante (`espesor_cara_mm`) hacia atrás, bien largo a propósito
    (al menos 100mm, o `profundidad_mm + 4` si la caja es más profunda
    que eso) para no depender de ningún cálculo fino de dónde termina
    exactamente la pared — que sobre recorrido, no que falte. Si se pasa
    `punto_manual` (x, y) se taladra ahí directamente (el que elige a
    mano se hace cargo de que entre; no se valida), si no se busca
    automático con `punto_agujero_atras`. Devuelve el cilindro, o None
    si "atras" no encontró/no tiene un punto válido (el diámetro no
    entra en la pared con margen en ningún lado)."""
    radio = agujero_cable_diam_mm / 2
    if lado == "atras":
        punto = (
            punto_manual if punto_manual is not None
            else punto_agujero_atras(poly, radio, espesor_pared_mm, soporte_tapa_mm)
        )
        if punto is None:
            return None
        x, y = punto
        z_adentro = espesor_cara_mm
        z_afuera = max(z_adentro + 100, profundidad_mm + 4)  # bien largo a propósito: que sobre, no que falte
        return trimesh.creation.cylinder(radius=radio, segment=[(x, y, z_afuera), (x, y, z_adentro)], sections=32)

    resultado = punto_y_direccion_pared(poly, lado, radio)
    if resultado is None:
        return None
    x, y, dx, dy = resultado
    z = profundidad_mm * 0.5
    margen_afuera, margen_adentro = espesor_pared_mm + 3.0, soporte_tapa_mm + 4.0
    p1 = (x + dx * margen_afuera, y + dy * margen_afuera, z)
    p2 = (x - dx * margen_adentro, y - dy * margen_adentro, z)
    return trimesh.creation.cylinder(radius=radio, segment=[p1, p2], sections=32)


def armar_tapa(poly, espesor_mm, holgura_tapa_mm=HOLGURA_TAPA_MM_DEFAULT):
    """Tapa: contorno de `poly` (C0) achicado hacia adentro por
    `holgura_tapa_mm` (más chico que `soporte_tapa_mm` para que el
    escalón la frene y no siga de largo hacia el hueco principal),
    sólida y fina, para cerrar el hueco por atrás después de meter el
    LED. Sin agujero de cable — ese va en la carcasa
    (`armar_agujero_pared`), no acá."""
    tapa_poly = poly.buffer(-holgura_tapa_mm, join_style=1)
    piezas = mesh3d.piezas_desde_geom(tapa_poly, espesor_mm)
    return trimesh.util.concatenate(piezas) if len(piezas) > 1 else piezas[0]
