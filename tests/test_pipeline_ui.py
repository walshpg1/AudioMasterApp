from pathlib import Path
import time
import pytest

from pipeline.ui import find_latest_audio, _mux_is_ready


def test_find_latest_audio_returns_newest(tmp_path):
    old = tmp_path / "old.wav"
    new = tmp_path / "new.wav"
    old.write_bytes(b"x")
    time.sleep(0.02)
    new.write_bytes(b"x")
    result = find_latest_audio(tmp_path, frozenset({".wav", ".mp3"}))
    assert result == new


def test_find_latest_audio_ignores_non_audio(tmp_path):
    (tmp_path / "video.mp4").write_bytes(b"x")
    (tmp_path / "audio.wav").write_bytes(b"x")
    result = find_latest_audio(tmp_path, frozenset({".wav", ".mp3"}))
    assert result.name == "audio.wav"


def test_find_latest_audio_missing_dir(tmp_path):
    result = find_latest_audio(tmp_path / "nonexistent", frozenset({".wav"}))
    assert result is None


def test_find_latest_audio_empty_dir(tmp_path):
    result = find_latest_audio(tmp_path, frozenset({".wav", ".mp3"}))
    assert result is None


def test_mux_is_ready_requires_both(tmp_path):
    v = tmp_path / "v.mp4"
    a = tmp_path / "a.wav"
    assert _mux_is_ready(None, a, False) is False
    assert _mux_is_ready(v, None, False) is False


def test_mux_is_ready_blocked_when_running(tmp_path):
    v = tmp_path / "v.mp4"
    a = tmp_path / "a.wav"
    assert _mux_is_ready(v, a, mux_running=True) is False


def test_mux_is_ready_true_when_both_present(tmp_path):
    v = tmp_path / "v.mp4"
    a = tmp_path / "a.wav"
    assert _mux_is_ready(v, a, mux_running=False) is True
