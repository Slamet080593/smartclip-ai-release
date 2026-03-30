#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$ROOT_DIR/.venv"

log() {
  printf '%s\n' "$1"
}

have_cmd() {
  command -v "$1" >/dev/null 2>&1
}

install_system_packages() {
  if have_cmd apt-get; then
    log "[INFO] Installing Linux packages via apt..."
    sudo apt-get update
    sudo apt-get install -y \
      python3 \
      python3-venv \
      python3-pip \
      python3-tk \
      ffmpeg
    return
  fi

  if have_cmd dnf; then
    log "[INFO] Installing Linux packages via dnf..."
    sudo dnf install -y \
      python3 \
      python3-pip \
      python3-tkinter \
      ffmpeg
    return
  fi

  if have_cmd pacman; then
    log "[INFO] Installing Linux packages via pacman..."
    sudo pacman -Sy --noconfirm \
      python \
      python-pip \
      tk \
      ffmpeg
    return
  fi

  log "[ERROR] Package manager tidak dikenali. Install manual: python3, python3-venv, python3-tk, ffmpeg."
  exit 1
}

ensure_yt_dlp() {
  if have_cmd yt-dlp; then
    log "[INFO] yt-dlp sudah ada di PATH."
    return
  fi
  log "[INFO] Installing yt-dlp via venv pip..."
  "$VENV_DIR/bin/pip" install yt-dlp
}

main() {
  log "== SmartClip AI Linux Installer =="
  install_system_packages

  if [[ ! -d "$VENV_DIR" ]]; then
    log "[INFO] Membuat virtualenv..."
    python3 -m venv "$VENV_DIR"
  fi

  log "[INFO] Menginstall dependency Python..."
  "$VENV_DIR/bin/python" -m pip install --upgrade pip wheel setuptools
  "$VENV_DIR/bin/pip" install -r "$ROOT_DIR/requirements.txt"

  ensure_yt_dlp

  cat <<EOF

[DONE] Install selesai.

Jalankan GUI:
  $ROOT_DIR/run_gui.sh

Jalankan CLI:
  $ROOT_DIR/run_cli.sh

Catatan:
- Pastikan salah satu AI CLI tersedia di PATH: gemini / claude / qwen / codex
- Untuk YouTube yang ketat, login di browser lokal sangat membantu
EOF
}

main "$@"
