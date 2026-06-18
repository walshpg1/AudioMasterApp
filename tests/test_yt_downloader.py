from __future__ import annotations
import sys
from pathlib import Path
from unittest.mock import patch
from youtube_import.models import DownloadJob, DownloadResult
from youtube_import.downloader import find_ytdlp


def test_download_result_defaults():
    result = DownloadResult(success=False, output_path=None, error=None, log_lines=[])
    assert result.success is False
    assert result.output_path is None
    assert result.error is None
    assert result.log_lines == []


def test_find_ytdlp_missing():
    with patch("shutil.which", return_value=None):
        with patch.object(sys, "frozen", False, create=True):
            result = find_ytdlp()
    assert result is None
