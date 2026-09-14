#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generators/esculturas.py
----------------------------
Escultura/relieve 3D a partir de una imagen — Python puro
(core/heightmap.py: el brillo de cada píxel modula la altura de una
grilla, en vez de sacar solo el contorno plano como hace
core/imagen_import.py). El resultado es un bloque sólido con la foto
"tallada" arriba: watertight, con piso plano y paredes laterales, listo
para imprimir — no una silueta ni una nube de puntos.

Pensado para logos/fotos/dibujos con contraste razonable: una foto muy
plana en brillo (todo gris parejo) da un relieve casi sin relieve.
"""

import io
import os

from core import heightmap, pieza, mesh_primitivas, render_preview

NOMBRE = "Escultura (relieve desde imagen)"
DESCRIPCION = "Imagen -> relieve 3D tallado (el brillo de cada zona modula la altura). STL watertight."

CARPETA_SALIDA = "output"

RESOLUCION_RAPIDA_PX = 45
RESOLUCION_DEFAULT_PX = 120
RESOLUCION_ALTA_PX = 180

FORMAS_MEDALLON = ["Rectangular", "Circular", "Ovalada"]
LAYOUTS_COLLAGE = ["Lado a lado", "Grilla 2x2", "Principal + chicas"]


# Vistas completas: 3/4 (hero, como se ve la pieza en la mano), Rasante
# (luz casi al ras de la superficie — la técnica clásica para inspeccionar
# un relieve/bajorrelieve, exagera la sensación de profundidad tallada
# mucho más que una vista frontal plana) y Arriba (útil para medallones
# circulares/ovalados y para ver el layout completo de un collage).
_VISTAS_COMPLETAS = [(32, -58, "3/4"), (6, -92, "Rasante (detalle del relieve)"), (82, -90, "Arriba")]
_VISTAS_RAPIDAS = [(32, -58, "3/4"), (6, -92, "Rasante")]


def _guardar_preview_sombreado(destino, malla, titulo, rapido=False):
    vistas = _VISTAS_RAPIDAS if rapido else _VISTAS_COMPLETAS
    render_preview.render_multivista(destino, malla, titulo, vistas)


def preview_rapido(ruta_imagen, ancho_mm=80.0, alto_mm=80.0,
                    espesor_base_mm=3.0, relieve_mm=8.0,
                    suavizado_px=1.0, oscuro_alto=True):
    """Preview instantáneo — la MISMA técnica que `generar()` pero a
    resolución baja (`RESOLUCION_RAPIDA_PX`, ~0.3-0.5s en vez de varios
    segundos) y renderizada como imagen sombreada 2D (no el visor 3D
    interactivo, que se muestra recién después de generar) — para
    juzgar el relieve mientras se ajustan los parámetros. Devuelve
    png_bytes, o None si no se pudo leer la imagen."""
    if not ruta_imagen or not os.path.exists(ruta_imagen):
        return None
    try:
        malla = heightmap.escultura_desde_imagen(
            ruta_imagen, ancho_mm=ancho_mm, alto_mm=alto_mm,
            espesor_base_mm=espesor_base_mm, relieve_mm=relieve_mm,
            resolucion_px=RESOLUCION_RAPIDA_PX, suavizado_px=suavizado_px,
            oscuro_alto=oscuro_alto,
        )
    except (OSError, ValueError):
        return None

    buf = io.BytesIO()
    _guardar_preview_sombreado(buf, malla, "Vista rápida", rapido=True)
    return buf.getvalue()


def generar(ruta_imagen, ancho_mm=80.0, alto_mm=80.0,
            espesor_base_mm=3.0, relieve_mm=8.0,
            resolucion_px=RESOLUCION_DEFAULT_PX, suavizado_px=1.0,
            oscuro_alto=True, segmentar_sujeto=False, forma_medallon="Rectangular",
            carpeta_salida=CARPETA_SALIDA):
    """Arma la escultura/relieve y exporta el STL. Devuelve un dict con
    la ruta, medidas y avisos. No pregunta nada ni imprime nada — así lo
    puede llamar tanto la CLI como la app visual.

    `resolucion_px`: detalle de la grilla (lado más largo) — más alto
    es más fiel a la imagen pero más lento y más pesado el STL.
    `espesor_base_mm`: piso mínimo (para que no se rompa). `relieve_mm`:
    cuánto sobresale la parte más alta por encima del piso.
    `oscuro_alto=True`: las zonas oscuras de la imagen quedan más altas
    (relieve escultórico típico) — en falso, al revés.
    `segmentar_sujeto=True`: relieve "escultórico diferenciado" — el
    sujeto (persona/objeto principal, detectado con rembg) sobresale
    más que el fondo, en vez de un relieve uniforme por brillo solo."""
    if not os.path.exists(ruta_imagen):
        raise FileNotFoundError(f"no encuentro la imagen: {ruta_imagen}")
    if espesor_base_mm <= 0:
        raise ValueError("el espesor de la base tiene que ser mayor a 0 (si no, no hay piso)")

    malla = heightmap.escultura_desde_imagen(
        ruta_imagen, ancho_mm=ancho_mm, alto_mm=alto_mm,
        espesor_base_mm=espesor_base_mm, relieve_mm=relieve_mm,
        resolucion_px=resolucion_px, suavizado_px=suavizado_px,
        oscuro_alto=oscuro_alto, segmentar_sujeto=segmentar_sujeto,
        forma_medallon=forma_medallon,
    )

    os.makedirs(carpeta_salida, exist_ok=True)
    base_nombre = pieza.nombre_archivo(os.path.splitext(os.path.basename(ruta_imagen))[0], default="escultura")
    ruta_stl = os.path.join(carpeta_salida, f"escultura_{base_nombre}.stl")
    ruta_png = os.path.join(carpeta_salida, f"escultura_{base_nombre}_preview.png")

    malla.export(ruta_stl)
    _guardar_preview_sombreado(ruta_png, malla, "Escultura")

    ancho_final_mm, alto_final_mm, profundo_final_mm, entra_a1, mensaje_a1 = pieza.chequear_desde_malla(
        malla, nombre="escultura"
    )

    info = [
        f"Relieve de {relieve_mm:.1f}mm sobre una base de {espesor_base_mm:.1f}mm — "
        f"grosor total en la parte más alta: {espesor_base_mm + relieve_mm:.1f}mm."
    ]
    avisos = []
    if not malla.is_watertight:
        avisos.append("No quedó perfectamente watertight, revisala antes de imprimir.")

    return {
        "ruta_stl": ruta_stl,
        "ruta_png": ruta_png,
        "ancho_mm": ancho_final_mm, "alto_mm": alto_final_mm, "profundidad_mm": profundo_final_mm,
        "vertices": len(malla.vertices), "caras": len(malla.faces),
        "watertight": malla.is_watertight,
        "info": info,
        "avisos": avisos,
        "entra_a1": entra_a1,
        "mensaje_a1": mensaje_a1,
    }


# ---------------------------------------------------------------------------
# Combinar varias imágenes en un mismo relieve (collage tallado)
# ---------------------------------------------------------------------------

def _armar_collage(rutas_imagenes, layout="Lado a lado", separador_px=10, lado_px=900):
    """Compone 2-4 imágenes en un único lienzo PIL (una imagen compuesta),
    para tallarla como UN solo relieve — cada foto ocupa su región, con
    un separador entre ellas (queda como una "juntura" en el relieve
    final, similar a un marco de fotos tallado en una sola placa).

    `layout`:
    - "Lado a lado": todas en una fila horizontal, mismo alto.
    - "Grilla 2x2": hasta 4 fotos en cuadrícula 2x2 (si son menos de 4,
      la última celda queda vacía/blanca).
    - "Principal + chicas": la primera foto grande a la izquierda, el
      resto apiladas más chicas a la derecha.

    Devuelve la ruta del archivo temporal compuesto (PNG), para pasarla
    tal cual al mismo pipeline de `escultura_desde_imagen()` que ya
    usa una sola imagen — no hace falta tocar heightmap.py."""
    from PIL import Image

    imagenes = [Image.open(r).convert("RGB") for r in rutas_imagenes]
    if not imagenes:
        raise ValueError("no hay imágenes para combinar")

    if layout == "Grilla 2x2":
        celda = lado_px // 2
        lienzo = Image.new("RGB", (lado_px, lado_px), (255, 255, 255))
        posiciones = [(0, 0), (celda + separador_px, 0), (0, celda + separador_px), (celda + separador_px, celda + separador_px)]
        for img, (px, py) in zip(imagenes[:4], posiciones):
            img_ajustada = _ajustar_a_caja(img, celda - separador_px, celda - separador_px)
            lienzo.paste(img_ajustada, (px, py))

    elif layout == "Principal + chicas":
        principal = imagenes[0]
        secundarias = imagenes[1:4]
        ancho_principal = int(lado_px * 0.6)
        ancho_secundarias = lado_px - ancho_principal - separador_px
        alto_secundaria = (lado_px - separador_px * max(len(secundarias) - 1, 0)) // max(len(secundarias), 1) if secundarias else lado_px

        lienzo = Image.new("RGB", (lado_px, lado_px), (255, 255, 255))
        lienzo.paste(_ajustar_a_caja(principal, ancho_principal, lado_px), (0, 0))
        y = 0
        for img in secundarias:
            lienzo.paste(_ajustar_a_caja(img, ancho_secundarias, alto_secundaria), (ancho_principal + separador_px, y))
            y += alto_secundaria + separador_px

    else:  # "Lado a lado"
        n = len(imagenes)
        alto = lado_px
        ancho_cada = (lado_px * n - separador_px * (n - 1)) // n if n > 1 else lado_px
        ancho_total = ancho_cada * n + separador_px * (n - 1)
        lienzo = Image.new("RGB", (ancho_total, alto), (255, 255, 255))
        x = 0
        for img in imagenes:
            lienzo.paste(_ajustar_a_caja(img, ancho_cada, alto), (x, 0))
            x += ancho_cada + separador_px

    os.makedirs(CARPETA_SALIDA, exist_ok=True)
    ruta_temp = os.path.join(CARPETA_SALIDA, "_collage_temp.png")
    lienzo.save(ruta_temp)
    return ruta_temp


def _ajustar_a_caja(img, ancho_px, alto_px):
    """Recorta+escala `img` para llenar exactamente una caja ancho x alto
    (cover, no letterbox) — mismo criterio que un marco de fotos: se
    pierde un poco de los bordes en vez de dejar franjas blancas."""
    from PIL import Image

    ancho_px, alto_px = max(1, ancho_px), max(1, alto_px)
    ratio_caja = ancho_px / alto_px
    ratio_img = img.width / img.height

    if ratio_img > ratio_caja:
        nuevo_alto = alto_px
        nuevo_ancho = int(alto_px * ratio_img)
    else:
        nuevo_ancho = ancho_px
        nuevo_alto = int(ancho_px / ratio_img)

    img_r = img.resize((nuevo_ancho, nuevo_alto), Image.LANCZOS)
    x0 = (nuevo_ancho - ancho_px) // 2
    y0 = (nuevo_alto - alto_px) // 2
    return img_r.crop((x0, y0, x0 + ancho_px, y0 + alto_px))


def generar_combinado(rutas_imagenes, layout="Lado a lado", ancho_mm=120.0, alto_mm=80.0,
                       espesor_base_mm=3.0, relieve_mm=8.0,
                       resolucion_px=RESOLUCION_DEFAULT_PX, suavizado_px=1.0,
                       oscuro_alto=True, segmentar_sujeto=False,
                       carpeta_salida=CARPETA_SALIDA):
    """Combina 2-4 fotos en UN solo relieve tallado (ver `_armar_collage`
    para los layouts) — misma técnica y mismo contrato de salida que
    `generar()`, solo que la imagen de entrada es un collage compuesto
    en vez de una foto sola. Pensado para retratos familiares, "antes y
    después", varias mascotas, etc. en una única placa imprimible."""
    if len(rutas_imagenes) < 2:
        raise ValueError("hacen falta al menos 2 imágenes para combinar")
    if len(rutas_imagenes) > 4:
        raise ValueError("hasta 4 imágenes por collage (más queda ilegible en el relieve)")
    for r in rutas_imagenes:
        if not os.path.exists(r):
            raise FileNotFoundError(f"no encuentro la imagen: {r}")

    ruta_collage = _armar_collage(rutas_imagenes, layout=layout)

    resultado = generar(
        ruta_collage, ancho_mm=ancho_mm, alto_mm=alto_mm,
        espesor_base_mm=espesor_base_mm, relieve_mm=relieve_mm,
        resolucion_px=resolucion_px, suavizado_px=suavizado_px,
        oscuro_alto=oscuro_alto, segmentar_sujeto=segmentar_sujeto,
        carpeta_salida=carpeta_salida,
    )
    resultado["info"].append(f"Collage de {len(rutas_imagenes)} imágenes ({layout}).")
    return resultado


