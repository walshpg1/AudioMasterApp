from __future__ import annotations
from pathlib import Path
from youtube_import.models import DownloadJob, DownloadResult


def test_download_result_defaults():
    result = DownloadResult(success=False, output_path=None, error=None, log_lines=[])
    assert result.success is False
    assert result.output_path is None
    assert result.error is None
    assert result.log_lines == []
