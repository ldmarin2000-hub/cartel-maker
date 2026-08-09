@echo off
REM setup_ia3d.bat
REM ---------------
REM Crea el entorno aparte para "Estatua 3D completa (IA local)" del
REM generador de Esculturas. Va en C:\ia3d_venv (ruta corta a
REM proposito) en vez de dentro del proyecto: los archivos internos de
REM licencia de torch tienen rutas tan anidadas que rompen el limite
REM de 260 caracteres de Windows si el proyecto vive en una carpeta
REM con nombre largo (como "Somos paithon labs\Iskra App\cartel-maker").
REM
REM Ocupa entre 3 y 4 GB en el disco C: (torch + diffusers +
REM transformers + rembg + matplotlib). Los pesos del modelo
REM (Shap-E, ~1-2 GB mas) se descargan solos la primera vez que se usa
REM la funcion, no aca.
REM
REM Correr una sola vez. Si ya existe C:\ia3d_venv, no hace falta
REM correrlo de nuevo.

echo Creando entorno para "Estatua 3D completa (IA local)"...
py -3 -m venv C:\ia3d_venv
if errorlevel 1 goto :error

echo Instalando torch y torchvision (CPU)...
C:\ia3d_venv\Scripts\python.exe -m pip install --index-url https://download.pytorch.org/whl/cpu torch torchvision --no-cache-dir
if errorlevel 1 goto :error

echo Instalando diffusers, transformers, rembg[cpu], matplotlib, scikit-image...
C:\ia3d_venv\Scripts\python.exe -m pip install diffusers transformers accelerate "rembg[cpu]" pillow numpy trimesh matplotlib scikit-image --no-cache-dir
if errorlevel 1 goto :error

echo.
echo Listo. La primera vez que generes una estatua va a tardar mas
echo porque ademas descarga los pesos del modelo (~1-2 GB).
pause
exit /b 0

:error
echo.
echo Algo fallo. Revisa el mensaje de arriba.
pause
exit /b 1
