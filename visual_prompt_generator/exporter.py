from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

from visual_prompt_generator.models import GenerationJob, PromptResult


def write_storyboard_prompted(
    output_dir: Path,
    corrected_data: dict,
    results: list[PromptResult],
    job: GenerationJob,
) -> Path:
    """Write storyboard_prompted.json alongside the existing storyboard files.

    Never overwrites storyboard.json or storyboard_corrected.json.
    Scenes without a matching PromptResult are written with generation_status='pending'.
    """
    path = output_dir / "storyboards" / "storyboard_prompted.json"
    path.parent.mkdir(parents=True, exist_ok=True)

    by_scene: dict[int, PromptResult] = {r.scene_number: r for r in results}

    scenes = []
    for sc in corrected_data.get("scenes", []):
        sn = int(sc["scene_number"])
        result = by_scene.get(sn)
        scenes.append({
            "scene_number": sn,
            "start": sc["start"],
            "end": sc["end"],
            "duration": sc.get("duration", round(sc["end"] - sc["start"], 3)),
            "narration": sc.get("narration", sc.get("text", "")),
            "visual_prompt": result.visual_prompt if result else "",
            "camera": result.camera if result else "",
            "mood": result.mood if result else "",
            "visual_type": "video",
            "generation_status": "generated" if result else "pending",
        })

    data = {
        "source": corrected_data.get("source", ""),
        "project_name": corrected_data.get("project_name", ""),
        "duration": corrected_data.get("duration", 0.0),
        "style": job.style,
        "provider": job.provider,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scenes": scenes,
    }

    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
