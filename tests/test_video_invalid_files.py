from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from video_tools.watcher import VideoWatcher
from video_tools.ffmpeg_runner import run_extraction
from video_tools.models import ExtractionJob, ExtractionResult


def test_zero_byte_file_not_returned_by_watcher(tmp_path):
    (tmp_path / "empty.mp4").write_bytes(b"")
    watcher = VideoWatcher(tmp_path, stability_checks=1)
    watcher.scan()
    result = watcher.scan()
    assert result == []


def test_ffmpeg_failure_returns_error_result(tmp_path):
    job = ExtractionJob(
        source_path=tmp_path / "bad.mp4",
        output_path=tmp_path / "bad_lastframe.png",
        fmt="png",
    )
    results = []

    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.stderr = "Error opening input file."

    with patch("video_tools.ffmpeg_runner.subprocess.run", return_value=mock_proc):
        run_extraction(job, "ffmpeg", on_done=results.append, retries=1, retry_delay=0)

    assert results[0].success is False
    assert results[0].output_path is None
    assert "Error opening input file" in results[0].error


def test_ffmpeg_timeout_returns_error_result(tmp_path):
    import subprocess
    job = ExtractionJob(tmp_path / "big.mp4", tmp_path / "big_lastframe.png", "png")
    results = []

    with patch("video_tools.ffmpeg_runner.subprocess.run", side_effect=subprocess.TimeoutExpired("ffmpeg", 120)):
        run_extraction(job, "ffmpeg", on_done=results.append, retries=1, retry_delay=0)

    assert results[0].success is False
    assert "timed out" in results[0].error.lower()
