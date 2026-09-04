#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generators/topper.py
--------------------
Generador unificado de toppers para tortas, cupcakes, y decoraciones.
Integración 3D completa con STL export y previsualizaciones fieles
(texto real, fuente real, tipo de base real).
"""

import os
import base64
import numpy as np
import trimesh

from core import pieza, fuentes, colores

# shapely/matplotlib.textpath se importan on-demand (ver _shapely(), _textpath())
# en vez de al cargar el módulo: si el entorno tiene una instalación de shapely
# rota (pasó en Streamlit Cloud con 2.1.x — AttributeError en shapely.lib al
# importar), un import a nivel de módulo tumba TODA la página de Topper
# (incluidos Neón/LED/Acrílico, que no dependen de shapely). Así, solo falla
# — con un error controlado — el modo 3D en sí.
_sg = None
_so = None
_saf = None
_TextPath = None
_FontProperties = None
_texto2d_mod = None
_geometry_mod = None


def _shapely():
    global _sg, _so
    if _sg is None:
        import shapely.geometry as sg
        import shapely.ops as so
        _sg, _so = sg, so
    return _sg, _so


def _affinity():
    global _saf
    if _saf is None:
        import shapely.affinity as saf
        _saf = saf
    return _saf


def _textpath():
    global _TextPath, _FontProperties
    if _TextPath is None:
        from matplotlib.textpath import TextPath
        from matplotlib.font_manager import FontProperties
        _TextPath, _FontProperties = TextPath, FontProperties
    return _TextPath, _FontProperties


def _texto2d():
    # core.texto2d importa shapely a nivel de módulo -- mismo motivo que
    # arriba, se pospone el import para no tumbar la página entera.
    global _texto2d_mod
    if _texto2d_mod is None:
        from core import texto2d
        _texto2d_mod = texto2d
    return _texto2d_mod


def _geom():
    # core.geometry también importa shapely a nivel de módulo -- ídem.
    global _geometry_mod
    if _geometry_mod is None:
        from core import geometry
        _geometry_mod = geometry
    return _geometry_mod


_svg_import_mod = None


def _svg_import():
    # core.svg_import también importa shapely a nivel de módulo -- ídem.
    global _svg_import_mod
    if _svg_import_mod is None:
        from core import svg_import
        _svg_import_mod = svg_import
    return _svg_import_mod


_imagen_import_mod = None


def _imagen_import():
    # core.imagen_import también importa shapely a nivel de módulo -- ídem.
    global _imagen_import_mod
    if _imagen_import_mod is None:
        from core import imagen_import
        _imagen_import_mod = imagen_import
    return _imagen_import_mod

NOMBRE = "Topper (decoración para tortas)"
DESCRIPCION = "Toppers 3D, Neón, LED, Acrílico para tortas, cupcakes, postres."

CARPETA_SALIDA = "output"

# ---------------------------------------------------------------------------
# Catálogos
# ---------------------------------------------------------------------------

# Estilos visuales — controlan altura y "energía" de la silueta
ESTILOS = {
    "Minimalista":  {"altura_mm": 8,  "curva": 0.0},
    "Elegante":     {"altura_mm": 12, "curva": 0.15},
    "Divertido":    {"altura_mm": 15, "curva": 0.35},
    "Romántico":    {"altura_mm": 10, "curva": 0.2},
    "Moderno":      {"altura_mm": 11, "curva": 0.05},
    "Vintage":      {"altura_mm": 9,  "curva": 0.25},
    "Geométrico":   {"altura_mm": 13, "curva": 0.0},
    "Bohemio":      {"altura_mm": 10, "curva": 0.3},
}

# Formas de base disponibles (silueta de la placa/base)
FORMAS_BASE = ["Redonda", "Ovalada", "Cuadrada", "Rectangular"]

# Modos de base — cómo se apoya/inserta el topper en la torta, combinados
# con cada forma de FORMAS_BASE
MODOS_BASE = ["Plana (apoyada)", "Con palo (clavar en torta)", "Con figura arriba"]

# Catálogo completo de bases: cada forma × cada modo, más los dos casos
# especiales que no dependen de una silueta de placa (letras paradas sobre
# disco, y figura libre sin ninguna base) — así el usuario elige entre
# muchas combinaciones (redonda/ovalada/cuadrada/rectangular, con o sin
# palo, con o sin figura decorativa arriba) para potenciar la creatividad.
BASES = [f"{forma} — {modo}" for forma in FORMAS_BASE for modo in MODOS_BASE] + [
    "Redonda (letras paradas)",
    "Sin base (figura libre)",
]

# Temas/categoría — no cambian geometría pero orientan el diseño y presets
TEMAS = [
    "General", "Matrimonio", "Cumpleaños", "Fiesta", "Bebé / Baby Shower",
    "Graduación", "Aniversario", "Quince Años",
]

# Objetos decorativos que se pueden agregar sobre la base — cada uno tiene
# su propia geometría simplificada (ver _figura_decorativa), no todos son
# la misma esfera genérica.
OBJETOS_DECORATIVOS = [
    "Ninguno", "Flores", "Corazón", "Estrella", "Personaje/Figura",
    "Pareja/Novios", "Juguete", "Animal", "Símbolo",
]

# Marcos decorativos para el topper "Plano" — un aro fino alrededor del
# texto (ver _forma_marco). "Ninguno" deja el texto suelto.
FORMAS_MARCO = ["Ninguno", "Círculo", "Hexágono", "Pentágono", "SVG propio", "Imagen propia"]


def _parsear_base(base_tipo):
    """Descompone un valor de BASES en (forma, modo). Para los casos
    especiales (letras paradas / sin base) devuelve modo=None."""
    if " — " in base_tipo:
        forma, modo = base_tipo.split(" — ", 1)
        return forma, modo
    return base_tipo, None


def _fuente_por_defecto():
    """Primera fuente curada disponible, o None si no hay ninguna."""
    lista = fuentes.listar_fuentes()
    return lista[0][1] if lista else None


# ---------------------------------------------------------------------------
# Geometría auxiliar (primitivas trimesh en mm)
# ---------------------------------------------------------------------------

def _cilindro(radio, altura, z0=0.0, segmentos=20, radio_top_factor=1.0):
    """Cilindro (o tronco de cono si radio_top_factor != 1) sólido, watertight."""
    theta = np.linspace(0, 2 * np.pi, segmentos, endpoint=False)
    verts = []
    for angle in theta:
        x, y = radio * np.cos(angle), radio * np.sin(angle)
        verts.append([x, y, z0])
        verts.append([x * radio_top_factor, y * radio_top_factor, z0 + altura])
    idx_bottom = len(verts)
    verts.append([0, 0, z0])
    idx_top = len(verts)
    verts.append([0, 0, z0 + altura])

    faces = []
    n = segmentos
    for i in range(n):
        j = (i + 1) % n
        faces.append([i * 2, j * 2, idx_bottom])
        faces.append([i * 2 + 1, idx_top, j * 2 + 1])
        faces.append([i * 2, j * 2, j * 2 + 1])
        faces.append([i * 2, j * 2 + 1, i * 2 + 1])

    return np.array(verts, dtype=np.float64), faces


def _esfera(radio, centro_z, segmentos=12):
    malla = trimesh.creation.icosphere(subdivisions=2, radius=radio)
    malla.apply_translation([0, 0, centro_z])
    return malla


def _texto_a_poligono(texto, fuente_ttf=None, tam_fuente=100):
    """Convierte `texto` en un shapely (Multi)Polygon con agujeros reales
    (la "o" tiene hueco, etc.) usando los contornos vectoriales de la
    fuente elegida — texto real, no una aproximación de bloques."""
    sg, so = _shapely()
    TextPath, FontProperties = _textpath()
    try:
        fp = FontProperties(fname=fuente_ttf) if fuente_ttf else FontProperties()
        tp = TextPath((0, 0), texto, size=tam_fuente, prop=fp)
    except Exception:
        tp = TextPath((0, 0), texto, size=tam_fuente, prop=FontProperties())

    contornos = [sg.Polygon(p) for p in tp.to_polygons() if len(p) >= 3]
    contornos = [p for p in contornos if p.is_valid and p.area > 1e-6]
    if not contornos:
        return None

    contornos.sort(key=lambda p: p.area, reverse=True)
    usados = [False] * len(contornos)
    resultado = []
    for i, p in enumerate(contornos):
        if usados[i]:
            continue
        huecos = []
        for j in range(i + 1, len(contornos)):
            if usados[j]:
                continue
            if p.contains(contornos[j]):
                huecos.append(list(contornos[j].exterior.coords))
                usados[j] = True
        resultado.append(sg.Polygon(p.exterior.coords, huecos))

    return so.unary_union(resultado)


def _texto_a_malla3d(texto, altura, fuente_ttf=None, z0=0.0, grosor=None):
    if grosor is None:
        grosor = max(4.0, altura * 0.4)  # letras "robustas" — se leen bien desde varios ángulos, no una placa fina
    """Malla 3D del texto (letras reales, con sus huecos) en MI convención
    local: X=ancho, Y=grosor del material (parado, mirando hacia +Y), Z=altura
    visual — apoyada de pie desde z0 hasta z0+altura, centrada en X e Y=0.
    None si el texto queda vacío (ej. solo espacios)."""
    texto_limpio = (texto or "").strip() or "Topper"
    # tam_fuente fijo de referencia — el tamaño final se ajusta reescalando
    # a `altura`, así todas las fuentes quedan a la misma altura visual.
    multi = _texto_a_poligono(texto_limpio, fuente_ttf, tam_fuente=100)
    if multi is None or multi.is_empty:
        return None

    piezas = multi.geoms if hasattr(multi, "geoms") else [multi]
    mallas = [trimesh.creation.extrude_polygon(p, height=grosor)
              for p in piezas if p.is_valid and p.area > 0]
    if not mallas:
        return None

    # malla: X=ancho(glifo), Y=alto(glifo), Z=grosor(extrusión) tal como sale
    # de extrude_polygon — reescalo X/Y para que el alto visual sea `altura`.
    malla = trimesh.util.concatenate(mallas)
    alto_actual = max(malla.extents[1], 1e-9)
    factor = altura / alto_actual
    malla.apply_scale([factor, factor, 1.0])

    # Roto 90° en X: (x,y,z) -> (x, -z, y) — el alto del glifo (viejo Y) pasa
    # a ser la altura vertical real (Z), y el grosor (viejo Z) pasa a Y
    # (profundidad, mirando hacia la cámara "Frente").
    R = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]], dtype=float)
    T4 = np.eye(4)
    T4[:3, :3] = R
    malla.apply_transform(T4)

    bounds = malla.bounds
    cx = (bounds[0][0] + bounds[1][0]) / 2
    cy = (bounds[0][1] + bounds[1][1]) / 2
    z_min = bounds[0][2]
    malla.apply_translation([-cx, -cy, z0 - z_min])
    return malla


def _bloque(ancho, profundidad, altura, cx=0.0, cy=0.0, z0=0.0):
    caja = trimesh.creation.box(extents=[ancho, profundidad, altura])
    caja.apply_translation([cx, cy, z0 + altura / 2])
    return caja


def _forma_base(forma, radio, altura, z0=0.0, factor_ovalo=0.62):
    """Malla de la base según su silueta — Redonda/Ovalada/Cuadrada/
    Rectangular — todas dimensionadas por un único `radio` (mitad del
    lado/diámetro mayor), para que las cuatro se puedan pedir con el mismo
    parámetro de tamaño."""
    if forma == "Ovalada":
        v, f = _cilindro(radio, altura, z0=z0, segmentos=28)
        malla = trimesh.Trimesh(vertices=v, faces=np.array(f, dtype=np.int64), process=True)
        malla.apply_scale([1.0, factor_ovalo, 1.0])
        return malla
    if forma == "Cuadrada":
        lado = radio * 1.7
        return _bloque(lado, lado, altura, z0=z0)
    if forma == "Rectangular":
        return _bloque(radio * 2.1, radio * 1.3, altura, z0=z0)
    # "Redonda" (default)
    v, f = _cilindro(radio, altura, z0=z0, segmentos=28)
    return trimesh.Trimesh(vertices=v, faces=np.array(f, dtype=np.int64), process=True)


def _figura_decorativa(tipo_objeto, radio, centro_z):
    """Malla simplificada según el objeto decorativo elegido — cada tipo
    tiene su propia silueta (no todos son la misma esfera genérica)."""
    if tipo_objeto == "Corazón":
        # Dos esferas juntas arriba + cono invertido abajo, aproximando un corazón
        lobulo1 = trimesh.creation.icosphere(subdivisions=2, radius=radio * 0.62)
        lobulo1.apply_translation([-radio * 0.42, 0, centro_z + radio * 0.25])
        lobulo2 = trimesh.creation.icosphere(subdivisions=2, radius=radio * 0.62)
        lobulo2.apply_translation([radio * 0.42, 0, centro_z + radio * 0.25])
        punta = trimesh.creation.cone(radius=radio * 0.95, height=radio * 1.3, sections=16)
        R = trimesh.transformations.rotation_matrix(np.pi, [1, 0, 0])
        punta.apply_transform(R)
        punta.apply_translation([0, 0, centro_z - radio * 0.05])
        return trimesh.util.concatenate([lobulo1, lobulo2, punta])
    if tipo_objeto == "Estrella":
        # Extrude de un polígono de estrella de 5 puntas
        sg, _ = _shapely()
        n_puntas = 5
        angs = np.linspace(0, 2 * np.pi, n_puntas * 2, endpoint=False) + np.pi / 2
        pts = []
        for i, a in enumerate(angs):
            r = radio if i % 2 == 0 else radio * 0.42
            pts.append((r * np.cos(a), r * np.sin(a)))
        poly = sg.Polygon(pts)
        malla = trimesh.creation.extrude_polygon(poly, height=radio * 0.6)
        malla.apply_translation([0, 0, centro_z - radio * 0.3])
        return malla
    if tipo_objeto == "Pareja/Novios":
        # Dos figuras simples (cono+esfera cada una) una junto a la otra
        piezas = []
        for signo in (-1, 1):
            cuerpo = trimesh.creation.cone(radius=radio * 0.45, height=radio * 1.1, sections=16)
            cuerpo.apply_translation([signo * radio * 0.5, 0, centro_z - radio * 0.55])
            cabeza = trimesh.creation.icosphere(subdivisions=2, radius=radio * 0.32)
            cabeza.apply_translation([signo * radio * 0.5, 0, centro_z + radio * 0.5])
            piezas += [cuerpo, cabeza]
        return trimesh.util.concatenate(piezas)
    if tipo_objeto in ("Personaje/Figura", "Juguete", "Animal"):
        # Cuerpo (cono) + cabeza (esfera) — silueta genérica de figura de pie
        cuerpo = trimesh.creation.cone(radius=radio * 0.6, height=radio * 1.3, sections=16)
        cuerpo.apply_translation([0, 0, centro_z - radio * 0.55])
        cabeza = trimesh.creation.icosphere(subdivisions=2, radius=radio * 0.45)
        cabeza.apply_translation([0, 0, centro_z + radio * 0.5])
        return trimesh.util.concatenate([cuerpo, cabeza])
    if tipo_objeto == "Flores":
        # Centro + 5 pétalos (esferas chicas alrededor)
        centro = trimesh.creation.icosphere(subdivisions=2, radius=radio * 0.4)
        centro.apply_translation([0, 0, centro_z])
        piezas = [centro]
        for a in np.linspace(0, 2 * np.pi, 5, endpoint=False):
            petalo = trimesh.creation.icosphere(subdivisions=1, radius=radio * 0.4)
            petalo.apply_translation([radio * 0.55 * np.cos(a), radio * 0.55 * np.sin(a), centro_z])
            piezas.append(petalo)
        return trimesh.util.concatenate(piezas)
    # "Símbolo" y default: esfera lisa
    return _esfera(radio, centro_z=centro_z)


def _combinar(mallas):
    """Concatena mallas (sin booleana real, solo unión de geometría para
    export STL — suficiente para imprimir como piezas fusionadas visualmente)."""
    validas = [m for m in mallas if m is not None and len(m.vertices) > 0]
    if not validas:
        raise ValueError("No hay geometría para combinar")
    return trimesh.util.concatenate(validas)


# Rotación que convierte "mi arriba" (eje Z, como en un molde/cortante visto
# desde arriba) al eje "arriba" que espera el visor glTF/model-viewer (eje Y)
# — la misma matriz que usa core/mesh3d.py para el lado "de frente" — así la
# base queda abajo y el topper arriba en la vista "Frente" del visor.
_MATRIZ_ARRIBA_VISOR = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], dtype=float)


def _orientar_para_visor(malla):
    T4 = np.eye(4)
    T4[:3, :3] = _MATRIZ_ARRIBA_VISOR
    malla.apply_transform(T4)
    return malla


# ---------------------------------------------------------------------------
# Toppers 3D
# ---------------------------------------------------------------------------

def generar_3d(texto, tamaño_mm=80, estilo="Elegante", color="Dorado",
               base_tipo="Redonda — Plana (apoyada)", material="PLA",
               tema="General", objeto_decorativo="Ninguno", fuente=None):
    """Generar topper 3D imprimible con STL export.

    `base_tipo`: uno de BASES — cambia la geometría real generada.
    `objeto_decorativo`: agrega un elemento esférico decorativo sobre la base
    cuando corresponde (representa flores/figura/etc. de forma simplificada).
    """
    os.makedirs(CARPETA_SALIDA, exist_ok=True)

    config = ESTILOS.get(estilo, ESTILOS["Elegante"])
    altura_mm = config["altura_mm"]
    texto_valido = (texto or "").strip() or "Topper"

    piezas = []
    forma, modo = _parsear_base(base_tipo)
    base_alt = 3

    if base_tipo == "Redonda (letras paradas)":
        # Disco de base + el texto real parado sobre él (cada letra, con sus huecos reales)
        texto3d = _texto_a_malla3d(texto_valido, altura=altura_mm, fuente_ttf=fuente, z0=base_alt)
        ancho_final = texto3d.extents[0] if texto3d is not None else 40
        base_radio = max(20, ancho_final * 0.65)
        piezas.append(_forma_base("Redonda", base_radio, base_alt, z0=0))
        if texto3d is not None:
            piezas.append(texto3d)

    elif base_tipo == "Sin base (figura libre)":
        # Solo el texto, parado directo en el piso — sin ninguna base
        texto3d = _texto_a_malla3d(texto_valido, altura=altura_mm, fuente_ttf=fuente, z0=0)
        if texto3d is not None:
            piezas.append(texto3d)

    elif modo == "Con palo (clavar en torta)":
        # Palito delgado que se clava en la torta + placa (con la forma
        # elegida) + texto real parado encima
        texto3d = _texto_a_malla3d(texto_valido, altura=altura_mm, fuente_ttf=fuente, z0=0)
        ancho_final = texto3d.extents[0] if texto3d is not None else 40

        palo_radio, palo_largo = 1.5, 55
        v, f = _cilindro(palo_radio, palo_largo, z0=-palo_largo)
        piezas.append(trimesh.Trimesh(vertices=v, faces=np.array(f, dtype=np.int64), process=True))

        placa_radio = max(16, ancho_final * 0.55)
        piezas.append(_forma_base(forma, placa_radio, base_alt, z0=0))

        if texto3d is not None:
            texto3d.apply_translation([0, 0, base_alt])
            piezas.append(texto3d)

    elif modo == "Con figura arriba":
        # Texto parado y visible, centrado en la base + tallo con la figura
        # decorativa elegida al costado en X (eje que la rotación final no
        # toca), representando el objeto elegido (flores/personaje/etc.)
        texto3d = _texto_a_malla3d(texto_valido, altura=altura_mm, fuente_ttf=fuente, z0=0)
        ancho_final = texto3d.extents[0] if texto3d is not None else 40
        base_radio = max(24, ancho_final * 0.85)

        piezas.append(_forma_base(forma, base_radio, base_alt, z0=0))

        if texto3d is not None:
            texto3d.apply_translation([0, 0, base_alt])
            piezas.append(texto3d)

        x_fig = ancho_final / 2 + base_radio * 0.25
        v, f = _cilindro(2.5, 12, z0=base_alt)
        tallo = trimesh.Trimesh(vertices=v, faces=np.array(f, dtype=np.int64), process=True)
        tallo.apply_translation([x_fig, 0, 0])
        piezas.append(tallo)
        objeto_figura = objeto_decorativo if objeto_decorativo != "Ninguno" else "Símbolo"
        figura = _figura_decorativa(objeto_figura, altura_mm * 0.6, centro_z=base_alt + 12 + altura_mm * 0.6)
        figura.apply_translation([x_fig, 0, 0])
        piezas.append(figura)

    else:  # "Plana (apoyada)" (o forma no reconocida) — base con la forma elegida + texto encima
        texto3d = _texto_a_malla3d(texto_valido, altura=altura_mm, fuente_ttf=fuente, z0=base_alt)
        ancho_final = texto3d.extents[0] if texto3d is not None else 40
        base_radio = max(15, ancho_final * 0.6)
        piezas.append(_forma_base(forma, base_radio, base_alt, z0=0))
        if texto3d is not None:
            piezas.append(texto3d)

    # Objeto decorativo adicional (con la silueta elegida) al costado del
    # texto — independiente de la base, salvo en "Con figura arriba" donde
    # el objeto YA es la figura central del tallo.
    if objeto_decorativo != "Ninguno" and modo != "Con figura arriba":
        ancho_texto = piezas[-1].extents[0] if piezas else 40
        z0_obj = 0 if base_tipo == "Sin base (figura libre)" else base_alt
        r_obj = altura_mm * 0.35
        x_obj = ancho_texto / 2 + r_obj + 4
        figura_dec = _figura_decorativa(objeto_decorativo, r_obj, centro_z=z0_obj + r_obj)
        figura_dec.apply_translation([x_obj, 0, 0])
        piezas.append(figura_dec)

    malla = _combinar(piezas)
    malla.fix_normals()
    malla = _orientar_para_visor(malla)
    malla.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0]))

    # Escalar para que encaje en tamaño deseado (ancho real del diseño)
    extents_xy = max(malla.extents[0], malla.extents[2], 1e-6)
    escala = tamaño_mm / extents_xy
    malla.apply_scale(escala)

    base_nombre = pieza.nombre_archivo(texto, default="topper")
    base_slug = "".join(c if c.isalnum() else "_" for c in base_tipo).strip("_")
    ruta_stl = os.path.join(CARPETA_SALIDA, f"topper_{base_nombre}_{estilo}_{base_slug}.stl")
    malla.export(ruta_stl)

    resultado = {
        "tipo": "3d",
        "texto": texto,
        "tamaño_mm": tamaño_mm,
        "estilo": estilo,
        "material": material,
        "color": color,
        "base": base_tipo,
        "tema": tema,
        "objeto_decorativo": objeto_decorativo,
        "fuente": fuente,
        "ruta_stl": ruta_stl,
        "vertices": len(malla.vertices),
        "caras": len(malla.faces),
        "watertight": malla.is_watertight,
        "estado": "✓ Generado",
    }
    return resultado


# ---------------------------------------------------------------------------
# Toppers Neón
# ---------------------------------------------------------------------------

def generar_neon(texto, tamaño_mm=80, tipo_led="Flexible (frío)", grosor_tubo=10, fuente=None):
    """Generar topper Neón LED flexible con DXF."""
    os.makedirs(CARPETA_SALIDA, exist_ok=True)

    largo_texto_mm = len(texto) * 6 + 20
    altura_tubo = grosor_tubo + 2

    dxf_content = f"""SECTION
  2
