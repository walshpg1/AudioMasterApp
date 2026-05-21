import math
import pytest
from audio_analysis import analyse, AnalysisResult, _subtype_to_bitdepth


def test_analyse_sample_rate(test_wav):
    result = analyse(test_wav)
    assert result.sample_rate == 44100


def test_analyse_channels(test_wav):
    result = analyse(test_wav)
    assert result.channels == 2


def test_analyse_bit_depth(test_wav):
    result = analyse(test_wav)
    assert result.bit_depth == "24-bit"


def test_analyse_duration(test_wav):
    result = analyse(test_wav)
    assert abs(result.duration_seconds - 3.0) < 0.05


def test_analyse_peak_is_finite_negative(test_wav):
    result = analyse(test_wav)
    assert math.isfinite(result.peak_dbfs)
    assert result.peak_dbfs < 0


def test_analyse_rms_is_finite_negative(test_wav):
    result = analyse(test_wav)
    assert math.isfinite(result.rms_dbfs)
    assert result.rms_dbfs < 0


def test_analyse_lufs_is_plausible(test_wav):
    result = analyse(test_wav)
    assert -70.0 < result.integrated_lufs < 0.0


def test_analyse_no_error_on_valid_file(test_wav):
    result = analyse(test_wav)
    assert result.error is None


def test_analyse_missing_file_returns_error():
    result = analyse("does_not_exist.wav")
    assert result.error is not None
    assert result.sample_rate == 0


def test_analyse_result_path_matches_input(test_wav):
    result = analyse(test_wav)
    assert result.path == test_wav


def test_subtype_to_bitdepth_pcm16():
    assert _subtype_to_bitdepth("PCM_16") == "16-bit"


def test_subtype_to_bitdepth_pcm24():
    assert _subtype_to_bitdepth("PCM_24") == "24-bit"


def test_subtype_to_bitdepth_float():
    assert _subtype_to_bitdepth("FLOAT") == "32-bit float"


def test_subtype_to_bitdepth_unknown():
    result = _subtype_to_bitdepth("VORBIS")
    assert result == "VORBIS"


def test_analyse_silent_wav_returns_no_error(silent_wav):
    result = analyse(silent_wav)
    assert result.error is None


def test_analyse_silent_wav_lufs_is_handled(silent_wav):
    import math
    result = analyse(silent_wav)
    # Silent audio produces -inf LUFS from pyloudnorm; the function must not crash
    assert result.error is None
    assert isinstance(result.integrated_lufs, float)
