#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/triposr_worker.py
------------------------
Proceso standalone (NO se importa desde app.py/main.py) para la
reconstrucción de una estatua 3D completa a partir de una sola foto,
usando TripoSR (Stability AI + Tripo, 2024) — reemplaza a Shap-E
(core/ia3d_worker.py, modelo de 2022) como modelo por defecto: TripoSR
es un reconstructor feed-forward (una sola pasada, sigue la imagen de
verdad) en vez de un generador difuso que "imagina" un objeto parecido
— da mucha más fidelidad a la foto real (pose, proporciones, rasgos),
en fracción del tiempo (~1 min en CPU vs 3-15 min de Shap-E).

Corre en el mismo venv aparte que Shap-E (`C:/ia3d_venv` — ver
setup_ia3d.bat), más el código fuente de TripoSR clonado en
`C:/ia3d_venv/triposr_src` (no tiene paquete pip oficial). La app
principal lo invoca por subprocess (ver core/ia3d.py).

Nota técnica: el `torchmcubes` que pide TripoSR upstream necesita
compilar una extensión C++/CUDA — no hay toolchain de compilación en
esta máquina, así que `triposr_src/tsr/models/isosurface.py` está
parcheado (ver ese archivo) para usar PyMCubes en su lugar (wheels
precompilados, mismo resultado).

Capacidades:
- Modelo de segmentación de fondo seleccionable (MODELOS_REMBG) — u2net
  genérico y rápido por default, o un modelo especializado (personas /
  objetos) para mejor recorte en el caso de uso correspondiente — la
  calidad del recorte es, en la práctica, la mayor palanca de calidad
  del resultado final (basura entra, basura sale).
- Exporta STL (para imprimir, sin color) Y opcionalmente un GLB con el
  color real que TripoSR calculó por vértice (para guardar/mirar en
  color — el STL nunca puede llevar color, así que hasta ahora ese dato
  se calculaba y se tiraba).
- Modo batch: `generar_lote()` procesa varias fotos cargando el modelo
  UNA sola vez (en vez de una vez por foto) — bastante más rápido para
  una escena grupal de varias figuras.

USO (desde el venv chico, con cwd en la raíz del proyecto):
    C:/ia3d_venv/Scripts/python.exe -m core.triposr_worker \
        <imagen_entrada> <stl_salida> <png_preview_salida> \
        --ancho_mm 80 --resolucion_malla 256 --quitar_fondo 1 --modelo_rembg u2net
