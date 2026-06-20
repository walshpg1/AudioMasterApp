from visual_prompt_generator.models import SceneContext, SceneInfo
from visual_prompt_generator.providers import MockProvider, PromptRequest


def _req(
    narration: str = "Test narration.",
    style_name: str = "documentary",
    context: SceneContext | None = None,
) -> PromptRequest:
    return PromptRequest(
        scene_number=1,
        narration=narration,
        style_name=style_name,
        system_prompt="A placeholder system prompt.",
        context=context,
    )


def test_mock_provider_name():
    assert MockProvider().name == "mock"


def test_mock_provider_is_available():
    assert MockProvider().is_available is True


def test_mock_provider_returns_visual_prompt():
    resp = MockProvider().generate(_req())
    assert resp.visual_prompt


def test_mock_provider_visual_prompt_contains_narration():
    resp = MockProvider().generate(_req(narration="The fear was holding me back."))
    assert "The fear was holding me back." in resp.visual_prompt


def test_mock_provider_returns_camera():
    resp = MockProvider().generate(_req())
    assert resp.camera


def test_mock_provider_returns_mood():
    resp = MockProvider().generate(_req())
    assert resp.mood


def test_mock_provider_returns_raw():
    resp = MockProvider().generate(_req())
    assert resp.raw is not None


def test_mock_provider_is_deterministic():
    p = MockProvider()
    req = _req(narration="A river flows.")
    r1 = p.generate(req)
    r2 = p.generate(req)
    assert r1.visual_prompt == r2.visual_prompt
    assert r1.camera == r2.camera
    assert r1.mood == r2.mood


def test_mock_provider_visual_prompt_reflects_style():
    resp = MockProvider().generate(_req(style_name="cinematic"))
    assert "cinematic" in resp.visual_prompt.lower()


def test_mock_provider_documentary_style_label():
    resp = MockProvider().generate(_req(style_name="documentary"))
    assert "documentary" in resp.visual_prompt.lower()


def test_mock_provider_ai_art_style_label():
    resp = MockProvider().generate(_req(style_name="ai_art"))
    assert "ai art" in resp.visual_prompt.lower()


def test_mock_provider_accepts_none_context():
    resp = MockProvider().generate(_req(context=None))
    assert resp.visual_prompt


def test_mock_provider_accepts_full_context():
    ctx = SceneContext(
        previous=SceneInfo(1, "Before."),
        current=SceneInfo(2, "During."),
        next=SceneInfo(3, "After."),
    )
    resp = MockProvider().generate(_req(context=ctx))
    assert resp.visual_prompt
