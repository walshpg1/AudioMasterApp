# Pipeline Status Tab — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Pipeline tab to AudioMasterApp that monitors LTX render folders, auto-extracts the last frame from each completed render, and provides a one-click FFmpeg mux to combine the video with a mastered audio file.

**Architecture:** A new `pipeline/` package sits alongside `video_tools/`. It reuses `ExtractionService` and `VideoWatcher` from `video_tools/` (two instances, one per folder) and adds `mux_runner.py` for the FFmpeg audio+video combine step. `PipelineTab` is a plain UI class following the same pattern as `VideoToolsTab`.

**Tech Stack:** Python, customtkinter, Pillow, FFmpeg (subprocess), threading, unittest.mock

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `pipeline/__init__.py` | Create | Package marker |
| `pipeline/models.py` | Create | `MuxJob`, `MuxResult` dataclasses |
| `pipeline/mux_runner.py` | Create | `build_mux_command()`, `run_mux()` |
| `pipeline/ui.py` | Create | `PipelineTab` UI class + `find_latest_audio()`, `_mux_is_ready()` helpers |
| `settings_manager.py` | Modify | Add `pipeline_output_folder`, `pipeline_watcher_enabled` defaults |
| `app.py` | Modify | Import `PipelineTab`, add `"Pipeline"` tab |
| `tests/test_pipeline_models.py` | Create | Dataclass field and default tests |
| `tests/test_pipeline_mux_runner.py` | Create | Command structure, path safety, `on_done` called once |
| `tests/test_pipeline_ui.py` | Create | `find_latest_audio`, `_mux_is_ready` helper tests |

---

### Task 1: Scaffold `pipeline/` package and models

**Files:**
- Create: `pipeline/__init__.py`
- Create: `pipeline/models.py`
- Create: `tests/test_pipeline_models.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_pipeline_models.py
from pathlib import Path
import pytest
from pipeline.models import MuxJob, MuxResult


def test_mux_job_fields(tmp_path):
    v = tmp_path / "video.mp4"
    a = tmp_path / "audio.wav"
    o = tmp_path / "out.mp4"
    job = MuxJob(video_path=v, audio_path=a, output_path=o)
    assert job.video_path == v
    assert job.audio_path == a
    assert job.output_path == o


def test_mux_result_success_defaults(tmp_path):
    job = MuxJob(tmp_path / "v.mp4", tmp_path / "a.wav", tmp_path / "o.mp4")
    result = MuxResult(job=job, success=True, ffmpeg_cmd=["ffmpeg"])
    assert result.success is True
    assert result.error is None


def test_mux_result_failure(tmp_path):
    job = MuxJob(tmp_path / "v.mp4", tmp_path / "a.wav", tmp_path / "o.mp4")
    result = MuxResult(job=job, success=False, ffmpeg_cmd=["ffmpeg"], error="bad exit")
    assert result.success is False
    assert result.error == "bad exit"
```

- [ ] **Step 2: Run tests — verify they fail**

```
cd D:\AIStudio\Apps\AudioMasterApp
python -m pytest tests/test_pipeline_models.py -v
```

Expected: `ModuleNotFoundError: No module named 'pipeline'`

- [ ] **Step 3: Create `pipeline/__init__.py`**

```python
# pipeline/__init__.py
# (empty — marks directory as a package)
```

- [ ] **Step 4: Create `pipeline/models.py`**

```python
# pipeline/models.py
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class MuxJob:
    video_path: Path
    audio_path: Path
    output_path: Path


@dataclass
class MuxResult:
    job: MuxJob
    success: bool
    ffmpeg_cmd: list[str]
    error: Optional[str] = None
```

- [ ] **Step 5: Run tests — verify they pass**

```
python -m pytest tests/test_pipeline_models.py -v
```

Expected: `3 passed`

- [ ] **Step 6: Commit**

```
git add pipeline/__init__.py pipeline/models.py tests/test_pipeline_models.py
git commit -m "feat: add pipeline package scaffold and MuxJob/MuxResult models"
```

---

### Task 2: FFmpeg mux runner

