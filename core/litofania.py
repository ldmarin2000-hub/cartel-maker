#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/litofania.py
--------------------
Litofanía: una placa donde la imagen se forma por GROSOR variable (claro = fino,
pasa la luz; oscuro = grueso, la bloquea). Este módulo se arma por partes:

  L1 -- imagen -> MAPA DE BRILLO (`imagen_a_mapa_brillo`): una grilla 2D con el brillo
        de cada punto de la placa, en [0, 1], a la resolución pedida en píxeles/mm.
  L2 -- brillo -> GROSOR (`brillo_a_grosor`): el mapa de grosores en mm, compensando que
        el plástico atenúa la luz de forma exponencial (Beer-Lambert) para que, a
        contraluz, la placa se vea como la foto en una pantalla. Ver la cabecera de esa
        sección más abajo.
  L3 -- grosor -> MALLA 3D (`malla_desde_grosor`): la placa watertight (fondo plano, frente
        con relieve, paredes cerradas), armada con numpy sin bucles de Python.

El mapa de brillo (L1) es FIEL a la foto: por defecto el resultado es exactamente el gris
de PIL (`convert("L")`), sin realce de ningún tipo. Convertir ese brillo en grosor es la
etapa siguiente (L2): no se mezcla "el brillo del píxel" con "el grosor para que se vea así".

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


# ---------------------------------------------------------------------------
#  L2: brillo -> grosor, con compensación de la atenuación de la luz
# ---------------------------------------------------------------------------
#
# Modelo (Beer-Lambert): la luz que pasa por un espesor t es proporcional a e^(-k·t). Relativa a la
# zona MÁS FINA de la placa (`grosor_min`), la luz que pasa es T(t) = e^(-k·(t - grosor_min)), y lo
# más grueso (`grosor_max`) deja pasar `luz_minima` = e^(-k·Δ) de ella (Δ = grosor_max - grosor_min).
#
# Fidelidad: la foto guarda valores sRGB (gamma ~2,2) y una pantalla los muestra con la luz
# `EOTF_sRGB(brillo)`. Para que la placa, a contraluz, se vea como la foto en una pantalla, la luz
# que pase tiene que ser  T*(b) = luz_minima + (1 - luz_minima)·EOTF_sRGB(b)  (el suelo `luz_minima`
# es el negro de la placa: nunca llega a cero). Despejando el grosor:
#
#     grosor(b) = grosor_min + Δ · ln(1 / T*(b)) / ln(1 / luz_minima)
#
# El coeficiente k no aparece: solo importan `luz_minima` y los dos grosores. Brillo 1 da
# exactamente `grosor_min` y brillo 0 da exactamente `grosor_max`.
#
# Límite del modelo: el plástico real también DISPERSA la luz, y Beer-Lambert es una aproximación;
# `luz_minima` es un parámetro EFECTIVO que se mide imprimiendo la placa de calibración (L6).

GROSOR_MIN_DEFAULT = 0.8          # mm: lo más claro, deja pasar la luz
GROSOR_MAX_DEFAULT = 2.8          # mm: lo más oscuro, la bloquea casi toda
LUZ_MINIMA_DEFAULT = 0.05         # lo más grueso deja pasar el 5 % de la luz de lo más fino (supuesto hasta L6)
LUZ_MINIMA_RANGO = (0.005, 0.5)   # 0,5 % a 50 %
PRIMERA_CAPA_DEFAULT = 0.2        # mm: la primera capa del perfil estándar de la A1 con boquilla de 0,4
NIVELES_POCOS_AVISO = 12          # menos niveles de gris reales que esto y se ven bandas en los degradés


def eotf_srgb(valor):
    """sRGB -> luz lineal relativa (0..1): la luz con que una pantalla muestra ese valor de gris."""
    valor = np.asarray(valor, dtype=np.float64)
    return np.where(valor <= 0.04045, valor / 12.92, ((valor + 0.055) / 1.055) ** 2.4)


