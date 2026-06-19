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


def test_load_does_nothing_when_unavailable():
    p = _make_unavailable()
    p.load(Path("test.mp3"))
    assert p._data is None


def test_seek_offset_set_on_seek():
    import numpy as np
    mock_sd = MagicMock()

    p = AudioPlayer.__new__(AudioPlayer)
    p._available = True
    p._data = np.zeros((44100, 2), dtype="float32")
    p._sr = 44100
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
    p._playing = True
    p._seek_offset = 10.0
    p._play_start = time.time() - 3.0  # 3s elapsed
    p._lock = threading.Lock()

    with patch.dict("sys.modules", {"sounddevice": mock_sd}):
        p.pause()

    assert p._playing is False
    # seek_offset should now be approximately 13.0 (10 + 3)
    assert p._seek_offset == pytest.approx(13.0, abs=0.1)


def test_set_position_does_not_start_playback():
    import numpy as np
    mock_sd = MagicMock()

    p = AudioPlayer.__new__(AudioPlayer)
    p._available = True
    p._data = np.zeros((44100, 2), dtype="float32")
    p._sr = 44100
    p._playing = False
    p._seek_offset = 0.0
    p._play_start = 0.0
    p._lock = threading.Lock()

    with patch.dict("sys.modules", {"sounddevice": mock_sd}):
        p.set_position(25.0)

    assert p._seek_offset == 25.0
    assert p._playing is False
    mock_sd.play.assert_not_called()


def test_set_position_does_nothing_when_unavailable():
    p = _make_unavailable()
    p.set_position(30.0)
    assert p._seek_offset == 0.0


# ---------------------------------------------------------------------------
# is_available / is_loaded properties
# ---------------------------------------------------------------------------

def test_is_available_false_when_unavailable():
    assert _make_unavailable().is_available is False


def test_is_loaded_false_when_no_data():
    import numpy as np
    p = AudioPlayer.__new__(AudioPlayer)
    p._available = True
    p._data = None
    p._sr = 44100
    p._playing = False
    p._seek_offset = 0.0
    p._play_start = 0.0
    p._lock = threading.Lock()
    assert p.is_loaded is False


def test_is_loaded_true_after_data_set():
    import numpy as np
    p = AudioPlayer.__new__(AudioPlayer)
    p._available = True
    p._data = np.zeros((1000, 2), dtype="float32")
    p._sr = 44100
    p._playing = False
    p._seek_offset = 0.0
    p._play_start = 0.0
    p._lock = threading.Lock()
    assert p.is_loaded is True


# ---------------------------------------------------------------------------
# load() raises on failure
# ---------------------------------------------------------------------------

def test_load_raises_on_decode_failure():
    p = AudioPlayer.__new__(AudioPlayer)
    p._available = True
    p._data = None
    p._sr = 44100
    p._playing = False
    p._seek_offset = 0.0
    p._play_start = 0.0
    p._lock = threading.Lock()

    def _bad_decode(path):
        raise RuntimeError("corrupt file")

    with patch("narration_analysis.player.AudioPlayer.load.__wrapped__", _bad_decode, create=True):
        with patch("audio_decode.decode_audio_file", side_effect=RuntimeError("corrupt file")):
            with pytest.raises(RuntimeError, match="corrupt file"):
                p.load(Path("bad.wav"))

    assert p._data is None  # data must not be set on failure


# ---------------------------------------------------------------------------
# play() uses _seek_offset (not always 0)
# ---------------------------------------------------------------------------

def test_play_starts_from_seek_offset():
    import numpy as np
    mock_sd = MagicMock()

    p = AudioPlayer.__new__(AudioPlayer)
    p._available = True
    p._data = np.zeros((44100 * 60, 2), dtype="float32")  # 60s of audio
    p._sr = 44100
    p._playing = False
    p._seek_offset = 30.0  # cursor at 30s
    p._play_start = 0.0
    p._lock = threading.Lock()

    with patch.dict("sys.modules", {"sounddevice": mock_sd}):
        with patch("threading.Thread") as mock_thread:
            mock_thread.return_value = MagicMock()
            p.play()

    # sd.play should have been called with a clip starting at 30s, not full data
    call_args = mock_sd.play.call_args
    clip_played = call_args[0][0]
    expected_start_sample = 30 * 44100
    expected_clip_len = 44100 * 60 - expected_start_sample
    assert len(clip_played) == expected_clip_len
    assert p._playing is True


def test_play_resets_playing_on_sd_error():
    import numpy as np
    mock_sd = MagicMock()
    mock_sd.play.side_effect = RuntimeError("device error")

    p = AudioPlayer.__new__(AudioPlayer)
    p._available = True
    p._data = np.zeros((44100, 2), dtype="float32")
    p._sr = 44100
    p._playing = False
    p._seek_offset = 0.0
    p._play_start = 0.0
    p._lock = threading.Lock()

    with patch.dict("sys.modules", {"sounddevice": mock_sd}):
        with pytest.raises(RuntimeError, match="device error"):
            p.play()

    assert p._playing is False
