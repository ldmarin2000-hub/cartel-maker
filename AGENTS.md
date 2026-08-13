# Cartel Maker — Guía para Agentes de Código

## Resumen del proyecto

**Cartel Maker** es un generador de modelos 3D imprimibles orientado a la impresora Bambu Lab A1 (volumen 256×256×256 mm). Produce carteles de neón trazado, llaveros paramétricos, letras iluminadas de pie, ambigramas de dos caras y esculturas en relieve (litofanía) a partir de imágenes.

Todo el pipeline de geometría está en **Python puro** (shapely + trimesh + numpy + scikit-image). No requiere OpenSCAD ni dependencias de sistema externas.

## Stack tecnológico

- **Lenguaje**: Python 3
- **Framework de UI**: Streamlit (app visual en el navegador)
- **CLI**: menú interactivo en consola (`main.py`)
- **Geometría 2D**: shapely, svgelements (SVG), Pillow (raster)
- **Geometría 3D / mallas**: trimesh, manifold3d, mapbox_earcut, rtree
- **Procesamiento de imágenes**: scikit-image, PIL, numpy, scipy
- **Visualización**: matplotlib (previews estáticos), `<model-viewer>` embebido (visor 3D interactivo offline)
- **Control de versiones**: Git (`.gitignore` excluye `output/`, `presets/`, `.venv/`, `__pycache__/`, archivos generados)

## Estructura de directorios

```
app.py                  # Punto de entrada de la app visual (Streamlit)
main.py                 # Menú interactivo de consola; descubre generadores automáticamente
ui_streamlit.py         # Widgets compartidos de Streamlit (selector de fuente, bloque de presets)
requirements.txt        # Dependencias de Python (sin build system: no hay pyproject.toml ni setup.py)

pages/                  # Cada .py suelto aquí se convierte en página del menú lateral de Streamlit
  1_🔥_Neon.py
  2_🔑_Llavero.py
  3_✂️_Letras.py
  4_🔀_Ambigrama.py
  5_🗿_Esculturas.py

generators/             # Lógica pura de cada generador (sin input()/print())
  neon.py               # Cartel de neón trazado (canal LED)
  llavero.py            # Llavero paramétrico (5 modos de identidad visual)
  letras.py             # Letra iluminada de pie (cáscara hueca para LED)
  ambigrama.py          # Ambigrama de dos caras (intersección booleana 3D)
  esculturas.py         # Relieve desde imagen + estatua 3D completa por IA

core/                   # Librería compartida entre generadores (pura, sin depender de Streamlit)
  pieza.py              # Exportar multicolor/AMS, piezas sueltas, base de escritorio, chequeo A1
  mesh3d.py             # Extrusión 3D, uniones booleanas, orientación de ejes
  texto2d.py            # Texto .ttf -> polígono shapely relleno (con huecos)
  decoraciones.py       # Formas predefinidas + emoji/símbolo + SVG + imagen raster
  fuentes.py            # Catálogo de fuentes curadas + sistema + preview en vivo
  colores.py            # Paleta curada de filamentos PLA reales (~30 tonos)
  preview3d.py          # Visor 3D interactivo offline (<model-viewer> vendoreado)
  heightmap.py          # Imagen -> relieve 3D watertight (grilla de alturas)
  imagen_import.py      # Imagen raster -> vectorización por contorno (silueta)
  svg_import.py         # SVG -> polígono shapely (svgelements, 100% Python)
  raster.py             # Texto -> máscara booleana (Pillow)
  skeleton.py           # Máscara -> esqueleto central (para canal de neón)
  geometry.py           # Construcción de canal/placa/paredes del neón, orejas, salida de cable
  modulos.py            # Partir en módulos con cola de milano si no entra en la A1
  checks.py             # Curvas WS2812, fusión de trazos
  bambu_a1.py           # Constantes y chequeos del volumen de impresión
  presets.py            # Guardar/cargar combinaciones de parámetros (JSON)
  ui.py                 # Helpers de consola (pedir texto/float/opción/sí-no)
  ia3d.py               # Puente a estatua 3D por IA (local vía subprocess o API externa)
  ia3d_worker.py        # Worker que corre en venv aparte (torch + diffusers + rembg)
  exportar_3mf.py       # Exportar .3mf pintado por triángulo (multicolor listo para Bambu Studio)
  storage.py            # Limpieza de archivos temporales viejos

fonts/curadas/          # 24 Google Fonts categorizadas a mano (OFL)
fonts/simbolos/         # Noto Emoji + Noto Sans Symbols 2 (monocromas, para decoraciones)
fonts/                  # Fuentes propias del usuario (adicional a curadas/)
assets/vendor/          # model-viewer.min.js vendoreado (offline)
output/                 # STL, preview PNG, SVG generados (no se versiona)
presets/                # JSON de presets guardados por generador (no se versiona)
scad/                   # Archivos .scad legacy (referencia, ya no se usan en runtime)
```

## Cómo correr el proyecto

### App visual (recomendado)

```bash
streamlit run app.py
```

Abre `http://localhost:8501`. Cada generador tiene su propia página en el menú lateral.