def _validar_grosores(grosor_min, grosor_max, luz_minima):
    if not (grosor_min > 0):
        raise ValueError("grosor_min tiene que ser mayor que 0")
    if not (grosor_max > grosor_min):
        raise ValueError("grosor_max tiene que ser mayor que grosor_min")
    bajo, alto = LUZ_MINIMA_RANGO
    if not (bajo <= luz_minima <= alto):   # también rechaza NaN
        raise ValueError(f"luz_minima tiene que estar entre {bajo * 100:g} % y {alto * 100:g} % "
                         f"(entre {bajo:g} y {alto:g}), recibí {luz_minima}")


def coeficiente_atenuacion(luz_minima, grosor_min, grosor_max):
    """k (en 1/mm) del modelo Beer-Lambert para esa `luz_minima` y ese rango de grosores."""
    _validar_grosores(grosor_min, grosor_max, luz_minima)
    return float(np.log(1.0 / luz_minima) / (grosor_max - grosor_min))


def media_luz_mm(luz_minima, grosor_min, grosor_max):
    """Espesor de media luz (mm): cuántos milímetros de plástico dejan pasar la mitad de la luz.
    Es la forma más intuitiva de leer `luz_minima`, y lo que se puede medir con el filamento."""
    return float(np.log(2.0) / coeficiente_atenuacion(luz_minima, grosor_min, grosor_max))


def luz_minima_desde_media_luz(media_luz, grosor_min, grosor_max):
    """Inversa de `media_luz_mm`: la `luz_minima` que corresponde a ese espesor de media luz en ese
    rango de grosores (con el mismo filamento, más rango = más oscuro lo más grueso)."""
    if not (media_luz > 0):
        raise ValueError("el espesor de media luz tiene que ser mayor que 0")
    if not (grosor_min > 0 and grosor_max > grosor_min):
        raise ValueError("hace falta 0 < grosor_min < grosor_max")
    return float(0.5 ** ((grosor_max - grosor_min) / media_luz))


def luz_transmitida(grosor, grosor_min=GROSOR_MIN_DEFAULT, grosor_max=GROSOR_MAX_DEFAULT,
                    luz_minima=LUZ_MINIMA_DEFAULT):
    """Modelo directo: luz que pasa por `grosor` (mm), relativa a la que pasa por `grosor_min`
    (= 1,0); por `grosor_max` pasa exactamente `luz_minima`. Lo usan los tests y la simulación a contraluz."""
    k = coeficiente_atenuacion(luz_minima, grosor_min, grosor_max)
    return np.exp(-k * (np.asarray(grosor, dtype=np.float64) - grosor_min))


def grosor_desde_brillo(brillo, grosor_min=GROSOR_MIN_DEFAULT, grosor_max=GROSOR_MAX_DEFAULT,
                        luz_minima=LUZ_MINIMA_DEFAULT, compensar=True):
    """Array de brillo en [0, 1] -> array de grosor en mm (mismo tamaño). No modifica `brillo`.

    `compensar=True` (lo recomendado): la curva de la cabecera de esta sección, para que la luz
    transmitida sea fiel a la foto. `compensar=False`: grosor lineal con el brillo
    (`grosor_min + (1 - brillo)·Δ`), sin tener en cuenta cómo atenúa la luz el plástico; sirve para
    comparar. En los dos casos brillo 1 -> `grosor_min` y brillo 0 -> `grosor_max`, exactos."""
    _validar_grosores(grosor_min, grosor_max, luz_minima)
    brillo = np.asarray(brillo, dtype=np.float64)
    if not np.isfinite(brillo).all():
        raise ValueError("el mapa de brillo tiene valores no numéricos (NaN o infinito)")
    if brillo.size and (brillo.min() < -1e-9 or brillo.max() > 1.0 + 1e-9):
        raise ValueError("el brillo tiene que estar en [0, 1]")
    brillo = np.clip(brillo, 0.0, 1.0)            # copia: la entrada no se toca

    if compensar:
        luz_objetivo = np.minimum(luz_minima + (1.0 - luz_minima) * eotf_srgb(brillo), 1.0)
        fraccion = np.log(1.0 / luz_objetivo) / np.log(1.0 / luz_minima)
        # los extremos son exactos por definición del modelo (no dependen del último bit de un log)
        fraccion = np.where(brillo >= 1.0, 0.0, np.where(brillo <= 0.0, 1.0, fraccion))
    else:
        fraccion = 1.0 - brillo
    fraccion = np.clip(fraccion, 0.0, 1.0)
    return grosor_min * (1.0 - fraccion) + grosor_max * fraccion   # con 0 y 1 da grosor_min y grosor_max exactos


