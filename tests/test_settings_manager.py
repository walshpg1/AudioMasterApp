import json
import os
import pytest
from pathlib import Path
import settings_manager
from export_formats import DEFAULT_FORMAT


@pytest.fixture
def settings_path(tmp_path, monkeypatch):
    """Redirect SETTINGS_PATH to a temp file so tests never touch the real settings.json."""
    path = tmp_path / "settings.json"
    monkeypatch.setattr("settings_manager.SETTINGS_PATH", path)
    return path


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

def test_defaults_include_all_expected_keys(settings_path):
    settings = settings_manager.load()
    expected = [
        "last_input_file", "last_input_folder", "last_output_folder",
        "last_selected_preset", "last_selected_export_format",
        "resolve_import_enabled", "auto_generate_report",
        "latest_report_path",
        "last_watch_folder", "watch_poll_interval_seconds",
        "move_processed_originals_enabled", "move_failed_originals_enabled",
        "resolve_handoff_note_enabled",
        "window_geometry",
    ]
    for key in expected:
        assert key in settings, f"Missing key: {key}"


def test_latest_report_path_default_is_none(settings_path):
    settings = settings_manager.load()
    assert settings["latest_report_path"] is None


def test_watch_folder_default_is_none(settings_path):
    settings = settings_manager.load()
    assert settings["last_watch_folder"] is None


def test_watch_poll_interval_default_is_5(settings_path):
    settings = settings_manager.load()
    assert settings["watch_poll_interval_seconds"] == 5


def test_move_processed_default_is_true(settings_path):
    settings = settings_manager.load()
    assert settings["move_processed_originals_enabled"] is True


def test_move_failed_default_is_true(settings_path):
    settings = settings_manager.load()
    assert settings["move_failed_originals_enabled"] is True


def test_resolve_handoff_note_default_is_false(settings_path):
    settings = settings_manager.load()
    assert settings["resolve_handoff_note_enabled"] is False


def test_load_creates_file_when_missing(settings_path):
    assert not settings_path.exists()
    settings_manager.load()
    assert settings_path.exists()


def test_load_returns_default_export_format(settings_path):
    settings = settings_manager.load()
    assert settings["last_selected_export_format"] == DEFAULT_FORMAT.name


def test_load_returns_false_for_boolean_flags(settings_path):
    settings = settings_manager.load()
    assert settings["resolve_import_enabled"] is False
    assert settings["auto_generate_report"] is False


def test_load_returns_none_for_path_fields(settings_path):
    settings = settings_manager.load()
    assert settings["last_input_file"] is None
    assert settings["last_input_folder"] is None
    assert settings["last_output_folder"] is None
    assert settings["window_geometry"] is None


# ---------------------------------------------------------------------------
# Save / load roundtrip
# ---------------------------------------------------------------------------

def test_save_load_roundtrip(settings_path):
    settings = settings_manager.load()
    settings["last_input_file"] = "D:/Music/song.wav"
    settings["resolve_import_enabled"] = True
    settings["auto_generate_report"] = True
    settings_manager.save(settings)
    loaded = settings_manager.load()
    assert loaded["last_input_file"] == "D:/Music/song.wav"
    assert loaded["resolve_import_enabled"] is True
    assert loaded["auto_generate_report"] is True


def test_save_creates_valid_json(settings_path):
    settings_manager.save(settings_manager.load())
    data = json.loads(settings_path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)


def test_load_merges_missing_keys_from_partial_file(settings_path):
    settings_path.write_text(
        json.dumps({"last_input_file": "/test.wav"}), encoding="utf-8"
    )
    settings = settings_manager.load()
    assert "auto_generate_report" in settings
    assert "resolve_import_enabled" in settings
    assert settings["last_input_file"] == "/test.wav"


# ---------------------------------------------------------------------------
# Corrupt settings
# ---------------------------------------------------------------------------

def test_corrupt_json_returns_defaults(settings_path):
    settings_path.write_text("not valid json {{{{", encoding="utf-8")
    settings = settings_manager.load()
    assert settings["resolve_import_enabled"] is False
    assert settings["last_selected_export_format"] == DEFAULT_FORMAT.name


def test_corrupt_json_creates_backup_file(settings_path):
    settings_path.write_text("corrupted!", encoding="utf-8")
    settings_manager.load()
    backups = list(settings_path.parent.glob("settings_corrupt_*.json"))
    assert len(backups) == 1


def test_corrupt_backup_contains_original_content(settings_path):
    settings_path.write_text("corrupted!", encoding="utf-8")
    settings_manager.load()
    backups = list(settings_path.parent.glob("settings_corrupt_*.json"))
    assert backups[0].read_text(encoding="utf-8") == "corrupted!"


