from pathlib import Path
from unittest.mock import patch
import pytest

from video_tools.extraction_service import ExtractionService
from video_tools.models import ExtractionResult


def make_mock_root():
    from unittest.mock import MagicMock
    root = MagicMock()
    root.after.side_effect = lambda delay, fn: fn()
    return root


def test_output_folder_created_if_missing(tmp_path):
    output_folder = tmp_path / "stills"
    assert not output_folder.exists()

    root = make_mock_root()
    service = ExtractionService(root)
    src = tmp_path / "render.mp4"
    src.write_bytes(b"fake")

    def fake_run(job, ffmpeg, on_done, **kw):
        on_done(ExtractionResult(job=job, success=True, output_path=job.output_path, ffmpeg_cmd=[]))

    with patch("video_tools.extraction_service.ffmpeg_runner.run_extraction", side_effect=fake_run):
        with patch("video_tools.extraction_service.find_ffmpeg", return_value="ffmpeg"):
            service.extract_one(src, output_folder, "png", lambda r: None)
            import time; time.sleep(0.1)

    assert output_folder.exists()


def test_output_filename_png(tmp_path):
    root = make_mock_root()
    service = ExtractionService(root)
    captured = []
    src = tmp_path / "render_001.mp4"
    src.write_bytes(b"x")

    def fake_run(job, ffmpeg, on_done, **kw):
        captured.append(job.output_path.name)
        on_done(ExtractionResult(job=job, success=True, output_path=job.output_path, ffmpeg_cmd=[]))

    with patch("video_tools.extraction_service.ffmpeg_runner.run_extraction", side_effect=fake_run):
        with patch("video_tools.extraction_service.find_ffmpeg", return_value="ffmpeg"):
            service.extract_one(src, tmp_path, "png", lambda r: None)
            import time; time.sleep(0.1)

    assert captured == ["render_001_lastframe.png"]


def test_output_filename_jpg(tmp_path):
    root = make_mock_root()
    service = ExtractionService(root)
    captured = []
    src = tmp_path / "clip.mp4"
    src.write_bytes(b"x")

    def fake_run(job, ffmpeg, on_done, **kw):
        captured.append(job.output_path.name)
        on_done(ExtractionResult(job=job, success=True, output_path=job.output_path, ffmpeg_cmd=[]))

    with patch("video_tools.extraction_service.ffmpeg_runner.run_extraction", side_effect=fake_run):
        with patch("video_tools.extraction_service.find_ffmpeg", return_value="ffmpeg"):
            service.extract_one(src, tmp_path, "jpg", lambda r: None)
            import time; time.sleep(0.1)

    assert captured == ["clip_lastframe.jpg"]
