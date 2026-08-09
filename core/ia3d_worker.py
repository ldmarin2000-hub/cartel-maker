#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/ia3d_worker.py
--------------------
Proceso standalone (NO se importa desde app.py/main.py) para la
reconstrucción de una estatua 3D completa a partir de una sola foto,
usando Shap-E img2img (OpenAI, vía diffusers) — a diferencia de
core/heightmap.py (relieve 2.5D, una sola cara), esto genera un
volumen completo que sigue la pose del sujeto en la foto.

Corre en un venv aparte (`C:/ia3d_venv`, ruta corta a propósito: los
archivos de licencia de torch tienen rutas internas tan anidadas que
rompen el límite de 260 caracteres de Windows si el proyecto vive en
una ruta larga como esta). La app principal lo invoca por subprocess
(ver core/ia3d.py) y se comunican por archivos, no por import directo
— así el venv grande (torch, diffusers, ~2GB) no es una dependencia
obligatoria del resto de la app.

USO (desde el venv chico, con cwd en la raíz del proyecto):
    C:/ia3d_venv/Scripts/python.exe -m core.ia3d_worker \
        <imagen_entrada> <stl_salida> <png_preview_salida> \
        --ancho_mm 80 --pasos 32 --guidance 3.0 --quitar_fondo 1
