from __future__ import annotations
from visual_prompt_generator.models import GenerationJob, PromptResult, SceneContext, SceneInfo
from visual_prompt_generator.providers import PromptProvider, PromptRequest
from visual_prompt_generator.styles import get_style


class PromptEngine:
    def __init__(self, provider: PromptProvider, job: GenerationJob) -> None:
        self._provider = provider
        self._job = job
        self._style = get_style(job.style)

    def generate_one(self, scenes: list[SceneInfo], index: int) -> PromptResult:
        """Generate a prompt for scenes[index] with optional neighbouring context."""
        current = scenes[index]

        if self._job.context_window > 0:
            previous = scenes[index - 1] if index > 0 else None
            next_ = scenes[index + 1] if index < len(scenes) - 1 else None
            context: SceneContext | None = SceneContext(
                previous=previous, current=current, next=next_
            )
        else:
            context = None

        request = PromptRequest(
            scene_number=current.scene_number,
            narration=current.narration,
            style_name=self._job.style,
            system_prompt=self._style.system_prompt,
            context=context,
        )
        response = self._provider.generate(request)
        return PromptResult(
            scene_number=current.scene_number,
            visual_prompt=response.visual_prompt,
            camera=response.camera,
            mood=response.mood,
        )

    def generate_all(self, scenes: list[SceneInfo]) -> list[PromptResult]:
        """Generate prompts for every scene in order."""
        return [self.generate_one(scenes, i) for i in range(len(scenes))]
