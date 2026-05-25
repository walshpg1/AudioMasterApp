from __future__ import annotations
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ExportFormat:
    name: str
    slug: str
    extension: str
    ffmpeg_codec: str
    sample_rate: int
    ffmpeg_extra: tuple[str, ...] = ()


_FORMATS: list[ExportFormat] = [
    ExportFormat(
        name="WAV 24-bit 48 kHz",
        slug="wav_24_48",
        extension="wav",
        ffmpeg_codec="pcm_s24le",
        sample_rate=48000,
    ),
    ExportFormat(
        name="WAV 16-bit 44.1 kHz",
        slug="wav_16_441",
        extension="wav",
        ffmpeg_codec="pcm_s16le",
        sample_rate=44100,
    ),
    ExportFormat(
        name="MP3 320 kbps",
        slug="mp3_320",
        extension="mp3",
        ffmpeg_codec="libmp3lame",
        sample_rate=48000,
        ffmpeg_extra=("-b:a", "320k"),
    ),
    ExportFormat(
        name="MP3 192 kbps",
        slug="mp3_192",
        extension="mp3",
        ffmpeg_codec="libmp3lame",
        sample_rate=48000,
        ffmpeg_extra=("-b:a", "192k"),
    ),
    ExportFormat(
        name="FLAC Lossless",
        slug="flac_lossless",
        extension="flac",
        ffmpeg_codec="flac",
        sample_rate=48000,
    ),
]

DEFAULT_FORMAT = _FORMATS[0]


def list_export_formats() -> list[ExportFormat]:
    return list(_FORMATS)


def get_export_format(slug: str) -> ExportFormat | None:
    return next((f for f in _FORMATS if f.slug == slug), None)
