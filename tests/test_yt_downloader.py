from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

from youtube_import.models import DownloadJob, DownloadResult
from youtube_import.downloader import (
    find_ytdlp,
    parse_progress_line,
    parse_destination_line,
)


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


def test_parse_progress_download():
    result = parse_progress_line("[download]  47.3% of ~5.00MiB")
    assert result == ("downloading", 0.473)


def test_parse_progress_converting_ffmpeg():
    result = parse_progress_line("[ffmpeg] Merging formats into output.mp3")
    assert result == ("converting", None)


def test_parse_progress_converting_extract():
    result = parse_progress_line("[ExtractAudio] Destination: track.mp3")
    assert result == ("converting", None)


def test_parse_progress_irrelevant_line():
    result = parse_progress_line("[youtube] Extracting URL: https://youtube.com/watch?v=abc")
    assert result is None


def test_parse_progress_100_percent():
    result = parse_progress_line("[download] 100% of 5.00MiB")
    assert result == ("downloading", 1.0)


def test_parse_destination_line_valid():
    line = r"[ExtractAudio] Destination: D:\AIStudio\Outputs\audio\downloads\my track.mp3"
    result = parse_destination_line(line)
    assert result == Path(r"D:\AIStudio\Outputs\audio\downloads\my track.mp3")


def test_parse_destination_line_irrelevant():
    result = parse_destination_line("[download]  47.3% of ~5.00MiB")
    assert result is None
