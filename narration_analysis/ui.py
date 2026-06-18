from __future__ import annotations
import logging
import os
import re
import threading
from pathlib import Path
from tkinter import filedialog
from typing import Optional

import customtkinter as ctk

from narration_analysis.exporter import _OUTPUT_ROOT, export_all
from narration_analysis.models import AnalysisResult, Scene
from narration_analysis.player import AudioPlayer
from narration_analysis.scene_builder import build_scenes
from narration_analysis.transcriber import TranscriptionCancelled, transcribe

logger = logging.getLogger(__name__)

_MODELS = ["tiny", "base", "small", "medium", "large"]
_AUDIO_EXTS = [("Audio files", "*.mp3 *.wav *.m4a"), ("All files", "*.*")]
_PROJECT_RE = re.compile(r"[\s\-]+")


def _make_project_name(stem: str) -> str:
    return _PROJECT_RE.sub("_", stem)


class NarrationAnalysisTab:
    def __init__(self, parent: ctk.CTkFrame, root: ctk.CTk) -> None:
        self._parent = parent
        self._root = root
        self._player = AudioPlayer()
        self._audio_path: Optional[Path] = None
        self._result: Optional[AnalysisResult] = None
        self._cancel_event = threading.Event()
        self._is_playing = False
        self._model_var = ctk.StringVar(value="small")
        self._poll_id: str | None = None
        self._build_ui()
        self._poll_playback()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        pad = {"padx": 12, "pady": 4}

        ctk.CTkLabel(
            self._parent,
            text="Narration Analysis",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=12, pady=(12, 4))

        # Section 1 — Input
        input_row = ctk.CTkFrame(self._parent)
        input_row.pack(fill="x", **pad)
        ctk.CTkButton(
            input_row, text="Browse Audio", command=self._browse, width=120
        ).pack(side="left", padx=8, pady=8)
        self._file_lbl = ctk.CTkLabel(
            input_row, text="No file selected", anchor="w", font=ctk.CTkFont(size=11)
        )
        self._file_lbl.pack(side="left", fill="x", expand=True, padx=(4, 8), pady=8)

        # Section 2 — Controls
        ctrl_row = ctk.CTkFrame(self._parent)
        ctrl_row.pack(fill="x", **pad)
        ctk.CTkLabel(ctrl_row, text="Model:", width=50).pack(side="left", padx=(8, 2), pady=8)
        ctk.CTkOptionMenu(
            ctrl_row, values=_MODELS, variable=self._model_var, width=100
        ).pack(side="left", padx=2, pady=8)

        try:
            import torch
            gpu = torch.cuda.is_available()
        except ImportError:
            gpu = False
        ctk.CTkLabel(
            ctrl_row,
            text="GPU: Available" if gpu else "GPU: CPU only",
            text_color="#4CAF50" if gpu else "gray50",
            font=ctk.CTkFont(size=11),
        ).pack(side="left", padx=8, pady=8)

        self._cancel_btn = ctk.CTkButton(
            ctrl_row, text="Cancel", command=self._cancel_analysis,
            width=80, fg_color="#C62828", state="disabled",
        )
        self._cancel_btn.pack(side="right", padx=4, pady=8)
        self._analyse_btn = ctk.CTkButton(
            ctrl_row, text="Analyse", command=self._start_analysis, width=100, state="disabled"
        )
        self._analyse_btn.pack(side="right", padx=8, pady=8)

        self._progress = ctk.CTkProgressBar(self._parent)
        self._progress.pack(fill="x", **pad)
        self._progress.set(0)
        self._status_lbl = ctk.CTkLabel(
            self._parent, text="Ready", anchor="w", font=ctk.CTkFont(size=11)
        )
        self._status_lbl.pack(anchor="w", padx=12, pady=(0, 4))

        # Section 3 — Preview (two columns)
        preview_frame = ctk.CTkFrame(self._parent)
        preview_frame.pack(fill="both", expand=True, **pad)
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.columnconfigure(1, weight=1)
        preview_frame.rowconfigure(0, weight=1)

        left = ctk.CTkFrame(preview_frame)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 4), pady=4)
        ctk.CTkLabel(left, text="Transcript", font=ctk.CTkFont(weight="bold")).pack(
            anchor="w", padx=8, pady=4
        )
        self._transcript_box = ctk.CTkTextbox(left, state="disabled", wrap="word")
        self._transcript_box.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        right = ctk.CTkFrame(preview_frame)
        right.grid(row=0, column=1, sticky="nsew", padx=(4, 0), pady=4)
        ctk.CTkLabel(right, text="Scenes", font=ctk.CTkFont(weight="bold")).pack(
            anchor="w", padx=8, pady=4
        )
        self._scenes_frame = ctk.CTkScrollableFrame(right)
        self._scenes_frame.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        # Section 4 — Playback
        pb_row = ctk.CTkFrame(self._parent)
        pb_row.pack(fill="x", **pad)
        self._play_btn = ctk.CTkButton(
            pb_row, text="▶ Play", command=self._toggle_play, width=90, state="disabled"
        )
        self._play_btn.pack(side="left", padx=8, pady=8)
        self._stop_btn = ctk.CTkButton(
            pb_row, text="⏹ Stop", command=self._stop_playback, width=80, state="disabled"
        )
        self._stop_btn.pack(side="left", padx=4, pady=8)
        self._pos_lbl = ctk.CTkLabel(pb_row, text="00:00", font=ctk.CTkFont(size=11))
        self._pos_lbl.pack(side="left", padx=8)

        # Section 5 — Export status
        ctk.CTkLabel(
            self._parent, text="Exported Files", font=ctk.CTkFont(weight="bold")
        ).pack(anchor="w", padx=12, pady=(8, 2))
        self._export_box = ctk.CTkTextbox(self._parent, height=90, state="disabled", wrap="none")
        self._export_box.pack(fill="x", **pad)
        btn_row = ctk.CTkFrame(self._parent, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=(0, 8))
        self._open_folder_btn = ctk.CTkButton(
            btn_row, text="Open Output Folder", command=self._open_folder,
            state="disabled", width=160,
        )
        self._open_folder_btn.pack(side="left")

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _browse(self) -> None:
        path_str = filedialog.askopenfilename(filetypes=_AUDIO_EXTS)
        if not path_str:
            return
        self._audio_path = Path(path_str)
        self._file_lbl.configure(text=self._audio_path.name)
        self._player.load(self._audio_path)
        self._analyse_btn.configure(state="normal")
        self._play_btn.configure(state="normal")
        self._stop_btn.configure(state="normal")
        self._status_lbl.configure(text=f"Loaded: {self._audio_path.name}")

    def _start_analysis(self) -> None:
        self._cancel_event.clear()
        self._analyse_btn.configure(state="disabled")
        self._cancel_btn.configure(state="normal")
        self._progress.set(0)
        self._status_lbl.configure(text="Starting transcription...")
        threading.Thread(target=self._analysis_worker, daemon=True).start()

    def _cancel_analysis(self) -> None:
        self._cancel_event.set()

    def _toggle_play(self) -> None:
        if self._is_playing:
            self._player.pause()
            self._is_playing = False
            self._play_btn.configure(text="▶ Play")
        else:
            if self._player.is_playing():
                self._player.unpause()
            else:
                self._player.play()
            self._is_playing = True
            self._play_btn.configure(text="⏸ Pause")

    def _stop_playback(self) -> None:
        self._player.stop()
        self._is_playing = False
        self._play_btn.configure(text="▶ Play")
        self._pos_lbl.configure(text="00:00")

    def _seek_to(self, seconds: float) -> None:
        self._player.seek(seconds)
        self._is_playing = True
        self._play_btn.configure(text="⏸ Pause")

    def _open_folder(self) -> None:
        if self._result:
            os.startfile(str(self._result.output_dir))

    # ------------------------------------------------------------------
    # Background worker
    # ------------------------------------------------------------------

    def _analysis_worker(self) -> None:
        try:
            path = self._audio_path
            project_name = _make_project_name(path.stem)
            output_dir = _OUTPUT_ROOT / project_name

            segments, duration = transcribe(
                path,
                self._model_var.get(),
                lambda f: self._root.after(0, self._update_progress, f),
                self._cancel_event,
            )
            scenes = build_scenes(segments)
            result = AnalysisResult(
                source_path=path,
                project_name=project_name,
                duration=duration,
                segments=segments,
                scenes=scenes,
                output_dir=output_dir,
            )
            exported = export_all(result)
            self._result = result
            self._root.after(0, self._on_complete, result, exported)

        except TranscriptionCancelled:
            self._root.after(0, self._on_cancelled)
        except Exception as exc:
            logger.exception("Analysis worker failed")
            self._root.after(0, self._on_error, str(exc))

    def _update_progress(self, frac: float) -> None:
        self._progress.set(frac)
        self._status_lbl.configure(text=f"Transcribing… {int(frac * 100)}%")

    # ------------------------------------------------------------------
    # Completion callbacks (main thread)
    # ------------------------------------------------------------------

    def _on_complete(self, result: AnalysisResult, exported: dict) -> None:
        self._progress.set(1.0)
        self._status_lbl.configure(text=f"Done — {len(result.scenes)} scenes extracted")
        self._analyse_btn.configure(state="normal")
        self._cancel_btn.configure(state="disabled")
        self._populate_transcript(result)
        self._populate_scenes(result)
        self._populate_exports(exported)
        self._open_folder_btn.configure(state="normal")

    def _on_cancelled(self) -> None:
        self._status_lbl.configure(text="Cancelled.")
        self._analyse_btn.configure(state="normal")
        self._cancel_btn.configure(state="disabled")
        self._progress.set(0)

    def _on_error(self, err: str) -> None:
        self._status_lbl.configure(text=f"Error: {err}")
        self._analyse_btn.configure(state="normal")
        self._cancel_btn.configure(state="disabled")
        self._progress.set(0)

    # ------------------------------------------------------------------
    # Preview population
    # ------------------------------------------------------------------

    def _populate_transcript(self, result: AnalysisResult) -> None:
        self._transcript_box.configure(state="normal")
        self._transcript_box.delete("1.0", "end")
        for seg in result.segments:
            m, s = int(seg.start // 60), int(seg.start % 60)
            self._transcript_box.insert("end", f"[{m:02d}:{s:02d}] {seg.text}\n")
        self._transcript_box.configure(state="disabled")

    def _populate_scenes(self, result: AnalysisResult) -> None:
        for widget in self._scenes_frame.winfo_children():
            widget.destroy()
        for scene in result.scenes:
            self._add_scene_row(scene)

    def _add_scene_row(self, scene: Scene) -> None:
        sm, ss = int(scene.start // 60), int(scene.start % 60)
        em, es = int(scene.end // 60), int(scene.end % 60)
        tc = f"{sm:02d}:{ss:02d}–{em:02d}:{es:02d}"
        preview = scene.text[:38] + ("…" if len(scene.text) > 38 else "")
        label = f"▶  Scene {scene.scene_number}  {tc}  \"{preview}\""
        row = ctk.CTkFrame(self._scenes_frame)
        row.pack(fill="x", pady=2)
        ctk.CTkButton(
            row,
            text=label,
            anchor="w",
            command=lambda t=scene.start: self._seek_to(t),
            fg_color="transparent",
            hover_color=("gray85", "gray30"),
            text_color=("gray10", "gray90"),
            font=ctk.CTkFont(size=11),
        ).pack(fill="x", padx=4, pady=2)

    def _populate_exports(self, exported: dict) -> None:
        self._export_box.configure(state="normal")
        self._export_box.delete("1.0", "end")
        for key, path in exported.items():
            self._export_box.insert("end", f"{key}: {path}\n")
        self._export_box.configure(state="disabled")

    # ------------------------------------------------------------------
    # Playback position polling (every 500 ms)
    # ------------------------------------------------------------------

    def _poll_playback(self) -> None:
        if self._is_playing:
            pos = self._player.get_pos_seconds()
            m, s = int(pos // 60), int(pos % 60)
            self._pos_lbl.configure(text=f"{m:02d}:{s:02d}")
            if not self._player.is_playing():
                self._is_playing = False
                self._play_btn.configure(text="▶ Play")
        self._poll_id = self._root.after(500, self._poll_playback)

    def cleanup(self) -> None:
        if self._poll_id is not None:
            self._root.after_cancel(self._poll_id)
            self._poll_id = None
        self._player.cleanup()
