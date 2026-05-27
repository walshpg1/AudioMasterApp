from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from video_tools.models import ExtractionJob, ExtractionResult
from video_tools.ffmpeg_runner import build_command, run_extraction


# ---------------------------------------------------------------------------
# build_command
# ---------------------------------------------------------------------------

def test_build_command_png():
    job = ExtractionJob(
        source_path=Path("render_001.mp4"),
        output_path=Path("render_001_lastframe.png"),
        fmt="png",
    )
    cmd = build_command(job, ffmpeg="ffmpeg")
    assert cmd == [
        "ffmpeg", "-sseof", "-1",
        "-i", "render_001.mp4",
        "-frames:v", "1",
        "render_001_lastframe.png",
    ]


def test_build_command_jpg():
    job = ExtractionJob(
        source_path=Path("render_002.mp4"),
        output_path=Path("render_002_lastframe.jpg"),
        fmt="jpg",
    )
    cmd = build_command(job, ffmpeg="ffmpeg")
    assert cmd == [
        "ffmpeg", "-sseof", "-1",
        "-i", "render_002.mp4",
        "-frames:v", "1",
        "-q:v", "2",
        "render_002_lastframe.jpg",
    ]


def test_build_command_path_with_spaces():
    job = ExtractionJob(
        source_path=Path("my render final.mp4"),
        output_path=Path("my render final_lastframe.png"),
        fmt="png",
    )
    cmd = build_command(job, ffmpeg="ffmpeg")
    # paths must be list items, never joined into a shell string
    assert "my render final.mp4" in cmd
    assert "my render final_lastframe.png" in cmd
    assert len([x for x in cmd if " " in x]) >= 2  # spaces preserved inside items


def test_build_command_uses_provided_ffmpeg_path():
    job = ExtractionJob(Path("a.mp4"), Path("a_lastframe.png"), "png")
    cmd = build_command(job, ffmpeg=r"C:\ffmpeg\bin\ffmpeg.exe")
    assert cmd[0] == r"C:\ffmpeg\bin\ffmpeg.exe"


# ---------------------------------------------------------------------------
# run_extraction
# ---------------------------------------------------------------------------

def test_run_extraction_success(tmp_path):
    job = ExtractionJob(
        source_path=tmp_path / "render.mp4",
        output_path=tmp_path / "render_lastframe.png",
        fmt="png",
    )
    results = []

    mock_proc = MagicMock()
    mock_proc.returncode = 0

    with patch("video_tools.ffmpeg_runner.subprocess.run", return_value=mock_proc):
        run_extraction(job, "ffmpeg", on_done=results.append, retries=1, retry_delay=0)

    assert len(results) == 1
    assert results[0].success is True
    assert results[0].output_path == job.output_path
    assert results[0].error is None


def test_run_extraction_failure_all_retries(tmp_path):
    job = ExtractionJob(
        source_path=tmp_path / "bad.mp4",
        output_path=tmp_path / "bad_lastframe.png",
        fmt="png",
    )
    results = []

    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.stderr = "some ffmpeg error"

    with patch("video_tools.ffmpeg_runner.subprocess.run", return_value=mock_proc):
        run_extraction(job, "ffmpeg", on_done=results.append, retries=3, retry_delay=0)

    assert len(results) == 1
    assert results[0].success is False
    assert results[0].error is not None


def test_run_extraction_calls_on_done_exactly_once(tmp_path):
    job = ExtractionJob(tmp_path / "r.mp4", tmp_path / "r_lastframe.png", "png")
    call_count = []

    mock_proc = MagicMock()
    mock_proc.returncode = 0

    with patch("video_tools.ffmpeg_runner.subprocess.run", return_value=mock_proc):
        run_extraction(job, "ffmpeg", on_done=lambda r: call_count.append(1), retries=2, retry_delay=0)

    assert len(call_count) == 1


def test_run_extraction_ffmpeg_cmd_in_result(tmp_path):
    job = ExtractionJob(tmp_path / "x.mp4", tmp_path / "x_lastframe.png", "png")
    results = []

    mock_proc = MagicMock()
    mock_proc.returncode = 0

    with patch("video_tools.ffmpeg_runner.subprocess.run", return_value=mock_proc):
        run_extraction(job, "ffmpeg", on_done=results.append, retries=1, retry_delay=0)

    assert results[0].ffmpeg_cmd[0] == "ffmpeg"
    assert "-sseof" in results[0].ffmpeg_cmd
