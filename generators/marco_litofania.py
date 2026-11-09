#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generators/marco_litofania.py
--------------------------------
L8: el marco de la litofanía. Imagen -> DOS STL que se encastran: la PLACA (la litofanía con una banda opaca
alrededor) y el MARCO (borde con una ventana del tamaño exacto de la imagen y un bolsillo atrás donde entra la
placa con holgura). La geometría está en `core/litofania_marco.py`; ver su cabecera.

Como `generators/litofania.py`, solo orquesta lo que ya existe: `construir_mapas` de L4 (imagen -> mapas de brillo y
grosor, con sus mismos avisos de imagen y grosor), la grilla con banda, `malla_desde_grilla_grosor` de L3 para la
placa y el marco de `core/litofania_marco.py`. No toca la litofanía de L4. No pregunta ni imprime nada en `generar()`.

El marco va en un filamento OPACO (uno translúcido filtra luz por los costados) y la placa en el translúcido. Atrás
no cierra nada: lo cierra y lo fija la cámara de luz (L9); mientras tanto la placa se sostiene por la ceja y la
fricción del encastre.

Contrato de resultado igual que el resto del proyecto (`ruta_stl`, `ancho_mm`, `alto_mm`, `profundidad_mm`,
`vertices`, `caras`, `watertight`, `info`, `avisos`, `entra_a1`, `mensaje_a1`): `ruta_stl` es la de la placa, y
las medidas son las del MARCO, que es la pieza más grande. Además `ruta_stl_placa`, `ruta_stl_marco` y los datos de
cada pieza. Los errores son `FileNotFoundError` / `ValueError`.
"""

import os
import time

from core import bambu_a1, litofania as lf, litofania_marco as marco, pieza
from generators import litofania as gen_l4

NOMBRE = "Litofanía: marco"
DESCRIPCION = ("Marco opaco con ventana del tamaño de la imagen + placa de litofanía que encastra con holgura "
               "(dos STL, watertight).")

CARPETA_SALIDA = gen_l4.CARPETA_SALIDA
SEPARACION_EN_CAMA_MM = 10.0       # entre las dos piezas si se imprimen juntas


def _chequear_pieza(nombre, ancho_mm, alto_mm, profundo_mm):
    """La pieza se puede girar sobre la cama: se compara el lado MAYOR contra el eje X de
    `bambu_a1.chequear_tamano`. Devuelve (entra, mensaje)."""
    entra, mensaje = bambu_a1.chequear_tamano(max(ancho_mm, alto_mm), min(ancho_mm, alto_mm), profundo_mm, nombre=nombre)
    return bool(entra), mensaje


def entran_juntas_en_la_cama(dim_a, dim_b, separacion=SEPARACION_EN_CAMA_MM):
    """¿Caben las dos piezas (cada una `(ancho, alto)`, sin girarlas) en la cama de la A1, una al lado de la otra
    en cualquiera de los dos ejes? Es solo informativo: se pueden imprimir en dos trabajos."""
    ax, ay, _ = bambu_a1.VOLUMEN_MM
    (wa, ha), (wb, hb) = dim_a, dim_b
    en_x = wa + separacion + wb <= ax and max(ha, hb) <= ay
    en_y = ha + separacion + hb <= ay and max(wa, wb) <= ax
    return bool(en_x or en_y)


def guia_de_encastre(geo):
    """Cómo imprimir y armar las dos piezas, en pasos."""
    return [
        "Imprimí el MARCO en un filamento OPACO (uno translúcido filtra luz por los costados y baja el contraste) y la "
        "PLACA en el translúcido, cada una por separado.",
        "Las dos salen sin soportes: la placa con el dorso liso contra la cama (como la litofanía normal) y el marco con la "
        "ceja contra la cama y el bolsillo hacia arriba, tal como se exportan.",
        f"La placa entra al marco DESDE ATRÁS, con el relieve hacia la ceja: queda al ras del dorso y la ceja de "
        f"{geo.grosor_ceja:g} mm apoya sobre su banda opaca de {geo.apoyo + geo.holgura:.2f} mm.",
        f"Hay {geo.holgura:g} mm de holgura por lado (el bolsillo mide {geo.ancho_placa + 2 * geo.holgura:.2f} x "
        f"{geo.alto_placa + 2 * geo.holgura:.2f} mm). Por ese juego la placa se puede correr hasta {geo.holgura:g} mm hacia un "
        f"lado, y entonces la ceja tapa hasta {geo.holgura:g} mm de borde de la foto de ese lado: centrala antes de fijarla. "
        f"Si queda floja o dura, probá otra holgura (la impresora y el filamento cambian el ajuste real).",
        "Atrás no cierra nada: la placa se sostiene por la ceja y la fricción hasta que la cámara de luz la cierre y la fije.",
    ]


def generar(ruta_imagen, ancho_mm=100.0, alto_mm=None, px_por_mm=lf.PX_POR_MM_DEFAULT,
            grosor_min=lf.GROSOR_MIN_DEFAULT, grosor_max=lf.GROSOR_MAX_DEFAULT,
            luz_minima=lf.LUZ_MINIMA_DEFAULT, compensar=True,
            invertir=False, cara_visible="relieve",
            capa_mm=None, primera_capa_mm=lf.PRIMERA_CAPA_DEFAULT,
            desplazamiento=(0.0, 0.0), brillo=0.0, contraste=1.0, gamma=1.0,
            auto_niveles=False, realce_local=False, suavizado_mm=0.0, diagonal="adaptativa",
            boquilla_mm=gen_l4.BOQUILLA_DEFAULT_MM, verificar=True,
            ancho_borde=marco.ANCHO_BORDE_DEFAULT, grosor_ceja=marco.GROSOR_CEJA_DEFAULT,
            margen_encastre=marco.MARGEN_ENCASTRE_DEFAULT, holgura=marco.HOLGURA_DEFAULT,
            carpeta_salida=CARPETA_SALIDA, prefijo=None):
    """Imagen -> los STL de la placa y del marco. Devuelve un dict (ver la cabecera del módulo).

    Los parámetros de imagen, grosor, capa y malla son los de `generators.litofania.generar` (se pasan a L1, L2 y
    L3 tal cual). Lo propio: `ancho_borde`, `grosor_ceja`, `margen_encastre` (banda opaca de la placa) y `holgura`
    (por lado), ver `core/litofania_marco.py`. Escribe `{prefijo}_placa.stl` y `{prefijo}_marco.stl` (por defecto,
    el nombre de la imagen). Falla con `FileNotFoundError` si la imagen no existe y con `ValueError` si la imagen no
    sirve o un parámetro no tiene sentido: en ese caso no escribe nada."""
    gen_l4._validar_parametros(ruta_imagen, cara_visible, diagonal, boquilla_mm)

    mapa_brillo, mapa_grosor, tiempos = gen_l4.construir_mapas(
        ruta_imagen, ancho_mm, alto_mm, px_por_mm=px_por_mm, grosor_min=grosor_min, grosor_max=grosor_max,
        luz_minima=luz_minima, compensar=compensar, invertir=invertir, capa_mm=capa_mm,
        primera_capa_mm=primera_capa_mm, desplazamiento=desplazamiento, brillo=brillo, contraste=contraste,
        gamma=gamma, auto_niveles=auto_niveles, realce_local=realce_local, suavizado_mm=suavizado_mm)

    t0 = time.perf_counter()
    grilla, banda_x, banda_y = marco.grilla_con_banda(mapa_grosor, margen_encastre)
    geo = marco.geometria_del_marco(mapa_grosor.ancho_mm, mapa_grosor.alto_mm, banda_x, banda_y, float(grilla.max()),
                                    ancho_borde=ancho_borde, grosor_ceja=grosor_ceja, holgura=holgura)
    tiempos["geometria"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    malla_placa = lf.malla_desde_grilla_grosor(grilla, geo.ancho_placa, geo.alto_placa,
                                               cara_visible=cara_visible, diagonal=diagonal)
    malla_marco = marco.malla_del_marco(geo)
    marco_impresion = marco.marco_para_imprimir(malla_marco, geo)
    tiempos["mallas"] = time.perf_counter() - t0

    verificacion_placa = verificacion_marco = None
    if verificar:
        t0 = time.perf_counter()
        verificacion_placa, verificacion_marco = lf.verificar_malla(malla_placa), lf.verificar_malla(marco_impresion)
        tiempos["verificacion"] = time.perf_counter() - t0
        watertight_placa, watertight_marco = bool(verificacion_placa["watertight"]), bool(verificacion_marco["watertight"])
    else:
        watertight_placa, watertight_marco = bool(malla_placa.is_watertight), bool(marco_impresion.is_watertight)

    t0 = time.perf_counter()
    os.makedirs(carpeta_salida, exist_ok=True)
    base = pieza.nombre_archivo(prefijo if prefijo else os.path.splitext(os.path.basename(ruta_imagen))[0],
                                default="litofania")
    ruta_placa = os.path.join(carpeta_salida, f"{base}_placa.stl")
    ruta_marco = os.path.join(carpeta_salida, f"{base}_marco.stl")
    malla_placa.export(ruta_placa)
    marco_impresion.export(ruta_marco)
    tiempos["exportacion"] = time.perf_counter() - t0
    stl_mb_placa, stl_mb_marco = os.path.getsize(ruta_placa) / 1e6, os.path.getsize(ruta_marco) / 1e6

    profundo_placa = float(malla_placa.bounds[1][2] - malla_placa.bounds[0][2])
    ancho_placa, alto_placa = float(geo.ancho_placa), float(geo.alto_placa)
    ancho_marco, alto_marco, profundo_marco = float(geo.ancho_marco), float(geo.alto_marco), float(geo.profundidad_total)
    entra_placa, mensaje_placa = _chequear_pieza("placa", ancho_placa, alto_placa, profundo_placa)
    entra_marco, mensaje_marco = _chequear_pieza("marco", ancho_marco, alto_marco, profundo_marco)
    entra_a1 = entra_placa and entra_marco
    mensaje_a1 = f"{mensaje_marco} {mensaje_placa}"
    juntas = entran_juntas_en_la_cama((ancho_marco, alto_marco), (ancho_placa, alto_placa))

    # los avisos de imagen y grosor son los de L4; su chequeo de la A1 era para la placa sin marco y acá lo reemplazan los de abajo
    analisis = gen_l4.avisos_y_notas(mapa_brillo, mapa_grosor, cara_visible=cara_visible, boquilla_mm=boquilla_mm,
                                     primera_capa_mm=primera_capa_mm, caras=len(malla_placa.faces), stl_mb=stl_mb_placa)
    avisos = [a for a in analisis["avisos"] if not a.startswith(analisis["mensaje_a1"])]
    for entra, mensaje, nombre in ((entra_marco, mensaje_marco, "marco"), (entra_placa, mensaje_placa, "placa")):
        if not entra:
            avisos.insert(0, f"{mensaje} Achicá la litofanía o el borde: el marco todavía no se parte en módulos.")

    info = [
        f"MARCO de {ancho_marco:.1f} x {alto_marco:.1f} x {profundo_marco:.1f} mm (borde de {geo.ancho_borde:g} mm, ceja de "
        f"{geo.grosor_ceja:g} mm); ventana de {geo.ancho_imagen:.1f} x {geo.alto_imagen:.1f} mm, el tamaño de la imagen.",
        f"PLACA de {ancho_placa:.1f} x {alto_placa:.1f} x {profundo_placa:.1f} mm (la imagen más una banda opaca de "
        f"{geo.banda_x:.2f} x {geo.banda_y:.2f} mm); bolsillo del marco con {geo.holgura:g} mm de holgura por lado.",
        f"STL de la placa: {stl_mb_placa:.1f} MB ({len(malla_placa.faces):,} triángulos); del marco: {stl_mb_marco:.2f} MB "
        f"({len(marco_impresion.faces):,} triángulos).".replace(",", "."),
        ("Entran las dos piezas juntas en la cama de la A1." if juntas else
         "No entran las dos juntas en la cama de la A1: imprimilas en dos trabajos."),
        ("La foto se lee derecha mirando la cara con relieve, que queda del lado de la ceja." if cara_visible == "relieve"
         else "La foto se lee derecha mirando la cara lisa, que queda del lado de la ceja (la placa se coloca dada vuelta)."),
    ] + guia_de_encastre(geo)

    return {
        "ruta_stl": ruta_placa, "ruta_stl_placa": ruta_placa, "ruta_stl_marco": ruta_marco,
        "ancho_mm": ancho_marco, "alto_mm": alto_marco, "profundidad_mm": profundo_marco,
        "vertices": len(malla_placa.vertices) + len(marco_impresion.vertices),
        "caras": len(malla_placa.faces) + len(marco_impresion.faces),
        "watertight": watertight_placa and watertight_marco,
        "watertight_placa": watertight_placa, "watertight_marco": watertight_marco,
        "info": info, "avisos": avisos, "entra_a1": entra_a1, "mensaje_a1": mensaje_a1,
        "entra_placa_a1": entra_placa, "entra_marco_a1": entra_marco, "entran_juntas": juntas,
        "placa": {"ancho_mm": ancho_placa, "alto_mm": alto_placa, "profundidad_mm": profundo_placa,
                  "vertices": len(malla_placa.vertices), "caras": len(malla_placa.faces), "stl_mb": stl_mb_placa,
                  "mensaje_a1": mensaje_placa},
        "marco": {"ancho_mm": ancho_marco, "alto_mm": alto_marco, "profundidad_mm": profundo_marco,
                  "vertices": len(marco_impresion.vertices), "caras": len(marco_impresion.faces), "stl_mb": stl_mb_marco,
                  "mensaje_a1": mensaje_marco},
        "geometria": geo, "banda_x": banda_x, "banda_y": banda_y,
        "ancho_imagen_mm": geo.ancho_imagen, "alto_imagen_mm": geo.alto_imagen,
        "stl_mb": stl_mb_placa + stl_mb_marco,
        "verificacion": {"placa": verificacion_placa, "marco": verificacion_marco} if verificar else None,
        "tiempos": tiempos, "guia": guia_de_encastre(geo),
        "mapa_brillo": mapa_brillo, "mapa_grosor": mapa_grosor,
    }


def ejecutar():
    from core import ui

    print(f"\n{NOMBRE}")
    print("  Convierte una imagen en una placa de litofanía y un marco opaco que la encastra (dos STL).")

    ruta_imagen = ui.pedir_texto("Ruta a la imagen (PNG/JPG)", "")
    if not ruta_imagen or not os.path.exists(ruta_imagen):
        print(f"  ERROR: no encuentro la imagen: {ruta_imagen!r}")
        return

    ancho_mm = ui.pedir_float("Ancho de la imagen (mm)", 100.0)
    px_por_mm = ui.pedir_float("Resolución (píxeles por mm; 4 es lo que aprovecha una boquilla de 0,4)", lf.PX_POR_MM_DEFAULT)
    grosor_min = ui.pedir_float("Grosor de lo más claro (mm)", lf.GROSOR_MIN_DEFAULT)
    grosor_max = ui.pedir_float("Grosor de lo más oscuro (mm)", lf.GROSOR_MAX_DEFAULT)
    luz_pct = ui.pedir_float("Luz que deja pasar lo más grueso, en % de lo más fino", lf.LUZ_MINIMA_DEFAULT * 100)
    invertir = ui.pedir_si_no("¿Invertir la imagen (negativo)?", default=False)
    cara_visible = ui.pedir_opcion("¿Qué cara se mira?", list(lf.CARAS_VISIBLES), "relieve")
    capa = ui.pedir_float("Altura de capa (mm; 0 = sin ajustar a capas)", 0.0)
    ancho_borde = ui.pedir_float("Ancho del borde del marco (mm)", marco.ANCHO_BORDE_DEFAULT)
    grosor_ceja = ui.pedir_float("Grosor de la ceja (mm)", marco.GROSOR_CEJA_DEFAULT)
    margen = ui.pedir_float("Banda opaca de la placa que agarra la ceja (mm)", marco.MARGEN_ENCASTRE_DEFAULT)
    holgura = ui.pedir_float("Holgura del encastre (mm por lado)", marco.HOLGURA_DEFAULT)

    print(f"\n  » {ruta_imagen}  {ancho_mm:g} mm de ancho  borde {ancho_borde:g} mm  holgura {holgura:g} mm")
    print("  (armando las mallas, puede tardar unos segundos...)")

    try:
        r = generar(
            ruta_imagen, ancho_mm=ancho_mm, px_por_mm=px_por_mm, grosor_min=grosor_min, grosor_max=grosor_max,
            luz_minima=luz_pct / 100.0, invertir=invertir, cara_visible=cara_visible,
            capa_mm=capa if capa > 0 else None, ancho_borde=ancho_borde, grosor_ceja=grosor_ceja,
            margen_encastre=margen, holgura=holgura, carpeta_salida=CARPETA_SALIDA,
        )
    except (FileNotFoundError, ValueError) as e:
        print(f"  ERROR: {e}")
        return

    for nota in r["info"]:
        print(f"  · {nota}")
    for aviso in r["avisos"]:
        print(f"  ⚠ {aviso}")
    print(f"  ✓ placa -> {r['ruta_stl_placa']}  (watertight={r['watertight_placa']})")
    print(f"  ✓ marco -> {r['ruta_stl_marco']}  (watertight={r['watertight_marco']})")
    print(f"  {'✓' if r['entra_a1'] else '⚠'} {r['mensaje_a1']}")
    print()
