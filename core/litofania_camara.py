#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/litofania_camara.py
--------------------------
L9 de la litofanía: la CÁMARA DE LUZ trasera. Cierra la placa por detrás, la fija y aloja la tira de LED. Son dos
piezas más que se suman a la placa y al marco de L8 (cuatro STL en total):

  * la CÁMARA: una caja con el frente macizo (la BRIDA) y el dorso abierto, de la misma huella que el marco. La
    brida tiene una ABERTURA un poco mayor que la ventana (así no tapa la foto) pero menor que la placa: queda
    apoyada contra la banda opaca de la placa, que queda así firme entre la ceja del marco y la brida de la cámara.
    Se arma con `core.carcasa_hueca.armar_carcasa_hueca` (la misma mecánica de las letras huecas: pared, frente,
    rebaje para la tapa) y se le suma la abertura, el agujero del cable y los agujeros de las clavijas.
  * la TAPA: cierra el dorso, entra en el rebaje de la cámara. La tira de LED se pega por dentro de la tapa.

La cámara se une al marco con CLAVIJAS que salen del dorso del marco (opcionales en L8: sin clavijas el marco es
exactamente el de siempre) y entran en agujeros ciegos de la brida con un poco de juego. Van en la corona del marco
(entre el bolsillo y el borde exterior), así que no debilitan nada y imprimen sin soportes.

Sistema de coordenadas del ENSAMBLE: el de `core/litofania_marco.py` (placa con la esquina de abajo a la izquierda en
el origen, dorso en z = 0). La cámara va detrás: z < 0, con la cara de afuera de la brida en z = 0 (apoyada contra el
dorso del marco y de la placa) y el dorso abierto en z = -profundidad. La carcasa de `carcasa_hueca` se arma con el
frente en z = 0 y creciendo hacia +z, y con la y invertida: el ensamble es esa pieza girada 180° sobre el eje X
(`(x, y, z) -> (x, -y, -z)`, una rotación propia), así que "abajo" en el ensamble es "arriba" en la carcasa.

Apilamiento en z (de adelante hacia atrás): ceja del marco, placa (su grosor máximo es el del bolsillo), brida. La
ceja apoya sobre la cara alta de la banda (z = grosor máximo) y la brida sobre su dorso (z = 0): sin juego en el
modelo. En la impresora la tolerancia real es del orden de ±0,1 mm por cara; eso no se puede verificar desde acá.

