#!/bin/bash
# Inicia el sistema Residencial Torremolinos con un doble clic.
# Funciona en Linux y macOS (el .command de macOS llama a este script).

cd "$(dirname "$0")" || exit 1

PORT=8000
URL="http://127.0.0.1:${PORT}"

PYTHON_BIN="python3"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "No se encontro Python 3. Instalalo antes de continuar."
  echo "Descarga: https://www.python.org/downloads/"
  read -n 1 -s -r -p "Presiona una tecla para cerrar..."
  exit 1
fi

open_browser() {
  sleep 1.5
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$URL" >/dev/null 2>&1
  elif command -v open >/dev/null 2>&1; then
    open "$URL" >/dev/null 2>&1
  fi
}

if curl -s -o /dev/null --max-time 1 "$URL"; then
  echo "El servidor ya esta corriendo en $URL"
  open_browser &
  read -n 1 -s -r -p "Presiona una tecla para cerrar esta ventana..."
  exit 0
fi

echo "Residencial Torremolinos - iniciando en $URL ..."
echo "No cierres esta ventana mientras uses la aplicacion."
echo "Para apagar, usa el boton 'Apagar servidor (Off)' dentro de la app,"
echo "o presiona Ctrl+C aqui."
echo

open_browser &

"$PYTHON_BIN" app.py --port "$PORT"

echo
echo "El servidor se detuvo."
read -n 1 -s -r -p "Presiona una tecla para cerrar esta ventana..."
