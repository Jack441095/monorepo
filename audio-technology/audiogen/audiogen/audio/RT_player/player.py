# audio/RT_player/player.py
# ---------------------------------------------------------------------------
# Real-time player thread, buffer policy, and section scheduling glue.
# ---------------------------------------------------------------------------
import logging
import os
import threading
import time
from dataclasses import dataclass
from queue import Empty, Queue
from typing import List, Optional

import numpy as np
import math
try:
    import sounddevice as sd
except ImportError:  # pragma: no cover - optional runtime dependency
    sd = None

from .buffer_controller import PlaybackBufferController
from .drone_manager import DroneManager
from .playback_stream import AudioOutputStream
from .renderer import AudioRenderer
from .section_scheduler import SectionScheduler
from .telemetry import PlaybackTelemetry
from sampler import SamplerEngine as SamplerSynthesisEngine
from data.auto_mix_profiles import auto_mix_bias_for_emotion
from data.delay_profiles import delay_feedbacks_for_emotion
from audiogen_core.config import CONFIG, effective_tempo_bpm_from_config
from audiogen_core.mixer_config import AUDIO_MIXER_CHANNEL_COUNT, default_mixer_strips
from data.music_data import EMOTIONS, get_root
from midi.midi_range_limiter import RANGE_LIMITER
from audio.audio_container import (
    _tempo_synced_delay_ms,
    apply_melody_aux_send_hints,
    get_audio_container,
    melody_wants_shared_reverb_aux,
)

logger = logging.getLogger(__name__)


@dataclass
class AudioChunk:
    audio: np.ndarray
    bar_index: int
    emotion_name: str
    tempo: float
    root_note: int


