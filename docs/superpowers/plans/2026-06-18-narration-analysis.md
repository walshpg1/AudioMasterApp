# Narration Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Narration Analysis" tab to AudioMasterApp that transcribes voiceover audio via faster-whisper and exports transcripts, subtitles, scene lists, and a storyboard JSON for ComfyUI/LTX workflows.

**Architecture:** A `narration_analysis/` package with five focused modules (models, transcriber, scene_builder, exporter, player) plus a UI class, wired into `app.py` with a single import and tab registration. All output is isolated to `D:\AIStudio\Outputs\narration_analysis\{project_name}\`.

**Tech Stack:** Python 3.14, CustomTkinter, faster-whisper 1.2.1, pygame 2.x (new dep), soundfile (existing)

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `narration_analysis/__init__.py` | Package marker |
| Create | `narration_analysis/models.py` | TranscriptSegment, Scene, AnalysisResult dataclasses |
| Create | `narration_analysis/transcriber.py` | faster-whisper wrapper, progress callbacks, cancel support |
| Create | `narration_analysis/scene_builder.py` | Sentence-level splitting of segments into scenes |
| Create | `narration_analysis/exporter.py` | Writes TXT/SRT/VTT/JSON/storyboard to per-project output dirs |
| Create | `narration_analysis/player.py` | pygame.mixer wrapper for play/pause/seek |
| Create | `narration_analysis/ui.py` | NarrationAnalysisTab class |
| Create | `tests/test_narration_models.py` | Model dataclass tests |
| Create | `tests/test_narration_transcriber.py` | Transcriber tests (mocked faster-whisper) |
| Create | `tests/test_narration_scene_builder.py` | Scene splitting tests |
| Create | `tests/test_narration_exporter.py` | File output tests (tmp_path) |
| Create | `tests/test_narration_player.py` | Player tests (mocked/unavailable path) |
| Modify | `requirements.txt` | Add pygame>=2.5.0 |
| Modify | `app.py` lines 29–33, 146–153, 724–729 | Import, tab registration, cleanup |

**Isolation guarantee:** No other file in this list touches existing path constants, mux workflow, staging folders, or output governance.

---

## Task 1: Install pygame and create package skeleton

**Files:**
- Modify: `requirements.txt`
- Create: `narration_analysis/__init__.py`

- [ ] **Step 1: Install pygame**

```bash
pip install "pygame>=2.5.0"
```

Expected: `Successfully installed pygame-2.x.x`

- [ ] **Step 2: Add to requirements.txt**

Open `requirements.txt` and add after the last line:

```
pygame>=2.5.0
```

Full file should now be:
```
customtkinter>=5.2.0
soundfile>=0.12.1
numpy>=1.26.0
pyloudnorm>=0.1.1
matplotlib>=3.8.0
pytest>=8.0.0
Pillow>=10.0.0
pygame>=2.5.0
```

- [ ] **Step 3: Create package directory and `__init__.py`**

Create `narration_analysis/__init__.py` with:

```python
```

(Empty file — just marks the directory as a Python package.)

- [ ] **Step 4: Verify importable**

```bash
cd D:\AIStudio\Apps\AudioMasterApp
python -c "import narration_analysis; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add requirements.txt narration_analysis/__init__.py
git commit -m "feat(narration): create package skeleton, add pygame dependency"
```

---

## Task 2: Models

**Files:**
- Create: `narration_analysis/models.py`
- Create: `tests/test_narration_models.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_narration_models.py`:

```python
from pathlib import Path
import pytest
from narration_analysis.models import TranscriptSegment, Scene, AnalysisResult


def test_transcript_segment():
    seg = TranscriptSegment(start=1.0, end=5.5, text="Hello world.")
    assert seg.start == 1.0
    assert seg.end == 5.5
    assert seg.text == "Hello world."


def test_scene():
    sc = Scene(scene_number=3, start=10.0, end=20.0, text="A new beginning.")
    assert sc.scene_number == 3
    assert sc.start == 10.0
    assert sc.end == 20.0
    assert sc.text == "A new beginning."


def test_analysis_result_fields():
    segs = [TranscriptSegment(0.0, 5.0, "Hello.")]
    scenes = [Scene(1, 0.0, 5.0, "Hello.")]
    result = AnalysisResult(
        source_path=Path("voiceover.mp3"),
        project_name="My_Project",
        duration=5.0,
        segments=segs,
        scenes=scenes,
        output_dir=Path(r"D:\AIStudio\Outputs\narration_analysis\My_Project"),
    )
    assert result.project_name == "My_Project"
    assert result.duration == 5.0
    assert len(result.segments) == 1
    assert len(result.scenes) == 1
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd D:\AIStudio\Apps\AudioMasterApp
python -m pytest tests/test_narration_models.py -v
```

Expected: `ImportError: cannot import name 'TranscriptSegment'`

- [ ] **Step 3: Implement `narration_analysis/models.py`**

```python
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str


@dataclass
class Scene:
    scene_number: int
    start: float
    end: float
    text: str


@dataclass
class AnalysisResult:
    source_path: Path
    project_name: str
    duration: float
    segments: list[TranscriptSegment]
    scenes: list[Scene]
    output_dir: Path
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
python -m pytest tests/test_narration_models.py -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add narration_analysis/models.py tests/test_narration_models.py
git commit -m "feat(narration): add models (TranscriptSegment, Scene, AnalysisResult)"
```

---

## Task 3: Transcriber

**Files:**
- Create: `narration_analysis/transcriber.py`
- Create: `tests/test_narration_transcriber.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_narration_transcriber.py`:

```python
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import narration_analysis.transcriber as _t
from narration_analysis.transcriber import transcribe, TranscriptionCancelled


