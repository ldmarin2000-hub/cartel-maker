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

USO (desde el venv chico, con cwd en la raíz del proyecto):
    C:/ia3d_venv/Scripts/python.exe -m core.triposr_worker \
        <imagen_entrada> <stl_salida> <png_preview_salida> \
        --ancho_mm 80 --resolucion_malla 256 --quitar_fondo 1
"""

import argparse
import os
import sys

import numpy as np

RUTA_TRIPOSR_SRC = r"C:\ia3d_venv\triposr_src"


def _cargar_imagen_preparada(ruta_imagen, quitar_fondo, rembg_session=None):
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
        session = rembg_session or rembg.new_session()
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

    malla = trimesh.Trimesh(vertices=malla_cruda.vertices, faces=malla_cruda.faces, process=True)
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


def generar(ruta_imagen, ruta_stl, ruta_png, ancho_mm=80.0, resolucion_malla=256,
            quitar_fondo=True, aplicar_suavizado=True, aplicar_decimation=True):
    import gc
    import torch

    if RUTA_TRIPOSR_SRC not in sys.path:
        sys.path.insert(0, RUTA_TRIPOSR_SRC)
    from tsr.system import TSR

    modelo = TSR.from_pretrained("stabilityai/TripoSR", config_name="config.yaml", weight_name="model.ckpt")
    modelo.renderer.set_chunk_size(8192)
    modelo.to("cpu")

    imagen = _cargar_imagen_preparada(ruta_imagen, quitar_fondo)

    with torch.no_grad():
        scene_codes = modelo([imagen], device="cpu")
    mallas_crudas = modelo.extract_mesh(scene_codes, True, resolution=resolucion_malla)

    del modelo, scene_codes
    gc.collect()

    malla = _post_procesar_malla(
        mallas_crudas[0], ancho_mm,
        aplicar_suavizado=aplicar_suavizado, aplicar_decimation=aplicar_decimation,
    )
    malla.export(ruta_stl)
    _guardar_preview(ruta_png, malla, "Estatua (IA local — TripoSR)")

    try:
        from core import storage
        storage.comprimir_png(ruta_png)
    except Exception:
        pass

    print(f"OK vertices={len(malla.vertices)} caras={len(malla.faces)} watertight={malla.is_watertight}")
    print(f"OK bounds={malla.bounds.tolist()}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ruta_imagen")
    ap.add_argument("ruta_stl")
    ap.add_argument("ruta_png")
    ap.add_argument("--ancho_mm", type=float, default=80.0)
    ap.add_argument("--resolucion_malla", type=int, default=256)
    ap.add_argument("--quitar_fondo", type=int, default=1)
    ap.add_argument("--suavizado", type=int, default=1)
    ap.add_argument("--decimation", type=int, default=1)
    args = ap.parse_args()

    try:
        generar(
            args.ruta_imagen, args.ruta_stl, args.ruta_png,
            ancho_mm=args.ancho_mm, resolucion_malla=args.resolucion_malla,
            quitar_fondo=bool(args.quitar_fondo), aplicar_suavizado=bool(args.suavizado),
            aplicar_decimation=bool(args.decimation),
        )
    except Exception as e:  # noqa: BLE001 — se reporta al proceso padre por stderr, no hay UI acá
        print(f"ERROR {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
