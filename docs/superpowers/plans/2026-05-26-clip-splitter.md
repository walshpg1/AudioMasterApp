# Clip Splitter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Clip Splitter" panel to the Single File tab that masters the selected file and cuts the mastered output into equal-length clips saved to a named subfolder.

**Architecture:** A new `audio_splitter.py` module exposes a pure `split_audio()` function that shells out to FFmpeg's segment muxer. `app.py` gains a new `_build_clip_splitter_panel()` UI section and a `_master_split_worker()` thread that calls `master()` then `split_audio()` in sequence.

**Tech Stack:** Python 3.12, FFmpeg (segment muxer), customtkinter, numpy + soundfile (tests only).

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `audio_splitter.py` | `SplitResult` dataclass + `split_audio()` function |
| Create | `tests/test_audio_splitter.py` | Unit tests for `audio_splitter` |
| Modify | `app.py` | Add panel, state vars, worker, and open-folder action |

---

## Task 1: Implement `audio_splitter.py` (TDD)

**Files:**
- Create: `audio_splitter.py`
- Create: `tests/test_audio_splitter.py`

---

- [ ] **Step 1: Write the failing tests**

Create `tests/test_audio_splitter.py` with this content:

```python
import math
from pathlib import Path
import numpy as np
import soundfile as sf
import pytest
from audio_splitter import split_audio, SplitResult


def _make_wav(path: Path, duration_seconds: float, sample_rate: int = 44100) -> str:
    rng = np.random.default_rng(0)
    samples = rng.uniform(-0.5, 0.5, (int(sample_rate * duration_seconds), 2))
    sf.write(str(path), samples, sample_rate, subtype="PCM_24")
    return str(path)


def test_split_happy_path(tmp_path):
    """15 s WAV split at 5 s → 3 clips of ~5 s each."""
    src = _make_wav(tmp_path / "song.wav", 15.0)
    result = split_audio(src, 5.0, tmp_path / "clips")
    assert result.error is None, result.error
    assert result.clip_count == 3
    assert len(result.clips) == 3
    for clip in result.clips:
        info = sf.info(clip)
        assert abs(info.duration - 5.0) < 0.1


def test_split_remainder_kept(tmp_path):
    """17 s WAV split at 5 s → 4 clips (3 × 5 s + 1 × 2 s)."""
    src = _make_wav(tmp_path / "song.wav", 17.0)
    result = split_audio(src, 5.0, tmp_path / "clips")
    assert result.error is None, result.error
    assert result.clip_count == 4
    durations = [sf.info(c).duration for c in result.clips]
    assert abs(durations[-1] - 2.0) < 0.2


def test_split_single_clip(tmp_path):
    """3 s WAV split at 5 s → 1 clip containing the whole file."""
    src = _make_wav(tmp_path / "song.wav", 3.0)
    result = split_audio(src, 5.0, tmp_path / "clips")
    assert result.error is None, result.error
    assert result.clip_count == 1


def test_split_invalid_duration(tmp_path):
    """duration=0 → error set, no files written."""
    src = _make_wav(tmp_path / "song.wav", 10.0)
    clips_dir = tmp_path / "clips"
    result = split_audio(src, 0.0, clips_dir)
    assert result.error is not None
    assert not clips_dir.exists() or not any(clips_dir.iterdir())


def test_split_bad_input_path(tmp_path):
    """Non-existent input file → error in SplitResult, clip_count == 0."""
    result = split_audio("nonexistent_file.wav", 5.0, tmp_path / "clips")
    assert result.error is not None
    assert result.clip_count == 0


def test_split_output_dir_created(tmp_path):
    """output_dir is created automatically if it does not exist."""
    src = _make_wav(tmp_path / "song.wav", 6.0)
    clips_dir = tmp_path / "new" / "nested" / "clips"
    result = split_audio(src, 5.0, clips_dir)
    assert result.error is None, result.error
    assert clips_dir.exists()


def test_split_clips_named_with_stem_and_number(tmp_path):
    """Clips are named {stem}_001.wav, {stem}_002.wav, …"""
    src = _make_wav(tmp_path / "mysong.wav", 12.0)
    result = split_audio(src, 5.0, tmp_path / "clips")
    assert result.error is None, result.error
    names = [Path(c).name for c in result.clips]
    assert names[0] == "mysong_001.wav"
    assert names[1] == "mysong_002.wav"
    assert names[2] == "mysong_003.wav"


def test_split_output_dir_on_result(tmp_path):
    """SplitResult.output_dir matches the directory passed in."""
    src = _make_wav(tmp_path / "song.wav", 5.0)
    clips_dir = tmp_path / "clips"
    result = split_audio(src, 5.0, clips_dir)
    assert result.output_dir == clips_dir
```

