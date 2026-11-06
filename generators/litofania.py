#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generators/litofania.py
--------------------------
Litofanía de punta a punta: imagen -> placa 3D watertight (STL) que, a contraluz, se ve como la foto.

Este generador solo ORQUESTA lo que ya existe en core/litofania.py, sin reimplementar nada:

    imagen_a_mapa_brillo (L1)  ->  brillo_a_grosor (L2)  ->  malla_desde_grosor (L3)  ->  STL

y le suma lo que le falta a un generador del proyecto: el chequeo contra la Bambu A1, los avisos de
imprimibilidad (tamaño, grosor frágil, resolución que la boquilla no aprovecha, peso del archivo), las
notas de orientación y un dict de resultado con el mismo contrato que Esculturas (`ruta_stl`, `ancho_mm`,
`alto_mm`, `profundidad_mm`, `vertices`, `caras`, `watertight`, `info`, `avisos`, `entra_a1`, `mensaje_a1`),
más los datos propios de la litofanía. No dibuja preview PNG (la simulación a contraluz es L5).

No pregunta ni imprime nada en `generar()`: así lo llama igual la consola (`ejecutar()`) y la página.
Los archivos inválidos fallan con `FileNotFoundError` / `ValueError` (nunca `ValidationError`), que es lo
que las páginas ya atrapan para mostrar el error sin caerse.
"""

import os
import time

from core import bambu_a1, litofania as lf, pieza
from core.validation import ValidationError

NOMBRE = "Litofanía"
DESCRIPCION = "Imagen -> placa que a contraluz se ve como la foto (el brillo se convierte en grosor). STL watertight."

CARPETA_SALIDA = "output"

GROSOR_FRAGIL_MM = 0.6          # por debajo de esto la zona más fina de la placa es muy frágil (3 capas de 0,2)
BOQUILLA_DEFAULT_MM = 0.4
TOLERANCIA_RESOLUCION = 1.02    # el mapa redondea los píxeles; 2 % de margen para no avisar en el límite exacto
BYTES_CABECERA_STL = 84         # STL binario: 80 de cabecera + 4 del conteo, y 50 bytes por triángulo


def _px_por_mm_util(boquilla_mm):
    """Resolución a partir de la cual más píxeles no se imprimen: dos por cada ancho de boquilla."""
    return 2.0 / boquilla_mm


def _validar_parametros(ruta_imagen, cara_visible, diagonal, boquilla_mm):
    if not ruta_imagen or not os.path.exists(ruta_imagen):
        raise FileNotFoundError(f"no encuentro la imagen: {ruta_imagen}")
    if cara_visible not in lf.CARAS_VISIBLES:
        raise ValueError(f"cara_visible tiene que ser una de {lf.CARAS_VISIBLES}, recibí {cara_visible!r}")
    if diagonal not in lf.DIAGONALES:
        raise ValueError(f"diagonal tiene que ser una de {lf.DIAGONALES}, recibí {diagonal!r}")
    if not (boquilla_mm > 0):
        raise ValueError("boquilla_mm tiene que ser mayor que 0")


def _chequear_a1(ancho_mm, alto_mm, profundo_mm):
    """La placa se puede girar sobre la cama, así que se compara el lado MAYOR contra el eje X de
    `bambu_a1.chequear_tamano`. Devuelve (entra_sin_partir, mensaje, aviso o None). No hay partido
    automático en módulos: si no entra, el aviso lo dice."""
    lado_mayor, lado_menor = max(ancho_mm, alto_mm), min(ancho_mm, alto_mm)
    entra, mensaje = bambu_a1.chequear_tamano(lado_mayor, lado_menor, profundo_mm, nombre="litofanía")
    ax, ay, az = bambu_a1.VOLUMEN_MM
    if lado_mayor > ax or profundo_mm > az:                      # (el lado menor <= el mayor <= 256: no puede sobrar solo)
        aviso = (f"{mensaje} La litofanía todavía no se parte en módulos: achicá la placa "
                 f"(el lado mayor máximo es {ax} mm).")
    elif not entra:
        aviso = (f"{mensaje} La litofanía todavía no se parte en módulos: conviene achicar la placa "
                 f"para no pelear con el borde de la cama.")
    else:
        aviso = None
    return bool(entra), mensaje, aviso


def caras_de_la_placa(ancho_px, alto_px):
    """Triángulos de la malla de L3 para un mapa de `ancho_px` x `alto_px`, sin armarla: 2 por celda del frente,
    2 por tramo del perímetro en las paredes y 1 por tramo en el abanico de la trasera."""
    perimetro = 2 * (ancho_px - 1) + 2 * (alto_px - 1)
    return 2 * (ancho_px - 1) * (alto_px - 1) + 3 * perimetro


def stl_mb_de_la_placa(caras):
    """Peso en MB del STL binario de una malla de `caras` triángulos."""
    return (BYTES_CABECERA_STL + lf.BYTES_POR_TRIANGULO_STL * caras) / 1e6


def avisos_y_notas(mapa_brillo, mapa_grosor, cara_visible="relieve", boquilla_mm=BOQUILLA_DEFAULT_MM,
                   primera_capa_mm=lf.PRIMERA_CAPA_DEFAULT, caras=None, stl_mb=None):
    """Los avisos, las notas y el chequeo de la A1 de una litofanía, a partir de los mapas de L1 y L2: no hace
    falta armar la malla ni exportar nada, así que la página puede llamarla en cada cambio de parámetros.
    `caras` y `stl_mb` (los reales de la malla y del archivo, si ya existen) se estiman de la grilla si no se
    pasan. Devuelve `{"avisos", "info", "entra_a1", "mensaje_a1"}`; `generar()` usa esta misma función."""
    if caras is None:
        caras = caras_de_la_placa(mapa_grosor.ancho_px, mapa_grosor.alto_px)
    if stl_mb is None:
        stl_mb = stl_mb_de_la_placa(caras)
    capa_mm, grosor_min = mapa_grosor.capa_mm, mapa_grosor.grosor_min
    ancho_final, alto_final, profundo_final = mapa_grosor.ancho_mm, mapa_grosor.alto_mm, float(mapa_grosor.grosor.max())
    entra_a1, mensaje_a1, aviso_a1 = _chequear_a1(ancho_final, alto_final, profundo_final)

    # --- avisos: primero lo que impide o arriesga imprimir, después la calidad, al final lo que dicen L1 y L2 ---
    avisos = []
    if aviso_a1:
        avisos.append(aviso_a1)
    grosor_fino = mapa_grosor.grosor_min_efectivo
    if grosor_fino < GROSOR_FRAGIL_MM - 1e-9:
        avisos.append(f"La zona más fina de la placa queda en {grosor_fino:.2f} mm (menos de {GROSOR_FRAGIL_MM:g} mm): "
                      f"es muy frágil y puede romperse o quedar con agujeros. Subí grosor_min.")
    if capa_mm is None and grosor_min < primera_capa_mm - 1e-9:
        avisos.append(f"grosor_min ({grosor_min:g} mm) es menor que la primera capa ({primera_capa_mm:g} mm): "
                      f"lo más fino va a salir de {primera_capa_mm:g} mm.")
    if stl_mb > lf.PESO_STL_AVISO_MB:
        avisos.append(f"La malla es pesada: el STL pesa {stl_mb:.0f} MB ({caras / 1e6:.1f} millones de "
                      f"triángulos). Puede costar abrirlo y rebanarlo; bajá px_por_mm o achicá la placa.")
    px_util = _px_por_mm_util(boquilla_mm)
    if mapa_brillo.px_por_mm > px_util * TOLERANCIA_RESOLUCION:
        avisos.append(f"La resolución ({mapa_brillo.px_por_mm:.1f} px/mm) supera lo que imprime una boquilla de "
                      f"{boquilla_mm:g} mm (~{px_util:g} px/mm): el archivo pesa más y el detalle extra no se ve. "
                      f"Con {px_util:g} px/mm o menos queda igual.")
    avisos.extend(a for a in mapa_brillo.avisos if "pesada" not in a)    # el "pesada" de L1 es una estimación: arriba va el real
    avisos.extend(mapa_grosor.avisos)

    info = [
        f"Placa de {ancho_final:.1f} x {alto_final:.1f} mm, grosor de {mapa_grosor.grosor_min_efectivo:.2f} a "
        f"{mapa_grosor.grosor_max_efectivo:.2f} mm; mapa de {mapa_grosor.ancho_px}x{mapa_grosor.alto_px} px a "
        f"{mapa_grosor.px_por_mm:.1f} px/mm.",
        f"STL de {stl_mb:.1f} MB con {caras:,} triángulos.".replace(",", "."),
        "Se imprime acostada: la cara lisa contra la cama y el relieve hacia arriba. Para imprimirla parada, "
        "girala 90° en el laminador.",
        ("La foto se lee derecha mirando la cara con relieve." if cara_visible == "relieve"
         else "La foto se lee derecha mirando la cara lisa (la del lado de la cama)."),
        f"La luz mínima ({mapa_grosor.luz_minima * 100:g} %) es una suposición del plástico: hasta calibrar con "
        f"una placa de prueba, el contraste real puede variar.",
    ]
    return {"avisos": avisos, "info": info, "entra_a1": entra_a1, "mensaje_a1": mensaje_a1}


def construir_mapas(ruta_imagen, ancho_mm, alto_mm=None, px_por_mm=lf.PX_POR_MM_DEFAULT,
                    grosor_min=lf.GROSOR_MIN_DEFAULT, grosor_max=lf.GROSOR_MAX_DEFAULT,
                    luz_minima=lf.LUZ_MINIMA_DEFAULT, compensar=True, invertir=False,
                    capa_mm=None, primera_capa_mm=lf.PRIMERA_CAPA_DEFAULT,
                    desplazamiento=(0.0, 0.0), brillo=0.0, contraste=1.0, gamma=1.0,
                    auto_niveles=False, realce_local=False, suavizado_mm=0.0):
    """La primera mitad de `generar()`: imagen -> `MapaBrillo` (L1) -> `MapaGrosor` (L2), sin armar la malla.
    Devuelve `(mapa_brillo, mapa_grosor, tiempos)`. La página de Streamlit la usa para la simulación en vivo, así
    que lo que se ve es exactamente lo que `generar()` va a imprimir. Un archivo inválido da `ValueError`."""
    tiempos = {}
    try:
        t0 = time.perf_counter()
        mapa_brillo = lf.imagen_a_mapa_brillo(
            ruta_imagen, ancho_mm, alto_mm, px_por_mm=px_por_mm, desplazamiento=desplazamiento,
            brillo=brillo, contraste=contraste, gamma=gamma, auto_niveles=auto_niveles,
            realce_local=realce_local, suavizado_mm=suavizado_mm, invertir=invertir)
        tiempos["imagen_a_brillo"] = time.perf_counter() - t0

        t0 = time.perf_counter()
        mapa_grosor = lf.brillo_a_grosor(
            mapa_brillo, grosor_min=grosor_min, grosor_max=grosor_max, luz_minima=luz_minima,
            compensar=compensar, capa_mm=capa_mm, primera_capa_mm=primera_capa_mm)
        tiempos["brillo_a_grosor"] = time.perf_counter() - t0
    except ValidationError as e:
        raise ValueError(str(e)) from e
    return mapa_brillo, mapa_grosor, tiempos


def generar(ruta_imagen, ancho_mm=100.0, alto_mm=None, px_por_mm=lf.PX_POR_MM_DEFAULT,
            grosor_min=lf.GROSOR_MIN_DEFAULT, grosor_max=lf.GROSOR_MAX_DEFAULT,
            luz_minima=lf.LUZ_MINIMA_DEFAULT, compensar=True,
            invertir=False, cara_visible="relieve",
            capa_mm=None, primera_capa_mm=lf.PRIMERA_CAPA_DEFAULT,
            desplazamiento=(0.0, 0.0), brillo=0.0, contraste=1.0, gamma=1.0,
            auto_niveles=False, realce_local=False, suavizado_mm=0.0, diagonal="adaptativa",
            boquilla_mm=BOQUILLA_DEFAULT_MM, verificar=True,
            carpeta_salida=CARPETA_SALIDA, prefijo=None):
    """Imagen -> STL de la litofanía. Devuelve un dict (ver la cabecera del módulo).

    Los parámetros de imagen, grosor, capa y malla se pasan tal cual a L1, L2 y L3 (ver sus docstrings en
    core/litofania.py). Lo propio de acá: `boquilla_mm` (para avisar si la resolución pedida no se
    aprovecha), `verificar` (corre `lf.verificar_malla`, ~2,7 s a 800x1000 px; se puede apagar) y
    `prefijo` del nombre del archivo (`{prefijo}_litofania.stl`; por defecto, el nombre de la imagen).

    Falla con `FileNotFoundError` si la imagen no existe y con `ValueError` si la imagen no sirve o un
    parámetro no tiene sentido."""
    _validar_parametros(ruta_imagen, cara_visible, diagonal, boquilla_mm)

    mapa_brillo, mapa_grosor, tiempos = construir_mapas(
        ruta_imagen, ancho_mm, alto_mm, px_por_mm=px_por_mm, grosor_min=grosor_min, grosor_max=grosor_max,
        luz_minima=luz_minima, compensar=compensar, invertir=invertir, capa_mm=capa_mm,
        primera_capa_mm=primera_capa_mm, desplazamiento=desplazamiento, brillo=brillo, contraste=contraste,
        gamma=gamma, auto_niveles=auto_niveles, realce_local=realce_local, suavizado_mm=suavizado_mm)

    t0 = time.perf_counter()
    malla = lf.malla_desde_grosor(mapa_grosor, cara_visible=cara_visible, diagonal=diagonal)
    tiempos["grosor_a_malla"] = time.perf_counter() - t0

    verificacion = None
    if verificar:
        t0 = time.perf_counter()
        verificacion = lf.verificar_malla(malla)
        tiempos["verificacion"] = time.perf_counter() - t0
        watertight = bool(verificacion["watertight"])
    else:
        watertight = bool(malla.is_watertight)

    t0 = time.perf_counter()
    os.makedirs(carpeta_salida, exist_ok=True)
    base = pieza.nombre_archivo(prefijo if prefijo else os.path.splitext(os.path.basename(ruta_imagen))[0],
                                default="litofania")
    ruta_stl = os.path.join(carpeta_salida, f"{base}_litofania.stl")
    malla.export(ruta_stl)
    tiempos["exportacion"] = time.perf_counter() - t0
    stl_mb = os.path.getsize(ruta_stl) / 1e6

    (minx, miny, minz), (maxx, maxy, maxz) = malla.bounds
    ancho_final, alto_final, profundo_final = float(maxx - minx), float(maxy - miny), float(maxz - minz)
    analisis = avisos_y_notas(mapa_brillo, mapa_grosor, cara_visible=cara_visible, boquilla_mm=boquilla_mm,
                              primera_capa_mm=primera_capa_mm, caras=len(malla.faces), stl_mb=stl_mb)

    return {
        "ruta_stl": ruta_stl,
        "ancho_mm": ancho_final, "alto_mm": alto_final, "profundidad_mm": profundo_final,
        "vertices": len(malla.vertices), "caras": len(malla.faces),
        "watertight": watertight,
        "info": analisis["info"], "avisos": analisis["avisos"],
        "entra_a1": analisis["entra_a1"], "mensaje_a1": analisis["mensaje_a1"],
        "ancho_px": mapa_grosor.ancho_px, "alto_px": mapa_grosor.alto_px, "px_por_mm": mapa_grosor.px_por_mm,
        "grosor_min": mapa_grosor.grosor_min_efectivo, "grosor_max": mapa_grosor.grosor_max_efectivo,
        "niveles": mapa_grosor.niveles, "luz_minima": mapa_grosor.luz_minima,
        "media_luz_mm": mapa_grosor.media_luz_mm,
        "stl_mb": stl_mb,
        "verificacion": verificacion,
        "tiempos": tiempos,
        "mapa_brillo": mapa_brillo, "mapa_grosor": mapa_grosor,
    }


def ejecutar():
    from core import ui

    print(f"\n{NOMBRE}")
    print("  Convierte una imagen en una placa que, a contraluz, se ve como la foto.")

    ruta_imagen = ui.pedir_texto("Ruta a la imagen (PNG/JPG)", "")
    if not ruta_imagen or not os.path.exists(ruta_imagen):
        print(f"  ERROR: no encuentro la imagen: {ruta_imagen!r}")
        return

    ancho_mm = ui.pedir_float("Ancho de la placa (mm)", 100.0)
    px_por_mm = ui.pedir_float("Resolución (píxeles por mm; 4 es lo que aprovecha una boquilla de 0,4)",
                               lf.PX_POR_MM_DEFAULT)
    grosor_min = ui.pedir_float("Grosor de lo más claro (mm)", lf.GROSOR_MIN_DEFAULT)
    grosor_max = ui.pedir_float("Grosor de lo más oscuro (mm)", lf.GROSOR_MAX_DEFAULT)
    luz_pct = ui.pedir_float("Luz que deja pasar lo más grueso, en % de lo más fino", lf.LUZ_MINIMA_DEFAULT * 100)
    invertir = ui.pedir_si_no("¿Invertir la imagen (negativo)?", default=False)
    cara_visible = ui.pedir_opcion("¿Qué cara se mira?", list(lf.CARAS_VISIBLES), "relieve")
    capa = ui.pedir_float("Altura de capa (mm; 0 = sin ajustar a capas)", 0.0)

    print(f"\n  » {ruta_imagen}  {ancho_mm:g} mm de ancho  grosor {grosor_min:g}-{grosor_max:g} mm")
    print("  (armando el mapa y la malla, puede tardar unos segundos...)")

    try:
        r = generar(
            ruta_imagen, ancho_mm=ancho_mm, px_por_mm=px_por_mm, grosor_min=grosor_min, grosor_max=grosor_max,
            luz_minima=luz_pct / 100.0, invertir=invertir, cara_visible=cara_visible,
            capa_mm=capa if capa > 0 else None, carpeta_salida=CARPETA_SALIDA,
        )
    except (FileNotFoundError, ValueError) as e:
        print(f"  ERROR: {e}")
        return

    print(f"  tamaño ~ {r['ancho_mm']:.0f} x {r['alto_mm']:.0f} x {r['profundidad_mm']:.1f} mm")
    for nota in r["info"]:
        print(f"  · {nota}")
    for aviso in r["avisos"]:
        print(f"  ⚠ {aviso}")
    print(f"  ✓ STL -> {r['ruta_stl']}  ({r['vertices']} vért., watertight={r['watertight']})")
    print(f"  {'✓' if r['entra_a1'] else '⚠'} {r['mensaje_a1']}")
    print()