"""

import argparse
import sys

import numpy as np


def _cargar_imagen_preparada(ruta_imagen, quitar_fondo):
    from PIL import Image

    img = Image.open(ruta_imagen).convert("RGBA")

    if quitar_fondo:
        import rembg

        img = rembg.remove(img)

    # Shap-E se entrenó con renders sobre fondo blanco y el sujeto
    # centrado — pegamos sobre blanco (usa el alfa si lo hay) en vez
    # de mandar transparencia cruda, y recortamos al cuadrado del
    # sujeto para que no quede perdido/chico en el centro.
    fondo = Image.new("RGBA", img.size, (255, 255, 255, 255))
    fondo.alpha_composite(img)
    rgb = fondo.convert("RGB")

    alpha = np.array(img.split()[-1]) if quitar_fondo else None
    if alpha is not None and alpha.max() > 0:
        ys, xs = np.where(alpha > 10)
        x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
        margen = int(max(x1 - x0, y1 - y0) * 0.12)
        x0, y0 = max(0, x0 - margen), max(0, y0 - margen)
        x1, y1 = min(rgb.width, x1 + margen), min(rgb.height, y1 + margen)
        rgb = rgb.crop((x0, y0, x1, y1))

    lado = max(rgb.size)
    cuadro = Image.new("RGB", (lado, lado), (255, 255, 255))
    cuadro.paste(rgb, ((lado - rgb.width) // 2, (lado - rgb.height) // 2))
    return cuadro.resize((256, 256), Image.LANCZOS)


def _malla_desde_mesh_shape(mesh_out, ancho_mm, aplicar_suavizado=True, aplicar_decimation=True):
    import trimesh

    verts = mesh_out.verts.detach().cpu().numpy().astype(np.float64)
    faces = mesh_out.faces.detach().cpu().numpy().astype(np.int64)

    # Shap-E entrega Y-up; el resto del proyecto (heightmap, mesh3d)
    # trabaja en Z-up (Z = altura de impresión) — roto 90° en X.
    verts = verts[:, [0, 2, 1]]
    verts[:, 1] *= -1

    malla = trimesh.Trimesh(vertices=verts, faces=faces, process=True)
    malla.remove_unreferenced_vertices()

    if not malla.is_watertight:
        trimesh.repair.fill_holes(malla)
        malla.fix_normals()

    # Laplacian smoothing: reduce ruido/artefactos de la IA sin perder silueta
    if aplicar_suavizado:
        try:
            malla = trimesh.smoothing.laplacian_filter(malla, iterations=1, lambda_=0.1)
        except Exception:
            pass  # si falla, sigue con la malla sin suavizar

    # Quadric mesh decimation: reduce vértices para archivo más liviano
    if aplicar_decimation:
        try:
            verts_orig = len(malla.vertices)
            ratio_target = 0.7  # mantener 70% de vértices
            malla = trimesh.simplification.simplify_mesh(malla, target_count=max(500, int(verts_orig * ratio_target)))
            malla.remove_unreferenced_vertices()
        except Exception:
            pass  # si falla, usa la malla sin decimation

    malla.fix_normals()
    escala = ancho_mm / max(malla.extents[:2].max(), 1e-6)
    malla.apply_scale(escala)
    malla.apply_translation(-malla.bounds[0])  # apoyada en Z=0, esquina en (0,0)
    return malla


def _guardar_preview(destino, malla, titulo):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LightSource
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    tris = malla.vertices[malla.faces]
    (minx, miny, minz), (maxx, maxy, maxz) = malla.bounds
    dx, dy, dz = max(maxx - minx, 1), max(maxy - miny, 1), max(maxz - minz, 1)

    fig = plt.figure(figsize=(11, 6))
    vistas = [(20, -60, "3/4"), (10, 30, "Frente")]

    # Cálculo de faces normals para shading (lighting)
    face_normals = malla.face_normals

    for i, (elev, azim, sub) in enumerate(vistas):
        ax = fig.add_subplot(1, 2, i + 1, projection="3d")

        # Pseudo-shading: variar el color por normal para dar profundidad
        shade_vals = np.dot(face_normals, np.array([0.5, -0.5, 1]))
        shade_vals = (shade_vals + 1) / 2
        shade_vals = np.clip(shade_vals, 0.3, 1.0)

        # Aplicar shading a color base
        colors = np.zeros((len(tris), 3))
        base_rgb = np.array([0.788, 0.659, 0.463])  # #c9a876 RGB
        colors[:] = base_rgb * shade_vals[:, np.newaxis]

        poly = Poly3DCollection(tris, facecolor=colors, edgecolor="#00000011", linewidths=0.02)
        ax.add_collection3d(poly)

        ax.set_xlim(minx, maxx)
        ax.set_ylim(miny, maxy)
        ax.set_zlim(minz, maxz)
        ax.view_init(elev=elev, azim=azim)
        ax.set_title(sub, color="#ccc", fontsize=10)
        ax.set_box_aspect((dx, dy, dz))
        ax.set_axis_off()
        ax.set_facecolor("#1a1a1a")
        for pane in (ax.xaxis.pane, ax.yaxis.pane, ax.zaxis.pane):
            pane.set_alpha(0.0)

    fig.suptitle(titulo, color="#ccc", fontsize=12)
    fig.savefig(destino, dpi=110, facecolor="#1a1a1a", bbox_inches="tight")
    plt.close(fig)


def generar(ruta_imagen, ruta_stl, ruta_png, ancho_mm=80.0, pasos=32, guidance=3.0, quitar_fondo=True, aplicar_suavizado=True, aplicar_decimation=True):
    import torch
    from diffusers import ShapEImg2ImgPipeline

    imagen = _cargar_imagen_preparada(ruta_imagen, quitar_fondo)

    pipe = ShapEImg2ImgPipeline.from_pretrained("openai/shap-e-img2img", torch_dtype=torch.float32)
    pipe = pipe.to("cpu")

    salida = pipe(
        imagen,
        guidance_scale=guidance,
        num_inference_steps=pasos,
        frame_size=256,
        output_type="mesh",
    )
    mesh_out = salida.images[0]

    malla = _malla_desde_mesh_shape(mesh_out, ancho_mm, aplicar_suavizado=aplicar_suavizado, aplicar_decimation=aplicar_decimation)
    malla.export(ruta_stl)
    _guardar_preview(ruta_png, malla, "Estatua (IA local)")

    print(f"OK vertices={len(malla.vertices)} caras={len(malla.faces)} watertight={malla.is_watertight}")
    print(f"OK bounds={malla.bounds.tolist()}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ruta_imagen")
    ap.add_argument("ruta_stl")
    ap.add_argument("ruta_png")
    ap.add_argument("--ancho_mm", type=float, default=80.0)
    ap.add_argument("--pasos", type=int, default=32)
    ap.add_argument("--guidance", type=float, default=3.0)
    ap.add_argument("--quitar_fondo", type=int, default=1)
    ap.add_argument("--suavizado", type=int, default=1)
    ap.add_argument("--decimation", type=int, default=1)
    args = ap.parse_args()

    try:
        generar(
            args.ruta_imagen, args.ruta_stl, args.ruta_png,
            ancho_mm=args.ancho_mm, pasos=args.pasos, guidance=args.guidance,
            quitar_fondo=bool(args.quitar_fondo), aplicar_suavizado=bool(args.suavizado),
            aplicar_decimation=bool(args.decimation),
        )
    except Exception as e:  # noqa: BLE001 — se reporta al proceso padre por stderr, no hay UI acá
        print(f"ERROR {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
