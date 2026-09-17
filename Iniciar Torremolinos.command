#!/bin/bash
set -e

# macOS: doble clic en este archivo para iniciar Residencial Torremolinos.
cd "$(dirname "$0")" || exit 1
exec ./iniciar_torremolinos.sh
