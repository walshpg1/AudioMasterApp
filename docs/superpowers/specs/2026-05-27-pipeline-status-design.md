# Pipeline Status View — Design Spec
**Date:** 2026-05-27
**App:** AudioMasterApp
**Feature:** Pipeline tab — LTX render monitoring, last-frame extraction, audio+video mux

---

## Overview

Add a **Pipeline** tab to AudioMasterApp that monitors both LTX render output folders, auto-extracts the last frame from each completed `.mp4`, displays the most recent mastered audio file, and provides a one-click FFmpeg mux to combine them into a finished `video+audio.mp4`.

This is a pure extension — no existing functionality is modified.

---

## Decisions Made

| Question | Decision | Reason |
|---|---|---|
| Where it lives | New "Pipeline" tab | Clean separation — Video Tools stays general-purpose |
| Folders watched | Both `renders\video\LTX\` and `renders\video\LTX_Director\` | Both workflows in use |
| Audio pairing | Display + mux button | User wants to see them paired and combine when ready |
| Architecture | New `pipeline/` package reusing `video_tools/` | No duplication, clean boundaries |
| Watch folder config | Hardcoded LTX paths, not browseable | These folders never change |
| Audio detection | Auto-detect newest file in `audio\processed\`, overrideable | Always picks up latest master |
| Mux output | `{video_stem}_audio.mp4` in configurable folder, default `exports\tiktok\` | Matches primary export target |

---

## File Structure

```
AudioMasterApp/
├── app.py                          ← 2-line change: add tab + import
├── pipeline/
│   ├── __init__.py                 ← empty, marks as package
│   ├── models.py                   ← MuxJob, MuxResult dataclasses
│   ├── mux_runner.py               ← build_mux_command(), run_mux()
│   └── ui.py                       ← PipelineTab class
└── tests/
    ├── test_pipeline_models.py
    ├── test_pipeline_mux_runner.py
    └── test_pipeline_ui.py
```

---

## Architecture

### Data Flow

```
PipelineTab
    ├── ExtractionService (LTX)      ← reused from video_tools
    │       └── VideoWatcher → renders\video\LTX\
    ├── ExtractionService (Director) ← reused from video_tools
    │       └── VideoWatcher → renders\video\LTX_Director\
    └── mux_runner.run_mux()
            └── subprocess.run(ffmpeg_cmd)
                → MuxResult
                → root.after(0, on_mux_result)
                → UI update (feed, status)
```

Two `ExtractionService` instances run in parallel, both reporting into the same activity feed. Neither shares mutable state with the other or with the UI — all callbacks go through `root.after(0, ...)`.

### Integration in `app.py`

Two lines added, nothing removed:

```python
from pipeline.ui import PipelineTab        # new import

self._tabview.add("Pipeline")              # new tab
PipelineTab(self._tabview.tab("Pipeline"), self)
```

---

## Package Internals

### `models.py`

```python
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

### `mux_runner.py`

**`build_mux_command(job, ffmpeg="ffmpeg") -> list[str]`**

Pure function — no side effects, fully testable.

```python
["ffmpeg", "-i", str(job.video_path), "-i", str(job.audio_path),
 "-c:v", "copy", "-c:a", "aac", "-shortest", str(job.output_path)]
```

- `-c:v copy` — no video re-encode, preserves LTX quality
- `-c:a aac` — encodes audio to AAC for broad compatibility
- `-shortest` — trims output to the shorter of video/audio
- No `shell=True`. Paths are always list items.

**`run_mux(job, ffmpeg_path, on_done) -> None`**

Runs in a caller-supplied daemon thread. Calls `on_done(MuxResult)` exactly once. No retry logic (mux failures are user-actionable — wrong file, unwritable folder).

### `ui.py` — `PipelineTab`

Plain class (not a `ctk.CTkFrame` subclass). Receives tab frame and Tk root.

#### Layout (top to bottom)

```
┌─────────────────────────────────────────────────┐
│ LTX Render Watcher          ● Watching  [Enable] │
│ renders\video\LTX\ & LTX_Director\              │
├─────────────────────────────────────────────────┤
│ Render Feed (scrollable CTkTextbox, read-only)   │
│  14:22  [LTX] ✓ render_001.mp4 → frame saved   │
│  14:25  [DIR] ✓ render_002.mp4 → frame saved   │
│  14:31  [LTX] ⏳ render_003.mp4 — still writing │
├─────────────────────────────────────────────────┤
│ [thumbnail 120×72]  render_002_lastframe.png     │
│                     DIR · 14:25  [Open in Viewer]│
├─────────────────────────────────────────────────┤
│ Audio Master                                     │
│ 🎵 audio_master_v3.wav (auto-detected) [Browse] │
├─────────────────────────────────────────────────┤
│ Output: exports\tiktok\               [Browse]   │
│ [      Mux Video + Audio →           ]           │
└─────────────────────────────────────────────────┘
```

