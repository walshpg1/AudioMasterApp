# YouTube Audio Import — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "YouTube Import" tab to AudioMasterApp that downloads audio via yt-dlp and lets the user load it into the Single File mastering tab.

**Architecture:** A new `youtube_import/` package mirrors the existing `video_tools/` and `pipeline/` packages — pure-logic modules (`models.py`, `downloader.py`) separate from the UI (`ui.py`). The UI tab class follows the established `SomethingTab(parent, root)` pattern used by `VideoToolsTab` and `PipelineTab`. A background daemon thread runs yt-dlp; all UI callbacks marshal back to the main thread via `root.after(0, callback)`.

**Tech Stack:** Python 3.11+, CustomTkinter, yt-dlp binary (subprocess), FFmpeg binary (via `--ffmpeg-location`), `threading.Event` for cancellation, `dataclasses`, `re`, `shutil.which` for tool discovery.

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `youtube_import/__init__.py` | Empty package marker |
| Create | `youtube_import/models.py` | `DownloadJob`, `DownloadResult` dataclasses |
| Create | `youtube_import/downloader.py` | `find_ytdlp()`, `parse_progress_line()`, `parse_destination_line()`, `YoutubeDownloader` |
| Create | `youtube_import/ui.py` | `YouTubeImportTab(parent, root)` |
| Create | `tests/test_yt_downloader.py` | Unit tests — pure logic only |
| Modify | `settings_manager.py` | Add 2 keys to `_defaults()` |
| Modify | `app.py` | 4 additions: import, tab register, tab init, bridge method |

---

## Task 1: Package skeleton + DownloadResult dataclass

**Files:**
- Create: `youtube_import/__init__.py`
- Create: `youtube_import/models.py`
- Create: `tests/test_yt_downloader.py`

- [ ] **Step 1: Create the empty package marker**

```python
# youtube_import/__init__.py
# (empty file)
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_yt_downloader.py`:

```python
from __future__ import annotations
from pathlib import Path
from youtube_import.models import DownloadJob, DownloadResult


def test_download_result_defaults():
    result = DownloadResult(success=False, output_path=None, error=None, log_lines=[])
    assert result.success is False
    assert result.output_path is None
    assert result.error is None
    assert result.log_lines == []
```

- [ ] **Step 3: Run test to verify it fails**

```
cd D:\AIStudio\Apps\AudioMasterApp
.venv\Scripts\python.exe -m pytest tests/test_yt_downloader.py::test_download_result_defaults -v
```

Expected: `FAILED` — `ModuleNotFoundError: No module named 'youtube_import'`

- [ ] **Step 4: Write minimal implementation**

Create `youtube_import/models.py`:

```python
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DownloadJob:
    url: str
    output_format: str      # "mp3" | "wav" | "flac"
    output_dir: Path
    ffmpeg_path: str
    ytdlp_path: str


@dataclass
class DownloadResult:
    success: bool
    output_path: Path | None
    error: str | None
    log_lines: list[str] = field(default_factory=list)
```

- [ ] **Step 5: Run test to verify it passes**

```
.venv\Scripts\python.exe -m pytest tests/test_yt_downloader.py::test_download_result_defaults -v
```

Expected: `PASSED`

- [ ] **Step 6: Commit**

```
git add youtube_import/__init__.py youtube_import/models.py tests/test_yt_downloader.py
git commit -m "feat: add youtube_import package skeleton and data models"
```

---

## Task 2: find_ytdlp() and path constants

**Files:**
- Create: `youtube_import/downloader.py`
- Modify: `tests/test_yt_downloader.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_yt_downloader.py`:

```python
import sys
from unittest.mock import patch

from youtube_import.downloader import find_ytdlp


def test_find_ytdlp_missing():
    with patch("shutil.which", return_value=None):
        with patch.object(sys, "frozen", False, create=True):
            result = find_ytdlp()
    assert result is None
```

- [ ] **Step 2: Run test to verify it fails**

```
.venv\Scripts\python.exe -m pytest tests/test_yt_downloader.py::test_find_ytdlp_missing -v
```

Expected: `FAILED` — `ModuleNotFoundError: No module named 'youtube_import.downloader'`

- [ ] **Step 3: Write minimal implementation**

