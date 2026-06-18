from __future__ import annotations
import json
import logging
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

from export_formats import DEFAULT_FORMAT, list_export_formats

logger = logging.getLogger(__name__)


def _compute_settings_path(
    frozen: bool = False,
    executable_dir: Path | None = None,
) -> Path:
    """Return the path where settings.json should live.

    In packaged (frozen) mode, settings are stored in the user's AppData so they
    survive app updates.  In dev mode, the file lives beside this module.
    """
    if frozen:
        appdata = os.environ.get("APPDATA") or str(Path.home())
        return Path(appdata) / "AudioMasterApp" / "settings.json"
    return Path(__file__).parent / "settings.json"


SETTINGS_PATH = _compute_settings_path(
    frozen=getattr(sys, "frozen", False),
)


def _defaults() -> dict:
    return {
        "last_input_file": None,
        "last_input_folder": None,
        "last_output_folder": None,
        "last_selected_preset": None,
        "last_selected_export_format": DEFAULT_FORMAT.name,
        "resolve_import_enabled": False,
        "auto_generate_report": False,
        "latest_report_path": None,
        "last_watch_folder": None,
        "watch_poll_interval_seconds": 5,
        "move_processed_originals_enabled": True,
        "move_failed_originals_enabled": True,
        "resolve_handoff_note_enabled": False,
        "window_geometry": None,
        # Video Tools
        "video_watch_folder": r"D:\AIStudio\Outputs\video\raw",
        "video_output_folder": "",
        "video_format": "png",
        "video_watcher_enabled": False,
        # Pipeline
        "pipeline_output_folder": r"D:\AIStudio\Outputs\video\exports\tiktok",
        "pipeline_watcher_enabled": False,
        # YouTube Import
        "youtube_output_format": "mp3",
        "youtube_last_url":      "",
    }


def load(preset_names: list[str] | None = None) -> dict:
    """Load settings from disk.

    Creates defaults if the file is missing, backs up and recreates if corrupt.
    Validates preset and export-format references against currently available options.
    """
    if not SETTINGS_PATH.exists():
        defaults = _defaults()
        save(defaults)
        return defaults

    try:
        raw = SETTINGS_PATH.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("Root element is not a JSON object")
    except Exception as exc:
        logger.warning("Settings file is corrupt (%s) — backing up and recreating defaults", exc)
        _backup_corrupt()
        defaults = _defaults()
        save(defaults)
        return defaults

    # Merge with defaults so any keys added in future versions are always present
    settings = {**_defaults(), **data}

    # Validate preset reference — fall back to first available preset
    if preset_names is not None:
        if settings.get("last_selected_preset") not in preset_names:
            settings["last_selected_preset"] = preset_names[0] if preset_names else None

    # Validate export format reference — fall back to DEFAULT_FORMAT
    valid_format_names = {f.name for f in list_export_formats()}
    if settings.get("last_selected_export_format") not in valid_format_names:
        settings["last_selected_export_format"] = DEFAULT_FORMAT.name

    return settings


def save(settings: dict) -> None:
    """Write settings dict to disk. Silently logs on failure so app never crashes."""
    try:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_PATH.write_text(
            json.dumps(settings, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.error("Failed to save settings: %s", exc)


def _backup_corrupt() -> None:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = SETTINGS_PATH.parent / f"settings_corrupt_{timestamp}.json"
    try:
        shutil.copy2(SETTINGS_PATH, dest)
        logger.info("Backed up corrupt settings to %s", dest.name)
    except Exception as exc:
        logger.error("Could not back up corrupt settings: %s", exc)
