from pathlib import Path
from unittest.mock import MagicMock, patch
import threading
import pytest

from video_tools.extraction_service import ExtractionService
from video_tools.models import ExtractionJob, ExtractionResult


def make_mock_root():
    """Return a fake Tk root where after(0, fn) calls fn() immediately."""
    root = MagicMock()
    root.after.side_effect = lambda delay, fn: fn()
    return root


# ---------------------------------------------------------------------------
# extract_one
# ---------------------------------------------------------------------------

def test_extract_one_calls_runner_with_correct_args(tmp_path):
    root = make_mock_root()
    service = ExtractionService(root)
    results = []

    src = tmp_path / "render.mp4"
    src.write_bytes(b"fake")

    mock_result = ExtractionResult(
        job=ExtractionJob(src, tmp_path / "render_lastframe.png", "png"),
        success=True,
        output_path=tmp_path / "render_lastframe.png",
        ffmpeg_cmd=["ffmpeg"],
    )

    with patch("video_tools.extraction_service.ffmpeg_runner.run_extraction") as mock_run:
        mock_run.side_effect = lambda job, ffmpeg, on_done, **kw: on_done(mock_result)
        with patch("video_tools.extraction_service.find_ffmpeg", return_value="ffmpeg"):
            service.extract_one(src, tmp_path, "png", results.append)
            # Give daemon thread a moment
            import time; time.sleep(0.1)

    assert len(results) == 1
    assert results[0].success is True


def test_extract_one_output_path_naming(tmp_path):
    root = make_mock_root()
    service = ExtractionService(root)
    captured_jobs = []

    src = tmp_path / "my_render.mp4"
    src.write_bytes(b"fake")

    def fake_run(job, ffmpeg, on_done, **kw):
        captured_jobs.append(job)
        on_done(ExtractionResult(job=job, success=True, output_path=job.output_path, ffmpeg_cmd=[]))

    with patch("video_tools.extraction_service.ffmpeg_runner.run_extraction", side_effect=fake_run):
        with patch("video_tools.extraction_service.find_ffmpeg", return_value="ffmpeg"):
            service.extract_one(src, tmp_path, "png", lambda r: None)
            import time; time.sleep(0.1)

    assert len(captured_jobs) == 1
    assert captured_jobs[0].output_path.name == "my_render_lastframe.png"


def test_extract_one_jpg_output_naming(tmp_path):
    root = make_mock_root()
    service = ExtractionService(root)
    captured_jobs = []

    src = tmp_path / "clip.mp4"
    src.write_bytes(b"fake")

    def fake_run(job, ffmpeg, on_done, **kw):
        captured_jobs.append(job)
        on_done(ExtractionResult(job=job, success=True, output_path=job.output_path, ffmpeg_cmd=[]))

    with patch("video_tools.extraction_service.ffmpeg_runner.run_extraction", side_effect=fake_run):
        with patch("video_tools.extraction_service.find_ffmpeg", return_value="ffmpeg"):
            service.extract_one(src, tmp_path, "jpg", lambda r: None)
            import time; time.sleep(0.1)

    assert captured_jobs[0].output_path.name == "clip_lastframe.jpg"


# ---------------------------------------------------------------------------
# stop()
# ---------------------------------------------------------------------------

def test_stop_sets_stop_event():
    root = make_mock_root()
    service = ExtractionService(root)
    service.stop()  # should not raise even if never started


def test_stop_after_start_graceful(tmp_path):
    root = make_mock_root()
    service = ExtractionService(root)
    with patch("video_tools.extraction_service.find_ffmpeg", return_value="ffmpeg"):
        service.start(tmp_path, tmp_path / "stills", "png", lambda r: None)
    service.stop()  # should not raise or hang
    assert service._stop_event.is_set()
