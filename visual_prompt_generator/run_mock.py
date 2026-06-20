"""End-to-end harness: storyboard_corrected.json → MockProvider → storyboard_prompted.json.

Usage:
    python -m visual_prompt_generator.run_mock <path/to/storyboard_corrected.json>
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

from visual_prompt_generator.exporter import write_storyboard_prompted
from visual_prompt_generator.models import GenerationJob, SceneInfo
from visual_prompt_generator.providers import MockProvider
from visual_prompt_generator.prompt_engine import PromptEngine


def load_corrected_storyboard(path: Path) -> dict:
    """Load storyboard_corrected.json from disk. Raises FileNotFoundError or JSONDecodeError."""
    return json.loads(path.read_text(encoding="utf-8"))


def _scenes_from_data(data: dict) -> list[SceneInfo]:
    return [
        SceneInfo(
            scene_number=int(sc["scene_number"]),
            narration=sc.get("narration", sc.get("text", "")),
        )
        for sc in data.get("scenes", [])
    ]


def run_pipeline(
    corrected_path: Path,
    style: str = "documentary",
    context_window: int = 1,
) -> dict:
    """Run the full mock pipeline and return a summary dict.

    Output is written to storyboards/storyboard_prompted.json beside the input.
    storyboard_corrected.json is never modified.

    Returns:
        dict with keys: project_name, source, scene_count, n_generated, output_path
    """
    corrected_path = Path(corrected_path)
    data = load_corrected_storyboard(corrected_path)

    scenes = _scenes_from_data(data)
    job = GenerationJob(provider="mock", style=style, context_window=context_window)
    engine = PromptEngine(MockProvider(), job)
    results = engine.generate_all(scenes)

    # storyboard_corrected.json lives at <output_dir>/storyboards/storyboard_corrected.json
    output_dir = corrected_path.parent.parent
    output_path = write_storyboard_prompted(output_dir, data, results, job)

    return {
        "project_name": data.get("project_name", ""),
        "source": data.get("source", ""),
        "scene_count": len(scenes),
        "n_generated": len(results),
        "output_path": output_path,
    }


def print_summary(summary: dict) -> None:
    print(f"Project:    {summary['project_name']}")
    print(f"Source:     {summary['source']}")
    print(f"Scenes:     {summary['scene_count']}")
    print(f"Generated:  {summary['n_generated']}")
    print(f"Output:     {summary['output_path']}")


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print(
            "Usage: python -m visual_prompt_generator.run_mock "
            "<path/to/storyboard_corrected.json>",
            file=sys.stderr,
        )
        return 1

    corrected_path = Path(args[0])
    try:
        summary = run_pipeline(corrected_path)
        print_summary(summary)
        return 0
    except FileNotFoundError as exc:
        print(f"Error: file not found — {exc}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"Error: invalid JSON — {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
