from __future__ import annotations
import logging
import subprocess
import time
from pathlib import Path
from typing import Callable

from video_tools.models import ExtractionJob, ExtractionResult

logger = logging.getLogger(__name__)


def build_command(job: ExtractionJob, ffmpeg: str = "ffmpeg") -> list[str]:
    """Return the FFmpeg command list for extracting the last frame.

    Pure function — no side effects. Paths are list items; shell=True is never used.
    """
    cmd = [
        ffmpeg,
        "-sseof", "-1",
        "-i", str(job.source_path),
        "-frames:v", "1",
    ]
    if job.fmt == "jpg":
        cmd += ["-q:v", "2"]
    cmd.append(str(job.output_path))
    return cmd


def run_extraction(
    job: ExtractionJob,
    ffmpeg_path: str,
    on_done: Callable[[ExtractionResult], None],
    retries: int = 3,
    retry_delay: float = 1.0,
) -> None:
    """Run FFmpeg to extract the last frame. Calls on_done exactly once.

    Retries up to `retries` times with `retry_delay` seconds between attempts,
    to handle temporarily locked files. Intended to be called from a background thread.
    """
    cmd = build_command(job, ffmpeg_path)
    last_error: str | None = None

    for attempt in range(retries):
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if proc.returncode == 0:
                on_done(ExtractionResult(
                    job=job,
                    success=True,
                    output_path=job.output_path,
                    ffmpeg_cmd=cmd,
                ))
                return
            last_error = proc.stderr[-400:] if proc.stderr else "non-zero exit"
            logger.warning("FFmpeg attempt %d/%d failed: %s", attempt + 1, retries, last_error)
        except subprocess.TimeoutExpired:
            last_error = "FFmpeg timed out after 120 s"
            logger.warning("FFmpeg attempt %d/%d timed out", attempt + 1, retries)
        except OSError as exc:
            last_error = str(exc)
            logger.warning("FFmpeg attempt %d/%d OSError: %s", attempt + 1, retries, exc)

        if attempt < retries - 1:
            time.sleep(retry_delay)

    on_done(ExtractionResult(
        job=job,
        success=False,
        output_path=None,
        ffmpeg_cmd=cmd,
        error=last_error,
    ))
