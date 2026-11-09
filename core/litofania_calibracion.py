#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/litofania_calibracion.py
--------------------------------
L6 de la litofanía: placa de calibración de grosores. Hasta acá el `luz_minima` del 5 % era un supuesto sobre el
plástico; esta placa sirve para medirlo con TU filamento.

La placa es una ESCALERA: N franjas planas de grosor creciente (por defecto 7, de 0,6 a 3,0 mm), cada una con su
grosor GRABADO en una tira debajo, con dígitos de 7 segmentos. Se imprime, se pone a contraluz, se le saca una foto
y se lee el gris de cada franja. `calibrar_luz_minima` convierte esas lecturas en el coeficiente de atenuación `k`
del plástico, su "media luz" en mm y el `luz_minima` para el rango de grosores que uses.

Qué mide (y qué no): `luz_minima` depende del rango de grosores elegido, pero `k` es del filamento (y la lámpara).
Con `k`, `luz_minima = e^(-k·(grosor_max - grosor_min))` para cualquier rango: la relación ya está en L2
(`media_luz_mm` y `luz_minima_desde_media_luz`) y acá se reusa, no se reescribe. El modelo es el de L2
(Beer-Lambert): la luz cae como e^(-k·grosor). Un plástico que dispersa mucho no sigue esa curva y el ajuste lo
dice con un R² bajo en vez de dar un número falso.

