#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_ROOT"

APP_NAME="${1:-Torremolinos}"
PYTHON_BIN="python3"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "No se encontro Python 3."
  exit 1
fi

case "$(uname -s)" in
  Linux|Darwin) ;;
  *)
    echo "Este constructor funciona en Linux y macOS."
    exit 1
    ;;
esac

"$PYTHON_BIN" -m pip install -r requirements.txt -r requirements-build.txt
"$PYTHON_BIN" -m PyInstaller \
  --noconfirm \
  --clean \
  --onefile \
  --console \
  --name "$APP_NAME" \
  --add-data "static:static" \
  --hidden-import fitz \
  --hidden-import pymupdf \
  --collect-all reportlab \
  --collect-all msal \
  app.py

mkdir -p "dist/data/attachments"
if [[ -f "data/torremolinos.sqlite3" && ! -f "dist/data/torremolinos.sqlite3" ]]; then
  cp "data/torremolinos.sqlite3" "dist/data/torremolinos.sqlite3"
fi
if [[ -d "data/attachments" ]]; then
  cp -R "data/attachments/." "dist/data/attachments/"
fi

echo
echo "Ejecutable creado en: dist/$APP_NAME"
echo "Los datos persistentes se guardan en: dist/data"
