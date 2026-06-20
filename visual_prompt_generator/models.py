from __future__ import annotations
from dataclasses import dataclass


@dataclass
class SceneInfo:
    scene_number: int
    narration: str


@dataclass
class SceneContext:
    previous: SceneInfo | None
    current: SceneInfo
    next: SceneInfo | None


@dataclass
class PromptResult:
    scene_number: int
    visual_prompt: str
    camera: str
    mood: str


@dataclass
class GenerationJob:
    provider: str
    style: str
    context_window: int = 1
