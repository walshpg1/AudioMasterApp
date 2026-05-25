from __future__ import annotations
import logging
import logging.handlers
import math
import os
import re
import threading
from pathlib import Path
from tkinter import filedialog, IntVar

import customtkinter as ctk

import settings_manager
from audio_analysis import analyse, AnalysisResult
from export_formats import list_export_formats, ExportFormat
from mastering_engine import master, list_presets
from resolve_bridge import connect as resolve_connect, import_to_media_pool, BridgeResult

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

_DEFAULT_OUTPUT_DIR = Path(__file__).parent / "output"


class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("AudioMasterApp")
        self.geometry("520x860")
        self.resizable(False, False)

        self._loading = True
        self._wav_path: str | None = None
        self._last_output_path: str | None = None
        self._resolve_connected: bool = False
        self._output_dir: Path = _DEFAULT_OUTPUT_DIR
        self._settings: dict = settings_manager._defaults()

        self._presets = list_presets()
        self._preset_map = {p["name"]: p for p in self._presets}
        self._export_formats = list_export_formats()
        self._format_map = {f.name: f for f in self._export_formats}

        # Checkbox variables must exist before _build_ui references them
        self._auto_report_var = IntVar(value=0)
        self._resolve_auto_var = IntVar(value=0)

        self._build_ui()
        self._load_settings()
        self._loading = False

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        threading.Thread(target=self._resolve_check_worker, daemon=True).start()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        pad = {"padx": 16, "pady": 5}

        # --- File selector ---
        file_frame = ctk.CTkFrame(self)
        file_frame.pack(fill="x", **pad)
        ctk.CTkButton(
            file_frame, text="Select WAV File...", command=self._select_file, width=160
        ).pack(side="left", padx=8, pady=8)
        self._file_label = ctk.CTkLabel(file_frame, text="No file selected", anchor="w")
        self._file_label.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(
            file_frame, text="Reset", command=self._reset, width=70
        ).pack(side="right", padx=(0, 8), pady=8)

        # --- Preset dropdown ---
        preset_frame = ctk.CTkFrame(self)
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

        # --- Export format dropdown ---
        format_frame = ctk.CTkFrame(self)
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

        # --- Output folder selector ---
        output_frame = ctk.CTkFrame(self)
        output_frame.pack(fill="x", **pad)
        ctk.CTkButton(
            output_frame, text="Output Folder...", command=self._select_output_folder, width=130
        ).pack(side="left", padx=8, pady=8)
        self._output_folder_label = ctk.CTkLabel(
            output_frame,
            text=str(_DEFAULT_OUTPUT_DIR),
            anchor="w",
            font=ctk.CTkFont(size=11),
        )
        self._output_folder_label.pack(side="left", fill="x", expand=True, padx=(0, 4))
        ctk.CTkButton(
            output_frame, text="Open", command=self._open_output_folder, width=55
        ).pack(side="right", padx=(0, 8), pady=8)

        # --- Analysis panel ---
        analysis_frame = ctk.CTkFrame(self)
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

        # --- Options panel ---
        options_frame = ctk.CTkFrame(self)
        options_frame.pack(fill="x", **pad)
        ctk.CTkCheckBox(
            options_frame,
            text="Auto-generate loudness report after mastering",
            variable=self._auto_report_var,
            command=self._on_auto_report_change,
        ).pack(anchor="w", padx=12, pady=(8, 4))
        ctk.CTkCheckBox(
            options_frame,
            text="Send to Resolve automatically after mastering",
            variable=self._resolve_auto_var,
            command=self._on_resolve_auto_change,
        ).pack(anchor="w", padx=12, pady=(0, 8))

        # --- Action buttons ---
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=16, pady=4)
        ctk.CTkButton(
            btn_frame, text="Analyse", command=self._run_analyse, width=220
        ).pack(side="left", padx=(0, 8))
        self._master_btn = ctk.CTkButton(
            btn_frame, text="Master File", command=self._run_master, width=220, state="disabled"
        )
        self._master_btn.pack(side="left")

        # --- Play button ---
        play_frame = ctk.CTkFrame(self, fg_color="transparent")
        play_frame.pack(fill="x", padx=16, pady=(0, 4))
        self._play_btn = ctk.CTkButton(
            play_frame, text="▶  Play Mastered File",
            command=self._play_output, state="disabled",
        )
        self._play_btn.pack(fill="x")

        # --- Resolve bridge panel ---
        resolve_frame = ctk.CTkFrame(self)
        resolve_frame.pack(fill="x", **pad)
        ctk.CTkLabel(
            resolve_frame, text="DaVinci Resolve", font=ctk.CTkFont(weight="bold")
        ).pack(anchor="w", padx=12, pady=(8, 4))
        resolve_row = ctk.CTkFrame(resolve_frame, fg_color="transparent")
        resolve_row.pack(fill="x", padx=12, pady=(0, 4))
        self._resolve_dot = ctk.CTkLabel(resolve_row, text="●", text_color="gray", width=20)
        self._resolve_dot.pack(side="left")
        self._resolve_status_lbl = ctk.CTkLabel(resolve_row, text="Checking...", anchor="w")
        self._resolve_status_lbl.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            resolve_row, text="Refresh", command=self._refresh_resolve, width=80
        ).pack(side="right", padx=(0, 4))
        self._resolve_btn = ctk.CTkButton(
            resolve_frame,
            text="Send to Resolve Media Pool",
            command=self._send_to_resolve,
            state="disabled",
        )
        self._resolve_btn.pack(padx=12, pady=(0, 8))

        # --- Progress bar ---
        self._progress = ctk.CTkProgressBar(self)
        self._progress.pack(fill="x", padx=16, pady=4)
        self._progress.set(0)

        # --- Status bar ---
        self._status_lbl = ctk.CTkLabel(self, text="Ready", anchor="w")
        self._status_lbl.pack(fill="x", padx=16, pady=(4, 10))

    # ------------------------------------------------------------------
    # Settings persistence
    # ------------------------------------------------------------------

    def _load_settings(self) -> None:
        preset_names = [p["name"] for p in self._presets]
        self._settings = settings_manager.load(preset_names)

        # Restore preset selection
        stored_preset = self._settings.get("last_selected_preset")
        if stored_preset and stored_preset in self._preset_map:
            self._preset_var.set(stored_preset)

        # Restore export format selection
        stored_format = self._settings.get("last_selected_export_format")
        if stored_format and stored_format in self._format_map:
            self._format_var.set(stored_format)

        # Restore output folder
        stored_output = self._settings.get("last_output_folder")
        if stored_output:
            p = Path(stored_output)
            if p.is_dir():
                self._output_dir = p
                self._output_folder_label.configure(text=str(p))

        # Restore checkboxes
        self._auto_report_var.set(1 if self._settings.get("auto_generate_report") else 0)
        self._resolve_auto_var.set(1 if self._settings.get("resolve_import_enabled") else 0)

        # Restore window position (size is fixed; only apply position part)
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
        self._settings["window_geometry"] = self.geometry()
        settings_manager.save(self._settings)
        self.destroy()

    # ------------------------------------------------------------------
    # File selection
    # ------------------------------------------------------------------

    def _select_file(self) -> None:
        initial_dir = self._settings.get("last_input_folder") or str(Path.home())
        path = filedialog.askopenfilename(
            title="Select WAV file",
            initialdir=initial_dir,
            filetypes=[("WAV files", "*.wav"), ("All files", "*.*")],
        )
        if path:
            if not path.lower().endswith(".wav"):
                self._set_status("Please select a .wav file.", "warning")
                return
            self._wav_path = path
            self._file_label.configure(text=Path(path).name)
            self._master_btn.configure(state="normal")
            self._set_status("File selected. Click Analyse to inspect it.", "normal")
            self._settings["last_input_file"] = path
            self._settings["last_input_folder"] = str(Path(path).parent)
            self._save_settings()

    def _reset(self) -> None:
        self._wav_path = None
        self._last_output_path = None
        self._file_label.configure(text="No file selected")
        self._master_btn.configure(state="disabled")
        self._play_btn.configure(state="disabled")
        self._resolve_btn.configure(state="disabled")
        self._progress.set(0)
        for lbl in self._analysis_labels.values():
            lbl.configure(text="—")
        self._set_status("Ready", "normal")

    # ------------------------------------------------------------------
    # Output folder
    # ------------------------------------------------------------------

    def _select_output_folder(self) -> None:
        initial = str(self._output_dir)
        folder = filedialog.askdirectory(title="Select output folder", initialdir=initial)
        if folder:
            self._output_dir = Path(folder)
            self._output_folder_label.configure(text=folder)
            self._settings["last_output_folder"] = folder
            self._save_settings()

    def _open_output_folder(self) -> None:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(str(self._output_dir))

    # ------------------------------------------------------------------
    # Preset / format change
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Options checkboxes
    # ------------------------------------------------------------------

    def _on_auto_report_change(self) -> None:
        self._settings["auto_generate_report"] = bool(self._auto_report_var.get())
        self._save_settings()

    def _on_resolve_auto_change(self) -> None:
        self._settings["resolve_import_enabled"] = bool(self._resolve_auto_var.get())
        self._save_settings()

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Mastering
    # ------------------------------------------------------------------

    def _run_master(self) -> None:
        if not self._wav_path:
            self._set_status("No file selected.", "warning")
            return
        preset_name = self._preset_var.get()
        preset = self._preset_map[preset_name]
        format_name = self._format_var.get()
        export_fmt = self._format_map[format_name]
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
            mastered_analysis = analyse(result.output_path)
            if not mastered_analysis.error:
                mastered_lufs = mastered_analysis.integrated_lufs
        self.after(0, lambda: self._progress.set(0.95))
        self.after(0, self._on_master_done, result, mastered_lufs)

    def _on_master_done(self, result, mastered_lufs: float | None) -> None:
        self._progress.set(1.0)
        self._master_btn.configure(state="normal")
        if result.error:
            self._set_status(f"Mastering error: {result.error}", "error")
            return
        self._last_output_path = result.output_path
        output_name = Path(result.output_path).name
        self._set_status(f"Done!  →  {output_name}", "success")
        self._play_btn.configure(state="normal")
        if self._resolve_connected:
            self._resolve_btn.configure(state="normal")
        if mastered_lufs is not None and result.pass1_lufs is not None:
            before = f"{result.pass1_lufs:.1f}"
            after = f"{mastered_lufs:.1f}" if math.isfinite(mastered_lufs) else "< −70"
            self._analysis_labels["Integrated LUFS"].configure(
                text=f"{before}  →  {after} LUFS"
            )
        # Auto-send to Resolve if enabled
        if self._settings.get("resolve_import_enabled") and self._resolve_connected:
            threading.Thread(target=self._resolve_import_worker, daemon=True).start()

    def _play_output(self) -> None:
        if self._last_output_path and Path(self._last_output_path).exists():
            os.startfile(self._last_output_path)
        else:
            self._set_status("Mastered file not found.", "warning")

    # ------------------------------------------------------------------
    # Resolve bridge
    # ------------------------------------------------------------------

    def _resolve_check_worker(self) -> None:
        resolve, msg = resolve_connect()
        self.after(0, self._on_resolve_check, resolve is not None, msg)

    def _on_resolve_check(self, connected: bool, msg: str) -> None:
        self._resolve_connected = connected
        dot_colour = "#4CAF50" if connected else "#F44336"
        self._resolve_dot.configure(text_color=dot_colour)
        self._resolve_status_lbl.configure(text=f"Resolve: {msg}")
        # Enable Send button only when connected and a mastered file exists
        if connected and self._last_output_path:
            self._resolve_btn.configure(state="normal")
        else:
            self._resolve_btn.configure(state="disabled")

    def _refresh_resolve(self) -> None:
        self._resolve_dot.configure(text_color="gray")
        self._resolve_status_lbl.configure(text="Checking...")
        self._resolve_connected = False
        self._resolve_btn.configure(state="disabled")
        threading.Thread(target=self._resolve_check_worker, daemon=True).start()

    def _send_to_resolve(self) -> None:
        if not self._last_output_path:
            self._set_status("Master a file first.", "warning")
            return
        self._set_status("Sending to Resolve media pool…", "normal")
        self._resolve_btn.configure(state="disabled")
        threading.Thread(target=self._resolve_import_worker, daemon=True).start()

    def _resolve_import_worker(self) -> None:
        result = import_to_media_pool(self._last_output_path)
        self.after(0, self._on_resolve_import_done, result)

    def _on_resolve_import_done(self, result: BridgeResult) -> None:
        self._resolve_btn.configure(state="normal" if self._resolve_connected else "disabled")
        level = "success" if result.clip_imported else "error"
        self._set_status(f"Resolve: {result.message}", level)

    # ------------------------------------------------------------------
    # Status helper
    # ------------------------------------------------------------------

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
