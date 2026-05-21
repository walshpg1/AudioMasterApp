# AudioMasterApp Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Windows desktop app that loudness-masters WAV files via FFmpeg with a customtkinter GUI and optional DaVinci Resolve media pool integration.

**Architecture:** Thin GUI shell (`app.py`) calls three independent modules (`audio_analysis`, `mastering_engine`, `resolve_bridge`), each returning a typed dataclass result. FFmpeg handles all audio processing via subprocess; Resolve scripting is an optional layer that fails gracefully.

**Tech Stack:** Python 3.12, customtkinter 5.2+, soundfile, numpy, pyloudnorm, FFmpeg (system), DaVinciResolveScript (bundled with Resolve)

---

## File Map

| File | Responsibility |
|---|---|
| `app.py` | customtkinter GUI shell — event wiring, threading, status display |
| `audio_analysis.py` | Open WAV, measure sample rate/channels/bit depth/duration/peak/RMS/LUFS |
| `mastering_engine.py` | Load preset JSON, run 2-pass FFmpeg loudnorm, return output path |
| `resolve_bridge.py` | Connect to Resolve scripting API, import WAV into media pool |
| `presets/*.json` | One JSON file per mastering preset (4 total) |
| `tests/test_audio_analysis.py` | Unit + integration tests for audio_analysis |
| `tests/test_mastering_engine.py` | Integration tests for mastering_engine (real FFmpeg calls) |
| `tests/test_resolve_bridge.py` | Unit tests for resolve_bridge offline path |
| `tests/conftest.py` | Shared pytest fixtures (test WAV generator) |
| `pytest.ini` | Test discovery config |
| `requirements.txt` | Pip dependencies |
| `README.md` | Setup + usage documentation |

---

## Task 1: Project Scaffold

**Files:**
- Create: `D:\AudioMasterApp\requirements.txt`
- Create: `D:\AudioMasterApp\pytest.ini`
- Create: `D:\AudioMasterApp\tests\conftest.py`
- Create dirs: `output\`, `logs\`, `presets\`, `tests\`

- [ ] **Step 1: Create the virtual environment**

```powershell
cd D:\AudioMasterApp
py -3.12 -m venv .venv
```

Expected: `.venv\` folder appears, no errors.

- [ ] **Step 2: Write requirements.txt**

Create `D:\AudioMasterApp\requirements.txt`:

```
customtkinter>=5.2.0
soundfile>=0.12.1
numpy>=1.26.0
pyloudnorm>=0.1.1
pytest>=8.0.0
```

- [ ] **Step 3: Install dependencies**

```powershell
D:\AudioMasterApp\.venv\Scripts\pip install -r D:\AudioMasterApp\requirements.txt
```

Expected: All packages install without error. Confirm with:
```powershell
D:\AudioMasterApp\.venv\Scripts\python -c "import customtkinter, soundfile, numpy, pyloudnorm; print('OK')"
```
Expected output: `OK`

- [ ] **Step 4: Create folder structure**

```powershell
New-Item -ItemType Directory -Force D:\AudioMasterApp\output
New-Item -ItemType Directory -Force D:\AudioMasterApp\logs
New-Item -ItemType Directory -Force D:\AudioMasterApp\presets
New-Item -ItemType Directory -Force D:\AudioMasterApp\tests
```

- [ ] **Step 5: Write pytest.ini**

Create `D:\AudioMasterApp\pytest.ini`:

```ini
[pytest]
testpaths = tests
```

- [ ] **Step 6: Write tests/conftest.py**

Create `D:\AudioMasterApp\tests\conftest.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import soundfile as sf
import pytest


@pytest.fixture
def test_wav(tmp_path):
    path = tmp_path / "test_source.wav"
    sr = 44100
    rng = np.random.default_rng(42)
    data = rng.uniform(-0.5, 0.5, (sr * 3, 2))
    sf.write(str(path), data, sr, subtype="PCM_24")
    return str(path)


@pytest.fixture
def silent_wav(tmp_path):
    path = tmp_path / "silent.wav"
    sr = 44100
    data = np.zeros((sr * 2, 2))
    sf.write(str(path), data, sr, subtype="PCM_24")
    return str(path)