def cuantizar_a_capas(grosor, capa_mm, primera_capa_mm=PRIMERA_CAPA_DEFAULT):
    """Lleva cada grosor al nivel de capa más cercano: los niveles son `primera_capa_mm + m·capa_mm`
    (m = 0, 1, 2...). Es lo que hace el rebanador al cortar a mitad de cada capa (un supuesto que
    confirma la placa de L6). Los empates (justo a mitad de camino) van al nivel de arriba."""
    if not (capa_mm > 0):
        raise ValueError("capa_mm tiene que ser mayor que 0")
    if not (primera_capa_mm > 0):
        raise ValueError("primera_capa_mm tiene que ser mayor que 0")
    grosor = np.asarray(grosor, dtype=np.float64)
    m = np.floor((grosor - primera_capa_mm) / capa_mm + 0.5 + 1e-9)
    return primera_capa_mm + np.maximum(m, 0.0) * capa_mm


@dataclass
class MapaGrosor:
    """Resultado de `brillo_a_grosor`: el mapa de grosores en mm, sobre la misma grilla que el mapa
    de brillo del que sale (misma forma, mismo tamaño de placa).

    `grosor_min` / `grosor_max`: los pedidos. `grosor_min_efectivo` / `grosor_max_efectivo`: los que
    de verdad quedan (distintos solo si se cuantizó a capas). `coeficiente_atenuacion` (1/mm) y
    `media_luz_mm` salen de `luz_minima` y los grosores pedidos. `niveles`: cuántos niveles de grosor
    distintos existen entre los extremos al cuantizar (None si no se cuantizó)."""
    grosor: np.ndarray
    ancho_mm: float
    alto_mm: float
    ancho_px: int
    alto_px: int
    px_por_mm: float
    grosor_min: float
    grosor_max: float
    grosor_min_efectivo: float
    grosor_max_efectivo: float
    luz_minima: float
    coeficiente_atenuacion: float
    media_luz_mm: float
    compensado: bool
    capa_mm: float = None
    primera_capa_mm: float = None
    niveles: int = None
    avisos: list = field(default_factory=list)


