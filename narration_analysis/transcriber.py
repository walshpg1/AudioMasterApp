from __future__ import annotations
import threading
from pathlib import Path
from typing import Callable

from faster_whisper import WhisperModel

from narration_analysis.models import TranscriptSegment

_CACHED_MODEL: tuple[str, str, WhisperModel] | None = None


class TranscriptionCancelled(Exception):
    pass


def _get_device() -> str:
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"


def _get_model(model_size: str) -> WhisperModel:
    global _CACHED_MODEL
    device = _get_device()
    if _CACHED_MODEL and _CACHED_MODEL[0] == model_size and _CACHED_MODEL[1] == device:
        return _CACHED_MODEL[2]
    compute_type = "float16" if device == "cuda" else "int8"
    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    _CACHED_MODEL = (model_size, device, model)
    return model


def transcribe(
    audio_path: Path,
    model_size: str,
    progress_cb: Callable[[float], None],
    cancel_event: threading.Event,
) -> tuple[list[TranscriptSegment], float]:
    """Transcribe audio file. Returns (segments, duration_seconds)."""
    model = _get_model(model_size)
    segments_iter, info = model.transcribe(str(audio_path), beam_size=5)
    duration: float = info.duration

    result: list[TranscriptSegment] = []
    for segment in segments_iter:
        if cancel_event.is_set():
            raise TranscriptionCancelled()
        result.append(TranscriptSegment(
            start=segment.start,
            end=segment.end,
            text=segment.text.strip(),
        ))
        if duration > 0:
            progress_cb(min(segment.end / duration, 1.0))

    return result, duration
