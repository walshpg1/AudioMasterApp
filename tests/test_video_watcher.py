from pathlib import Path
import pytest
from video_tools.watcher import VideoWatcher, WATCHED_EXTENSIONS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_file(path: Path, size: int = 1024) -> Path:
    path.write_bytes(b"x" * size)
    return path


# ---------------------------------------------------------------------------
# WATCHED_EXTENSIONS
# ---------------------------------------------------------------------------

def test_watched_extensions_contains_mp4():
    assert ".mp4" in WATCHED_EXTENSIONS


def test_watched_extensions_is_frozenset():
    assert isinstance(WATCHED_EXTENSIONS, frozenset)


# ---------------------------------------------------------------------------
# Stability detection
# ---------------------------------------------------------------------------

def test_stable_file_returned_after_two_scans(tmp_path):
    make_file(tmp_path / "render.mp4", size=1024)
    watcher = VideoWatcher(tmp_path, stability_checks=2)
    first = watcher.scan()   # pending, count=0 → not ready
    assert first == []
    second = watcher.scan()  # size unchanged, count=1 → not ready (need 2)
    assert second == []
    third = watcher.scan()   # size unchanged, count=2 → ready
    assert [p.name for p in third] == ["render.mp4"]


def test_unstable_file_not_returned(tmp_path):
    p = make_file(tmp_path / "render.mp4", size=100)
    watcher = VideoWatcher(tmp_path, stability_checks=2)
    watcher.scan()
    # Simulate file still being written — change size
    p.write_bytes(b"x" * 200)
    result = watcher.scan()
    assert result == []


def test_zero_byte_file_ignored(tmp_path):
    (tmp_path / "empty.mp4").write_bytes(b"")
    watcher = VideoWatcher(tmp_path, stability_checks=1)
    watcher.scan()
    result = watcher.scan()
    assert result == []


# ---------------------------------------------------------------------------
# Extension filtering
# ---------------------------------------------------------------------------

def test_non_mp4_file_ignored(tmp_path):
    make_file(tmp_path / "audio.wav")
    watcher = VideoWatcher(tmp_path, stability_checks=1)
    watcher.scan()
    result = watcher.scan()
    assert result == []


def test_lastframe_file_ignored(tmp_path):
    make_file(tmp_path / "render_lastframe.mp4")
    watcher = VideoWatcher(tmp_path, stability_checks=1)
    watcher.scan()
    result = watcher.scan()
    assert result == []


# ---------------------------------------------------------------------------
# Seen cache — debounce
# ---------------------------------------------------------------------------

def test_stable_file_returned_only_once(tmp_path):
    make_file(tmp_path / "render.mp4")
    watcher = VideoWatcher(tmp_path, stability_checks=1)
    watcher.scan()  # pending
    first_ready = watcher.scan()  # ready
    assert len(first_ready) == 1
    second_ready = watcher.scan()  # already seen
    assert second_ready == []


def test_reset_seen_allows_reprocessing(tmp_path):
    make_file(tmp_path / "render.mp4")
    watcher = VideoWatcher(tmp_path, stability_checks=1)
    watcher.scan()
    watcher.scan()  # file now in _seen
    watcher.reset_seen()
    watcher.scan()  # pending again
    result = watcher.scan()  # ready again
    assert len(result) == 1


# ---------------------------------------------------------------------------
# Multiple files
# ---------------------------------------------------------------------------

def test_multiple_files_all_returned(tmp_path):
    for name in ["a.mp4", "b.mp4", "c.mp4"]:
        make_file(tmp_path / name)
    watcher = VideoWatcher(tmp_path, stability_checks=1)
    watcher.scan()
    result = watcher.scan()
    assert [p.name for p in result] == ["a.mp4", "b.mp4", "c.mp4"]


# ---------------------------------------------------------------------------
# Scan handles missing folder gracefully
# ---------------------------------------------------------------------------

def test_scan_missing_folder_returns_empty(tmp_path):
    watcher = VideoWatcher(tmp_path / "nonexistent", stability_checks=1)
    result = watcher.scan()
    assert result == []
