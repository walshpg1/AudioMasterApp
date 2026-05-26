from pathlib import Path
import numpy as np
import soundfile as sf
import pytest
from audio_splitter import split_audio, SplitResult


def _make_wav(path: Path, duration_seconds: float, sample_rate: int = 44100) -> str:
    rng = np.random.default_rng(0)
    samples = rng.uniform(-0.5, 0.5, (int(sample_rate * duration_seconds), 2))
    sf.write(str(path), samples, sample_rate, subtype="PCM_24")
    return str(path)


def test_split_happy_path(tmp_path):
    """15 s WAV split at 5 s → 3 clips of ~5 s each."""
    src = _make_wav(tmp_path / "song.wav", 15.0)
    result = split_audio(src, 5.0, tmp_path / "clips")
    assert result.error is None, result.error
    assert result.clip_count == 3
    assert len(result.clips) == 3
    for clip in result.clips:
        info = sf.info(clip)
        assert abs(info.duration - 5.0) < 0.1


def test_split_remainder_kept(tmp_path):
    """17 s WAV split at 5 s → 4 clips (3 × 5 s + 1 × 2 s)."""
    src = _make_wav(tmp_path / "song.wav", 17.0)
    result = split_audio(src, 5.0, tmp_path / "clips")
    assert result.error is None, result.error
    assert result.clip_count == 4
    durations = [sf.info(c).duration for c in result.clips]
    assert abs(durations[-1] - 2.0) < 0.2


def test_split_single_clip(tmp_path):
    """3 s WAV split at 5 s → 1 clip containing the whole file."""
    src = _make_wav(tmp_path / "song.wav", 3.0)
    result = split_audio(src, 5.0, tmp_path / "clips")
    assert result.error is None, result.error
    assert result.clip_count == 1


def test_split_invalid_duration(tmp_path):
    """duration=0 → error set, no files written."""
    src = _make_wav(tmp_path / "song.wav", 10.0)
    clips_dir = tmp_path / "clips"
    result = split_audio(src, 0.0, clips_dir)
    assert result.error is not None
    assert not clips_dir.exists() or not any(clips_dir.iterdir())


def test_split_bad_input_path(tmp_path):
    """Non-existent input file → error in SplitResult, clip_count == 0."""
    result = split_audio("nonexistent_file.wav", 5.0, tmp_path / "clips")
    assert result.error is not None
    assert result.clip_count == 0


def test_split_output_dir_created(tmp_path):
    """output_dir is created automatically if it does not exist."""
    src = _make_wav(tmp_path / "song.wav", 6.0)
    clips_dir = tmp_path / "new" / "nested" / "clips"
    result = split_audio(src, 5.0, clips_dir)
    assert result.error is None, result.error
    assert clips_dir.exists()


def test_split_clips_named_with_stem_and_number(tmp_path):
    """Clips are named {stem}_001.wav, {stem}_002.wav, …"""
    src = _make_wav(tmp_path / "mysong.wav", 12.0)
    result = split_audio(src, 5.0, tmp_path / "clips")
    assert result.error is None, result.error
    names = [Path(c).name for c in result.clips]
    assert names[0] == "mysong_001.wav"
    assert names[1] == "mysong_002.wav"
    assert names[2] == "mysong_003.wav"


def test_split_output_dir_on_result(tmp_path):
    """SplitResult.output_dir matches the directory passed in."""
    src = _make_wav(tmp_path / "song.wav", 5.0)
    clips_dir = tmp_path / "clips"
    result = split_audio(src, 5.0, clips_dir)
    assert result.output_dir == clips_dir
