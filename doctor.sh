#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$ROOT_DIR/.venv"

show_cmd() {
  local name="$1"
  if command -v "$name" >/dev/null 2>&1; then
    printf '%-14s OK    %s\n' "$name" "$(command -v "$name")"
  else
    printf '%-14s MISSING\n' "$name"
  fi
}

echo "== SmartClip AI Doctor =="
show_cmd python3
show_cmd ffmpeg
show_cmd ffprobe
show_cmd yt-dlp
show_cmd gemini
show_cmd claude
show_cmd qwen
show_cmd codex

if [[ -x "$VENV_DIR/bin/python" ]]; then
  echo
  echo "== Python package check (.venv) =="
  "$VENV_DIR/bin/python" - <<'PY'
import importlib.util
modules = [
    "customtkinter",
    "PIL",
    "whisper",
    "yt_dlp",
    "browser_cookie3",
    "youtube_transcript_api",
]
for name in modules:
    ok = importlib.util.find_spec(name) is not None
    print(f"{name:24} {'OK' if ok else 'MISSING'}")
PY
else
  echo
  echo "Virtualenv .venv belum ada. Jalankan ./install_linux.sh dulu."
fi

echo
echo "Tips:"
echo "- Kalau AI CLI ada tapi belum auth, login dulu secara manual."
echo "- Untuk YouTube yang ketat, login di browser lokal membantu yt-dlp lewat cookies browser."
