from __future__ import annotations
import logging
import logging.handlers
import math
import os
import threading
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from audio_analysis import analyse, AnalysisResult
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


class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("AudioMasterApp")
        self.geometry("520x660")
        self.resizable(False, False)

        self._wav_path: str | None = None
        self._last_output_path: str | None = None
        self._resolve_connected: bool = False
        self._presets = list_presets()
        self._preset_map = {p["name"]: p for p in self._presets}

        self._build_ui()
        threading.Thread(target=self._resolve_check_worker, daemon=True).start()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        pad = {"padx": 16, "pady": 6}

        # File selector
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

        # Preset dropdown
        preset_frame = ctk.CTkFrame(self)
        preset_frame.pack(fill="x", **pad)
        ctk.CTkLabel(preset_frame, text="Preset:", width=60).pack(side="left", padx=8, pady=8)
        self._preset_var = ctk.StringVar(value=self._presets[0]["name"])
        ctk.CTkOptionMenu(
            preset_frame,
            variable=self._preset_var,
            values=[p["name"] for p in self._presets],
            width=300,
        ).pack(side="left", padx=8, pady=8)

        # Analysis panel
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

        # Action buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=16, pady=4)
        ctk.CTkButton(
            btn_frame, text="Analyse", command=self._run_analyse, width=220
        ).pack(side="left", padx=(0, 8))
        self._master_btn = ctk.CTkButton(
            btn_frame, text="Master File", command=self._run_master, width=220, state="disabled"
        )
        self._master_btn.pack(side="left")

        # Play button
        play_frame = ctk.CTkFrame(self, fg_color="transparent")
        play_frame.pack(fill="x", padx=16, pady=(0, 4))
        self._play_btn = ctk.CTkButton(
            play_frame, text="▶  Play Mastered File",
            command=self._play_output, state="disabled",
        )
        self._play_btn.pack(fill="x")

        # Resolve bridge panel (always visible, status reflects connection)
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

        # Progress bar
        self._progress = ctk.CTkProgressBar(self)
        self._progress.pack(fill="x", padx=16, pady=4)
        self._progress.set(0)

        # Status bar
        self._status_lbl = ctk.CTkLabel(self, text="Ready", anchor="w")
        self._status_lbl.pack(fill="x", padx=16, pady=(4, 12))

    # ------------------------------------------------------------------
    # File selection
    # ------------------------------------------------------------------

    def _select_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Select WAV file",
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

    def _reset(self) -> None:
        self._wav_path = None
        self._last_output_path = None
        self._file_label.configure(text="No file selected")
        self._master_btn.configure(state="disabled")
        self._play_btn.configure(state="disabled")
        self._progress.set(0)
        for lbl in self._analysis_labels.values():
            lbl.configure(text="—")
        self._analysis_labels["Integrated LUFS"].configure(text="—")
        self._set_status("Ready", "normal")

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
        self._set_status(f"Mastering — Pass 1 (measuring)…", "normal")
        self._progress.configure(mode="determinate")
        self._progress.set(0.05)
        self._master_btn.configure(state="disabled")
        threading.Thread(target=self._master_worker, args=(preset,), daemon=True).start()

    def _master_worker(self, preset: dict) -> None:
        self.after(0, lambda: self._progress.set(0.35))
        result = master(self._wav_path, preset)
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
        self._set_status(f"Done!  →  output/{output_name}", "success")
        self._play_btn.configure(state="normal")
        if mastered_lufs is not None and result.pass1_lufs is not None:
            before = f"{result.pass1_lufs:.1f}"
            after = f"{mastered_lufs:.1f}" if math.isfinite(mastered_lufs) else "< −70"
            self._analysis_labels["Integrated LUFS"].configure(
                text=f"{before}  →  {after} LUFS"
            )
        if self._resolve_connected:
            self._resolve_btn.configure(state="normal")

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
        if connected:
            self._resolve_dot.configure(text_color="#4CAF50")
            self._resolve_status_lbl.configure(text=f"Resolve: {msg}")
        else:
            self._resolve_dot.configure(text_color="#F44336")
            self._resolve_status_lbl.configure(text=f"Resolve: {msg}")

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
        self._resolve_btn.configure(state="normal")
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
