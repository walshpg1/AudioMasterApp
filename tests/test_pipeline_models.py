from pathlib import Path
import pytest
from pipeline.models import MuxJob, MuxResult


def test_mux_job_fields(tmp_path):
    v = tmp_path / "video.mp4"
    a = tmp_path / "audio.wav"
    o = tmp_path / "out.mp4"
    job = MuxJob(video_path=v, audio_path=a, output_path=o)
    assert job.video_path == v
    assert job.audio_path == a
    assert job.output_path == o


def test_mux_result_success_defaults(tmp_path):
    job = MuxJob(tmp_path / "v.mp4", tmp_path / "a.wav", tmp_path / "o.mp4")
    result = MuxResult(job=job, success=True, ffmpeg_cmd=["ffmpeg"])
    assert result.success is True
    assert result.error is None


def test_mux_result_failure(tmp_path):
    job = MuxJob(tmp_path / "v.mp4", tmp_path / "a.wav", tmp_path / "o.mp4")
    result = MuxResult(job=job, success=False, ffmpeg_cmd=["ffmpeg"], error="bad exit")
    assert result.success is False
    assert result.error == "bad exit"
