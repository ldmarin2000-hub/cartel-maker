#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/litofania_marco.py
-------------------------
L8 de la litofanía: el marco. Son DOS piezas que se imprimen por separado y se encastran:

  * la PLACA: la de L4/L2/L3 (la imagen convertida en grosor) más una BANDA opaca alrededor, de `margen_encastre`
    mm, al grosor máximo. La banda no es parte de la imagen: es lo que agarra la ceja del marco. Se arma con la
    misma `malla_desde_grilla_grosor` de L3 (sin geometría propia), así que cierra por construcción.
  * el MARCO: un rectángulo con una VENTANA pasante del tamaño EXACTO de la imagen (así no tapa la foto) y, detrás
    de una ceja de `grosor_ceja` mm, un BOLSILLO abierto por atrás donde entra la placa con `holgura` mm por lado.
    Es `caja - ventana - bolsillo` con booleanas de manifold (exacto y watertight).

El marco va en un filamento opaco (uno translúcido filtra luz por los costados y mata el contraste) y la placa en
el translúcido. Atrás no cierra nada: lo cierra y lo fija la cámara de luz (L9), por eso acá la placa se sostiene
solo por la ceja y la fricción del encastre.

Sistema de coordenadas del ENSAMBLE (mm; el mismo para las dos piezas): la placa tiene su esquina de abajo a la
izquierda en el origen, su dorso en z = 0 y su relieve hacia +z. La imagen ocupa `ventana`. El marco tiene el
dorso (abierto) en z = 0 y la ceja arriba, entre `profundidad_bolsillo` y `profundidad_total`. Con la placa
centrada, la ceja apoya sobre la banda y la ventana queda justo sobre la imagen; con juego, la placa puede correrse
hasta `holgura` mm hacia un lado, y entonces la ceja tapa como mucho `holgura` mm de borde de la foto de ese
lado (es inherente a cualquier encastre con juego).

