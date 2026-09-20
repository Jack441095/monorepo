# composition/song_generator/export.py
# Sidecar report export (JSON) and MIDI export for a finished `SongRender`.

from __future__ import annotations

import json
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    import pretty_midi  # type: ignore[import]

try:
    import pretty_midi  # type: ignore[import]
except ImportError:
    pretty_midi = None

from .models import SongRender


class ExportMixin:
    """JSON report + MIDI export for a `SongRender`."""

    @staticmethod
    def export_report(song: SongRender, *, out_path: str) -> str:
        """
        Write a small JSON sidecar with seed/config snapshot + metrics (if present).
        """
        payload: Dict[str, Any] = {
            "sections": [
                {
                    "emotion_name": s.emotion_name,
                    "bars": int(s.bars),
                    "root_note": int(s.root_note),
                    "temperature": float(s.temperature),
                    "target_notes_per_bar": float(s.target_notes_per_bar),
                    "melody_style": str(s.melody_style),
                }
                for s in (song.sections or [])
            ],
            "tempo_map": list(song.tempo_map or []),
            "metadata": dict(song.metadata or {}),
            "event_count": int(len(song.events or [])),
        }
        rp = str(out_path) + ".report.json"
        with open(rp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
        return rp

    @staticmethod
    def export_to_midi(
        song: SongRender,
        *,
        out_path: str,
        default_bpm: float = 70.0,
        program_map: Optional[Dict[int, int]] = None,
    ) -> str:
        """
        Export the arranged song to a MIDI file.

        Notes:
        - Uses a simple tempo mapping: each section starts a new fixed tempo.
        - Uses one instrument per channel, where channel is your internal 0..5.
        """
        if pretty_midi is None:
            raise RuntimeError(
                "MIDI export requires 'pretty_midi' but it is not installed. "
                "Install it (e.g. `pip install pretty_midi`) or disable MIDI export."
            )
        pm = pretty_midi.PrettyMIDI(initial_tempo=float(default_bpm))

        program_map = program_map or {
            0: pretty_midi.instrument_name_to_program("Acoustic Bass"),
            1: pretty_midi.instrument_name_to_program("Electric Piano 1"),
            2: pretty_midi.instrument_name_to_program("Lead 1 (square)"),
            # pretty_midi only accepts General MIDI *melodic* names; keep these conservative.
            3: pretty_midi.instrument_name_to_program("Synth Strings 1"),
            4: pretty_midi.instrument_name_to_program("Pad 2 (warm)"),
            5: pretty_midi.instrument_name_to_program("Flute"),
            # Channel 6 is percussion. In General MIDI, drums live on channel 10 (is_drum)
            # where the *program* is irrelevant and each MIDI note number selects a drum
            # sound -- so it must NOT go through `instrument_name_to_program` (which only
            # accepts the 128 melodic GM names and raised ValueError on "Acoustic Bass Drum",
            # crashing all MIDI export). Program 0 + is_drum=True below is the correct route.
            6: 0,
        }

        instruments: Dict[int, Any] = {}
        for ch in range(7):
            inst = pretty_midi.Instrument(
                program=int(program_map.get(ch, 0)),
                is_drum=(ch == 6),
                name=f"ch_{ch}",
            )
            instruments[ch] = inst
            pm.instruments.append(inst)

        # Tempo map: convert beat positions to seconds using the tempo active at that beat.
        tempo_map = list(song.tempo_map) if song.tempo_map else [(0.0, float(default_bpm))]
        tempo_map.sort(key=lambda t: t[0])

        def bpm_at_beat(beat: float) -> float:
            current = tempo_map[0][1]
            for start_beat, bpm in tempo_map:
                if beat + 1e-9 >= start_beat:
                    current = bpm
                else:
                    break
            return float(current)

        def beat_to_seconds(beat: float) -> float:
            # Piecewise integration across tempo segments
            sec = 0.0
            last_beat = 0.0
            for i, (seg_start, seg_bpm) in enumerate(tempo_map):
                if beat <= seg_start:
                    break
                next_start = tempo_map[i + 1][0] if i + 1 < len(tempo_map) else beat
                seg_end = min(beat, next_start)
                if seg_end > max(last_beat, seg_start):
                    span_beats = seg_end - max(last_beat, seg_start)
                    sec += span_beats * (60.0 / float(seg_bpm))
                last_beat = seg_end
                if seg_end >= beat:
                    return sec
            # Remaining beats at current tempo
            sec += max(0.0, beat - last_beat) * (60.0 / bpm_at_beat(beat))
            return sec

        # Embed reproducibility metadata as a text event at time 0 (DAW-visible).
        try:
            if getattr(song, "metadata", None):
                from audiogen_core.repro import generation_metadata_text

                seed = None
                try:
                    metadata = getattr(song, "metadata", None)
                    seed = metadata.get("seed") if metadata else None
                except Exception:
                    seed = None
                text = generation_metadata_text(seed=seed, max_len=1000)
                pm.lyrics.append(pretty_midi.Lyric(text=f"GEN_META {text}", time=0.0))
        except Exception:
            pass

        # Add notes
        for ch, _midi, vel, start_beat, dur_beats, notes in song.events:
            if ch not in instruments:
                continue
            start_s = beat_to_seconds(float(start_beat))
            end_s = beat_to_seconds(float(start_beat + dur_beats))
            end_s = max(end_s, start_s + 0.01)
            velocity = int(max(1, min(127, int(vel))))
            for n in notes:
                if not isinstance(n, int):
                    continue
                pitch = int(max(0, min(127, n)))
                instruments[ch].notes.append(
                    pretty_midi.Note(
                        velocity=velocity,
                        pitch=pitch,
                        start=float(start_s),
                        end=float(end_s),
                    )
                )

        for inst in pm.instruments:
            inst.notes.sort(key=lambda note: note.start)

        pm.write(out_path)
        return out_path