"""

import argparse
import os
import sys

import numpy as np

RUTA_TRIPOSR_SRC = r"C:\ia3d_venv\triposr_src"

# Modelos de rembg disponibles para el recorte de fondo — cada uno es un
# .onnx que se descarga solo la primera vez que se usa (~170-180MB).
# "u2net" es el único que ya viene descargado por defecto en la mayoría
# de los setups (es el que usa el resto de la app); los otros dos son
# más precisos para su caso de uso específico pero más pesados/lentos.
MODELOS_REMBG = {
    "General (rápido)": "u2net",
    "Persona/Retrato (más preciso en gente)": "u2net_human_seg",
    "Objeto/Producto (alta precisión general)": "isnet-general-use",
}


def _cargar_imagen_preparada(ruta_imagen, quitar_fondo, rembg_session=None, modelo_rembg="u2net"):
    """Igual que ia3d_worker._cargar_imagen_preparada pero usando las
    utilidades propias de TripoSR (remove_background/resize_foreground),
    que dejan el sujeto ocupando ~85% del cuadro sobre fondo gris medio
    — así es como se entrenó el modelo, da mejores resultados que pegar
    sobre blanco liso."""
    from PIL import Image
    from tsr.utils import remove_background, resize_foreground

    img = Image.open(ruta_imagen).convert("RGBA")

    if quitar_fondo:
        import rembg
        session = rembg_session or rembg.new_session(modelo_rembg)
        img = remove_background(img, session)
        img = resize_foreground(img, 0.85)
    elif img.mode != "RGBA":
        img = img.convert("RGBA")

    img_arr = np.array(img).astype(np.float32) / 255.0
    if img_arr.shape[-1] == 4:
        img_arr = img_arr[:, :, :3] * img_arr[:, :, 3:4] + (1 - img_arr[:, :, 3:4]) * 0.5
    else:
        img_arr = img_arr[:, :, :3]
    return Image.fromarray((img_arr * 255.0).astype(np.uint8))


def _post_procesar_malla(malla_cruda, ancho_mm, aplicar_suavizado=True, aplicar_decimation=True):
    import trimesh

    # Preservar el color por vértice que calculó TripoSR (antes se perdía
    # acá mismo, sin llegar siquiera a la exportación) — se usa después
    # para el GLB de color; el STL de impresión nunca lleva color.
    colores_originales = None
    try:
        vc = malla_cruda.visual.vertex_colors
        if vc is not None and len(vc) == len(malla_cruda.vertices):
            colores_originales = np.array(vc, dtype=np.uint8)
    except Exception:
        colores_originales = None

    malla = trimesh.Trimesh(
        vertices=malla_cruda.vertices, faces=malla_cruda.faces,
        vertex_colors=colores_originales, process=True,
    )
    malla.remove_unreferenced_vertices()

    # TripoSR entrega Y-up (igual que Shap-E) — roto 90° en X para pasar
    # a Z-up (convención de todo el resto del proyecto: Z = altura de
    # impresión).
    malla.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))

    if not malla.is_watertight:
        trimesh.repair.fill_holes(malla)
        malla.fix_normals()

    if aplicar_suavizado:
        try:
            malla = trimesh.smoothing.laplacian_filter(malla, iterations=1, lambda_=0.1)
        except Exception:
            pass

    if aplicar_decimation:
        try:
            verts_orig = len(malla.vertices)
            target_count = max(1000, int(verts_orig * 0.35))  # TripoSR da mallas bastante más densas que Shap-E
            malla = trimesh.simplification.simplify(malla, target_count=target_count)
            malla.remove_unreferenced_vertices()
        except Exception:
            pass

    malla.fix_normals()
    max_extent = np.max(malla.extents[:2]) if len(malla.extents) >= 2 else 1.0
    escala = ancho_mm / max(max_extent, 1e-6)
    malla.apply_scale(escala)
    malla.apply_translation(-malla.bounds[0])
    return malla


def _guardar_preview(destino, malla, titulo):
    # Sombreado real (2 luces) + sombra de contacto + fondo de estudio —
    # mismo renderer que usa Esculturas para el relieve, ver
    # core/render_preview.py (comparten lenguaje visual, no código
    # duplicado). `core` es importable desde este venv aparte igual —
    # el subprocess corre con cwd en la raíz del proyecto.
    from core import render_preview
    vistas = [(22, -55, "3/4"), (8, 0, "Frente"), (75, -90, "Arriba")]
    render_preview.render_multivista(destino, malla, titulo, vistas)


def _exportar_glb_color(malla, ruta_glb):
    """Exporta un GLB con el color real por vértice (si lo hay) — STL no
    puede llevar color nunca, este es el archivo para guardar/mirar en
    color (recuerdo digital, o referencia para pintar a mano). Silencioso
    si la malla no tiene color o algo falla — es un extra, no algo de lo
    que dependa el resto del flujo."""
    try:
        malla.export(ruta_glb)
        return True
    except Exception:
        return False


def _cargar_modelo():
    if RUTA_TRIPOSR_SRC not in sys.path:
        sys.path.insert(0, RUTA_TRIPOSR_SRC)
    from tsr.system import TSR

    modelo = TSR.from_pretrained("stabilityai/TripoSR", config_name="config.yaml", weight_name="model.ckpt")
    modelo.renderer.set_chunk_size(8192)
    modelo.to("cpu")
    return modelo


def _reconstruir_una(modelo, ruta_imagen, ruta_stl, ruta_png, ancho_mm, resolucion_malla,
                      quitar_fondo, modelo_rembg, aplicar_suavizado, aplicar_decimation,
                      exportar_color, rembg_session=None):
    import torch

    imagen = _cargar_imagen_preparada(ruta_imagen, quitar_fondo, rembg_session=rembg_session, modelo_rembg=modelo_rembg)

    with torch.no_grad():
        scene_codes = modelo([imagen], device="cpu")
    mallas_crudas = modelo.extract_mesh(scene_codes, True, resolution=resolucion_malla)

    malla = _post_procesar_malla(
        mallas_crudas[0], ancho_mm,
        aplicar_suavizado=aplicar_suavizado, aplicar_decimation=aplicar_decimation,
    )
    malla.export(ruta_stl)
    _guardar_preview(ruta_png, malla, "Estatua (IA local — TripoSR)")

    ruta_glb = None
    if exportar_color:
        candidato = os.path.splitext(ruta_stl)[0] + "_color.glb"
        if _exportar_glb_color(malla, candidato):
            ruta_glb = candidato

    try:
        from core import storage
        storage.comprimir_png(ruta_png)
    except Exception:
        pass

    return malla, ruta_glb


def generar(ruta_imagen, ruta_stl, ruta_png, ancho_mm=80.0, resolucion_malla=256,
            quitar_fondo=True, modelo_rembg="u2net", aplicar_suavizado=True,
            aplicar_decimation=True, exportar_color=True):
    import gc

    modelo = _cargar_modelo()
    malla, ruta_glb = _reconstruir_una(
        modelo, ruta_imagen, ruta_stl, ruta_png, ancho_mm, resolucion_malla,
        quitar_fondo, modelo_rembg, aplicar_suavizado, aplicar_decimation, exportar_color,
    )
    del modelo
    gc.collect()

    print(f"OK vertices={len(malla.vertices)} caras={len(malla.faces)} watertight={malla.is_watertight}")
    print(f"OK bounds={malla.bounds.tolist()}")
    print(f"OK ruta_glb={ruta_glb or ''}")


def generar_lote(especificaciones, resolucion_malla=256, quitar_fondo=True, modelo_rembg="u2net",
                  aplicar_suavizado=True, aplicar_decimation=True, exportar_color=True):
    """Reconstruye VARIAS fotos cargando TripoSR una sola vez — cada
    elemento de `especificaciones` es (ruta_imagen, ruta_stl, ruta_png,
    ancho_mm). El costo de cargar el modelo (~7s) se paga una vez en vez
    de N veces, que es lo que hacía antes generar_grupo_3d() al invocar
    este worker por subprocess una vez por figura."""
    import gc
    import rembg as rembg_mod

    modelo = _cargar_modelo()
    sesion = rembg_mod.new_session(modelo_rembg) if quitar_fondo else None

    resultados = []
    for ruta_imagen, ruta_stl, ruta_png, ancho_mm in especificaciones:
        malla, ruta_glb = _reconstruir_una(
            modelo, ruta_imagen, ruta_stl, ruta_png, ancho_mm, resolucion_malla,
            quitar_fondo, modelo_rembg, aplicar_suavizado, aplicar_decimation, exportar_color,
            rembg_session=sesion,
        )
        resultados.append((ruta_stl, ruta_png, ruta_glb, len(malla.vertices), len(malla.faces), malla.is_watertight))
        print(f"OK item ruta_stl={ruta_stl} vertices={len(malla.vertices)} watertight={malla.is_watertight}")

    del modelo
    gc.collect()
    return resultados


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ruta_imagen", nargs="?", default=None)
    ap.add_argument("ruta_stl", nargs="?", default=None)
    ap.add_argument("ruta_png", nargs="?", default=None)
    ap.add_argument("--ancho_mm", type=float, default=80.0)
    ap.add_argument("--resolucion_malla", type=int, default=256)
    ap.add_argument("--quitar_fondo", type=int, default=1)
    ap.add_argument("--modelo_rembg", type=str, default="u2net")
    ap.add_argument("--suavizado", type=int, default=1)
    ap.add_argument("--decimation", type=int, default=1)
    ap.add_argument("--exportar_color", type=int, default=1)
    ap.add_argument(
        "--lote", type=str, default=None,
        help="Ruta a un JSON con una lista de [ruta_imagen, ruta_stl, ruta_png, ancho_mm] — "
             "modo batch, carga el modelo una sola vez para todas las figuras.",
    )
    args = ap.parse_args()

    try:
        if args.lote:
            import json
            with open(args.lote, "r", encoding="utf-8") as f:
                especificaciones = [tuple(item) for item in json.load(f)]
            generar_lote(
                especificaciones, resolucion_malla=args.resolucion_malla,
                quitar_fondo=bool(args.quitar_fondo), modelo_rembg=args.modelo_rembg,
                aplicar_suavizado=bool(args.suavizado), aplicar_decimation=bool(args.decimation),
                exportar_color=bool(args.exportar_color),
            )
        else:
            if not (args.ruta_imagen and args.ruta_stl and args.ruta_png):
                raise ValueError("faltan ruta_imagen/ruta_stl/ruta_png (o usá --lote)")
            generar(
                args.ruta_imagen, args.ruta_stl, args.ruta_png,
                ancho_mm=args.ancho_mm, resolucion_malla=args.resolucion_malla,
                quitar_fondo=bool(args.quitar_fondo), modelo_rembg=args.modelo_rembg,
                aplicar_suavizado=bool(args.suavizado), aplicar_decimation=bool(args.decimation),
                exportar_color=bool(args.exportar_color),
            )
    except Exception as e:  # noqa: BLE001 — se reporta al proceso padre por stderr, no hay UI acá
        print(f"ERROR {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
