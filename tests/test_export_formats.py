import pytest
from export_formats import (
    list_export_formats,
    get_export_format,
    DEFAULT_FORMAT,
    ExportFormat,
)


def test_list_export_formats_returns_five():
    assert len(list_export_formats()) == 5


def test_all_formats_have_required_fields():
    for fmt in list_export_formats():
        assert fmt.name
        assert fmt.slug
        assert fmt.extension in {"wav", "mp3", "flac"}
        assert fmt.ffmpeg_codec
        assert fmt.sample_rate > 0


def test_all_format_slugs_unique():
    slugs = [f.slug for f in list_export_formats()]
    assert len(slugs) == len(set(slugs))


def test_all_format_names_unique():
    names = [f.name for f in list_export_formats()]
    assert len(names) == len(set(names))


def test_get_export_format_wav_24_48():
    fmt = get_export_format("wav_24_48")
    assert fmt is not None
    assert fmt.ffmpeg_codec == "pcm_s24le"
    assert fmt.sample_rate == 48000
    assert fmt.extension == "wav"


def test_get_export_format_wav_16_441():
    fmt = get_export_format("wav_16_441")
    assert fmt is not None
    assert fmt.ffmpeg_codec == "pcm_s16le"
    assert fmt.sample_rate == 44100


def test_get_export_format_mp3_320():
    fmt = get_export_format("mp3_320")
    assert fmt is not None
    assert fmt.ffmpeg_codec == "libmp3lame"
    assert "-b:a" in fmt.ffmpeg_extra
    assert "320k" in fmt.ffmpeg_extra


def test_get_export_format_mp3_192():
    fmt = get_export_format("mp3_192")
    assert fmt is not None
    assert "192k" in fmt.ffmpeg_extra


def test_get_export_format_flac():
    fmt = get_export_format("flac_lossless")
    assert fmt is not None
    assert fmt.ffmpeg_codec == "flac"
    assert fmt.extension == "flac"


def test_get_export_format_unknown_returns_none():
    assert get_export_format("does_not_exist") is None


def test_default_format_is_wav_24_48():
    assert DEFAULT_FORMAT.slug == "wav_24_48"
    assert DEFAULT_FORMAT.ffmpeg_codec == "pcm_s24le"
    assert DEFAULT_FORMAT.sample_rate == 48000


def test_export_format_is_immutable():
    fmt = get_export_format("wav_24_48")
    with pytest.raises((AttributeError, TypeError)):
        fmt.slug = "modified"


def test_list_returns_copy_not_internal_list():
    a = list_export_formats()
    b = list_export_formats()
    assert a is not b
    assert a == b
