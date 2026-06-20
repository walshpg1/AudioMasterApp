from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass

from visual_prompt_generator.models import SceneContext


@dataclass
class PromptRequest:
    scene_number: int
    narration: str
    style_name: str
    system_prompt: str
    context: SceneContext | None


@dataclass
class ProviderResponse:
    visual_prompt: str
    camera: str
    mood: str
    raw: str


class PromptProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def generate(self, request: PromptRequest) -> ProviderResponse: ...


class MockProvider(PromptProvider):
    """Deterministic provider for testing. No network, no API key required."""

    @property
    def name(self) -> str:
        return "mock"

    @property
    def is_available(self) -> bool:
        return True

    def generate(self, request: PromptRequest) -> ProviderResponse:
        style_label = request.style_name.replace("_", " ").capitalize()
        visual_prompt = f"{style_label} scene illustrating: {request.narration}"
        return ProviderResponse(
            visual_prompt=visual_prompt,
            camera="Static medium shot",
            mood="Reflective",
            raw=visual_prompt,
        )
