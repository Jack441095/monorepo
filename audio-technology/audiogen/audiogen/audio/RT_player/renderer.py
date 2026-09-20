# audio/RT_player/renderer.py
# ---------------------------------------------------------------------------
# Builds per-channel audio, sums via the mixer (dry + aux sends), then
# feeds MasterBus (reverb/delay/distortion returns + master chain).
# ---------------------------------------------------------------------------
import logging
import time
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple

import numpy as np

from audio.engine.master_bus import MasterBus

from .render_pipeline import RenderPipeline
from utils.startup_profiler import _truthy_env
from sampler.utils import dc_block

logger = logging.getLogger(__name__)

def _db_to_linear(db: float) -> float:
    return 10.0 ** (float(db) / 20.0)


def _linear_to_db(x: float) -> float:
    return 20.0 * float(np.log10(max(1e-12, float(x))))


class _RenderProfiler:
    """Low-overhead rolling profiler for bar rendering."""

    def __init__(self, enabled: bool):
        self.enabled = bool(enabled)
        self._last_log = 0.0
        self.reset()

    def reset(self) -> None:
        self.n_bars = 0
        self.t_total = 0.0
        self.t_mono = 0.0
        self.t_chords = 0.0
        self.t_mix = 0.0
        self.t_master = 0.0
        self.events_total = 0
        self.events_mono = 0
        self.events_chords = 0

    def maybe_log(self, *, now_s: float, tempo: float) -> None:
        if not self.enabled:
            return
        if self.n_bars <= 0:
            return
        if now_s - self._last_log < 5.0:
            return
        self._last_log = now_s
        bars = max(1, int(self.n_bars))
        logger.info(
            "Render profile (avg over %d bars): total=%.1fms mono=%.1fms chords=%.1fms mix=%.1fms master=%.1fms | events=%d (mono=%d chords=%d) | tempo=%.1f",
            bars,
            (self.t_total / bars) * 1000.0,
            (self.t_mono / bars) * 1000.0,
            (self.t_chords / bars) * 1000.0,
            (self.t_mix / bars) * 1000.0,
            (self.t_master / bars) * 1000.0,
            int(self.events_total / bars),
            int(self.events_mono / bars),
            int(self.events_chords / bars),
            float(tempo),
        )

    def record(
        self,
        *,
        t0: float,
        t1: float,
        t2: float,
        t3: float,
        t4: float,
        t5: float,
        t6: float,
        events: List,
        mono_bins: Dict[int, List],
        chord_events: List,
        tempo: float,
    ) -> None:
        if not self.enabled:
            return
        self.n_bars += 1
        self.t_total += t6 - t0
        self.t_mono += t2 - t1
        self.t_chords += t3 - t2
        self.t_mix += t5 - t4
        self.t_master += t6 - t5
        try:
            self.events_total += len(events)
            self.events_chords += len(chord_events)
            self.events_mono += sum(len(v) for v in mono_bins.values())
        except Exception:
            pass
        self.maybe_log(now_s=time.time(), tempo=float(tempo))


