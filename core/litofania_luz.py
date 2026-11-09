#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/litofania_luz.py
-----------------------
L9 de la litofanía, parte física: ¿a qué distancia de la placa tiene que ir la tira de LED para que NO se vean los
puntos de luz? Un modelo chico y honesto, para dar un número en vez de "a ojo".

Modelo: cada LED es una fuente puntual ideal que emite como un Lambert (cos θ), a una distancia `d` por detrás de la
placa. La iluminancia que llega a un punto de la placa a distancia lateral ρ de la fuente es

        E(ρ) = I0 · cos θ_emisión · cos θ_recepción / r²  =  I0 · d² / (d² + ρ²)²        (r² = d² + ρ²)

(con I0 = 1: solo importan las razones). La tira son filas paralelas separadas `separacion_filas` mm, con un LED cada
`paso_led` mm, centradas y cubriendo el interior de la cámara. Se miden dos cosas:

  * el RIZADO LOCAL (los puntos): (Emax - Emin) / (Emax + Emin) sobre una celda `paso_led` x `separacion_filas`
    alrededor del centro, un período entero del patrón de LED. Baja rápido al alejar la tira: ~3,5 % con la
    distancia igual al espaciado, ~1 % con 1,2 veces.
  * el BORDE / CENTRO (el viñeteo): Emin / Emax sobre toda la ventana de la imagen. Alejar la tira borra los puntos
    pero oscurece los bordes, porque el arreglo es finito.

