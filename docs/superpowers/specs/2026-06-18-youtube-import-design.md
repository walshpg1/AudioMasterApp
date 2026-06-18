# YouTube Audio Import — Feature Design
**Date:** 2026-06-18
**App:** AudioMasterApp
**Status:** Approved — ready for implementation

---

## 1. Overview

Add a "YouTube Import" tab to AudioMasterApp that lets the user paste a YouTube URL, choose an output format (MP3 / WAV / FLAC), and download the audio using yt-dlp. The downloaded file is saved to `D:\AIStudio\Outputs\audio\downloads`. After a successful download the user can load the file directly into the Single File mastering tab with one click.

---

## 2. Scope

**In scope:**
- New `youtube_import/` package (ui, downloader, models)
- Minimal additions to `app.py`, `settings_manager.py`
- Unit tests for all pure-logic functions
- yt-dlp and FFmpeg presence validation with clear install instructions

**Out of scope (Phase 2):**
- Auto-mastering on download completion
- Batch/staging folder queue
- Playlist support (single video only for v1 — `--no-playlist` enforced)
- yt-dlp Python library (binary subprocess only)
- Manual separate FFmpeg conversion step

---

## 3. Module Structure

```
AudioMasterApp/
  youtube_import/
    __init__.py           # empty
    models.py             # DownloadJob, DownloadResult dataclasses
    downloader.py         # find_ytdlp(), YoutubeDownloader
    ui.py                 # YouTubeImportTab(parent, root)
  tests/
    test_yt_downloader.py # unit tests — pure logic only
```

Changes to existing files:
- `app.py` — 4 additions (import, tab register, tab init, bridge method)
- `settings_manager.py` — 2 new default keys
- `ffmpeg_utils.py` — no changes

---

## 4. Service Layer (`downloader.py`)

### Tool Discovery

```python
def find_ytdlp() -> str | None:
    """Locate yt-dlp binary. Checks PyInstaller bundle dir first, then PATH."""
```

Mirrors `ffmpeg_utils.find_ffmpeg()` exactly.

### Data Classes (`models.py`)

```python
@dataclass
class DownloadJob:
    url: str
    output_format: str      # "mp3" | "wav" | "flac"
    output_dir: Path
    ffmpeg_path: str

@dataclass
class DownloadResult:
    success: bool
    output_path: Path | None
    error: str | None
    log_lines: list[str]
```

### yt-dlp Command

```
yt-dlp
  -x
  --audio-format <format>
  --audio-quality 0
  --ffmpeg-location <ffmpeg_path>
  --output "<output_dir>/%(title)s.%(ext)s"
  --no-playlist
  --progress
  <url>
```

Full command is logged with a `[yt-dlp cmd]` prefix. URL is included — this runs on the user's own machine.

### Progress Parsing (pure function)

```python
def parse_progress_line(line: str) -> tuple[str, float] | None:
    """
    "[download]  47.3% ..."  → ("downloading", 0.473)
    "[ffmpeg] ..."           → ("converting", None)
    "[ExtractAudio] ..."     → ("converting", None)
    anything else            → None
    """
```

Phase switches from "downloading" to "converting" when `[ffmpeg]` or `[ExtractAudio]` appears.

### Filename Capture (pure function)

```python
def parse_destination_line(line: str) -> Path | None:
    """
    "[ExtractAudio] Destination: D:\\path\\to\\song.mp3"  → Path("D:\\path\\to\\song.mp3")
    anything else                                          → None
    """
```

`YoutubeDownloader.run()` calls this on every stdout line. The last non-`None` result becomes `result.output_path`. This avoids scanning the directory for the newest file and is robust to filenames with spaces.

### `YoutubeDownloader.run()`

Signature:
```python
def run(
    self,
    job: DownloadJob,
    progress_cb: Callable[[str, float | None], None],
    done_cb: Callable[[DownloadResult], None],
    cancel_event: threading.Event | None = None,
) -> None:
```

- Runs yt-dlp subprocess, reads stdout line-by-line
- Calls `progress_cb(phase, fraction)` for each parsed progress line
- Captures `output_path` from `[ExtractAudio] Destination:` lines (see above)
- Checks `cancel_event` after each line; if set, kills the subprocess and returns `DownloadResult(success=False, error="Cancelled")`
- Calls `done_cb(result)` — **caller** is responsible for marshalling to main thread via `root.after()`

---

## 5. UI Tab (`ui.py`)

### Layout

```
YouTube Audio Import
────────────────────────────────────────────────
URL
[ paste YouTube URL here...           ] [Clear]

Output Format    ○ MP3   ○ WAV   ○ FLAC

[ Download ]

████████████████░░░░░░░░  47%   Downloading…

────────────────────────────────────────────────
Output:  track_name.mp3
[ Open Downloads Folder ]  [ Load into Single File Mastering ]

────────────────────────────────────────────────
⚠ Only download audio you own, have permission to use,
  or that is royalty-free / public-domain.
```

### State Machine

