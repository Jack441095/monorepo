# sampler/sampler_resample.py
"""
Resampling / pitch-tracking DSP for the Sampler (variable-rate playback,
glide, granular shimmer, loop crossfade, pitch-tracking filter).

Split out of sampler.py (P4 giant-file decomposition) as a mixin, above
`sampler_kernels`/`sampler_types` and below `sampler_render` in the sampler
package's internal call graph. Method bodies are moved verbatim (precise
line-range extraction) -- no numeric/behavior changes, no buffer
shape/dtype/copy-semantics changes.

Elevated-risk note: the numba-JIT kernels this mixin calls
(`_one_pole_filter_nb_mono`, `_variable_rate_read_nb`, etc.) are only DEFINED
in `sampler_kernels` when numba is importable (same as the original module).
A static `from .sampler_kernels import _variable_rate_read_nb` would raise
ImportError at import time when numba is unavailable, which the original
single-file module never did (those names were simply unreferenced dead
branches, guarded by `if _have_numba():` / `if _nb is not None:`). To
preserve that fallback behavior exactly, this module imports the kernels
submodule itself (`from . import sampler_kernels as _kernels`) and accesses
`_kernels._name` lazily at each existing guarded call site, instead of
binding a load-time copy of the name.
"""
import hashlib
from typing import Tuple

import numpy as np

from audiogen_core.config import QualityMode

from . import sampler_kernels as _kernels
from .sampler_kernels import _have_numba, _nb
from .utils import find_nearest_zero_crossing


