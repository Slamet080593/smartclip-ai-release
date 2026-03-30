#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$ROOT_DIR/.venv"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "[ERROR] Virtualenv belum siap. Jalankan ./install_linux.sh dulu."
  exit 1
fi

exec "$VENV_DIR/bin/python" "$ROOT_DIR/gui_app.py"
