# monophonic.py

from typing import List, Optional, Tuple

import numpy as np

from .sampler import Sampler
from .utils import apply_fade_in_out, apply_fade_out

MONO_CUTOFF_FADE_MS = 5.0
# Keep this very small: larger values noticeably dull transients ("less pluck").
# This fade exists primarily to avoid rare clicky edges on note boundaries.
MONO_EDGE_FADE_MS = 0.2


def quantize_mono_duration_sec(duration_sec: float) -> float:
    try:
        from audiogen_core.config import CONFIG

        ms = float(getattr(getattr(CONFIG, "audio", None), "mono_render_duration_quantize_ms", 20.0) or 20.0)
    except Exception:
        ms = 20.0
    d = max(0.005, float(duration_sec))
    if ms <= 1e-6:
        return round(d, 4)
    step = max(0.001, float(ms) / 1000.0)
    return float(round(d / step) * step)


class MonophonicRenderer:
    def __init__(self, sampler: Sampler, sample_rate: int = 44100):
        self.sampler = sampler
        self.sample_rate = sample_rate
        self._cutoff_fade_smp = max(
            32, int(MONO_CUTOFF_FADE_MS * sample_rate / 1000.0)
        )
        self._edge_fade_smp = max(16, int(MONO_EDGE_FADE_MS * sample_rate / 1000.0))
        self.portamento_time = getattr(sampler.config, "portamento_time", 0.0)
        self.portamento_probability = float(getattr(sampler.config, "portamento_probability", 1.0) or 1.0)
        self.portamento_probability = float(max(0.0, min(1.0, self.portamento_probability)))
        # Many generated melodies/arps are quantized with no overlaps, so "true legato"
        # (start < prev_end) rarely occurs. Allow a small gate window so back-to-back
        # notes can still glide occasionally.
        try:
            gate_ms = getattr(sampler.config, "portamento_gate_ms", None)
            if gate_ms is None:
                gate_ms = 1000.0 * float(self.portamento_time or 0.0)
            self._portamento_gate_smp = int(max(0.0, float(gate_ms)) * sample_rate / 1000.0)
        except Exception:
            self._portamento_gate_smp = int(max(0.0, float(self.portamento_time or 0.0)) * sample_rate)

    def render_bar(
        self,
        events: List[Tuple],
        bar_samples: int,
        tempo: float,
        out: Optional[np.ndarray] = None,
        *,
        events_sorted: bool = False,
    ) -> np.ndarray:
        """
        Render monophonic events into ``out`` when provided (shape ``(bar_samples, 2)``,
        float32); otherwise allocate and return a new buffer. Caller must zero ``out``
        before calling when reusing a pooled buffer.
        """
        bs = int(max(0, bar_samples))
        if out is not None:
            if out.shape != (bs, 2) or out.dtype != np.float32:
                raise ValueError(f"out must be float32 with shape ({bs}, 2), got {out.dtype} {out.shape}")
            buf = out
        else:
            buf = np.zeros((bs, 2), dtype=np.float32)
        if not events:
            return buf

        if not events_sorted and len(events) > 1 and any(
            events[i][3] > events[i + 1][3] for i in range(len(events) - 1)
        ):
            events = sorted(events, key=lambda e: e[3])

        previous_note = None
        previous_end_sample = 0

        for i, (_, midi, velocity, start_beats, duration_beats, _notes) in enumerate(
            events
        ):
            start_smp = int(start_beats / 4.0 * bs)
            if start_smp >= bs:
                continue

            natural_sec = duration_beats * (60.0 / tempo)

            if i + 1 < len(events):
                next_start_smp = int(events[i + 1][3] / 4.0 * bs)
                available_smp = max(0, next_start_smp - start_smp)
            else:
                available_smp = bs - start_smp

            max_sec = available_smp / self.sample_rate
            render_sec = min(natural_sec, max_sec)
            note_was_cut = render_sec < natural_sec
            release_after = render_sec if note_was_cut else None

            if render_sec <= 0.0:
                continue

            legato = False
            if previous_note is not None:
                # Treat near-zero gaps as legato for glide triggering (gate window).
                gap_smp = int(start_smp) - int(previous_end_sample)
                legato = bool(gap_smp <= int(getattr(self, "_portamento_gate_smp", 0) or 0))

            use_glide = False
            if legato and self.portamento_time > 0 and previous_note != midi:
                try:
                    rng = getattr(self.sampler, "_rng", None)
                    r = float(rng.random()) if rng is not None else float(np.random.random())
                except Exception:
                    r = float(np.random.random())
                use_glide = bool(r < float(self.portamento_probability))

            q_velocity = int(max(1, min(127, round(int(velocity) / 4.0) * 4)))
            if use_glide:
                glide_dur = min(self.portamento_time, render_sec)
                note_audio = self.sampler.render_glide_note(
                    previous_note, midi, q_velocity, glide_dur, render_sec, release_after
                )
            else:
                render_sec = quantize_mono_duration_sec(render_sec)
                if release_after is not None:
                    release_after = min(render_sec, quantize_mono_duration_sec(release_after))
                note_audio = self.sampler.render_note(
                    midi, q_velocity, render_sec, release_after
                )

            # Sampler note cache entries are immutable (may be returned read-only).
            # We apply edge/cutoff fades in-place here, so ensure we have a writable buffer.
            try:
                if hasattr(note_audio, "flags") and not bool(note_audio.flags.writeable):
                    note_audio = note_audio.copy()
            except Exception:
                note_audio = np.asarray(note_audio, dtype=np.float32).copy()

            edge_fade = min(self._edge_fade_smp, max(0, len(note_audio) // 4))
            if edge_fade > 0:
                note_audio = apply_fade_in_out(note_audio, edge_fade)

            if len(note_audio) > available_smp:
                note_audio = note_audio[:available_smp].copy()
                fade_len = min(self._cutoff_fade_smp, available_smp)
                note_audio = apply_fade_out(note_audio, fade_len)

            end_smp = min(start_smp + len(note_audio), bs)
            seg_len = end_smp - start_smp
            if seg_len > 0:
                buf[start_smp:end_smp] += note_audio[:seg_len]

            previous_note = midi
            previous_end_sample = end_smp

        return buf