Create `youtube_import/downloader.py`:

```python
from __future__ import annotations
import logging
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable

from youtube_import.models import DownloadJob, DownloadResult

logger = logging.getLogger(__name__)

OUTPUTS_ROOT  = Path(r"D:\AIStudio\Outputs")
DOWNLOADS_DIR = OUTPUTS_ROOT / "audio" / "downloads"


def find_ytdlp() -> str | None:
    """Locate yt-dlp binary. Checks PyInstaller bundle dir first, then PATH."""
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        candidate = exe_dir / "yt-dlp.exe"
        if candidate.exists():
            return str(candidate)
    return shutil.which("yt-dlp")
```

- [ ] **Step 4: Run test to verify it passes**

```
.venv\Scripts\python.exe -m pytest tests/test_yt_downloader.py::test_find_ytdlp_missing -v
```

Expected: `PASSED`

- [ ] **Step 5: Commit**

```
git add youtube_import/downloader.py tests/test_yt_downloader.py
git commit -m "feat: add find_ytdlp() and output path constants"
```

---

## Task 3: parse_progress_line()

**Files:**
- Modify: `youtube_import/downloader.py`
- Modify: `tests/test_yt_downloader.py`

- [ ] **Step 1: Write the five failing tests**

Append to `tests/test_yt_downloader.py`:

```python
from youtube_import.downloader import parse_progress_line


def test_parse_progress_download():
    result = parse_progress_line("[download]  47.3% of ~5.00MiB")
    assert result == ("downloading", 0.473)


def test_parse_progress_converting_ffmpeg():
    result = parse_progress_line("[ffmpeg] Merging formats into output.mp3")
    assert result == ("converting", None)


def test_parse_progress_converting_extract():
    result = parse_progress_line("[ExtractAudio] Destination: track.mp3")
    assert result == ("converting", None)


def test_parse_progress_irrelevant_line():
    result = parse_progress_line("[youtube] Extracting URL: https://youtube.com/watch?v=abc")
    assert result is None


def test_parse_progress_100_percent():
    result = parse_progress_line("[download] 100% of 5.00MiB")
    assert result == ("downloading", 1.0)
```

- [ ] **Step 2: Run tests to verify all fail**

```
.venv\Scripts\python.exe -m pytest tests/test_yt_downloader.py::test_parse_progress_download tests/test_yt_downloader.py::test_parse_progress_converting_ffmpeg tests/test_yt_downloader.py::test_parse_progress_converting_extract tests/test_yt_downloader.py::test_parse_progress_irrelevant_line tests/test_yt_downloader.py::test_parse_progress_100_percent -v
```

Expected: all `FAILED` — `ImportError: cannot import name 'parse_progress_line'`

- [ ] **Step 3: Write minimal implementation**

Add to `youtube_import/downloader.py` after the `find_ytdlp` function:

```python
def parse_progress_line(line: str) -> tuple[str, float | None] | None:
    """
    "[download]  47.3% ..."  -> ("downloading", 0.473)
    "[ffmpeg] ..."           -> ("converting", None)
    "[ExtractAudio] ..."     -> ("converting", None)
    anything else            -> None
    """
    stripped = line.strip()
    if stripped.startswith("[download]"):
        m = re.search(r"(\d+\.?\d*)%", stripped)
        if m:
            return ("downloading", float(m.group(1)) / 100.0)
    elif stripped.startswith("[ffmpeg]") or stripped.startswith("[ExtractAudio]"):
        return ("converting", None)
    return None
```

- [ ] **Step 4: Run tests to verify all pass**

```
.venv\Scripts\python.exe -m pytest tests/test_yt_downloader.py::test_parse_progress_download tests/test_yt_downloader.py::test_parse_progress_converting_ffmpeg tests/test_yt_downloader.py::test_parse_progress_converting_extract tests/test_yt_downloader.py::test_parse_progress_irrelevant_line tests/test_yt_downloader.py::test_parse_progress_100_percent -v
```

Expected: all `PASSED`

- [ ] **Step 5: Commit**

```
git add youtube_import/downloader.py tests/test_yt_downloader.py
git commit -m "feat: add parse_progress_line() with tests"
```

---