Las mallas "de impresión" son las mismas dadas vuelta para imprimir sin soportes: la placa tal cual sale de L3 (dorso
contra la cama) y el marco con la ceja contra la cama y el bolsillo abierto hacia arriba.
"""

from dataclasses import dataclass

import numpy as np
import trimesh

from core import litofania as lf

ANCHO_BORDE_DEFAULT = 8.0         # mm de la ventana al borde exterior del marco
GROSOR_CEJA_DEFAULT = 1.2         # mm (6 capas de 0,2)
MARGEN_ENCASTRE_DEFAULT = 2.0     # mm de banda opaca de la placa alrededor de la imagen
HOLGURA_DEFAULT = 0.25            # mm por lado entre la placa y el bolsillo

GROSOR_CEJA_MIN = 0.8             # mm: menos que 4 capas de 0,2 no se sostiene
PARED_MIN = 1.2                   # mm: la pared del bolsillo, tres perímetros de 0,4
APOYO_MIN = 1.0                   # mm que la ceja apoya sobre la banda aun con la placa corrida a un lado
HOLGURA_MAX = 2.0


@dataclass
class Encastre:
    """Geometría del ensamble (ver la cabecera del módulo). Los rectángulos son `(x0, y0, x1, y1)` en mm."""
    ancho_imagen: float
    alto_imagen: float
    banda_x: float
    banda_y: float
    ancho_placa: float
    alto_placa: float
    profundidad_bolsillo: float       # = el grosor máximo de la placa: la placa queda al ras del dorso
    grosor_ceja: float
    profundidad_total: float
    ancho_borde: float
    holgura: float
    ventana: tuple
    placa: tuple
    bolsillo: tuple
    exterior: tuple
    pared: float                      # el más fino de los cuatro lados de la pared del bolsillo
    apoyo: float                      # lo que apoya la ceja sobre la banda con la placa corrida hasta tocar la pared

    @property
    def ancho_marco(self):
        return self.exterior[2] - self.exterior[0]

    @property
    def alto_marco(self):
        return self.exterior[3] - self.exterior[1]


# ---------------------------------------------------------------------------
#  La placa: la grilla de L2 con una banda opaca
# ---------------------------------------------------------------------------

def grilla_con_banda(mapa_grosor, margen_encastre=MARGEN_ENCASTRE_DEFAULT):
    """`MapaGrosor` (L2) -> `(grilla, banda_x, banda_y)`: la misma grilla de grosores con una banda de `margen_encastre`
    mm (redondeada a píxeles: `banda_x` y `banda_y` son la real) alrededor, al grosor máximo de la placa. La
    imagen queda intacta en el centro. No modifica el mapa. La malla de la placa sale de pasarle esa grilla, con
    `ancho_mm = ancho_imagen + 2·banda_x` y `alto_mm = alto_imagen + 2·banda_y`, a `lf.malla_desde_grilla_grosor`."""
    if not isinstance(mapa_grosor, lf.MapaGrosor):
        raise TypeError("grilla_con_banda necesita un MapaGrosor (el resultado de brillo_a_grosor)")
    if not (margen_encastre > 0):
        raise ValueError("margen_encastre tiene que ser mayor que 0")
    paso_x = mapa_grosor.ancho_mm / (mapa_grosor.ancho_px - 1)
    paso_y = mapa_grosor.alto_mm / (mapa_grosor.alto_px - 1)
    pad_x, pad_y = max(1, int(round(margen_encastre / paso_x))), max(1, int(round(margen_encastre / paso_y)))
    valor = max(float(mapa_grosor.grosor.max()), float(mapa_grosor.grosor_max_efectivo))
    grilla = np.pad(mapa_grosor.grosor, ((pad_y, pad_y), (pad_x, pad_x)), mode="constant", constant_values=valor)
    return grilla, pad_x * paso_x, pad_y * paso_y


# ---------------------------------------------------------------------------
#  El marco
# ---------------------------------------------------------------------------

def geometria_del_marco(ancho_imagen, alto_imagen, banda_x, banda_y, grosor_placa,
                        ancho_borde=ANCHO_BORDE_DEFAULT, grosor_ceja=GROSOR_CEJA_DEFAULT, holgura=HOLGURA_DEFAULT):
    """Rectángulos y profundidades del ensamble para una imagen de `ancho_imagen` x `alto_imagen` mm con bandas
    `banda_x` / `banda_y` y una placa de `grosor_placa` mm de alto máximo. Falla con `ValueError` si algún parámetro no
    tiene sentido o si el marco no se puede imprimir (pared del bolsillo menor que `PARED_MIN`, ceja que apoya
    menos que `APOYO_MIN`)."""
    if not (ancho_imagen > 0 and alto_imagen > 0):
        raise ValueError("la imagen tiene que tener ancho y alto mayores que 0")
    if not (banda_x > 0 and banda_y > 0):
        raise ValueError("la banda de encastre tiene que ser mayor que 0")
    if not (grosor_placa > 0):
        raise ValueError("grosor_placa tiene que ser mayor que 0")
    if not (ancho_borde > 0):
        raise ValueError("ancho_borde tiene que ser mayor que 0")
    if not (grosor_ceja >= GROSOR_CEJA_MIN):
        raise ValueError(f"grosor_ceja tiene que ser de al menos {GROSOR_CEJA_MIN:g} mm (si no, no se sostiene)")
    if not (0 <= holgura <= HOLGURA_MAX):
        raise ValueError(f"holgura tiene que estar entre 0 y {HOLGURA_MAX:g} mm, recibí {holgura}")
    banda = min(banda_x, banda_y)
    apoyo = banda - holgura
    if not (apoyo >= APOYO_MIN - 1e-9):
        raise ValueError(f"con una banda de {banda:.2f} mm y una holgura de {holgura:g} mm la ceja apoya solo {apoyo:.2f} mm "
                         f"sobre la placa (al menos {APOYO_MIN:g}): subí margen_encastre o bajá la holgura")
    pared = min(ancho_borde - banda_x - holgura, ancho_borde - banda_y - holgura)
    if not (pared >= PARED_MIN - 1e-9):
        raise ValueError(f"con ancho_borde = {ancho_borde:g} mm, una banda de {banda:.2f} mm y holgura {holgura:g} mm, la pared "
                         f"del bolsillo queda de {pared:.2f} mm (al menos {PARED_MIN:g}): subí ancho_borde")
    ancho_placa, alto_placa = ancho_imagen + 2 * banda_x, alto_imagen + 2 * banda_y
    return Encastre(
        ancho_imagen=float(ancho_imagen), alto_imagen=float(alto_imagen), banda_x=float(banda_x), banda_y=float(banda_y),
        ancho_placa=float(ancho_placa), alto_placa=float(alto_placa),
        profundidad_bolsillo=float(grosor_placa), grosor_ceja=float(grosor_ceja),
        profundidad_total=float(grosor_placa + grosor_ceja), ancho_borde=float(ancho_borde), holgura=float(holgura),
        ventana=(banda_x, banda_y, banda_x + ancho_imagen, banda_y + alto_imagen),
        placa=(0.0, 0.0, ancho_placa, alto_placa),
        bolsillo=(-holgura, -holgura, ancho_placa + holgura, alto_placa + holgura),
        exterior=(banda_x - ancho_borde, banda_y - ancho_borde,
                  banda_x + ancho_imagen + ancho_borde, banda_y + alto_imagen + ancho_borde),
        pared=float(pared), apoyo=float(apoyo),
    )


def _caja(x0, y0, z0, x1, y1, z1):
    caja = trimesh.creation.box(extents=[x1 - x0, y1 - y0, z1 - z0])
    caja.apply_translation([(x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2])
    return caja


def malla_del_marco(geo, clavijas=None):
    """`Encastre` -> malla del marco en las coordenadas del ENSAMBLE: la caja exterior, menos la ventana pasante y
    menos el bolsillo (abierto por el dorso, z = 0, hasta `profundidad_bolsillo`).

    `clavijas` (opcional, por defecto ninguna: la malla es EXACTAMENTE la de siempre): una lista de
    `(x, y, diametro, largo)` en mm. Cada una es un cilindro que sale del dorso del marco hacia atrás (z < 0, hasta
    `-largo`) y está unido al cuerpo (L9 las usa para fijar la cámara de luz)."""
    ex = geo.exterior
    exterior = _caja(ex[0], ex[1], 0.0, ex[2], ex[3], geo.profundidad_total)
    v = geo.ventana
    ventana = _caja(v[0], v[1], -1.0, v[2], v[3], geo.profundidad_total + 1.0)
    b = geo.bolsillo
    bolsillo = _caja(b[0], b[1], -1.0, b[2], b[3], geo.profundidad_bolsillo)
    marco = trimesh.boolean.difference([exterior, ventana], engine="manifold")
    marco = trimesh.boolean.difference([marco, bolsillo], engine="manifold")
    if clavijas:
        cilindros = [trimesh.creation.cylinder(radius=diametro / 2, segment=[(x, y, -largo), (x, y, 0.5)], sections=32)
                     for x, y, diametro, largo in clavijas]
        marco = trimesh.boolean.union([marco] + cilindros, engine="manifold")
    return marco


def ensamblar_placa(malla_placa, geo, cara_visible="relieve"):
    """La malla de la placa (la de `malla_desde_grilla_grosor`, dorso en z = 0) puesta en el ensamble, lista para
    verla junto al marco. Con `cara_visible="relieve"` queda como está, el relieve contra la ceja. Con `"plana"`
    se da vuelta (giro de 180° sobre el eje Y) para que la cara lisa quede contra la ceja y sea la que se ve por la
    ventana. Devuelve una malla nueva."""
    if cara_visible not in lf.CARAS_VISIBLES:
        raise ValueError(f"cara_visible tiene que ser una de {lf.CARAS_VISIBLES}, recibí {cara_visible!r}")
    v = np.array(malla_placa.vertices, dtype=np.float64)
    if cara_visible == "plana":
        v[:, 0] = geo.ancho_placa - v[:, 0]
        v[:, 2] = geo.profundidad_bolsillo - v[:, 2]
    return trimesh.Trimesh(v, np.array(malla_placa.faces), process=False)


def marco_para_imprimir(malla_marco, geo):
    """El marco del ensamble girado 180° sobre el eje X y llevado al origen: la ceja contra la cama y el bolsillo
    abierto hacia arriba, sin soportes. Devuelve una malla nueva."""
    v = np.array(malla_marco.vertices, dtype=np.float64)
    v = np.column_stack([v[:, 0] - geo.exterior[0], geo.exterior[3] - v[:, 1], geo.profundidad_total - v[:, 2]])
    return trimesh.Trimesh(v, np.array(malla_marco.faces), process=False)
