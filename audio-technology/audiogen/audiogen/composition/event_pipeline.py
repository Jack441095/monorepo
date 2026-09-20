from audiogen_core.config import resolve_config
# composition/event_pipeline.py
# Project module `event_pipeline` (composition).

import logging
import random
from typing import Iterable, List, Sequence, Tuple, Union

from midi.midi_range_limiter import RANGE_LIMITER

from .event import Event

logger = logging.getLogger(__name__)


class EventPipeline:
    """Owns post-generation event validation and humanization."""

    def __init__(self, rng=random):
        # `rng` may be the module-level `random` (legacy/tests) or a `random.Random`
        # instance (deterministic generation).
        self.rng = rng
        # Optional provider for deterministic, token-keyed RNGs (preferred).
        # Signature: fn(*tokens) -> random.Random
        self._deterministic_rng_provider = None

    def set_rng(self, rng) -> None:
        self.rng = rng

    def set_deterministic_rng_provider(self, fn) -> None:
        self._deterministic_rng_provider = fn

    def _det_rng(self, *tokens):
        fn = getattr(self, "_deterministic_rng_provider", None)
        if callable(fn):
            try:
                return fn(*tokens)
            except Exception:
                pass
        # Fallback: best-effort stable-ish RNG from current rng.
        try:
            base = getattr(self.rng, "random", random.random)()
            seed = int(float(base) * 1_000_000_000) ^ (hash(tuple(tokens)) & 0xFFFFFFFF)
            return random.Random(int(seed))
        except Exception:
            return random.Random(hash(tuple(tokens)) & 0xFFFFFFFF)

    @staticmethod
    def _clamp_velocity(v: int) -> int:
        return int(max(1, min(127, int(v))))

    @staticmethod
    def _bar_index(start_beats: float, beats_per_bar: float) -> int:
        if beats_per_bar <= 0:
            return 0
        return int(max(0, float(start_beats)) // float(beats_per_bar))

    def _apply_deterministic_groove(
        self,
        events: List[Event],
        *,
        beats_per_bar: float = 4.0,
    ) -> List[Event]:
        """
        Apply deterministic “performed” microtiming + velocity accents.

        This layer is *structured* (grid + accents) and keyed off a deterministic RNG,
        so it reads like pocket/performance rather than random jitter.
        """
        comp = resolve_config("composition", "", None)
        if comp is None:
            return events

        # If hard 16th quantization is enabled, do not apply any microtiming/swing.
        try:
            if bool(getattr(comp, "quantize_16th_enabled", False)):
                return events
        except Exception:
            pass

        try:
            micro_enabled = bool(getattr(comp, "micro_timing_enabled", False))
            chords_ms = float(getattr(comp, "micro_timing_chords_max_ms", 0.0) or 0.0)
            arp_ms = float(getattr(comp, "micro_timing_arp_max_ms", 0.0) or 0.0)
            mel_enabled = bool(getattr(comp, "melody_microtiming_enabled", False))
            mel_ms = float(getattr(comp, "melody_microtiming_max_ms", 0.0) or 0.0)
            mel_swing_enabled = bool(getattr(comp, "melody_swing_enabled", False))
            mel_swing = float(getattr(comp, "melody_swing_amount", 0.0) or 0.0)
        except Exception:
            micro_enabled = False
            chords_ms = 0.0
            arp_ms = 0.0
            mel_enabled = False
            mel_ms = 0.0
            mel_swing_enabled = False
            mel_swing = 0.0

        if not (micro_enabled or mel_enabled):
            return events

        # Velocity accent strength (0..1+). Used to tame “slammy” dynamics in dense/high-energy material.
        try:
            accent_strength = float(getattr(comp, "groove_accent_strength", 1.0) or 1.0) if comp is not None else 1.0
        except Exception:
            accent_strength = 1.0
        accent_strength = max(0.0, min(1.25, float(accent_strength)))

        # Convert ms → beats using a best-effort tempo (global_tempo is “good enough” for feel).
        # Using beats keeps the layer consistent with the rest of the pipeline.
        try:
            bpm = resolve_config("audio", "global_tempo", 70.0, float)
        except Exception:
            bpm = 70.0
        bpm = max(20.0, min(260.0, float(bpm)))
        sec_per_beat = 60.0 / float(bpm)
        ms_to_beats = 1e-3 / max(1e-6, sec_per_beat)

        chords_max_b = max(0.0, float(chords_ms) * ms_to_beats)
        arp_max_b = max(0.0, float(arp_ms) * ms_to_beats)
        mel_max_b = max(0.0, float(mel_ms) * ms_to_beats)
        mel_swing = max(0.0, min(0.25, float(mel_swing)))

        out: List[Event] = []
        for ev in events:
            ch = int(ev.channel)
            st = float(ev.start_beats)
            dur = float(ev.duration_beats)

            # Basic grid phase for accents: quarters + eighth “and”.
            # (Do NOT hard-quantize; just accent/offset slightly.)
            ph_q = st % 1.0
            on_downbeat = ph_q < 1e-6
            on_and = abs(ph_q - 0.5) < 1e-6

            # Choose lane-specific max microtiming.
            if ch == 2:
                max_b = mel_max_b if mel_enabled else 0.0
            elif ch == 3:
                max_b = arp_max_b if micro_enabled else 0.0
            elif ch in (1, 0, 5, 4):
                max_b = chords_max_b if micro_enabled else 0.0
            else:
                max_b = 0.0

            # Deterministic “push/pull”:
            # - bass slightly early on downbeats
            # - chords slightly late (laid back)
            # - arp slightly early on offbeats
            # - lead minimal (but optional swing)
            rng = self._det_rng("groove", ch, round(st, 6), round(dur, 6))
            base = 0.0
            if max_b > 1e-12:
                if ch == 0:
                    base = (-0.45 * max_b) if on_downbeat else (-0.10 * max_b)
                elif ch == 1:
                    base = (0.35 * max_b) if on_downbeat else (0.10 * max_b)
                elif ch == 3:
                    base = (-0.30 * max_b) if on_and else (0.05 * max_b)
                elif ch == 5:
                    base = (0.08 * max_b)
                elif ch == 2:
                    base = 0.0

                # Small deterministic variation so repeated hits don’t phase-lock.
                jitter = (rng.random() - 0.5) * 0.35 * max_b
                offset = float(base + jitter)
                st = max(0.0, st + offset)

            # Lead swing (delay “and” of the beat) as a gentle feel option.
            if ch == 2 and mel_swing_enabled and mel_swing > 1e-6:
                if on_and:
                    st = max(0.0, st + float(mel_swing) * 0.5)  # in beats

            # Deterministic accents (velocity):
            vel = int(ev.velocity)
            if ch in (0, 1, 3, 2, 5):
                acc = 0
                if on_downbeat:
                    acc = 6 if ch in (0, 1) else 4
                elif on_and and ch in (3, 2):
                    acc = 3
                if abs(float(accent_strength) - 1.0) > 1e-6 and acc:
                    acc = int(round(float(acc) * float(accent_strength)))
                vel = self._clamp_velocity(int(vel + acc))

            out.append(
                Event(
                    channel=ch,
                    midi=ev.midi,
                    velocity=int(vel),
                    start_beats=float(st),
                    duration_beats=float(max(0.05, dur)),
                    notes=list(ev.notes),
                )
            )

        return out

    @staticmethod
    def _snap_to_grid(x: float, grid: float) -> float:
        g = float(grid)
        if g <= 1e-12:
            return float(x)
        return float(round(float(x) / g) * g)

    def _quantize_16th(self, events: List[Event], *, beats_per_bar: float = 4.0) -> List[Event]:
        """
        Hard-quantize event timing to a 16th-note grid.
        Policy: default is start-only, preserving musical note lengths.
        """
        comp = resolve_config("composition", "", None)
        if comp is None:
            return events
        try:
            enabled = bool(getattr(comp, "quantize_16th_enabled", False))
            mode = str(getattr(comp, "quantize_16th_mode", "start_only") or "start_only").strip().lower()
        except Exception:
            enabled = False
            mode = "start_only"
        if not enabled:
            return events

        grid = float(beats_per_bar) / 16.0 if float(beats_per_bar) > 1e-9 else 0.25
        grid = max(1e-6, float(grid))
        out: List[Event] = []
        for ev in events:
            st = max(0.0, float(ev.start_beats))
            dur = max(0.05, float(ev.duration_beats))
            st_q = max(0.0, self._snap_to_grid(st, grid))
            if mode == "start_and_end":
                en = st + dur
                en_q = max(st_q + grid, self._snap_to_grid(en, grid))
                dur_q = max(0.05, float(en_q - st_q))
            else:
                dur_q = dur
            out.append(
                Event(
                    channel=int(ev.channel),
                    midi=ev.midi,
                    velocity=int(ev.velocity),
                    start_beats=float(st_q),
                    duration_beats=float(dur_q),
                    notes=list(ev.notes),
                )
            )
        return out

    @staticmethod
    def _to_event_list(events: Iterable[Union[Event, Sequence]]) -> List[Event]:
        out: List[Event] = []
        for ev in events:
            if isinstance(ev, Event):
                out.append(ev)
                continue
            try:
                out.append(Event.from_tuple(ev))  # type: ignore[arg-type]
            except Exception:
                # Let validate() decide what to do; keep a placeholder tuple-style failure out.
                logger.warning("Skipping malformed event: %r", ev)
        return out

    def clamp_event_payload(self, channel: int, notes):
        if not isinstance(notes, list):
            return notes

        return [RANGE_LIMITER.clamp_note(n, channel) if isinstance(n, int) else n for n in notes]

    def validate_event_objects(self, events: Iterable[Union[Event, Sequence]]) -> List[Event]:
        validated: List[Event] = []
        for event in self._to_event_list(events):
            channel = event.channel
            midi = event.midi
            velocity = event.velocity
            start = event.start_beats
            duration = event.duration_beats
            notes = event.notes
            if not isinstance(channel, int) or not (0 <= channel <= 5):
                logger.warning("Skipping event with invalid channel: %r", event)
                continue

            midi_value = midi
            if channel != 1 and isinstance(midi, int) and midi > 0:
                midi_value = RANGE_LIMITER.clamp_note(midi, channel)

            velocity = max(1, min(127, int(velocity)))
            start = max(0.0, float(start))
            duration = max(0.05, float(duration))
            notes_value = self.clamp_event_payload(channel, notes)

            validated.append(
                Event(
                    channel=int(channel),
                    midi=midi_value,
                    velocity=int(velocity),
                    start_beats=float(start),
                    duration_beats=float(duration),
                    notes=list(notes_value) if isinstance(notes_value, list) else [notes_value],
                )
            )

        # Final timing policy: hard-quantize to 16ths if enabled.
        try:
            validated = self._quantize_16th(validated, beats_per_bar=4.0)
        except Exception:
            pass
        return validated

    def validate_events(self, events: List[Tuple]) -> List[Tuple]:
        # Backwards-compatible tuple API.
        return [e.to_tuple() for e in self.validate_event_objects(events)]

    def humanize_event_objects(
        self,
        events: Iterable[Union[Event, Sequence]],
        humanization,
        probability: float = 1.0,
    ) -> List[Event]:
        h = humanization
        src = list(self._to_event_list(events))
        # First apply deterministic groove/microtiming layer (structured pocket).
        try:
            src = self._apply_deterministic_groove(src, beats_per_bar=4.0)
        except Exception:
            pass
        new_events: List[Event] = []
        batch_size = len(src)

        rng = getattr(self, "rng", random)
        do_humanize = [rng.random() < probability for _ in range(batch_size)]
        timing_jitters = [
            rng.uniform(-h.timing_jitter, h.timing_jitter) if (h.timing_jitter > 0 and do_humanize[i]) else 0
            for i in range(batch_size)
        ]

        if hasattr(h, "velocity_multipliers") and h.velocity_multipliers:
            velocity_factors = [
                rng.choice(h.velocity_multipliers) if do_humanize[i] else 1.0
                for i in range(batch_size)
            ]
        elif h.velocity_fluctuation > 0:
            velocity_factors = [
                1.0 + rng.uniform(-h.velocity_fluctuation, h.velocity_fluctuation) if do_humanize[i] else 1.0
                for i in range(batch_size)
            ]
        else:
            velocity_factors = [1.0] * batch_size

        duration_factors = [
            1.0 + rng.uniform(-h.articulation_variation, h.articulation_variation)
            if (h.articulation_variation > 0 and do_humanize[i]) else 1.0
            for i in range(batch_size)
        ]

        for i, ev in enumerate(src):
            channel = ev.channel
            midi = ev.midi
            velocity = ev.velocity
            start = max(0.0, float(ev.start_beats) + timing_jitters[i])
            duration = float(ev.duration_beats)
            notes = ev.notes

            if channel != 0 and do_humanize[i]:
                velocity = int(velocity * velocity_factors[i])
                velocity = max(20, min(127, velocity))

            duration *= duration_factors[i]
            duration = max(0.1, duration)
            new_events.append(
                Event(
                    channel=int(channel),
                    midi=midi,
                    velocity=int(velocity),
                    start_beats=float(start),
                    duration_beats=float(duration),
                    notes=list(notes),
                )
            )

        return new_events

    def humanize_events(self, events: List[Tuple], humanization, probability: float = 1.0) -> List[Tuple]:
        # Backwards-compatible tuple API.
        return [e.to_tuple() for e in self.humanize_event_objects(events, humanization, probability)]
