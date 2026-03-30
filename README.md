# SmartClip AI Release

Potong video panjang jadi clip vertikal siap upload dengan bantuan AI, subtitle fallback, dan caption siap copy.

`SmartClip AI Release` adalah build Linux-first untuk creator yang ingin:

- mengambil momen terbaik dari video panjang
- render cepat ke format vertikal
- burn subtitle otomatis
- dapat caption siap copy untuk TikTok, Reels, Facebook, dan Shorts

Engine utamanya:

- `yt-dlp` untuk metadata, audio, dan clip extraction
- subtitle bawaan YouTube bila tersedia
- fallback Whisper lokal bila subtitle tidak ada
- AI CLI (`gemini`, `claude`, `qwen`, atau `codex`) untuk memilih momen
- `ffmpeg` untuk render vertikal + burn subtitle
- `Copy Hub` untuk caption siap copy per platform

## Status

Rilis ini ditujukan untuk **Linux alpha testing**.

## Fitur Utama

- clip extraction dari YouTube/Twitch source
- subtitle bawaan YouTube bila tersedia
- fallback Whisper lokal untuk video tanpa subtitle
- AI-assisted clip selection via `gemini`, `claude`, `qwen`, atau `codex`
- render vertikal + burn subtitle
- `Copy Hub` untuk copy caption per platform
- existing output browser untuk buka hasil lama tanpa rerun
- storage path configurable per user

Yang sudah siap:

- output/work path configurable per user
- settings disimpan per user
- dependency check di GUI dan CLI
- browser existing outputs
- copy-ready caption hub

Yang belum dijanjikan:

- installer Windows/macOS
- packaging satu-file
- onboarding non-teknis penuh

## Instalasi Cepat

Untuk user Linux, sekarang cukup:

```bash
git clone <repo-url>
cd Yt-Clipper-Release
chmod +x install_linux.sh run_gui.sh run_cli.sh doctor.sh
./install_linux.sh
./doctor.sh
./run_gui.sh
```

Script installer akan:

- install dependency sistem Linux yang dibutuhkan
- membuat virtualenv `.venv`
- install dependency Python
- memastikan `yt-dlp` tersedia

Yang masih perlu disiapkan user sendiri:

- login AI CLI seperti `gemini` atau `claude`

## Cek Kondisi Mesin

Setelah install, jalankan:

```bash
./doctor.sh
```

Tool ini akan cek:

- binary sistem yang dibutuhkan
- paket Python di `.venv`
- AI CLI mana yang tersedia di PATH

## Dependency Sistem

Pastikan command berikut tersedia di `PATH`:

- `python3`
- `ffmpeg`
- `ffprobe`
- `yt-dlp`
- salah satu AI CLI:
  - `gemini`
  - `claude`
  - `qwen`
  - `codex`

Opsional tapi disarankan:

- browser login YouTube aktif agar `browser_cookie3` bisa membantu `yt-dlp`

## Setup Manual

Kalau tidak ingin pakai installer script, setup manual tetap bisa.

### Python Requirements

Install dependency Python:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Jalankan GUI

```bash
./run_gui.sh
```

Saat pertama kali membuka app:

1. cek panel `Dependency Status`
2. pilih `Output Root` untuk hasil video akhir
3. pilih `Work Root` untuk cache/temp
4. klik `Save Settings`

Default lokasi:

- output: `~/Videos/Yt-Clipper`
- work/cache: `~/.local/share/yt-clipper`
- settings: `~/.config/yt-clipper/settings.json`

## Jalankan CLI

```bash
./run_cli.sh
```

CLI akan:

- menampilkan settings aktif
- mengecek dependency
- meminta URL video
- menyimpan hasil ke output root yang aktif

## Catatan Operasional

- YouTube bisa memblokir request anonim. Jika clip extraction sering `429` atau `Sign in to confirm you’re not a bot`, login YouTube di browser lokal biasanya membantu.
- Render GPU akan fallback ke CPU bila encoder hardware gagal.
- Twitch didukung lewat jalur fallback audio + Whisper. Subtitle API YouTube hanya untuk source YouTube.
- Jika AI miss momen penting, gunakan build utama yang sudah punya manual override. Fitur itu belum dipindahkan ke fork release ini.

## Auth AI CLI

App ini tidak membundel login AI. User tetap harus login sekali ke CLI yang dipilih.

Contoh:

```bash
gemini
```

atau

```bash
claude
```

Kalau command ada tapi belum login, biasanya app akan tetap gagal saat analisis transcript.

## Struktur Output

Output disimpan seperti:

```text
<output-root>/YYYY-MM-DD/<uploader>/<title>/
```

Isi folder hasil:

- `clip_*.mp4`
- `detail.md`

## Known Limitations

- Linux-first, belum dibundel untuk Windows/macOS
- Whisper lokal bisa berat di CPU
- akurasi subtitle fallback tergantung kualitas audio
- beberapa video YouTube tetap bisa terkena rate limit walau cookies browser tersedia

## Rekomendasi Distribusi

Untuk alpha test via GitHub, paling aman bagikan dalam bentuk:

1. source folder ini
2. `install_linux.sh`
3. `run_gui.sh` / `run_cli.sh`
4. README ini

Belum disarankan mengklaim ini sebagai installer publik final lintas OS.

## Dokumen Tambahan

- catatan rilis alpha: `RELEASE_NOTES.md`
- template bug report GitHub: `.github/ISSUE_TEMPLATE/bug_report.md`