```

- [ ] **Step 7: Verify pytest discovers tests (empty run)**

```powershell
cd D:\AudioMasterApp
.venv\Scripts\pytest --collect-only
```

Expected: `no tests ran` (no test files yet) — no import errors.

- [ ] **Step 8: Commit scaffold**

```powershell
cd D:\AudioMasterApp
git add requirements.txt pytest.ini tests\conftest.py
git commit -m "feat: project scaffold, venv, pytest config"
```

---

## Task 2: Preset JSON Files

**Files:**
- Create: `D:\AudioMasterApp\presets\streaming_master.json`
- Create: `D:\AudioMasterApp\presets\tiktok_youtube_loud.json`
- Create: `D:\AudioMasterApp\presets\voiceover.json`
- Create: `D:\AudioMasterApp\presets\demo_loud.json`

- [ ] **Step 1: Write streaming_master.json**

Create `D:\AudioMasterApp\presets\streaming_master.json`:

```json
{
  "name": "Streaming Master -14 LUFS",
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

- [ ] **Step 2: Write tiktok_youtube_loud.json**

Create `D:\AudioMasterApp\presets\tiktok_youtube_loud.json`:

```json
{
  "name": "TikTok/YouTube Loud -12 LUFS",
  "slug": "tiktok_youtube_loud",
  "target_lufs": -12.0,
  "true_peak_ceiling": -1.0,
  "compress": true,
  "compress_ratio": 2.0,
  "compress_threshold_db": -18.0,
  "compress_attack_ms": 20,
  "compress_release_ms": 200
}
```

- [ ] **Step 3: Write voiceover.json**

Create `D:\AudioMasterApp\presets\voiceover.json`:

```json
{
  "name": "Voiceover -16 LUFS",
  "slug": "voiceover",
  "target_lufs": -16.0,
  "true_peak_ceiling": -1.0,
  "compress": false,
  "compress_ratio": 2.0,
  "compress_threshold_db": -18.0,
  "compress_attack_ms": 20,
  "compress_release_ms": 200
}
```

- [ ] **Step 4: Write demo_loud.json**

Create `D:\AudioMasterApp\presets\demo_loud.json`:

```json
{
  "name": "Demo Loud -10 LUFS",
  "slug": "demo_loud",
  "target_lufs": -10.0,
  "true_peak_ceiling": -1.0,
  "compress": true,
  "compress_ratio": 2.0,
  "compress_threshold_db": -18.0,
  "compress_attack_ms": 20,
  "compress_release_ms": 200
}
```

- [ ] **Step 5: Verify JSON is valid**

```powershell
cd D:\AudioMasterApp
.venv\Scripts\python -c "
import json, pathlib
for p in pathlib.Path('presets').glob('*.json'):
    d = json.loads(p.read_text())
    print(p.name, d['target_lufs'])
"
```

Expected output (order may vary):
```
streaming_master.json -14.0
tiktok_youtube_loud.json -12.0
voiceover.json -16.0
demo_loud.json -10.0
```

- [ ] **Step 6: Commit presets**

```powershell
cd D:\AudioMasterApp
git add presets\
git commit -m "feat: add four mastering preset JSON files"
```

---

## Task 3: audio_analysis.py

**Files:**
- Create: `D:\AudioMasterApp\audio_analysis.py`
- Create: `D:\AudioMasterApp\tests\test_audio_analysis.py`

- [ ] **Step 1: Write the failing tests**

Create `D:\AudioMasterApp\tests\test_audio_analysis.py`:

```python
import math
import pytest
from audio_analysis import analyse, AnalysisResult, _subtype_to_bitdepth


def test_analyse_sample_rate(test_wav):
    result = analyse(test_wav)
    assert result.sample_rate == 44100


def test_analyse_channels(test_wav):
    result = analyse(test_wav)
    assert result.channels == 2


def test_analyse_bit_depth(test_wav):
    result = analyse(test_wav)
    assert result.bit_depth == "24-bit"


def test_analyse_duration(test_wav):
    result = analyse(test_wav)
    assert abs(result.duration_seconds - 3.0) < 0.05


def test_analyse_peak_is_finite_negative(test_wav):
    result = analyse(test_wav)
    assert math.isfinite(result.peak_dbfs)
    assert result.peak_dbfs < 0


def test_analyse_rms_is_finite_negative(test_wav):
    result = analyse(test_wav)
    assert math.isfinite(result.rms_dbfs)
    assert result.rms_dbfs < 0


def test_analyse_lufs_is_plausible(test_wav):
    result = analyse(test_wav)
    assert -70.0 < result.integrated_lufs < 0.0


def test_analyse_no_error_on_valid_file(test_wav):
    result = analyse(test_wav)
    assert result.error is None


def test_analyse_missing_file_returns_error():
    result = analyse("does_not_exist.wav")
    assert result.error is not None
    assert result.sample_rate == 0


def test_analyse_result_path_matches_input(test_wav):
    result = analyse(test_wav)
    assert result.path == test_wav


def test_subtype_to_bitdepth_pcm16():
    assert _subtype_to_bitdepth("PCM_16") == "16-bit"


def test_subtype_to_bitdepth_pcm24():
    assert _subtype_to_bitdepth("PCM_24") == "24-bit"


def test_subtype_to_bitdepth_float():
    assert _subtype_to_bitdepth("FLOAT") == "32-bit float"


def test_subtype_to_bitdepth_unknown():
    result = _subtype_to_bitdepth("VORBIS")
    assert result == "VORBIS"
```

- [ ] **Step 2: Run tests — confirm they all fail**

```powershell
cd D:\AudioMasterApp
.venv\Scripts\pytest tests\test_audio_analysis.py -v
```

Expected: All tests FAIL with `ModuleNotFoundError: No module named 'audio_analysis'`

- [ ] **Step 3: Write audio_analysis.py**

Create `D:\AudioMasterApp\audio_analysis.py`:

```python
from __future__ import annotations
import math
import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
import soundfile as sf
import pyloudnorm as pyln

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    path: str
    sample_rate: int
    bit_depth: str
    channels: int
    duration_seconds: float
    peak_dbfs: float
    rms_dbfs: float
    integrated_lufs: float
    error: Optional[str] = None


def analyse(path: str) -> AnalysisResult:
    try:
        with sf.SoundFile(path) as f:
            sample_rate = f.samplerate
            channels = f.channels
            frames = len(f)
            subtype = f.subtype
            data = f.read(dtype="float64", always_2d=True)

        duration_seconds = frames / sample_rate
        bit_depth = _subtype_to_bitdepth(subtype)
        peak_dbfs = 20.0 * math.log10(max(float(np.abs(data).max()), 1e-10))
        rms = math.sqrt(float(np.mean(data ** 2)))
        rms_dbfs = 20.0 * math.log10(max(rms, 1e-10))
        meter = pyln.Meter(sample_rate)
        integrated_lufs = float(meter.integrated_loudness(data))

        return AnalysisResult(
            path=path,
            sample_rate=sample_rate,
            bit_depth=bit_depth,
            channels=channels,
            duration_seconds=duration_seconds,
            peak_dbfs=peak_dbfs,
            rms_dbfs=rms_dbfs,
            integrated_lufs=integrated_lufs,
        )
    except Exception as exc:
        logger.exception("Analysis failed for %s", path)
        return AnalysisResult(
            path=path,
            sample_rate=0,
            bit_depth="unknown",
            channels=0,
            duration_seconds=0.0,
            peak_dbfs=0.0,
            rms_dbfs=0.0,
            integrated_lufs=0.0,
            error=str(exc),
        )


def _subtype_to_bitdepth(subtype: str) -> str:
    return {
        "PCM_16": "16-bit",
        "PCM_24": "24-bit",
        "PCM_32": "32-bit",
        "FLOAT": "32-bit float",
        "DOUBLE": "64-bit float",
    }.get(subtype, subtype)
```

- [ ] **Step 4: Run tests — confirm all pass**

```powershell
cd D:\AudioMasterApp
.venv\Scripts\pytest tests\test_audio_analysis.py -v
```

Expected: All 14 tests PASS.

- [ ] **Step 5: Commit**

```powershell
cd D:\AudioMasterApp
git add audio_analysis.py tests\test_audio_analysis.py
git commit -m "feat: audio_analysis module with LUFS/peak/RMS measurement"
```

---

## Task 4: mastering_engine.py

**Files:**
- Create: `D:\AudioMasterApp\mastering_engine.py`
- Create: `D:\AudioMasterApp\tests\test_mastering_engine.py`

- [ ] **Step 1: Write the failing tests**

Create `D:\AudioMasterApp\tests\test_mastering_engine.py`:

```python
from pathlib import Path
import pytest
from mastering_engine import master, load_preset, list_presets, MasterResult


def test_load_preset_streaming():
    preset = load_preset("streaming_master")
    assert preset["target_lufs"] == -14.0
    assert preset["slug"] == "streaming_master"
    assert preset["compress"] is False


def test_load_preset_tiktok():
    preset = load_preset("tiktok_youtube_loud")
    assert preset["target_lufs"] == -12.0
    assert preset["compress"] is True


def test_load_preset_voiceover():
    preset = load_preset("voiceover")
    assert preset["target_lufs"] == -16.0
    assert preset["compress"] is False


def test_load_preset_demo():
    preset = load_preset("demo_loud")
    assert preset["target_lufs"] == -10.0
    assert preset["compress"] is True


def test_list_presets_returns_four():
    presets = list_presets()
    assert len(presets) == 4


def test_list_presets_order():
    presets = list_presets()
    slugs = [p["slug"] for p in presets]
    assert slugs == ["streaming_master", "tiktok_youtube_loud", "voiceover", "demo_loud"]


def test_master_streaming_creates_output_file(test_wav):
    preset = load_preset("streaming_master")
    result = master(test_wav, preset)
    assert result.error is None, result.error
    assert result.output_path is not None
    assert Path(result.output_path).exists()


def test_master_output_is_wav(test_wav):
    preset = load_preset("streaming_master")
    result = master(test_wav, preset)
    assert result.output_path.endswith(".wav")


def test_master_output_filename_contains_stem_and_slug(test_wav):
    preset = load_preset("voiceover")
    result = master(test_wav, preset)
    name = Path(result.output_path).name
    assert "test_source" in name
    assert "voiceover" in name
    assert "_mastered_" in name


def test_master_does_not_overwrite_input(test_wav):
    preset = load_preset("streaming_master")
    result = master(test_wav, preset)
    assert Path(result.output_path).resolve() != Path(test_wav).resolve()


def test_master_with_compression(test_wav):
    preset = load_preset("tiktok_youtube_loud")
    result = master(test_wav, preset)
    assert result.error is None, result.error
    assert Path(result.output_path).exists()


def test_master_demo_loud(test_wav):
    preset = load_preset("demo_loud")
    result = master(test_wav, preset)
    assert result.error is None, result.error


def test_master_missing_input_returns_error():
    preset = load_preset("streaming_master")
    result = master("nonexistent_file.wav", preset)
    assert result.error is not None
    assert result.output_path is None


def test_master_result_has_pass1_lufs(test_wav):
    preset = load_preset("streaming_master")
    result = master(test_wav, preset)
    assert result.pass1_lufs is not None
    assert isinstance(result.pass1_lufs, float)
```

- [ ] **Step 2: Run tests — confirm they all fail**

```powershell
cd D:\AudioMasterApp
.venv\Scripts\pytest tests\test_mastering_engine.py -v
```

Expected: All tests FAIL with `ModuleNotFoundError: No module named 'mastering_engine'`

- [ ] **Step 3: Write mastering_engine.py**

Create `D:\AudioMasterApp\mastering_engine.py`:

```python
from __future__ import annotations
import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

PRESETS_DIR = Path(__file__).parent / "presets"
OUTPUT_DIR = Path(__file__).parent / "output"

PRESET_ORDER = ["streaming_master", "tiktok_youtube_loud", "voiceover", "demo_loud"]


@dataclass
class MasterResult:
    output_path: Optional[str]
    preset_name: str
    pass1_lufs: Optional[float]
    error: Optional[str] = None


def load_preset(slug: str) -> dict:
    path = PRESETS_DIR / f"{slug}.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def list_presets() -> list[dict]:
    result = []
    for slug in PRESET_ORDER:
        path = PRESETS_DIR / f"{slug}.json"
        if path.exists():
            with open(path, encoding="utf-8") as f:
                result.append(json.load(f))
    return result


def master(input_path: str, preset: dict) -> MasterResult:
    input_path = Path(input_path)
    preset_name = preset["name"]
    slug = preset["slug"]
    target_lufs = preset["target_lufs"]
    true_peak = preset["true_peak_ceiling"]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"{input_path.stem}_mastered_{slug}.wav"

    # Pass 1: measure
    p1_cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-af", f"loudnorm=I={target_lufs}:TP={true_peak}:LRA=11:print_format=json",
        "-f", "null", "-",
    ]
    p1 = subprocess.run(p1_cmd, capture_output=True, text=True)
    if p1.returncode != 0:
        logger.error("FFmpeg Pass 1 failed: %s", p1.stderr[-800:])
        return MasterResult(output_path=None, preset_name=preset_name, pass1_lufs=None,
                            error=f"FFmpeg Pass 1 failed: {p1.stderr[-400:]}")

    measured = _parse_loudnorm_json(p1.stderr)
    if measured is None:
        return MasterResult(output_path=None, preset_name=preset_name, pass1_lufs=None,
                            error="Could not parse FFmpeg loudnorm output from Pass 1")

    pass1_lufs = float(measured.get("input_i", 0.0))

    # Build filter chain for Pass 2
    loudnorm = (
        f"loudnorm=I={target_lufs}:TP={true_peak}:LRA=11"
        f":measured_I={measured['input_i']}"
        f":measured_TP={measured['input_tp']}"
        f":measured_LRA={measured['input_lra']}"
        f":measured_thresh={measured['input_thresh']}"
        f":offset={measured['target_offset']}"
        f":linear=true:print_format=none"
    )

    if preset.get("compress"):
        ratio = preset["compress_ratio"]
        thresh = preset["compress_threshold_db"]
        attack = preset["compress_attack_ms"]
        release = preset["compress_release_ms"]
        af = (
            f"acompressor=ratio={ratio}:threshold={thresh}dB"
            f":attack={attack}:release={release},"
            f"{loudnorm}"
        )
    else:
        af = loudnorm

    # Pass 2: apply
    p2_cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-af", af,
        "-ar", "48000",
        "-c:a", "pcm_s24le",
        str(output_path),
    ]
    p2 = subprocess.run(p2_cmd, capture_output=True, text=True)
    if p2.returncode != 0:
        logger.error("FFmpeg Pass 2 failed: %s", p2.stderr[-800:])
        return MasterResult(output_path=None, preset_name=preset_name, pass1_lufs=pass1_lufs,
                            error=f"FFmpeg Pass 2 failed: {p2.stderr[-400:]}")

    return MasterResult(output_path=str(output_path), preset_name=preset_name, pass1_lufs=pass1_lufs)


def _parse_loudnorm_json(stderr: str) -> dict | None:
    start = stderr.rfind("{")
    end = stderr.rfind("}") + 1
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(stderr[start:end])
    except json.JSONDecodeError:
        return None
```

- [ ] **Step 4: Run tests — confirm all pass**

```powershell
cd D:\AudioMasterApp
.venv\Scripts\pytest tests\test_mastering_engine.py -v
```

Expected: All 14 tests PASS. The FFmpeg tests will take a few seconds each (real audio processing).

- [ ] **Step 5: Commit**

```powershell
cd D:\AudioMasterApp
git add mastering_engine.py tests\test_mastering_engine.py
git commit -m "feat: mastering_engine with 2-pass FFmpeg loudnorm and compression"
```

---

## Task 5: resolve_bridge.py

**Files:**
- Create: `D:\AudioMasterApp\resolve_bridge.py`
- Create: `D:\AudioMasterApp\tests\test_resolve_bridge.py`

- [ ] **Step 1: Write the failing tests**

Create `D:\AudioMasterApp\tests\test_resolve_bridge.py`:

```python
import pytest
from resolve_bridge import connect, import_to_media_pool, BridgeResult


def test_connect_returns_tuple():
    resolve, msg = connect()
    assert isinstance(msg, str)
    assert len(msg) > 0


def test_connect_message_is_descriptive():
    resolve, msg = connect()
    # When Resolve is not running, message must explain why
    if resolve is None:
        assert any(kw in msg.lower() for kw in ["not running", "not found", "error", "connect"])


def test_import_returns_bridge_result_type():
    result = import_to_media_pool("any_path.wav")
    assert isinstance(result, BridgeResult)


def test_import_when_resolve_unavailable_returns_not_connected():
    result = import_to_media_pool("any_path.wav")
    # If Resolve is not running, connected must be False
    if not result.connected:
        assert result.clip_imported is False
        assert result.timeline_created is False
        assert result.error is None or isinstance(result.error, str)


def test_bridge_result_all_fields():
    result = BridgeResult(
        connected=False,
        project_name=None,
        clip_imported=False,
        timeline_created=False,
        message="Resolve is not running",
        error=None,
    )
    assert result.connected is False
    assert result.project_name is None
    assert result.clip_imported is False
    assert result.timeline_created is False
    assert result.message == "Resolve is not running"
    assert result.error is None


def test_bridge_result_with_error():
    result = BridgeResult(
        connected=True,
        project_name="AudioMasterApp",
        clip_imported=False,
        timeline_created=False,
        message="Import failed",
        error="Media pool error",
    )
    assert result.connected is True
    assert result.error == "Media pool error"
```

- [ ] **Step 2: Run tests — confirm they fail**

```powershell
cd D:\AudioMasterApp
.venv\Scripts\pytest tests\test_resolve_bridge.py -v
```

Expected: All tests FAIL with `ModuleNotFoundError: No module named 'resolve_bridge'`

- [ ] **Step 3: Write resolve_bridge.py**

Create `D:\AudioMasterApp\resolve_bridge.py`:

```python
from __future__ import annotations
import logging
import os
import sys
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

RESOLVE_MODULES = (
    r"C:\ProgramData\Blackmagic Design\DaVinci Resolve"
    r"\Support\Developer\Scripting\Modules"
)
PROJECT_NAME = "AudioMasterApp"


@dataclass
class BridgeResult:
    connected: bool
    project_name: Optional[str]
    clip_imported: bool
    timeline_created: bool
    message: str
    error: Optional[str] = None


def connect() -> tuple[object | None, str]:
    if RESOLVE_MODULES not in sys.path:
        sys.path.append(RESOLVE_MODULES)
    try:
        import DaVinciResolveScript as dvr  # type: ignore[import]
        resolve = dvr.scriptapp("Resolve")
        if resolve is None:
            return None, "Resolve is not running"
        version = resolve.GetVersionString()
        return resolve, f"Connected (v{version})"
    except ImportError:
        return None, "DaVinciResolveScript module not found"
    except Exception as exc:
        logger.exception("Resolve connection error")
        return None, f"Connection error: {exc}"


def import_to_media_pool(mastered_path: str) -> BridgeResult:
    resolve, msg = connect()
    if resolve is None:
        return BridgeResult(
            connected=False,
            project_name=None,
            clip_imported=False,
            timeline_created=False,
            message=msg,
        )

    try:
        pm = resolve.GetProjectManager()
        project = pm.GetCurrentProject()
        if project is None:
            project = pm.CreateProject(PROJECT_NAME)
        if project is None:
            return BridgeResult(
                connected=True,
                project_name=None,
                clip_imported=False,
                timeline_created=False,
                message="Could not get or create Resolve project",
                error="Project creation failed",
            )

        project_name = project.GetName()
        media_pool = project.GetMediaPool()

        abs_path = os.path.abspath(mastered_path)
        clips = media_pool.ImportMedia([abs_path])
        clip_imported = bool(clips)

        timeline_created = False
        if clip_imported and media_pool.GetTimelineCount() == 0:
            stem = os.path.splitext(os.path.basename(mastered_path))[0]
            tl = media_pool.CreateEmptyTimeline(f"{stem}_timeline")
            timeline_created = tl is not None

        status = f"Imported to '{project_name}'" if clip_imported else "Clip import failed"
        return BridgeResult(
            connected=True,
            project_name=project_name,
            clip_imported=clip_imported,
            timeline_created=timeline_created,
            message=status,
        )

    except Exception as exc:
        logger.exception("Resolve media pool import error")
        return BridgeResult(
            connected=True,
            project_name=None,
            clip_imported=False,
            timeline_created=False,
            message="Resolve bridge error — see logs",
            error=str(exc),
        )

# ---------------------------------------------------------------------------
# Fairlight automation note
# ---------------------------------------------------------------------------
# The DaVinci Resolve scripting API exposes media pool import, project/timeline
# management, and render queue operations. It does NOT expose Fairlight FX
# plugin parameters (EQ, compressor, limiter knob values). Those must be set
# manually inside the Fairlight page after import. This is an API limitation
# in all Resolve versions through 19.x.
```

- [ ] **Step 4: Run tests — confirm all pass**

```powershell
cd D:\AudioMasterApp
.venv\Scripts\pytest tests\test_resolve_bridge.py -v
```

Expected: All 6 tests PASS. (Tests cover offline path only; live Resolve integration is manual.)

- [ ] **Step 5: Commit**

```powershell
cd D:\AudioMasterApp
git add resolve_bridge.py tests\test_resolve_bridge.py
git commit -m "feat: resolve_bridge with graceful fallback when Resolve is not running"
```

---

## Task 6: app.py — GUI Shell

**Files:**
- Create: `D:\AudioMasterApp\app.py`

No unit tests for the GUI layer — it is pure event wiring with no testable logic. Verification is manual (Step 3).

- [ ] **Step 1: Write app.py**

Create `D:\AudioMasterApp\app.py`:

```python
from __future__ import annotations
import logging
import logging.handlers
import math
import threading
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from audio_analysis import analyse, AnalysisResult
from mastering_engine import master, list_presets
from resolve_bridge import connect as resolve_connect, import_to_media_pool, BridgeResult

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
_LOG_DIR = Path(__file__).parent / "logs"
_LOG_DIR.mkdir(exist_ok=True)

_handler = logging.handlers.RotatingFileHandler(
    _LOG_DIR / "audiomasterapp.log", maxBytes=5 * 1024 * 1024, backupCount=3,
    encoding="utf-8",
)
logging.basicConfig(
    handlers=[_handler],
    level=logging.DEBUG,
    format="%(asctime)s %(name)-20s %(levelname)-8s %(message)s",
)

# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

_STATUS_COLOURS = {
    "normal": ("white", "gray80"),
    "success": ("#4CAF50", "#388E3C"),
    "warning": ("#FFC107", "#F9A825"),
    "error": ("#F44336", "#C62828"),
}


class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("AudioMasterApp")
        self.geometry("520x660")
        self.resizable(False, False)

        self._wav_path: str | None = None
        self._last_output_path: str | None = None
        self._resolve_connected: bool = False
        self._presets = list_presets()
        self._preset_map = {p["name"]: p for p in self._presets}

        self._build_ui()
        threading.Thread(target=self._resolve_check_worker, daemon=True).start()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        pad = {"padx": 16, "pady": 6}

        # File selector
        file_frame = ctk.CTkFrame(self)
        file_frame.pack(fill="x", **pad)
        ctk.CTkButton(
            file_frame, text="Select WAV File...", command=self._select_file, width=160
        ).pack(side="left", padx=8, pady=8)
        self._file_label = ctk.CTkLabel(file_frame, text="No file selected", anchor="w")
        self._file_label.pack(side="left", fill="x", expand=True, padx=(0, 8))

        # Preset dropdown
        preset_frame = ctk.CTkFrame(self)
        preset_frame.pack(fill="x", **pad)
        ctk.CTkLabel(preset_frame, text="Preset:", width=60).pack(side="left", padx=8, pady=8)
        self._preset_var = ctk.StringVar(value=self._presets[0]["name"])
        ctk.CTkOptionMenu(
            preset_frame,
            variable=self._preset_var,
            values=[p["name"] for p in self._presets],
            width=300,
        ).pack(side="left", padx=8, pady=8)

        # Analysis panel
        analysis_frame = ctk.CTkFrame(self)
        analysis_frame.pack(fill="x", **pad)
        ctk.CTkLabel(
            analysis_frame, text="Analysis", font=ctk.CTkFont(weight="bold")
        ).pack(anchor="w", padx=12, pady=(8, 4))
        self._analysis_labels: dict[str, ctk.CTkLabel] = {}
        for field in [
            "Sample rate", "Bit depth", "Channels",
            "Duration", "Peak dBFS", "RMS dBFS", "Integrated LUFS",
        ]:
            row = ctk.CTkFrame(analysis_frame, fg_color="transparent")
            row.pack(fill="x", padx=8, pady=1)
            ctk.CTkLabel(row, text=f"{field}:", width=140, anchor="w").pack(side="left")
            lbl = ctk.CTkLabel(row, text="—", anchor="w")
            lbl.pack(side="left")
            self._analysis_labels[field] = lbl

        # Action buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=16, pady=4)
        ctk.CTkButton(
            btn_frame, text="Analyse", command=self._run_analyse, width=220
        ).pack(side="left", padx=(0, 8))
        self._master_btn = ctk.CTkButton(
            btn_frame, text="Master File", command=self._run_master, width=220, state="disabled"
        )
        self._master_btn.pack(side="left")

        # Resolve bridge panel (always visible, status reflects connection)
        resolve_frame = ctk.CTkFrame(self)
        resolve_frame.pack(fill="x", **pad)
        ctk.CTkLabel(
            resolve_frame, text="DaVinci Resolve", font=ctk.CTkFont(weight="bold")
        ).pack(anchor="w", padx=12, pady=(8, 4))
        resolve_row = ctk.CTkFrame(resolve_frame, fg_color="transparent")
        resolve_row.pack(fill="x", padx=12, pady=(0, 4))
        self._resolve_dot = ctk.CTkLabel(resolve_row, text="●", text_color="gray", width=20)
        self._resolve_dot.pack(side="left")
        self._resolve_status_lbl = ctk.CTkLabel(resolve_row, text="Checking...", anchor="w")
        self._resolve_status_lbl.pack(side="left")
        self._resolve_btn = ctk.CTkButton(
            resolve_frame,
            text="Send to Resolve Media Pool",
            command=self._send_to_resolve,
            state="disabled",
        )
        self._resolve_btn.pack(padx=12, pady=(0, 8))

        # Progress bar
        self._progress = ctk.CTkProgressBar(self)
        self._progress.pack(fill="x", padx=16, pady=4)
        self._progress.set(0)

        # Status bar
        self._status_lbl = ctk.CTkLabel(self, text="Ready", anchor="w")
        self._status_lbl.pack(fill="x", padx=16, pady=(4, 12))

    # ------------------------------------------------------------------
    # File selection
    # ------------------------------------------------------------------

    def _select_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Select WAV file",
            filetypes=[("WAV files", "*.wav"), ("All files", "*.*")],
        )
        if path:
            if not path.lower().endswith(".wav"):
                self._set_status("Please select a .wav file.", "warning")
                return
            self._wav_path = path
            self._file_label.configure(text=Path(path).name)
            self._master_btn.configure(state="normal")
            self._set_status("File selected. Click Analyse to inspect it.", "normal")

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def _run_analyse(self) -> None:
        if not self._wav_path:
            self._set_status("No file selected.", "warning")
            return
        self._set_status("Analysing...", "normal")
        self._progress.configure(mode="indeterminate")
        self._progress.start()
        threading.Thread(target=self._analyse_worker, daemon=True).start()

    def _analyse_worker(self) -> None:
        result = analyse(self._wav_path)
        self.after(0, self._on_analyse_done, result)

    def _on_analyse_done(self, result: AnalysisResult) -> None:
        self._progress.stop()
        self._progress.configure(mode="determinate")
        self._progress.set(0)
        if result.error:
            self._set_status(f"Analysis failed: {result.error}", "error")
            return
        mins, secs = divmod(result.duration_seconds, 60)
        self._analysis_labels["Sample rate"].configure(text=f"{result.sample_rate:,} Hz")
        self._analysis_labels["Bit depth"].configure(text=result.bit_depth)
        ch_name = {1: "Mono", 2: "Stereo"}.get(result.channels, str(result.channels))
        self._analysis_labels["Channels"].configure(text=ch_name)
        self._analysis_labels["Duration"].configure(text=f"{int(mins)}:{secs:05.2f}")
        self._analysis_labels["Peak dBFS"].configure(text=f"{result.peak_dbfs:.1f} dB")
        self._analysis_labels["RMS dBFS"].configure(text=f"{result.rms_dbfs:.1f} dB")
        lufs = result.integrated_lufs
        lufs_text = f"{lufs:.1f} LUFS" if math.isfinite(lufs) else "< −70 LUFS (very quiet)"
        self._analysis_labels["Integrated LUFS"].configure(text=lufs_text)
        self._set_status("Analysis complete.", "success")

    # ------------------------------------------------------------------
    # Mastering
    # ------------------------------------------------------------------

    def _run_master(self) -> None:
        if not self._wav_path:
            self._set_status("No file selected.", "warning")
            return
        preset_name = self._preset_var.get()
        preset = self._preset_map[preset_name]
        self._set_status(f"Mastering — Pass 1 (measuring)…", "normal")
        self._progress.configure(mode="determinate")
        self._progress.set(0.05)
        self._master_btn.configure(state="disabled")
        threading.Thread(target=self._master_worker, args=(preset,), daemon=True).start()

    def _master_worker(self, preset: dict) -> None:
        self.after(0, lambda: self._progress.set(0.35))
        result = master(self._wav_path, preset)
        self.after(0, lambda: self._progress.set(0.95))
        self.after(0, self._on_master_done, result)

    def _on_master_done(self, result) -> None:
        self._progress.set(1.0)
        self._master_btn.configure(state="normal")
        if result.error:
            self._set_status(f"Mastering error: {result.error}", "error")
            return
        self._last_output_path = result.output_path
        output_name = Path(result.output_path).name
        self._set_status(f"Done!  →  output/{output_name}", "success")
        if self._resolve_connected:
            self._resolve_btn.configure(state="normal")

    # ------------------------------------------------------------------
    # Resolve bridge
    # ------------------------------------------------------------------

    def _resolve_check_worker(self) -> None:
        resolve, msg = resolve_connect()
        self.after(0, self._on_resolve_check, resolve is not None, msg)

    def _on_resolve_check(self, connected: bool, msg: str) -> None:
        self._resolve_connected = connected
        if connected:
            self._resolve_dot.configure(text_color="#4CAF50")
            self._resolve_status_lbl.configure(text=f"Resolve: {msg}")
        else:
            self._resolve_dot.configure(text_color="#F44336")
            self._resolve_status_lbl.configure(text=f"Resolve: {msg}")

    def _send_to_resolve(self) -> None:
        if not self._last_output_path:
            self._set_status("Master a file first.", "warning")
            return
        self._set_status("Sending to Resolve media pool…", "normal")
        self._resolve_btn.configure(state="disabled")
        threading.Thread(target=self._resolve_import_worker, daemon=True).start()

    def _resolve_import_worker(self) -> None:
        result = import_to_media_pool(self._last_output_path)
        self.after(0, self._on_resolve_import_done, result)

    def _on_resolve_import_done(self, result: BridgeResult) -> None:
        self._resolve_btn.configure(state="normal")
        level = "success" if result.clip_imported else "error"
        self._set_status(f"Resolve: {result.message}", level)

    # ------------------------------------------------------------------
    # Status helper
    # ------------------------------------------------------------------

    def _set_status(self, msg: str, level: str = "normal") -> None:
        colours = _STATUS_COLOURS.get(level, _STATUS_COLOURS["normal"])
        colour = colours[0] if ctk.get_appearance_mode() == "Dark" else colours[1]
        self._status_lbl.configure(text=msg, text_color=colour)


if __name__ == "__main__":
    app = App()
    app.mainloop()
```

- [ ] **Step 2: Run the app and manually verify**

```powershell
cd D:\AudioMasterApp
.venv\Scripts\python app.py
```

Manual checklist:
- [ ] Window opens, dark theme, correct title "AudioMasterApp"
- [ ] "Select WAV File..." button opens a file dialog; selecting a WAV shows the filename
- [ ] Preset dropdown shows all 4 presets
- [ ] "Master File" button is disabled before file selection, enabled after
- [ ] Resolve status shows correctly (green dot if Resolve is open, red dot if not)
- [ ] "Analyse" populates all 7 analysis fields
- [ ] "Master File" runs and shows success status with output filename
- [ ] Mastered file appears in `D:\AudioMasterApp\output\`

- [ ] **Step 3: Commit**

```powershell
cd D:\AudioMasterApp
git add app.py
git commit -m "feat: customtkinter GUI shell with analysis, mastering, and Resolve bridge"
```

---

## Task 7: README.md

**Files:**
- Create: `D:\AudioMasterApp\README.md`

- [ ] **Step 1: Write README.md**

Create `D:\AudioMasterApp\README.md`:

```markdown
# AudioMasterApp

A Windows desktop tool for mastering WAV files to loudness targets using FFmpeg,
with optional DaVinci Resolve media pool integration.

## Requirements

- Windows 11
- Python 3.12 (install from python.org — use the "Add to PATH" option)
- FFmpeg on system PATH ([winget](https://winget.run/pkg/Gyan/FFmpeg): `winget install Gyan.FFmpeg`)
- DaVinci Resolve (optional — for media pool import)

## Setup

```powershell
# 1. Clone or unzip to D:\AudioMasterApp
cd D:\AudioMasterApp

# 2. Create virtual environment
py -3.12 -m venv .venv

# 3. Activate it
.venv\Scripts\Activate.ps1

# 4. Install dependencies
pip install -r requirements.txt
```

## Running the App

```powershell
cd D:\AudioMasterApp
.venv\Scripts\python app.py
```

Or, with the venv activated:

```powershell
python app.py
```

## Running Tests

```powershell
cd D:\AudioMasterApp
.venv\Scripts\pytest -v
```

## Presets

| Preset | Target LUFS | True Peak | Compression |
|---|---|---|---|
| Streaming Master | −14 LUFS | −1 dBTP | No |
| TikTok/YouTube Loud | −12 LUFS | −1 dBTP | Yes (2:1 gentle) |
| Voiceover | −16 LUFS | −1 dBTP | No |
| Demo Loud | −10 LUFS | −1 dBTP | Yes (2:1 gentle) |

Output files are written to `output/` as `{original}_mastered_{preset}.wav`.
The original file is never modified.

## DaVinci Resolve Integration

The app connects to Resolve via the scripting API at:
`C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\Modules`

When Resolve is open, the app can:
- Detect the running Resolve version
- Import the mastered WAV into the current project's media pool
- Create an empty timeline named after the file

**Limitations of Fairlight automation (Resolve 19.x and earlier):**
- Fairlight FX plugin parameters (EQ bands, compressor ratios, limiter ceiling)
  cannot be set via the scripting API — only clip/track import and timeline
  creation are supported
- Render-in-place via scripting requires manually configuring render settings
  inside Resolve before triggering via the API
- All Fairlight DSP must be applied manually on the Fairlight page after import

If Resolve is not running, the bridge fails gracefully and all mastering
still works via FFmpeg.

## Output Format

All mastered files are output as:
- Format: WAV PCM 24-bit
- Sample rate: 48 kHz (Resolve/streaming standard)
- Naming: `{original stem}_mastered_{preset slug}.wav`

## Future Improvements

- Batch folder processing
- Waveform and frequency spectrum display
- Additional presets (podcast, vinyl, CD master)
- EBU R128 short-term/momentary loudness display
- Export before/after loudness report (PDF or CSV)
- Fairlight render-in-place if Resolve API expands support
```

- [ ] **Step 2: Commit README**

```powershell
cd D:\AudioMasterApp
git add README.md
git commit -m "docs: add README with install steps, preset table, and Resolve limitations"
```

---

## Task 8: Full Test Suite + Final Smoke Test

- [ ] **Step 1: Run the full test suite**

```powershell
cd D:\AudioMasterApp
.venv\Scripts\pytest -v
```

Expected output (all green):
```
tests/test_audio_analysis.py::test_analyse_sample_rate          PASSED
tests/test_audio_analysis.py::test_analyse_channels             PASSED
tests/test_audio_analysis.py::test_analyse_bit_depth            PASSED
tests/test_audio_analysis.py::test_analyse_duration             PASSED
tests/test_audio_analysis.py::test_analyse_peak_is_finite_negative  PASSED
tests/test_audio_analysis.py::test_analyse_rms_is_finite_negative   PASSED
tests/test_audio_analysis.py::test_analyse_lufs_is_plausible    PASSED
tests/test_audio_analysis.py::test_analyse_no_error_on_valid_file   PASSED
tests/test_audio_analysis.py::test_analyse_missing_file_returns_error  PASSED
tests/test_audio_analysis.py::test_analyse_result_path_matches_input PASSED
tests/test_audio_analysis.py::test_subtype_to_bitdepth_pcm16   PASSED
tests/test_audio_analysis.py::test_subtype_to_bitdepth_pcm24   PASSED
tests/test_audio_analysis.py::test_subtype_to_bitdepth_float   PASSED
tests/test_audio_analysis.py::test_subtype_to_bitdepth_unknown  PASSED
tests/test_mastering_engine.py::test_load_preset_streaming      PASSED
tests/test_mastering_engine.py::test_load_preset_tiktok         PASSED
tests/test_mastering_engine.py::test_load_preset_voiceover      PASSED
tests/test_mastering_engine.py::test_load_preset_demo           PASSED
tests/test_mastering_engine.py::test_list_presets_returns_four  PASSED
tests/test_mastering_engine.py::test_list_presets_order         PASSED
tests/test_mastering_engine.py::test_master_streaming_creates_output_file  PASSED
tests/test_mastering_engine.py::test_master_output_is_wav       PASSED
tests/test_mastering_engine.py::test_master_output_filename_contains_stem_and_slug PASSED
tests/test_mastering_engine.py::test_master_does_not_overwrite_input   PASSED
tests/test_mastering_engine.py::test_master_with_compression    PASSED
tests/test_mastering_engine.py::test_master_demo_loud           PASSED
tests/test_mastering_engine.py::test_master_missing_input_returns_error PASSED
tests/test_mastering_engine.py::test_master_result_has_pass1_lufs  PASSED
tests/test_resolve_bridge.py::test_connect_returns_tuple        PASSED
tests/test_resolve_bridge.py::test_connect_message_is_descriptive  PASSED
tests/test_resolve_bridge.py::test_import_returns_bridge_result_type PASSED
tests/test_resolve_bridge.py::test_import_when_resolve_unavailable_returns_not_connected PASSED
tests/test_resolve_bridge.py::test_bridge_result_all_fields     PASSED
tests/test_resolve_bridge.py::test_bridge_result_with_error     PASSED

34 passed
```

- [ ] **Step 2: Verify output directory has mastered files from test runs**

```powershell
Get-ChildItem D:\AudioMasterApp\output\
```

Expected: Several `*_mastered_*.wav` files from the integration tests.

- [ ] **Step 3: Verify log file was created**

```powershell
Get-ChildItem D:\AudioMasterApp\logs\
```

Expected: `audiomasterapp.log` exists (may be empty if no errors occurred).

- [ ] **Step 4: Final launch of app**

```powershell
cd D:\AudioMasterApp
.venv\Scripts\python app.py
```

Verify golden path end-to-end:
1. Select a real WAV from your music or voice files
2. Click "Analyse" — all 7 fields populate
3. Choose "TikTok/YouTube Loud -12 LUFS"
4. Click "Master File" — progress bar moves, status shows output filename
5. Open `D:\AudioMasterApp\output\` — mastered file is there
6. (Optional) Open DaVinci Resolve, then click "Send to Resolve Media Pool" — clip appears in media pool

- [ ] **Step 5: Final commit**

```powershell
cd D:\AudioMasterApp
git add -A
git status
git commit -m "feat: AudioMasterApp v1 complete — all tests passing"
```

---

## Quick-Reference Commands

```powershell
# Run app
cd D:\AudioMasterApp; .venv\Scripts\python app.py

# Run all tests
cd D:\AudioMasterApp; .venv\Scripts\pytest -v

# Run a specific test file
cd D:\AudioMasterApp; .venv\Scripts\pytest tests\test_mastering_engine.py -v

# Check output files
Get-ChildItem D:\AudioMasterApp\output\

# Tail the log
Get-Content D:\AudioMasterApp\logs\audiomasterapp.log -Tail 30
```