## Task 4: parse_destination_line()

**Files:**
- Modify: `youtube_import/downloader.py`
- Modify: `tests/test_yt_downloader.py`

- [ ] **Step 1: Write the two failing tests**

Append to `tests/test_yt_downloader.py`:

```python
from youtube_import.downloader import parse_destination_line


def test_parse_destination_line_valid():
    line = r"[ExtractAudio] Destination: D:\AIStudio\Outputs\audio\downloads\my track.mp3"
    result = parse_destination_line(line)
    assert result == Path(r"D:\AIStudio\Outputs\audio\downloads\my track.mp3")


def test_parse_destination_line_irrelevant():
    result = parse_destination_line("[download]  47.3% of ~5.00MiB")
    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

```
.venv\Scripts\python.exe -m pytest tests/test_yt_downloader.py::test_parse_destination_line_valid tests/test_yt_downloader.py::test_parse_destination_line_irrelevant -v
```

Expected: `FAILED` — `ImportError: cannot import name 'parse_destination_line'`

- [ ] **Step 3: Write minimal implementation**

Add to `youtube_import/downloader.py` after `parse_progress_line`:

```python
def parse_destination_line(line: str) -> Path | None:
    """
    "[ExtractAudio] Destination: D:\\path\\to\\song.mp3" -> Path(...)
    anything else -> None
    """
    stripped = line.strip()
    prefix = "[ExtractAudio] Destination: "
    if stripped.startswith(prefix):
        return Path(stripped[len(prefix):])
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

```
.venv\Scripts\python.exe -m pytest tests/test_yt_downloader.py::test_parse_destination_line_valid tests/test_yt_downloader.py::test_parse_destination_line_irrelevant -v
```

Expected: both `PASSED`

- [ ] **Step 5: Run all tests in the file to confirm nothing regressed**

```
.venv\Scripts\python.exe -m pytest tests/test_yt_downloader.py -v
```

Expected: all 9 tests `PASSED`

- [ ] **Step 6: Commit**

```
git add youtube_import/downloader.py tests/test_yt_downloader.py
git commit -m "feat: add parse_destination_line() with tests"
```

---

## Task 5: YoutubeDownloader.run()

**Files:**
- Modify: `youtube_import/downloader.py`

No unit tests for this method — it spawns a real subprocess. Pure-logic helpers are already covered by Tasks 2–4.

- [ ] **Step 1: Add the YoutubeDownloader class**

Append to `youtube_import/downloader.py` (after the pure functions):

```python
class YoutubeDownloader:
    def run(
        self,
        job: DownloadJob,
        progress_cb: Callable[[str, float | None], None],
        done_cb: Callable[[DownloadResult], None],
        cancel_event: threading.Event | None = None,
    ) -> None:
        cmd = [
            job.ytdlp_path,
            "-x",
            "--audio-format", job.output_format,
            "--audio-quality", "0",
            "--ffmpeg-location", job.ffmpeg_path,
            "--output", str(job.output_dir / "%(title)s.%(ext)s"),
            "--no-playlist",
            "--progress",
            job.url,
        ]
        logger.info("[yt-dlp cmd] %s", " ".join(cmd))
        job.output_dir.mkdir(parents=True, exist_ok=True)

        log_lines: list[str] = []
        output_path: Path | None = None

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            cancelled = False
            for line in proc.stdout:
                stripped = line.rstrip("\n")
                logger.debug("[yt-dlp out] %s", stripped)
                log_lines.append(stripped)

                if cancel_event and cancel_event.is_set():
                    proc.kill()
                    proc.wait()
                    cancelled = True
                    break

                dest = parse_destination_line(stripped)
                if dest is not None:
                    output_path = dest

                parsed = parse_progress_line(stripped)
                if parsed is not None:
                    progress_cb(parsed[0], parsed[1])

            if cancelled:
                done_cb(DownloadResult(
                    success=False, output_path=None,
                    error="Cancelled", log_lines=log_lines,
                ))
                return

            stderr_output = proc.stderr.read()
            for err_line in stderr_output.splitlines():
                logger.debug("[yt-dlp err] %s", err_line)
            proc.wait()

            logger.info("[yt-dlp done] returncode=%d output_path=%s", proc.returncode, output_path)

            if proc.returncode == 0 and output_path and output_path.exists():
                done_cb(DownloadResult(
                    success=True, output_path=output_path,
                    error=None, log_lines=log_lines,
                ))
            else:
                error_msg = stderr_output.strip() or f"yt-dlp exited with code {proc.returncode}"
                done_cb(DownloadResult(
                    success=False, output_path=None,
                    error=error_msg[:200], log_lines=log_lines,
                ))

        except Exception as exc:
            logger.error("[yt-dlp done] exception: %s", exc)
            done_cb(DownloadResult(
                success=False, output_path=None,
                error=str(exc), log_lines=log_lines,
            ))
```

