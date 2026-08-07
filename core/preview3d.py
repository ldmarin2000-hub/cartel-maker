#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/preview3d.py
--------------------
Visor 3D real (rotar/zoom/pan, luz + sombra) para reemplazar los
renders estáticos de matplotlib (2 ángulos fijos, sin poder mover la
cámara). Arma una escena trimesh a partir de los STL ya exportados,
la exporta a GLB en memoria (glTF binario, trimesh lo hace nativo) y
arma el HTML de un <model-viewer> (Google, BSD-3) con el modelo
embebido como data URI — offline, sin pedirle nada a internet: el
bundle de model-viewer vive vendoreado en assets/vendor/ (ver
`_leer_bundle_model_viewer`) y va inline en el propio HTML.

Este módulo es puro (no importa streamlit): devuelve un string HTML,
listo para pasarle a `st.components.v1.html(...)` desde la página. Así
lo puede usar main.py/CLI (para exportar el HTML a un archivo, por
ejemplo) sin arrastrar una dependencia de Streamlit.
"""

import base64
import os

import numpy as np
import trimesh

from core import colores

_RUTA_BUNDLE_MODEL_VIEWER = os.path.join(
    os.path.dirname(__file__), "..", "assets", "vendor", "model-viewer.min.js"
)

# Subsecuencia de la paleta curada (core/colores.py) elegida por contraste
# entre sí (no colores vecinos) — para que decoración tras decoración se
# distinga a simple vista en el visor, ciclando siempre la misma paleta que
# usa el resto de la app (no una lista de hex aparte inventada acá).
PALETA_DECORACIONES = [colores.hex_de(n) for n in (
    "Rojo", "Turquesa", "Amarillo", "Púrpura", "Verde Lima", "Celeste", "Rosa Fluor", "Dorado",
)]

_bundle_cache = None


def _leer_bundle_model_viewer():
    """Lee el bundle de model-viewer una sola vez (1MB+, no tiene sentido
    releerlo de disco en cada render)."""
    global _bundle_cache
    if _bundle_cache is None:
        with open(_RUTA_BUNDLE_MODEL_VIEWER, "r", encoding="utf-8") as f:
            _bundle_cache = f.read()
    return _bundle_cache


def _hex_a_rgba(color_hex, alpha=255):
    color_hex = color_hex.lstrip("#")
    return [int(color_hex[i:i + 2], 16) for i in (0, 2, 4)] + [alpha]


def _malla_coloreada(ruta_stl, color_hex):
    malla = trimesh.load(ruta_stl, force="mesh")
    rgba = _hex_a_rgba(color_hex)
    malla.visual = trimesh.visual.color.ColorVisuals(
        malla, face_colors=np.tile(rgba, (len(malla.faces), 1))
    )
    return malla


def armar_html_visor(piezas, height_px=480, fondo="#12141a"):
    """Arma el HTML de un visor 3D interactivo (rotar con el mouse, zoom
    con scroll, auto-rotate cuando está quieto) con todas las `piezas`
    ya en su posición real, cada una de su color — así se ve de una el
    resultado multicolor final, no solo la letra sola.

    `piezas`: lista de dicts `{"ruta_stl", "color" (hex, opcional),
    "nombre" (opcional), "offset" (opcional, (dx,dy,dz) mm)}` — se
    saltea silenciosamente cualquier pieza cuyo archivo no exista (por
    si se llama antes de exportar algo opcional). `offset` sirve para
    piezas que se exportan en su propio origen local (pensadas para
    imprimirse sueltas) pero cuya posición real ensamblada se conoce
    igual (ej. la tapa, que va pegada detrás del hueco) — sin offset,
    quedan en el origen tal cual las exportó el generador. Devuelve el
    HTML listo para `st.components.v1.html`, o None si ninguna pieza
    tenía archivo."""
    escena = trimesh.Scene()
    for i, p in enumerate(piezas):
        ruta = p.get("ruta_stl")
        if not ruta or not os.path.exists(ruta):
            continue
        if p.get("multicolor"):
            # STL combinado tipo AMS (varios cuerpos sueltos, sin fusionar): lo separamos
            # en memoria y le damos un color cíclico a cada uno, para que se distinga cada
            # pieza en el visor aunque venga en un solo archivo.
            cruda = trimesh.load(ruta, force="mesh")
            partes = cruda.split(only_watertight=False)
            for j, parte in enumerate(partes if len(partes) else [cruda]):
                rgba = _hex_a_rgba(color_decoracion(j))
                parte.visual = trimesh.visual.color.ColorVisuals(
                    parte, face_colors=np.tile(rgba, (len(parte.faces), 1))
                )
                escena.add_geometry(parte, node_name=f"{p.get('nombre') or f'pieza_{i}'}_{j}")
            continue
        color_hex = p.get("color", "#e8c88a")
        malla = _malla_coloreada(ruta, color_hex)
        if p.get("offset"):
            malla.apply_translation(p["offset"])
        escena.add_geometry(malla, node_name=p.get("nombre") or f"pieza_{i}")

    if len(escena.geometry) == 0:
        return None

    glb_b64 = base64.b64encode(escena.export(file_type="glb")).decode("ascii")
    bundle_js = _leer_bundle_model_viewer()

    return f"""
<script type="module">{bundle_js}</script>
<style>
  .visor3d-wrap {{ width: 100%; height: {height_px}px; border-radius: 10px; overflow: hidden; }}
  model-viewer {{ width: 100%; height: 100%; background: {fondo}; }}
</style>
<div class="visor3d-wrap">
  <model-viewer
      src="data:model/gltf-binary;base64,{glb_b64}"
      camera-controls
      auto-rotate
      rotation-per-second="16deg"
      shadow-intensity="1"
      exposure="1.15"
      environment-image="neutral"
      interaction-prompt="none">
  </model-viewer>
</div>
"""


def color_decoracion(indice):
    """Color hex para la decoración N (cíclico), así cada una se ve
    distinta en el visor sin que el usuario tenga que elegir color a
    mano — referencia visual, no implica un color de filamento real."""
    return PALETA_DECORACIONES[indice % len(PALETA_DECORACIONES)]


