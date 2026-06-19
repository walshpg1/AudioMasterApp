from __future__ import annotations
import json
import logging
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from export_formats import ExportFormat, DEFAULT_FORMAT
from ffmpeg_utils import find_ffmpeg, CREATE_NO_WINDOW_FLAG

logger = logging.getLogger(__name__)

# In a PyInstaller bundle, read-only resources live in sys._MEIPASS.
if getattr(sys, "frozen", False):
    PRESETS_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "presets"
else:
    PRESETS_DIR = Path(__file__).parent / "presets"

OUTPUT_DIR = Path(__file__).parent / "output"

REQUIRED_PRESET_FIELDS = {"name", "slug", "target_lufs", "true_peak_ceiling", "compress"}


@dataclass
class MasterResult:
    output_path: Optional[str]
    preset_name: str
    pass1_lufs: Optional[float]
    pass1_stats: Optional[dict] = None
    error: Optional[str] = None


def validate_preset(data: dict) -> str | None:
    """Return an error description if data is not a valid preset, None if valid."""
    missing = REQUIRED_PRESET_FIELDS - data.keys()
    if missing:
        return f"Missing required fields: {', '.join(sorted(missing))}"
    if not isinstance(data.get("compress"), bool):
        return "Field 'compress' must be a boolean"
    return None


def load_preset(slug: str) -> dict:
    path = PRESETS_DIR / f"{slug}.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def list_presets() -> list[dict]:
    """Load all valid presets from presets/, sorted by sort_order then name."""
    presets = []
    for path in sorted(PRESETS_DIR.glob("*.json")):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            error = validate_preset(data)
            if error:
                logger.warning("Skipping preset %s: %s", path.name, error)
                continue
            presets.append(data)
        except Exception as exc:
            logger.warning("Failed to load preset %s: %s", path.name, exc)
    presets.sort(key=lambda p: (p.get("sort_order", 9999), p["name"]))
    return presets


def master(
    input_path: str,
    preset: dict,
    export_fmt: ExportFormat | None = None,
    output_dir: Path | str | None = None,
) -> MasterResult:
    if export_fmt is None:
        export_fmt = DEFAULT_FORMAT

    input_path = Path(input_path)
    effective_output_dir = Path(output_dir) if output_dir else OUTPUT_DIR
    preset_name = preset["name"]
    slug = preset["slug"]
    target_lufs = preset["target_lufs"]
    true_peak = preset["true_peak_ceiling"]

    if not input_path.exists():
        return MasterResult(
            output_path=None,
            preset_name=preset_name,
            pass1_lufs=None,
            error=f"Input file does not exist: {input_path}",
        )

    effective_output_dir.mkdir(parents=True, exist_ok=True)
    output_path = (
        effective_output_dir
        / f"{input_path.stem}_mastered_{slug}_{export_fmt.slug}.{export_fmt.extension}"
    )

    ffmpeg = find_ffmpeg() or "ffmpeg"

    # Pass 1: measure integrated loudness
    p1_cmd = [
        ffmpeg, "-y", "-i", str(input_path),
        "-af", f"loudnorm=I={target_lufs}:TP={true_peak}:LRA=11:print_format=json",
        "-f", "null", "-",
    ]
    p1 = subprocess.run(p1_cmd, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW_FLAG)
    if p1.returncode != 0:
        logger.error("FFmpeg Pass 1 failed: %s", p1.stderr[-800:])
        return MasterResult(
            output_path=None,
            preset_name=preset_name,
            pass1_lufs=None,
            error=f"FFmpeg Pass 1 failed: {p1.stderr[-400:]}",
        )

    measured = _parse_loudnorm_json(p1.stderr)
    if measured is None:
        return MasterResult(
            output_path=None,
            preset_name=preset_name,
            pass1_lufs=None,
            error="Could not parse FFmpeg loudnorm output from Pass 1",
        )

    pass1_lufs = float(measured.get("input_i", 0.0))

    # Build filter chain for Pass 2
    loudnorm = (
        f"loudnorm=I={target_lufs}:TP={true_peak}:LRA=11"
        f":measured_I={measured['input_i']}"
        f":measured_TP={measured['input_tp']}"
        f":measured_LRA={measured['input_lra']}"
        f":measured_thresh={measured['input_thresh']}"
        f":offset={measured['target_offset']}"
        f":linear=true:print_format=none"
    )

    if preset.get("compress"):
        ratio = preset["compress_ratio"]
        thresh = preset["compress_threshold_db"]
        attack = preset["compress_attack_ms"]
        release = preset["compress_release_ms"]
        af = (
            f"acompressor=ratio={ratio}:threshold={thresh}dB"
            f":attack={attack}:release={release},"
            f"{loudnorm}"
        )
    else:
        af = loudnorm

    # Pass 2: apply loudnorm + encode to target format
    p2_cmd = [
        ffmpeg, "-y", "-i", str(input_path),
        "-af", af,
        "-ar", str(export_fmt.sample_rate),
        "-c:a", export_fmt.ffmpeg_codec,
        *export_fmt.ffmpeg_extra,
        str(output_path),
    ]
    p2 = subprocess.run(p2_cmd, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW_FLAG)
    if p2.returncode != 0:
        logger.error("FFmpeg Pass 2 failed: %s", p2.stderr[-800:])
        return MasterResult(
            output_path=None,
            preset_name=preset_name,
            pass1_lufs=pass1_lufs,
            pass1_stats=measured,
            error=f"FFmpeg Pass 2 failed: {p2.stderr[-400:]}",
        )

    return MasterResult(
        output_path=str(output_path),
        preset_name=preset_name,
        pass1_lufs=pass1_lufs,
        pass1_stats=measured,
    )


def _parse_loudnorm_json(stderr: str) -> dict | None:
    start = stderr.rfind("{")
    if start == -1:
        return None
    depth = 0
    for i, ch in enumerate(stderr[start:], start=start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(stderr[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None
