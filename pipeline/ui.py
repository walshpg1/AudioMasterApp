from __future__ import annotations
import datetime
import logging
import os
import threading
from pathlib import Path
from tkinter import filedialog
from typing import Optional

import customtkinter as ctk
from PIL import Image

import settings_manager
from ffmpeg_utils import find_ffmpeg
from pipeline.models import MuxJob, MuxResult
from pipeline.mux_runner import run_mux
from video_tools.extraction_service import ExtractionService
from video_tools.models import ExtractionResult

logger = logging.getLogger(__name__)

_LTX_FOLDER          = Path(r"D:\AIStudio\Apps\AIVideoStudio\renders\video\LTX")
_LTX_DIRECTOR_FOLDER = Path(r"D:\AIStudio\Apps\AIVideoStudio\renders\video\LTX_Director")
_AUDIO_PROCESSED_DIR = Path(r"D:\AIStudio\Apps\AIVideoStudio\audio\processed")
_STILLS_FOLDER       = Path(r"D:\AIStudio\Apps\AIVideoStudio\renders\video\stills")
_AUDIO_EXTENSIONS    = frozenset({".wav", ".mp3"})

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


def find_latest_audio(audio_dir: Path, extensions: frozenset[str]) -> Optional[Path]:
    """Return the most recently modified audio file in audio_dir, or None."""
    if not audio_dir.exists():
        return None
    candidates = [
        p for p in audio_dir.iterdir()
        if p.is_file() and p.suffix.lower() in extensions
    ]
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None


def _mux_is_ready(
    video_path: Optional[Path],
    audio_path: Optional[Path],
    mux_running: bool,
) -> bool:
    return bool(video_path and audio_path and not mux_running)