# ---------------------------------------------------------------------------
# Pedestal + placa de nombre para estatuas 3D (single o escena grupal)
# ---------------------------------------------------------------------------

def agregar_pedestal(ruta_stl_estatua, forma_base="Redonda", texto="", fuente_ttf=None,
                      ruta_salida=None, alto_pedestal_mm=8.0):
    """Toma un STL de estatua ya generado (ej. por IA local/TripoSR) y le
    agrega un pedestal con la forma elegida debajo, más una placa con
    texto grabado (nombre/fecha/dedicatoria) al frente si se pasa
    `texto` — para que quede como una estatuilla de mesa lista para
    imprimir en una sola pieza, en vez de la figura sola apoyada
    directo. Devuelve la ruta del nuevo STL (o `ruta_salida` si se
    especificó)."""
    import trimesh

    estatua = trimesh.load(ruta_stl_estatua, force="mesh")
    ancho_estatua = max(estatua.extents[0], estatua.extents[2])
    radio_pedestal = max(20, ancho_estatua * 0.6)

    pedestal = mesh_primitivas.forma_base(forma_base, radio_pedestal, alto_pedestal_mm, z0=0)

    piezas = [pedestal]
    estatua_elevada = estatua.copy()
    estatua_elevada.apply_translation([0, 0, alto_pedestal_mm - estatua.bounds[0][2]])
    piezas.append(estatua_elevada)

    if texto and texto.strip():
        altura_texto = alto_pedestal_mm * 0.5
        texto3d = mesh_primitivas.texto_a_malla3d(texto.strip(), altura=altura_texto, fuente_ttf=fuente_ttf, z0=0)
        if texto3d is not None:
            # al frente del pedestal (eje que la orientación final no toca)
            texto3d.apply_translation([0, -radio_pedestal * 0.45, 0])
            piezas.append(texto3d)

    combinada = mesh_primitivas.combinar(piezas)
    combinada.fix_normals()

    if ruta_salida is None:
        base, ext = os.path.splitext(ruta_stl_estatua)
        ruta_salida = f"{base}_pedestal{ext}"
    combinada.export(ruta_salida)
    return ruta_salida, combinada


