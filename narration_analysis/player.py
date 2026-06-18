from __future__ import annotations
import logging
import threading
import time
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


def _check_available() -> bool:
    try:
        import sounddevice  # noqa: F401
        return True
    except Exception:
        return False


class AudioPlayer:
    def __init__(self) -> None:
        self._available: bool = _check_available()
        self._data: np.ndarray | None = None
        self._sr: int = 44100
        self._path: Path | None = None
        self._playing: bool = False
        self._seek_offset: float = 0.0
        self._play_start: float = 0.0
        self._lock = threading.Lock()

    def load(self, path: Path) -> None:
        if not self._available:
            return
        try:
            from audio_decode import decode_audio_file
            data, sr = decode_audio_file(path)
            with self._lock:
                self._data = data.astype("float32")
                self._sr = sr
                self._path = path
                self._seek_offset = 0.0
        except Exception as exc:
            logger.warning("Could not load %s for playback: %s", path.name, exc)

    def seek(self, seconds: float) -> None:
        if not self._available or self._data is None:
            return
        import sounddevice as sd
        sd.stop()
        with self._lock:
            start = int(seconds * self._sr)
            clip = self._data[max(0, start):]
            self._seek_offset = seconds
            self._play_start = time.time()
            self._playing = True
        sd.play(clip, self._sr)
        threading.Thread(target=self._monitor, daemon=True).start()

    def play(self) -> None:
        if not self._available or self._data is None:
            return
        import sounddevice as sd
        sd.stop()
        with self._lock:
            self._seek_offset = 0.0
            self._play_start = time.time()
            self._playing = True
        sd.play(self._data, self._sr)
        threading.Thread(target=self._monitor, daemon=True).start()

    def pause(self) -> None:
        if not self._available:
            return
        import sounddevice as sd
        with self._lock:
            if self._playing:
                self._seek_offset = self._seek_offset + (time.time() - self._play_start)
                self._playing = False
        sd.stop()

    def unpause(self) -> None:
        if not self._available or self._data is None:
            return
        import sounddevice as sd
        with self._lock:
            offset = self._seek_offset
            start = int(offset * self._sr)
            clip = self._data[max(0, start):]
            self._play_start = time.time()
            self._playing = True
        sd.play(clip, self._sr)
        threading.Thread(target=self._monitor, daemon=True).start()

    def stop(self) -> None:
        if not self._available:
            return
        import sounddevice as sd
        sd.stop()
        with self._lock:
            self._playing = False
            self._seek_offset = 0.0

    def is_playing(self) -> bool:
        with self._lock:
            return self._playing

    def get_pos_seconds(self) -> float:
        with self._lock:
            if not self._playing:
                return self._seek_offset
            return self._seek_offset + (time.time() - self._play_start)

    def cleanup(self) -> None:
        if not self._available:
            return
        try:
            import sounddevice as sd
            sd.stop()
        except Exception:
            pass

    def _monitor(self) -> None:
        import sounddevice as sd
        sd.wait()
        with self._lock:
            self._playing = False
