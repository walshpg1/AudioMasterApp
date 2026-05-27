from pathlib import Path
import pytest
from video_tools.models import ExtractionJob, ExtractionResult


def test_extraction_job_fields():
    job = ExtractionJob(
        source_path=Path("input.mp4"),
        output_path=Path("output.png"),
        fmt="png",
    )
    assert job.source_path == Path("input.mp4")
    assert job.output_path == Path("output.png")
    assert job.fmt == "png"


def test_extraction_result_success():
    job = ExtractionJob(Path("a.mp4"), Path("a_lastframe.png"), "png")
    result = ExtractionResult(
        job=job,
        success=True,
        output_path=Path("a_lastframe.png"),
        ffmpeg_cmd=["ffmpeg", "-sseof", "-1"],
    )
    assert result.success is True
    assert result.error is None
    assert result.ffmpeg_cmd == ["ffmpeg", "-sseof", "-1"]


def test_extraction_result_failure():
    job = ExtractionJob(Path("b.mp4"), Path("b_lastframe.png"), "png")
    result = ExtractionResult(
        job=job,
        success=False,
        output_path=None,
        ffmpeg_cmd=["ffmpeg"],
        error="FFmpeg timed out",
    )
    assert result.success is False
    assert result.output_path is None
    assert result.error == "FFmpeg timed out"