Las mallas "de impresión" son el ensamble girado para imprimir sin soportes: la cámara con el frente contra la cama
y el dorso abierto hacia arriba, la tapa plana.
"""

from dataclasses import dataclass

import numpy as np
import shapely.geometry as sg
import trimesh

from core import carcasa_hueca as ch
from core import litofania_marco as lm
from core import mesh3d

DISTANCIA_LED_DEFAULT = 20.0      # mm de la cara de los LED a la placa (ver core/litofania_luz.py)
GROSOR_TIRA_DEFAULT = 3.0         # mm: la tira de LED con su adhesivo
PARED_CAMARA_DEFAULT = 2.0        # mm de pared lateral de la cámara
ESPESOR_BRIDA_DEFAULT = 4.5       # mm de frente macizo (la brida)
SOPORTE_TAPA_DEFAULT = ch.SOPORTE_TAPA_MM_DEFAULT      # 2.0: lo que se angosta la cavidad respecto del rebaje
TAPA_ESPESOR_DEFAULT = 2.0        # mm de la tapa (y del rebaje)
HOLGURA_TAPA_DEFAULT = 0.3        # mm por lado entre la tapa y el rebaje (en carcasa_hueca el default es 1,0)
MARGEN_ABERTURA_DEFAULT = 0.5     # mm que la abertura de la brida es mayor que la ventana, por lado
CABLE_DIAM_DEFAULT = 5.0
LADO_CABLE_DEFAULT = "abajo"
LADOS_CABLE = ("arriba", "abajo", "izquierda", "derecha")
CLAVIJA_DIAM_DEFAULT = 2.5
CLAVIJA_LARGO_DEFAULT = 3.0
JUEGO_CLAVIJA_DEFAULT = 0.15      # mm por lado: el agujero mide diámetro + 2 · juego

AGUJERO_EXTRA_MM = 0.5            # mm más profundo que la clavija es el agujero (para que nunca apoye en el fondo)
TECHO_AGUJERO_MIN = 0.8           # mm de brida que quedan sobre el fondo del agujero de la clavija
MARGEN_CLAVIJA_MIN = 1.0          # mm de material entre la clavija y los bordes de la corona del marco
COBERTURA_BANDA_MIN = 0.8         # mm de banda que la brida cubre aun con la placa corrida hasta tocar el bolsillo
TAPA_ESPESOR_MIN = 1.2
APOYO_TAPA_MIN = 1.0              # mm de rebaje donde apoya la tapa (soporte_tapa - holgura_tapa)
PARED_CAMARA_MIN = lm.PARED_MIN

LUZ_RIZADO_NOTA = ("El modelo de luz supone LED puntuales ideales y NO cuenta las reflexiones de las paredes ni la "
                   "difusión de la propia placa: es una guía, no una garantía.")


@dataclass
class Camara:
    """Geometría de la cámara de luz (ver la cabecera del módulo). Los rectángulos son `(x0, y0, x1, y1)` en mm, en las
    coordenadas del ensamble."""
    geo: object                       # el `Encastre` de L8
    distancia_led: float
    grosor_tira: float
    pared: float
    espesor_brida: float
    soporte_tapa: float
    tapa_espesor: float
    holgura_tapa: float
    margen_abertura: float
    profundidad: float                # de la cámara, de la cara de afuera de la brida al dorso abierto
    z_ledge: float                    # profundidad (hacia atrás) a la que arranca el rebaje de la tapa
    abertura: tuple
    cavidad: tuple                    # la sección de la cavidad principal (la que ven los LED)
    cobertura_banda: float            # lo que la brida cubre de la banda, con la placa corrida hasta tocar el bolsillo
    lado_cable: str
    cable_diam: float
    clavija_diam: float
    clavija_largo: float
    juego_clavija: float
    clavijas: tuple                   # ((x, y), ...)

    @property
    def interior(self):
        """`(ancho, alto)` de la cavidad donde va la tira de LED."""
        return self.cavidad[2] - self.cavidad[0], self.cavidad[3] - self.cavidad[1]


# ---------------------------------------------------------------------------
#  Las clavijas del marco
# ---------------------------------------------------------------------------

def posiciones_de_clavijas(geo):
    """Cuatro posiciones `(x, y)` en el ensamble, en el centro de la corona del marco (entre el bolsillo y el borde
    exterior): una en el medio de cada lado izquierdo y derecho y dos en el arriba y el abajo, corridas hacia +x
    (`ancho_marco / 6`) del medio. Esa asimetría hace que la cámara solo entre en una posición (girada 180° o 90°
    las clavijas no coinciden con los agujeros)."""
    ex, b = geo.exterior, geo.bolsillo
    xm, ym = (ex[0] + ex[2]) / 2, (ex[1] + ex[3]) / 2
    corrimiento = geo.ancho_marco / 6
    return (((ex[0] + b[0]) / 2, ym), ((b[2] + ex[2]) / 2, ym),
            (xm + corrimiento, (ex[1] + b[1]) / 2), (xm + corrimiento, (b[3] + ex[3]) / 2))


def _validar_clavijas(geo, diametro, largo, juego):
    if not (diametro > 0):
        raise ValueError("el diámetro de la clavija tiene que ser mayor que 0")
    if not (largo > 0):
        raise ValueError("el largo de la clavija tiene que ser mayor que 0")
    if not (juego > 0):
        raise ValueError("el juego de la clavija tiene que ser mayor que 0 (sin juego no entra)")
    necesaria = diametro + 2 * juego + 2 * MARGEN_CLAVIJA_MIN
    if not (geo.pared >= necesaria - 1e-9):
        raise ValueError(f"la corona del marco mide {geo.pared:.2f} mm y las clavijas de {diametro:g} mm con {juego:g} mm de juego "
                         f"piden {necesaria:.2f} mm (al menos {MARGEN_CLAVIJA_MIN:g} mm de material a cada lado): subí ancho_borde "
                         f"o achicá la clavija")


def clavijas_del_marco(geo, diametro=CLAVIJA_DIAM_DEFAULT, largo=CLAVIJA_LARGO_DEFAULT, juego=JUEGO_CLAVIJA_DEFAULT):
    """Las clavijas para `malla_del_marco(geo, clavijas)` / `marco_litofania.generar(clavijas=...)`: una lista de
    `(x, y, diametro, largo)`. Falla con `ValueError` si no entran en la corona del marco."""
    _validar_clavijas(geo, diametro, largo, juego)
    return [(x, y, float(diametro), float(largo)) for x, y in posiciones_de_clavijas(geo)]


# ---------------------------------------------------------------------------
#  La geometría
# ---------------------------------------------------------------------------

def geometria_de_la_camara(geo, distancia_led=DISTANCIA_LED_DEFAULT, grosor_tira=GROSOR_TIRA_DEFAULT,
                           pared=PARED_CAMARA_DEFAULT, espesor_brida=ESPESOR_BRIDA_DEFAULT,
                           soporte_tapa=SOPORTE_TAPA_DEFAULT, tapa_espesor=TAPA_ESPESOR_DEFAULT,
                           holgura_tapa=HOLGURA_TAPA_DEFAULT, margen_abertura=MARGEN_ABERTURA_DEFAULT,
                           lado_cable=LADO_CABLE_DEFAULT, cable_diam=CABLE_DIAM_DEFAULT,
                           clavija_diam=CLAVIJA_DIAM_DEFAULT, clavija_largo=CLAVIJA_LARGO_DEFAULT,
                           juego_clavija=JUEGO_CLAVIJA_DEFAULT):
    """`Encastre` de L8 -> `Camara`. La profundidad sale de la distancia de los LED a la placa:
    `distancia_led + grosor_tira + tapa_espesor` (la tira va pegada a la tapa). Falla con `ValueError` si algún
    parámetro no tiene sentido o si la cámara no se puede imprimir o armar."""
    if not isinstance(geo, lm.Encastre):
        raise TypeError("geometria_de_la_camara necesita el Encastre de L8 (geometria_del_marco)")
    if not (distancia_led > 0):
        raise ValueError("distancia_led tiene que ser mayor que 0")
    if not (grosor_tira > 0):
        raise ValueError("grosor_tira tiene que ser mayor que 0")
    if not (pared >= PARED_CAMARA_MIN - 1e-9):
        raise ValueError(f"la pared de la cámara tiene que ser de al menos {PARED_CAMARA_MIN:g} mm, recibí {pared:g}")
    if not (tapa_espesor >= TAPA_ESPESOR_MIN - 1e-9):
        raise ValueError(f"el espesor de la tapa tiene que ser de al menos {TAPA_ESPESOR_MIN:g} mm, recibí {tapa_espesor:g}")
    if not (holgura_tapa >= 0):
        raise ValueError("holgura_tapa no puede ser negativa")
    if not (soporte_tapa - holgura_tapa >= APOYO_TAPA_MIN - 1e-9):
        raise ValueError(f"la tapa apoya solo {soporte_tapa - holgura_tapa:g} mm en el rebaje (al menos {APOYO_TAPA_MIN:g}): "
                         f"subí soporte_tapa o bajá holgura_tapa")
    if not (margen_abertura >= 0):
        raise ValueError("margen_abertura no puede ser negativo")
    if lado_cable not in LADOS_CABLE:
        raise ValueError(f"lado_cable tiene que ser uno de {LADOS_CABLE}, recibí {lado_cable!r}")
    if not (cable_diam > 0):
        raise ValueError("cable_diam tiene que ser mayor que 0")
    _validar_clavijas(geo, clavija_diam, clavija_largo, juego_clavija)
    if not (espesor_brida - (clavija_largo + AGUJERO_EXTRA_MM) >= TECHO_AGUJERO_MIN - 1e-9):
        raise ValueError(f"con clavijas de {clavija_largo:g} mm la brida tiene que tener al menos "
                         f"{clavija_largo + AGUJERO_EXTRA_MM + TECHO_AGUJERO_MIN:g} mm de espesor, recibí {espesor_brida:g}")

    banda = min(geo.banda_x, geo.banda_y)
    cobertura = banda - margen_abertura - geo.holgura
    if not (cobertura >= COBERTURA_BANDA_MIN - 1e-9):
        raise ValueError(f"con una banda de {banda:.2f} mm, una abertura {margen_abertura:g} mm mayor que la ventana y {geo.holgura:g} mm "
                         f"de holgura, la brida cubre solo {cobertura:.2f} mm de la banda (al menos {COBERTURA_BANDA_MIN:g}): "
                         f"bajá margen_abertura o subí margen_encastre")

    profundidad = distancia_led + grosor_tira + tapa_espesor
    z_ledge = ch.calcular_z_ledge(profundidad, espesor_brida, tapa_espesor)
    if not (z_ledge - espesor_brida >= grosor_tira - 1e-9):
        raise ValueError(f"entre la brida ({espesor_brida:g} mm) y la tapa no entra la tira de {grosor_tira:g} mm: "
                         f"distancia_led tiene que ser de al menos {espesor_brida:g} mm")

    ex, v = geo.exterior, geo.ventana
    abertura = (v[0] - margen_abertura, v[1] - margen_abertura, v[2] + margen_abertura, v[3] + margen_abertura)
    inset = pared + soporte_tapa
    cavidad = (ex[0] + inset, ex[1] + inset, ex[2] - inset, ex[3] - inset)
    if not (cavidad[2] > cavidad[0] and cavidad[3] > cavidad[1]):
        raise ValueError("la cámara no tiene cavidad: bajá la pared o el soporte de la tapa, o subí ancho_borde")
    if not (cavidad[0] <= abertura[0] and cavidad[1] <= abertura[1] and cavidad[2] >= abertura[2] and cavidad[3] >= abertura[3]):
        raise ValueError(f"la abertura de la brida no entra en la cavidad (pared {pared:g} + soporte {soporte_tapa:g} mm contra un borde de "
                         f"{geo.ancho_borde:g} mm): subí ancho_borde o bajá la pared o el soporte")
    radio = cable_diam / 2
    if not (profundidad / 2 - radio >= espesor_brida - 1e-9 and profundidad / 2 + radio <= z_ledge + 1e-9):
        raise ValueError(f"el agujero del cable (Ø{cable_diam:g} mm, a media profundidad) no entra entre la brida y la tapa: "
                         f"alargá la cámara (distancia_led) o achicá el cable")

    return Camara(geo=geo, distancia_led=float(distancia_led), grosor_tira=float(grosor_tira), pared=float(pared),
                  espesor_brida=float(espesor_brida), soporte_tapa=float(soporte_tapa), tapa_espesor=float(tapa_espesor),
                  holgura_tapa=float(holgura_tapa), margen_abertura=float(margen_abertura), profundidad=float(profundidad),
                  z_ledge=float(z_ledge), abertura=abertura, cavidad=cavidad, cobertura_banda=float(cobertura),
                  lado_cable=lado_cable, cable_diam=float(cable_diam), clavija_diam=float(clavija_diam),
                  clavija_largo=float(clavija_largo), juego_clavija=float(juego_clavija),
                  clavijas=tuple(posiciones_de_clavijas(geo)))


# ---------------------------------------------------------------------------
#  Las mallas
# ---------------------------------------------------------------------------

_LADO_EN_LA_CARCASA = {"arriba": "abajo", "abajo": "arriba", "izquierda": "izquierda", "derecha": "derecha"}


def _poly_de_la_carcasa(cam):
    """El contorno `poly` de `carcasa_hueca` (la silueta exterior achicada por la pared), en las coordenadas de la
    carcasa (y invertida)."""
    ex = cam.geo.exterior
    return sg.box(ex[0] + cam.pared, -ex[3] + cam.pared, ex[2] - cam.pared, -ex[1] - cam.pared)


def _a_ensamble(malla):
    """Carcasa -> ensamble: giro de 180° sobre el eje X (rotación propia, no espeja)."""
    v = np.array(malla.vertices, dtype=np.float64) * np.array([1.0, -1.0, -1.0])
    return trimesh.Trimesh(v, np.array(malla.faces), process=False)


def malla_y_avisos_de_la_camara(cam):
    """`Camara` -> `(malla, avisos)`: la malla de la cámara en las coordenadas del ENSAMBLE (la carcasa hueca de
    `carcasa_hueca` con la abertura en la brida, los agujeros de las clavijas y el agujero del cable) y los avisos de
    `armar_carcasa_hueca` (el de los laminadores que tapan las piezas abiertas atrás). Falla con `ValueError` si la
    carcasa queda maciza o el agujero del cable no encuentra pared."""
    poly = _poly_de_la_carcasa(cam)
    carcasa, hueca, avisos = ch.armar_carcasa_hueca(poly, cam.profundidad, cam.pared, cam.tapa_espesor,
                                               soporte_tapa_mm=cam.soporte_tapa, espesor_cara_mm=cam.espesor_brida,
                                               hueco_unido=True)
    if not hueca:
        raise ValueError("la cámara quedó maciza: no hay lugar para la cavidad")

    a = cam.abertura
    ancho, alto = a[2] - a[0], a[3] - a[1]
    abertura = trimesh.creation.box(extents=[ancho, alto, cam.espesor_brida + 2.0])
    abertura.apply_translation([(a[0] + a[2]) / 2, -(a[1] + a[3]) / 2, cam.espesor_brida / 2])

    cortes = [abertura]
    radio = cam.clavija_diam / 2 + cam.juego_clavija
    for x, y in cam.clavijas:
        cortes.append(trimesh.creation.cylinder(radius=radio, sections=32, segment=[
            (x, -y, -1.0), (x, -y, cam.clavija_largo + AGUJERO_EXTRA_MM)]))
    cable = ch.armar_agujero_pared(poly, cam.pared, cam.cable_diam, _LADO_EN_LA_CARCASA[cam.lado_cable], cam.profundidad,
                                   cam.tapa_espesor, soporte_tapa_mm=cam.soporte_tapa, espesor_cara_mm=cam.espesor_brida,
                                   holgura_tapa_mm=cam.holgura_tapa)
    if cable is None:
        raise ValueError(f"no encontré dónde pasar el agujero del cable por el lado {cam.lado_cable!r}")
    cortes.append(cable)
    return _a_ensamble(trimesh.boolean.difference([carcasa] + cortes, engine="manifold")), list(avisos)


def malla_de_la_camara(cam):
    """Solo la malla de `malla_y_avisos_de_la_camara`."""
    return malla_y_avisos_de_la_camara(cam)[0]


def malla_de_la_tapa(cam):
    """`Camara` -> malla de la tapa en su lugar del ensamble (en el rebaje del dorso de la cámara)."""
    tapa = ch.armar_tapa(_poly_de_la_carcasa(cam), cam.tapa_espesor, holgura_tapa_mm=cam.holgura_tapa)
    tapa.apply_translation([0.0, 0.0, cam.z_ledge])
    return _a_ensamble(tapa)


def camara_para_imprimir(malla, geo):
    """La cámara del ensamble girada para imprimir sin soportes: la brida contra la cama y el dorso abierto hacia arriba,
    llevada al origen (mismo giro en planta que `marco_para_imprimir`). Devuelve una malla nueva."""
    v = np.array(malla.vertices, dtype=np.float64)
    v = np.column_stack([v[:, 0] - geo.exterior[0], geo.exterior[3] - v[:, 1], -v[:, 2]])
    return trimesh.Trimesh(v, np.array(malla.faces), process=False)


def tapa_para_imprimir(malla, cam):
    """La tapa del ensamble llevada a la cama (plana, el lado de afuera hacia abajo) y al origen. Devuelve una malla nueva."""
    ex, desde_el_borde = cam.geo.exterior, cam.pared + cam.holgura_tapa
    v = np.array(malla.vertices, dtype=np.float64)
    v = np.column_stack([v[:, 0] - ex[0] - desde_el_borde, ex[3] - v[:, 1] - desde_el_borde, -v[:, 2] - cam.z_ledge])
    return trimesh.Trimesh(v, np.array(malla.faces), process=False)
