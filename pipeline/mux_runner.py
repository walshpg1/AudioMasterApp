from __future__ import annotations
import logging
import subprocess
from typing import Callable

from pipeline.models import MuxJob, MuxResult
from ffmpeg_utils import CREATE_NO_WINDOW_FLAG

logger = logging.getLogger(__name__)

_MUX_TIMEOUT = 300  # 5 minutes


def build_mux_command(job: MuxJob, ffmpeg: str = "ffmpeg") -> list[str]:
    return [
        ffmpeg,
        "-i", str(job.video_path),
        "-i", str(job.audio_path),
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        str(job.output_path),
    ]


def run_mux(
    job: MuxJob,
    ffmpeg_path: str,
    on_done: Callable[[MuxResult], None],
) -> None:
    """Run FFmpeg mux in the calling thread. Calls on_done exactly once."""
    cmd = build_mux_command(job, ffmpeg_path)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=_MUX_TIMEOUT, creationflags=CREATE_NO_WINDOW_FLAG)
        if proc.returncode == 0:
            on_done(MuxResult(job=job, success=True, ffmpeg_cmd=cmd))
        else:
            error = proc.stderr[-400:] if proc.stderr else "non-zero exit"
            on_done(MuxResult(job=job, success=False, ffmpeg_cmd=cmd, error=error))
    except subprocess.TimeoutExpired:
        on_done(MuxResult(job=job, success=False, ffmpeg_cmd=cmd, error=f"FFmpeg mux timed out after {_MUX_TIMEOUT} s"))
    except OSError as exc:
        on_done(MuxResult(job=job, success=False, ffmpeg_cmd=cmd, error=str(exc)))