def test_non_dict_root_returns_defaults(settings_path):
    settings_path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    settings = settings_manager.load()
    assert settings["auto_generate_report"] is False


def test_corrupt_settings_recreates_file(settings_path):
    settings_path.write_text("bad!", encoding="utf-8")
    settings_manager.load()
    # New settings.json should be valid JSON after recovery
    data = json.loads(settings_path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# Preset validation
# ---------------------------------------------------------------------------

def test_invalid_preset_falls_back_to_first_in_list(settings_path):
    settings_path.write_text(
        json.dumps({"last_selected_preset": "Nonexistent Preset"}), encoding="utf-8"
    )
    preset_names = ["Streaming Master -14 LUFS", "Demo Loud -10 LUFS"]
    settings = settings_manager.load(preset_names)
    assert settings["last_selected_preset"] == "Streaming Master -14 LUFS"


def test_valid_preset_is_preserved(settings_path):
    settings_path.write_text(
        json.dumps({"last_selected_preset": "Demo Loud -10 LUFS"}), encoding="utf-8"
    )
    preset_names = ["Streaming Master -14 LUFS", "Demo Loud -10 LUFS"]
    settings = settings_manager.load(preset_names)
    assert settings["last_selected_preset"] == "Demo Loud -10 LUFS"


def test_none_preset_names_skips_preset_validation(settings_path):
    settings_path.write_text(
        json.dumps({"last_selected_preset": "Custom Preset"}), encoding="utf-8"
    )
    settings = settings_manager.load(preset_names=None)
    assert settings["last_selected_preset"] == "Custom Preset"


def test_invalid_preset_with_empty_list_sets_none(settings_path):
    settings_path.write_text(
        json.dumps({"last_selected_preset": "Gone"}), encoding="utf-8"
    )
    settings = settings_manager.load(preset_names=[])
    assert settings["last_selected_preset"] is None


# ---------------------------------------------------------------------------
# Export format validation
# ---------------------------------------------------------------------------

def test_invalid_export_format_falls_back_to_default(settings_path):
    settings_path.write_text(
        json.dumps({"last_selected_export_format": "AIFF 32-bit"}), encoding="utf-8"
    )
    settings = settings_manager.load()
    assert settings["last_selected_export_format"] == DEFAULT_FORMAT.name


def test_valid_export_format_is_preserved(settings_path):
    settings_path.write_text(
        json.dumps({"last_selected_export_format": "MP3 320 kbps"}), encoding="utf-8"
    )
    settings = settings_manager.load()
    assert settings["last_selected_export_format"] == "MP3 320 kbps"


def test_all_supported_formats_are_valid(settings_path):
    from export_formats import list_export_formats
    for fmt in list_export_formats():
        settings_path.write_text(
            json.dumps({"last_selected_export_format": fmt.name}), encoding="utf-8"
        )
        settings = settings_manager.load()
        assert settings["last_selected_export_format"] == fmt.name


# ---------------------------------------------------------------------------
# Packaged-mode path
# ---------------------------------------------------------------------------

def test_compute_settings_path_frozen_uses_appdata():
    path = settings_manager._compute_settings_path(frozen=True)
    appdata = os.environ.get("APPDATA") or str(Path.home())
    assert str(path).startswith(appdata)


def test_compute_settings_path_frozen_includes_app_name():
    path = settings_manager._compute_settings_path(frozen=True)
    assert "AudioMasterApp" in str(path)


def test_compute_settings_path_frozen_filename_is_settings_json():
    path = settings_manager._compute_settings_path(frozen=True)
    assert path.name == "settings.json"


def test_compute_settings_path_non_frozen_is_beside_module():
    path = settings_manager._compute_settings_path(frozen=False)
    expected = Path(settings_manager.__file__).parent / "settings.json"
    assert path == expected


def test_compute_settings_path_frozen_differs_from_non_frozen():
    frozen_path = settings_manager._compute_settings_path(frozen=True)
    dev_path = settings_manager._compute_settings_path(frozen=False)
    assert frozen_path != dev_path


def test_save_creates_parent_directory(tmp_path, monkeypatch):
    nested = tmp_path / "deep" / "nested" / "settings.json"
    monkeypatch.setattr("settings_manager.SETTINGS_PATH", nested)
    settings_manager.save(settings_manager._defaults())
    assert nested.exists()


def test_defaults_include_youtube_output_format():
    defaults = settings_manager._defaults()
    assert "youtube_output_format" in defaults
    assert defaults["youtube_output_format"] == "mp3"


def test_defaults_include_youtube_last_url():
    defaults = settings_manager._defaults()
    assert "youtube_last_url" in defaults
    assert defaults["youtube_last_url"] == ""