**Files:**
- Create: `pipeline/mux_runner.py`
- Create: `tests/test_pipeline_mux_runner.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_pipeline_mux_runner.py
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pipeline.models import MuxJob, MuxResult
from pipeline.mux_runner import build_mux_command, run_mux


def make_job(tmp_path):
    return MuxJob(
        video_path=tmp_path / "render.mp4",
        audio_path=tmp_path / "audio.wav",
        output_path=tmp_path / "out.mp4",
    )


def test_build_mux_command_structure(tmp_path):
    job = make_job(tmp_path)
    cmd = build_mux_command(job)
    assert cmd[0] == "ffmpeg"
    assert str(job.video_path) in cmd
    assert str(job.audio_path) in cmd
    assert "-c:v" in cmd
    assert "copy" in cmd
    assert "-c:a" in cmd
    assert "aac" in cmd
    assert "-shortest" in cmd
    assert cmd[-1] == str(job.output_path)


def test_build_mux_command_input_order(tmp_path):
    job = make_job(tmp_path)
    cmd = build_mux_command(job)
    # video must appear before audio in -i arguments
    vi = cmd.index(str(job.video_path))
    ai = cmd.index(str(job.audio_path))
    assert vi < ai


def test_build_mux_command_custom_ffmpeg(tmp_path):
    job = make_job(tmp_path)
    cmd = build_mux_command(job, ffmpeg=r"C:\ffmpeg\bin\ffmpeg.exe")
    assert cmd[0] == r"C:\ffmpeg\bin\ffmpeg.exe"


def test_build_mux_command_paths_with_spaces(tmp_path):
    job = MuxJob(
        video_path=tmp_path / "my render.mp4",
        audio_path=tmp_path / "my audio.wav",
        output_path=tmp_path / "my out.mp4",
    )
    cmd = build_mux_command(job)
    # paths with spaces must be separate list items — never joined strings
    assert str(job.video_path) in cmd
    assert str(job.audio_path) in cmd
    assert str(job.output_path) in cmd


def test_run_mux_success_calls_on_done_once(tmp_path):
    job = make_job(tmp_path)
    results = []
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    with patch("pipeline.mux_runner.subprocess.run", return_value=mock_proc):
        run_mux(job, "ffmpeg", results.append)
    assert len(results) == 1
    assert results[0].success is True
    assert results[0].ffmpeg_cmd[0] == "ffmpeg"


def test_run_mux_nonzero_exit(tmp_path):
    job = make_job(tmp_path)
    results = []
    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.stderr = "encoding error details"
    with patch("pipeline.mux_runner.subprocess.run", return_value=mock_proc):
        run_mux(job, "ffmpeg", results.append)
    assert len(results) == 1
    assert results[0].success is False
    assert results[0].error is not None


def test_run_mux_timeout(tmp_path):
    job = make_job(tmp_path)
    results = []
    with patch(
        "pipeline.mux_runner.subprocess.run",
        side_effect=subprocess.TimeoutExpired("ffmpeg", 300),
    ):
        run_mux(job, "ffmpeg", results.append)
    assert len(results) == 1
    assert results[0].success is False
    assert "timed out" in results[0].error.lower()


def test_run_mux_oserror(tmp_path):
    job = make_job(tmp_path)
    results = []
    with patch(
        "pipeline.mux_runner.subprocess.run",
        side_effect=OSError("ffmpeg not found"),
    ):
        run_mux(job, "ffmpeg", results.append)
    assert len(results) == 1
    assert results[0].success is False
```

- [ ] **Step 2: Run tests — verify they fail**

```
python -m pytest tests/test_pipeline_mux_runner.py -v
```

Expected: `ModuleNotFoundError: No module named 'pipeline.mux_runner'`

- [ ] **Step 3: Create `pipeline/mux_runner.py`**

