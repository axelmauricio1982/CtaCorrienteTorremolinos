@echo off
setlocal
cd /d "%~dp0"

set PORT=8000
set URL=http://127.0.0.1:%PORT%

set PYTHON_BIN=
where python >nul 2>nul && set PYTHON_BIN=python
if not defined PYTHON_BIN (
  where python3 >nul 2>nul && set PYTHON_BIN=python3
)
if not defined PYTHON_BIN (
  echo No se encontro Python. Instalalo desde https://www.python.org/downloads/
  pause
  exit /b 1
)

curl -s -o nul --max-time 1 %URL% >nul 2>nul
if %errorlevel% equ 0 (
  echo El servidor ya esta corriendo en %URL%
  start "" "%URL%"
  pause
  exit /b 0
)

echo Residencial Torremolinos - iniciando en %URL% ...
echo No cierres esta ventana mientras uses la aplicacion.
echo Para apagar, usa el boton "Apagar servidor (Off)" dentro de la app,
echo o presiona Ctrl+C aqui.
echo.

start "" cmd /c "timeout /t 2 /nobreak >nul & start "" "%URL%""

%PYTHON_BIN% app.py --port %PORT%

echo.
echo El servidor se detuvo.
pause
