from __future__ import annotations
import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

PRESETS_DIR = Path(__file__).parent / "presets"
OUTPUT_DIR = Path(__file__).parent / "output"

PRESET_ORDER = ["streaming_master", "tiktok_youtube_loud", "voiceover", "demo_loud"]


@dataclass
class MasterResult:
    output_path: Optional[str]
    preset_name: str
    pass1_lufs: Optional[float]
    error: Optional[str] = None


def load_preset(slug: str) -> dict:
    path = PRESETS_DIR / f"{slug}.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def list_presets() -> list[dict]:
    result = []
    for slug in PRESET_ORDER:
        path = PRESETS_DIR / f"{slug}.json"
        if path.exists():
            with open(path, encoding="utf-8") as f:
                result.append(json.load(f))
    return result


def master(input_path: str, preset: dict) -> MasterResult:
    input_path = Path(input_path)
    preset_name = preset["name"]
    slug = preset["slug"]
    target_lufs = preset["target_lufs"]
    true_peak = preset["true_peak_ceiling"]

    # Check if input file exists
    if not input_path.exists():
        return MasterResult(
            output_path=None,
            preset_name=preset_name,
            pass1_lufs=None,
            error=f"Input file does not exist: {input_path}"
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"{input_path.stem}_mastered_{slug}.wav"

    # Pass 1: measure
    p1_cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-af", f"loudnorm=I={target_lufs}:TP={true_peak}:LRA=11:print_format=json",
        "-f", "null", "-",
    ]
    p1 = subprocess.run(p1_cmd, capture_output=True, text=True)
    if p1.returncode != 0:
        logger.error("FFmpeg Pass 1 failed: %s", p1.stderr[-800:])
        return MasterResult(
            output_path=None,
            preset_name=preset_name,
            pass1_lufs=None,
            error=f"FFmpeg Pass 1 failed: {p1.stderr[-400:]}"
        )

    measured = _parse_loudnorm_json(p1.stderr)
    if measured is None:
        return MasterResult(
            output_path=None,
            preset_name=preset_name,
            pass1_lufs=None,
            error="Could not parse FFmpeg loudnorm output from Pass 1"
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

    # Pass 2: apply
    p2_cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-af", af,
        "-ar", "48000",
        "-c:a", "pcm_s24le",
        str(output_path),
    ]
    p2 = subprocess.run(p2_cmd, capture_output=True, text=True)
    if p2.returncode != 0:
        logger.error("FFmpeg Pass 2 failed: %s", p2.stderr[-800:])
        return MasterResult(
            output_path=None,
            preset_name=preset_name,
            pass1_lufs=pass1_lufs,
            error=f"FFmpeg Pass 2 failed: {p2.stderr[-400:]}"
        )

    return MasterResult(
        output_path=str(output_path),
        preset_name=preset_name,
        pass1_lufs=pass1_lufs
    )


def _parse_loudnorm_json(stderr: str) -> dict | None:
    start = stderr.rfind("{")
    end = stderr.rfind("}") + 1
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(stderr[start:end])
    except json.JSONDecodeError:
        return None
