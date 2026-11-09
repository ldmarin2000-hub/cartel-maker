#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generators/camara_litofania.py
--------------------------------
L9: la cámara de luz de la litofanía. Imagen -> CUATRO STL que se arman: la PLACA y el MARCO de L8 (el marco con
cuatro clavijas en el dorso), la CÁMARA (caja trasera con una abertura que apoya sobre la banda de la placa, agujero
para el cable y agujeros para las clavijas) y la TAPA. La geometría está en `core/litofania_camara.py` y el modelo de
la luz en `core/litofania_luz.py`; ver sus cabeceras.

Orquesta lo que ya existe: llama a `marco_litofania.generar` (L8 -> L4 -> L1-L3) pidiéndole las clavijas, así que la
placa y el marco salen de la misma imagen, con los mismos avisos y sin tocar nada de L1-L5 ni de L8. No pregunta ni
imprime nada en `generar()`.

Contrato de resultado igual que L8 (`ruta_stl` es la de la placa; `ancho_mm`/`alto_mm` son los del MARCO, que manda
en la huella, y `profundidad_mm` la de la pieza más alta, la cámara), más `ruta_stl_camara`, `ruta_stl_tapa`, los datos de
cada pieza y de la luz. Los errores son `FileNotFoundError` / `ValueError` y en ese caso no se escribe nada.
"""

import os
import time

import trimesh

from core import bambu_a1, litofania as lf, litofania_camara as cam_, litofania_luz as luz, litofania_marco as marco, pieza
from generators import litofania as gen_l4, marco_litofania as gen_l8

NOMBRE = "Litofanía: cámara de luz"
DESCRIPCION = ("Cámara trasera con tira de LED, tapa y clavijas en el marco que la fijan por detrás de la litofanía "
               "(cuatro STL, watertight).")

CARPETA_SALIDA = gen_l4.CARPETA_SALIDA
NOMBRES_DE_PIEZA = {"placa": "placa", "marco": "marco", "camara": "cámara", "tapa": "tapa"}


def guia_de_armado(c, u, sep_max, dist_min, avisos_carcasa):
    """Cómo imprimir y armar las cuatro piezas, y las cosas que el modelo no puede verificar. `c`: `Camara`; `u`:
    `UniformidadLuz`; `sep_max`: separación máxima entre filas de tira (mm; `None` si a esa distancia no hay ninguna que sirva); `dist_min`: distancia mínima de la tira a la placa
    (mm); `avisos_carcasa`: los de `armar_carcasa_hueca`."""
    geo = c.geo
    pasos = [
        "Las cuatro salen sin soportes. Marco: la ceja contra la cama (y las clavijas hacia arriba); placa: el dorso liso contra la "
        "cama; cámara: el frente (la brida) contra la cama y el dorso abierto hacia arriba; tapa: plana. El marco y la cámara en "
        "filamento OPACO (uno claro o fino filtra luz: las paredes blancas finas dejan pasar luz, forralas con cinta negra si pasa) y "
        "solo la placa en el translúcido.",
        f"Armado, de adelante hacia atrás: marco con la ceja hacia abajo, la placa dentro del bolsillo con el relieve hacia la ceja, y "
        f"la cámara encima con las {len(c.clavijas)} clavijas del marco en los agujeros de la brida. La placa queda firme entre la "
        f"ceja y la brida: la brida cubre {c.cobertura_banda:.2f} mm de su banda opaca aun con la placa corrida hasta tocar el bolsillo.",
        "El apilamiento está calculado sin juego en z (ceja contra la cara alta de la banda, brida contra el dorso de la placa). En la "
        "impresora la tolerancia real es del orden de ±0,1 mm por cara y eso no se puede verificar desde acá: si queda floja, "
        "un poco de cinta fina entre la brida y la placa la afirma; si no entra, lijá la brida.",
        f"La tira de LED se pega por DENTRO de la tapa (cavidad de {c.interior[0]:.0f} x {c.interior[1]:.0f} mm), con los LED a "
        f"{c.distancia_led:g} mm de la placa. Para que no se vean puntos: "
        + (f"filas de tira separadas {sep_max:.0f} mm como máximo (con un LED cada {u.paso_led:g} mm) "
           if sep_max is not None else
           f"a esta distancia no alcanza con juntar las filas (con un LED cada {u.paso_led:g} mm): alejá la tira o usá una con más LED por metro; ")
        + f"y no acerques la tira a menos de {dist_min:.0f} mm.",
        f"El cable sale por el lado {c.lado_cable} (agujero de Ø{c.cable_diam:g} mm a media profundidad). La tapa entra suelta en el "
        f"rebaje: fijala con cinta o una gota de pegamento (no tiene lengüetas).",
        cam_.LUZ_RIZADO_NOTA,
    ]
    return pasos + list(avisos_carcasa)


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
            distancia_led=cam_.DISTANCIA_LED_DEFAULT, grosor_tira=cam_.GROSOR_TIRA_DEFAULT,
            paso_led=luz.PASO_LED_DEFAULT, separacion_filas=luz.PASO_LED_DEFAULT,
            pared_camara=cam_.PARED_CAMARA_DEFAULT, espesor_brida=cam_.ESPESOR_BRIDA_DEFAULT,
            soporte_tapa=cam_.SOPORTE_TAPA_DEFAULT, tapa_espesor=cam_.TAPA_ESPESOR_DEFAULT,
            holgura_tapa=cam_.HOLGURA_TAPA_DEFAULT, margen_abertura=cam_.MARGEN_ABERTURA_DEFAULT,
            lado_cable=cam_.LADO_CABLE_DEFAULT, cable_diam=cam_.CABLE_DIAM_DEFAULT,
            clavija_diam=cam_.CLAVIJA_DIAM_DEFAULT, clavija_largo=cam_.CLAVIJA_LARGO_DEFAULT,
            juego_clavija=cam_.JUEGO_CLAVIJA_DEFAULT,
            carpeta_salida=CARPETA_SALIDA, prefijo=None):
    """Imagen -> los STL de la placa, el marco (con clavijas), la cámara y la tapa. Devuelve un dict (ver la cabecera
    del módulo).

    Los parámetros de imagen, grosor, capa, malla y marco son los de `generators.marco_litofania.generar`. Lo propio:
    `distancia_led` (mm de los LED a la placa; la profundidad de la cámara sale de ahí), `grosor_tira`, `paso_led` y
    `separacion_filas` (de la tira, solo para el modelo de la luz), `pared_camara`, `espesor_brida`, `soporte_tapa`,
    `tapa_espesor`, `holgura_tapa`, `margen_abertura`, `lado_cable` (uno de `core.litofania_camara.LADOS_CABLE`, visto
    de frente a la foto), `cable_diam` y las clavijas (`clavija_diam`, `clavija_largo`, `juego_clavija`).
    Escribe `{prefijo}_placa.stl`, `_marco.stl`, `_camara.stl` y `_tapa.stl`. Falla con `FileNotFoundError` si la imagen
    no existe y con `ValueError` si la imagen no sirve o un parámetro no tiene sentido: en ese caso no escribe nada."""
    if not (paso_led > 0 and separacion_filas > 0):
        raise ValueError("paso_led y separacion_filas tienen que ser mayores que 0")
    armado = {}

    def _clavijas(geo):
        # corre dentro de L8 antes de escribir nada: acá se valida la cámara y se arman sus mallas
        c = cam_.geometria_de_la_camara(
            geo, distancia_led=distancia_led, grosor_tira=grosor_tira, pared=pared_camara, espesor_brida=espesor_brida,
            soporte_tapa=soporte_tapa, tapa_espesor=tapa_espesor, holgura_tapa=holgura_tapa, margen_abertura=margen_abertura,
            lado_cable=lado_cable, cable_diam=cable_diam, clavija_diam=clavija_diam, clavija_largo=clavija_largo,
            juego_clavija=juego_clavija)
        t0 = time.perf_counter()
        armado["camara"], armado["avisos_carcasa"] = cam_.malla_y_avisos_de_la_camara(c)
        armado["tapa"] = cam_.malla_de_la_tapa(c)
        armado["tiempo"] = time.perf_counter() - t0
        armado["c"] = c
        return cam_.clavijas_del_marco(geo, clavija_diam, clavija_largo, juego_clavija)

    r = gen_l8.generar(
        ruta_imagen, ancho_mm=ancho_mm, alto_mm=alto_mm, px_por_mm=px_por_mm, grosor_min=grosor_min, grosor_max=grosor_max,
        luz_minima=luz_minima, compensar=compensar, invertir=invertir, cara_visible=cara_visible, capa_mm=capa_mm,
        primera_capa_mm=primera_capa_mm, desplazamiento=desplazamiento, brillo=brillo, contraste=contraste, gamma=gamma,
        auto_niveles=auto_niveles, realce_local=realce_local, suavizado_mm=suavizado_mm, diagonal=diagonal,
        boquilla_mm=boquilla_mm, verificar=verificar, ancho_borde=ancho_borde, grosor_ceja=grosor_ceja,
        margen_encastre=margen_encastre, holgura=holgura, carpeta_salida=carpeta_salida, prefijo=prefijo,
        clavijas=_clavijas)
    c, geo = armado["c"], r["geometria"]
    tiempos = dict(r["tiempos"], camara=armado["tiempo"])

    camara_impresion = cam_.camara_para_imprimir(armado["camara"], geo)
    tapa_impresion = cam_.tapa_para_imprimir(armado["tapa"], c)
    verificacion_camara = verificacion_tapa = None
    if verificar:
        t0 = time.perf_counter()
        verificacion_camara, verificacion_tapa = lf.verificar_malla(camara_impresion), lf.verificar_malla(tapa_impresion)
        tiempos["verificacion"] = tiempos.get("verificacion", 0.0) + time.perf_counter() - t0
        watertight_camara, watertight_tapa = bool(verificacion_camara["watertight"]), bool(verificacion_tapa["watertight"])
    else:
        watertight_camara, watertight_tapa = bool(camara_impresion.is_watertight), bool(tapa_impresion.is_watertight)

    t0 = time.perf_counter()
    base = r["ruta_stl_placa"][:-len("_placa.stl")]
    ruta_camara, ruta_tapa = f"{base}_camara.stl", f"{base}_tapa.stl"
    camara_impresion.export(ruta_camara)
    tapa_impresion.export(ruta_tapa)
    tiempos["exportacion"] = tiempos.get("exportacion", 0.0) + time.perf_counter() - t0
    stl_mb_camara, stl_mb_tapa = os.path.getsize(ruta_camara) / 1e6, os.path.getsize(ruta_tapa) / 1e6

    # las medidas reales de cada pieza, de lo que se exporta (el marco ahora lleva las clavijas)
    ext_marco = trimesh.load(r["ruta_stl_marco"]).extents
    medidas = {
        "placa": (r["placa"]["ancho_mm"], r["placa"]["alto_mm"], r["placa"]["profundidad_mm"]),
        "marco": tuple(float(x) for x in ext_marco),
        "camara": tuple(float(x) for x in camara_impresion.extents),
        "tapa": tuple(float(x) for x in tapa_impresion.extents),
    }
    entra, mensajes = {}, {}
    for nombre, (ancho, alto, profundo) in medidas.items():
        entra[nombre], mensajes[nombre] = gen_l8._chequear_pieza(NOMBRES_DE_PIEZA[nombre], ancho, alto, profundo)
    entra_a1 = all(entra.values())
    mensaje_a1 = " ".join(mensajes[n] for n in ("marco", "camara", "placa", "tapa"))

    # los avisos de L8 por A1 se reemplazan por los de las cuatro piezas
    de_l8 = {f"{r['marco']['mensaje_a1']} Achicá la litofanía o el borde: el marco todavía no se parte en módulos.",
             f"{r['placa']['mensaje_a1']} Achicá la litofanía o el borde: el marco todavía no se parte en módulos."}
    avisos = [a for a in r["avisos"] if a not in de_l8]
    for nombre in ("tapa", "placa", "camara", "marco"):
        if not entra[nombre]:
            avisos.insert(0, f"{mensajes[nombre]} Achicá la litofanía o el borde: la cámara y el marco todavía no se parten en módulos.")

    u = luz.uniformidad_de_luz(c.distancia_led, paso_led, separacion_filas, ancho_camara=c.interior[0], alto_camara=c.interior[1],
                               ancho_imagen=geo.ancho_imagen, alto_imagen=geo.alto_imagen)
    avisos += luz.avisos_de_luz(u, ancho_camara=c.interior[0], alto_camara=c.interior[1])
    try:
        sep_max = luz.separacion_maxima_de_filas(c.distancia_led, paso_led, ancho_camara=c.interior[0], alto_camara=c.interior[1])
    except ValueError:
        sep_max = None                    # a esa distancia, con ese paso de LED, no hay separación de filas que evite los puntos
    dist_min = luz.distancia_minima(paso_led, separacion_filas, ancho_camara=c.interior[0], alto_camara=c.interior[1])
    guia = guia_de_armado(c, u, sep_max, dist_min, armado["avisos_carcasa"])

    info = r["info"][:5] + [
        f"CÁMARA de {medidas['camara'][0]:.1f} x {medidas['camara'][1]:.1f} x {medidas['camara'][2]:.1f} mm (frente de "
        f"{c.espesor_brida:g} mm, pared de {c.pared:g} mm); abertura de {c.abertura[2] - c.abertura[0]:.1f} x "
        f"{c.abertura[3] - c.abertura[1]:.1f} mm, cubre {c.cobertura_banda:.2f} mm de la banda de la placa. TAPA de "
        f"{medidas['tapa'][0]:.1f} x {medidas['tapa'][1]:.1f} x {medidas['tapa'][2]:.1f} mm.",
        f"{len(c.clavijas)} clavijas de Ø{c.clavija_diam:g} x {c.clavija_largo:g} mm en el marco y {len(c.clavijas)} agujeros en la "
        f"brida ({c.juego_clavija:g} mm de juego por lado). STL de la cámara: {stl_mb_camara:.2f} MB; de la tapa: {stl_mb_tapa:.2f} MB.",
        f"Luz: tira a {c.distancia_led:g} mm de la placa (LED cada {u.paso_led:g} mm, filas cada {u.separacion_filas:g} mm, "
        f"{u.n_leds} LED en la cavidad de {c.interior[0]:.0f} x {c.interior[1]:.0f} mm): rizado entre LED de "
        f"{u.rizado_local * 100:.1f} % y bordes con el {u.borde_centro * 100:.0f} % de la luz del centro. "
        f"Modelo de LED puntuales: ignora las reflexiones de las paredes y la difusión de la placa.",
    ] + guia

    ancho_marco, alto_marco = r["ancho_mm"], r["alto_mm"]
    profundidad = max(m[2] for m in medidas.values())
    out = dict(r)
    out.update({
        "ruta_stl_camara": ruta_camara, "ruta_stl_tapa": ruta_tapa,
        "ancho_mm": ancho_marco, "alto_mm": alto_marco, "profundidad_mm": float(profundidad),
        "vertices": r["vertices"] + len(camara_impresion.vertices) + len(tapa_impresion.vertices),
        "caras": r["caras"] + len(camara_impresion.faces) + len(tapa_impresion.faces),
        "watertight": r["watertight"] and watertight_camara and watertight_tapa,
        "watertight_camara": watertight_camara, "watertight_tapa": watertight_tapa,
        "info": info, "avisos": avisos, "entra_a1": entra_a1, "mensaje_a1": mensaje_a1,
        "entra_marco_a1": entra["marco"], "entra_placa_a1": entra["placa"],
        "entra_camara_a1": entra["camara"], "entra_tapa_a1": entra["tapa"],
        "marco": dict(r["marco"], ancho_mm=medidas["marco"][0], alto_mm=medidas["marco"][1], profundidad_mm=medidas["marco"][2],
                      mensaje_a1=mensajes["marco"]),
        "placa": dict(r["placa"], mensaje_a1=mensajes["placa"]),
        "camara": {"ancho_mm": medidas["camara"][0], "alto_mm": medidas["camara"][1], "profundidad_mm": medidas["camara"][2],
                   "vertices": len(camara_impresion.vertices), "caras": len(camara_impresion.faces), "stl_mb": stl_mb_camara,
                   "mensaje_a1": mensajes["camara"]},
        "tapa": {"ancho_mm": medidas["tapa"][0], "alto_mm": medidas["tapa"][1], "profundidad_mm": medidas["tapa"][2],
                 "vertices": len(tapa_impresion.vertices), "caras": len(tapa_impresion.faces), "stl_mb": stl_mb_tapa,
                 "mensaje_a1": mensajes["tapa"]},
        "stl_mb": r["stl_mb"] + stl_mb_camara + stl_mb_tapa,
        "camara_geometria": c, "luz": u, "separacion_maxima_filas": sep_max, "distancia_minima_led": dist_min,
        "verificacion": ({"placa": r["verificacion"]["placa"], "marco": r["verificacion"]["marco"],
                          "camara": verificacion_camara, "tapa": verificacion_tapa} if verificar else None),
        "tiempos": tiempos, "guia": guia,
    })
    out.pop("entran_juntas", None)
    return out


def ejecutar():
    from core import ui

    print(f"\n{NOMBRE}")
    print("  Convierte una imagen en una litofanía con marco y cámara de luz trasera (cuatro STL).")

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
    holgura = ui.pedir_float("Holgura del encastre (mm por lado)", marco.HOLGURA_DEFAULT)
    distancia = ui.pedir_float("Distancia de la tira de LED a la placa (mm)", cam_.DISTANCIA_LED_DEFAULT)
    paso_led = ui.pedir_float("Distancia entre LED de la tira (mm; 60 LED/m = 16,7)", luz.PASO_LED_DEFAULT)
    lado = ui.pedir_opcion("¿Por qué lado sale el cable (mirando la foto)?", list(cam_.LADOS_CABLE), cam_.LADO_CABLE_DEFAULT)

    print(f"\n  » {ruta_imagen}  {ancho_mm:g} mm de ancho  LED a {distancia:g} mm  cable por {lado}")
    print("  (armando las mallas, puede tardar unos segundos...)")

    try:
        r = generar(
            ruta_imagen, ancho_mm=ancho_mm, px_por_mm=px_por_mm, grosor_min=grosor_min, grosor_max=grosor_max,
            luz_minima=luz_pct / 100.0, invertir=invertir, cara_visible=cara_visible,
            capa_mm=capa if capa > 0 else None, ancho_borde=ancho_borde, holgura=holgura, distancia_led=distancia,
            paso_led=paso_led, separacion_filas=paso_led, lado_cable=lado, carpeta_salida=CARPETA_SALIDA,
        )
    except (FileNotFoundError, ValueError) as e:
        print(f"  ERROR: {e}")
        return

    for nota in r["info"]:
        print(f"  · {nota}")
    for aviso in r["avisos"]:
        print(f"  ⚠ {aviso}")
    for nombre in ("placa", "marco", "camara", "tapa"):
        print(f"  ✓ {nombre} -> {r['ruta_stl_' + nombre]}  (watertight={r['watertight_' + nombre]})")
    print(f"  {'✓' if r['entra_a1'] else '⚠'} {r['mensaje_a1']}")
    print()