class PolyphonicPlayer(threading.Thread):
    """
    Player with adaptive generation loop and continuous drone.
    """

    def __init__(self, composer, config=None, container=None):
        super().__init__(daemon=False)
        self.config = config or CONFIG
        self.container = container or get_audio_container()
        if self.container is None:
            raise RuntimeError("Audio container not available")
        self.composer = composer
        # Allow async section pre-generation in real runtime (unit tests default to off).
        self.allow_async_pregen = True
        self.synthesis_engine = SamplerSynthesisEngine(self.config)
        self._sampler_load_thread = None
        # Sampler prefetch worker (single long-lived thread; avoids per-bar thread spawns).
        self._prefetch_queue: Queue = Queue(maxsize=1)
        self._prefetch_worker_thread: Optional[threading.Thread] = None

        # Pre-load only the drone synchronously so startup can proceed quickly.
        self.synthesis_engine.preload_samplers(["drone"])

        # Load drone sample as a loop
        self._init_drone()

        # Start loading the remaining samplers immediately (background), so the
        # first preroll bars don't pay lazy-load + normalization costs.
        self._background_preload_started = False
        self._schedule_background_sampler_preload()

        # Start prefetch worker early so the first bars can enqueue requests.
        self._start_prefetch_worker()

        if self.container.mixer:
            # Do not default arp to silence when channel_mix omits ch3 (would hide the arp bed entirely).
            mix3 = self.config.audio.channel_mix.get(3) or {}
            try:
                arp_vol = float(mix3["volume"])
            except Exception:
                arp_vol = float(default_mixer_strips()[3].volume)
            self.container.mixer.set_channel_volume(3, arp_vol)

        # Audio renderer with reverb
        self.renderer = AudioRenderer(
            synthesis_engine=self.synthesis_engine,
            mixer=self.container.mixer,
            sample_rate=self.container.sample_rate,
            reverb_processor=self.container.reverb,
            master_bus=getattr(self.container, "master_bus", None),
        )

        # State
        self.state_lock = threading.Lock()
        self._emotion = None
        self._root = 60
        self._paused = False
        self._running = True
        self._playing = False

        # Buffer
        self.telemetry = PlaybackTelemetry(buffer_capacity=1024, logger=logger)
        self.buffer_controller = PlaybackBufferController(capacity=1024, telemetry=self.telemetry)
        self.buffer = self.buffer_controller.buffer
        # Cold start: queue a couple of bars before starting the OS stream so the
        # first heavy render/load doesn't immediately underrun.
        # Startup preroll in bars (how many bars to queue before starting the OS stream).
        # Make this configurable so users can trade startup latency vs underrun risk.
        self._startup_preroll_bars = max(1, int(getattr(self.config.audio, "startup_preroll_bars", 3) or 3))
        # Keep a healthy runway so one slow generate/render doesn't drain the queue.
        self._target_buffer_bars = max(2, int(getattr(self.config.audio, "target_buffer_bars", 12) or 12))
        self._base_startup_preroll_bars = int(self._startup_preroll_bars)
        self._base_target_buffer_bars = int(self._target_buffer_bars)
        self._rt_extra_buffer_bars = 0
        self._rt_last_underflow_time = 0.0
        self._rt_last_buffer_decay_time = 0.0
        self._rt_underflow_burst_count = 0
        self._rt_mode_stable = "normal"
        self._rt_mode_candidate = None
        self._rt_mode_candidate_streak = 0
        self._rt_mode_last_eval_chunk_index = -1
        self._rt_watchdog_safe_bars_remaining = 0
        self._rt_watchdog_triggered_count = 0
        self._rt_watchdog_last_ratio = 0.0
        # Refreshed from the generation loop; read by the PortAudio callback for telemetry only.
        self._telemetry_target_buffer_bars = int(self._target_buffer_bars)
        self._gen_burst_max_bars = max(2, int(getattr(self.config.audio, "gen_burst_max_bars", 12) or 12))
        audio_cfg = self.config.audio
        # Phrase grid for pending-emotion swaps (1 = every heard bar; 2 = every 2 heard bars; etc.)
        self._emotion_transition_boundary_bars = max(
            1, int(getattr(audio_cfg, "emotion_transition_boundary_bars", 1))
        )
        self._transition_boundary_bars = self._emotion_transition_boundary_bars
        self._emotion_handoff_crossfade_scale = float(
            np.clip(getattr(audio_cfg, "emotion_handoff_crossfade_scale", 0.84), 0.12, 1.0)
        )
        self._emotion_handoff_crossfade_max_seconds = float(
            np.clip(getattr(audio_cfg, "emotion_handoff_crossfade_max_seconds", 0.92), 0.04, 2.5)
        )

        # Cold-start fade-in (applied only once per player lifetime).
        try:
            self._startup_fade_in_enabled = bool(getattr(audio_cfg, "startup_fade_in_enabled", True))
        except Exception:
            self._startup_fade_in_enabled = True
        try:
            self._startup_fade_in_bars = max(0, int(getattr(audio_cfg, "startup_fade_in_bars", 2) or 0))
        except Exception:
            self._startup_fade_in_bars = 2
        try:
            self._startup_fade_in_start_gain = float(getattr(audio_cfg, "startup_fade_in_start_gain", 0.0) or 0.0)
        except Exception:
            self._startup_fade_in_start_gain = 0.0

        self.section_lock = threading.RLock()
        self._crossfade_pending = False
        self._transition_queue_cap_bars = max(4, self._emotion_transition_boundary_bars * 2)
        self._transition_crossfade_samples = max(
            256,
            int(
                self.container.sample_rate
                * float(getattr(audio_cfg, "transition_crossfade_seconds", 0.08) or 0.08)
            ),
        )
        self._transition_overlap_ratio = float(
            getattr(audio_cfg, "transition_overlap_ratio", 0.25) or 0.25
        )
        self._transition_max_overlap_seconds = float(
            getattr(audio_cfg, "transition_max_overlap_seconds", 1.5) or 1.5
        )
        self._last_generated_audio = None
        self.section_scheduler = SectionScheduler(owner=self, logger=logger)

        # Statistics
        self.total_bars_played = 0
        self.chunks_generated = 0
        # Per-bar render wall time (drives buffer targets and CPU ladder).
        self.last_bar_render_time = 0.0
        self.max_bar_render_time = 0.0
        # Background section / arranged compose (does not inflate bar buffer targets).
        self.last_section_compose_time = 0.0
        # Back-compat aliases for stats/tools (mirror bar render times).
        self.last_generation_time = 0.0
        self.max_generation_time = 0.0
        self._gen_stage_ema_ms = {
            "mono": 0.0,
            "chords": 0.0,
            "mix": 0.0,
            "master": 0.0,
            "total": 0.0,
        }
        self._gen_stage_last_ms = dict(self._gen_stage_ema_ms)
        self._gen_culprit = "unknown"
        # Emergency quality tier: drop to bass+drone only when generation can't keep up.
        self._emergency_active = False
        self._emergency_reason = ""
        self._emergency_last_change_time = 0.0
        self._emergency_last_underruns_seen = 0

        # Debug: last scheduled bar events (pre-render), for CLI inspection.
        self._debug_last_bar_index = 0
        self._debug_last_bar_events = []
        self._debug_last_bar_trace = None
        self._debug_notes_auto_enabled = False
        self._debug_notes_auto_channel = None
        self._debug_notes_stream_enabled = False
        self._debug_notes_stream_channel = None

        # FX gesture baselines (so per-bar gestures are reversible and bounded).
        self._fx_base_reverb_wet = None
        self._fx_base_dist = None
        self._fx_preset_transition = None

        # Pre‑allocated channel buffers (used inside renderer, but we keep them here for size)
        max_bar_seconds = 4.0 * 60.0 / 40.0
        a = getattr(self.config, "audio", None)
        pad = int(
            getattr(a, "bar_render_padding_samples", None)
            or getattr(a, "buffer_size", 4096)
            or 4096
        )
        self._max_bar_samples = int(max_bar_seconds * self.container.sample_rate) + pad
        self._channel_buffers = [
            np.zeros((self._max_bar_samples, 2), dtype=np.float32)
            for _ in range(int(AUDIO_MIXER_CHANNEL_COUNT))
        ]

        # Audio stream
        self._last_recovery_attempt_time = 0.0
        self._last_portaudio_underflow_log_ts = 0.0
        rt_bs = getattr(a, "rt_output_blocksize_frames", None) if a is not None else None
        block_frames = (
            int(rt_bs)
            if rt_bs is not None
            else int(getattr(self.config.audio, "buffer_size", 4096) or 4096)
        )
        self.output_stream = AudioOutputStream(
            sd_module=sd,
            sample_rate=self.config.audio.sample_rate,
            blocksize=max(256, block_frames),
            callback=self._audio_callback,
            logger=logger,
        )
        self.stream = None
        # Delay starting the OS audio stream until preroll is ready; otherwise the callback
        # drains an empty queue and triggers immediate underruns/backoff spirals at startup.
        self._prewarm_thread = None
        self._rt_prewarm_thread = None
        self._rt_mix_master_warmed = False
        # _background_preload_started is initialized above (after drone preload).

        # Generation thread
        self.gen_thread = threading.Thread(target=self._generation_loop, daemon=False)
        self.gen_thread.start()

        try:
            self.schedule_rt_prewarm(root=int(self._root), emotion=None)
        except Exception:
            pass

        logger.info("Player initialized (optimized thread-safe)")

    def _start_prefetch_worker(self) -> None:
        """
        Start a single background worker that performs sampler prefetch.

        This avoids spawning threads on the realtime generation loop, which can
        cause jitter and occasional slow bars.
        """
        try:
            audio_cfg = getattr(self.config, "audio", None)
            enabled = bool(getattr(audio_cfg, "prefetch_enabled", True)) if audio_cfg is not None else True
        except Exception:
            enabled = True
        if not enabled:
            return
        # Only start if the synthesis engine supports prefetch.
        try:
            se = getattr(self, "synthesis_engine", None)
            ok = bool(se is not None and hasattr(se, "prefetch_events"))
        except Exception:
            ok = False
        if not ok:
            return
        th = getattr(self, "_prefetch_worker_thread", None)
        if th is not None and th.is_alive():
            return

        def _worker() -> None:
            while True:
                try:
                    item = self._prefetch_queue.get()
                except Exception:
                    item = None
                if item is None:
                    break
                try:
                    events_snapshot, tempo_val, vel_val = item
                except Exception:
                    continue
                try:
                    se2 = getattr(self, "synthesis_engine", None)
                    if se2 is not None and hasattr(se2, "prefetch_events"):
                        se2.prefetch_events(list(events_snapshot), tempo=float(tempo_val), default_velocity=int(vel_val))
                except Exception:
                    # Best-effort: prefetch must never crash the realtime player.
                    pass

        self._prefetch_worker_thread = threading.Thread(
            target=_worker,
            name="sampler-prefetch-worker",
            daemon=True,
        )
        self._prefetch_worker_thread.start()

    def set_debug_notes_auto(self, enabled: bool, channel: Optional[int] = None) -> None:
        with self.state_lock:
            self._debug_notes_auto_enabled = bool(enabled)
            self._debug_notes_auto_channel = None if channel is None else int(channel)

    def get_debug_notes_auto(self) -> tuple[bool, Optional[int]]:
        with self.state_lock:
            return bool(getattr(self, "_debug_notes_auto_enabled", False)), getattr(
                self, "_debug_notes_auto_channel", None
            )

    def set_debug_notes_stream(self, enabled: bool, channel: Optional[int] = None) -> None:
        """If enabled, the CLI prints every scheduled note event once per bar."""
        with self.state_lock:
            self._debug_notes_stream_enabled = bool(enabled)
            self._debug_notes_stream_channel = None if channel is None else int(channel)

    def get_debug_notes_stream(self) -> tuple[bool, Optional[int]]:
        with self.state_lock:
            return bool(getattr(self, "_debug_notes_stream_enabled", False)), getattr(
                self, "_debug_notes_stream_channel", None
            )

    def _init_drone(self):
        drone_sampler = self.synthesis_engine.samplers.get('drone')
        if drone_sampler and drone_sampler.layers:
            raw = drone_sampler._raw_cache[0]
            try:
                vol = float(getattr(self.config.audio, "drone_loop_volume", 0.4))
            except Exception:
                vol = 0.4
            self.drone = DroneManager(raw, self.container.sample_rate, volume=vol)
            logger.info(f"Drone loop loaded: {len(raw)} samples, "
                        f"{len(raw)/self.container.sample_rate:.1f} seconds")
        else:
            logger.warning("No drone sample found, generating sine wave")
            # generate a 10-second sine wave
            duration = 10.0
            freq = 261.63
            samples = int(duration * self.container.sample_rate)
            t = np.linspace(0, duration, samples)
            mono = np.sin(2 * np.pi * freq * t).astype(np.float32)
            stereo = np.column_stack([mono, mono])
            # fade in/out
            fade_len = min(1024, samples // 10)
            if fade_len > 0:
                fade_in = np.linspace(0, 1, fade_len)[:, np.newaxis]
                fade_out = np.linspace(1, 0, fade_len)[:, np.newaxis]
                stereo[:fade_len] *= fade_in
                stereo[-fade_len:] *= fade_out
            try:
                vol = float(getattr(self.config.audio, "drone_loop_volume", 0.4))
            except Exception:
                vol = 0.4
            self.drone = DroneManager(stereo, self.container.sample_rate, volume=vol)

    def _init_audio_stream(self):
        self.output_stream.start()
        self.stream = self.output_stream.stream

    # Public API
    def load_emotion(self, emotion_index: int, root: int = 60):
        if 0 <= emotion_index < len(EMOTIONS):
            emotion = EMOTIONS[emotion_index]
            # Measure "emotion selected -> generated chunk ready" latency.
            # - cold start: preview generation is synchronous inside load_emotion()
            # - transitions: generation completes when SectionScheduler commits next_section_ready
            try:
                t0 = time.perf_counter()
            except Exception:
                t0 = time.time()
            try:
                self._last_emotion_request_perf = float(t0)
                self._last_emotion_request_name = str(getattr(emotion, "name", "") or "")
            except Exception:
                pass
            # Optional: key-lock all emotions to shared C major / A minor centers.
            # Implemented here so both cold-start and transitions share identical logic.
            try:
                comp = getattr(self.config, "composition", None)
            except Exception:
                comp = None
            if comp is not None and bool(getattr(comp, "key_lock_enabled", False)):
                try:
                    maj_root = int(getattr(comp, "key_lock_major_root_midi", 60) or 60)
                except Exception:
                    maj_root = 60
                try:
                    min_root = int(getattr(comp, "key_lock_minor_root_midi", 57) or 57)
                except Exception:
                    min_root = 57
                try:
                    maj_scale = list(getattr(comp, "key_lock_major_scale_intervals", None) or [0, 2, 4, 5, 7, 9, 11])
                except Exception:
                    maj_scale = [0, 2, 4, 5, 7, 9, 11]
                try:
                    min_scale = list(getattr(comp, "key_lock_minor_scale_intervals", None) or [0, 2, 3, 5, 7, 8, 10])
                except Exception:
                    min_scale = [0, 2, 3, 5, 7, 8, 10]

                def _mode_majorish(scale_iv: List[int]) -> bool:
                    try:
                        pcs = sorted({int(x) % 12 for x in list(scale_iv or [])})
                    except Exception:
                        pcs = []
                    if not pcs:
                        return True
                    # Heuristic: if it contains a major 3rd and not a minor 3rd, treat as major-ish; vice versa for minor-ish.
                    has_m3 = 3 in pcs
                    has_M3 = 4 in pcs
                    if has_M3 and not has_m3:
                        return True
                    if has_m3 and not has_M3:
                        return False
                    # Otherwise, compare overlap with our target sets.
                    maj_set = {int(x) % 12 for x in maj_scale}
                    min_set = {int(x) % 12 for x in min_scale}
                    maj_score = len(set(pcs) & maj_set) - len(set(pcs) - maj_set)
                    min_score = len(set(pcs) & min_set) - len(set(pcs) - min_set)
                    return bool(maj_score >= min_score)

                majorish = _mode_majorish(list(getattr(emotion, "scale_intervals", []) or []))
                root = int(maj_root if majorish else min_root)
                # Feed scale lock via config so the section planner derives owner.global_scale deterministically.
                try:
                    comp.global_scale_intervals = list(maj_scale if majorish else min_scale)
                except Exception:
                    pass

            with self.section_lock:
                # Any load_emotion after the first is a transition: never clear the ring buffer
                # again (only the initial cold start may clear). Heuristics on _playing / buffer
                # fill missed edge cases and caused full buffer.clear() + audible cutouts.
                with self.state_lock:
                    transition_in_progress = self._emotion is not None
                if not transition_in_progress:
                    with self.state_lock:
                        self._emotion = emotion
                        self._root = root

                    self._apply_emotion_runtime_state(emotion)
                    self.buffer.clear()
                    self.section_scheduler.reset_transition_state()
                    # Fast cold start: generate a tiny preview immediately, and let the normal
                    # pre-generation pipeline build the full timeline in the background.
                    try:
                        try:
                            pb = int(
                                getattr(self.config.audio, "cold_start_preview_bars", 1) or 1
                            )
                        except Exception:
                            pb = 1
                        pb = max(1, min(4, pb))
                        self.section_scheduler.generate_new_section_fast_preview(preview_bars=pb)
                        self.section_scheduler.ensure_pregen_enqueued()
                        # Cold start generation is synchronous here; record a latency sample now.
                        try:
                            t1 = time.perf_counter()
                        except Exception:
                            t1 = time.time()
                        try:
                            req = float(getattr(self, "_last_emotion_request_perf", 0.0) or 0.0)
                            if req > 0.0:
                                self._last_emotion_switch_latency_s = float(max(0.0, float(t1) - float(req)))
                                self._last_emotion_switch_emotion = str(getattr(emotion, "name", "") or "")
                                self._last_emotion_switch_stage = "cold_start"
                        except Exception:
                            pass
                    except Exception:
                        self.section_scheduler.generate_new_section()
                else:
                    # Snapshot the currently-heard arrangement role (chorus/verse/etc) so arranged
                    # emotion switches can keep the same stage when generating the next timeline.
                    try:
                        self.section_scheduler.snapshot_current_arrangement_role_hint()
                    except Exception:
                        pass
                    self.section_scheduler.pending_emotion = emotion
                    self.section_scheduler.pending_root = root
                    self.section_scheduler.next_section_ready = False
                    self.section_scheduler.next_section_events = None
                    self.section_scheduler.next_section_bars = 0
                    self.section_scheduler.next_section_emotion = None
                    self.section_scheduler.next_section_root = None
                    # Do not trim the queue: discarding pre-rendered bars shrinks headroom and
                    # caused underruns/silence right after the performance refactor tightened timing.
                    # Reset loudness smoothing memory so the first bar after handoff doesn't
                    # inherit stale loudness state from the previous emotion.
                    try:
                        # Per-bar leveler memory.
                        setattr(self, "_debug_prev_bar_rms", 0.0)
                        # Emotion RMS normalizer: restart gain for the pending emotion.
                        st = getattr(self, "_emotion_rms_ema", None)
                        if isinstance(st, dict):
                            key = str(getattr(emotion, "name", "") or "")
                            if key:
                                st[key] = {"n": 0, "rms_ema": None, "gain": float(getattr(self, "_output_leveler_gain", 1.0) or 1.0)}
                                setattr(self, "_emotion_rms_ema", st)
                    except Exception:
                        pass
            if not transition_in_progress:
                # Pipeline the next phrase/song as soon as the first section exists (generative player).
                self.section_scheduler.ensure_pregen_enqueued()
            # Prewarming can be expensive; skip it on cold start so first audio begins sooner.
            if transition_in_progress:
                # Important: sampler prewarm can cause CPU spikes that starve the PortAudio callback,
                # especially right when the user hits `n` rapidly. Keep this opt-in.
                try:
                    audio_cfg = getattr(self.config, "audio", None)
                    prewarm_enabled = bool(getattr(audio_cfg, "emotion_switch_sampler_prewarm_enabled", False)) if audio_cfg is not None else False
                except Exception:
                    prewarm_enabled = False
                if prewarm_enabled:
                    self._schedule_sampler_prewarm()
            if transition_in_progress:
                self.section_scheduler.ensure_pregen_enqueued()
            if transition_in_progress:
                try:
                    self.schedule_rt_prewarm(root=int(root), emotion=emotion)
                except Exception:
                    pass
            if transition_in_progress:
                logger.info("Queued emotion change: %s", emotion.name.upper())
            else:
                logger.info(f"Now playing: {emotion.name.upper()}")
        else:
            logger.warning(f"Invalid emotion index {emotion_index}. Use 0‑{len(EMOTIONS)-1}")

    def _record_emotion_switch_generated(self, emotion) -> None:
        """
        Called by SectionScheduler when a pending emotion's next chunk is generated and committed.
        Records latency from the most recent load_emotion() request to the commit point.
        """
        try:
            req_t = float(getattr(self, "_last_emotion_request_perf", 0.0) or 0.0)
        except Exception:
            req_t = 0.0
        if req_t <= 0.0:
            return
        try:
            req_name = str(getattr(self, "_last_emotion_request_name", "") or "")
        except Exception:
            req_name = ""
        try:
            emo_name = str(getattr(emotion, "name", "") or "")
        except Exception:
            emo_name = ""
        if req_name and emo_name and req_name.strip().lower() != emo_name.strip().lower():
            return
        try:
            t1 = time.perf_counter()
        except Exception:
            t1 = time.time()
        try:
            self._last_emotion_switch_latency_s = float(max(0.0, float(t1) - float(req_t)))
            self._last_emotion_switch_emotion = str(emo_name or req_name or "")
            self._last_emotion_switch_stage = "transition_pregen_commit"
        except Exception:
            return

    def _schedule_sampler_prewarm(self):
        thread = getattr(self, "_prewarm_thread", None)
        if thread is not None and thread.is_alive():
            return
        self._prewarm_thread = threading.Thread(
            target=self._prewarm_samplers,
            name="sampler-prewarm",
            daemon=True,
        )
        self._prewarm_thread.start()

    def _schedule_background_sampler_preload(self):
        if self._background_preload_started:
            return
        thread = getattr(self, "_sampler_load_thread", None)
        if thread is not None and thread.is_alive():
            return
        self._background_preload_started = True
        self._sampler_load_thread = threading.Thread(
            target=self._background_preload_remaining_samplers,
            name="sampler-load",
            daemon=True,
        )
        self._sampler_load_thread.start()

    def refresh_samplers_after_preset_change(self, *, keep: Optional[set[str]] = None) -> None:
        """
        Refresh sampler instances after a preset/pack change without restarting playback.

        By default this keeps the drone sampler alive so the continuous drone loop does not
        reset (no audible stop; playback position continues), while other samplers can pick
        up the new preset's pack/style settings on their next lazy load.
        """
        keep_set = {"drone"} if keep is None else {str(x) for x in (keep or set()) if str(x)}
        try:
            dropped = int(self.synthesis_engine.unload_samplers(keep=keep_set))
        except Exception:
            dropped = 0

        # If we dropped anything, allow the background preloader to run again
        # so the next bars don't pay cold-load costs.
        if dropped > 0:
            try:
                self._background_preload_started = False
            except Exception:
                pass
            try:
                self._schedule_background_sampler_preload()
            except Exception:
                pass

        logger.info("Sampler refresh after preset change (dropped=%d keep=%s)", int(dropped), sorted(keep_set))

    def _background_preload_remaining_samplers(self):
        if not hasattr(self.synthesis_engine, "preload_samplers"):
            return
        try:
            self.synthesis_engine.preload_samplers(["bass", "chords", "melody", "arp", "counter_melody"])
        except Exception:
            logger.exception("Background sampler preload failed")

    def _prewarm_samplers(self):
        with self.state_lock:
            emotion = self.section_scheduler.pending_emotion or self._emotion
            root = self.section_scheduler.pending_root if self.section_scheduler.pending_root is not None else self._root
        if emotion is None:
            return
        all_notes = set()
        from data.chord_parser import midi_to_note
        key_root_name = midi_to_note(root)

        for prog in emotion.chord_progressions:
            for chord in prog:
                offset = get_root(chord, key_root_name)
                note = root + offset
                all_notes.add(note)
                all_notes.add(note + 4)
                all_notes.add(note + 7)
                all_notes.add(note + 11)
        for note in range(root - 12, root + 24, 2):
            all_notes.add(note)
        self.synthesis_engine.prewarm_notes(list(all_notes))

    @property
    def emotion(self):
        with self.state_lock:
            return self._emotion

    @property
    def root(self):
        with self.state_lock:
            return self._root

    @property
    def paused(self):
        with self.state_lock:
            return self._paused

    def pause(self):
        with self.state_lock:
            self._paused = True
        logger.info("Paused")

    def resume(self):
        with self.state_lock:
            self._paused = False
        logger.info("Resumed")

    def toggle_pause(self):
        with self.state_lock:
            self._paused = not self._paused
        logger.info("Toggled pause")

    def stop(self):
        with self.state_lock:
            self._running = False
            self._playing = False
        # Stop the OS audio stream early so the callback can't run during teardown.
        # (The generator thread and other teardown steps can take time.)
        try:
            self.output_stream.stop()
        except Exception:
            pass
        self.stream = self.output_stream.stream
        time.sleep(0.2)
        # Stop sampler prefetch worker promptly.
        try:
            self._prefetch_queue.put_nowait(None)
        except Exception:
            pass
        try:
            th = getattr(self, "_prefetch_worker_thread", None)
            if th is not None and th.is_alive():
                th.join(timeout=0.5)
        except Exception:
            pass
        if self.gen_thread.is_alive():
            self.gen_thread.join(timeout=2.0)
        mb = getattr(self.container, "master_bus", None)
        if mb is not None and hasattr(mb, "detach_event_bus"):
            mb.detach_event_bus()
        if self.is_alive():
            self.join(timeout=2.0)
        logger.info("Player stopped")

    def get_stats(self) -> dict:
        effective_fill = self.buffer_controller.effective_fill_bars()
        stats = self.telemetry.snapshot(
            buffer_fill=effective_fill,
            target_buffer_bars=self._compute_target_buffer_bars(),
        )
        stats.update({
            'total_bars': self.total_bars_played,
            'chunks_generated': self.chunks_generated,
            'paused': self.paused,
            'playing': self._playing,
            'last_gen_time_ms': self.last_bar_render_time * 1000,
            'max_gen_time_ms': self.max_bar_render_time * 1000,
            'last_section_compose_time_ms': float(getattr(self, 'last_section_compose_time', 0.0) or 0.0) * 1000.0,
            'queued_buffer_bars': self.buffer_controller.queued_fill_bars(),
            'quality_tier': str(self._runtime_generation_mode()),
            'emergency_active': bool(getattr(self, "_emergency_active", False)),
            'emergency_reason': str(getattr(self, "_emergency_reason", "") or ""),
            'gen_culprit': str(getattr(self, "_gen_culprit", "unknown") or "unknown"),
            'gen_stage_ema_ms': {
                str(k): float(v) for k, v in dict(getattr(self, "_gen_stage_ema_ms", {}) or {}).items()
            },
            'gen_stage_last_ms': {
                str(k): float(v) for k, v in dict(getattr(self, "_gen_stage_last_ms", {}) or {}).items()
            },
            'rt_mode_stable': str(getattr(self, "_rt_mode_stable", "normal") or "normal"),
            'rt_mode_candidate': str(getattr(self, "_rt_mode_candidate", "") or ""),
            'rt_mode_candidate_streak': int(getattr(self, "_rt_mode_candidate_streak", 0) or 0),
            'rt_watchdog_safe_bars_remaining': int(getattr(self, "_rt_watchdog_safe_bars_remaining", 0) or 0),
            'rt_watchdog_triggered_count': int(getattr(self, "_rt_watchdog_triggered_count", 0) or 0),
            'rt_watchdog_last_ratio': float(getattr(self, "_rt_watchdog_last_ratio", 0.0) or 0.0),
        })
        try:
            lat_s = float(getattr(self, "_last_emotion_switch_latency_s", 0.0) or 0.0)
        except Exception:
            lat_s = 0.0
        if lat_s > 0.0 or hasattr(self, "_last_emotion_switch_latency_s"):
            stats["last_emotion_switch_latency_ms"] = float(max(0.0, lat_s) * 1000.0)
            stats["last_emotion_switch_emotion"] = str(getattr(self, "_last_emotion_switch_emotion", "") or "")
            stats["last_emotion_switch_stage"] = str(getattr(self, "_last_emotion_switch_stage", "") or "")
        return stats

    @property
    def current_bar_seconds(self) -> float:
        """Public accessor for tempo‑derived bar duration (seconds).

        Unlike ``_current_bar_seconds()``, this is a safe property that
        benchmark and audit tools can use without accessing private members.
        """
        return self._current_bar_seconds()

    @property
    def stage_timing_ms(self) -> dict:
        """Public accessor for the most recent per‑stage render timings (ms).

        Benchmarks and audit scripts should prefer this over reaching into
        ``renderer.last_stage_timing_ms`` directly.
        """
        try:
            return dict(getattr(self.renderer, "last_stage_timing_ms", {}) or {})
        except Exception:
            return {}

    # Internal methods
    def _apply_emotion_runtime_state(self, emotion, *, reset_mixer_filters: bool = True):
        RANGE_LIMITER.reset_to_defaults()
        # Resetting IIR states on every crossfade makes the next bar start from zi=0 and reads as
        # a level/tone "drop". Cold starts still reset; section handoffs keep filter continuity.
        if (
            reset_mixer_filters
            and self.container.mixer
            and hasattr(self.container.mixer, "reset_all_filters")
        ):
            self.container.mixer.reset_all_filters()
        self._apply_emotion_delay_state(emotion)
        # Effects/mix are controlled globally by meta presets (not per-emotion).

    def _apply_emotion_delay_state(self, emotion) -> None:
        mixer = getattr(self.container, "mixer", None)
        if mixer is None or emotion is None:
            return
        channel_delay = getattr(self.config.audio, "channel_delay", {}) or {}
        # Apply base delay params (enabled/time/mix) from config, then modulate feedback per emotion.
        # This keeps the perceived "space" stable (wet %) while preventing dense emotions from washing out.
        for ch_i in (2, 3):
            cfg = channel_delay.get(ch_i) or {}
            ch = mixer.get_channel(int(ch_i)) if hasattr(mixer, "get_channel") else None
            if ch is None:
                continue
            try:
                ch.delay_enabled = bool(cfg.get("enabled", False))
                time_ms = float(cfg.get("time_ms", 300.0))
                if bool(cfg.get("sync", False)):
                    bpm = None
                    try:
                        if effective_tempo_bpm_from_config is not None:
                            bpm = float(effective_tempo_bpm_from_config(self.config, emotion))
                    except Exception:
                        bpm = None
                    if bpm:
                        synced = _tempo_synced_delay_ms(bpm=float(bpm), division=str(cfg.get("division", "1/8")))
                        if synced is not None:
                            time_ms = float(synced)
                ch.delay_time_ms = float(time_ms)
                ch.delay_mix = float(cfg.get("mix", getattr(ch, "delay_mix", 0.0)))
            except Exception:
                pass

        melody_base = float((channel_delay.get(2) or {}).get("feedback", getattr(self.config.audio, "delay_bus_feedback", 0.16)))
        arp_base = float((channel_delay.get(3) or {}).get("feedback", melody_base))
        counter_base = float((channel_delay.get(5) or {}).get("feedback", melody_base))
        feedbacks = delay_feedbacks_for_emotion(
            getattr(emotion, "name", ""),
            melody_base=melody_base,
            arp_base=arp_base,
            counter_base=counter_base,
        )
        for channel, feedback in feedbacks.items():
            ch = mixer.get_channel(channel) if hasattr(mixer, "get_channel") else None
            if ch is not None:
                ch.delay_feedback = float(feedback)

        # If melody channel_delay is enabled, treat its mix as an *additional* hint
        # for aux delay/reverb send levels. Do not zero existing sends: mixer strips
        # may author sends for multiple channels and presets may set delay sends even
        # when per-channel delay insert is disabled.
        mch = apply_melody_aux_send_hints(mixer, channel_delay)

        mb = getattr(self.container, "master_bus", None)
        if mb is not None:
            try:
                a = self.config.audio
                if mch is not None and bool(getattr(mch, "delay_enabled", False)):
                    mb.delay_time_ms = float(getattr(mch, "delay_time_ms", getattr(a, "delay_bus_time_ms", mb.delay_time_ms)))
                else:
                    mb.delay_time_ms = float(getattr(a, "delay_bus_time_ms", mb.delay_time_ms))
                mb.delay_feedback = max(0.0, min(0.99, float(getattr(a, "delay_bus_feedback", mb.delay_feedback))))
            except Exception:
                pass

        rev = getattr(self.container, "reverb", None)
        if rev is not None:
            try:
                a = self.config.audio
                if melody_wants_shared_reverb_aux(a) and not bool(getattr(a, "reverb_enabled", True)):
                    a.reverb_enabled = True
                rw = float(getattr(a, "reverb_wet", 0.5))
                if bool(getattr(a, "emotion_auto_mix_enabled", True)):
                    rw = max(0.0, min(1.0, rw + auto_mix_bias_for_emotion(emotion).reverb_wet_delta))
                if bool(getattr(a, "reverb_enabled", True)):
                    rev.set_wet(rw)
                else:
                    rev.set_wet(0.0)
            except Exception:
                pass

        self._apply_emotion_auto_mix_eq(emotion)

    def _apply_emotion_auto_mix_eq(self, emotion) -> None:
        """Subtle per-emotion master-EQ tilt (auto-mixer work, docs/AUDIOGEN_COMPOSITION_PLAN.md).

        Recomputed from the CONFIGURED base gain each call (not accumulated), so repeated
        emotion switches can't drift the tilt further than the bias table intends.
        """
        mb = getattr(self.container, "master_bus", None)
        a = getattr(self.config, "audio", None)
        if mb is None or a is None or not bool(getattr(a, "emotion_auto_mix_enabled", True)):
            return
        if not bool(getattr(mb, "master_eq_enabled", False)):
            return
        try:
            bias = auto_mix_bias_for_emotion(emotion)
            bands = list(getattr(mb, "_master_eq_bands", None) or [])
            if not bands:
                return
            base_low = float(getattr(a, "master_eq_band1_gain_db", 0.0))
            base_high = float(getattr(a, "master_eq_band4_gain_db", 0.0))
            new_bands = []
            for i, (b_type, freq, gain, q) in enumerate(bands):
                if i == 0 and b_type == "lowshelf":
                    gain = base_low + bias.eq_low_shelf_delta_db
                elif i == 3 and b_type == "highshelf":
                    gain = base_high + bias.eq_high_shelf_delta_db
                new_bands.append((b_type, freq, gain, q))
            mb._master_eq_bands = new_bands
            mb._master_eq_cache_key = None
        except Exception:
            pass

    def _generate_new_section(self):
        self.section_scheduler.generate_new_section()

    def _pre_generate_next_section(self):
        self.section_scheduler.pre_generate_next_section()

    def _generate_next_bar(self) -> Optional[AudioChunk]:
        t_gen0 = time.time()
        pr = None
        try:
            from utils.rt_bar_profiler import start_rt_cprofile_if_enabled

            pr = start_rt_cprofile_if_enabled()
        except Exception:
            pr = None
        try:
            return self._generate_next_bar_impl(t_gen0)
        finally:
            try:
                from utils.rt_bar_profiler import finish_rt_cprofile_if_slow

                finish_rt_cprofile_if_slow(
                    pr,
                    logger,
                    time.time() - t_gen0,
                    float(getattr(self, "_rt_profile_bar_seconds", 2.0)),
                )
            except Exception:
                pass

    def _generate_next_bar_impl(self, t_gen0: float) -> Optional[AudioChunk]:
        setattr(self, "_rt_profile_bar_seconds", 2.0)
        _prep_t0 = time.perf_counter()
        bar_data = self.section_scheduler.prepare_next_bar()
        _prepare_ms = (time.perf_counter() - _prep_t0) * 1000.0
        _render_ms = 0.0
        try:
            tb = float(bar_data.get("tempo", 70.0) or 70.0)
            setattr(self, "_rt_profile_bar_seconds", max(0.25, 4.0 * 60.0 / max(40.0, tb)))
        except Exception:
            setattr(self, "_rt_profile_bar_seconds", 2.0)
        switched_section = bar_data["switched_section"]
        emotion_handoff = bool(bar_data.get("emotion_handoff"))
        arranged_song_fade = bar_data.get("arranged_song_fade")
        # Best-effort sampler cache prefetch for the *next* bar (non-blocking).
        try:
            audio_cfg = getattr(self.config, "audio", None)
            enabled = bool(getattr(audio_cfg, "prefetch_enabled", True)) if audio_cfg is not None else True
        except Exception:
            enabled = True
        if enabled:
            try:
                preview = list(bar_data.get("next_bar_events_preview") or [])
            except Exception:
                preview = []
            if preview:
                try:
                    max_ev = int(getattr(getattr(self.config, "audio", None), "prefetch_max_events", 220) or 220)
                except Exception:
                    max_ev = 220
                if max_ev > 0 and len(preview) > max_ev:
                    preview = preview[:max_ev]
                try:
                    tempo_pf = float(bar_data.get("tempo", 70.0) or 70.0)
                except Exception:
                    tempo_pf = 70.0
                try:
                    vel_pf = int(getattr(getattr(self.config, "audio", None), "prefetch_default_velocity", 80) or 80)
                except Exception:
                    vel_pf = 80
                # Enqueue only the latest prefetch request (drop stale work).
                try:
                    while True:
                        try:
                            _ = self._prefetch_queue.get_nowait()
                        except Empty:
                            break
                        except Exception:
                            break
                    try:
                        self._prefetch_queue.put_nowait((preview, tempo_pf, vel_pf))
                    except Exception:
                        pass
                except Exception:
                    pass
        if bar_data["silence"] is not None:
            try:
                from utils.rt_bar_profiler import log_rt_bar_timing_if_enabled

                log_rt_bar_timing_if_enabled(
                    logger,
                    prepare_ms=float(_prepare_ms),
                    render_ms=0.0,
                    total_ms=(time.time() - t_gen0) * 1000.0,
                )
            except Exception:
                pass
            return AudioChunk(
                audio=bar_data["silence"],
                bar_index=bar_data["bar_index"],
                emotion_name="",
                tempo=bar_data["tempo"],
                root_note=bar_data["root_note"],
            )

        emotion = bar_data["emotion"]
        root = bar_data["root_note"]
        tempo = bar_data["tempo"]
        bar_seconds = 4.0 * 60.0 / tempo
        samples = int(bar_seconds * self.container.sample_rate)
        # Style/emotion-aware smoothing for preset-driven FX changes.
        self._apply_fx_preset_transition_step()

        # Capture events for debugging / CLI inspection.
        try:
            with self.state_lock:
                self._debug_last_bar_index = int(bar_data.get("bar_index", 0) or 0)
                self._debug_last_bar_events = list(bar_data.get("bar_events") or [])
                self._debug_last_bar_trace = bar_data.get("bar_trace", None)
        except Exception:
            pass

        # ----------------------------------------------------------
        # Optional per-bar FX gestures driven by bar_trace.
        # Realtime-safe: only adjusts a few master return scalars.
        # ----------------------------------------------------------
        try:
            comp = getattr(self.config, "composition", None)
            fx_k = float(getattr(comp, "texture_fx_gesture_strength", 0.0) or 0.0) if comp is not None else 0.0
        except Exception:
            fx_k = 0.0
        fx_k = float(max(0.0, min(1.0, float(fx_k))))
        if fx_k > 1e-6:
            try:
                mb = getattr(self.container, "master_bus", None)
            except Exception:
                mb = None
            tr = bar_data.get("bar_trace", None)
            if mb is not None and isinstance(tr, dict):
                try:
                    space = float(tr.get("fx_space_boost", 0.0) or 0.0)
                    grit = float(tr.get("fx_grit_boost", 0.0) or 0.0)
                except Exception:
                    space, grit = 0.0, 0.0
                space = float(max(0.0, min(1.0, float(space))))
                grit = float(max(0.0, min(1.0, float(grit))))

                # Initialize baselines once.
                try:
                    if self._fx_base_reverb_wet is None:
                        self._fx_base_reverb_wet = float(getattr(mb, "reverb_return_wet", 0.5) or 0.5)
                    if self._fx_base_dist is None:
                        self._fx_base_dist = {
                            "enabled": bool(getattr(getattr(mb, "distortion", None), "enabled", False)),
                            "drive": float(getattr(getattr(mb, "distortion", None), "drive", 1.35) or 1.35),
                            "mix": float(getattr(mb, "distortion_return_level", 0.08) or 0.08),
                        }
                except Exception:
                    pass

                # Reverb "space" gesture.
                try:
                    base = float(self._fx_base_reverb_wet if self._fx_base_reverb_wet is not None else 0.5)
                    wet = float(base) + float(fx_k) * float(space) * 0.25
                    mb.set_reverb_return_wet(float(wet))
                except Exception:
                    pass

                # Distortion "grit" gesture (return level; bounded).
                try:
                    bd = self._fx_base_dist if isinstance(self._fx_base_dist, dict) else None
                    if bd is not None:
                        mix0 = float(bd.get("mix", 0.08) or 0.08)
                        drive0 = float(bd.get("drive", 1.35) or 1.35)
                        mix = float(mix0) + float(fx_k) * float(grit) * 0.10
                        drive = float(drive0) * (1.0 + 0.20 * float(fx_k) * float(grit))
                        mb.set_master_distortion(
                            enabled=bool(bd.get("enabled", True) or True),
                            drive=float(max(1.0, min(2.5, drive))),
                            mix=float(max(0.0, min(0.35, mix))),
                        )
                except Exception:
                    pass

        # ----------------------------------------------------------
        # Optional realtime debug printouts (compact per-bar trace).
        # ----------------------------------------------------------
        try:
            dbg = bool(getattr(getattr(self.config, "composition", None), "debug_bar_trace_enabled", False))
        except Exception:
            dbg = False
        if dbg:
            try:
                # Avoid duplicate logs if the generator thread retries the same bar.
                bidx = int(bar_data.get("bar_index", 0) or 0)
                last = getattr(self, "_debug_last_logged_bar_index", None)
                if last is None or int(last) != int(bidx) or bool(switched_section):
                    setattr(self, "_debug_last_logged_bar_index", int(bidx))
                    for line in self.debug_last_bar_trace_dump():
                        logger.info("%s", line)
            except Exception:
                pass

        # Section summary when we activate a new section (best-effort).
        try:
            sec_dbg = bool(getattr(getattr(self.config, "composition", None), "debug_section_summary_enabled", False))
        except Exception:
            sec_dbg = False
        if sec_dbg and bool(switched_section):
            try:
                # Print only the header + cadence pairs section (keeps logs short).
                lines = self.debug_last_section_harmony_dump()
                if lines:
                    logger.info("---- section summary ----")
                    # header + first few bars
                    for ln in lines[: min(10, len(lines))]:
                        logger.info("%s", ln)
                    # Always include cadence pairs block if present.
                    if "cadence pairs (phrase ends):" in lines:
                        i0 = lines.index("cadence pairs (phrase ends):")
                        for ln in lines[i0 : min(len(lines), i0 + 7)]:
                            logger.info("%s", ln)
                # Harmonic hook signature (if captured).
                gen = getattr(getattr(self, "composer", None), "gen", None)
                sig = getattr(gen, "_harmonic_hook_signature", None) if gen is not None else None
                if isinstance(sig, dict):
                    pair = sig.get("pair", None)
                    if isinstance(pair, list) and len(pair) >= 2:
                        logger.info("harmonic_hook_pair: %s -> %s", str(pair[-2]), str(pair[-1]))
            except Exception:
                pass


        try:
            mode = self._runtime_generation_mode()
            culprit = self._dominant_generation_stage()
            fx_scale = 1.0
            try:
                a = getattr(self.config, "audio", None)
                if mode == "balanced":
                    fx_scale = float(getattr(a, "fx_return_scale_balanced", 0.75) or 0.75)
                elif mode == "safe":
                    fx_scale = float(getattr(a, "fx_return_scale_safe", 0.50) or 0.50)
                elif mode == "emergency":
                    fx_scale = float(getattr(a, "fx_return_scale_emergency", 0.35) or 0.35)
                else:
                    fx_scale = 1.0
            except Exception:
                fx_scale = 1.0
            if mode == "balanced" and culprit == "master":
                # If master processing dominates, easing return FX helps more than dropping notes.
                fx_scale *= 0.82
            try:
                _a2 = getattr(self.config, "audio", None)
                if (
                    _a2 is not None
                    and bool(getattr(_a2, "arrangement_fx_return_automation_enabled", True))
                ):
                    from data.arrangement_curves import arrangement_role_fx_return_mult

                    _st = float(getattr(_a2, "arrangement_fx_return_strength", 1.0) or 1.0)
                    _arole = str(bar_data.get("arrangement_role") or "")
                    _fm = arrangement_role_fx_return_mult(_arole, strength=_st)
                    fx_scale = float(fx_scale) * float(_fm)
            except Exception:
                pass
            fx_scale = float(np.clip(float(fx_scale), 0.0, 1.0))
            vel_ride = 1.0
            try:
                _a3 = getattr(self.config, "audio", None)
                if _a3 is not None and bool(
                    getattr(_a3, "arrangement_velocity_ride_enabled", True)
                ):
                    from data.arrangement_curves import arrangement_role_velocity_ride_mult

                    _vst = float(
                        getattr(_a3, "arrangement_velocity_ride_strength", 1.0) or 1.0
                    )
                    _arv = str(bar_data.get("arrangement_role") or "")
                    _pcl = bool(bar_data.get("arrangement_pre_chorus_last_bar") or False)
                    _swon = bool(
                        getattr(
                            _a3,
                            "arrangement_pre_chorus_last_bar_swell_enabled",
                            True,
                        )
                    )
                    _pss = float(
                        getattr(
                            _a3,
                            "arrangement_pre_chorus_last_bar_swell_strength",
                            1.0,
                        )
                        or 1.0
                    )
                    vel_ride = arrangement_role_velocity_ride_mult(
                        _arv,
                        strength=_vst,
                        pre_chorus_last_bar=(_pcl and _swon),
                        pre_chorus_swell_strength=_pss,
                    )
            except Exception:
                vel_ride = 1.0
            try:
                vel_ride = float(
                    np.clip(
                        float(vel_ride),
                        float(0.75),
                        float(1.15),
                    )
                )
            except Exception:
                vel_ride = 1.0
            drone_slice = None
            if self.drone is not None and not self._should_suppress_drone(emotion):
                drone_slice = self.drone.get_slice(samples)
            t0 = time.time()
            try:
                # ----------------------------------------------------------
                # Graded realtime load shedding (drop low-priority channels)
                # ----------------------------------------------------------
                ev = list(bar_data.get("bar_events") or [])
                try:
                    a = getattr(self.config, "audio", None)
                    shed_enabled = bool(getattr(a, "load_shed_enabled", False)) if a is not None else False
                except Exception:
                    shed_enabled = False
                if shed_enabled and ev:
                    try:
                        bar_seconds_rt = float(bar_seconds)
                        with self.state_lock:
                            ratio_rt = float(self.last_bar_render_time or 0.0) / max(0.1, bar_seconds_rt)
                    except Exception:
                        ratio_rt = 0.0
                    try:
                        a = getattr(self.config, "audio", None)
                        thr = float(getattr(a, "load_shed_balanced_ratio_threshold", 0.90) or 0.90)
                    except Exception:
                        thr = 0.90

                    drop = []
                    if mode == "safe":
                        try:
                            drop = list(getattr(getattr(self.config, "audio", None), "load_shed_drop_channels_safe", []) or [])
                        except Exception:
                            drop = []
                    elif mode == "balanced" and ratio_rt >= thr:
                        if culprit in {"mono", "chords", "mix"}:
                            try:
                                drop = list(getattr(getattr(self.config, "audio", None), "load_shed_drop_channels_balanced", []) or [])
                            except Exception:
                                drop = []
                    if drop:
                        try:
                            drop_set = set(int(x) for x in drop)
                        except Exception:
                            drop_set = set()
                        ev = [e for e in ev if not (len(e) > 0 and int(e[0]) in drop_set)]

                    if mode == "safe":
                        try:
                            cap = int(getattr(getattr(self.config, "audio", None), "load_shed_max_events_safe", 320) or 320)
                        except Exception:
                            cap = 320
                        if cap > 0 and len(ev) > cap:
                            # Preserve ordering (already sorted in renderer) but cap count.
                            ev = ev[:cap]

                # Emergency tier: keep all musical events by default.
                # (Emergency mode still uses `fast_master` and other RT safeguards.)

                audio = self.renderer.render_bar(
                    ev,
                    tempo,
                    samples,
                    drone=drone_slice,
                    velocity_multiplier=float(vel_ride),
                    fast_master=self._should_fast_master(mode),
                    skip_master_inserts=self._should_bypass_master_inserts(mode),
                    skip_multiband=self._should_bypass_master_multiband(mode),
                    skip_master_eq=self._should_bypass_master_eq(mode),
                    fx_return_scale=float(fx_scale),
                    reverb_quality_tier=self._runtime_reverb_quality_tier(mode),
                    arrangement_role=str(bar_data.get("arrangement_role") or ""),
                )
            except TypeError:
                # Tests and alternate renderer implementations may not accept `fast_master`.
                audio = self.renderer.render_bar(
                    bar_data["bar_events"],
                    tempo,
                    samples,
                    drone=drone_slice,
                )
            dt = time.time() - t0
            _render_ms = float(dt) * 1000.0
            self._update_generation_stage_telemetry()
            # Bar-to-bar overlap crossfade: only when the user changes emotional preset
            # (queued emotion swap). Form boundaries (intro→verse, loop→next song, etc.) use
            # composition-level continuity plus startup / end-of-song gain ramps instead.
            if switched_section and emotion_handoff:
                self._crossfade_pending = True
        except Exception:
            logger.exception("Error rendering audio frame")
            audio = np.zeros((samples, 2), dtype=np.float32)
            dt = time.time() - t_gen0
            _render_ms = float(dt) * 1000.0

        # Arranged-song loop: fade out the last N bars before the next song activates.
        # This is applied pre-crossfade and pre-levelers so it isn't "undone" by normalization.
        try:
            if (
                arranged_song_fade is not None
                and isinstance(arranged_song_fade, (tuple, list))
                and len(arranged_song_fade) == 2
            ):
                sg = float(arranged_song_fade[0])
                eg = float(arranged_song_fade[1])
                if (sg < 0.999) or (eg < 0.999):
                    audio = self._apply_gain_ramp(audio, start_gain=sg, end_gain=eg)
        except Exception:
            pass

        # Track total wall time per generated bar (prep + render + mix + FX).
        total_dt = time.time() - t_gen0
        self._record_bar_render_timing(float(total_dt))
        self._update_rt_render_watchdog(render_seconds=float(total_dt), bar_seconds=float(bar_seconds))

        # Helpful warning when we get close to real-time.
        try:
            if total_dt >= max(0.25, float(bar_seconds) * 0.85):
                logger.warning(
                    "Slow bar render: %.1fms (bar=%.1fms) events=%d tempo=%.1f",
                    total_dt * 1000.0,
                    float(bar_seconds) * 1000.0,
                    len(bar_data.get("bar_events") or []),
                    float(tempo),
                )
        except Exception:
            pass

        if self._crossfade_pending:
            had_prev_for_fade = (
                self._last_generated_audio is not None and len(self._last_generated_audio) > 0
            )
            audio = self._apply_transition_crossfade(
                audio,
                emotion_handoff=emotion_handoff,
            )
            if emotion_handoff and not had_prev_for_fade:
                audio = self._ease_in_emotion_handoff_bar(audio)
        audio = self._sanitize_audio(audio, expected_samples=samples)

        # ------------------------------------------------------------------
        # Emotion loudness normalization (RMS)
        # ------------------------------------------------------------------
        try:
            audio_cfg = getattr(self.config, "audio", None)
            enabled = bool(getattr(audio_cfg, "rt_emotion_loudness_norm_enabled", False)) if audio_cfg is not None else False
        except Exception:
            enabled = False
        if enabled:
            try:
                import numpy as _np

                emo_name = (emotion.name if emotion else "")
                a0 = _np.asarray(audio, dtype=_np.float32)
                rms0 = float(_np.sqrt(_np.mean(_np.square(a0)))) if a0.size else 0.0

                # Per-emotion EMA state.
                st = getattr(self, "_emotion_rms_ema", None)
                if not isinstance(st, dict):
                    st = {}
                s = st.get(emo_name)
                if not isinstance(s, dict):
                    s = {"n": 0, "rms_ema": None, "gain": 1.0}
                n = int(s.get("n", 0) or 0) + 1
                alpha = 0.30 if n <= 4 else 0.15
                rms_ema = (
                    rms0
                    if s.get("rms_ema") is None
                    else float(s.get("rms_ema")) * (1.0 - alpha) + rms0 * alpha
                )

                # Shared target RMS. Keep small to avoid clipping and preserve headroom.
                target = float(getattr(self, "_loudness_target_rms", 0.020) or 0.020)
                target = max(0.006, min(0.060, target))
                setattr(self, "_loudness_target_rms", target)

                # Compute desired gain immediately (including the very first bars of a new emotion)
                # so emotion switches don't produce loudness jumps while the EMA "warms up".
                ref_rms = float(rms_ema) if (rms_ema > 1e-6 and n >= 2) else float(rms0)
                desired = float(target / ref_rms) if ref_rms > 1e-6 else 1.0
                desired = max(0.50, min(1.60, float(desired)))

                # Hard safety clamp: never boost above what the current bar can sustain.
                # If the instantaneous RMS is already above target, this prevents the EMA-lagged
                # normalizer from "pushing" into a spike.
                max_from_instant = float(target / max(1e-6, float(rms0))) if rms0 > 1e-9 else 1.60
                max_from_instant = max(0.50, min(1.60, float(max_from_instant) * 1.02))
                clamp_hit = bool(desired > max_from_instant)
                if clamp_hit:
                    desired = float(max_from_instant)

                g_prev = float(s.get("gain", 1.0) or 1.0)
                # Smooth gain changes to avoid pumping.
                # When we just switched emotions, converge a bit faster to avoid audible jumps.
                if bool(emotion_handoff):
                    g_alpha = 0.32 if desired < g_prev else 0.20
                else:
                    g_alpha = 0.22 if desired < g_prev else 0.12
                g = float(g_prev * (1.0 - g_alpha) + desired * g_alpha)
                # Critical: also clamp the *applied* gain. Otherwise, when g_prev is high and we
                # clamp desired downward, smoothing can still leave g above the safe instantaneous cap.
                if float(rms0) > float(target):
                    g = min(float(g), float(max_from_instant))

                # Apply gain and keep peak sane.
                audio = (a0 * g).astype(_np.float32) if a0.size else audio
                pk = float(_np.max(_np.abs(audio))) if a0.size else 0.0
                if pk > 0.98:
                    audio = (audio * (0.98 / pk)).astype(_np.float32)

                s.update({"n": int(n), "rms_ema": float(rms_ema), "gain": float(g)})
                st[emo_name] = s
                setattr(self, "_emotion_rms_ema", st)

            except Exception:
                pass

        audio = self._sanitize_audio(audio, expected_samples=samples)

        # Output level smoothing (prevents big per-bar amplitude jumps when event density spikes).
        # Keeps changes subtle: only reacts when RMS jumps sharply bar-to-bar.
        applied_gain = 1.0
        rms_pre = None
        try:
            audio_cfg = getattr(self.config, "audio", None)
            enabled = bool(getattr(audio_cfg, "rt_output_level_smoothing_enabled", False)) if audio_cfg is not None else False
        except Exception:
            enabled = False
        if enabled:
            try:
                import numpy as _np
                a0 = _np.asarray(audio, dtype=_np.float32)
                rms_pre = float(_np.sqrt(_np.mean(_np.square(a0)))) if a0.size else 0.0
                prev_rms = float(getattr(self, "_debug_prev_bar_rms", 0.0) or 0.0)
                if prev_rms > 1e-6 and rms_pre > 1e-6:
                    loud_ratio = float(rms_pre / prev_rms)
                    target_ratio = loud_ratio
                    if loud_ratio >= 1.55:
                        target_ratio = 1.18
                    elif loud_ratio <= 0.55:
                        target_ratio = 0.82
                    if abs(target_ratio - loud_ratio) > 1e-6:
                        desired_gain = max(0.35, min(1.35, target_ratio / max(1e-9, loud_ratio)))
                        g_prev = float(getattr(self, "_output_leveler_gain", 1.0) or 1.0)
                        alpha = 0.35 if desired_gain < g_prev else 0.18  # faster to reduce than increase
                        applied_gain = float(g_prev * (1.0 - alpha) + desired_gain * alpha)
                        setattr(self, "_output_leveler_gain", float(applied_gain))
                        audio = (a0 * float(applied_gain)).astype(_np.float32)
                        # Keep post-gain peak in bounds.
                        pk = float(_np.max(_np.abs(audio))) if audio.size else 0.0
                        if pk > 0.98:
                            audio = (audio * (0.98 / pk)).astype(_np.float32)
                    else:
                        setattr(self, "_output_leveler_gain", float(getattr(self, "_output_leveler_gain", 1.0) or 1.0))
                setattr(self, "_debug_prev_bar_rms", float(rms_pre))
            except Exception:
                pass
        audio = self._sanitize_audio(audio, expected_samples=samples)

        # ------------------------------------------------------------------
        # Cold-start fade-in (2 bars by default)
        # Applied after all levelers/normalizers so the ramp is preserved.
        # ------------------------------------------------------------------
        try:
            fade_bars = int(getattr(self, "_startup_fade_in_bars", 0) or 0)
            enabled = bool(getattr(self, "_startup_fade_in_enabled", False)) and fade_bars > 0
        except Exception:
            enabled = False
            fade_bars = 0
        if enabled:
            # `chunks_generated` is 0-based and monotonically increases; unlike bar_index,
            # it will not reset on section boundaries or arranged loops.
            i = int(getattr(self, "chunks_generated", 0) or 0)
            if 0 <= i < fade_bars:
                sg0 = float(np.clip(float(getattr(self, "_startup_fade_in_start_gain", 0.0) or 0.0), 0.0, 1.0))
                # Half-cosine across [0..fade_bars] so with 2 bars we get: 0→0.5→1.0
                def _w(p: float) -> float:
                    p = float(np.clip(float(p), 0.0, 1.0))
                    return 0.5 - 0.5 * math.cos(math.pi * p)
                p0 = float(i) / float(fade_bars)
                p1 = float(i + 1) / float(fade_bars)
                g0 = sg0 + (1.0 - sg0) * _w(p0)
                g1 = sg0 + (1.0 - sg0) * _w(p1)
                audio = self._apply_gain_ramp(audio, start_gain=float(g0), end_gain=float(g1))
                audio = self._sanitize_audio(audio, expected_samples=samples)

        chunk = AudioChunk(
            audio=audio,
            bar_index=bar_data["bar_index"],
            emotion_name=emotion.name if emotion else "",
            tempo=tempo,
            root_note=root
        )

        try:
            from utils.rt_bar_profiler import log_rt_bar_timing_if_enabled

            log_rt_bar_timing_if_enabled(
                logger,
                prepare_ms=float(_prepare_ms),
                render_ms=float(_render_ms),
                total_ms=(time.time() - t_gen0) * 1000.0,
            )
        except Exception:
            pass

        with self.state_lock:
            self.chunks_generated += 1
            chunks_generated = int(self.chunks_generated)
        if chunks_generated == 1:
            self._schedule_background_sampler_preload()
        self._schedule_background_sampler_prefetch(
            bar_data.get("next_bar_events_preview") or [],
            tempo=float(tempo),
        )
        self._last_generated_audio = audio.copy()
        return chunk

    @staticmethod
    def _apply_gain_ramp(audio: np.ndarray, *, start_gain: float, end_gain: float) -> np.ndarray:
        """
        Apply a smooth per-sample gain ramp across this bar.
        Uses a half-cosine curve to avoid clicks at boundaries.
        """
        if audio is None:
            return audio
        x = np.asarray(audio, dtype=np.float32)
        n = int(x.shape[0]) if x.ndim >= 1 else 0
        if n <= 1:
            return audio
        sg = float(np.clip(float(start_gain), 0.0, 1.0))
        eg = float(np.clip(float(end_gain), 0.0, 1.0))
        if abs(sg - 1.0) < 1e-6 and abs(eg - 1.0) < 1e-6:
            return audio
        # Half-cosine interpolation from sg to eg.
        t = np.linspace(0.0, np.pi, n, dtype=np.float32)
        w = 0.5 - 0.5 * np.cos(t)  # 0..1
        g = (sg + (eg - sg) * w).astype(np.float32, copy=False)[:, np.newaxis]
        out = x.astype(np.float32, copy=True)
        out *= g
        return out

    def debug_last_bar_notes(self, *, channel: Optional[int] = None) -> dict:
        """
        Return a dict with the last scheduled bar's MIDI note numbers grouped by channel.
        Events are tuples: (channel, midi, velocity, start_beats, duration_beats, notes).
        """
        try:
            with self.state_lock:
                bar_idx = int(getattr(self, "_debug_last_bar_index", 0) or 0)
                events = list(getattr(self, "_debug_last_bar_events", []) or [])
        except Exception:
            bar_idx = 0
            events = []

        out = {"bar_index": bar_idx, "channels": {}}
        ch_filter = None if channel is None else int(channel)
        for ev in events:
            if not ev or len(ev) != 6:
                continue
            try:
                ch = int(ev[0])
            except Exception:
                continue
            if ch_filter is not None and ch != ch_filter:
                continue
            try:
                notes = ev[5] if isinstance(ev[5], list) else None
            except Exception:
                notes = None
            if notes:
                ns = []
                for n in notes:
                    try:
                        ns.append(int(n))
                    except Exception:
                        continue
            else:
                try:
                    ns = [int(ev[1])]
                except Exception:
                    continue
            bucket = out["channels"].setdefault(ch, set())
            for n in ns:
                bucket.add(int(n))

        # Convert sets to sorted lists for printing / JSON.
        for ch, s in list(out["channels"].items()):
            try:
                out["channels"][ch] = sorted(int(n) for n in s)
            except Exception:
                out["channels"][ch] = []
        return out

    def debug_last_bar_events_dump(self, *, channel: Optional[int] = None) -> list[str]:
        """
        Return human-readable lines for the last scheduled bar's events:
        ch midi(note) vel start dur
        """
        try:
            from info_stuff.cli_interactive import midi_note_label
        except Exception:
            midi_note_label = None

        try:
            with self.state_lock:
                bar_idx = int(getattr(self, "_debug_last_bar_index", 0) or 0)
                events = list(getattr(self, "_debug_last_bar_events", []) or [])
        except Exception:
            bar_idx = 0
            events = []
        if not events:
            return []

        ch_filter = None if channel is None else int(channel)
        rows = []
        for ev in events:
            if not ev or len(ev) != 6:
                continue
            try:
                ch, midi, vel, st, dur, notes = ev
                ch = int(ch)
            except Exception:
                continue
            if ch_filter is not None and ch != ch_filter:
                continue
            try:
                midi_i = int(midi)
                vel_i = int(vel)
                st_f = float(st)
                dur_f = float(dur)
            except Exception:
                continue
            # Polyphonic events (chords) carry their full note list in `notes`.
            # Monophonic events use `midi` only.
            note_list = None
            try:
                if isinstance(notes, (list, tuple)) and len(notes) > 0:
                    note_list = [int(n) for n in notes]
            except Exception:
                note_list = None
            if not note_list:
                note_list = [midi_i]

            if midi_note_label:
                note_s = "[" + ", ".join(f"{n}({midi_note_label(int(n))})" for n in note_list) + "]"
            else:
                note_s = "[" + ", ".join(str(int(n)) for n in note_list) + "]"
            rows.append(
                (
                    st_f,
                    f"bar {bar_idx:>3d} | ch {ch} | {note_s:<24} vel={vel_i:>3d} start={st_f:>6.2f} dur={dur_f:>5.2f}",
                )
            )
        rows.sort(key=lambda x: x[0])
        return [r[1] for r in rows]

    def _schedule_background_sampler_prefetch(self, events, *, tempo: float) -> None:
        """
        Best-effort: warm sampler caches for the *next* bar.

        Important realtime constraint: never spawn per-bar threads here (thread churn can
        create jitter/GC pressure on long runs). We already have a single prefetch worker
        thread consuming `_prefetch_queue`; just enqueue the latest request.
        """
        if not events:
            return
        try:
            audio_cfg = getattr(self.config, "audio", None)
            enabled = bool(getattr(audio_cfg, "prefetch_enabled", True)) if audio_cfg is not None else True
        except Exception:
            enabled = True
        if not enabled:
            return
        try:
            preview = list(events)
        except Exception:
            return
        if not preview:
            return
        try:
            max_ev = int(getattr(getattr(self.config, "audio", None), "prefetch_max_events", 220) or 220)
        except Exception:
            max_ev = 220
        if max_ev > 0 and len(preview) > max_ev:
            preview = preview[:max_ev]
        try:
            vel_pf = int(getattr(getattr(self.config, "audio", None), "prefetch_default_velocity", 80) or 80)
        except Exception:
            vel_pf = 80
        try:
            # Enqueue only the latest request (drop stale work).
            while True:
                try:
                    _ = self._prefetch_queue.get_nowait()
                except Empty:
                    break
                except Exception:
                    break
            try:
                self._prefetch_queue.put_nowait((preview, float(tempo), int(vel_pf)))
            except Exception:
                pass
        except Exception:
            pass

    def _ease_in_emotion_handoff_bar(self, audio: np.ndarray) -> np.ndarray:
        """When there is no previous bar to crossfade against, ramp the attack slightly."""
        if audio is None or len(audio) < 128:
            return audio
        n = int(min(len(audio) // 6, self.container.sample_rate * 0.055, 4800))
        n = max(128, n)
        out = np.array(audio, dtype=np.float32, copy=True)
        ramp = np.linspace(0.0, 1.0, n, dtype=np.float32)[:, np.newaxis]
        out[:n] *= ramp
        return out

    def debug_last_bar_trace_dump(self) -> list[str]:
        """Return compact per-bar trace lines for the last scheduled bar."""
        try:
            with self.state_lock:
                bar_idx = int(getattr(self, "_debug_last_bar_index", 0) or 0)
                tr = getattr(self, "_debug_last_bar_trace", None)
        except Exception:
            bar_idx = 0
            tr = None
        if not isinstance(tr, dict):
            return []
        # Compact, stable ordering for CLI.
        parts = []
        try:
            parts.append(f"bar={bar_idx}")
            fk = str(tr.get("feature_key", "") or "")
            if fk:
                parts.append(f"harm={fk}")
            chord = str(tr.get("chord", "") or "")
            if chord:
                parts.append(f"chord={chord}")
            role = str(tr.get("phrase_role", "") or "")
            if role:
                parts.append(f"role={role}")
            contour = str(tr.get("contour", "") or "")
            if contour:
                parts.append(f"contour={contour}")
            cad_style = str(tr.get("cadence_style", "") or "")
            if cad_style:
                parts.append(f"cadence={cad_style}")
            arc = str(tr.get("tension_arc", "") or "")
            if arc:
                parts.append(f"arc={arc}")
            mcur = tr.get("mel_cad_target_current", None)
            mnxt = tr.get("mel_cad_target_next", None)
            if mcur is not None or mnxt is not None:
                try:
                    parts.append(f"melCad(cur|next)={'' if mcur is None else int(mcur)}|{'' if mnxt is None else int(mnxt)}")
                except Exception:
                    pass
            act = str(tr.get("hit_action", "") or "")
            if act:
                parts.append(f"hit={act}")
            ov = tr.get("melody_over_arp", None)
            if ov is not None:
                parts.append(f"overlap(mel>arp)={int(ov)}")
            ten = tr.get("tension", None)
            if ten is not None:
                try:
                    parts.append(f"tension={float(ten):.2f}")
                except Exception:
                    pass
            r = tr.get("root", None)
            if r is not None:
                parts.append(f"root={int(r)}")
        except Exception:
            pass
        if not parts:
            return []
        lines = ["trace: " + " | ".join(parts)]

        # Transition handoff trace (only meaningful on bar 0 right after a switch).
        if int(bar_idx) == 0:
            try:
                gen = getattr(getattr(self, "composer", None), "gen", None)
                hctx = getattr(gen, "_emotion_transition_handoff_ctx", None) if gen is not None else None
                if isinstance(hctx, dict) and hctx:
                    prev_pc = hctx.get("previous_lead_pc", None)
                    prev_bass = hctx.get("previous_bass_midi", None)
                    prev_ch = hctx.get("previous_chord_pcs", None)
                    common = getattr(gen, "_last_handoff_bar0_common_tones", None) if gen is not None else None
                    b0 = getattr(gen, "_last_handoff_bar0_chord", None) if gen is not None else None
                    # Keep it one compact line.
                    hp = []
                    if prev_pc is not None:
                        hp.append(f"prevLeadPC={int(prev_pc)}")
                    if prev_bass is not None:
                        hp.append(f"prevBass={int(prev_bass)}")
                    if prev_ch is not None:
                        try:
                            hp.append(f"prevChordPCs={len(set(prev_ch))}")
                        except Exception:
                            pass
                    if common is not None:
                        hp.append(f"bar0Common={int(common)}")
                    if b0:
                        hp.append(f"bar0Chord={str(b0)}")
                    if hp:
                        lines.append("handoff: " + " | ".join(hp))
            except Exception:
                pass
        return lines

    def debug_last_section_harmony_dump(self) -> list[str]:
        """
        Return human-readable lines for the last generated section's harmony.
        Uses the generator's exported per-bar debug trace when available.
        """
        try:
            gen = getattr(getattr(self, "composer", None), "gen", None)
            trace = getattr(gen, "_last_section_debug_trace_by_bar", None) if gen is not None else None
        except Exception:
            trace = None
        if not isinstance(trace, list) or not trace:
            return []

        # Pull common context from the first bar (best-effort).
        try:
            cad_style = str((trace[0] or {}).get("cadence_style", "") or "")
        except Exception:
            cad_style = ""
        try:
            arc = str((trace[0] or {}).get("tension_arc", "") or "")
        except Exception:
            arc = ""

        lines: list[str] = []
        hdr = "section harmony"
        meta = []
        if cad_style:
            meta.append(f"cadence={cad_style}")
        if arc:
            meta.append(f"arc={arc}")
        if meta:
            hdr += " (" + ", ".join(meta) + ")"
        lines.append(hdr)

        # Bar-by-bar chord view (compact).
        chords: list[str] = []
        for t in trace:
            if not isinstance(t, dict):
                continue
            b = int(t.get("bar", 0) or 0)
            ch = str(t.get("chord", "") or "")
            chords.append(ch)
            fk = str(t.get("feature_key", "") or "")
            role = str(t.get("phrase_role", "") or "")
            parts = [f"bar {b:>2d}", f"chord={ch}"]
            if fk:
                parts.append(f"harm={fk}")
            if role:
                parts.append(f"role={role}")
            lines.append(" | ".join(parts))

        # Cadence pairs at phrase ends (phrase grid assumed 4 bars).
        pairs: list[str] = []
        for b in range(1, len(chords)):
            if (b % 4) == 3:
                a = chords[b - 1]
                c = chords[b]
                if a or c:
                    pairs.append(f"  bar {b-1}->{b}: {a} → {c}")
        if pairs:
            lines.append("cadence pairs (phrase ends):")
            lines.extend(pairs)
        return lines

    def _apply_transition_crossfade(
        self,
        audio: np.ndarray,
        *,
        emotion_handoff: bool = False,
    ) -> np.ndarray:
        previous = self._last_generated_audio
        self._crossfade_pending = False
        if previous is None or len(previous) == 0 or len(audio) == 0:
            return audio

        # Tempo-aware crossfade; emotion handoffs use config scale/cap (defaults favor smooth `n` swaps).
        bar_seconds = self._current_bar_seconds()
        tempo_fade = int(
            self.container.sample_rate
            * min(0.55, max(0.14, 0.22 * bar_seconds))
        )

        ratio = min(0.55, max(0.12, float(self._transition_overlap_ratio)))
        if emotion_handoff:
            ratio = min(0.52, max(0.20, ratio * 1.42))
        dynamic_fade_len = int(len(audio) * ratio)
        max_overlap = float(self._transition_max_overlap_seconds)
        max_fade_len = int(self.container.sample_rate * max(0.12, max_overlap))
        min_samples = self._transition_crossfade_samples
        target_fade_len = max(min_samples, tempo_fade, dynamic_fade_len)
        target_fade_len = min(target_fade_len, max_fade_len)
        if emotion_handoff:
            em_scale = float(
                np.clip(getattr(self, "_emotion_handoff_crossfade_scale", 0.84), 0.12, 1.0)
            )
            em_cap_s = float(
                np.clip(getattr(self, "_emotion_handoff_crossfade_max_seconds", 0.92), 0.04, 2.5)
            )
            floor = max(2048, int(self.container.sample_rate * 0.042))
            target_fade_len = max(floor, int(target_fade_len * em_scale))
            target_fade_len = min(target_fade_len, int(self.container.sample_rate * em_cap_s))
        fade_len = min(target_fade_len, len(previous), len(audio))
        if fade_len <= 0:
            return audio

        # Light loudness match over the fade region to reduce perceived "jump"
        # when switching presets with different sample content or velocity.
        prev_seg = previous[-fade_len:]
        new_seg = audio[:fade_len]
        prev_rms = float(np.sqrt(np.mean(prev_seg * prev_seg) + 1e-8))
        new_rms = float(np.sqrt(np.mean(new_seg * new_seg) + 1e-8))
        if new_rms > 1e-8 and prev_rms > 1e-8:
            gain = prev_rms / new_rms
            gain = float(np.clip(gain, 0.75, 1.35))
            audio = audio.copy()
            audio[:fade_len] *= gain

        theta = np.linspace(0.0, np.pi / 2.0, fade_len, dtype=np.float32)[:, np.newaxis]
        fade_out = np.cos(theta)
        fade_in = np.sin(theta)
        fade_out[-1] = 0.0
        fade_in[0] = 0.0
        blended = audio.copy()
        blended[:fade_len] = previous[-fade_len:] * fade_out + audio[:fade_len] * fade_in
        return blended

    @staticmethod
    def _should_suppress_drone(emotion) -> bool:
        if emotion is None:
            return False
        try:
            # User override: force drone always on.
            from audiogen_core.config import CONFIG

            if bool(getattr(CONFIG.composition, "drone_always_on", False)):
                return False
        except Exception:
            pass
        return emotion.name.lower() in {"relief"}

    def _current_bar_seconds(self) -> float:
        with self.state_lock:
            emotion = self._emotion
        tempo = effective_tempo_bpm_from_config(self.config, emotion)
        return max(0.1, 4.0 * 60.0 / max(1.0, tempo))

    def record_section_compose_time(self, compose_seconds: float) -> None:
        """Record background section/arranged compose duration (not used for buffer sizing)."""
        with self.state_lock:
            self.last_section_compose_time = float(max(0.0, compose_seconds))

    def _record_bar_render_timing(self, total_dt: float) -> None:
        with self.state_lock:
            dt = float(max(0.0, total_dt))
            self.last_bar_render_time = dt
            self.last_generation_time = dt
            prev_max = float(self.max_bar_render_time or 0.0)
            decayed = prev_max * 0.985
            mx = float(max(decayed, dt))
            self.max_bar_render_time = mx
            self.max_generation_time = mx

    def _bar_render_times_for_buffer_policy(self) -> tuple[float, float]:
        with self.state_lock:
            return (
                float(self.last_bar_render_time or 0.0),
                float(self.max_bar_render_time or 0.0),
            )

    def _playback_warmup_complete(self) -> bool:
        """True once at least one bar was rendered and playback has started."""
        with self.state_lock:
            return bool(self._playing) and int(self.chunks_generated or 0) >= 1

    def _buffer_fill_stress_signal(self, buffer_fill: int) -> bool:
        """Empty queue is only a stress signal after warmup (avoids false emergency at startup)."""
        if int(buffer_fill) > 0:
            return True
        return self._playback_warmup_complete()

    def _runtime_generation_mode(self) -> str:
        """Return the cached CPU ladder mode (updated only on the generation thread)."""
        with self.state_lock:
            return str(getattr(self, "_rt_mode_stable", "normal") or "normal")

    def _advance_runtime_mode_ladder(self) -> str:
        def _severity(mode_name: str) -> int:
            m = str(mode_name or "normal").strip().lower()
            if m == "normal":
                return 0
            if m == "balanced":
                return 1
            if m == "safe":
                return 2
            if m == "emergency":
                return 3
            return 0

        def _base_mode_unlocked(
            *,
            buffer_fill: int,
            bar_seconds: float,
            generation_ratio: float,
            underruns: int,
            now: float,
            fill_stress: bool,
        ) -> str:
            low_fill = int(buffer_fill) <= 0 and fill_stress
            very_low_fill = int(buffer_fill) <= 2 and fill_stress

            prev_u = int(getattr(self, "_emergency_last_underruns_seen", 0) or 0)
            u_delta = max(0, int(underruns) - int(prev_u))
            self._emergency_last_underruns_seen = int(underruns)

            engage = (
                (generation_ratio >= 1.08)
                or low_fill
                or (u_delta >= 1 and very_low_fill)
            )
            release = (int(buffer_fill) >= 4) and (generation_ratio <= 0.75) and (u_delta == 0)
            min_hold_s = 6.0
            last_change = float(getattr(self, "_emergency_last_change_time", 0.0) or 0.0)
            active = bool(getattr(self, "_emergency_active", False))
            if active:
                if release and (now - last_change) >= float(min_hold_s):
                    self._emergency_active = False
                    self._emergency_reason = ""
                    self._emergency_last_change_time = float(now)
            else:
                if engage:
                    self._emergency_active = True
                    if generation_ratio >= 1.0:
                        self._emergency_reason = f"generation_ratio={generation_ratio:.2f}"
                    elif u_delta >= 1:
                        self._emergency_reason = "underrun"
                    else:
                        self._emergency_reason = f"buffer_fill={int(buffer_fill)}"
                    self._emergency_last_change_time = float(now)
            if bool(getattr(self, "_emergency_active", False)):
                return "emergency"

            if int(getattr(self, "_rt_watchdog_safe_bars_remaining", 0) or 0) > 0:
                return "safe"

            if low_fill or generation_ratio >= 0.82 or int(underruns) >= 4:
                return "safe"
            if very_low_fill or generation_ratio >= 0.55 or int(underruns) >= 2:
                return "balanced"
            return "normal"

        with self.state_lock:
            buffer_fill = int(self.buffer_controller.effective_fill_bars())
            emotion = self._emotion
            tempo = effective_tempo_bpm_from_config(self.config, emotion)
            bar_seconds = max(0.1, 4.0 * 60.0 / max(1.0, float(tempo)))
            last_bar = float(self.last_bar_render_time or 0.0)
            generation_ratio = float(last_bar) / max(bar_seconds, 0.1)
            underruns = int(self.telemetry.buffer_underruns)
            playing = bool(self._playing)
            chunks = int(self.chunks_generated or 0)
            fill_stress = int(buffer_fill) > 0 or (playing and chunks >= 1)
            try:
                now = float(time.time())
            except Exception:
                now = 0.0

            base = _base_mode_unlocked(
                buffer_fill=buffer_fill,
                bar_seconds=bar_seconds,
                generation_ratio=generation_ratio,
                underruns=underruns,
                now=now,
                fill_stress=bool(fill_stress),
            )
            if base == "emergency":
                self._rt_mode_stable = "emergency"
                self._rt_mode_candidate = None
                self._rt_mode_candidate_streak = 0
                return "emergency"

            try:
                a = getattr(self.config, "audio", None)
                hyst_enabled = bool(getattr(a, "rt_mode_hysteresis_enabled", True))
                hold_promote = max(1, int(getattr(a, "rt_mode_promote_hold_bars", 3) or 3))
                hold_demote = max(1, int(getattr(a, "rt_mode_demote_hold_bars", 1) or 1))
            except Exception:
                hyst_enabled = True
                hold_promote = 3
                hold_demote = 1

            if not hyst_enabled:
                self._rt_mode_stable = str(base)
                self._rt_mode_candidate = None
                self._rt_mode_candidate_streak = 0
                return str(base)

            tick = int(self.chunks_generated or 0)
            last_tick = int(getattr(self, "_rt_mode_last_eval_chunk_index", -1) or -1)
            stable = str(getattr(self, "_rt_mode_stable", "normal") or "normal")
            candidate = getattr(self, "_rt_mode_candidate", None)
            streak = int(getattr(self, "_rt_mode_candidate_streak", 0) or 0)

            if tick != last_tick:
                self._rt_mode_last_eval_chunk_index = int(tick)
                if base == stable:
                    candidate = None
                    streak = 0
                else:
                    hold = hold_demote if _severity(base) > _severity(stable) else hold_promote
                    if candidate == base:
                        streak += 1
                    else:
                        candidate = base
                        streak = 1
                    if streak >= int(hold):
                        stable = str(base)
                        candidate = None
                        streak = 0
                rem = int(getattr(self, "_rt_watchdog_safe_bars_remaining", 0) or 0)
                if rem > 0:
                    self._rt_watchdog_safe_bars_remaining = int(max(0, rem - 1))

            self._rt_mode_stable = str(stable)
            self._rt_mode_candidate = candidate
            self._rt_mode_candidate_streak = int(streak)
            return str(stable)

    def _update_rt_render_watchdog(self, *, render_seconds: float, bar_seconds: float) -> None:
        try:
            a = getattr(self.config, "audio", None)
            enabled = bool(getattr(a, "rt_render_watchdog_enabled", True))
            threshold = float(getattr(a, "rt_render_watchdog_ratio", 0.92) or 0.92)
            hold = max(1, int(getattr(a, "rt_render_watchdog_hold_bars", 6) or 6))
        except Exception:
            enabled = True
            threshold = 0.92
            hold = 6
        if not enabled:
            return
        ratio = float(render_seconds) / max(1e-6, float(bar_seconds))
        self._rt_watchdog_last_ratio = float(ratio)
        if ratio >= float(threshold):
            prev = int(getattr(self, "_rt_watchdog_safe_bars_remaining", 0) or 0)
            self._rt_watchdog_safe_bars_remaining = int(max(prev, hold))
            self._rt_watchdog_triggered_count = int(getattr(self, "_rt_watchdog_triggered_count", 0) or 0) + 1
            logger.warning(
                "RT render watchdog engaged: ratio=%.2f hold_bars=%d",
                float(ratio),
                int(self._rt_watchdog_safe_bars_remaining),
            )

    def _update_generation_stage_telemetry(self) -> None:
        try:
            raw = dict(getattr(self.renderer, "last_stage_timing_ms", {}) or {})
        except Exception:
            raw = {}
        if not raw:
            return
        last = dict(getattr(self, "_gen_stage_last_ms", {}) or {})
        ema = dict(getattr(self, "_gen_stage_ema_ms", {}) or {})
        alpha = 0.22
        for key in ("mono", "chords", "mix", "master", "total"):
            v = float(raw.get(key, 0.0) or 0.0)
            last[key] = max(0.0, v)
            prev = float(ema.get(key, 0.0) or 0.0)
            ema[key] = float((1.0 - alpha) * prev + alpha * last[key])
        self._gen_stage_last_ms = last
        self._gen_stage_ema_ms = ema
        self._gen_culprit = self._dominant_generation_stage()

    def _dominant_generation_stage(self) -> str:
        try:
            stages = dict(getattr(self, "_gen_stage_ema_ms", {}) or {})
        except Exception:
            stages = {}
        keys = ("mono", "chords", "mix", "master")
        best_k = "unknown"
        best_v = -1.0
        for k in keys:
            try:
                v = float(stages.get(k, 0.0) or 0.0)
            except Exception:
                v = 0.0
            if v > best_v:
                best_v = v
                best_k = k
        if best_v <= 1e-6:
            return "unknown"
        return str(best_k)

    def _render_pressure_ratio(self) -> float:
        try:
            bar_seconds = float(self._current_bar_seconds())
        except Exception:
            bar_seconds = 0.1
        try:
            with self.state_lock:
                last_bar = float(self.last_bar_render_time or 0.0)
        except Exception:
            last_bar = 0.0
        return float(last_bar) / max(0.1, float(bar_seconds))

    def _rt_prewarm_flags(self):
        audio = getattr(self.config, "audio", None)
        if audio is None:
            return False, False, False, True
        chord = bool(getattr(audio, "rt_chord_cache_prewarm_enabled", True))
        mono = bool(getattr(audio, "rt_mono_cache_prewarm_enabled", True))
        mix = bool(getattr(audio, "rt_mix_master_warmup_enabled", True))
        bg = bool(getattr(audio, "rt_prewarm_background", True))
        return chord, mono, mix, bg

    def _run_rt_prewarm(self, *, root: int, emotion=None) -> None:
        chord_on, mono_on, mix_on, _bg = self._rt_prewarm_flags()
        if not chord_on and not mono_on and not mix_on:
            return
        try:
            from audio.rt_prewarm import run_rt_prewarm

            tempo = float(effective_tempo_bpm_from_config(self.config))
            sr = int(getattr(self.config.audio, "sample_rate", 44100) or 44100)
            run_rt_prewarm(
                self,
                root_note=int(root),
                tempo_bpm=tempo,
                sample_rate=sr,
                chord_cache=bool(chord_on),
                mono_cache=bool(mono_on),
                mix_master=bool(mix_on) and not bool(getattr(self, "_rt_mix_master_warmed", False)),
            )
            if mix_on:
                self._rt_mix_master_warmed = True
        except Exception:
            pass

    def schedule_rt_prewarm(self, *, root: int, emotion=None) -> None:
        chord_on, mono_on, mix_on, bg = self._rt_prewarm_flags()
        if not chord_on and not mono_on and not mix_on:
            return
        if bg:
            t = getattr(self, "_rt_prewarm_thread", None)
            if t is not None and t.is_alive():
                return
            self._rt_prewarm_thread = threading.Thread(
                target=self._run_rt_prewarm,
                kwargs={"root": int(root), "emotion": emotion},
                daemon=True,
            )
            self._rt_prewarm_thread.start()
        else:
            self._run_rt_prewarm(root=int(root), emotion=emotion)


    def _should_fast_master(self, mode: str) -> bool:
        """
        Skip limiter oversample / soft-clip when close to or over real-time.
        Reverb and delay returns still run (see MasterBus.process fast_path).
        """
        if mode in {"emergency"}:
            return True
        try:
            audio = getattr(self.config, "audio", None)
            thr = float(getattr(audio, "rt_fast_master_ratio", 0.88) or 0.88)
        except Exception:
            thr = 0.88
        ratio = self._render_pressure_ratio()
        try:
            underruns = int(getattr(self.telemetry, "buffer_underruns", 0) or 0)
        except Exception:
            underruns = 0
        if ratio >= float(thr):
            return True
        if self._dominant_generation_stage() == "master" and ratio >= max(0.65, float(thr) - 0.12):
            return True
        if mode == "balanced" and (underruns >= 2 or ratio >= 0.82):
            return True
        return False

    def _runtime_reverb_quality_tier(self, mode: str) -> str:
        m = str(mode or "normal").strip().lower()
        rank = {"emergency": 0, "safe": 1, "balanced": 2, "high_rt": 3, "high": 4}
        if m in {"emergency"}:
            tier = "safe"
        elif m in {"safe"}:
            tier = "safe"
        elif m in {"balanced"}:
            tier = "balanced"
        else:
            try:
                audio = getattr(self.config, "audio", None)
                tier = str(getattr(audio, "rt_reverb_default_tier", "balanced") or "balanced").strip().lower()
            except Exception:
                tier = "balanced"
            try:
                audio = getattr(self.config, "audio", None)
                adaptive = bool(getattr(audio, "rt_reverb_adaptive_high_enabled", True)) if audio else True
                hi_thr = float(getattr(audio, "rt_reverb_adaptive_high_ratio", 0.72) or 0.72) if audio else 0.72
            except Exception:
                adaptive, hi_thr = True, 0.72
            if adaptive and self._render_pressure_ratio() <= float(hi_thr):
                try:
                    fill = int(self.buffer_controller.effective_fill_bars())
                    tgt = int(getattr(self, "_target_buffer_bars", 8) or 8)
                except Exception:
                    fill, tgt = 0, 8
                if fill >= max(2, tgt // 2):
                    tier = "high"
        try:
            a = getattr(self.config, "audio", None)
            if (
                m not in {"safe", "emergency"}
                and a is not None
                and bool(getattr(a, "rt_preserve_spatial_fx_quality", True))
            ):
                floor = str(getattr(a, "rt_reverb_min_quality_tier", "balanced") or "balanced").strip().lower()
                if int(rank.get(tier, 2)) < int(rank.get(floor, 2)):
                    tier = floor
        except Exception:
            pass
        return tier

    @staticmethod
    def _runtime_reverb_quality_tier_static(mode: str) -> str:
        """Static mapping for tests that call the old static helper."""
        m = str(mode or "normal").strip().lower()
        if m in {"emergency"}:
            tier = "safe"
        elif m in {"safe"}:
            tier = "safe"
        elif m in {"balanced"}:
            tier = "balanced"
        else:
            tier = "high"
        try:
            from audiogen_core.config import CONFIG

            a = getattr(CONFIG, "audio", None)
            if (
                m not in {"safe", "emergency"}
                and a is not None
                and bool(getattr(a, "rt_preserve_spatial_fx_quality", True))
            ):
                floor = str(getattr(a, "rt_reverb_min_quality_tier", "balanced") or "balanced").strip().lower()
                rank = {"emergency": 0, "safe": 1, "balanced": 2, "high": 3}
                if int(rank.get(tier, 3)) < int(rank.get(floor, 2)):
                    tier = floor
        except Exception:
            pass
        return tier

    def _should_bypass_master_multiband(self, mode: str) -> bool:
        try:
            audio = getattr(self.config, "audio", None)
            if audio is not None and hasattr(audio, "rt_bypass_master_multiband"):
                if bool(getattr(audio, "rt_bypass_master_multiband", True)):
                    return True
                return False
            policy = str(getattr(audio, "master_inserts_rt_bypass_mode", "realtime") or "realtime").lower()
        except Exception:
            policy = "realtime"
        if policy == "never":
            return False
        if policy in {"realtime", "live", "all"}:
            return True
        if policy == "balanced":
            return mode in {"normal", "safe", "balanced", "emergency"}
        return mode in {"safe", "emergency"}

    def _should_bypass_master_eq(self, mode: str) -> bool:
        try:
            audio = getattr(self.config, "audio", None)
            if audio is not None and bool(getattr(audio, "rt_bypass_master_eq", False)):
                return True
            policy = str(getattr(audio, "master_inserts_rt_bypass_mode", "realtime") or "realtime").lower()
        except Exception:
            policy = "realtime"
        if policy == "never":
            return False
        if policy in {"realtime", "live", "all"}:
            return False
        if policy == "balanced":
            return mode in {"safe", "balanced", "emergency"}
        return mode in {"safe", "emergency"}

    def _should_bypass_master_inserts(self, mode: str) -> bool:
        """Bypass both multiband and master EQ (legacy aggregate flag)."""
        return self._should_bypass_master_multiband(mode) and self._should_bypass_master_eq(mode)

    def _runtime_target_notes_per_bar(self) -> float:
        mode = self._runtime_generation_mode()
        base = float(getattr(self.config.composition, "melody_target_notes_per_bar", 6.0))
        base = max(2.0, min(12.0, base))
        if mode == "emergency":
            return base * (3.0 / 6.0)
        if mode == "safe":
            return base * (4.0 / 6.0)
        if mode == "balanced":
            return base * (5.0 / 6.0)
        return base

    @staticmethod
    def _clamp01(v: float) -> float:
        return float(max(0.0, min(1.0, float(v))))

    @staticmethod
    def _smoothstep(t: float) -> float:
        x = float(max(0.0, min(1.0, float(t))))
        return x * x * (3.0 - 2.0 * x)

    def _set_fx_state(self, st: dict) -> None:
        mb = getattr(self.container, "master_bus", None)
        rev = getattr(self.container, "reverb", None)
        if rev is not None:
            try:
                rev.set_rt60(float(st.get("reverb_rt60", getattr(rev, "rt60", 0.8))))
            except Exception:
                pass
            try:
                rev.set_damping(float(st.get("reverb_damping", getattr(rev, "damping", 0.5))))
            except Exception:
                pass
            try:
                rev.set_wet(float(st.get("reverb_wet_proc", getattr(rev, "wet", 0.3))))
            except Exception:
                pass
        if mb is not None:
            try:
                mb.set_reverb_return_wet(float(st.get("reverb_return_wet", getattr(mb, "reverb_return_wet", 0.5))))
            except Exception:
                pass
            try:
                drive = float(st.get("distortion_drive", getattr(getattr(mb, "distortion", None), "drive", 1.35)))
                mix = float(st.get("distortion_mix", getattr(mb, "distortion_return_level", 0.08)))
                en = bool(mix > 1e-6)
                mb.set_master_distortion(enabled=en, drive=float(max(1.0, min(3.0, drive))), mix=self._clamp01(mix))
            except Exception:
                pass

    def _infer_fx_transition_bars(self, style_name: str, emotion_name: str) -> int:
        style = str(style_name or "").strip().lower()
        emo = str(emotion_name or "").strip().lower()
        bars = 4
        if style in {"ambient"}:
            bars += 2
        elif style in {"jazz"}:
            bars -= 1
        elif style in {"pop"}:
            bars += 0
        if emo in {"sadness", "grief", "relief", "love", "neutral"}:
            bars += 1
        elif emo in {"excitement", "surprise", "anger"}:
            bars -= 1
        return int(max(2, min(8, bars)))

    def queue_fx_preset_transition(
        self,
        *,
        style_name: str = "",
        emotion_name: str = "",
        start_state: Optional[dict] = None,
    ) -> None:
        """
        Queue a short bar-based transition to new FX preset targets.
        Targets are taken from current CONFIG.audio; start state can be provided
        by the caller to avoid jumps when config was already applied.
        """
        audio = getattr(self.config, "audio", None)
        if audio is None:
            return
        mb = getattr(self.container, "master_bus", None)
        rev = getattr(self.container, "reverb", None)
        if mb is None and rev is None:
            return
        start = dict(start_state or {})
        if not start:
            try:
                if mb is not None:
                    start["reverb_return_wet"] = float(getattr(mb, "reverb_return_wet", 0.5) or 0.5)
                    start["distortion_drive"] = float(
                        getattr(getattr(mb, "distortion", None), "drive", 1.35) or 1.35
                    )
                    start["distortion_mix"] = float(getattr(mb, "distortion_return_level", 0.08) or 0.08)
            except Exception:
                pass
            try:
                if rev is not None:
                    start["reverb_rt60"] = float(getattr(rev, "rt60", 0.8) or 0.8)
                    start["reverb_damping"] = float(getattr(rev, "damping", 0.5) or 0.5)
                    start["reverb_wet_proc"] = float(getattr(rev, "wet", 0.3) or 0.3)
            except Exception:
                pass

        target = {
            "reverb_rt60": float(getattr(audio, "reverb_rt60", 0.8) or 0.8),
            "reverb_damping": float(getattr(audio, "reverb_damping", 0.5) or 0.5),
            "reverb_wet_proc": float(getattr(audio, "reverb_wet", 0.5) or 0.5),
            "reverb_return_wet": float(getattr(audio, "reverb_wet", 0.5) or 0.5),
            "distortion_drive": float(getattr(audio, "distortion_drive", 1.35) or 1.35),
            "distortion_mix": float(
                getattr(audio, "distortion_bus_return_level", getattr(audio, "distortion_mix", 0.08)) or 0.08
            ),
        }
        bars = self._infer_fx_transition_bars(str(style_name), str(emotion_name))
        self._fx_preset_transition = {
            "step": 0,
            "bars": int(max(1, bars)),
            "start": start,
            "target": target,
        }
        # Restore "from" state immediately (config application may have already jumped to target).
        self._set_fx_state(start)
        try:
            self._fx_base_reverb_wet = float(start.get("reverb_return_wet", self._fx_base_reverb_wet or 0.5))
            self._fx_base_dist = {
                "enabled": bool(float(start.get("distortion_mix", 0.0) or 0.0) > 1e-6),
                "drive": float(start.get("distortion_drive", 1.35) or 1.35),
                "mix": float(start.get("distortion_mix", 0.08) or 0.08),
            }
        except Exception:
            pass

    def _apply_fx_preset_transition_step(self) -> None:
        tr = getattr(self, "_fx_preset_transition", None)
        if not isinstance(tr, dict):
            return
        bars = int(max(1, int(tr.get("bars", 1) or 1)))
        step = int(max(0, int(tr.get("step", 0) or 0)))
        start = dict(tr.get("start", {}) or {})
        target = dict(tr.get("target", {}) or {})
        # Advance one bar per generated bar.
        u = self._smoothstep(float(step + 1) / float(bars))
        keys = ("reverb_rt60", "reverb_damping", "reverb_wet_proc", "reverb_return_wet", "distortion_drive", "distortion_mix")
        cur = {}
        for k in keys:
            try:
                a = float(start.get(k, target.get(k, 0.0)) or 0.0)
                b = float(target.get(k, a) or a)
                cur[k] = float(a + (b - a) * float(u))
            except Exception:
                continue
        self._set_fx_state(cur)
        step += 1
        if step >= bars:
            self._fx_preset_transition = None
            try:
                self._fx_base_reverb_wet = float(target.get("reverb_return_wet", self._fx_base_reverb_wet or 0.5))
                self._fx_base_dist = {
                    "enabled": bool(float(target.get("distortion_mix", 0.0) or 0.0) > 1e-6),
                    "drive": float(target.get("distortion_drive", 1.35) or 1.35),
                    "mix": float(target.get("distortion_mix", 0.08) or 0.08),
                }
            except Exception:
                pass
        else:
            tr["step"] = int(step)
            self._fx_preset_transition = tr

    def _compute_target_buffer_bars(self) -> int:
        self._maybe_decay_rt_buffer_boost()
        last_bar, max_bar = self._bar_render_times_for_buffer_policy()
        target = self.buffer_controller.compute_target_buffer_bars(
            current_bar_seconds=self._current_bar_seconds(),
            last_generation_time=last_bar,
            max_generation_time=max_bar,
            minimum_target=self._target_buffer_bars,
        )
        # Hard cap to prevent runaway targets (e.g. one slow bar causing 50+ bar target).
        try:
            cap = int(getattr(getattr(self.config, "audio", None), "target_buffer_cap_bars", 24) or 24)
        except Exception:
            cap = 24
        if cap > 0:
            target = min(int(target), int(max(2, cap)))
        with self.section_lock:
            pending_transition = self.section_scheduler.pending_emotion is not None
        if pending_transition:
            # Do not cap as aggressively as a few bars — that caused underruns during crossfades.
            transition_cap = max(14, self._transition_queue_cap_bars + 6)
            return max(2, min(target, transition_cap))
        return target

    def _compute_startup_preroll_bars(self) -> int:
        self._maybe_decay_rt_buffer_boost()
        last_bar, max_bar = self._bar_render_times_for_buffer_policy()
        bars = self.buffer_controller.compute_startup_preroll_bars(
            current_bar_seconds=self._current_bar_seconds(),
            last_generation_time=last_bar,
            max_generation_time=max_bar,
            # Start audio sooner (1 bar) while keeping the rest of the buffer policy intact.
            minimum_preroll=max(1, self._startup_preroll_bars),
            minimum_target=self._target_buffer_bars,
        )
        try:
            cap = int(getattr(self.config.audio, "startup_preroll_cap_bars", 3) or 3)
        except Exception:
            cap = 3
        return max(1, min(int(bars), max(1, cap)))

    def _request_stream_recovery(self):
        self.output_stream.request_recovery()

    def _maybe_decay_rt_buffer_boost(self) -> None:
        try:
            audio_cfg = getattr(self.config, "audio", None)
            enabled = bool(getattr(audio_cfg, "underrun_auto_buffer_boost_enabled", True))
            decay_s = float(getattr(audio_cfg, "underrun_auto_buffer_boost_decay_seconds", 10.0) or 10.0)
        except Exception:
            enabled = True
            decay_s = 10.0
        if not enabled:
            return
        boost = int(getattr(self, "_rt_extra_buffer_bars", 0) or 0)
        if boost <= 0:
            return
        try:
            now = float(time.time())
        except Exception:
            now = 0.0
        last_u = float(getattr(self, "_rt_last_underflow_time", 0.0) or 0.0)
        last_decay = float(getattr(self, "_rt_last_buffer_decay_time", 0.0) or 0.0)
        if (now - last_u) < max(2.0, float(decay_s)):
            return
        if (now - last_decay) < 2.0:
            return
        boost = max(0, boost - 1)
        self._rt_extra_buffer_bars = int(boost)
        self._rt_last_buffer_decay_time = now
        base_t = int(getattr(self, "_base_target_buffer_bars", self._target_buffer_bars) or self._target_buffer_bars)
        base_p = int(
            getattr(self, "_base_startup_preroll_bars", self._startup_preroll_bars) or self._startup_preroll_bars
        )
        self._target_buffer_bars = max(2, int(base_t) + int(boost))
        self._startup_preroll_bars = max(1, int(base_p) + min(2, int(boost)))
        logger.info(
            "RT buffer boost decayed: extra=%d target=%d preroll=%d",
            int(boost),
            int(self._target_buffer_bars),
            int(self._startup_preroll_bars),
        )

    def _apply_rt_underflow_buffer_boost(self) -> None:
        try:
            audio_cfg = getattr(self.config, "audio", None)
            enabled = bool(getattr(audio_cfg, "underrun_auto_buffer_boost_enabled", True))
            trigger = int(getattr(audio_cfg, "underrun_auto_buffer_boost_trigger_count", 3) or 3)
            step = int(getattr(audio_cfg, "underrun_auto_buffer_boost_step_bars", 1) or 1)
            max_extra = int(getattr(audio_cfg, "underrun_auto_buffer_boost_max_extra_bars", 6) or 6)
        except Exception:
            enabled = True
            trigger, step, max_extra = 3, 1, 6
        if not enabled:
            return
        try:
            now = float(time.time())
        except Exception:
            now = 0.0
        self._rt_last_underflow_time = now
        burst = int(getattr(self, "_rt_underflow_burst_count", 0) or 0) + 1
        self._rt_underflow_burst_count = burst
        if burst < max(1, trigger):
            return
        self._rt_underflow_burst_count = 0
        cur = int(getattr(self, "_rt_extra_buffer_bars", 0) or 0)
        nxt = min(max(0, max_extra), cur + max(1, step))
        if nxt == cur:
            return
        self._rt_extra_buffer_bars = int(nxt)
        base_t = int(getattr(self, "_base_target_buffer_bars", self._target_buffer_bars) or self._target_buffer_bars)
        base_p = int(
            getattr(self, "_base_startup_preroll_bars", self._startup_preroll_bars) or self._startup_preroll_bars
        )
        self._target_buffer_bars = max(2, int(base_t) + int(nxt))
        self._startup_preroll_bars = max(1, int(base_p) + min(2, int(nxt)))
        logger.warning(
            "RT buffer boost engaged after callback underflows: extra=%d target=%d preroll=%d",
            int(nxt),
            int(self._target_buffer_bars),
            int(self._startup_preroll_bars),
        )

    def _maybe_recover_stream(self):
        if not self.output_stream.recovery_requested:
            return
        if sd is None:
            return
        now = time.time()
        if now - self._last_recovery_attempt_time < 1.0:
            return
        self._last_recovery_attempt_time = now
        self.telemetry.note_stream_recovery_attempt()
        logger.warning("Attempting audio stream recovery (%d)", self.telemetry.stream_recovery_attempts)
        self.output_stream.failed = False
        self._init_audio_stream()

    def _log_stream_status(self, status):
        # PortAudio output_underflow usually indicates callback starvation (CPU scheduling),
        # not necessarily that our ring buffer is empty. Track it separately from queue underruns.
        if getattr(status, "output_underflow", False):
            self.telemetry.note_callback_underflow()
            self._apply_rt_underflow_buffer_boost()
            now = time.time()
            if now - self._last_portaudio_underflow_log_ts >= 1.0:
                self._last_portaudio_underflow_log_ts = now
                logger.warning(
                    "PortAudio output_underflow (callback starved); underruns=%d underflows=%d status=%s",
                    int(getattr(self.telemetry, "buffer_underruns", 0) or 0),
                    int(getattr(self.telemetry, "callback_underflows", 0) or 0),
                    status,
                )
        if status and (not getattr(status, "priming_output", False)):
            self.telemetry.log_stream_status(status)

    def _update_playback_telemetry(self, frames: int):
        with self.state_lock:
            last_gen = float(self.last_bar_render_time or 0.0)
            max_gen = float(self.max_bar_render_time or 0.0)
            target_bars = int(getattr(self, "_telemetry_target_buffer_bars", 0) or 0)
        self.telemetry.note_callback(
            frames=frames,
            buffer_fill=self.buffer_controller.effective_fill_bars(),
            target_buffer_bars=target_bars,
            last_generation_time=last_gen,
            max_generation_time=max_gen,
        )

    def _sanitize_audio(self, audio: np.ndarray, expected_samples: Optional[int] = None) -> np.ndarray:
        if audio is None:
            target_len = max(0, int(expected_samples or 0))
            return np.zeros((target_len, 2), dtype=np.float32)

        audio = np.asarray(audio, dtype=np.float32)
        if audio.ndim == 1:
            audio = np.column_stack([audio, audio])
        elif audio.ndim != 2:
            target_len = max(0, int(expected_samples or 0))
            logger.warning("Unexpected audio shape %s; substituting silence", getattr(audio, "shape", None))
            return np.zeros((target_len, 2), dtype=np.float32)

        if audio.shape[1] == 1:
            audio = np.repeat(audio, 2, axis=1)
        elif audio.shape[1] > 2:
            audio = audio[:, :2]

        audio = np.nan_to_num(audio, nan=0.0, posinf=0.0, neginf=0.0, copy=False)

        if expected_samples is not None:
            expected_samples = max(0, int(expected_samples))
            current = len(audio)
            if current < expected_samples:
                padded = np.zeros((expected_samples, 2), dtype=np.float32)
                padded[:current] = audio
                audio = padded
            elif current > expected_samples:
                audio = audio[:expected_samples]

        peak = float(np.max(np.abs(audio))) if len(audio) else 0.0
        if peak > 1.0:
            audio = np.tanh(audio).astype(np.float32, copy=False)
        elif audio.dtype != np.float32:
            audio = audio.astype(np.float32, copy=False)

        return audio

    def _dequeue_audio_frames(self, frames: int) -> np.ndarray:
        with self.state_lock:
            paused = self._paused
            running = self._running
        return self.buffer_controller.dequeue_audio_frames(
            frames=frames,
            running=running,
            paused=paused,
            on_bar_complete=self._on_bar_played,
        )

    def _on_bar_played(self):
        with self.state_lock:
            self.total_bars_played += 1
        self.section_scheduler.note_bar_played()

    def _audio_callback(self, outdata, frames, _time_info, status):
        try:
            self._log_stream_status(status)
            with self.state_lock:
                paused = self._paused
                running = self._running
            fill_before = self.buffer_controller.dequeue_audio_frames_into(
                outdata,
                frames,
                running=running,
                paused=paused,
                on_bar_complete=self._on_bar_played,
            )
            with self.state_lock:
                last_gen = float(self.last_bar_render_time or 0.0)
                max_gen = float(self.max_bar_render_time or 0.0)
                target_bars = int(getattr(self, "_telemetry_target_buffer_bars", 0) or 0)
            self.telemetry.note_callback(
                frames=frames,
                buffer_fill=fill_before,
                target_buffer_bars=target_bars,
                last_generation_time=last_gen,
                max_generation_time=max_gen,
            )
            # Per-underrun detail goes to logs/runtime.log (console filters this substring).
            try:
                prev = getattr(self, "_last_logged_underruns", 0)
                cur = int(getattr(self.telemetry, "buffer_underruns", 0))
                if cur > prev:
                    setattr(self, "_last_logged_underruns", cur)
                    fill = self.buffer_controller.effective_fill_bars()
                    target_bars = target_bars
                    with self.state_lock:
                        mode_label = str(getattr(self, "_rt_mode_stable", "normal") or "normal")
                    logger.warning(
                        "BUFFER UNDERRUN #%d (fill=%db target=%db last_gen=%.1fms max_gen=%.1fms mode=%s)",
                        cur,
                        int(fill),
                        int(target_bars),
                        float(last_gen) * 1000.0,
                        float(max_gen) * 1000.0,
                        mode_label,
                    )
            except Exception:
                pass
        except Exception:
            logger.exception("Audio callback failed; outputting silence")
            outdata.fill(0.0)
            self.output_stream.failed = True
            self._request_stream_recovery()

    def _generation_loop(self):
        while True:
            with self.state_lock:
                if not self._running:
                    break
                paused = self._paused
                emotion_ok = self._emotion is not None
            if paused:
                # Keep the bar clock aligned with what is actually heard: while paused the
                # audio callback outputs silence and does not drain chunks. If we kept
                # generating here, resume would play a long backlog and feel "late" vs wall clock.
                time.sleep(0.05)
                continue
            if not emotion_ok:
                time.sleep(0.1)
                continue

            # Count queued bars + the bar currently being played from (matches refill need).
            ahead = self.buffer_controller.effective_fill_bars()
            target = max(self._target_buffer_bars, self._compute_target_buffer_bars())
            self._telemetry_target_buffer_bars = target

            if self.section_scheduler.should_pre_generate():
                self.section_scheduler.ensure_pregen_enqueued()

            self._advance_runtime_mode_ladder()

            if ahead < target:
                # Refill in bursts so one slow render cannot empty the queue before the next tick.
                mode = self._runtime_generation_mode()
                max_burst = int(self._gen_burst_max_bars)
                # When CPU is tight, smaller bursts reduce contention with the audio callback.
                if mode == "safe":
                    max_burst = min(max_burst, 4)
                elif mode == "balanced":
                    max_burst = min(max_burst, 8)
                n = 0
                while ahead < target and n < max_burst:
                    with self.state_lock:
                        if not self._running:
                            break
                    chunk = self._generate_next_bar()
                    if chunk is None:
                        break
                    with self.state_lock:
                        if not self._running:
                            break
                    if not self.buffer_controller.write_blocking(chunk, timeout=0.5):
                        break
                    n += 1
                    ahead = self.buffer_controller.effective_fill_bars()
                if ahead >= target:
                    time.sleep(0.002)
            else:
                time.sleep(0.005)

    def run(self):
        # If there are no audio devices, don't wait for a large preroll just to
        # advance the internal bar clock (headless mode).
        headless = os.getenv("AUDIOGEN_HEADLESS", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        try:
            if headless:
                pass
            elif sd is None:
                headless = True
            else:
                devs = sd.query_devices()
                headless = (not devs) or (len(devs) <= 0)
        except Exception:
            headless = False

        preroll_target = max(self._startup_preroll_bars, self._compute_startup_preroll_bars())
        if headless:
            preroll_target = min(int(preroll_target), 1)
        while len(self.buffer) < preroll_target and self._running:
            time.sleep(0.1)
        with self.state_lock:
            self._playing = True
        # Start audio only after preroll is ready.
        self._last_logged_underruns = int(getattr(self.telemetry, "buffer_underruns", 0))
        self._init_audio_stream()

        while self._running:
            with self.state_lock:
                if self._paused:
                    sleep_time = 0.1
                else:
                    sleep_time = 0.05
            # Headless mode: if the OS audio stream couldn't start (no devices),
            # advance the bar clock by consuming rendered chunks at real-time pace.
            if self.stream is None and not self._paused:
                try:
                    chunk = self.buffer.read()
                except Exception:
                    chunk = None
                if chunk is None:
                    time.sleep(0.05)
                    continue
                try:
                    n = len(getattr(chunk, "audio", []) or [])
                    sr = int(getattr(self.container, "sample_rate", 44100) or 44100)
                    dt = float(n) / float(max(1, sr))
                except Exception:
                    dt = self._current_bar_seconds()
                self._on_bar_played()
                time.sleep(max(0.01, min(0.5, dt)))
                continue
            self._maybe_recover_stream()
            time.sleep(sleep_time)