@pytest.fixture(autouse=True)
def reset_model_cache():
    _t._CACHED_MODEL = None
    yield
    _t._CACHED_MODEL = None


def _fake_seg(start: float, end: float, text: str) -> MagicMock:
    seg = MagicMock()
    seg.start = start
    seg.end = end
    seg.text = text
    return seg


def _mock_whisper(seg_data: list[tuple], duration: float) -> MagicMock:
    segs = [_fake_seg(*d) for d in seg_data]
    info = MagicMock()
    info.duration = duration
    model = MagicMock()
    model.transcribe.return_value = (iter(segs), info)
    return model


def test_transcribe_returns_segments():
    mock = _mock_whisper([(0.0, 5.0, "  Hello world  ")], 5.0)
    with patch("narration_analysis.transcriber.WhisperModel", return_value=mock):
        segs, duration = transcribe(Path("test.wav"), "tiny", lambda f: None, threading.Event())
    assert len(segs) == 1
    assert segs[0].text == "Hello world"
    assert segs[0].start == 0.0
    assert segs[0].end == 5.0
    assert duration == 5.0


def test_transcribe_strips_whitespace():
    mock = _mock_whisper([(0.0, 3.0, "\n  Stripped text.\n")], 3.0)
    with patch("narration_analysis.transcriber.WhisperModel", return_value=mock):
        segs, _ = transcribe(Path("test.wav"), "tiny", lambda f: None, threading.Event())
    assert segs[0].text == "Stripped text."


def test_transcribe_cancelled_before_first_segment():
    mock = _mock_whisper([(0.0, 5.0, "Hello")], 5.0)
    cancel = threading.Event()
    cancel.set()
    with patch("narration_analysis.transcriber.WhisperModel", return_value=mock):
        with pytest.raises(TranscriptionCancelled):
            transcribe(Path("test.wav"), "tiny", lambda f: None, cancel)


def test_progress_callback_called_per_segment():
    mock = _mock_whisper(
        [(0.0, 5.0, "First."), (5.0, 10.0, "Second.")],
        10.0,
    )
    progress: list[float] = []
    with patch("narration_analysis.transcriber.WhisperModel", return_value=mock):
        transcribe(Path("test.wav"), "tiny", progress.append, threading.Event())
    assert len(progress) == 2
    assert progress[0] == pytest.approx(0.5)
    assert progress[1] == pytest.approx(1.0)


def test_model_cached_between_calls():
    mock = _mock_whisper([(0.0, 5.0, "Hello")], 5.0)
    with patch("narration_analysis.transcriber.WhisperModel", return_value=mock) as MockCls:
        transcribe(Path("test.wav"), "tiny", lambda f: None, threading.Event())
        _t._CACHED_MODEL[2].transcribe.return_value = (iter([_fake_seg(0.0, 5.0, "World")]), MagicMock(duration=5.0))
        transcribe(Path("test.wav"), "tiny", lambda f: None, threading.Event())
    assert MockCls.call_count == 1  # model constructed once, reused second call
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/test_narration_transcriber.py -v
```

Expected: `ImportError: cannot import name 'transcribe'`

- [ ] **Step 3: Implement `narration_analysis/transcriber.py`**

```python
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
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
python -m pytest tests/test_narration_transcriber.py -v
```

Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add narration_analysis/transcriber.py tests/test_narration_transcriber.py
git commit -m "feat(narration): add transcriber (faster-whisper wrapper, cancel, progress)"
```

---

## Task 4: Scene Builder

**Files:**
- Create: `narration_analysis/scene_builder.py`
- Create: `tests/test_narration_scene_builder.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_narration_scene_builder.py`:

```python
import pytest
from narration_analysis.models import TranscriptSegment
from narration_analysis.scene_builder import build_scenes


def test_empty_segments():
    assert build_scenes([]) == []


def test_single_segment_no_split():
    segs = [TranscriptSegment(0.0, 5.0, "Hello world.")]
    scenes = build_scenes(segs)
    assert len(scenes) == 1
    assert scenes[0].scene_number == 1
    assert scenes[0].start == 0.0
    assert scenes[0].end == 5.0
    assert scenes[0].text == "Hello world."


def test_two_sentences_in_one_segment():
    segs = [TranscriptSegment(0.0, 10.0, "Hello world. Goodbye world.")]
    scenes = build_scenes(segs)
    assert len(scenes) == 2
    assert scenes[0].text == "Hello world."
    assert scenes[1].text == "Goodbye world."


def test_short_fragment_merged_with_previous():
    # "Yes." is one word — should merge with "Hello world."
    segs = [TranscriptSegment(0.0, 10.0, "Hello world. Yes. That is all.")]
    scenes = build_scenes(segs)
    assert len(scenes) == 2
    assert "Yes." in scenes[0].text
    assert scenes[1].text == "That is all."


def test_scene_numbers_are_sequential():
    segs = [
        TranscriptSegment(0.0, 5.0, "First sentence."),
        TranscriptSegment(5.0, 10.0, "Second sentence."),
    ]
    scenes = build_scenes(segs)
    assert [sc.scene_number for sc in scenes] == [1, 2]


def test_exclamation_and_question_split():
    segs = [TranscriptSegment(0.0, 9.0, "Are you ready? Yes! Let us begin.")]
    scenes = build_scenes(segs)
    assert len(scenes) == 3
    assert scenes[0].text == "Are you ready?"
    assert scenes[1].text == "Yes!"
    assert scenes[2].text == "Let us begin."


def test_timestamps_ordered():
    segs = [TranscriptSegment(0.0, 10.0, "First part. Second part.")]
    scenes = build_scenes(segs)
    assert scenes[0].start < scenes[0].end
    assert scenes[1].start >= scenes[0].end
    assert scenes[1].end == pytest.approx(10.0)


def test_multiple_segments():
    segs = [
        TranscriptSegment(0.0, 5.0, "Segment one."),
        TranscriptSegment(5.0, 10.0, "Segment two."),
        TranscriptSegment(10.0, 15.0, "Segment three."),
    ]
    scenes = build_scenes(segs)
    assert len(scenes) == 3
    assert scenes[2].end == 15.0
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/test_narration_scene_builder.py -v
```

