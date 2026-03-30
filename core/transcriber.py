import whisper
import os
import subprocess
import glob
from urllib.parse import parse_qs, urlparse
from core.ingest import download_audio_only, should_redownload_audio
from core.timecode import format_prompt_time

def detect_source_platform(video_url: str) -> str:
    host = urlparse(video_url.strip()).netloc.lower()
    if any(token in host for token in ("youtube.com", "youtu.be")):
        return "youtube"
    if "twitch.tv" in host:
        return "twitch"
    return "generic"

def _extract_video_id(video_url: str) -> str | None:
    parsed = urlparse(video_url.strip())

    if parsed.netloc.endswith("youtu.be"):
        candidate = parsed.path.strip("/").split("/")[0]
        return candidate[:11] if len(candidate) >= 11 else None

    query_video_id = parse_qs(parsed.query).get("v", [None])[0]
    if query_video_id:
        return query_video_id[:11]

    path_parts = [part for part in parsed.path.split("/") if part]
    for prefix in ("shorts", "embed", "live", "v"):
        if prefix in path_parts:
            index = path_parts.index(prefix) + 1
            if index < len(path_parts):
                candidate = path_parts[index]
                return candidate[:11] if len(candidate) >= 11 else None
    return None

def try_download_youtube_subs(video_url: str, temp_dir: str = "temp") -> str:
    """Mencoba mengambil subtitle dari YouTube menggunakan youtube-transcript-api.
    Lebih reliable dari yt-dlp karena tidak memerlukan JS runtime.
    Urutan prioritas: subtitle manual bahasa ID -> EN -> auto-generated.
    """
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled
    
    print(f"[INFO] Mengecek subtitle bawaan YouTube untuk {video_url}...")
    
    # Extract video ID dari URL
    video_id = _extract_video_id(video_url)
    if not video_id:
        print("[WARNING] Tidak bisa mengekstrak Video ID dari URL.")
        return None
    
    # Bersihkan sisa file lama
    old_subs = glob.glob(os.path.join(temp_dir, "source_subs*.srt"))
    for f in old_subs:
        try: os.remove(f)
        except: pass
    
    try:
        # v1.x API: pakai instance, bukan class method
        # Beri timeout 10 detik agar tidak hang kalau YouTube memblokir direct request
        import requests
        session = requests.Session()
        original_request = session.request

        def request_with_timeout(method, url, **kwargs):
            kwargs.setdefault("timeout", 10)
            return original_request(method, url, **kwargs)

        session.request = request_with_timeout
        api = YouTubeTranscriptApi(http_client=session)
        transcript_list = api.list(video_id)
        
        transcript = None
        # Coba manual subtitle dulu (ID -> EN)
        for lang in ['id', 'en']:
            try:
                transcript = transcript_list.find_transcript([lang]).fetch()
                break
            except NoTranscriptFound:
                pass
        
        # Fallback ke auto-generated
        if not transcript:
            try:
                transcript = transcript_list.find_generated_transcript(['id', 'en']).fetch()
            except NoTranscriptFound:
                pass
        
        if not transcript:
            print("[WARNING] Tidak ada subtitle bawaan valid. Memulai Fallback (Whisper)...")
            return None

        # Tulis ke file SRT
        srt_path = os.path.join(temp_dir, "source_subs.srt")
        with open(srt_path, "w", encoding="utf-8") as f:
            for i, entry in enumerate(transcript, start=1):
                if isinstance(entry, dict):
                    start = entry.get("start", 0)
                    duration = entry.get("duration", 2.0)
                    text = entry.get("text", "")
                else:
                    start = getattr(entry, "start", 0)
                    duration = getattr(entry, "duration", 2.0)
                    text = getattr(entry, "text", "")
                end = start + duration
                
                def _to_srt_ts(sec):
                    ms = int((sec % 1) * 1000)
                    s = int(sec)
                    m, s = divmod(s, 60)
                    h, m = divmod(m, 60)
                    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
                
                text = text.replace('\n', ' ')
                f.write(f"{i}\n{_to_srt_ts(start)} --> {_to_srt_ts(end)}\n{text}\n\n")
        
        print(f"[SUCCESS] Subtitle YT berhasil diambil via API! ({len(transcript)} baris) → Bypass Whisper!")
        return srt_path
        
    except TranscriptsDisabled:
        print("[WARNING] Subtitle dinonaktifkan oleh kreator. Fallback ke Whisper...")
        return None
    except Exception as e:
        print(f"[WARNING] youtube-transcript-api gagal: {e}. Fallback ke Whisper...")
        return None

