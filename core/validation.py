#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/validation.py
------------------
Validación de inputs, constraints, y errores user-friendly para sculpture gen.
"""

import os
from pathlib import Path


class ValidationError(Exception):
    """Error de validación con mensaje user-friendly."""
    pass


def validar_imagen(ruta_imagen: str, max_mb: float = 50.0) -> None:
    """Validar imagen: existe, formato soportado, tamaño."""
    if not ruta_imagen or not os.path.exists(ruta_imagen):
        raise ValidationError("Imagen no encontrada. Subí un archivo PNG o JPG.")

    ext = Path(ruta_imagen).suffix.lower()
    if ext not in [".png", ".jpg", ".jpeg"]:
        raise ValidationError(f"Formato {ext} no soportado. Usá PNG o JPG.")

    tamaño_mb = os.path.getsize(ruta_imagen) / (1024**2)
    if tamaño_mb > max_mb:
        raise ValidationError(f"Imagen muy grande ({tamaño_mb:.1f}MB). Máximo {max_mb}MB.")

    if tamaño_mb < 0.05:
        raise ValidationError("Imagen demasiado chica (<50KB). Usá algo más detallado.")


def validar_dimensiones_relieve(ancho_mm: float, alto_mm: float,
                                espesor_base_mm: float, relieve_mm: float) -> None:
    """Validar parámetros de relieve."""
    if ancho_mm < 20 or ancho_mm > 500:
        raise ValidationError("Ancho debe estar entre 20 y 500 mm.")
    if alto_mm < 20 or alto_mm > 500:
        raise ValidationError("Alto debe estar entre 20 y 500 mm.")
    if espesor_base_mm < 0.5 or espesor_base_mm > 20:
        raise ValidationError("Espesor de base debe estar entre 0.5 y 20 mm.")
    if relieve_mm < 0.5 or relieve_mm > 50:
        raise ValidationError("Relieve debe estar entre 0.5 y 50 mm.")

    total_z = espesor_base_mm + relieve_mm
    if total_z > 100:
        raise ValidationError(f"Altura total ({total_z:.1f}mm) muy grande. Máximo 100mm.")


def validar_dimensiones_estatua(ancho_mm: float) -> None:
    """Validar parámetros de estatua 3D."""
    if ancho_mm < 20 or ancho_mm > 500:
        raise ValidationError("Ancho debe estar entre 20 y 500 mm.")


def avisos_en_relieve(ancho_mm: float, alto_mm: float, suavizado_px: float) -> list:
    """Generar avisos (no errores) basados en parámetros."""
    avisos = []

    if ancho_mm > 200 and alto_mm > 200:
        avisos.append(
            "⚠️ Relieve muy grande (>200x200mm). Verificá que tu impresora aguante."
        )

    if suavizado_px == 0:
        avisos.append(
            "⚠️ Suavizado deshabilitado. Si la imagen tiene ruido JPG, "
            "el relieve puede quedar con picos feos."
        )

    if suavizado_px > 3:
        avisos.append(
            "⚠️ Suavizado muy alto. Podrías perder detalles finos."
        )

    return avisos


def avisos_en_estatua(pasos: int) -> list:
    """Generar avisos para estatua 3D."""
    avisos = []

    if pasos < 20:
        avisos.append(
            "⚠️ Muy pocos pasos. La estatua podría quedar rústica/incompleta."
        )

    if pasos > 60:
        avisos.append(
            "⚠️ Muchos pasos. Esto tardará 20+ minutos en CPU. "
            "Probá con 'Normal' primero para validar el encuadre."
        )

    return avisos
