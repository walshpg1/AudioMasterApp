from __future__ import annotations
import datetime
import logging
import os
from pathlib import Path
from tkinter import filedialog
from typing import Optional

import customtkinter as ctk
from PIL import Image

import settings_manager
from ffmpeg_utils import find_ffmpeg
from video_tools.extraction_service import ExtractionService
from video_tools.models import ExtractionResult

logger = logging.getLogger(__name__)

_STILLS_SUBDIR = "stills"
_FORMATS = ["PNG", "JPG"]

_STATUS_COLOURS = {
    "idle":       ("gray80", "gray40"),
    "watching":   ("#4CAF50", "#388E3C"),
    "processing": ("#FFC107", "#F9A825"),
    "error":      ("#F44336", "#C62828"),
}
_STATUS_LABELS = {
    "idle":       "● Idle",
    "watching":   "● Watching",
    "processing": "● Processing",
    "error":      "● Error",
}


class VideoToolsTab:
    """Builds and owns the Video Tools tab UI.

    Receives the tab frame and the Tk root (needed for root.after() calls).
    """

    def __init__(self, parent: ctk.CTkFrame, root: ctk.CTk) -> None:
        self._parent = parent
        self._root = root
        self._service = ExtractionService(root)
        self._watching = False
        self._last_output_path: Optional[Path] = None

        s = settings_manager.load()
        self._watch_folder_var = ctk.StringVar(
            value=s.get("video_watch_folder", r"D:\AIStudio\Apps\AIVideoStudio\renders")
        )
        self._output_folder_var = ctk.StringVar(value=s.get("video_output_folder", ""))
        self._format_var = ctk.StringVar(value=s.get("video_format", "png").upper())
        self._watcher_enabled_var = ctk.IntVar(value=int(s.get("video_watcher_enabled", False)))

        self._build_ui()

        if self._watcher_enabled_var.get():
            self._start_watcher()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        pad = {"padx": 12, "pady": 4}

        ctk.CTkLabel(
            self._parent,
            text="Extract Last Frame",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=12, pady=(12, 4))

        # Watch folder row
        wf = ctk.CTkFrame(self._parent)
        wf.pack(fill="x", **pad)
        ctk.CTkButton(wf, text="Watch Folder...", command=self._browse_watch_folder, width=130).pack(
            side="left", padx=8, pady=8
        )
        ctk.CTkLabel(
            wf, textvariable=self._watch_folder_var, anchor="w", font=ctk.CTkFont(size=11)
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))

        # Output folder row
        of = ctk.CTkFrame(self._parent)
        of.pack(fill="x", **pad)
        ctk.CTkButton(of, text="Output Folder...", command=self._browse_output_folder, width=130).pack(
            side="left", padx=8, pady=8
        )
        self._output_folder_lbl = ctk.CTkLabel(
            of, text=self._effective_output_folder(), anchor="w", font=ctk.CTkFont(size=11)
        )
        self._output_folder_lbl.pack(side="left", fill="x", expand=True, padx=(0, 8))

        # Format + watcher toggle + status row
        ctrl = ctk.CTkFrame(self._parent)
        ctrl.pack(fill="x", **pad)
        ctk.CTkLabel(ctrl, text="Format:", width=60).pack(side="left", padx=(8, 0), pady=8)
        ctk.CTkOptionMenu(
            ctrl,
            variable=self._format_var,
            values=_FORMATS,
            width=80,
            command=self._on_format_change,
        ).pack(side="left", padx=8, pady=8)
        ctk.CTkSwitch(
            ctrl,
            text="Enable Watcher",
            variable=self._watcher_enabled_var,
            command=self._on_watcher_toggle,
        ).pack(side="left", padx=8, pady=8)
        self._status_lbl = ctk.CTkLabel(ctrl, text="● Idle", width=110, anchor="e")
        self._status_lbl.pack(side="right", padx=8, pady=8)

        # Manual extract button
        btn_row = ctk.CTkFrame(self._parent)
        btn_row.pack(fill="x", **pad)
        self._manual_btn = ctk.CTkButton(
            btn_row, text="Extract Manually...", command=self._extract_manually, width=170
        )
        self._manual_btn.pack(side="left", padx=8, pady=8)

        # Activity log
        ctk.CTkLabel(
            self._parent, text="Activity Log", font=ctk.CTkFont(weight="bold")
        ).pack(anchor="w", padx=12, pady=(8, 2))
        self._log = ctk.CTkTextbox(self._parent, height=180, state="disabled", wrap="word")
        self._log.pack(fill="x", **pad)
        self._log.tag_config("success", foreground="#4CAF50")
        self._log.tag_config("error", foreground="#F44336")
        self._log.tag_config("waiting", foreground="#FFC107")

        # FFmpeg command preview
        ctk.CTkLabel(
            self._parent, text="FFmpeg Command", font=ctk.CTkFont(weight="bold")
        ).pack(anchor="w", padx=12, pady=(8, 2))
        self._cmd_box = ctk.CTkTextbox(self._parent, height=50, state="disabled", wrap="none")
        self._cmd_box.pack(fill="x", **pad)

        # Frame preview panel
        preview = ctk.CTkFrame(self._parent)
        preview.pack(fill="x", **pad)
        self._thumb_lbl = ctk.CTkLabel(
            preview, text="No frame yet", width=200, height=120,
            fg_color="#333333", corner_radius=4,
        )
        self._thumb_lbl.pack(side="left", padx=8, pady=8)
        info = ctk.CTkFrame(preview, fg_color="transparent")
        info.pack(side="left", fill="both", expand=True, padx=(0, 8))
        self._frame_name_lbl = ctk.CTkLabel(info, text="", anchor="w", font=ctk.CTkFont(size=11))
        self._frame_name_lbl.pack(anchor="w", pady=(8, 4))
        self._open_btn = ctk.CTkButton(
            info, text="Open in Viewer", command=self._open_in_viewer, width=130, state="disabled"
        )
        self._open_btn.pack(anchor="w")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _effective_output_folder(self) -> str:
        val = self._output_folder_var.get()
        if val:
            return val
        watch = self._watch_folder_var.get()
        return str(Path(watch) / _STILLS_SUBDIR) if watch else f"<watch folder>/{_STILLS_SUBDIR}"

    def _resolved_output_folder(self) -> str:
        val = self._output_folder_var.get()
        if val:
            return val
        return str(Path(self._watch_folder_var.get()) / _STILLS_SUBDIR)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _browse_watch_folder(self) -> None:
        folder = filedialog.askdirectory(title="Select Watch Folder")
        if folder:
            self._watch_folder_var.set(folder)
            self._output_folder_lbl.configure(text=self._effective_output_folder())
            self._save_settings()

    def _browse_output_folder(self) -> None:
        folder = filedialog.askdirectory(title="Select Output Folder")
        if folder:
            self._output_folder_var.set(folder)
            self._output_folder_lbl.configure(text=folder)
            self._save_settings()

    def _on_format_change(self, _=None) -> None:
        self._save_settings()

    def _on_watcher_toggle(self) -> None:
        if self._watcher_enabled_var.get():
            self._start_watcher()
        else:
            self._stop_watcher()
        self._save_settings()

    def _extract_manually(self) -> None:
        path = filedialog.askopenfilename(
            title="Select Video File",
            filetypes=[("MP4 files", "*.mp4")],
        )
        if not path:
            return
        self._manual_btn.configure(state="disabled")
        self._set_status("processing")
        self._service.extract_one(
            Path(path),
            self._resolved_output_folder(),
            self._format_var.get().lower(),
            self._on_manual_result,
        )

    # ------------------------------------------------------------------
    # Watcher lifecycle
    # ------------------------------------------------------------------

    def _start_watcher(self) -> None:
        watch_folder = self._watch_folder_var.get()
        if not watch_folder or not Path(watch_folder).exists():
            self._set_status("error")
            self._log_line(f"Watch folder not found: {watch_folder}", tag="error")
            self._watcher_enabled_var.set(0)
            return
        self._service.start(
            watch_folder,
            self._resolved_output_folder(),
            self._format_var.get().lower(),
            self._on_result,
        )
        self._watching = True
        self._set_status("watching")
        self._log_line(f"Watching: {watch_folder}", tag="success")

    def _stop_watcher(self) -> None:
        self._service.stop()
        self._watching = False
        self._set_status("idle")
        self._log_line("Watcher stopped.", tag=None)

    # ------------------------------------------------------------------
    # Result callbacks (always called on main thread via root.after)
    # ------------------------------------------------------------------

    def _on_result(self, result: ExtractionResult) -> None:
        self._update_cmd_box(result.ffmpeg_cmd)
        if result.success and result.output_path:
            self._log_line(f"✓ {result.output_path.name}", tag="success")
            self._update_preview(result.output_path)
        else:
            self._log_line(f"✗ {result.job.source_path.name}: {result.error}", tag="error")
            if self._watching:
                self._set_status("watching")

    def _on_manual_result(self, result: ExtractionResult) -> None:
        self._manual_btn.configure(state="normal")
        self._on_result(result)
        self._set_status("watching" if self._watching else "idle")

    # ------------------------------------------------------------------
    # UI updates
    # ------------------------------------------------------------------

    def _log_line(self, text: str, tag: str | None) -> None:
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self._log.configure(state="normal")
        self._log.insert("end", f"{ts}  {text}\n", tag or "")
        self._log.see("end")
        self._log.configure(state="disabled")

    def _update_cmd_box(self, cmd: list[str]) -> None:
        text = " ".join(f'"{x}"' if " " in str(x) else str(x) for x in cmd)
        self._cmd_box.configure(state="normal")
        self._cmd_box.delete("1.0", "end")
        self._cmd_box.insert("end", text)
        self._cmd_box.configure(state="disabled")

    def _update_preview(self, path: Path) -> None:
        try:
            with Image.open(path) as src:
                src.thumbnail((200, 120), Image.Resampling.LANCZOS)
                img = src.copy()
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
            self._thumb_lbl.configure(image=ctk_img, text="")
            self._thumb_lbl._ctk_image = ctk_img  # prevent GC
            self._frame_name_lbl.configure(text=path.name)
            self._last_output_path = path
            self._open_btn.configure(state="normal")
        except Exception as exc:
            logger.warning("Preview update failed: %s", exc)

    def _set_status(self, state: str) -> None:
        label = _STATUS_LABELS.get(state, "● Idle")
        colour = _STATUS_COLOURS.get(state, ("gray80", "gray40"))
        self._status_lbl.configure(text=label, text_color=colour)

    def _open_in_viewer(self) -> None:
        if self._last_output_path and self._last_output_path.exists():
            os.startfile(str(self._last_output_path))

    def _save_settings(self) -> None:
        s = settings_manager.load()
        s["video_watch_folder"] = self._watch_folder_var.get()
        s["video_output_folder"] = self._output_folder_var.get()
        s["video_format"] = self._format_var.get().lower()
        s["video_watcher_enabled"] = bool(self._watcher_enabled_var.get())
        settings_manager.save(s)