Límites (van a la guía, no se pueden verificar desde acá): el modelo NO incluye las reflexiones (paredes blancas
suben el borde, así que es pesimista para el viñeteo) ni la difusión de la propia placa (que borra puntos, así que es
conservador para el rizado), ni la curva de emisión real de un LED de tira, que no es un Lambert perfecto.
"""

from dataclasses import dataclass

import numpy as np

PASO_LED_DEFAULT = 16.7           # mm: una tira de 60 LED/m
RIZADO_MAX_DEFAULT = 0.05         # 5 %: por debajo no se ven puntos en un degradé liso
BORDE_CENTRO_MIN_DEFAULT = 0.5    # por debajo, los bordes quedan a menos de la mitad de luz que el centro
RESOLUCION_DEFAULT = 101          # puntos por lado de las grillas de evaluación


@dataclass
class UniformidadLuz:
    """Resultado de `uniformidad_de_luz`. `rizado_local`: 0 = sin puntos. `borde_centro`: 1 = parejo."""
    distancia: float
    paso_led: float
    separacion_filas: float
    n_leds: int
    rizado_local: float
    borde_centro: float


def _validar(distancia, paso_led, separacion_filas):
    if not (distancia > 0):
        raise ValueError("la distancia a la placa tiene que ser mayor que 0")
    if not (paso_led > 0):
        raise ValueError("paso_led tiene que ser mayor que 0")
    if not (separacion_filas > 0):
        raise ValueError("separacion_filas tiene que ser mayor que 0")


def fuentes_de_la_tira(ancho, alto, paso_led, separacion_filas):
    """Posiciones `(x, y)` de los LED, centradas en el origen: filas paralelas al eje X separadas `separacion_filas`
    y un LED cada `paso_led` mm, cubriendo `ancho` x `alto` mm (cuantas entran enteras, simétricas). Devuelve un array
    `(N, 2)`."""
    if not (ancho > 0 and alto > 0):
        raise ValueError("el ancho y el alto de la cámara tienen que ser mayores que 0")
    if not (paso_led > 0 and separacion_filas > 0):
        raise ValueError("paso_led y separacion_filas tienen que ser mayores que 0")
    nx, ny = int(np.floor(ancho / paso_led + 1e-9)) + 1, int(np.floor(alto / separacion_filas + 1e-9)) + 1
    xs = (np.arange(nx) - (nx - 1) / 2) * paso_led
    ys = (np.arange(ny) - (ny - 1) / 2) * separacion_filas
    X, Y = np.meshgrid(xs, ys)
    return np.column_stack([X.ravel(), Y.ravel()])


def iluminancia(x, y, fuentes, distancia):
    """Iluminancia relativa en los puntos `(x, y)` (arrays del mismo tamaño) sobre la placa, a `distancia` mm de un
    plano de fuentes `(N, 2)`: la suma de `d² / (d² + ρ²)²` de cada una (cada fuente con intensidad 1)."""
    x, y = np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64)
    if not (distancia > 0):
        raise ValueError("la distancia a la placa tiene que ser mayor que 0")
    d2 = float(distancia) ** 2
    total = np.zeros(np.broadcast(x, y).shape)
    for fx, fy in np.asarray(fuentes, dtype=np.float64).reshape(-1, 2):
        total = total + d2 / (d2 + (x - fx) ** 2 + (y - fy) ** 2) ** 2
    return total


def uniformidad_de_luz(distancia, paso_led=PASO_LED_DEFAULT, separacion_filas=PASO_LED_DEFAULT,
                       ancho_camara=100.0, alto_camara=100.0, ancho_imagen=100.0, alto_imagen=100.0,
                       resolucion=RESOLUCION_DEFAULT):
    """Rizado local y borde/centro de la luz sobre la placa (ver la cabecera del módulo) para una tira de LED a
    `distancia` mm por detrás, que cubre `ancho_camara` x `alto_camara` mm, con la imagen de `ancho_imagen` x
    `alto_imagen` mm centrada. Devuelve un `UniformidadLuz`."""
    _validar(distancia, paso_led, separacion_filas)
    if not (ancho_imagen > 0 and alto_imagen > 0):
        raise ValueError("el ancho y el alto de la imagen tienen que ser mayores que 0")
    if not (isinstance(resolucion, (int, np.integer)) and resolucion >= 3):
        raise ValueError("resolucion tiene que ser un entero de al menos 3")
    fuentes = fuentes_de_la_tira(ancho_camara, alto_camara, paso_led, separacion_filas)
    X, Y = np.meshgrid(np.linspace(-paso_led / 2, paso_led / 2, resolucion),
                       np.linspace(-separacion_filas / 2, separacion_filas / 2, resolucion))
    e = iluminancia(X, Y, fuentes, distancia)
    rizado = float((e.max() - e.min()) / (e.max() + e.min()))
    X, Y = np.meshgrid(np.linspace(-ancho_imagen / 2, ancho_imagen / 2, resolucion),
                       np.linspace(-alto_imagen / 2, alto_imagen / 2, resolucion))
    g = iluminancia(X, Y, fuentes, distancia)
    return UniformidadLuz(distancia=float(distancia), paso_led=float(paso_led), separacion_filas=float(separacion_filas),
                          n_leds=len(fuentes), rizado_local=rizado, borde_centro=float(g.min() / g.max()))


def _biseccion(f, bajo, alto, objetivo, iteraciones=60):
    """Menor `x` en [bajo, alto] con f(x) <= objetivo, para una `f` que BAJA al subir x."""
    for _ in range(iteraciones):
        medio = (bajo + alto) / 2
        if f(medio) > objetivo:
            bajo = medio
        else:
            alto = medio
    return alto


def distancia_minima(paso_led=PASO_LED_DEFAULT, separacion_filas=PASO_LED_DEFAULT, rizado_max=RIZADO_MAX_DEFAULT,
                     ancho_camara=100.0, alto_camara=100.0):
    """La menor distancia (mm) de la tira a la placa con la que el rizado local no pasa de `rizado_max`."""
    _validar(1.0, paso_led, separacion_filas)
    if not (0 < rizado_max < 1):
        raise ValueError("rizado_max tiene que estar entre 0 y 1")
    mayor = max(paso_led, separacion_filas)
    f = lambda d: uniformidad_de_luz(d, paso_led, separacion_filas, ancho_camara, alto_camara, 10.0, 10.0).rizado_local
    alto = 20.0 * mayor
    if f(alto) > rizado_max:
        raise ValueError("ni a una distancia enorme el rizado baja del máximo pedido")
    return float(_biseccion(f, 0.05 * mayor, alto, rizado_max))


def separacion_maxima_de_filas(distancia, paso_led=PASO_LED_DEFAULT, rizado_max=RIZADO_MAX_DEFAULT,
                               ancho_camara=100.0, alto_camara=100.0):
    """La mayor separación (mm) entre filas de tira con la que, a `distancia` mm de la placa, el rizado local no pasa
    de `rizado_max`. Es lo que la guía le dice a quien pega la tira."""
    _validar(distancia, paso_led, 1.0)
    if not (0 < rizado_max < 1):
        raise ValueError("rizado_max tiene que estar entre 0 y 1")
    f = lambda s: uniformidad_de_luz(distancia, paso_led, s, ancho_camara, alto_camara, 10.0, 10.0).rizado_local
    chica, grande = 0.2 * distancia, 20.0 * distancia
    if f(chica) > rizado_max:
        raise ValueError("ni con filas muy juntas el rizado baja del máximo pedido: el paso del LED es demasiado grande para esa distancia")
    if f(grande) <= rizado_max:
        return float(grande)
    # f SUBE con la separación: la mayor con f <= objetivo es el cruce
    bajo, alto = chica, grande
    for _ in range(60):
        medio = (bajo + alto) / 2
        if f(medio) <= rizado_max:
            bajo = medio
        else:
            alto = medio
    return float(bajo)


def avisos_de_luz(u, rizado_max=RIZADO_MAX_DEFAULT, borde_centro_min=BORDE_CENTRO_MIN_DEFAULT,
                  ancho_camara=100.0, alto_camara=100.0):
    """Avisos (lista de textos, vacía si está bien) para un `UniformidadLuz`: se van a ver puntos, o los bordes quedan
    muy oscuros."""
    avisos = []
    if u.rizado_local > rizado_max:
        minima = distancia_minima(u.paso_led, u.separacion_filas, rizado_max, ancho_camara, alto_camara)
        avisos.append(f"A {u.distancia:g} mm de la placa se van a ver los puntos de los LED (rizado de {u.rizado_local * 100:.1f} %, "
                      f"más que el {rizado_max * 100:g} % tolerado): alejá la tira a {minima:.0f} mm o más, o juntá las filas / "
                      f"usá una tira con más LED por metro.")
    if u.borde_centro < borde_centro_min:
        avisos.append(f"Los bordes de la litofanía van a recibir solo el {u.borde_centro * 100:.0f} % de la luz del centro "
                      f"(se tolera {borde_centro_min * 100:g} %): acercá la tira, o poné una fila de tira cerca de las paredes. "
                      f"Las paredes blancas de la cámara ayudan, pero el modelo no las cuenta.")
    return avisos