- [ ] **Step 2: Run all downloader tests to confirm nothing regressed**

```
.venv\Scripts\python.exe -m pytest tests/test_yt_downloader.py -v
```

Expected: all 9 tests `PASSED`

- [ ] **Step 3: Commit**

```
git add youtube_import/downloader.py
git commit -m "feat: add YoutubeDownloader.run() with cancellation support"
```

---

## Task 6: settings_manager additions

**Files:**
- Modify: `settings_manager.py`
- Modify: `tests/test_settings_manager.py`

- [ ] **Step 1: Write the failing tests**

Open `tests/test_settings_manager.py` and append:

```python
import settings_manager


def test_defaults_include_youtube_output_format():
    defaults = settings_manager._defaults()
    assert "youtube_output_format" in defaults
    assert defaults["youtube_output_format"] == "mp3"


def test_defaults_include_youtube_last_url():
    defaults = settings_manager._defaults()
    assert "youtube_last_url" in defaults
    assert defaults["youtube_last_url"] == ""
```

- [ ] **Step 2: Run the tests to verify they fail**

```
.venv\Scripts\python.exe -m pytest tests/test_settings_manager.py::test_defaults_include_youtube_output_format tests/test_settings_manager.py::test_defaults_include_youtube_last_url -v
```

Expected: both `FAILED` — `AssertionError: assert 'youtube_output_format' in {...}`

- [ ] **Step 3: Add the two keys to `_defaults()` in `settings_manager.py`**

Find the return dict in `_defaults()` (around line 36) and add the two new keys at the end of the dict, before the closing brace:

```python
        # YouTube Import
        "youtube_output_format": "mp3",   # last selected format
        "youtube_last_url":      "",      # last pasted URL (UX convenience)
```

The `_defaults()` function return block should end like this:

```python
        # Pipeline
        "pipeline_output_folder": r"D:\AIStudio\Outputs\video\exports\tiktok",
        "pipeline_watcher_enabled": False,
        # YouTube Import
        "youtube_output_format": "mp3",
        "youtube_last_url":      "",
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```
.venv\Scripts\python.exe -m pytest tests/test_settings_manager.py::test_defaults_include_youtube_output_format tests/test_settings_manager.py::test_defaults_include_youtube_last_url -v
```

Expected: both `PASSED`

- [ ] **Step 5: Run all settings tests**

```
.venv\Scripts\python.exe -m pytest tests/test_settings_manager.py -v
```

Expected: all pass (one pre-existing failure `test_load_returns_none_for_path_fields` is unrelated and was failing before this work).

- [ ] **Step 6: Commit**

```
git add settings_manager.py tests/test_settings_manager.py
git commit -m "feat: add youtube_output_format and youtube_last_url settings defaults"
```

---

## Task 7: app.py — 4 additions

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Add the import**

In `app.py`, after the existing tab imports (around line 34, after `from narration_analysis.ui import NarrationAnalysisTab`), add:

```python
from youtube_import.ui import YouTubeImportTab
```

- [ ] **Step 2: Register the tab**

In `_build_ui()` (around line 148, after `self._tabview.add("Narration Analysis")`), add:

```python
        self._tabview.add("YouTube Import")
```

- [ ] **Step 3: Initialise the tab**

In `_build_ui()` (around line 156, after `self._narration_tab = NarrationAnalysisTab(...)`), add:

```python
        YouTubeImportTab(self._tabview.tab("YouTube Import"), self)
