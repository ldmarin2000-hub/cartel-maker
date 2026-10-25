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
DESCRIPCION = "Collar o pulsera de cuentas con letra encastrada (cuenta redonda, cuadrada o con la forma de la letra + separadores)"

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
CAPA_MM = 0.2                    # alto de capa de impresión: el chanfle de las formas no redondas se arma por capas

FORMAS_CUENTA = ("redonda", "cuadrada", "letra")
RADIO_ESQUINA_PORCENTAJE = 0.25  # esquina de la cuenta cuadrada, como fracción de su lado
BORDE_LETRA_DEFAULT = 4.0        # mm de borde alrededor de la letra cuando la cuenta tiene la forma de la letra

# Medidas listas para usar: el collar grande (las de la cuenta de Fusion 360) y la pulsera chica. Todo
# sigue siendo editable; esto es solo el punto de partida de la página y de la consola.
PRESETS_MEDIDAS = {
    "collar": {
        "diametro": DIAMETRO_DEFAULT, "alto": ALTO_DEFAULT, "agujero": AGUJERO_DEFAULT, "chanfle": CHANFLE_DEFAULT,
        "alto_letra": 42.0, "profundidad_hueco": PROFUNDIDAD_HUECO_DEFAULT, "holgura": HOLGURA_DEFAULT,
        "margen_letra": MARGEN_BORDE_LETRA_MM, "pared_min": PARED_MIN_MM,
        "radio_esquina": 17.5, "borde_letra": BORDE_LETRA_DEFAULT, "rebaje_diametro": 50.0,
        "sep_diametro": 28.0, "sep_largo": 10.0, "sep_agujero": 10.0, "sep_perfil": "rombo",
        "forma_lado": 80.0, "forma_alto": ALTO_DEFAULT, "forma_agujero": 8.0, "forma_perfil": "rombo",
    },
    "pulsera": {
        "diametro": 12.0, "alto": 7.0, "agujero": 2.5, "chanfle": 0.4,
        "alto_letra": 7.0, "profundidad_hueco": 1.0, "holgura": 0.1,
        "margen_letra": 1.0, "pared_min": 0.8,
        "radio_esquina": 3.0, "borde_letra": 1.5, "rebaje_diametro": 9.0,
        # el cilindro se imprime PARADO: ahí el agujero redondo no necesita soporte y, como los agujeros
        # verticales salen apenas más chicos de lo pedido, se le da 0,3 mm de más. Las formas se imprimen
        # acostadas, igual que la cuenta: rombo (o gota) para no llevar soportes.
        "sep_diametro": 7.0, "sep_largo": 3.0, "sep_agujero": 2.8, "sep_perfil": "redondo",
        "forma_lado": 14.0, "forma_alto": 7.0, "forma_agujero": 2.5, "forma_perfil": "rombo",
    },
}
TIPOS_PIEZA = tuple(PRESETS_MEDIDAS)


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


