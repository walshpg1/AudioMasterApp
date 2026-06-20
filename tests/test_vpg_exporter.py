import json
from pathlib import Path

import pytest

from visual_prompt_generator.exporter import write_storyboard_prompted
from visual_prompt_generator.models import GenerationJob, PromptResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def corrected_data():
    return {
        "source": "voiceover.wav",
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
def job():
    return GenerationJob(provider="mock", style="documentary")


@pytest.fixture
def results():
    return [
        PromptResult(
            scene_number=1,
            visual_prompt="Documentary scene illustrating: The beginning of the story.",
            camera="Static wide",
            mood="Calm",
        ),
        PromptResult(
            scene_number=2,
            visual_prompt="Documentary scene illustrating: The middle unfolds.",
            camera="Handheld",
            mood="Tense",
        ),
        PromptResult(
            scene_number=3,
            visual_prompt="Documentary scene illustrating: The end arrives.",
            camera="Slow zoom out",
            mood="Reflective",
        ),
    ]


# ---------------------------------------------------------------------------
# File creation
# ---------------------------------------------------------------------------

def test_creates_file(tmp_path, corrected_data, results, job):
    path = write_storyboard_prompted(tmp_path, corrected_data, results, job)
    assert path.exists()


def test_returns_correct_path(tmp_path, corrected_data, results, job):
    path = write_storyboard_prompted(tmp_path, corrected_data, results, job)
    assert path == tmp_path / "storyboards" / "storyboard_prompted.json"


def test_creates_storyboards_dir_if_missing(tmp_path, corrected_data, results, job):
    assert not (tmp_path / "storyboards").exists()
    write_storyboard_prompted(tmp_path, corrected_data, results, job)
    assert (tmp_path / "storyboards").is_dir()


# ---------------------------------------------------------------------------
# Top-level schema
# ---------------------------------------------------------------------------

def test_top_level_source(tmp_path, corrected_data, results, job):
    data = json.loads(
        write_storyboard_prompted(tmp_path, corrected_data, results, job).read_text("utf-8")
    )
    assert data["source"] == "voiceover.wav"


def test_top_level_project_name(tmp_path, corrected_data, results, job):
    data = json.loads(
        write_storyboard_prompted(tmp_path, corrected_data, results, job).read_text("utf-8")
    )
    assert data["project_name"] == "Test_Project"


def test_top_level_duration(tmp_path, corrected_data, results, job):
    data = json.loads(
        write_storyboard_prompted(tmp_path, corrected_data, results, job).read_text("utf-8")
    )
    assert data["duration"] == 30.0


def test_top_level_style(tmp_path, corrected_data, results, job):
    data = json.loads(
        write_storyboard_prompted(tmp_path, corrected_data, results, job).read_text("utf-8")
    )
    assert data["style"] == "documentary"


def test_top_level_provider(tmp_path, corrected_data, results, job):
    data = json.loads(
        write_storyboard_prompted(tmp_path, corrected_data, results, job).read_text("utf-8")
    )
    assert data["provider"] == "mock"


def test_top_level_generated_at_present(tmp_path, corrected_data, results, job):
    data = json.loads(
        write_storyboard_prompted(tmp_path, corrected_data, results, job).read_text("utf-8")
    )
    assert "generated_at" in data
    assert data["generated_at"]


# ---------------------------------------------------------------------------
# Scene records
# ---------------------------------------------------------------------------

def test_scene_count(tmp_path, corrected_data, results, job):
    data = json.loads(
        write_storyboard_prompted(tmp_path, corrected_data, results, job).read_text("utf-8")
    )
    assert len(data["scenes"]) == 3


def test_scene_has_visual_prompt(tmp_path, corrected_data, results, job):
    data = json.loads(
        write_storyboard_prompted(tmp_path, corrected_data, results, job).read_text("utf-8")
    )
    sc = data["scenes"][0]
    assert sc["visual_prompt"] == "Documentary scene illustrating: The beginning of the story."


def test_scene_has_camera(tmp_path, corrected_data, results, job):
    data = json.loads(
        write_storyboard_prompted(tmp_path, corrected_data, results, job).read_text("utf-8")
    )
    assert data["scenes"][0]["camera"] == "Static wide"


def test_scene_has_mood(tmp_path, corrected_data, results, job):
    data = json.loads(
        write_storyboard_prompted(tmp_path, corrected_data, results, job).read_text("utf-8")
    )
    assert data["scenes"][0]["mood"] == "Calm"


def test_scene_visual_type_is_video(tmp_path, corrected_data, results, job):
    data = json.loads(
        write_storyboard_prompted(tmp_path, corrected_data, results, job).read_text("utf-8")
    )
    for sc in data["scenes"]:
        assert sc["visual_type"] == "video"


def test_scene_generation_status_generated(tmp_path, corrected_data, results, job):
    data = json.loads(
        write_storyboard_prompted(tmp_path, corrected_data, results, job).read_text("utf-8")
    )
    for sc in data["scenes"]:
        assert sc["generation_status"] == "generated"


def test_scene_preserves_timecodes(tmp_path, corrected_data, results, job):
    data = json.loads(
        write_storyboard_prompted(tmp_path, corrected_data, results, job).read_text("utf-8")
    )
    sc = data["scenes"][1]
    assert sc["start"] == 10.0
    assert sc["end"] == 20.0
    assert sc["duration"] == 10.0


def test_scene_preserves_narration(tmp_path, corrected_data, results, job):
    data = json.loads(
        write_storyboard_prompted(tmp_path, corrected_data, results, job).read_text("utf-8")
    )
    assert data["scenes"][0]["narration"] == "The beginning of the story."


def test_scene_numbers_correct(tmp_path, corrected_data, results, job):
    data = json.loads(
        write_storyboard_prompted(tmp_path, corrected_data, results, job).read_text("utf-8")
    )
    assert [sc["scene_number"] for sc in data["scenes"]] == [1, 2, 3]


# ---------------------------------------------------------------------------
# Partial results (missing scene gets pending status)
# ---------------------------------------------------------------------------

def test_partial_results_pending_status(tmp_path, corrected_data, job):
    partial = [
        PromptResult(scene_number=1, visual_prompt="p1", camera="c1", mood="m1"),
        PromptResult(scene_number=3, visual_prompt="p3", camera="c3", mood="m3"),
    ]
    data = json.loads(
        write_storyboard_prompted(tmp_path, corrected_data, partial, job).read_text("utf-8")
    )
    assert data["scenes"][1]["generation_status"] == "pending"
    assert data["scenes"][1]["visual_prompt"] == ""
    assert data["scenes"][1]["camera"] == ""
    assert data["scenes"][1]["mood"] == ""


def test_partial_results_generated_scenes_intact(tmp_path, corrected_data, job):
    partial = [
        PromptResult(scene_number=1, visual_prompt="p1", camera="c1", mood="m1"),
    ]
    data = json.loads(
        write_storyboard_prompted(tmp_path, corrected_data, partial, job).read_text("utf-8")
    )
    assert data["scenes"][0]["generation_status"] == "generated"
    assert data["scenes"][0]["visual_prompt"] == "p1"


# ---------------------------------------------------------------------------
# Non-destructive — does not overwrite sibling storyboard files
# ---------------------------------------------------------------------------

def test_does_not_overwrite_corrected(tmp_path, corrected_data, results, job):
    sb_dir = tmp_path / "storyboards"
    sb_dir.mkdir(parents=True)
    corrected = sb_dir / "storyboard_corrected.json"
    corrected.write_text('{"sentinel": "corrected"}', encoding="utf-8")

    write_storyboard_prompted(tmp_path, corrected_data, results, job)

    assert json.loads(corrected.read_text("utf-8")) == {"sentinel": "corrected"}


def test_does_not_overwrite_original(tmp_path, corrected_data, results, job):
    sb_dir = tmp_path / "storyboards"
    sb_dir.mkdir(parents=True)
    original = sb_dir / "storyboard.json"
    original.write_text('{"sentinel": "original"}', encoding="utf-8")

    write_storyboard_prompted(tmp_path, corrected_data, results, job)

    assert json.loads(original.read_text("utf-8")) == {"sentinel": "original"}


def test_output_path_distinct_from_corrected(tmp_path, corrected_data, results, job):
    path = write_storyboard_prompted(tmp_path, corrected_data, results, job)
    assert path.name == "storyboard_prompted.json"
    assert "corrected" not in path.name
