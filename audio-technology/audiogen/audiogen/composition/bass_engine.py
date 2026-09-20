from audiogen_core.config import resolve_config
# composition/bass_engine.py
# Project module `bass_engine` (composition).

import logging
from typing import List, Tuple

from data.music_data import EmotionProfile

logger = logging.getLogger(__name__)


class BassEngine:
    """Owns bass-register utilities and bass-line generation."""

    BASS_LOW = 33
    BASS_HIGH = 41
    BASS_TARGET_LOW = 33

    def __init__(self, owner):
        self.owner = owner

    @staticmethod
    def bass_pattern(style: str, beats_per_bar: float, notes_per_bar: int) -> List[Tuple[float, float]]:
        if style in {"sustained", "drone"} or notes_per_bar <= 1:
            return [(0.0, beats_per_bar)]
        if style == "bouncy":
            return [(0.0, 1.0), (2.0, 1.0)]
        if style == "driving":
            return [(0.0, 1.0), (1.0, 1.0), (2.0, 1.0), (3.0, 1.0)]
        return [(0.0, 2.0), (2.0, 2.0)]

    def clamp_to_bass_register(self, midi_note: int) -> int:
        while midi_note < self.BASS_LOW:
            midi_note += 12
        while midi_note > self.BASS_HIGH:
            midi_note -= 12
        return midi_note

    def get_bass_chord_tones(self, chord: str, root: int) -> List[int]:
        all_notes = self.owner._chord_symbol_to_notes(chord, root)
        bass_notes = [n for n in all_notes if self.BASS_LOW <= n <= self.BASS_HIGH]
        if not bass_notes:
            bass_notes = [self.clamp_to_bass_register(root)]
        return sorted(bass_notes)

    def generate_bass_line(
        self,
        chords: List[str],
        roots: List[int],
        bars: int,
        emotion: EmotionProfile,
        beats_per_bar: float = 4.0,
        density: float = 1.0,
        base_style: str = "simple",
        debug: bool = False,
    ) -> List[Tuple[int, float, float]]:
        events = []

        emo_name = emotion.name.lower()
        if any(tag in emo_name for tag in ("sad", "grief", "remorse", "disappointment")):
            notes_per_bar = 1
            style = "sustained"
        elif "joy" in emo_name or "excitement" in emo_name:
            notes_per_bar = max(2, int(4.0 * density))
            style = "bouncy"
        elif "calm" in emo_name:
            notes_per_bar = max(1, int(1.5 * density))
            style = "sustained"
        elif "anger" in emo_name:
            notes_per_bar = max(2, int(4.0 * density))
            style = "driving"
        else:
            notes_per_bar = max(2, int(2.0 * density))
            style = base_style

        for bar, (chord, root) in enumerate(zip(chords, roots)):
            bass_tones = self.get_bass_chord_tones(chord, root)
            if debug:
                logger.debug("Bar %s: chord=%s, root=%s, bass options=%s", bar, chord, root, bass_tones)

            pattern = self.bass_pattern(style, beats_per_bar, max(1, notes_per_bar))
            for i, (beat_offset, duration) in enumerate(pattern):
                beat = bar * beats_per_bar + beat_offset

                if style == "drone":
                    note = bass_tones[0]
                elif style == "bouncy":
                    root_note = bass_tones[0]
                    fifth_candidates = [n for n in bass_tones if (n - root_note) % 12 == 7]
                    fifth = fifth_candidates[0] if fifth_candidates else root_note
                    note = root_note if i % 2 == 0 else fifth
                elif style == "sustained":
                    note = bass_tones[0]
                elif style == "driving":
                    note = bass_tones[0]
                else:
                    root_note = bass_tones[0]
                    fifth_candidates = [n for n in bass_tones if (n - root_note) % 12 == 7]
                    fifth = fifth_candidates[0] if fifth_candidates else root_note
                    note = root_note if i % 2 == 0 else fifth

                events.append((note, beat, duration))

        events = self.smooth_bass_line(events, chords, roots, beats_per_bar)
        intel_on = resolve_config("composition", "bass_intelligence_enabled", True, bool)
        intel_k = resolve_config("composition", "bass_intelligence_strength", 0.72, float)
        if intel_on and events:
            events = self.apply_bass_intelligence(
                events,
                chords=chords,
                roots=roots,
                beats_per_bar=beats_per_bar,
                strength=float(max(0.0, min(1.0, float(intel_k)))),
            )

        if debug:
            for note, start, dur in events:
                bar = int(start // beats_per_bar)
                logger.debug("  Final: bar %s, note %s", bar, note)

        return events

    def smooth_bass_line(
        self,
        events: List[Tuple[int, float, float]],
        chords: List[str],
        roots: List[int],
        beats_per_bar: float,
    ) -> List[Tuple[int, float, float]]:
        if len(events) < 2:
            return events

        smoothed = [events[0]]
        for i in range(1, len(events)):
            prev_note = smoothed[-1][0]
            curr_note, start, dur = events[i]
            bar = min(int(start // beats_per_bar), len(chords) - 1)
            allowed = self.get_bass_chord_tones(chords[bar], roots[bar])

            if abs(curr_note - prev_note) > 7:
                curr_note = min(allowed, key=lambda n: abs(n - prev_note))
            elif curr_note not in allowed:
                curr_note = min(allowed, key=lambda n: abs(n - curr_note))

            smoothed.append((curr_note, start, dur))
        return smoothed

    @staticmethod
    def _is_dominant_like(chord: str) -> bool:
        s = str(chord or "").lower()
        return ("v" in s and "iv" not in s) or ("7" in s) or ("dom" in s) or ("sus" in s)

    def apply_bass_intelligence(
        self,
        events: List[Tuple[int, float, float]],
        *,
        chords: List[str],
        roots: List[int],
        beats_per_bar: float,
        strength: float,
    ) -> List[Tuple[int, float, float]]:
        if len(events) < 2 or beats_per_bar <= 1e-9:
            return events
        out = [tuple(ev) for ev in events]
        s = max(0.0, min(1.0, float(strength)))

        # Bar downbeat correction: keep first hit near root with stepwise carry from previous bar.
        for bar in range(1, max(1, len(chords))):
            target_root = self.clamp_to_bass_register(int(roots[min(bar, len(roots) - 1)]))
            first_i = None
            prev_i = None
            bar_start = float(bar) * float(beats_per_bar)
            for i, ev in enumerate(out):
                st = float(ev[1])
                if st < bar_start:
                    prev_i = i
                if bar_start - 1e-6 <= st < bar_start + 0.75:
                    first_i = i
                    break
            if first_i is None:
                continue
            prev_note = int(out[prev_i][0]) if prev_i is not None else int(out[first_i][0])
            cur_note = int(out[first_i][0])
            # Blend between current and root-focused target while penalizing large leaps.
            candidates = [target_root, target_root + 12, target_root - 12, cur_note]
            candidates = [self.clamp_to_bass_register(int(c)) for c in candidates]
            best = min(
                candidates,
                key=lambda n: (0.75 * abs(int(n) - int(prev_note)) + (1.0 - 0.50 * s) * abs(int(n) - int(target_root))),
            )
            if abs(int(best) - int(prev_note)) > 7 and s >= 0.30:
                # Force a stepwise compromise note when a jump would be too wide.
                step = 2 if int(best) > int(prev_note) else -2
                best = self.clamp_to_bass_register(int(prev_note) + int(step))
            out[first_i] = (int(best), float(out[first_i][1]), float(out[first_i][2]))

            # Dominant-like bars: add a subtle pre-cadential lift on beat 3 when possible.
            if self._is_dominant_like(chords[min(bar, len(chords) - 1)]) and s >= 0.45:
                lift_i = None
                for i, ev in enumerate(out):
                    st = float(ev[1])
                    if bar_start + 1.75 <= st <= bar_start + 2.25:
                        lift_i = i
                        break
                if lift_i is not None:
                    r = int(target_root)
                    fifth = self.clamp_to_bass_register(int(r + 7))
                    choose = fifth if abs(int(fifth) - int(prev_note)) <= 7 else r
                    out[lift_i] = (int(choose), float(out[lift_i][1]), float(out[lift_i][2]))
        return out

    @staticmethod
    def bass_note_to_events(bass_notes: List[Tuple[int, float, float]], channel: int = 0, velocity: int = 80) -> List[Tuple]:
        return [(channel, note, velocity, start, dur, [note]) for note, start, dur in bass_notes]