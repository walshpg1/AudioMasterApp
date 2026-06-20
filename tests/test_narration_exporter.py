import json
from pathlib import Path

import pytest

from narration_analysis.models import AnalysisResult, Scene, SceneEdit, TranscriptSegment
from narration_analysis.exporter import (
    _ensure_dirs,
    _fmt_srt_time,
    _fmt_vtt_time,
    _fmt_tc,
    corrected_files_exist,
    export_all,
    export_corrections,
    load_corrections,
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


# ---------------------------------------------------------------------------
# export_corrections
# ---------------------------------------------------------------------------

@pytest.fixture
def edits(scenes):
    return {
        1: SceneEdit(
            scene_number=1,
            original_narration="Hello world.",
            narration="Hello, world!",
            visual_prompt="Close-up of a smiling face.",
            edited=True,
        ),
        2: SceneEdit(
            scene_number=2,
            original_narration="The day work let me go.",
            narration="The day work let me go.",
            edited=False,
        ),
    }


@pytest.fixture
def corrected_transcript():
    return "Hello, world!\nThe day work let me go."


def test_export_corrections_returns_three_keys(result, edits, corrected_transcript):
    exported = export_corrections(result, edits, corrected_transcript)
    assert set(exported.keys()) == {"corrected_txt", "corrected_scene_list", "corrected_storyboard"}


def test_export_corrections_files_exist(result, edits, corrected_transcript):
    exported = export_corrections(result, edits, corrected_transcript)
    for path in exported.values():
        assert path.exists(), f"Missing: {path}"


def test_export_corrections_txt_content(result, edits, corrected_transcript):
    exported = export_corrections(result, edits, corrected_transcript)
    content = exported["corrected_txt"].read_text(encoding="utf-8")
    assert content == corrected_transcript


def test_export_corrections_txt_has_no_timestamps(result, edits, corrected_transcript):
    exported = export_corrections(result, edits, corrected_transcript)
    content = exported["corrected_txt"].read_text(encoding="utf-8")
    assert "[" not in content


def test_export_corrections_scene_list_has_edited_narration(result, edits, corrected_transcript):
    exported = export_corrections(result, edits, corrected_transcript)
    data = json.loads(exported["corrected_scene_list"].read_text(encoding="utf-8"))
    sc1 = next(s for s in data if s["scene"] == 1)
    assert sc1["narration"] == "Hello, world!"
    assert sc1["original_narration"] == "Hello world."
    assert sc1["edited"] is True


def test_export_corrections_scene_list_unedited_scene(result, edits, corrected_transcript):
    exported = export_corrections(result, edits, corrected_transcript)
    data = json.loads(exported["corrected_scene_list"].read_text(encoding="utf-8"))
    sc2 = next(s for s in data if s["scene"] == 2)
    assert sc2["narration"] == "The day work let me go."
    assert sc2["edited"] is False


def test_export_corrections_storyboard_has_original_narration(result, edits, corrected_transcript):
    exported = export_corrections(result, edits, corrected_transcript)
    data = json.loads(exported["corrected_storyboard"].read_text(encoding="utf-8"))
    sc1 = next(s for s in data["scenes"] if s["scene_number"] == 1)
    assert sc1["original_narration"] == "Hello world."
    assert sc1["narration"] == "Hello, world!"
    assert sc1["visual_prompt"] == "Close-up of a smiling face."
    assert sc1["edited"] is True


def test_export_corrections_storyboard_structure(result, edits, corrected_transcript):
    exported = export_corrections(result, edits, corrected_transcript)
    data = json.loads(exported["corrected_storyboard"].read_text(encoding="utf-8"))
    assert data["source"] == "voiceover.mp3"
    assert data["project_name"] == "My_Project"
    assert data["duration"] == 12.5
    assert len(data["scenes"]) == 2


def test_export_corrections_does_not_touch_original_files(result, edits, corrected_transcript):
    original_exported = export_all(result)
    export_corrections(result, edits, corrected_transcript)
    # Original files must be untouched
    for key, path in original_exported.items():
        assert path.exists(), f"Original file missing after corrections export: {key}"
    # Corrected files must be distinct paths
    corrected_exported = export_corrections(result, edits, corrected_transcript)
    original_paths = set(original_exported.values())
    corrected_paths = set(corrected_exported.values())
    assert original_paths.isdisjoint(corrected_paths)


# ---------------------------------------------------------------------------
# corrected_files_exist / load_corrections
# ---------------------------------------------------------------------------

def test_corrected_files_exist_false_before_save(result):
    _ensure_dirs(result.output_dir)
    assert corrected_files_exist(result) is False


def test_corrected_files_exist_true_after_save(result, edits, corrected_transcript):
    export_corrections(result, edits, corrected_transcript)
    assert corrected_files_exist(result) is True


def test_corrected_files_exist_false_when_only_txt_present(result, edits, corrected_transcript):
    export_corrections(result, edits, corrected_transcript)
    # Remove storyboard — should return False
    (result.output_dir / "storyboards" / "storyboard_corrected.json").unlink()
    assert corrected_files_exist(result) is False


def test_load_corrections_returns_transcript(result, edits, corrected_transcript):
    export_corrections(result, edits, corrected_transcript)
    loaded_transcript, _ = load_corrections(result)
    assert loaded_transcript == corrected_transcript


def test_load_corrections_returns_scene_edits(result, edits, corrected_transcript):
    export_corrections(result, edits, corrected_transcript)
    _, loaded_edits = load_corrections(result)
    assert set(loaded_edits.keys()) == {1, 2}


def test_load_corrections_restores_narration(result, edits, corrected_transcript):
    export_corrections(result, edits, corrected_transcript)
    _, loaded_edits = load_corrections(result)
    assert loaded_edits[1].narration == "Hello, world!"
    assert loaded_edits[2].narration == "The day work let me go."


def test_load_corrections_restores_original_narration(result, edits, corrected_transcript):
    export_corrections(result, edits, corrected_transcript)
    _, loaded_edits = load_corrections(result)
    assert loaded_edits[1].original_narration == "Hello world."


def test_load_corrections_restores_visual_prompt(result, edits, corrected_transcript):
    export_corrections(result, edits, corrected_transcript)
    _, loaded_edits = load_corrections(result)
    assert loaded_edits[1].visual_prompt == "Close-up of a smiling face."
    assert loaded_edits[2].visual_prompt == ""


def test_load_corrections_restores_edited_flag(result, edits, corrected_transcript):
    export_corrections(result, edits, corrected_transcript)
    _, loaded_edits = load_corrections(result)
    assert loaded_edits[1].edited is True
    assert loaded_edits[2].edited is False


def test_load_corrections_restores_status(result, edits, corrected_transcript):
    export_corrections(result, edits, corrected_transcript)
    _, loaded_edits = load_corrections(result)
    assert loaded_edits[1].status == "pending"


def test_load_corrections_raises_when_txt_missing(result, edits, corrected_transcript):
    export_corrections(result, edits, corrected_transcript)
    stem = result.source_path.stem
    (result.output_dir / "transcripts" / f"{stem}_corrected.txt").unlink()
    with pytest.raises(Exception):
        load_corrections(result)


def test_load_corrections_raises_when_storyboard_missing(result, edits, corrected_transcript):
    export_corrections(result, edits, corrected_transcript)
    (result.output_dir / "storyboards" / "storyboard_corrected.json").unlink()
    with pytest.raises(Exception):
        load_corrections(result)


def test_load_corrections_raises_on_invalid_json(result, edits, corrected_transcript):
    export_corrections(result, edits, corrected_transcript)
    sb_path = result.output_dir / "storyboards" / "storyboard_corrected.json"
    sb_path.write_text("not valid json", encoding="utf-8")
    with pytest.raises(Exception):
        load_corrections(result)
