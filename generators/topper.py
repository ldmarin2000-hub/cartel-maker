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

# Tipos de base — cómo se apoya/inserta el topper en la torta
BASES = [
    "Sólida (plana)",
    "Palo (clavar en torta)",
    "Redonda (letras paradas)",
    "Redonda con figura arriba",
    "Sin base (figura libre)",
]

# Temas/categoría — no cambian geometría pero orientan el diseño y presets
TEMAS = [
    "General", "Matrimonio", "Cumpleaños", "Fiesta", "Bebé / Baby Shower",
    "Graduación", "Aniversario", "Quince Años",
]

# Objetos decorativos que se pueden agregar sobre la base
OBJETOS_DECORATIVOS = [
    "Ninguno", "Flores", "Corazón", "Estrella", "Personaje/Figura",
    "Pareja/Novios", "Juguete", "Animal", "Símbolo",
]


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


def _bloque(ancho, profundidad, altura, cx=0.0, cy=0.0, z0=0.0):
    caja = trimesh.creation.box(extents=[ancho, profundidad, altura])
    caja.apply_translation([cx, cy, z0 + altura / 2])
    return caja


def _combinar(mallas):
    """Concatena mallas (sin booleana real, solo unión de geometría para
    export STL — suficiente para imprimir como piezas fusionadas visualmente)."""
    validas = [m for m in mallas if m is not None and len(m.vertices) > 0]
    if not validas:
        raise ValueError("No hay geometría para combinar")
    return trimesh.util.concatenate(validas)


# ---------------------------------------------------------------------------
# Toppers 3D
# ---------------------------------------------------------------------------

def generar_3d(texto, tamaño_mm=80, estilo="Elegante", color="Dorado",
               base_tipo="Sólida (plana)", material="PLA",
               tema="General", objeto_decorativo="Ninguno", fuente=None):
    """Generar topper 3D imprimible con STL export.

    `base_tipo`: uno de BASES — cambia la geometría real generada.
    `objeto_decorativo`: agrega un elemento esférico decorativo sobre la base
    cuando corresponde (representa flores/figura/etc. de forma simplificada).
    """
    os.makedirs(CARPETA_SALIDA, exist_ok=True)

    config = ESTILOS.get(estilo, ESTILOS["Elegante"])
    altura_mm = config["altura_mm"]

    piezas = []

    if base_tipo == "Palo (clavar en torta)":
        # Palito delgado que se clava en la torta + placa donde va el diseño
        palo_radio, palo_largo = 1.5, 55
        v, f = _cilindro(palo_radio, palo_largo, z0=-palo_largo)
        piezas.append(trimesh.Trimesh(vertices=v, faces=np.array(f, dtype=np.int64), process=True))

        placa_radio, placa_alt = 18, 3
        v, f = _cilindro(placa_radio, placa_alt, z0=0)
        piezas.append(trimesh.Trimesh(vertices=v, faces=np.array(f, dtype=np.int64), process=True))

        v, f = _cilindro(placa_radio * 0.9, altura_mm, z0=placa_alt, radio_top_factor=0.75)
        piezas.append(trimesh.Trimesh(vertices=v, faces=np.array(f, dtype=np.int64), process=True))

    elif base_tipo == "Redonda (letras paradas)":
        # Base circular ancha y chata + "letras" (bloques) paradas sobre el borde
        base_radio, base_alt = max(20, len(texto) * 4), 3
        v, f = _cilindro(base_radio, base_alt, z0=0)
        piezas.append(trimesh.Trimesh(vertices=v, faces=np.array(f, dtype=np.int64), process=True))

        letras = [c for c in texto.strip()][:14] or ["A"]
        ancho_letra = max(3.0, (base_radio * 1.6) / max(len(letras), 1))
        x0 = -(len(letras) * ancho_letra) / 2 + ancho_letra / 2
        for i, _c in enumerate(letras):
            h = altura_mm * (0.7 + 0.3 * ((i % 3) / 2))  # variación sutil de altura
            piezas.append(_bloque(ancho_letra * 0.7, 3, h, cx=x0 + i * ancho_letra, cy=0, z0=base_alt))

    elif base_tipo == "Redonda con figura arriba":
        base_radio, base_alt = 22, 3
        v, f = _cilindro(base_radio, base_alt, z0=0)
        piezas.append(trimesh.Trimesh(vertices=v, faces=np.array(f, dtype=np.int64), process=True))

        # Tallo corto + figura (esfera) representando objeto decorativo
        v, f = _cilindro(2.5, 10, z0=base_alt)
        piezas.append(trimesh.Trimesh(vertices=v, faces=np.array(f, dtype=np.int64), process=True))
        piezas.append(_esfera(altura_mm * 0.9, centro_z=base_alt + 10 + altura_mm * 0.9))

    elif base_tipo == "Sin base (figura libre)":
        # Solo la figura, apoyada directo en Z=0 (sin placa base)
        piezas.append(_esfera(altura_mm, centro_z=altura_mm))
        v, f = _cilindro(altura_mm * 0.3, altura_mm * 0.6, z0=0)
        piezas.append(trimesh.Trimesh(vertices=v, faces=np.array(f, dtype=np.int64), process=True))

    else:  # "Sólida (plana)" — comportamiento clásico: base + pico cónico
        base_radio, base_alt = 15, 3
        v, f = _cilindro(base_radio, base_alt, z0=0)
        piezas.append(trimesh.Trimesh(vertices=v, faces=np.array(f, dtype=np.int64), process=True))

        v, f = _cilindro(25, altura_mm, z0=base_alt, radio_top_factor=0.8)
        piezas.append(trimesh.Trimesh(vertices=v, faces=np.array(f, dtype=np.int64), process=True))

    # Objeto decorativo adicional (independiente de la base, si se pidió)
    if objeto_decorativo != "Ninguno" and base_tipo not in ("Redonda con figura arriba", "Sin base (figura libre)"):
        z_top = altura_mm + (3 if "Sólida" in base_tipo or "Palo" in base_tipo else 0)
        piezas.append(_esfera(altura_mm * 0.35, centro_z=z_top + altura_mm * 0.35))

    malla = _combinar(piezas)
    malla.fix_normals()

    # Escalar para que encaje en tamaño deseado (ancho/profundidad)
    extents_xy = max(malla.extents[0], malla.extents[1], 1e-6)
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


