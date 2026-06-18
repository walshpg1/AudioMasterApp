from __future__ import annotations
import logging
import os
import threading
from pathlib import Path

import customtkinter as ctk

import settings_manager
from ffmpeg_utils import find_ffmpeg
from youtube_import.downloader import find_ytdlp, YoutubeDownloader, DOWNLOADS_DIR
from youtube_import.models import DownloadJob, DownloadResult

logger = logging.getLogger(__name__)

_LEGAL_NOTE = (
    "⚠  Only download audio you own, have permission to use,\n"
    "   or that is royalty-free / public-domain."
)

_IDLE        = "IDLE"
_DOWNLOADING = "DOWNLOADING"
_CONVERTING  = "CONVERTING"
_COMPLETE    = "COMPLETE"
_FAILED      = "FAILED"
_CANCELLED   = "CANCELLED"


class YouTubeImportTab:
    def __init__(self, parent, root) -> None:
        self._root  = root
        self._state = _IDLE
        self._output_path: Path | None = None
        self._cancel_event: threading.Event | None = None

        self._ytdlp_path  = find_ytdlp()
        self._ffmpeg_path = find_ffmpeg()

        self._build_ui(parent)
        self._apply_tool_state()
        self._load_settings()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self, parent) -> None:
        pad = {"padx": 12, "pady": 4}

        # URL section
        url_section = ctk.CTkFrame(parent)
        url_section.pack(fill="x", **pad)
        ctk.CTkLabel(url_section, text="URL", anchor="w").pack(
            anchor="w", padx=8, pady=(8, 2)
        )
        url_row = ctk.CTkFrame(url_section, fg_color="transparent")
        url_row.pack(fill="x", padx=8, pady=(0, 8))
        self._url_entry = ctk.CTkEntry(
            url_row, placeholder_text="paste YouTube URL here…"
        )
        self._url_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(
            url_row, text="Clear", width=70, command=self._clear_url
        ).pack(side="right")

        # Format selection
        fmt_section = ctk.CTkFrame(parent)
        fmt_section.pack(fill="x", **pad)
        ctk.CTkLabel(fmt_section, text="Output Format", anchor="w").pack(
            side="left", padx=8, pady=8
        )
        self._format_var = ctk.StringVar(value="mp3")
        for fmt in ("mp3", "wav", "flac"):
            ctk.CTkRadioButton(
                fmt_section, text=fmt.upper(),
                variable=self._format_var, value=fmt,
                command=self._on_format_change,
            ).pack(side="left", padx=8)

        # Tool warning label (packed only when a tool is missing)
        self._tool_warning_lbl = ctk.CTkLabel(
            parent, text="", anchor="w", justify="left",
            text_color="#FFC107", wraplength=480,
        )

        # Button row
        self._btn_row = ctk.CTkFrame(parent, fg_color="transparent")
        self._btn_row.pack(fill="x", padx=12, pady=4)
        self._download_btn = ctk.CTkButton(
            self._btn_row, text="Download", command=self._on_download
        )
        self._download_btn.pack(side="left")
        self._cancel_btn = ctk.CTkButton(
            self._btn_row, text="Cancel", command=self._on_cancel
        )
        # Cancel is packed/unpacked by _set_state

        # Progress section
        self._progress_frame = ctk.CTkFrame(parent, fg_color="transparent")
        self._progress_frame.pack(fill="x", padx=12)
        self._progress_bar = ctk.CTkProgressBar(self._progress_frame)
        self._progress_bar.set(0)
        # Progress bar is packed/unpacked by _set_state
        self._status_lbl = ctk.CTkLabel(
            self._progress_frame, text="", anchor="w"
        )
        self._status_lbl.pack(fill="x", pady=(2, 0))

        # Separator
        ctk.CTkFrame(parent, height=1, fg_color="gray30").pack(
            fill="x", padx=12, pady=8
        )

        # Result section
        result_section = ctk.CTkFrame(parent, fg_color="transparent")
        result_section.pack(fill="x", padx=12)
        self._output_lbl = ctk.CTkLabel(result_section, text="", anchor="w")
        self._output_lbl.pack(anchor="w")
        self._action_row = ctk.CTkFrame(result_section, fg_color="transparent")
        self._action_row.pack(fill="x", pady=(4, 0))
        ctk.CTkButton(
            self._action_row, text="Open Downloads Folder",
            command=self._open_downloads_folder, width=180,
        ).pack(side="left")
        self._load_btn = ctk.CTkButton(
            self._action_row, text="Load into Single File Mastering",
            command=self._on_load, width=220,
        )
        # Load btn is packed/unpacked by _set_state

        # Separator + legal note
        ctk.CTkFrame(parent, height=1, fg_color="gray30").pack(
            fill="x", padx=12, pady=8
        )
        ctk.CTkLabel(
            parent, text=_LEGAL_NOTE,
            anchor="w", justify="left",
            text_color="gray", font=ctk.CTkFont(size=11),
        ).pack(fill="x", padx=12)

    def _apply_tool_state(self) -> None:
        if self._ytdlp_path and self._ffmpeg_path:
            return  # both tools present — nothing to do

        self._download_btn.pack_forget()

        if not self._ytdlp_path:
            msg = (
                "⚠  yt-dlp not found.\n"
                "   Install with:  pip install yt-dlp   or   winget install yt-dlp\n"
                "   Then restart the app."
            )
        else:
            msg = "⚠  FFmpeg not found. AudioMasterApp requires FFmpeg to be installed."

        self._tool_warning_lbl.configure(text=msg)
        self._tool_warning_lbl.pack(fill="x", padx=12, pady=(4, 0))

    def _load_settings(self) -> None:
        s = getattr(self._root, "_settings", {})
        fmt = s.get("youtube_output_format", "mp3")
        if fmt in ("mp3", "wav", "flac"):
            self._format_var.set(fmt)
        last_url = s.get("youtube_last_url", "")
        if last_url:
            self._url_entry.insert(0, last_url)

    # ------------------------------------------------------------------
    # State machine
    # ------------------------------------------------------------------

    def _set_state(self, state: str) -> None:
        self._state = state
        is_active = state in (_DOWNLOADING, _CONVERTING)

        self._download_btn.configure(state="disabled" if is_active else "normal")

        if is_active:
            self._cancel_btn.pack(side="left", padx=(8, 0))
        else:
            self._cancel_btn.pack_forget()

        if state in (_IDLE, _FAILED, _CANCELLED):
            self._progress_bar.stop()
            self._progress_bar.pack_forget()
        elif state == _COMPLETE:
            self._progress_bar.stop()
            self._progress_bar.configure(mode="determinate")
            self._progress_bar.set(1.0)
            if not self._progress_bar.winfo_ismapped():
                self._progress_bar.pack(fill="x")
        else:  # DOWNLOADING / CONVERTING
            if not self._progress_bar.winfo_ismapped():
                self._progress_bar.pack(fill="x")

        if state == _COMPLETE:
            self._load_btn.pack(side="left", padx=(8, 0))
        else:
            self._load_btn.pack_forget()

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _clear_url(self) -> None:
        self._url_entry.delete(0, "end")

    def _on_format_change(self) -> None:
        if hasattr(self._root, "_settings"):
            self._root._settings["youtube_output_format"] = self._format_var.get()
            settings_manager.save(self._root._settings)

    def _on_download(self) -> None:
        url = self._url_entry.get().strip()
        if not url:
            self._status_lbl.configure(text="Please paste a YouTube URL first.")
            return
        if not self._ytdlp_path or not self._ffmpeg_path:
            return

        if hasattr(self._root, "_settings"):
            self._root._settings["youtube_last_url"] = url
            settings_manager.save(self._root._settings)

        self._cancel_event  = threading.Event()
        self._output_path   = None
        self._output_lbl.configure(text="")
        self._status_lbl.configure(text="Downloading…")
        self._set_state(_DOWNLOADING)

        job = DownloadJob(
            url=url,
            output_format=self._format_var.get(),
            output_dir=DOWNLOADS_DIR,
            ffmpeg_path=self._ffmpeg_path,
            ytdlp_path=self._ytdlp_path,
        )
        cancel_ev = self._cancel_event
        threading.Thread(
            target=self._worker, args=(job, cancel_ev), daemon=True
        ).start()

    def _on_cancel(self) -> None:
        if self._cancel_event:
            self._cancel_event.set()

    def _worker(self, job: DownloadJob, cancel_event: threading.Event) -> None:
        YoutubeDownloader().run(
            job,
            progress_cb=lambda phase, frac: self._root.after(
                0, self._on_progress, phase, frac
            ),
            done_cb=lambda result: self._root.after(0, self._on_done, result),
            cancel_event=cancel_event,
        )

    def _on_progress(self, phase: str, fraction: float | None) -> None:
        if phase == "downloading" and fraction is not None:
            self._progress_bar.configure(mode="determinate")
            self._progress_bar.set(fraction)
            self._status_lbl.configure(
                text=f"Downloading…  {fraction * 100:.0f}%"
            )
        else:
            self._progress_bar.configure(mode="indeterminate")
            self._progress_bar.start()
            label = "Converting…" if phase == "converting" else "Downloading…"
            self._status_lbl.configure(text=label)

    def _on_done(self, result: DownloadResult) -> None:
        self._progress_bar.stop()
        if result.error == "Cancelled":
            self._status_lbl.configure(text="Cancelled")
            self._set_state(_CANCELLED)
        elif result.success and result.output_path:
            self._output_path = result.output_path
            filename = result.output_path.name
            self._output_lbl.configure(text=f"Output:  {filename}")
            self._status_lbl.configure(text=f"Complete — {filename}")
            self._set_state(_COMPLETE)
        else:
            self._status_lbl.configure(
                text=f"Failed: {result.error or 'Unknown error'}"
            )
            self._set_state(_FAILED)

    def _open_downloads_folder(self) -> None:
        DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(str(DOWNLOADS_DIR))

    def _on_load(self) -> None:
        if self._output_path and self._output_path.exists():
            self._root.load_file_for_mastering(self._output_path)
        else:
            self._status_lbl.configure(text="Downloaded file no longer found.")
