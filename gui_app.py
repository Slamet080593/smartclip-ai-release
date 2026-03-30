import customtkinter as ctk
import sys
import threading
import os
import glob
import re
from datetime import datetime
import signal
from pathlib import Path
from tkinter import filedialog

from core.app_config import (
    build_output_dir,
    ensure_runtime_dirs,
    get_settings_path,
    load_settings,
    sanitize_settings,
    save_settings,
)
from core.deps import check_runtime_dependencies, format_dependency_summary
from core.ingest import get_video_metadata
from core.ingest import download_surgical_video
from core.transcriber import generate_timestamped_transcript, detect_source_platform
from core.analyzer_cli import analyze_transcript
from core.renderer import extract_and_shift_srt, render_clip
from core.timecode import parse_timecode_to_seconds

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

LAUGHDOSE_CAPTION_TEMPLATES = [
    ("INI NGAKAK BANGET 😭", "Lu kuat nonton ini tanpa ketawa ga? 😂"),
    ("GUE GA KUAT 😭", "Yang begini nih bikin hari jadi lebih ringan 😂 Lu pernah ngalamin juga?"),
    ("REAL BANGET 😭", "Kadang hal kecil gini malah paling bikin ngakak 😂"),
    ("TUNGGU SAMPE AKHIR 😭", "Endingnya ga ketebak 😂"),
]

PLATFORM_HASHTAGS = {
    "TikTok": "#fyp #funny #viral #ngakak #lucu #shorts",
    "Instagram Reels": "#reels #funny #viral #ngakak #lucu",
    "Facebook": "#funny #viral #ngakak #lucu",
    "YouTube Shorts": "#shorts #funny #viral #ngakak #lucu",
}

PLATFORM_TAB_LABELS = {
    "TikTok": "TikTok",
    "Instagram Reels": "IG Reels",
    "Facebook": "Facebook",
    "YouTube Shorts": "YT Shorts",
    "Asset Info": "Asset",
}

class GUIConsoleLogger:
    def __init__(self, textbox):
        self.textbox = textbox
        self.original_stdout = sys.stdout

    def write(self, message):
        self.original_stdout.write(message)
        self.textbox.after(0, self._append_text, message)

    def _append_text(self, message):
        self.textbox.configure(state="normal")
        self.textbox.insert("end", message)
        self.textbox.see("end")
        self.textbox.configure(state="disabled")

    def flush(self):
        self.original_stdout.flush()

class YtClipperApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.settings = sanitize_settings(load_settings())
        self.runtime_paths = ensure_runtime_dirs(self.settings)
        self.output_root = self.runtime_paths["output_root"]
        self.work_root = self.runtime_paths["work_root"]
        self.temp_dir = self.runtime_paths["temp_dir"]
        self.assets_dir = self.runtime_paths["assets_dir"]
        self.logs_dir = self.runtime_paths["logs_dir"]
        
        self.title("SmartClip AI - Professional Edition")
        self.geometry("1720x920")
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(2, weight=0)
        self.grid_rowconfigure(0, weight=1)

        # ====== LEFT PANEL ======
        self.left_frame = ctk.CTkFrame(self, width=280, corner_radius=0)
        self.left_frame.grid(row=0, column=0, sticky="nsew")
        self.left_frame.grid_rowconfigure(9, weight=1)

        self.logo_label = ctk.CTkLabel(self.left_frame, text="⚡ SmartClip AI", font=ctk.CTkFont(size=20, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 20))

        # --- System Settings Block ---
        self.sys_label = ctk.CTkLabel(self.left_frame, text="⚙ System Settings", font=ctk.CTkFont(size=14, weight="bold"))
        self.sys_label.grid(row=1, column=0, padx=20, pady=(10,5), sticky="w")
        
        self.ai_menu = ctk.CTkOptionMenu(self.left_frame, values=["gemini", "claude", "qwen", "codex"], command=self._refresh_dependency_status)
        self.ai_menu.grid(row=2, column=0, padx=20, pady=5, sticky="ew")
        self.ai_menu.set(self.settings["ai_backend"])

        self.render_menu = ctk.CTkOptionMenu(self.left_frame, values=["Render: CPU", "Render: GPU"])
        self.render_menu.grid(row=3, column=0, padx=20, pady=5, sticky="ew")
        self.render_menu.set(self.settings["render_mode"])

        # --- Subtitle Styling Block ---
        self.sub_label = ctk.CTkLabel(self.left_frame, text="📄 Subtitle Styling", font=ctk.CTkFont(size=14, weight="bold"))
        self.sub_label.grid(row=4, column=0, padx=20, pady=(30,5), sticky="w")

        self.font_menu = ctk.CTkOptionMenu(self.left_frame, values=["Arial", "Oswald", "Montserrat"])
        self.font_menu.grid(row=5, column=0, padx=20, pady=5, sticky="ew")
        self.font_menu.set(self.settings["subtitle_font"])

        self.color_menu = ctk.CTkOptionMenu(self.left_frame, values=["Text: White", "Text: Yellow"])
        self.color_menu.grid(row=6, column=0, padx=20, pady=5, sticky="ew")
        self.color_menu.set(self.settings["subtitle_color"])

        # --- Video Styling Block ---
        self.video_label = ctk.CTkLabel(self.left_frame, text="✂️ Video Layout", font=ctk.CTkFont(size=14, weight="bold"))
        self.video_label.grid(row=7, column=0, padx=20, pady=(30,5), sticky="w")

        self.aspect_menu = ctk.CTkOptionMenu(self.left_frame, values=["Aspect: Blur Bg", "Aspect: Center Crop", "Aspect: Letterbox"])
        self.aspect_menu.grid(row=8, column=0, padx=20, pady=5, sticky="ew")
        self.aspect_menu.set(self.settings["aspect_mode"])

        self.path_label = ctk.CTkLabel(self.left_frame, text="📁 Storage", font=ctk.CTkFont(size=14, weight="bold"))
        self.path_label.grid(row=9, column=0, padx=20, pady=(30, 5), sticky="w")

        self.output_root_entry = ctk.CTkEntry(self.left_frame)
        self.output_root_entry.grid(row=10, column=0, padx=20, pady=5, sticky="ew")
        self.output_root_entry.insert(0, str(self.output_root))

        self.output_browse_btn = ctk.CTkButton(self.left_frame, text="Browse Output", height=30, command=self._browse_output_root)
        self.output_browse_btn.grid(row=11, column=0, padx=20, pady=(0, 6), sticky="ew")

        self.work_root_entry = ctk.CTkEntry(self.left_frame)
        self.work_root_entry.grid(row=12, column=0, padx=20, pady=5, sticky="ew")
        self.work_root_entry.insert(0, str(self.work_root))

        self.work_browse_btn = ctk.CTkButton(self.left_frame, text="Browse Work Dir", height=30, command=self._browse_work_root)
        self.work_browse_btn.grid(row=13, column=0, padx=20, pady=(0, 6), sticky="ew")

        self.save_settings_btn = ctk.CTkButton(self.left_frame, text="Save Settings", height=34, command=self._save_runtime_settings)
        self.save_settings_btn.grid(row=14, column=0, padx=20, pady=(6, 8), sticky="ew")

        self.deps_label = ctk.CTkLabel(self.left_frame, text="🩺 Dependency Status", font=ctk.CTkFont(size=14, weight="bold"))
        self.deps_label.grid(row=15, column=0, padx=20, pady=(16, 5), sticky="w")

        self.deps_status = ctk.CTkTextbox(self.left_frame, height=130, font=ctk.CTkFont(family="Consolas", size=11))
        self.deps_status.grid(row=16, column=0, padx=20, pady=(0, 10), sticky="ew")
        self.deps_status.configure(state="disabled")

        # ====== CENTER PANEL ======
        self.right_frame = ctk.CTkFrame(self)
        self.right_frame.grid(row=0, column=1, sticky="nsew", padx=(10, 5), pady=10)
        self.right_frame.grid_rowconfigure(3, weight=1)
        self.right_frame.grid_rowconfigure(4, weight=1)
        self.right_frame.grid_columnconfigure(0, weight=1)
        self.clip_results = []
        self.output_entries = []

        # ====== COPY HUB SIDEBAR ======
        self.copy_frame = ctk.CTkFrame(self, width=620, corner_radius=12)
        self.copy_frame.grid(row=0, column=2, sticky="nsew", padx=(5, 10), pady=10)
        self.copy_frame.grid_propagate(False)
        self.copy_frame.grid_rowconfigure(1, weight=1)
        self.copy_frame.grid_columnconfigure(0, weight=1)

        # --- Top Action Block (Input Source) ---
        self.top_box = ctk.CTkFrame(self.right_frame)
        self.top_box.grid(row=0, column=0, sticky="ew", padx=10, pady=10)

        ctk.CTkLabel(self.top_box, text="🎬 Input Source", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=10, pady=5, sticky="w")
        self.url_entry = ctk.CTkEntry(self.top_box, placeholder_text="YouTube URL: https://...", width=500)
        self.url_entry.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="w")
        self.platform_menu = ctk.CTkOptionMenu(self.top_box, values=["Auto", "YouTube", "Twitch"], width=140)
        self.platform_menu.grid(row=1, column=1, padx=(0, 10), pady=(0, 10), sticky="e")

        # --- Analysis & Output Settings Block ---
        self.analysis_box = ctk.CTkFrame(self.right_frame, fg_color="transparent")
        self.analysis_box.grid(row=1, column=0, sticky="ew", padx=10, pady=0)
        
        ctk.CTkLabel(self.analysis_box, text="⚙ Analysis & Output", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=10, pady=5, sticky="w")
        
        self.param_frame = ctk.CTkFrame(self.analysis_box)
        self.param_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=0)
        
        ctk.CTkLabel(self.param_frame, text="Max Clips:").grid(row=0, column=0, padx=5, pady=5)
        self.max_clips_var = ctk.StringVar(value="3")
        ctk.CTkEntry(self.param_frame, textvariable=self.max_clips_var, width=50).grid(row=0, column=1, padx=5, pady=5)
        
        ctk.CTkLabel(self.param_frame, text="Min Sec:").grid(row=0, column=2, padx=5, pady=5)
        self.min_sec_var = ctk.StringVar(value="40")
        ctk.CTkEntry(self.param_frame, textvariable=self.min_sec_var, width=50).grid(row=0, column=3, padx=5, pady=5)
        
        ctk.CTkLabel(self.param_frame, text="Max Sec:").grid(row=0, column=4, padx=5, pady=5)
        self.max_sec_var = ctk.StringVar(value="60")
        ctk.CTkEntry(self.param_frame, textvariable=self.max_sec_var, width=50).grid(row=0, column=5, padx=5, pady=5)
        
        ctk.CTkLabel(self.param_frame, text="Target Moment:").grid(row=1, column=0, padx=5, pady=5, sticky="e")
        self.moment_menu = ctk.CTkOptionMenu(self.param_frame, values=["Default", "Lucu", "Sedih", "Motivasi", "Marah", "Awkward"])
        self.moment_menu.grid(row=1, column=1, columnspan=3, padx=5, pady=5, sticky="ew")

        # --- Middle Action Block (Formats & Button) ---
        self.mid_box = ctk.CTkFrame(self.right_frame)
        self.mid_box.grid(row=2, column=0, sticky="ew", padx=10, pady=10)
        
        self.chk_tiktok = ctk.CTkCheckBox(self.mid_box, text="9:16 TikTok", state="disabled")
        self.chk_tiktok.select()
        self.chk_tiktok.grid(row=0, column=0, padx=20, pady=10)
        
        self.chk_burn = ctk.CTkCheckBox(self.mid_box, text="Burn Subs", state="normal")
        self.chk_burn.select()
        self.chk_burn.grid(row=0, column=1, padx=20, pady=10)

        self.start_btn = ctk.CTkButton(self.mid_box, text="▶ START AI PROCESSING", 
                                       fg_color="#1DB954", hover_color="#1aa34a",
                                       height=40, font=ctk.CTkFont(size=15, weight="bold"),
                                       command=self.start_process_thread)
        self.start_btn.grid(row=1, column=0, columnspan=2, sticky="ew", padx=20, pady=(10, 20))

        self.load_btn = ctk.CTkButton(
            self.mid_box,
            text="📂 LOAD EXISTING OUTPUT",
            height=36,
            command=self.load_existing_output,
        )
        self.load_btn.grid(row=2, column=0, columnspan=2, sticky="ew", padx=20, pady=(0, 16))

        # --- Existing Outputs Browser ---
        self.library_box = ctk.CTkFrame(self.right_frame)
        self.library_box.grid(row=3, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self.library_box.grid_rowconfigure(1, weight=1)
        self.library_box.grid_columnconfigure(0, weight=1)

        library_header = ctk.CTkFrame(self.library_box, fg_color="transparent")
        library_header.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        library_header.grid_columnconfigure(0, weight=1)

        self.library_label = ctk.CTkLabel(
            library_header,
            text="📚 Existing Outputs",
            font=ctk.CTkFont(size=15, weight="bold"),
            anchor="w",
        )
        self.library_label.grid(row=0, column=0, sticky="w")

        self.refresh_library_btn = ctk.CTkButton(
            library_header,
            text="Refresh",
            width=90,
            command=self.refresh_output_library,
        )
        self.refresh_library_btn.grid(row=0, column=1, sticky="e")

        self.output_browser_scroll = ctk.CTkScrollableFrame(self.library_box)
        self.output_browser_scroll.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))

        # --- Bottom Console Block ---
        self.console_box = ctk.CTkTextbox(
            self.right_frame,
            height=240,
            font=ctk.CTkFont(family="Consolas", size=13),
        )
        self.console_box.grid(row=4, column=0, sticky="nsew", padx=10, pady=10)
        self.console_box.configure(state="disabled")

        self.results_header = ctk.CTkLabel(
            self.copy_frame,
            text="Copy Hub\n\nBelum ada hasil. Jalankan clipper atau load output lama, lalu caption siap copy akan muncul di sini.",
            anchor="w",
            justify="left",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        self.results_header.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))

        self.results_scroll = ctk.CTkScrollableFrame(self.copy_frame)
        self.results_scroll.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))

        # Initialize logging
        sys.stdout = GUIConsoleLogger(self.console_box)
        sys.stderr = sys.stdout # Redirect error too
        
        self._refresh_dependency_status()
        self.refresh_output_library()
        print(">> SmartClip AI Release booted.")
        print(f"[INFO] Settings file: {get_settings_path()}")
        print(f"[INFO] Output root aktif: {self.output_root}")
        print(f"[INFO] Work root aktif: {self.work_root}")
        print("[INFO] Ubah path di panel kiri lalu klik 'Save Settings' kalau ingin pindah lokasi simpan.")
        print(">> Switched to Gemini CLI Backend. Ready.")

    def _set_start_button_state(self, state: str, text: str) -> None:
        self.start_btn.configure(state=state, text=text)

    def _apply_runtime_paths(self, runtime_paths: dict) -> None:
        self.runtime_paths = runtime_paths
        self.output_root = runtime_paths["output_root"]
        self.work_root = runtime_paths["work_root"]
        self.temp_dir = runtime_paths["temp_dir"]
        self.assets_dir = runtime_paths["assets_dir"]
        self.logs_dir = runtime_paths["logs_dir"]

    def _browse_output_root(self) -> None:
        folder = filedialog.askdirectory(title="Pilih output root", initialdir=str(self.output_root))
        if folder:
            self.output_root_entry.delete(0, "end")
            self.output_root_entry.insert(0, folder)

    def _browse_work_root(self) -> None:
        folder = filedialog.askdirectory(title="Pilih work root", initialdir=str(self.work_root))
        if folder:
            self.work_root_entry.delete(0, "end")
            self.work_root_entry.insert(0, folder)

    def _collect_settings_from_ui(self) -> dict:
        return sanitize_settings({
            "output_root": self.output_root_entry.get().strip(),
            "work_root": self.work_root_entry.get().strip(),
            "ai_backend": self.ai_menu.get(),
            "render_mode": self.render_menu.get(),
            "subtitle_font": self.font_menu.get(),
            "subtitle_color": self.color_menu.get(),
            "aspect_mode": self.aspect_menu.get(),
        })

    def _save_runtime_settings(self) -> None:
        self.settings = self._collect_settings_from_ui()
        save_settings(self.settings)
        self._apply_runtime_paths(ensure_runtime_dirs(self.settings))
        self.refresh_output_library()
        self._refresh_dependency_status()
        print(f"[INFO] Settings disimpan. Output root: {self.output_root}")

    def _refresh_dependency_status(self, *_args) -> None:
        report = check_runtime_dependencies(self.ai_menu.get() if hasattr(self, "ai_menu") else "gemini")
        self.dependency_report = report
        self.deps_status.configure(state="normal")
        self.deps_status.delete("1.0", "end")
        self.deps_status.insert("1.0", format_dependency_summary(report))
        self.deps_status.configure(state="disabled")

    def _set_results_header(self, text: str) -> None:
        self.results_header.configure(text=text)

    def _clear_results_view(self) -> None:
        for child in self.results_scroll.winfo_children():
            child.destroy()

    def _copy_text(self, label: str, text: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update_idletasks()
        print(f"[COPY] {label} berhasil disalin ke clipboard.")

    def _scan_output_library(self) -> list[dict]:
        entries = []
        root = Path(self.output_root)
        if not root.exists():
            return entries

        for detail_path in sorted(root.rglob("detail.md"), reverse=True):
            folder = detail_path.parent
            try:
                rel = folder.relative_to(root)
                parts = rel.parts
            except ValueError:
                parts = ()

            date = parts[0] if len(parts) > 0 else "-"
            channel = parts[1] if len(parts) > 1 else "Unknown"
            title = parts[2] if len(parts) > 2 else folder.name

            mp4_count = len(list(folder.glob("*.mp4")))
            entries.append({
                "folder": str(folder),
                "detail_path": str(detail_path),
                "date": date,
                "channel": channel,
                "title": title,
                "clip_count": mp4_count,
            })
        return entries

    def refresh_output_library(self) -> None:
        self.output_entries = self._scan_output_library()
        for child in self.output_browser_scroll.winfo_children():
            child.destroy()

        if not self.output_entries:
            empty = ctk.CTkLabel(
                self.output_browser_scroll,
                text=f"Belum ada output terdeteksi di:\n{self.output_root}",
                anchor="w",
                justify="left",
            )
            empty.pack(fill="x", padx=4, pady=8)
            return

        for entry in self.output_entries:
            card = ctk.CTkFrame(self.output_browser_scroll)
            card.pack(fill="x", expand=True, padx=4, pady=5)
            card.grid_columnconfigure(0, weight=1)

            title = ctk.CTkLabel(
                card,
                text=entry["title"],
                font=ctk.CTkFont(size=14, weight="bold"),
                anchor="w",
                justify="left",
                wraplength=520,
            )
            title.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 2))

            meta = ctk.CTkLabel(
                card,
                text=f"{entry['date']} • {entry['channel']} • {entry['clip_count']} clip",
                anchor="w",
                text_color=("gray40", "gray70"),
            )
            meta.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 6))

            open_btn = ctk.CTkButton(
                card,
                text="Load Ke Copy Hub",
                width=140,
                command=lambda folder=entry["folder"]: self.load_existing_output(folder),
            )
            open_btn.grid(row=0, column=1, rowspan=2, padx=10, pady=8)

    def _parse_detail_markdown(self, detail_path: str) -> tuple[dict, list[dict]]:
        with open(detail_path, "r", encoding="utf-8") as handle:
            content = handle.read()

        lines = content.splitlines()
        video_meta = {"uploader": "Unknown_Creator", "title": Path(detail_path).parent.name}
        if lines and lines[0].startswith("# Details for "):
            raw = lines[0][len("# Details for "):]
            if " by " in raw:
                title, uploader = raw.rsplit(" by ", 1)
                video_meta = {"title": title.strip(), "uploader": uploader.strip()}

        sections = [
            match.group(0).strip()
            for match in re.finditer(r"^## Clip .*?(?=^---\s*$|\Z)", content, re.MULTILINE | re.DOTALL)
        ]
        clips = []
        for index, section in enumerate(sections, start=1):
            payload = {
                "title": f"Clip {index}",
                "caption": "",
                "credit": "",
                "reason": "",
                "video_file": "",
                "start": "-",
                "end": "-",
            }
            lines = [line.rstrip() for line in section.splitlines()]
            if lines:
                header = lines[0]
                if ": " in header:
                    payload["title"] = header.split(": ", 1)[1].strip()

            current_field = None
            for line in lines[1:]:
                stripped = line.strip()
                if stripped == "**Caption:**":
                    current_field = "caption"
                    continue
                if stripped.startswith("**Credit:**"):
                    payload["credit"] = stripped.split("**Credit:**", 1)[1].strip()
                    current_field = None
                    continue
                if stripped.startswith("**Start:**"):
                    payload["start"] = stripped.split("**Start:**", 1)[1].strip()
                    current_field = None
                    continue
                if stripped.startswith("**End:**"):
                    payload["end"] = stripped.split("**End:**", 1)[1].strip()
                    current_field = None
                    continue
                if stripped.startswith("**Reason:**"):
                    payload["reason"] = stripped.split("**Reason:**", 1)[1].strip()
                    current_field = None
                    continue
                if stripped.startswith("**Video File:**"):
                    payload["video_file"] = stripped.split("**Video File:**", 1)[1].strip()
                    current_field = None
                    continue
                if current_field == "caption":
                    payload["caption"] = f"{payload['caption']}\n{stripped}".strip() if stripped else payload["caption"]

            clips.append(payload)
        return video_meta, clips

    def load_existing_output(self, folder: str | None = None) -> None:
        if folder is None:
            folder = filedialog.askdirectory(
                title="Pilih folder output Yt-Clipper",
                initialdir=str(self.output_root),
            )
            if not folder:
                return

        detail_path = os.path.join(folder, "detail.md")
        if not os.path.exists(detail_path):
            print("[ERROR] Folder terpilih tidak punya detail.md")
            self._set_results_header("Folder ini tidak punya detail.md, jadi caption lama belum bisa dimuat.")
            return

        try:
            video_meta, clips = self._parse_detail_markdown(detail_path)
        except Exception as exc:
            print(f"[ERROR] Gagal membaca detail lama: {exc}")
            self._set_results_header("Gagal membaca detail output lama. Cek format detail.md.")
            return

        self.clip_results = []
        for index, clip in enumerate(clips, start=1):
            video_file = os.path.join(folder, clip.get("video_file") or "")
            self.clip_results.append({
                "index": index,
                "clip": clip,
                "video_file": video_file if clip.get("video_file") else folder,
                "copies": self._build_platform_copy(clip, index, video_meta, video_file if clip.get("video_file") else folder),
            })

        print(f"[INFO] Loaded {len(self.clip_results)} clip dari output lama: {folder}")
        self._render_results_view()

    def _build_platform_copy(self, clip: dict, clip_index: int, video_meta: dict, video_file: str) -> dict[str, str]:
        hook, engagement = LAUGHDOSE_CAPTION_TEMPLATES[(clip_index - 1) % len(LAUGHDOSE_CAPTION_TEMPLATES)]
        ai_caption = (clip.get("caption") or "").strip()
        reason = (clip.get("reason") or "").strip()
        credit = (clip.get("credit") or f"cc @{video_meta.get('uploader', 'creator')}").strip()
        title = (clip.get("title") or f"Clip {clip_index}").strip()
        file_name = Path(video_file).name

        if ai_caption:
            body = ai_caption
        elif reason:
            body = f"{reason} 😂"
        else:
            body = "Auto hiburan random yang bikin susah nahan ketawa 😂"

        short_body = body.replace("\n", " ").strip()
        generic = f"{hook}\n\n{short_body}\n{engagement}"

        return {
            "TikTok": f"{generic}\n\n{PLATFORM_HASHTAGS['TikTok']}\n\n{credit}",
            "Instagram Reels": f"{hook}\n\n{title}\n{short_body}\n\n{PLATFORM_HASHTAGS['Instagram Reels']}\n\n{credit}",
            "Facebook": f"Pernah ngalamin gini ga? 😭😂\n\n{title}\n{short_body}\n\nTag temen lo yang pasti ketawa liat ini 🤣\n\n{PLATFORM_HASHTAGS['Facebook']}\n\n{credit}",
            "YouTube Shorts": f"{hook}\n{title}\n{short_body}\n\n{PLATFORM_HASHTAGS['YouTube Shorts']}\n\n{credit}",
            "Asset Info": f"Judul: {title}\nFile: {file_name}\nStart: {clip.get('start', '-')}\nEnd: {clip.get('end', '-')}\nCredit: {credit}",
        }

    def _render_results_view(self) -> None:
        self._clear_results_view()
        if not self.clip_results:
            self._set_results_header("Belum ada clip yang berhasil dirender. Cek tab Console untuk detail error.")
            return

        self._set_results_header(
            f"{len(self.clip_results)} clip siap. Pilih panel per clip lalu tekan copy sesuai platform."
        )

        for item in self.clip_results:
            clip = item["clip"]
            clip_index = item["index"]
            copies = item["copies"]

            card = ctk.CTkFrame(self.results_scroll)
            card.pack(fill="x", expand=True, padx=4, pady=6)
            card.grid_columnconfigure(0, weight=1)

            title = ctk.CTkLabel(
                card,
                text=f"Clip #{clip_index} • {clip.get('title', 'Untitled')}",
                font=ctk.CTkFont(size=16, weight="bold"),
                anchor="w",
            )
            title.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))

            meta = ctk.CTkLabel(
                card,
                text=f"{clip.get('start', '-')} -> {clip.get('end', '-')}  |  {Path(item['video_file']).name}",
                anchor="w",
                text_color=("gray40", "gray70"),
            )
            meta.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))

            platform_tabs = ctk.CTkTabview(card)
            platform_tabs.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))

            for platform_name, content in copies.items():
                tab_label = PLATFORM_TAB_LABELS.get(platform_name, platform_name)
                platform_tabs.add(tab_label)
                tab = platform_tabs.tab(tab_label)

                actions = ctk.CTkFrame(tab, fg_color="transparent")
                actions.pack(fill="x", padx=4, pady=(6, 4))

                copy_btn = ctk.CTkButton(
                    actions,
                    text=f"Copy {platform_name}",
                    width=140,
                    command=lambda p=platform_name, c=content: self._copy_text(p, c),
                )
                copy_btn.pack(side="left")

                textbox = ctk.CTkTextbox(tab, height=140, wrap="word")
                textbox.pack(fill="both", expand=True, padx=4, pady=(0, 8))
                textbox.insert("1.0", content)
                textbox.configure(state="disabled")

            default_tab = "TikTok" if "TikTok" in copies else next(iter(copies))
            platform_tabs.set(PLATFORM_TAB_LABELS.get(default_tab, default_tab))

    def start_process_thread(self):
        url = self.url_entry.get().strip()
        if not url:
            print("[ERROR] URL Kosong!")
            return

        self.settings = self._collect_settings_from_ui()
        save_settings(self.settings)
        self._apply_runtime_paths(ensure_runtime_dirs(self.settings))
        self._refresh_dependency_status()
        if not getattr(self, "dependency_report", {"ready": True})["ready"]:
            print("[ERROR] Dependency wajib belum lengkap. Cek panel status di kiri.")
            return

        ai_cmd = self.ai_menu.get()
        print(f">> Menyambung ke '{ai_cmd}' CLI Backend...")
        
        params = {
            "max": self.max_clips_var.get(),
            "min_s": self.min_sec_var.get(),
            "max_s": self.max_sec_var.get(),
            "moment": self.moment_menu.get()
        }
        burn_subs = bool(self.chk_burn.get())
        aspect_mode = self.aspect_menu.get()
        render_mode = self.render_menu.get()
        source_platform = self.platform_menu.get()
        self.clip_results = []
        self._clear_results_view()
        self._set_results_header("Sedang memproses clip. Hasil copy-ready akan muncul di sini setelah render selesai.")
            
        self._set_start_button_state("disabled", "PROCESSING...")
        thread = threading.Thread(
            target=self.run_pipeline,
            args=(url, ai_cmd, params, burn_subs, aspect_mode, render_mode, source_platform),
            daemon=True,
        )
        thread.start()

    def run_pipeline(
        self,
        video_source,
        ai_cmd,
        params,
        burn_subs=True,
        aspect_mode="Aspect: Blur Bg",
        render_mode="Render: CPU",
        source_platform="Auto",
    ):
        try:
            print("=======================================")
            print("  STARTING ANALYZER & CUTTER PIPELINE  ")
            print("=======================================")
            
            ensure_runtime_dirs(self.settings)
            for stale in glob.glob(str(self.temp_dir / "raw_clip_*.mp4")):
                os.remove(stale)
                print(f"[CLEANUP] Menghapus raw clip lama: {stale}")
                
            self.console_box.after(0, self.console_box.insert, "end", "\n[0] Mengambil Metadata Video dan Setup Folders...\n")
            meta = get_video_metadata(video_source)
            output_dir = build_output_dir(self.output_root, meta)
            output_dir.mkdir(parents=True, exist_ok=True)
            self.console_box.after(0, self.console_box.insert, "end", f"[INFO] Direktori akhir: {output_dir}\n")

            detail_path = output_dir / "detail.md"
            with open(detail_path, "w", encoding="utf-8") as df:
                df.write(f"# Details for {meta['title']} by {meta['uploader']}\n\n")
                
            detected_platform = detect_source_platform(video_source)
            selected_platform = source_platform.lower()
            effective_platform = detected_platform if selected_platform == "auto" else selected_platform
            print(f"[INFO] Platform source: selected={source_platform} effective={effective_platform}")

            # 1. Ingest & Transcribe (Smart: Coba Subtitle platform-specific → Fallback Whisper)
            print("\n[1] Menyiapkan Transkripsi (Smart Subtitle Fetch / Whisper Fallback)...")
            self.console_box.after(0, self.console_box.insert, "end", "\n[1] Smart Fetching Subtitle / Audio Fallback...\n")
            transcript_result = generate_timestamped_transcript(
                video_source,
                audio_path=str(self.temp_dir / "source_audio.m4a"),
                source_platform=effective_platform,
            )
            if not transcript_result: return
            
            full_srt = transcript_result['srt_content']
            prompt_text = transcript_result['prompt_text']
            
            print(f"\n[3] Menganalisis Potensi Viral ({ai_cmd} CLI)...")
            viral_clips = analyze_transcript(prompt_text, ai_cmd, params, str(self.temp_dir))
            
            if not viral_clips:
                print("[WARNING] Tidak ada klip viral (CLI output kosong/malformed).")
                return

            success_count = 0
            failed_count = 0
                
            for i, clip in enumerate(viral_clips, start=1):
                print(f"\n--- MEMPROSES KLIP #{i}: {clip.get('title')} ---")
                start_t = clip.get('start')
                end_t = clip.get('end')
                
                try:
                    duration_sec = parse_timecode_to_seconds(end_t) - parse_timecode_to_seconds(start_t)
                except Exception:
                    duration_sec = 60
                
                raw_clip_path = self.temp_dir / f"raw_clip_{i}.mp4"
                download_surgical_video(video_source, str(raw_clip_path), start_t, end_t)
                if not raw_clip_path.exists():
                    failed_count += 1
                    continue
                
                shifted_srt = self.temp_dir / f"subtitles_clip_{i}.srt"
                extract_and_shift_srt(full_srt, start_t, duration_sec, str(shifted_srt))
                
                safe_title = clip.get('title', f"ViralClip_{i}").replace(" ", "_").replace("/", "_")
                final_video = output_dir / f"clip_{i}_{safe_title}.mp4"
                
                render_clip(str(raw_clip_path), str(shifted_srt), str(final_video), burn_subs, aspect_mode, render_mode)
                if not final_video.exists():
                    failed_count += 1
                    continue

                success_count += 1
                self.clip_results.append({
                    "index": i,
                    "clip": clip,
                    "video_file": str(final_video),
                    "copies": self._build_platform_copy(clip, i, meta, str(final_video)),
                })
                
                with open(detail_path, "a", encoding="utf-8") as df:
                    df.write(f"## Clip {i}: {clip.get('title', 'Untitled')}\n")
                    df.write(f"**Start:** {start_t}\n")
                    df.write(f"**End:** {end_t}\n\n")
                    df.write(f"**Caption:**\n{clip.get('caption', 'N/A')}\n\n")
                    df.write(f"**Credit:** {clip.get('credit', 'N/A')}\n\n")
                    df.write(f"**Reason:** {clip.get('reason', 'N/A')}\n")
                    df.write(f"**Video File:** clip_{i}_{safe_title}.mp4\n\n---\n\n")
                
            print(f"\n*** PROSES KLIPING SELESAI: {success_count} sukses, {failed_count} gagal. ***")
            self.after(0, self.refresh_output_library)
            self.after(0, self._render_results_view)
        except Exception as e:
            print(f"\n[FATAL ERROR] {e}")
        finally:
            self.after(0, self._set_start_button_state, "normal", "▶ START AI PROCESSING")

if __name__ == "__main__":
    # Fix untuk mengatasi terminal hang saat di force close pakai Ctrl+C 
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    
    app = YtClipperApp()
    app.mainloop()
