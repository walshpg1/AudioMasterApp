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
