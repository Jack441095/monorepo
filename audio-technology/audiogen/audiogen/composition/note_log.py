from __future__ import annotations

import csv
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, List, Optional, Sequence, Tuple


_NOTE_NAMES_SHARP = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def _midi_to_name(midi: int) -> str:
    try:
        m = int(midi)
    except Exception:
        return ""
    if m < 0:
        return ""
    return str(_NOTE_NAMES_SHARP[m % 12])


def _default_log_path() -> Path:
    # project_root/logs/note_log.csv
    root = Path(__file__).resolve().parents[1]
    return root / "logs" / "note_log.csv"


def _safe_mkdir(p: Path) -> None:
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass


def _scale_pitch_classes(tonic_pc: int, scale_intervals: Sequence[int]) -> List[int]:
    t = int(tonic_pc) % 12
    out: List[int] = []
    for iv in list(scale_intervals or []):
        try:
            out.append((t + int(iv)) % 12)
        except Exception:
            continue
    # de-dup while preserving order
    seen = set()
    out2 = []
    for pc in out:
        if pc in seen:
            continue
        seen.add(pc)
        out2.append(pc)
    return out2


@dataclass
class NoteLogContext:
    emotion_name: str
    section_index: int
    root_midi: int
    beats_per_bar: float = 4.0
    scale_intervals: Tuple[int, ...] = ()
    seed: Optional[int] = None
    run_tag: str = ""


class NoteCSVLogger:
    """
    Append one row per *note* (not per event) to a CSV file.

    We log at the composition layer (post-validation/humanization) so the sheet reflects
    what the audio engine will actually play.
    """

    _HEADER = (
        "ts_unix",
        "emotion",
        "section_index",
        "channel",
        "bar",
        "beat_in_bar",
        "start_beats",
        "duration_beats",
        "velocity",
        "midi",
        "note_name",
        "pitch_class",
        "root_midi",
        "root_pc",
        "scale_pcs",
        "in_scale",
        "seed",
        "run_tag",
        "event_midi_field",
    )

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = Path(path) if path else _default_log_path()
        _safe_mkdir(self.path.parent)

    def _ensure_header(self) -> None:
        try:
            if self.path.exists() and self.path.stat().st_size > 0:
                return
        except Exception:
            # If we can't stat, still try writing header (file may not exist).
            pass
        try:
            with self.path.open("a", encoding="utf-8", newline="") as f:
                csv.writer(f).writerow(list(self._HEADER))
        except Exception:
            pass

    def log_events(self, events: Iterable[Sequence[Any]], ctx: NoteLogContext) -> int:
        self._ensure_header()

        tonic_pc = int(ctx.root_midi) % 12
        scale_pcs = _scale_pitch_classes(tonic_pc, list(ctx.scale_intervals or ()))
        scale_pcs_s = " ".join(str(int(x)) for x in scale_pcs)
        beats_per_bar = float(ctx.beats_per_bar) if float(ctx.beats_per_bar) > 1e-9 else 4.0

        rows: List[List[Any]] = []
        now = time.time()

        for ev in list(events or []):
            if not isinstance(ev, (list, tuple)) or len(ev) != 6:
                continue
            ch, midi_field, vel, start_beats, dur_beats, notes = ev
            try:
                ch_i = int(ch)
            except Exception:
                continue
            try:
                start = float(start_beats)
            except Exception:
                start = 0.0
            try:
                dur = float(dur_beats)
            except Exception:
                dur = 0.0
            try:
                vel_i = int(vel)
            except Exception:
                vel_i = 0

            bar = int(max(0.0, start) // beats_per_bar)
            beat_in_bar = float(max(0.0, start) - float(bar) * beats_per_bar)

            note_list: List[Any]
            if isinstance(notes, list):
                note_list = list(notes)
            elif isinstance(notes, tuple):
                note_list = list(notes)
            else:
                note_list = [notes]

            for n in note_list:
                if not isinstance(n, int):
                    continue
                midi_n = int(n)
                pc = int(midi_n) % 12
                in_scale = (pc in set(scale_pcs)) if scale_pcs else False
                rows.append(
                    [
                        float(now),
                        str(ctx.emotion_name),
                        int(ctx.section_index),
                        int(ch_i),
                        int(bar),
                        float(beat_in_bar),
                        float(start),
                        float(dur),
                        int(vel_i),
                        int(midi_n),
                        _midi_to_name(midi_n),
                        int(pc),
                        int(ctx.root_midi),
                        int(tonic_pc),
                        str(scale_pcs_s),
                        bool(in_scale),
                        None if ctx.seed is None else int(ctx.seed),
                        str(ctx.run_tag or ""),
                        str(midi_field),
                    ]
                )

        if not rows:
            return 0

        try:
            # Best-effort advisory lock via atomic append semantics.
            with self.path.open("a", encoding="utf-8", newline="") as f:
                w = csv.writer(f)
                w.writerows(rows)
        except Exception:
            return 0
        return int(len(rows))


_LOGGER_SINGLETON: Optional[NoteCSVLogger] = None


def get_note_csv_logger(path: Optional[str] = None) -> NoteCSVLogger:
    global _LOGGER_SINGLETON
    if _LOGGER_SINGLETON is None or (path is not None and str(_LOGGER_SINGLETON.path) != str(Path(path))):
        _LOGGER_SINGLETON = NoteCSVLogger(path=path)
    return _LOGGER_SINGLETON

