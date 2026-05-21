from pathlib import Path
import pytest
from mastering_engine import master, load_preset, list_presets, MasterResult


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


def test_list_presets_returns_four():
    presets = list_presets()
    assert len(presets) == 4


def test_list_presets_order():
    presets = list_presets()
    slugs = [p["slug"] for p in presets]
    assert slugs == ["streaming_master", "tiktok_youtube_loud", "voiceover", "demo_loud"]


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
