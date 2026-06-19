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
from narration_analysis.scene_builder import build_scenes, build_scenes_narrative
from narration_analysis.transcriber import TranscriptionCancelled, transcribe

logger = logging.getLogger(__name__)

_MODELS = ["tiny", "base", "small", "medium", "large"]
_AUDIO_EXTS = [("Audio files", "*.mp3 *.wav *.m4a"), ("All files", "*.*")]
_PROJECT_RE = re.compile(r"[\s\-]+")

_ROW_SELECTED  = ("gray75", "gray25")  # selected scene row highlight
_ROW_NORMAL    = "transparent"         # unselected scene row


def _make_project_name(stem: str) -> str:
    return _PROJECT_RE.sub("_", stem)


def _fmt_tc(seconds: float) -> str:
    m, s = int(seconds // 60), int(seconds % 60)
    return f"{m:02d}:{s:02d}"


class NarrationAnalysisTab:
    def __init__(self, parent: ctk.CTkFrame, root: ctk.CTk) -> None:
        self._parent = parent
        self._root = root
        self._player = AudioPlayer()
        self._audio_path: Optional[Path] = None
        self._result: Optional[AnalysisResult] = None
        self._cancel_event = threading.Event()

        # Playback state (Change 4: separate is_paused flag)
        self._is_playing = False
        self._is_paused  = False

        # Scene selection (Change 3: highlight tracking)
        self._selected_scene_btn: Optional[ctk.CTkButton] = None
        self._selected_scene: Optional[Scene] = None

        self._model_var      = ctk.StringVar(value="small")
        self._scene_mode_var = ctk.StringVar(value="narrative")
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

        # Scene mode toggle
        mode_row = ctk.CTkFrame(self._parent)
        mode_row.pack(fill="x", padx=12, pady=(0, 4))
        ctk.CTkLabel(mode_row, text="Scene Mode:", width=90).pack(side="left", padx=(8, 2), pady=6)
        ctk.CTkRadioButton(
            mode_row, text="Narrative", variable=self._scene_mode_var, value="narrative"
        ).pack(side="left", padx=(4, 12))
        ctk.CTkRadioButton(
            mode_row, text="Subtitle", variable=self._scene_mode_var, value="subtitle"
        ).pack(side="left", padx=4)

        self._progress = ctk.CTkProgressBar(self._parent)
        self._progress.pack(fill="x", **pad)
        self._progress.set(0)
        self._status_lbl = ctk.CTkLabel(
            self._parent, text="Ready", anchor="w", font=ctk.CTkFont(size=11)
        )
        self._status_lbl.pack(anchor="w", padx=12, pady=(0, 4))

        # Section 3 — Three-column preview: Transcript | Scenes | Storyboard
        preview_frame = ctk.CTkFrame(self._parent)
        preview_frame.pack(fill="both", expand=True, **pad)
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.columnconfigure(1, weight=1)
        preview_frame.columnconfigure(2, weight=1)
        preview_frame.rowconfigure(0, weight=1)

        # Column A — Transcript
        left = ctk.CTkFrame(preview_frame)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 3), pady=4)
        ctk.CTkLabel(left, text="Transcript", font=ctk.CTkFont(weight="bold")).pack(
            anchor="w", padx=8, pady=4
        )
        self._transcript_box = ctk.CTkTextbox(left, state="disabled", wrap="word")
        self._transcript_box.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        # Column B — Scenes
        mid = ctk.CTkFrame(preview_frame)
        mid.grid(row=0, column=1, sticky="nsew", padx=3, pady=4)
        ctk.CTkLabel(mid, text="Scenes", font=ctk.CTkFont(weight="bold")).pack(
            anchor="w", padx=8, pady=4
        )
        self._scenes_frame = ctk.CTkScrollableFrame(mid)
        self._scenes_frame.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        # Column C — Storyboard (Change 2)
        self._build_storyboard_panel(preview_frame)

        # Section 4 — Playback (Change 5: compact, secondary prominence)
        pb_row = ctk.CTkFrame(self._parent)
        pb_row.pack(fill="x", padx=12, pady=(4, 2))
        self._play_btn = ctk.CTkButton(
            pb_row, text="▶ Play", command=self._toggle_play,
            width=80, height=28, state="disabled",
            font=ctk.CTkFont(size=12),
        )
        self._play_btn.pack(side="left", padx=(0, 4), pady=6)
        self._stop_btn = ctk.CTkButton(
            pb_row, text="⏹ Stop", command=self._stop_playback,
            width=70, height=28, state="disabled",
            font=ctk.CTkFont(size=12),
        )
        self._stop_btn.pack(side="left", padx=4, pady=6)
        self._pos_lbl = ctk.CTkLabel(
            pb_row, text="00:00",
            font=ctk.CTkFont(size=11), text_color="gray60",
        )
        self._pos_lbl.pack(side="left", padx=8)

        # Section 5 — Open Output Folder (Change 1: Exported Files textbox removed)
        btn_row = ctk.CTkFrame(self._parent, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=(2, 8))
        self._open_folder_btn = ctk.CTkButton(
            btn_row, text="Open Output Folder", command=self._open_folder,
            state="disabled", width=160, height=28,
        )
        self._open_folder_btn.pack(side="left")

    def _build_storyboard_panel(self, parent: ctk.CTkFrame) -> None:
        """Storyboard preview column — Change 2.

        Designed to accommodate editable visual_prompt, Generate Prompt button,
        and status variants (Ready / Generated) in a future iteration.
        """
        outer = ctk.CTkFrame(parent)
        outer.grid(row=0, column=2, sticky="nsew", padx=(3, 0), pady=4)

        ctk.CTkLabel(
            outer, text="Storyboard", font=ctk.CTkFont(weight="bold")
        ).pack(anchor="w", padx=8, pady=(4, 2))

        # Scene number — placeholder until a scene is selected
        self._sb_scene_lbl = ctk.CTkLabel(
            outer,
            text="Select a scene →",
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w",
            text_color="gray50",
        )
        self._sb_scene_lbl.pack(anchor="w", padx=8, pady=(6, 0))

        # Start / End / Duration
        self._sb_time_lbl = ctk.CTkLabel(
            outer, text="",
            font=ctk.CTkFont(size=11), text_color="gray60", anchor="w",
        )
        self._sb_time_lbl.pack(anchor="w", padx=8, pady=(2, 4))

        ctk.CTkFrame(outer, height=1, fg_color=("gray70", "gray30")).pack(
            fill="x", padx=8, pady=(2, 6)
        )

        # Narration
        ctk.CTkLabel(
            outer, text="Narration",
            font=ctk.CTkFont(size=11, weight="bold"), anchor="w",
        ).pack(anchor="w", padx=8, pady=(0, 2))
        self._sb_narration_box = ctk.CTkTextbox(
            outer, height=90, state="disabled", wrap="word",
            font=ctk.CTkFont(size=11),
        )
        self._sb_narration_box.pack(fill="x", padx=8, pady=(0, 6))

        ctk.CTkFrame(outer, height=1, fg_color=("gray70", "gray30")).pack(
            fill="x", padx=8, pady=(0, 6)
        )

        # Visual Prompt — read-only in v1; space reserved for edit widget + Generate button
        ctk.CTkLabel(
            outer, text="Visual Prompt",
            font=ctk.CTkFont(size=11, weight="bold"), anchor="w",
        ).pack(anchor="w", padx=8, pady=(0, 2))
        self._sb_prompt_box = ctk.CTkTextbox(
            outer, height=70, state="disabled", wrap="word",
            font=ctk.CTkFont(size=11), text_color="gray60",
        )
        self._sb_prompt_box.pack(fill="x", padx=8, pady=(0, 6))

        ctk.CTkFrame(outer, height=1, fg_color=("gray70", "gray30")).pack(
            fill="x", padx=8, pady=(0, 6)
        )

        # Status — space reserved for badge / dropdown in future
        ctk.CTkLabel(
            outer, text="Status",
            font=ctk.CTkFont(size=11, weight="bold"), anchor="w",
        ).pack(anchor="w", padx=8, pady=(0, 2))
        self._sb_status_lbl = ctk.CTkLabel(
            outer, text="",
            font=ctk.CTkFont(size=11), text_color="gray60", anchor="w",
        )
        self._sb_status_lbl.pack(anchor="w", padx=8, pady=(0, 8))

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _browse(self) -> None:
        path_str = filedialog.askopenfilename(filetypes=_AUDIO_EXTS)
        if not path_str:
            return
        self._audio_path = Path(path_str)
        self._file_lbl.configure(text=self._audio_path.name)
        self._analyse_btn.configure(state="normal")

        if not self._player.is_available:
            self._status_lbl.configure(
                text="Playback unavailable: sounddevice is not installed"
            )
            return

        try:
            self._player.load(self._audio_path)
            self._play_btn.configure(state="normal")
            self._stop_btn.configure(state="normal")
            self._status_lbl.configure(text=f"Loaded: {self._audio_path.name}")
        except Exception as exc:
            logger.exception("Playback load failed: %s", path_str)
            self._play_btn.configure(state="disabled")
            self._stop_btn.configure(state="disabled")
            self._status_lbl.configure(
                text=f"Playback load failed: {type(exc).__name__}: {exc}"[:120]
            )

    def _start_analysis(self) -> None:
        self._cancel_event.clear()
        self._analyse_btn.configure(state="disabled")
        self._cancel_btn.configure(state="normal")
        self._progress.set(0)
        self._status_lbl.configure(text="Starting transcription...")
        mode = self._scene_mode_var.get()
        threading.Thread(target=self._analysis_worker, args=(mode,), daemon=True).start()

    def _cancel_analysis(self) -> None:
        self._cancel_event.set()

    def _toggle_play(self) -> None:
        if self._is_playing:
            try:
                self._player.pause()
            except Exception as exc:
                logger.warning("Pause failed: %s", exc)
            self._is_playing = False
            self._is_paused  = True
            self._play_btn.configure(text="▶ Play")
        else:
            if not self._player.is_loaded:
                self._status_lbl.configure(text="No audio loaded — browse a file first")
                return
            try:
                if self._is_paused:
                    self._player.unpause()
                else:
                    self._player.play()
                self._is_playing = True
                self._is_paused  = False
                self._play_btn.configure(text="⏸ Pause")
            except Exception as exc:
                self._is_playing = False
                self._is_paused  = False
                msg = f"{type(exc).__name__}: {exc}"
                self._status_lbl.configure(text=f"Playback failed: {msg}"[:120])
                logger.exception("Playback failed")

    def _stop_playback(self) -> None:
        try:
            self._player.stop()
        except Exception as exc:
            logger.warning("Stop failed: %s", exc)
        self._is_playing = False
        self._is_paused  = False
        self._play_btn.configure(text="▶ Play")
        self._pos_lbl.configure(text="00:00")

    def _select_scene(self, scene: Scene, btn: ctk.CTkButton) -> None:
        """Change 3: highlight row, seek audio cursor, update storyboard. No auto-play."""
        # Highlight management
        if self._selected_scene_btn is not None:
            self._selected_scene_btn.configure(fg_color=_ROW_NORMAL)
        self._selected_scene_btn = btn
        self._selected_scene     = scene
        btn.configure(fg_color=_ROW_SELECTED)

        # Seek without playing (Change 3 + uses new set_position)
        self._player.set_position(scene.start)
        self._is_playing = False
        self._is_paused  = False
        self._play_btn.configure(text="▶ Play")

        # Update position label immediately so the user sees the new cursor
        self._pos_lbl.configure(text=_fmt_tc(scene.start))

        # Update storyboard panel (Change 2)
        self._update_storyboard(scene)

    def _update_storyboard(self, scene: Scene) -> None:
        """Populate the storyboard panel from in-memory Scene object (Change 6)."""
        duration = round(scene.end - scene.start, 1)

        self._sb_scene_lbl.configure(
            text=f"Scene {scene.scene_number}",
            text_color=("gray10", "gray90"),
        )
        self._sb_time_lbl.configure(
            text=f"Start: {_fmt_tc(scene.start)}   End: {_fmt_tc(scene.end)}   Duration: {duration}s"
        )

        self._sb_narration_box.configure(state="normal")
        self._sb_narration_box.delete("1.0", "end")
        self._sb_narration_box.insert("1.0", scene.text)
        self._sb_narration_box.configure(state="disabled")

        # visual_prompt is empty in v1; slot reserved for future edit widget
        self._sb_prompt_box.configure(state="normal")
        self._sb_prompt_box.delete("1.0", "end")
        self._sb_prompt_box.insert("1.0", "(empty)")
        self._sb_prompt_box.configure(state="disabled")

        # status is Pending in v1; slot reserved for badge/dropdown
        self._sb_status_lbl.configure(text="Pending")

    def _clear_storyboard(self) -> None:
        """Reset storyboard to placeholder state (called when new analysis completes)."""
        self._sb_scene_lbl.configure(text="Select a scene →", text_color="gray50")
        self._sb_time_lbl.configure(text="")
        for box in (self._sb_narration_box, self._sb_prompt_box):
            box.configure(state="normal")
            box.delete("1.0", "end")
            box.configure(state="disabled")
        self._sb_status_lbl.configure(text="")

    def _open_folder(self) -> None:
        if self._result:
            os.startfile(str(self._result.output_dir))

    # ------------------------------------------------------------------
    # Background worker
    # ------------------------------------------------------------------

    def _analysis_worker(self, mode: str) -> None:
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
            scenes = (
                build_scenes_narrative(segments) if mode == "narrative"
                else build_scenes(segments)
            )
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

    def _on_complete(self, result: AnalysisResult, exported: dict) -> None:  # noqa: ARG002
        self._progress.set(1.0)
        self._status_lbl.configure(text=f"Done — {len(result.scenes)} scenes extracted")
        self._analyse_btn.configure(state="normal")
        self._cancel_btn.configure(state="disabled")
        self._populate_transcript(result)
        self._populate_scenes(result)
        self._clear_storyboard()
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
        self._selected_scene_btn = None
        self._selected_scene     = None
        for scene in result.scenes:
            self._add_scene_row(scene)

    def _add_scene_row(self, scene: Scene) -> None:
        sm, ss = int(scene.start // 60), int(scene.start % 60)
        em, es = int(scene.end // 60), int(scene.end % 60)
        tc      = f"{sm:02d}:{ss:02d}–{em:02d}:{es:02d}"
        preview = scene.text[:38] + ("…" if len(scene.text) > 38 else "")
        label   = f"Scene {scene.scene_number}  {tc}  \"{preview}\""
        row = ctk.CTkFrame(self._scenes_frame)
        row.pack(fill="x", pady=2)
        btn = ctk.CTkButton(
            row,
            text=label,
            anchor="w",
            fg_color=_ROW_NORMAL,
            hover_color=("gray85", "gray30"),
            text_color=("gray10", "gray90"),
            font=ctk.CTkFont(size=11),
        )
        btn.configure(command=lambda s=scene, b=btn: self._select_scene(s, b))
        btn.pack(fill="x", padx=4, pady=2)

    # ------------------------------------------------------------------
    # Playback position polling (every 500 ms)
    # ------------------------------------------------------------------

    def _poll_playback(self) -> None:
        if self._is_playing:
            pos = self._player.get_pos_seconds()
            self._pos_lbl.configure(text=_fmt_tc(pos))
            if not self._player.is_playing():
                # Audio ended naturally — clear both UI flags
                self._is_playing = False
                self._is_paused  = False
                self._play_btn.configure(text="▶ Play")
        self._poll_id = self._root.after(500, self._poll_playback)

    def cleanup(self) -> None:
        if self._poll_id is not None:
            self._root.after_cancel(self._poll_id)
            self._poll_id = None
        self._player.cleanup()
