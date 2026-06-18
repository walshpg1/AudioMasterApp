import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from narration_analysis.player import AudioPlayer


def _make_unavailable() -> AudioPlayer:
    """Construct a player bypassing __init__ with _available=False."""
    p = AudioPlayer.__new__(AudioPlayer)
    p._available = False
    p._data = None
    p._sr = 44100
    p._path = None
    p._playing = False
    p._seek_offset = 0.0
    p._play_start = 0.0
    p._lock = threading.Lock()
    return p


def test_is_playing_false_when_unavailable():
    assert _make_unavailable().is_playing() is False


def test_get_pos_zero_when_unavailable():
    assert _make_unavailable().get_pos_seconds() == 0.0


def test_seek_does_not_raise_when_unavailable():
    _make_unavailable().seek(30.0)  # must not raise


def test_play_does_not_raise_when_unavailable():
    _make_unavailable().play()


def test_pause_does_not_raise_when_unavailable():
    _make_unavailable().pause()


def test_stop_does_not_raise_when_unavailable():
    _make_unavailable().stop()


def test_cleanup_does_not_raise_when_unavailable():
    _make_unavailable().cleanup()


def test_load_does_not_set_path_when_unavailable():
    p = _make_unavailable()
    p.load(Path("test.mp3"))
    assert p._path is None


def test_seek_offset_set_on_seek():
    import numpy as np
    mock_sd = MagicMock()

    p = AudioPlayer.__new__(AudioPlayer)
    p._available = True
    p._data = np.zeros((44100, 2), dtype="float32")
    p._sr = 44100
    p._path = Path("test.mp3")
    p._playing = False
    p._seek_offset = 0.0
    p._play_start = 0.0
    p._lock = threading.Lock()

    with patch.dict("sys.modules", {"sounddevice": mock_sd}):
        with patch("threading.Thread") as mock_thread:
            mock_thread.return_value = MagicMock()
            p.seek(30.0)

    assert p._seek_offset == 30.0
    assert p._playing is True


def test_get_pos_adds_seek_offset():
    import time

    p = AudioPlayer.__new__(AudioPlayer)
    p._available = True
    p._data = None
    p._sr = 44100
    p._path = None
    p._playing = True
    p._seek_offset = 30.0
    p._play_start = time.time() - 5.0  # simulates 5s of playback
    p._lock = threading.Lock()

    pos = p.get_pos_seconds()
    assert pos == pytest.approx(35.0, abs=0.1)


def test_stop_resets_seek_offset():
    mock_sd = MagicMock()

    p = AudioPlayer.__new__(AudioPlayer)
    p._available = True
    p._data = None
    p._sr = 44100
    p._path = None
    p._playing = True
    p._seek_offset = 42.0
    p._play_start = 0.0
    p._lock = threading.Lock()

    with patch.dict("sys.modules", {"sounddevice": mock_sd}):
        p.stop()

    assert p._playing is False
    assert p._seek_offset == 0.0


def test_pause_captures_position():
    import time
    mock_sd = MagicMock()

    p = AudioPlayer.__new__(AudioPlayer)
    p._available = True
    p._data = None
    p._sr = 44100
    p._path = None
    p._playing = True
    p._seek_offset = 10.0
    p._play_start = time.time() - 3.0  # 3s elapsed
    p._lock = threading.Lock()

    with patch.dict("sys.modules", {"sounddevice": mock_sd}):
        p.pause()

    assert p._playing is False
    # seek_offset should now be approximately 13.0 (10 + 3)
    assert p._seek_offset == pytest.approx(13.0, abs=0.1)
