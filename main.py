#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================================
  CARTEL MAKER · menú principal
  ---------------------------------------------------------------------------
  Menú interactivo que descubre automáticamente los generadores disponibles
  en generators/ y deja elegir cuál correr.

  Cómo agregar un generador nuevo:
    1) Crear generators/mi_generador.py
    2) Definir en ese archivo:
         NOMBRE       = "Nombre corto para el menú"
         DESCRIPCION  = "Una línea explicando qué hace"
         def ejecutar(): ...   # pregunta parámetros, genera, imprime avisos
    3) Listo — main.py lo va a listar solo, no hace falta tocar este archivo.

  USO:
    python main.py
============================================================================
"""

import importlib
import pkgutil
import sys

# En Windows la consola puede venir con una codepage vieja (cp1252, etc.)
# que no sabe imprimir ✓/⚠/·. Forzamos UTF-8 para que el menú nunca crashee
# por eso (en la peor terminal se van a ver mal, pero no corta la ejecución).
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

import generators


def _descubrir_generadores():
    """Importa todos los módulos de generators/ y devuelve los que
    cumplen el contrato (NOMBRE, DESCRIPCION, ejecutar)."""
    encontrados = []
    for info in pkgutil.iter_modules(generators.__path__):
        modulo = importlib.import_module(f"generators.{info.name}")
        if all(hasattr(modulo, attr) for attr in ("NOMBRE", "DESCRIPCION", "ejecutar")):
            encontrados.append(modulo)
        else:
            print(f"  (aviso: generators/{info.name}.py no cumple el contrato, se ignora)")
    return encontrados


def _elegir(generadores):
    print("\n=== Cartel Maker ===")
    for i, g in enumerate(generadores, 1):
        print(f"  {i}) {g.NOMBRE} — {g.DESCRIPCION}")
    print("  0) Salir")

    eleccion = input("\nElegí una opción: ").strip()
    if eleccion == "0":
        return None
    try:
        idx = int(eleccion) - 1
        if 0 <= idx < len(generadores):
            return generadores[idx]
    except ValueError:
        pass
    print("  Opción inválida.")
    return _elegir(generadores)


def main():
    generadores = _descubrir_generadores()
    if not generadores:
        print("No se encontró ningún generador en generators/.")
        sys.exit(1)

    while True:
        elegido = _elegir(generadores)
        if elegido is None:
            print("Listo, chau.")
            break
        elegido.ejecutar()


if __name__ == "__main__":
    main()
