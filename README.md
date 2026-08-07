# Cartel Maker

Generador de modelos 3D imprimibles (Bambu Lab A1): carteles de neón,
carteles LED de letras de palo, llaveros, y lo que se vaya agregando.

## Instalación

1. Tener Python instalado (Windows).
2. Instalar dependencias:

   ```bash
   pip install -r requirements.txt
   ```

3. Todos los generadores (neón, llavero, letras, ambigrama) son Python
   puro — no hace falta instalar nada más, ni OpenSCAD. Las fuentes se
   listan automáticamente (12 curadas en `fonts/curadas/` + las que
   pongas en `fonts/` + las instaladas en Windows, `C:\Windows\Fonts`),
   agrupadas por estilo con preview real tipeado en la fuente — así no
   hay que escribir rutas a mano ni adivinar cómo se ve.

## Uso

### App visual (recomendado)

```bash
streamlit run app.py
```

Abre una pestaña del navegador en `http://localhost:8501`. Cada generador
tiene su propia página en el menú de la izquierda: completás el formulario,
apretás **Generar**, y ves el preview 3D interactivo (arrastrar para
rotar, scroll para zoom, auto-rotate), las medidas, los avisos y el botón
de descarga del STL ahí mismo.

### Menú de consola (alternativa)

```bash
python main.py
```

> Si ves los acentos/tildes rotos en la consola de Windows, corré antes
> `chcp 65001` (pone la terminal en UTF-8). No hace falta en la terminal
> integrada de VSCode ni en PowerShell 7.

Elegís un generador del menú, contestás los parámetros que te pregunta (o
dejás los defaults), y el STL + preview quedan en `output/`.

### En ambos casos

Al final se muestra:

- el tamaño final del modelo en mm,
- si entra o no en el plato de la Bambu A1 (256×256×256 mm) sin partir en
  módulos,
- avisos relevantes del generador (fusión de trazos, curvas muy cerradas
  para WS2812, etc.).

## Estructura del proyecto

```
app.py             punto de entrada de la app visual (Streamlit)
pages/             una página de Streamlit por generador (capa visual)
main.py            menú interactivo de consola, descubre generadores automáticamente
core/               lógica compartida entre generadores (raster, esqueleto,
                    texto2d/decoraciones, geometría, malla 3D, preview 2D,
                    preview3d (visor interactivo), pieza (mecánica de
                    armado final: nombre de archivo, export multicolor/
                    sueltas, soporte de escritorio, chequeo A1), colores
                    (paleta de filamento curada), fuentes (catálogo +
                    categorías + preview en vivo), presets (guardar/cargar
                    combinaciones de parámetros), chequeos, ui, wrapper
                    OpenSCAD)
generators/         un archivo por generador (neon.py, letras.py, llavero.py):
                    generar() es la lógica pura que usan tanto app.py como main.py;
                    llavero.py y letras.py también tienen preview_rapido()
                    (2D, sin mesh3d/booleanas, para la vista rápida)
ui_streamlit.py     widgets de Streamlit compartidos entre páginas (selector
                    de fuente, bloque de presets) — no es core/ porque SÍ
                    depende de Streamlit; no va en pages/ porque cualquier
                    .py suelto ahí se vuelve una página nueva del menú
scad/               archivos .scad paramétricos (Customizer de OpenSCAD)
fonts/curadas/      12 Google Fonts bajadas y categorizadas a mano (script,
                    manuscrita, display, redondeada) — licencia OFL, ver
                    fonts/curadas/LICENSES/
fonts/              tus propios .ttf (además de los de fonts/curadas/)
assets/vendor/      model-viewer.min.js vendoreado (Apache-2.0, Google) para
                    el visor 3D — offline, no pide nada a internet
output/             STL + preview + SVG generados (no se versiona)
presets/            combinaciones de parámetros guardadas, por generador
                    (no se versiona — son tuyos, no del repo)
```

### Presets y vista rápida

Cada página tiene un bloque **"💾 Presets guardados"** arriba del
formulario: guardá la combinación actual de parámetros con un nombre
(`core/presets.py`, un .json por preset en `presets/<generador>/`) y
volvé a cargarla después — pisa los widgets del formulario vía
`st.session_state` y fuerza un rerun (`ui_streamlit.py::bloque_presets`).
No cubre `st.file_uploader` (SVG propio): esos no se pueden pre-cargar
programáticamente.