```

- [ ] **Step 4: Add the bridge method**

At the end of the `App` class, before `if __name__ == "__main__":`, add:

```python
    def load_file_for_mastering(self, path: Path) -> None:
        """Switch to Single File tab and pre-load a downloaded file."""
        self._wav_path = str(path)
        self._file_label.configure(text=path.name)
        self._master_btn.configure(state="normal")
        self._master_split_btn.configure(state="normal")
        self._tabview.set("Single File")
```

- [ ] **Step 5: Smoke-test that the app launches**

```
.venv\Scripts\python.exe app.py
```

Expected: AudioMasterApp opens with a "YouTube Import" tab visible in the tab bar. No import errors in the console.

- [ ] **Step 6: Commit**

```
git add app.py
git commit -m "feat: register YouTubeImportTab and add load_file_for_mastering bridge"
```

---

## Task 8: YouTubeImportTab UI

**Files:**
- Create: `youtube_import/ui.py`

No unit tests for the UI — it requires a live Tk mainloop.

- [ ] **Step 1: Write the full UI implementation**

Create `youtube_import/ui.py`:

```python
from __future__ import annotations
import logging
import os
import threading
from pathlib import Path

import customtkinter as ctk

import settings_manager
from ffmpeg_utils import find_ffmpeg
from youtube_import.downloader import find_ytdlp, YoutubeDownloader, DOWNLOADS_DIR
from youtube_import.models import DownloadJob, DownloadResult

logger = logging.getLogger(__name__)

_LEGAL_NOTE = (
    "⚠  Only download audio you own, have permission to use,\n"
    "   or that is royalty-free / public-domain."
)

_IDLE        = "IDLE"
_DOWNLOADING = "DOWNLOADING"
_CONVERTING  = "CONVERTING"
_COMPLETE    = "COMPLETE"
_FAILED      = "FAILED"
_CANCELLED   = "CANCELLED"