- [ ] **Step 2: Run tests — confirm they all fail**

```
.venv\Scripts\pytest tests/test_audio_splitter.py -v
```

Expected: `ImportError: No module named 'audio_splitter'` (or similar — all tests fail).

---

- [ ] **Step 3: Create `audio_splitter.py`**

```python
from __future__ import annotations
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ffmpeg_utils import find_ffmpeg

logger = logging.getLogger(__name__)


@dataclass
class SplitResult:
    clips: list[str] = field(default_factory=list)
    clip_count: int = 0
    output_dir: Optional[Path] = None
    error: Optional[str] = None


def split_audio(
    input_path: str,
    clip_duration: float,
    output_dir: Path,
) -> SplitResult:
    """Cut input_path into clips of clip_duration seconds, saved to output_dir.

    Uses FFmpeg segment muxer with stream-copy (no re-encoding).
    The final clip may be shorter than clip_duration if the file does not divide evenly.
    Returns SplitResult with error set on failure; never raises.
    """
    if clip_duration <= 0:
        return SplitResult(error=f"clip_duration must be > 0, got {clip_duration}")

    src = Path(input_path)
    if not src.exists():
        return SplitResult(error=f"Input file does not exist: {src}")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    ext = src.suffix  # preserves format: .wav, .mp3, .flac, etc.
    pattern = str(output_dir / f"{src.stem}_%03d{ext}")

    ffmpeg = find_ffmpeg() or "ffmpeg"
    cmd = [
        ffmpeg, "-y", "-i", str(src),
        "-f", "segment",
        "-segment_time", str(clip_duration),
        "-reset_timestamps", "1",
        "-segment_start_number", "1",
        "-c", "copy",
        pattern,
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        logger.error("FFmpeg split failed: %s", proc.stderr[-800:])
        return SplitResult(
            output_dir=output_dir,
            error=f"FFmpeg split failed: {proc.stderr[-400:]}",
        )

    clips = sorted(output_dir.glob(f"{src.stem}_*{ext}"))
    return SplitResult(
        clips=[str(c) for c in clips],
        clip_count=len(clips),
        output_dir=output_dir,
    )
```

- [ ] **Step 4: Run tests — confirm they all pass**

```
.venv\Scripts\pytest tests/test_audio_splitter.py -v
```

Expected: all 8 tests PASS.

- [ ] **Step 5: Commit**

```
git add audio_splitter.py tests/test_audio_splitter.py
git commit -m "feat: add audio_splitter module with split_audio()"
```

---

## Task 2: Wire up the Clip Splitter panel in `app.py`

**Files:**
- Modify: `app.py`

---

- [ ] **Step 1: Add the import and state variables**

At the top of `app.py`, add the import after the existing local imports (around line 29):

```python
from audio_splitter import split_audio, SplitResult as SplitAudioResult
```

In `App.__init__`, after `self._last_handoff_note_path` (around line 81), add:

```python
self._clip_duration_var = ctk.StringVar(value="5")
self._last_clips_dir: Path | None = None
```

- [ ] **Step 2: Add `_build_clip_splitter_panel()` method**

Add this method to `app.py` after `_build_single_file_tab` (after line ~291):

```python
def _build_clip_splitter_panel(self, parent) -> None:
    pad = {"padx": 12, "pady": 4}

    panel = ctk.CTkFrame(parent)
    panel.pack(fill="x", **pad)

    ctk.CTkLabel(
        panel, text="Clip Splitter",
        font=ctk.CTkFont(weight="bold"),
    ).pack(anchor="w", padx=12, pady=(8, 2))
    ctk.CTkLabel(
        panel,
        text="Masters the file, then cuts it into equal-length clips.",
        font=ctk.CTkFont(size=11),
        text_color="gray",
    ).pack(anchor="w", padx=12, pady=(0, 6))

    dur_row = ctk.CTkFrame(panel, fg_color="transparent")
    dur_row.pack(fill="x", padx=12, pady=(0, 6))
    ctk.CTkLabel(dur_row, text="Clip duration (s):", width=130, anchor="w").pack(side="left")
    ctk.CTkEntry(dur_row, width=70, textvariable=self._clip_duration_var).pack(side="left")

    btn_row = ctk.CTkFrame(panel, fg_color="transparent")
    btn_row.pack(fill="x", padx=12, pady=(0, 10))
    self._master_split_btn = ctk.CTkButton(
        btn_row, text="Master & Split",
        command=self._run_master_and_split, width=160,
    )
    self._master_split_btn.pack(side="left", padx=(0, 8))
    self._open_clips_btn = ctk.CTkButton(
        btn_row, text="Open Clips Folder",
        command=self._open_clips_folder, width=160, state="disabled",
    )
    self._open_clips_btn.pack(side="left")
```

