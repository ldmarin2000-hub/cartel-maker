#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generators/collar.py
--------------------
Collar de cuentas con letra encastrada: cada letra va en una cuenta
cilíndrica (un "redondel") con un agujero transversal para el hilo, y la
letra es una PIEZA APARTE que encastra en un hueco de la tapa -- así se
imprime cada cosa en su color y sin soportes.

Este módulo arranca por la CUENTA (base con hueco + letra suelta). La
secuencia completa (separadores, formas, exportación) se suma encima de
`armar_cuenta`, que es el primitivo de todo lo demás.

Convenciones de ejes (la cuenta ensamblada, tal cual se ve armada):
  * Z es el espesor de la cuenta (la base apoya en Z=0, la tapa con la
    letra queda en Z=alto).
  * El agujero para el hilo cruza la cuenta de lado a lado por su
    diámetro, a media altura. Con `angulo_agujero=0` va a lo largo de X
    (la línea base de la letra); el ángulo lo gira alrededor de Z.
  * La letra se lee derecha mirando la tapa desde arriba (+Z).
"""

import os

import numpy as np
import trimesh
from PIL import ImageFont
from shapely.affinity import translate, scale as escalar_geom
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import polylabel

from core import bambu_a1, colores, decoraciones, fuentes, mesh3d, pieza, texto2d, ui

NOMBRE = "Collar"
DESCRIPCION = "Collar de cuentas con letra encastrada (cuenta + letra + separadores)"

PERFILES_AGUJERO = ["rombo", "gota", "redondo"]
# El separador cilíndrico se imprime parado y su agujero va a lo largo del eje, así que no
# hay problema de voladizo: acepta además el cuadrado de lados rectos.
PERFILES_AGUJERO_SEPARADOR = ["rombo", "cuadrado", "redondo"]

# Valores de la cuenta de Fusion 360 del usuario (Diametro/Alto/Agujero/Chanfle).
DIAMETRO_DEFAULT = 70.0
ALTO_DEFAULT = 30.0
AGUJERO_DEFAULT = 20.0
CHANFLE_DEFAULT = 1.0

PROFUNDIDAD_HUECO_DEFAULT = 2.0
HOLGURA_DEFAULT = 0.15           # mm por lado entre la letra y su hueco
REBAJE_PROFUNDIDAD_DEFAULT = 0.5  # rebaje circular para sticker: lo justo para que quede al ras
REBAJE_BORDE_MIN_MM = 3.0         # ancho mínimo de borde que tiene que quedar alrededor del rebaje
PARED_MIN_MM = 1.2               # menos que esto entre el hueco y el techo del agujero = frágil
MARGEN_BORDE_LETRA_MM = 5.0      # la letra más ancha no se acerca al borde de la cuenta más que esto
SEGMENTOS_CIRCULO = 128
RASTER_PX_LETRA = 400


# ---------------------------------------------------------------------------
#  Agujero para el hilo
# ---------------------------------------------------------------------------

def perfil_agujero(perfil, tam):
    """Sección del agujero como polígono 2D (x = ancho, y = arriba), centrada
    en el origen. `tam` es el ANCHO del agujero (diagonal del rombo,
    diámetro del círculo). El rombo y la gota tienen las paredes superiores a
    45°: se imprimen acostados sin soportes, a diferencia del círculo, cuyo
    techo es un puente que se cae."""
    r = tam / 2
    if perfil == "rombo":
        return Polygon([(-r, 0), (0, -r), (r, 0), (0, r)])
    if perfil == "redondo":
        return Point(0, 0).buffer(r, quad_segs=SEGMENTOS_CIRCULO // 4)
    if perfil == "cuadrado":
        return box(-r, -r, r, r)
    if perfil == "gota":
        # arco de círculo de 135° a 405° (pasa por abajo) + ápice (0, r*sqrt2): las
        # tangentes desde el ápice tocan el círculo justo en 45° y 135°. Se arma punto
        # a punto -- unir un círculo con un triángulo deja puntos casi duplicados en las
        # tangencias y la extrusión sale con la malla abierta.
        angulos = np.radians(np.linspace(135, 405, SEGMENTOS_CIRCULO * 3 // 4, endpoint=True))
        arco = [(r * np.cos(a), r * np.sin(a)) for a in angulos]
        return Polygon(arco + [(0, r * np.sqrt(2))])
    raise ValueError(
        f"perfil del agujero debe ser uno de {PERFILES_AGUJERO + ['cuadrado']}, recibí {perfil!r}")


def altura_techo_agujero(perfil, tam):
    """Cuánto sube el agujero por encima de su centro (mm) -- sirve para
    chequear que quede pared entre el techo del agujero y el fondo del
    hueco de la letra."""
    return float(perfil_agujero(perfil, tam).bounds[3])


def _malla_agujero(perfil, tam, largo, angulo_deg, z_centro):
    """Prisma que atraviesa la cuenta, listo para restarle: sección
    `perfil_agujero` extruida `largo` a lo largo del eje del agujero."""
    prisma = trimesh.creation.extrude_polygon(perfil_agujero(perfil, tam), height=largo)
    prisma.apply_translation([0, 0, -largo / 2])
    # local x -> mundo Y (ancho), local y -> mundo Z (arriba), local z (extrusión) -> mundo X (eje)
    T = np.eye(4)
    T[:3, :3] = np.array([[0, 0, 1], [1, 0, 0], [0, 1, 0]], dtype=float)
    prisma.apply_transform(T)
    if angulo_deg:
        prisma.apply_transform(trimesh.transformations.rotation_matrix(np.radians(angulo_deg), [0, 0, 1]))
    prisma.apply_translation([0, 0, z_centro])
    return prisma


# ---------------------------------------------------------------------------
#  Cuerpo de la cuenta
# ---------------------------------------------------------------------------

def _cuerpo_cilindro(diametro, alto, chanfle):
    """Cilindro con chanfle de 45° en el borde de arriba y de abajo,
    generado por revolución de su perfil (r, z)."""
    r, c = diametro / 2, min(chanfle, diametro / 4, alto / 2)
    if c <= 0:
        pts = [(0, 0), (r, 0), (r, alto), (0, alto)]
    else:
        pts = [(0, 0), (r - c, 0), (r, c), (r, alto - c), (r - c, alto), (0, alto)]
    cuerpo = trimesh.creation.revolve(np.array(pts, dtype=float), sections=SEGMENTOS_CIRCULO)
    cuerpo.merge_vertices()
    cuerpo.fix_normals()
    return cuerpo


def _restar(cuerpo, *cortadores):
    return trimesh.boolean.difference([cuerpo, *cortadores], engine="manifold")


# ---------------------------------------------------------------------------
#  Letra
# ---------------------------------------------------------------------------

def _metricas_caracter(caracter, fuente):
    """(sobre_linea_base_abajo, alto) en píxeles del carácter, con
    `sobre_linea_base_abajo` = cuánto está su borde de ABAJO por encima de
    la línea base (negativo en las que tienen cola: g, y, p...)."""
    ascenso = fuente.getmetrics()[0]
    caja = fuente.getbbox(caracter)  # (izq, arriba, der, abajo), con arriba medido desde el ascenso
    return ascenso - caja[3], caja[3] - caja[1]


def letra_poligono(caracter, ruta_ttf, alto_mayuscula_mm, raster_px=RASTER_PX_LETRA):
    """Polígono de UN carácter, en mm, centrado en el origen. Todas las
    letras salen con la MISMA escala (la que hace que una "H" mida
    `alto_mayuscula_mm`) y la misma línea base -- no se agranda cada letra
    hasta llenar el disco, porque una "I" saldría gigante y una "M" chica.
    Horizontalmente se centra la caja de la letra; verticalmente se centra
    la caja de la mayúscula, así las colas (g, y) cuelgan por debajo y no
    corren el resto. Devuelve None para un carácter sin tinta (espacio)."""
    if not caracter.strip():
        return None
    poligono = texto2d.texto_a_poligono_crudo(caracter, ruta_ttf, raster_px=raster_px)
    if poligono is None or poligono.is_empty:
        return None

    fuente = ImageFont.truetype(ruta_ttf, raster_px)
    base_abajo, _ = _metricas_caracter(caracter, fuente)
    h_abajo, h_alto = _metricas_caracter("H", fuente)
    escala = alto_mayuscula_mm / h_alto

    minx, miny, maxx, _ = poligono.bounds
    poligono = translate(poligono, xoff=-(minx + maxx) / 2, yoff=base_abajo - miny - (h_abajo + h_alto / 2))
    poligono = escalar_geom(poligono, xfact=escala, yfact=escala, origin=(0, 0))
    return poligono.simplify(texto2d.SIMPLIFY_MM, preserve_topology=True)


def extension_radial(poligono):
    """Distancia del centro al punto más lejano de `poligono`."""
    if poligono is None or poligono.is_empty:
        return 0.0
    return max(float(np.hypot(x, y)) for g in (poligono.geoms if poligono.geom_type == "MultiPolygon" else [poligono])
               for x, y in g.exterior.coords)


# ---------------------------------------------------------------------------
#  La cuenta armada
# ---------------------------------------------------------------------------

def armar_cuenta(poligono_letra, diametro=DIAMETRO_DEFAULT, alto=ALTO_DEFAULT,
                 agujero=AGUJERO_DEFAULT, chanfle=CHANFLE_DEFAULT,
                 perfil=PERFILES_AGUJERO[0], angulo_agujero=0.0,
                 profundidad_hueco=PROFUNDIDAD_HUECO_DEFAULT, holgura=HOLGURA_DEFAULT,
                 relieve=0.0, rebaje_sticker_diametro=None,
                 rebaje_sticker_profundidad=REBAJE_PROFUNDIDAD_DEFAULT):
    """Arma una cuenta: devuelve `(base, letra, info)`.

    * `base`: cilindro con chanfle, con el agujero para el hilo y (si hay
      `poligono_letra`) el hueco donde encastra la letra. Apoya en Z=0.
    * `letra`: la pieza suelta, ya EN SU LUGAR dentro del hueco (para
      chequear el encastre / mostrar el armado). Su parte de abajo queda
      `profundidad_hueco` por debajo de la tapa y sobresale `relieve` mm
      (0 = al ras). `None` si no hay letra.
    * `info`: `{"pared_mm", "avisos"}` -- `pared_mm` es el espesor que queda
      entre el techo del agujero y el fondo del hueco (lo que hay que
      cuidar para que la cuenta no se rompa).

    La letra suelta es la silueta nominal; el hueco es esa silueta
    agrandada `holgura` mm por lado, para que entre sin forzar.

    Modo "lisa para sticker": sin `poligono_letra`, la tapa queda lisa. Si
    además se pasa `rebaje_sticker_diametro` (el diámetro del sticker), la
    tapa lleva un rebaje circular de `rebaje_sticker_profundidad` mm para que
    el sticker quede al ras y no se despegue por los bordes (se le suma
    `holgura` por lado, igual que al hueco de la letra). Es una alternativa
    a la letra encastrada: no se pueden pedir las dos a la vez."""
    if diametro <= 0 or alto <= 0 or agujero <= 0:
        raise ValueError("diámetro, alto y agujero tienen que ser mayores que 0")
    if profundidad_hueco <= 0 or profundidad_hueco >= alto:
        raise ValueError("la profundidad del hueco tiene que estar entre 0 y el alto de la cuenta")
    hay_rebaje = rebaje_sticker_diametro is not None
    if hay_rebaje:
        if poligono_letra is not None:
            raise ValueError("el rebaje para sticker y la letra encastrada son alternativos: pedí uno solo")
        if rebaje_sticker_diametro <= 0:
            raise ValueError("el diámetro del rebaje para sticker tiene que ser mayor que 0")
        if rebaje_sticker_diametro + 2 * holgura > diametro - 2 * REBAJE_BORDE_MIN_MM:
            raise ValueError(
                f"el rebaje de {rebaje_sticker_diametro:g} mm no entra en la cuenta de {diametro:g} mm: "
                f"tiene que quedar al menos {REBAJE_BORDE_MIN_MM:g} mm de borde (máximo "
                f"{diametro - 2 * REBAJE_BORDE_MIN_MM - 2 * holgura:g} mm)"
            )
        if rebaje_sticker_profundidad <= 0 or rebaje_sticker_profundidad >= alto:
            raise ValueError("la profundidad del rebaje tiene que estar entre 0 y el alto de la cuenta")

    avisos = []
    z_centro = alto / 2
    techo_agujero = z_centro + altura_techo_agujero(perfil, agujero)
    if hay_rebaje:
        fondo_hueco = alto - rebaje_sticker_profundidad
    else:
        fondo_hueco = alto - profundidad_hueco
    hay_hueco = poligono_letra is not None or hay_rebaje
    pared = fondo_hueco - techo_agujero if hay_hueco else alto - techo_agujero
    if pared < PARED_MIN_MM:
        avisos.append(
            f"Entre el techo del agujero y el fondo del hueco de la letra quedan {pared:.1f} mm "
            f"(menos de {PARED_MIN_MM} mm: la cuenta queda frágil). Achicá el agujero, "
            f"agrandá el alto o reducí la profundidad del hueco."
        )
    if z_centro - altura_techo_agujero(perfil, agujero) < 0.5 and perfil != "gota":
        avisos.append("El agujero es casi tan grande como el alto de la cuenta: queda sin piso.")

    cuerpo = _cuerpo_cilindro(diametro, alto, chanfle)
    cortadores = [_malla_agujero(perfil, agujero, diametro * 1.5, angulo_agujero, z_centro)]

    malla_letra = None
    if poligono_letra is not None:
        hueco_poligono = poligono_letra.buffer(holgura, join_style="round")
        piezas_hueco = mesh3d.piezas_desde_geom(hueco_poligono, profundidad_hueco + 1.0, z=fondo_hueco)
        cortadores.extend(piezas_hueco)

        piezas_letra = mesh3d.piezas_desde_geom(poligono_letra, profundidad_hueco + relieve, z=fondo_hueco)
        malla_letra = trimesh.util.concatenate(piezas_letra) if len(piezas_letra) > 1 else piezas_letra[0]

    if hay_rebaje:
        circulo = Point(0, 0).buffer(rebaje_sticker_diametro / 2 + holgura, quad_segs=SEGMENTOS_CIRCULO // 4)
        cortadores.extend(mesh3d.piezas_desde_geom(circulo, rebaje_sticker_profundidad + 1.0, z=fondo_hueco))

    base = _restar(cuerpo, *cortadores)
    return base, malla_letra, {"pared_mm": pared, "avisos": avisos}


# ---------------------------------------------------------------------------
#  Separadores
# ---------------------------------------------------------------------------

SEP_DIAMETRO_DEFAULT = 28.0
SEP_LARGO_DEFAULT = 10.0
SEP_AGUJERO_DEFAULT = 10.0
FORMA_LADO_DEFAULT = 80.0
FORMA_ALTO_DEFAULT = ALTO_DEFAULT
FORMA_AGUJERO_DEFAULT = 8.0


def armar_separador_cilindro(diametro=SEP_DIAMETRO_DEFAULT, largo=SEP_LARGO_DEFAULT,
                             agujero=SEP_AGUJERO_DEFAULT, perfil="rombo", chanfle=CHANFLE_DEFAULT):
    """Separador cilíndrico: un tubito corto con el agujero a lo largo del eje
    (el hilo lo atraviesa de punta a punta). Se imprime parado (eje en Z), apoyado
    en Z=0. Devuelve `(malla, avisos)`."""
    if diametro <= 0 or largo <= 0 or agujero <= 0:
        raise ValueError("diámetro, largo y agujero del separador tienen que ser mayores que 0")
    seccion = perfil_agujero(perfil, agujero)
    circulo = Point(0, 0).buffer(diametro / 2, quad_segs=SEGMENTOS_CIRCULO // 4)
    if not circulo.contains(seccion):
        raise ValueError(
            f"el agujero de {agujero:g} mm no entra en un separador de {diametro:g} mm de diámetro")
    avisos = []
    if not Point(0, 0).buffer(diametro / 2 - PARED_MIN_MM).contains(seccion):
        avisos.append(
            f"Al separador le queda menos de {PARED_MIN_MM} mm de pared alrededor del agujero: "
            f"agrandá el diámetro o achicá el agujero.")
    prisma = trimesh.creation.extrude_polygon(seccion, height=largo + 2.0)
    prisma.apply_translation([0, 0, -1.0])
    return _restar(_cuerpo_cilindro(diametro, largo, chanfle), prisma), avisos


def contorno_forma(lado_mm, nombre=None, ruta_svg=None):
    """Contorno de un separador de forma (estrella, corazón, un SVG...) como
    polígono en mm, centrado en el origen y escalado para que su lado más largo
    mida `lado_mm`. Elegí una forma con `nombre` (de `decoraciones.NOMBRES_VALIDOS`)
    o con `ruta_svg`. Devuelve None si la forma no tiene área.

    El origen es por donde pasa el agujero del hilo: normalmente el centro de la
    caja de la forma, pero si ahí no hay material (una luna en creciente, un anillo)
    se recentra sobre el punto más interior de la forma para que el agujero tenga
    por dónde pasar."""
    if ruta_svg:
        poligono = decoraciones.forma_desde_svg(ruta_svg, 1.0)
    elif nombre:
        poligono = decoraciones.forma(nombre, 1.0)
    else:
        raise ValueError("pedí la forma por `nombre` o por `ruta_svg`")
    if poligono is None or poligono.is_empty:
        return None
    minx, miny, maxx, maxy = poligono.bounds
    lado_mayor = max(maxx - minx, maxy - miny)
    if lado_mayor <= 0:
        return None
    k = lado_mm / lado_mayor
    poligono = translate(poligono, xoff=-(minx + maxx) / 2, yoff=-(miny + maxy) / 2)
    poligono = escalar_geom(poligono, xfact=k, yfact=k, origin=(0, 0)).buffer(0)
    if not poligono.contains(Point(0, 0)):
        mayor = max(poligono.geoms, key=lambda g: g.area) if poligono.geom_type == "MultiPolygon" else poligono
        interior = polylabel(mayor, tolerance=0.1)
        poligono = translate(poligono, xoff=-interior.x, yoff=-interior.y)
    return poligono


SALIDA_IGNORADA_MM = 2.0  # al salir por un borde curvo el ancho tiende a 0 sí o sí: no cuenta


def ancho_minimo_en_el_paso(contorno, angulo_deg, paso_mm=1.0, ignorar_salida_mm=SALIDA_IGNORADA_MM):
    """Ancho MÍNIMO (perpendicular a la dirección del agujero) que tiene el
    contorno a lo largo del camino que recorre el agujero por su centro. Si es
    menor que el ancho del agujero más las paredes, el agujero abre una ranura en
    el costado de la pieza (típico en la punta de una estrella).

    Los últimos `ignorar_salida_mm` antes de cada salida no se miden: contra
    cualquier borde curvo el ancho tiende a 0 justo ahí (es el agujero asomando
    por la pared, no un adelgazamiento de la pieza), y mediría la posición de la
    última muestra en vez de la forma. Una punta angosta sí se detecta, porque
    ya está angosta mucho antes de llegar a la salida. Devuelve None si el
    camino no pasa por el interior del contorno."""
    a = np.radians(angulo_deg)
    dx, dy = np.cos(a), np.sin(a)
    nx, ny = -dy, dx
    minx, miny, maxx, maxy = contorno.bounds
    largo = float(np.hypot(maxx - minx, maxy - miny))
    origen = Point(0, 0)
    camino = contorno.intersection(LineString([(-dx * largo, -dy * largo), (dx * largo, dy * largo)]))
    tramos = [g for g in (camino.geoms if hasattr(camino, "geoms") else [camino])
              if g.geom_type == "LineString" and g.length > 0 and g.distance(origen) < 1e-6]
    if not tramos:
        return None
    ts = [x * dx + y * dy for x, y in tramos[0].coords]
    t0, t1 = min(ts) + ignorar_salida_mm, max(ts) - ignorar_salida_mm
    estaciones = [0.0] if t1 <= t0 else list(np.arange(t0, t1, paso_mm)) + [t1]

    minimo = None
    for t in estaciones:
        cx, cy = t * dx, t * dy
        centro = Point(cx, cy)
        cruce = contorno.intersection(LineString([(cx - nx * largo, cy - ny * largo),
                                                  (cx + nx * largo, cy + ny * largo)]))
        tramos_cruce = list(cruce.geoms) if hasattr(cruce, "geoms") else [cruce]
        ancho = max((g.length for g in tramos_cruce if g.distance(centro) < 1e-6), default=0.0)
        minimo = ancho if minimo is None else min(minimo, ancho)
    return minimo


def armar_separador_forma(contorno, alto=FORMA_ALTO_DEFAULT, agujero=FORMA_AGUJERO_DEFAULT,
                          perfil=PERFILES_AGUJERO[0], angulo_agujero=0.0):
    """Separador con forma (estrella, corazón...): el `contorno` extruido `alto`
    mm, apoyado en Z=0 y con el agujero cruzándolo de lado a lado por su centro,
    a media altura -- igual que una cuenta pero con otro contorno (y sin chanfle:
    las aristas quedan rectas). Devuelve `(malla, avisos)`."""
    if contorno is None or contorno.is_empty:
        raise ValueError("el separador de forma necesita un contorno con área")
    if alto <= 0 or agujero <= 0:
        raise ValueError("alto y agujero del separador de forma tienen que ser mayores que 0")
    avisos = []
    z_centro = alto / 2
    techo = altura_techo_agujero(perfil, agujero)
    piso = z_centro + perfil_agujero(perfil, agujero).bounds[1]  # bounds[1] es negativo: z del fondo del agujero
    if alto - (z_centro + techo) < PARED_MIN_MM or piso < PARED_MIN_MM:
        avisos.append(
            f"El agujero de {agujero:g} mm es muy grande para un separador de {alto:g} mm de alto: "
            f"le queda menos de {PARED_MIN_MM} mm de pared arriba o abajo.")
    minimo = ancho_minimo_en_el_paso(contorno, angulo_agujero)
    if minimo is None:
        raise ValueError("el agujero no pasa por el centro de la forma (¿el contorno no cubre el origen?)")
    if minimo < agujero + 2 * PARED_MIN_MM:
        avisos.append(
            f"A lo largo del agujero la forma se angosta hasta {minimo:.1f} mm, menos que el agujero "
            f"({agujero:g} mm) más sus paredes: el agujero abriría una ranura en el costado. Agrandá la forma, achicá el "
            f"agujero o probá otro ángulo.")

    piezas = mesh3d.piezas_desde_geom(contorno, alto)
    cuerpo = trimesh.util.concatenate(piezas) if len(piezas) > 1 else piezas[0]
    minx, miny, maxx, maxy = contorno.bounds
    largo_agujero = float(np.hypot(maxx - minx, maxy - miny)) * 1.5 + 4
    return _restar(cuerpo, _malla_agujero(perfil, agujero, largo_agujero, angulo_agujero, z_centro)), avisos


# ---------------------------------------------------------------------------
#  Secuencia: texto + separadores -> lista de piezas a armar
# ---------------------------------------------------------------------------

SLOTS_SEPARADOR = ("entre_letras", "entre_palabras", "inicio", "final")
TIPOS_SEPARADOR = ("ninguno", "cilindro", "forma")
MODOS_CUENTA = ("letra", "sticker")


def _normalizar_separadores(separadores):
    """Completa `separadores` (dict slot -> {"tipo", "forma"}) con "ninguno" en
    los slots que falten y valida. "entre_palabras" admite además "igual" (usar
    lo mismo que entre letras), que es su valor si no se pide nada."""
    normal = {slot: {"tipo": "ninguno", "forma": None} for slot in SLOTS_SEPARADOR}
    normal["entre_palabras"]["tipo"] = "igual"
    for slot, cfg in (separadores or {}).items():
        if slot not in SLOTS_SEPARADOR:
            raise ValueError(f"slot de separador desconocido {slot!r}: usá {SLOTS_SEPARADOR}")
        cfg = dict(cfg) if isinstance(cfg, dict) else {"tipo": cfg}
        tipo = cfg.get("tipo", "ninguno")
        validos = TIPOS_SEPARADOR + (("igual",) if slot == "entre_palabras" else ())
        if tipo not in validos:
            raise ValueError(f"tipo de separador {tipo!r} inválido para {slot!r}: usá {validos}")
        if tipo == "forma":
            forma = cfg.get("forma") or {}
            if not (forma.get("nombre") or forma.get("svg")):
                raise ValueError(f"el separador de forma de {slot!r} necesita una forma (nombre o svg)")
        normal[slot] = {"tipo": tipo, "forma": cfg.get("forma")}
    return normal


def armar_secuencia(texto, separadores=None):
    """Lista ordenada de lo que va en el collar, de izquierda a derecha:
    `{"tipo": "cuenta", "caracter": "M"}` por cada carácter que no sea un
    espacio, y `{"tipo": "separador", "slot": ..., "sep": {"tipo", "forma"}}`
    entre/alrededor de las cuentas según `separadores`. Los espacios (uno o
    muchos) parten palabras: ahí va el separador "entre_palabras"."""
    cfg = _normalizar_separadores(separadores)
    palabras = texto.split()
    if not palabras:
        raise ValueError("escribí al menos una letra")

    def sep_de(slot):
        sep = cfg[slot]
        if sep["tipo"] == "igual":
            sep = cfg["entre_letras"]
        return None if sep["tipo"] == "ninguno" else {"tipo": "separador", "slot": slot, "sep": sep}

    secuencia = []

    def agregar_sep(slot):
        item = sep_de(slot)
        if item:
            secuencia.append(item)

    agregar_sep("inicio")
    for i, palabra in enumerate(palabras):
        if i > 0:
            agregar_sep("entre_palabras")
        for j, caracter in enumerate(palabra):
            if j > 0:
                agregar_sep("entre_letras")
            secuencia.append({"tipo": "cuenta", "caracter": caracter})
    agregar_sep("final")
    return secuencia


# ---------------------------------------------------------------------------
#  Armado del collar completo
# ---------------------------------------------------------------------------

ALTO_LETRA_PORCENTAJE_DEFAULT = 0.6   # alto de la mayúscula como fracción del diámetro de la cuenta
CARPETA_SALIDA = "output"


def _clave_forma(forma):
    return ("forma", "nombre", forma["nombre"]) if forma.get("nombre") else ("forma", "svg", forma["svg"])


def _etiqueta_forma(forma):
    return forma["nombre"] if forma.get("nombre") else os.path.splitext(os.path.basename(forma["svg"]))[0]


def _rotar_z(malla, grados):
    m = malla.copy()
    if grados:
        m.apply_transform(trimesh.transformations.rotation_matrix(np.radians(grados), [0, 0, 1]))
    return m


def _colocar_en_fila(malla, cursor_x, z_eje, malla_ref=None):
    """Mueve `malla` (ya rotada para que su agujero corra a lo largo de X) para
    que su borde izquierdo quede en `cursor_x`, centrada en Y=0. `z_eje` es la
    altura Z donde tiene que quedar el eje del agujero (para que todas las piezas
    enfilen el mismo hilo). Devuelve `(malla_movida, ancho_en_x)`."""
    m = malla.copy()
    ancho = float(m.bounds[1][0] - m.bounds[0][0])
    m.apply_translation([cursor_x - m.bounds[0][0], 0, z_eje])
    return m, ancho


def generar(texto, ruta_ttf=None, modo_cuenta="letra",
            diametro=DIAMETRO_DEFAULT, alto=ALTO_DEFAULT, agujero=AGUJERO_DEFAULT, chanfle=CHANFLE_DEFAULT,
            perfil=PERFILES_AGUJERO[0], angulo_agujero=0.0,
            alto_letra_mm=None, profundidad_hueco=PROFUNDIDAD_HUECO_DEFAULT, holgura=HOLGURA_DEFAULT, relieve=0.0,
            rebaje_sticker_diametro=None, rebaje_sticker_profundidad=REBAJE_PROFUNDIDAD_DEFAULT,
            separadores=None, sep_diametro=SEP_DIAMETRO_DEFAULT, sep_largo=SEP_LARGO_DEFAULT,
            sep_agujero=SEP_AGUJERO_DEFAULT, sep_perfil="rombo",
            forma_lado=FORMA_LADO_DEFAULT, forma_alto=FORMA_ALTO_DEFAULT, forma_agujero=FORMA_AGUJERO_DEFAULT,
            color_cuenta="Blanco", color_letra="Negro", color_separador="Naranja",
            carpeta_salida=CARPETA_SALIDA, prefijo=None, agrupar_repetidas=False):
    """Arma un collar completo y exporta los STL de TODAS sus piezas, una por una,
    numeradas en el orden en que van en el collar (`..._04_cuenta_E_base.stl`,
    `..._04_cuenta_E_letra.stl`): la misma letra dos veces o la misma estrella al
    principio y al final salen como piezas separadas, así la muestra está completa.

    Con `agrupar_repetidas=True` las piezas idénticas se exportan una sola vez, con
    la cantidad a imprimir en el nombre del archivo (`..._x7.stl`).

    `texto`: una cuenta por cada carácter que no sea espacio (los espacios parten
    palabras). `modo_cuenta`: "letra" (letra encastrada en la tapa) o "sticker"
    (tapa lisa, con rebaje circular si se pasa `rebaje_sticker_diametro`).
    `separadores`: ver `armar_secuencia` (slots entre_letras / entre_palabras /
    inicio / final, cada uno ninguno | cilindro | forma).

    Devuelve un dict con `piezas` (lo exportado), `armado` (lista de
    `(malla, color_hex, etiqueta)` del collar acostado en fila, para el visor 3D),
    `avisos`, `info`, y las medidas del collar."""
    if modo_cuenta not in MODOS_CUENTA:
        raise ValueError(f"modo_cuenta debe ser uno de {MODOS_CUENTA}, recibí {modo_cuenta!r}")
    if modo_cuenta == "letra" and not (ruta_ttf and os.path.exists(ruta_ttf)):
        raise FileNotFoundError(f"no encuentro la fuente: {ruta_ttf}")
    if sep_perfil not in PERFILES_AGUJERO_SEPARADOR:
        raise ValueError(f"sep_perfil debe ser uno de {PERFILES_AGUJERO_SEPARADOR}, recibí {sep_perfil!r}")

    secuencia = armar_secuencia(texto, separadores)
    avisos = []

    def aviso(prefijo_aviso, lista):
        for a in lista:
            mensaje = f"{prefijo_aviso}: {a}"
            if mensaje not in avisos:
                avisos.append(mensaje)

    # --- cuentas (una por carácter distinto) ---------------------------------
    caracteres = list(dict.fromkeys(i["caracter"] for i in secuencia if i["tipo"] == "cuenta"))
    cuentas = {}  # clave -> (base, letra_ensamblada | None)
    if modo_cuenta == "letra":
        alto_letra = alto_letra_mm if alto_letra_mm else ALTO_LETRA_PORCENTAJE_DEFAULT * diametro
        poligonos = {}
        for c in caracteres:
            p = letra_poligono(c, ruta_ttf, alto_letra)
            if p is None:
                raise ValueError(f"la fuente no tiene forma para el carácter {c!r}")
            poligonos[c] = p
        limite = diametro / 2 - MARGEN_BORDE_LETRA_MM - holgura
        mas_lejos = max(extension_radial(p) for p in poligonos.values())
        if mas_lejos > limite:
            factor = limite / mas_lejos
            poligonos = {c: escalar_geom(p, xfact=factor, yfact=factor, origin=(0, 0)) for c, p in poligonos.items()}
            avisos.append(
                f"Las letras no entraban en la cuenta con el margen de {MARGEN_BORDE_LETRA_MM:g} mm: "
                f"las achiqué todas juntas al {factor * 100:.0f}% (mayúscula de {alto_letra * factor:.1f} mm).")
        for c, p in poligonos.items():
            base, letra, info = armar_cuenta(
                p, diametro=diametro, alto=alto, agujero=agujero, chanfle=chanfle, perfil=perfil,
                angulo_agujero=angulo_agujero, profundidad_hueco=profundidad_hueco, holgura=holgura,
                relieve=relieve)
            cuentas[("letra", c)] = (base, letra)
            aviso(f"Cuenta '{c}'", info["avisos"])
    else:
        base, _, info = armar_cuenta(
            None, diametro=diametro, alto=alto, agujero=agujero, chanfle=chanfle, perfil=perfil,
            angulo_agujero=angulo_agujero, rebaje_sticker_diametro=rebaje_sticker_diametro,
            rebaje_sticker_profundidad=rebaje_sticker_profundidad, holgura=holgura)
        cuentas[("lisa",)] = (base, None)
        aviso("Cuenta lisa", info["avisos"])

    def clave_cuenta(item):
        return ("letra", item["caracter"]) if modo_cuenta == "letra" else ("lisa",)

    # --- separadores (cilindro y una forma por cada forma distinta) ------------
    separadores_mallas = {}  # clave -> malla
    etiquetas_sep = {}
    for item in secuencia:
        if item["tipo"] != "separador":
            continue
        sep = item["sep"]
        if sep["tipo"] == "cilindro" and ("cilindro",) not in separadores_mallas:
            malla, av = armar_separador_cilindro(sep_diametro, sep_largo, sep_agujero, sep_perfil, chanfle)
            separadores_mallas[("cilindro",)] = malla
            etiquetas_sep[("cilindro",)] = "cilindro"
            aviso("Separador cilíndrico", av)
        elif sep["tipo"] == "forma":
            clave = _clave_forma(sep["forma"])
            if clave not in separadores_mallas:
                contorno = contorno_forma(forma_lado, nombre=sep["forma"].get("nombre"), ruta_svg=sep["forma"].get("svg"))
                etiqueta = _etiqueta_forma(sep["forma"])
                if contorno is None:
                    raise ValueError(f"la forma {etiqueta!r} no tiene ninguna parte con área")
                malla, av = armar_separador_forma(contorno, forma_alto, forma_agujero, perfil, angulo_agujero)
                separadores_mallas[clave] = malla
                etiquetas_sep[clave] = etiqueta
                aviso(f"Separador '{etiqueta}'", av)

    def clave_separador(item):
        return ("cilindro",) if item["sep"]["tipo"] == "cilindro" else _clave_forma(item["sep"]["forma"])

    # --- exportar un STL por pieza distinta ------------------------------------
    os.makedirs(carpeta_salida, exist_ok=True)
    prefijo = prefijo or pieza.nombre_archivo(texto, default="collar")
    conteo_cuentas, conteo_sep = {}, {}
    for item in secuencia:
        if item["tipo"] == "cuenta":
            conteo_cuentas[clave_cuenta(item)] = conteo_cuentas.get(clave_cuenta(item), 0) + 1
        else:
            conteo_sep[clave_separador(item)] = conteo_sep.get(clave_separador(item), 0) + 1

    piezas = []
    nombres_salida = []

    def exportar(malla, nombre_base, cantidad, tipo, etiqueta, color_nombre, posicion=None):
        sufijo = f"_x{cantidad}" if cantidad > 1 else ""
        ruta = os.path.join(carpeta_salida, f"{prefijo}_{nombre_base}{sufijo}.stl")
        m = malla.copy()
        m.apply_translation([0, 0, -m.bounds[0][2]])  # apoyada en la cama
        m.export(ruta)
        ext = m.extents
        entra, mensaje = bambu_a1.chequear_tamano(ext[0], ext[1], ext[2], nombre=etiqueta)
        if not entra and mensaje not in avisos:
            avisos.append(mensaje)
        piezas.append({
            "tipo": tipo, "etiqueta": etiqueta, "cantidad": cantidad, "posicion": posicion, "ruta_stl": ruta,
            "color": color_nombre, "color_hex": colores.hex_de(color_nombre),
            "vertices": len(m.vertices), "watertight": m.is_watertight,
            "ancho_mm": float(ext[0]), "alto_mm": float(ext[1]), "espesor_mm": float(ext[2]),
        })
        nombres_salida.append(ruta)

    if agrupar_repetidas:
        for k, (clave, (base, letra)) in enumerate(cuentas.items(), start=1):
            cantidad = conteo_cuentas.get(clave, 0)
            if modo_cuenta == "letra":
                c = clave[1]
                seguro = pieza.nombre_archivo(c, default=f"u{ord(c):04x}")
                exportar(base, f"cuenta_{k:02d}_{seguro}_base", cantidad, "cuenta", f"cuenta {c}", color_cuenta)
                exportar(letra, f"cuenta_{k:02d}_{seguro}_letra", cantidad, "letra", f"letra {c}", color_letra)
            else:
                exportar(base, "cuenta_lisa", cantidad, "cuenta", "cuenta lisa", color_cuenta)
        for clave, malla in separadores_mallas.items():
            etiqueta = etiquetas_sep[clave]
            exportar(malla, f"separador_{pieza.nombre_archivo(etiqueta, default='forma')}", conteo_sep[clave],
                     "separador", f"separador {etiqueta}", color_separador)
    else:
        # una pieza por lugar del collar, numerada: el número en el nombre también evita que "e" y "E" (o
        # dos formas iguales) se pisen en un sistema de archivos que no distingue mayúsculas
        ancho_numero = max(2, len(str(len(secuencia))))
        for pos, item in enumerate(secuencia, start=1):
            numero = f"{pos:0{ancho_numero}d}"
            if item["tipo"] == "cuenta":
                base, letra = cuentas[clave_cuenta(item)]
                if modo_cuenta == "letra":
                    c = item["caracter"]
                    seguro = pieza.nombre_archivo(c, default=f"u{ord(c):04x}")
                    exportar(base, f"{numero}_cuenta_{seguro}_base", 1, "cuenta", f"cuenta {c}", color_cuenta, pos)
                    exportar(letra, f"{numero}_cuenta_{seguro}_letra", 1, "letra", f"letra {c}", color_letra, pos)
                else:
                    exportar(base, f"{numero}_cuenta_lisa", 1, "cuenta", "cuenta lisa", color_cuenta, pos)
            else:
                clave = clave_separador(item)
                etiqueta = etiquetas_sep[clave]
                exportar(separadores_mallas[clave], f"{numero}_separador_{pieza.nombre_archivo(etiqueta, default='forma')}",
                         1, "separador", f"separador {etiqueta}", color_separador, pos)

    # --- armado: el collar acostado en fila (para el visor 3D) -----------------
    armado = []
    cursor = 0.0
    z_eje = alto / 2
    for item in secuencia:
        if item["tipo"] == "cuenta":
            base, letra = cuentas[clave_cuenta(item)]
            base_rotada = _rotar_z(base, -angulo_agujero)
            base_r, ancho = _colocar_en_fila(base_rotada, cursor, 0.0)
            armado.append((base_r, colores.hex_de(color_cuenta), f"cuenta {item['caracter']}"))
            if letra is not None:
                # la letra recibe EXACTO el mismo desplazamiento que su cuenta
                letra_r = _rotar_z(letra, -angulo_agujero)
                letra_r.apply_translation(base_r.bounds[0] - base_rotada.bounds[0])
                armado.append((letra_r, colores.hex_de(color_letra), f"letra {item['caracter']}"))
        else:
            clave = clave_separador(item)
            malla = separadores_mallas[clave]
            if clave == ("cilindro",):
                # se imprime parado (eje en Z): acostarlo para que el eje corra a lo largo de X
                m = malla.copy()
                m.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0]))
                m.apply_translation([0, 0, z_eje - (m.bounds[0][2] + m.bounds[1][2]) / 2])
                colocado, ancho = _colocar_en_fila(m, cursor, 0.0)
            else:
                m = _rotar_z(malla, -angulo_agujero)
                colocado, ancho = _colocar_en_fila(m, cursor, z_eje - forma_alto / 2)
            armado.append((colocado, colores.hex_de(color_separador), f"separador {etiquetas_sep[clave]}"))
        cursor += ancho

    n_cuentas = sum(conteo_cuentas.values())
    n_separadores = sum(conteo_sep.values())
    if agrupar_repetidas:
        info = [
            f"{n_cuentas} cuenta(s) y {n_separadores} separador(es) en {len(piezas)} pieza(s) distinta(s). "
            "Las repetidas salen una sola vez: imprimí tantas copias como indica el nombre del archivo (_x7 = 7 copias)."
        ]
    else:
        info = [
            f"{n_cuentas} cuenta(s) y {n_separadores} separador(es): {len(piezas)} archivo(s) STL, uno por cada pieza "
            "del collar, numerados en el orden en que van (01, 02, 03...)."
        ]
    if modo_cuenta == "letra":
        info.append("Cada letra va en su propio STL, apoyada en la cama: imprimila aparte (en su color) y encastrala en la tapa de su cuenta.")
    return {
        "texto": texto,
        "piezas": piezas,
        "rutas_stl": nombres_salida,
        "armado": armado,
        "n_cuentas": n_cuentas,
        "n_separadores": n_separadores,
        "largo_mm": cursor,
        "avisos": avisos,
        "info": info,
    }


# ---------------------------------------------------------------------------
#  Interfaz de consola (menú de main.py)
# ---------------------------------------------------------------------------
def _elegir_fuente():
    print("  Fuentes: escribí un nombre (ej. 'Anton') o dejá vacío para 'Anton'.")
    eleccion = ui.pedir_texto("Fuente", "Anton")
    if os.path.exists(eleccion):
        return eleccion
    encontrada = fuentes.buscar_por_nombre(eleccion)
    if encontrada:
        print(f"    -> usando {encontrada}")
        return encontrada
    return eleccion


def _pedir_separador(titulo, opciones, default):
    tipo = ui.pedir_opcion(titulo, opciones, default)
    if tipo != "forma":
        return tipo
    nombre = ui.pedir_opcion("  ¿Qué forma?", [n for n in decoraciones.NOMBRES_VALIDOS if n != "ninguno"], "estrella")
    return {"tipo": "forma", "forma": {"nombre": nombre}}


def ejecutar():
    print(f"\n{NOMBRE}")

    texto = ui.pedir_texto("Texto (una cuenta por letra, los espacios parten palabras)", "ME RECIBI")
    modo = ui.pedir_opcion("Cuenta", list(MODOS_CUENTA), "letra")
    ruta_ttf = _elegir_fuente() if modo == "letra" else None
    perfil = ui.pedir_opcion("Forma del agujero para el hilo", PERFILES_AGUJERO, PERFILES_AGUJERO[0])
    angulo = ui.pedir_float("Ángulo del agujero respecto de la letra (grados)", 0.0)
    rebaje = None
    if modo == "sticker":
        d = ui.pedir_float("Diámetro del rebaje para el sticker en mm (0 = tapa lisa)", 0.0)
        rebaje = d if d > 0 else None
    sep = {
        "entre_letras": _pedir_separador("Separador entre letras", ["ninguno", "cilindro", "forma"], "cilindro"),
        "entre_palabras": _pedir_separador("Separador entre palabras", ["igual", "ninguno", "cilindro", "forma"], "igual"),
        "inicio": _pedir_separador("Separador al principio", ["ninguno", "cilindro", "forma"], "ninguno"),
        "final": _pedir_separador("Separador al final", ["ninguno", "cilindro", "forma"], "ninguno"),
    }

    try:
        r = generar(texto, ruta_ttf, modo_cuenta=modo, perfil=perfil, angulo_agujero=angulo,
                    rebaje_sticker_diametro=rebaje, separadores=sep)
    except (FileNotFoundError, ValueError) as e:
        print(f"  ERROR: {e}")
        return

    print(f"  collar de ~{r['largo_mm']:.0f} mm: {r['n_cuentas']} cuenta(s), {r['n_separadores']} separador(es)")
    for nota in r["info"]:
        print(f"  · {nota}")
    for aviso in r["avisos"]:
        print(f"  ⚠ {aviso}")
    for p in r["piezas"]:
        print(f"  ✓ {p['etiqueta']} x{p['cantidad']} -> {p['ruta_stl']}  (watertight={p['watertight']})")
    print()
