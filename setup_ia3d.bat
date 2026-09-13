@echo off
REM setup_ia3d.bat
REM ---------------
REM Crea el entorno aparte para "Estatua 3D completa (IA local)" del
REM generador de Esculturas — usa TripoSR (Stability AI + Tripo, 2024),
REM un reconstructor feed-forward mucho mas fiel a la foto real y mas
REM rapido que Shap-E (el modelo viejo, 2022, sigue en core/ia3d_worker.py
REM sin usarse). Va en C:\ia3d_venv (ruta corta a proposito) en vez de
REM dentro del proyecto: los archivos internos de licencia de torch
REM tienen rutas tan anidadas que rompen el limite de 260 caracteres de
REM Windows si el proyecto vive en una carpeta con nombre largo (como
REM "Somos paithon labs\Iskra App\cartel-maker").
REM
REM Ocupa unos 3-4 GB en el disco C: (torch + transformers + rembg +
REM matplotlib + el codigo fuente de TripoSR). Los pesos del modelo
REM (~150MB) se descargan solos la primera vez que se usa la funcion,
REM no aca.
REM
REM Requiere Git en PATH (para clonar TripoSR) y NO requiere compilador
REM de C++/CUDA — la extension nativa que pide TripoSR (torchmcubes) se
REM reemplaza por PyMCubes (wheels precompilados, ver
REM ia3d_setup_patches\isosurface.py) porque compilar torchmcubes de
REM cero necesita Visual Studio Build Tools, que la mayoria de las
REM maquinas no tiene instalado.
REM
REM Correr una sola vez. Si ya existe C:\ia3d_venv, no hace falta
REM correrlo de nuevo.

echo Creando entorno para "Estatua 3D completa (IA local)"...
py -3 -m venv C:\ia3d_venv
if errorlevel 1 goto :error

echo Instalando torch y torchvision (CPU)...
C:\ia3d_venv\Scripts\python.exe -m pip install --index-url https://download.pytorch.org/whl/cpu torch torchvision --no-cache-dir
if errorlevel 1 goto :error

echo Instalando transformers (version fija 4.35.0 - TripoSR necesita esta
echo version exacta, una mas nueva rompe la arquitectura del backbone DINO)...
C:\ia3d_venv\Scripts\python.exe -m pip install "transformers==4.35.0" --no-cache-dir
if errorlevel 1 goto :error

echo Instalando PyMCubes, omegaconf, einops, rembg[cpu], trimesh, matplotlib, scikit-image, imageio...
C:\ia3d_venv\Scripts\python.exe -m pip install PyMCubes omegaconf einops "rembg[cpu]" pillow numpy trimesh matplotlib scikit-image "imageio[ffmpeg]" --no-cache-dir
if errorlevel 1 goto :error

echo Descargando el codigo fuente de TripoSR (no tiene paquete pip oficial)...
if exist C:\ia3d_venv\triposr_src (
    echo   ya existe, salteando clone
) else (
    git clone --depth 1 https://github.com/VAST-AI-Research/TripoSR.git C:\ia3d_venv\triposr_src
    if errorlevel 1 goto :error
)

echo Aplicando parche local (torchmcubes -^> PyMCubes, sin compilador)...
copy /Y ia3d_setup_patches\isosurface.py C:\ia3d_venv\triposr_src\tsr\models\isosurface.py
if errorlevel 1 goto :error

echo.
echo Listo. La primera vez que generes una estatua va a tardar un poco
echo mas porque ademas descarga los pesos del modelo (~150MB).
pause
exit /b 0

:error
echo.
echo Algo fallo. Revisa el mensaje de arriba.
pause
exit /b 1
