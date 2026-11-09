#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generators/calibracion_litofania.py
--------------------------------------
L6: placa de calibración de grosores para la litofanía. Una escalera de franjas planas (por defecto 7, de 0,6 a
3,0 mm) con el grosor de cada una grabado debajo, para medir con TU filamento cuánta luz pasa por cada espesor y
sacar el `luz_minima` real (ver `core/litofania_calibracion.py`: ahí está la grilla y `calibrar_luz_minima`).

Como `generators/litofania.py`, este generador solo orquesta: grilla de grosores -> `malla_desde_grilla_grosor`
(L3) -> STL, sin geometría propia, más el chequeo contra la Bambu A1, los avisos y el mismo contrato de resultado
(`ruta_stl`, `ancho_mm`, `alto_mm`, `profundidad_mm`, `vertices`, `caras`, `watertight`, `info`, `avisos`,
`entra_a1`, `mensaje_a1`) con los datos de la placa. No pregunta ni imprime nada en `generar()`; los errores son
`ValueError`.
"""

import os
import time

from core import bambu_a1, litofania as lf, litofania_calibracion as cal, pieza
from generators.litofania import GROSOR_FRAGIL_MM

NOMBRE = "Litofanía: placa de calibración"
DESCRIPCION = ("Escalera de franjas de grosor conocido (con el grosor grabado) para medir cuánta luz deja pasar tu "
               "filamento y calibrar el luz mínimo de la litofanía. STL watertight.")

CARPETA_SALIDA = "output"
PREFIJO_DEFAULT = "placa_calibracion_litofania"


def _chequear_a1(ancho_mm, alto_mm, profundo_mm):
    """La placa se puede girar sobre la cama: se compara el lado MAYOR contra el eje X de
    `bambu_a1.chequear_tamano`. Devuelve (entra, mensaje, aviso o None)."""
    lado_mayor, lado_menor = max(ancho_mm, alto_mm), min(ancho_mm, alto_mm)
    entra, mensaje = bambu_a1.chequear_tamano(lado_mayor, lado_menor, profundo_mm, nombre="placa de calibración")
    aviso = None
    if not entra:
        aviso = (f"{mensaje} Achicá la placa: menos franjas (n_franjas), franjas más angostas o más cortas.")
    return bool(entra), mensaje, aviso


def _tabla_de_prediccion(placa, media_luz_supuesta):
    """Qué luz debería pasar por cada franja, relativa a la más fina (= 100 %), si el filamento tuviera esa media
    luz (L2). Es lo que hay que comparar con la foto. Devuelve (filas, mapa_grosor_o_None)."""
    try:
        mapa = cal.mapa_grosor_de_la_placa(placa, media_luz_supuesta)
    except ValueError:
        return None, None
    luces = lf.luz_transmitida([e["grosor"] for e in placa.escalones], mapa.grosor_min, mapa.grosor_max, mapa.luz_minima)
    return [{"indice": e["indice"], "etiqueta": e["etiqueta"], "grosor": e["grosor"], "luz_pct": float(l * 100.0)}
            for e, l in zip(placa.escalones, luces)], mapa


def guia_de_uso(escalones):
    """Cómo usar la placa, en pasos, para mostrar en consola o en la página."""
    n = len(escalones)
    return [
        "Imprimila con el MISMO filamento, color, temperatura, altura de capa y relleno que vas a usar en la litofanía "
        "(la calibración vale para ese plástico y esas condiciones).",
        "Ponela plana contra la lámpara que vas a usar, en un cuarto a oscuras y sin que se filtre luz por los costados "
        "(los separadores gruesos ayudan).",
        "Sacale una foto de frente con la exposición, el balance de blancos y el ISO BLOQUEADOS (no automáticos), sin flash y "
        "sin reflejos. A ojo no se calibra bien: se lee un gris por franja.",
        f"Con cualquier programa de dibujo, leé el gris (0-255) en el CENTRO de cada una de las {n} franjas, de la más "
        f"fina ({escalones[0]['etiqueta']} mm) a la más gruesa ({escalones[-1]['etiqueta']} mm).",
        "Si la franja más fina sale blanca pura (255) o la más gruesa casi negra, repetí la foto con menos o más "
        "exposición: esas franjas se descartan. Hacen falta al menos 3 útiles.",
        "Pasale los grises a `calibrar_luz_minima` (core/litofania_calibracion.py): da el coeficiente k, el espesor de "
        "media luz y el luz mínimo para el rango de grosores que quieras. Con la misma media luz, un rango más ancho "
        "da un luz mínimo más bajo.",
    ]


def generar(n_franjas=cal.N_FRANJAS_DEFAULT, grosor_min=cal.GROSOR_MIN_DEFAULT, grosor_max=cal.GROSOR_MAX_DEFAULT,
            ancho_franja=cal.ANCHO_FRANJA_DEFAULT, alto_franja=cal.ALTO_FRANJA_DEFAULT,
            separador_mm=cal.SEPARADOR_DEFAULT, borde_mm=cal.BORDE_DEFAULT,
            alto_etiqueta=cal.ALTO_ETIQUETA_DEFAULT, px_por_mm=cal.PX_POR_MM_DEFAULT,
            capa_mm=None, primera_capa_mm=lf.PRIMERA_CAPA_DEFAULT,
            cara_visible="relieve", diagonal="adaptativa", verificar=True, media_luz_supuesta=None,
            carpeta_salida=CARPETA_SALIDA, prefijo=PREFIJO_DEFAULT):
    """Parámetros de la placa -> STL. Devuelve un dict (ver la cabecera del módulo) con además `escalones`
    (grosor real y etiqueta de cada franja), `tabla_prediccion` (luz relativa esperada por franja si el filamento
    tuviera `media_luz_supuesta`; por defecto la de L2 con sus valores por defecto), `mapa_grosor` (la placa como
    `MapaGrosor`, para simularla con L5), `placa` y `guia`. `capa_mm` ajusta los grosores a capas reales.
    Falla con `ValueError` si algún parámetro no tiene sentido."""
    if cara_visible not in lf.CARAS_VISIBLES:
        raise ValueError(f"cara_visible tiene que ser una de {lf.CARAS_VISIBLES}, recibí {cara_visible!r}")
    if diagonal not in lf.DIAGONALES:
        raise ValueError(f"diagonal tiene que ser una de {lf.DIAGONALES}, recibí {diagonal!r}")
    if media_luz_supuesta is None:
        media_luz_supuesta = lf.media_luz_mm(lf.LUZ_MINIMA_DEFAULT, lf.GROSOR_MIN_DEFAULT, lf.GROSOR_MAX_DEFAULT)
    elif not (media_luz_supuesta > 0):
        raise ValueError("media_luz_supuesta tiene que ser mayor que 0")

    tiempos = {}
    t0 = time.perf_counter()
    placa = cal.placa_de_calibracion(
        n_franjas=n_franjas, grosor_min=grosor_min, grosor_max=grosor_max, ancho_franja=ancho_franja,
        alto_franja=alto_franja, separador_mm=separador_mm, borde_mm=borde_mm, alto_etiqueta=alto_etiqueta,
        px_por_mm=px_por_mm, capa_mm=capa_mm, primera_capa_mm=primera_capa_mm)
    tiempos["grilla"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    malla = lf.malla_desde_grilla_grosor(placa.grosor, placa.ancho_mm, placa.alto_mm,
                                         cara_visible=cara_visible, diagonal=diagonal)
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
    base = pieza.nombre_archivo(prefijo, default=PREFIJO_DEFAULT)
    ruta_stl = os.path.join(carpeta_salida, f"{base}.stl")
    malla.export(ruta_stl)
    tiempos["exportacion"] = time.perf_counter() - t0
    stl_mb = os.path.getsize(ruta_stl) / 1e6

    (minx, miny, minz), (maxx, maxy, maxz) = malla.bounds
    ancho_final, alto_final, profundo_final = float(maxx - minx), float(maxy - miny), float(maxz - minz)
    entra_a1, mensaje_a1, aviso_a1 = _chequear_a1(ancho_final, alto_final, profundo_final)

    tabla, mapa_grosor = _tabla_de_prediccion(placa, media_luz_supuesta)

    avisos = []
    if aviso_a1:
        avisos.append(aviso_a1)
    avisos.extend(placa.avisos)
    fino = placa.grosor_digito
    if fino < GROSOR_FRAGIL_MM - 1e-9:
        avisos.append(f"La franja más fina mide {fino:.2f} mm (menos de {GROSOR_FRAGIL_MM:g} mm): es frágil y puede "
                      f"quedar con agujeros; los dígitos grabados hasta ese grosor también.")

    info = [
        f"Placa de {ancho_final:.1f} x {alto_final:.1f} mm con {len(placa.escalones)} franjas de "
        f"{', '.join(e['etiqueta'] for e in placa.escalones)} mm (el grosor de cada franja está grabado debajo de ella).",
        f"Marco y tira de etiquetas de {placa.grosor_marco:.2f} mm; dígitos grabados hasta {placa.grosor_digito:.2f} mm. "
        f"STL de {stl_mb:.1f} MB con {len(malla.faces):,} triángulos.".replace(",", "."),
        ("Los dígitos se leen derechos mirando la cara con relieve." if cara_visible == "relieve"
         else "Los dígitos se leen derechos mirando la cara lisa (la del lado de la cama)."),
    ]
    if capa_mm is None:
        info.append("Sin altura de capa, el laminador redondea cada grosor a sus capas: el grosor impreso puede diferir un "
                    "poco de la etiqueta. Con capa_mm la placa ya usa grosores de capas reales.")
    if tabla:
        info.append("Luz esperada por franja (relativa a la más fina) si tu filamento fuera como el supuesto de L2 "
                    f"(media luz {media_luz_supuesta:.2f} mm): "
                    + ", ".join(f"{f['etiqueta']} mm -> {f['luz_pct']:.0f} %" for f in tabla) + ".")
    else:
        info.append(f"Con una media luz supuesta de {media_luz_supuesta:g} mm la luz mínima cae fuera de lo que admite "
                    f"el generador: no hay tabla de predicción.")
    info.extend(guia_de_uso(placa.escalones))

    return {
        "ruta_stl": ruta_stl,
        "ancho_mm": ancho_final, "alto_mm": alto_final, "profundidad_mm": profundo_final,
        "vertices": len(malla.vertices), "caras": len(malla.faces),
        "watertight": watertight,
        "info": info, "avisos": avisos,
        "entra_a1": entra_a1, "mensaje_a1": mensaje_a1,
        "escalones": placa.escalones,
        "grosores": [e["grosor"] for e in placa.escalones],
        "etiquetas": [e["etiqueta"] for e in placa.escalones],
        "ancho_px": placa.ancho_px, "alto_px": placa.alto_px, "px_por_mm": placa.px_por_mm,
        "stl_mb": stl_mb, "verificacion": verificacion, "tiempos": tiempos,
        "tabla_prediccion": tabla, "media_luz_supuesta": float(media_luz_supuesta),
        "mapa_grosor": mapa_grosor, "placa": placa, "guia": guia_de_uso(placa.escalones),
    }


def _leer_grises(texto, n):
    try:
        valores = [float(v) for v in texto.replace(";", ",").split(",") if v.strip()]
    except ValueError:
        raise ValueError("los grises tienen que ser números separados por comas") from None
    if len(valores) != n:
        raise ValueError(f"escribiste {len(valores)} grises y la placa tiene {n} franjas")
    return valores


def ejecutar():
    from core import ui

    print(f"\n{NOMBRE}")
    print("  Escalera de franjas de grosor conocido para medir la luz que deja pasar tu filamento.")

    n = int(ui.pedir_float("Cantidad de franjas", float(cal.N_FRANJAS_DEFAULT)))
    grosor_min = ui.pedir_float("Grosor de la franja más fina (mm)", cal.GROSOR_MIN_DEFAULT)
    grosor_max = ui.pedir_float("Grosor de la franja más gruesa (mm)", cal.GROSOR_MAX_DEFAULT)
    capa = ui.pedir_float("Altura de capa (mm; 0 = sin ajustar a capas)", 0.0)

    try:
        r = generar(n_franjas=n, grosor_min=grosor_min, grosor_max=grosor_max,
                    capa_mm=capa if capa > 0 else None, carpeta_salida=CARPETA_SALIDA)
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

    texto = ui.pedir_texto("\n  Si ya la imprimiste y sacaste la foto, escribí el gris (0-255) de cada franja separado por "
                           "comas (Enter para salir)", "")
    if texto.strip():
        try:
            c = cal.calibrar_luz_minima(r["grosores"], _leer_grises(texto, len(r["grosores"])), grosor_min, grosor_max)
        except ValueError as e:
            print(f"  ERROR: {e}")
            return
        print(f"  k = {c.k:.3f} 1/mm  ·  media luz = {c.media_luz_mm:.3f} mm  ·  R² = {c.r2:.3f}")
        print(f"  luz mínima para {grosor_min:g}-{grosor_max:g} mm: {c.luz_minima * 100:.2f} %")
        for aviso in c.avisos:
            print(f"  ⚠ {aviso}")
    print()
