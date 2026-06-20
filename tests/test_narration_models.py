from pathlib import Path
import pytest
from narration_analysis.models import TranscriptSegment, Scene, AnalysisResult, SceneEdit


def test_transcript_segment():
    seg = TranscriptSegment(start=1.0, end=5.5, text="Hello world.")
    assert seg.start == 1.0
    assert seg.end == 5.5
    assert seg.text == "Hello world."


def test_scene():
    sc = Scene(scene_number=3, start=10.0, end=20.0, text="A new beginning.")
    assert sc.scene_number == 3
    assert sc.start == 10.0
    assert sc.end == 20.0
    assert sc.text == "A new beginning."


def test_analysis_result_fields():
    segs = [TranscriptSegment(0.0, 5.0, "Hello.")]
    scenes = [Scene(1, 0.0, 5.0, "Hello.")]
    result = AnalysisResult(
        source_path=Path("voiceover.mp3"),
        project_name="My_Project",
        duration=5.0,
        segments=segs,
        scenes=scenes,
        output_dir=Path(r"D:\AIStudio\Outputs\narration_analysis\My_Project"),
    )
    assert result.project_name == "My_Project"
    assert result.duration == 5.0
    assert len(result.segments) == 1
    assert len(result.scenes) == 1


# ---------------------------------------------------------------------------
# SceneEdit
# ---------------------------------------------------------------------------

def test_scene_edit_defaults():
    edit = SceneEdit(scene_number=1, original_narration="Hello.", narration="Hello.")
    assert edit.visual_prompt == ""
    assert edit.status == "pending"
    assert edit.edited is False


def test_scene_edit_narration_independent_of_original():
    edit = SceneEdit(scene_number=2, original_narration="Original text.", narration="Original text.")
    edit.narration = "Corrected text."
    assert edit.original_narration == "Original text."
    assert edit.narration == "Corrected text."


def test_scene_edit_edited_flag_not_auto_set():
    # edited is False by default even if narration differs — caller must set it
    edit = SceneEdit(scene_number=1, original_narration="A", narration="B")
    assert edit.edited is False


def test_scene_edit_edited_flag_set_explicitly():
    edit = SceneEdit(scene_number=1, original_narration="A", narration="B", edited=True)
    assert edit.edited is True


def test_scene_edit_with_visual_prompt():
    edit = SceneEdit(
        scene_number=3,
        original_narration="A scene.",
        narration="A scene.",
        visual_prompt="Wide shot of mountains at dawn.",
        edited=True,
    )
    assert edit.visual_prompt == "Wide shot of mountains at dawn."
    assert edit.edited is True


def test_scene_edit_status_override():
    edit = SceneEdit(
        scene_number=1,
        original_narration="Hello.",
        narration="Hello.",
        status="approved",
    )
    assert edit.status == "approved"
