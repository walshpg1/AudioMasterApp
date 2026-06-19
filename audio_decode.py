"""Uniform audio-decode interface.

decode_audio_file() returns (float64_data, samplerate) for any supported format:
  - WAV, FLAC, AIFF  → soundfile (fast, no subprocess)
  - MP3, AAC, M4A, OGG, OPUS, WEBM, etc. → FFmpeg stdout pipe (no temp files)
"""
from __future__ import annotations
import re
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

from ffmpeg_utils import find_ffmpeg, CREATE_NO_WINDOW_FLAG

# Extensions that libsndfile can reliably decode without FFmpeg.
_SF_NATIVE_EXTS: frozenset[str] = frozenset({
    ".wav", ".flac", ".aiff", ".aif", ".w64", ".rf64",
})


def decode_audio_file(path: str | Path) -> tuple[np.ndarray, int]:
    """Return *(float64 data 2-D, samplerate)* for any supported audio file.

    data shape is (num_samples, num_channels).
    Raises RuntimeError (or soundfile.SoundFileError) on failure.
    """
    ext = Path(path).suffix.lower()
    if ext in _SF_NATIVE_EXTS:
        data, sr = sf.read(str(path), always_2d=True, dtype="float64")
        return data, sr
    return _ffmpeg_pipe_decode(str(path))


def probe_audio_info(path: str | Path) -> dict:
    """Return basic stream info without fully decoding the file.

    Returns dict with keys: sample_rate (int), channels (int),
    duration_seconds (float), codec_name (str).
    """
    ffmpeg = find_ffmpeg() or "ffmpeg"
    proc = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(path)],
        capture_output=True, text=True,
        creationflags=CREATE_NO_WINDOW_FLAG,
    )
    return _parse_ffmpeg_info(proc.stderr)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ffmpeg_pipe_decode(
    path: str,
    samplerate: int | None = None,
    channels: int | None = None,
) -> tuple[np.ndarray, int]:
    """Decode *path* via FFmpeg stdout pipe → (float64 data, samplerate).

    If *samplerate*/*channels* are given the probe step is skipped.
    """
    ffmpeg = find_ffmpeg() or "ffmpeg"
    if samplerate is None or channels is None:
        _sr, _ch = _ffmpeg_probe_stream(ffmpeg, path)
        samplerate = samplerate or _sr
        channels = channels or _ch

    cmd = [
        ffmpeg, "-hide_banner", "-loglevel", "error",
        "-i", path,
        "-f", "f32le",
        "-ac", str(channels),
        "-ar", str(samplerate),
        "pipe:1",
    ]
    proc = subprocess.run(cmd, capture_output=True, creationflags=CREATE_NO_WINDOW_FLAG)
    if proc.returncode != 0 or not proc.stdout:
        raise RuntimeError(
            f"FFmpeg could not decode '{Path(path).name}': "
            + proc.stderr.decode(errors="replace")[-300:]
        )
    samples = np.frombuffer(proc.stdout, dtype="<f4")
    if len(samples) == 0:
        raise RuntimeError(f"FFmpeg returned no audio data for '{Path(path).name}'")
    data = samples.reshape(-1, channels).astype("float64")
    return data, samplerate


def _ffmpeg_probe_stream(ffmpeg: str, path: str) -> tuple[int, int]:
    """Return *(sample_rate, channels)* by parsing ``ffmpeg -i`` stderr."""
    proc = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", path],
        capture_output=True, text=True,
        creationflags=CREATE_NO_WINDOW_FLAG,
    )
    info = _parse_ffmpeg_info(proc.stderr)
    return info["sample_rate"], info["channels"]


def _parse_ffmpeg_info(stderr: str) -> dict:
    """Extract audio stream metadata from ``ffmpeg -i`` stderr text."""
    # Sample rate: "44100 Hz" or "48000 Hz"
    sr_m = re.search(r"(\d{4,6})\s*Hz", stderr)
    samplerate = int(sr_m.group(1)) if sr_m else 44100

    # Channels: "stereo", "mono", "2 channels", "5.1(side)", …
    if re.search(r"\bstereo\b", stderr):
        channels = 2
    elif re.search(r"\bmono\b", stderr):
        channels = 1
    else:
        ch_m = re.search(r"(\d+)\s*channel", stderr)
        channels = int(ch_m.group(1)) if ch_m else 2

    # Duration: "Duration: 00:01:23.45"
    dur_m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", stderr)
    duration = 0.0
    if dur_m:
        h, m, s = dur_m.groups()
        duration = int(h) * 3600 + int(m) * 60 + float(s)

    # Codec name from Audio stream line: "Audio: mp3, 44100 Hz, …"
    codec_m = re.search(r"Audio:\s*(\S+)", stderr)
    codec = codec_m.group(1).rstrip(",") if codec_m else "unknown"

    return {
        "sample_rate": samplerate,
        "channels": channels,
        "duration_seconds": duration,
        "codec_name": codec,
    }
