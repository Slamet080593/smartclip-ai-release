import glob
import os

from core.analyzer_cli import analyze_transcript
from core.app_config import build_output_dir, ensure_runtime_dirs, load_settings, sanitize_settings
from core.deps import check_runtime_dependencies, format_dependency_summary
from core.ingest import download_surgical_video, get_video_metadata
from core.renderer import extract_and_shift_srt, render_clip
from core.timecode import parse_timecode_to_seconds
from core.transcriber import detect_source_platform, generate_timestamped_transcript


def init_workspace(temp_dir: str, assets_dir: str) -> None:
    os.makedirs(temp_dir, exist_ok=True)
    os.makedirs(assets_dir, exist_ok=True)
    for stale in glob.glob(os.path.join(temp_dir, "raw_clip_*.mp4")):
        os.remove(stale)
        print(f"[CLEANUP] Menghapus raw clip lama: {stale}")


def main() -> None:
    print("=======================================")
    print("    THE REAL YT-CLIPPER (RELEASE)      ")
    print("=======================================")

    settings = sanitize_settings(load_settings())
    paths = ensure_runtime_dirs(settings)
    dependency_report = check_runtime_dependencies(settings["ai_backend"])

    print("\n[SETTINGS]")
    print(f"Output Root : {paths['output_root']}")
    print(f"Work Root   : {paths['work_root']}")
    print("\n[DEPENDENCY CHECK]")
    print(format_dependency_summary(dependency_report))
    if not dependency_report["ready"]:
        print("\n[ERROR] Dependency wajib belum lengkap. Lengkapi dulu sebelum menjalankan release CLI.")
        return

    init_workspace(str(paths["temp_dir"]), str(paths["assets_dir"]))

    video_source = input("\n[?] Masukkan Link Video yang ingin diproses: ").strip()
    if not video_source:
        print("[ERROR] Link tidak boleh kosong!")
        return

    print("\n[0] Mengambil Metadata Video dan Setup Folders...")
    meta = get_video_metadata(video_source)
    output_dir = build_output_dir(paths["output_root"], meta)
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"[INFO] Direktori akhir disetel ke: {output_dir}")

    detail_path = output_dir / "detail.md"
    with open(detail_path, "w", encoding="utf-8") as df:
        df.write(f"# Details for {meta['title']} by {meta['uploader']}\n\n")

    effective_platform = detect_source_platform(video_source)
    audio_path = paths["temp_dir"] / "source_audio.m4a"

    print("\n[1] Menyiapkan Transkripsi (Smart Subtitle Fetch / Whisper Fallback)...")
    transcript_result = generate_timestamped_transcript(
        video_source,
        audio_path=str(audio_path),
        source_platform=effective_platform,
    )
    if not transcript_result:
        return

    full_srt = transcript_result["srt_content"]
    prompt_text = transcript_result["prompt_text"]

    print(f"\n[3] Menganalisis Potensi Viral dengan {settings['ai_backend']} CLI...")
    params = {"max": 3, "min_s": 40, "max_s": 60, "moment": "Default"}
    viral_clips = analyze_transcript(prompt_text, settings["ai_backend"], params, str(paths["temp_dir"]))
    if not viral_clips:
        print("[WARNING] Tidak ada klip viral yang ditemukan oleh AI.")
        return

    print(f"[INFO] AI menemukan {len(viral_clips)} klip berpotensi viral!")

    success_count = 0
    failed_count = 0
    for i, clip in enumerate(viral_clips, start=1):
        print(f"\n--- MEMPROSES KLIP #{i}: {clip.get('title', 'Untitled')} ---")
        start_t = clip.get("start")
        end_t = clip.get("end")
        if not start_t or not end_t:
            print(f"[ERROR] Klip {i} tidak memiliki start/end time. Melewati...")
            failed_count += 1
            continue

        try:
            duration_sec = parse_timecode_to_seconds(end_t) - parse_timecode_to_seconds(start_t)
        except Exception:
            duration_sec = 60

        raw_clip_path = paths["temp_dir"] / f"raw_clip_{i}.mp4"
        download_surgical_video(video_source, str(raw_clip_path), start_t, end_t)
        if not raw_clip_path.exists():
            failed_count += 1
            continue

        shifted_srt = paths["temp_dir"] / f"subtitles_clip_{i}.srt"
        extract_and_shift_srt(full_srt, start_t, duration_sec, str(shifted_srt))

        safe_title = clip.get("title", f"ViralClip_{i}").replace(" ", "_").replace("/", "_")
        final_video = output_dir / f"clip_{i}_{safe_title}.mp4"
        render_clip(str(raw_clip_path), str(shifted_srt), str(final_video), render_mode=settings["render_mode"])

        if not final_video.exists():
            failed_count += 1
            continue

        success_count += 1
        with open(detail_path, "a", encoding="utf-8") as df:
            df.write(f"## Clip {i}: {clip.get('title', 'Untitled')}\n")
            df.write(f"**Caption:**\n{clip.get('caption', 'N/A')}\n\n")
            df.write(f"**Credit:** {clip.get('credit', 'N/A')}\n\n")
            df.write(f"**Reason:** {clip.get('reason', 'N/A')}\n")
            df.write(f"**Video File:** clip_{i}_{safe_title}.mp4\n\n---\n\n")

    print(f"\n*** PROSES KLIPING SELESAI: {success_count} sukses, {failed_count} gagal. ***")
    print(f"Hasil disimpan di: {output_dir}")


if __name__ == "__main__":
    main()
