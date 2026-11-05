#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/litofania.py
--------------------
Litofanía: una placa donde la imagen se forma por GROSOR variable (claro = fino,
pasa la luz; oscuro = grueso, la bloquea). Este módulo se arma por partes; hoy tiene
la primera:

  L1 -- imagen -> MAPA DE BRILLO (`imagen_a_mapa_brillo`): una grilla 2D con el brillo
        de cada punto de la placa, en [0, 1], a la resolución pedida en píxeles/mm.

El mapa de brillo es FIEL a la foto: por defecto el resultado es exactamente el gris
de PIL (`convert("L")`), sin realce de ningún tipo. Convertir ese brillo en grosor (y
compensar que el grosor atenúa la luz de forma exponencial) es otra etapa (L2 y la
calibración): no se mezcla "el brillo del píxel" con "el grosor para que se vea así".

Por qué no reusa `core/heightmap.py::_grilla_de_alturas` (el cargador que usa
Esculturas): ignora la etiqueta EXIF de rotación (una foto de celular queda
acostada), pasa a negro lo transparente (el fondo de un logo saldría como pared
opaca) y aplica CLAHE por defecto (cambia la escala de grises). Acá se corrige cada
cosa, y heightmap.py queda como está.
"""

from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageOps

from core import validation
from core.validation import ValidationError

PX_POR_MM_DEFAULT = 4.0   # 0,25 mm por píxel: la línea de una boquilla de 0,4 mm abarca ~1,7 píxeles
PX_POR_MM_MIN = 1.0
PX_POR_MM_MAX = 8.0
PX_POR_MM_BAJO_AVISO = 2.0          # por debajo de esto el píxel (>0,5 mm) es más ancho que la línea impresa
BYTES_POR_TRIANGULO_STL = 50        # STL binario
PESO_STL_AVISO_MB = 100.0           # a partir de acá la malla se vuelve pesada de abrir y rebanar
PERCENTILES_AUTO_NIVELES = (2.0, 98.0)
CLIP_LIMIT_REALCE_LOCAL = 0.03      # el mismo que usa el relieve de Esculturas


@dataclass
class MapaBrillo:
    """Resultado de `imagen_a_mapa_brillo`.

    `brillo`: array 2D float64 en [0, 1] (0 = negro, 1 = blanco), fila 0 = arriba de la foto,
    de forma `(alto_px, ancho_px)`. `ancho_mm` x `alto_mm`: el tamaño de la placa. `px_por_mm`:
    la resolución REAL (puede ser menor que la pedida si la foto no tiene tantos píxeles: nunca
    se agranda). `triangulos_estimados` / `stl_estimado_mb`: lo que pesaría la malla de arriba
    (la superficie con relieve; el fondo plano y las paredes suman poco)."""
    brillo: np.ndarray
    ancho_mm: float
    alto_mm: float
    ancho_px: int
    alto_px: int
    px_por_mm: float
    px_por_mm_pedido: float
    triangulos_estimados: int
    stl_estimado_mb: float
    avisos: list = field(default_factory=list)


# ---------------------------------------------------------------------------
#  Carga: cualquier modo de imagen -> gris float en [0, 1]
# ---------------------------------------------------------------------------

def _a_gris(img):
    """Imagen de PIL (de cualquier modo) -> `(array float32 en [0,1], tenia_transparencia)`.

    * La transparencia se aplana sobre BLANCO (blanco = fino = pasa la luz): sin esto el fondo
      transparente de un logo, que suele ser negro con alfa 0, saldría como la parte más gruesa.
    * Las imágenes de 16 bits conservan su precisión (se dividen por 65535, no se pasan a 8 bits).
    * El gris es el de PIL (Rec. 601 sobre los valores sRGB, sin linealizar): el "blanco y negro"
      que ve el ojo. CMYK y demás modos pasan por RGB."""
    modo = img.mode
    if modo in ("I;16", "I;16L", "I;16B", "I;16N", "I"):
        arr = np.asarray(img, dtype=np.float64)
        maximo = 65535.0 if (modo != "I" or arr.max() > 255) else 255.0
        return np.clip(arr / maximo, 0.0, 1.0).astype(np.float32), False
    if modo == "F":
        return np.clip(np.asarray(img, dtype=np.float32), 0.0, 1.0), False

    tenia_transparencia = modo in ("RGBA", "LA", "PA", "La", "RGBa") or "transparency" in img.info
    if tenia_transparencia:
        rgba = img.convert("RGBA")
        fondo = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        img = Image.alpha_composite(fondo, rgba).convert("L")
    elif modo == "L":
        pass
    elif modo in ("RGB", "1", "P"):
        img = img.convert("L")
    else:  # CMYK, YCbCr, LAB, HSV...
        img = img.convert("RGB").convert("L")
    return np.asarray(img, dtype=np.float32) / 255.0, tenia_transparencia


def _abrir(ruta_imagen, max_mb):
    """Valida el archivo (sin exigir un peso mínimo: un logo chico es válido), lo abre y le
    aplica la rotación EXIF. Devuelve la imagen de PIL."""
    validation.validar_imagen(ruta_imagen, max_mb=max_mb, min_mb=0)
    try:
        img = Image.open(ruta_imagen)
        img.load()
    except Exception as e:  # archivo corrupto, bomba de descompresión...
        raise ValidationError(f"No pude leer la imagen ({type(e).__name__}). ¿Está dañada?") from e
    return ImageOps.exif_transpose(img)  # una foto de celular viene "acostada" con una etiqueta que la endereza


# ---------------------------------------------------------------------------
#  Ajustes tonales (todos opcionales y neutros por defecto)
# ---------------------------------------------------------------------------

def invertir_brillo(brillo):
    """Negativo: el complemento `1 - brillo`. Cambia los valores, no la geometría (no espeja)."""
    return 1.0 - brillo


def _ajustar(brillo, px_por_mm, brillo_delta, contraste, gamma, auto_niveles, realce_local, suavizado_mm):
    """Aplica los ajustes pedidos, en este orden: suavizado, auto-niveles, realce local, gamma,
    contraste, brillo. Cada uno se SALTEA si está en su valor neutro, así el camino por defecto
    no toca ni un valor. Devuelve el mapa recortado a [0, 1]."""
    if suavizado_mm > 0:
        from scipy.ndimage import gaussian_filter
        brillo = gaussian_filter(brillo, sigma=suavizado_mm * px_por_mm, mode="nearest")
    if auto_niveles:
        bajo, alto = np.percentile(brillo, PERCENTILES_AUTO_NIVELES)
        if alto - bajo > 1e-6:
            brillo = (brillo - bajo) / (alto - bajo)
    if realce_local:
        from skimage import exposure
        brillo = exposure.equalize_adapthist(np.clip(brillo, 0.0, 1.0), clip_limit=CLIP_LIMIT_REALCE_LOCAL)
    if gamma != 1.0:
        brillo = np.clip(brillo, 0.0, 1.0) ** (1.0 / gamma)   # gamma > 1 aclara los tonos medios
    if contraste != 1.0:
        brillo = (brillo - 0.5) * contraste + 0.5
    if brillo_delta != 0.0:
        brillo = brillo + brillo_delta
    return np.clip(brillo, 0.0, 1.0)


# ---------------------------------------------------------------------------
#  L1: imagen -> mapa de brillo
# ---------------------------------------------------------------------------

def imagen_a_mapa_brillo(ruta_imagen, ancho_mm, alto_mm=None, px_por_mm=PX_POR_MM_DEFAULT,
                         desplazamiento=(0.0, 0.0), brillo=0.0, contraste=1.0, gamma=1.0,
                         auto_niveles=False, realce_local=False, suavizado_mm=0.0, invertir=False,
                         max_mb=50.0):
    """Imagen -> `MapaBrillo` para una placa de `ancho_mm` x `alto_mm`.

    Tamaño: con `alto_mm=None` la altura sale de la proporción de la foto. Si se pasan las dos
    medidas y no coinciden con la proporción de la foto, se RECORTA (nunca se estira); la ventana
    arranca centrada y `desplazamiento=(dx, dy)`, cada uno en [-1, 1], la corre hacia un borde
    (dx=-1 izquierda, +1 derecha; dy=-1 arriba, +1 abajo).

    Resolución: `px_por_mm` (entre 1 y 8; 4 por defecto). Nunca se agranda la foto: si tiene
    menos píxeles de los pedidos, el mapa sale a la resolución que la foto sí tiene y se avisa.

    Ajustes tonales, todos APAGADOS por defecto (sin ellos el mapa es exactamente el gris de PIL):
    `brillo` (suma, en [-1, 1]), `contraste` (1 = neutro), `gamma` (1 = neutro; >1 aclara los
    medios), `auto_niveles` (estira entre los percentiles 2 y 98), `realce_local` (CLAHE: ALTERA
    la escala de grises, sirve para fotos a contraluz o con niebla) y `suavizado_mm` (desenfoque
    gaussiano en mm, no en píxeles, para que no dependa de la resolución).

    `invertir=True`: negativo (`1 - brillo`), aplicado al final, después de los ajustes.

    Falla con `ValidationError` si la imagen no existe, no es PNG/JPG, pesa de más o está dañada,
    y con `ValueError` si un parámetro no tiene sentido."""
    if ancho_mm <= 0 or (alto_mm is not None and alto_mm <= 0):
        raise ValueError("ancho_mm y alto_mm tienen que ser mayores que 0")
    if not (PX_POR_MM_MIN <= px_por_mm <= PX_POR_MM_MAX):
        raise ValueError(f"px_por_mm tiene que estar entre {PX_POR_MM_MIN:g} y {PX_POR_MM_MAX:g}, recibí {px_por_mm:g}")
    if gamma <= 0 or contraste < 0 or suavizado_mm < 0:
        raise ValueError("gamma tiene que ser mayor que 0, y contraste y suavizado_mm no pueden ser negativos")
    dx, dy = desplazamiento
    if not (-1.0 <= dx <= 1.0 and -1.0 <= dy <= 1.0):
        raise ValueError("desplazamiento tiene que estar entre -1 y 1 en cada eje")

    avisos = []
    img = _abrir(ruta_imagen, max_mb)
    ancho_origen, alto_origen = img.size
    if ancho_origen < 2 or alto_origen < 2:
        raise ValidationError("La imagen tiene menos de 2 píxeles de lado.")
    gris, tenia_transparencia = _a_gris(img)
    if tenia_transparencia:
        avisos.append("La imagen tenía transparencia: se aplanó sobre blanco (la parte transparente deja pasar la luz).")

    # --- ventana de recorte: la proporción pedida, sin estirar ---
    proporcion_origen = ancho_origen / alto_origen
    if alto_mm is None:
        alto_mm = ancho_mm / proporcion_origen
        x0, y0, x1, y1 = 0.0, 0.0, float(ancho_origen), float(alto_origen)
    else:
        proporcion_pedida = ancho_mm / alto_mm
        x0, y0, x1, y1 = 0.0, 0.0, float(ancho_origen), float(alto_origen)
        if abs(proporcion_pedida - proporcion_origen) / proporcion_origen > 1e-3:
            if proporcion_origen > proporcion_pedida:       # la foto es más ancha: se recorta a lo ancho
                nuevo = alto_origen * proporcion_pedida
                x0 = (ancho_origen - nuevo) / 2 * (1 + dx)
                x1 = x0 + nuevo
            else:                                            # la foto es más alta: se recorta a lo alto
                nuevo = ancho_origen / proporcion_pedida
                y0 = (alto_origen - nuevo) / 2 * (1 + dy)
                y1 = y0 + nuevo
            avisos.append("La proporción pedida no es la de la foto: se recortó (sin estirar). "
                          "Con el desplazamiento podés mover qué parte queda.")

    # --- resolución: la pedida, sin pasar de los píxeles que la foto sí tiene ---
    px_foto = (x1 - x0) / ancho_mm
    px_real = min(px_por_mm, px_foto)
    if px_real < px_por_mm - 1e-9:
        avisos.append(f"La foto tiene {px_foto:.1f} px/mm a este tamaño y pediste {px_por_mm:g}: no se agranda, "
                      f"el mapa sale a {px_foto:.1f} px/mm (no hay más detalle que sacarle).")
    if px_real < PX_POR_MM_BAJO_AVISO:
        avisos.append(f"Resolución baja ({px_real:.1f} px/mm): cada píxel mide más que la línea impresa y se va a notar "
                      f"el pixelado. Usá una foto más grande o una placa más chica.")
    ancho_px = max(2, round(ancho_mm * px_real))
    alto_px = max(2, round(alto_mm * px_real))

    # --- recorte + escala en una sola pasada, en float (Lanczos: filtra antes de achicar) ---
    chica = Image.fromarray(gris).resize(
        (ancho_px, alto_px), resample=Image.LANCZOS, box=(x0, y0, x1, y1))
    mapa = np.clip(np.asarray(chica, dtype=np.float64), 0.0, 1.0)   # Lanczos puede pasarse apenas de [0,1]
    px_efectivo = ancho_px / ancho_mm

    mapa = _ajustar(mapa, px_efectivo, brillo, contraste, gamma, auto_niveles, realce_local, suavizado_mm)
    if invertir:
        mapa = invertir_brillo(mapa)

    triangulos = 2 * (ancho_px - 1) * (alto_px - 1)
    stl_mb = triangulos * BYTES_POR_TRIANGULO_STL / 1e6
    if stl_mb > PESO_STL_AVISO_MB:
        avisos.append(f"La malla va a ser pesada: ~{triangulos / 1e6:.1f} millones de triángulos (~{stl_mb:.0f} MB de STL) "
                      f"a {px_efectivo:.1f} px/mm. Con 4 px/mm ya se aprovecha todo el detalle que imprime una boquilla de 0,4 mm.")

    return MapaBrillo(
        brillo=mapa, ancho_mm=float(ancho_mm), alto_mm=float(alto_mm), ancho_px=ancho_px, alto_px=alto_px,
        px_por_mm=px_efectivo, px_por_mm_pedido=float(px_por_mm), triangulos_estimados=int(triangulos),
        stl_estimado_mb=float(stl_mb), avisos=avisos,
    )


def mapa_a_imagen(mapa):
    """`MapaBrillo` (o el array de brillo) -> imagen de PIL en grises de 8 bits, para guardarla o mostrarla."""
    brillo = mapa.brillo if isinstance(mapa, MapaBrillo) else mapa
    return Image.fromarray(np.round(np.clip(brillo, 0.0, 1.0) * 255.0).astype(np.uint8))