def contorno_cuenta(forma, diametro, poligono_letra=None, radio_esquina=None, borde_letra=BORDE_LETRA_DEFAULT):
    """Silueta de la cuenta vista desde arriba, como polígono centrado en el origen.

    * "redonda": círculo de `diametro`.
    * "cuadrada": cuadrado de lado `diametro` con las esquinas redondeadas a `radio_esquina`
      (por defecto el 25% del lado).
    * "letra": la propia letra agrandada `borde_letra` mm por todos lados -- una cuenta con la
      forma de la letra y un bordecito. Necesita `poligono_letra`. Si con ese borde la letra queda
      en pedazos sueltos (la tilde de una Ñ, el punto de una i) da error: se arregla con más borde
      o con otra letra/fuente."""
    if forma == "redonda":
        return Point(0, 0).buffer(diametro / 2, quad_segs=SEGMENTOS_CIRCULO // 4)
    if forma == "cuadrada":
        r = diametro * RADIO_ESQUINA_PORCENTAJE if radio_esquina is None else radio_esquina
        r = max(0.0, min(r, diametro / 2))
        mitad = diametro / 2
        if r <= 0:
            return box(-mitad, -mitad, mitad, mitad)
        return box(-(mitad - r), -(mitad - r), mitad - r, mitad - r).buffer(r, quad_segs=16)
    if forma == "letra":
        if poligono_letra is None:
            raise ValueError("la cuenta con forma de letra necesita una letra")
        if borde_letra < 0:
            raise ValueError("el borde de la letra no puede ser negativo")
        contorno = poligono_letra.buffer(borde_letra, join_style="round", quad_segs=16)
        contorno = contorno.simplify(0.02, preserve_topology=True)
        if contorno.geom_type == "MultiPolygon":
            raise ValueError(
                f"con un borde de {borde_letra:g} mm la letra queda en pedazos separados (tilde, punto...): "
                "aumentá el borde o usá otra letra/fuente")
        return contorno
    raise ValueError(f"forma de la cuenta debe ser una de {FORMAS_CUENTA}, recibí {forma!r}")


def _cuerpo_por_capas(contorno, alto, chanfle, capa=CAPA_MM):
    """Contorno cualquiera extruido `alto` mm, con chanfle de 45° arriba y abajo hecho por CAPAS:
    cada `capa` mm el contorno se achica lo que le toca a esa altura. La impresora corta en capas de
    todos modos, así que un chanfle escalonado a ese paso se imprime igual que uno liso."""
    n = int(round(min(chanfle, alto / 2 - capa) / capa)) if chanfle > 0 else 0
    if n < 1:
        piezas = mesh3d.piezas_desde_geom(contorno, alto)
        return trimesh.util.concatenate(piezas) if len(piezas) > 1 else piezas[0]
    c = n * capa
    losas = []
    for k in range(n):
        achique = c - (k + 0.5) * capa  # 45°: a la altura z del chanfle se achica c - z
        achicado = contorno.buffer(-achique, join_style="round", quad_segs=16)
        if achicado.is_empty:
            continue
        losas.extend(mesh3d.piezas_desde_geom(achicado, capa, z=k * capa))                 # abajo
        losas.extend(mesh3d.piezas_desde_geom(achicado, capa, z=alto - (k + 1) * capa))    # arriba
    losas.extend(mesh3d.piezas_desde_geom(contorno, alto - 2 * c, z=c))
    cuerpo = trimesh.boolean.union(losas, engine="manifold")
    cuerpo.merge_vertices()
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
    # tolerancia de simplificado proporcional al tamaño: 0,15 mm para una letra de 42 mm (como siempre),
    # pero 0,025 mm para una de 7 mm -- con 0,15 las curvas de una letra chica quedarían facetadas
    tolerancia = max(0.02, min(texto2d.SIMPLIFY_MM, alto_mayuscula_mm * texto2d.SIMPLIFY_MM / 42.0))
    return poligono.simplify(tolerancia, preserve_topology=True)


def extension_cuadrada(poligono):
    """Mayor distancia, medida en X o en Y (no en diagonal), del centro a `poligono`: lo que
    importa para que una letra entre en una cuenta cuadrada."""
    if poligono is None or poligono.is_empty:
        return 0.0
    minx, miny, maxx, maxy = poligono.bounds
    return float(max(abs(minx), abs(maxx), abs(miny), abs(maxy)))


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
                 rebaje_sticker_profundidad=REBAJE_PROFUNDIDAD_DEFAULT,
                 forma_cuenta="redonda", radio_esquina=None, borde_letra=BORDE_LETRA_DEFAULT,
                 pared_min=PARED_MIN_MM):
    """Arma una cuenta: devuelve `(base, letra, info)`.

    * `base`: el cuerpo de la cuenta con chanfle, con el agujero para el hilo y (si hay
      `poligono_letra`) el hueco donde encastra la letra. Apoya en Z=0.
    * `letra`: la pieza suelta, ya EN SU LUGAR dentro del hueco (para
      chequear el encastre / mostrar el armado). Su parte de abajo queda
      `profundidad_hueco` por debajo de la tapa y sobresale `relieve` mm
      (0 = al ras). `None` si no hay letra.
    * `info`: `{"pared_mm", "avisos"}` -- `pared_mm` es el espesor que queda
      entre el techo del agujero y el fondo del hueco (lo que hay que
      cuidar para que la cuenta no se rompa).

    `forma_cuenta`: la silueta del cuerpo (ver `contorno_cuenta`): "redonda" (`diametro`),
    "cuadrada" (lado `diametro`, esquinas a `radio_esquina`) o "letra" (la propia letra con
    `borde_letra` mm de borde alrededor; en ese caso `diametro` no se usa). `pared_min`: la pared
    mínima aceptable (mm) antes de avisar de fragilidad; 1,2 va bien para un collar, para una
    pulsera de cuentas chicas conviene 0,8 (dos perímetros de boquilla 0,4).

    La letra suelta es la silueta nominal; el hueco es esa silueta
    agrandada `holgura` mm por lado, para que entre sin forzar.

    Modo "lisa para sticker": sin `poligono_letra`, la tapa queda lisa. Si
    además se pasa `rebaje_sticker_diametro` (el diámetro del sticker), la
    tapa lleva un rebaje circular de `rebaje_sticker_profundidad` mm para que
    el sticker quede al ras y no se despegue por los bordes (se le suma
    `holgura` por lado, igual que al hueco de la letra). Es una alternativa
    a la letra encastrada: no se pueden pedir las dos a la vez."""
    if forma_cuenta not in FORMAS_CUENTA:
        raise ValueError(f"forma de la cuenta debe ser una de {FORMAS_CUENTA}, recibí {forma_cuenta!r}")
    if forma_cuenta == "letra" and poligono_letra is None:
        raise ValueError("la cuenta con forma de letra necesita una letra (no existe en modo sticker)")
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
        # borde que tiene que quedar alrededor del rebaje: 3 mm en una cuenta grande, proporcional (10%) en una chica
        borde_min = min(REBAJE_BORDE_MIN_MM, max(1.0, diametro * 0.1))
        if rebaje_sticker_diametro + 2 * holgura > diametro - 2 * borde_min:
            raise ValueError(
                f"el rebaje de {rebaje_sticker_diametro:g} mm no entra en la cuenta de {diametro:g} mm: "
                f"tiene que quedar al menos {borde_min:g} mm de borde (máximo "
                f"{diametro - 2 * borde_min - 2 * holgura:g} mm)"
            )
        if rebaje_sticker_profundidad <= 0 or rebaje_sticker_profundidad >= alto:
            raise ValueError("la profundidad del rebaje tiene que estar entre 0 y el alto de la cuenta")

    contorno = contorno_cuenta(forma_cuenta, diametro, poligono_letra, radio_esquina, borde_letra)

    avisos = []
    z_centro = alto / 2
    techo_agujero = z_centro + altura_techo_agujero(perfil, agujero)
    if hay_rebaje:
        fondo_hueco = alto - rebaje_sticker_profundidad
    else:
        fondo_hueco = alto - profundidad_hueco
    hay_hueco = poligono_letra is not None or hay_rebaje
    pared = fondo_hueco - techo_agujero if hay_hueco else alto - techo_agujero
    if pared < pared_min:
        avisos.append(
            f"Entre el techo del agujero y el fondo del hueco de la letra quedan {pared:.1f} mm "
            f"(menos de {pared_min:g} mm: la cuenta queda frágil). Achicá el agujero, "
            f"agrandá el alto o reducí la profundidad del hueco."
        )
    if z_centro - altura_techo_agujero(perfil, agujero) < 0.5 and perfil != "gota":
        avisos.append("El agujero es casi tan grande como el alto de la cuenta: queda sin piso.")
    if forma_cuenta == "letra":
        # la cuenta con forma de letra es angosta en algunos tramos (una barra de la E, un trazo fino):
        # el agujero tiene que caber con paredes en cada tramo de material que cruza
        minimo = ancho_minimo_en_el_paso(contorno, angulo_agujero)
        if minimo is None:
            raise ValueError("el agujero no cruza la cuenta: a esa altura y ángulo no hay nada de la letra")
        if minimo < agujero + 2 * pared_min:
            avisos.append(
                f"A lo largo del agujero la cuenta se angosta hasta {minimo:.1f} mm, menos que el agujero "
                f"({agujero:g} mm) más sus paredes: abriría una ranura en el costado. Usá una fuente más "
                f"gruesa, una letra más grande, más borde o un agujero más chico.")

    if forma_cuenta == "redonda":
        cuerpo = _cuerpo_cilindro(diametro, alto, chanfle)
        largo_agujero = diametro * 1.5
    else:
        cuerpo = _cuerpo_por_capas(contorno, alto, chanfle)
        minx, miny, maxx, maxy = contorno.bounds
        largo_agujero = max(maxx - minx, maxy - miny) * 1.5 + 4
    cortadores = [_malla_agujero(perfil, agujero, largo_agujero, angulo_agujero, z_centro)]

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
                             agujero=SEP_AGUJERO_DEFAULT, perfil="rombo", chanfle=CHANFLE_DEFAULT,
                             pared_min=PARED_MIN_MM):
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
    if not Point(0, 0).buffer(diametro / 2 - pared_min).contains(seccion):
        avisos.append(
            f"Al separador le queda menos de {pared_min:g} mm de pared alrededor del agujero: "
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
    el costado de la pieza (típico en la punta de una estrella o en la barra de
    una E).

    El camino puede cruzar varios tramos de material (el trazo de una letra, un
    hueco, otro trazo): se mide cada uno. Los últimos `ignorar_salida_mm` de cada
    tramo no se miden: contra cualquier borde curvo el ancho tiende a 0 justo ahí
    (es el agujero asomando por la pared, no un adelgazamiento de la pieza), y
    mediría la posición de la última muestra en vez de la forma. Una punta angosta
    sí se detecta, porque ya está angosta mucho antes de llegar a la salida. En un
    tramo corto (una letra chica) se ignora a lo sumo un cuarto del tramo en cada
    punta, para que siempre se mida la parte de adentro: si no, un tramo de 3 mm se
    mediría una sola vez por el medio y una barra fina que sigue al palo (la de la
    E) pasaría sin avisar. Devuelve None si el camino no toca nada del contorno."""
    a = np.radians(angulo_deg)
    dx, dy = np.cos(a), np.sin(a)
    nx, ny = -dy, dx
    minx, miny, maxx, maxy = contorno.bounds
    largo = float(np.hypot(maxx - minx, maxy - miny))
    camino = contorno.intersection(LineString([(-dx * largo, -dy * largo), (dx * largo, dy * largo)]))
    tramos = [g for g in (camino.geoms if hasattr(camino, "geoms") else [camino])
              if g.geom_type == "LineString" and g.length > 0]
    if not tramos:
        return None

    minimo = None
    for tramo in tramos:
        ts = [x * dx + y * dy for x, y in tramo.coords]
        largo_tramo = max(ts) - min(ts)
        ignorar = min(ignorar_salida_mm, largo_tramo / 4)
        t0, t1 = min(ts) + ignorar, max(ts) - ignorar
        paso = min(paso_mm, largo_tramo / 6)
        estaciones = [(min(ts) + max(ts)) / 2] if t1 <= t0 else list(np.arange(t0, t1, paso)) + [t1]
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
                          perfil=PERFILES_AGUJERO[0], angulo_agujero=0.0, pared_min=PARED_MIN_MM,
                          chanfle=0.0):
    """Separador con forma (estrella, corazón...): el `contorno` extruido `alto`
    mm, apoyado en Z=0 y con el agujero cruzándolo de lado a lado por su centro,
    a media altura -- igual que una cuenta pero con otro contorno. `chanfle` (mm,
    0 = aristas rectas) redondea el borde de arriba y de abajo por capas, como en
    una cuenta no redonda. Devuelve `(malla, avisos)`."""
    if contorno is None or contorno.is_empty:
        raise ValueError("el separador de forma necesita un contorno con área")
    if alto <= 0 or agujero <= 0:
        raise ValueError("alto y agujero del separador de forma tienen que ser mayores que 0")
    avisos = []
    z_centro = alto / 2
    techo = altura_techo_agujero(perfil, agujero)
    piso = z_centro + perfil_agujero(perfil, agujero).bounds[1]  # bounds[1] es negativo: z del fondo del agujero
    if alto - (z_centro + techo) < pared_min or piso < pared_min:
        avisos.append(
            f"El agujero de {agujero:g} mm es muy grande para un separador de {alto:g} mm de alto: "
            f"le queda menos de {pared_min:g} mm de pared arriba o abajo.")
    minimo = ancho_minimo_en_el_paso(contorno, angulo_agujero)
    if minimo is None:
        raise ValueError("el agujero no pasa por el centro de la forma (¿el contorno no cubre el origen?)")
    if minimo < agujero + 2 * pared_min:
        avisos.append(
            f"A lo largo del agujero la forma se angosta hasta {minimo:.1f} mm, menos que el agujero "
            f"({agujero:g} mm) más sus paredes: el agujero abriría una ranura en el costado. Agrandá la forma, achicá el "
            f"agujero o probá otro ángulo.")

    cuerpo = _cuerpo_por_capas(contorno, alto, chanfle)
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


# ---------------------------------------------------------------------------
#  Salida agrupada por color: placas listas para imprimir
# ---------------------------------------------------------------------------

FORMATOS_SALIDA = ("por_pieza", "por_color", "ambos")
CAMA_MM = float(bambu_a1.VOLUMEN_MM[0])   # la A1 es cuadrada: 256 x 256 mm
MARGEN_CAMA_MM = 8.0                      # lo que se deja libre contra el borde de la cama
SEPARACION_PLACA_MM = 4.0                 # aire entre una pieza y la de al lado
ALTURA_MAPA_MM = 0.35                     # a esta altura se corta la pieza para dibujar su silueta en el mapa


def acomodar_en_placas(tamanos, cama=CAMA_MM, margen=MARGEN_CAMA_MM, separacion=SEPARACION_PLACA_MM):
    """Reparte piezas en placas de `cama` x `cama` mm, en filas de izquierda a derecha y de arriba
    abajo, respetando el ORDEN en que vienen (el del collar). `tamanos`: lista de `(ancho, alto)`.

    La primera fila queda contra el fondo de la cama (arriba en la vista de Bambu Studio y en el mapa),
    así la numeración se lee como un texto.

    Devuelve `(colocacion, no_entran)`: `colocacion[i] = (placa, cx, cy)` es el centro de la pieza i
    en coordenadas de la cama (placa empieza en 1), y `no_entran` los índices de las piezas más
    grandes que el área útil de una placa (se colocan igual, solas, para que no se pierdan: el aviso
    es cosa de quien llama). Las piezas nunca se pisan y entre dos vecinas queda `separacion`."""
    util = cama - 2 * margen
    colocacion, no_entran = [], []
    placa, x, y, alto_fila = 1, 0.0, 0.0, 0.0
    hay_algo = False   # ¿hay algo ya en la placa actual?
    for i, (w, h) in enumerate(tamanos):
        if w > util or h > util:
            no_entran.append(i)
        if hay_algo and x + w > util:               # no entra en esta fila: fila nueva
            x, y, alto_fila = 0.0, y + alto_fila + separacion, 0.0
        if hay_algo and y + h > util:               # no entra en esta placa: placa nueva
            placa, x, y, alto_fila, hay_algo = placa + 1, 0.0, 0.0, 0.0, False
        colocacion.append((placa, margen + x + w / 2, cama - margen - y - h / 2))
        x += w + separacion
        alto_fila = max(alto_fila, h)
        hay_algo = True
    return colocacion, no_entran


def _trayecto_matplotlib(poligono):
    """Camino de matplotlib de un polígono shapely con sus huecos (la O, la R...)."""
    from matplotlib.path import Path
    from shapely.geometry.polygon import orient
    poligono = orient(poligono, sign=1.0)   # exterior antihorario, huecos horarios: así se rellena con huecos
    rings = [np.asarray(poligono.exterior.coords)] + [np.asarray(r.coords) for r in poligono.interiors]
    return Path.make_compound_path(*[Path(r, closed=True) for r in rings])


def _poligonos_del_corte(corte):
    """Polígonos (con huecos) de un corte horizontal de una malla. Se arman a partir de los anillos
    del corte: un anillo dentro de otro es un hueco (la O, la R...), uno dentro del hueco es una isla."""
    resultado = None
    for anillo in corte.discrete:
        if len(anillo) < 4:
            continue
        pg = Polygon(np.asarray(anillo)[:, :2]).buffer(0)
        if pg.is_empty:
            continue
        resultado = pg if resultado is None else resultado.symmetric_difference(pg)
    if resultado is None or resultado.is_empty:
        return []
    return list(resultado.geoms) if resultado.geom_type == "MultiPolygon" else [resultado]


def _color_de_texto_sobre(color_hex):
    """Negro o blanco, el que más contraste le haga a `color_hex` (para rotular una pieza de ese color)."""
    r, g, b = (int(color_hex.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    luminancia = 0.299 * r + 0.587 * g + 0.114 * b
    return "#111111" if luminancia > 140 else "#ffffff"


def dibujar_mapa_placa(ruta_png, piezas, titulo):
    """Imagen de una placa: la silueta de cada pieza (ya colocada en la cama) con su número en el collar
    y su letra, para saber cuál es cuál al armar. `piezas`: lista de dicts `{"malla", "texto",
    "color_hex"}`. Devuelve `ruta_png`."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patheffects as efectos
    from matplotlib.patches import PathPatch

    minx = min(p["malla"].bounds[0][0] for p in piezas) - 6
    maxx = max(p["malla"].bounds[1][0] for p in piezas) + 6
    miny = min(p["malla"].bounds[0][1] for p in piezas) - 6
    maxy = max(p["malla"].bounds[1][1] for p in piezas) + 6
    ancho_in = 7.0
    fig, ax = plt.subplots(figsize=(ancho_in, max(1.8, ancho_in * (maxy - miny) / (maxx - minx))))
    pt_por_mm = ancho_in * 72 / (maxx - minx)
    for p in piezas:
        malla = p["malla"]
        z = min(ALTURA_MAPA_MM, float(malla.extents[2]) / 2)
        poligonos = []
        try:
            corte = malla.section(plane_origin=[0, 0, malla.bounds[0][2] + z], plane_normal=[0, 0, 1])
            poligonos = _poligonos_del_corte(corte) if corte is not None else []
        except Exception:
            poligonos = []
        if poligonos:
            for pg in poligonos:
                ax.add_patch(PathPatch(_trayecto_matplotlib(pg), facecolor=p["color_hex"], edgecolor="#333", lw=0.8, alpha=0.85))
        else:  # sin silueta: al menos la caja
            (x0, y0, _), (x1, y1, _) = malla.bounds
            ax.add_patch(plt.Rectangle((x0, y0), x1 - x0, y1 - y0, facecolor=p["color_hex"], edgecolor="#333", lw=0.8, alpha=0.6))
        cx, cy = (malla.bounds[0][0] + malla.bounds[1][0]) / 2, (malla.bounds[0][1] + malla.bounds[1][1]) / 2
        lado = min(malla.extents[0], malla.extents[1])
        color_texto = _color_de_texto_sobre(p["color_hex"])
        contorno_texto = "#ffffff" if color_texto == "#111111" else "#111111"   # halo: se lee aunque pase sobre la pieza
        ax.text(cx, cy, p["texto"], ha="center", va="center", fontsize=max(5.0, min(16.0, 0.32 * lado * pt_por_mm)),
                color=color_texto, fontweight="bold",
                path_effects=[efectos.withStroke(linewidth=2.2, foreground=contorno_texto)])
    ax.set_xlim(minx, maxx)
    ax.set_ylim(miny, maxy)
    ax.set_aspect("equal")
    ax.set_title(titulo, fontsize=9)
    ax.tick_params(labelsize=7)
    ax.set_xlabel("mm (cama de la A1)", fontsize=7)
    fig.tight_layout()
    fig.savefig(ruta_png, dpi=110)
    plt.close(fig)
    return ruta_png


def generar(texto, ruta_ttf=None, modo_cuenta="letra",
            diametro=DIAMETRO_DEFAULT, alto=ALTO_DEFAULT, agujero=AGUJERO_DEFAULT, chanfle=CHANFLE_DEFAULT,
            perfil=PERFILES_AGUJERO[0], angulo_agujero=0.0,
            alto_letra_mm=None, profundidad_hueco=PROFUNDIDAD_HUECO_DEFAULT, holgura=HOLGURA_DEFAULT, relieve=0.0,
            rebaje_sticker_diametro=None, rebaje_sticker_profundidad=REBAJE_PROFUNDIDAD_DEFAULT,
            separadores=None, sep_diametro=SEP_DIAMETRO_DEFAULT, sep_largo=SEP_LARGO_DEFAULT,
            sep_agujero=SEP_AGUJERO_DEFAULT, sep_perfil="rombo",
            forma_lado=FORMA_LADO_DEFAULT, forma_alto=FORMA_ALTO_DEFAULT, forma_agujero=FORMA_AGUJERO_DEFAULT,
            color_cuenta="Blanco", color_letra="Negro", color_separador="Naranja",
            carpeta_salida=CARPETA_SALIDA, prefijo=None, agrupar_repetidas=False,
            forma_cuenta="redonda", radio_esquina=None, borde_letra=BORDE_LETRA_DEFAULT,
            margen_letra=MARGEN_BORDE_LETRA_MM, pared_min=PARED_MIN_MM, formato_salida="por_pieza",
            forma_perfil=None):
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

    `forma_cuenta`: "redonda", "cuadrada" (esquinas a `radio_esquina`) o "letra" (cada cuenta
    tiene la forma de su letra con `borde_letra` mm de borde; no existe en modo sticker).
    `formato_salida`: "por_pieza" (un STL por cada pieza, como se explicó arriba), "por_color" (un STL
    con todas las bases, otro con todas las letras y otro con todos los separadores -- lo que se imprime
    de un mismo color --, con las piezas ya acomodadas en la cama; si no entran en una placa de la A1 se
    parten en `..._placa1.stl`, `..._placa2.stl`... y siempre salen todas las copias) o "ambos". En
    "por_color" cada placa trae además un mapa numerado en PNG. Las letras ocupan en su placa el mismo
    lugar que su base en la de las bases.
    Agujero de los separadores: es INDEPENDIENTE del de la cuenta. El cilindro usa `sep_agujero` y
    `sep_perfil`; los separadores de forma (estrella, corazón...) usan `forma_agujero` y `forma_perfil`
    (None = la misma forma que `perfil`, la de la cuenta).
    `margen_letra`: cuánto tiene que quedar libre entre la letra y el borde de la cuenta.
    `pared_min`: pared mínima (mm) antes de avisar de fragilidad. Para medidas de pulsera
    ver `PRESETS_MEDIDAS["pulsera"]`.

    Devuelve un dict con `piezas` (lo exportado), `armado` (lista de
    `(malla, color_hex, etiqueta)` del collar acostado en fila, para el visor 3D),
    `avisos`, `info`, y las medidas del collar."""
    if modo_cuenta not in MODOS_CUENTA:
        raise ValueError(f"modo_cuenta debe ser uno de {MODOS_CUENTA}, recibí {modo_cuenta!r}")
    if modo_cuenta == "letra" and not (ruta_ttf and os.path.exists(ruta_ttf)):
        raise FileNotFoundError(f"no encuentro la fuente: {ruta_ttf}")
    if sep_perfil not in PERFILES_AGUJERO_SEPARADOR:
        raise ValueError(f"sep_perfil debe ser uno de {PERFILES_AGUJERO_SEPARADOR}, recibí {sep_perfil!r}")
    if forma_cuenta not in FORMAS_CUENTA:
        raise ValueError(f"forma_cuenta debe ser una de {FORMAS_CUENTA}, recibí {forma_cuenta!r}")
    if formato_salida not in FORMATOS_SALIDA:
        raise ValueError(f"formato_salida debe ser uno de {FORMATOS_SALIDA}, recibí {formato_salida!r}")
    if forma_perfil is not None and forma_perfil not in PERFILES_AGUJERO:
        raise ValueError(f"forma_perfil debe ser uno de {PERFILES_AGUJERO} (o None), recibí {forma_perfil!r}")
    if forma_cuenta == "letra" and modo_cuenta == "sticker":
        raise ValueError("la cuenta con forma de letra solo existe con letra encastrada, no en modo sticker")

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
        # en una cuenta con forma de letra el cuerpo se arma alrededor de la letra: no hay nada que achicar
        medir = extension_radial if forma_cuenta == "redonda" else extension_cuadrada
        limite = diametro / 2 - margen_letra - holgura
        mas_lejos = max(medir(p) for p in poligonos.values()) if forma_cuenta != "letra" else 0.0
        if mas_lejos > limite:
            factor = limite / mas_lejos
            poligonos = {c: escalar_geom(p, xfact=factor, yfact=factor, origin=(0, 0)) for c, p in poligonos.items()}
            avisos.append(
                f"Las letras no entraban en la cuenta con el margen de {margen_letra:g} mm: "
                f"las achiqué todas juntas al {factor * 100:.0f}% (mayúscula de {alto_letra * factor:.1f} mm).")
        for c, p in poligonos.items():
            base, letra, info = armar_cuenta(
                p, diametro=diametro, alto=alto, agujero=agujero, chanfle=chanfle, perfil=perfil,
                angulo_agujero=angulo_agujero, profundidad_hueco=profundidad_hueco, holgura=holgura,
                relieve=relieve, forma_cuenta=forma_cuenta, radio_esquina=radio_esquina,
                borde_letra=borde_letra, pared_min=pared_min)
            cuentas[("letra", c)] = (base, letra)
            aviso(f"Cuenta '{c}'", info["avisos"])
    else:
        base, _, info = armar_cuenta(
            None, diametro=diametro, alto=alto, agujero=agujero, chanfle=chanfle, perfil=perfil,
            angulo_agujero=angulo_agujero, rebaje_sticker_diametro=rebaje_sticker_diametro,
            rebaje_sticker_profundidad=rebaje_sticker_profundidad, holgura=holgura,
            forma_cuenta=forma_cuenta, radio_esquina=radio_esquina, pared_min=pared_min)
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
            malla, av = armar_separador_cilindro(
                sep_diametro, sep_largo, sep_agujero, sep_perfil, chanfle, pared_min=pared_min)
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
                malla, av = armar_separador_forma(
                    contorno, forma_alto, forma_agujero, forma_perfil or perfil, angulo_agujero,
                    pared_min=pared_min, chanfle=chanfle)
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
            "salida": "por_pieza", "tipo": tipo, "etiqueta": etiqueta, "cantidad": cantidad,
            "posicion": posicion, "ruta_stl": ruta,
            "color": color_nombre, "color_hex": colores.hex_de(color_nombre),
            "vertices": len(m.vertices), "watertight": m.is_watertight,
            "ancho_mm": float(ext[0]), "alto_mm": float(ext[1]), "espesor_mm": float(ext[2]),
        })
        nombres_salida.append(ruta)

    if formato_salida in ("por_pieza", "ambos"):
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

    # --- salida agrupada por color: placas listas para imprimir ----------------------
    mapas = []
    if formato_salida in ("por_color", "ambos"):
        # en el orden del collar; cada cuenta lleva su letra ya en su lugar (la del hueco)
        cuentas_orden, separadores_orden = [], []
        for pos, item in enumerate(secuencia, start=1):
            if item["tipo"] == "cuenta":
                base, letra = cuentas[clave_cuenta(item)]
                texto_cuenta = item["caracter"] if modo_cuenta == "letra" else ""
                cuentas_orden.append((pos, texto_cuenta, base, letra))
            else:
                clave = clave_separador(item)
                separadores_orden.append((pos, etiquetas_sep[clave], separadores_mallas[clave]))

        def poner(malla, dx, dy):
            m = malla.copy()
            m.apply_translation([dx, dy, 0])
            m.apply_translation([0, 0, -m.bounds[0][2]])  # apoyada en la cama
            return m

        def exportar_placas(nombre, titulo, color_nombre, piezas_placa, n_total_placas):
            """`piezas_placa[placa] = [(pos, texto, malla ya colocada), ...]` -> un STL y un mapa por placa."""
            for placa, contenido in sorted(piezas_placa.items()):
                sufijo = f"_placa{placa}" if n_total_placas > 1 else ""
                ruta = os.path.join(carpeta_salida, f"{prefijo}_{nombre}{sufijo}.stl")
                junta = trimesh.util.concatenate([m for _, _, m in contenido])
                junta.export(ruta)
                ext = junta.extents
                entra, mensaje = bambu_a1.chequear_tamano(ext[0], ext[1], ext[2], nombre=f"{nombre}{sufijo}")
                if not entra and mensaje not in avisos:
                    avisos.append(mensaje)
                ruta_mapa = os.path.join(carpeta_salida, f"{prefijo}_{nombre}{sufijo}_mapa.png")
                dibujar_mapa_placa(
                    ruta_mapa,
                    [{"malla": m, "texto": f"{pos}\n{texto_p}" if texto_p else f"{pos}",
                      "color_hex": colores.hex_de(color_nombre)} for pos, texto_p, m in contenido],
                    f"{titulo} — placa {placa} de {n_total_placas}" if n_total_placas > 1 else titulo)
                mapas.append({"grupo": nombre, "placa": placa, "n_placas": n_total_placas, "ruta_png": ruta_mapa,
                              "titulo": titulo})
                piezas.append({
                    "salida": "por_color", "tipo": nombre, "grupo": nombre,
                    "etiqueta": titulo + (f" (placa {placa} de {n_total_placas})" if n_total_placas > 1 else ""),
                    "cantidad": len(contenido), "posicion": None, "posiciones": [pos for pos, _, _ in contenido],
                    "centros": [(float((m.bounds[0][0] + m.bounds[1][0]) / 2), float((m.bounds[0][1] + m.bounds[1][1]) / 2))
                                for _, _, m in contenido],
                    "placa": placa, "n_placas": n_total_placas, "ruta_stl": ruta, "ruta_mapa": ruta_mapa,
                    "color": color_nombre, "color_hex": colores.hex_de(color_nombre),
                    "vertices": len(junta.vertices), "watertight": bool(junta.is_watertight),
                    "ancho_mm": float(ext[0]), "alto_mm": float(ext[1]), "espesor_mm": float(ext[2]),
                })
                nombres_salida.append(ruta)
                nombres_salida.append(ruta_mapa)

        def avisar_placas(titulo, n_placas, no_entran, tamanos):
            if n_placas > 1:
                avisos.append(f"{titulo.capitalize()} no entran en una sola placa de la A1 "
                              f"({CAMA_MM:g} x {CAMA_MM:g} mm): salen en {n_placas} placas.")
            for i in no_entran:
                avisos.append(f"Una pieza de {titulo} mide {tamanos[i][0]:.0f} x {tamanos[i][1]:.0f} mm y no entra "
                              f"en la cama de la A1 ({CAMA_MM:g} mm): hay que achicarla.")

        # bases y letras comparten la distribución: la letra N queda en su placa donde está la base N en la suya
        tamanos_bases = [(float(b.extents[0]), float(b.extents[1])) for _, _, b, _ in cuentas_orden]
        colocacion, no_entran = acomodar_en_placas(tamanos_bases)
        n_placas_cuentas = max(c[0] for c in colocacion)
        avisar_placas("las bases", n_placas_cuentas, no_entran, tamanos_bases)
        bases_por_placa, letras_por_placa = {}, {}
        for (pos, texto_cuenta, base, letra), (placa, cx, cy) in zip(cuentas_orden, colocacion):
            dx = cx - float(base.bounds[0][0] + base.bounds[1][0]) / 2
            dy = cy - float(base.bounds[0][1] + base.bounds[1][1]) / 2
            bases_por_placa.setdefault(placa, []).append((pos, texto_cuenta, poner(base, dx, dy)))
            if letra is not None:
                letras_por_placa.setdefault(placa, []).append((pos, texto_cuenta, poner(letra, dx, dy)))
        exportar_placas("bases", "todas las bases", color_cuenta, bases_por_placa, n_placas_cuentas)
        if letras_por_placa:
            exportar_placas("letras", "todas las letras", color_letra, letras_por_placa, n_placas_cuentas)

        if separadores_orden:
            tamanos_sep = [(float(m.extents[0]), float(m.extents[1])) for _, _, m in separadores_orden]
            colocacion_sep, no_entran_sep = acomodar_en_placas(tamanos_sep)
            n_placas_sep = max(c[0] for c in colocacion_sep)
            avisar_placas("los separadores", n_placas_sep, no_entran_sep, tamanos_sep)
            sep_por_placa = {}
            for (pos, etiqueta_sep, malla), (placa, cx, cy) in zip(separadores_orden, colocacion_sep):
                dx = cx - float(malla.bounds[0][0] + malla.bounds[1][0]) / 2
                dy = cy - float(malla.bounds[0][1] + malla.bounds[1][1]) / 2
                sep_por_placa.setdefault(placa, []).append((pos, "", poner(malla, dx, dy)))
            exportar_placas("separadores", "todos los separadores", color_separador, sep_por_placa, n_placas_sep)

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
    por_pieza = [p for p in piezas if p["salida"] == "por_pieza"]
    por_color = [p for p in piezas if p["salida"] == "por_color"]
    info = []
    if por_pieza and agrupar_repetidas:
        info.append(
            f"{n_cuentas} cuenta(s) y {n_separadores} separador(es) en {len(por_pieza)} pieza(s) distinta(s). "
            "Las repetidas salen una sola vez: imprimí tantas copias como indica el nombre del archivo (_x7 = 7 copias).")
    elif por_pieza:
        info.append(
            f"{n_cuentas} cuenta(s) y {n_separadores} separador(es): {len(por_pieza)} archivo(s) STL, uno por cada pieza "
            "del collar, numerados en el orden en que van (01, 02, 03...).")
    if por_color:
        info.append(
            f"{n_cuentas} cuenta(s) y {n_separadores} separador(es) agrupados por color: {len(por_color)} archivo(s) STL "
            "(todas las bases, todas las letras, todos los separadores), con las piezas ya acomodadas en la cama y un "
            "mapa numerado de cada placa. Las letras quedan en su placa en el mismo lugar que su base. Al abrir un STL "
            "con varias piezas, Bambu Studio pregunta si es un solo objeto con varias partes: decí que no para dejarlas sueltas.")
    if modo_cuenta == "letra" and por_pieza:
        info.append("Cada letra va en su propio STL, apoyada en la cama: imprimila aparte (en su color) y encastrala en la tapa de su cuenta.")
    return {
        "texto": texto,
        "piezas": piezas,
        "mapas": mapas,
        "formato_salida": formato_salida,
        "rutas_stl": nombres_salida,
        "armado": armado,
        "n_cuentas": n_cuentas,
        "n_separadores": n_separadores,
        "largo_mm": cursor,
        "avisos": avisos,
        "info": info,
    }


EXTRA_MUNECA_CM = 1.5      # lo que tiene que sobrar sobre la muñeca para que la pulsera no apriete
TOLERANCIA_MUNECA_CM = 0.5


def medidas_de(tipo, sticker=False):
    """Los valores de `PRESETS_MEDIDAS[tipo]` ("collar" o "pulsera") con los nombres de los
    argumentos de `generar()`, listos para `generar(texto, ruta, **medidas_de("pulsera"))`.
    El diámetro del rebaje para sticker solo se incluye con `sticker=True`."""
    if tipo not in PRESETS_MEDIDAS:
        raise ValueError(f"tipo de pieza debe ser uno de {TIPOS_PIEZA}, recibí {tipo!r}")
    medidas = dict(PRESETS_MEDIDAS[tipo])
    medidas["alto_letra_mm"] = medidas.pop("alto_letra")
    rebaje = medidas.pop("rebaje_diametro")
    if sticker:
        medidas["rebaje_sticker_diametro"] = rebaje
    return medidas


def ajuste_a_muneca(largo_mm, muneca_cm, n_piezas=None, extra_cm=EXTRA_MUNECA_CM):
    """Compara el largo de la pulsera con la muñeca (más `extra_cm` de holgura). Devuelve un dict
    `{"estado": "justa" | "corta" | "larga", "diferencia_cm", "objetivo_cm", "mensaje"}`; con
    `n_piezas` (cuentas + separadores) el mensaje también dice más o menos cuántas piezas faltan o
    sobran."""
    if muneca_cm <= 0:
        raise ValueError("la muñeca tiene que medir más de 0 cm")
    objetivo = muneca_cm + extra_cm
    diferencia = largo_mm / 10 - objetivo
    if abs(diferencia) <= TOLERANCIA_MUNECA_CM:
        estado, mensaje = "justa", f"Largo {largo_mm / 10:.1f} cm: justo para una muñeca de {muneca_cm:g} cm."
    else:
        estado = "corta" if diferencia < 0 else "larga"
        piezas = ""
        if n_piezas:
            n = max(1, round(abs(diferencia) * 10 / (largo_mm / n_piezas)))
            piezas = f" (unas {n} pieza(s) {'más' if estado == 'corta' else 'menos'})"
        mensaje = (f"Largo {largo_mm / 10:.1f} cm: {'te faltan' if estado == 'corta' else 'te sobran'} "
                   f"{abs(diferencia):.1f} cm para una muñeca de {muneca_cm:g} cm (+{extra_cm:g} cm de holgura){piezas}.")
    return {"estado": estado, "diferencia_cm": diferencia, "objetivo_cm": objetivo, "mensaje": mensaje}


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
    tipo = ui.pedir_opcion("Tipo de pieza (define las medidas)", list(TIPOS_PIEZA), "collar")
    modo = ui.pedir_opcion("Cuenta", list(MODOS_CUENTA), "letra")
    formas = [f for f in FORMAS_CUENTA if not (f == "letra" and modo == "sticker")]
    forma_cuenta = ui.pedir_opcion("Forma de la cuenta", formas, "redonda")
    ruta_ttf = _elegir_fuente() if modo == "letra" else None
    perfil = ui.pedir_opcion("Forma del agujero para el hilo", PERFILES_AGUJERO, PERFILES_AGUJERO[0])
    angulo = ui.pedir_float("Ángulo del agujero respecto de la letra (grados)", 0.0)
    rebaje = None
    if modo == "sticker":
        d = ui.pedir_float("Diámetro del rebaje para el sticker en mm (0 = tapa lisa)", 0.0)
        rebaje = d if d > 0 else None
    medidas = medidas_de(tipo)
    formato = ui.pedir_opcion("Cómo exportar", list(FORMATOS_SALIDA), "por_color")
    sep = {
        "entre_letras": _pedir_separador("Separador entre letras", ["ninguno", "cilindro", "forma"], "cilindro"),
        "entre_palabras": _pedir_separador("Separador entre palabras", ["igual", "ninguno", "cilindro", "forma"], "igual"),
        "inicio": _pedir_separador("Separador al principio", ["ninguno", "cilindro", "forma"], "ninguno"),
        "final": _pedir_separador("Separador al final", ["ninguno", "cilindro", "forma"], "ninguno"),
    }

    try:
        r = generar(texto, ruta_ttf, modo_cuenta=modo, perfil=perfil, angulo_agujero=angulo,
                    rebaje_sticker_diametro=rebaje, separadores=sep, forma_cuenta=forma_cuenta,
                    formato_salida=formato, **medidas)
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
    for m in r["mapas"]:
        print(f"  🗺 mapa -> {m['ruta_png']}")
    print()