```python
# pipeline/mux_runner.py
from __future__ import annotations
import logging
import subprocess
from typing import Callable

from pipeline.models import MuxJob, MuxResult

logger = logging.getLogger(__name__)

_MUX_TIMEOUT = 300  # 5 minutes — large video files can be slow


def build_mux_command(job: MuxJob, ffmpeg: str = "ffmpeg") -> list[str]:
    return [
        ffmpeg,
        "-i", str(job.video_path),
        "-i", str(job.audio_path),
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        str(job.output_path),
    ]


def run_mux(
    job: MuxJob,
    ffmpeg_path: str,
    on_done: Callable[[MuxResult], None],
) -> None:
    """Run FFmpeg mux in the calling thread. Calls on_done exactly once."""
    cmd = build_mux_command(job, ffmpeg_path)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=_MUX_TIMEOUT)
        if proc.returncode == 0:
            on_done(MuxResult(job=job, success=True, ffmpeg_cmd=cmd))
        else:
            error = proc.stderr[-400:] if proc.stderr else "non-zero exit"
            on_done(MuxResult(job=job, success=False, ffmpeg_cmd=cmd, error=error))
    except subprocess.TimeoutExpired:
        on_done(MuxResult(job=job, success=False, ffmpeg_cmd=cmd, error="FFmpeg mux timed out after 300 s"))
    except OSError as exc:
        on_done(MuxResult(job=job, success=False, ffmpeg_cmd=cmd, error=str(exc)))
```

- [ ] **Step 4: Run tests — verify they pass**

```
python -m pytest tests/test_pipeline_mux_runner.py -v
```

Expected: `8 passed`

- [ ] **Step 5: Commit**

```
git add pipeline/mux_runner.py tests/test_pipeline_mux_runner.py
git commit -m "feat: add pipeline mux_runner with build_mux_command and run_mux"
```

---

### Task 3: Update `settings_manager.py`

**Files:**
- Modify: `settings_manager.py`

- [ ] **Step 1: Read the current `_defaults()` function**

Open `settings_manager.py` and locate `_defaults()`. The last video key currently is:

```python
"video_watcher_enabled": False,
```

- [ ] **Step 2: Add two pipeline keys after the existing video keys**

```python
        # Pipeline
        "pipeline_output_folder": r"D:\AIStudio\Apps\AIVideoStudio\exports\tiktok",
        "pipeline_watcher_enabled": False,
```

The full block with context:

```python
        # Video Tools
        "video_watch_folder":   r"D:\AIStudio\Apps\AIVideoStudio\renders",
        "video_output_folder":  "",
        "video_format":         "png",
        "video_watcher_enabled": False,
        # Pipeline
        "pipeline_output_folder": r"D:\AIStudio\Apps\AIVideoStudio\exports\tiktok",
        "pipeline_watcher_enabled": False,
```

- [ ] **Step 3: Run the full test suite to confirm nothing broke**

```
python -m pytest tests/ -v --ignore=tests/test_resolve_bridge.py 2>&1 | tail -20
```

Expected: all existing tests still pass.

- [ ] **Step 4: Commit**

```
git add settings_manager.py
git commit -m "feat: add pipeline settings keys to settings_manager defaults"
```

---

### Task 4: `pipeline/ui.py` — PipelineTab UI class

**Files:**
- Create: `pipeline/ui.py`
- Create: `tests/test_pipeline_ui.py`

**Important context:**
- `ExtractionService.start()` already calls `self.stop()` internally if the service is already running — safe to call `start()` without stopping first.
- All `ExtractionService` callbacks are marshalled to the main thread via `root.after(0, ...)` — you do not need to add another `root.after` wrap in `_on_extraction`.
- `self._thumb_lbl._ctk_image = ctk_img` is the standard pattern to prevent CTkImage from being garbage collected.
- The mux runs in a daemon thread; `_on_mux_result` is wrapped in `root.after(0, ...)` manually (unlike extraction, mux has its own thread).

- [ ] **Step 1: Write the failing tests (helper functions only — no Tk required)**

```python
# tests/test_pipeline_ui.py
from pathlib import Path
import time
import pytest

from pipeline.ui import find_latest_audio, _mux_is_ready


def test_find_latest_audio_returns_newest(tmp_path):
    old = tmp_path / "old.wav"
    new = tmp_path / "new.wav"
    old.write_bytes(b"x")
    time.sleep(0.02)  # ensure different mtime
    new.write_bytes(b"x")
    result = find_latest_audio(tmp_path, frozenset({".wav", ".mp3"}))
    assert result == new


def test_find_latest_audio_ignores_non_audio(tmp_path):
    (tmp_path / "video.mp4").write_bytes(b"x")
    (tmp_path / "audio.wav").write_bytes(b"x")
    result = find_latest_audio(tmp_path, frozenset({".wav", ".mp3"}))
    assert result.name == "audio.wav"


def test_find_latest_audio_missing_dir(tmp_path):
    result = find_latest_audio(tmp_path / "nonexistent", frozenset({".wav"}))
    assert result is None


def test_find_latest_audio_empty_dir(tmp_path):
    result = find_latest_audio(tmp_path, frozenset({".wav", ".mp3"}))
    assert result is None


def test_mux_is_ready_requires_both(tmp_path):
    v = tmp_path / "v.mp4"
    a = tmp_path / "a.wav"
    assert _mux_is_ready(None, a, False) is False
    assert _mux_is_ready(v, None, False) is False


def test_mux_is_ready_blocked_when_running(tmp_path):
    v = tmp_path / "v.mp4"
    a = tmp_path / "a.wav"
    assert _mux_is_ready(v, a, mux_running=True) is False


def test_mux_is_ready_true_when_both_present(tmp_path):
    v = tmp_path / "v.mp4"
    a = tmp_path / "a.wav"
    assert _mux_is_ready(v, a, mux_running=False) is True
```

