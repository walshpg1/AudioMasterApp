from __future__ import annotations
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Optional

from ffmpeg_utils import find_ffmpeg
import video_tools.ffmpeg_runner as ffmpeg_runner
from video_tools.models import ExtractionJob, ExtractionResult
from video_tools.watcher import VideoWatcher

logger = logging.getLogger(__name__)

_MAX_WORKERS = 2
_POLL_INTERVAL = 5.0


class ExtractionService:
    """Orchestrates the video watcher and FFmpeg runner.

    All on_result callbacks are invoked on the Tk main thread via root.after(0, ...).
    """

    def __init__(self, root) -> None:
        self._root = root
        self._stop_event = threading.Event()
        self._poll_thread: Optional[threading.Thread] = None
        self._executor: Optional[ThreadPoolExecutor] = None
        self._processed: set[Path] = set()
        self._watcher: Optional[VideoWatcher] = None

    def start(
        self,
        watch_folder: Path | str,
        output_folder: Path | str,
        fmt: str,
        on_result: Callable[[ExtractionResult], None],
    ) -> None:
        """Start the watch loop. Stops any existing loop first."""
        if self._poll_thread and self._poll_thread.is_alive():
            self.stop()

        watch_folder = Path(watch_folder)
        output_folder = Path(output_folder)
        self._stop_event.clear()
        self._watcher = VideoWatcher(watch_folder)
        self._executor = ThreadPoolExecutor(max_workers=_MAX_WORKERS)
        self._poll_thread = threading.Thread(
            target=self._poll_loop,
            args=(watch_folder, output_folder, fmt, on_result),
            daemon=True,
        )
        self._poll_thread.start()
        logger.info("ExtractionService started watching %s", watch_folder)

    def stop(self) -> None:
        """Signal the poll loop to stop and wait up to 5 s for it to exit."""
        self._stop_event.set()
        if self._poll_thread:
            self._poll_thread.join(timeout=5.0)
        if self._executor:
            self._executor.shutdown(wait=False)
        logger.info("ExtractionService stopped")

    def extract_one(
        self,
        path: Path | str,
        output_folder: Path | str,
        fmt: str,
        on_result: Callable[[ExtractionResult], None],
    ) -> None:
        """Extract the last frame from a single file in a background thread."""
        path = Path(path)
        output_folder = Path(output_folder)
        output_folder.mkdir(parents=True, exist_ok=True)
        output_path = output_folder / f"{path.stem}_lastframe.{fmt}"
        job = ExtractionJob(source_path=path, output_path=output_path, fmt=fmt)
        ffmpeg = find_ffmpeg() or "ffmpeg"

        def _run() -> None:
            ffmpeg_runner.run_extraction(
                job,
                ffmpeg,
                on_done=lambda result: self._root.after(0, lambda r=result: on_result(r)),
            )

        threading.Thread(target=_run, daemon=True).start()

    # ------------------------------------------------------------------

    def _poll_loop(
        self,
        watch_folder: Path,
        output_folder: Path,
        fmt: str,
        on_result: Callable[[ExtractionResult], None],
    ) -> None:
        output_folder.mkdir(parents=True, exist_ok=True)
        ffmpeg = find_ffmpeg() or "ffmpeg"

        while not self._stop_event.is_set():
            try:
                stable = self._watcher.scan()
                for path in stable:
                    if path in self._processed:
                        continue
                    self._processed.add(path)
                    output_path = output_folder / f"{path.stem}_lastframe.{fmt}"
                    job = ExtractionJob(
                        source_path=path,
                        output_path=output_path,
                        fmt=fmt,
                    )
                    self._executor.submit(
                        ffmpeg_runner.run_extraction,
                        job,
                        ffmpeg,
                        lambda result: self._root.after(0, lambda r=result: on_result(r)),
                    )
            except Exception as exc:
                logger.error("Poll loop error: %s", exc, exc_info=True)

            self._stop_event.wait(_POLL_INTERVAL)
