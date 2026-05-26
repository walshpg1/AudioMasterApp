# Clip Splitter — Design Spec
**Date:** 2026-05-26
**Feature:** Master & Split into configurable-length clips from the Single File tab

---

## Overview

Add a "Clip Splitter" panel to the Single File tab that masters the selected file and then cuts the mastered output into equal-length clips. Primary use case is generating social media preview clips (TikTok, Instagram Reels, YouTube Shorts).

---

## Requirements

- Clip duration is configurable by the user (default: 5 seconds); must be a positive number
- Workflow is always **master then split** — the mastered file is produced first, then cut into clips
- The remainder at the end (if the file does not divide evenly) is kept as a shorter clip
- Clips are saved to a subfolder named `{stem}_clips/` inside the shared output folder (e.g. `output/MySong_clips/`)
- Clips are named `{stem}_001.{ext}`, `{stem}_002.{ext}`, … where `ext` matches the selected export format (e.g. `wav`, `mp3`, `flac`)
- The mastered single file is also kept in the output folder as normal
- "Open Clips Folder" button opens the subfolder and is disabled until clips have been generated

---

## Architecture

### New file: `audio_splitter.py`

```python
@dataclass
class SplitResult:
    clips: list[str]       # absolute paths to generated clip files
    clip_count: int
    output_dir: Path
    error: str | None

def split_audio(
    input_path: str,
    clip_duration: float,
    output_dir: Path,
) -> SplitResult:
    ...
```

- Uses FFmpeg's `segment` muxer (`-f segment -segment_time <duration> -reset_timestamps 1`)
- `output_dir` is created if it does not exist
- Returns `SplitResult` with `error` set on failure; does not raise
- No dependency on the mastering engine — accepts any audio file

### `app.py` changes

| Addition | Purpose |
|---|---|
| `_build_clip_splitter_panel()` | Adds the panel to the Single File tab |
| `_run_master_and_split()` | Thread entry point: master → split → update UI |
| `_clip_duration_var` | `StringVar` bound to the duration input field |
| `_last_clips_dir` | `Path \| None` — stored so "Open Clips Folder" knows where to look |
| `_master_split_btn` | The "Master & Split" button |
| `_open_clips_btn` | The "Open Clips Folder" button (disabled until clips exist) |

---

## UI

Panel location: between "Open Latest Report" and "DaVinci Resolve Handoff" in the Single File tab.

```
┌─ Clip Splitter ────────────────────────────────────┐
│ Masters the file, then cuts it into equal-length    │
│ clips.                                              │
│                                                     │
│  Clip duration (s):  [ 5 ]                          │
│                                                     │
│  [ Master & Split ]  [ Open Clips Folder (disabled)]│
└─────────────────────────────────────────────────────┘
```

---

## Data Flow

1. User selects file, picks preset + format, sets clip duration, clicks **Master & Split**
2. UI disables button, sets status to "Mastering…", starts progress bar
3. Background thread:
   - Calls `master()` → mastered file written to `output_dir`
   - Calls `split_audio(mastered_file, duration, output_dir / f"{stem}_clips")`
4. On completion: enables "Open Clips Folder", status shows `"Done! N clips → {stem}_clips/"`
5. Progress bar: `0 → 0.35 → 0.70 → 0.95 → 1.0`

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| Duration input is non-numeric or ≤ 0 | Warning status shown; thread not started |
| `master()` returns an error | Error shown in status bar; splitting skipped |
| `split_audio()` returns an error | Error shown; mastered file is kept |
| Source file shorter than one clip duration | Single clip produced containing the whole file; treated as success |
| Output subfolder already exists | Clips written into it; existing files with matching names overwritten |

---

## Testing

New file: `tests/test_audio_splitter.py`

| Test | Input | Expected |
|---|---|---|
| Happy path | 15s WAV, 5s duration | 3 clips, each ≈ 5s |
| Remainder kept | 17s WAV, 5s duration | 4 clips (3 × 5s + 1 × 2s) |
| Single clip | 3s WAV, 5s duration | 1 clip ≈ 3s |
| Invalid duration | duration = 0 | `SplitResult.error` set, no files written |
| Bad input path | non-existent file | `SplitResult.error` set |

Tests follow the same pattern as `tests/test_mastering_engine.py` — generate short sine-wave WAVs with `numpy`/`scipy`, run the function, assert on the result.

---

## Out of Scope

- Splitting without mastering
- Batch or watch-folder splitting
- Clip preview in the Preview tab (clips folder can be opened via "Open Clips Folder")
- Auto-report for individual clips
