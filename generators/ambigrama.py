#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generators/ambigrama.py
---------------------------
Generador de ambigramas 3D: una pieza que muestra un contenido (texto o
una forma) mirándola desde ARRIBA/ABAJO, y OTRO contenido distinto
mirándola DE FRENTE — el mismo truco de "de un lado el corazón, del otro
el nombre" pero orientado para que el nombre se lea de arriba/abajo (no
de frente), como un dije que se mira desde ambas caras.

Técnica (la misma que se usa a mano en Tinkercad/similares):
  1) Los dos contenidos se escalan — CADA UNO POR SEPARADO en X e Y, no
     de forma uniforme — para entrar EXACTOS en la misma caja compartida
     (ancho_mm x profundidad_mm x alto_mm). Esto fuerza a los dos a medir
     lo mismo aunque eso distorsione sus proporciones naturales (una
     palabra larga queda con las letras más angostas, por ejemplo).
  2) El lado "de arriba" se extruye derecho a lo largo de Z (sin rotar —
     core/mesh3d.py::extruir_vertical). El lado "de frente" se extruye a
     lo largo de Y (core/mesh3d.py::extruir_de_frente), para que se lea
     mirando el objeto de frente (la cara ancha), no desde el costado
     angosto.
  3) Se hace la intersección booleana de los dos sólidos.
  4) La intersección puede dejar partes sueltas (que no llegan a tocarse
     entre sí) — se sueldan con puentes finos
     (core/mesh3d.py::conectar_componentes_3d).

