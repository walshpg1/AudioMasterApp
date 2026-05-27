from __future__ import annotations
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

WATCHED_EXTENSIONS: frozenset[str] = frozenset({".mp4"})


class VideoWatcher:
    """Polls a folder for new, fully-written MP4 files.

    A file is stable when its size is unchanged for `stability_checks`
    consecutive scans. Stable files are returned exactly once per session
    unless reset_seen() is called.
    """

    def __init__(
        self,
        folder: Path | str,
        poll_interval: float = 5.0,
        stability_checks: int = 2,
    ) -> None:
        self.folder = Path(folder)
        self.poll_interval = poll_interval
        self.stability_checks = stability_checks
        self._seen: set[Path] = set()
        self._pending: dict[Path, dict] = {}

    def scan(self) -> list[Path]:
        """Return newly stable, unseen MP4 files in alphabetical order."""
        try:
            candidates = self._get_candidates()
        except (OSError, PermissionError) as exc:
            logger.error("Video watch scan failed for %s: %s", self.folder, exc)
            return []

        current = set(candidates)
        for stale in [p for p in self._pending if p not in current]:
            del self._pending[stale]

        ready: list[Path] = []
        for path in candidates:
            try:
                size = path.stat().st_size
            except OSError:
                continue

            if size == 0:
                continue

            if path in self._pending:
                entry = self._pending[path]
                if size == entry["size"]:
                    entry["count"] += 1
                    if entry["count"] >= self.stability_checks:
                        ready.append(path)
                        self._seen.add(path)
                        del self._pending[path]
                else:
                    entry["size"] = size
                    entry["count"] = 0
            else:
                self._pending[path] = {"size": size, "count": 0}

        return sorted(ready)

    def reset_seen(self) -> None:
        """Clear seen + pending caches. Next scan treats all files as new."""
        self._seen.clear()
        self._pending.clear()

    def _get_candidates(self) -> list[Path]:
        return [
            p for p in self.folder.iterdir()
            if p.is_file()
            and p.suffix.lower() in WATCHED_EXTENSIONS
            and "_lastframe" not in p.stem
            and p not in self._seen
        ]
