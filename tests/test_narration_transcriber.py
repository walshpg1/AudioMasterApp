import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import narration_analysis.transcriber as _t
from narration_analysis.transcriber import transcribe, TranscriptionCancelled


@pytest.fixture(autouse=True)
def reset_model_cache():
    _t._CACHED_MODEL = None
    yield
    _t._CACHED_MODEL = None


def _fake_seg(start: float, end: float, text: str) -> MagicMock:
    seg = MagicMock()
    seg.start = start
    seg.end = end
    seg.text = text
    return seg


def _mock_whisper(seg_data: list[tuple], duration: float) -> MagicMock:
    segs = [_fake_seg(*d) for d in seg_data]
    info = MagicMock()
    info.duration = duration
    model = MagicMock()
    model.transcribe.return_value = (iter(segs), info)
    return model


def test_transcribe_returns_segments():
    mock = _mock_whisper([(0.0, 5.0, "  Hello world  ")], 5.0)
    with patch("narration_analysis.transcriber.WhisperModel", return_value=mock):
        segs, duration = transcribe(Path("test.wav"), "tiny", lambda f: None, threading.Event())
    assert len(segs) == 1
    assert segs[0].text == "Hello world"
    assert segs[0].start == 0.0
    assert segs[0].end == 5.0
    assert duration == 5.0


def test_transcribe_strips_whitespace():
    mock = _mock_whisper([(0.0, 3.0, "\n  Stripped text.\n")], 3.0)
    with patch("narration_analysis.transcriber.WhisperModel", return_value=mock):
        segs, _ = transcribe(Path("test.wav"), "tiny", lambda f: None, threading.Event())
    assert segs[0].text == "Stripped text."


def test_transcribe_cancelled_before_first_segment():
    mock = _mock_whisper([(0.0, 5.0, "Hello")], 5.0)
    cancel = threading.Event()
    cancel.set()
    with patch("narration_analysis.transcriber.WhisperModel", return_value=mock):
        with pytest.raises(TranscriptionCancelled):
            transcribe(Path("test.wav"), "tiny", lambda f: None, cancel)


def test_progress_callback_called_per_segment():
    mock = _mock_whisper(
        [(0.0, 5.0, "First."), (5.0, 10.0, "Second.")],
        10.0,
    )
    progress: list[float] = []
    with patch("narration_analysis.transcriber.WhisperModel", return_value=mock):
        transcribe(Path("test.wav"), "tiny", progress.append, threading.Event())
    assert len(progress) == 2
    assert progress[0] == pytest.approx(0.5)
    assert progress[1] == pytest.approx(1.0)


def test_model_cached_between_calls():
    mock = _mock_whisper([(0.0, 5.0, "Hello")], 5.0)
    with patch("narration_analysis.transcriber.WhisperModel", return_value=mock) as MockCls:
        transcribe(Path("test.wav"), "tiny", lambda f: None, threading.Event())
        _t._CACHED_MODEL[2].transcribe.return_value = (iter([_fake_seg(0.0, 5.0, "World")]), MagicMock(duration=5.0))
        transcribe(Path("test.wav"), "tiny", lambda f: None, threading.Event())
    assert MockCls.call_count == 1  # model constructed once, reused second call
