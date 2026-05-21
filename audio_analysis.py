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
