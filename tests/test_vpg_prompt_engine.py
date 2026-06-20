from visual_prompt_generator.models import GenerationJob, PromptResult, SceneInfo
from visual_prompt_generator.providers import MockProvider, PromptProvider, PromptRequest, ProviderResponse
from visual_prompt_generator.prompt_engine import PromptEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _engine(context_window: int = 1, style: str = "documentary") -> PromptEngine:
    return PromptEngine(
        provider=MockProvider(),
        job=GenerationJob(provider="mock", style=style, context_window=context_window),
    )


def _scenes(*narrations: str) -> list[SceneInfo]:
    return [SceneInfo(scene_number=i + 1, narration=n) for i, n in enumerate(narrations)]


class _CapturingProvider(PromptProvider):
    """Records every PromptRequest it receives; returns a fixed ProviderResponse."""

    def __init__(self) -> None:
        self.requests: list[PromptRequest] = []

    @property
    def name(self) -> str:
        return "capturing"

    @property
    def is_available(self) -> bool:
        return True

    def generate(self, request: PromptRequest) -> ProviderResponse:
        self.requests.append(request)
        return ProviderResponse(
            visual_prompt=f"prompt:{request.narration}",
            camera="static",
            mood="neutral",
            raw="",
        )


# ---------------------------------------------------------------------------
# generate_one
# ---------------------------------------------------------------------------

def test_generate_one_returns_prompt_result():
    result = _engine().generate_one(_scenes("A river flows."), 0)
    assert isinstance(result, PromptResult)


def test_generate_one_correct_scene_number():
    scenes = _scenes("First.", "Second.", "Third.")
    result = _engine().generate_one(scenes, 1)
    assert result.scene_number == 2


def test_generate_one_prompt_contains_narration():
    scenes = _scenes("Mountains at dawn.")
    result = _engine().generate_one(scenes, 0)
    assert "Mountains at dawn." in result.visual_prompt


def test_generate_one_has_camera():
    result = _engine().generate_one(_scenes("Scene."), 0)
    assert result.camera


def test_generate_one_has_mood():
    result = _engine().generate_one(_scenes("Scene."), 0)
    assert result.mood


# ---------------------------------------------------------------------------
# generate_all
# ---------------------------------------------------------------------------

def test_generate_all_returns_all_scenes():
    results = _engine().generate_all(_scenes("A.", "B.", "C.", "D."))
    assert len(results) == 4


def test_generate_all_scene_numbers_match():
    results = _engine().generate_all(_scenes("A.", "B.", "C."))
    assert [r.scene_number for r in results] == [1, 2, 3]


def test_generate_all_empty_list():
    assert _engine().generate_all([]) == []


def test_generate_all_single_scene():
    results = _engine().generate_all(_scenes("Only."))
    assert len(results) == 1
    assert results[0].scene_number == 1


# ---------------------------------------------------------------------------
# context_window = 0
# ---------------------------------------------------------------------------

def test_context_window_zero_passes_no_context():
    cap = _CapturingProvider()
    engine = PromptEngine(
        provider=cap,
        job=GenerationJob(provider="capturing", style="documentary", context_window=0),
    )
    engine.generate_all(_scenes("A.", "B.", "C."))
    for req in cap.requests:
        assert req.context is None


# ---------------------------------------------------------------------------
# context_window = 1
# ---------------------------------------------------------------------------

def test_context_window_one_passes_context():
    cap = _CapturingProvider()
    engine = PromptEngine(
        provider=cap,
        job=GenerationJob(provider="capturing", style="documentary", context_window=1),
    )
    engine.generate_all(_scenes("A.", "B.", "C."))
    for req in cap.requests:
        assert req.context is not None


def test_first_scene_has_no_previous():
    cap = _CapturingProvider()
    engine = PromptEngine(
        provider=cap,
        job=GenerationJob(provider="capturing", style="documentary", context_window=1),
    )
    engine.generate_all(_scenes("First.", "Second.", "Third."))
    assert cap.requests[0].context.previous is None


def test_last_scene_has_no_next():
    cap = _CapturingProvider()
    engine = PromptEngine(
        provider=cap,
        job=GenerationJob(provider="capturing", style="documentary", context_window=1),
    )
    engine.generate_all(_scenes("First.", "Second.", "Third."))
    assert cap.requests[-1].context.next is None


def test_middle_scene_has_both_neighbours():
    cap = _CapturingProvider()
    engine = PromptEngine(
        provider=cap,
        job=GenerationJob(provider="capturing", style="documentary", context_window=1),
    )
    engine.generate_all(_scenes("A.", "B.", "C."))
    middle = cap.requests[1]
    assert middle.context.previous is not None
    assert middle.context.next is not None


def test_single_scene_has_no_neighbours():
    cap = _CapturingProvider()
    engine = PromptEngine(
        provider=cap,
        job=GenerationJob(provider="capturing", style="documentary", context_window=1),
    )
    engine.generate_all(_scenes("Only."))
    req = cap.requests[0]
    assert req.context.previous is None
    assert req.context.next is None


def test_context_carries_correct_narrations():
    cap = _CapturingProvider()
    engine = PromptEngine(
        provider=cap,
        job=GenerationJob(provider="capturing", style="documentary", context_window=1),
    )
    engine.generate_all(_scenes("First.", "Second.", "Third."))
    middle = cap.requests[1]
    assert middle.context.previous.narration == "First."
    assert middle.context.current.narration == "Second."
    assert middle.context.next.narration == "Third."


def test_context_carries_correct_scene_numbers():
    cap = _CapturingProvider()
    engine = PromptEngine(
        provider=cap,
        job=GenerationJob(provider="capturing", style="documentary", context_window=1),
    )
    engine.generate_all(_scenes("A.", "B.", "C."))
    middle = cap.requests[1]
    assert middle.context.previous.scene_number == 1
    assert middle.context.current.scene_number == 2
    assert middle.context.next.scene_number == 3


def test_style_system_prompt_passed_to_provider():
    cap = _CapturingProvider()
    engine = PromptEngine(
        provider=cap,
        job=GenerationJob(provider="capturing", style="cinematic", context_window=0),
    )
    engine.generate_all(_scenes("Scene."))
    assert cap.requests[0].system_prompt  # non-empty
    assert cap.requests[0].style_name == "cinematic"