Llavero y Letras (los dos generadores con sliders de posición de
decoración, donde más hace falta feedback inmediato) muestran además una
**vista rápida en 2D** que se actualiza sola con cada cambio de parámetro,
sin tocar "Generar": es la geometría plana (texto + decoración
posicionada), sin el hueco/las booleanas 3D reales, así que sale en
~0.2-0.3s en vez de los varios segundos que tarda la malla 3D
watertight — `generators/llavero.py::preview_rapido()` y
`generators/letras.py::preview_rapido()`, cacheadas con `st.cache_data`
para que ajustar un slider y volver al valor anterior sea instantáneo.
Neón y Ambigrama no la tienen: en neón el trazado ya se ve razonablemente
bien por la tipografía elegida (menos que ajustar a ciegas), y en
ambigrama el resultado real depende de la intersección booleana entre
los 2 lados — un preview plano de un solo lado sería más confuso que
útil.

### Fuentes y colores curados

El selector de fuente (`ui_streamlit.py::selector_fuente`, usado en las 4
páginas) agrupa por categoría — Script, Manuscrita, Display, Redondeada
(las 12 curadas de `fonts/curadas/`), después "Tus fuentes" (`fonts/`) y
al final "Sistema" (Windows, suelen ser cientos) — y debajo muestra un
preview real: el texto tipeado de verdad en la fuente elegida (no una
imagen genérica "Aa"), embebiendo el .ttf como `@font-face` en base64
(`core/fuentes.py::html_preview_fuente`). Se ve exactamente cómo va a
quedar antes de generar nada.

Los colores (`core/colores.py`) son una paleta curada de ~22 tonos que
se corresponden con filamentos PLA reales (no nombres CSS genéricos
como "HotPink") — el llavero la usa para elegir el color real de cada
pieza, y el resto de los generadores la usa como referencia de color en
el visor 3D (no cambia el STL, es para que el preview se parezca a lo
que vas a imprimir y sepas qué filamento comprar).

### Preview 3D interactivo (`core/preview3d.py`)

Cada página muestra un visor 3D real en vez de una imagen estática: arma
una escena trimesh con los STL ya exportados (cada pieza de su color:
letra, tapa, soporte, decoraciones), la exporta a GLB en memoria, y la
embebe en un `<model-viewer>` (Google, offline — el bundle vive
vendoreado en `assets/vendor/`, no depende de internet ni de instalar
nada aparte). Rotar/zoom/pan de verdad, sombra y luz — no 2 ángulos fijos
como el preview anterior. Las piezas pensadas para imprimirse sueltas
(tapa, soporte de escritorio, decoraciones sin AMS) se muestran en su
posición real cuando se conoce el offset (ej. la tapa, que va pegada
justo detrás del hueco); el soporte de escritorio va rotado respecto de
la letra (encastra desde abajo) así que se muestra en su propio visor
aparte para no dar una posición falsa. Un STL combinado tipo AMS
(varios cuerpos sin fusionar) se separa en memoria (`mesh.split()`) y
cada cuerpo se colorea distinto, para distinguir las piezas aunque
vengan en un solo archivo.

### Mecánica compartida (`core/pieza.py`)

Lo que se repetía casi textual en los 4 generadores (armar el resultado
final, no la geometría en sí, que es propia de cada uno) está en
`core/pieza.py` — un generador nuevo (lámpara, accesorio, lo que sea)
arranca con esto ya resuelto:

- `nombre_archivo(texto, default)` — sanitiza un nombre para usarlo de
  archivo.
- `exportar_multicolor(piezas, ruta_stl)` — combina piezas ya
  posicionadas en un solo STL sin fusionar (truco AMS: en Bambu Studio,
  "Partir en objetos" las separa para pintar cada una).
- `exportar_piezas_sueltas(piezas_con_nombre, carpeta_salida, prefijo)`
  — un STL por pieza, para pegar a mano.
- `exportar_base_escritorio(...)` — la base con ranura a presión
  (`core/soporte.py`) que ya usan el neón y la letra iluminada.
- `chequear_desde_malla(malla, nombre)` — mide por bounds y chequea
  contra la Bambu A1 (`core/bambu_a1.py`) en un solo llamado.

Cada función es un primitivo independiente — la política (qué exportar
suelto, qué combinar, cuándo agregar soporte) sigue en cada
`generators/*.py`, que es donde varía de verdad entre un llavero y una
letra iluminada; acá solo vive el mecanismo que se repetía igual.

### Agregar un generador nuevo

1. Crear `generators/mi_generador.py` con una función `generar(**params)`
   que haga todo el trabajo (sin `input()`/`print()`) y devuelva un dict
   con rutas, medidas y avisos — más `NOMBRE`, `DESCRIPCION` y `ejecutar()`
   (wrapper de consola que pide los parámetros con `core/ui.py` y llama a
   `generar()`). Para el armado final (nombre de archivo, export
   multicolor/sueltas, soporte de escritorio, chequeo A1), usar
   `core/pieza.py` en vez de reescribirlo.
