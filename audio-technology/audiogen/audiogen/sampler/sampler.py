# sampler/sampler.py
"""
Public entry point for the sampler package's core `Sampler` class.

P4 giant-file decomposition (1,950 lines -> sampler.py + 5 sibling files): the numba kernels and the
`VelocityLayer` dataclass are pure leaf helpers (`sampler_kernels.py`,
`sampler_types.py`); layer-selection/routing, resampling/pitch-tracking DSP,
and the per-note render pipeline are mixed in from `sampler_layers.py`,
`sampler_resample.py`, and `sampler_render.py` respectively. This file keeps
the original filename/module path (`sampler.sampler`) as the public surface --
`Sampler` and `VelocityLayer` are importable from here exactly as before
(`from sampler.sampler import Sampler, VelocityLayer`), and `__init__`,
`render_note`, `render_glide_note`, `_get_adsr_envelope`, and
`_profile_maybe_log` (the top of the internal call graph, tying every layer
together) stay defined directly on this class. All method bodies below were
moved/kept via precise line-range extraction -- no behavior changes.
"""
import logging
from typing import Dict, List, Optional, Tuple
from collections import OrderedDict
import threading

import numpy as np

from audiogen_core.config import SamplerConfiguration, QualityMode
from midi.velocity_mapper import VELOCITY_MAPPER
from utils.startup_profiler import _truthy_env

from .adsr import ADSREnvelope
from .sample_loader import SampleLoader
from .utils import apply_fade_out, create_silent_sample

from .sampler_kernels import _db_to_linear, _have_numba

# Re-export the numba kernels (only defined in sampler_kernels when numba is
# importable, exactly as the original single-file module conditionally defined
# them) so `from sampler.sampler import _one_pole_filter_nb_mono, ...`
# (studio/audiogen/audiogen/utils/numba_warmup.py) keeps working unchanged.
# Guarded the same way the original module guarded these definitions -- if numba
# is unavailable, these names simply do not exist here either, matching the
# pre-split behavior exactly (callers already catch the resulting ImportError).
if _have_numba():
    from .sampler_kernels import (  # noqa: F401 -- conditional compatibility re-exports
        _one_pole_filter_nb_mono,
        _one_pole_filter_nb_stereo,
        _variable_rate_read_nb,
        _variable_rate_read_hq_nb,
        _variable_rate_read_positions_nb,
        _variable_rate_read_positions_hq_nb,
    )
from .sampler_types import VelocityLayer
from .sampler_layers import _LayerRoutingMixin
from .sampler_resample import _ResamplingMixin
from .sampler_render import _RenderMixin

logger = logging.getLogger(__name__)