ENTITIES
  0
LWPOLYLINE
  5
1F
100
AcDbEntity
  8
TUBO_LED
100
AcDbLwPolyline
 90
4
 70
1
 10
0.0
 20
0.0
 10
{largo_texto_mm}
 20
0.0
 10
{largo_texto_mm}
 20
{altura_tubo}
 10
0.0
 20
{altura_tubo}
ENDSEC
  0
EOF"""

    base_nombre = pieza.nombre_archivo(texto, default="topper")
    ruta_dxf = os.path.join(CARPETA_SALIDA, f"neon_{base_nombre}_{tipo_led.replace(' ', '_')}.dxf")
    with open(ruta_dxf, "w", encoding="utf-8") as f:
        f.write(dxf_content)

    consumo_w = (largo_texto_mm / 1000) * 1.5
    voltaje = "24V" if tipo_led.startswith("Flexible") else "5V"

    return {
        "tipo": "neon",
        "texto": texto,
        "tamaño_mm": tamaño_mm,
        "tipo_led": tipo_led,
        "grosor_tubo": grosor_tubo,
        "largo_tubo_mm": largo_texto_mm,
        "voltaje": voltaje,
        "consumo_w": round(consumo_w, 1),
        "fuente": fuente,
        "ruta_dxf": ruta_dxf,
        "estado": "✓ Generado",
    }


# ---------------------------------------------------------------------------
# Toppers LED
# ---------------------------------------------------------------------------

def generar_led(texto, tamaño_mm=80, material="PLA", efecto="Fijo", con_bateria=True, fuente=None):
    """Generar topper LED con estructura e integración LED."""
    os.makedirs(CARPETA_SALIDA, exist_ok=True)

    piezas = []
    v, f = _cilindro(20, 4, z0=0)
    piezas.append(trimesh.Trimesh(vertices=v, faces=np.array(f, dtype=np.int64), process=True))
    v, f = _cilindro(28, 20, z0=4, radio_top_factor=0.9)
    piezas.append(trimesh.Trimesh(vertices=v, faces=np.array(f, dtype=np.int64), process=True))

    malla = _combinar(piezas)
    malla.fix_normals()

    extents_xy = max(malla.extents[0], malla.extents[1], 1e-6)
    malla.apply_scale(tamaño_mm / extents_xy)

    base_nombre = pieza.nombre_archivo(texto, default="topper")
    ruta_stl = os.path.join(CARPETA_SALIDA, f"led_{base_nombre}_{efecto}.stl")
    malla.export(ruta_stl)

    consumo_w = {"Fijo": 5.0, "Parpadeo": 4.5, "Secuencial": 5.5, "Arcoíris": 6.0}.get(efecto, 5.0)
    voltaje = "5V USB" if con_bateria else "12V"

    return {
        "tipo": "led",
        "texto": texto,
        "tamaño_mm": tamaño_mm,
        "material": material,
        "efecto": efecto,
        "con_bateria": con_bateria,
        "consumo_w": consumo_w,
        "voltaje": voltaje,
        "fuente": fuente,
        "ruta_stl": ruta_stl,
        "vertices": len(malla.vertices),
        "caras": len(malla.faces),
        "estado": "✓ Generado",
    }


# ---------------------------------------------------------------------------
# Toppers Acrílico
# ---------------------------------------------------------------------------

def generar_acrilico(texto, tamaño_mm=80, espesor_mm=3, acabado="Transparente", fuente=None):
    """Generar topper Acrílico para grabado láser con DXF."""
    os.makedirs(CARPETA_SALIDA, exist_ok=True)

    ancho = tamaño_mm + 20
    alto = int(tamaño_mm * 0.6) + 10
    radio_esquina = 5

    dxf_content = f"""SECTION
  2
