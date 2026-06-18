import pytest
from narration_analysis.models import TranscriptSegment
from narration_analysis.scene_builder import build_scenes


def test_empty_segments():
    assert build_scenes([]) == []


def test_single_segment_no_split():
    segs = [TranscriptSegment(0.0, 5.0, "Hello world.")]
    scenes = build_scenes(segs)
    assert len(scenes) == 1
    assert scenes[0].scene_number == 1
    assert scenes[0].start == 0.0
    assert scenes[0].end == 5.0
    assert scenes[0].text == "Hello world."


def test_two_sentences_in_one_segment():
    segs = [TranscriptSegment(0.0, 10.0, "Hello world. Goodbye world.")]
    scenes = build_scenes(segs)
    assert len(scenes) == 2
    assert scenes[0].text == "Hello world."
    assert scenes[1].text == "Goodbye world."


def test_short_fragment_merged_with_previous():
    # "Yes." is one word — should merge with "Hello world."
    segs = [TranscriptSegment(0.0, 10.0, "Hello world. Yes. That is all.")]
    scenes = build_scenes(segs)
    assert len(scenes) == 2
    assert "Yes." in scenes[0].text
    assert scenes[1].text == "That is all."


def test_scene_numbers_are_sequential():
    segs = [
        TranscriptSegment(0.0, 5.0, "First sentence."),
        TranscriptSegment(5.0, 10.0, "Second sentence."),
    ]
    scenes = build_scenes(segs)
    assert [sc.scene_number for sc in scenes] == [1, 2]


def test_exclamation_and_question_split():
    segs = [TranscriptSegment(0.0, 9.0, "Are you ready? Yes! Let us begin.")]
    scenes = build_scenes(segs)
    assert len(scenes) == 3
    assert scenes[0].text == "Are you ready?"
    assert scenes[1].text == "Yes!"
    assert scenes[2].text == "Let us begin."


def test_timestamps_ordered():
    segs = [TranscriptSegment(0.0, 10.0, "First part. Second part.")]
    scenes = build_scenes(segs)
    assert scenes[0].start < scenes[0].end
    assert scenes[1].start >= scenes[0].end
    assert scenes[1].end == pytest.approx(10.0)


def test_multiple_segments():
    segs = [
        TranscriptSegment(0.0, 5.0, "Segment one."),
        TranscriptSegment(5.0, 10.0, "Segment two."),
        TranscriptSegment(10.0, 15.0, "Segment three."),
    ]
    scenes = build_scenes(segs)
    assert len(scenes) == 3
    assert scenes[2].end == 15.0
