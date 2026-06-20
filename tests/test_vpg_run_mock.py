import json
from pathlib import Path

import pytest

from visual_prompt_generator.run_mock import (
    load_corrected_storyboard,
    main,
    print_summary,
    run_pipeline,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_CORRECTED_DATA = {
    "source": "test_audio.wav",
    "project_name": "Test_Project",
    "duration": 30.0,
    "scenes": [
        {
            "scene_number": 1,
            "start": 0.0,
            "end": 10.0,
            "duration": 10.0,
            "narration": "The beginning of the story.",
            "original_narration": "The beginning of the story.",
            "visual_prompt": "",
            "status": "pending",
            "edited": False,
        },
        {
            "scene_number": 2,
            "start": 10.0,
            "end": 20.0,
            "duration": 10.0,
            "narration": "The middle unfolds.",
            "original_narration": "The middle unfolds.",
            "visual_prompt": "",
            "status": "pending",
            "edited": False,
        },
        {
            "scene_number": 3,
            "start": 20.0,
            "end": 30.0,
            "duration": 10.0,
            "narration": "The end arrives.",
            "original_narration": "The end arrives.",
            "visual_prompt": "",
            "status": "pending",
            "edited": False,
        },
    ],
}


@pytest.fixture
def project_dir(tmp_path):
    """Return a project dir with storyboards/storyboard_corrected.json populated."""
    sb_dir = tmp_path / "storyboards"
    sb_dir.mkdir()
    corrected = sb_dir / "storyboard_corrected.json"
    corrected.write_text(json.dumps(_CORRECTED_DATA, indent=2), encoding="utf-8")
    return tmp_path


@pytest.fixture
def corrected_path(project_dir):
    return project_dir / "storyboards" / "storyboard_corrected.json"


# ---------------------------------------------------------------------------
# load_corrected_storyboard
# ---------------------------------------------------------------------------

def test_load_returns_dict(corrected_path):
    data = load_corrected_storyboard(corrected_path)
    assert isinstance(data, dict)


def test_load_returns_correct_project_name(corrected_path):
    data = load_corrected_storyboard(corrected_path)
    assert data["project_name"] == "Test_Project"


def test_load_returns_correct_scene_count(corrected_path):
    data = load_corrected_storyboard(corrected_path)
    assert len(data["scenes"]) == 3


def test_load_raises_on_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_corrected_storyboard(tmp_path / "nonexistent.json")


def test_load_raises_on_invalid_json(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("not valid json {{", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        load_corrected_storyboard(bad)


# ---------------------------------------------------------------------------
# run_pipeline — output file
# ---------------------------------------------------------------------------

def test_run_pipeline_writes_prompted(corrected_path, project_dir):
    run_pipeline(corrected_path)
    assert (project_dir / "storyboards" / "storyboard_prompted.json").exists()


def test_run_pipeline_output_path_in_summary(corrected_path, project_dir):
    summary = run_pipeline(corrected_path)
    assert summary["output_path"] == project_dir / "storyboards" / "storyboard_prompted.json"


def test_run_pipeline_output_path_exists(corrected_path):
    summary = run_pipeline(corrected_path)
    assert Path(summary["output_path"]).exists()


def test_run_pipeline_scene_count_matches(corrected_path):
    summary = run_pipeline(corrected_path)
    assert summary["scene_count"] == 3


def test_run_pipeline_n_generated_equals_scene_count(corrected_path):
    summary = run_pipeline(corrected_path)
    assert summary["n_generated"] == summary["scene_count"]


# ---------------------------------------------------------------------------
# run_pipeline — does not touch corrected file
# ---------------------------------------------------------------------------

def test_run_pipeline_does_not_modify_corrected(corrected_path):
    original = corrected_path.read_text(encoding="utf-8")
    run_pipeline(corrected_path)
    assert corrected_path.read_text(encoding="utf-8") == original


def test_run_pipeline_corrected_content_unchanged(corrected_path):
    original_data = json.loads(corrected_path.read_text(encoding="utf-8"))
    run_pipeline(corrected_path)
    after_data = json.loads(corrected_path.read_text(encoding="utf-8"))
    assert original_data == after_data


# ---------------------------------------------------------------------------
# run_pipeline — summary contents
# ---------------------------------------------------------------------------

def test_summary_project_name(corrected_path):
    summary = run_pipeline(corrected_path)
    assert summary["project_name"] == "Test_Project"


def test_summary_source(corrected_path):
    summary = run_pipeline(corrected_path)
    assert summary["source"] == "test_audio.wav"


def test_summary_scene_count(corrected_path):
    summary = run_pipeline(corrected_path)
    assert summary["scene_count"] == 3


def test_summary_output_path_key_present(corrected_path):
    summary = run_pipeline(corrected_path)
    assert "output_path" in summary


# ---------------------------------------------------------------------------
# run_pipeline — output JSON content
# ---------------------------------------------------------------------------

def test_output_scenes_have_visual_prompt(corrected_path):
    summary = run_pipeline(corrected_path)
    data = json.loads(Path(summary["output_path"]).read_text("utf-8"))
    for sc in data["scenes"]:
        assert sc["visual_prompt"], f"scene {sc['scene_number']} has empty visual_prompt"


def test_output_scenes_have_camera(corrected_path):
    summary = run_pipeline(corrected_path)
    data = json.loads(Path(summary["output_path"]).read_text("utf-8"))
    for sc in data["scenes"]:
        assert sc["camera"]


def test_output_scenes_have_mood(corrected_path):
    summary = run_pipeline(corrected_path)
    data = json.loads(Path(summary["output_path"]).read_text("utf-8"))
    for sc in data["scenes"]:
        assert sc["mood"]


def test_output_scenes_all_generated(corrected_path):
    summary = run_pipeline(corrected_path)
    data = json.loads(Path(summary["output_path"]).read_text("utf-8"))
    for sc in data["scenes"]:
        assert sc["generation_status"] == "generated"


def test_output_preserves_timecodes(corrected_path):
    summary = run_pipeline(corrected_path)
    data = json.loads(Path(summary["output_path"]).read_text("utf-8"))
    sc = data["scenes"][1]
    assert sc["start"] == 10.0
    assert sc["end"] == 20.0
    assert sc["duration"] == 10.0


def test_output_scene_count_matches_input(corrected_path):
    summary = run_pipeline(corrected_path)
    data = json.loads(Path(summary["output_path"]).read_text("utf-8"))
    assert len(data["scenes"]) == 3


def test_output_style_is_documentary(corrected_path):
    summary = run_pipeline(corrected_path)
    data = json.loads(Path(summary["output_path"]).read_text("utf-8"))
    assert data["style"] == "documentary"


def test_output_provider_is_mock(corrected_path):
    summary = run_pipeline(corrected_path)
    data = json.loads(Path(summary["output_path"]).read_text("utf-8"))
    assert data["provider"] == "mock"


# ---------------------------------------------------------------------------
# run_pipeline — error cases
# ---------------------------------------------------------------------------

def test_invalid_path_raises_file_not_found(tmp_path):
    bad = tmp_path / "nowhere" / "storyboard_corrected.json"
    with pytest.raises(FileNotFoundError):
        run_pipeline(bad)


# ---------------------------------------------------------------------------
# print_summary
# ---------------------------------------------------------------------------

def test_print_summary_contains_project_name(corrected_path, capsys):
    summary = run_pipeline(corrected_path)
    print_summary(summary)
    assert "Test_Project" in capsys.readouterr().out


def test_print_summary_contains_scene_count(corrected_path, capsys):
    summary = run_pipeline(corrected_path)
    print_summary(summary)
    assert "3" in capsys.readouterr().out


def test_print_summary_contains_output_path(corrected_path, capsys):
    summary = run_pipeline(corrected_path)
    print_summary(summary)
    assert "storyboard_prompted.json" in capsys.readouterr().out


def test_print_summary_contains_source(corrected_path, capsys):
    summary = run_pipeline(corrected_path)
    print_summary(summary)
    assert "test_audio.wav" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# main() CLI entry point
# ---------------------------------------------------------------------------

def test_main_no_args_returns_nonzero():
    assert main([]) != 0


def test_main_invalid_path_returns_nonzero(tmp_path):
    bad = str(tmp_path / "missing" / "storyboard_corrected.json")
    assert main([bad]) != 0


def test_main_valid_path_returns_zero(corrected_path):
    assert main([str(corrected_path)]) == 0


def test_main_valid_path_writes_output(corrected_path, project_dir):
    main([str(corrected_path)])
    assert (project_dir / "storyboards" / "storyboard_prompted.json").exists()


def test_main_prints_project_name(corrected_path, capsys):
    main([str(corrected_path)])
    assert "Test_Project" in capsys.readouterr().out
