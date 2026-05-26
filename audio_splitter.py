from __future__ import annotations
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ffmpeg_utils import find_ffmpeg

logger = logging.getLogger(__name__)


@dataclass
class SplitResult:
    clips: list[str] = field(default_factory=list)
    clip_count: int = 0
    output_dir: Optional[Path] = None
    error: Optional[str] = None


def split_audio(
    input_path: str,
    clip_duration: float,
    output_dir: Path,
) -> SplitResult:
    """Cut input_path into clips of clip_duration seconds, saved to output_dir.

    Uses FFmpeg segment muxer with stream-copy (no re-encoding).
    The final clip may be shorter than clip_duration if the file does not divide evenly.
    Returns SplitResult with error set on failure; never raises.
    """
    if clip_duration <= 0:
        return SplitResult(error=f"clip_duration must be > 0, got {clip_duration}")

    src = Path(input_path)
    if not src.exists():
        return SplitResult(error=f"Input file does not exist: {src}")

    output_dir = Path(output_dir)
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return SplitResult(error=f"Cannot create output directory: {exc}")

    ext = src.suffix  # preserves format: .wav, .mp3, .flac, etc.
    pattern = str(output_dir / f"{src.stem}_%03d{ext}")

    ffmpeg = find_ffmpeg() or "ffmpeg"
    cmd = [
        ffmpeg, "-y", "-i", str(src),
        "-f", "segment",
        "-segment_time", str(clip_duration),
        "-reset_timestamps", "1",
        "-segment_start_number", "1",
        "-c", "copy",
        pattern,
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return SplitResult(
            output_dir=output_dir,
            error="FFmpeg timed out after 600 s",
        )
    if proc.returncode != 0:
        logger.error("FFmpeg split failed: %s", proc.stderr[-800:])
        return SplitResult(
            output_dir=output_dir,
            error=f"FFmpeg split failed: {proc.stderr[-400:]}",
        )

    clips = sorted(output_dir.glob(f"{src.stem}_[0-9][0-9][0-9]{ext}"))
    return SplitResult(
        clips=[str(c) for c in clips],
        clip_count=len(clips),
        output_dir=output_dir,
    )