def brillo_a_grosor(mapa_brillo, grosor_min=GROSOR_MIN_DEFAULT, grosor_max=GROSOR_MAX_DEFAULT,
                    luz_minima=LUZ_MINIMA_DEFAULT, compensar=True, capa_mm=None,
                    primera_capa_mm=PRIMERA_CAPA_DEFAULT):
    """`MapaBrillo` (L1) -> `MapaGrosor`. No arma malla (eso es L3) y no modifica el mapa de brillo.

    `luz_minima`: cuánta luz deja pasar la zona más gruesa, como fracción de la que deja pasar la más
    fina (0,05 = 5 %; menos es un plástico más denso). `compensar`: ver `grosor_desde_brillo`.

    `capa_mm` (por ejemplo 0,08 / 0,12 / 0,2): cuantiza los grosores a niveles de capa reales
    (`primera_capa_mm + m·capa_mm`); apagado por defecto. Con capa, los extremos se ajustan a la capa
    más cercana, `niveles` dice cuántos grises reales hay y se avisa si son pocos."""
    if not isinstance(mapa_brillo, MapaBrillo):
        raise TypeError("brillo_a_grosor necesita un MapaBrillo (el resultado de imagen_a_mapa_brillo)")
    _validar_grosores(grosor_min, grosor_max, luz_minima)
    if capa_mm is not None:
        if not (capa_mm > 0):
            raise ValueError("capa_mm tiene que ser mayor que 0")
        if not (primera_capa_mm > 0):
            raise ValueError("primera_capa_mm tiene que ser mayor que 0")
        if capa_mm >= grosor_max - grosor_min:
            raise ValueError(f"la capa ({capa_mm:g} mm) tiene que ser menor que el rango de grosores "
                             f"({grosor_max - grosor_min:g} mm)")

    grosor = grosor_desde_brillo(mapa_brillo.brillo, grosor_min, grosor_max, luz_minima, compensar)
    avisos = []
    minimo_efectivo, maximo_efectivo, niveles = float(grosor_min), float(grosor_max), None
    if capa_mm is not None:
        grosor = cuantizar_a_capas(grosor, capa_mm, primera_capa_mm)
        minimo_efectivo = float(cuantizar_a_capas(grosor_min, capa_mm, primera_capa_mm))
        maximo_efectivo = float(cuantizar_a_capas(grosor_max, capa_mm, primera_capa_mm))
        niveles = int(round((maximo_efectivo - minimo_efectivo) / capa_mm)) + 1
        if grosor_min < primera_capa_mm - 1e-9:
            avisos.append(f"grosor_min ({grosor_min:g} mm) es menor que la primera capa ({primera_capa_mm:g} mm): "
                          f"lo más fino va a salir de {primera_capa_mm:g} mm.")
        if abs(minimo_efectivo - grosor_min) > 1e-6 or abs(maximo_efectivo - grosor_max) > 1e-6:
            avisos.append(f"Con capas de {capa_mm:g} mm (primera de {primera_capa_mm:g}) los grosores extremos caen en "
                          f"{minimo_efectivo:.2f} y {maximo_efectivo:.2f} mm (pediste {grosor_min:.2f} y {grosor_max:.2f}).")
        if niveles < NIVELES_POCOS_AVISO:
            avisos.append(f"Con capas de {capa_mm:g} mm solo hay {niveles} niveles de gris reales entre "
                          f"{minimo_efectivo:.2f} y {maximo_efectivo:.2f} mm: se van a ver bandas en los degradés. "
                          f"Probá una capa más fina (0,12 o 0,08) o un rango de grosores mayor.")

    return MapaGrosor(
        grosor=grosor, ancho_mm=mapa_brillo.ancho_mm, alto_mm=mapa_brillo.alto_mm,
        ancho_px=mapa_brillo.ancho_px, alto_px=mapa_brillo.alto_px, px_por_mm=mapa_brillo.px_por_mm,
        grosor_min=float(grosor_min), grosor_max=float(grosor_max),
        grosor_min_efectivo=minimo_efectivo, grosor_max_efectivo=maximo_efectivo,
        luz_minima=float(luz_minima),
        coeficiente_atenuacion=coeficiente_atenuacion(luz_minima, grosor_min, grosor_max),
        media_luz_mm=media_luz_mm(luz_minima, grosor_min, grosor_max),
        compensado=bool(compensar), capa_mm=capa_mm,
        primera_capa_mm=primera_capa_mm if capa_mm is not None else None,
        niveles=niveles, avisos=avisos,
    )


# ---------------------------------------------------------------------------
#  L3: grosor -> malla 3D watertight, vectorizada
# ---------------------------------------------------------------------------
#
# La placa vive en el plano XY: la cara trasera es PLANA en z = 0 y el frente es el relieve, con
# z = grosor. Fila 0 del mapa = arriba (y = alto_mm), columna 0 = izquierda (x = 0). Visto desde +Z
# (el lado del relieve) la foto se lee derecha, sin espejar. La placa mide EXACTAMENTE
# `ancho_mm` x `alto_mm`: los vértices van en `linspace(0, ancho_mm, nx)`, así que el paso es
# ancho_mm/(nx-1) y no el ancho_mm/nx nominal de L1 (una diferencia menor a 1/(nx-1)).
#
# Todo es numpy sobre la grilla completa, sin un solo bucle de Python (un test lo verifica con `ast`):
#
#   * frente: un vértice por punto del mapa, y 2 triángulos por celda (4 recortes de la matriz de
#     índices dan las 4 esquinas de TODAS las celdas a la vez);
#   * paredes: el perímetro (otros 4 recortes) une el borde del frente con el de la trasera;
#   * trasera plana: un ABANICO desde un vértice central, no una grilla -- una grilla duplicaría los
#     triángulos de la malla, y así la trasera y las paredes suman menos del 1 %. Los triángulos del
#     abanico son largos y finos (hasta ~500:1 en una placa grande) pero de área positiva; si alguna vez
#     molestaran al rebanador, el plan B es una trasera con la misma grilla (el doble de triángulos).
#
# Cierra por construcción: toda arista pertenece a exactamente 2 caras (las interiores del frente, las
# del borde del frente con una pared, las verticales entre paredes vecinas y las del borde de la trasera
# con una pared y con el abanico). `verificar_malla` lo comprueba por separado.

