from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DownloadJob:
    url: str
    output_format: str      # "mp3" | "wav" | "flac"
    output_dir: Path
    ffmpeg_path: str
    ytdlp_path: str


@dataclass
class DownloadResult:
    success: bool
    output_path: Path | None
    error: str | None
    log_lines: list[str] = field(default_factory=list)