OJO: como los dos lados se fuerzan a la misma caja, un contenido con
proporciones muy distintas al del otro lado (una palabra larga vs. una
forma compacta) va a salir visiblemente distorsionado/apretado. Avisamos
cuando eso pasa.
"""

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import trimesh
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

from core import bambu_a1, decoraciones, mesh3d, svg_import, texto2d, ui

NOMBRE = "Ambigrama (2 caras)"
DESCRIPCION = "Un contenido de arriba/abajo, otro de frente — mismo objeto, 2 lecturas distintas."

CARPETA_SALIDA = "output"
TIPOS_CONTENIDO = ("texto", "forma", "svg")
DECORACIONES = [n for n in decoraciones.NOMBRES_VALIDOS if n != "ninguno"]


def _preparar_lado_crudo(tipo, valor, ruta_ttf, espaciado_relativo=0.0):
    """tipo: "texto", "forma" o "svg". Devuelve el polígono SIN escalar
    todavía (eso lo hace escalar_a_caja() después, a la caja compartida).
    `espaciado_relativo` (solo para texto) acerca/aleja las letras —
    negativo las junta, hasta tocarse/superponerse (ver
    core/raster.py::rasterizar_con_espaciado) — para que una palabra larga
    entre en una caja angosta sin quedar tan comprimida letra por letra.
    Para "svg", `valor` es la ruta a un .svg propio del usuario."""
    if tipo == "texto":
        if not ruta_ttf or not os.path.exists(ruta_ttf):
            raise FileNotFoundError(f"no encuentro la fuente: {ruta_ttf}")
        poly = texto2d.texto_a_poligono_crudo(valor, ruta_ttf, espaciado_relativo=espaciado_relativo)
        if poly is None:
            raise ValueError(f"no se pudo extraer el texto {valor!r} (probá otra fuente)")
        return poly
    elif tipo == "forma":
        forma = decoraciones.forma(valor, 10)
        if forma is None:
            raise ValueError(f"decoración desconocida: {valor!r}")
        return forma
    elif tipo == "svg":
        if not valor or not os.path.exists(valor):
            raise FileNotFoundError(f"no encuentro el SVG: {valor}")
        poly = svg_import.svg_a_poligono(valor)
        if poly is None:
            raise ValueError(f"no se pudo sacar ninguna forma con área del SVG: {valor}")
        return poly
    else:
        raise ValueError(f"tipo debe ser uno de {TIPOS_CONTENIDO}, recibí {tipo!r}")


FACTOR_AVISO_COMPRESION = 0.6  # por debajo de esto avisamos (pero NO cambiamos el tamaño pedido)


def _avisar_si_comprimido(poly_crudo, ancho_pedido, alto_mm, etiqueta, info):
    """Avisa (sin cambiar nada) si `ancho_pedido` comprime el contenido a
    menos de FACTOR_AVISO_COMPRESION de su ancho natural — la medida que
    pediste se respeta siempre; si hace falta, achicá el espaciado entre
    letras en vez de agrandar la caja."""
    minx, miny, maxx, maxy = poly_crudo.bounds
    alto_real = maxy - miny
    if alto_real <= 0:
        return
    ancho_natural = (maxx - minx) * (alto_mm / alto_real)
    if ancho_pedido < ancho_natural * FACTOR_AVISO_COMPRESION:
        info.append(
            f"'{etiqueta}' se comprime bastante para entrar en {ancho_pedido:.0f}mm "
            f"(ancho natural ~{ancho_natural:.0f}mm) — si las letras se superponen mucho, "
            f"probá un espaciado más negativo o una caja un poco más ancha."
        )


def _etiqueta_lado(tipo, valor):
    """Texto corto para mostrar en el título del preview / nombre de
    archivo — para "svg" usa solo el nombre del ícono, no la ruta
    completa (que puede ser un path temporal feo subido desde la app)."""
    if tipo == "svg" and valor:
        return os.path.splitext(os.path.basename(valor))[0]
    return str(valor)


def _nombre_archivo(valor_frente, valor_costado):
    crudo = f"{valor_frente}_{valor_costado}"
    limpio = "".join(c if c.isalnum() else "_" for c in crudo).strip("_")
    return limpio or "ambigrama"


def _guardar_preview(ruta_png, malla, titulo_frente, titulo_costado):
    tris = malla.vertices[malla.faces]
    (minx, miny, minz), (maxx, maxy, maxz) = malla.bounds
    dx, dy, dz = max(maxx - minx, 1), max(maxy - miny, 1), max(maxz - minz, 1)

    fig = plt.figure(figsize=(10, 5))
    vistas = [(90, -90, f"De arriba: {titulo_frente}"), (0, -90, f"De frente: {titulo_costado}")]
    for i, (elev, azim, titulo) in enumerate(vistas):
        ax = fig.add_subplot(1, 2, i + 1, projection="3d")
        ax.add_collection3d(Poly3DCollection(tris, facecolor="#e91e63", edgecolor=None))
        ax.set_xlim(minx, maxx)
        ax.set_ylim(miny, maxy)
        ax.set_zlim(minz, maxz)
        ax.view_init(elev=elev, azim=azim)
        ax.set_title(titulo)
        ax.set_box_aspect((dx, dy, dz))
        ax.set_axis_off()
    fig.savefig(ruta_png, dpi=110, facecolor="white")
    plt.close(fig)


def generar(tipo_frente, valor_frente, tipo_costado, valor_costado,
            ruta_ttf_frente=None, ruta_ttf_costado=None,
            espaciado_frente=0.0, espaciado_costado=0.0,
            ancho_mm=55, profundidad_mm=20, alto_mm=55,
            agregar_aro=True, aro_radio_hueco=2.0, aro_radio_tab=6.0, aro_borde="auto",
            carpeta_salida=CARPETA_SALIDA):
    """Arma el ambigrama y exporta el STL. Devuelve un dict con la ruta,
    medidas y avisos. No pregunta nada ni imprime nada — así lo puede
    llamar tanto la CLI como la app visual.

    `ancho_mm` x `profundidad_mm` x `alto_mm` es la caja COMPARTIDA a la
    que se fuerzan los dos lados (ver docstring del módulo) — se respeta
    tal cual, no se agranda sola. `espaciado_frente`/`espaciado_costado`
    (solo aplican si ese lado es texto) acercan las letras entre sí para
    que una palabra larga entre mejor en una caja angosta. `aro_borde`
    ("auto"/"min"/"max") elige en qué extremo va el aro — "auto" busca el
    más angosto solo, "min"/"max" lo fuerza a mano si el automático no da
    lo que el usuario quiere (ver core/mesh3d.py::agregar_aro_3d)."""
    poly_frente_crudo = _preparar_lado_crudo(tipo_frente, valor_frente, ruta_ttf_frente, espaciado_frente)
    poly_costado_crudo = _preparar_lado_crudo(tipo_costado, valor_costado, ruta_ttf_costado, espaciado_costado)

    etiqueta_frente = _etiqueta_lado(tipo_frente, valor_frente)
    etiqueta_costado = _etiqueta_lado(tipo_costado, valor_costado)

    info = []
    _avisar_si_comprimido(poly_frente_crudo, ancho_mm, profundidad_mm, etiqueta_frente, info)
    _avisar_si_comprimido(poly_costado_crudo, ancho_mm, alto_mm, etiqueta_costado, info)

    # "arriba": su propio (x,y) queda tal cual en (X,Y) — se lee mirando desde
    # arriba/abajo (eje Z). "de frente": se lee mirando a lo largo del eje Y
    # (la cara ancha ancho_mm x alto_mm), no del costado angosto.
    poly_frente = texto2d.escalar_a_caja(poly_frente_crudo, ancho_mm, profundidad_mm)
    poly_costado = texto2d.escalar_a_caja(poly_costado_crudo, ancho_mm, alto_mm)

    solido_frente = mesh3d.extruir_vertical(poly_frente, alto_mm)
    solido_costado = mesh3d.extruir_de_frente(poly_costado, profundidad_mm)

    malla = trimesh.boolean.intersection([solido_frente, solido_costado], engine="manifold")
    if malla.is_empty or len(malla.vertices) == 0:
        raise ValueError(
            "la intersección salió vacía — probá agrandar la caja (ancho/profundidad/alto) "
            "o cambiar los contenidos"
        )

    # La intersección puede dejar letras sueltas (que no llegan a tocarse entre sí,
    # o ni siquiera tocan la base) — las soldamos con puentes finos para que sea
    # UN solo objeto imprimible, no piezas sueltas flotando.
    malla, n_puentes = mesh3d.conectar_componentes_3d(malla)
    if n_puentes:
        info.append(f"Se agregaron {n_puentes} puente(s) para que las letras/formas sueltas queden en una sola pieza.")

    if agregar_aro:
        malla = mesh3d.agregar_aro_3d(malla, radio_hueco=aro_radio_hueco, radio_tab=aro_radio_tab, borde=aro_borde)
        # El aro también puede quedar sin soldar del todo — mismo remedio.
        malla, n_puentes_aro = mesh3d.conectar_componentes_3d(malla)
        if aro_borde == "auto":
            info.append("Aro agregado en la punta/extremo más angosto del contenido, para colgar de un llavero.")
        else:
            info.append("Aro agregado arriba, en el extremo que elegiste, para colgar de un llavero.")
        if n_puentes_aro:
            info.append(f"El aro necesitó {n_puentes_aro} puente(s) extra para quedar bien soldado.")

    os.makedirs(carpeta_salida, exist_ok=True)
    base_nombre = _nombre_archivo(etiqueta_frente, etiqueta_costado)
    ruta_stl = os.path.join(carpeta_salida, f"ambigrama_{base_nombre}.stl")
    ruta_png = os.path.join(carpeta_salida, f"ambigrama_{base_nombre}_preview.png")

    malla.export(ruta_stl)
    _guardar_preview(ruta_png, malla, etiqueta_frente, etiqueta_costado)

    minx, miny, minz = malla.bounds[0]
    maxx, maxy, maxz = malla.bounds[1]
    entra_a1, mensaje_a1 = bambu_a1.chequear_tamano(
        maxx - minx, maxy - miny, maxz - minz, nombre="ambigrama"
    )

    return {
        "ruta_stl": ruta_stl,
        "ruta_png": ruta_png,
        "ancho_mm": maxx - minx, "profundidad_mm": maxy - miny, "alto_mm": maxz - minz,
        "vertices": len(malla.vertices),
        "watertight": malla.is_watertight,
        "info": info,
        "avisos": [],
        "entra_a1": entra_a1,
        "mensaje_a1": mensaje_a1,
    }


# ---------------------------------------------------------------------------
#  Interfaz de consola (menú de main.py)
# ---------------------------------------------------------------------------
def _pedir_lado(etiqueta):
    tipo = ui.pedir_opcion(f"Lado {etiqueta}: texto, forma o svg", list(TIPOS_CONTENIDO), "texto")
    if tipo == "texto":
        valor = ui.pedir_texto(f"  Texto ({etiqueta})", "Monica")
        from core import fuentes
        nombre_fuente = ui.pedir_texto(f"  Fuente ({etiqueta})", "Comic Sans MS")
        ruta_ttf = nombre_fuente if os.path.exists(nombre_fuente) else fuentes.buscar_por_nombre(nombre_fuente)
        espaciado = ui.pedir_float(f"  Espaciado entre letras ({etiqueta}, negativo = más juntas)", 0.0)
        return tipo, valor, ruta_ttf or nombre_fuente, espaciado
    elif tipo == "svg":
        valor = ui.pedir_texto(f"  Ruta al .svg ({etiqueta})", "")
        return tipo, valor, None, 0.0
    else:
        valor = ui.pedir_opcion(f"  Forma ({etiqueta})", DECORACIONES, "corazon")
        return tipo, valor, None, 0.0


def ejecutar():
    print(f"\n{NOMBRE}")
    print("  Armás 2 lados: uno se ve mirando desde ARRIBA/ABAJO, el otro DE FRENTE (mismo objeto, 2 lecturas).")
    print("  Los dos se fuerzan a la MISMA caja (por defecto 55x20x55mm), como en el original.")

    tipo_f, valor_f, ttf_f, esp_f = _pedir_lado("de arriba")
    tipo_c, valor_c, ttf_c, esp_c = _pedir_lado("de frente")

    print(f"\n  » Arriba/abajo: {valor_f!r} ({tipo_f})   De frente: {valor_c!r} ({tipo_c})")
    print("  (armando la geometría e intersectando, puede tardar unos segundos...)")

    try:
        r = generar(tipo_f, valor_f, tipo_c, valor_c, ruta_ttf_frente=ttf_f, ruta_ttf_costado=ttf_c,
                    espaciado_frente=esp_f, espaciado_costado=esp_c)
    except (FileNotFoundError, ValueError) as e:
        print(f"  ERROR: {e}")
        return

    print(f"  tamaño ~ {r['ancho_mm']:.0f} x {r['profundidad_mm']:.0f} x {r['alto_mm']:.0f} mm")
    for nota in r["info"]:
        print(f"  · {nota}")
    for aviso in r["avisos"]:
        print(f"  ⚠ {aviso}")
    print(f"  ✓ STL -> {r['ruta_stl']}  ({r['vertices']} vért., watertight={r['watertight']})")
    print(f"  ✓ preview -> {r['ruta_png']}")
    print(f"  {'✓' if r['entra_a1'] else '⚠'} {r['mensaje_a1']}")
    print()
