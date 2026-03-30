# Release Notes

## v0.1.0-alpha

Tanggal: 2026-03-31

### Highlight

- Linux-first alpha release siap dibagikan lewat GitHub
- installer cepat via `install_linux.sh`
- launcher siap pakai: `run_gui.sh` dan `run_cli.sh`
- settings per user untuk output root dan work root
- dependency status checker di GUI dan `doctor.sh`
- subtitle bawaan YouTube dengan fallback Whisper lokal
- browser existing outputs dan `Copy Hub` untuk caption siap copy

### Cocok Untuk

- tester Linux
- creator yang nyaman install dependency sistem
- workflow semi-manual dengan AI CLI login sendiri

### Belum Final

- belum ada installer Windows/macOS
- belum ada bundling binary/appimage
- AI CLI auth masih dilakukan manual oleh user
- build release ini belum memindahkan semua fitur override manual dari build utama

### Cara Mulai

```bash
chmod +x install_linux.sh run_gui.sh run_cli.sh doctor.sh
./install_linux.sh
./doctor.sh
./run_gui.sh
```

### Saat Melapor Bug

Sertakan:

- distro Linux
- output `./doctor.sh`
- AI CLI yang dipakai
- link video sample bila aman dibagikan
- log console yang relevan
