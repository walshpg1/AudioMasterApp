# AudioMasterApp — Design Spec
**Date:** 2026-05-21  
**Status:** Approved  
**Author:** Claude (Senior Python/Resolve automation engineer)

---

## 1. Purpose

A Windows desktop application that helps the user automatically master WAV files for music and voice using a Python/FFmpeg mastering engine, with an optional DaVinci Resolve/Fairlight integration layer for media pool import and timeline creation.

**Success criteria:**
- Select a WAV, choose a preset, click Master — get a correctly loudness-normalised WAV in `output/`
- Analysis panel shows LUFS, peak, RMS, sample rate, bit depth, channels, duration
- Resolve bridge imports the mastered file into Resolve's media pool when Resolve is open
- Original WAV is never modified
- Any failure surfaces as a plain-English status message, never a raw traceback

---

## 2. System Context

| Item | Value |
|---|---|
| OS | Windows 11 |
| Python | 3.12.7 (via `py -3.12`) |
| FFmpeg | Available on PATH (April 2026 build) |
| Resolve scripting | `C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\Modules\DaVinciResolveScript.py` |
| Project root | `D:\AudioMasterApp` |
| GUI toolkit | customtkinter (dark mode default) |

---

## 3. File Structure

```
D:\AudioMasterApp\
├── app.py                  # GUI shell — event wiring only, no logic
├── audio_analysis.py       # WAV metadata + LUFS/peak/RMS measurement
├── mastering_engine.py     # FFmpeg 2-pass loudnorm + optional compression
├── resolve_bridge.py       # Resolve scripting connection + media pool import
├── presets/
│   ├── streaming_master.json
│   ├── tiktok_youtube_loud.json
│   ├── voiceover.json
│   └── demo_loud.json
├── output/                 # Auto-created; all mastered files land here
├── logs/                   # Rotating log file (5 MB max, 3 backups)
├── docs/
│   └── superpowers/specs/  # This file
├── requirements.txt
└── README.md
```

---

## 4. Architecture

**Pattern:** Layered modules with a thin GUI shell.

```
GUI (app.py)
  │
  ├─→ audio_analysis.py  →  AnalysisResult (dataclass)
  ├─→ mastering_engine.py →  MasterResult (dataclass)
  └─→ resolve_bridge.py  →  BridgeResult (dataclass)
```

- GUI owns no business logic — it calls modules and displays results
- Modules communicate only via return values (dataclasses), never by importing each other
- Resolve bridge is fully optional; its absence or failure does not affect mastering

---

## 5. GUI Design

Single window, ~520×620px, customtkinter dark theme.

**Layout (top to bottom):**
1. Title bar with app name and dark/light toggle
2. File selector row — button + path label
3. Preset dropdown (4 options)
4. Analysis panel — 7-field grid, populated after Analyse click
5. Action buttons row — `[ Analyse ]` and `[ Master File ]`
6. Resolve Bridge panel — shown only when Resolve is detected running; contains status dot + `[ Send to Resolve Media Pool ]` button
7. Status bar — plain-English message, colour-coded (green/amber/red)
8. Progress bar — shown during FFmpeg processing

**Behaviour:**
- `Master File` is disabled until a file is selected
- Progress bar indeterminate during analysis, determinate (0→50→100%) across FFmpeg Pass 1 and Pass 2
- No modal dialogs — all feedback via status bar

---

## 6. Audio Analysis (`audio_analysis.py`)

**Libraries:** `soundfile`, `numpy`, `pyloudnorm`

**Returns `AnalysisResult`:**
```python
@dataclass
class AnalysisResult:
    path: str
    sample_rate: int
    bit_depth: str        # e.g. "24-bit", "32-bit float"
    channels: int
    duration_seconds: float
    peak_dbfs: float
    rms_dbfs: float
    integrated_lufs: float
    error: str | None
```

**Steps:**
1. Open with `soundfile.SoundFile` — read `samplerate`, `channels`, `subtype` (→ bit depth string), `frames` (→ duration)
2. Read audio data as `float32` numpy array
3. Peak dBFS: `20 * log10(abs(data).max())`
4. RMS dBFS: `20 * log10(sqrt(mean(data**2)))`
5. LUFS: `pyloudnorm.Meter(sample_rate).integrated_loudness(data)`
6. All steps wrapped in try/except; partial results returned with `error` field populated

---

