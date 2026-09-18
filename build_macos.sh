#!/bin/bash

set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Este script genera la aplicacion de macOS y debe ejecutarse en macOS."
  exit 1
fi

cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON_BIN:-python3}"
SKIP_INSTALL="${1:-}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "No se encontro Python 3. Instalalo antes de continuar."
  exit 1
fi

if [[ "$SKIP_INSTALL" != "--skip-install" ]]; then
  "$PYTHON_BIN" -m pip install -r requirements.txt -r requirements-build.txt
fi

"$PYTHON_BIN" -m PyInstaller \
  --noconfirm \
  --clean \
  --onedir \
  --windowed \
  --name Torremolinos \
  --add-data "static:static" \
  --hidden-import fitz \
  --hidden-import pymupdf \
  --collect-all reportlab \
  --collect-all msal \
  app.py

mkdir -p dist/data/attachments

if [[ -f data/torremolinos.sqlite3 && ! -f dist/data/torremolinos.sqlite3 ]]; then
  cp data/torremolinos.sqlite3 dist/data/torremolinos.sqlite3
fi

if [[ -d data/attachments ]]; then
  cp -R data/attachments/. dist/data/attachments/
fi

echo
echo "Aplicacion creada en: dist/Torremolinos.app"
echo "Los datos persistentes se guardan en: dist/data"
echo "Abre Torremolinos.app con doble clic para iniciar el sistema."