CARAS_VISIBLES = ("relieve", "plana")
DIAGONALES = ("adaptativa", "fija")


def _validar_grilla_grosor(grosor, ancho_mm, alto_mm, cara_visible, diagonal):
    """Valida los datos de la malla y devuelve el grosor como array float64 2D."""
    grosor = np.asarray(grosor, dtype=np.float64)
    if grosor.ndim != 2 or grosor.shape[0] < 2 or grosor.shape[1] < 2:
        raise ValueError(f"el mapa de grosor tiene que ser 2D de al menos 2x2 puntos, recibí forma {grosor.shape}")
    if not np.isfinite(grosor).all():
        raise ValueError("el mapa de grosor tiene valores no numéricos (NaN o infinito)")
    if not (grosor > 0).all():
        raise ValueError("todos los grosores tienen que ser mayores que 0 (la placa no puede tener agujeros ni paredes de altura cero)")
    if not (ancho_mm > 0 and alto_mm > 0):
        raise ValueError("ancho_mm y alto_mm tienen que ser mayores que 0")
    if cara_visible not in CARAS_VISIBLES:
        raise ValueError(f"cara_visible tiene que ser una de {CARAS_VISIBLES}, recibí {cara_visible!r}")
    if diagonal not in DIAGONALES:
        raise ValueError(f"diagonal tiene que ser una de {DIAGONALES}, recibí {diagonal!r}")
    return grosor


def _caras_del_frente(indices, grosor, diagonal):
    """2 triángulos por celda, con la normal hacia +Z. `adaptativa`: en cada celda va la diagonal con
    menor salto de altura (sigue las crestas y evita dientes de sierra); `fija`: siempre a-d."""
    a, b = indices[:-1, :-1], indices[:-1, 1:]
    c, d = indices[1:, :-1], indices[1:, 1:]
    con_diagonal_ad = np.stack([np.stack([a, c, d], axis=-1), np.stack([a, d, b], axis=-1)], axis=2)
    if diagonal == "fija":
        return con_diagonal_ad.reshape(-1, 3)
    con_diagonal_bc = np.stack([np.stack([a, c, b], axis=-1), np.stack([b, c, d], axis=-1)], axis=2)
    salto_ad = np.abs(grosor[:-1, :-1] - grosor[1:, 1:])
    salto_bc = np.abs(grosor[:-1, 1:] - grosor[1:, :-1])
    return np.where((salto_ad <= salto_bc)[:, :, None, None], con_diagonal_ad, con_diagonal_bc).reshape(-1, 3)


def _perimetro(indices):
    """Índices del borde de la grilla, antihorario visto desde +Z (abajo hacia la derecha, derecha hacia
    arriba, arriba hacia la izquierda, izquierda hacia abajo), sin repetir las esquinas."""
    return np.concatenate([indices[-1, :-1], indices[:0:-1, -1], indices[0, :0:-1], indices[:-1, 0]])


