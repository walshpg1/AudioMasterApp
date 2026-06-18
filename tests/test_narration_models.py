from pathlib import Path
import pytest
from narration_analysis.models import TranscriptSegment, Scene, AnalysisResult


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
