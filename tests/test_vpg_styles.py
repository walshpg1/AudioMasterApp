import pytest
from visual_prompt_generator.styles import STYLES, PromptStyle, get_style, style_names

_EXPECTED = [
    "documentary",
    "cinematic",
    "motivational",
    "corporate",
    "historical",
    "realistic",
    "ai_art",
]


def test_all_expected_styles_registered():
    for name in _EXPECTED:
        assert name in STYLES, f"{name!r} not in STYLES"


def test_style_count():
    assert len(STYLES) == len(_EXPECTED)


def test_get_style_returns_prompt_style():
    assert isinstance(get_style("documentary"), PromptStyle)


def test_get_style_name_matches_key():
    for name in _EXPECTED:
        assert get_style(name).name == name


def test_get_style_unknown_raises_value_error():
    with pytest.raises(ValueError, match="Unknown style"):
        get_style("nonexistent")


def test_style_names_contains_all():
    assert sorted(style_names()) == sorted(_EXPECTED)


def test_style_names_returns_list():
    assert isinstance(style_names(), list)


def test_prompt_style_is_frozen():
    style = get_style("cinematic")
    with pytest.raises(AttributeError):
        style.name = "changed"  # type: ignore[misc]


def test_each_style_has_nonempty_system_prompt():
    for name in _EXPECTED:
        prompt = get_style(name).system_prompt
        assert len(prompt.strip()) > 20, f"{name!r} system_prompt too short"


def test_each_style_has_nonempty_display_name():
    for name in _EXPECTED:
        assert get_style(name).display_name.strip(), f"{name!r} display_name is empty"


def test_display_names_are_distinct():
    display_names = [get_style(n).display_name for n in _EXPECTED]
    assert len(display_names) == len(set(display_names))