- [ ] **Step 2: Run tests — verify they fail**

```
python -m pytest tests/test_pipeline_ui.py -v
```

Expected: `ImportError` — `pipeline.ui` does not exist yet.

- [ ] **Step 3: Create `pipeline/ui.py`**

```python
# pipeline/ui.py
from __future__ import annotations
import datetime
import logging
import os
import threading
from pathlib import Path
from tkinter import filedialog
from typing import Optional

import customtkinter as ctk
from PIL import Image

import settings_manager
from ffmpeg_utils import find_ffmpeg
from pipeline.models import MuxJob, MuxResult
from pipeline.mux_runner import run_mux
from video_tools.extraction_service import ExtractionService
from video_tools.models import ExtractionResult

logger = logging.getLogger(__name__)

_LTX_FOLDER          = Path(r"D:\AIStudio\Apps\AIVideoStudio\renders\video\LTX")
_LTX_DIRECTOR_FOLDER = Path(r"D:\AIStudio\Apps\AIVideoStudio\renders\video\LTX_Director")
_AUDIO_PROCESSED_DIR = Path(r"D:\AIStudio\Apps\AIVideoStudio\audio\processed")
_STILLS_FOLDER       = Path(r"D:\AIStudio\Apps\AIVideoStudio\renders\video\stills")
_AUDIO_EXTENSIONS    = frozenset({".wav", ".mp3"})

_STATUS_COLOURS = {
    "idle":       ("gray80", "gray40"),
    "watching":   ("#4CAF50", "#388E3C"),
    "processing": ("#FFC107", "#F9A825"),
    "error":      ("#F44336", "#C62828"),
}
_STATUS_LABELS = {
    "idle":       "● Idle",
    "watching":   "● Watching",
    "processing": "● Processing",
    "error":      "● Error",
}


def find_latest_audio(audio_dir: Path, extensions: frozenset[str]) -> Optional[Path]:
    """Return the most recently modified audio file in audio_dir, or None."""
    if not audio_dir.exists():
        return None
    candidates = [
        p for p in audio_dir.iterdir()
        if p.is_file() and p.suffix.lower() in extensions
    ]
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None


def _mux_is_ready(
    video_path: Optional[Path],
    audio_path: Optional[Path],
    mux_running: bool,
) -> bool:
    return bool(video_path and audio_path and not mux_running)


class PipelineTab:
    """Builds and owns the Pipeline tab UI.

    Monitors both LTX render folders, auto-extracts last frames, and
    provides a mux button to combine the latest render with mastered audio.
    """

    def __init__(self, parent: ctk.CTkFrame, root: ctk.CTk) -> None:
        self._parent = parent
        self._root = root
        self._service_ltx = ExtractionService(root)
        self._service_dir = ExtractionService(root)
        self._watching = False
        self._last_video_path: Optional[Path] = None
        self._last_output_path: Optional[Path] = None
        self._audio_path: Optional[Path] = None
        self._mux_running = False

        s = settings_manager.load()
        self._output_folder_var = ctk.StringVar(
            value=s.get("pipeline_output_folder", r"D:\AIStudio\Apps\AIVideoStudio\exports\tiktok")
        )
        self._watcher_enabled_var = ctk.IntVar(
            value=int(s.get("pipeline_watcher_enabled", False))
        )

        self._build_ui()
        self._detect_audio()
        if self._watcher_enabled_var.get():
            self._start_watchers()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        pad = {"padx": 12, "pady": 4}

        ctk.CTkLabel(
            self._parent,
            text="LTX Pipeline",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=12, pady=(12, 4))

        # Watch status row
        watch_row = ctk.CTkFrame(self._parent)
        watch_row.pack(fill="x", **pad)
        ctk.CTkLabel(
            watch_row,
            text="renders\\video\\LTX\\  +  LTX_Director\\",
            anchor="w",
            font=ctk.CTkFont(size=11),
        ).pack(side="left", padx=8, pady=8, fill="x", expand=True)
        self._status_lbl = ctk.CTkLabel(watch_row, text="● Idle", width=100, anchor="e")
        self._status_lbl.pack(side="right", padx=(0, 4), pady=8)
        ctk.CTkSwitch(
            watch_row,
            text="Enable",
            variable=self._watcher_enabled_var,
            command=self._on_watcher_toggle,
            width=80,
        ).pack(side="right", padx=4, pady=8)

        # Render feed
        ctk.CTkLabel(
            self._parent, text="Render Feed", font=ctk.CTkFont(weight="bold")
        ).pack(anchor="w", padx=12, pady=(8, 2))
        self._feed = ctk.CTkTextbox(self._parent, height=160, state="disabled", wrap="word")
        self._feed.pack(fill="x", **pad)
        self._feed.tag_config("success", foreground="#4CAF50")
        self._feed.tag_config("error", foreground="#F44336")
        self._feed.tag_config("waiting", foreground="#FFC107")

        # Last frame preview
        preview = ctk.CTkFrame(self._parent)
        preview.pack(fill="x", **pad)
        self._thumb_lbl = ctk.CTkLabel(
            preview, text="No frame yet", width=120, height=72,
            fg_color="#333333", corner_radius=4,
        )
        self._thumb_lbl.pack(side="left", padx=8, pady=8)
        info = ctk.CTkFrame(preview, fg_color="transparent")
        info.pack(side="left", fill="both", expand=True, padx=(0, 8))
        self._frame_name_lbl = ctk.CTkLabel(info, text="", anchor="w", font=ctk.CTkFont(size=11))
        self._frame_name_lbl.pack(anchor="w", pady=(8, 2))
        self._frame_source_lbl = ctk.CTkLabel(
            info, text="", anchor="w", font=ctk.CTkFont(size=10), text_color="gray60"
        )
        self._frame_source_lbl.pack(anchor="w", pady=(0, 4))
        self._open_btn = ctk.CTkButton(
            info, text="Open in Viewer", command=self._open_in_viewer, width=120, state="disabled"
        )
        self._open_btn.pack(anchor="w")

        # Audio master row
        audio_row = ctk.CTkFrame(self._parent)
        audio_row.pack(fill="x", **pad)
        ctk.CTkLabel(audio_row, text="Audio:", width=55).pack(side="left", padx=(8, 0), pady=8)
        self._audio_lbl = ctk.CTkLabel(
            audio_row, text="Detecting...", anchor="w", font=ctk.CTkFont(size=11)
        )
        self._audio_lbl.pack(side="left", fill="x", expand=True, padx=4, pady=8)
        ctk.CTkButton(
            audio_row, text="Browse...", command=self._browse_audio, width=90
        ).pack(side="right", padx=8, pady=8)

        # Output folder row
        out_row = ctk.CTkFrame(self._parent)
        out_row.pack(fill="x", **pad)
        ctk.CTkLabel(out_row, text="Output:", width=55).pack(side="left", padx=(8, 0), pady=8)
        ctk.CTkLabel(
            out_row, textvariable=self._output_folder_var, anchor="w", font=ctk.CTkFont(size=11)
        ).pack(side="left", fill="x", expand=True, padx=4, pady=8)
        ctk.CTkButton(
            out_row, text="Browse...", command=self._browse_output, width=90
        ).pack(side="right", padx=8, pady=8)

        # Mux button
        mux_row = ctk.CTkFrame(self._parent)
        mux_row.pack(fill="x", **pad)
        self._mux_btn = ctk.CTkButton(
            mux_row, text="Mux Video + Audio →", command=self._do_mux, state="disabled"
        )
        self._mux_btn.pack(fill="x", padx=8, pady=8)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _detect_audio(self) -> None:
        self._audio_path = find_latest_audio(_AUDIO_PROCESSED_DIR, _AUDIO_EXTENSIONS)
        if self._audio_path:
            self._audio_lbl.configure(text=f"🎵 {self._audio_path.name} (auto-detected)")
        else:
            self._audio_lbl.configure(text="No audio file — use Browse")
        self._update_mux_btn()

    def _update_mux_btn(self) -> None:
        ready = _mux_is_ready(self._last_video_path, self._audio_path, self._mux_running)
        self._mux_btn.configure(state="normal" if ready else "disabled")

    # ------------------------------------------------------------------
    # Watcher lifecycle
    # ------------------------------------------------------------------

    def _start_watchers(self) -> None:
        _STILLS_FOLDER.mkdir(parents=True, exist_ok=True)
        stills = str(_STILLS_FOLDER)

        if _LTX_FOLDER.exists():
            self._service_ltx.start(
                str(_LTX_FOLDER), stills, "png",
                lambda r: self._on_extraction(r, "LTX"),
            )
        else:
            self._log_line(f"Warning: LTX folder not found, skipping", tag="waiting")

        if _LTX_DIRECTOR_FOLDER.exists():
            self._service_dir.start(
                str(_LTX_DIRECTOR_FOLDER), stills, "png",
                lambda r: self._on_extraction(r, "DIR"),
            )
        else:
            self._log_line(f"Warning: LTX_Director folder not found, skipping", tag="waiting")

        self._watching = True
        self._set_status("watching")
        self._log_line("Watching LTX + LTX_Director", tag="success")

    def _stop_watchers(self) -> None:
        self._service_ltx.stop()
        self._service_dir.stop()
        self._watching = False
        self._set_status("idle")
        self._log_line("Watcher stopped", tag=None)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_watcher_toggle(self) -> None:
        if self._watcher_enabled_var.get():
            self._start_watchers()
        else:
            self._stop_watchers()
        self._save_settings()

    def _browse_audio(self) -> None:
        path = filedialog.askopenfilename(
            title="Select Audio File",
            filetypes=[("Audio files", "*.wav *.mp3")],
        )
        if path:
            self._audio_path = Path(path)
            self._audio_lbl.configure(text=f"🎵 {self._audio_path.name}")
            self._update_mux_btn()

    def _browse_output(self) -> None:
        folder = filedialog.askdirectory(title="Select Output Folder")
        if folder:
            self._output_folder_var.set(folder)
            self._save_settings()

    def _do_mux(self) -> None:
        if not self._last_video_path or not self._audio_path:
            return
        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            self._log_line("FFmpeg not found — cannot mux", tag="error")
            return
        output_folder = Path(self._output_folder_var.get())
        output_folder.mkdir(parents=True, exist_ok=True)
        output_path = output_folder / f"{self._last_video_path.stem}_audio.mp4"
        job = MuxJob(
            video_path=self._last_video_path,
            audio_path=self._audio_path,
            output_path=output_path,
        )
        self._mux_running = True
        self._update_mux_btn()
        self._log_line(f"Muxing → {output_path.name}...", tag=None)

        def _on_done(result: MuxResult) -> None:
            self._root.after(0, lambda r=result: self._on_mux_result(r))

        threading.Thread(target=run_mux, args=(job, ffmpeg, _on_done), daemon=True).start()

    # ------------------------------------------------------------------
    # Result callbacks (always called on main thread)
    # ------------------------------------------------------------------

    def _on_extraction(self, result: ExtractionResult, source: str) -> None:
        if result.success and result.output_path:
            self._log_line(f"✓ {result.output_path.name}", tag="success", source=source)
            self._last_video_path = result.job.source_path
            self._last_output_path = result.output_path
            self._update_preview(result.output_path, source)
            self._update_mux_btn()
        else:
            self._log_line(
                f"✗ {result.job.source_path.name}: {result.error}", tag="error", source=source
            )

    def _on_mux_result(self, result: MuxResult) -> None:
        self._mux_running = False
        if result.success:
            self._log_line(f"✓ Mux complete: {result.job.output_path.name}", tag="success")
        else:
            self._log_line(f"✗ Mux failed: {result.error}", tag="error")
        self._update_mux_btn()

    # ------------------------------------------------------------------
    # UI updates
    # ------------------------------------------------------------------

    def _log_line(self, text: str, tag: str | None, source: str = "") -> None:
        ts = datetime.datetime.now().strftime("%H:%M")
        src_tag = f"  [{source}]" if source else ""
        self._feed.configure(state="normal")
        self._feed.insert("end", f"{ts}{src_tag}  {text}\n", tag or "")
        self._feed.see("end")
        self._feed.configure(state="disabled")

    def _update_preview(self, path: Path, source: str) -> None:
        try:
            with Image.open(path) as src:
                src.thumbnail((120, 72), Image.Resampling.LANCZOS)
                img = src.copy()
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
            self._thumb_lbl.configure(image=ctk_img, text="")
            self._thumb_lbl._ctk_image = ctk_img  # prevent GC
            self._frame_name_lbl.configure(text=path.name)
            self._frame_source_lbl.configure(
                text=f"{source} · {datetime.datetime.now().strftime('%H:%M')}"
            )
            self._open_btn.configure(state="normal")
        except Exception as exc:
            logger.warning("Preview update failed: %s", exc)

    def _set_status(self, state: str) -> None:
        self._status_lbl.configure(
            text=_STATUS_LABELS.get(state, "● Idle"),
            text_color=_STATUS_COLOURS.get(state, ("gray80", "gray40")),
        )

    def _open_in_viewer(self) -> None:
        if self._last_output_path and self._last_output_path.exists():
            os.startfile(str(self._last_output_path))

    def _save_settings(self) -> None:
        s = settings_manager.load()
        s["pipeline_output_folder"] = self._output_folder_var.get()
        s["pipeline_watcher_enabled"] = bool(self._watcher_enabled_var.get())
        settings_manager.save(s)
```

