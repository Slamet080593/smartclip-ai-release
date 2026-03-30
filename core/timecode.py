def parse_timecode_to_seconds(value: str) -> float:
    raw = (value or "").strip().replace(",", ".")
    if not raw:
        raise ValueError("Empty timecode")

    parts = raw.split(":")
    if len(parts) > 3:
        raise ValueError(f"Unsupported timecode: {value}")

    seconds = 0.0
    for part in parts:
        seconds = seconds * 60 + float(part)
    return seconds


def format_prompt_time(seconds: float) -> str:
    total_ms = int(round(seconds * 1000))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{milliseconds:03d}"
