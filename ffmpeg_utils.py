from __future__ import annotations
import shutil
import subprocess
import sys
from pathlib import Path

# On Windows, suppress the console window that would otherwise appear when
# launching console-subsystem executables (ffmpeg, yt-dlp, …) from a GUI process.
CREATE_NO_WINDOW_FLAG: int = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def find_ffmpeg() -> str | None:
    """Return the path to the ffmpeg executable, or None if not found.

    Search order:
    1. Beside the .exe when running as a PyInstaller bundle (sys.frozen).
    2. System PATH.
    """
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        candidate = exe_dir / "ffmpeg.exe"
        if candidate.exists():
            return str(candidate)
    return shutil.which("ffmpeg")


def get_ffmpeg_version(ffmpeg_path: str | None = None) -> str | None:
    """Return the first line of `ffmpeg -version`, or None on failure."""
    path = ffmpeg_path or find_ffmpeg()
    if not path:
        return None
    try:
        result = subprocess.run(
            [path, "-version"],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=CREATE_NO_WINDOW_FLAG,
        )
        if result.returncode == 0 and result.stdout:
            return result.stdout.splitlines()[0]
    except Exception:
        pass
    return None


def check_ffmpeg() -> tuple[bool, str]:
    """Return (available, message) describing the FFmpeg installation status."""
    path = find_ffmpeg()
    if not path:
        return False, (
            "FFmpeg was not found on this system.\n\n"
            "Install it with:\n"
            "  winget install Gyan.FFmpeg\n\n"
            "Then restart AudioMasterApp."
        )
    version_line = get_ffmpeg_version(path)
    parts = version_line.split() if version_line else []
    short = parts[2] if len(parts) >= 3 else "found"
    return True, f"FFmpeg {short}  ({path})"