- [ ] **Step 4: Run tests — verify they pass**

```
python -m pytest tests/test_pipeline_ui.py -v
```

Expected: `7 passed`

- [ ] **Step 5: Commit**

```
git add pipeline/ui.py tests/test_pipeline_ui.py
git commit -m "feat: add PipelineTab UI class with find_latest_audio and mux button logic"
```

---

### Task 5: Wire `PipelineTab` into `app.py`

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Add the import**

In `app.py`, find the existing import block near the top. After the `VideoToolsTab` import line:

```python
from video_tools.ui import VideoToolsTab
```

Add:

```python
from pipeline.ui import PipelineTab
```

- [ ] **Step 2: Add the tab**

Find the block where tabs are added:

```python
        self._tabview.add("Video Tools")
```

Immediately after that line, add:

```python
        self._tabview.add("Pipeline")
```

Then find where `VideoToolsTab` is instantiated:

```python
        VideoToolsTab(self._tabview.tab("Video Tools"), self)
```

Immediately after that line, add:

```python
        PipelineTab(self._tabview.tab("Pipeline"), self)
```

- [ ] **Step 3: Run the full test suite**

```
python -m pytest tests/ -v --ignore=tests/test_resolve_bridge.py 2>&1 | tail -20
```

Expected: all tests pass (329+ passed, 0 failed).