| State | Progress bar | Status text | Download btn | Cancel btn | Load btn |
|---|---|---|---|---|---|
| `IDLE` | hidden | — | enabled | hidden | hidden |
| `DOWNLOADING` | indeterminate→% | "Downloading…" | disabled | visible | hidden |
| `CONVERTING` | indeterminate | "Converting…" | disabled | visible | hidden |
| `COMPLETE` | 1.0 | "Complete — {filename}" | enabled | hidden | visible |
| `FAILED` | hidden | "Failed: {reason}" | enabled | hidden | hidden |
| `CANCELLED` | hidden | "Cancelled" | enabled | hidden | hidden |

The Cancel button calls `_cancel_event.set()`, which signals the worker thread to kill the subprocess. The `CANCELLED` state is treated like `FAILED` for UI purposes (Download re-enabled, no Load button).

### Missing Tool States

Shown on tab load, replaces Download button:

**yt-dlp missing:**
```
⚠ yt-dlp not found.
  Install with:  pip install yt-dlp   or   winget install yt-dlp
  Then restart the app.
```

**FFmpeg missing:**
```
⚠ FFmpeg not found. AudioMasterApp requires FFmpeg to be installed.
```

Both checks run once during `__init__`. If either tool is missing, the Download button is hidden and the warning label is shown.

### Thread Flow

```
[Download clicked]
  → validate URL non-empty
  → set state DOWNLOADING
  → self._cancel_event = threading.Event()
  → threading.Thread(target=_worker, daemon=True).start()

[Cancel clicked]
  → self._cancel_event.set()
  (worker detects this and kills subprocess)

[_worker — background thread]
  → YoutubeDownloader().run(
        job,
        progress_cb  = lambda phase, frac: root.after(0, self._on_progress, phase, frac),
        done_cb      = lambda result:       root.after(0, self._on_done, result),
        cancel_event = self._cancel_event,
    )

[_on_progress — main thread via after()]
  → update progress bar + status label

[_on_done — main thread via after()]
  → set state COMPLETE, FAILED, or CANCELLED
  → store result.output_path
  → show/hide Load button
```

---

## 6. `app.py` Integration (4 additions)

```python
# 1. Import
from youtube_import.ui import YouTubeImportTab

# 2. Tab registration
self._tabview.add("YouTube Import")

# 3. Tab initialisation
YouTubeImportTab(self._tabview.tab("YouTube Import"), self)

# 4. Public bridge method
def load_file_for_mastering(self, path: Path) -> None:
    """Switch to Single File tab and pre-load a file for mastering."""
    self._wav_path = path
    self._input_file_label.configure(text=str(path))
    self._analyse_btn.configure(state="normal")
    self._tabview.set("Single File")
```

No other changes to `app.py`.

---

## 7. `settings_manager.py` Additions

Two new keys in `_defaults()`:

```python
"youtube_output_format": "mp3",   # last selected format
"youtube_last_url":      "",      # last pasted URL (UX convenience)
```

Output directory (`D:\AIStudio\Outputs\audio\downloads`) is a constant in `downloader.py` — not user-configurable in v1.

---

## 8. Output Directory

```python
# downloader.py
OUTPUTS_ROOT   = Path(r"D:\AIStudio\Outputs")
DOWNLOADS_DIR  = OUTPUTS_ROOT / "audio" / "downloads"
```

`OUTPUTS_ROOT` mirrors the same root used by the rest of the AIStudio toolchain. `DOWNLOADS_DIR` is the only constant used throughout the feature — never a string literal. Created with `Path.mkdir(parents=True, exist_ok=True)` at download time, not at app startup.

---

## 9. Logging

- Log file: standard app log (rotating, existing handler)
- `[yt-dlp cmd]` prefix for the full command line
- `[yt-dlp out]` prefix for each stdout line
- `[yt-dlp err]` prefix for stderr
- `[yt-dlp done]` prefix for result summary

---

## 10. Tests (`tests/test_yt_downloader.py`)

Pure-logic only — no network, no subprocess, no Tkinter:

| Test | Covers |
|---|---|
| `test_find_ytdlp_missing` | Returns `None` when not on PATH |
| `test_parse_progress_download` | `"[download]  47.3%…"` → `("downloading", 0.473)` |
| `test_parse_progress_converting_ffmpeg` | `"[ffmpeg] Merging…"` → `("converting", None)` |
| `test_parse_progress_converting_extract` | `"[ExtractAudio]…"` → `("converting", None)` |
| `test_parse_progress_irrelevant_line` | Random line → `None` |
| `test_parse_progress_100_percent` | `"[download] 100%"` → `("downloading", 1.0)` |
| `test_download_result_defaults` | Dataclass initialises with `success=False, output_path=None` |
| `test_parse_destination_line_valid` | `"[ExtractAudio] Destination: D:\path\song.mp3"` → `Path(...)` |
| `test_parse_destination_line_irrelevant` | Unrelated line → `None` |

---

## 11. Constraints

- `--no-playlist` is always passed — single video only in v1
- No auto-mastering triggered on download completion
- No yt-dlp Python library — binary subprocess only
- No separate manual FFmpeg step — yt-dlp handles conversion via `--ffmpeg-location`
- Output path resolved from `[ExtractAudio] Destination:` stdout line — no directory scanning
- Cancellation via `threading.Event` + subprocess kill — no force-termination of ffmpeg separately
- Output dir derived from `OUTPUTS_ROOT` constant — no hardcoded path strings in logic code