Expected: `ImportError: cannot import name 'build_scenes'`

- [ ] **Step 3: Implement `narration_analysis/scene_builder.py`**

```python
from __future__ import annotations
import re
from narration_analysis.models import Scene, TranscriptSegment

_SENTENCE_END = re.compile(r'(?<=[.!?])\s+')


def build_scenes(segments: list[TranscriptSegment]) -> list[Scene]:
    if not segments:
        return []

    # Step 1: split each segment's text at sentence boundaries,
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

    # Step 2: merge fragments shorter than 2 words with the previous entry.
    merged: list[tuple[float, float, str]] = []
    for start, end, text in raw:
        if len(text.split()) < 2 and merged:
            ps, _, pt = merged[-1]
            merged[-1] = (ps, end, pt + " " + text)
        else:
            merged.append((start, end, text))

    return [
        Scene(scene_number=i + 1, start=s, end=e, text=t)
        for i, (s, e, t) in enumerate(merged)
    ]
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
python -m pytest tests/test_narration_scene_builder.py -v
```

Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add narration_analysis/scene_builder.py tests/test_narration_scene_builder.py
git commit -m "feat(narration): add scene_builder (sentence-level splitting with merge)"
```

---

## Task 5: Exporter

**Files:**
- Create: `narration_analysis/exporter.py`
- Create: `tests/test_narration_exporter.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_narration_exporter.py`:

```python
import json
from pathlib import Path

import pytest

from narration_analysis.models import AnalysisResult, Scene, TranscriptSegment
from narration_analysis.exporter import (
    _ensure_dirs,
    _fmt_srt_time,
    _fmt_vtt_time,
    _fmt_tc,
    export_all,
)


@pytest.fixture
def segs():
    return [
        TranscriptSegment(start=0.0, end=5.0, text="Hello world."),
        TranscriptSegment(start=5.0, end=12.5, text="The day work let me go."),
    ]


@pytest.fixture
def scenes():
    return [
        Scene(scene_number=1, start=0.0, end=5.0, text="Hello world."),
        Scene(scene_number=2, start=5.0, end=12.5, text="The day work let me go."),
    ]


@pytest.fixture
def result(tmp_path, segs, scenes):
    return AnalysisResult(
        source_path=Path("voiceover.mp3"),
        project_name="My_Project",
        duration=12.5,
        segments=segs,
        scenes=scenes,
        output_dir=tmp_path,
    )


def test_fmt_srt_time():
    assert _fmt_srt_time(0.0) == "00:00:00,000"
    assert _fmt_srt_time(65.5) == "00:01:05,500"
    assert _fmt_srt_time(3661.123) == "01:01:01,123"


def test_fmt_vtt_time():
    assert _fmt_vtt_time(0.0) == "00:00.000"
    assert _fmt_vtt_time(65.5) == "01:05.500"


def test_fmt_tc():
    assert _fmt_tc(0.0) == "00:00"
    assert _fmt_tc(75.0) == "01:15"


def test_ensure_dirs_creates_subfolders(tmp_path):
    _ensure_dirs(tmp_path)
    for name in ("transcripts", "srt", "vtt", "json", "storyboards"):
        assert (tmp_path / name).is_dir()


def test_export_all_creates_all_files(result):
    exported = export_all(result)
    assert set(exported.keys()) == {"txt", "srt", "vtt", "alignment", "scene_list", "storyboard"}
    for path in exported.values():
        assert path.exists(), f"Missing: {path}"


def test_txt_content(result):
    exported = export_all(result)
    content = exported["txt"].read_text(encoding="utf-8")
    assert "[00:00] Hello world." in content
    assert "[00:05] The day work let me go." in content


def test_srt_content(result):
    exported = export_all(result)
    content = exported["srt"].read_text(encoding="utf-8")
    assert "1\n00:00:00,000 --> 00:00:05,000" in content
    assert "Hello world." in content
    assert "2\n00:00:05,000 --> 00:00:12,500" in content


def test_vtt_content(result):
    exported = export_all(result)
    content = exported["vtt"].read_text(encoding="utf-8")
    assert content.startswith("WEBVTT")
    assert "00:00.000 --> 00:05.000" in content


def test_alignment_json(result):
    exported = export_all(result)
    data = json.loads(exported["alignment"].read_text(encoding="utf-8"))
    assert data[0] == {"start": 0.0, "end": 5.0, "text": "Hello world."}
    assert data[1]["text"] == "The day work let me go."


def test_scene_list_json(result):
    exported = export_all(result)
    data = json.loads(exported["scene_list"].read_text(encoding="utf-8"))
    assert data[0]["scene"] == 1
    assert data[0]["start_tc"] == "00:00"
    assert data[0]["end_tc"] == "00:05"
    assert data[1]["start_tc"] == "00:05"


