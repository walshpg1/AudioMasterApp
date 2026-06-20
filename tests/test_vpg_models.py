from visual_prompt_generator.models import GenerationJob, PromptResult, SceneContext, SceneInfo


def test_scene_info_fields():
    info = SceneInfo(scene_number=3, narration="A quiet forest.")
    assert info.scene_number == 3
    assert info.narration == "A quiet forest."


def test_scene_context_all_fields():
    prev = SceneInfo(1, "Before.")
    curr = SceneInfo(2, "During.")
    nxt = SceneInfo(3, "After.")
    ctx = SceneContext(previous=prev, current=curr, next=nxt)
    assert ctx.previous is prev
    assert ctx.current is curr
    assert ctx.next is nxt


def test_scene_context_none_neighbours():
    curr = SceneInfo(1, "Only scene.")
    ctx = SceneContext(previous=None, current=curr, next=None)
    assert ctx.previous is None
    assert ctx.next is None


def test_scene_context_none_previous_only():
    curr = SceneInfo(1, "First.")
    nxt = SceneInfo(2, "Second.")
    ctx = SceneContext(previous=None, current=curr, next=nxt)
    assert ctx.previous is None
    assert ctx.next is nxt


def test_scene_context_none_next_only():
    prev = SceneInfo(1, "First.")
    curr = SceneInfo(2, "Last.")
    ctx = SceneContext(previous=prev, current=curr, next=None)
    assert ctx.previous is prev
    assert ctx.next is None


def test_prompt_result_fields():
    r = PromptResult(
        scene_number=5,
        visual_prompt="Wide shot of mountains.",
        camera="Locked-off wide",
        mood="Epic",
    )
    assert r.scene_number == 5
    assert r.visual_prompt == "Wide shot of mountains."
    assert r.camera == "Locked-off wide"
    assert r.mood == "Epic"


def test_generation_job_default_context_window():
    job = GenerationJob(provider="mock", style="documentary")
    assert job.context_window == 1


def test_generation_job_custom_context_window():
    job = GenerationJob(provider="mock", style="cinematic", context_window=0)
    assert job.context_window == 0


def test_generation_job_fields():
    job = GenerationJob(provider="claude", style="historical", context_window=2)
    assert job.provider == "claude"
    assert job.style == "historical"
    assert job.context_window == 2