### Menú de consola

```bash
python main.py
```

> En consolas de Windows con acentos rotos, correr antes `chcp 65001`.

### Scripts de conveniencia (Windows)

- `iniciar_app.bat` — crea `.venv` y corre `streamlit run app.py`
- `setup_ia3d.bat` — crea `C:\ia3d_venv` con torch + diffusers + rembg (~3-4 GB), necesario para "Estatua 3D completa (IA local)"

## Convenciones de código

- **Idioma**: todos los comentarios, docstrings, nombres de variables descriptivas, mensajes de UI y README están en **español**.
- **Encoding**: UTF-8 explícito en todos los archivos (`# -*- coding: utf-8 -*-`). En Windows se fuerza UTF-8 en `sys.stdout`/`sys.stderr` desde `main.py`.
- **Estilo**: snake_case para funciones y variables; UPPER_CASE para constantes de módulo.
- **Contrato de generadores**: cada archivo en `generators/` debe exponer:
  - `NOMBRE`: str — nombre corto para el menú
  - `DESCRIPCION`: str — una línea explicativa
  - `generar(**params) -> dict` — función pura (sin I/O) que devuelve rutas, medidas y avisos
  - `ejecutar()` — wrapper de consola que pide parámetros con `core/ui.py` y llama a `generar()`
- **Previews rápidos**: los generadores que lo ameritan (neón, llavero, letras, ambigrama, esculturas) implementan `preview_rapido()` — geometría 2D o malla de baja resolución, sin booleanas 3D ni export, para feedback instantáneo en la UI.
- **Página de Streamlit**: cada `pages/N_emoji_Nombre.py` es solo la capa visual (widgets + llamada al generador). No va lógica de geometría ahí.

## Testing

**No hay suite de tests automatizados** en este proyecto. La verificación se hace de forma manual:

1. Generar un STL y abrirlo en Bambu Studio (o similar) para validar geometría.
2. Revisar que `malla.is_watertight` sea `True` (los generadores lo reportan).
3. Usar el preview rápido y el visor 3D interactivo para juzgar forma y medidas antes de imprimir.

Si se agregan tests, el proyecto no tiene runner configurado; se sugiere usar `pytest` como dependencia de desarrollo.

## Seguridad y datos sensibles

- **API keys**: la página de Esculturas tiene un campo de API key para servicios externos (Tripo3D/Meshy). Usa `type="password"` de Streamlit y vive solo en `st.session_state`; **nunca se guarda en disco ni se commitea**.
- **Archivos subidos**: las imágenes/SVG que sube el usuario se escriben temporalmente en `output/` (no versionado). `core/storage.py` limpia archivos de más de 7 días.
- **Entorno de IA local**: vive completamente aparte en `C:\ia3d_venv` (ruta corta) para evitar el límite de 260 caracteres de Windows con las rutas internas de torch.

## Agregar un generador nuevo

1. Crear `generators/mi_generador.py` con `NOMBRE`, `DESCRIPCION`, `generar(**params)` y `ejecutar()`.
2. Usar `core/pieza.py` para el armado final (export multicolor/sueltas, soporte escritorio, chequeo A1) en vez de reescribirlo.
3. Crear `pages/N_emoji_MiGenerador.py` con widgets + llamada a `generar()`.
4. Para el selector de fuente, usar `ui_streamlit.selector_fuente(...)`; para colores, `core.colores.NOMBRES` + `core.colores.hex_de(...)`.
5. Para presets, poner `key=` a cada widget, juntar en `PRESET_KEYS` y llamar `ui_streamlit.bloque_presets("mi_generador", PRESET_KEYS)`.
6. `main.py` lo descubre automáticamente; Streamlit lo agrega solo al menú por estar en `pages/`.

## Dependencias clave y su rol

| Paquete | Rol |
|---|---|
| `streamlit` | App visual interactiva |
| `trimesh` | Mallas 3D, extrusión, export STL/GLB |
| `manifold3d` | Uniones booleanas 3D robustas (fallback a concatenate) |
| `shapely` | Geometría 2D (buffers, uniones, diferencias) |
| `numpy` | Arrays numéricos, transformaciones |
| `scikit-image` | Marching squares, esqueleto, filtros de imagen |
| `Pillow` | Rasterizar texto, leer imágenes, redimensionar |
| `networkx` | Grafos para conectar componentes (puentes en neón/ambigrama) |
| `scipy` | Operaciones geométricas auxiliares |
| `matplotlib` | Previews estáticos 2D/3D |
| `svgelements` | Leer SVG sin dependencias de sistema (sin Cairo/GTK) |
| `mapbox_earcut` | Triangulación de polígonos para mallas 3D |
| `rtree` | Índice espacial para operaciones shapely/trimesh |

## Notas operativas

- El proyecto está desarrollado y probado en **Windows**. Algunas rutas hardcodean `C:\Windows\Fonts` y `C:\ia3d_venv`.
- El visor 3D es **100% offline**: embebe `assets/vendor/model-viewer.min.js` inline en el HTML; no hace requests a internet.
- No hay proceso de build ni empaquetado: se corre directamente desde el código fuente.