La malla NO es geometría propia: es una grilla de grosores (rectángulos y dígitos pintados con numpy) que se pasa a
`litofania.malla_desde_grilla_grosor` (L3), así que cierra por construcción. En esa grilla cada punto es un vértice
de la malla y el paso es de 1/px_por_mm: la franja ocupa los vértices `[col0, col1]` (planos a su grosor) y la
rampa de un vértice al siguiente queda en el separador, fuera de la franja.
"""

from dataclasses import dataclass, field

import numpy as np

from core import litofania as lf

N_FRANJAS_DEFAULT = 7
N_FRANJAS_MIN, N_FRANJAS_MAX = 3, 20
GROSOR_MIN_DEFAULT = 0.6          # mm: cubre el 0,8 de L2 y es el límite de lo frágil (L4)
GROSOR_MAX_DEFAULT = 3.0          # mm: cubre el 2,8 de L2
GROSOR_MAX_ETIQUETABLE = 9.99     # mm: las etiquetas son "d.d" o "d.dd"
ANCHO_FRANJA_DEFAULT = 18.0       # mm
ALTO_FRANJA_DEFAULT = 30.0        # mm
SEPARADOR_DEFAULT = 3.0           # mm entre franjas: marco al grosor máximo, evita que una franja ilumine a la vecina
BORDE_DEFAULT = 3.0               # mm alrededor
ALTO_ETIQUETA_DEFAULT = 10.0      # mm: tira de etiquetas debajo de las franjas
PX_POR_MM_DEFAULT = 4.0
PX_POR_MM_RANGO = (2.0, 8.0)

# dígitos de 7 segmentos (en mm; en la grilla se redondean a píxeles)
DIGITO_ANCHO_MM = 3.6
DIGITO_ALTO_MM = 6.0
DIGITO_TRAZO_MM = 1.2
DIGITO_SEPARACION_MM = 1.2
ALTO_ETIQUETA_MIN_MM = DIGITO_ALTO_MM + 2.0

# segmentos de cada dígito: a arriba, b arriba-derecha, c abajo-derecha, d abajo, e abajo-izquierda,
# f arriba-izquierda, g medio
SEGMENTOS = {"0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc",
             "5": "afgcd", "6": "afgedc", "7": "abc", "8": "abcdefg", "9": "abcdfg"}

R2_MINIMO = 0.98                  # por debajo de esto el plástico no sigue bien e^(-k·grosor)
GRIS_SATURADO = 250               # una franja así de clara está sobreexpuesta: la foto la recortó
GRIS_RUIDO = 5                    # y así de oscura se hunde en el ruido de la cámara
FRANJAS_UTILES_MIN = 3
LUZ_CAIDA_MINIMA = 1e-3            # caída mínima de ln(luz) entre la franja más fina y la más gruesa para poder medir k


@dataclass
class PlacaCalibracion:
    """Resultado de `placa_de_calibracion`. `grosor`: array 2D float64 en mm (fila 0 = arriba), un punto por
    vértice de la malla. `escalones`: una entrada por franja, de izquierda a derecha, con `indice`,
    `grosor_pedido`, `grosor` (el real, ya ajustado a capas si se pidió), `etiqueta` (el texto grabado) y su
    ubicación en vértices (`col0`..`col1`, `fila0`..`fila1` de la franja; `etiqueta_fila0`..`etiqueta_fila1` de su
    celda de etiqueta, con las mismas columnas) y en mm (`x0_mm`..`x1_mm`, `y0_mm`..`y1_mm`, y desde abajo)."""
    grosor: np.ndarray
    ancho_mm: float
    alto_mm: float
    ancho_px: int
    alto_px: int
    px_por_mm: float
    escalones: list
    grosor_marco: float
    grosor_digito: float
    capa_mm: float = None
    primera_capa_mm: float = None
    avisos: list = field(default_factory=list)


@dataclass
class CalibracionLuz:
    """Resultado de `calibrar_luz_minima`. `k`: coeficiente de atenuación (1/mm). `media_luz_mm`: espesor que deja
    pasar la mitad de la luz. `luz_minima`: la que corresponde a `[grosor_min, grosor_max]`. `r2`: qué tan bien
    sigue la exponencial (1 = perfecto). `usadas` / `descartadas`: índices de franjas, y `motivos` el porqué de
    cada descartada."""
    k: float
    media_luz_mm: float
    luz_minima: float
    r2: float
    usadas: list
    descartadas: list
    motivos: dict
    grosor_min: float
    grosor_max: float
    luz_minima_en_rango: bool
    avisos: list = field(default_factory=list)


# ---------------------------------------------------------------------------
#  La placa: grilla de grosores
# ---------------------------------------------------------------------------

def _px(mm, px_por_mm):
    return int(round(mm * px_por_mm))


def etiqueta_de(grosor, decimales):
    return f"{grosor:.{decimales}f}"


def _decimales_para(grosores):
    """1 decimal si todos los grosores son múltiplos de 0,1 mm (lo normal); si no, 2."""
    return 1 if np.allclose(grosores, np.round(grosores, 1), atol=1e-6) else 2


def _medidas_del_digito(px_por_mm):
    ancho = max(3, _px(DIGITO_ANCHO_MM, px_por_mm))
    alto = max(5, _px(DIGITO_ALTO_MM, px_por_mm))
    trazo = max(2, _px(DIGITO_TRAZO_MM, px_por_mm))
    separacion = max(1, _px(DIGITO_SEPARACION_MM, px_por_mm))
    return ancho, alto, trazo, separacion


def _ancho_del_texto_px(texto, px_por_mm):
    ancho, _, trazo, separacion = _medidas_del_digito(px_por_mm)
    return sum(trazo if c == "." else ancho for c in texto) + separacion * (len(texto) - 1)


def _pintar_texto(grosor, texto, col, fila, px_por_mm, valor):
    """Graba `texto` (dígitos y un punto) con la esquina superior izquierda en (fila, col) de la grilla: cada trazo
    de cada dígito vale `valor`. Los rectángulos son semiabiertos en píxeles de vértice."""
    ancho, alto, trazo, separacion = _medidas_del_digito(px_por_mm)
    medio = (alto - trazo) // 2
    rects = {                                   # segmento -> (fila0, fila1, col0, col1) dentro de la caja del dígito
        "a": (0, trazo, 0, ancho), "d": (alto - trazo, alto, 0, ancho), "g": (medio, medio + trazo, 0, ancho),
        "b": (0, medio + trazo, ancho - trazo, ancho), "c": (medio, alto, ancho - trazo, ancho),
        "f": (0, medio + trazo, 0, trazo), "e": (medio, alto, 0, trazo),
    }
    x = col
    for caracter in texto:
        if caracter == ".":
            grosor[fila + alto - trazo: fila + alto, x: x + trazo] = valor
            x += trazo + separacion
            continue
        for segmento in SEGMENTOS[caracter]:
            f0, f1, c0, c1 = rects[segmento]
            grosor[fila + f0: fila + f1, x + c0: x + c1] = valor
        x += ancho + separacion


def placa_de_calibracion(n_franjas=N_FRANJAS_DEFAULT, grosor_min=GROSOR_MIN_DEFAULT, grosor_max=GROSOR_MAX_DEFAULT,
                         ancho_franja=ANCHO_FRANJA_DEFAULT, alto_franja=ALTO_FRANJA_DEFAULT,
                         separador_mm=SEPARADOR_DEFAULT, borde_mm=BORDE_DEFAULT,
                         alto_etiqueta=ALTO_ETIQUETA_DEFAULT, px_por_mm=PX_POR_MM_DEFAULT,
                         capa_mm=None, primera_capa_mm=lf.PRIMERA_CAPA_DEFAULT):
    """Grilla de grosores de la placa de calibración (ver la cabecera del módulo). De izquierda a derecha, `n_franjas`
    franjas planas con grosores equiespaciados de `grosor_min` a `grosor_max` (ajustados a capas con
    `cuantizar_a_capas` de L2 si se pasa `capa_mm`), separadas por un marco al grosor máximo; debajo de cada una, en
    una tira también al grosor máximo, su grosor grabado hasta el grosor mínimo. Falla con `ValueError` si algún
    parámetro no tiene sentido o si las etiquetas no entran."""
    if not (isinstance(n_franjas, (int, np.integer)) and N_FRANJAS_MIN <= n_franjas <= N_FRANJAS_MAX):
        raise ValueError(f"n_franjas tiene que ser un entero entre {N_FRANJAS_MIN} y {N_FRANJAS_MAX}, recibí {n_franjas!r}")
    if not (grosor_min > 0):
        raise ValueError("grosor_min tiene que ser mayor que 0")
    if not (grosor_max > grosor_min):
        raise ValueError("grosor_max tiene que ser mayor que grosor_min")
    if grosor_max > GROSOR_MAX_ETIQUETABLE:
        raise ValueError(f"grosor_max no puede pasar de {GROSOR_MAX_ETIQUETABLE:g} mm (las etiquetas no entran)")
    if not (PX_POR_MM_RANGO[0] <= px_por_mm <= PX_POR_MM_RANGO[1]):
        raise ValueError(f"px_por_mm tiene que estar entre {PX_POR_MM_RANGO[0]:g} y {PX_POR_MM_RANGO[1]:g} "
                         f"(con menos los dígitos no se leen), recibí {px_por_mm:g}")
    if not (separador_mm >= 1.0 and borde_mm >= 1.0):
        raise ValueError("separador_mm y borde_mm tienen que ser de al menos 1 mm")
    if not (alto_franja >= 5.0):
        raise ValueError("alto_franja tiene que ser de al menos 5 mm")
    if not (alto_etiqueta >= ALTO_ETIQUETA_MIN_MM):
        raise ValueError(f"alto_etiqueta tiene que ser de al menos {ALTO_ETIQUETA_MIN_MM:g} mm para que entren los dígitos")
    if capa_mm is not None:
        if not (capa_mm > 0):
            raise ValueError("capa_mm tiene que ser mayor que 0")
        if not (primera_capa_mm > 0):
            raise ValueError("primera_capa_mm tiene que ser mayor que 0")

    pedidos = np.linspace(grosor_min, grosor_max, n_franjas)
    reales = lf.cuantizar_a_capas(pedidos, capa_mm, primera_capa_mm) if capa_mm is not None else pedidos.copy()
    decimales = _decimales_para(reales)
    etiquetas = [etiqueta_de(t, decimales) for t in reales]
    ancho_texto = max(_ancho_del_texto_px(e, px_por_mm) for e in etiquetas)
    ancho_f, alto_f, sep, bor, alto_e = (_px(ancho_franja, px_por_mm), _px(alto_franja, px_por_mm),
                                          _px(separador_mm, px_por_mm), _px(borde_mm, px_por_mm),
                                          _px(alto_etiqueta, px_por_mm))
    if ancho_texto + 2 * max(1, _px(0.4, px_por_mm)) > ancho_f:
        minimo = (ancho_texto / px_por_mm) + 0.8
        raise ValueError(f"ancho_franja ({ancho_franja:g} mm) es muy chico para las etiquetas: hacen falta al menos "
                         f"{minimo:.1f} mm")

    avisos = []
    grosor_marco, grosor_digito = float(reales.max()), float(reales.min())
    if capa_mm is not None and len(set(np.round(reales, 6))) < n_franjas:
        avisos.append(f"Con capas de {capa_mm:g} mm algunas franjas caen en el mismo nivel y quedan iguales: "
                      f"usá menos franjas, un rango más ancho o una capa más fina.")

    ancho_total = 2 * bor + n_franjas * ancho_f + (n_franjas - 1) * sep      # en vértices: nx = ancho_total + 1
    alto_total = 2 * bor + alto_f + sep + alto_e
    grosor = np.full((alto_total + 1, ancho_total + 1), grosor_marco, dtype=np.float64)

    fila0 = bor
    fila_et0 = bor + alto_f + sep
    _, alto_dig, _, _ = _medidas_del_digito(px_por_mm)
    escalones = []
    for k in range(n_franjas):
        col0 = bor + k * (ancho_f + sep)
        col1 = col0 + ancho_f
        grosor[fila0: fila0 + alto_f + 1, col0: col1 + 1] = reales[k]
        ancho_t = _ancho_del_texto_px(etiquetas[k], px_por_mm)
        col_t = col0 + (ancho_f - ancho_t) // 2
        fila_t = fila_et0 + (alto_e - alto_dig) // 2
        _pintar_texto(grosor, etiquetas[k], col_t, fila_t, px_por_mm, grosor_digito)
        paso = 1.0 / px_por_mm
        escalones.append({
            "indice": k, "grosor_pedido": float(pedidos[k]), "grosor": float(reales[k]), "etiqueta": etiquetas[k],
            "col0": col0, "col1": col1, "fila0": fila0, "fila1": fila0 + alto_f,
            "etiqueta_fila0": fila_et0, "etiqueta_fila1": fila_et0 + alto_e,
            "x0_mm": col0 * paso, "x1_mm": col1 * paso,
            "y0_mm": (alto_total - (fila0 + alto_f)) * paso, "y1_mm": (alto_total - fila0) * paso,
        })

    return PlacaCalibracion(
        grosor=grosor, ancho_mm=ancho_total / px_por_mm, alto_mm=alto_total / px_por_mm,
        ancho_px=ancho_total + 1, alto_px=alto_total + 1, px_por_mm=float(px_por_mm), escalones=escalones,
        grosor_marco=grosor_marco, grosor_digito=grosor_digito,
        capa_mm=capa_mm, primera_capa_mm=primera_capa_mm if capa_mm is not None else None, avisos=avisos,
    )


def mapa_grosor_de_la_placa(placa, media_luz_mm):
    """La placa como `MapaGrosor` de L2, para simularla a contraluz con L5 (`simular_contraluz`) bajo un plástico de
    `media_luz_mm`. El rango del modelo es el de las franjas, y la `luz_minima` que le corresponde sale de
    `luz_minima_desde_media_luz` de L2 (si cae fuera del rango que admite L2, `ValueError`)."""
    gmin, gmax = placa.grosor_digito, placa.grosor_marco
    luz_minima = lf.luz_minima_desde_media_luz(media_luz_mm, gmin, gmax)
    return lf.MapaGrosor(
        grosor=placa.grosor, ancho_mm=placa.ancho_mm, alto_mm=placa.alto_mm, ancho_px=placa.ancho_px,
        alto_px=placa.alto_px, px_por_mm=placa.px_por_mm, grosor_min=gmin, grosor_max=gmax,
        grosor_min_efectivo=gmin, grosor_max_efectivo=gmax, luz_minima=luz_minima,
        coeficiente_atenuacion=lf.coeficiente_atenuacion(luz_minima, gmin, gmax),
        media_luz_mm=lf.media_luz_mm(luz_minima, gmin, gmax), compensado=False,
        capa_mm=placa.capa_mm, primera_capa_mm=placa.primera_capa_mm,
    )


# ---------------------------------------------------------------------------
#  Del gris de la foto al plástico
# ---------------------------------------------------------------------------

def calibrar_luz_minima(grosores_mm, grises, grosor_min=lf.GROSOR_MIN_DEFAULT, grosor_max=lf.GROSOR_MAX_DEFAULT,
                        gris_saturado=GRIS_SATURADO, gris_ruido=GRIS_RUIDO, min_franjas=FRANJAS_UTILES_MIN,
                        r2_minimo=R2_MINIMO):
    """Del gris (0-255) que se lee en cada franja de la foto de la placa a contraluz -> `CalibracionLuz`.

    Cada gris pasa a luz lineal con `eotf_srgb` de L2 (la foto guarda valores sRGB), y se ajusta una recta por
    mínimos cuadrados a ln(luz) contra grosor: la pendiente es `-k` (Beer-Lambert). La intersección (la
    exposición de la foto y el brillo de la lámpara) no importa. De `k` salen la media luz y el `luz_minima` de
    `[grosor_min, grosor_max]`, con las funciones de L2.

    Se descartan las franjas saturadas (gris >= `gris_saturado`: la cámara las recortó) y las que se hunden en el ruido
    (gris <= `gris_ruido`); hacen falta al menos `min_franjas` útiles. Un R² menor que `r2_minimo` avisa que el plástico no
    sigue bien una exponencial (dispersa la luz): el número es aproximado. Falla con `ValueError` si los datos no
    sirven (largos distintos, grises fuera de 0-255, pocas franjas útiles, o una luz que no baja con el grosor)."""
    t = np.asarray(grosores_mm, dtype=np.float64).ravel()
    g = np.asarray(grises, dtype=np.float64).ravel()
    if t.size != g.size:
        raise ValueError(f"hay {t.size} grosores y {g.size} grises: tiene que ser uno por franja")
    if not (np.isfinite(t).all() and np.isfinite(g).all()):
        raise ValueError("los grosores y los grises tienen que ser números")
    if (g < 0).any() or (g > 255).any():
        raise ValueError("los grises tienen que estar entre 0 y 255")
    if (t <= 0).any():
        raise ValueError("los grosores tienen que ser mayores que 0")
    lf._validar_grosores(grosor_min, grosor_max, lf.LUZ_MINIMA_DEFAULT)

    motivos = {}
    for i, valor in enumerate(g):
        if valor >= gris_saturado:
            motivos[i] = f"saturada (gris {valor:g} >= {gris_saturado:g}: la foto la recortó; sacala con menos exposición)"
        elif valor <= gris_ruido:
            motivos[i] = f"muy oscura (gris {valor:g} <= {gris_ruido:g}: se hunde en el ruido de la cámara)"
    usadas = [i for i in range(t.size) if i not in motivos]
    if len(usadas) < min_franjas:
        raise ValueError(f"solo {len(usadas)} franjas útiles (hacen falta al menos {min_franjas}): "
                         + "; ".join(f"franja {i + 1} {m}" for i, m in sorted(motivos.items())))
    tu, gu = t[usadas], g[usadas]
    if np.ptp(tu) <= 0:
        raise ValueError("las franjas útiles tienen todas el mismo grosor: no se puede medir cómo cae la luz")

    luz = lf.eotf_srgb(gu / 255.0)
    y = np.log(luz)
    pendiente, ordenada = np.polyfit(tu, y, 1)
    if not (pendiente * np.ptp(tu) < -LUZ_CAIDA_MINIMA):      # menos que esto es ruido: ni una pendiente de 1e-16 vale
        raise ValueError("la luz no baja con el grosor (la pendiente salió "
                         f"{pendiente:+.3g}): revisá que los grises estén en el orden de los grosores y que la foto sea "
                         "de la placa a contraluz")
    k = float(-pendiente)
    residuos = y - (pendiente * tu + ordenada)
    total = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - float((residuos ** 2).sum()) / total if total > 0 else 1.0
    media_luz = float(np.log(2.0) / k)
    luz_minima = lf.luz_minima_desde_media_luz(media_luz, grosor_min, grosor_max)   # la cuenta de L2, no una copia
    bajo, alto = lf.LUZ_MINIMA_RANGO
    en_rango = bajo <= luz_minima <= alto

    avisos = []
    if r2 < r2_minimo:
        avisos.append(f"El ajuste es flojo (R² = {r2:.3f}, se pedía al menos {r2_minimo:g}): este plástico no sigue bien una "
                      f"exponencial (dispersa la luz) o la foto tiene reflejos o exposición despareja. El número es una "
                      f"aproximación; calibrá en el rango de grosores que vas a usar y repetí la foto.")
    if motivos:
        avisos.append(f"Se descartaron {len(motivos)} de {t.size} franjas: "
                      + "; ".join(f"franja {i + 1} {m}" for i, m in sorted(motivos.items())) + ".")
    if len(usadas) == min_franjas and len(usadas) < t.size:
        avisos.append(f"Quedaron solo {len(usadas)} franjas útiles: el ajuste es poco robusto. Repetí la foto con otra exposición.")
    if not en_rango:
        avisos.append(f"El luz_minima que sale ({luz_minima * 100:.2f} %) está fuera de lo que admite el generador "
                      f"({bajo * 100:g} %–{alto * 100:g} %) para el rango {grosor_min:g}–{grosor_max:g} mm: probá un rango más "
                      f"angosto o más ancho.")

    return CalibracionLuz(
        k=k, media_luz_mm=media_luz, luz_minima=luz_minima, r2=float(r2), usadas=usadas,
        descartadas=sorted(motivos), motivos=motivos, grosor_min=float(grosor_min), grosor_max=float(grosor_max),
        luz_minima_en_rango=bool(en_rango), avisos=avisos,
    )