# ---------------------------------------------------------------------------
# Escena grupal 3D — combinar varias fotos en una sola escultura (IA local)
# ---------------------------------------------------------------------------

def generar_grupo_3d(rutas_imagenes, alto_mm_principal=80.0, resolucion_malla=256,
                      quitar_fondo=True, forma_base="Redonda", texto_placa="",
                      fuente_ttf=None, timeout_seg=900, carpeta_salida=CARPETA_SALIDA):
    """Reconstruye CADA foto por separado con TripoSR (core.ia3d) y arma
    una sola escultura con todas las figuras paradas sobre un pedestal
    compartido — para "combinar varias imágenes en una misma escultura"
    de verdad (no un collage plano): una familia, mascota + dueño, etc.,
    cada una como figura 3D independiente, todas en una sola pieza
    imprimible. La primera imagen es la "principal" (altura de
    referencia `alto_mm_principal`); las demás se escalan proporcional
    a su propio tamaño relativo detectado.

    Puede tardar bastante — es N reconstrucciones TripoSR en serie
    (~30-70s cada una en CPU) más el armado final."""
    from core import ia3d
    import trimesh

    if len(rutas_imagenes) < 2:
        raise ValueError("hacen falta al menos 2 imágenes para una escena grupal")
    if len(rutas_imagenes) > 4:
        raise ValueError("hasta 4 figuras por escena (más queda apretado en la base)")
    for r in rutas_imagenes:
        if not os.path.exists(r):
            raise FileNotFoundError(f"no encuentro la imagen: {r}")

    figuras = []
    tiempos_totales = []
    for r in rutas_imagenes:
        res = ia3d.generar_local(
            r, carpeta_salida=carpeta_salida, ancho_mm=alto_mm_principal,
            resolucion_malla=resolucion_malla, quitar_fondo=quitar_fondo, timeout_seg=timeout_seg,
        )
        malla = trimesh.load(res["ruta_stl"], force="mesh")
        figuras.append(malla)
        tiempos_totales.append(res.get("info", [""])[0])

    anchos = [max(f.extents[0], f.extents[2]) for f in figuras]
    ancho_mayor = max(anchos)
    separacion_mm = ancho_mayor * 0.35
    ancho_total_figuras = sum(anchos) + separacion_mm * (len(figuras) - 1)

    radio_pedestal = max(30, ancho_total_figuras * 0.6)
    alto_pedestal_mm = 6.0
    pedestal = mesh_primitivas.forma_base(forma_base, radio_pedestal, alto_pedestal_mm, z0=0)

    piezas = [pedestal]
    x_actual = -ancho_total_figuras / 2
    for malla, ancho in zip(figuras, anchos):
        cx_actual = malla.bounds.mean(axis=0)[0]
        malla.apply_translation([-cx_actual + x_actual + ancho / 2, 0, alto_pedestal_mm - malla.bounds[0][2]])
        piezas.append(malla)
        x_actual += ancho + separacion_mm

    if texto_placa and texto_placa.strip():
        altura_texto = alto_pedestal_mm * 0.6
        texto3d = mesh_primitivas.texto_a_malla3d(texto_placa.strip(), altura=altura_texto, fuente_ttf=fuente_ttf, z0=0)
        if texto3d is not None:
            texto3d.apply_translation([0, -radio_pedestal * 0.5, 0])
            piezas.append(texto3d)

    escena = mesh_primitivas.combinar(piezas)
    escena.fix_normals()

    os.makedirs(carpeta_salida, exist_ok=True)
    base_nombre = "_".join(
        pieza.nombre_archivo(os.path.splitext(os.path.basename(r))[0], default="figura")
        for r in rutas_imagenes[:3]
    )
    ruta_stl = os.path.join(carpeta_salida, f"escena_{base_nombre}.stl")
    ruta_png = os.path.join(carpeta_salida, f"escena_{base_nombre}_preview.png")
    escena.export(ruta_stl)
    _guardar_preview_sombreado(ruta_png, escena, "Escena grupal")

    ancho_final_mm, alto_final_mm, profundo_final_mm, entra_a1, mensaje_a1 = pieza.chequear_desde_malla(
        escena, nombre="escena grupal"
    )

    avisos = []
    if not escena.is_watertight:
        avisos.append("No quedó perfectamente watertight, revisala antes de imprimir.")

    return {
        "ruta_stl": ruta_stl,
        "ruta_png": ruta_png,
        "ancho_mm": ancho_final_mm, "alto_mm": alto_final_mm, "profundidad_mm": profundo_final_mm,
        "vertices": len(escena.vertices), "caras": len(escena.faces),
        "watertight": escena.is_watertight,
        "info": [f"{len(rutas_imagenes)} figuras reconstruidas con TripoSR sobre pedestal {forma_base.lower()} compartido."],
        "avisos": avisos,
        "entra_a1": entra_a1,
        "mensaje_a1": mensaje_a1,
    }


