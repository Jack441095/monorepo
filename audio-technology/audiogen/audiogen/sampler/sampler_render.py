# sampler/sampler_render.py
"""
Per-note render pipeline for the Sampler (`_render_layer`, `_render_layer_glide`):
variable-rate read + shimmer, loop-crossfade caching, attack/edge fades, fixed
and key-tracked low-pass filtering, and the per-note filter envelope.

Split out of sampler.py (P4 giant-file decomposition) as a mixin: this is the
highest internal layer (it calls into `_ResamplingMixin` and
`_LayerRoutingMixin` methods via `self`), sitting just below the public
`render_note`/`render_glide_note` entry points that stay in sampler.py.
Method bodies are moved verbatim (precise line-range extraction) -- no
numeric/behavior changes, no buffer shape/dtype/copy-semantics changes.
"""
from typing import Optional

import numpy as np

from .utils import apply_fade_in_out, create_silent_sample


class _RenderMixin:
    def _render_layer(
        self,
        *,
        midi: int,
        velocity: int,
        duration_sec: float,
        release_after: Optional[float],
        lower,
        upper,
        w_low: float,
        w_up: float,
    ) -> np.ndarray:
        """Render raw audio for the selected layer(s) (before ADSR + velocity amplitude)."""
        if not getattr(self, "_raw_cache", None):
            return create_silent_sample(duration_sec, self.sample_rate)

        lower_idx = self._layer_index(lower)
        raw = self._raw_cache[lower_idx]
        offset_samples = int(getattr(lower, "start_offset", 0.0) * self.sample_rate)
        sj_ms = float(getattr(self.config, "start_jitter_ms", 0.0) or 0.0)
        if sj_ms > 0.0:
            sj = int(round(sj_ms * float(self.sample_rate) / 1000.0))
            if sj > 0:
                try:
                    offset_samples = max(
                        0, offset_samples + int(self._rng.integers(0, int(sj) + 1))
                    )
                except Exception:
                    offset_samples = max(0, offset_samples)

        step = self._pitch_ratio(int(midi), int(getattr(lower, "root_midi", 60)))

        loop_enabled = bool(getattr(self.config, "loop_enabled", False))
        # Optional: randomize the start point *within the loop* (or whole sample),
        # then depend on looping for sustain. This avoids identical chord/pad transients.
        rstart = bool(getattr(self.config, "random_start_within_loop", False))
        if loop_enabled and rstart:
            try:
                ls_abs = int(getattr(lower, "loop_start", 0) or 0)
                le_abs = int(getattr(lower, "loop_end", 0) or 0)
            except Exception:
                ls_abs, le_abs = 0, 0
            if le_abs <= ls_abs:
                # No loop points provided: optionally loop the whole sample.
                if bool(getattr(self.config, "loop_whole_sample_if_missing_points", True)):
                    ls_abs, le_abs = 0, int(len(raw))
            # Pick a random start within the loopable window (leave a tiny safety margin).
            if le_abs > ls_abs + 2048:
                try:
                    start_abs = int(
                        self._rng.integers(int(ls_abs), int(le_abs - 2048) + 1)
                    )
                    offset_samples = max(0, int(start_abs))
                except Exception:
                    pass

        if offset_samples >= len(raw):
            return create_silent_sample(duration_sec, self.sample_rate)
        raw_trimmed = raw[offset_samples:]

        if loop_enabled:
            # When random start is used, loop points are re-based to the trimmed audio.
            ls_abs = int(getattr(lower, "loop_start", 0) or 0)
            le_abs = int(getattr(lower, "loop_end", 0) or 0)
            if (le_abs <= ls_abs) and bool(getattr(self.config, "loop_whole_sample_if_missing_points", True)):
                ls_abs, le_abs = 0, int(len(raw))
            loop_start = max(0, int(ls_abs) - int(offset_samples))
            loop_end = int(le_abs) - int(offset_samples) if int(le_abs) > 0 else 0
            if loop_end <= loop_start:
                loop_end = 0
        else:
            loop_start = 0
            loop_end = 0

        max_samples = int(duration_sec * self.sample_rate)

        if (
            loop_enabled
            and loop_end > loop_start
            and float(getattr(self.config, "loop_crossfade_ms", 0.0) or 0.0) > 0.0
        ):
            key = (
                int(lower_idx),
                int(offset_samples),
                int(loop_start),
                int(loop_end),
                int(round(float(self.config.loop_crossfade_ms))),
            )
            lock = getattr(self, "_loop_cache_lock", None)
            if lock is None:
                lock = self._cache_lock
            with lock:
                smoothed = self._loop_smooth_cache.get(key)
                if smoothed is None:
                    smoothed, ls, le = self._apply_loop_crossfade(
                        np.asarray(raw_trimmed, dtype=np.float32),
                        loop_start=loop_start,
                        loop_end=loop_end,
                        crossfade_ms=float(self.config.loop_crossfade_ms),
                    )
                    self._loop_smooth_cache[key] = smoothed
                    try:
                        self._loop_smooth_cache.move_to_end(key)
                    except Exception:
                        pass
                    # Evict oldest entries to keep memory bounded.
                    maxsize = int(getattr(self, "_LOOP_SMOOTH_CACHE_MAXSIZE", 128) or 128)
                    while len(self._loop_smooth_cache) > maxsize:
                        try:
                            self._loop_smooth_cache.popitem(last=False)
                        except Exception:
                            break
                    raw_trimmed = smoothed
                    loop_start, loop_end = int(ls), int(le)
                else:
                    raw_trimmed = smoothed
                    try:
                        self._loop_smooth_cache.move_to_end(key)
                    except Exception:
                        pass

        shimmer = bool(getattr(self.config, "shimmer_enabled", False))
        if loop_enabled and shimmer and loop_end > loop_start:
            audio = self._granular_shimmer_read(
                raw_trimmed,
                step=float(step),
                loop_start=int(loop_start),
                loop_end=int(loop_end),
                max_samples=int(max_samples),
                grain_ms=float(getattr(self.config, "shimmer_grain_ms", 220.0) or 220.0),
                overlap=float(getattr(self.config, "shimmer_overlap", 0.75) or 0.75),
                looplet_ms=float(getattr(self.config, "shimmer_looplet_ms", 800.0) or 800.0),
                drift_seconds=float(getattr(self.config, "shimmer_drift_seconds", 4.0) or 4.0),
                reseed_seconds=float(getattr(self.config, "shimmer_reseed_seconds", 24.0) or 24.0),
                spray_ms=float(getattr(self.config, "shimmer_spray_ms", 20.0) or 20.0),
                pan_spread=float(getattr(self.config, "shimmer_pan_spread", 0.12) or 0.12),
                time_jitter=float(getattr(self.config, "shimmer_time_jitter", 0.0) or 0.0),
            )
        else:
            audio = self._variable_rate_read(raw_trimmed, step, loop_start, loop_end, max_samples)

        if upper != lower and getattr(self, "_raw_cache", None):
            upper_idx = self._layer_index(upper)
            raw_up = self._raw_cache[upper_idx]
            offset_up = int(getattr(upper, "start_offset", 0.0) * self.sample_rate)
            if offset_up < len(raw_up):
                raw_up_trimmed = raw_up[offset_up:]
                step_up = self._pitch_ratio(int(midi), int(getattr(upper, "root_midi", 60)))
                if loop_enabled:
                    loop_start_up = max(0, int(getattr(upper, "loop_start", 0)) - offset_up)
                    loop_end_up = (
                        int(getattr(upper, "loop_end", 0)) - offset_up
                        if int(getattr(upper, "loop_end", 0) or 0) > 0
                        else 0
                    )
                    if loop_end_up <= loop_start_up:
                        loop_end_up = 0
                else:
                    loop_start_up = 0
                    loop_end_up = 0
                audio_up = self._variable_rate_read(
                    raw_up_trimmed, step_up, loop_start_up, loop_end_up, max_samples
                )
                min_len = min(len(audio), len(audio_up))
                audio[:min_len] = audio[:min_len] * float(w_low) + audio_up[:min_len] * float(w_up)
                if len(audio_up) > len(audio):
                    audio = np.concatenate([audio, audio_up[len(audio) :] * float(w_up)])

        if getattr(self, "attack_fade_samples", 0) > 0 and len(audio) > int(
            self.attack_fade_samples
        ):
            n = int(self.attack_fade_samples)
            # Cache attack fade envelope by length (exact DSP).
            with self._env_cache_lock:
                fade_in = self._env_cache.get(("attack_fade", int(n)))
                if fade_in is None:
                    fade_in = np.linspace(0.0, 1.0, n, dtype=np.float32)
                    self._env_cache[("attack_fade", int(n))] = fade_in
            audio[:n] *= fade_in[:, np.newaxis]

        edge_min = int(getattr(self, "_edge_fade_min_samples", 0) or 0)
        if edge_min > 0 and len(audio) > 8:
            n_edge = min(edge_min, max(0, int(len(audio) // 8)))
            if n_edge > 0:
                audio = apply_fade_in_out(audio, n_edge)

        # Fixed low-pass (2-pole / ~12dB/oct) for gentle top cut.
        try:
            ba = getattr(self, "_fixed_lpf_ba", None)
            if ba is not None:
                b, a = ba
                import scipy.signal

                x = np.asarray(audio, dtype=np.float32)
                if x.ndim == 1:
                    audio = scipy.signal.lfilter(b, a, x).astype(np.float32)
                else:
                    y = np.empty_like(x)
                    for ch_i in range(x.shape[1]):
                        y[:, ch_i] = scipy.signal.lfilter(b, a, x[:, ch_i]).astype(np.float32)
                    audio = y
        except Exception:
            pass

        if getattr(self, "use_pitch_filter", False) and getattr(lower, "pitch_tracking", False):
            fs = getattr(lower, "filter_settings", None) or {}
            hm = float(
                fs.get("harmonic_multiplier", getattr(self.config, "lowpass_harmonic_multiplier", 4.0))
            )
            mn = float(fs.get("min_cutoff", getattr(self.config, "lowpass_min_cutoff", 200.0)))
            mx = float(fs.get("max_cutoff", getattr(self.config, "lowpass_max_cutoff", 8000.0)))
            q = float(fs.get("q", getattr(self.config, "filter_q", 0.707)))
            drive = float(fs.get("drive", getattr(self.config, "filter_drive", 0.0)))
            v2c = float(fs.get("vel_to_cutoff", getattr(self.config, "vel_to_cutoff", 0.0)))
            model = str(fs.get("model", getattr(self.config, "filter_model", "butter"))).lower()

            # Bass safety clamp to avoid "buzzy" sub lows and save headroom.
            if getattr(self, "name", "") == "bass":
                mx = min(mx, 750.0)
                v2c = 0.0

            if model in {"biquad", "svf"} and getattr(self, "_biquad_lpf", None) is not None:
                audio = self._biquad_lpf.apply(
                    audio,
                    midi_note=int(midi),
                    velocity=int(velocity),
                    harmonic_multiplier=hm,
                    min_cutoff=mn,
                    max_cutoff=mx,
                    q=q,
                    vel_to_cutoff=v2c,
                    drive=drive,
                )
            elif getattr(self, "pitch_filter", None) is not None:
                self.pitch_filter.reset_state()
                audio = self.pitch_filter.apply(
                    audio, midi, harmonic_multiplier=hm, min_cutoff=mn, max_cutoff=mx
                )
        if getattr(self, "_pitch_filter_enabled", False):
            audio = self._apply_pitch_filter(audio, midi)

        # Optional per-note low-pass filter envelope (sampler "prettiness").
        # This runs after keytracking/fixed LPF so it reads as an articulation gesture.
        try:
            cfg = getattr(self, "config", None)
            env_on = bool(getattr(cfg, "filter_envelope_enabled", False)) if cfg is not None else False
            disable = bool(getattr(cfg, "disable_filter", False)) if cfg is not None else False
        except Exception:
            env_on = False
            disable = False
        if env_on and not disable and len(audio) > 0:
            try:
                from .pitch_filter import DynamicLowPass

                atk = float(getattr(cfg, "filter_attack", 0.01) or 0.01)
                dec = float(getattr(cfg, "filter_decay", 0.1) or 0.1)
                sus = float(getattr(cfg, "filter_sustain", 0.7) or 0.7)
                rel = float(getattr(cfg, "filter_release", 0.2) or 0.2)
                base = float(getattr(cfg, "filter_base_cutoff", 2000.0) or 2000.0)
                peak = float(getattr(cfg, "filter_peak_cutoff", 8000.0) or 8000.0)
                curve = str(getattr(cfg, "filter_env_curve", "linear") or "linear").strip().lower()
                sus = float(max(0.0, min(1.0, sus)))
                nyq = float(self.sample_rate) / 2.0
                base = float(max(20.0, min(base, nyq - 1.0)))
                peak = float(max(20.0, min(peak, nyq - 1.0)))
                if peak < base:
                    base, peak = peak, base

                n = int(len(audio))
                sr = float(self.sample_rate)
                a = max(0, int(round(atk * sr)))
                d = max(0, int(round(dec * sr)))
                r = max(0, int(round(rel * sr)))
                a = min(a, n)
                d = min(d, max(0, n - a))
                r = min(r, max(0, n - a - d))
                s_len = max(0, n - a - d - r)

                env = np.empty(n, dtype=np.float32)
                idx = 0
                if a > 0:
                    env[idx : idx + a] = np.linspace(0.0, 1.0, a, dtype=np.float32, endpoint=False)
                    idx += a
                if d > 0:
                    env[idx : idx + d] = np.linspace(1.0, sus, d, dtype=np.float32, endpoint=False)
                    idx += d
                if s_len > 0:
                    env[idx : idx + s_len] = np.float32(sus)
                    idx += s_len
                if r > 0:
                    env[idx : idx + r] = np.linspace(sus, 0.0, r, dtype=np.float32, endpoint=True)
                    idx += r
                if idx < n:
                    env[idx:] = np.float32(0.0)

                if curve in {"exp", "exponential"}:
                    env = np.power(env, 2.0, dtype=np.float32)

                cutoff = (np.float32(base) + env * np.float32(peak - base)).astype(np.float32, copy=False)
                dlp = DynamicLowPass(sample_rate=int(self.sample_rate))
                audio = dlp.process(np.asarray(audio, dtype=np.float32), cutoff)
            except Exception:
                pass

        # dc_block() is timed via render_note() profiling, but the work happens here.
        # DC-blocking is applied once per bar on the master bus (`audio/RT_player/renderer.py`)
        # to avoid re-filtering every single note render.

        return audio.astype(np.float32)

    def _render_layer_glide(
        self,
        *,
        midi_from: int,
        midi_to: int,
        velocity: int,
        glide_sec: float,
        duration_sec: float,
        release_after: Optional[float],
        lower,
        upper,
        w_low: float,
        w_up: float,
    ) -> np.ndarray:
        """Render a note with an initial pitch glide (classic sampler behavior)."""
        if not getattr(self, "_raw_cache", None):
            return create_silent_sample(duration_sec, self.sample_rate)

        # Glide is not compatible with shimmer (windowed granular playback).
        if bool(getattr(self.config, "shimmer_enabled", False)):
            return self._render_layer(
                midi=int(midi_to),
                velocity=int(velocity),
                duration_sec=float(duration_sec),
                release_after=release_after,
                lower=lower,
                upper=upper,
                w_low=float(w_low),
                w_up=float(w_up),
            )

        def _render_one(layer) -> np.ndarray:
            layer_idx = self._layer_index(layer)
            raw = self._raw_cache[layer_idx]
            offset_samples = int(getattr(layer, "start_offset", 0.0) * self.sample_rate)
            sj_ms = float(getattr(self.config, "start_jitter_ms", 0.0) or 0.0)
            # Keep jitter consistent with normal notes; if enabled, it applies to the whole glide note.
            if sj_ms > 0.0:
                sj = int(round(sj_ms * float(self.sample_rate) / 1000.0))
                if sj > 0:
                    try:
                        offset_samples = max(
                            0, offset_samples + int(self._rng.integers(0, int(sj) + 1))
                        )
                    except Exception:
                        offset_samples = max(0, offset_samples)

            if offset_samples >= len(raw):
                return create_silent_sample(duration_sec, self.sample_rate)
            raw_trimmed = raw[offset_samples:]

            step_from = self._pitch_ratio(int(midi_from), int(getattr(layer, "root_midi", 60)))
            step_to = self._pitch_ratio(int(midi_to), int(getattr(layer, "root_midi", 60)))

            loop_enabled = bool(getattr(self.config, "loop_enabled", False))
            # If random_start_within_loop is enabled, disable it for glide notes because it
            # destroys continuity (the whole point of a glide is continuity).
            if loop_enabled:
                ls_abs = int(getattr(layer, "loop_start", 0) or 0)
                le_abs = int(getattr(layer, "loop_end", 0) or 0)
                if (le_abs <= ls_abs) and bool(getattr(self.config, "loop_whole_sample_if_missing_points", True)):
                    ls_abs, le_abs = 0, int(len(raw))
                loop_start = max(0, int(ls_abs) - int(offset_samples))
                loop_end = int(le_abs) - int(offset_samples) if int(le_abs) > 0 else 0
                if loop_end <= loop_start:
                    loop_end = 0
            else:
                loop_start = 0
                loop_end = 0

            max_samples = int(float(duration_sec) * float(self.sample_rate))
            glide_samples = int(round(max(0.0, float(glide_sec)) * float(self.sample_rate)))
            positions = self._glide_positions(
                step_from=float(step_from),
                step_to=float(step_to),
                glide_samples=int(glide_samples),
                total_samples=int(max_samples),
            )

            # Loop smoothing (same as normal note path) before reading.
            if (
                loop_enabled
                and int(loop_end) > int(loop_start)
                and float(getattr(self.config, "loop_crossfade_ms", 0.0) or 0.0) > 0.0
            ):
                key = (
                    int(layer_idx),
                    int(offset_samples),
                    int(loop_start),
                    int(loop_end),
                    int(round(float(self.config.loop_crossfade_ms))),
                )
                lock = getattr(self, "_loop_cache_lock", None)
                if lock is None:
                    lock = self._cache_lock
                with lock:
                    smoothed = self._loop_smooth_cache.get(key)
                    if smoothed is None:
                        smoothed, ls, le = self._apply_loop_crossfade(
                            np.asarray(raw_trimmed, dtype=np.float32),
                            loop_start=int(loop_start),
                            loop_end=int(loop_end),
                            crossfade_ms=float(self.config.loop_crossfade_ms),
                        )
                        self._loop_smooth_cache[key] = smoothed
                        try:
                            self._loop_smooth_cache.move_to_end(key)
                        except Exception:
                            pass
                        maxsize = int(getattr(self, "_LOOP_SMOOTH_CACHE_MAXSIZE", 128) or 128)
                        while len(self._loop_smooth_cache) > maxsize:
                            try:
                                self._loop_smooth_cache.popitem(last=False)
                            except Exception:
                                break
                        raw_trimmed = smoothed
                        loop_start, loop_end = int(ls), int(le)
                    else:
                        raw_trimmed = smoothed
                        try:
                            self._loop_smooth_cache.move_to_end(key)
                        except Exception:
                            pass

            audio = self._variable_rate_read_positions(
                raw_trimmed,
                positions=positions,
                loop_start=int(loop_start),
                loop_end=int(loop_end),
            )
            return audio

        audio = _render_one(lower)
        if upper != lower and getattr(self, "_raw_cache", None):
            audio_up = _render_one(upper)
            min_len = min(len(audio), len(audio_up))
            if min_len > 0:
                audio[:min_len] = audio[:min_len] * float(w_low) + audio_up[:min_len] * float(w_up)
            if len(audio_up) > len(audio):
                audio = np.concatenate([audio, audio_up[len(audio) :] * float(w_up)])

        # From here on, match the post-steps in _render_layer (fades, filters, env).
        if getattr(self, "attack_fade_samples", 0) > 0 and len(audio) > int(self.attack_fade_samples):
            n = int(self.attack_fade_samples)
            with self._env_cache_lock:
                fade_in = self._env_cache.get(("attack_fade", int(n)))
                if fade_in is None:
                    fade_in = np.linspace(0.0, 1.0, n, dtype=np.float32)
                    self._env_cache[("attack_fade", int(n))] = fade_in
            audio[:n] *= fade_in[:, np.newaxis]

        edge_min = int(getattr(self, "_edge_fade_min_samples", 0) or 0)
        if edge_min > 0 and len(audio) > 8:
            n_edge = min(edge_min, max(0, int(len(audio) // 8)))
            if n_edge > 0:
                audio = apply_fade_in_out(audio, n_edge)

        # Fixed low-pass (2-pole / ~12dB/oct) for gentle top cut.
        try:
            ba = getattr(self, "_fixed_lpf_ba", None)
            if ba is not None:
                b, a = ba
                import scipy.signal

                x = np.asarray(audio, dtype=np.float32)
                if x.ndim == 1:
                    audio = scipy.signal.lfilter(b, a, x).astype(np.float32)
                else:
                    y = np.empty_like(x)
                    for ch_i in range(x.shape[1]):
                        y[:, ch_i] = scipy.signal.lfilter(b, a, x[:, ch_i]).astype(np.float32)
                    audio = y
        except Exception:
            pass

        # Keytracking filter + optional filter envelope: use midi_to as the note identity.
        midi = int(midi_to)
        velocity = int(velocity)

        if getattr(self, "use_pitch_filter", False) and getattr(lower, "pitch_tracking", False):
            fs = getattr(lower, "filter_settings", None) or {}
            hm = float(
                fs.get("harmonic_multiplier", getattr(self.config, "lowpass_harmonic_multiplier", 4.0))
            )
            mn = float(fs.get("min_cutoff", getattr(self.config, "lowpass_min_cutoff", 200.0)))
            mx = float(fs.get("max_cutoff", getattr(self.config, "lowpass_max_cutoff", 8000.0)))
            q = float(fs.get("q", getattr(self.config, "filter_q", 0.707)))
            drive = float(fs.get("drive", getattr(self.config, "filter_drive", 0.0)))
            v2c = float(fs.get("vel_to_cutoff", getattr(self.config, "vel_to_cutoff", 0.0)))
            model = str(fs.get("model", getattr(self.config, "filter_model", "butter"))).lower()

            if getattr(self, "name", "") == "bass":
                mx = min(mx, 750.0)
                v2c = 0.0

            if model in {"biquad", "svf"} and getattr(self, "_biquad_lpf", None) is not None:
                audio = self._biquad_lpf.apply(
                    audio,
                    midi_note=int(midi),
                    velocity=int(velocity),
                    harmonic_multiplier=hm,
                    min_cutoff=mn,
                    max_cutoff=mx,
                    q=q,
                    vel_to_cutoff=v2c,
                    drive=drive,
                )
            elif getattr(self, "pitch_filter", None) is not None:
                self.pitch_filter.reset_state()
                audio = self.pitch_filter.apply(
                    audio, midi, harmonic_multiplier=hm, min_cutoff=mn, max_cutoff=mx
                )
        if getattr(self, "_pitch_filter_enabled", False):
            audio = self._apply_pitch_filter(audio, midi)

        # Optional per-note low-pass filter envelope (sampler "prettiness").
        try:
            cfg = getattr(self, "config", None)
            env_on = bool(getattr(cfg, "filter_envelope_enabled", False)) if cfg is not None else False
            disable = bool(getattr(cfg, "disable_filter", False)) if cfg is not None else False
        except Exception:
            env_on = False
            disable = False
        if env_on and not disable and len(audio) > 0:
            try:
                from .pitch_filter import DynamicLowPass

                atk = float(getattr(cfg, "filter_attack", 0.01) or 0.01)
                dec = float(getattr(cfg, "filter_decay", 0.1) or 0.1)
                sus = float(getattr(cfg, "filter_sustain", 0.7) or 0.7)
                rel = float(getattr(cfg, "filter_release", 0.2) or 0.2)
                base = float(getattr(cfg, "filter_base_cutoff", 2000.0) or 2000.0)
                peak = float(getattr(cfg, "filter_peak_cutoff", 8000.0) or 8000.0)
                curve = str(getattr(cfg, "filter_env_curve", "linear") or "linear").strip().lower()
                sus = float(max(0.0, min(1.0, sus)))
                nyq = float(self.sample_rate) / 2.0
                base = float(max(20.0, min(base, nyq - 1.0)))
                peak = float(max(20.0, min(peak, nyq - 1.0)))
                if peak < base:
                    base, peak = peak, base

                n = int(len(audio))
                sr = float(self.sample_rate)
                a = max(0, int(round(atk * sr)))
                d = max(0, int(round(dec * sr)))
                r = max(0, int(round(rel * sr)))
                a = min(a, n)
                d = min(d, max(0, n - a))
                r = min(r, max(0, n - a - d))
                s_len = max(0, n - a - d - r)

                env = np.empty(n, dtype=np.float32)
                idx = 0
                if a > 0:
                    env[idx : idx + a] = np.linspace(0.0, 1.0, a, dtype=np.float32, endpoint=False)
                    idx += a
                if d > 0:
                    env[idx : idx + d] = np.linspace(1.0, sus, d, dtype=np.float32, endpoint=False)
                    idx += d
                if s_len > 0:
                    env[idx : idx + s_len] = np.float32(sus)
                    idx += s_len
                if r > 0:
                    env[idx : idx + r] = np.linspace(sus, 0.0, r, dtype=np.float32, endpoint=True)
                    idx += r
                if idx < n:
                    env[idx:] = np.float32(0.0)

                if curve in {"exp", "exponential"}:
                    env = np.power(env, 2.0, dtype=np.float32)

                cutoff = (np.float32(base) + env * np.float32(peak - base)).astype(np.float32, copy=False)
                dlp = DynamicLowPass(sample_rate=int(self.sample_rate))
                audio = dlp.process(np.asarray(audio, dtype=np.float32), cutoff)
            except Exception:
                pass

        return audio.astype(np.float32)
