from __future__ import annotations
import logging
import logging.handlers
import math
import os
import re
import sys
import threading
from pathlib import Path
from tkinter import filedialog, IntVar

import customtkinter as ctk

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

import audio_preview
import settings_manager
import loudness_report
from ffmpeg_utils import check_ffmpeg
from version import APP_VERSION
from audio_analysis import analyse, AnalysisResult
from batch_processor import process_batch, BatchFileResult, BatchSummary, SUPPORTED_EXTENSIONS
from export_formats import list_export_formats, ExportFormat
from folder_watcher import FolderWatcher
from mastering_engine import master, list_presets
import resolve_handoff
from audio_splitter import split_audio, SplitResult as SplitAudioResult

# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

_STATUS_COLOURS = {
    "normal": ("white", "gray80"),
    "success": ("#4CAF50", "#388E3C"),
    "warning": ("#FFC107", "#F9A825"),
    "error": ("#F44336", "#C62828"),
}

_GEOMETRY_RE = re.compile(r"^\d+x\d+[+-]\d+[+-]\d+$")

# Base directory: beside the exe when packaged, beside app.py in dev mode.
_APP_DIR: Path = (
    Path(sys.executable).parent if getattr(sys, "frozen", False)
    else Path(__file__).parent
)
_DEFAULT_OUTPUT_DIR = _APP_DIR / "output"


def _ensure_runtime_dirs() -> None:
    """Create output/reports/logs/temp beside the app on first run."""
    for name in ("output", "reports", "logs", "temp"):
        (_APP_DIR / name).mkdir(parents=True, exist_ok=True)

# Matplotlib preview theme (dark mode)
_PLT_BG = "#2b2b2b"    # figure / axes background
_PLT_FG = "#909090"    # axis labels, ticks, spines
_PLT_WAVE = "#4da6ff"  # waveform line
_PLT_SPEC = "#ff9944"  # spectrum line


