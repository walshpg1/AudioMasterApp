import json
from pathlib import Path

import pytest

from narration_analysis.models import AnalysisResult, Scene, TranscriptSegment
from narration_analysis.exporter import (
    _ensure_dirs,
    _fmt_srt_time,
    _fmt_vtt_time,
    _fmt_tc,
    export_all,
)


@pytest.fixture
def segs():
    return [
        TranscriptSegment(start=0.0, end=5.0, text="Hello world."),
        TranscriptSegment(start=5.0, end=12.5, text="The day work let me go."),
    ]


@pytest.fixture
def scenes():
    return [
        Scene(scene_number=1, start=0.0, end=5.0, text="Hello world."),
        Scene(scene_number=2, start=5.0, end=12.5, text="The day work let me go."),
    ]


@pytest.fixture
def result(tmp_path, segs, scenes):
    return AnalysisResult(
        source_path=Path("voiceover.mp3"),
        project_name="My_Project",
        duration=12.5,
        segments=segs,
        scenes=scenes,
        output_dir=tmp_path,
    )


def test_fmt_srt_time():
    assert _fmt_srt_time(0.0) == "00:00:00,000"
    assert _fmt_srt_time(65.5) == "00:01:05,500"
    assert _fmt_srt_time(3661.123) == "01:01:01,123"


def test_fmt_vtt_time():
    assert _fmt_vtt_time(0.0) == "00:00.000"
    assert _fmt_vtt_time(65.5) == "01:05.500"


def test_fmt_tc():
    assert _fmt_tc(0.0) == "00:00"
    assert _fmt_tc(75.0) == "01:15"


def test_ensure_dirs_creates_subfolders(tmp_path):
    _ensure_dirs(tmp_path)
    for name in ("transcripts", "srt", "vtt", "json", "storyboards"):
        assert (tmp_path / name).is_dir()


def test_export_all_creates_all_files(result):
    exported = export_all(result)
    assert set(exported.keys()) == {"txt", "srt", "vtt", "alignment", "scene_list", "storyboard"}
    for path in exported.values():
        assert path.exists(), f"Missing: {path}"


def test_txt_content(result):
    exported = export_all(result)
    content = exported["txt"].read_text(encoding="utf-8")
    assert "[00:00] Hello world." in content
    assert "[00:05] The day work let me go." in content


def test_srt_content(result):
    exported = export_all(result)
    content = exported["srt"].read_text(encoding="utf-8")
    assert "1\n00:00:00,000 --> 00:00:05,000" in content
    assert "Hello world." in content
    assert "2\n00:00:05,000 --> 00:00:12,500" in content


def test_vtt_content(result):
    exported = export_all(result)
    content = exported["vtt"].read_text(encoding="utf-8")
    assert content.startswith("WEBVTT")
    assert "00:00.000 --> 00:05.000" in content


def test_alignment_json(result):
    exported = export_all(result)
    data = json.loads(exported["alignment"].read_text(encoding="utf-8"))
    assert data[0] == {"start": 0.0, "end": 5.0, "text": "Hello world."}
    assert data[1]["text"] == "The day work let me go."


def test_scene_list_json(result):
    exported = export_all(result)
    data = json.loads(exported["scene_list"].read_text(encoding="utf-8"))
    assert data[0]["scene"] == 1
    assert data[0]["start_tc"] == "00:00"
    assert data[0]["end_tc"] == "00:05"
    assert data[1]["start_tc"] == "00:05"


def test_storyboard_json(result):
    exported = export_all(result)
    data = json.loads(exported["storyboard"].read_text(encoding="utf-8"))
    assert data["project_name"] == "My_Project"
    assert data["source"] == "voiceover.mp3"
    assert data["duration"] == 12.5
    sc = data["scenes"][0]
    assert sc["scene_number"] == 1
    assert sc["narration"] == "Hello world."
    assert sc["start"] == 0.0
    assert sc["end"] == 5.0
    assert sc["duration"] == 5.0
    assert sc["visual_prompt"] == ""
    assert sc["status"] == "pending"


def test_storyboard_all_scenes_present(result):
    exported = export_all(result)
    data = json.loads(exported["storyboard"].read_text(encoding="utf-8"))
    assert len(data["scenes"]) == 2
    assert data["scenes"][1]["scene_number"] == 2