class PipelineTab:
    """Builds and owns the Pipeline tab UI."""

    def __init__(self, parent: ctk.CTkFrame, root: ctk.CTk) -> None:
        self._parent = parent
        self._root = root
        self._service_ltx = ExtractionService(root)
        self._service_dir = ExtractionService(root)
        self._watching = False
        self._last_video_path: Optional[Path] = None
        self._last_output_path: Optional[Path] = None
        self._audio_path: Optional[Path] = None
        self._mux_running = False

        s = settings_manager.load()
        self._output_folder_var = ctk.StringVar(
            value=s.get("pipeline_output_folder", r"D:\AIStudio\Apps\AIVideoStudio\exports\tiktok")
        )
        self._watcher_enabled_var = ctk.IntVar(
            value=int(s.get("pipeline_watcher_enabled", False))
        )

        self._build_ui()
        self._detect_audio()
        if self._watcher_enabled_var.get():
            self._start_watchers()

    def _build_ui(self) -> None:
        pad = {"padx": 12, "pady": 4}

        ctk.CTkLabel(
            self._parent,
            text="LTX Pipeline",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=12, pady=(12, 4))

        # Watch status row
        watch_row = ctk.CTkFrame(self._parent)
        watch_row.pack(fill="x", **pad)
        ctk.CTkLabel(
            watch_row,
            text="renders\\video\\LTX\\  +  LTX_Director\\",
            anchor="w",
            font=ctk.CTkFont(size=11),
        ).pack(side="left", padx=8, pady=8, fill="x", expand=True)
        self._status_lbl = ctk.CTkLabel(watch_row, text="● Idle", width=100, anchor="e")
        self._status_lbl.pack(side="right", padx=(0, 4), pady=8)
        ctk.CTkSwitch(
            watch_row,
            text="Enable",
            variable=self._watcher_enabled_var,
            command=self._on_watcher_toggle,
            width=80,
        ).pack(side="right", padx=4, pady=8)

        # Render feed
        ctk.CTkLabel(
            self._parent, text="Render Feed", font=ctk.CTkFont(weight="bold")
        ).pack(anchor="w", padx=12, pady=(8, 2))
        self._feed = ctk.CTkTextbox(self._parent, height=160, state="disabled", wrap="word")
        self._feed.pack(fill="x", **pad)
        self._feed.tag_config("success", foreground="#4CAF50")
        self._feed.tag_config("error", foreground="#F44336")
        self._feed.tag_config("waiting", foreground="#FFC107")

        # Last frame preview
        preview = ctk.CTkFrame(self._parent)
        preview.pack(fill="x", **pad)
        self._thumb_lbl = ctk.CTkLabel(
            preview, text="No frame yet", width=120, height=72,
            fg_color="#333333", corner_radius=4,
        )
        self._thumb_lbl.pack(side="left", padx=8, pady=8)
        info = ctk.CTkFrame(preview, fg_color="transparent")
        info.pack(side="left", fill="both", expand=True, padx=(0, 8))
        self._frame_name_lbl = ctk.CTkLabel(info, text="", anchor="w", font=ctk.CTkFont(size=11))
        self._frame_name_lbl.pack(anchor="w", pady=(8, 2))
        self._frame_source_lbl = ctk.CTkLabel(
            info, text="", anchor="w", font=ctk.CTkFont(size=10), text_color="gray60"
        )
        self._frame_source_lbl.pack(anchor="w", pady=(0, 4))
        self._open_btn = ctk.CTkButton(
            info, text="Open in Viewer", command=self._open_in_viewer, width=120, state="disabled"
        )
        self._open_btn.pack(anchor="w")

        # Audio master row
        audio_row = ctk.CTkFrame(self._parent)
        audio_row.pack(fill="x", **pad)
        ctk.CTkLabel(audio_row, text="Audio:", width=55).pack(side="left", padx=(8, 0), pady=8)
        self._audio_lbl = ctk.CTkLabel(
            audio_row, text="Detecting...", anchor="w", font=ctk.CTkFont(size=11)
        )
        self._audio_lbl.pack(side="left", fill="x", expand=True, padx=4, pady=8)
        ctk.CTkButton(
            audio_row, text="Browse...", command=self._browse_audio, width=90
        ).pack(side="right", padx=8, pady=8)

        # Output folder row
        out_row = ctk.CTkFrame(self._parent)
        out_row.pack(fill="x", **pad)
        ctk.CTkLabel(out_row, text="Output:", width=55).pack(side="left", padx=(8, 0), pady=8)
        ctk.CTkLabel(
            out_row, textvariable=self._output_folder_var, anchor="w", font=ctk.CTkFont(size=11)
        ).pack(side="left", fill="x", expand=True, padx=4, pady=8)
        ctk.CTkButton(
            out_row, text="Browse...", command=self._browse_output, width=90
        ).pack(side="right", padx=8, pady=8)

        # Mux button
        mux_row = ctk.CTkFrame(self._parent)
        mux_row.pack(fill="x", **pad)
        self._mux_btn = ctk.CTkButton(
            mux_row, text="Mux Video + Audio →", command=self._do_mux, state="disabled"
        )
        self._mux_btn.pack(fill="x", padx=8, pady=8)

    def _detect_audio(self) -> None:
        self._audio_path = find_latest_audio(_AUDIO_PROCESSED_DIR, _AUDIO_EXTENSIONS)
        if self._audio_path:
            self._audio_lbl.configure(text=f"🎵 {self._audio_path.name} (auto-detected)")
        else:
            self._audio_lbl.configure(text="No audio file — use Browse")
        self._update_mux_btn()

    def _update_mux_btn(self) -> None:
        ready = _mux_is_ready(self._last_video_path, self._audio_path, self._mux_running)
        self._mux_btn.configure(state="normal" if ready else "disabled")

    def _on_watcher_toggle(self) -> None:
        if self._watcher_enabled_var.get():
            self._start_watchers()
        else:
            self._stop_watchers()
        self._save_settings()

    def _start_watchers(self) -> None:
        _STILLS_FOLDER.mkdir(parents=True, exist_ok=True)
        stills = str(_STILLS_FOLDER)

        if _LTX_FOLDER.exists():
            self._service_ltx.start(
                str(_LTX_FOLDER), stills, "png",
                lambda r: self._on_extraction(r, "LTX"),
            )
        else:
            self._log_line("Warning: LTX folder not found, skipping", tag="waiting")

        if _LTX_DIRECTOR_FOLDER.exists():
            self._service_dir.start(
                str(_LTX_DIRECTOR_FOLDER), stills, "png",
                lambda r: self._on_extraction(r, "DIR"),
            )
        else:
            self._log_line("Warning: LTX_Director folder not found, skipping", tag="waiting")

        self._watching = True
        self._set_status("watching")
        self._log_line("Watching LTX + LTX_Director", tag="success")

    def _stop_watchers(self) -> None:
        self._service_ltx.stop()
        self._service_dir.stop()
        self._watching = False
        self._set_status("idle")
        self._log_line("Watcher stopped", tag=None)

    def _on_extraction(self, result: ExtractionResult, source: str) -> None:
        if result.success and result.output_path:
            self._log_line(f"✓ {result.output_path.name}", tag="success", source=source)
            self._last_video_path = result.job.source_path
            self._last_output_path = result.output_path
            self._update_preview(result.output_path, source)
            self._update_mux_btn()
        else:
            self._log_line(
                f"✗ {result.job.source_path.name}: {result.error}", tag="error", source=source
            )

    def _do_mux(self) -> None:
        if not self._last_video_path or not self._audio_path:
            return
        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            self._log_line("FFmpeg not found — cannot mux", tag="error")
            return
        output_folder = Path(self._output_folder_var.get())
        output_folder.mkdir(parents=True, exist_ok=True)
        output_path = output_folder / f"{self._last_video_path.stem}_audio.mp4"
        job = MuxJob(
            video_path=self._last_video_path,
            audio_path=self._audio_path,
            output_path=output_path,
        )
        self._mux_running = True
        self._update_mux_btn()
        self._log_line(f"Muxing → {output_path.name}...", tag=None)

        def _on_done(result: MuxResult) -> None:
            self._root.after(0, lambda r=result: self._on_mux_result(r))

        threading.Thread(target=run_mux, args=(job, ffmpeg, _on_done), daemon=True).start()

    def _on_mux_result(self, result: MuxResult) -> None:
        self._mux_running = False
        if result.success:
            self._log_line(f"✓ Mux complete: {result.job.output_path.name}", tag="success")
        else:
            self._log_line(f"✗ Mux failed: {result.error}", tag="error")
        self._update_mux_btn()

    def _log_line(self, text: str, tag: str | None, source: str = "") -> None:
        ts = datetime.datetime.now().strftime("%H:%M")
        src_tag = f"  [{source}]" if source else ""
        self._feed.configure(state="normal")
        self._feed.insert("end", f"{ts}{src_tag}  {text}\n", tag or "")
        self._feed.see("end")
        self._feed.configure(state="disabled")

    def _update_preview(self, path: Path, source: str) -> None:
        try:
            with Image.open(path) as src:
                src.thumbnail((120, 72), Image.Resampling.LANCZOS)
                img = src.copy()
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
            self._thumb_lbl.configure(image=ctk_img, text="")
            self._thumb_lbl._ctk_image = ctk_img  # prevent GC
            self._frame_name_lbl.configure(text=path.name)
            self._frame_source_lbl.configure(
                text=f"{source} · {datetime.datetime.now().strftime('%H:%M')}"
            )
            self._open_btn.configure(state="normal")
        except Exception as exc:
            logger.warning("Preview update failed: %s", exc)

    def _set_status(self, state: str) -> None:
        self._status_lbl.configure(
            text=_STATUS_LABELS.get(state, "● Idle"),
            text_color=_STATUS_COLOURS.get(state, ("gray80", "gray40")),
        )

    def _open_in_viewer(self) -> None:
        if self._last_output_path and self._last_output_path.exists():
            os.startfile(str(self._last_output_path))

    def _browse_audio(self) -> None:
        path = filedialog.askopenfilename(
            title="Select Audio File",
            filetypes=[("Audio files", "*.wav *.mp3")],
        )
        if path:
            self._audio_path = Path(path)
            self._audio_lbl.configure(text=f"🎵 {self._audio_path.name}")
            self._update_mux_btn()

    def _browse_output(self) -> None:
        folder = filedialog.askdirectory(title="Select Output Folder")
        if folder:
            self._output_folder_var.set(folder)
            self._save_settings()

    def _save_settings(self) -> None:
        s = settings_manager.load()
        s["pipeline_output_folder"] = self._output_folder_var.get()
        s["pipeline_watcher_enabled"] = bool(self._watcher_enabled_var.get())
        settings_manager.save(s)