def test_storyboard_json(result):
    exported = export_all(result)
    data = json.loads(exported["storyboard"].read_text(encoding="utf-8"))
    assert data["project_name"] == "My_Project"
    assert data["source"] == "voiceover.mp3"
    assert data["duration"] == 12.5
    sc = data["scenes"][0]
    assert sc["scene_number"] == 1
    assert sc["narration"] == "Hello world."
    assert sc["start"] == 0.0
    assert sc["end"] == 5.0
    assert sc["duration"] == 5.0
    assert sc["visual_prompt"] == ""
    assert sc["status"] == "pending"


def test_storyboard_all_scenes_present(result):
    exported = export_all(result)
    data = json.loads(exported["storyboard"].read_text(encoding="utf-8"))
    assert len(data["scenes"]) == 2
    assert data["scenes"][1]["scene_number"] == 2
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/test_narration_exporter.py -v
```

Expected: `ImportError: cannot import name '_ensure_dirs'`

- [ ] **Step 3: Implement `narration_analysis/exporter.py`**

```python
from __future__ import annotations
import json
from pathlib import Path

from narration_analysis.models import AnalysisResult, Scene, TranscriptSegment

_OUTPUT_ROOT = Path(r"D:\AIStudio\Outputs\narration_analysis")
_SUBFOLDERS = ("transcripts", "srt", "vtt", "json", "storyboards")


def _ensure_dirs(output_dir: Path) -> None:
    for name in _SUBFOLDERS:
        (output_dir / name).mkdir(parents=True, exist_ok=True)