#### Feed entries

Each line: `HH:MM  [LTX|DIR]  {message}` with colour tags:
- Green (`#4CAF50`) — frame extracted successfully
- Red (`#F44336`) — extraction or mux error
- Amber (`#FFC107`) — file still writing

#### Mux button state machine

| State | Button | Trigger |
|---|---|---|
| No render completed yet | Disabled | Startup |
| Render done, audio present | Enabled | ExtractionResult success |
| Mux running | Disabled | User clicks mux |
| Mux complete | Enabled | MuxResult fires |

The most recently extracted render is used for mux. If multiple renders have completed, the last one wins — user can re-mux by noting which render they want (manual mux not in scope).

#### Audio auto-detection

On startup and after each `start()` call: scan `D:\AIStudio\Apps\AIVideoStudio\audio\processed\` for `*.wav` and `*.mp3`, sort by `mtime` descending, pre-fill the audio label with the newest file. User can override with Browse. Not persisted.

#### Output naming

`{video_stem}_audio.mp4` — e.g. `render_002_audio.mp4`. Written to the configured output folder.

---

## Settings — `settings_manager.py` Changes

Two new keys:

```python
"pipeline_output_folder": r"D:\AIStudio\Apps\AIVideoStudio\exports\tiktok",
"pipeline_watcher_enabled": False,
```

Watch folders are hardcoded constants in `ui.py` — not in settings:

```python
_LTX_FOLDER          = Path(r"D:\AIStudio\Apps\AIVideoStudio\renders\video\LTX")
_LTX_DIRECTOR_FOLDER = Path(r"D:\AIStudio\Apps\AIVideoStudio\renders\video\LTX_Director")
_AUDIO_PROCESSED_DIR = Path(r"D:\AIStudio\Apps\AIVideoStudio\audio\processed")
```

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| LTX folder missing on startup | Log warning in feed, that watcher skips silently, other continues |
| LTX_Director folder missing | Same — independent of LTX watcher |
| FFmpeg not found | Feed error, mux button stays disabled |
| Audio file deleted before mux | `MuxResult` with error, red feed entry |
| Output folder unwritable | `MuxResult` with error, red feed entry |
| Render still writing | Watcher stability check prevents premature extraction (inherited from `VideoWatcher`) |

---

## Testing

All tests use `unittest.mock.patch("subprocess.run", ...)` — no real FFmpeg calls.

| File | What it covers |
|---|---|
| `test_pipeline_models.py` | `MuxJob` and `MuxResult` dataclass fields and defaults |
| `test_pipeline_mux_runner.py` | Command structure (copy/aac/shortest), path-with-spaces safety, `on_done` called once on success and failure |
| `test_pipeline_ui.py` | Mux button enabled only after successful extraction, audio auto-detection selects newest file, watcher enable/disable lifecycle |

---

## Constraints

- Do NOT alter any existing audio, batch, watch-folder, or video extraction functionality.
- All existing tests must continue to pass.
- Pipeline is fully isolated in `pipeline/` — removing the package leaves the app intact.
- No `shell=True` anywhere.
- All Tkinter/CTk calls from background threads are prohibited — use `root.after(0, ...)` exclusively.
- Watch folders (`LTX` and `LTX_Director`) are constants, not user-configurable.

---

## Dependencies

All already present:

| Package | Needed for |
|---|---|
| `customtkinter` | UI widgets |
| `video_tools` | `VideoWatcher`, `ExtractionService`, models |
| `ffmpeg_utils` | `find_ffmpeg()` |
| `threading` / `concurrent.futures` | Background mux thread |

---

## Future Expansion

- **Select which render to mux** — replace "last render wins" with a render list UI
- **FLOAT renders** — add a third watcher for `renders\Videos\` (FLOAT pipeline)
- **Batch mux** — queue multiple video+audio pairs
- **Export presets** — TikTok, Reels, Shorts with format-specific FFmpeg flags
