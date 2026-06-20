from __future__ import annotations
import json
from pathlib import Path

from narration_analysis.models import AnalysisResult, Scene, SceneEdit, TranscriptSegment

_OUTPUT_ROOT = Path(r"D:\AIStudio\Outputs\narration_analysis")
_SUBFOLDERS = ("transcripts", "srt", "vtt", "json", "storyboards")


def _ensure_dirs(output_dir: Path) -> None:
    for name in _SUBFOLDERS:
        (output_dir / name).mkdir(parents=True, exist_ok=True)


def _fmt_srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds % 1) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _fmt_vtt_time(seconds: float) -> str:
    m = int(seconds // 60)
    s = int(seconds % 60)
    ms = int(round((seconds % 1) * 1000))
    return f"{m:02d}:{s:02d}.{ms:03d}"


def _fmt_tc(seconds: float) -> str:
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"


def _write_txt(output_dir: Path, stem: str, segments: list[TranscriptSegment]) -> Path:
    path = output_dir / "transcripts" / f"{stem}.txt"
    lines = [f"[{_fmt_tc(seg.start)}] {seg.text}" for seg in segments]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _write_srt(output_dir: Path, stem: str, segments: list[TranscriptSegment]) -> Path:
    path = output_dir / "srt" / f"{stem}.srt"
    blocks = [
        f"{i}\n{_fmt_srt_time(seg.start)} --> {_fmt_srt_time(seg.end)}\n{seg.text}"
        for i, seg in enumerate(segments, 1)
    ]
    path.write_text("\n\n".join(blocks), encoding="utf-8")
    return path


def _write_vtt(output_dir: Path, stem: str, segments: list[TranscriptSegment]) -> Path:
    path = output_dir / "vtt" / f"{stem}.vtt"
    lines = ["WEBVTT", ""]
    for seg in segments:
        lines += [f"{_fmt_vtt_time(seg.start)} --> {_fmt_vtt_time(seg.end)}", seg.text, ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _write_alignment(output_dir: Path, stem: str, segments: list[TranscriptSegment]) -> Path:
    path = output_dir / "json" / f"{stem}_alignment.json"
    data = [{"start": seg.start, "end": seg.end, "text": seg.text} for seg in segments]
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _write_scene_list(output_dir: Path, stem: str, scenes: list[Scene]) -> Path:
    path = output_dir / "json" / f"{stem}_scene_list.json"
    data = [
        {
            "scene": sc.scene_number,
            "start": sc.start,
            "end": sc.end,
            "start_tc": _fmt_tc(sc.start),
            "end_tc": _fmt_tc(sc.end),
            "text": sc.text,
        }
        for sc in scenes
    ]
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _write_storyboard(output_dir: Path, result: AnalysisResult) -> Path:
    path = output_dir / "storyboards" / "storyboard.json"
    data = {
        "source": result.source_path.name,
        "project_name": result.project_name,
        "duration": result.duration,
        "scenes": [
            {
                "scene_number": sc.scene_number,
                "narration": sc.text,
                "start": sc.start,
                "end": sc.end,
                "duration": round(sc.end - sc.start, 3),
                "visual_prompt": "",
                "status": "pending",
            }
            for sc in result.scenes
        ],
    }
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _write_corrected_txt(output_dir: Path, stem: str, corrected_transcript: str) -> Path:
    path = output_dir / "transcripts" / f"{stem}_corrected.txt"
    path.write_text(corrected_transcript, encoding="utf-8")
    return path


def _write_corrected_scene_list(
    output_dir: Path,
    stem: str,
    scenes: list[Scene],
    edits: dict[int, SceneEdit],
) -> Path:
    path = output_dir / "json" / f"{stem}_scene_list_corrected.json"
    data = []
    for sc in scenes:
        edit = edits.get(sc.scene_number)
        data.append({
            "scene": sc.scene_number,
            "start": sc.start,
            "end": sc.end,
            "start_tc": _fmt_tc(sc.start),
            "end_tc": _fmt_tc(sc.end),
            "original_narration": edit.original_narration if edit else sc.text,
            "narration": edit.narration if edit else sc.text,
            "edited": edit.edited if edit else False,
        })
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _write_corrected_storyboard(
    output_dir: Path,
    result: AnalysisResult,
    edits: dict[int, SceneEdit],
) -> Path:
    path = output_dir / "storyboards" / "storyboard_corrected.json"
    scenes = []
    for sc in result.scenes:
        edit = edits.get(sc.scene_number)
        scenes.append({
            "scene_number": sc.scene_number,
            "start": sc.start,
            "end": sc.end,
            "duration": round(sc.end - sc.start, 3),
            "original_narration": edit.original_narration if edit else sc.text,
            "narration": edit.narration if edit else sc.text,
            "visual_prompt": edit.visual_prompt if edit else "",
            "status": edit.status if edit else "pending",
            "edited": edit.edited if edit else False,
        })
    data = {
        "source": result.source_path.name,
        "project_name": result.project_name,
        "duration": result.duration,
        "scenes": scenes,
    }
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def export_corrections(
    result: AnalysisResult,
    edits: dict[int, SceneEdit],
    corrected_transcript: str,
) -> dict[str, Path]:
    """Write corrected output files. Never touches the original export files."""
    _ensure_dirs(result.output_dir)
    stem = result.source_path.stem
    return {
        "corrected_txt": _write_corrected_txt(result.output_dir, stem, corrected_transcript),
        "corrected_scene_list": _write_corrected_scene_list(
            result.output_dir, stem, result.scenes, edits
        ),
        "corrected_storyboard": _write_corrected_storyboard(result.output_dir, result, edits),
    }


def corrected_files_exist(result: AnalysisResult) -> bool:
    """Return True only when all three corrected files are present on disk."""
    stem = result.source_path.stem
    return (
        (result.output_dir / "transcripts" / f"{stem}_corrected.txt").exists()
        and (result.output_dir / "storyboards" / "storyboard_corrected.json").exists()
    )


def load_corrections(result: AnalysisResult) -> tuple[str, dict[int, SceneEdit]]:
    """Read corrected state from disk.

    Uses storyboard_corrected.json as the source of truth for scene edits
    and <stem>_corrected.txt for the transcript.  Raises on missing or
    invalid files so the caller can fall back to fresh Whisper output.
    """
    stem = result.source_path.stem

    txt_path = result.output_dir / "transcripts" / f"{stem}_corrected.txt"
    corrected_transcript = txt_path.read_text(encoding="utf-8")

    sb_path = result.output_dir / "storyboards" / "storyboard_corrected.json"
    data = json.loads(sb_path.read_text(encoding="utf-8"))

    edits: dict[int, SceneEdit] = {}
    for sc in data["scenes"]:
        sn = int(sc["scene_number"])
        edits[sn] = SceneEdit(
            scene_number=sn,
            original_narration=sc.get("original_narration", sc.get("narration", "")),
            narration=sc.get("narration", ""),
            visual_prompt=sc.get("visual_prompt", ""),
            status=sc.get("status", "pending"),
            edited=bool(sc.get("edited", False)),
        )

    return corrected_transcript, edits


def export_all(result: AnalysisResult) -> dict[str, Path]:
    _ensure_dirs(result.output_dir)
    stem = result.source_path.stem
    return {
        "txt": _write_txt(result.output_dir, stem, result.segments),
        "srt": _write_srt(result.output_dir, stem, result.segments),
        "vtt": _write_vtt(result.output_dir, stem, result.segments),
        "alignment": _write_alignment(result.output_dir, stem, result.segments),
        "scene_list": _write_scene_list(result.output_dir, stem, result.scenes),
        "storyboard": _write_storyboard(result.output_dir, result),
    }
