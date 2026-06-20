from __future__ import annotations
import logging
import os
import re
import threading
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Optional

import customtkinter as ctk

from narration_analysis.exporter import (
    _OUTPUT_ROOT,
    corrected_files_exist,
    export_all,
    export_corrections,
    load_corrections,
)
from narration_analysis.models import AnalysisResult, Scene, SceneEdit
from narration_analysis.player import AudioPlayer
from narration_analysis.scene_builder import build_scenes, build_scenes_narrative
from narration_analysis.transcriber import TranscriptionCancelled, transcribe

logger = logging.getLogger(__name__)

_MODELS = ["tiny", "base", "small", "medium", "large"]
_AUDIO_EXTS = [("Audio files", "*.mp3 *.wav *.m4a"), ("All files", "*.*")]
_PROJECT_RE = re.compile(r"[\s\-]+")

_ROW_SELECTED = ("gray75", "gray25")
_ROW_NORMAL   = "transparent"


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

        # Playback state
        self._is_playing = False
        self._is_paused  = False

        # Scene selection
        self._selected_scene_btn: Optional[ctk.CTkButton] = None
        self._selected_scene: Optional[Scene] = None
        self._scene_btns: dict[int, ctk.CTkButton] = {}

        # Correction state
        self._edits: dict[int, SceneEdit] = {}
        self._corrected_transcript: str = ""
        self._is_dirty: bool = False
        self._transcript_mode: str = "Original"

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

        # Section 3 — Three-column preview
        preview_frame = ctk.CTkFrame(self._parent)
        preview_frame.pack(fill="both", expand=True, **pad)
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.columnconfigure(1, weight=1)
        preview_frame.columnconfigure(2, weight=1)
        preview_frame.rowconfigure(0, weight=1)

        # Column A — Transcript (with Original / Corrected toggle)
        left = ctk.CTkFrame(preview_frame)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 3), pady=4)

        transcript_header = ctk.CTkFrame(left, fg_color="transparent")
        transcript_header.pack(fill="x", padx=4, pady=(4, 2))
        ctk.CTkLabel(
            transcript_header, text="Transcript", font=ctk.CTkFont(weight="bold")
        ).pack(side="left", padx=4)
        self._transcript_toggle = ctk.CTkSegmentedButton(
            transcript_header,
            values=["Original", "Corrected"],
            command=self._on_transcript_mode_change,
            width=180,
            font=ctk.CTkFont(size=11),
        )
        self._transcript_toggle.set("Original")
        self._transcript_toggle.pack(side="right", padx=4)

        self._transcript_box = ctk.CTkTextbox(left, state="disabled", wrap="word")
        self._transcript_box.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        self._transcript_box.bind("<KeyRelease>", self._on_transcript_key)
        self._transcript_box.bind("<FocusOut>", lambda e: self._commit_corrected_transcript())

        # Column B — Scenes
        mid = ctk.CTkFrame(preview_frame)
        mid.grid(row=0, column=1, sticky="nsew", padx=3, pady=4)
        ctk.CTkLabel(mid, text="Scenes", font=ctk.CTkFont(weight="bold")).pack(
            anchor="w", padx=8, pady=4
        )
        self._scenes_frame = ctk.CTkScrollableFrame(mid)
        self._scenes_frame.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        # Column C — Storyboard
        self._build_storyboard_panel(preview_frame)

        # Section 4 — Playback
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

        # Section 5 — Action buttons
        btn_row = ctk.CTkFrame(self._parent, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=(2, 8))
        self._save_corrections_btn = ctk.CTkButton(
            btn_row, text="Save Corrections", command=self._save_corrections,
            state="disabled", width=150, height=28,
            fg_color=("#2E7D32", "#1B5E20"),
        )
        self._save_corrections_btn.pack(side="left", padx=(0, 4))
        self._revert_all_btn = ctk.CTkButton(
            btn_row, text="Revert All", command=self._revert_all,
            state="disabled", width=100, height=28,
            fg_color=("#C62828", "#7B1515"),
        )
        self._revert_all_btn.pack(side="left", padx=4)
        self._open_folder_btn = ctk.CTkButton(
            btn_row, text="Open Output Folder", command=self._open_folder,
            state="disabled", width=160, height=28,
        )
        self._open_folder_btn.pack(side="left", padx=4)
        self._dirty_lbl = ctk.CTkLabel(
            btn_row, text="",
            font=ctk.CTkFont(size=11), text_color="#FF8C00",
        )
        self._dirty_lbl.pack(side="left", padx=12)

    def _build_storyboard_panel(self, parent: ctk.CTkFrame) -> None:
        outer = ctk.CTkFrame(parent)
        outer.grid(row=0, column=2, sticky="nsew", padx=(3, 0), pady=4)

        ctk.CTkLabel(
            outer, text="Storyboard", font=ctk.CTkFont(weight="bold")
        ).pack(anchor="w", padx=8, pady=(4, 2))

        # Scene number row + edited badge
        scene_hdr = ctk.CTkFrame(outer, fg_color="transparent")
        scene_hdr.pack(fill="x", padx=8, pady=(6, 0))
        self._sb_scene_lbl = ctk.CTkLabel(
            scene_hdr,
            text="Select a scene →",
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w",
            text_color="gray50",
        )
        self._sb_scene_lbl.pack(side="left")
        self._sb_edited_lbl = ctk.CTkLabel(
            scene_hdr, text="",
            font=ctk.CTkFont(size=11), text_color="#FF8C00",
        )
        self._sb_edited_lbl.pack(side="right")

        # Timecode
        self._sb_time_lbl = ctk.CTkLabel(
            outer, text="",
            font=ctk.CTkFont(size=11), text_color="gray60", anchor="w",
        )
        self._sb_time_lbl.pack(anchor="w", padx=8, pady=(2, 4))

        ctk.CTkFrame(outer, height=1, fg_color=("gray70", "gray30")).pack(
            fill="x", padx=8, pady=(2, 6)
        )

        # Narration — editable when scene selected
        ctk.CTkLabel(
            outer, text="Narration",
            font=ctk.CTkFont(size=11, weight="bold"), anchor="w",
        ).pack(anchor="w", padx=8, pady=(0, 2))
        self._sb_narration_box = ctk.CTkTextbox(
            outer, height=90, state="disabled", wrap="word",
            font=ctk.CTkFont(size=11),
        )
        self._sb_narration_box.pack(fill="x", padx=8, pady=(0, 6))
        self._sb_narration_box.bind("<FocusOut>", lambda e: self._commit_storyboard())
        self._sb_narration_box.bind("<KeyRelease>", lambda e: self._mark_dirty())

        ctk.CTkFrame(outer, height=1, fg_color=("gray70", "gray30")).pack(
            fill="x", padx=8, pady=(0, 6)
        )

        # Visual Prompt — editable when scene selected
        ctk.CTkLabel(
            outer, text="Visual Prompt",
            font=ctk.CTkFont(size=11, weight="bold"), anchor="w",
        ).pack(anchor="w", padx=8, pady=(0, 2))
        self._sb_prompt_box = ctk.CTkTextbox(
            outer, height=70, state="disabled", wrap="word",
            font=ctk.CTkFont(size=11),
        )
        self._sb_prompt_box.pack(fill="x", padx=8, pady=(0, 6))
        self._sb_prompt_box.bind("<FocusOut>", lambda e: self._commit_storyboard())
        self._sb_prompt_box.bind("<KeyRelease>", lambda e: self._mark_dirty())

        ctk.CTkFrame(outer, height=1, fg_color=("gray70", "gray30")).pack(
            fill="x", padx=8, pady=(0, 6)
        )

        # Status (fixed in v4)
        ctk.CTkLabel(
            outer, text="Status",
            font=ctk.CTkFont(size=11, weight="bold"), anchor="w",
        ).pack(anchor="w", padx=8, pady=(0, 2))
        self._sb_status_lbl = ctk.CTkLabel(
            outer, text="",
            font=ctk.CTkFont(size=11), text_color="gray60", anchor="w",
        )
        self._sb_status_lbl.pack(anchor="w", padx=8, pady=(0, 6))

        # Revert Scene button
        self._sb_revert_btn = ctk.CTkButton(
            outer, text="Revert Scene", command=self._revert_scene,
            state="disabled", width=120, height=26,
            fg_color=("#C62828", "#7B1515"),
            font=ctk.CTkFont(size=11),
        )
        self._sb_revert_btn.pack(anchor="w", padx=8, pady=(0, 8))

    # ------------------------------------------------------------------
    # Event handlers — browse & analysis
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
        if self._is_dirty:
            if not messagebox.askyesno(
                "Unsaved Changes",
                "You have unsaved corrections.\n\n"
                "Running a new analysis will replace them. Continue?",
            ):
                return
        self._cancel_event.clear()
        self._analyse_btn.configure(state="disabled")
        self._cancel_btn.configure(state="normal")
        self._progress.set(0)
        self._status_lbl.configure(text="Starting transcription...")
        mode = self._scene_mode_var.get()
        threading.Thread(target=self._analysis_worker, args=(mode,), daemon=True).start()

    def _cancel_analysis(self) -> None:
        self._cancel_event.set()

    # ------------------------------------------------------------------
    # Event handlers — playback
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Event handlers — scene selection
    # ------------------------------------------------------------------

    def _select_scene(self, scene: Scene, btn: ctk.CTkButton) -> None:
        # Commit current storyboard edits before switching scene
        self._commit_storyboard()

        if self._selected_scene_btn is not None:
            self._selected_scene_btn.configure(fg_color=_ROW_NORMAL)
        self._selected_scene_btn = btn
        self._selected_scene     = scene
        btn.configure(fg_color=_ROW_SELECTED)

        self._player.set_position(scene.start)
        self._is_playing = False
        self._is_paused  = False
        self._play_btn.configure(text="▶ Play")
        self._pos_lbl.configure(text=_fmt_tc(scene.start))

        self._update_storyboard(scene)

    # ------------------------------------------------------------------
    # Event handlers — transcript toggle
    # ------------------------------------------------------------------

    def _on_transcript_mode_change(self, value: str) -> None:
        # Save content before leaving Corrected mode
        if self._transcript_mode == "Corrected":
            self._corrected_transcript = self._transcript_box.get("1.0", "end-1c")

        self._transcript_mode = value

        if value == "Original":
            self._populate_original_transcript()
        else:
            self._transcript_box.configure(state="normal")
            self._transcript_box.delete("1.0", "end")
            self._transcript_box.insert("1.0", self._corrected_transcript)
            # leave editable

    def _on_transcript_key(self, event=None) -> None:
        if self._transcript_mode == "Corrected":
            self._mark_dirty()

    def _commit_corrected_transcript(self) -> None:
        if self._transcript_mode == "Corrected":
            self._corrected_transcript = self._transcript_box.get("1.0", "end-1c")

    # ------------------------------------------------------------------
    # Event handlers — storyboard editing
    # ------------------------------------------------------------------

    def _commit_storyboard(self) -> None:
        """Read narration and visual_prompt boxes into _edits for the selected scene."""
        if self._selected_scene is None:
            return
        edit = self._edits.get(self._selected_scene.scene_number)
        if edit is None:
            return

        narration     = self._sb_narration_box.get("1.0", "end-1c")
        visual_prompt = self._sb_prompt_box.get("1.0", "end-1c")

        changed = (narration != edit.narration) or (visual_prompt != edit.visual_prompt)
        edit.narration     = narration
        edit.visual_prompt = visual_prompt
        edit.edited = (narration != edit.original_narration) or bool(visual_prompt)

        if changed:
            self._sb_edited_lbl.configure(text="[Edited]" if edit.edited else "")
            self._refresh_scene_btn_label(self._selected_scene.scene_number)

    # ------------------------------------------------------------------
    # Storyboard display
    # ------------------------------------------------------------------

    def _update_storyboard(self, scene: Scene) -> None:
        edit = self._edits.get(scene.scene_number)
        duration = round(scene.end - scene.start, 1)

        self._sb_scene_lbl.configure(
            text=f"Scene {scene.scene_number}",
            text_color=("gray10", "gray90"),
        )
        self._sb_edited_lbl.configure(
            text="[Edited]" if (edit and edit.edited) else ""
        )
        self._sb_time_lbl.configure(
            text=f"Start: {_fmt_tc(scene.start)}   End: {_fmt_tc(scene.end)}   Duration: {duration}s"
        )

        narration = edit.narration if edit else scene.text
        self._sb_narration_box.configure(state="normal")
        self._sb_narration_box.delete("1.0", "end")
        self._sb_narration_box.insert("1.0", narration)
        # leave editable

        visual_prompt = edit.visual_prompt if edit else ""
        self._sb_prompt_box.configure(state="normal")
        self._sb_prompt_box.delete("1.0", "end")
        if visual_prompt:
            self._sb_prompt_box.insert("1.0", visual_prompt)
        # leave editable

        self._sb_status_lbl.configure(
            text=(edit.status if edit else "pending").capitalize()
        )
        self._sb_revert_btn.configure(state="normal")

    def _clear_storyboard(self) -> None:
        self._sb_scene_lbl.configure(text="Select a scene →", text_color="gray50")
        self._sb_edited_lbl.configure(text="")
        self._sb_time_lbl.configure(text="")
        for box in (self._sb_narration_box, self._sb_prompt_box):
            box.configure(state="normal")
            box.delete("1.0", "end")
            box.configure(state="disabled")
        self._sb_status_lbl.configure(text="")
        self._sb_revert_btn.configure(state="disabled")

    # ------------------------------------------------------------------
    # Dirty state
    # ------------------------------------------------------------------

    def _mark_dirty(self) -> None:
        self._is_dirty = True
        self._save_corrections_btn.configure(state="normal")
        self._revert_all_btn.configure(state="normal")
        self._dirty_lbl.configure(text="● Unsaved changes")

    def _recheck_dirty(self) -> None:
        """Recompute dirty flag from current in-memory edit state."""
        has_scene_edits = any(e.edited for e in self._edits.values())
        orig_transcript = (
            "\n".join(seg.text for seg in self._result.segments)
            if self._result else ""
        )
        self._is_dirty = has_scene_edits or (self._corrected_transcript != orig_transcript)
        if self._is_dirty:
            self._save_corrections_btn.configure(state="normal")
            self._revert_all_btn.configure(state="normal")
        else:
            self._save_corrections_btn.configure(state="disabled")
            self._revert_all_btn.configure(state="disabled")
            self._dirty_lbl.configure(text="")

    # ------------------------------------------------------------------
    # Save / Revert
    # ------------------------------------------------------------------

    def _save_corrections(self) -> None:
        if not self._result:
            return
        self._commit_storyboard()
        self._commit_corrected_transcript()
        try:
            exported = export_corrections(
                self._result,
                self._edits,
                self._corrected_transcript,
            )
            self._is_dirty = False
            self._save_corrections_btn.configure(state="disabled")
            self._revert_all_btn.configure(state="disabled")
            self._dirty_lbl.configure(text="")
            n_edited = sum(1 for e in self._edits.values() if e.edited)
            self._status_lbl.configure(
                text=f"Corrections saved — {n_edited} scene(s) edited"
            )
            logger.info("Corrections saved: %s", {k: str(v) for k, v in exported.items()})
        except Exception as exc:
            logger.exception("Failed to save corrections")
            self._status_lbl.configure(text=f"Save failed: {exc}"[:120])

    def _revert_scene(self) -> None:
        if self._selected_scene is None:
            return
        edit = self._edits.get(self._selected_scene.scene_number)
        if edit is None:
            return
        edit.narration     = edit.original_narration
        edit.visual_prompt = ""
        edit.edited        = False
        self._update_storyboard(self._selected_scene)
        self._refresh_scene_btn_label(self._selected_scene.scene_number)
        self._recheck_dirty()

    def _revert_all(self) -> None:
        if not messagebox.askyesno(
            "Revert All",
            "Revert all scene corrections and transcript edits to the original "
            "Whisper output?\n\nThis cannot be undone.",
        ):
            return
        for edit in self._edits.values():
            edit.narration     = edit.original_narration
            edit.visual_prompt = ""
            edit.edited        = False

        if self._result:
            self._corrected_transcript = "\n".join(
                seg.text for seg in self._result.segments
            )

        if self._selected_scene is not None:
            self._update_storyboard(self._selected_scene)

        if self._result:
            for sc in self._result.scenes:
                self._refresh_scene_btn_label(sc.scene_number)

        # Reset transcript display to Original mode
        self._transcript_mode = "Original"
        self._transcript_toggle.set("Original")
        self._populate_original_transcript()

        self._is_dirty = False
        self._save_corrections_btn.configure(state="disabled")
        self._revert_all_btn.configure(state="disabled")
        self._dirty_lbl.configure(text="")
        self._status_lbl.configure(text="All corrections reverted")

    # ------------------------------------------------------------------
    # Misc handlers
    # ------------------------------------------------------------------

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

    def _try_load_corrections(self, result: AnalysisResult) -> str:
        """Offer to reload corrected state from disk if files exist.

        Returns a status suffix so _on_complete can compose the final message.
        Falls back silently to fresh Whisper state on any error.
        """
        if not corrected_files_exist(result):
            return ""
        if not messagebox.askyesno(
            "Load Saved Corrections",
            "Corrected edits were found for this project.\n\nLoad them?",
        ):
            return ""
        try:
            corrected_transcript, edits = load_corrections(result)
            self._corrected_transcript = corrected_transcript
            self._edits = edits
            n = sum(1 for e in edits.values() if e.edited)
            return f"  ·  {n} correction(s) loaded"
        except Exception as exc:
            logger.warning("Failed to load corrected state: %s", exc)
            self._status_lbl.configure(
                text=f"Warning: corrections found but could not be loaded — {exc}"[:120]
            )
            return ""

    def _on_complete(self, result: AnalysisResult, exported: dict) -> None:  # noqa: ARG002
        self._progress.set(1.0)
        self._analyse_btn.configure(state="normal")
        self._cancel_btn.configure(state="disabled")
        self._seed_edits(result)
        suffix = self._try_load_corrections(result)
        self._status_lbl.configure(
            text=f"Done — {len(result.scenes)} scenes extracted{suffix}"
        )
        self._populate_transcript(result)
        self._populate_scenes(result)
        self._clear_storyboard()
        self._open_folder_btn.configure(state="normal")
        self._save_corrections_btn.configure(state="disabled")
        self._revert_all_btn.configure(state="disabled")
        self._dirty_lbl.configure(text="")

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

    def _seed_edits(self, result: AnalysisResult) -> None:
        """Initialise the correction layer from fresh Whisper output."""
        self._edits = {
            sc.scene_number: SceneEdit(
                scene_number=sc.scene_number,
                original_narration=sc.text,
                narration=sc.text,
            )
            for sc in result.scenes
        }
        self._corrected_transcript = "\n".join(seg.text for seg in result.segments)
        self._is_dirty = False
        self._scene_btns = {}

    def _populate_transcript(self, result: AnalysisResult) -> None:
        self._transcript_mode = "Original"
        self._transcript_toggle.set("Original")
        self._populate_original_transcript()

    def _populate_original_transcript(self) -> None:
        self._transcript_box.configure(state="normal")
        self._transcript_box.delete("1.0", "end")
        if self._result:
            for seg in self._result.segments:
                m, s = int(seg.start // 60), int(seg.start % 60)
                self._transcript_box.insert("end", f"[{m:02d}:{s:02d}] {seg.text}\n")
        self._transcript_box.configure(state="disabled")

    def _populate_scenes(self, result: AnalysisResult) -> None:
        for widget in self._scenes_frame.winfo_children():
            widget.destroy()
        self._selected_scene_btn = None
        self._selected_scene     = None
        self._scene_btns         = {}
        for scene in result.scenes:
            self._add_scene_row(scene)

    def _add_scene_row(self, scene: Scene) -> None:
        edit = self._edits.get(scene.scene_number)
        sm, ss = int(scene.start // 60), int(scene.start % 60)
        em, es = int(scene.end // 60), int(scene.end % 60)
        tc      = f"{sm:02d}:{ss:02d}–{em:02d}:{es:02d}"
        label   = self._scene_btn_label(scene, edit)
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
        self._scene_btns[scene.scene_number] = btn

    @staticmethod
    def _scene_btn_label(scene: Scene, edit: Optional[SceneEdit]) -> str:
        sm, ss = int(scene.start // 60), int(scene.start % 60)
        em, es = int(scene.end // 60), int(scene.end % 60)
        tc      = f"{sm:02d}:{ss:02d}–{em:02d}:{es:02d}"
        display = edit.narration if edit else scene.text
        preview = display[:38] + ("…" if len(display) > 38 else "")
        mark    = " ✎" if (edit and edit.edited) else ""
        return f"Scene {scene.scene_number}{mark}  {tc}  \"{preview}\""

    def _refresh_scene_btn_label(self, scene_number: int) -> None:
        btn = self._scene_btns.get(scene_number)
        if btn is None or self._result is None:
            return
        scene = next((sc for sc in self._result.scenes if sc.scene_number == scene_number), None)
        if scene is None:
            return
        edit = self._edits.get(scene_number)
        btn.configure(text=self._scene_btn_label(scene, edit))

    # ------------------------------------------------------------------
    # Playback position polling (every 500 ms)
    # ------------------------------------------------------------------

    def _poll_playback(self) -> None:
        if self._is_playing:
            pos = self._player.get_pos_seconds()
            self._pos_lbl.configure(text=_fmt_tc(pos))
            if not self._player.is_playing():
                self._is_playing = False
                self._is_paused  = False
                self._play_btn.configure(text="▶ Play")
        self._poll_id = self._root.after(500, self._poll_playback)

    def cleanup(self) -> None:
        if self._poll_id is not None:
            self._root.after_cancel(self._poll_id)
            self._poll_id = None
        self._player.cleanup()
