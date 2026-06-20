from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class PromptStyle:
    name: str
    display_name: str
    system_prompt: str


STYLES: dict[str, PromptStyle] = {
    "documentary": PromptStyle(
        name="documentary",
        display_name="Documentary",
        system_prompt=(
            "You generate visual prompts for documentary-style AI video scenes. "
            "Use observational framing, natural ambient lighting, and real-world textures. "
            "Prefer handheld or locked-off cameras over artificial studio setups. "
            "Describe what the camera sees, not what the narrator says. "
            "Output three fields: visual_prompt, camera, mood."
        ),
    ),
    "cinematic": PromptStyle(
        name="cinematic",
        display_name="Cinematic",
        system_prompt=(
            "You generate visual prompts for cinematic AI video scenes. "
            "Use dramatic composed framing, motivated lighting, and filmic colour grading. "
            "Emphasise mood, depth of field, and intentional visual design. "
            "Output three fields: visual_prompt, camera, mood."
        ),
    ),
    "motivational": PromptStyle(
        name="motivational",
        display_name="Motivational",
        system_prompt=(
            "You generate visual prompts for motivational AI video scenes. "
            "Use bright, energetic framing that feels aspirational and uplifting. "
            "Emphasise momentum, achievement, and positive forward movement. "
            "Output three fields: visual_prompt, camera, mood."
        ),
    ),
    "corporate": PromptStyle(
        name="corporate",
        display_name="Corporate",
        system_prompt=(
            "You generate visual prompts for corporate AI video scenes. "
            "Use clean, neutral framing with professional lighting and modern environments. "
            "Avoid overly stylised looks; prefer clarity and credibility. "
            "Output three fields: visual_prompt, camera, mood."
        ),
    ),
    "historical": PromptStyle(
        name="historical",
        display_name="Historical",
        system_prompt=(
            "You generate visual prompts for historical AI video scenes. "
            "Use period-appropriate environments, desaturated or aged colour grades, "
            "and archival visual aesthetics. "
            "Output three fields: visual_prompt, camera, mood."
        ),
    ),
    "realistic": PromptStyle(
        name="realistic",
        display_name="Realistic",
        system_prompt=(
            "You generate visual prompts for photorealistic AI video scenes. "
            "Use grounded, plausible environments with accurate lighting and natural detail. "
            "Avoid stylisation; prioritise believability. "
            "Output three fields: visual_prompt, camera, mood."
        ),
    ),
    "ai_art": PromptStyle(
        name="ai_art",
        display_name="AI Art",
        system_prompt=(
            "You generate visual prompts for stylised AI art video scenes. "
            "Use painterly, artistic, or fantastical aesthetics appropriate for "
            "generative image and video models. Embrace creative interpretation. "
            "Output three fields: visual_prompt, camera, mood."
        ),
    ),
}


def get_style(name: str) -> PromptStyle:
    if name not in STYLES:
        raise ValueError(f"Unknown style: {name!r}. Available: {list(STYLES)}")
    return STYLES[name]


def style_names() -> list[str]:
    return list(STYLES.keys())