def parse_srt_to_transcript(srt_file: str) -> dict:
    """Membaca file SRT jadi string prompt yang di mengerti Gemini."""
    try:
        with open(srt_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        srt_content = "".join(lines)
        prompt_text = "== TRANSKRIP UNTUK DIANALISIS ==\n"
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.isdigit():
                i += 1
                if i >= len(lines): break
                timing = lines[i].strip()
                i += 1
                text_lines = []
                while i < len(lines) and lines[i].strip() != '':
                    text_lines.append(lines[i].strip())
                    i += 1
                    
                if " --> " in timing:
                    t_start, t_end = timing.split(" --> ")
                    human_start = t_start.replace(",", ".")
                    human_end = t_end.replace(",", ".")
                    text_joined = " ".join(text_lines).replace('<c>', '').replace('</c>', '')
                    prompt_text += f"[{human_start} -> {human_end}] {text_joined}\n"
            else:
                i += 1
                
        return {
            "srt_content": srt_content,
            "prompt_text": prompt_text,
            "segments": [{"text": "Bypass mode", "start": 0, "end": 0}] 
        }
    except Exception as e:
        print(f"[ERROR] Gagal membaca srt hasil extract: {e}")
        return None

def generate_timestamped_transcript(
    video_url: str,
    audio_path: str = "temp/source_audio.m4a",
    model_size: str = "base",
    source_platform: str = "auto",
) -> dict:
    """
    Mendapatkan transkrip dari video:
    1. Coba download subtitle bawaan YouTube (fast path)
    2. Kalau tidak ada → download audio + Whisper lokal (fallback)
    """
    platform = source_platform.lower()
    if platform == "auto":
        platform = detect_source_platform(video_url)
    temp_dir = os.path.dirname(audio_path) or "temp"
    os.makedirs(temp_dir, exist_ok=True)

    # Langkah Cerdas 1: Coba ambil subtitle asli YouTube kalau memang source YouTube
    if platform == "youtube":
        subs_file = try_download_youtube_subs(video_url, temp_dir)
        if subs_file:
            parsed = parse_srt_to_transcript(subs_file)
            if parsed:
                return parsed
    elif platform == "twitch":
        print("[INFO] Source platform disetel ke Twitch. Subtitle YouTube dilewati, langsung pakai fallback audio/Whisper.")
    else:
        print("[INFO] Source platform non-YouTube. Subtitle API YouTube dilewati, langsung pakai fallback audio/Whisper.")

    # Langkah Cerdas 2: Fallback — download audio baru kalau URL berubah atau belum ada
    print("[INFO] Tidak ada subtitle YT. Memeriksa cache audio...")
    if should_redownload_audio(video_url, audio_path):
        success = download_audio_only(video_url, audio_path)
        if not success or not os.path.exists(audio_path):
            print(f"[ERROR] Gagal mendownload audio dari {video_url}.")
            return None

    if not os.path.exists(audio_path):
        print(f"[ERROR] Audio file {audio_path} tidak ditemukan untuk fallback whisper.")
        return None

    print(f"[INFO] Fallback Transcriber Whisper Lokal ({model_size}) dihidupkan untuk {audio_path}...")
    try:
        model = whisper.load_model(model_size)
        result = model.transcribe(audio_path, language="id", word_timestamps=False)
        
        srt_content = ""
        prompt_text = "== TRANSKRIP UNTUK DIANALISIS ==\n"
        
        for i, segment in enumerate(result['segments'], start=1):
            start_s = segment['start']
            end_s = segment['end']
            text = segment['text'].strip()
            
            srt_content += f"{i}\n{_format_srt_time(start_s)} --> {_format_srt_time(end_s)}\n{text}\n\n"
            prompt_text += f"[{format_prompt_time(start_s)} -> {format_prompt_time(end_s)}] {text}\n"
            
        print(f"[INFO] Transkripsi selesai. Total segmen: {len(result['segments'])}")
        return {
            "srt_content": srt_content,
            "prompt_text": prompt_text,
            "segments": result['segments']
        }
    except Exception as e:
        print(f"[ERROR] Transcriber gagal: {e}")
        return None

def _format_srt_time(seconds: float) -> str:
    ms = int((seconds - int(seconds)) * 1000)
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
