import os
import subprocess
import json
import shutil
from pathlib import Path

COMMON_CLI_DIRS = (
    Path.home() / ".local" / "bin",
    Path.home() / ".opencode" / "bin",
)


def _resolve_cli_command(cli_cmd: str) -> str | None:
    direct = shutil.which(cli_cmd)
    if direct:
        return direct

    for directory in COMMON_CLI_DIRS:
        candidate = directory / cli_cmd
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)

    nvm_root = Path.home() / ".nvm" / "versions" / "node"
    if nvm_root.exists():
        candidates = sorted(nvm_root.glob(f"*/bin/{cli_cmd}"))
        for candidate in reversed(candidates):
            if candidate.exists() and os.access(candidate, os.X_OK):
                return str(candidate)
    return None


def _build_runtime_env(resolved_cmd: str | None) -> dict:
    env = os.environ.copy()
    extra_dirs = [str(path) for path in COMMON_CLI_DIRS if path.exists()]
    nvm_root = Path.home() / ".nvm" / "versions" / "node"
    if nvm_root.exists():
        extra_dirs.extend(str(path.parent) for path in sorted(nvm_root.glob("*/bin/codex")))
        extra_dirs.extend(str(path.parent) for path in sorted(nvm_root.glob("*/bin/gemini")))
        extra_dirs.extend(str(path.parent) for path in sorted(nvm_root.glob("*/bin/claude")))
        extra_dirs.extend(str(path.parent) for path in sorted(nvm_root.glob("*/bin/qwen")))
    if resolved_cmd:
        extra_dirs.insert(0, str(Path(resolved_cmd).parent))

    existing_path = env.get("PATH", "")
    deduped = []
    for item in extra_dirs + existing_path.split(os.pathsep):
        cleaned = item.strip()
        if cleaned and cleaned not in deduped:
            deduped.append(cleaned)
    env["PATH"] = os.pathsep.join(deduped)
    return env

def _extract_json_array(raw_output: str) -> list:
    decoder = json.JSONDecoder()
    for index, char in enumerate(raw_output):
        if char != "[":
            continue
        try:
            payload, _ = decoder.raw_decode(raw_output[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, list):
            return payload
    raise json.JSONDecodeError("No JSON array found", raw_output, 0)

def analyze_transcript(prompt_text: str, cli_cmd: str, params: dict, temp_dir: str = "temp") -> list:
    """
    Meminta CLI agent (gemini/claude/qwen/codex) untuk mendeteksi segmen paling viral.
    Menggunakan pipa shell untuk menghindari batas panjang argumen.
    """
    max_clips = params.get("max", "3")
    min_s = params.get("min_s", "40")
    max_s = params.get("max_s", "60")
    moment = params.get("moment", "Default")
    
    if "Default" in moment:
        moment_instruction = "yang paling viral (ada hook, konflik, atau mengejutkan)"
    else:
        moment_instruction = f"yang paling viral dengan FOKUS UTAMA PADA MOMEN '{moment}' (wajib menonjolkan nuansa emosi {moment})"
        
    system_prompt = (
        f"Kamu adalah Produser YouTube Shorts/TikTok ahli. "
        f"Baca transkrip podcast ini dan carikan {max_clips} momen/segmen berdurasi "
        f"antara {min_s} hingga {max_s} detik {moment_instruction}.\n\n"
        "OUTPUT HARUS BERUPA JSON ARRAY murni (tanpa Markdown ```json, tanpa teks pengantar):\n"
        '[\n'
        '  {\n'
        '    "start": "00:05:10.250",\n'
        '    "end": "00:06:05.800",\n'
        '    "title": "Judul Menarik",\n'
        '    "reason": "Alasan kepilih clip ini",\n'
        '    "caption": "Caption TikTok dengan hook dan beberapa #hashtag relevan",\n'
        '    "credit": "Credit format untuk sosmed (misal: cc @creator_name)"\n'
        '  }\n'
        ']\n\n'
        "Gunakan timestamp sepresisi mungkin dari transkrip. Jika tersedia milidetik, pertahankan milidetik itu.\n\n"
    )
    
    full_prompt = system_prompt + prompt_text
    prompt_file = os.path.join(temp_dir, "prompt.txt")
    
    with open(prompt_file, "w", encoding="utf-8") as f:
        f.write(full_prompt)

    resolved_cmd = _resolve_cli_command(cli_cmd)
    runtime_env = _build_runtime_env(resolved_cmd)
    if resolved_cmd:
        print(f"[INFO] Memanggil '{cli_cmd}' CLI via {resolved_cmd} untuk menganalisa transcript (bisa memakan waktu)...")
    else:
        print(f"[INFO] Memanggil '{cli_cmd}' CLI untuk menganalisa transcript (bisa memakan waktu)...")
    
    try:
        with open(prompt_file, "r", encoding="utf-8") as prompt_handle:
            result = subprocess.run(
                [resolved_cmd or cli_cmd],
                stdin=prompt_handle,
                capture_output=True,
                text=True,
                check=True,
                env=runtime_env,
            )
        raw_output = result.stdout.strip()

        try:
            data = _extract_json_array(raw_output)
            return data
        except json.JSONDecodeError:
            print("[ERROR] AI tidak mengembalikan array JSON yang valid.\nOutput mentah:\n", raw_output)
            return []
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Eksekusi {cli_cmd} gagal: {e}")
        print(f"Pastikan perintah '{cli_cmd}' terinstall di system dan bisa membaca stdin.")
        return []
    except FileNotFoundError:
        print(f"[ERROR] Perintah '{cli_cmd}' tidak ditemukan. Coba cek instalasi CLI atau PATH GUI.")
        return []
    except json.JSONDecodeError as e:
        print(f"[ERROR] Gagal memparsing JSON dari respon: {e}")
        return []
