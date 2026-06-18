# Narration Analysis Tab — Design Spec
**Date:** 2026-06-18  
**App:** AudioMasterApp (Python / CustomTkinter)  
**Status:** Approved for implementation

---

## Overview

Add a "Narration Analysis" tab to AudioMasterApp that processes voiceover audio files using faster-whisper and generates a full suite of outputs for AI video production: transcripts, subtitles, scene lists, and storyboard JSON.

---

## Architecture

### Package Layout

```
narration_analysis/
  __init__.py
  models.py          # TranscriptSegment, Scene, AnalysisResult dataclasses
  transcriber.py     # faster-whisper wrapper with progress callbacks
  scene_builder.py   # sentence splitting; produces scene list + storyboard
  exporter.py        # writes TXT, SRT, VTT, alignment JSON, scene_list, storyboard
  player.py          # pygame mixer: play/pause/seek by timestamp
  ui.py              # NarrationAnalysisTab class
```

### app.py Changes

- One import: `from narration_analysis.ui import NarrationAnalysisTab`
- One tab registration: `self._tabview.add("Narration Analysis")`
- One instantiation: `NarrationAnalysisTab(self._tabview.tab("Narration Analysis"), self)`

No other changes to `app.py`.

---

## Models (`models.py`)

```python
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
    project_name: str          # e.g. "The_Day_Work_Let_Me_Go" — derived from filename, spaces→underscores
    duration: float
    segments: list[TranscriptSegment]
    scenes: list[Scene]
    output_dir: Path           # root: D:\AIStudio\Outputs\narration_analysis\{project_name}\
```

---

## Transcriber (`transcriber.py`)

- Backend: `faster-whisper` (already installed)
- GPU: detect via `torch.cuda.is_available()` at runtime; fall back to CPU silently
- Model size: user-selectable (tiny / base / small / medium / large)
- Interface:
  ```python
  def transcribe(
      audio_path: Path,
      model_size: str,
      progress_cb: Callable[[float], None],
      cancel_event: threading.Event,
  ) -> list[TranscriptSegment]
  ```
- `progress_cb` receives 0.0–1.0 based on segment timestamps vs total duration
- `cancel_event` checked between segments; raises `TranscriptionCancelled` if set
- Model is cached in memory between runs (same size = no reload)

---

## Scene Builder (`scene_builder.py`)

Splits Whisper segments into scenes at sentence boundaries.

**Algorithm:**
1. Flatten all segment text into a running buffer with timestamps
2. Split at `.`, `!`, `?` (sentence boundary detection via regex, no external NLP deps)
3. Each sentence = one scene with inherited `start`/`end` from the underlying segments
4. Short fragments (<2 words) are merged with the previous scene

```python
def build_scenes(segments: list[TranscriptSegment]) -> list[Scene]
```

---

## Exporter (`exporter.py`)

