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
