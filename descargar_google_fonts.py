#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Descargar fuentes cursivas de Google Fonts"""

import os
import requests
from pathlib import Path

FUENTES = {
    "Dancing Script": "Dancing+Script",
    "Caveat": "Caveat",
    "Permanent Marker": "Permanent+Marker",
    "Satisfy": "Satisfy",
    "Allura": "Allura",
    "Handlee": "Handlee",
    "Courgette": "Courgette",
    "Aloha": "Aloha",
    "Playpen Sans": "Playpen+Sans",
    "Fredoka": "Fredoka",
    "Cinzel": "Cinzel",
}

CARPETA = "fonts/curadas"
os.makedirs(CARPETA, exist_ok=True)

print("Descargando fuentes cursivas de Google Fonts...\n")
descargadas = 0

for nombre, query in FUENTES.items():
    archivo = nombre.lower().replace(" ", "_") + ".ttf"
    ruta = os.path.join(CARPETA, archivo)

    if os.path.exists(ruta):
        print(f"[OK] {nombre} ya existe")
        continue

    url = f"https://fonts.google.com/download?family={query}"
    try:
        print(f"[DL] {nombre}...", end=" ", flush=True)
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            with open(ruta, "wb") as f:
                f.write(resp.content)
            size_kb = len(resp.content) // 1024
            print(f"OK ({size_kb}KB)")
            descargadas += 1
        else:
            print(f"FAIL ({resp.status_code})")
    except Exception as e:
        print(f"FAIL")

print(f"\nDescargadas {descargadas} fuentes. Listo.")
