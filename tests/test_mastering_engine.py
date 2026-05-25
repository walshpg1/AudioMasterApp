from pathlib import Path
import pytest
from mastering_engine import master, load_preset, list_presets, validate_preset, MasterResult
from export_formats import get_export_format, DEFAULT_FORMAT


# ---------------------------------------------------------------------------
# load_preset — existing presets
# ---------------------------------------------------------------------------

def test_load_preset_streaming():
    preset = load_preset("streaming_master")
    assert preset["target_lufs"] == -14.0
    assert preset["slug"] == "streaming_master"
    assert preset["compress"] is False


def test_load_preset_tiktok():
    preset = load_preset("tiktok_youtube_loud")
    assert preset["target_lufs"] == -12.0
    assert preset["compress"] is True


def test_load_preset_voiceover():
    preset = load_preset("voiceover")
    assert preset["target_lufs"] == -16.0
    assert preset["compress"] is False


def test_load_preset_demo():
    preset = load_preset("demo_loud")
    assert preset["target_lufs"] == -10.0
    assert preset["compress"] is True


# ---------------------------------------------------------------------------
# load_preset — new presets
# ---------------------------------------------------------------------------

def test_load_preset_podcast():
    preset = load_preset("podcast_master")
    assert preset["target_lufs"] == -16.0
    assert preset["compress"] is True
    assert preset["sort_order"] == 50


def test_load_preset_music_distribution():
    preset = load_preset("music_distribution")
    assert preset["target_lufs"] == -14.0
    assert preset["compress"] is True
    assert preset["compress_ratio"] == 1.5


def test_load_preset_cd_reference():
    preset = load_preset("cd_reference")
    assert preset["target_lufs"] == -9.0
    assert preset["true_peak_ceiling"] == -0.3
    assert preset["compress"] is True


def test_load_preset_vinyl_has_warning():
    preset = load_preset("vinyl_premaster")
    assert preset["target_lufs"] == -18.0
    assert preset["compress"] is False
    assert "warning" in preset
    assert len(preset["warning"]) > 10


# ---------------------------------------------------------------------------
# list_presets — dynamic registry
# ---------------------------------------------------------------------------

def test_list_presets_returns_eight():
    presets = list_presets()
    assert len(presets) == 8


def test_list_presets_sorted_by_sort_order():
    presets = list_presets()
    orders = [p.get("sort_order", 9999) for p in presets]
    assert orders == sorted(orders)


def test_list_presets_first_four_slugs():
    presets = list_presets()
    slugs = [p["slug"] for p in presets[:4]]
    assert slugs == ["streaming_master", "tiktok_youtube_loud", "voiceover", "demo_loud"]


def test_list_presets_all_have_required_fields():
    for preset in list_presets():
        assert validate_preset(preset) is None, f"Invalid preset: {preset.get('slug')}"


# ---------------------------------------------------------------------------
# validate_preset
# ---------------------------------------------------------------------------

def test_validate_preset_valid():
    data = {
        "name": "Test", "slug": "test",
        "target_lufs": -14.0, "true_peak_ceiling": -1.0, "compress": False,
    }
    assert validate_preset(data) is None


def test_validate_preset_missing_name():
    data = {"slug": "test", "target_lufs": -14.0, "true_peak_ceiling": -1.0, "compress": False}
    error = validate_preset(data)
    assert error is not None
    assert "name" in error


def test_validate_preset_missing_target_lufs():
    data = {"name": "Test", "slug": "test", "true_peak_ceiling": -1.0, "compress": False}
    error = validate_preset(data)
    assert error is not None
    assert "target_lufs" in error


def test_validate_preset_compress_not_bool():
    data = {
        "name": "Test", "slug": "test",
        "target_lufs": -14.0, "true_peak_ceiling": -1.0, "compress": "yes",
    }
    error = validate_preset(data)
    assert error is not None
    assert "compress" in error


def test_validate_preset_missing_multiple_fields():
    error = validate_preset({})
    assert error is not None
    assert "Missing" in error


# ---------------------------------------------------------------------------
# master() — default format (WAV 24-bit 48 kHz)
# ---------------------------------------------------------------------------

def test_master_streaming_creates_output_file(test_wav):
    preset = load_preset("streaming_master")
    result = master(test_wav, preset)
    assert result.error is None, result.error
    assert result.output_path is not None
    assert Path(result.output_path).exists()


def test_master_output_is_wav(test_wav):
    preset = load_preset("streaming_master")
    result = master(test_wav, preset)
    assert result.output_path.endswith(".wav")


def test_master_output_filename_contains_stem_and_slug(test_wav):
    preset = load_preset("voiceover")
    result = master(test_wav, preset)
    name = Path(result.output_path).name
    assert "test_source" in name
    assert "voiceover" in name
    assert "_mastered_" in name


def test_master_does_not_overwrite_input(test_wav):
    preset = load_preset("streaming_master")
    result = master(test_wav, preset)
    assert Path(result.output_path).resolve() != Path(test_wav).resolve()


def test_master_with_compression(test_wav):
    preset = load_preset("tiktok_youtube_loud")
    result = master(test_wav, preset)
    assert result.error is None, result.error
    assert Path(result.output_path).exists()


def test_master_demo_loud(test_wav):
    preset = load_preset("demo_loud")
    result = master(test_wav, preset)
    assert result.error is None, result.error


def test_master_missing_input_returns_error():
    preset = load_preset("streaming_master")
    result = master("nonexistent_file.wav", preset)
    assert result.error is not None
    assert result.output_path is None


def test_master_result_has_pass1_lufs(test_wav):
    preset = load_preset("streaming_master")
    result = master(test_wav, preset)
    assert result.pass1_lufs is not None
    assert isinstance(result.pass1_lufs, float)


def test_master_default_format_produces_wav(test_wav):
    preset = load_preset("streaming_master")
    result = master(test_wav, preset)
    assert result.output_path.endswith(".wav")
    assert "wav_24_48" in result.output_path


# ---------------------------------------------------------------------------
# master() — explicit export formats
# ---------------------------------------------------------------------------

def test_master_with_wav_16_441(test_wav):
    preset = load_preset("streaming_master")
    fmt = get_export_format("wav_16_441")
    result = master(test_wav, preset, fmt)
    assert result.error is None, result.error
    assert result.output_path.endswith(".wav")
    assert "wav_16_441" in result.output_path


def test_master_with_mp3_320(test_wav):
    preset = load_preset("streaming_master")
    fmt = get_export_format("mp3_320")
    result = master(test_wav, preset, fmt)
    assert result.error is None, result.error
    assert result.output_path.endswith(".mp3")
    assert Path(result.output_path).exists()


def test_master_with_mp3_192(test_wav):
    preset = load_preset("tiktok_youtube_loud")
    fmt = get_export_format("mp3_192")
    result = master(test_wav, preset, fmt)
    assert result.error is None, result.error
    assert result.output_path.endswith(".mp3")


def test_master_with_flac(test_wav):
    preset = load_preset("voiceover")
    fmt = get_export_format("flac_lossless")
    result = master(test_wav, preset, fmt)
    assert result.error is None, result.error
    assert result.output_path.endswith(".flac")
    assert Path(result.output_path).exists()


def test_master_format_slug_in_output_filename(test_wav):
    preset = load_preset("streaming_master")
    fmt = get_export_format("mp3_320")
    result = master(test_wav, preset, fmt)
    assert "mp3_320" in Path(result.output_path).name