Output root: `D:\AIStudio\Outputs\narration_analysis\`

| File | Subfolder | Format |
|---|---|---|
| `{stem}.txt` | `transcripts/` | Plain text transcript |
| `{stem}.srt` | `srt/` | SubRip subtitles |
| `{stem}.vtt` | `vtt/` | WebVTT captions |
| `{stem}_alignment.json` | `json/` | Per-segment start/end/text |
| `{stem}_scene_list.json` | `json/` | Per-scene with number/start/end/text |
| `{stem}_storyboard.json` | `storyboards/` | Full storyboard for ComfyUI/LTX |

**SRT format:** standard numbered blocks with `HH:MM:SS,mmm --> HH:MM:SS,mmm`

**VTT format:** `WEBVTT` header, `MM:SS.mmm --> MM:SS.mmm` timecodes

**Alignment JSON:**
```json
[{"start": 12.5, "end": 18.2, "text": "The day work let me go..."}]
```

**Scene list JSON:**
```json
[{"scene": 1, "start": 0.0, "end": 12.5, "start_tc": "00:00", "end_tc": "00:12", "text": "Twenty-one years."}]
```

**Storyboard JSON:**
```json
{
  "source": "voiceover.mp3",
  "project_name": "The_Day_Work_Let_Me_Go",
  "duration": 120.4,
  "scenes": [
    {
      "scene_number": 1,
      "narration": "Twenty-one years.",
      "start": 0.0,
      "end": 12.5,
      "duration": 12.5,
      "visual_prompt": "",
      "status": "pending"
    }
  ]
}
```

`visual_prompt` is reserved for future prompt-generation workflows (Script → ElevenLabs → Narration Analysis → Storyboard → ComfyUI). `status` tracks scene production state (`pending` → `generating` → `complete` → `rejected`).

```python
def export_all(result: AnalysisResult) -> dict[str, Path]
# Returns mapping of format name → output path
```

---

## Player (`player.py`)

- Library: `pygame.mixer`
- Interface:
  ```python
  class AudioPlayer:
      def load(self, path: Path) -> None
      def seek(self, seconds: float) -> None
      def play(self) -> None
      def pause(self) -> None
      def stop(self) -> None
      def is_playing(self) -> bool
  ```
- pygame.mixer is initialized once; subsequent loads replace the current track
- `seek()` implemented via unload + reload + `set_pos()` (pygame limitation)
- Player instance lives on `NarrationAnalysisTab`; cleaned up on app close

---

## UI (`ui.py`)

### Layout (top → bottom)

**Section 1 — Input**
- Browse button → `filedialog.askopenfilename` (MP3/WAV/M4A filter)
- File drop zone label (visual affordance only; full DnD requires changing the app root class, deferred to future iteration)
- Filename + duration label once loaded

**Section 2 — Transcription Controls**
- Model selector: OptionMenu (Tiny / Base / Small / Medium / Large), default Small
- GPU indicator label (auto-detected, greyed out if unavailable)
- "Analyse" button
- Progress bar (0–100%) + status label

**Section 3 — Output Preview** (scrollable, split into two columns)
- Left: `CTkTextbox` — full transcript with timestamps
- Right: `CTkScrollableFrame` — scene list; each scene is a button row (`[▶] Scene N  00:12–00:25  "text..."`)
  - Clicking a scene row: seeks audio to scene start, begins playback

**Section 4 — Playback Controls**
- ▶/⏸ Play/Pause button, ⏹ Stop button
- Current position label (`MM:SS`)
- All controls disabled until a file is loaded

**Section 5 — Export Status**
- Read-only textbox listing written file paths after analysis completes
- "Open Output Folder" button → `os.startfile(output_dir)`

### Threading Model

- "Analyse" click → disables controls, spawns daemon thread
- Thread: `transcriber.transcribe()` → `scene_builder.build_scenes()` → `exporter.export_all()`
- Progress updates posted back to UI via `root.after(0, callback)`
- On completion: re-enables controls, populates preview panels
- Cancel button sets `threading.Event`; transcriber checks it between segments

---

## Dependencies

| Package | Already installed? | Purpose |
|---|---|---|
| `faster-whisper` | Yes | Transcription |
| `pygame` | **No** | Audio playback |
| `tkinterdnd2` | **No** | Drag-and-drop (optional, graceful fallback) |
| `torch` | Yes | CUDA detection |

New dependencies to add to `requirements.txt`: `pygame>=2.5.0`  
`tkinterdnd2` is deferred — enabling it requires changing the app root class from `ctk.CTk`, which is out of scope for this iteration.

---

## Output Structure

```
D:\AIStudio\Outputs\narration_analysis\
  {project_name}\
    transcripts\    ← {stem}.txt
    srt\            ← {stem}.srt
    vtt\            ← {stem}.vtt
    json\           ← {stem}_alignment.json, {stem}_scene_list.json
    storyboards\    ← storyboard.json, scene_list.json
```

`project_name` is derived from the audio filename: spaces and hyphens replaced with underscores, lowercased only if already lowercase (preserves `The_Day_Work_Let_Me_Go` capitalisation). All subfolders created automatically on first run.

## Isolation Guarantee

This feature is **additive only**. It must not modify any of the following:
- Existing path constants in `app.py`, `pipeline/ui.py`, `video_tools/ui.py`, or `ffmpeg_utils.py`
- The Mux workflow or staging folders (`Pipeline\staging\audio_ready`, `Outputs\video\*`)
- The existing output governance (`Outputs\audio\*`, `Outputs\frames\*`, `Outputs\images\*`)
- Any existing tab, batch processor, or watch-folder logic

All new I/O is confined to `D:\AIStudio\Outputs\narration_analysis\` and the `narration_analysis\` package directory.

---

## Future Expansion Hooks

- `storyboard.json` schema is intentionally flat and complete — ComfyUI, LTX Director, and Resolve scripts can consume it directly
- `exporter.export_all()` returns a `dict[str, Path]` — additional exporters (e.g., DaVinci EDL) can be added without changing the UI
- `transcriber.py` accepts a `model_size` string — swapping in a different backend later requires only changes to this one file
