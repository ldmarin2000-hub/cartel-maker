#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/litofania_simulacion.py
-------------------------------
L5 de la litofanía: simulación a contraluz. Toma el `MapaGrosor` de L2 y calcula cuánta luz deja pasar
cada punto de la placa, para ver en pantalla cómo va a SALIR (no un ideal) antes de imprimir.

Usa EXACTAMENTE el mismo modelo físico que L2: `core.litofania.luz_transmitida` (Beer-Lambert, con
`luz_minima` y los grosores pedidos). No hay una fórmula propia acá: si la hubiera, la simulación podría
mostrar algo distinto de lo que L2 calculó para imprimir. Se evalúa sobre el grosor que de verdad se
imprime (`mapa.grosor`, ya cuantizado a capas si se pidió), así las bandas de una capa gruesa se ven.

Qué es y qué no es lo que se ve:

  * `luz` es lineal, relativa a la que pasa por `grosor_min` (= 1,0); por `grosor_max` pasa `luz_minima`.
  * `vista` es esa luz codificada en sRGB (lo que mostraría una pantalla). El negro de la placa NUNCA es
    negro: con `luz_minima` = 5 % se ve como un gris de ~0,25, y es lo que va a hacer la placa real. Por eso
    la imagen simulada no es la foto original; `brillo_desde_luz` quita ese piso y vuelve al brillo de la foto
    (brillo -> grosor -> luz -> brillo da el mismo brillo, salvo la cuantización por capas).
  * Sale en grises: un filamento de color atenúa distinto cada canal y eso solo lo mide la calibración (L6).
  * Beer-Lambert es una aproximación (el plástico también dispersa la luz): `luz_minima` es un parámetro
    efectivo, y la simulación vale lo que valga ese valor.
"""

from dataclasses import dataclass

import numpy as np
from PIL import Image

from core import litofania as lf

TOLERANCIA_SATURACION = 1e-12   # por encima de 1 + esto se cuenta como luz de más (el redondeo no cuenta)


@dataclass
class SimulacionLuz:
    """Resultado de `simular_contraluz`. `luz` y `vista` son arrays 2D float64 en [0, 1] con la forma
    `(alto_px, ancho_px)` del mapa de grosor (fila 0 = arriba). `px_saturados`: cuántos puntos dejaban pasar
    MÁS luz que `grosor_min` (porque la cuantización a capas los dejó más finos que el pedido) y se recortaron
    a 1. El resto de los campos son los del mapa de grosor con el que se simuló."""
    luz: np.ndarray
    vista: np.ndarray
    ancho_mm: float
    alto_mm: float
    ancho_px: int
    alto_px: int
    px_por_mm: float
    grosor_min: float
    grosor_max: float
    luz_minima: float
    px_saturados: int


def oetf_srgb(luz):
    """Luz lineal relativa (0..1) -> valor sRGB (0..1): la inversa de `litofania.eotf_srgb`."""
    luz = np.clip(np.asarray(luz, dtype=np.float64), 0.0, 1.0)
    sin_extremos = np.where(luz <= 0.0031308, luz * 12.92, 1.055 * np.power(luz, 1.0 / 2.4) - 0.055)
    return np.where(luz >= 1.0, 1.0, sin_extremos)     # el blanco es exactamente 1 (la fórmula da 0,9999999999999999)


def brillo_desde_luz(luz, luz_minima):
    """Luz transmitida -> el brillo de la foto que la produce: quita el piso `luz_minima` (el negro de la
    placa) y pasa a sRGB, `OETF((luz - luz_minima) / (1 - luz_minima))`. Es la inversa exacta de lo que hace
    L2 con `compensar=True`; sirve para comparar la simulación con la foto."""
    if not (0.0 <= luz_minima < 1.0):
        raise ValueError(f"luz_minima tiene que estar en [0, 1), recibí {luz_minima}")
    luz = np.asarray(luz, dtype=np.float64)
    return oetf_srgb((luz - luz_minima) / (1.0 - luz_minima))        # oetf_srgb recorta a [0, 1]


def simular_contraluz(mapa_grosor):
    """`MapaGrosor` (L2) -> `SimulacionLuz`. No modifica el mapa. Lo que pasa de 1 (por capas que dejan un
    punto más fino que `grosor_min`) se recorta y se cuenta en `px_saturados`."""
    if not isinstance(mapa_grosor, lf.MapaGrosor):
        raise TypeError("simular_contraluz necesita un MapaGrosor (el resultado de brillo_a_grosor)")
    luz = lf.luz_transmitida(mapa_grosor.grosor, mapa_grosor.grosor_min, mapa_grosor.grosor_max,
                             mapa_grosor.luz_minima)
    saturados = int(np.count_nonzero(luz > 1.0 + TOLERANCIA_SATURACION))
    luz = np.clip(luz, 0.0, 1.0)
    return SimulacionLuz(
        luz=luz, vista=oetf_srgb(luz),
        ancho_mm=mapa_grosor.ancho_mm, alto_mm=mapa_grosor.alto_mm,
        ancho_px=mapa_grosor.ancho_px, alto_px=mapa_grosor.alto_px, px_por_mm=mapa_grosor.px_por_mm,
        grosor_min=mapa_grosor.grosor_min, grosor_max=mapa_grosor.grosor_max, luz_minima=mapa_grosor.luz_minima,
        px_saturados=saturados,
    )


def simulacion_a_imagen(simulacion):
    """`SimulacionLuz` (o un array `vista` en [0, 1]) -> imagen de PIL en grises de 8 bits, para guardarla
    o mostrarla con `st.image`."""
    vista = simulacion.vista if isinstance(simulacion, SimulacionLuz) else simulacion
    return Image.fromarray(np.round(np.clip(vista, 0.0, 1.0) * 255.0).astype(np.uint8))
