from __future__ import annotations
from dataclasses import dataclass
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
class AnalysisResult:
    source_path: Path
    project_name: str
    duration: float
    segments: list[TranscriptSegment]
    scenes: list[Scene]
    output_dir: Path
