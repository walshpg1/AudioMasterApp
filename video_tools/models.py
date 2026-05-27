from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class ExtractionJob:
    source_path: Path
    output_path: Path
    fmt: str  # "png" or "jpg"


@dataclass
class ExtractionResult:
    job: ExtractionJob
    success: bool
    output_path: Optional[Path]
    ffmpeg_cmd: list[str]
    error: Optional[str] = None
