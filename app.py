#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
app.py
--------
Punto de entrada de la app visual (Streamlit). Cada generador vive en su
propia página dentro de pages/, con el mismo criterio de descubrimiento
modular que main.py: para agregar un generador nuevo alcanza con sumar un
archivo a pages/.

USO:
    streamlit run app.py
"""

import streamlit as st

st.set_page_config(page_title="Cartel Maker", page_icon="🛠️", layout="wide")

st.title("🛠️ Cartel Maker")
st.write(
    "Generador de modelos 3D imprimibles para la Bambu Lab A1 (256×256×256 mm). "
    "Elegí un generador en el menú de la izquierda."
)

st.markdown(
    "| Generador | Estado |\n"
    "|---|---|\n"
    "| 🔥 Neón (texto trazado) | ✅ Funcionando |\n"
    "| 🔑 Llavero | ✅ Funcionando (Python puro, sin OpenSCAD, formas propias en SVG) |\n"
    "| ✂️ Letra iluminada de pie | ✅ Funcionando (Python puro) |\n"
    "| 🔀 Ambigrama (2 caras) | ✅ Funcionando (Python puro, formas propias en SVG) |\n"
    "| 🗿 Esculturas (relieve desde imagen) | ✅ Funcionando (Python puro, litofanía/relieve tallado) |\n"
)

st.caption("Los STL y preview generados quedan en la carpeta `output/`.")
