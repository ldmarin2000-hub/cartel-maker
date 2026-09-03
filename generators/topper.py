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

from core import pieza, fuentes

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
FORMAS_MARCO = ["Ninguno", "Círculo", "Hexágono", "Pentágono"]


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


def _armar_geometria_plano(lineas, tamaño_mm=100, fuente=None, marco="Ninguno",
                            espaciado_relativo=-0.05, grosor_marco_mm=3.0,
                            margen_marco_mm=6.0, ancho_puente_mm=2.5,
                            con_palo=True, largo_palo_mm=45.0, ancho_palo_mm=6.0,
                            raster_px=400):
    """Arma la geometría 2D (shapely) del topper plano: 1 a 3 líneas de
    texto real (con huecos, "espaciado_relativo" negativo para que las
    letras de fuentes script queden más juntas), un marco decorativo
    opcional envolviendo el bloque de texto, y un palo abajo para clavar
    en la torta. Lo que quede suelto (letras que ni con el espaciado
    negativo se tocan, o el texto respecto del marco) se une con puentes
    finos vía core/geometry.py::conectar_componentes -- la misma técnica
    que ya usa el generador de Neón -- así el diseño sale como UNA sola
    pieza imprimible sin importar si la fuente conecta sus letras o no.
    Devuelve (geometria, cantidad_de_puentes)."""
    sg, so = _shapely()
    saf = _affinity()
    t2d = _texto2d()
    geo = _geom()

    lineas_validas = [l.strip() for l in (lineas or []) if l and l.strip()][:3]
    if not lineas_validas:
        raise ValueError("Escribí al menos una línea de texto")

    n = len(lineas_validas)
    alto_linea_mm = tamaño_mm / (n + (n - 1) * 0.35)
    gap_mm = alto_linea_mm * 0.35

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
        y_cursor -= (alto_linea_mm + gap_mm)

    if not piezas_texto:
        raise ValueError("no se pudo extraer ninguna línea de texto (probá otra fuente)")

    texto_total = so.unary_union(piezas_texto) if len(piezas_texto) > 1 else piezas_texto[0]
    minx, miny, maxx, maxy = texto_total.bounds
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2

    if marco != "Ninguno":
        radio = max(maxx - minx, maxy - miny) / 2 + margen_marco_mm
        aro = _forma_marco(marco, cx, cy, radio, grosor_marco_mm)
        contenido = so.unary_union([texto_total, aro])
    else:
        contenido = texto_total

    conectado, n_puentes = geo.conectar_componentes(contenido, ancho_puente_mm, 0.4)

    if con_palo:
        minx, miny, maxx, maxy = conectado.bounds
        solape = min(4.0, alto_linea_mm * 0.3)
        cx_pata = (minx + maxx) / 2
        pata = sg.box(cx_pata - ancho_palo_mm / 2, miny - largo_palo_mm,
                      cx_pata + ancho_palo_mm / 2, miny + solape)
        conectado = so.unary_union([conectado, pata])

    return conectado, n_puentes


def generar_plano(lineas, tamaño_mm=100, fuente=None, marco="Ninguno",
                   espaciado_relativo=-0.05, grosor_marco_mm=3.0, margen_marco_mm=6.0,
                   ancho_puente_mm=2.5, con_palo=True, largo_palo_mm=45.0,
                   ancho_palo_mm=6.0, espesor_mm=3.0, raster_px=400):
    """Generar topper "plano" (recortado, tipo acrílico/madera láser): 1 a
    3 líneas de texto, marco decorativo opcional, y palo para clavar en
    la torta -- ver `_armar_geometria_plano`. Devuelve un dict con la
    ruta del STL, medidas y avisos."""
    os.makedirs(CARPETA_SALIDA, exist_ok=True)

    conectado, n_puentes = _armar_geometria_plano(
        lineas, tamaño_mm, fuente, marco, espaciado_relativo, grosor_marco_mm,
        margen_marco_mm, ancho_puente_mm, con_palo, largo_palo_mm, ancho_palo_mm, raster_px,
    )

    piezas_geoms = conectado.geoms if hasattr(conectado, "geoms") else [conectado]
    mallas = [trimesh.creation.extrude_polygon(p, height=espesor_mm)
              for p in piezas_geoms if p.is_valid and p.area > 0]
    if not mallas:
        raise ValueError("el diseño quedó vacío, probá con otro texto")
    malla = trimesh.util.concatenate(mallas)
    malla.fix_normals()

    lineas_validas = [l.strip() for l in lineas if l and l.strip()][:3]
    base_nombre = pieza.nombre_archivo(" ".join(lineas_validas), default="topper")
    marco_slug = "".join(c if c.isalnum() else "_" for c in marco).strip("_")
    ruta_stl = os.path.join(CARPETA_SALIDA, f"topper_plano_{base_nombre}_{marco_slug}.stl")
    malla.export(ruta_stl)

    return {
        "tipo": "plano",
        "lineas": lineas_validas,
        "tamaño_mm": tamaño_mm,
        "marco": marco,
        "puentes": n_puentes,
        "fuente": fuente,
        "ruta_stl": ruta_stl,
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
                        color_hex="#d4af37", **kwargs):
    """Preview real (no esquemático) del topper plano: arma la geometría
    de verdad (`_armar_geometria_plano`, incluidos los puentes) y la
    dibuja como SVG. Devuelve None si no se pudo armar el diseño."""
    try:
        contenido, n_puentes = _armar_geometria_plano(lineas, tamaño_mm, fuente_ttf, marco, **kwargs)
    except Exception:
        return None

    minx, miny, maxx, maxy = contenido.bounds
    ancho, alto = max(maxx - minx, 1e-6), max(maxy - miny, 1e-6)
    pad = max(ancho, alto) * 0.06 + 3
    vb_w, vb_h = ancho + pad * 2, alto + pad * 2
    tx, ty = -minx + pad, maxy + pad  # ty: ya negamos Y en _shapely_a_svg_path
    path_d = _shapely_a_svg_path(contenido)

    puentes_txt = f"{n_puentes} puente(s)" if n_puentes else "sin puentes (ya conectado)"
    svg = f'''<svg viewBox="0 0 {vb_w:.1f} {vb_h:.1f}" xmlns="http://www.w3.org/2000/svg"
    style="max-width:100%;height:auto;background:#f4f0e8;border-radius:10px">
    <g transform="translate({tx:.2f},{ty:.2f})">
        <path d="{path_d}" fill="{color_hex}" fill-rule="evenodd" stroke="#8a6d1a" stroke-width="0.6"/>
    </g>
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
