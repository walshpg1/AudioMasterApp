from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class MuxJob:
    video_path: Path
    audio_path: Path
    output_path: Path


@dataclass
class MuxResult:
    job: MuxJob
    success: bool
    ffmpeg_cmd: list[str]
    error: Optional[str] = None