def malla_desde_grilla_grosor(grosor, ancho_mm, alto_mm, cara_visible="relieve", diagonal="adaptativa"):
    """Array de grosores (mm, fila 0 = arriba) -> `trimesh.Trimesh` watertight de una placa de
    `ancho_mm` x `alto_mm`. No modifica `grosor`.

    `cara_visible`: "relieve" (por defecto) = quien mira desde el lado del relieve (+Z) ve la foto
    derecha; "plana" = quien mira la cara lisa (desde -Z) la ve derecha, para lo cual se espeja X.
    `diagonal`: "adaptativa" (por defecto) o "fija". Vectorizado: sin bucles de Python."""
    import trimesh
    grosor = _validar_grilla_grosor(grosor, ancho_mm, alto_mm, cara_visible, diagonal)
    if cara_visible == "plana":
        grosor = grosor[:, ::-1]
    alto_px, ancho_px = grosor.shape

    xs = np.linspace(0.0, ancho_mm, ancho_px)
    ys = np.linspace(alto_mm, 0.0, alto_px)                          # fila 0 arriba
    x, y = np.meshgrid(xs, ys)
    frente = np.column_stack((x.ravel(), y.ravel(), grosor.ravel()))
    indices = np.arange(ancho_px * alto_px, dtype=np.int32).reshape(alto_px, ancho_px)
    caras_frente = _caras_del_frente(indices, grosor, diagonal)

    perimetro = _perimetro(indices)
    m = perimetro.size
    primero_atras = ancho_px * alto_px                                # índice del primer vértice de la trasera
    atras = np.column_stack((frente[perimetro, 0], frente[perimetro, 1], np.zeros(m)))
    centro = np.array([[ancho_mm / 2.0, alto_mm / 2.0, 0.0]])
    vertices = np.vstack((frente, atras, centro))

    # paredes: cada tramo del perímetro (f0 -> f1) une el borde del frente con el de la trasera (b0 -> b1)
    f0, f1 = perimetro, np.roll(perimetro, -1)
    b0 = primero_atras + np.arange(m, dtype=np.int32)
    b1 = primero_atras + (np.arange(m, dtype=np.int32) + 1) % m
    paredes = np.concatenate([np.stack([f0, b0, b1], axis=-1), np.stack([f0, b1, f1], axis=-1)])

    # trasera plana: abanico desde el vértice central, con la normal hacia -Z
    abanico = np.stack([b0, np.full(m, primero_atras + m, dtype=np.int32), b1], axis=-1)

    caras = np.concatenate([caras_frente, paredes, abanico])
    return trimesh.Trimesh(vertices=vertices, faces=caras, process=False)


def malla_desde_grosor(mapa_grosor, cara_visible="relieve", diagonal="adaptativa"):
    """`MapaGrosor` (L2) -> malla watertight de la placa, del tamaño en mm del mapa. No exporta (eso
    es L4) y no modifica el mapa de grosor."""
    if not isinstance(mapa_grosor, MapaGrosor):
        raise TypeError("malla_desde_grosor necesita un MapaGrosor (el resultado de brillo_a_grosor)")
    return malla_desde_grilla_grosor(mapa_grosor.grosor, mapa_grosor.ancho_mm, mapa_grosor.alto_mm,
                                     cara_visible=cara_visible, diagonal=diagonal)


def verificar_malla(malla):
    """Comprobaciones independientes de que la malla cierra, devueltas en un dict (`ok` = todas):
    `watertight`, `winding_consistente`, `volumen_positivo` (las caras miran hacia afuera), `euler`
    (V - E + F: 2 para una superficie cerrada sin agujeros ni asas), `aristas_con_dos_caras` (toda arista
    la comparten exactamente 2 caras), `caras_degeneradas` (área cero) y `caras_duplicadas`."""
    caras = np.asarray(malla.faces)
    n_vertices, n_caras = len(malla.vertices), len(caras)
    aristas = np.sort(caras[:, [0, 1, 1, 2, 2, 0]].reshape(-1, 2), axis=1).astype(np.int64)
    claves, usos = np.unique(aristas[:, 0] * n_vertices + aristas[:, 1], return_counts=True)
    resultado = {
        "vertices": int(n_vertices), "caras": int(n_caras), "aristas": int(claves.size),
        "euler": int(n_vertices - claves.size + n_caras),
        "aristas_con_dos_caras": bool((usos == 2).all()),
        "caras_degeneradas": int((malla.area_faces <= 0).sum()),
        "caras_duplicadas": int(n_caras - np.unique(np.sort(caras, axis=1), axis=0).shape[0]),
        "watertight": bool(malla.is_watertight),
        "winding_consistente": bool(malla.is_winding_consistent),
        "volumen_positivo": bool(malla.volume > 0),
    }
    resultado["ok"] = bool(
        resultado["watertight"] and resultado["winding_consistente"] and resultado["volumen_positivo"]
        and resultado["euler"] == 2 and resultado["aristas_con_dos_caras"]
        and resultado["caras_degeneradas"] == 0 and resultado["caras_duplicadas"] == 0)
    return resultado