class YouTubeImportTab:
    def __init__(self, parent, root) -> None:
        self._root  = root
        self._state = _IDLE
        self._output_path: Path | None = None
        self._cancel_event: threading.Event | None = None

        self._ytdlp_path  = find_ytdlp()
        self._ffmpeg_path = find_ffmpeg()

        self._build_ui(parent)
        self._apply_tool_state()
        self._load_settings()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self, parent) -> None:
        pad = {"padx": 12, "pady": 4}

        # URL section
        url_section = ctk.CTkFrame(parent)
        url_section.pack(fill="x", **pad)
        ctk.CTkLabel(url_section, text="URL", anchor="w").pack(
            anchor="w", padx=8, pady=(8, 2)
        )
        url_row = ctk.CTkFrame(url_section, fg_color="transparent")
        url_row.pack(fill="x", padx=8, pady=(0, 8))
        self._url_entry = ctk.CTkEntry(
            url_row, placeholder_text="paste YouTube URL here…"
        )
        self._url_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(
            url_row, text="Clear", width=70, command=self._clear_url
        ).pack(side="right")

        # Format selection
        fmt_section = ctk.CTkFrame(parent)
        fmt_section.pack(fill="x", **pad)
        ctk.CTkLabel(fmt_section, text="Output Format", anchor="w").pack(
            side="left", padx=8, pady=8
        )
        self._format_var = ctk.StringVar(value="mp3")
        for fmt in ("mp3", "wav", "flac"):
            ctk.CTkRadioButton(
                fmt_section, text=fmt.upper(),
                variable=self._format_var, value=fmt,
                command=self._on_format_change,
            ).pack(side="left", padx=8)

        # Tool warning label (packed only when a tool is missing)
        self._tool_warning_lbl = ctk.CTkLabel(
            parent, text="", anchor="w", justify="left",
            text_color="#FFC107", wraplength=480,
        )

        # Button row
        self._btn_row = ctk.CTkFrame(parent, fg_color="transparent")
        self._btn_row.pack(fill="x", padx=12, pady=4)
        self._download_btn = ctk.CTkButton(
            self._btn_row, text="Download", command=self._on_download
        )
        self._download_btn.pack(side="left")
        self._cancel_btn = ctk.CTkButton(
            self._btn_row, text="Cancel", command=self._on_cancel
        )
        # Cancel is packed/unpacked by _set_state

        # Progress section
        self._progress_frame = ctk.CTkFrame(parent, fg_color="transparent")
        self._progress_frame.pack(fill="x", padx=12)
        self._progress_bar = ctk.CTkProgressBar(self._progress_frame)
        self._progress_bar.set(0)
        # Progress bar is packed/unpacked by _set_state
        self._status_lbl = ctk.CTkLabel(
            self._progress_frame, text="", anchor="w"
        )
        self._status_lbl.pack(fill="x", pady=(2, 0))

        # Separator
        ctk.CTkFrame(parent, height=1, fg_color="gray30").pack(
            fill="x", padx=12, pady=8
        )

        # Result section
        result_section = ctk.CTkFrame(parent, fg_color="transparent")
        result_section.pack(fill="x", padx=12)
        self._output_lbl = ctk.CTkLabel(result_section, text="", anchor="w")
        self._output_lbl.pack(anchor="w")
        self._action_row = ctk.CTkFrame(result_section, fg_color="transparent")
        self._action_row.pack(fill="x", pady=(4, 0))
        ctk.CTkButton(
            self._action_row, text="Open Downloads Folder",
            command=self._open_downloads_folder, width=180,
        ).pack(side="left")
        self._load_btn = ctk.CTkButton(
            self._action_row, text="Load into Single File Mastering",
            command=self._on_load, width=220,
        )
        # Load btn is packed/unpacked by _set_state

        # Separator + legal note
        ctk.CTkFrame(parent, height=1, fg_color="gray30").pack(
            fill="x", padx=12, pady=8
        )
        ctk.CTkLabel(
            parent, text=_LEGAL_NOTE,
            anchor="w", justify="left",
            text_color="gray", font=ctk.CTkFont(size=11),
        ).pack(fill="x", padx=12)

    def _apply_tool_state(self) -> None:
        if self._ytdlp_path and self._ffmpeg_path:
            return  # both tools present — nothing to do

        self._download_btn.pack_forget()

        if not self._ytdlp_path:
            msg = (
                "⚠  yt-dlp not found.\n"
                "   Install with:  pip install yt-dlp   or   winget install yt-dlp\n"
                "   Then restart the app."
            )
        else:
            msg = "⚠  FFmpeg not found. AudioMasterApp requires FFmpeg to be installed."

        self._tool_warning_lbl.configure(text=msg)
        self._tool_warning_lbl.pack(fill="x", padx=12, pady=(4, 0))

    def _load_settings(self) -> None:
        s = getattr(self._root, "_settings", {})
        fmt = s.get("youtube_output_format", "mp3")
        if fmt in ("mp3", "wav", "flac"):
            self._format_var.set(fmt)
        last_url = s.get("youtube_last_url", "")
        if last_url:
            self._url_entry.insert(0, last_url)

    # ------------------------------------------------------------------
    # State machine
    # ------------------------------------------------------------------

    def _set_state(self, state: str) -> None:
        self._state = state
        is_active = state in (_DOWNLOADING, _CONVERTING)

        self._download_btn.configure(state="disabled" if is_active else "normal")

        if is_active:
            self._cancel_btn.pack(side="left", padx=(8, 0))
        else:
            self._cancel_btn.pack_forget()

        if state in (_IDLE, _FAILED, _CANCELLED):
            self._progress_bar.stop()
            self._progress_bar.pack_forget()
        elif state == _COMPLETE:
            self._progress_bar.stop()
            self._progress_bar.configure(mode="determinate")
            self._progress_bar.set(1.0)
            if not self._progress_bar.winfo_ismapped():
                self._progress_bar.pack(fill="x")
        else:  # DOWNLOADING / CONVERTING
            if not self._progress_bar.winfo_ismapped():
                self._progress_bar.pack(fill="x")

        if state == _COMPLETE:
            self._load_btn.pack(side="left", padx=(8, 0))
        else:
            self._load_btn.pack_forget()

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _clear_url(self) -> None:
        self._url_entry.delete(0, "end")

    def _on_format_change(self) -> None:
        if hasattr(self._root, "_settings"):
            self._root._settings["youtube_output_format"] = self._format_var.get()
            settings_manager.save(self._root._settings)

    def _on_download(self) -> None:
        url = self._url_entry.get().strip()
        if not url:
            self._status_lbl.configure(text="Please paste a YouTube URL first.")
            return
        if not self._ytdlp_path or not self._ffmpeg_path:
            return

        if hasattr(self._root, "_settings"):
            self._root._settings["youtube_last_url"] = url
            settings_manager.save(self._root._settings)

        self._cancel_event  = threading.Event()
        self._output_path   = None
        self._output_lbl.configure(text="")
        self._status_lbl.configure(text="Downloading…")
        self._set_state(_DOWNLOADING)

        job = DownloadJob(
            url=url,
            output_format=self._format_var.get(),
            output_dir=DOWNLOADS_DIR,
            ffmpeg_path=self._ffmpeg_path,
            ytdlp_path=self._ytdlp_path,
        )
        cancel_ev = self._cancel_event
        threading.Thread(
            target=self._worker, args=(job, cancel_ev), daemon=True
        ).start()

    def _on_cancel(self) -> None:
        if self._cancel_event:
            self._cancel_event.set()

    def _worker(self, job: DownloadJob, cancel_event: threading.Event) -> None:
        YoutubeDownloader().run(
            job,
            progress_cb=lambda phase, frac: self._root.after(
                0, self._on_progress, phase, frac
            ),
            done_cb=lambda result: self._root.after(0, self._on_done, result),
            cancel_event=cancel_event,
        )

    def _on_progress(self, phase: str, fraction: float | None) -> None:
        if phase == "downloading" and fraction is not None:
            self._progress_bar.configure(mode="determinate")
            self._progress_bar.set(fraction)
            self._status_lbl.configure(
                text=f"Downloading…  {fraction * 100:.0f}%"
            )
        else:
            self._progress_bar.configure(mode="indeterminate")
            self._progress_bar.start()
            label = "Converting…" if phase == "converting" else "Downloading…"
            self._status_lbl.configure(text=label)

    def _on_done(self, result: DownloadResult) -> None:
        self._progress_bar.stop()
        if result.error == "Cancelled":
            self._status_lbl.configure(text="Cancelled")
            self._set_state(_CANCELLED)
        elif result.success and result.output_path:
            self._output_path = result.output_path
            filename = result.output_path.name
            self._output_lbl.configure(text=f"Output:  {filename}")
            self._status_lbl.configure(text=f"Complete — {filename}")
            self._set_state(_COMPLETE)
        else:
            self._status_lbl.configure(
                text=f"Failed: {result.error or 'Unknown error'}"
            )
            self._set_state(_FAILED)

    def _open_downloads_folder(self) -> None:
        DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(str(DOWNLOADS_DIR))

    def _on_load(self) -> None:
        if self._output_path and self._output_path.exists():
            self._root.load_file_for_mastering(self._output_path)
        else:
            self._status_lbl.configure(text="Downloaded file no longer found.")
