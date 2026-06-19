import pytest
from narration_analysis.models import TranscriptSegment
from narration_analysis.scene_builder import build_scenes, build_scenes_narrative


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


# ---------------------------------------------------------------------------
# Narrative mode tests
# ---------------------------------------------------------------------------

def test_narrative_empty():
    assert build_scenes_narrative([]) == []


def test_narrative_scene_numbers_sequential():
    segs = [
        TranscriptSegment(0.0, 12.0, "First long sentence with plenty of words here."),
        TranscriptSegment(12.0, 24.0, "Second long sentence with plenty of words here."),
        TranscriptSegment(24.0, 36.0, "Third long sentence with plenty of words here."),
    ]
    scenes = build_scenes_narrative(segs)
    assert [sc.scene_number for sc in scenes] == list(range(1, len(scenes) + 1))


def test_narrative_merges_short_rhetorical_sentences():
    # Three short sentences under the target individually — subtitle mode gives 3,
    # narrative mode should keep them together.
    segs = [
        TranscriptSegment(0.0, 3.0, "21 years."),
        TranscriptSegment(3.0, 7.0, "That is how long I spent building my career."),
        TranscriptSegment(7.0, 11.0, "21 years of routines."),
    ]
    subtitle = build_scenes(segs)
    narrative = build_scenes_narrative(segs)
    assert len(subtitle) == 3
    assert len(narrative) < len(subtitle)
    assert "21 years." in narrative[0].text
    assert "That is how long" in narrative[0].text


def test_narrative_fewer_scenes_than_subtitle():
    # Realistic narration: many short sentences should collapse to far fewer narrative scenes.
    sentences = [
        "Every morning I woke up at six.",        # ~7w, 3s
        "I made the same coffee.",                 # ~5w, 2s
        "I drove the same route.",                 # ~5w, 2s
        "I sat at the same desk.",                 # ~6w, 2s
        "For twenty-one years I did this.",        # ~7w, 3s
        "Then one day the call came.",             # ~6w, 2s
        "Everything changed after that.",          # ~4w, 2s
        "Nothing would ever be the same again.",   # ~7w, 3s
    ]
    t = 0.0
    segs = []
    for s in sentences:
        dur = len(s.split()) * 0.4  # ~0.4s per word
        segs.append(TranscriptSegment(t, t + dur, s))
        t += dur

    subtitle = build_scenes(segs)
    narrative = build_scenes_narrative(segs)
    assert len(narrative) < len(subtitle)


def test_narrative_respects_max_duration():
    # Two 8-second segments: adding the second would reach 16s > MAX_DUR=15s.
    # The first must be flushed before the second is added.
    segs = [
        TranscriptSegment(0.0, 8.0, "First sentence has enough words to be a real scene."),
        TranscriptSegment(8.0, 16.0, "Second sentence has enough words to be a real scene."),
    ]
    scenes = build_scenes_narrative(segs)
    assert len(scenes) == 2
    assert scenes[0].end <= 8.0 + 1e-9
    assert scenes[1].start >= 8.0 - 1e-9


def test_narrative_respects_max_words():
    # Each segment has 27 words; 27+27=54 exceeds MAX_WORDS=50.
    # The first group must flush before the second is added.
    long_text = "word " * 26 + "end."   # 27 words
    segs = [
        TranscriptSegment(0.0, 5.0, long_text),
        TranscriptSegment(5.0, 10.0, long_text),
    ]
    scenes = build_scenes_narrative(segs)
    assert len(scenes) == 2


def test_narrative_paragraph_gap_flushes_at_minimum():
    # Two 6-second sentences (12s, ~16 words total) followed by a 1.5s gap.
    # 12s >= MIN_DUR=5 and 16 words >= MIN_WORDS=8 → paragraph flush.
    segs = [
        TranscriptSegment(0.0, 6.0, "This is the first long sentence with many words."),   # ~9w
        TranscriptSegment(6.0, 12.0, "This is the second long sentence with many words."), # ~9w
        # 1.5s gap
        TranscriptSegment(13.5, 19.5, "New paragraph starts here with fresh content."),    # ~8w
    ]
    scenes = build_scenes_narrative(segs)
    # Gap of 1.5s at 12s into a 18-word group → flush; third sentence is a new scene
    assert len(scenes) == 2
    assert scenes[1].start == pytest.approx(13.5)


def test_narrative_timestamps_span_group():
    segs = [
        TranscriptSegment(0.0, 5.0, "Opening line of the narration."),
        TranscriptSegment(5.0, 10.0, "Middle line of the narration."),
        TranscriptSegment(10.0, 15.0, "Closing line of the narration."),
    ]
    scenes = build_scenes_narrative(segs)
    # Regardless of how many scenes, first scene starts at 0 and last ends at 15
    assert scenes[0].start == 0.0
    assert scenes[-1].end == pytest.approx(15.0)