- [ ] **Step 4: Commit**

```
git add app.py
git commit -m "feat: add Pipeline tab to app"
```

---

### Task 6: Full verification

**Files:** none — run-only step

- [ ] **Step 1: Run all pipeline tests in isolation**

```
python -m pytest tests/test_pipeline_models.py tests/test_pipeline_mux_runner.py tests/test_pipeline_ui.py -v
```

Expected: `18 passed` (3 + 8 + 7)

- [ ] **Step 2: Run full suite**

```
python -m pytest tests/ -v --ignore=tests/test_resolve_bridge.py 2>&1 | tail -10
```

Expected: all tests pass.

- [ ] **Step 3: Check git log**

```
git log --oneline -8
```

Expected commits (newest first):
```
feat: add Pipeline tab to app
feat: add PipelineTab UI class with find_latest_audio and mux button logic
feat: add pipeline settings keys to settings_manager defaults
feat: add pipeline mux_runner with build_mux_command and run_mux
feat: add pipeline package scaffold and MuxJob/MuxResult models
```

- [ ] **Step 4: Done**

The Pipeline tab is complete. To smoke-test manually: launch `app.py`, click the Pipeline tab, toggle Enable Watcher — both folders (if they exist) should start watching, and any completed renders should trigger last-frame extraction and enable the Mux button.