class Sampler(_RenderMixin, _ResamplingMixin, _LayerRoutingMixin):
    """
    Classic hardware sampler: pitch = speed, loop points in original sample,
    linear interpolation, no warping, no time‑stretching.
    """

    def __init__(self, sampler_config: SamplerConfiguration, sample_rate: int = 44100, global_config=None):
        self.config = sampler_config
        self.name = sampler_config.name
        self.sample_rate = sample_rate
        self._global_config = global_config
        self._rng = self._build_rng()

        # ADSR (global, can be overridden per layer)
        self.adsr_attack = sampler_config.adsr_attack
        self.adsr_decay = sampler_config.adsr_decay
        self.adsr_sustain = sampler_config.adsr_sustain
        self.adsr_release = sampler_config.adsr_release
        self.envelope_curve = getattr(sampler_config, "envelope_curve", "linear")

        # Velocity crossfade (can be disabled for CPU)
        self.use_velocity_crossfade = sampler_config.use_velocity_crossfade

        # Optional pitch‑tracking filter (simple Butterworth)
        self.use_pitch_filter = sampler_config.use_pitch_tracking_lowpass
        if self.use_pitch_filter:
            from .pitch_filter import PitchTrackingFilter
            from .biquad import KeyTrackedBiquadLPF

            self.pitch_filter = PitchTrackingFilter(
                sample_rate=sample_rate, order=getattr(sampler_config, "filter_order", 2)
            )
            self._biquad_lpf = KeyTrackedBiquadLPF(sample_rate=sample_rate)
        else:
            self.pitch_filter = None
            self._biquad_lpf = None

        # Optional fixed low-pass (2-pole biquad) for simple top-cut (ex: chords).
        self._fixed_lpf_ba = None
        try:
            hz = float(getattr(sampler_config, "fixed_lowpass_hz", 0.0) or 0.0)
            q = float(getattr(sampler_config, "fixed_lowpass_q", 0.707) or 0.707)
        except Exception:
            hz = 0.0
            q = 0.707
        if hz and hz > 0.0:
            try:
                from .biquad import _rbj_lowpass

                self._fixed_lpf_ba = _rbj_lowpass(float(hz), float(q), int(sample_rate))
            except Exception:
                self._fixed_lpf_ba = None

        # Attack fade (small fade to avoid clicks, can be set to 0)
        self.attack_fade_samples = int(
            getattr(sampler_config, "attack_fade_ms", 0.0) * sample_rate / 1000.0
        )

        self.quality_mode = getattr(sampler_config, "quality_mode", QualityMode.MEDIUM)
        self.transposition_quality_mode = str(
            getattr(sampler_config, "transposition_quality_mode", "fast") or "fast"
        ).strip().lower()
        self._pitch_ratio_lut_center = 128
        self._pitch_ratio_lut = np.power(
            2.0, (np.arange(-128, 129, dtype=np.float32) / 12.0)
        ).astype(np.float32, copy=False)
        self._edge_fade_min_samples = max(
            0,
            int(
                float(getattr(sampler_config, "edge_fade_min_ms", 1.2) or 1.2)
                * float(sample_rate)
                / 1000.0
            ),
        )

        self._profile_enabled = _truthy_env("AUDIOGEN_SAMPLER_PROFILE", False)
        self._profile_last_log = 0.0
        self._profile_note_calls = 0
        self._profile_cache_hits = 0
        self._profile_cache_misses = 0
        self._profile_t_render_layer = 0.0
        self._profile_t_adsr = 0.0
        self._profile_t_dcblock = 0.0

        # Render cache (note -> audio). Tests may construct via __new__ and set these manually.
        self._cache_lock = threading.Lock()
        self._note_cache: "OrderedDict[Tuple, np.ndarray]" = OrderedDict()
        self.NOTE_CACHE_MAXSIZE = int(getattr(sampler_config, "note_cache_maxsize", 64) or 64)

        # Load samples
        self.layers: List[VelocityLayer] = []
        self._raw_cache: List[np.ndarray] = []  # index matches layers
        self._build_layers(sampler_config)

        # Load raw audio for each layer
        loader = SampleLoader(
            sample_rate=sample_rate,
            logger=logger,
            librosa_module=None,  # avoid librosa dependency, use scipy.io.wavfile
            pre_gain_db=getattr(sampler_config, "pre_gain_db", 0.0),
            post_gain_db=getattr(sampler_config, "post_gain_db", 0.0),
            db_to_linear=_db_to_linear,
            normalizer_config=getattr(getattr(self._global_config, "audio", None), "__dict__", None),
            source_dc_enabled=bool(getattr(sampler_config, "dc_block_enabled", True)),
            source_dc_cutoff_hz=float(getattr(sampler_config, "dc_block_cutoff_hz", 12.0) or 12.0),
        )
        for layer in self.layers:
            raw = loader.load_sample(layer.file_path)
            self._raw_cache.append(raw)

        # Cache for loop-smoothed sources (Ableton Simpler-like loop crossfade).
        self._loop_smooth_cache: "OrderedDict[Tuple[int, int, int, int, int], np.ndarray]" = OrderedDict()
        self._loop_cache_lock = threading.Lock()
        # Keep this bounded: offsets/jitter can otherwise create unbounded keys.
        try:
            self._LOOP_SMOOTH_CACHE_MAXSIZE = int(
                getattr(sampler_config, "loop_smooth_cache_maxsize", 128) or 128
            )
        except Exception:
            self._LOOP_SMOOTH_CACHE_MAXSIZE = 128
        self._LOOP_SMOOTH_CACHE_MAXSIZE = int(max(8, min(4096, self._LOOP_SMOOTH_CACHE_MAXSIZE)))

        # Small envelope cache for fades/crossfades (reduces allocs in hot paths).
        self._env_cache_lock = threading.Lock()
        self._env_cache: Dict[Tuple[str, int], np.ndarray] = {}

        # ADSR cache: avoids per-note object allocations.
        self._adsr_cache_lock = threading.Lock()
        self._adsr_cache: "OrderedDict[Tuple, ADSREnvelope]" = OrderedDict()
        self._ADSR_CACHE_MAXSIZE = int(getattr(sampler_config, "adsr_cache_maxsize", 32) or 32)

        self._rebuild_layer_route_cache()

        logger.info(
            f"Sampler '{self.name}' initialized (classic mode) – layers: {len(self.layers)}"
        )

    def render_glide_note(
        self,
        midi_from: int,
        midi_to: int,
        velocity: int,
        glide_sec: float,
        duration_sec: float,
        release_after: Optional[float] = None,
    ) -> np.ndarray:
        """
        Render a single monophonic note that glides from `midi_from` to `midi_to`.

        Intended for short legato slides (~20ms) in generated melodies/arps.
        """
        if not getattr(self, "layers", None):
            return create_silent_sample(duration_sec, getattr(self, "sample_rate", 44100))

        lower, upper, w_low, w_up = self._select_layers_for_velocity(int(velocity))
        if lower is None:
            return create_silent_sample(duration_sec, getattr(self, "sample_rate", 44100))

        audio = self._render_layer_glide(
            midi_from=int(midi_from),
            midi_to=int(midi_to),
            velocity=int(velocity),
            glide_sec=float(glide_sec),
            duration_sec=float(duration_sec),
            release_after=release_after,
            lower=lower,
            upper=upper,
            w_low=float(w_low),
            w_up=float(w_up),
        )

        attack = getattr(lower, "adsr_attack", None)
        decay = getattr(lower, "adsr_decay", None)
        sustain = getattr(lower, "adsr_sustain", None)
        release = getattr(lower, "adsr_release", None)
        attack = self.adsr_attack if attack is None else attack
        decay = self.adsr_decay if decay is None else decay
        sustain = self.adsr_sustain if sustain is None else sustain
        release = self.adsr_release if release is None else release
        curve = getattr(lower, "envelope_curve", None) or getattr(self, "envelope_curve", "linear")

        adsr = self._get_adsr_envelope(
            attack=float(attack),
            decay=float(decay),
            sustain=float(sustain),
            release=float(release),
            curve=str(curve),
            sample_rate=int(getattr(self, "sample_rate", 44100)),
        )
        release_sample = (
            None
            if release_after is None
            else int(float(release_after) * float(getattr(self, "sample_rate", 44100)))
        )
        audio = adsr.apply(audio, release_after=release_sample)

        amp_mapped = float(
            VELOCITY_MAPPER.get_parameters(getattr(self, "name", "melody"), int(velocity))["amplitude"]
        )
        try:
            strength = float(getattr(self.config, "velocity_amplitude_strength", 1.0))
        except Exception:
            strength = 1.0
        strength = float(np.clip(strength, 0.0, 1.0))
        amp = 1.0 + strength * (amp_mapped - 1.0)
        try:
            a_min = getattr(self.config, "velocity_amplitude_min", None)
            a_max = getattr(self.config, "velocity_amplitude_max", None)
            if a_min is not None:
                amp = max(float(a_min), float(amp))
            if a_max is not None:
                amp = min(float(a_max), float(amp))
        except Exception:
            pass
        audio = (audio * float(amp)).astype(np.float32, copy=False)
        try:
            samp_db = float(getattr(self.config, "amplitude_db", 0.0) or 0.0)
        except Exception:
            samp_db = 0.0
        if abs(float(samp_db)) > 1e-6:
            audio = (audio * _db_to_linear(float(samp_db))).astype(np.float32, copy=False)
        try:
            legacy_amp = float(getattr(self.config, "amplitude", 1.0) or 1.0)
        except Exception:
            legacy_amp = 1.0
        if abs(legacy_amp - 1.0) > 1e-6:
            audio = (audio * float(legacy_amp)).astype(np.float32, copy=False)

        if release_after is None:
            fade_out = min(512, len(audio) // 8)
            if fade_out > 0:
                audio = apply_fade_out(audio, fade_out)

        return audio

    def render_note(
        self,
        midi: int,
        velocity: int,
        duration_sec: float,
        release_after: Optional[float] = None,
    ) -> np.ndarray:
        """Render a single note, with LRU cache and Simpler-like loop smoothing."""
        if not getattr(self, "layers", None):
            return create_silent_sample(duration_sec, getattr(self, "sample_rate", 44100))

        import time

        # Amortize: duration values come from beats→seconds and can carry floating noise.
        # Rounding keeps cache hits high without audible impact at these precisions.
        dur = round(float(duration_sec), 4)
        rel = None if release_after is None else round(float(release_after), 4)
        cache_key = (int(midi), int(velocity), dur, rel, self._transposition_mode_cache_token())
        # If we randomize the sample start point, caching would defeat the purpose (identical
        # audio returned every time). Disable note cache in that mode.
        cfg = getattr(self, "config", None)
        cache_allowed = not (
            bool(getattr(cfg, "random_start_within_loop", False))
            or bool(getattr(cfg, "shimmer_enabled", False))
        )
        lock = getattr(self, "_cache_lock", None)
        if cache_allowed and lock is not None:
            with lock:
                cached = getattr(self, "_note_cache", {}).get(cache_key)
                if cached is not None:
                    try:
                        self._note_cache.move_to_end(cache_key)
                    except Exception:
                        pass
                    if getattr(self, "_profile_enabled", False):
                        self._profile_note_calls += 1
                        self._profile_cache_hits += 1
                        self._profile_maybe_log(time.time())
                    return cached

        lower, upper, w_low, w_up = self._select_layers_for_velocity(int(velocity))
        if lower is None:
            return create_silent_sample(duration_sec, getattr(self, "sample_rate", 44100))

        t0 = time.perf_counter() if getattr(self, "_profile_enabled", False) else 0.0
        audio = self._render_layer(
            midi=int(midi),
            velocity=int(velocity),
            duration_sec=float(duration_sec),
            release_after=release_after,
            lower=lower,
            upper=upper,
            w_low=float(w_low),
            w_up=float(w_up),
        )
        t1 = time.perf_counter() if getattr(self, "_profile_enabled", False) else 0.0

        attack = getattr(lower, "adsr_attack", None)
        decay = getattr(lower, "adsr_decay", None)
        sustain = getattr(lower, "adsr_sustain", None)
        release = getattr(lower, "adsr_release", None)
        attack = self.adsr_attack if attack is None else attack
        decay = self.adsr_decay if decay is None else decay
        sustain = self.adsr_sustain if sustain is None else sustain
        release = self.adsr_release if release is None else release
        curve = getattr(lower, "envelope_curve", None) or getattr(self, "envelope_curve", "linear")

        adsr = self._get_adsr_envelope(
            attack=float(attack),
            decay=float(decay),
            sustain=float(sustain),
            release=float(release),
            curve=str(curve),
            sample_rate=int(getattr(self, "sample_rate", 44100)),
        )
        release_sample = (
            None
            if release_after is None
            else int(float(release_after) * float(getattr(self, "sample_rate", 44100)))
        )
        t2 = time.perf_counter() if getattr(self, "_profile_enabled", False) else 0.0
        audio = adsr.apply(audio, release_after=release_sample)
        t3 = time.perf_counter() if getattr(self, "_profile_enabled", False) else 0.0

        amp_mapped = float(
            VELOCITY_MAPPER.get_parameters(getattr(self, "name", "melody"), int(velocity))["amplitude"]
        )
        try:
            strength = float(getattr(self.config, "velocity_amplitude_strength", 1.0))
        except Exception:
            strength = 1.0
        strength = float(np.clip(strength, 0.0, 1.0))
        amp = 1.0 + strength * (amp_mapped - 1.0)
        try:
            a_min = getattr(self.config, "velocity_amplitude_min", None)
            a_max = getattr(self.config, "velocity_amplitude_max", None)
            if a_min is not None:
                amp = max(float(a_min), float(amp))
            if a_max is not None:
                amp = min(float(a_max), float(amp))
        except Exception:
            pass
        audio = (audio * float(amp)).astype(np.float32, copy=False)
        try:
            samp_db = float(getattr(self.config, "amplitude_db", 0.0) or 0.0)
        except Exception:
            samp_db = 0.0
        if abs(float(samp_db)) > 1e-6:
            audio = (audio * _db_to_linear(float(samp_db))).astype(np.float32, copy=False)
        # Backward compatibility: legacy linear multiplier.
        try:
            legacy_amp = float(getattr(self.config, "amplitude", 1.0) or 1.0)
        except Exception:
            legacy_amp = 1.0
        if abs(legacy_amp - 1.0) > 1e-6:
            audio = (audio * float(legacy_amp)).astype(np.float32, copy=False)

        if release_after is None:
            fade_out = min(512, len(audio) // 8)
            if fade_out > 0:
                audio = apply_fade_out(audio, fade_out)

        if cache_allowed and lock is not None:
            with lock:
                # Cached buffers are treated as immutable. Some render paths apply fades in-place
                # downstream; marking read-only prevents subtle cache corruption and quality drift.
                try:
                    audio.setflags(write=False)
                except Exception:
                    pass
                self._note_cache[cache_key] = audio
                try:
                    self._note_cache.move_to_end(cache_key)
                except Exception:
                    pass
                maxsize = int(getattr(self, "NOTE_CACHE_MAXSIZE", 64) or 64)
                while len(self._note_cache) > maxsize:
                    try:
                        self._note_cache.popitem(last=False)
                    except Exception:
                        break

        if getattr(self, "_profile_enabled", False):
            self._profile_note_calls += 1
            self._profile_cache_misses += 1
            self._profile_t_render_layer += max(0.0, t1 - t0)
            self._profile_t_adsr += max(0.0, t3 - t2)
            self._profile_maybe_log(time.time())

        return audio

    def _get_adsr_envelope(
        self,
        *,
        attack: float,
        decay: float,
        sustain: float,
        release: float,
        curve: str,
        sample_rate: int,
    ) -> ADSREnvelope:
        # Tests may construct Sampler via __new__ (skipping __init__), so lazily
        # initialize ADSR cache fields when missing.
        if not hasattr(self, "_adsr_cache_lock") or not hasattr(self, "_adsr_cache"):
            self._adsr_cache_lock = getattr(self, "_cache_lock", threading.Lock())
            self._adsr_cache = OrderedDict()
        if not hasattr(self, "_ADSR_CACHE_MAXSIZE"):
            self._ADSR_CACHE_MAXSIZE = 32

        # Round the cache key to avoid float noise exploding the cache.
        key = (
            round(float(attack), 5),
            round(float(decay), 5),
            round(float(sustain), 5),
            round(float(release), 5),
            str(curve),
            int(sample_rate),
        )
        with self._adsr_cache_lock:
            cached = self._adsr_cache.get(key)
            if cached is not None:
                try:
                    self._adsr_cache.move_to_end(key)
                except Exception:
                    pass
                return cached
            env = ADSREnvelope(
                float(attack),
                float(decay),
                float(sustain),
                float(release),
                sample_rate=int(sample_rate),
                curve=str(curve),
            )
            self._adsr_cache[key] = env
            try:
                self._adsr_cache.move_to_end(key)
            except Exception:
                pass
            while len(self._adsr_cache) > int(getattr(self, "_ADSR_CACHE_MAXSIZE", 32) or 32):
                try:
                    self._adsr_cache.popitem(last=False)
                except Exception:
                    break
            return env
    def _profile_maybe_log(self, now_s: float) -> None:
        if not getattr(self, "_profile_enabled", False):
            return
        if now_s - float(getattr(self, "_profile_last_log", 0.0) or 0.0) < 5.0:
            return
        self._profile_last_log = float(now_s)
        calls = int(getattr(self, "_profile_note_calls", 0) or 0)
        if calls <= 0:
            return
        hits = int(getattr(self, "_profile_cache_hits", 0) or 0)
        misses = int(getattr(self, "_profile_cache_misses", 0) or 0)
        denom = max(1, calls)
        logger.info(
            "Sampler profile (%s): calls=%d hit=%.1f%% (hits=%d misses=%d) | render_layer=%.2fms adsr=%.2fms",
            getattr(self, "name", "?"),
            calls,
            (hits / denom) * 100.0,
            hits,
            misses,
            (float(getattr(self, "_profile_t_render_layer", 0.0)) / max(1, misses)) * 1000.0,
            (float(getattr(self, "_profile_t_adsr", 0.0)) / max(1, misses)) * 1000.0,
        )