2. Sumar `pages/N_emoji_MiGenerador.py`: los widgets del formulario +
   `generators.mi_generador.generar(...)` — para el selector de fuente,
   usar `ui_streamlit.selector_fuente(...)` (agrupado + preview en vivo,
   no reescribirlo); para el color, las opciones de `core.colores.NOMBRES`
   + `core.colores.hex_de(...)`; para el preview 3D, armar la lista de
   piezas (`{"ruta_stl", "color", "nombre"}`) y pasarla a
   `core.preview3d.armar_html_visor(...)`; para presets, ponerle `key=`
   a cada widget que valga la pena guardar, juntar esos keys en una lista
   `PRESET_KEYS`, y llamar `ui_streamlit.bloque_presets("mi_generador",
   PRESET_KEYS)` arriba del formulario. Si además conviene una vista
   rápida (generadores con sliders de posición, tipo llavero/letras),
   sumar un `preview_rapido(...)` al generador que arme solo la
   geometría 2D (sin mesh3d/booleanas) y llamarlo cacheado con
   `st.cache_data` en cada rerun de la página, no solo al generar.
3. Listo — `main.py` lo lista solo por consola, y Streamlit lo agrega solo
   al menú lateral por estar en `pages/`.

## Estado actual

- **Neón**: pipeline completo enganchado al menú y a la app visual
  (`generators/neon.py` + `core/*`). Si el cartel no entra en la Bambu A1 se
  parte solo en módulos con cola de milano (`core/modulos.py`), y agrega
  automáticamente un canalcito de salida de cable y orejas de montaje tipo
  bocallave (`core/geometry.py`). Las fuentes se eligen de una lista (las
  instaladas en Windows + las de `fonts/`), sin escribir rutas
  (`core/fuentes.py`). Placa de fondo con 3 variantes: `contorno` (con
  puentes estructurales automáticos para que las letras sueltas impriman
  como una sola pieza), `rect_hundido` (rectángulo macizo, canal hundido) y
  `rect_plano` (rectángulo fino con las letras en relieve — mismo gasto de
  material que "contorno" pero con el respaldo conectado de "rect_hundido").
  Para el cableado: un agujero hacia atrás en cada punta suelta del
  recorrido (donde termina/empieza cada tramo de LED) para soldar/conectar
  ahí, más un canalcito de salida en el punto más conveniente — el cable
  entre letras corre pegado a la parte de atrás del cartel. Si dos puntas
  quedan a menos de `diámetro del agujero + pared_mm` de distancia, se
  agrupan en un solo agujero en vez de dejar dos pegados con una pared de
  plástico demasiado fina entre ellos. Montaje con 3
  opciones: `colgado` (orejas con bocallave), `escritorio` (una pata abajo
  que encastra a presión en una base impresa aparte —
  `core/soporte.py`/`_base_escritorio.stl`) o `ninguno`. Control de
  "redondeo de bordes" (mm) para suavizar esquinas filosas que a veces deja
  el trazado en curvas cerradas de la fuente.
- **Llavero**: **Python puro, sin OpenSCAD** (`generators/llavero.py` +
  `core/texto2d.py` + `core/decoraciones.py` + `core/mesh3d.py`). El texto
  se saca directo del contorno de la fuente (con huecos correctos, ej. la
  "o"), así que las medidas son reales — ya no estimadas. 8 decoraciones
  (corazón, estrella, flor, gato, rayo, luna, rombo, círculo) porteadas a
  shapely, más la opción de subir un ícono/logo propio en SVG
  (`core/svg_import.py`, ver más abajo). Exporta un STL por pieza (base y
  texto), más un preview a
  color. Toggle "Tengo AMS": con AMS se exporta además un STL multicolor
  (base + texto ya combinados como cuerpos separados en su posición real,
  vía `trimesh.util.concatenate`, sin fusionar) — un solo archivo, un solo
  import a Bambu Studio, sin el problema de que el slicer reacomode 2 STL
  sueltos y los desalinee. Ahí adentro: clic derecho → "Partir en objetos"
  para pintarlas cada una de su color. Sin AMS, cada pieza se exporta
  apoyada en el suelo para imprimirla sola y pegarla después.
  `scad/llaveros.scad` queda como referencia/backup, ya no se usa.
