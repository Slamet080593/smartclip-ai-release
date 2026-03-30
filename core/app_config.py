import json
import os
from datetime import datetime
from pathlib import Path

APP_DIR_NAME = "yt-clipper"
DEFAULT_SETTINGS = {
    "output_root": str(Path.home() / "Videos" / "Yt-Clipper"),
    "work_root": str(Path.home() / ".local" / "share" / APP_DIR_NAME),
    "ai_backend": "gemini",
    "render_mode": "Render: CPU",
    "subtitle_font": "Arial",
    "subtitle_color": "Text: White",
    "aspect_mode": "Aspect: Blur Bg",
}


def get_settings_dir() -> Path:
    return Path.home() / ".config" / APP_DIR_NAME


def get_settings_path() -> Path:
    return get_settings_dir() / "settings.json"


def load_settings() -> dict:
    settings = DEFAULT_SETTINGS.copy()
    path = get_settings_path()
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as handle:
                settings.update(json.load(handle))
        except Exception:
            pass
    return settings


def save_settings(settings: dict) -> Path:
    path = get_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = DEFAULT_SETTINGS.copy()
    payload.update(settings)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
    return path


def _normalize_dir(raw_path: str) -> str:
    expanded = os.path.expanduser((raw_path or "").strip())
    return str(Path(expanded).resolve()) if expanded else ""


def sanitize_settings(settings: dict) -> dict:
    sanitized = DEFAULT_SETTINGS.copy()
    sanitized.update(settings or {})
    sanitized["output_root"] = _normalize_dir(sanitized["output_root"]) or DEFAULT_SETTINGS["output_root"]
    sanitized["work_root"] = _normalize_dir(sanitized["work_root"]) or DEFAULT_SETTINGS["work_root"]
    return sanitized


def get_runtime_paths(settings: dict) -> dict:
    clean = sanitize_settings(settings)
    output_root = Path(clean["output_root"])
    work_root = Path(clean["work_root"])
    temp_dir = work_root / "temp"
    assets_dir = work_root / "assets"
    logs_dir = work_root / "logs"
    return {
        "output_root": output_root,
        "work_root": work_root,
        "temp_dir": temp_dir,
        "assets_dir": assets_dir,
        "logs_dir": logs_dir,
        "settings": clean,
    }


def ensure_runtime_dirs(settings: dict) -> dict:
    paths = get_runtime_paths(settings)
    for key in ("output_root", "work_root", "temp_dir", "assets_dir", "logs_dir"):
        paths[key].mkdir(parents=True, exist_ok=True)
    return paths


def build_output_dir(output_root: Path, meta: dict) -> Path:
    today_str = datetime.now().strftime("%Y-%m-%d")
    return output_root / today_str / meta["uploader"] / meta["title"]
