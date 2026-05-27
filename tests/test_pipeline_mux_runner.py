import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pipeline.models import MuxJob, MuxResult
from pipeline.mux_runner import build_mux_command, run_mux


def make_job(tmp_path):
    return MuxJob(
        video_path=tmp_path / "render.mp4",
        audio_path=tmp_path / "audio.wav",
        output_path=tmp_path / "out.mp4",
    )


def test_build_mux_command_structure(tmp_path):
    job = make_job(tmp_path)
    cmd = build_mux_command(job)
    assert cmd[0] == "ffmpeg"
    assert str(job.video_path) in cmd
    assert str(job.audio_path) in cmd
    assert "-c:v" in cmd
    assert "copy" in cmd
    assert "-c:a" in cmd
    assert "aac" in cmd
    assert "-shortest" in cmd
    assert cmd[-1] == str(job.output_path)


def test_build_mux_command_input_order(tmp_path):
    job = make_job(tmp_path)
    cmd = build_mux_command(job)
    vi = cmd.index(str(job.video_path))
    ai = cmd.index(str(job.audio_path))
    assert vi < ai


def test_build_mux_command_custom_ffmpeg(tmp_path):
    job = make_job(tmp_path)
    cmd = build_mux_command(job, ffmpeg=r"C:\ffmpeg\bin\ffmpeg.exe")
    assert cmd[0] == r"C:\ffmpeg\bin\ffmpeg.exe"


def test_build_mux_command_paths_with_spaces(tmp_path):
    job = MuxJob(
        video_path=tmp_path / "my render.mp4",
        audio_path=tmp_path / "my audio.wav",
        output_path=tmp_path / "my out.mp4",
    )
    cmd = build_mux_command(job)
    assert str(job.video_path) in cmd
    assert str(job.audio_path) in cmd
    assert str(job.output_path) in cmd


def test_run_mux_success_calls_on_done_once(tmp_path):
    job = make_job(tmp_path)
    results = []
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    with patch("pipeline.mux_runner.subprocess.run", return_value=mock_proc):
        run_mux(job, "ffmpeg", results.append)
    assert len(results) == 1
    assert results[0].success is True
    assert results[0].ffmpeg_cmd[0] == "ffmpeg"


def test_run_mux_nonzero_exit(tmp_path):
    job = make_job(tmp_path)
    results = []
    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.stderr = "encoding error details"
    with patch("pipeline.mux_runner.subprocess.run", return_value=mock_proc):
        run_mux(job, "ffmpeg", results.append)
    assert len(results) == 1
    assert results[0].success is False
    assert results[0].error is not None


def test_run_mux_timeout(tmp_path):
    job = make_job(tmp_path)
    results = []
    with patch(
        "pipeline.mux_runner.subprocess.run",
        side_effect=subprocess.TimeoutExpired("ffmpeg", 300),
    ):
        run_mux(job, "ffmpeg", results.append)
    assert len(results) == 1
    assert results[0].success is False
    assert "timed out" in results[0].error.lower()


def test_run_mux_oserror(tmp_path):
    job = make_job(tmp_path)
    results = []
    with patch(
        "pipeline.mux_runner.subprocess.run",
        side_effect=OSError("ffmpeg not found"),
    ):
        run_mux(job, "ffmpeg", results.append)
    assert len(results) == 1
    assert results[0].success is False
