from __future__ import annotations
import re
from narration_analysis.models import Scene, TranscriptSegment

_SENTENCE_END = re.compile(r'(?<=[.!?])\s+')


def build_scenes(segments: list[TranscriptSegment]) -> list[Scene]:
    if not segments:
        return []

    # Split each segment's text at sentence boundaries,
    # distributing timestamps proportionally by character count.
    raw: list[tuple[float, float, str]] = []
    for seg in segments:
        text = seg.text.strip()
        parts = _SENTENCE_END.split(text)
        parts = [p for p in parts if p]
        if len(parts) == 1:
            raw.append((seg.start, seg.end, parts[0]))
        else:
            total_chars = sum(len(p) for p in parts)
            duration = seg.end - seg.start
            cursor = seg.start
            for part in parts:
                frac = len(part) / total_chars if total_chars > 0 else 1.0 / len(parts)
                part_end = cursor + frac * duration
                raw.append((cursor, part_end, part))
                cursor = part_end
            # Snap last end to segment end to avoid float drift
            if raw:
                s, _, t = raw[-1]
                raw[-1] = (s, seg.end, t)

    # Merge fragments shorter than 2 words with the previous entry,
    # but only if the previous entry also has <= 2 words.
    merged: list[tuple[float, float, str]] = []
    for start, end, text in raw:
        if len(text.split()) < 2 and merged and len(merged[-1][-1].split()) <= 2:
            ps, _, pt = merged[-1]
            merged[-1] = (ps, end, pt + " " + text)
        else:
            merged.append((start, end, text))

    return [
        Scene(scene_number=i + 1, start=s, end=e, text=t)
        for i, (s, e, t) in enumerate(merged)
    ]
