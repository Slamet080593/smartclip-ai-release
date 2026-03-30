import subprocess
import os
import json
import tempfile
from contextlib import contextmanager
from http.cookiejar import MozillaCookieJar

YOUTUBE_COOKIE_DOMAINS = (".youtube.com", "youtube.com", ".google.com", "google.com", ".googlevideo.com", "googlevideo.com")

def _load_browser_cookie_jar():
    try:
        import browser_cookie3
    except ImportError:
        return None, None

    browser_loaders = [
        ("firefox", browser_cookie3.firefox),
        ("chrome", browser_cookie3.chrome),
        ("chromium", browser_cookie3.chromium),
        ("edge", browser_cookie3.edge),
        ("brave", browser_cookie3.brave),
    ]

    for browser_name, loader in browser_loaders:
        try:
            jar = loader()
        except Exception:
            continue
        if jar:
            return browser_name, jar
    return None, None

def _filter_youtube_cookies(source_jar):
    cookie_jar = MozillaCookieJar()
    for cookie in source_jar:
        domain = getattr(cookie, "domain", "") or ""
        if any(domain.endswith(target) for target in YOUTUBE_COOKIE_DOMAINS):
            cookie_jar.set_cookie(cookie)
    return cookie_jar

@contextmanager
def _temporary_youtube_cookie_file():
    browser_name, source_jar = _load_browser_cookie_jar()
    if not source_jar:
        yield None, None
        return

    filtered_jar = _filter_youtube_cookies(source_jar)
    if not filtered_jar:
        yield None, browser_name
        return

    temp_file = tempfile.NamedTemporaryFile(prefix="ytclipper_cookies_", suffix=".txt", delete=False)
    temp_file.close()
    filtered_jar.filename = temp_file.name
    filtered_jar.save(ignore_discard=True, ignore_expires=True)
    try:
        yield temp_file.name, browser_name
    finally:
        try:
            os.remove(temp_file.name)
        except OSError:
            pass

def _run_ytdlp(cmd: list[str]) -> subprocess.CompletedProcess:
    with _temporary_youtube_cookie_file() as (cookie_file, browser_name):
        if cookie_file:
            print(f"[INFO] Menggunakan cookies browser ({browser_name}) untuk yt-dlp.")
            cmd = [*cmd[:1], "--cookies", cookie_file, *cmd[1:]]
        elif browser_name:
            print(f"[WARNING] Browser {browser_name} ditemukan tetapi tidak ada cookies YouTube yang bisa dipakai.")
        else:
            print("[WARNING] Tidak menemukan cookies browser untuk YouTube. yt-dlp berjalan tanpa sesi login.")
        return subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

def get_video_metadata(url: str) -> dict:
    """Mengambil metadata video menggunakan yt-dlp secara cepat."""
    print(f"[INFO] Fetching metadata dari {url}...")
    cmd = ["yt-dlp", "-J", "--no-warnings", "--no-playlist", url]
    try:
        result = _run_ytdlp(cmd)
        data = json.loads(result.stdout)
        return {
            "uploader": data.get("uploader", "Unknown_Creator").replace("/", "_").replace("\\", "_"),
            "title": data.get("title", "Unknown_Title").replace("/", "_").replace("\\", "_")
        }
    except Exception as e:
        print(f"[ERROR] Gagal mendapatkan metadata via yt-dlp: {e}")
        return {"uploader": "Unknown_Creator", "title": "Unknown_Title"}

def download_audio_only(url: str, output_path: str) -> str:
    """Mendownload hanya audio dari YouTube untuk Transcription (Sangat Cepat)."""
    print(f"[INFO] Ingesting Audio only dari {url}...")
    
    # Simpan URL ke cache file supaya bisa dibandingkan di run berikutnya
    url_cache_file = os.path.join(os.path.dirname(output_path), "source_url.txt")
    
    cmd = [
        "yt-dlp",
        "-f", "bestaudio[ext=m4a]/bestaudio",
        "--no-playlist",
        "-o", output_path,
        url
    ]
    try:
        with _temporary_youtube_cookie_file() as (cookie_file, browser_name):
            run_cmd = cmd
            if cookie_file:
                print(f"[INFO] Menggunakan cookies browser ({browser_name}) untuk download audio.")
                run_cmd = [*cmd[:1], "--cookies", cookie_file, *cmd[1:]]
            elif browser_name:
                print(f"[WARNING] Browser {browser_name} ditemukan tetapi tidak ada cookies YouTube yang bisa dipakai.")
            else:
                print("[WARNING] Tidak menemukan cookies browser untuk YouTube. Download audio berjalan tanpa sesi login.")
            subprocess.run(run_cmd, check=True)
        with open(url_cache_file, "w") as f:
            f.write(url)
        return output_path
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Ingest Audio gagal: {e}")
        return ""

def should_redownload_audio(url: str, output_path: str) -> bool:
    """Cek apakah audio perlu didownload ulang berdasarkan URL berubah atau file tidak ada."""
    url_cache_file = os.path.join(os.path.dirname(output_path), "source_url.txt")
    
    if not os.path.exists(output_path):
        return True
    
    if not os.path.exists(url_cache_file):
        print("[WARNING] Cache URL tidak ditemukan, download ulang audio untuk keamanan.")
        return True
    
    with open(url_cache_file, "r") as f:
        cached_url = f.read().strip()
    
    if cached_url != url:
        print(f"[INFO] URL berubah! Cache lama: '{cached_url[:50]}...' → Reset download.")
        return True
    
    print("[INFO] URL sama dengan sebelumnya, memakai cache audio yang ada.")
    return False


def download_surgical_video(url: str, output_path: str, start_time: str, end_time: str) -> str:
    """Mendownload porsi spesifik dari video YouTube (Surgical Extraction).
    Format start_time, end_time harus sesuai format yt-dlp: misal '00:01:30' atau '01:30'
    """
    print(f"[INFO] Surgical Extraction Video ({start_time} to {end_time}) dari {url}...")
    cmd = [
        "yt-dlp",
        "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/mp4",
        "--download-sections", f"*{start_time}-{end_time}",
        "--force-keyframes-at-cuts",
        "--force-overwrites",  # Wajib! Agar file lama dari URL sebelumnya tidak dipakai
        "--no-playlist",
        "-o", output_path,
        url
    ]
    try:
        with _temporary_youtube_cookie_file() as (cookie_file, browser_name):
            run_cmd = cmd
            if cookie_file:
                print(f"[INFO] Menggunakan cookies browser ({browser_name}) untuk surgical download.")
                run_cmd = [*cmd[:1], "--cookies", cookie_file, *cmd[1:]]
            elif browser_name:
                print(f"[WARNING] Browser {browser_name} ditemukan tetapi tidak ada cookies YouTube yang bisa dipakai.")
            else:
                print("[WARNING] Tidak menemukan cookies browser untuk YouTube. Surgical download berjalan tanpa sesi login.")
            subprocess.run(run_cmd, check=True)
        return output_path
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Surgical Download gagal: {e}")
        return ""
