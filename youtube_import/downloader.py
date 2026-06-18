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
    Parse yt-dlp progress lines.

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
    "[ExtractAudio] Destination: D:\\path\\to\\song.mp3" -> Path(...)
    anything else -> None
    """
    stripped = line.strip()
    prefix = "[ExtractAudio] Destination: "
    if stripped.startswith(prefix):
        return Path(stripped[len(prefix):])
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
            )

            # Drain stderr concurrently to prevent pipe buffer deadlock
            stderr_lines: list[str] = []
            def _drain_stderr() -> None:
                for l in proc.stderr:
                    stderr_lines.append(l.rstrip("\n"))
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
            stderr_output = "\n".join(stderr_lines)
            for err_line in stderr_lines:
                logger.debug("[yt-dlp err] %s", err_line)

            logger.info("[yt-dlp done] returncode=%d output_path=%s", proc.returncode, output_path)

            if proc.returncode == 0 and output_path and output_path.exists():
                done_cb(DownloadResult(
                    success=True, output_path=output_path,
                    error=None, log_lines=log_lines,
                ))
            else:
                error_msg = stderr_output.strip() or f"yt-dlp exited with code {proc.returncode}"
                done_cb(DownloadResult(
                    success=False, output_path=None,
                    error=error_msg[:200], log_lines=log_lines,
                ))

        except Exception as exc:
            logger.error("[yt-dlp done] exception: %s", exc)
            done_cb(DownloadResult(
                success=False, output_path=None,
                error=str(exc), log_lines=log_lines,
            ))
