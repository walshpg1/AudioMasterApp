from __future__ import annotations
import csv
import json
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from ffmpeg_utils import find_ffmpeg, CREATE_NO_WINDOW_FLAG

logger = logging.getLogger(__name__)

# Writable data directory: beside the exe when packaged, beside the module otherwise.
if getattr(sys, "frozen", False):
    REPORTS_DIR = Path(sys.executable).parent / "reports"
else:
    REPORTS_DIR = Path(__file__).parent / "reports"

CSV_COLUMNS = [
    "source_file",
    "output_file",
    "preset",
    "export_format",
    "before_integrated_lufs",
    "before_true_peak",
    "before_lra",
    "before_threshold",
    "before_target_offset",
    "after_integrated_lufs",
    "after_true_peak",
    "after_lra",
    "after_threshold",
    "after_target_offset",
    "status",
    "error_message",
    "processed_at",
]


def measure_file(path: str | Path) -> dict | None:
    """Run FFmpeg loudnorm analysis; return the parsed stats dict or None on failure."""
    cmd = [
        find_ffmpeg() or "ffmpeg", "-y", "-i", str(path),
        "-af", "loudnorm=I=-14:TP=-1:LRA=11:print_format=json",
        "-f", "null", "-",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW_FLAG)
        if proc.returncode != 0:
            return None
        return _parse_loudnorm_json(proc.stderr)
    except Exception as exc:
        logger.warning("measure_file failed for %s: %s", path, exc)
        return None


def build_row(
    source_file: str,
    output_file: str | None,
    preset_name: str,
    export_format_name: str,
    before_stats: dict | None,
    after_stats: dict | None,
    status: str,
    error_message: str | None = None,
    processed_at: str | None = None,
) -> dict:
    """Build a single CSV row dict from mastering result data."""
    def _get(stats: dict | None, key: str) -> str:
        if not stats:
            return ""
        val = stats.get(key, "")
        return str(val) if val is not None else ""

    if processed_at is None:
        processed_at = datetime.now().isoformat(timespec="seconds")

    return {
        "source_file": source_file or "",
        "output_file": output_file or "",
        "preset": preset_name or "",
        "export_format": export_format_name or "",
        "before_integrated_lufs": _get(before_stats, "input_i"),
        "before_true_peak": _get(before_stats, "input_tp"),
        "before_lra": _get(before_stats, "input_lra"),
        "before_threshold": _get(before_stats, "input_thresh"),
        "before_target_offset": _get(before_stats, "target_offset"),
        "after_integrated_lufs": _get(after_stats, "input_i"),
        "after_true_peak": _get(after_stats, "input_tp"),
        "after_lra": _get(after_stats, "input_lra"),
        "after_threshold": _get(after_stats, "input_thresh"),
        "after_target_offset": _get(after_stats, "target_offset"),
        "status": status,
        "error_message": error_message or "",
        "processed_at": processed_at,
    }


def write_report(rows: list[dict], reports_dir: Path | None = None) -> Path:
    """Write rows to a timestamped CSV file; return the path."""
    if reports_dir is None:
        reports_dir = REPORTS_DIR
    reports_dir = Path(reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)

    filename = f"mastering_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    report_path = reports_dir / filename

    with open(report_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    logger.info("Report written: %s (%d row(s))", report_path.name, len(rows))
    return report_path


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
                    return json.loads(stderr[start: i + 1])
                except json.JSONDecodeError:
                    return None
    return None
