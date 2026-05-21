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