def _fmt_srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds % 1) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _fmt_vtt_time(seconds: float) -> str:
    m = int(seconds // 60)
    s = int(seconds % 60)
    ms = int(round((seconds % 1) * 1000))
    return f"{m:02d}:{s:02d}.{ms:03d}"


def _fmt_tc(seconds: float) -> str:
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"


def _write_txt(output_dir: Path, stem: str, segments: list[TranscriptSegment]) -> Path:
    path = output_dir / "transcripts" / f"{stem}.txt"
    lines = [f"[{_fmt_tc(seg.start)}] {seg.text}" for seg in segments]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _write_srt(output_dir: Path, stem: str, segments: list[TranscriptSegment]) -> Path:
    path = output_dir / "srt" / f"{stem}.srt"
    blocks = [
        f"{i}\n{_fmt_srt_time(seg.start)} --> {_fmt_srt_time(seg.end)}\n{seg.text}"
        for i, seg in enumerate(segments, 1)
    ]
    path.write_text("\n\n".join(blocks), encoding="utf-8")
    return path


def _write_vtt(output_dir: Path, stem: str, segments: list[TranscriptSegment]) -> Path:
    path = output_dir / "vtt" / f"{stem}.vtt"
    lines = ["WEBVTT", ""]
    for seg in segments:
        lines += [f"{_fmt_vtt_time(seg.start)} --> {_fmt_vtt_time(seg.end)}", seg.text, ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _write_alignment(output_dir: Path, stem: str, segments: list[TranscriptSegment]) -> Path:
    path = output_dir / "json" / f"{stem}_alignment.json"
    data = [{"start": seg.start, "end": seg.end, "text": seg.text} for seg in segments]
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _write_scene_list(output_dir: Path, stem: str, scenes: list[Scene]) -> Path:
    path = output_dir / "json" / f"{stem}_scene_list.json"
    data = [
        {
            "scene": sc.scene_number,
            "start": sc.start,
            "end": sc.end,
            "start_tc": _fmt_tc(sc.start),
            "end_tc": _fmt_tc(sc.end),
            "text": sc.text,
        }
        for sc in scenes
    ]
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _write_storyboard(output_dir: Path, result: AnalysisResult) -> Path:
    path = output_dir / "storyboards" / "storyboard.json"
    data = {
        "source": result.source_path.name,
        "project_name": result.project_name,
        "duration": result.duration,
        "scenes": [
            {
                "scene_number": sc.scene_number,
                "narration": sc.text,
                "start": sc.start,
                "end": sc.end,
                "duration": round(sc.end - sc.start, 3),
                "visual_prompt": "",
                "status": "pending",
            }
            for sc in result.scenes
        ],
    }
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def export_all(result: AnalysisResult) -> dict[str, Path]:
    _ensure_dirs(result.output_dir)
    stem = result.source_path.stem
    return {
        "txt": _write_txt(result.output_dir, stem, result.segments),
        "srt": _write_srt(result.output_dir, stem, result.segments),
        "vtt": _write_vtt(result.output_dir, stem, result.segments),
        "alignment": _write_alignment(result.output_dir, stem, result.segments),
        "scene_list": _write_scene_list(result.output_dir, stem, result.scenes),
        "storyboard": _write_storyboard(result.output_dir, result),
    }
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
python -m pytest tests/test_narration_exporter.py -v
```

Expected: `14 passed`

- [ ] **Step 5: Commit**

```bash
git add narration_analysis/exporter.py tests/test_narration_exporter.py
git commit -m "feat(narration): add exporter (TXT/SRT/VTT/JSON/storyboard with visual_prompt+status)"
```

---

## Task 6: Audio Player

**Files:**
- Create: `narration_analysis/player.py`
- Create: `tests/test_narration_player.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_narration_player.py`:

```python
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from narration_analysis.player import AudioPlayer


def _unavailable() -> AudioPlayer:
    """Construct a player that has no pygame available."""
    p = AudioPlayer.__new__(AudioPlayer)
    p._available = False
    p._path = None
    p._seek_offset = 0.0
    return p


def test_is_playing_false_when_unavailable():
    assert _unavailable().is_playing() is False


def test_get_pos_zero_when_unavailable():
    assert _unavailable().get_pos_seconds() == 0.0


def test_seek_does_not_raise_when_unavailable():
    _unavailable().seek(30.0)  # must not raise


def test_play_does_not_raise_when_unavailable():
    _unavailable().play()


def test_pause_does_not_raise_when_unavailable():
    _unavailable().pause()


def test_stop_does_not_raise_when_unavailable():
    _unavailable().stop()


def test_cleanup_does_not_raise_when_unavailable():
    _unavailable().cleanup()


def test_load_does_not_set_path_when_unavailable():
    p = _unavailable()
    p.load(Path("test.mp3"))
    assert p._path is None


def test_seek_offset_set_on_seek():
    mock_pygame = MagicMock()
    mock_pygame.mixer.music.get_busy.return_value = True

    p = AudioPlayer.__new__(AudioPlayer)
    p._available = True
    p._path = Path("test.mp3")
    p._seek_offset = 0.0

    with patch.dict("sys.modules", {"pygame": mock_pygame}):
        p.seek(30.0)

    assert p._seek_offset == 30.0


def test_get_pos_adds_seek_offset():
    mock_pygame = MagicMock()
    mock_pygame.mixer.music.get_pos.return_value = 5000  # 5 seconds into current play

    p = AudioPlayer.__new__(AudioPlayer)
    p._available = True
    p._path = Path("test.mp3")
    p._seek_offset = 30.0

    with patch.dict("sys.modules", {"pygame": mock_pygame}):
        pos = p.get_pos_seconds()

    assert pos == pytest.approx(35.0)
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/test_narration_player.py -v
```

Expected: `ImportError: cannot import name 'AudioPlayer'`

- [ ] **Step 3: Implement `narration_analysis/player.py`**

```python
from __future__ import annotations
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_INITIALIZED = False


def _init_mixer() -> bool:
    global _INITIALIZED
    if _INITIALIZED:
        return True
    try:
        import pygame
        pygame.mixer.pre_init(frequency=44100, size=-16, channels=2, buffer=512)
        pygame.mixer.init()
        _INITIALIZED = True
        return True
    except Exception as exc:
        logger.warning("pygame.mixer init failed — playback unavailable: %s", exc)
        return False


class AudioPlayer:
    def __init__(self) -> None:
        self._available: bool = _init_mixer()
        self._path: Path | None = None
        self._seek_offset: float = 0.0

    def load(self, path: Path) -> None:
        if not self._available:
            return
        import pygame
        suffix = path.suffix.lower()
        if suffix not in {".mp3", ".wav", ".ogg", ".flac"}:
            logger.warning("pygame may not support %s — playback may fail", suffix)
        try:
            pygame.mixer.music.load(str(path))
            self._path = path
            self._seek_offset = 0.0
        except Exception as exc:
            logger.warning("Could not load %s for playback: %s", path.name, exc)

    def seek(self, seconds: float) -> None:
        if not self._available or self._path is None:
            return
        import pygame
        self._seek_offset = seconds
        try:
            pygame.mixer.music.load(str(self._path))
            pygame.mixer.music.play(start=seconds)
        except Exception as exc:
            logger.warning("Seek failed: %s", exc)

    def play(self) -> None:
        if not self._available:
            return
        import pygame
        self._seek_offset = 0.0
        pygame.mixer.music.play()

    def pause(self) -> None:
        if not self._available:
            return
        import pygame
        pygame.mixer.music.pause()

    def unpause(self) -> None:
        if not self._available:
            return
        import pygame
        pygame.mixer.music.unpause()

    def stop(self) -> None:
        if not self._available:
            return
        import pygame
        pygame.mixer.music.stop()
        self._seek_offset = 0.0

    def is_playing(self) -> bool:
        if not self._available:
            return False
        import pygame
        return bool(pygame.mixer.music.get_busy())

    def get_pos_seconds(self) -> float:
        """Return absolute playback position (seek_offset + elapsed)."""
        if not self._available:
            return 0.0
        import pygame
        ms = pygame.mixer.music.get_pos()
        if ms < 0:
            return 0.0
        return self._seek_offset + ms / 1000.0

    def cleanup(self) -> None:
        if not self._available:
            return
        try:
            import pygame
            pygame.mixer.quit()
        except Exception:
            pass
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
python -m pytest tests/test_narration_player.py -v
```

Expected: `11 passed`

- [ ] **Step 5: Commit**

```bash
git add narration_analysis/player.py tests/test_narration_player.py
git commit -m "feat(narration): add audio player (pygame wrapper, seek-by-offset, graceful fallback)"
```

---

## Task 7: UI Tab

**Files:**
- Create: `narration_analysis/ui.py`

No unit tests for the UI class (it requires a live Tk root). Integration-tested in Task 9.

- [ ] **Step 1: Create `narration_analysis/ui.py`**

```python
from __future__ import annotations
import logging
import os
import re
import threading
from pathlib import Path
from tkinter import filedialog
from typing import Optional

import customtkinter as ctk

from narration_analysis.exporter import _OUTPUT_ROOT, export_all
from narration_analysis.models import AnalysisResult, Scene
from narration_analysis.player import AudioPlayer
from narration_analysis.scene_builder import build_scenes
from narration_analysis.transcriber import TranscriptionCancelled, transcribe

logger = logging.getLogger(__name__)

_MODELS = ["tiny", "base", "small", "medium", "large"]
_AUDIO_EXTS = [("Audio files", "*.mp3 *.wav *.m4a"), ("All files", "*.*")]
_PROJECT_RE = re.compile(r"[\s\-]+")


def _make_project_name(stem: str) -> str:
    return _PROJECT_RE.sub("_", stem)


class NarrationAnalysisTab:
    def __init__(self, parent: ctk.CTkFrame, root: ctk.CTk) -> None:
        self._parent = parent
        self._root = root
        self._player = AudioPlayer()
        self._audio_path: Optional[Path] = None
        self._result: Optional[AnalysisResult] = None
        self._cancel_event = threading.Event()
        self._is_playing = False
        self._model_var = ctk.StringVar(value="small")
        self._build_ui()
        self._poll_playback()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        pad = {"padx": 12, "pady": 4}

        ctk.CTkLabel(
            self._parent,
            text="Narration Analysis",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=12, pady=(12, 4))

        # Section 1 — Input
        input_row = ctk.CTkFrame(self._parent)
        input_row.pack(fill="x", **pad)
        ctk.CTkButton(
            input_row, text="Browse Audio", command=self._browse, width=120
        ).pack(side="left", padx=8, pady=8)
        self._file_lbl = ctk.CTkLabel(
            input_row, text="No file selected", anchor="w", font=ctk.CTkFont(size=11)
        )
        self._file_lbl.pack(side="left", fill="x", expand=True, padx=(4, 8), pady=8)

        # Section 2 — Controls
        ctrl_row = ctk.CTkFrame(self._parent)
        ctrl_row.pack(fill="x", **pad)
        ctk.CTkLabel(ctrl_row, text="Model:", width=50).pack(side="left", padx=(8, 2), pady=8)
        ctk.CTkOptionMenu(
            ctrl_row, values=_MODELS, variable=self._model_var, width=100
        ).pack(side="left", padx=2, pady=8)

        try:
            import torch
            gpu = torch.cuda.is_available()
        except ImportError:
            gpu = False
        ctk.CTkLabel(
            ctrl_row,
            text="GPU: Available" if gpu else "GPU: CPU only",
            text_color="#4CAF50" if gpu else "gray50",
            font=ctk.CTkFont(size=11),
        ).pack(side="left", padx=8, pady=8)

        self._cancel_btn = ctk.CTkButton(
            ctrl_row, text="Cancel", command=self._cancel_analysis,
            width=80, fg_color="#C62828", state="disabled",
        )
        self._cancel_btn.pack(side="right", padx=4, pady=8)
        self._analyse_btn = ctk.CTkButton(
            ctrl_row, text="Analyse", command=self._start_analysis, width=100
        )
        self._analyse_btn.pack(side="right", padx=8, pady=8)

        self._progress = ctk.CTkProgressBar(self._parent)
        self._progress.pack(fill="x", **pad)
        self._progress.set(0)
        self._status_lbl = ctk.CTkLabel(
            self._parent, text="Ready", anchor="w", font=ctk.CTkFont(size=11)
        )
        self._status_lbl.pack(anchor="w", padx=12, pady=(0, 4))

        # Section 3 — Preview (two columns)
        preview_frame = ctk.CTkFrame(self._parent)
        preview_frame.pack(fill="both", expand=True, **pad)
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.columnconfigure(1, weight=1)
        preview_frame.rowconfigure(0, weight=1)

        left = ctk.CTkFrame(preview_frame)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 4), pady=4)
        ctk.CTkLabel(left, text="Transcript", font=ctk.CTkFont(weight="bold")).pack(
            anchor="w", padx=8, pady=4
        )
        self._transcript_box = ctk.CTkTextbox(left, state="disabled", wrap="word")
        self._transcript_box.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        right = ctk.CTkFrame(preview_frame)
        right.grid(row=0, column=1, sticky="nsew", padx=(4, 0), pady=4)
        ctk.CTkLabel(right, text="Scenes", font=ctk.CTkFont(weight="bold")).pack(
            anchor="w", padx=8, pady=4
        )
        self._scenes_frame = ctk.CTkScrollableFrame(right)
        self._scenes_frame.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        # Section 4 — Playback
        pb_row = ctk.CTkFrame(self._parent)
        pb_row.pack(fill="x", **pad)
        self._play_btn = ctk.CTkButton(
            pb_row, text="▶ Play", command=self._toggle_play, width=90, state="disabled"
        )
        self._play_btn.pack(side="left", padx=8, pady=8)
        self._stop_btn = ctk.CTkButton(
            pb_row, text="⏹ Stop", command=self._stop_playback, width=80, state="disabled"
        )
        self._stop_btn.pack(side="left", padx=4, pady=8)
        self._pos_lbl = ctk.CTkLabel(pb_row, text="00:00", font=ctk.CTkFont(size=11))
        self._pos_lbl.pack(side="left", padx=8)

        # Section 5 — Export status
        ctk.CTkLabel(
            self._parent, text="Exported Files", font=ctk.CTkFont(weight="bold")
        ).pack(anchor="w", padx=12, pady=(8, 2))
        self._export_box = ctk.CTkTextbox(self._parent, height=90, state="disabled", wrap="none")
        self._export_box.pack(fill="x", **pad)
        btn_row = ctk.CTkFrame(self._parent, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=(0, 8))
        self._open_folder_btn = ctk.CTkButton(
            btn_row, text="Open Output Folder", command=self._open_folder,
            state="disabled", width=160,
        )
        self._open_folder_btn.pack(side="left")

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _browse(self) -> None:
        path_str = filedialog.askopenfilename(filetypes=_AUDIO_EXTS)
        if not path_str:
            return
        self._audio_path = Path(path_str)
        self._file_lbl.configure(text=self._audio_path.name)
        self._player.load(self._audio_path)
        self._play_btn.configure(state="normal")
        self._stop_btn.configure(state="normal")
        self._status_lbl.configure(text=f"Loaded: {self._audio_path.name}")

    def _start_analysis(self) -> None:
        if self._audio_path is None:
            self._status_lbl.configure(text="Select an audio file first.")
            return
        self._cancel_event.clear()
        self._analyse_btn.configure(state="disabled")
        self._cancel_btn.configure(state="normal")
        self._progress.set(0)
        self._status_lbl.configure(text="Starting transcription...")
        threading.Thread(target=self._analysis_worker, daemon=True).start()

    def _cancel_analysis(self) -> None:
        self._cancel_event.set()

    def _toggle_play(self) -> None:
        if self._is_playing:
            self._player.pause()
            self._is_playing = False
            self._play_btn.configure(text="▶ Play")
        else:
            if self._player.is_playing():
                self._player.unpause()
            else:
                self._player.play()
            self._is_playing = True
            self._play_btn.configure(text="⏸ Pause")

    def _stop_playback(self) -> None:
        self._player.stop()
        self._is_playing = False
        self._play_btn.configure(text="▶ Play")
        self._pos_lbl.configure(text="00:00")

    def _seek_to(self, seconds: float) -> None:
        self._player.seek(seconds)
        self._is_playing = True
        self._play_btn.configure(text="⏸ Pause")

    def _open_folder(self) -> None:
        if self._result:
            os.startfile(str(self._result.output_dir))

    # ------------------------------------------------------------------
    # Background worker
    # ------------------------------------------------------------------

    def _analysis_worker(self) -> None:
        try:
            path = self._audio_path
            project_name = _make_project_name(path.stem)
            output_dir = _OUTPUT_ROOT / project_name

            segments, duration = transcribe(
                path,
                self._model_var.get(),
                lambda f: self._root.after(0, self._update_progress, f),
                self._cancel_event,
            )
            scenes = build_scenes(segments)
            result = AnalysisResult(
                source_path=path,
                project_name=project_name,
                duration=duration,
                segments=segments,
                scenes=scenes,
                output_dir=output_dir,
            )
            exported = export_all(result)
            self._result = result
            self._root.after(0, self._on_complete, result, exported)

        except TranscriptionCancelled:
            self._root.after(0, self._on_cancelled)
        except Exception as exc:
            logger.exception("Analysis worker failed")
            self._root.after(0, self._on_error, str(exc))

    def _update_progress(self, frac: float) -> None:
        self._progress.set(frac)
        self._status_lbl.configure(text=f"Transcribing… {int(frac * 100)}%")

    # ------------------------------------------------------------------
    # Completion callbacks (main thread)
    # ------------------------------------------------------------------

    def _on_complete(self, result: AnalysisResult, exported: dict) -> None:
        self._progress.set(1.0)
        self._status_lbl.configure(text=f"Done — {len(result.scenes)} scenes extracted")
        self._analyse_btn.configure(state="normal")
        self._cancel_btn.configure(state="disabled")
        self._populate_transcript(result)
        self._populate_scenes(result)
        self._populate_exports(exported)
        self._open_folder_btn.configure(state="normal")

    def _on_cancelled(self) -> None:
        self._status_lbl.configure(text="Cancelled.")
        self._analyse_btn.configure(state="normal")
        self._cancel_btn.configure(state="disabled")
        self._progress.set(0)

    def _on_error(self, err: str) -> None:
        self._status_lbl.configure(text=f"Error: {err}")
        self._analyse_btn.configure(state="normal")
        self._cancel_btn.configure(state="disabled")

    # ------------------------------------------------------------------
    # Preview population
    # ------------------------------------------------------------------

    def _populate_transcript(self, result: AnalysisResult) -> None:
        self._transcript_box.configure(state="normal")
        self._transcript_box.delete("1.0", "end")
        for seg in result.segments:
            m, s = int(seg.start // 60), int(seg.start % 60)
            self._transcript_box.insert("end", f"[{m:02d}:{s:02d}] {seg.text}\n")
        self._transcript_box.configure(state="disabled")

    def _populate_scenes(self, result: AnalysisResult) -> None:
        for widget in self._scenes_frame.winfo_children():
            widget.destroy()
        for scene in result.scenes:
            self._add_scene_row(scene)

    def _add_scene_row(self, scene: Scene) -> None:
        sm, ss = int(scene.start // 60), int(scene.start % 60)
        em, es = int(scene.end // 60), int(scene.end % 60)
        tc = f"{sm:02d}:{ss:02d}–{em:02d}:{es:02d}"
        preview = scene.text[:38] + ("…" if len(scene.text) > 38 else "")
        label = f"▶  Scene {scene.scene_number}  {tc}  \"{preview}\""
        row = ctk.CTkFrame(self._scenes_frame)
        row.pack(fill="x", pady=2)
        ctk.CTkButton(
            row,
            text=label,
            anchor="w",
            command=lambda t=scene.start: self._seek_to(t),
            fg_color="transparent",
            hover_color=("gray85", "gray30"),
            text_color=("gray10", "gray90"),
            font=ctk.CTkFont(size=11),
        ).pack(fill="x", padx=4, pady=2)

    def _populate_exports(self, exported: dict) -> None:
        self._export_box.configure(state="normal")
        self._export_box.delete("1.0", "end")
        for key, path in exported.items():
            self._export_box.insert("end", f"{key}: {path}\n")
        self._export_box.configure(state="disabled")

    # ------------------------------------------------------------------
    # Playback position polling (every 500 ms)
    # ------------------------------------------------------------------

    def _poll_playback(self) -> None:
        if self._is_playing:
            pos = self._player.get_pos_seconds()
            m, s = int(pos // 60), int(pos % 60)
            self._pos_lbl.configure(text=f"{m:02d}:{s:02d}")
            if not self._player.is_playing():
                self._is_playing = False
                self._play_btn.configure(text="▶ Play")
        self._root.after(500, self._poll_playback)

    def cleanup(self) -> None:
        self._player.cleanup()
```

- [ ] **Step 2: Verify no syntax errors**

```bash
python -c "from narration_analysis.ui import NarrationAnalysisTab; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Run all narration tests**

```bash
python -m pytest tests/test_narration_models.py tests/test_narration_transcriber.py tests/test_narration_scene_builder.py tests/test_narration_exporter.py tests/test_narration_player.py -v
```

Expected: All green, 0 failures.

- [ ] **Step 4: Commit**

```bash
git add narration_analysis/ui.py
git commit -m "feat(narration): add NarrationAnalysisTab UI (browse, transcribe, preview, playback)"
```

---

## Task 8: Wire into app.py

**Files:**
- Modify: `app.py`

Changes are three targeted edits — no other logic in `app.py` is touched.

- [ ] **Step 1: Add the import**

In `app.py`, find the existing import block at the top (around line 32–33):

```python
from video_tools.ui import VideoToolsTab
from pipeline.ui import PipelineTab
```

Add one line immediately after:

```python
from video_tools.ui import VideoToolsTab
from pipeline.ui import PipelineTab
from narration_analysis.ui import NarrationAnalysisTab
```

- [ ] **Step 2: Register the tab**

Find (around line 146):
```python
        self._tabview.add("Video Tools")
        self._tabview.add("Pipeline")
```

Add one line after:
```python
        self._tabview.add("Video Tools")
        self._tabview.add("Pipeline")
        self._tabview.add("Narration Analysis")
```

- [ ] **Step 3: Instantiate the tab and store for cleanup**

Find (around line 152–153):
```python
        VideoToolsTab(self._tabview.tab("Video Tools"), self)
        PipelineTab(self._tabview.tab("Pipeline"), self)
```

Add one line after:
```python
        VideoToolsTab(self._tabview.tab("Video Tools"), self)
        PipelineTab(self._tabview.tab("Pipeline"), self)
        self._narration_tab = NarrationAnalysisTab(self._tabview.tab("Narration Analysis"), self)
```

- [ ] **Step 4: Add cleanup on close**

Find `_on_close` (around line 724):
```python
    def _on_close(self) -> None:
        if self._watching:
            self._watch_stop_event.set()
        self._settings["window_geometry"] = self.geometry()
        settings_manager.save(self._settings)
        self.destroy()
```

Add one line before `self.destroy()`:
```python
    def _on_close(self) -> None:
        if self._watching:
            self._watch_stop_event.set()
        self._settings["window_geometry"] = self.geometry()
        settings_manager.save(self._settings)
        self._narration_tab.cleanup()
        self.destroy()
```

- [ ] **Step 5: Verify import is clean**

```bash
python -c "import app; print('OK')"
```

Expected: `OK` (may take a moment for Tk to init — if it opens a window, close it)

- [ ] **Step 6: Run full test suite to confirm no regressions**

```bash
python -m pytest -v
```

Expected: All existing tests pass plus the new narration tests. No failures.

- [ ] **Step 7: Commit**

```bash
git add app.py
git commit -m "feat(narration): wire NarrationAnalysisTab into app.py (import, tab, cleanup)"
```

---

## Task 9: Smoke Test

Manual verification — no automated test needed.

- [ ] **Step 1: Launch the app**

```bash
cd D:\AIStudio\Apps\AudioMasterApp
python app.py
```

Expected: App opens with "Narration Analysis" visible as the last tab.

- [ ] **Step 2: Browse for an audio file**

Click "Browse Audio" and select any MP3 or WAV file. Verify:
- Filename appears in the label next to the Browse button
- Status bar says "Loaded: {filename}"

- [ ] **Step 3: Run analysis**

Select model "tiny" (fastest). Click "Analyse". Verify:
- Progress bar advances
- Status shows "Transcribing… N%"
- Cancel button becomes enabled
- Analyse button is disabled during run

- [ ] **Step 4: Verify completion**

After transcription completes:
- Status shows "Done — N scenes extracted"
- Left panel shows transcript with `[MM:SS]` timestamps
- Right panel shows scene rows with `▶  Scene N  HH:MM–HH:MM  "text…"` format
- Export box shows 6 file paths (txt, srt, vtt, alignment, scene_list, storyboard)
- "Open Output Folder" button is enabled

- [ ] **Step 5: Verify output files**

Click "Open Output Folder". In Explorer, verify:
```
D:\AIStudio\Outputs\narration_analysis\{project_name}\
  transcripts\  ← {stem}.txt  (exists, non-empty)
  srt\          ← {stem}.srt  (exists, numbered blocks)
  vtt\          ← {stem}.vtt  (starts with WEBVTT)
  json\         ← {stem}_alignment.json, {stem}_scene_list.json
  storyboards\  ← storyboard.json  (open it; confirm visual_prompt="" and status="pending")
```

- [ ] **Step 6: Verify scene seek**

Click any scene row in the Scenes panel. Verify:
- Audio starts playing from that scene's start time
- Play button changes to "⏸ Pause"
- Position counter advances

- [ ] **Step 7: Verify existing tabs unaffected**

Click through Single File, Batch, Watch Folder, Preview, Video Tools, Pipeline tabs. Verify all work exactly as before — no regressions.

- [ ] **Step 8: Final commit**

```bash
git add -A
git commit -m "feat: Narration Analysis tab — transcribe, export, scene preview, playback"
```