```

- [ ] **Step 2: Run all tests to confirm nothing regressed**

```
.venv\Scripts\python.exe -m pytest tests/test_yt_downloader.py tests/test_settings_manager.py tests/test_ffmpeg_utils.py -v
```

Expected: all pass (pre-existing `test_load_returns_none_for_path_fields` failure is unrelated).

- [ ] **Step 3: Smoke test the full feature**

```
.venv\Scripts\python.exe app.py
```

Manually verify:
- "YouTube Import" tab is present in the tab bar
- If yt-dlp is not installed: warning message appears instead of Download button
- If yt-dlp is installed: URL field, format radio buttons, and Download button are visible
- Paste a URL and click Download — progress bar appears, Cancel button appears
- Cancel button terminates the download and shows "Cancelled"
- Successful download shows "Complete — {filename}", Load button appears
- Load button switches to Single File tab and pre-fills the filename

- [ ] **Step 4: Commit**

```
git add youtube_import/ui.py
git commit -m "feat: add YouTubeImportTab UI with download/cancel/load flow"
```

---

## Final verification

- [ ] **Run the full test suite**

```
.venv\Scripts\python.exe -m pytest tests/test_yt_downloader.py tests/test_settings_manager.py tests/test_ffmpeg_utils.py tests/test_audio_analysis.py -v
```

Expected: all 9 new tests pass; no regressions in the modules touched by this feature.