class _ResamplingMixin:
    def _build_rng(self) -> np.random.Generator:
        """
        Per-sampler RNG.

        When a global deterministic seed is present (CONFIG.composition.seed), this becomes
        repeatable and thread-stable. Otherwise it is nondeterministic (fresh per run).
        """
        seed = None
        try:
            seed = getattr(getattr(self._global_config, "composition", None), "seed", None)
        except Exception:
            seed = None

        if seed is None:
            return np.random.default_rng()

        try:
            s = f"{int(seed)}:{str(getattr(self, 'name', '') or '')}".encode("utf-8")
            digest = hashlib.blake2b(s, digest_size=8).digest()
            derived = int.from_bytes(digest, byteorder="little", signed=False) & 0xFFFFFFFF
        except Exception:
            derived = int(int(seed)) & 0xFFFFFFFF
        return np.random.default_rng(int(derived))

    def _use_hq_transposition(self) -> bool:
        mode = str(getattr(self, "transposition_quality_mode", "fast") or "fast").strip().lower()
        if mode == "hq":
            return True
        if mode == "auto":
            qm = getattr(self, "quality_mode", None)
            if qm is None:
                qm = getattr(getattr(self, "config", None), "quality_mode", None)
            if isinstance(qm, QualityMode):
                return qm == QualityMode.HIGH
            try:
                return str(getattr(qm, "value", qm)).strip().lower() == "high"
            except Exception:
                return False
        return False

    def _transposition_mode_cache_token(self) -> str:
        return "hq" if self._use_hq_transposition() else "fast"

    def _pitch_ratio(self, midi_note: int, root_midi: int) -> float:
        semitones = int(midi_note) - int(root_midi)
        idx = int(semitones) + int(self._pitch_ratio_lut_center)
        lut = getattr(self, "_pitch_ratio_lut", None)
        if lut is not None and 0 <= idx < int(len(lut)):
            return float(lut[idx])
        return float(2.0 ** (float(semitones) / 12.0))

    def _init_pitch_filter(
        self, enabled: bool, min_cutoff: float = 200.0, max_cutoff: float = 8000.0
    ):
        """Initialize a simple one‑pole low‑pass filter that tracks pitch."""
        self._pitch_filter_enabled = enabled
        self._pitch_filter_min = min_cutoff
        self._pitch_filter_max = max_cutoff
        if enabled:
            self._filter_state = 0.0  # for mono, but will handle stereo
            self._filter_state_r = 0.0

    def _apply_pitch_filter(self, audio: np.ndarray, midi_note: int) -> np.ndarray:
        """Apply one‑pole low‑pass filter with cutoff based on midi_note."""
        if not self._pitch_filter_enabled:
            return audio

        # Map MIDI note to cutoff frequency (logarithmic)
        # C2 (36) -> min, C8 (96) -> max
        t = (midi_note - 36) / 60.0  # 36..96 range
        t = np.clip(t, 0.0, 1.0)
        cutoff = self._pitch_filter_min + t * (self._pitch_filter_max - self._pitch_filter_min)
        # One‑pole coefficient
        alpha = np.exp(-2.0 * np.pi * cutoff / self.sample_rate)
        coeff = float(1.0 - alpha)  # 0..1

        x = np.asarray(audio, dtype=np.float32)
        if x.size == 0:
            return x

        if x.ndim == 1:
            st = float(getattr(self, "_filter_state", 0.0) or 0.0)
            if _nb is not None:
                y, st = _kernels._one_pole_filter_nb_mono(x, coeff, st)
                self._filter_state = float(st)
                return y
            one_minus = 1.0 - coeff
            for i in range(len(x)):
                st = coeff * float(x[i]) + one_minus * st
                x[i] = st
            self._filter_state = float(st)
            return x

        # Stereo
        st_l = float(getattr(self, "_filter_state", 0.0) or 0.0)
        st_r = float(getattr(self, "_filter_state_r", 0.0) or 0.0)
        if _nb is not None:
            y, st_l, st_r = _kernels._one_pole_filter_nb_stereo(x, coeff, st_l, st_r)
            self._filter_state = float(st_l)
            self._filter_state_r = float(st_r)
            return y
        one_minus = 1.0 - coeff
        for i in range(x.shape[0]):
            st_l = coeff * float(x[i, 0]) + one_minus * st_l
            st_r = coeff * float(x[i, 1]) + one_minus * st_r
            x[i, 0] = st_l
            x[i, 1] = st_r
        self._filter_state = float(st_l)
        self._filter_state_r = float(st_r)
        return x

    def _variable_rate_read(
        self, raw: np.ndarray, step: float, loop_start: int, loop_end: int, max_samples: int
    ) -> np.ndarray:

        if len(raw) == 0 or max_samples <= 0:
            return np.zeros((max_samples, 2), dtype=np.float32)

        # Ensure stereo float32
        if raw.ndim == 1:
            raw_stereo = np.column_stack([raw, raw]).astype(np.float32)
        else:
            raw_stereo = raw.astype(np.float32)

        src_len = len(raw_stereo)
        # Defensive loop-point validation: loop points are authored in "source samples"
        # but the actual loaded buffer can differ (resample, trims, start offsets).
        # If loop points fall out of bounds, interpolation can index out of range.
        try:
            ls = int(loop_start)
        except Exception:
            ls = 0
        try:
            le = int(loop_end)
        except Exception:
            le = 0
        if src_len <= 1:
            return np.zeros((max_samples, 2), dtype=np.float32)
        if ls < 0:
            ls = 0
        if le < 0:
            le = 0
        if ls >= src_len:
            ls = 0
        if le > src_len:
            le = src_len
        # Require at least a tiny span; otherwise treat as non-looping.
        looping = le > ls + 4

        if _have_numba():
            if self._use_hq_transposition():
                return _kernels._variable_rate_read_hq_nb(raw_stereo, float(step), ls, le, looping, int(max_samples))
            else:
                return _kernels._variable_rate_read_nb(raw_stereo, float(step), ls, le, looping, int(max_samples))

        # Build all read positions at once — avoids the per-sample Python loop
        positions = np.arange(max_samples, dtype=np.float64) * step  # float64 keeps precision for long notes

        if looping:
            loop_range = float(le - ls)
            past_mask = positions >= le
            if past_mask.any():
                positions[past_mask] = ls + (positions[past_mask] - le) % loop_range
            n_valid = max_samples
        else:
            n_valid = int(np.searchsorted(positions, src_len, side="left"))
            n_valid = min(n_valid, max_samples)
            positions = positions[:n_valid]

        if n_valid == 0:
            return np.zeros((0, 2), dtype=np.float32)

        idx_f = positions.astype(np.int32)  # floor indices
        frac = (positions - idx_f).astype(np.float32)  # fractional parts

        if self._use_hq_transposition():
            # Catmull-Rom cubic interpolation: higher quality than linear for offline/high modes.
            idx_m1 = np.maximum(idx_f - 1, 0)
            idx_0 = np.clip(idx_f, 0, src_len - 1)
            idx_p1 = np.minimum(idx_f + 1, src_len - 1)
            idx_p2 = np.minimum(idx_f + 2, src_len - 1)

            p0 = raw_stereo[idx_m1]
            p1 = raw_stereo[idx_0]
            p2 = raw_stereo[idx_p1]
            p3 = raw_stereo[idx_p2]

            t = frac[:, np.newaxis]
            t2 = t * t
            t3 = t2 * t
            out = 0.5 * (
                (2.0 * p1)
                + (-p0 + p2) * t
                + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t2
                + (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * t3
            )
            return out.astype(np.float32, copy=False)

        # Vectorized linear interpolation (realtime-safe default).
        idx_c = np.minimum(idx_f + 1, src_len - 1)  # ceil indices, clamped at last sample
        out = raw_stereo[idx_f] * (1.0 - frac[:, np.newaxis]) + raw_stereo[idx_c] * frac[:, np.newaxis]
        return out.astype(np.float32, copy=False)

    def _variable_rate_read_positions(
        self,
        raw: np.ndarray,
        *,
        positions: np.ndarray,
        loop_start: int,
        loop_end: int,
    ) -> np.ndarray:
        """
        Vectorized variable-rate read using explicit source `positions` (in samples).

        Supports optional looping: positions are wrapped into [loop_start, loop_end)
        when loop points are valid. When looping is disabled, output is truncated at
        the first position that reaches the end of the source buffer.
        """
        if raw is None:
            return np.zeros((0, 2), dtype=np.float32)
        pos = np.asarray(positions, dtype=np.float64)
        if pos.size == 0:
            return np.zeros((0, 2), dtype=np.float32)

        # Ensure stereo float32
        if raw.ndim == 1:
            raw_stereo = np.column_stack([raw, raw]).astype(np.float32)
        else:
            raw_stereo = raw.astype(np.float32, copy=False)

        src_len = int(len(raw_stereo))
        if src_len <= 1:
            return np.zeros((0, 2), dtype=np.float32)

        try:
            ls = int(loop_start)
        except Exception:
            ls = 0
        try:
            le = int(loop_end)
        except Exception:
            le = 0
        if ls < 0:
            ls = 0
        if le < 0:
            le = 0
        if ls >= src_len:
            ls = 0
        if le > src_len:
            le = src_len
        looping = bool(le > ls + 4)

        if looping:
            loop_range = float(le - ls)
            past = pos >= float(le)
            if past.any():
                pos = pos.copy()
                pos[past] = float(ls) + (pos[past] - float(le)) % loop_range
            n_valid = int(pos.size)
        else:
            n_valid = int(np.searchsorted(pos, float(src_len), side="left"))
            n_valid = int(max(0, min(n_valid, int(pos.size))))
            pos = pos[:n_valid]

        if n_valid <= 0:
            return np.zeros((0, 2), dtype=np.float32)

        if _have_numba():
            if self._use_hq_transposition():
                return _kernels._variable_rate_read_positions_hq_nb(raw_stereo, pos)
            else:
                return _kernels._variable_rate_read_positions_nb(raw_stereo, pos)

        idx_f = pos.astype(np.int32)
        frac = (pos - idx_f).astype(np.float32)

        if self._use_hq_transposition():
            idx_m1 = np.maximum(idx_f - 1, 0)
            idx_0 = np.clip(idx_f, 0, src_len - 1)
            idx_p1 = np.minimum(idx_f + 1, src_len - 1)
            idx_p2 = np.minimum(idx_f + 2, src_len - 1)

            p0 = raw_stereo[idx_m1]
            p1 = raw_stereo[idx_0]
            p2 = raw_stereo[idx_p1]
            p3 = raw_stereo[idx_p2]

            t = frac[:, np.newaxis]
            t2 = t * t
            t3 = t2 * t
            out = 0.5 * (
                (2.0 * p1)
                + (-p0 + p2) * t
                + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t2
                + (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * t3
            )
            return out.astype(np.float32, copy=False)

        idx_c = np.minimum(idx_f + 1, src_len - 1)
        out = raw_stereo[idx_f] * (1.0 - frac[:, np.newaxis]) + raw_stereo[idx_c] * frac[:, np.newaxis]
        return out.astype(np.float32, copy=False)

    def _glide_positions(
        self,
        *,
        step_from: float,
        step_to: float,
        glide_samples: int,
        total_samples: int,
    ) -> np.ndarray:
        n = int(max(0, total_samples))
        if n <= 0:
            return np.zeros((0,), dtype=np.float64)
        g = int(max(0, min(int(glide_samples), n)))
        if g <= 1:
            step = np.full((n,), float(step_to), dtype=np.float64)
        else:
            # Linear glide in playback rate; short (20ms) so this reads as a slide
            # without obvious "ramp curvature" artifacts.
            ramp = np.linspace(float(step_from), float(step_to), g, dtype=np.float64, endpoint=False)
            if g < n:
                tail = np.full((n - g,), float(step_to), dtype=np.float64)
                step = np.concatenate([ramp, tail])
            else:
                step = ramp
        # positions[0] == 0 (match arange*step style)
        pos = np.cumsum(step, dtype=np.float64) - step
        return pos

    def _granular_shimmer_read(
        self,
        raw: np.ndarray,
        *,
        step: float,
        loop_start: int,
        loop_end: int,
        max_samples: int,
        grain_ms: float,
        overlap: float,
        looplet_ms: float,
        drift_seconds: float,
        reseed_seconds: float,
        spray_ms: float,
        pan_spread: float,
        time_jitter: float,
    ) -> np.ndarray:
        """
        Granular loop playback that slowly drifts the loop window.

        Designed for pads/chords: reduces obvious repetition without intentional pitch jitter.
        Drift/reseed are deterministic in render-time (no wall-clock time dependency).
        """
        if raw is None or len(raw) == 0 or max_samples <= 0:
            return np.zeros((max_samples, 2), dtype=np.float32)

        # Ensure stereo float32
        if raw.ndim == 1:
            raw_stereo = np.column_stack([raw, raw]).astype(np.float32)
        else:
            raw_stereo = raw.astype(np.float32, copy=False)

        sr = int(getattr(self, "sample_rate", 44100))
        src_len = int(len(raw_stereo))

        ls = int(max(0, min(int(loop_start), src_len - 1)))
        le = int(max(0, min(int(loop_end), src_len))) if int(loop_end) > int(loop_start) else int(src_len)
        if le <= ls + 4096:
            return self._variable_rate_read(raw_stereo, float(step), int(ls), int(le), int(max_samples))

        grain_len = int(round(float(grain_ms) * float(sr) / 1000.0))
        grain_len = int(max(64, min(grain_len, int(max_samples))))

        ov = float(max(0.0, min(float(overlap), 0.95)))
        hop = int(max(1, round(grain_len * (1.0 - ov))))
        tj = float(max(0.0, min(float(time_jitter), 0.5)))
        hop_j = int(round(float(hop) * tj))

        loop_span = int(le - ls)
        looplet_len = int(round(float(looplet_ms) * float(sr) / 1000.0))
        looplet_len = int(max(256, min(looplet_len, loop_span)))
        max_offset = int(max(0, loop_span - looplet_len))

        w = np.hanning(grain_len).astype(np.float32)
        w2 = w[:, np.newaxis]

        out = np.zeros((max_samples, 2), dtype=np.float32)
        norm = np.zeros((max_samples,), dtype=np.float32)

        drift_period = float(max(0.05, float(drift_seconds)))
        reseed_s = float(max(0.0, float(reseed_seconds)))
        phase = float(self._rng.random() * 2.0 * np.pi)
        spray_samps = int(round(float(max(0.0, float(spray_ms))) * float(sr) / 1000.0))
        pspread = float(max(0.0, min(float(pan_spread), 1.0)))

        grain_idx = 0
        out_i = 0
        last_reseed_bucket = -1
        while out_i < max_samples:
            tg = float(grain_idx * hop) / float(sr)
            if reseed_s > 1e-6:
                bucket = int(tg / reseed_s)
                if bucket != last_reseed_bucket:
                    phase = float(self._rng.random() * 2.0 * np.pi)
                    last_reseed_bucket = bucket

            if max_offset > 0:
                s = 0.5 * (1.0 + float(np.sin((2.0 * np.pi * tg / drift_period) + phase)))
                offset = int(round(s * float(max_offset)))
            else:
                offset = 0
            win_start = int(ls + offset)
            win_end = int(win_start + looplet_len)

            n = int(min(grain_len, max_samples - out_i))
            if hop_j > 0:
                hop_i = int(
                    max(
                        1,
                        int(hop)
                        + int(self._rng.integers(int(-hop_j), int(hop_j) + 1)),
                    )
                )
            else:
                hop_i = hop

            if spray_samps > 0:
                sp = int(
                    self._rng.integers(int(-spray_samps), int(spray_samps) + 1)
                )
            else:
                sp = 0
            if sp != 0:
                win_start = int(max(ls, min(win_start + sp, le - looplet_len)))
                win_end = int(win_start + looplet_len)

            pos = (np.arange(n, dtype=np.float64) * float(step)) + float(win_start)
            past = pos >= float(win_end)
            if past.any():
                pos[past] = float(win_start) + (pos[past] - float(win_end)) % float(looplet_len)

            idx_f = pos.astype(np.int32)
            frac = (pos - idx_f).astype(np.float32)
            idx_c = np.minimum(idx_f + 1, src_len - 1)
            g = raw_stereo[idx_f] * (1.0 - frac[:, np.newaxis]) + raw_stereo[idx_c] * frac[:, np.newaxis]
            g = g.astype(np.float32, copy=False)

            if pspread > 1e-6:
                pan = float(self._rng.uniform(float(-pspread), float(pspread)))
                pan = float(np.clip(pan, -1.0, 1.0))
                left_gain = float(np.sqrt(0.5 * (1.0 - pan)))
                right_gain = float(np.sqrt(0.5 * (1.0 + pan)))
                g = g.copy()
                g[:, 0] *= left_gain
                g[:, 1] *= right_gain

            out[out_i : out_i + n] += g[:n] * w2[:n]
            norm[out_i : out_i + n] += w[:n]

            grain_idx += 1
            out_i += hop_i

        nz = norm > 1e-8
        out[nz] = (out[nz].T / norm[nz]).T
        return out.astype(np.float32, copy=False)

    def _apply_loop_crossfade(
        self,
        raw_stereo: np.ndarray,
        *,
        loop_start: int,
        loop_end: int,
        crossfade_ms: float,
    ) -> Tuple[np.ndarray, int, int]:
        """
        Smooth the loop boundary by blending the loop tail into the loop head once.
        This emulates Ableton Simpler's loop crossfade feel (reduces clicks).
        Returns (possibly modified raw_stereo, adjusted_loop_start, adjusted_loop_end).
        """
        if raw_stereo is None or len(raw_stereo) == 0:
            return raw_stereo, loop_start, loop_end
        if loop_end <= loop_start:
            return raw_stereo, loop_start, loop_end

        ls = int(max(0, min(loop_start, len(raw_stereo) - 1)))
        le = int(max(0, min(loop_end, len(raw_stereo))))
        if le <= ls + 4:
            return raw_stereo, loop_start, 0

        # Snap loop points toward zero crossings (best-effort).
        try:
            ls = int(find_nearest_zero_crossing(raw_stereo, ls))
            le = int(find_nearest_zero_crossing(raw_stereo, le))
        except Exception:
            pass
        if le <= ls + 4:
            return raw_stereo, loop_start, 0

        loop_len = le - ls
        cf = int(float(crossfade_ms) * float(self.sample_rate) / 1000.0)
        cf = int(max(0, min(cf, loop_len // 4, 2048)))
        if cf <= 0:
            return raw_stereo, ls, le

        # Apply a single crossfade at the loop head.
        out = np.array(raw_stereo, dtype=np.float32, copy=True)
        # Cache the cosine crossfade windows by length (exact DSP, fewer allocs).
        with self._env_cache_lock:
            env_in = self._env_cache.get(("loop_env_in", int(cf)))
            env_out = self._env_cache.get(("loop_env_out", int(cf)))
            if env_in is None or env_out is None:
                t = np.linspace(0.0, 1.0, cf, dtype=np.float32)[:, np.newaxis]
                env_out = (0.5 * (1.0 + np.cos(np.pi * t))).astype(np.float32, copy=False)
                env_in = (0.5 * (1.0 - np.cos(np.pi * t))).astype(np.float32, copy=False)
                self._env_cache[("loop_env_in", int(cf))] = env_in
                self._env_cache[("loop_env_out", int(cf))] = env_out
        head = out[ls : ls + cf].copy()
        tail = out[le - cf : le].copy()
        out[ls : ls + cf] = tail * env_out + head * env_in
        return out, ls, le

    def pitch_shift(self, audio: np.ndarray, semitones: float) -> np.ndarray:
        """
        Lightweight pitch shift by resampling (classic sampler behavior: pitch = speed).
        Positive semitones shorten, negative semitones lengthen.
        """
        if audio is None:
            return audio
        x = np.asarray(audio, dtype=np.float32)
        if x.ndim != 1:
            x = x.reshape(-1).astype(np.float32, copy=False)
        if len(x) == 0:
            return x
        rate = float(2.0 ** (float(semitones) / 12.0))
        if rate <= 0:
            return x.copy()
        out_len = max(1, int(np.floor(len(x) / rate)))
        pos = np.arange(out_len, dtype=np.float64) * rate
        idx_f = pos.astype(np.int32)
        frac = (pos - idx_f).astype(np.float32)
        idx_c = np.minimum(idx_f + 1, len(x) - 1)
        y = x[idx_f] * (1.0 - frac) + x[idx_c] * frac
        return y.astype(np.float32)