# ---------------------------------------------------------------------------
#  Interfaz de consola (menú de main.py)
# ---------------------------------------------------------------------------
def ejecutar():
    from core import ui

    print(f"\n{NOMBRE}")
    print("  Convierte una imagen (foto/logo/dibujo) en un relieve 3D tallado.")

    ruta_imagen = ui.pedir_texto("Ruta a la imagen (PNG/JPG)", "")
    if not ruta_imagen or not os.path.exists(ruta_imagen):
        print(f"  ERROR: no encuentro la imagen: {ruta_imagen!r}")
        return

    ancho_mm = ui.pedir_float("Ancho (mm)", 80.0)
    alto_mm = ui.pedir_float("Alto (mm)", 80.0)
    relieve_mm = ui.pedir_float("Relieve (mm, cuánto sobresale lo más alto)", 8.0)
    espesor_base_mm = ui.pedir_float("Espesor de la base (mm)", 3.0)
    oscuro_alto = ui.pedir_si_no("¿Las zonas OSCURAS quedan más altas?", default=True)

    print(f"\n  » {ruta_imagen}  {ancho_mm:.0f}x{alto_mm:.0f}mm  relieve {relieve_mm:.0f}mm")
    print("  (armando la grilla y la malla, puede tardar unos segundos...)")

    try:
        r = generar(
            ruta_imagen, ancho_mm=ancho_mm, alto_mm=alto_mm,
            espesor_base_mm=espesor_base_mm, relieve_mm=relieve_mm, oscuro_alto=oscuro_alto,
        )
    except (FileNotFoundError, ValueError) as e:
        print(f"  ERROR: {e}")
        return

    print(f"  tamaño ~ {r['ancho_mm']:.0f} x {r['alto_mm']:.0f} x {r['profundidad_mm']:.0f} mm")
    for nota in r["info"]:
        print(f"  · {nota}")
    for aviso in r["avisos"]:
        print(f"  ⚠ {aviso}")
    print(f"  ✓ STL -> {r['ruta_stl']}  ({r['vertices']} vért., watertight={r['watertight']})")
    print(f"  ✓ preview -> {r['ruta_png']}")
    print(f"  {'✓' if r['entra_a1'] else '⚠'} {r['mensaje_a1']}")
    print()