## 7. Mastering Engine (`mastering_engine.py`)

**Library:** FFmpeg via `subprocess`, `json`, `pathlib`

**Preset JSON schema:**
```json
{
  "name": "Streaming Master",
  "slug": "streaming_master",
  "target_lufs": -14.0,
  "true_peak_ceiling": -1.0,
  "compress": false,
  "compress_ratio": 2.0,
  "compress_threshold_db": -18.0,
  "compress_attack_ms": 20,
  "compress_release_ms": 200
}
```

**Preset table:**

| Preset | LUFS | Compress |
|---|---|---|
| Streaming Master | -14 | No |
| TikTok/YouTube Loud | -12 | Yes (2:1) |
| Voiceover | -16 | No |
| Demo Loud | -10 | Yes (2:1) |

**Processing pipeline:**

*Pass 1 (measure):*
```
ffmpeg -i input.wav -af loudnorm=I=-14:TP=-1:LRA=11:print_format=json -f null -
```
Parse JSON from stderr → extract `input_i`, `input_tp`, `input_lra`, `input_thresh`, `target_offset`.

*Pass 2 (apply):*
```
ffmpeg -i input.wav -af [acompressor,]loudnorm=I=-14:TP=-1:LRA=11:measured_I=...:linear=true -ar 48000 output.wav
```
- `acompressor` filter prepended only when `compress: true`
- Output sample rate normalised to 48 kHz (Resolve/streaming standard)
- Output: `output/{stem}_mastered_{slug}.wav`

**Returns `MasterResult`:**
```python
@dataclass
class MasterResult:
    output_path: str | None
    preset_name: str
    pass1_lufs: float | None
    error: str | None
```

---

## 8. Resolve Bridge (`resolve_bridge.py`)

**Scripting path:** `C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\Modules`

**Connection sequence:**
1. Add Modules path to `sys.path`
2. `import DaVinciResolveScript as dvr` inside try/except ImportError
3. `resolve = dvr.scriptapp("Resolve")` — returns `None` if Resolve not open
4. Get/create project named `"AudioMasterApp"` via `project_manager`
5. Import mastered WAV via `media_pool.ImportMedia([abs_path])`
6. Create timeline named `f"{stem}_timeline"` if none exists

**Known Fairlight automation limitations (documented in README):**
- Fairlight FX plugin parameters (EQ, compressor, limiter) cannot be set via the scripting API — only clip/track import and basic timeline operations are exposed
- Render-in-place via scripting is possible but requires setting render settings manually
- All Fairlight DSP must be applied manually inside Resolve after import

**Returns `BridgeResult`:**
```python
@dataclass
class BridgeResult:
    connected: bool
    project_name: str | None
    clip_imported: bool
    timeline_created: bool
    message: str
    error: str | None
```

---

## 9. Error Handling

| Layer | Strategy |
|---|---|
| File validation | Check `.wav` extension + `soundfile` open attempt before any processing |
| Analysis errors | Catch all exceptions, populate `AnalysisResult.error`, display in status bar |
| FFmpeg errors | Check return code + capture stderr; surface as `MasterResult.error` |
| Resolve errors | Every call wrapped in try/except; `BridgeResult.connected = False` on any failure |
| Logging | `logging.handlers.RotatingFileHandler` → `logs/audiomasterapp.log`, 5 MB, 3 backups |
| GUI | Status bar text + colour only — no raw exceptions ever shown to user |

**Safety invariant:** Input WAV path is never passed to FFmpeg as an output target. Output is always written to `output/` with a `_mastered_{slug}` suffix.

---

## 10. Dependencies (`requirements.txt`)

```
customtkinter>=5.2.0
soundfile>=0.12.1
numpy>=1.26.0
pyloudnorm>=0.1.1
```

FFmpeg is a system dependency (not pip-installable); README documents this.

---

## 11. Out of Scope for v1

- Batch processing of multiple files
- MP3/FLAC input (WAV only)
- Fairlight FX parameter automation (API limitation)
- Render-from-Resolve workflow (mastering happens in Python/FFmpeg)
- Waveform visualisation
- Undo/history

---

## 12. Future Improvements

- Batch folder processing
- Waveform + frequency spectrum display
- Additional presets (podcast, vinyl, CD)
- Fairlight render-in-place automation (if Resolve API expands)
- EBU R128 short-term/momentary loudness display
- Export report PDF with before/after loudness stats