def preview_html_3d(texto, tamaño_mm=80, estilo="Elegante", base_tipo="Sólida (plana)",
                     color_hex="#cccccc", fuente_ttf=None):
    """Preview HTML (SVG + @font-face real) de topper 3D — refleja texto,
    fuente y tipo de base elegidos."""
    config = ESTILOS.get(estilo, ESTILOS["Elegante"])
    altura_mm = config["altura_mm"]

    css, familia = _font_face_css(fuente_ttf)

    scale = 2.2
    w = max(tamaño_mm * scale, 160)
    h = (altura_mm + 30) * scale

    cx = w / 2
    base_y = h - 20 * scale

    if base_tipo == "Palo (clavar en torta)":
        cuerpo = f'''
        <line x1="{cx}" y1="{base_y}" x2="{cx}" y2="{h-4}" stroke="#8B5A2B" stroke-width="4"/>
        <ellipse cx="{cx}" cy="{base_y}" rx="26" ry="6" fill="#ccc" stroke="#666"/>
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
        cuerpo = f'<ellipse cx="{cx}" cy="{base_y}" rx="{w*0.4}" ry="10" fill="#ddd" stroke="#666"/>' + bloques
    elif base_tipo == "Redonda con figura arriba":
        cuerpo = f'''
        <ellipse cx="{cx}" cy="{base_y}" rx="30" ry="7" fill="#ddd" stroke="#666"/>
        <line x1="{cx}" y1="{base_y}" x2="{cx}" y2="{base_y-15}" stroke="#999" stroke-width="3"/>
        <circle cx="{cx}" cy="{base_y-15-altura_mm*scale*0.5}" r="{altura_mm*scale*0.5}" fill="{color_hex}" stroke="#666" stroke-width="1.5"/>'''
    elif base_tipo == "Sin base (figura libre)":
        cuerpo = f'''
        <circle cx="{cx}" cy="{base_y-altura_mm*scale*0.6}" r="{altura_mm*scale*0.6}" fill="{color_hex}" stroke="#666" stroke-width="1.5"/>'''
    else:  # Sólida (plana)
        cuerpo = f'''
        <rect x="{cx-25}" y="{base_y}" width="50" height="8" fill="#ddd" stroke="#666"/>
        <path d="M {cx-tamaño_mm*scale*0.3} {base_y} L {cx} {base_y-altura_mm*scale} L {cx+tamaño_mm*scale*0.3} {base_y} Z"
              fill="{color_hex}" stroke="#666" stroke-width="1.5"/>'''

    etiqueta_texto = ""
    if base_tipo != "Redonda (letras paradas)":
        etiqueta_texto = f'<text x="{cx}" y="{base_y - altura_mm*scale - 8}" text-anchor="middle" font-size="16" font-family="{familia}" fill="#111" font-weight="bold">{texto[:16]}</text>'

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