class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("AudioMasterApp")
        self.geometry("520x960")
        self.resizable(False, False)

        self._loading = True

        # Single-file state
        _ensure_runtime_dirs()

        self._wav_path: str | None = None
        self._last_output_path: str | None = None
        self._last_handoff_note_path: str | None = None
        self._clip_duration_var = ctk.StringVar(value="5")
        self._last_clips_dir: Path | None = None
        self._preview_path: str | None = None
        self._ffmpeg_status: tuple[bool, str] | None = None
        self._output_dir: Path = _DEFAULT_OUTPUT_DIR
        self._settings: dict = settings_manager._defaults()

        # Preset / format registries (shared across tabs)
        self._presets = list_presets()
        self._preset_map = {p["name"]: p for p in self._presets}
        self._export_formats = list_export_formats()
        self._format_map = {f.name: f for f in self._export_formats}

        # Checkbox variables (must exist before _build_ui)
        self._auto_report_var = IntVar(value=0)
        self._handoff_note_var = IntVar(value=0)
        self._move_processed_var = IntVar(value=1)
        self._move_failed_var = IntVar(value=1)

        # Batch state
        self._batch_input_folder: Path | None = None
        self._batch_cancel_requested: bool = False
        self._batch_results: list = []

        # Watch state
        self._watch_folder: Path | None = None
        self._watch_stop_event: threading.Event = threading.Event()
        self._watching: bool = False

        self._build_ui()
        self._load_settings()
        self._loading = False

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        threading.Thread(target=self._ffmpeg_check_worker, daemon=True).start()

    # ==================================================================
    # UI construction
    # ==================================================================

    def _build_ui(self) -> None:
        # App header — packed first so it anchors to the top
        self._build_header()

        # Pack footer BEFORE tabview so expand=True on the tabview works
        self._status_lbl = ctk.CTkLabel(self, text="Ready", anchor="w")
        self._status_lbl.pack(side="bottom", fill="x", padx=16, pady=(0, 8))

        self._progress = ctk.CTkProgressBar(self)
        self._progress.pack(side="bottom", fill="x", padx=16, pady=(0, 2))
        self._progress.set(0)

        self._tabview = ctk.CTkTabview(self)
        self._tabview.pack(fill="both", expand=True, padx=8, pady=(8, 4))
        self._tabview.add("Single File")
        self._tabview.add("Batch")
        self._tabview.add("Watch Folder")
        self._tabview.add("Preview")

        self._build_single_file_tab(self._tabview.tab("Single File"))
        self._build_batch_tab(self._tabview.tab("Batch"))
        self._build_watch_tab(self._tabview.tab("Watch Folder"))
        self._build_preview_tab(self._tabview.tab("Preview"))

    # ------------------------------------------------------------------
    # Single File tab
    # ------------------------------------------------------------------

    def _build_single_file_tab(self, parent) -> None:
        pad = {"padx": 12, "pady": 4}

        # File selector
        file_frame = ctk.CTkFrame(parent)
        file_frame.pack(fill="x", **pad)
        ctk.CTkButton(
            file_frame, text="Select Audio File...", command=self._select_file, width=160
        ).pack(side="left", padx=8, pady=8)
        self._file_label = ctk.CTkLabel(file_frame, text="No file selected", anchor="w")
        self._file_label.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(
            file_frame, text="Reset", command=self._reset, width=70
        ).pack(side="right", padx=(0, 8), pady=8)

        # Preset dropdown
        preset_frame = ctk.CTkFrame(parent)
        preset_frame.pack(fill="x", **pad)
        ctk.CTkLabel(preset_frame, text="Preset:", width=60).pack(side="left", padx=8, pady=8)
        self._preset_var = ctk.StringVar(value=self._presets[0]["name"])
        ctk.CTkOptionMenu(
            preset_frame,
            variable=self._preset_var,
            values=[p["name"] for p in self._presets],
            command=self._on_preset_change,
            width=300,
        ).pack(side="left", padx=8, pady=8)

        # Export format dropdown
        format_frame = ctk.CTkFrame(parent)
        format_frame.pack(fill="x", **pad)
        ctk.CTkLabel(format_frame, text="Format:", width=60).pack(side="left", padx=8, pady=8)
        self._format_var = ctk.StringVar(value=self._export_formats[0].name)
        ctk.CTkOptionMenu(
            format_frame,
            variable=self._format_var,
            values=[f.name for f in self._export_formats],
            command=self._on_format_change,
            width=300,
        ).pack(side="left", padx=8, pady=8)

        # Output folder selector
        output_frame = ctk.CTkFrame(parent)
        output_frame.pack(fill="x", **pad)
        ctk.CTkButton(
            output_frame, text="Output Folder...", command=self._select_output_folder, width=130
        ).pack(side="left", padx=8, pady=8)
        self._output_folder_label = ctk.CTkLabel(
            output_frame, text=str(_DEFAULT_OUTPUT_DIR),
            anchor="w", font=ctk.CTkFont(size=11),
        )
        self._output_folder_label.pack(side="left", fill="x", expand=True, padx=(0, 4))
        ctk.CTkButton(
            output_frame, text="Open", command=self._open_output_folder, width=55
        ).pack(side="right", padx=(0, 8), pady=8)

        # Analysis panel
        analysis_frame = ctk.CTkFrame(parent)
        analysis_frame.pack(fill="x", **pad)
        ctk.CTkLabel(
            analysis_frame, text="Analysis", font=ctk.CTkFont(weight="bold")
        ).pack(anchor="w", padx=12, pady=(8, 4))
        self._analysis_labels: dict[str, ctk.CTkLabel] = {}
        for field in [
            "Sample rate", "Bit depth", "Channels",
            "Duration", "Peak dBFS", "RMS dBFS", "Integrated LUFS",
        ]:
            row = ctk.CTkFrame(analysis_frame, fg_color="transparent")
            row.pack(fill="x", padx=8, pady=1)
            ctk.CTkLabel(row, text=f"{field}:", width=140, anchor="w").pack(side="left")
            lbl = ctk.CTkLabel(row, text="—", anchor="w")
            lbl.pack(side="left")
            self._analysis_labels[field] = lbl

        # Options panel
        options_frame = ctk.CTkFrame(parent)
        options_frame.pack(fill="x", **pad)
        ctk.CTkCheckBox(
            options_frame,
            text="Auto-generate loudness report after mastering",
            variable=self._auto_report_var,
            command=self._on_auto_report_change,
        ).pack(anchor="w", padx=12, pady=(8, 8))

        # Action buttons
        btn_frame = ctk.CTkFrame(parent, fg_color="transparent")
        btn_frame.pack(fill="x", padx=12, pady=4)
        ctk.CTkButton(
            btn_frame, text="Analyse", command=self._run_analyse, width=215
        ).pack(side="left", padx=(0, 8))
        self._master_btn = ctk.CTkButton(
            btn_frame, text="Master File", command=self._run_master, width=215, state="disabled"
        )
        self._master_btn.pack(side="left")

        # Play button
        play_frame = ctk.CTkFrame(parent, fg_color="transparent")
        play_frame.pack(fill="x", padx=12, pady=(0, 4))
        self._play_btn = ctk.CTkButton(
            play_frame, text="▶  Play Mastered File",
            command=self._play_output, state="disabled",
        )
        self._play_btn.pack(fill="x")

        # Open Latest Report button
        report_frame_single = ctk.CTkFrame(parent, fg_color="transparent")
        report_frame_single.pack(fill="x", padx=12, pady=(0, 4))
        self._report_btn_single = ctk.CTkButton(
            report_frame_single, text="Open Latest Report",
            command=self._open_latest_report, state="disabled",
        )
        self._report_btn_single.pack(fill="x")

        self._build_clip_splitter_panel(parent)

        # DaVinci Resolve Free handoff panel
        handoff_frame = ctk.CTkFrame(parent)
        handoff_frame.pack(fill="x", **pad)
        ctk.CTkLabel(
            handoff_frame, text="DaVinci Resolve Handoff",
            font=ctk.CTkFont(weight="bold"),
        ).pack(anchor="w", padx=12, pady=(8, 2))
        ctk.CTkLabel(
            handoff_frame,
            text="Free Resolve requires manual import into Media Pool.",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        ).pack(anchor="w", padx=12, pady=(0, 6))
        handoff_btn_row = ctk.CTkFrame(handoff_frame, fg_color="transparent")
        handoff_btn_row.pack(fill="x", padx=12, pady=(0, 4))
        self._copy_path_btn = ctk.CTkButton(
            handoff_btn_row, text="Copy File Path",
            command=self._copy_path_to_clipboard, width=150, state="disabled",
        )
        self._copy_path_btn.pack(side="left", padx=(0, 8))
        self._open_handoff_btn = ctk.CTkButton(
            handoff_btn_row, text="Open Handoff Note",
            command=self._open_handoff_note, width=160, state="disabled",
        )
        self._open_handoff_btn.pack(side="left")
        ctk.CTkCheckBox(
            handoff_frame,
            text="Write .txt handoff note beside mastered file",
            variable=self._handoff_note_var,
            command=self._on_handoff_note_change,
        ).pack(anchor="w", padx=12, pady=(0, 8))

    def _build_clip_splitter_panel(self, parent) -> None:
        pad = {"padx": 12, "pady": 4}

        panel = ctk.CTkFrame(parent)
        panel.pack(fill="x", **pad)

        ctk.CTkLabel(
            panel, text="Clip Splitter",
            font=ctk.CTkFont(weight="bold"),
        ).pack(anchor="w", padx=12, pady=(8, 2))
        ctk.CTkLabel(
            panel,
            text="Masters the file, then cuts it into equal-length clips.",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        ).pack(anchor="w", padx=12, pady=(0, 6))

        dur_row = ctk.CTkFrame(panel, fg_color="transparent")
        dur_row.pack(fill="x", padx=12, pady=(0, 6))
        ctk.CTkLabel(dur_row, text="Clip duration (s):", width=130, anchor="w").pack(side="left")
        ctk.CTkEntry(dur_row, width=70, textvariable=self._clip_duration_var).pack(side="left")

        btn_row = ctk.CTkFrame(panel, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=(0, 10))
        self._master_split_btn = ctk.CTkButton(
            btn_row, text="Master & Split",
            command=self._run_master_and_split, width=160, state="disabled",
        )
        self._master_split_btn.pack(side="left", padx=(0, 8))
        self._open_clips_btn = ctk.CTkButton(
            btn_row, text="Open Clips Folder",
            command=self._open_clips_folder, width=160, state="disabled",
        )
        self._open_clips_btn.pack(side="left")

    # ------------------------------------------------------------------
    # Batch tab
    # ------------------------------------------------------------------

    def _build_batch_tab(self, parent) -> None:
        pad = {"padx": 12, "pady": 4}

        # Input folder selector
        folder_frame = ctk.CTkFrame(parent)
        folder_frame.pack(fill="x", **pad)
        ctk.CTkButton(
            folder_frame, text="Select Folder...", command=self._select_batch_folder, width=130
        ).pack(side="left", padx=8, pady=8)
        self._batch_folder_label = ctk.CTkLabel(
            folder_frame, text="No folder selected", anchor="w"
        )
        self._batch_folder_label.pack(side="left", fill="x", expand=True, padx=(0, 8))

        # Preset dropdown (independent from single-file tab)
        b_preset_frame = ctk.CTkFrame(parent)
        b_preset_frame.pack(fill="x", **pad)
        ctk.CTkLabel(b_preset_frame, text="Preset:", width=60).pack(side="left", padx=8, pady=8)
        self._batch_preset_var = ctk.StringVar(value=self._presets[0]["name"])
        ctk.CTkOptionMenu(
            b_preset_frame,
            variable=self._batch_preset_var,
            values=[p["name"] for p in self._presets],
            width=300,
        ).pack(side="left", padx=8, pady=8)

        # Format dropdown (independent)
        b_format_frame = ctk.CTkFrame(parent)
        b_format_frame.pack(fill="x", **pad)
        ctk.CTkLabel(b_format_frame, text="Format:", width=60).pack(side="left", padx=8, pady=8)
        self._batch_format_var = ctk.StringVar(value=self._export_formats[0].name)
        ctk.CTkOptionMenu(
            b_format_frame,
            variable=self._batch_format_var,
            values=[f.name for f in self._export_formats],
            width=300,
        ).pack(side="left", padx=8, pady=8)

        # Output folder display (mirrors single-file setting)
        out_row = ctk.CTkFrame(parent)
        out_row.pack(fill="x", **pad)
        ctk.CTkLabel(out_row, text="Output:", width=60).pack(side="left", padx=8, pady=6)
        self._batch_output_label = ctk.CTkLabel(
            out_row, text=str(_DEFAULT_OUTPUT_DIR),
            anchor="w", font=ctk.CTkFont(size=11),
        )
        self._batch_output_label.pack(side="left", fill="x", expand=True)

        # Start / Cancel buttons
        ctrl_frame = ctk.CTkFrame(parent, fg_color="transparent")
        ctrl_frame.pack(fill="x", padx=12, pady=4)
        self._batch_start_btn = ctk.CTkButton(
            ctrl_frame, text="Start Batch", command=self._start_batch, width=215
        )
        self._batch_start_btn.pack(side="left", padx=(0, 8))
        self._batch_cancel_btn = ctk.CTkButton(
            ctrl_frame, text="Cancel", command=self._cancel_batch,
            width=215, state="disabled",
        )
        self._batch_cancel_btn.pack(side="left")

        # Open Latest Report button (batch tab)
        report_frame_batch = ctk.CTkFrame(parent, fg_color="transparent")
        report_frame_batch.pack(fill="x", padx=12, pady=(0, 4))
        self._report_btn_batch = ctk.CTkButton(
            report_frame_batch, text="Open Latest Report",
            command=self._open_latest_report, state="disabled",
        )
        self._report_btn_batch.pack(fill="x")

        # Current file label
        self._batch_current_label = ctk.CTkLabel(
            parent, text="", anchor="w", font=ctk.CTkFont(size=11)
        )
        self._batch_current_label.pack(fill="x", padx=12, pady=(4, 0))

        # Batch log (scrollable, read-only)
        self._batch_log = ctk.CTkTextbox(
            parent, font=ctk.CTkFont(size=11, family="Courier New"), wrap="none"
        )
        self._batch_log.pack(fill="both", expand=True, padx=12, pady=(4, 8))
        self._batch_log.configure(state="disabled")

    # ------------------------------------------------------------------
    # Watch Folder tab
    # ------------------------------------------------------------------

    def _build_watch_tab(self, parent) -> None:
        pad = {"padx": 12, "pady": 4}

        # Watch folder selector
        folder_frame = ctk.CTkFrame(parent)
        folder_frame.pack(fill="x", **pad)
        ctk.CTkButton(
            folder_frame, text="Select Watch Folder...",
            command=self._select_watch_folder, width=160,
        ).pack(side="left", padx=8, pady=8)
        self._watch_folder_label = ctk.CTkLabel(
            folder_frame, text="No folder selected", anchor="w"
        )
        self._watch_folder_label.pack(side="left", fill="x", expand=True, padx=(0, 8))

        # Preset dropdown (independent)
        w_preset_frame = ctk.CTkFrame(parent)
        w_preset_frame.pack(fill="x", **pad)
        ctk.CTkLabel(w_preset_frame, text="Preset:", width=60).pack(
            side="left", padx=8, pady=8
        )
        self._watch_preset_var = ctk.StringVar(value=self._presets[0]["name"])
        ctk.CTkOptionMenu(
            w_preset_frame,
            variable=self._watch_preset_var,
            values=[p["name"] for p in self._presets],
            width=300,
        ).pack(side="left", padx=8, pady=8)

        # Export format dropdown (independent)
        w_format_frame = ctk.CTkFrame(parent)
        w_format_frame.pack(fill="x", **pad)
        ctk.CTkLabel(w_format_frame, text="Format:", width=60).pack(
            side="left", padx=8, pady=8
        )
        self._watch_format_var = ctk.StringVar(value=self._export_formats[0].name)
        ctk.CTkOptionMenu(
            w_format_frame,
            variable=self._watch_format_var,
            values=[f.name for f in self._export_formats],
            width=300,
        ).pack(side="left", padx=8, pady=8)

        # Output folder display (mirrors shared setting)
        out_row = ctk.CTkFrame(parent)
        out_row.pack(fill="x", **pad)
        ctk.CTkLabel(out_row, text="Output:", width=60).pack(
            side="left", padx=8, pady=6
        )
        self._watch_output_label = ctk.CTkLabel(
            out_row, text=str(_DEFAULT_OUTPUT_DIR),
            anchor="w", font=ctk.CTkFont(size=11),
        )
        self._watch_output_label.pack(side="left", fill="x", expand=True)

        # Options
        opts_frame = ctk.CTkFrame(parent)
        opts_frame.pack(fill="x", **pad)
        ctk.CTkCheckBox(
            opts_frame,
            text="Move processed originals to Processed/ subfolder",
            variable=self._move_processed_var,
            command=self._on_move_processed_change,
        ).pack(anchor="w", padx=12, pady=(8, 2))
        ctk.CTkCheckBox(
            opts_frame,
            text="Move failed originals to Failed/ subfolder",
            variable=self._move_failed_var,
            command=self._on_move_failed_change,
        ).pack(anchor="w", padx=12, pady=(2, 8))

        # Start / Stop buttons
        ctrl_frame = ctk.CTkFrame(parent, fg_color="transparent")
        ctrl_frame.pack(fill="x", padx=12, pady=4)
        self._watch_start_btn = ctk.CTkButton(
            ctrl_frame, text="Start Watch", command=self._start_watch, width=215,
        )
        self._watch_start_btn.pack(side="left", padx=(0, 8))
        self._watch_stop_btn = ctk.CTkButton(
            ctrl_frame, text="Stop Watch", command=self._stop_watch,
            width=215, state="disabled",
        )
        self._watch_stop_btn.pack(side="left")

        # Watch status label
        self._watch_status_lbl = ctk.CTkLabel(
            parent, text="Not watching",
            anchor="w", font=ctk.CTkFont(size=12, weight="bold"),
        )
        self._watch_status_lbl.pack(fill="x", padx=12, pady=(8, 2))

        # Activity log
        self._watch_log = ctk.CTkTextbox(
            parent, font=ctk.CTkFont(size=11, family="Courier New"), wrap="none"
        )
        self._watch_log.pack(fill="both", expand=True, padx=12, pady=(2, 8))
        self._watch_log.configure(state="disabled")

    # ------------------------------------------------------------------
    # Preview tab
    # ------------------------------------------------------------------

    def _build_preview_tab(self, parent) -> None:
        pad = {"padx": 12, "pady": 4}

        # Header row
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.pack(fill="x", **pad)
        self._preview_file_lbl = ctk.CTkLabel(
            header, text="No file selected", anchor="w",
            font=ctk.CTkFont(size=11),
        )
        self._preview_file_lbl.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            header, text="Refresh", command=self._refresh_preview_btn, width=90,
        ).pack(side="right")

        # Waveform figure
        wf_frame = ctk.CTkFrame(parent)
        wf_frame.pack(fill="x", padx=12, pady=(4, 2))
        self._waveform_fig = Figure(figsize=(5.5, 2.2), dpi=90, facecolor=_PLT_BG)
        self._waveform_ax = self._waveform_fig.add_subplot(111)
        self._waveform_fig.subplots_adjust(left=0.09, right=0.98, top=0.85, bottom=0.22)
        self._waveform_canvas = FigureCanvasTkAgg(self._waveform_fig, master=wf_frame)
        self._waveform_canvas.get_tk_widget().pack(fill="x", padx=4, pady=4)
        self._draw_preview_placeholder(
            self._waveform_ax, self._waveform_canvas,
            "Waveform", "Select a file to see waveform",
        )

        # Spectrum figure
        sp_frame = ctk.CTkFrame(parent)
        sp_frame.pack(fill="x", padx=12, pady=(2, 8))
        self._spectrum_fig = Figure(figsize=(5.5, 2.2), dpi=90, facecolor=_PLT_BG)
        self._spectrum_ax = self._spectrum_fig.add_subplot(111)
        self._spectrum_fig.subplots_adjust(left=0.09, right=0.98, top=0.85, bottom=0.22)
        self._spectrum_canvas = FigureCanvasTkAgg(self._spectrum_fig, master=sp_frame)
        self._spectrum_canvas.get_tk_widget().pack(fill="x", padx=4, pady=4)
        self._draw_preview_placeholder(
            self._spectrum_ax, self._spectrum_canvas,
            "Frequency Spectrum", "Select a file to see spectrum",
        )

    # ------------------------------------------------------------------
    # App header (title + About button)
    # ------------------------------------------------------------------

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(side="top", fill="x", padx=12, pady=(8, 0))
        ctk.CTkLabel(
            header,
            text=f"AudioMasterApp  v{APP_VERSION}",
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        ).pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            header,
            text="About",
            command=self._show_about_dialog,
            width=70,
            height=28,
        ).pack(side="right")

    def _show_about_dialog(self) -> None:
        available, ffmpeg_msg = self._ffmpeg_status or check_ffmpeg()
        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

        dialog = ctk.CTkToplevel(self)
        dialog.title("About AudioMasterApp")
        dialog.geometry("460x310")
        dialog.resizable(False, False)
        dialog.grab_set()

        ctk.CTkLabel(
            dialog, text="AudioMasterApp",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(pady=(20, 4))
        ctk.CTkLabel(
            dialog, text="Audio mastering for Windows",
            font=ctk.CTkFont(size=11), text_color="gray",
        ).pack(pady=(0, 16))

        info_frame = ctk.CTkFrame(dialog)
        info_frame.pack(fill="x", padx=24, pady=(0, 16))

        def _row(label: str, value: str, color: str = "white") -> None:
            row = ctk.CTkFrame(info_frame, fg_color="transparent")
            row.pack(fill="x", padx=8, pady=3)
            ctk.CTkLabel(
                row, text=label, width=110, anchor="w",
                font=ctk.CTkFont(size=11), text_color="gray",
            ).pack(side="left")
            ctk.CTkLabel(
                row, text=value, anchor="w",
                font=ctk.CTkFont(size=11), text_color=color,
            ).pack(side="left", fill="x", expand=True)

        _row("Version:", APP_VERSION)
        _row("Python:", py_ver)
        ffmpeg_color = "#4CAF50" if available else "#F44336"
        _row("FFmpeg:", ffmpeg_msg.splitlines()[0], color=ffmpeg_color)
        _row("Output folder:", str(_DEFAULT_OUTPUT_DIR))

        ctk.CTkButton(
            dialog, text="Close", command=dialog.destroy, width=100,
        ).pack(pady=(0, 20))

    # ==================================================================
    # FFmpeg startup check
    # ==================================================================

    def _ffmpeg_check_worker(self) -> None:
        status = check_ffmpeg()
        self._ffmpeg_status = status
        available, msg = status
        if not available:
            self.after(0, lambda m=msg: self._show_ffmpeg_warning(m))

    def _show_ffmpeg_warning(self, msg: str) -> None:
        self._set_status("FFmpeg not found — mastering unavailable", "error")
        dialog = ctk.CTkToplevel(self)
        dialog.title("FFmpeg Required")
        dialog.geometry("420x240")
        dialog.resizable(False, False)
        dialog.grab_set()
        ctk.CTkLabel(
            dialog, text="FFmpeg Not Found",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(padx=20, pady=(20, 8))
        ctk.CTkLabel(
            dialog, text=msg,
            anchor="w", justify="left",
            font=ctk.CTkFont(size=11),
            wraplength=380,
        ).pack(padx=20, pady=(0, 12), fill="x")
        ctk.CTkButton(dialog, text="Close", command=dialog.destroy).pack(pady=(0, 20))

    # ==================================================================
    # Settings persistence
    # ==================================================================

    def _load_settings(self) -> None:
        preset_names = [p["name"] for p in self._presets]
        self._settings = settings_manager.load(preset_names)

        stored_preset = self._settings.get("last_selected_preset")
        if stored_preset and stored_preset in self._preset_map:
            self._preset_var.set(stored_preset)
            self._batch_preset_var.set(stored_preset)
            self._watch_preset_var.set(stored_preset)

        stored_format = self._settings.get("last_selected_export_format")
        if stored_format and stored_format in self._format_map:
            self._format_var.set(stored_format)
            self._batch_format_var.set(stored_format)
            self._watch_format_var.set(stored_format)

        stored_output = self._settings.get("last_output_folder")
        if stored_output and Path(stored_output).is_dir():
            self._output_dir = Path(stored_output)
            self._output_folder_label.configure(text=stored_output)
            self._batch_output_label.configure(text=stored_output)
            self._watch_output_label.configure(text=stored_output)

        stored_watch = self._settings.get("last_watch_folder")
        if stored_watch and Path(stored_watch).is_dir():
            self._watch_folder = Path(stored_watch)
            self._watch_folder_label.configure(text=stored_watch)

        self._auto_report_var.set(1 if self._settings.get("auto_generate_report") else 0)
        self._handoff_note_var.set(1 if self._settings.get("resolve_handoff_note_enabled") else 0)
        self._move_processed_var.set(
            1 if self._settings.get("move_processed_originals_enabled", True) else 0
        )
        self._move_failed_var.set(
            1 if self._settings.get("move_failed_originals_enabled", True) else 0
        )

        self._update_report_btn()

        geo = self._settings.get("window_geometry")
        if geo and _GEOMETRY_RE.match(geo):
            try:
                self.geometry(geo)
            except Exception:
                pass

    def _save_settings(self) -> None:
        if not self._loading:
            settings_manager.save(self._settings)

    def _on_close(self) -> None:
        if self._watching:
            self._watch_stop_event.set()
        self._settings["window_geometry"] = self.geometry()
        settings_manager.save(self._settings)
        self.destroy()

    # ==================================================================
    # Single-file: file selection
    # ==================================================================

    def _select_file(self) -> None:
        initial = self._settings.get("last_input_folder") or str(Path.home())
        ext_pattern = " ".join(f"*{e}" for e in sorted(SUPPORTED_EXTENSIONS))
        path = filedialog.askopenfilename(
            title="Select Audio File",
            initialdir=initial,
            filetypes=[("Audio files", ext_pattern), ("All files", "*.*")],
        )
        if path:
            if Path(path).suffix.lower() not in SUPPORTED_EXTENSIONS:
                self._set_status("Unsupported file type. Please select a supported audio file.", "warning")
                return
            self._wav_path = path
            self._file_label.configure(text=Path(path).name)
            self._master_btn.configure(state="normal")
            self._master_split_btn.configure(state="normal")
            self._set_status("File selected. Click Analyse to inspect it.", "normal")
            self._settings["last_input_file"] = path
            self._settings["last_input_folder"] = str(Path(path).parent)
            self._save_settings()
            self._trigger_preview(path)

    def _reset(self) -> None:
        self._wav_path = None
        self._last_output_path = None
        self._last_handoff_note_path = None
        self._file_label.configure(text="No file selected")
        self._master_btn.configure(state="disabled")
        self._play_btn.configure(state="disabled")
        self._copy_path_btn.configure(state="disabled")
        self._open_handoff_btn.configure(state="disabled")
        self._open_clips_btn.configure(state="disabled")
        self._last_clips_dir = None
        self._progress.set(0)
        for lbl in self._analysis_labels.values():
            lbl.configure(text="—")
        self._set_status("Ready", "normal")

    # ==================================================================
    # Output folder (shared by both tabs)
    # ==================================================================

    def _select_output_folder(self) -> None:
        folder = filedialog.askdirectory(
            title="Select output folder", initialdir=str(self._output_dir)
        )
        if folder:
            self._output_dir = Path(folder)
            self._output_folder_label.configure(text=folder)
            self._batch_output_label.configure(text=folder)
            self._watch_output_label.configure(text=folder)
            self._settings["last_output_folder"] = folder
            self._save_settings()

    def _open_output_folder(self) -> None:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(str(self._output_dir))

    # ==================================================================
    # Single-file: preset / format callbacks
    # ==================================================================

    def _on_preset_change(self, name: str) -> None:
        preset = self._preset_map.get(name, {})
        warning = preset.get("warning")
        if warning:
            short = warning[:100] + "…" if len(warning) > 100 else warning
            self._set_status(f"Note: {short}", "warning")
        elif self._status_lbl.cget("text").startswith("Note:"):
            self._set_status("Ready", "normal")
        self._settings["last_selected_preset"] = name
        self._save_settings()

    def _on_format_change(self, name: str) -> None:
        self._settings["last_selected_export_format"] = name
        self._save_settings()

    # ==================================================================
    # Options checkboxes
    # ==================================================================

    def _on_auto_report_change(self) -> None:
        self._settings["auto_generate_report"] = bool(self._auto_report_var.get())
        self._save_settings()

    def _on_handoff_note_change(self) -> None:
        self._settings["resolve_handoff_note_enabled"] = bool(self._handoff_note_var.get())
        self._save_settings()

    # ==================================================================
    # Single-file: analysis
    # ==================================================================

    def _run_analyse(self) -> None:
        if not self._wav_path:
            self._set_status("No file selected.", "warning")
            return
        self._set_status("Analysing...", "normal")
        self._progress.configure(mode="indeterminate")
        self._progress.start()
        threading.Thread(target=self._analyse_worker, daemon=True).start()

    def _analyse_worker(self) -> None:
        result = analyse(self._wav_path)
        self.after(0, self._on_analyse_done, result)

    def _on_analyse_done(self, result: AnalysisResult) -> None:
        self._progress.stop()
        self._progress.configure(mode="determinate")
        self._progress.set(0)
        if result.error:
            self._set_status(f"Analysis failed: {result.error}", "error")
            return
        mins, secs = divmod(result.duration_seconds, 60)
        self._analysis_labels["Sample rate"].configure(text=f"{result.sample_rate:,} Hz")
        self._analysis_labels["Bit depth"].configure(text=result.bit_depth)
        ch_name = {1: "Mono", 2: "Stereo"}.get(result.channels, str(result.channels))
        self._analysis_labels["Channels"].configure(text=ch_name)
        self._analysis_labels["Duration"].configure(text=f"{int(mins)}:{secs:05.2f}")
        self._analysis_labels["Peak dBFS"].configure(text=f"{result.peak_dbfs:.1f} dB")
        self._analysis_labels["RMS dBFS"].configure(text=f"{result.rms_dbfs:.1f} dB")
        lufs = result.integrated_lufs
        lufs_text = f"{lufs:.1f} LUFS" if math.isfinite(lufs) else "< −70 LUFS (very quiet)"
        self._analysis_labels["Integrated LUFS"].configure(text=lufs_text)
        self._set_status("Analysis complete.", "success")

    # ==================================================================
    # Single-file: mastering
    # ==================================================================

    def _run_master(self) -> None:
        if not self._wav_path:
            self._set_status("No file selected.", "warning")
            return
        preset = self._preset_map[self._preset_var.get()]
        export_fmt = self._format_map[self._format_var.get()]
        self._set_status("Mastering — Pass 1 (measuring)…", "normal")
        self._progress.configure(mode="determinate")
        self._progress.set(0.05)
        self._master_btn.configure(state="disabled")
        threading.Thread(
            target=self._master_worker, args=(preset, export_fmt), daemon=True
        ).start()

    def _master_worker(self, preset: dict, export_fmt: ExportFormat) -> None:
        self.after(0, lambda: self._progress.set(0.35))
        result = master(self._wav_path, preset, export_fmt, self._output_dir)
        self.after(0, lambda: self._progress.set(0.85))
        mastered_lufs: float | None = None
        if result.output_path and not result.error:
            ma = analyse(result.output_path)
            if not ma.error:
                mastered_lufs = ma.integrated_lufs
        self.after(0, lambda: self._progress.set(0.95))
        report_path: str | None = None
        if not result.error and self._settings.get("auto_generate_report"):
            report_path = self._make_single_report(result, preset, export_fmt)
        handoff_note_path: str | None = None
        if not result.error and self._settings.get("resolve_handoff_note_enabled"):
            handoff_note_path = self._write_handoff_note_for_file(
                result, preset, export_fmt
            )
        self.after(
            0,
            lambda r=result, m=mastered_lufs, rp=report_path, hn=handoff_note_path:
                self._on_master_done(r, m, rp, hn),
        )

    def _make_single_report(
        self, result, preset: dict, export_fmt: ExportFormat,
        source_path: str | None = None,
    ) -> str | None:
        src = source_path if source_path is not None else self._wav_path
        try:
            after_stats = (
                loudness_report.measure_file(result.output_path)
                if result.output_path else None
            )
            row = loudness_report.build_row(
                source_file=str(src) if src else "",
                output_file=result.output_path or "",
                preset_name=preset["name"],
                export_format_name=export_fmt.name,
                before_stats=result.pass1_stats,
                after_stats=after_stats,
                status="ok",
            )
            rp = loudness_report.write_report([row])
            return str(rp)
        except Exception as exc:
            logger.error("Single-file report generation failed: %s", exc)
            return None

    def _on_master_done(
        self,
        result,
        mastered_lufs: float | None,
        report_path: str | None = None,
        handoff_note_path: str | None = None,
    ) -> None:
        self._progress.set(1.0)
        self._master_btn.configure(state="normal")
        if result.error:
            self._set_status(f"Mastering error: {result.error}", "error")
            return
        self._last_output_path = result.output_path
        output_name = Path(result.output_path).name
        if report_path:
            self._settings["latest_report_path"] = report_path
            self._save_settings()
            self._update_report_btn()
            rp_name = Path(report_path).name
            self._set_status(f"Done! → {output_name}  |  Report: {rp_name}", "success")
        else:
            self._set_status(f"Done!  →  {output_name}", "success")
        self._play_btn.configure(state="normal")
        self._copy_path_btn.configure(state="normal")
        if handoff_note_path:
            self._last_handoff_note_path = handoff_note_path
            self._open_handoff_btn.configure(state="normal")
        self._trigger_preview(result.output_path)
        if mastered_lufs is not None and result.pass1_lufs is not None:
            before = f"{result.pass1_lufs:.1f}"
            after = f"{mastered_lufs:.1f}" if math.isfinite(mastered_lufs) else "< −70"
            self._analysis_labels["Integrated LUFS"].configure(
                text=f"{before}  →  {after} LUFS"
            )

    def _play_output(self) -> None:
        if self._last_output_path and Path(self._last_output_path).exists():
            os.startfile(self._last_output_path)
        else:
            self._set_status("Mastered file not found.", "warning")

    # ==================================================================
    # Clip Splitter
    # ==================================================================

    def _run_master_and_split(self) -> None:
        if not self._wav_path:
            self._set_status("No file selected.", "warning")
            return
        raw = self._clip_duration_var.get().strip()
        try:
            duration = float(raw)
            if duration <= 0:
                raise ValueError
        except ValueError:
            self._set_status("Clip duration must be a positive number.", "warning")
            return
        preset = self._preset_map[self._preset_var.get()]
        export_fmt = self._format_map[self._format_var.get()]
        self._set_status("Mastering…", "normal")
        self._progress.configure(mode="determinate")
        self._progress.set(0.05)
        self._master_split_btn.configure(state="disabled")
        self._open_clips_btn.configure(state="disabled")
        threading.Thread(
            target=self._master_split_worker,
            args=(preset, export_fmt, duration),
            daemon=True,
        ).start()

    def _master_split_worker(
        self, preset: dict, export_fmt: ExportFormat, clip_duration: float
    ) -> None:
        wav_path = self._wav_path        # snapshot before blocking calls
        output_dir = self._output_dir    # snapshot before blocking calls
        self.after(0, lambda: self._progress.set(0.35))
        master_result = master(wav_path, preset, export_fmt, output_dir)
        self.after(0, lambda: self._progress.set(0.70))
        self.after(0, lambda: self._set_status("Splitting…", "normal"))
        if master_result.error:
            self.after(0, lambda r=master_result: self._on_master_split_done(r, None))
            return
        source_stem = Path(wav_path).stem
        clips_dir = output_dir / f"{source_stem}_clips"
        split_result = split_audio(master_result.output_path, clip_duration, clips_dir)
        self.after(0, lambda: self._progress.set(0.95))
        self.after(
            0,
            lambda m=master_result, s=split_result: self._on_master_split_done(m, s),
        )

    def _on_master_split_done(
        self,
        master_result,
        split_result: SplitAudioResult | None,
    ) -> None:
        self._master_split_btn.configure(state="normal")
        if master_result.error:
            self._progress.set(0)
            self._set_status(f"Mastering error: {master_result.error}", "error")
            return
        if split_result is None or split_result.error:
            self._progress.set(0)
            err = split_result.error if split_result else "Unknown split error"
            self._set_status(f"Split error: {err}", "error")
            return
        self._progress.set(1.0)
        self._last_clips_dir = split_result.output_dir
        self._open_clips_btn.configure(state="normal")
        folder_name = split_result.output_dir.name
        self._set_status(
            f"Done! {split_result.clip_count} clips → {folder_name}/",
            "success",
        )

    def _open_clips_folder(self) -> None:
        if self._last_clips_dir and self._last_clips_dir.exists():
            os.startfile(str(self._last_clips_dir))
        else:
            self._set_status("Clips folder not found.", "warning")

    # ==================================================================
    # Batch processing
    # ==================================================================

    def _select_batch_folder(self) -> None:
        initial = self._settings.get("last_input_folder") or str(Path.home())
        folder = filedialog.askdirectory(title="Select input folder", initialdir=initial)
        if folder:
            self._batch_input_folder = Path(folder)
            self._batch_folder_label.configure(text=folder)
            self._settings["last_input_folder"] = folder
            self._save_settings()

    def _start_batch(self) -> None:
        if not self._batch_input_folder:
            self._set_status("Please select an input folder first.", "warning")
            return
        preset = self._preset_map[self._batch_preset_var.get()]
        export_fmt = self._format_map[self._batch_format_var.get()]

        self._batch_log.configure(state="normal")
        self._batch_log.delete("0.0", "end")
        self._batch_log.configure(state="disabled")
        self._batch_cancel_requested = False
        self._batch_results = []
        self._batch_start_btn.configure(state="disabled")
        self._batch_cancel_btn.configure(state="normal")
        self._batch_current_label.configure(text="Starting…")
        self._progress.set(0)
        self._set_status("Batch processing started…", "normal")

        threading.Thread(
            target=self._batch_worker, args=(preset, export_fmt), daemon=True
        ).start()

    def _cancel_batch(self) -> None:
        self._batch_cancel_requested = True
        self._batch_cancel_btn.configure(state="disabled")
        self._set_status("Cancelling after current file…", "warning")

    def _batch_worker(self, preset: dict, export_fmt: ExportFormat) -> None:
        def progress_cb(current: int, total: int, filename: str) -> None:
            frac = current / total if total > 0 else 0.0
            self.after(
                0,
                lambda c=current, t=total, f=frac, n=filename:
                    self._on_batch_progress(f, n, c, t),
            )

        def file_done_cb(result: BatchFileResult) -> None:
            self.after(0, lambda r=result: self._on_batch_file_done(r))

        summary = process_batch(
            self._batch_input_folder,
            preset,
            export_fmt,
            self._output_dir,
            progress_callback=progress_cb,
            file_done_callback=file_done_cb,
            cancel_check=lambda: self._batch_cancel_requested,
        )
        self.after(0, lambda s=summary: self._on_batch_complete(s))

    def _on_batch_progress(
        self, fraction: float, filename: str, current: int, total: int
    ) -> None:
        self._progress.set(fraction)
        if filename:
            self._batch_current_label.configure(
                text=f"Processing {current + 1}/{total}: {filename}"
            )
            self._set_status(f"Batch: {current + 1}/{total} — {filename}", "normal")

    def _on_batch_file_done(self, result: BatchFileResult) -> None:
        self._batch_results.append(result)
        self._batch_log.configure(state="normal")
        if result.success:
            line = f"  OK  {result.input_path.name}\n"
        else:
            short_err = (result.error or "unknown error")[:80]
            line = f" ERR  {result.input_path.name}  —  {short_err}\n"
        self._batch_log.insert("end", line)
        self._batch_log.see("end")
        self._batch_log.configure(state="disabled")

    def _on_batch_complete(self, summary: BatchSummary) -> None:
        self._batch_start_btn.configure(state="normal")
        self._batch_cancel_btn.configure(state="disabled")
        self._batch_current_label.configure(text="")

        self._batch_log.configure(state="normal")
        sep = "-" * 50 + "\n"
        self._batch_log.insert("end", sep)
        if summary.cancelled:
            self._batch_log.insert("end", "Batch cancelled.\n")
        status_line = (
            f"Found: {summary.total_found}  |  "
            f"OK: {summary.processed}  |  "
            f"Failed: {summary.failed}\n"
        )
        self._batch_log.insert("end", status_line)
        self._batch_log.see("end")
        self._batch_log.configure(state="disabled")

        if summary.total_found == 0:
            self._set_status("Batch complete — no supported files found.", "warning")
            self._progress.set(0)
        elif summary.cancelled:
            self._set_status(
                f"Batch cancelled — {summary.processed}/{summary.total_found} completed.",
                "warning",
            )
        elif summary.failed > 0:
            self._set_status(
                f"Batch complete — {summary.processed} OK, {summary.failed} failed.",
                "warning",
            )
        else:
            self._set_status(
                f"Batch complete — {summary.processed} file(s) mastered.",
                "success",
            )
            self._progress.set(1.0)

        # Preview last successfully mastered file
        successful = [r for r in self._batch_results if r.success and r.output_path]
        if successful:
            self._trigger_preview(successful[-1].output_path)

        if self._settings.get("auto_generate_report") and self._batch_results:
            preset = self._preset_map[self._batch_preset_var.get()]
            export_fmt = self._format_map[self._batch_format_var.get()]
            self._batch_log.configure(state="normal")
            self._batch_log.insert("end", "Generating report…\n")
            self._batch_log.see("end")
            self._batch_log.configure(state="disabled")
            threading.Thread(
                target=self._batch_report_worker,
                args=(list(self._batch_results), preset, export_fmt),
                daemon=True,
            ).start()

    # ==================================================================
    # Loudness reports
    # ==================================================================

    def _batch_report_worker(
        self, results: list, preset: dict, export_fmt: ExportFormat
    ) -> None:
        try:
            rows = []
            for r in results:
                before_stats = (
                    r.master_result.pass1_stats if r.master_result else None
                )
                after_stats = (
                    loudness_report.measure_file(r.output_path) if r.output_path else None
                )
                row = loudness_report.build_row(
                    source_file=str(r.input_path),
                    output_file=r.output_path or "",
                    preset_name=preset["name"],
                    export_format_name=export_fmt.name,
                    before_stats=before_stats,
                    after_stats=after_stats,
                    status="ok" if r.success else "failed",
                    error_message=r.error,
                )
                rows.append(row)
            rp = loudness_report.write_report(rows)
            self.after(0, lambda p=str(rp): self._on_batch_report_done(p))
        except Exception as exc:
            logger.error("Batch report generation failed: %s", exc)

    def _on_batch_report_done(self, report_path: str) -> None:
        self._settings["latest_report_path"] = report_path
        self._save_settings()
        self._update_report_btn()
        rp_name = Path(report_path).name
        self._batch_log.configure(state="normal")
        self._batch_log.insert("end", f"Report: {rp_name}\n")
        self._batch_log.see("end")
        self._batch_log.configure(state="disabled")
        self._set_status(f"Report saved: {rp_name}", "success")

    def _open_latest_report(self) -> None:
        path = self._settings.get("latest_report_path")
        if path and Path(path).exists():
            os.startfile(str(path))
        else:
            self._set_status("No report available yet.", "warning")

    def _update_report_btn(self) -> None:
        path = self._settings.get("latest_report_path")
        has_report = bool(path and Path(path).exists())
        state = "normal" if has_report else "disabled"
        if hasattr(self, "_report_btn_single"):
            self._report_btn_single.configure(state=state)
        if hasattr(self, "_report_btn_batch"):
            self._report_btn_batch.configure(state=state)

    # ==================================================================
    # Watch folder
    # ==================================================================

    def _select_watch_folder(self) -> None:
        initial = self._settings.get("last_watch_folder") or str(Path.home())
        folder = filedialog.askdirectory(
            title="Select watch folder", initialdir=initial
        )
        if folder:
            self._watch_folder = Path(folder)
            self._watch_folder_label.configure(text=folder)
            self._settings["last_watch_folder"] = folder
            self._save_settings()

    def _on_move_processed_change(self) -> None:
        self._settings["move_processed_originals_enabled"] = bool(
            self._move_processed_var.get()
        )
        self._save_settings()

    def _on_move_failed_change(self) -> None:
        self._settings["move_failed_originals_enabled"] = bool(
            self._move_failed_var.get()
        )
        self._save_settings()

    def _start_watch(self) -> None:
        if not self._watch_folder:
            self._set_status("Please select a watch folder first.", "warning")
            return
        preset = self._preset_map[self._watch_preset_var.get()]
        export_fmt = self._format_map[self._watch_format_var.get()]

        self._watch_stop_event.clear()
        self._watching = True
        self._watch_start_btn.configure(state="disabled")
        self._watch_stop_btn.configure(state="normal")
        self._watch_status_lbl.configure(
            text=f"Watching {self._watch_folder.name}…"
        )
        self._set_status(
            f"Watch mode active — {self._watch_folder.name}", "success"
        )

        self._watch_log.configure(state="normal")
        self._watch_log.delete("0.0", "end")
        self._watch_log.configure(state="disabled")

        watcher = FolderWatcher(
            self._watch_folder,
            poll_interval=float(
                self._settings.get("watch_poll_interval_seconds", 5)
            ),
            stability_checks=2,
        )
        threading.Thread(
            target=self._watch_worker, args=(watcher, preset, export_fmt),
            daemon=True,
        ).start()

    def _stop_watch(self) -> None:
        self._watch_stop_event.set()
        self._watch_stop_btn.configure(state="disabled")
        self._set_status("Stopping watch…", "warning")

    def _watch_worker(
        self, watcher: FolderWatcher, preset: dict, export_fmt: ExportFormat
    ) -> None:
        while not self._watch_stop_event.is_set():
            ready = watcher.scan()
            for path in ready:
                if self._watch_stop_event.is_set():
                    break
                self.after(0, lambda n=path.name: self._on_watch_file_start(n))
                result = master(str(path), preset, export_fmt, self._output_dir)
                if result.error:
                    if self._settings.get("move_failed_originals_enabled", True):
                        watcher.mark_failed(path)
                    self.after(
                        0,
                        lambda n=path.name, e=result.error:
                            self._on_watch_file_fail(n, e),
                    )
                else:
                    if self._settings.get("move_processed_originals_enabled", True):
                        watcher.mark_processed(path)
                    report_path = None
                    if self._settings.get("auto_generate_report"):
                        report_path = self._make_single_report(
                            result, preset, export_fmt,
                            source_path=str(path),
                        )
                        if report_path:
                            self.after(
                                0,
                                lambda p=report_path: self._on_watch_report_done(p),
                            )
                    if self._settings.get("resolve_handoff_note_enabled"):
                        self._write_handoff_note_for_file(result, preset, export_fmt)
                    if result.output_path:
                        self.after(
                            0,
                            lambda p=result.output_path: self._trigger_preview(p),
                        )
                    self.after(0, lambda n=path.name: self._on_watch_file_done(n))
            self._watch_stop_event.wait(timeout=watcher.poll_interval)
        self.after(0, self._on_watch_stopped)

    def _on_watch_file_start(self, filename: str) -> None:
        self._watch_status_lbl.configure(text=f"Processing: {filename}")
        self._watch_log_append(f"▶  {filename}")

    def _on_watch_file_done(self, filename: str) -> None:
        self._watch_status_lbl.configure(text=f"Last processed: {filename}")
        self._watch_log_append(f"   ✓ done")

    def _on_watch_file_fail(self, filename: str, error: str) -> None:
        self._watch_status_lbl.configure(text=f"Last failed: {filename}")
        short_err = error[:80]
        self._watch_log_append(f"   ✗ {short_err}")

    def _on_watch_report_done(self, report_path: str) -> None:
        self._settings["latest_report_path"] = report_path
        self._save_settings()
        self._update_report_btn()

    def _on_watch_stopped(self) -> None:
        self._watching = False
        self._watch_start_btn.configure(state="normal")
        self._watch_stop_btn.configure(state="disabled")
        self._watch_status_lbl.configure(text="Not watching")
        self._set_status("Watch mode stopped.", "normal")
        self._watch_log_append("— Watch stopped —")

    def _watch_log_append(self, line: str) -> None:
        self._watch_log.configure(state="normal")
        self._watch_log.insert("end", line + "\n")
        self._watch_log.see("end")
        self._watch_log.configure(state="disabled")

    # ==================================================================
    # Audio preview (waveform + spectrum)
    # ==================================================================

    def _trigger_preview(self, path: str) -> None:
        self._preview_path = path
        self._preview_file_lbl.configure(text=f"Previewing: {Path(path).name}")
        threading.Thread(
            target=self._preview_worker, args=(path,), daemon=True
        ).start()

    def _preview_worker(self, path: str) -> None:
        waveform = audio_preview.safe_compute_waveform(path)
        spectrum = audio_preview.safe_compute_spectrum(path)
        self.after(
            0,
            lambda w=waveform, s=spectrum: self._update_preview_plots(w, s),
        )

    def _update_preview_plots(self, waveform: tuple, spectrum: tuple) -> None:
        times, samples = waveform
        freqs, mags = spectrum

        self._waveform_ax.clear()
        if times is not None and samples is not None:
            self._waveform_ax.plot(times, samples, color=_PLT_WAVE, linewidth=0.5)
            self._waveform_ax.set_xlim(times[0], times[-1])
            self._waveform_ax.set_xlabel("Time (s)", color=_PLT_FG, fontsize=7)
            self._waveform_ax.set_ylabel("Amp", color=_PLT_FG, fontsize=7)
            self._waveform_ax.tick_params(axis="both", colors=_PLT_FG, labelsize=7)
            for spine in self._waveform_ax.spines.values():
                spine.set_edgecolor(_PLT_FG)
        else:
            self._draw_preview_placeholder(
                self._waveform_ax, None, "Waveform", "Preview unavailable"
            )
        self._waveform_ax.set_facecolor(_PLT_BG)
        self._waveform_ax.set_title("Waveform", color=_PLT_FG, fontsize=9, pad=3)
        self._waveform_canvas.draw()

        self._spectrum_ax.clear()
        if freqs is not None and mags is not None:
            self._spectrum_ax.plot(freqs, mags, color=_PLT_SPEC, linewidth=0.7)
            self._spectrum_ax.set_xlabel("Hz", color=_PLT_FG, fontsize=7)
            self._spectrum_ax.set_ylabel("dB", color=_PLT_FG, fontsize=7)
            self._spectrum_ax.tick_params(axis="both", colors=_PLT_FG, labelsize=7)
            for spine in self._spectrum_ax.spines.values():
                spine.set_edgecolor(_PLT_FG)
        else:
            self._draw_preview_placeholder(
                self._spectrum_ax, None, "Frequency Spectrum", "Preview unavailable"
            )
        self._spectrum_ax.set_facecolor(_PLT_BG)
        self._spectrum_ax.set_title("Frequency Spectrum", color=_PLT_FG, fontsize=9, pad=3)
        self._spectrum_canvas.draw()

    def _draw_preview_placeholder(self, ax, canvas, title: str, msg: str) -> None:
        ax.clear()
        ax.set_facecolor(_PLT_BG)
        ax.set_title(title, color=_PLT_FG, fontsize=9, pad=3)
        ax.text(
            0.5, 0.5, msg,
            ha="center", va="center", color="gray",
            fontsize=9, transform=ax.transAxes,
        )
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)
        if canvas is not None:
            canvas.draw()

    def _refresh_preview_btn(self) -> None:
        if self._preview_path:
            self._trigger_preview(self._preview_path)
        else:
            self._set_status("No file to preview.", "warning")

    # ==================================================================
    # Resolve Free Handoff
    # ==================================================================

    def _write_handoff_note_for_file(
        self, result, preset: dict, export_fmt: ExportFormat
    ) -> str | None:
        if not result.output_path:
            return None
        try:
            content = resolve_handoff.generate_note_content(
                result.output_path, preset["name"], export_fmt.name
            )
            note_path = resolve_handoff.write_note(result.output_path, content)
            return str(note_path)
        except Exception as exc:
            logger.error("Handoff note generation failed: %s", exc)
            return None

    def _copy_path_to_clipboard(self) -> None:
        if not self._last_output_path:
            self._set_status("No mastered file available.", "warning")
            return
        self.clipboard_clear()
        self.clipboard_append(self._last_output_path)
        self._set_status("File path copied to clipboard.", "success")

    def _open_handoff_note(self) -> None:
        if self._last_handoff_note_path and Path(self._last_handoff_note_path).exists():
            os.startfile(self._last_handoff_note_path)
        else:
            self._set_status("No handoff note available.", "warning")

    # ==================================================================
    # Status helper
    # ==================================================================

    def _set_status(self, msg: str, level: str = "normal") -> None:
        colours = _STATUS_COLOURS.get(level, _STATUS_COLOURS["normal"])
        colour = colours[0] if ctk.get_appearance_mode() == "Dark" else colours[1]
        self._status_lbl.configure(text=msg, text_color=colour)


if __name__ == "__main__":
    _LOG_DIR = Path(__file__).parent / "logs"
    _LOG_DIR.mkdir(exist_ok=True)
    _handler = logging.handlers.RotatingFileHandler(
        _LOG_DIR / "audiomasterapp.log", maxBytes=5 * 1024 * 1024, backupCount=3,
        encoding="utf-8",
    )
    logging.basicConfig(
        handlers=[_handler],
        level=logging.DEBUG,
        format="%(asctime)s %(name)-20s %(levelname)-8s %(message)s",
    )
    app = App()
    app.mainloop()