- [ ] **Step 3: Call `_build_clip_splitter_panel()` from `_build_single_file_tab()`**

In `_build_single_file_tab()`, locate the block that creates `_report_btn_single` (around line 252). Insert one call **immediately after** that block and **before** the DaVinci Resolve handoff block:

```python
        self._report_btn_single.pack(fill="x")

        # ← INSERT HERE
        self._build_clip_splitter_panel(parent)

        # DaVinci Resolve Free handoff panel
        handoff_frame = ctk.CTkFrame(parent)
```

- [ ] **Step 4: Add `_run_master_and_split()`, `_master_split_worker()`, `_on_master_split_done()`, and `_open_clips_folder()`**

Add these four methods to `app.py` (place them after the existing `_play_output` method around line ~916):

```python
# ==================================================================
# Clip Splitter
# ==================================================================

def _run_master_and_split(self) -> None:
    if not self._wav_path:
        self._set_status("No file selected.", "warning")
        return
    raw = self._clip_duration_var.get().strip()
    try:
        duration = float(raw)
        if duration <= 0:
            raise ValueError
    except ValueError:
        self._set_status("Clip duration must be a positive number.", "warning")
        return
    preset = self._preset_map[self._preset_var.get()]
    export_fmt = self._format_map[self._format_var.get()]
    self._set_status("Mastering…", "normal")
    self._progress.configure(mode="determinate")
    self._progress.set(0.05)
    self._master_split_btn.configure(state="disabled")
    self._open_clips_btn.configure(state="disabled")
    threading.Thread(
        target=self._master_split_worker,
        args=(preset, export_fmt, duration),
        daemon=True,
    ).start()

def _master_split_worker(
    self, preset: dict, export_fmt: ExportFormat, clip_duration: float
) -> None:
    self.after(0, lambda: self._progress.set(0.35))
    master_result = master(self._wav_path, preset, export_fmt, self._output_dir)
    self.after(0, lambda: self._progress.set(0.70))
    if master_result.error:
        self.after(0, lambda r=master_result: self._on_master_split_done(r, None))
        return
    source_stem = Path(self._wav_path).stem
    clips_dir = self._output_dir / f"{source_stem}_clips"
    split_result = split_audio(master_result.output_path, clip_duration, clips_dir)
    self.after(0, lambda: self._progress.set(0.95))
    self.after(
        0,
        lambda m=master_result, s=split_result: self._on_master_split_done(m, s),
    )

def _on_master_split_done(
    self,
    master_result,
    split_result: SplitAudioResult | None,
) -> None:
    self._progress.set(1.0)
    self._master_split_btn.configure(state="normal")
    if master_result.error:
        self._set_status(f"Mastering error: {master_result.error}", "error")
        return
    if split_result is None or split_result.error:
        err = split_result.error if split_result else "Unknown split error"
        self._set_status(f"Split error: {err}", "error")
        return
    self._last_clips_dir = split_result.output_dir
    self._open_clips_btn.configure(state="normal")
    folder_name = split_result.output_dir.name
    self._set_status(
        f"Done! {split_result.clip_count} clips → {folder_name}/",
        "success",
    )

def _open_clips_folder(self) -> None:
    if self._last_clips_dir and self._last_clips_dir.exists():
        os.startfile(str(self._last_clips_dir))
    else:
        self._set_status("Clips folder not found.", "warning")
```

- [ ] **Step 5: Update `_reset()` to clear clip state**

In `app.py`, find the `_reset()` method (around line ~707). After the line that disables `_open_handoff_btn`, add:

```python
        self._open_clips_btn.configure(state="disabled")
        self._last_clips_dir = None
```

- [ ] **Step 6: Run the full test suite**

```
.venv\Scripts\pytest -v
```

Expected: all existing tests still pass, all 8 new splitter tests pass.

- [ ] **Step 7: Commit**

```
git add app.py
git commit -m "feat: add Clip Splitter panel to Single File tab"
```
