import importlib.util
import shutil


def check_runtime_dependencies(ai_backend: str = "gemini") -> dict:
    binaries = {
        "yt-dlp": shutil.which("yt-dlp"),
        "ffmpeg": shutil.which("ffmpeg"),
        "ffprobe": shutil.which("ffprobe"),
        ai_backend: shutil.which(ai_backend),
    }
    optional = {
        "browser_cookie3": importlib.util.find_spec("browser_cookie3") is not None,
    }
    missing_required = [name for name, path in binaries.items() if not path]
    return {
        "binaries": binaries,
        "optional": optional,
        "missing_required": missing_required,
        "ready": not missing_required,
    }


def format_dependency_summary(report: dict) -> str:
    lines = []
    for name, path in report["binaries"].items():
        lines.append(f"{name}: {'OK' if path else 'MISSING'}")
    for name, ok in report["optional"].items():
        lines.append(f"{name}: {'OK' if ok else 'optional-missing'}")
    return "\n".join(lines)
