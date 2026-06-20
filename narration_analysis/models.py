from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str


@dataclass
class Scene:
    scene_number: int
    start: float
    end: float
    text: str


@dataclass
class SceneEdit:
    """Working correction layer for a single scene. Never modifies the source Scene."""
    scene_number: int
    original_narration: str   # Whisper text — read-only reference
    narration: str            # working/corrected text; starts equal to original
    visual_prompt: str = ""
    status: str = "pending"
    edited: bool = False      # True when narration differs from original or visual_prompt is set


@dataclass
class AnalysisResult:
    source_path: Path
    project_name: str
    duration: float
    segments: list[TranscriptSegment]
    scenes: list[Scene]
    output_dir: Path