ENTITIES
  0
LWPOLYLINE
  5
1F
100
AcDbEntity
  8
CORTE
100
AcDbLwPolyline
 90
4
 70
1
 10
{radio_esquina}
 20
0.0
 10
{ancho - radio_esquina}
 20
0.0
 10
{ancho}
 20
{radio_esquina}
 10
{ancho}
 20
{alto - radio_esquina}
 10
{ancho - radio_esquina}
 20
{alto}
 10
{radio_esquina}
 20
{alto}
 10
0.0
 20
{alto - radio_esquina}
 10
0.0
 20
{radio_esquina}
  0
TEXT
  5
20
100
AcDbEntity
  8
GRABADO
100
AcDbText
 10
{ancho/2}
 20
{alto/2}
 40
6.0
  1
{texto}
ENDSEC
  0
EOF"""

    base_nombre = pieza.nombre_archivo(texto, default="topper")
    ruta_dxf = os.path.join(CARPETA_SALIDA, f"acrilico_{base_nombre}_{acabado.replace(' ', '_')}.dxf")
    with open(ruta_dxf, "w", encoding="utf-8") as f:
        f.write(dxf_content)

    potencia_base = espesor_mm * 20
    potencia_grabado = {"Espejo": potencia_base * 0.8, "Transparente": potencia_base * 1.0,
                        "Mate": potencia_base * 1.2, "Color": potencia_base * 0.9}.get(acabado, potencia_base)
    perimetro = 2 * (ancho + alto)
    tiempo_corte = perimetro / 5

    return {
        "tipo": "acrilico",
        "texto": texto,
        "tamaño_mm": tamaño_mm,
        "espesor_mm": espesor_mm,
        "acabado": acabado,
        "ancho": ancho,
        "alto": alto,
        "fuente": fuente,
        "potencia_w": int(potencia_grabado),
        "tiempo_corte_s": round(tiempo_corte, 1),
        "ruta_dxf": ruta_dxf,
        "estado": "✓ Generado",
    }


# ---------------------------------------------------------------------------
# Toppers Planos (recortados: 1-3 líneas de texto, marco decorativo
# opcional, letras conectadas con puentes finos, palo para clavar)
# ---------------------------------------------------------------------------

def _poligono_regular(cx, cy, radio, n_lados, rotacion=np.pi / 2):
    """Polígono regular (hexágono, pentágono, etc.) centrado en (cx, cy),
    circunradio `radio`. `rotacion` en radianes (default: una punta hacia
    arriba, como en los marcos de los toppers de referencia)."""
    sg, _ = _shapely()
    angs = np.linspace(0, 2 * np.pi, n_lados, endpoint=False) + rotacion
    pts = [(cx + radio * np.cos(a), cy + radio * np.sin(a)) for a in angs]
    return sg.Polygon(pts)


def _forma_marco(forma, cx, cy, radio, grosor_mm):
    """Aro/marco decorativo (Círculo/Hexágono/Pentágono) de `grosor_mm` de
    ancho, centrado en (cx, cy), con radio EXTERIOR `radio` — un anillo,
    no una forma rellena (así el interior queda libre para el texto)."""
    saf = _affinity()
    radio_int = max(radio - grosor_mm, 0.1)
    if forma == "Círculo":
        sg, _ = _shapely()
        exterior = sg.Point(cx, cy).buffer(radio, resolution=64)
        interior = sg.Point(cx, cy).buffer(radio_int, resolution=64)
    else:
        n_lados = 6 if forma == "Hexágono" else 5
        exterior = _poligono_regular(cx, cy, radio, n_lados)
        interior = saf.scale(exterior, xfact=radio_int / radio, yfact=radio_int / radio, origin=(cx, cy))
    return exterior.difference(interior)


def _marco_desde_svg(ruta_svg, cx, cy, radio, grosor_mm):
    """Aro a partir de la silueta de un SVG propio (core/svg_import.py,
    el mismo importador que usa Neón SVG y las decoraciones del
    Llavero): se escala la silueta rellena para que su lado/diámetro
    mayor mida `2*radio`, se centra en (cx, cy) y se hueca con el mismo
    criterio que los marcos de la lista (copia interior escalada +
    difference) -- funciona bien para un SVG de silueta cerrada simple
    (una estrella, un corazón, un logo); un SVG que YA es un aro/corona
    (con sus propios huecos) puede salir con una forma rara al
    volverlo a huecar."""
    svg_import = _svg_import()
    saf = _affinity()

    forma = svg_import.svg_a_poligono(ruta_svg)
    if forma is None:
        raise ValueError(f"no se pudo sacar ninguna forma con área del SVG: {ruta_svg}")

    minx, miny, maxx, maxy = forma.bounds
    radio_actual = max(maxx - minx, maxy - miny) / 2
    if radio_actual <= 0:
        raise ValueError("el SVG no tiene área utilizable")

    factor = radio / radio_actual
    forma = saf.scale(forma, xfact=factor, yfact=factor, origin=(0, 0))
    forma = saf.translate(forma, xoff=cx, yoff=cy)

    radio_int = max(radio - grosor_mm, 0.1)
    interior = saf.scale(forma, xfact=radio_int / radio, yfact=radio_int / radio, origin=(cx, cy))
    return forma.difference(interior)


def _poligono_desde_imagen_centrado(ruta_imagen, umbral, invertir):
    """Como `svg_import.svg_a_poligono()` pero para una imagen rasterizada
    (PNG/JPG, core/imagen_import.py no centra el resultado por su
    cuenta) -- vectoriza y centra en el origen, para poder reusar el
    mismo código de escalado/posicionamiento que ya vale para SVG."""
    saf = _affinity()
    imagen_import = _imagen_import()

    forma = imagen_import.imagen_a_poligono_crudo(ruta_imagen, umbral=umbral, invertir=invertir)
    if forma is None:
        raise ValueError(f"no se pudo sacar ninguna forma con área de la imagen: {ruta_imagen}")
    minx, miny, maxx, maxy = forma.bounds
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    return saf.translate(forma, xoff=-cx, yoff=-cy)


def _marco_desde_imagen(ruta_imagen, cx, cy, radio, grosor_mm, umbral=128, invertir=False):
    """Aro a partir de la silueta de una imagen propia (PNG/JPG, logo o
    ícono simple sobre fondo liso/transparente) -- mismo criterio que
    `_marco_desde_svg`, ver ahí para las limitaciones (mejor con una
    silueta cerrada simple que con un dibujo que ya es un aro/corona).
    `umbral`/`invertir`: ver core/imagen_import.py."""
    saf = _affinity()
    forma = _poligono_desde_imagen_centrado(ruta_imagen, umbral, invertir)

    minx, miny, maxx, maxy = forma.bounds
    radio_actual = max(maxx - minx, maxy - miny) / 2
    if radio_actual <= 0:
        raise ValueError("la imagen no tiene área utilizable")

    factor = radio / radio_actual
    forma = saf.scale(forma, xfact=factor, yfact=factor, origin=(0, 0))
    forma = saf.translate(forma, xoff=cx, yoff=cy)

    radio_int = max(radio - grosor_mm, 0.1)
    interior = saf.scale(forma, xfact=radio_int / radio, yfact=radio_int / radio, origin=(cx, cy))
    return forma.difference(interior)


LADOS_DECORACION_PLANO = ["Arriba", "Arriba derecha", "Arriba izquierda", "Derecha", "Izquierda"]


def _decoracion_desde_svg(ruta_svg, tam_mm):
    """Silueta RELLENA (no un aro, a diferencia de `_marco_desde_svg`) a
    partir de un SVG propio, escalada para que su lado mayor mida
    `tam_mm` y centrada en el origen -- un dibujo/ícono suelto (una
    mariposa, un moño, un logo) para pegar sobre el topper."""
    svg_import = _svg_import()
    saf = _affinity()

    forma = svg_import.svg_a_poligono(ruta_svg)
    if forma is None:
        raise ValueError(f"no se pudo sacar ninguna forma con área del SVG: {ruta_svg}")

    minx, miny, maxx, maxy = forma.bounds
    lado_actual = max(maxx - minx, maxy - miny)
    if lado_actual <= 0:
        raise ValueError("el SVG no tiene área utilizable")

    factor = tam_mm / lado_actual
    return saf.scale(forma, xfact=factor, yfact=factor, origin=(0, 0))


def _decoracion_desde_imagen(ruta_imagen, tam_mm, umbral=128, invertir=False):
    """Como `_decoracion_desde_svg` pero a partir de una imagen propia
    (PNG/JPG). `umbral`/`invertir`: ver core/imagen_import.py."""
    saf = _affinity()
    forma = _poligono_desde_imagen_centrado(ruta_imagen, umbral, invertir)

    minx, miny, maxx, maxy = forma.bounds
    lado_actual = max(maxx - minx, maxy - miny)
    if lado_actual <= 0:
        raise ValueError("la imagen no tiene área utilizable")

    factor = tam_mm / lado_actual
    return saf.scale(forma, xfact=factor, yfact=factor, origin=(0, 0))


MAX_COLORES_DECORACION_MULTICOLOR = 4  # cuántos colores como máximo se pueden USAR al final
COLORES_DETECCION_MULTICOLOR = 12  # cuántos se cuantizan puertas adentro para elegir entre ellos (ver core/imagen_import.py)


def _decoraciones_multicolor_desde_imagen(ruta_imagen, tam_mm, indices_seleccionados=None,
                                           colores_deteccion=COLORES_DETECCION_MULTICOLOR):
    """Como `_decoracion_desde_imagen`, pero separando la imagen en
    varias regiones por color real detectado (core/imagen_import.py::
    imagen_a_poligonos_por_color) en vez de una silueta de un solo
    color. `indices_seleccionados`: lista de índices (sobre el orden
    detectado, mayor a menor área) de CUÁLES colores usar -- hasta
    `MAX_COLORES_DECORACION_MULTICOLOR` -- así el que llama (la UI) elige
    a mano cuáles de los colores detectados son los reales y cuáles son
    ruido de antialiasing, en vez de que la función adivine "los N más
    grandes". None = tomar los primeros `MAX_COLORES_DECORACION_MULTICOLOR`
    tal cual vienen (uso directo sin pasar por la UI).

    Las escala y centra TODAS JUNTAS con el mismo factor/origen (no cada
    una por separado) para que conserven su posición relativa y sigan
    formando la imagen reconocible -- el centrado/escalado se calcula
    sobre las piezas YA FILTRADAS por `indices_seleccionados`, así un
    color descartado tampoco descuadra el tamaño/centro del resto.
    Devuelve una lista de (polígono, "#rrggbb" detectado)."""
    imagen_import = _imagen_import()
    saf = _affinity()
    so = _shapely()[1]

    crudos = imagen_import.imagen_a_poligonos_por_color(ruta_imagen, colores_deteccion=colores_deteccion)
    if not crudos:
        raise ValueError(f"no se pudo sacar ninguna forma con área de la imagen: {ruta_imagen}")

    if indices_seleccionados is not None:
        crudos = [crudos[i] for i in indices_seleccionados if 0 <= i < len(crudos)]
        if not crudos:
            raise ValueError("no se eligió ningún color para usar de la imagen")
    else:
        crudos = crudos[:MAX_COLORES_DECORACION_MULTICOLOR]

    todas = so.unary_union([p for p, _ in crudos]) if len(crudos) > 1 else crudos[0][0]
    minx, miny, maxx, maxy = todas.bounds
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    lado_actual = max(maxx - minx, maxy - miny)
    if lado_actual <= 0:
        raise ValueError("la imagen no tiene área utilizable")
    factor = tam_mm / lado_actual

    resultado = []
    for p, color_hex in crudos:
        p2 = saf.translate(p, xoff=-cx, yoff=-cy)
        p2 = saf.scale(p2, xfact=factor, yfact=factor, origin=(0, 0))
        resultado.append((p2, color_hex))
    return resultado


def detectar_colores_imagen(ruta_imagen, colores_deteccion=COLORES_DETECCION_MULTICOLOR):
    """Para la UI: detecta los colores dominantes de una imagen (mismo
    motor que `_decoraciones_multicolor_desde_imagen`, sin armar la
    geometría 3D completa) -- devuelve una lista de ("#rrggbb", fracción_de_área)
    ordenada de mayor a menor área, para que el usuario elija a mano
    cuáles de los detectados son colores reales (y les asigne un
    filamento real) y cuáles son ruido de antialiasing a ignorar. Lista
    vacía si no se pudo sacar nada (imagen inválida, etc. -- no debe
    romper la página)."""
    try:
        imagen_import = _imagen_import()
        candidatos = imagen_import.imagen_a_poligonos_por_color(ruta_imagen, colores_deteccion=colores_deteccion)
        area_total = sum(p.area for p, _ in candidatos) or 1.0
        return [(color_hex, p.area / area_total) for p, color_hex in candidatos]
    except Exception:
        return []


def _posicionar_decoracion(forma, lado, minx, miny, maxx, maxy):
    """Traslada `forma` (ya centrada en el origen, ver
    `_decoracion_desde_svg`) a una posición relativa al rectángulo
    (minx,miny,maxx,maxy) del resto del diseño (texto, o texto+marco si
    hay) según `lado` (ver LADOS_DECORACION_PLANO) -- metiéndose un
    poco adentro del diseño (en vez de apenas tocarlo) para que quede
    bien pegada; si aun así no llega a tocar nada, el paso de
    conectar_componentes de _armar_regiones_plano la suelda igual."""
    saf = _affinity()
    dminx, dminy, dmaxx, dmaxy = forma.bounds
    dw, dh = dmaxx - dminx, dmaxy - dminy
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2

    if lado == "Arriba":
        x_destino, y_destino = cx, maxy + dh * 0.3
    elif lado == "Arriba derecha":
        x_destino, y_destino = maxx - dw * 0.15, maxy - dh * 0.15
    elif lado == "Arriba izquierda":
        x_destino, y_destino = minx + dw * 0.15, maxy - dh * 0.15
    elif lado == "Derecha":
        x_destino, y_destino = maxx + dw * 0.3, cy
    else:  # "Izquierda"
        x_destino, y_destino = minx - dw * 0.3, cy

    dcx, dcy = (dminx + dmaxx) / 2, (dminy + dmaxy) / 2
    return saf.translate(forma, xoff=x_destino - dcx, yoff=y_destino - dcy)


def _armar_regiones_plano(lineas, tamaño_mm=100, fuente=None, marco="Ninguno",
                           marco_svg=None, marco_imagen=None, marco_imagen_umbral=128,
                           marco_imagen_invertir=False, texto_sobre_marco=False,
                           decoracion_svg=None, decoracion_imagen=None, decoracion_imagen_umbral=128,
                           decoracion_imagen_invertir=False,
                           decoracion_multicolor_imagen=None, decoracion_multicolor_indices=None,
                           decoracion_multicolor_deteccion=COLORES_DETECCION_MULTICOLOR,
                           decoraciones=None,
                           decoracion_tam_mm=25.0, decoracion_lado="Arriba derecha",
                           decoracion_sobre_marco=False,
                           espaciado_relativo=-0.05, separacion_lineas_mm=10.0,
                           offset_vertical_mm=0.0, grosor_marco_mm=3.0,
                           margen_marco_mm=6.0, borde_texto_mm=0.0,
                           ancho_puente_mm=2.5, con_palo=True, largo_palo_mm=45.0,
                           ancho_palo_mm=6.0, con_base=False, ancho_base_extra_mm=10.0,
                           alto_base_mm=6.0, raster_px=400):
    """Arma las 5 regiones del topper plano -- texto / borde del texto /
    marco / palo / decoración -- YA SIN superponerse entre sí, pensadas
    para pintar o imprimir cada una de un color distinto (AMS).
    `borde_texto_mm=0` desactiva el borde (queda en None); sin
    `decoracion_svg` no hay decoración (queda en None). 1 a 3 líneas de
    texto real (con huecos, "espaciado_relativo" negativo para que las
    letras de fuentes script queden más juntas), separadas entre sí por
    `separacion_lineas_mm`; `offset_vertical_mm` corre el texto hacia
    arriba/abajo DENTRO del marco, que se arma con el tamaño y centro
    del texto SIN ese corrimiento -- así se puede descentrar el texto a
    propósito sin que el marco lo siga. `texto_sobre_marco` decide quién
    "gana" donde el texto (y su borde) cruza el marco: en False (de
    siempre) el marco tapa al texto; en True es al revés, el texto tapa
    al marco (le deja un hueco ahí). `con_base` agrega una placa
    horizontal abajo de todo (alternativa al marco, estilo "topper
    parado sobre una base" en vez de "adentro de un aro") -- si además
    hay palo, sale directo de la base en vez de directo del texto.
    `decoracion_svg` (ruta a un SVG
    propio) agrega un dibujo/ícono suelto (ver `_decoracion_desde_svg` /
    `_posicionar_decoracion`) en el lado elegido (`decoracion_lado`,
    ver LADOS_DECORACION_PLANO) respecto del marco si hay, si no del
    texto; `decoracion_sobre_marco` es el mismo criterio que
    `texto_sobre_marco` pero para la decoración -- en False (de
    siempre) el marco tapa a la decoración, en True es al revés.

    `decoraciones`: alternativa a `decoracion_svg`/`decoracion_imagen`/
    `decoracion_multicolor_imagen` para varios dibujos INDEPENDIENTES a
    la vez (ej. un corazón a la derecha, una pata a la izquierda, un
    moño arriba -- cada uno su propio origen, tamaño y lado), en vez de
    un solo dibujo o los colores de UNA sola imagen. Lista de hasta
    `MAX_COLORES_DECORACION_MULTICOLOR` dicts, cada uno
    `{"svg": ruta}` o `{"imagen": ruta, "umbral":, "invertir":}` más
    `"tam_mm"` y `"lado"` propios (si falta alguno, cae a
    `decoracion_tam_mm`/`decoracion_lado`) y opcionalmente
    `"sobre_marco"` (si falta, cae a `decoracion_sobre_marco`). A
    diferencia del modo de una sola imagen multicolor (donde las piezas
    se posicionan TODAS JUNTAS para conservar su alineación relativa),
    acá cada dibujo se posiciona por separado en su propio lado --
    son dibujos sueltos sin relación entre sí. Tiene prioridad sobre
    `decoracion_svg`/`decoracion_imagen`/`decoracion_multicolor_imagen`
    si se pasan los dos.

    Lo que quede suelto (letras que ni con el espaciado negativo se
    tocan, el texto respecto del marco, la decoración, o el palo si no
    llega a tocar el diseño) se une con puentes finos vía
    core/geometry.py::conectar_componentes -- la misma técnica que ya
    usa el generador de Neón -- así el diseño sale como UNA sola pieza
    imprimible pase lo que pase. Esos puentes quedan como su PROPIA
    región ("conectores"), no mezclados en ninguna de las otras -- así
    se pueden imprimir de un color/filamento distinto (ej. transparente,
    para que casi no se noten).

    Devuelve (regiones, cantidad_de_puentes), con `regiones` un dict
    {"texto": geom, "borde": geom|None, "marco": geom|None,
    "palo": geom|None, "decoracion": geom|None, "conectores": geom|None}
    -- unir todo lo que no
    sea None da la pieza completa conectada."""
    sg, so = _shapely()
    saf = _affinity()
    t2d = _texto2d()
    geo = _geom()

    lineas_validas = [l.strip() for l in (lineas or []) if l and l.strip()][:3]
    if not lineas_validas:
        raise ValueError("Escribí al menos una línea de texto")

    n = len(lineas_validas)
    alto_linea_mm = (tamaño_mm - (n - 1) * separacion_lineas_mm) / n
    if alto_linea_mm < 5:
        raise ValueError("el tamaño es muy chico para esa separación entre líneas -- subí el tamaño o bajá la separación")

    piezas_texto = []
    y_cursor = 0.0
    for linea in lineas_validas:
        crudo = t2d.texto_a_poligono_crudo(linea, fuente, raster_px, espaciado_relativo=espaciado_relativo)
        if crudo is None or crudo.is_empty:
            continue
        poli, _ = t2d.escalar_a_alto(crudo, alto_linea_mm)
        minx, miny, maxx, maxy = poli.bounds
        cx_linea = (minx + maxx) / 2
        poli = saf.translate(poli, xoff=-cx_linea, yoff=y_cursor - miny)
        piezas_texto.append(poli)
        y_cursor -= (alto_linea_mm + separacion_lineas_mm)

    if not piezas_texto:
        raise ValueError("no se pudo extraer ninguna línea de texto (probá otra fuente)")

    texto_total = so.unary_union(piezas_texto) if len(piezas_texto) > 1 else piezas_texto[0]
    minx, miny, maxx, maxy = texto_total.bounds
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2

    aro = None
    if marco == "SVG propio" and marco_svg:
        radio = max(maxx - minx, maxy - miny) / 2 + margen_marco_mm
        aro = _marco_desde_svg(marco_svg, cx, cy, radio, grosor_marco_mm)
    elif marco == "Imagen propia" and marco_imagen:
        radio = max(maxx - minx, maxy - miny) / 2 + margen_marco_mm
        aro = _marco_desde_imagen(marco_imagen, cx, cy, radio, grosor_marco_mm,
                                   umbral=marco_imagen_umbral, invertir=marco_imagen_invertir)
    elif marco not in ("Ninguno", "SVG propio", "Imagen propia"):
        radio = max(maxx - minx, maxy - miny) / 2 + margen_marco_mm
        aro = _forma_marco(marco, cx, cy, radio, grosor_marco_mm)

    if offset_vertical_mm:
        texto_total = saf.translate(texto_total, yoff=offset_vertical_mm)

    borde = None
    if borde_texto_mm > 0:
        borde = texto_total.buffer(borde_texto_mm, join_style=1).difference(texto_total)

    if aro is not None:
        if texto_sobre_marco:
            # el texto (+ su borde) gana donde se crucen -- el marco queda
            # con un hueco ahí en vez de taparlos.
            tapado = texto_total if borde is None else so.unary_union([texto_total, borde])
            aro = aro.difference(tapado)
        else:
            # comportamiento de siempre: el marco gana, tapa lo que se
            # cruce del texto/borde.
            texto_total = texto_total.difference(aro)
            if borde is not None:
                borde = borde.difference(aro)

    if borde is not None and borde.is_empty:
        borde = None

    # `piezas_decoracion`: lista de (polígono, color_hex_detectado_o_None)
    # -- 1 sola pieza para SVG o imagen de un color (color=None, usa el
    # que elija el usuario), hasta MAX_COLORES_DECORACION_MULTICOLOR para
    # una imagen multicolor (cada una con el color real detectado como
    # sugerencia). Después de acá se tratan todas igual: se posicionan
    # COMO GRUPO (mismo desplazamiento para todas, así conservan su
    # posición relativa) y se resuelve marco vs. decoración por pieza.
    piezas_decoracion = []
    modo_independiente = bool(decoraciones)
    sobre_marco_por_pieza = []
    if modo_independiente:
        ref_minx, ref_miny, ref_maxx, ref_maxy = (aro.bounds if aro is not None else texto_total.bounds)
        for item in decoraciones[:MAX_COLORES_DECORACION_MULTICOLOR]:
            tam_item = item.get("tam_mm") or decoracion_tam_mm
            lado_item = item.get("lado") or decoracion_lado
            if item.get("svg"):
                forma = _decoracion_desde_svg(item["svg"], tam_item)
            elif item.get("imagen"):
                forma = _decoracion_desde_imagen(
                    item["imagen"], tam_item,
                    umbral=item.get("umbral", 128), invertir=item.get("invertir", False))
            else:
                continue
            forma = _posicionar_decoracion(forma, lado_item, ref_minx, ref_miny, ref_maxx, ref_maxy)
            piezas_decoracion.append((forma, None))
            sobre_marco_por_pieza.append(item.get("sobre_marco", decoracion_sobre_marco))
    elif decoracion_svg:
        piezas_decoracion = [(_decoracion_desde_svg(decoracion_svg, decoracion_tam_mm), None)]
    elif decoracion_multicolor_imagen:
        piezas_decoracion = _decoraciones_multicolor_desde_imagen(
            decoracion_multicolor_imagen, decoracion_tam_mm,
            indices_seleccionados=decoracion_multicolor_indices,
            colores_deteccion=decoracion_multicolor_deteccion)
    elif decoracion_imagen:
        piezas_decoracion = [(_decoracion_desde_imagen(
            decoracion_imagen, decoracion_tam_mm,
            umbral=decoracion_imagen_umbral, invertir=decoracion_imagen_invertir), None)]

    decoracion_slots = [None] * MAX_COLORES_DECORACION_MULTICOLOR
    if piezas_decoracion:
        if not modo_independiente:
            # Un solo SVG/imagen (1 pieza) o los colores de UNA imagen
            # multicolor (varias piezas que tienen que conservar su
            # posición relativa) -- se posicionan TODAS JUNTAS como un
            # solo grupo rígido, en el lado único `decoracion_lado`.
            ref_minx, ref_miny, ref_maxx, ref_maxy = (aro.bounds if aro is not None else texto_total.bounds)
            grupo = so.unary_union([p for p, _ in piezas_decoracion]) if len(piezas_decoracion) > 1 else piezas_decoracion[0][0]
            grupo_posicionado = _posicionar_decoracion(grupo, decoracion_lado, ref_minx, ref_miny, ref_maxx, ref_maxy)
            dx = grupo_posicionado.bounds[0] - grupo.bounds[0]
            dy = grupo_posicionado.bounds[1] - grupo.bounds[1]
            piezas_decoracion = [(saf.translate(p, xoff=dx, yoff=dy), c) for p, c in piezas_decoracion]
            sobre_marco_por_pieza = [decoracion_sobre_marco] * len(piezas_decoracion)

        for i, (p, color_hex) in enumerate(piezas_decoracion[:MAX_COLORES_DECORACION_MULTICOLOR]):
            if aro is not None:
                if sobre_marco_por_pieza[i]:
                    aro = aro.difference(p)
                else:
                    p = p.difference(aro)
            decoracion_slots[i] = p

    decoracion, decoracion_2, decoracion_3, decoracion_4 = decoracion_slots

    nombradas_principales = [g for g in (texto_total, borde, aro) if g is not None]
    principal = so.unary_union(nombradas_principales) if len(nombradas_principales) > 1 else nombradas_principales[0]

    base = None
    soporte = principal
    if con_base:
        # Una placa/plataforma horizontal abajo de todo -- alternativa al
        # marco (que envuelve el texto) para el estilo "topper apoyado
        # sobre una base", como pastel de bautismo/casamiento: ancho =
        # el diseño + un margen a cada lado, altura fija chica.
        minx, miny, maxx, maxy = principal.bounds
        base = sg.box(minx - ancho_base_extra_mm, miny - alto_base_mm,
                      maxx + ancho_base_extra_mm, miny + 0.5)
        soporte = so.unary_union([principal, base])

    palo = None
    if con_palo:
        # OJO: centrado/apoyado en "soporte" (texto+borde+marco+base si
        # hay), NO en el diseño completo -- si se usara el bbox con la
        # decoración incluida, una decoración grande o que cuelgue hacia
        # abajo (una figura, un moño largo) corre el palito de lugar sin
        # sentido, a veces terminando pegado a una pata/rulo de la
        # decoración en vez de centrado bajo el texto/base. Así el
        # palito sale siempre de la base (si hay) o del texto (si no).
        minx, miny, maxx, maxy = soporte.bounds
        cx_pata = (minx + maxx) / 2
        palo = sg.box(cx_pata - ancho_palo_mm / 2, miny - largo_palo_mm,
                      cx_pata + ancho_palo_mm / 2, miny + 0.5)

    # Las piezas (texto/borde/marco/base/decoración/palo) se conectan
    # TODAS JUNTAS en un solo pase -- así el árbol de expansión mínima
    # elige de verdad el puente más corto entre TODO lo que hay, en vez
    # de conectar primero la decoración al texto (sin saber todavía
    # dónde va a caer el palito) y recién después soldar el palito
    # aparte: si una decoración que cuelga (un moño, una cola) termina
    # más cerca del palito que del texto, ahora se suelda directo ahí en
    # lugar de sumar un puente aparte, más largo y más visible.
    nombradas = nombradas_principales + [
        g for g in (base, decoracion, decoracion_2, decoracion_3, decoracion_4, palo) if g is not None
    ]
    contenido = so.unary_union(nombradas) if len(nombradas) > 1 else nombradas[0]
    conectado, n_puentes = geo.conectar_componentes(contenido, ancho_puente_mm, 0.4)

    conectores = None
    extra = conectado.difference(contenido)
    if not extra.is_empty:
        conectores = extra

    return {
        "texto": texto_total, "borde": borde, "marco": aro, "base": base, "palo": palo,
        "decoracion": decoracion, "decoracion_2": decoracion_2, "decoracion_3": decoracion_3,
        "decoracion_4": decoracion_4, "conectores": conectores,
    }, n_puentes


_SIMPLIFY_EXTRUSION_MM = 0.05  # limpia ruido numérico de union()/difference() antes de triangular


def _extrudir_geom(geom, espesor_mm):
    """Extruye un (Multi)Polygon shapely a un trimesh.Trimesh de altura
    `espesor_mm`, o None si `geom` es None/vacío. Simplifica un poquito
    cada sub-polígono antes de extruir (mismo motivo que
    core/texto2d.py::SIMPLIFY_MM): un polígono que salió de varios
    union()/difference() seguidos (típico en los puentes finos de
    conectar_componentes, sobre todo si un puente quedó cortito) a veces
    junta puntos casi-colineales o casi-duplicados que confunden al
    triangulador y dejan la malla no watertight -- visto en la región
    "conectores" con un puente chico. El área prácticamente no cambia,
    solo saca esos puntos redundantes."""
    if geom is None or geom.is_empty:
        return None
    piezas_geoms = geom.geoms if hasattr(geom, "geoms") else [geom]
    mallas = []
    for p in piezas_geoms:
        if not p.is_valid or p.area <= 0:
            continue
        p = p.simplify(_SIMPLIFY_EXTRUSION_MM, preserve_topology=True)
        if p.is_empty or p.area <= 0:
            continue
        mallas.append(trimesh.creation.extrude_polygon(p, height=espesor_mm))
    if not mallas:
        return None
    malla = trimesh.util.concatenate(mallas)
    malla.fix_normals()
    return malla


def generar_plano(lineas, tamaño_mm=100, fuente=None, marco="Ninguno", marco_svg=None,
                   marco_imagen=None, marco_imagen_umbral=128, marco_imagen_invertir=False,
                   texto_sobre_marco=False,
                   decoracion_svg=None, decoracion_imagen=None, decoracion_imagen_umbral=128,
                   decoracion_imagen_invertir=False,
                   decoracion_multicolor_imagen=None, decoracion_multicolor_indices=None,
                   decoracion_multicolor_deteccion=COLORES_DETECCION_MULTICOLOR,
                   decoraciones=None,
                   decoracion_tam_mm=25.0, decoracion_lado="Arriba derecha",
                   decoracion_sobre_marco=False,
                   espaciado_relativo=-0.05, separacion_lineas_mm=10.0, offset_vertical_mm=0.0,
                   grosor_marco_mm=3.0, margen_marco_mm=6.0, borde_texto_mm=0.0,
                   ancho_puente_mm=2.5, con_palo=True, largo_palo_mm=45.0,
                   ancho_palo_mm=6.0, con_base=False, ancho_base_extra_mm=10.0, alto_base_mm=6.0,
                   espesor_mm=3.0, raster_px=400,
                   tiene_ams=False, color_texto="Dorado", color_borde="Blanco",
                   color_marco="Dorado", color_palo="Dorado", color_decoracion="Dorado",
                   color_decoracion_2="Blanco", color_decoracion_3="Negro", color_decoracion_4="Gris Frío",
                   color_conectores="Transparente/Natural", color_base="Dorado"):
    """Generar topper "plano" (recortado, tipo acrílico/madera láser): 1 a
    3 líneas de texto, marco decorativo opcional, borde de texto
    opcional, decoración (SVG propio) opcional, y palo para clavar en la
    torta -- ver `_armar_regiones_plano`. Con `tiene_ams=True` exporta
    ADEMÁS un .3mf y un .stl multicolor con cada región (texto/borde/
    marco/palo/decoración) ya pintada de su color (mismo mecanismo que
    el Llavero, core/pieza.py::exportar_multicolor*) -- sin AMS, el STL
    simple sirve igual como guía para pintar a mano (las regiones
    existen igual, nada más que en un solo color al imprimir). Devuelve
    un dict con las rutas, medidas y avisos."""
    os.makedirs(CARPETA_SALIDA, exist_ok=True)

    regiones, n_puentes = _armar_regiones_plano(
        lineas, tamaño_mm=tamaño_mm, fuente=fuente, marco=marco, marco_svg=marco_svg,
        marco_imagen=marco_imagen, marco_imagen_umbral=marco_imagen_umbral,
        marco_imagen_invertir=marco_imagen_invertir,
        texto_sobre_marco=texto_sobre_marco,
        decoracion_svg=decoracion_svg, decoracion_imagen=decoracion_imagen,
        decoracion_imagen_umbral=decoracion_imagen_umbral, decoracion_imagen_invertir=decoracion_imagen_invertir,
        decoracion_multicolor_imagen=decoracion_multicolor_imagen,
        decoracion_multicolor_indices=decoracion_multicolor_indices,
        decoracion_multicolor_deteccion=decoracion_multicolor_deteccion,
        decoraciones=decoraciones,
        decoracion_tam_mm=decoracion_tam_mm, decoracion_lado=decoracion_lado,
        decoracion_sobre_marco=decoracion_sobre_marco,
        espaciado_relativo=espaciado_relativo, separacion_lineas_mm=separacion_lineas_mm,
        offset_vertical_mm=offset_vertical_mm, grosor_marco_mm=grosor_marco_mm,
        margen_marco_mm=margen_marco_mm, borde_texto_mm=borde_texto_mm,
        ancho_puente_mm=ancho_puente_mm, con_palo=con_palo, largo_palo_mm=largo_palo_mm,
        ancho_palo_mm=ancho_palo_mm, con_base=con_base, ancho_base_extra_mm=ancho_base_extra_mm,
        alto_base_mm=alto_base_mm, raster_px=raster_px,
    )

    lineas_validas = [l.strip() for l in lineas if l and l.strip()][:3]
    base_nombre = pieza.nombre_archivo(" ".join(lineas_validas), default="topper")
    marco_slug = "".join(c if c.isalnum() else "_" for c in marco).strip("_")
    ruta_stl = os.path.join(CARPETA_SALIDA, f"topper_plano_{base_nombre}_{marco_slug}.stl")

    colores_por_region = {
        "texto": color_texto, "borde": color_borde, "marco": color_marco,
        "palo": color_palo, "decoracion": color_decoracion, "conectores": color_conectores,
        "base": color_base,
        "decoracion_2": color_decoracion_2, "decoracion_3": color_decoracion_3, "decoracion_4": color_decoracion_4,
    }
    mallas_por_region = {clave: _extrudir_geom(geom, espesor_mm) for clave, geom in regiones.items()}
    claves_presentes = [clave for clave, m in mallas_por_region.items() if m is not None]
    mallas_presentes = [mallas_por_region[clave] for clave in claves_presentes]
    if not mallas_presentes:
        raise ValueError("el diseño quedó vacío, probá con otro texto")
    malla = trimesh.util.concatenate(mallas_presentes)
    malla.export(ruta_stl)

    # Un STL por región SIEMPRE (no solo con AMS) -- para que el visor 3D de
    # la página pueda mostrar el resultado con los colores reales elegidos
    # en vez de un color parejo fijo (no para imprimir sueltas: son coplanares,
    # no se pegan bien a mano -- para eso está el STL combinado de arriba).
    piezas_color = []
    for clave in claves_presentes:
        ruta_region = os.path.join(CARPETA_SALIDA, f"topper_plano_{base_nombre}_{marco_slug}_{clave}.stl")
        mallas_por_region[clave].export(ruta_region)
        piezas_color.append({"clave": clave, "ruta_stl": ruta_region, "color": colores_por_region[clave]})

    ruta_3mf_multicolor = None
    ruta_stl_multicolor = None
    if tiene_ams:
        colores_hex = [colores.hex_de(colores_por_region[clave]) for clave in claves_presentes]
        ruta_3mf_multicolor = os.path.join(CARPETA_SALIDA, f"topper_plano_{base_nombre}_{marco_slug}_multicolor.3mf")
        pieza.exportar_multicolor_3mf(mallas_presentes, ruta_3mf_multicolor, colores_hex=colores_hex)
        ruta_stl_multicolor = os.path.join(CARPETA_SALIDA, f"topper_plano_{base_nombre}_{marco_slug}_multicolor.stl")
        pieza.exportar_multicolor(mallas_presentes, ruta_stl_multicolor)

    return {
        "tipo": "plano",
        "lineas": lineas_validas,
        "tamaño_mm": tamaño_mm,
        "marco": marco,
        "puentes": n_puentes,
        "fuente": fuente,
        "ruta_stl": ruta_stl,
        "piezas_color": piezas_color,
        "ruta_3mf_multicolor": ruta_3mf_multicolor,
        "ruta_stl_multicolor": ruta_stl_multicolor,
        "colores": {
            "texto": color_texto, "borde": color_borde, "marco": color_marco, "palo": color_palo,
            "decoracion": color_decoracion, "conectores": color_conectores, "base": color_base,
            "decoracion_2": color_decoracion_2, "decoracion_3": color_decoracion_3, "decoracion_4": color_decoracion_4,
        },
        "vertices": len(malla.vertices),
        "caras": len(malla.faces),
        "watertight": malla.is_watertight,
        "estado": "✓ Generado",
    }


# ---------------------------------------------------------------------------
# Previews HTML (texto real + fuente real vía @font-face embebido)
# ---------------------------------------------------------------------------

def _font_face_css(ruta_ttf, familia="topper-preview-font"):
    """@font-face embebido en base64, o "" si no se puede leer la fuente."""
    if not ruta_ttf:
        return "", "sans-serif"
    try:
        with open(ruta_ttf, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
    except OSError:
        return "", "sans-serif"
    formato = "opentype" if ruta_ttf.lower().endswith(".otf") else "truetype"
    css = f"""<style>
    @font-face {{
        font-family: "{familia}";
        src: url(data:font/{formato};base64,{b64}) format("{formato}");
    }}
    </style>"""
    return css, familia


def _svg_silueta_base(forma, cx, base_y, rx, ry_factor=0.28, fill="#ddd"):
    """SVG de la silueta de la base (vista en perspectiva simple, como una
    elipse achatada) según la forma elegida."""
    ry = rx * ry_factor
    if forma == "Cuadrada":
        lado = rx * 1.5
        return f'<rect x="{cx-lado/2}" y="{base_y-ry}" width="{lado}" height="{ry*2}" rx="4" fill="{fill}" stroke="#666"/>'
    if forma == "Rectangular":
        anchoR = rx * 2.0
        return f'<rect x="{cx-anchoR/2}" y="{base_y-ry}" width="{anchoR}" height="{ry*2}" rx="4" fill="{fill}" stroke="#666"/>'
    if forma == "Ovalada":
        return f'<ellipse cx="{cx}" cy="{base_y}" rx="{rx*1.3}" ry="{ry*0.75}" fill="{fill}" stroke="#666"/>'
    # "Redonda"
    return f'<ellipse cx="{cx}" cy="{base_y}" rx="{rx}" ry="{ry}" fill="{fill}" stroke="#666"/>'


def preview_html_3d(texto, tamaño_mm=80, estilo="Elegante", base_tipo="Redonda — Plana (apoyada)",
                     color_hex="#cccccc", fuente_ttf=None):
    """Preview HTML (SVG + @font-face real) de topper 3D — refleja texto,
    fuente y tipo de base (forma × modo, o caso especial) elegidos."""
    config = ESTILOS.get(estilo, ESTILOS["Elegante"])
    altura_mm = config["altura_mm"]
    forma, modo = _parsear_base(base_tipo)

    css, familia = _font_face_css(fuente_ttf)

    scale = 2.2
    w = max(tamaño_mm * scale, 160)
    h = (altura_mm + 30) * scale

    cx = w / 2
    base_y = h - 20 * scale

    if modo == "Con palo (clavar en torta)":
        cuerpo = f'''
        <line x1="{cx}" y1="{base_y}" x2="{cx}" y2="{h-4}" stroke="#8B5A2B" stroke-width="4"/>
        {_svg_silueta_base(forma, cx, base_y, 26, 0.22, "#ccc")}
        <path d="M {cx-tamaño_mm*scale*0.28} {base_y} L {cx} {base_y-altura_mm*scale} L {cx+tamaño_mm*scale*0.28} {base_y} Z"
              fill="{color_hex}" stroke="#666" stroke-width="1.5"/>'''
    elif base_tipo == "Redonda (letras paradas)":
        letras = list(texto.strip())[:10] or ["A"]
        n = len(letras)
        ancho_letra = min(28, (w * 0.7) / max(n, 1))
        x0 = cx - (n * ancho_letra) / 2 + ancho_letra / 2
        bloques = ""
        for i, ch in enumerate(letras):
            lx = x0 + i * ancho_letra
            lh = altura_mm * scale * (0.7 + 0.3 * ((i % 3) / 2))
            bloques += f'<rect x="{lx-ancho_letra*0.35}" y="{base_y-lh}" width="{ancho_letra*0.7}" height="{lh}" fill="{color_hex}" stroke="#666" stroke-width="1"/>'
            bloques += f'<text x="{lx}" y="{base_y-lh/2+6}" text-anchor="middle" font-size="14" font-family="{familia}" fill="#222">{ch}</text>'
        cuerpo = _svg_silueta_base("Redonda", cx, base_y, w * 0.4, 0.25, "#ddd") + bloques
    elif modo == "Con figura arriba":
        cuerpo = f'''
        {_svg_silueta_base(forma, cx, base_y, 30, 0.23, "#ddd")}
        <path d="M {cx-tamaño_mm*scale*0.22} {base_y} L {cx-tamaño_mm*scale*0.02} {base_y-altura_mm*scale} L {cx+tamaño_mm*scale*0.18} {base_y} Z"
              fill="{color_hex}" stroke="#666" stroke-width="1.2"/>
        <line x1="{cx+tamaño_mm*scale*0.28}" y1="{base_y}" x2="{cx+tamaño_mm*scale*0.28}" y2="{base_y-15}" stroke="#999" stroke-width="3"/>
        <circle cx="{cx+tamaño_mm*scale*0.28}" cy="{base_y-15-altura_mm*scale*0.4}" r="{altura_mm*scale*0.4}" fill="#e8a33d" stroke="#666" stroke-width="1.5"/>'''
    elif base_tipo == "Sin base (figura libre)":
        cuerpo = f'''
        <circle cx="{cx}" cy="{base_y-altura_mm*scale*0.6}" r="{altura_mm*scale*0.6}" fill="{color_hex}" stroke="#666" stroke-width="1.5"/>'''
    else:  # "Plana (apoyada)" (default)
        cuerpo = f'''
        {_svg_silueta_base(forma, cx, base_y, 25, 0.16, "#ddd")}
        <path d="M {cx-tamaño_mm*scale*0.3} {base_y} L {cx} {base_y-altura_mm*scale} L {cx+tamaño_mm*scale*0.3} {base_y} Z"
              fill="{color_hex}" stroke="#666" stroke-width="1.5"/>'''

    etiqueta_texto = ""
    if base_tipo != "Redonda (letras paradas)":
        y_texto = base_y - altura_mm * scale - 8
        if modo == "Con figura arriba":
            y_texto = base_y - altura_mm * scale * 0.7
        etiqueta_texto = f'<text x="{cx}" y="{y_texto}" text-anchor="middle" font-size="16" font-family="{familia}" fill="#111" font-weight="bold">{texto[:16]}</text>'

    svg = f'''{css}<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" style="max-width:100%;height:auto;background:#eef0f2;border-radius:10px">
    <rect x="0" y="0" width="{w}" height="{h}" fill="#eef0f2" rx="10"/>
    {cuerpo}
    {etiqueta_texto}
    <text x="{cx}" y="{h-2}" text-anchor="middle" font-size="10" fill="#555">{estilo} · {base_tipo}</text>
    </svg>'''
    return svg


def preview_html_neon(texto, grosor_tubo=10, largo_mm=50, fuente_ttf=None, color_hex="#00ff00"):
    css, familia = _font_face_css(fuente_ttf)
    scale = 2
    w = max(largo_mm * scale, 160)
    h = (grosor_tubo + 24) * scale

    svg = f'''{css}<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" style="max-width:100%;height:auto">
    <defs>
        <filter id="glow"><feGaussianBlur stdDeviation="1.5" result="b"/>
            <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    </defs>
    <rect x="0" y="0" width="{w}" height="{h}" fill="#0a0a0a" rx="10"/>
    <text x="{w/2}" y="{h/2+8}" text-anchor="middle" font-size="{min(28, w/max(len(texto),1)*1.4)}"
          font-family="{familia}" fill="{color_hex}" filter="url(#glow)" opacity="0.95">{texto[:16]}</text>
    <text x="{w/2}" y="{h-6}" text-anchor="middle" font-size="10" fill="{color_hex}" opacity="0.7">Tubo LED · {grosor_tubo}mm</text>
    </svg>'''
    return svg


def preview_html_led(texto, efecto="Fijo", tamaño_mm=80, fuente_ttf=None):
    css, familia = _font_face_css(fuente_ttf)
    colores_efecto = {"Fijo": "#ff3b30", "Parpadeo": "#ff9500", "Secuencial": "#ffcc00", "Arcoíris": "#af52de"}
    color = colores_efecto.get(efecto, "#ff3b30")

    scale = 1.8
    w = max(tamaño_mm * scale, 180)
    h = w * 0.8

    svg = f'''{css}<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" style="max-width:100%;height:auto">
    <defs>
        <filter id="ledglow"><feGaussianBlur stdDeviation="2.5" result="b"/>
            <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    </defs>
    <rect x="0" y="0" width="{w}" height="{h}" fill="#0a0a0a" rx="10"/>
    <rect x="{w/2-30}" y="{h-24}" width="60" height="10" fill="#333"/>
    <circle cx="{w/2}" cy="{h/2-5}" r="{w*0.32}" fill="none" stroke="#555" stroke-width="3"/>
    <text x="{w/2}" y="{h/2}" text-anchor="middle" font-size="{min(26, w/max(len(texto),1)*1.3)}"
          font-family="{familia}" fill="{color}" filter="url(#ledglow)" font-weight="bold">{texto[:14]}</text>
    <text x="{w/2}" y="{h-6}" text-anchor="middle" font-size="10" fill="{color}">Efecto: {efecto}</text>
    </svg>'''
    return svg


def preview_html_acrilico(texto, espesor_mm=3, ancho_mm=100, alto_mm=60, fuente_ttf=None):
    css, familia = _font_face_css(fuente_ttf)
    svg = f'''{css}<svg viewBox="0 0 {ancho_mm} {alto_mm}" xmlns="http://www.w3.org/2000/svg" style="max-width:100%;height:auto">
    <defs>
        <linearGradient id="acrylic" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" style="stop-color:#fff;stop-opacity:0.7"/>
            <stop offset="50%" style="stop-color:#e0e0e0;stop-opacity:0.5"/>
            <stop offset="100%" style="stop-color:#999;stop-opacity:0.3"/>
        </linearGradient>
    </defs>
    <rect x="0" y="0" width="{ancho_mm}" height="{alto_mm}" fill="#c9cdd3" rx="8"/>
    <rect x="5" y="5" width="{ancho_mm-10}" height="{alto_mm-10}" fill="url(#acrylic)" stroke="#333" stroke-width="1.5" rx="3"/>
    <text x="{ancho_mm/2}" y="{alto_mm/2+3}" text-anchor="middle" font-size="{min(16, ancho_mm/max(len(texto),1)*1.4)}"
          font-family="{familia}" font-weight="bold" fill="#333" opacity="0.7">{texto[:12]}</text>
    <text x="{ancho_mm/2}" y="{alto_mm-8}" text-anchor="middle" font-size="9" fill="#666">{espesor_mm}mm</text>
    </svg>'''
    return svg


def _shapely_a_svg_path(geom):
    """Convierte un (Multi)Polygon shapely a un string de <path d="..."">
    SVG con fill-rule evenodd -- así los huecos (interiors, y el hueco
    del marco) se ven como huecos de verdad sin armar el path a mano.
    Niega Y porque en SVG el eje Y crece hacia abajo."""
    piezas = geom.geoms if hasattr(geom, "geoms") else [geom]
    partes = []
    for p in piezas:
        for anillo in [p.exterior] + list(p.interiors):
            coords = list(anillo.coords)
            if len(coords) < 2:
                continue
            d = f"M {coords[0][0]:.2f},{-coords[0][1]:.2f} " + " ".join(
                f"L {x:.2f},{-y:.2f}" for x, y in coords[1:]
            ) + " Z"
            partes.append(d)
    return " ".join(partes)


def preview_html_plano(lineas, tamaño_mm=100, marco="Ninguno", fuente_ttf=None,
                        color_texto="#d4af37", color_borde="#f4f4f2",
                        color_marco="#d4af37", color_palo="#d4af37",
                        color_decoracion="#d4af37", color_conectores="#dce8e8",
                        color_base="#d4af37",
                        color_decoracion_2="#f4f4f2", color_decoracion_3="#1a1a1a",
                        color_decoracion_4="#8e9089", **kwargs):
    """Preview real (no esquemático) del topper plano: arma las 5
    regiones de verdad (`_armar_regiones_plano`, incluidos los puentes)
    y las dibuja como SVG, cada una de su color -- sirve como guía de
    pintado incluso para quien imprima en un solo color. Devuelve None
    si no se pudo armar el diseño."""
    try:
        regiones, n_puentes = _armar_regiones_plano(lineas, tamaño_mm, fuente_ttf, marco, **kwargs)
    except Exception:
        return None

    so = _shapely()[1]
    partes = [g for g in regiones.values() if g is not None]
    todo = so.unary_union(partes) if len(partes) > 1 else partes[0]
    minx, miny, maxx, maxy = todo.bounds
    ancho, alto = max(maxx - minx, 1e-6), max(maxy - miny, 1e-6)
    pad = max(ancho, alto) * 0.06 + 3
    vb_w, vb_h = ancho + pad * 2, alto + pad * 2
    tx, ty = -minx + pad, maxy + pad  # ty: ya negamos Y en _shapely_a_svg_path

    colores_region = {
        "conectores": color_conectores, "base": color_base, "marco": color_marco, "palo": color_palo,
        "decoracion": color_decoracion, "decoracion_2": color_decoracion_2, "decoracion_3": color_decoracion_3,
        "decoracion_4": color_decoracion_4, "borde": color_borde, "texto": color_texto,
    }
    capas = "".join(
        f'<path d="{_shapely_a_svg_path(regiones[clave])}" fill="{colores_region[clave]}" '
        f'fill-rule="evenodd" stroke="#00000055" stroke-width="0.4"/>'
        for clave in ("conectores", "base", "marco", "palo", "decoracion", "decoracion_2", "decoracion_3",
                      "decoracion_4", "borde", "texto") if regiones.get(clave) is not None
    )

    puentes_txt = f"{n_puentes} puente(s)" if n_puentes else "sin puentes (ya conectado)"
    svg = f'''<svg viewBox="0 0 {vb_w:.1f} {vb_h:.1f}" xmlns="http://www.w3.org/2000/svg"
    style="max-width:100%;height:auto;background:#f4f0e8;border-radius:10px">
    <g transform="translate({tx:.2f},{ty:.2f})">{capas}</g>
    <text x="{vb_w/2:.1f}" y="{vb_h-4:.1f}" text-anchor="middle" font-size="10" fill="#555">{marco} · {puentes_txt}</text>
    </svg>'''
    return svg


def generar(tipo, texto, tamaño_mm=80, **kwargs):
    """Generador unificado de toppers."""
    if tipo == "3d":
        return generar_3d(texto, tamaño_mm, **kwargs)
    elif tipo == "neon":
        return generar_neon(texto, tamaño_mm, **kwargs)
    elif tipo == "led":
        return generar_led(texto, tamaño_mm, **kwargs)
    elif tipo == "acrilico":
        return generar_acrilico(texto, tamaño_mm, **kwargs)
    else:
        raise ValueError(f"Tipo de topper desconocido: {tipo}")
