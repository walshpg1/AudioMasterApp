from __future__ import annotations
import logging
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable

from youtube_import.models import DownloadJob, DownloadResult
from ffmpeg_utils import CREATE_NO_WINDOW_FLAG

logger = logging.getLogger(__name__)

OUTPUTS_ROOT  = Path(r"D:\AIStudio\Outputs")
DOWNLOADS_DIR = OUTPUTS_ROOT / "audio" / "downloads"


def find_ytdlp() -> str | None:
    """Locate yt-dlp binary. Checks PyInstaller bundle dir first, then PATH."""
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        candidate = exe_dir / "yt-dlp.exe"
        if candidate.exists():
            return str(candidate)
    return shutil.which("yt-dlp")


def parse_progress_line(line: str) -> tuple[str, float | None] | None:
    """
    "[download]  47.3% ..."  -> ("downloading", 0.473)
    "[ffmpeg] ..."           -> ("converting", None)
    "[ExtractAudio] ..."     -> ("converting", None)
    anything else            -> None
    """
    stripped = line.strip()
    if stripped.startswith("[download]"):
        m = re.search(r"(\d+\.?\d*)%", stripped)
        if m:
            return ("downloading", float(m.group(1)) / 100.0)
    elif stripped.startswith("[ffmpeg]") or stripped.startswith("[ExtractAudio]"):
        return ("converting", None)
    return None


def parse_destination_line(line: str) -> Path | None:
    """
    "[ExtractAudio] Destination: D:\\path\\song.mp3" -> Path(...)
    "[download] Destination: D:\\path\\song.mp3"     -> Path(...)  (direct-audio fallback)
    anything else                                    -> None

    Both prefixes are checked; the caller keeps the last non-None result so that
    [ExtractAudio] (which appears after [download]) naturally wins when both are present.
    """
    stripped = line.strip()
    for prefix in ("[ExtractAudio] Destination: ", "[download] Destination: "):
        if stripped.startswith(prefix):
            return Path(stripped[len(prefix):])
    return None


def _extract_stderr_error(stderr_lines: list[str]) -> str | None:
    """Return the first genuine ERROR: line from yt-dlp stderr, or None.

    Warnings (e.g. version-age notices) are not errors and are ignored here.
    """
    for line in stderr_lines:
        if line.strip().upper().startswith("ERROR:"):
            return line.strip()
    return None


class YoutubeDownloader:
    def run(
        self,
        job: DownloadJob,
        progress_cb: Callable[[str, float | None], None],
        done_cb: Callable[[DownloadResult], None],
        cancel_event: threading.Event | None = None,
    ) -> None:
        cmd = [
            job.ytdlp_path,
            "-x",
            "--audio-format", job.output_format,
            "--audio-quality", "0",
            "--ffmpeg-location", job.ffmpeg_path,
            "--output", str(job.output_dir / "%(title)s.%(ext)s"),
            "--no-playlist",
            "--progress",
            "--newline",
            job.url,
        ]
        logger.info("[yt-dlp cmd] %s", " ".join(cmd))
        job.output_dir.mkdir(parents=True, exist_ok=True)

        log_lines: list[str] = []
        output_path: Path | None = None

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=CREATE_NO_WINDOW_FLAG,
            )

            # Signal UI immediately so "Downloading…" appears before first stdout line
            progress_cb("downloading", None)

            # Drain stderr concurrently to prevent pipe buffer deadlock
            stderr_lines: list[str] = []

            def _drain_stderr() -> None:
                for line in proc.stderr:
                    stripped = line.rstrip("\n")
                    stderr_lines.append(stripped)
                    s = stripped.strip()
                    if s.upper().startswith("ERROR:"):
                        logger.error("[yt-dlp err] %s", stripped)
                    elif s.upper().startswith("WARNING:"):
                        logger.warning("[yt-dlp err] %s", stripped)
                    else:
                        logger.debug("[yt-dlp err] %s", stripped)

            stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
            stderr_thread.start()

            cancelled = False
            for line in proc.stdout:
                stripped = line.rstrip("\n")
                logger.debug("[yt-dlp out] %s", stripped)
                log_lines.append(stripped)

                if cancel_event and cancel_event.is_set():
                    proc.kill()
                    proc.wait()
                    cancelled = True
                    break

                dest = parse_destination_line(stripped)
                if dest is not None:
                    output_path = dest

                parsed = parse_progress_line(stripped)
                if parsed is not None:
                    progress_cb(parsed[0], parsed[1])

            if cancelled:
                stderr_thread.join(timeout=2)
                done_cb(DownloadResult(
                    success=False, output_path=None,
                    error="Cancelled", log_lines=log_lines,
                ))
                return

            stderr_thread.join()
            proc.wait()

            logger.info(
                "[yt-dlp done] returncode=%d  stdout_lines=%d  stderr_lines=%d  output_path=%s",
                proc.returncode, len(log_lines), len(stderr_lines), output_path,
            )

            stderr_error = _extract_stderr_error(stderr_lines)

            if proc.returncode == 0 and output_path and output_path.exists() and stderr_error is None:
                done_cb(DownloadResult(
                    success=True, output_path=output_path,
                    error=None, log_lines=log_lines,
                ))
            else:
                if stderr_error:
                    error_msg = stderr_error[:200]
                elif proc.returncode != 0:
                    error_msg = f"yt-dlp exited with code {proc.returncode}"
                elif output_path is None:
                    error_msg = "Output file path not detected in yt-dlp output"
                else:
                    error_msg = f"Output file not found: {output_path}"
                done_cb(DownloadResult(
                    success=False, output_path=None,
                    error=error_msg, log_lines=log_lines,
                ))

        except Exception as exc:
            logger.error("[yt-dlp done] exception: %s", exc)
            done_cb(DownloadResult(
                success=False, output_path=None,
                error=str(exc), log_lines=log_lines,
            ))
