from __future__ import annotations
import re
from narration_analysis.models import Scene, TranscriptSegment

_SENTENCE_END = re.compile(r'(?<=[.!?])\s+')

# Narrative mode tuning constants
_NARRATIVE_MIN_DUR      =  5.0   # don't flush a group shorter than this
_NARRATIVE_TARGET_DUR   = 10.0   # aim to flush at or after this duration
_NARRATIVE_MAX_DUR      = 15.0   # hard ceiling — flush before exceeding
_NARRATIVE_MIN_WORDS    =  8     # don't flush a group with fewer words (guards short rhetorical openers)
_NARRATIVE_TARGET_WORDS = 30     # aim to flush at or after this word count
_NARRATIVE_MAX_WORDS    = 50     # hard ceiling — flush before exceeding
_NARRATIVE_PARA_GAP     =  1.0   # gap (seconds) treated as a paragraph boundary


def _split_to_sentences(segments: list[TranscriptSegment]) -> list[tuple[float, float, str]]:
    """Split segments at sentence boundaries with proportional timestamps.

    Returns a flat list of (start, end, text) tuples.  No merging is applied;
    callers handle that themselves according to their mode.
    """
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
    return raw


def build_scenes(segments: list[TranscriptSegment]) -> list[Scene]:
    """Subtitle mode: one sentence per scene.

    Behaviour is unchanged from v1 — small fragments are merged with
    their predecessor to avoid single-word scenes.
    """
    if not segments:
        return []

    raw = _split_to_sentences(segments)

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


def build_scenes_narrative(segments: list[TranscriptSegment]) -> list[Scene]:
    """Narrative mode: merge sentences into visual story blocks.

    Targets 8–15 seconds and 20–50 words per scene, producing 30–50 scenes
    for a typical 7–10 minute narration instead of 150–250 subtitle lines.

    Flush rules (in priority order):
    1. Hard ceiling — if adding the next sentence would exceed MAX_DUR or
       MAX_WORDS, flush the current group first.
    2. Soft target — flush after adding a sentence when the group meets or
       exceeds TARGET_DUR or TARGET_WORDS, provided it also clears the
       MIN_DUR and MIN_WORDS floor (guards against flushing mid-rhetorical-run).
    3. Paragraph break — flush when the gap to the next sentence is ≥
       PARA_GAP and the group clears both MIN floors.
    """
    if not segments:
        return []

    raw = _split_to_sentences(segments)
    if not raw:
        return []

    groups: list[list[tuple[float, float, str]]] = []
    current: list[tuple[float, float, str]] = []
    cur_words = 0
    group_start = 0.0

    for i, (start, end, text) in enumerate(raw):
        words = len(text.split())

        # --- Rule 1: hard ceiling check before adding ---
        if current:
            if (end - group_start > _NARRATIVE_MAX_DUR) or \
               (cur_words + words > _NARRATIVE_MAX_WORDS):
                groups.append(current)
                current = []
                cur_words = 0

        if not current:
            group_start = start

        current.append((start, end, text))
        cur_words += words
        cur_dur = end - group_start

        # Gap to the next sentence (0 if this is the last)
        next_gap = raw[i + 1][0] - end if i + 1 < len(raw) else 0.0

        # --- Rule 2: soft target flush ---
        if (cur_dur >= _NARRATIVE_TARGET_DUR or cur_words >= _NARRATIVE_TARGET_WORDS) and \
                cur_dur >= _NARRATIVE_MIN_DUR and cur_words >= _NARRATIVE_MIN_WORDS:
            groups.append(current)
            current = []
            cur_words = 0
            continue

        # --- Rule 3: paragraph break flush ---
        if next_gap >= _NARRATIVE_PARA_GAP and \
                cur_dur >= _NARRATIVE_MIN_DUR and cur_words >= _NARRATIVE_MIN_WORDS:
            groups.append(current)
            current = []
            cur_words = 0

    if current:
        groups.append(current)

    return [
        Scene(
            scene_number=i + 1,
            start=group[0][0],
            end=group[-1][1],
            text=" ".join(t for _, _, t in group),
        )
        for i, group in enumerate(groups)
    ]
