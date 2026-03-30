import os
import subprocess
from datetime import datetime, timedelta
from core.timecode import parse_timecode_to_seconds

def shift_srt_time(time_str: str, offset_seconds: float) -> str:
    """Menggeser time string SRT ('00:15:30,000') dengan memotong offset_seconds."""
    time_fmt = "%H:%M:%S,%f"
    try:
        t = datetime.strptime(time_str, time_fmt)
        shifted = t - timedelta(seconds=offset_seconds)
        # Cegah string melingkar ke tahun lalu jika offset > time asli
        if shifted.year < 1900:
            shifted = datetime.strptime("00:00:00,000", time_fmt)
        return shifted.strftime(time_fmt)[:-3]
    except Exception:
        return time_str

def extract_and_shift_srt(full_srt: str, start_time_str: str, clip_duration: float, output_srt: str):
    """
    Menyaring blok teks SRT khusus milik clip ini, 
    dan mereset timelinenya mulai 00:00:00.
    """
    offset_sec = parse_timecode_to_seconds(start_time_str)
    
    lines = full_srt.split('\n')
    extracted_lines = []
    
    i = 0
    seq_num = 1
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
                
                fmt = "%H:%M:%S,%f"
                ts_dt = datetime.strptime(t_start, fmt)
                te_dt = datetime.strptime(t_end, fmt)
                abs_start = ts_dt.hour*3600 + ts_dt.minute*60 + ts_dt.second + ts_dt.microsecond/1e6
                abs_end = te_dt.hour*3600 + te_dt.minute*60 + te_dt.second + te_dt.microsecond/1e6
                
                # Masuk radar ekstraksi?
                if abs_end > offset_sec and abs_start < (offset_sec + clip_duration + 5):
                    new_start = shift_srt_time(t_start, offset_sec)
                    new_end = shift_srt_time(t_end, offset_sec)
                    
                    extracted_lines.append(str(seq_num))
                    extracted_lines.append(f"{new_start} --> {new_end}")
                    extracted_lines.extend(text_lines)
                    extracted_lines.append("")
                    seq_num += 1
        else:
            i += 1

    with open(output_srt, "w", encoding="utf-8") as f:
        f.write("\n".join(extracted_lines))
    return output_srt

def _build_ffmpeg_cmd(video_raw: str, filter_complex: str, output_file: str, encoder: str) -> list[str]:
    cmd = [
        "ffmpeg", "-y",
        "-i", video_raw,
        "-filter_complex", filter_complex,
        "-map", "[v_out]",
        "-map", "[a_out]",
        "-c:v", encoder,
    ]

    if encoder == "libx264":
        cmd.extend(["-crf", "18", "-preset", "fast"])
    elif encoder == "h264_nvenc":
        cmd.extend(["-preset", "p5", "-cq", "19"])
    else:
        cmd.extend(["-preset", "fast"])

    cmd.extend([
        "-c:a", "aac",
        "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        output_file,
    ])
    return cmd

def render_clip(
    video_raw: str,
    srt_file: str,
    output_file: str,
    burn_subs: bool = True,
    aspect_mode: str = "Aspect: Blur Bg",
    render_mode: str = "Render: CPU",
):
    """
    Menerapkan 'The Claude Method' ke video raw hasil surgical extraction.
    Crop ke 9:16 portrait, hflip, noise, dan tempel subtitle SRT.
    """
    print(
        f"[INFO] Merender Kosmetik Akhir: {output_file} "
        f"(Subs: {burn_subs}, Layout: {aspect_mode}, Mode: {render_mode})"
    )
    
    abs_srt = os.path.abspath(srt_file).replace('\\', '/').replace(':', '\\:')
    
    if burn_subs:
        subs_filter = f",subtitles='{abs_srt}':force_style='Fontname=Oswald,Fontsize=18,PrimaryColour=&H00FFFF&,OutlineColour=&H40000000&,BorderStyle=1,Outline=2,Alignment=2,MarginV=35'"
    else:
        subs_filter = ""
        
    if aspect_mode == "Aspect: Blur Bg":
        bg_filter = (
            f"[0:v]split=2[bg_raw][fg_raw];"
            f"[bg_raw]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20:20[bg_blur];"
            f"[fg_raw]scale=1080:1920:force_original_aspect_ratio=decrease[fg_sized];"
            f"[bg_blur][fg_sized]overlay=(W-w)/2:(H-h)/2"
        )
    elif aspect_mode == "Aspect: Letterbox":
        bg_filter = f"[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2"
    else: # Center Crop
        bg_filter = f"[0:v]scale=-1:1920,crop=1080:1920:exact=1"

    filter_complex = (
        f"{bg_filter},"
        f"hflip,eq=brightness=0.01:saturation=1.1,"
        f"noise=alls=1:allf=t{subs_filter}[v_out];"
        f"[0:a]volume=1.0[a_out]" # Biarkan audio asli, tapi ter-map bersih
    )

    encoders = ["libx264"]
    if render_mode == "Render: GPU":
        encoders = ["h264_nvenc", "libx264"]

    last_error = None
    for encoder in encoders:
        if encoder != encoders[0]:
            print(f"[INFO] Fallback encoder -> {encoder}")
        cmd = _build_ffmpeg_cmd(video_raw, filter_complex, output_file, encoder)
        try:
            subprocess.run(cmd, check=True)
            print(f"[SUCCESS] Viral Clip siap dan Anti-Copyright: {output_file}")
            return
        except subprocess.CalledProcessError as exc:
            last_error = exc
            if encoder == "h264_nvenc":
                print("[WARNING] Render GPU gagal, fallback ke CPU libx264...")
                continue
            break

    print(f"[ERROR] Proses render kosmetik gagal: {last_error}")
