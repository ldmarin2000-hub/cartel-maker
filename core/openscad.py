#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/openscad.py
------------------
Wrapper para invocar OpenSCAD en modo headless y renderizar un .scad
paramétrico (Customizer) a STL o a una vista previa PNG, pasando las
variables del Customizer por línea de comandos (-D).
"""

import os
import shutil
import subprocess

_CANDIDATOS_WINDOWS = [
    r"C:\Program Files\OpenSCAD\openscad.exe",
    r"C:\Program Files (x86)\OpenSCAD\openscad.exe",
]


def encontrar_ejecutable():
    """Busca el ejecutable de OpenSCAD: primero en el PATH, después en las
    rutas típicas de instalación en Windows."""
    exe = shutil.which("openscad")
    if exe:
        return exe
    for candidato in _CANDIDATOS_WINDOWS:
        if os.path.exists(candidato):
            return candidato
    raise FileNotFoundError(
        "No encuentro OpenSCAD instalado. Instalalo desde https://openscad.org/ "
        "(o agregalo al PATH) y volvé a intentar."
    )


def _formatear_valor(valor):
    """Convierte un valor de Python a la sintaxis de literal de OpenSCAD
    para pasarlo con -D nombre=valor."""
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if isinstance(valor, (int, float)):
        return str(valor)
    escapado = str(valor).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escapado}"'


def _correr(cmd, timeout):
    try:
        resultado = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"OpenSCAD tardó más de {timeout}s y lo aborté. Probá con una geometría más simple.")
    if resultado.returncode != 0:
        raise RuntimeError(f"OpenSCAD falló:\n{resultado.stderr or resultado.stdout}")


def exportar_stl(ruta_scad, parametros, ruta_stl, timeout=120):
    """Renderiza `ruta_scad` a un STL, pasando `parametros` (dict) como
    variables del Customizer."""
    cmd = [encontrar_ejecutable(), "-o", ruta_stl]
    for clave, valor in parametros.items():
        cmd += ["-D", f"{clave}={_formatear_valor(valor)}"]
    cmd.append(ruta_scad)
    _correr(cmd, timeout)


def exportar_preview(ruta_scad, parametros, ruta_png, ancho_px=900, alto_px=700, timeout=120):
    """Renderiza una vista previa PNG (con los colores del Customizer) de
    `ruta_scad`. OJO: no usar --render acá — el render CGAL completo de
    OpenSCAD ignora los color() y pinta todo del amarillo por defecto; el
    preview normal (OpenCSG) sí respeta los colores, que es lo que importa
    para esta vista previa."""
    cmd = [
        encontrar_ejecutable(), "-o", ruta_png,
        "--autocenter", "--viewall",
        f"--imgsize={ancho_px},{alto_px}",
    ]
    for clave, valor in parametros.items():
        cmd += ["-D", f"{clave}={_formatear_valor(valor)}"]
    cmd.append(ruta_scad)
    _correr(cmd, timeout)