class AudioRenderer:
    """
    Renders a bar of audio from a list of events using a synthesis engine and mixer.
    The summed mix is processed by ``MasterBus`` (distortion aux, fader, inserts, limiter).
    """

    def __init__(
        self,
        synthesis_engine,
        mixer,
        sample_rate: int,
        reverb_processor=None,
        master_bus: Optional[MasterBus] = None,
    ):
        self.synthesis_engine = synthesis_engine
        self.mixer = mixer
        self.sample_rate = sample_rate
        self.reverb_processor = reverb_processor
        self.master_bus = master_bus or MasterBus(sample_rate)
        self.render_pipeline = RenderPipeline(self)
        # Per-bar buffer reuse to reduce allocations/GC in the realtime loop.
        # Keyed by bar_samples since tempo can vary.
        self._channel_buffers_by_len: "OrderedDict[int, Dict[int, np.ndarray]]" = OrderedDict()
        self._legacy_aux_zeros_by_len: "OrderedDict[int, Tuple[np.ndarray, np.ndarray]]" = OrderedDict()
        # Cap the number of distinct bar sizes we cache (tempo changes can otherwise grow this without bound).
        try:
            from audiogen_core.config import CONFIG as _CFG2

            _a2 = getattr(_CFG2, "audio", None)
            self._channel_buffer_cache_maxlen = int(getattr(_a2, "rt_channel_buffer_cache_maxlen", 12) or 12)
        except Exception:
            self._channel_buffer_cache_maxlen = 12
        # Enable render profiling via env OR CONFIG.audio.rt_render_profile_enabled.
        cfg_enabled = False
        try:
            from audiogen_core.config import CONFIG

            cfg_enabled = bool(getattr(getattr(CONFIG, "audio", None), "rt_render_profile_enabled", False))
        except Exception:
            cfg_enabled = False
        self._prof = _RenderProfiler(enabled=bool(cfg_enabled) or _truthy_env("AUDIOGEN_RT_PROFILE", False))
        self._dc_block_enabled = _truthy_env("AUDIOGEN_DC_BLOCK_BUS", True)
        self.last_stage_timing_ms = {
            "mono": 0.0,
            "chords": 0.0,
            "mix": 0.0,
            "master": 0.0,
            "total": 0.0,
            "events_total": 0,
            "events_mono": 0,
            "events_chords": 0,
        }
        try:
            from audiogen_core.config import CONFIG as _CFG

            _a = getattr(_CFG, "audio", None)
            self._bar_gain_stabilizer_enabled = bool(getattr(_a, "bar_gain_stabilizer_enabled", False))
            self._bar_gain_target_rms_db = float(getattr(_a, "bar_gain_target_rms_db", -18.0))
            self._bar_gain_max_up_db = float(getattr(_a, "bar_gain_max_up_db", 1.5))
            self._bar_gain_max_down_db = float(getattr(_a, "bar_gain_max_down_db", 2.5))
            self._sync_prefetch_enabled = bool(getattr(_a, "rt_render_sync_prefetch_enabled", False))
            self._reuse_master_bufs = bool(getattr(_a, "rt_master_reuse_stem_buffer", True))
            self._chorus_kick_sidechain_cfg = getattr(_a, "chorus_kick_sidechain", None)
        except Exception:
            self._bar_gain_stabilizer_enabled = False
            self._bar_gain_target_rms_db = -18.0
            self._bar_gain_max_up_db = 1.5
            self._bar_gain_max_down_db = 2.5
            self._sync_prefetch_enabled = False
            self._reuse_master_bufs = True
            self._chorus_kick_sidechain_cfg = None
        try:
            from audio.engine.chorus_kick_sidechain import (
                apply_chorus_kick_sidechain,
                should_apply_chorus_kick_sidechain,
            )

            self._apply_chorus_kick_sidechain = apply_chorus_kick_sidechain
            self._should_apply_chorus_kick_sidechain = should_apply_chorus_kick_sidechain
        except Exception:
            self._apply_chorus_kick_sidechain = None
            self._should_apply_chorus_kick_sidechain = None

    def _apply_bar_gain_stabilizer(self, audio: np.ndarray) -> np.ndarray:
        """
        Gentle per-bar loudness stabilizer (post-master).
        Clamped to avoid pumping; uses RMS and a small window.
        """
        if not self._bar_gain_stabilizer_enabled:
            return audio
        if audio is None or getattr(audio, "size", 0) <= 0:
            return audio

        n = int(audio.shape[0])
        if n <= 256:
            seg = audio
        else:
            a0 = int(n * 0.20)
            a1 = int(n * 0.85)
            seg = audio[a0:a1]
        rms = float(np.sqrt(np.mean(seg * seg) + 1e-12))
        cur_db = _linear_to_db(rms)
        delta_db = float(self._bar_gain_target_rms_db) - float(cur_db)
        delta_db = float(
            np.clip(delta_db, -abs(float(self._bar_gain_max_down_db)), abs(float(self._bar_gain_max_up_db)))
        )
        if abs(delta_db) < 1e-3:
            return audio
        g = np.float32(_db_to_linear(delta_db))
        out = audio.astype(np.float32, copy=True)
        out *= g
        return out

    @staticmethod
    def _events_are_sorted(events: List[Tuple]) -> bool:
        if not events or len(events) <= 1:
            return True
        try:
            prev = float(events[0][3])
        except Exception:
            return False
        for i in range(1, len(events)):
            try:
                cur = float(events[i][3])
            except Exception:
                return False
            if cur + 1e-12 < prev:
                return False
            prev = cur
        return True

    def _get_channel_buffers(self, bar_samples: int) -> Dict[int, np.ndarray]:
        bs = int(max(0, bar_samples))
        cached = self._channel_buffers_by_len.get(bs)
        if cached is None:
            cached = self.render_pipeline.create_channel_buffers(bs)
            self._channel_buffers_by_len[bs] = cached
            # Evict oldest cached sizes if we exceed the cap.
            try:
                cap = int(getattr(self, "_channel_buffer_cache_maxlen", 12) or 12)
            except Exception:
                cap = 12
            cap = max(2, min(64, cap))
            while len(self._channel_buffers_by_len) > cap:
                try:
                    self._channel_buffers_by_len.popitem(last=False)
                except Exception:
                    break
        else:
            # Refresh LRU order.
            try:
                self._channel_buffers_by_len.move_to_end(bs, last=True)
            except Exception:
                pass
        # Zero in-place to reuse.
        for a in cached.values():
            a.fill(0.0)
        return cached

    def _get_legacy_aux_zeros(self, bar_samples: int) -> Tuple[np.ndarray, np.ndarray]:
        bs = int(max(0, bar_samples))
        cached = self._legacy_aux_zeros_by_len.get(bs)
        if cached is None:
            cached = (
                np.zeros((bs, 2), dtype=np.float32),
                np.zeros((bs, 2), dtype=np.float32),
            )
            self._legacy_aux_zeros_by_len[bs] = cached
            try:
                cap = int(getattr(self, "_channel_buffer_cache_maxlen", 12) or 12)
            except Exception:
                cap = 12
            cap = max(2, min(64, cap))
            while len(self._legacy_aux_zeros_by_len) > cap:
                try:
                    self._legacy_aux_zeros_by_len.popitem(last=False)
                except Exception:
                    break
        else:
            try:
                self._legacy_aux_zeros_by_len.move_to_end(bs, last=True)
            except Exception:
                pass
        dly, dist = cached
        dly.fill(0.0)
        dist.fill(0.0)
        return dly, dist

    def render_bar(
        self,
        events: List[Tuple],
        tempo: float,
        bar_samples: int,
        drone: Optional[np.ndarray] = None,
        velocity_multiplier: float = 1.0,
        *,
        fast_master: bool = False,
        skip_master_inserts: bool = False,
        skip_multiband: bool = False,
        skip_master_eq: bool = False,
        fx_return_scale: float = 1.0,
        reverb_quality_tier: str = "high",
        arrangement_role: str = "",
        stem_sink: Optional[Dict[int, List[np.ndarray]]] = None,
    ) -> np.ndarray:
        """
        Render one bar of audio from the given events.

        Args:
            events: list of (channel, midi, velocity, start_beats, duration_beats, notes)
            tempo: beats per minute
            bar_samples: number of samples in this bar (derived from tempo)
            drone: optional pre‑rendered stereo drone slice (length bar_samples)
            velocity_multiplier: overall velocity scaling factor (e.g. from emotion)
            stem_sink: optional dict to append a copy of each fully-processed
                per-channel buffer into (keyed by mixer channel index, see
                core.mixer_config.CHANNEL_NAMES), captured just before the
                mixer sums channels down. None (default) skips this entirely
                with no effect on the returned mix.

        Returns:
            stereo float32 audio array of length bar_samples
        """
        prof = self._prof.enabled
        t0 = time.perf_counter()
        channel_audio = self._get_channel_buffers(bar_samples)

        events_sorted = self._events_are_sorted(events)
        if not events_sorted:
            events.sort(key=lambda x: x[3])
            events_sorted = True
        mono_bins, chord_events = self.render_pipeline.partition_mono_chord_events(events)
        if chord_events and bool(getattr(self, "_sync_prefetch_enabled", False)):
            try:
                self.synthesis_engine.prefetch_events(
                    chord_events,
                    tempo=float(tempo),
                    default_velocity=80,
                )
            except Exception:
                pass
        t1 = time.perf_counter()
        self.render_pipeline.render_monophonic_channels(
            mono_bins, tempo, bar_samples, channel_audio, events_sorted=events_sorted
        )
        t2 = time.perf_counter()
        self.render_pipeline.render_polyphonic_events(chord_events, tempo, bar_samples, channel_audio)
        t3 = time.perf_counter()
        self.render_pipeline.apply_drone_and_velocity(
            channel_audio, drone, bar_samples, velocity_multiplier
        )
        _sc = getattr(self, "_chorus_kick_sidechain_cfg", None)
        _should_sidechain = getattr(self, "_should_apply_chorus_kick_sidechain", None)
        _apply_sidechain = getattr(self, "_apply_chorus_kick_sidechain", None)
        if _sc is not None and _should_sidechain is not None and _apply_sidechain is not None:
            try:
                if _should_sidechain(
                    arrangement_role=str(arrangement_role or ""),
                    sidechain_cfg=_sc,
                ):
                    _apply_sidechain(
                        channel_audio,
                        sample_rate=int(self.sample_rate),
                        bar_samples=int(bar_samples),
                        sidechain_cfg=_sc,
                    )
            except Exception:
                logger.debug(
                    "chorus kick sidechain failed for role=%s",
                    str(arrangement_role or ""),
                    exc_info=True,
                )
        t4 = time.perf_counter()
        if stem_sink is not None:
            for ch, buf in channel_audio.items():
                stem_sink.setdefault(ch, []).append(buf.copy())
        out = self.mixer.mix_audio(channel_audio)
        # Backwards-compatible: older mixers returned (dry, reverb_send) only.
        if isinstance(out, tuple) and len(out) == 2:
            dry, reverb_send = out
            delay_send, distortion_send = self._get_legacy_aux_zeros(len(dry))
        else:
            dry, reverb_send, delay_send, distortion_send = out
        t5 = time.perf_counter()
        audio = self.master_bus.process(
            dry,
            reverb_send,
            delay_send,
            distortion_send,
            reverb_processor=self.reverb_processor,
            fast_path=bool(fast_master),
            skip_inserts=bool(skip_master_inserts),
            skip_multiband=bool(skip_multiband),
            skip_master_eq=bool(skip_master_eq),
            fx_return_scale=float(fx_return_scale),
            reverb_quality_tier=str(reverb_quality_tier or "high"),
            realtime=True,
            reuse_rt_buffers=bool(getattr(self, "_reuse_master_bufs", True)),
        )
        audio = self._apply_bar_gain_stabilizer(audio)
        t6 = time.perf_counter()

        try:
            self.last_stage_timing_ms = {
                "mono": float(max(0.0, t2 - t1) * 1000.0),
                "chords": float(max(0.0, t3 - t2) * 1000.0),
                "mix": float(max(0.0, t5 - t4) * 1000.0),
                "master": float(max(0.0, t6 - t5) * 1000.0),
                "total": float(max(0.0, t6 - t0) * 1000.0),
                "events_total": int(len(events or [])),
                "events_mono": int(sum(len(v) for v in mono_bins.values())),
                "events_chords": int(len(chord_events or [])),
            }
        except Exception:
            pass

        if prof:
            self._prof.record(
                t0=t0,
                t1=t1,
                t2=t2,
                t3=t3,
                t4=t4,
                t5=t5,
                t6=t6,
                events=events,
                mono_bins=mono_bins,
                chord_events=chord_events,
                tempo=float(tempo),
            )

        audio = audio.astype(np.float32)
        if self._dc_block_enabled:
            audio = dc_block(audio, sample_rate=int(self.sample_rate), cutoff_hz=20.0)
        return audio
