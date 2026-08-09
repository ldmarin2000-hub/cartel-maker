#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/ia3d.py
--------------
Puente hacia la generación de estatuas 3D completas por IA — a
diferencia de core/heightmap.py (relieve 2.5D: altura desde brillo,
una sola cara), acá se reconstruye un VOLUMEN completo que sigue la
pose del sujeto de la foto (para eso hace falta un modelo generativo
entrenado, no hay receta geométrica clásica que lo resuelva).

Dos caminos, mismo contrato de salida (ver `generar_local` /
`generar_api`):

- **Local** (`generar_local`): corre Shap-E (OpenAI, vía diffusers) en
  un venv aparte de ruta corta (`C:\\ia3d_venv` — ver setup_ia3d.bat y
  core/ia3d_worker.py) por subprocess, gratis y sin mandar la imagen a
  ningún lado, pero más lento (CPU) y de calidad más rústica.
- **API externa** (`generar_api`): manda la imagen a un servicio pago
  (Tripo3D o Meshy — mejor fidelidad/pose, tarda menos) usando una API
  key que pone el usuario en la UI, sin guardarla en disco ni en el
  repo.
"""

import os
import subprocess
import time

import trimesh

from core import pieza, storage

RAIZ_PROYECTO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYTHON_IA3D = r"C:\ia3d_venv\Scripts\python.exe"

CALIDADES_LOCAL = {
    "Rápida (más rústica, ~1-3 min en CPU)": 16,
    "Normal (~3-7 min en CPU)": 24,
    "Alta (más fiel, ~8-15 min en CPU)": 48,
}

PROVEEDORES_API = {
    "Tripo3D": {
        "url": "https://api.tripo3d.ai/v2/openapi/task",
        "doc": "https://platform.tripo3d.ai/docs",
    },
    "Meshy": {
        "url": "https://api.meshy.ai/openapi/v1/image-to-3d",
        "doc": "https://docs.meshy.ai",
    },
}


def entorno_local_disponible():
    """True si ya se corrió setup_ia3d.bat (existe el venv chico)."""
    return os.path.exists(PYTHON_IA3D)


def generar_local(ruta_imagen, carpeta_salida="output", ancho_mm=80.0,
                   pasos=32, quitar_fondo=True, timeout_seg=1800):
    """Corre core/ia3d_worker.py en el venv de IA (subprocess, no
    import — ese venv tiene torch/diffusers, este no) y devuelve el
    mismo shape de dict que generators/esculturas.py::generar(), para
    que la página los pueda tratar igual.

    Puede tardar bastante (CPU, sin GPU) — `timeout_seg` corta la
    espera si algo se cuelga. La primera vez además descarga los pesos
    del modelo (~1-2GB) desde Hugging Face, así que tarda más."""
    if not entorno_local_disponible():
        raise RuntimeError(
            f"Falta el entorno de IA local — corré setup_ia3d.bat una vez "
            f"(crea {PYTHON_IA3D}, ~3-4GB en disco)."
        )
    if not os.path.exists(ruta_imagen):
        raise FileNotFoundError(f"no encuentro la imagen: {ruta_imagen}")

    os.makedirs(carpeta_salida, exist_ok=True)

    # Cleanup: borrar imágenes subidas viejas (>7 días) para liberar espacio
    storage.limpiar_temporales(carpeta_salida, dias_antiguedad=7)
    base_nombre = pieza.nombre_archivo(
        os.path.splitext(os.path.basename(ruta_imagen))[0], default="estatua"
    )
    ruta_stl = os.path.join(carpeta_salida, f"estatua_{base_nombre}.stl")
    ruta_png = os.path.join(carpeta_salida, f"estatua_{base_nombre}_preview.png")

    comando = [
        PYTHON_IA3D, "-m", "core.ia3d_worker",
        os.path.abspath(ruta_imagen), os.path.abspath(ruta_stl), os.path.abspath(ruta_png),
        "--ancho_mm", str(ancho_mm),
        "--pasos", str(pasos),
        "--quitar_fondo", "1" if quitar_fondo else "0",
        "--suavizado", "1",
        "--decimation", "1",
    ]
    inicio = time.time()
    resultado = subprocess.run(
        comando, cwd=RAIZ_PROYECTO, capture_output=True, text=True,
        timeout=timeout_seg,
    )
    segundos = time.time() - inicio

    if resultado.returncode != 0:
        detalle = (resultado.stderr or resultado.stdout or "sin detalle").strip().splitlines()
        raise RuntimeError("falló la generación IA: " + (detalle[-1] if detalle else "error desconocido"))

    malla = trimesh.load(ruta_stl)
    ancho_final_mm, alto_final_mm, profundo_final_mm, entra_a1, mensaje_a1 = pieza.chequear_desde_malla(
        malla, nombre="estatua"
    )

    avisos = []
    if not malla.is_watertight:
        avisos.append("No quedó perfectamente watertight, revisala antes de imprimir.")
    info = [
        f"Generado con IA local (Shap-E, {pasos} pasos) en {segundos:.0f}s — "
        f"la fidelidad a la pose/proporciones original depende del modelo, no es exacta."
    ]

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


def generar_api(ruta_imagen, api_key, proveedor="Tripo3D", carpeta_salida="output", ancho_mm=80.0):
    """Scaffold para generar por API externa paga (mejor calidad que
    el modelo local). NO implementado todavía — cada proveedor tiene
    su propio flujo (crear tarea -> poll de estado -> descargar
    resultado) y requiere una cuenta con crédito. Lanza
    NotImplementedError con instrucciones; se completa cuando el
    usuario elija proveedor y tenga la key.

    La `api_key` nunca se guarda en disco ni se commitea — vive solo en
    st.session_state mientras dura la sesión de Streamlit (ver
    pages/5_🗿_Esculturas.py)."""
    if proveedor not in PROVEEDORES_API:
        raise ValueError(f"proveedor desconocido: {proveedor!r} (opciones: {list(PROVEEDORES_API)})")
    if not api_key:
        raise ValueError("falta la API key")

    raise NotImplementedError(
        f"Integración con {proveedor} todavía no está armada. "
        f"Doc del proveedor: {PROVEEDORES_API[proveedor]['doc']}"
    )