- **Ambigrama**: enganchado al menú y a la app visual
  (`generators/ambigrama.py` + `core/mesh3d.py`). Un contenido (texto o
  decoración) de arriba/abajo y otro de frente — cada uno extruido en un eje
  perpendicular al otro y unidos por intersección booleana, con aro para
  colgar (soldado, no flotando). Los dos lados se fuerzan a la MISMA caja
  compartida (ancho x profundidad x alto, default 55x20x55 — la misma
  técnica que a mano en Tinkercad) y esa medida se respeta tal cual, no se
  agranda sola. Si el texto no entra cómodo, hay control de espaciado
  entre letras (negativo = se juntan/superponen) para que palabras largas
  entren mejor en cajas angostas — avisa cuando la compresión es fuerte
  (hay un límite físico: una palabra muy larga en una caja muy angosta no
  entra legible por más que se ajuste el espaciado). La intersección
  booleana puede dejar letras sueltas (sin tocarse entre sí, o sin tocar
  la base) — se sueldan automáticamente con puentes finos
  (`core/mesh3d.py::conectar_componentes_3d`, mismo enfoque de árbol de
  expansión mínima que usa el neón en 2D) para que sea una sola pieza
  imprimible y watertight. El aro para colgar tiene 4 posiciones manuales
  además de la automática (2 discos en los bordes del contenido "de
  arriba", 2 loops parados que nacen del contenido "de frente" — arriba o
  abajo), para elegir a mano si el automático no da lo que se busca.
- **Formas propias (SVG)** (`core/svg_import.py`): tanto el llavero como
  el ambigrama aceptan, además de la lista de decoraciones predefinidas,
  un ícono/logo cualquiera en SVG — un solo color, sin fotos ni
  degradados (path/rect/circle/polygon/etc., con transforms y grupos
  anidados). Usa `svgelements` (100% Python) para leer el SVG y muestrear
  cada curva a puntos; los subtrazados contenidos adentro de otro se
  restan como huecos (`core/poligonos.py`, compartido con el texto de
  fuentes) — mismo resultado final que una decoración de la lista, así se
  usa igual en el resto del pipeline. No hace falta instalar nada aparte
  (a diferencia de cairosvg/svglib, que en Windows piden tener Cairo/GTK
  instalado por separado).
- **Letra iluminada de pie** (`generators/letras.py`): una letra/inicial
  grande, hueca por dentro para meterle una luz LED — Python puro,
  reutiliza `core/texto2d.py` (la letra como polígono relleno) y
  `core/mesh3d.py` (extrusión/booleanas). La cáscara queda con la cara de
  adelante y las paredes finas (`espesor_pared_mm`, para que pase la luz)
  y el fondo ABIERTO (para insertar el LED/pila y poder cambiarla) — si
  algún trazo de la letra es más angosto que 2x el espesor de pared, esa
  parte queda maciza en vez de romperse (y avisa). El offset negativo
  para el hueco usa `join_style` redondeado, no mitre — con mitre, los
  ángulos agudos de letras como la "M" generaban geometría degenerada al
  extruir. Reutiliza el mismo soporte de escritorio que el neón
  (`core/geometry.py::agregar_pata_escritorio` + `core/soporte.py`) para
  las letras que no se paran solas: agrega una pata sólida (sin hueco,
  para que aguante peso) en el punto con más material disponible. Exporta
  además una TAPA aparte (mismo contorno que la letra, sólida y fina, ver
  `_armar_tapa`) para cerrar el hueco después de meter el LED, con un
  agujerito (`agujero_cable_diam_mm`) cerca del borde inferior para sacar
  el cable — busca un punto que caiga en material sólido (no en un hueco
  de la letra, como el interior de una "O") antes de perforar; si no
  encuentra ninguno, exporta la tapa igual pero avisa que hay que
  taladrarla a mano. Nombre en cursiva pegado abajo (opcional): macizo,
  sin hueco (no lleva luz), soldado a la letra como una sola pieza del
  mismo color (`_armar_nombre_cursiva`) — si también hay soporte de
  escritorio, la pata sale del borde de abajo del conjunto letra+nombre,
  no de la letra sola. Decoraciones sueltas en el frente (opcional, hasta
  4): reutiliza las formas de `core/decoraciones.py` (las mismas del
  llavero — corazón, estrella, flor, gato, rayo, luna, rombo, círculo),
  posicionadas en % dentro de la caja de la letra y protruyendo hacia el
  que mira el cartel (`_armar_decoraciones_frente`) — quedan como piezas
  sueltas para pintar de otro color: un STL por decoración para pegar a
  mano, o un solo STL multicolor si hay AMS (mismo criterio que el
  llavero).
