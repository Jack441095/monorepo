# ---------------------------------------------------------------------------
# Central ConfigurationManager (audio, composition, AI, presets) + CONFIG singleton.
# ---------------------------------------------------------------------------
import logging
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from data.conversation_presets import (
    CONVERSATION_PRESETS,
)
from data.sample_packs import SAMPLE_PACKS
from data.sample_style_profiles import STYLE_PROFILES
from audiogen_core.config_performance import apply_performance_mode
from audiogen_core.config_profiles import (
    apply_layer as apply_profile_layer,
    export_conversation_preset as export_profile_preset,
    rebuild_from_active_layers as rebuild_profile_layers,
    save_conversation_preset as save_profile_preset,
    scaffold_sample_pack as scaffold_profile_pack,
    set_conversation_preset as set_profile_conversation_preset,
    set_sample_pack as set_profile_sample_pack,
    set_style_profile as set_profile_style_profile,
    update_conversation_preset_field as update_profile_preset_field,
)
from audiogen_core.config_samplers import (
    base_sampler_templates as build_sampler_templates,
    infer_sample_pack_path as infer_sampler_pack_path,
    initialize_sampler_configurations as build_sampler_configurations,
)
from audiogen_core.post_processing_config import PostProcessingPreset, default_post_process_presets
from audiogen_core.composition_config import CompositionConfiguration
from audiogen_core.sampler_configuration import QualityMode, SamplerConfiguration
from audiogen_core.mixer_config import (
    AUDIO_MIXER_CHANNEL_COUNT,
    ChorusKickSidechainConfig,
    MixerStripConfig,
    default_mixer_strips,
)

logger = logging.getLogger(__name__)


@dataclass
class EQSettings:
    """3‑band EQ settings for one audio channel."""
    enabled: bool = False
    low_gain_db: float = 0.0
    mid_gain_db: float = 0.0
    high_gain_db: float = 0.0
    low_freq: float = 80.0
    mid_freq: float = 1000.0
    high_freq: float = 5000.0
    mid_q: float = 1.0


@dataclass
class AudioConfiguration:
    global_tempo: float = 70.0
    sample_rate: int = 44100
    buffer_size: int = 4096
    # Realtime split (optional): ``buffer_size`` remains the legacy single knob that
    # applies to both when the split fields are unset (None).
    # - ``rt_output_blocksize_frames``: PortAudio output callback size in frames. Smaller
    #   values reduce output latency but increase Python callback rate (CPU overhead).
    # - ``bar_render_padding_samples``: extra headroom when sizing max bar sample buffers
    #   in the live player (unrelated to PortAudio block size).
    # Default to a smaller realtime output blocksize for snappier playback/latency.
    # Keeping it separate from `buffer_size` preserves legacy render/memory sizing.
    rt_output_blocksize_frames: Optional[int] = None
    bar_render_padding_samples: Optional[int] = None
    fade_samples: int = 64
    # Startup output shaping: apply a subtle master fade-in on cold start.
    # Measured in bars at the current tempo; applied after all RT levelers so it
    # can't be "undone" by normalization/smoothing.
    startup_fade_in_enabled: bool = True
    startup_fade_in_bars: int = 2
    startup_fade_in_start_gain: float = 0.0
    # Realtime robustness: keep quality mode switches sticky to prevent
    # balanced/safe flapping under borderline CPU load.
    rt_mode_hysteresis_enabled: bool = True
    rt_mode_promote_hold_bars: int = 3
    rt_mode_demote_hold_bars: int = 1
    # Render watchdog: if bar render time exceeds this ratio of real bar duration,
    # force temporary safe mode for the next N bars.
    rt_render_watchdog_enabled: bool = True
    rt_render_watchdog_ratio: float = 0.92
    rt_render_watchdog_hold_bars: int = 6
    # Normalization (sample load time). RMS mode helps keep sample packs/emotions
    # closer in perceived loudness without crushing musical dynamics (master limiter still applies).
    normalizer_target_level: float = -18.0
    normalizer_mode: str = "rms"
    normalizer_prevent_clipping: bool = True
    normalizer_pre_gain_db: float = 0.0
    normalizer_post_gain_db: float = 0.0
    # If True, normalize WAV samples at load time using the settings above.
    # Default is False to preserve sample-pack authorship (legacy behavior).
    normalize_samples_on_load: bool = False
    # Source-level DC blocking at sample load time (offline cost only).
    # Helps remove low-frequency bias/drift before realtime playback.
    sample_dc_block_enabled: bool = True
    # 1st-order high-pass cutoff for source-level DC blocker.
    sample_dc_block_cutoff_hz: float = 12.0
    # Only apply source DC blocker when channel-mean abs offset exceeds this.
    sample_dc_block_min_mean_abs: float = 5e-4
    # Persistent on-disk cache for finalized samples (decode + resample + fades + optional normalize).
    # Dramatically speeds up warm starts when packs contain many WAVs.
    sample_cache_enabled: bool = True
    # Load cached .npy via mmap to reduce RSS/IO bursts (copy-on-write if mutated).
    sample_cache_mmap: bool = True
    # Cache bounding policy (best-effort; never blocks audio load).
    # - max size (MB): when exceeded, delete oldest cached entries until under limit.
    # - max files: optional hard cap on number of cache files.
    # - ttl days: optional age-based expiry (0 disables).
    # - prune chance: avoid scanning the cache dir on every load; 1.0 = always.
    sample_cache_max_mb: float = 512.0
    sample_cache_max_files: int = 0
    sample_cache_ttl_days: float = 0.0
    sample_cache_prune_chance: float = 0.02
    # Source resampling quality for sample load stage: "fast", "high", or "best".
    sample_resample_quality: str = "high"
    # Additional tiny edge fade for chord-layer renders before cache store.
    chord_edge_fade_ms: float = 1.6
    lowpass_harmonic_multiplier: float = 4.0
    lowpass_min_cutoff: float = 200.0
    lowpass_max_cutoff: float = 10000.0
    master_volume: float = 0.5
    # DAW-like master output trim in dB (post-returns, pre-limiter).
    master_output_trim_db: float = 0.0
    channel_eq: Dict[int, EQSettings] = field(default_factory=dict)

    # ------------------------------------------------------------
    # Master EQ (post-fader insert, pre-limiter)
    # A gentle "loudness / Fletcher–Munson-ish" monitoring curve:
    # low shelf up, low-mid cut, presence dip, high shelf up.
    # ------------------------------------------------------------
    master_eq_enabled: bool = True
    master_eq_band1_type: str = "lowshelf"
    master_eq_band1_freq_hz: float = 120.0
    master_eq_band1_gain_db: float = 0.0
    master_eq_band1_q: float = 0.7

    master_eq_band2_type: str = "peaking"
    master_eq_band2_freq_hz: float = 350.0
    master_eq_band2_gain_db: float = -2.0
    master_eq_band2_q: float = 1.0

    master_eq_band3_type: str = "peaking"
    master_eq_band3_freq_hz: float = 3000.0
    master_eq_band3_gain_db: float = -1.0
    master_eq_band3_q: float = 1.0

    master_eq_band4_type: str = "highshelf"
    master_eq_band4_freq_hz: float = 10000.0
    master_eq_band4_gain_db: float = 0.8
    master_eq_band4_q: float = 0.7

    # ------------------------------------------------------------
    # Master multiband compressor (post-fader insert, pre-limiter)
    # Modeled after a gentle Ableton-style multiband mastering preset.
    # Implemented as a 3-band crossover with per-band compression.
    # ------------------------------------------------------------
    multiband_enabled: bool = True
    # Crossover points for a 3-band split: [low, mid, high].
    # Bands: [0, low) = low, [low, high) = mid, [high, Nyquist] = high.
    multiband_low_crossover_hz: float = 120.0
    multiband_high_crossover_hz: float = 2500.0
    # Per-band dynamics: gentle bus compression targets (~2–3 dB GR).
    # Thresholds in dBFS.
    multiband_low_threshold_db: float = -12.0
    multiband_mid_threshold_db: float = -18.0
    multiband_high_threshold_db: float = -12.0
    # Ratios (unitless).
    multiband_low_ratio: float = 2.0
    multiband_mid_ratio: float = 2.0
    multiband_high_ratio: float = 2.0
    # Attack / release in milliseconds.
    multiband_low_attack_ms: float = 20.0
    multiband_low_release_ms: float = 100.0
    multiband_mid_attack_ms: float = 15.0
    multiband_mid_release_ms: float = 100.0
    multiband_high_attack_ms: float = 8.0
    multiband_high_release_ms: float = 100.0
    # Soft knee in dB.
    multiband_knee_width_db: float = 6.0
    # Overall makeup gain applied after multiband compression (in dB).
    multiband_makeup_db: float = 1.5
    # Parallel mix between dry and multiband-compressed signal (0.0–1.0).
    multiband_mix: float = 0.6
    # Profile selector to allow future alternate curves (e.g. OTT-like).
    multiband_profile: str = "ableton_gentle"
    # Optional split tuning between realtime fast playback and offline/high-quality
    # render paths. When disabled, legacy single settings are used.
    master_offline_quality_split_enabled: bool = True
    master_offline_multiband_mix: float = 0.72
    master_offline_makeup_db: float = 2.0
    master_offline_eq_gain_scale: float = 1.15
    master_realtime_multiband_mix: float = 0.52
    master_realtime_makeup_db: float = 1.10

    # Reverb settings
    reverb_enabled: bool = True
    reverb_rt60: float = 10.0        # seconds (0.05–16.0)
    reverb_damping: float = 0.62     # 0 = bright, 1 = dark
    reverb_wet: float = 0.24         # 0 = dry, 1 = fully wet (reverb return level is reverb_wet × channel_reverb_send)
    # Separate dry transient from wet tail for cleaner long-decay spaces.
    reverb_predelay_ms: float = 28.0
    # Short tap network before late reverb for front-to-back depth.
    reverb_early_reflections_enabled: bool = True
    reverb_early_reflections_level: float = 0.24
    # Optional return low-pass to keep long tails silky (0 disables).
    reverb_return_lowpass_hz: float = 9500.0
    reverb_return_lowpass_slope_db_per_oct: float = 12.0
    reverb_return_highpass_hz: float = 500.0
    reverb_return_highpass_slope_db_per_oct: float = 12.0

    # Master post processing
    active_post_process_preset: str = "calm"
    distortion_enabled: bool = True
    distortion_drive: float = 1.35
    distortion_mix: float = 0.08

    # ------------------------------------------------------------
    # Send/return FX buses (DAW-like aux sends)
    # ------------------------------------------------------------
    delay_bus_enabled: bool = True
    delay_bus_time_ms: float = 320.0
    delay_bus_feedback: float = 0.21
    delay_bus_return_level: float = 0.32
    # Delay character controls (premium: keeps repeats clean and wide).
    delay_bus_pingpong: float = 0.35
    delay_bus_feedback_highpass_hz: float = 180.0
    delay_bus_feedback_lowpass_hz: float = 8200.0
    delay_bus_feedback_filter_slope_db_per_oct: float = 12.0

    distortion_bus_enabled: bool = True
    distortion_bus_return_level: float = 0.08
    # Distortion return tone controls (keeps parallel distortion usable).
    distortion_tone_highpass_hz: float = 140.0
    distortion_tone_lowpass_hz: float = 9000.0
    distortion_tone_slope_db_per_oct: float = 12.0

    # RT safety: scale return levels down under pressure (1.0 = full wet returns).
    fx_return_scale_balanced: float = 0.92
    fx_return_scale_safe: float = 0.82
    fx_return_scale_emergency: float = 0.35
    # Bucket sustained chord lengths for RT cache hits (ms); 0 disables quantization.
    chord_render_duration_quantize_ms: float = 50.0
    # Bucket monophonic note lengths for RT cache hits; timing placement is unchanged.
    mono_render_duration_quantize_ms: float = 20.0

    # Master output bus (post‑mixer): limiter + optional soft clip
    master_limiter_enabled: bool = True
    master_limiter_threshold: float = 0.9
    master_limiter_lookahead_ms: float = 5.0
    master_limiter_release: float = 0.999
    # Enabled 2026-07-04 (auto-mixer/DSP work): gentle analog-style saturation safety net,
    # pairs with the already-active limiter/true-peak stage for cheap "glue" warmth.
    master_soft_clip: bool = True
    master_soft_clip_drive: float = 0.95
    # Optional true-peak style safety pass: oversample before limiter and downsample after.
    master_true_peak_enabled: bool = True
    master_true_peak_oversample_factor: int = 2
    # Realtime path uses the regular lookahead limiter by default; true-peak
    # oversampling is kept for offline/high-quality processing where latency is irrelevant.
    master_true_peak_realtime_enabled: bool = False
    # Optional TPDF dither at final output stage (offline/high-quality paths only).
    master_dither_enabled: bool = False
    master_dither_amount: float = 1e-5

    # Mid/side stereo width control (post-EQ, pre-limiter). New 2026-07-04
    # (auto-mixer/DSP work) -- off by default since it's unvalidated sonically;
    # 1.0 = unity/no change, <1.0 narrower, >1.0 wider.
    master_stereo_width_enabled: bool = False
    master_stereo_width: float = 1.0

    # Optional final-stage loudness trim (post-fader+inserts, pre-limiter).
    # Keeps your channel faders authoritative; only nudges the *master* toward a target.
    # Enabled 2026-07-04 (auto-mixer/DSP work): the 28 emotions have wildly different
    # note density/velocity by design, which otherwise means wildly different loudness
    # song-to-song; this keeps perceived level consistent without touching channel mix.
    # Gentle by construction (clamped +/-1.5dB/block, EMA-smoothed) -- avoids
    # emotion-to-emotion jumps rather than aggressively normalizing.
    # Measured via a running BS.1770 K-weighted loudness estimate (audio/engine/lufs.py),
    # not plain RMS, when `master_target_use_k_weighting` is on (default) -- so this target
    # is effectively an LUFS target. -14.0 matches common streaming-platform loudness norms
    # (Spotify/YouTube), set 2026-07-05 (was -18.0 dB plain-RMS before the LUFS analyzer).
    master_target_enabled: bool = True
    master_target_use_k_weighting: bool = True
    master_target_rms_db: float = -14.0
    # Clamp how much gain can change per processed block (typically a bar). Measured
    # 2026-07-05: the raw mix naturally sits ~-35 LUFS (only ~1.8 LU spread across
    # emotions -- already consistent, just quiet), a ~21dB gap to -14. The correction is
    # measured fresh from the RAW (uncorrected) signal every block, not accumulated across
    # blocks -- so a clamp smaller than the actual gap doesn't "ramp up" over time, it just
    # applies the SAME clamped correction forever (verified: 6.0dB/block converged to ~-30
    # LUFS and stayed there, never closing the rest of the gap). The clamp must cover the
    # realistic full gap in one step; the EMA (target_ema_alpha) is what prevents an
    # audible instant jump, not this clamp. 24.0dB comfortably covers the measured ~21dB
    # gap with headroom for quieter emotions; the downstream limiter is the safety net.
    master_target_max_change_db: float = 24.0
    # EMA smoothing for measured loudness (higher = faster response).
    master_target_ema_alpha: float = 0.25

    # Real-time safety: bypass heavy master inserts under pressure.
    # - "never": always run inserts
    # - "realtime": bypass multiband on all RT ladder modes (keeps master EQ unless skip below)
    # - "balanced": bypass multiband+EQ when mode is safe/balanced/emergency
    # - "safe": bypass only when mode is safe/emergency
    master_inserts_rt_bypass_mode: str = "realtime"
    # When True, skip clarity multiband on the master bus during RT (large CPU win; EQ may remain).
    rt_bypass_master_multiband: bool = True
    # Fletcher–Munson master EQ insert during RT (lighter than multiband).
    rt_bypass_master_eq: bool = False
    # Default Schroeder tier for normal RT playback (balanced ≈ 6 combs; high = 8).
    rt_reverb_default_tier: str = "high_rt"
    # Promote to full high tier when render ratio is comfortably under real-time.
    rt_reverb_adaptive_high_enabled: bool = True
    rt_reverb_adaptive_high_ratio: float = 0.72
    # Use fast_path (skip limiter oversample / soft clip) when ratio exceeds this.
    rt_fast_master_ratio: float = 0.88
    # Reuse stem/send buffers in MasterBus.process during RT (fewer allocations per bar).
    rt_master_reuse_stem_buffer: bool = True
    # Skip limiter/soft-clip on normal RT when master is the bottleneck (low CPU mode sets this).
    rt_master_proactive_fast_path: bool = False
    # RT spike mitigation: populate chord LRU and warm mix/master once (see ``audio.rt_prewarm``).
    rt_chord_cache_prewarm_enabled: bool = True
    rt_mono_cache_prewarm_enabled: bool = False
    rt_mix_master_warmup_enabled: bool = True
    rt_prewarm_background: bool = True
    # ``AudioRenderer.render_bar`` should not do blocking sampler prefetch; the RT player
    # owns a background prefetch worker for this. Keep the old sync path opt-in.
    rt_render_sync_prefetch_enabled: bool = False
    # Keep reverb/delay usable under CPU pressure (floor tier when ladder dips).
    rt_preserve_spatial_fx_quality: bool = True
    rt_reverb_min_quality_tier: str = "balanced"

    # Live emotion handoff (n / menu): bar alignment; crossfade (higher = smoother).
    # Default to phrase-sized boundaries so emotion changes feel musical rather than jittery.
    emotion_transition_boundary_bars: int = 4
    # Scale applied to computed crossfade overlap for emotion handoffs (clamped in player).
    # Lower = shorter / tighter stitch (less audible dip across the phrase boundary).
    emotion_handoff_crossfade_scale: float = 0.72
    # Hard cap on crossfade overlap duration for emotion handoffs.
    emotion_handoff_crossfade_max_seconds: float = 0.65
    # Leave N rendered bars in the ring buffer when queueing a new emotion so playback does not
    # underrun (silence) before bar 0 of the new timeline is ready. 0 = trim all (legacy, choppy).
    emotion_handoff_queue_keep_bars: int = 6

    # Startup: bars queued before the OS stream opens (vs underrun risk). Tune down for snappier
    # first sound; tune up if you hear gaps at cold start. See also ``cold_start_preview_bars``.
    # Faster first sound while adaptive buffering protects against underruns.
    startup_preroll_bars: int = 4
    startup_preroll_cap_bars: int = 8
    # First load_emotion: synchronous preview size (bars) before audio — lower = faster boot.
    cold_start_preview_bars: int = 2
    # First load_emotion preview should prefer first-sound latency over full section search.
    # Background pre-generation still builds the normal/full section immediately after.
    cold_start_preview_runtime_mode: str = "preview"
    cold_start_preview_planner_effort: str = "minimal"
    # Avoid competing with the first preview render on cold start.
    cold_start_defer_pregen_until_first_bar: bool = True
    # Cold start variety: the first audible chunk historically always used section_index=0,
    # which can make openings feel identical across launches. Randomize the starting
    # section counter for non-arranged playback (arranged previews get their own seeding).
    cold_start_randomize_section_index: bool = True
    cold_start_section_index_span: int = 64
    # Arranged cold-start previews used `seed=None`, which can accidentally repeat the same
    # opening across launches when upstream RNG state is stable. Randomize preview seeds
    # unless the user explicitly pinned `--seed`.
    cold_start_randomize_arranged_preview_seed: bool = True

    # RT buffer policy (bars). Steady-state runway after startup; lower slightly with preroll for speed.
    target_buffer_bars: int = 14
    # Hard cap for adaptive target buffer size. Prevents runaway targets after one slow bar.
    target_buffer_cap_bars: int = 24
    # Generation loop: maximum bars generated per refill burst.
    gen_burst_max_bars: int = 12
    # Realtime underrun adaptive buffer policy.
    # When callback underflows happen repeatedly, temporarily increase target buffer bars.
    underrun_auto_buffer_boost_enabled: bool = True
    underrun_auto_buffer_boost_trigger_count: int = 3
    underrun_auto_buffer_boost_step_bars: int = 1
    underrun_auto_buffer_boost_max_extra_bars: int = 6
    underrun_auto_buffer_boost_decay_seconds: float = 10.0

    # Emotion-driven audio intent (post-FX + mix multipliers) applied at runtime when switching emotions.
    # This is a "bias layer" meant to improve perceptual emotional differentiation.
    # If you manually set FX via `fx <name>`, the system will respect that and not override FX.
    emotion_auto_fx_enabled: bool = True
    emotion_auto_mix_enabled: bool = True

    # RT drone loop level (used by the live player DroneManager).
    # This is applied to the looped raw drone sample (not MIDI pitch-shifted notes).
    drone_loop_volume: float = 0.4

    # Realtime diagnostics
    # Per-bar render timing to logs when True; or set env ``AUDIOGEN_RT_PROFILE=1``.
    # Baseline: compare ``buffer_underruns`` / ``callback_underflows`` in ``PlaybackTelemetry.snapshot()``.
    rt_render_profile_enabled: bool = False

    # Post-master bar loudness stabilizer (gentle, clamped; avoids emotion-to-emotion jumps)
    # NOTE: If you want DAW-like channel strip control (track faders),
    # disable this so it doesn't "undo" your mix moves post-master.
    bar_gain_stabilizer_enabled: bool = False
    bar_gain_target_rms_db: float = -18.0
    bar_gain_max_up_db: float = 1.5
    bar_gain_max_down_db: float = 2.5

    # Realtime output leveling (disable to make mixer strip ratios authoritative).
    rt_emotion_loudness_norm_enabled: bool = False
    rt_output_level_smoothing_enabled: bool = False

    # Realtime bar crossfade / transition shaping (base values; handoffs may scale these).
    transition_crossfade_seconds: float = 0.08
    transition_overlap_ratio: float = 0.22
    transition_max_overlap_seconds: float = 0.75

    # Sampler cache prefetch (next-bar warmup)
    prefetch_enabled: bool = True
    prefetch_max_events: int = 220
    prefetch_default_velocity: int = 80

    # Emotion switching: optional sampler "prewarm" pass.
    # This can help avoid the very first cache-miss spikes right after a switch, but it can also
    # steal CPU and cause callback starvation / underruns on some systems. Keep it opt-in.
    emotion_switch_sampler_prewarm_enabled: bool = False

    # Realtime load shedding (graded quality ladder).
    # Channel IDs are sampler channels: bass=0, chords=1, melody=2, arp=3, drone=4, counter_melody=5.
    # Prefer consistent musical output over muting channels; rely on buffering + master fast-path first.
    # Defaults keep arp (3) with chords — it is core to the generative texture; use e.g. [5] or [2] if you
    # enable shedding and need cheaper bars.
    load_shed_enabled: bool = False
    # In balanced mode, drop these channels only when generation time ratio crosses the threshold.
    load_shed_drop_channels_balanced: List[int] = field(default_factory=list)
    # In safe mode, drop these channels to stabilize CPU (empty by default).
    load_shed_drop_channels_safe: List[int] = field(default_factory=list)
    # Hard cap on event count in safe mode (after dropping channels).
    load_shed_max_events_safe: int = 320
    # When balanced, activate shedding when generation time ratio exceeds this.
    load_shed_balanced_ratio_threshold: float = 0.90

    # Per‑channel delay settings
    channel_delay: Dict[int, Dict[str, Any]] = field(default_factory=dict)
    # Typed mixer config (authoritative). `channel_mix` remains for backwards compatibility.
    mixer_strips: Dict[int, MixerStripConfig] = field(default_factory=dict)
    # Scale master FX return wet level (reverb/delay/distortion) by arranged section role
    # — slightly wider choruses, tighter intros/outros. See ``data.arrangement_curves.arrangement_role_fx_return_mult``.
    arrangement_fx_return_automation_enabled: bool = True
    arrangement_fx_return_strength: float = 1.0
    # Post-render stem level ride by role (+ optional pre-chorus last-bar swell). See
    # ``data.arrangement_curves.arrangement_role_velocity_ride_mult`` (affects all stems except
    # the pre-rendered drone buffer).
    arrangement_velocity_ride_enabled: bool = True
    arrangement_velocity_ride_strength: float = 1.0
    arrangement_pre_chorus_last_bar_swell_enabled: bool = True
    arrangement_pre_chorus_last_bar_swell_strength: float = 1.0
    # Chorus kick + ducking (see ``core.mixer_config.ChorusKickSidechainConfig``).
    chorus_kick_sidechain: ChorusKickSidechainConfig = field(default_factory=ChorusKickSidechainConfig)
    channel_mix: Dict[int, Dict[str, float]] = field(default_factory=dict)

    def __post_init__(self):
        # EQ defaults
        for ch in range(int(AUDIO_MIXER_CHANNEL_COUNT)):
            if ch not in self.channel_eq:
                self.channel_eq[ch] = EQSettings()

        # Delay defaults: shared melodic identity across lead / arp / counter.
        for ch in range(int(AUDIO_MIXER_CHANNEL_COUNT)):
            if ch not in self.channel_delay:
                if ch in (2, 3, 5):
                    div = "1/8"
                    self.channel_delay[ch] = {
                        "enabled": True,
                        # If sync is enabled, time_ms is treated as a fallback.
                        "sync": True,
                        # Shared melodic echo identity, tempo-synced at runtime.
                        "division": div,
                        "time_ms": 320.0,
                        "feedback": 0.21,
                        "mix": 0.30,
                        # Shared reverb aux send for melody when ch == 2 (see audio_container / player).
                        **({"reverb_send": 0.22} if ch == 2 else {}),
                    }
                else:
                    self.channel_delay[ch] = {"enabled": False}

        # Initialize typed strips, then mirror into legacy `channel_mix`.
        defaults = default_mixer_strips()
        for ch, strip in defaults.items():
            if ch not in self.mixer_strips:
                self.mixer_strips[ch] = MixerStripConfig(
                    volume=float(getattr(strip, "volume", 1.0)),
                    pan=float(getattr(strip, "pan", 0.0)),
                    reverb_send=float(getattr(strip, "reverb_send", 0.0)),
                    delay_send=float(getattr(strip, "delay_send", 0.0)),
                    distortion_send=float(getattr(strip, "distortion_send", 0.0)),
                    sends_pre_fader=bool(getattr(strip, "sends_pre_fader", False)),
                    reverb_send_pre_fader=getattr(strip, "reverb_send_pre_fader", None),
                    delay_send_pre_fader=getattr(strip, "delay_send_pre_fader", None),
                    distortion_send_pre_fader=getattr(strip, "distortion_send_pre_fader", None),
                    filter_enabled=bool(getattr(strip, "filter_enabled", True)),
                    highpass_hz=float(getattr(strip, "highpass_hz", 0.0)),
                    lowpass_hz=float(getattr(strip, "lowpass_hz", 0.0)),
                    filter_slope_db_per_oct=float(getattr(strip, "filter_slope_db_per_oct", 12.0)),
                )
            if ch not in self.channel_mix:
                self.channel_mix[ch] = {
                    "volume": float(self.mixer_strips[ch].volume),
                    "pan": float(self.mixer_strips[ch].pan),
                    "reverb_send": float(self.mixer_strips[ch].reverb_send),
                    "delay_send": float(getattr(self.mixer_strips[ch], "delay_send", 0.0)),
                    "distortion_send": float(getattr(self.mixer_strips[ch], "distortion_send", 0.0)),
                    "filter_enabled": bool(getattr(self.mixer_strips[ch], "filter_enabled", True)),
                    "highpass_hz": float(getattr(self.mixer_strips[ch], "highpass_hz", 0.0)),
                    "lowpass_hz": float(getattr(self.mixer_strips[ch], "lowpass_hz", 0.0)),
                    "filter_slope_db_per_oct": float(getattr(self.mixer_strips[ch], "filter_slope_db_per_oct", 12.0)),
                }
        # If legacy `channel_mix` was modified directly (older codepaths),
        # keep typed strips in sync for channels that already exist.
        for ch, mix_cfg in list(self.channel_mix.items()):
            try:
                chi = int(ch)
            except Exception:
                continue
            if chi not in self.mixer_strips:
                try:
                    self.mixer_strips[chi] = MixerStripConfig(
                        volume=float(mix_cfg.get("volume", 1.0)),
                        pan=float(mix_cfg.get("pan", 0.0)),
                        reverb_send=float(mix_cfg.get("reverb_send", 0.0)),
                        delay_send=float(mix_cfg.get("delay_send", 0.0)),
                        distortion_send=float(mix_cfg.get("distortion_send", 0.0)),
                        sends_pre_fader=bool(mix_cfg.get("sends_pre_fader", False)),
                        reverb_send_pre_fader=mix_cfg.get("reverb_send_pre_fader", None),
                        delay_send_pre_fader=mix_cfg.get("delay_send_pre_fader", None),
                        distortion_send_pre_fader=mix_cfg.get("distortion_send_pre_fader", None),
                        filter_enabled=bool(mix_cfg.get("filter_enabled", True)),
                        highpass_hz=float(mix_cfg.get("highpass_hz", 0.0)),
                        lowpass_hz=float(mix_cfg.get("lowpass_hz", 0.0)),
                        filter_slope_db_per_oct=float(mix_cfg.get("filter_slope_db_per_oct", 12.0)),
                    )
                except Exception:
                    logger.debug("failed to sync legacy channel_mix into mixer_strips (ch=%r)", ch, exc_info=True)

@dataclass
class InterfaceConfiguration:
    prompt_style: str = "cyan"
    error_style: str = "red"
    success_style: str = "green"
    warning_style: str = "yellow"
    info_style: str = "dim"

    # Local service defaults (control plane)
    service_host: str = "127.0.0.1"
    service_port: int = 8765
    service_cors_origins: List[str] = field(
        default_factory=lambda: ["http://localhost", "http://127.0.0.1", "http://localhost:3000"]
    )

@dataclass
class AIConfiguration:
    enabled: bool = True
    markov_enabled: bool = True
    markov_order: int = 2
    markov_temperature: float = 1.0
    lsystem_enabled: bool = True
    lsystem_iterations: int = 2
    lsystem_style: str = 'ornamental'
    genetic_enabled: bool = True
    genetic_generations: int = 10
    genetic_population_size: int = 20
    cellular_enabled: bool = True
    cellular_rule: str = 'rule30'
    cellular_cells: int = 16
    adaptive_harmony_enabled: bool = True
    adaptive_learning_rate: float = 0.1
    adaptive_epsilon: float = 0.1
    training_data_path: str = "ai_training_data"
    model_save_path: str = "ai_artifacts"


class ConfigurationManager:
    SAMPLER_ORDER = ("bass", "chords", "melody", "arp", "drone", "counter_melody")
    DEFAULT_PACK_ROOTS = {
        "bass": 29,
        "chords": 60,
        "melody": 60,
        "drone": 60,
        "arp": 60,
        "counter_melody": 60,
    }
    QualityMode = QualityMode
    SamplerConfiguration = SamplerConfiguration

    def __init__(self):
        self.audio = AudioConfiguration()
        self.composition = CompositionConfiguration()
        self.interface = InterfaceConfiguration()
        self.ai = AIConfiguration()
        self.sample_packs = deepcopy(SAMPLE_PACKS)
        self.style_profiles = deepcopy(STYLE_PROFILES)
        self.conversation_presets = deepcopy(CONVERSATION_PRESETS)
        self.active_sample_pack = "default"
        self.active_style_profile = "default"
        self.active_conversation_preset = "default_ambient_01"
        self.active_post_process_preset = "calm"
        self._post_process_override_active = False
        self._performance_mode = None
        self.post_process_presets = self._init_post_process_presets()
        self.samplers = self._initialize_sampler_configurations()
        self.presets = {}
        self._init_eq_presets()
        try:
            from audiogen_core.song_upgrade_profile import apply_default_song_upgrade_profile

            apply_default_song_upgrade_profile(self)
        except Exception:
            logger.warning("default song-upgrade Phase C profile failed during config init", exc_info=True)
        self._base_audio = deepcopy(self.audio)
        self._base_composition = deepcopy(self.composition)
        self._base_ai = deepcopy(self.ai)
        # Apply any macro knobs after initialization (best-effort).
        try:
            self._apply_dialogue_macro()
        except Exception:
            logger.warning("dialogue macro application failed during config init", exc_info=True)
        # Apply `active_style_profile` + `active_conversation_preset` so the selected
        # default is real (e.g. layered OST conversation, not an empty no-op).
        try:
            self._rebuild_from_active_layers()
        except Exception:
            logger.warning("initial style/conversation layer rebuild failed during config init", exc_info=True)
        try:
            self._apply_dialogue_macro()
        except Exception:
            logger.warning("dialogue macro application failed after layer rebuild", exc_info=True)

    def _apply_dialogue_macro(self) -> None:
        """
        Jam-friendly macro mapping: `composition.dialogue_amount` (0..1) scales
        multiple arp↔melody coupling knobs coherently.

        This is intentionally conservative: it uses `max(current, suggested)` so
        explicit user values still win when they are stronger than the macro.
        """
        c = getattr(self, "composition", None)
        if c is None:
            return
        try:
            d = float(getattr(c, "dialogue_amount", 0.0) or 0.0)
        except Exception:
            d = 0.0
        # Optional preset ladder (live-friendly coarse control).
        try:
            preset = str(getattr(c, "dialogue_preset", "") or "").strip().lower()
        except Exception:
            preset = ""
        preset_map = {
            "off": 0.0,
            "tight": 0.35,
            "strong": 0.65,
            "experimental": 0.85,
        }
        if preset in preset_map:
            d = max(float(d), float(preset_map[preset]))
        d = max(0.0, min(1.0, float(d)))
        if d <= 1e-9:
            return

        # Masking and groove lock.
        try:
            cur = float(getattr(c, "masking_constraints_strength", 0.70) or 0.70)
            setattr(c, "masking_constraints_strength", float(max(cur, min(1.0, cur * (1.0 + 0.45 * d)))))
        except Exception:
            logger.debug("dialogue macro: failed setting masking_constraints_strength", exc_info=True)
        try:
            cur = float(getattr(c, "arp_melody_groove_link_strength", 0.0) or 0.0)
            setattr(c, "arp_melody_groove_link_strength", float(max(cur, d)))
        except Exception:
            logger.debug("dialogue macro: failed setting arp_melody_groove_link_strength", exc_info=True)
        try:
            cur = float(getattr(c, "arp_density_follow_melody", 0.0) or 0.0)
            setattr(c, "arp_density_follow_melody", float(max(cur, 0.60 * d)))
        except Exception:
            logger.debug("dialogue macro: failed setting arp_density_follow_melody", exc_info=True)
        try:
            cur = float(getattr(c, "melody_phrase_rerank_masking_weight", 0.0) or 0.0)
            setattr(c, "melody_phrase_rerank_masking_weight", float(max(cur, 0.75 * d)))
        except Exception:
            logger.debug("dialogue macro: failed setting melody_phrase_rerank_masking_weight", exc_info=True)

        # Motif coupling becomes important at mid/high dialogue.
        try:
            if d >= 0.40:
                setattr(c, "arp_motif_coupling_enabled", True)
                cur = float(getattr(c, "arp_motif_coupling_strength", 0.6) or 0.6)
                setattr(c, "arp_motif_coupling_strength", float(max(cur, 0.70 * d)))
        except Exception:
            logger.debug("dialogue macro: failed setting arp motif coupling fields", exc_info=True)

        # Big-upgrades feature flags (conservative thresholds).
        try:
            if d >= 0.30:
                setattr(c, "phrase_intent_bus_enabled", True)
        except Exception:
            logger.debug("dialogue macro: failed enabling phrase_intent_bus_enabled", exc_info=True)
        try:
            if d >= 0.45:
                setattr(c, "arp_rhythm_cells_enabled", True)
                cur = float(getattr(c, "arp_rhythm_cells_strength", 0.75) or 0.75)
                setattr(c, "arp_rhythm_cells_strength", float(max(cur, 0.60 * d)))
        except Exception:
            logger.debug("dialogue macro: failed setting arp rhythm cells fields", exc_info=True)
        try:
            if d >= 0.55:
                setattr(c, "dialogue_harmony_policy_enabled", True)
                cur = float(getattr(c, "dialogue_harmony_policy_strength", 0.75) or 0.75)
                setattr(c, "dialogue_harmony_policy_strength", float(max(cur, 0.65 * d)))
        except Exception:
            logger.debug("dialogue macro: failed setting dialogue harmony policy fields", exc_info=True)
        try:
            if d >= 0.70:
                setattr(c, "register_choreography_enabled", True)
                cur = float(getattr(c, "register_choreography_strength", 0.75) or 0.75)
                setattr(c, "register_choreography_strength", float(max(cur, 0.70)))
        except Exception:
            logger.debug("dialogue macro: failed setting register choreography fields", exc_info=True)
        try:
            if d >= 0.75:
                setattr(c, "motif_multi_length_enabled", True)
                setattr(c, "motif_rhythm_only_enabled", True)
        except Exception:
            logger.debug("dialogue macro: failed enabling motif multi-length flags", exc_info=True)
        try:
            # Joint generation is expensive; keep it to very high dialogue or "experimental" preset.
            if d >= 0.85:
                setattr(c, "joint_generation_enabled", True)
        except Exception:
            logger.debug("dialogue macro: failed enabling joint_generation_enabled", exc_info=True)

        # Markov + compositional upgrades (balanced thresholds).
        try:
            if d >= 0.45:
                setattr(c, "melody_position_conditioning_enabled", True)
                cur = float(getattr(c, "melody_position_conditioning_strength", 0.75) or 0.75)
                setattr(c, "melody_position_conditioning_strength", float(max(cur, 0.75 * d)))
        except Exception:
            logger.debug("dialogue macro: failed setting melody position conditioning fields", exc_info=True)
        try:
            if d >= 0.60:
                setattr(c, "melody_rhythm_pitch_coupling_enabled", True)
                cur = float(getattr(c, "melody_rhythm_pitch_coupling_strength", 0.65) or 0.65)
                setattr(c, "melody_rhythm_pitch_coupling_strength", float(max(cur, 0.70 * d)))
        except Exception:
            logger.debug("dialogue macro: failed setting melody rhythm/pitch coupling fields", exc_info=True)
        try:
            if d >= 0.70:
                setattr(c, "melody_voiceleading_rerank_enabled", True)
                cur = float(getattr(c, "melody_voiceleading_rerank_strength", 0.60) or 0.60)
                setattr(c, "melody_voiceleading_rerank_strength", float(max(cur, 0.60 * d)))
        except Exception:
            logger.debug("dialogue macro: failed setting melody voiceleading rerank fields", exc_info=True)

        # Optional grid masking for very high dialogue.
        try:
            if d >= 0.65:
                setattr(c, "masking_grid_enabled", True)
                cur = float(getattr(c, "masking_grid_strength", 0.7) or 0.7)
                setattr(c, "masking_grid_strength", float(max(cur, 0.75)))
        except Exception:
            logger.debug("dialogue macro: failed setting masking grid fields", exc_info=True)

        # Discrete coupling modes (only if user hasn't set a non-default value).
        try:
            mode = str(getattr(c, "arp_melody_coupling_mode", "loose") or "loose").strip().lower()
        except Exception:
            mode = "loose"
        if mode in {"", "loose"}:
            try:
                if d >= 0.75:
                    setattr(c, "arp_melody_coupling_mode", "call_response_strong")
                elif d >= 0.40:
                    setattr(c, "arp_melody_coupling_mode", "motif_locked")
            except Exception:
                logger.debug("dialogue macro: failed setting arp_melody_coupling_mode", exc_info=True)

    def apply_dialogue_macro(self) -> None:
        """
        Public hook: reapply `dialogue_amount` + `dialogue_preset` macro mapping.
        Call after changing those fields at runtime so derived flags/strengths update.
        """
        try:
            self._apply_dialogue_macro()
        except Exception:
            logger.warning("dialogue macro application failed", exc_info=True)

    def _init_eq_presets(self):
        # Per-strip EQ is off by default; master Fletcher–Munson curve + sends define tone.
        self.audio.channel_eq = {i: EQSettings(enabled=False) for i in range(int(AUDIO_MIXER_CHANNEL_COUNT))}

    @staticmethod
    def _init_post_process_presets() -> Dict[str, PostProcessingPreset]:
        return default_post_process_presets()

    def _apply_post_process_preset(self, preset_name: str):
        # Writes audio.reverb_* and distortion_* on CONFIG.audio. After `fx <name>`,
        # AudioContainer.apply_audio_config pushes these into RoomReverb + MasterBus return
        # levels (reverb_return_wet, distortion_return_level).
        if preset_name not in self.post_process_presets:
            raise ValueError(f"Unknown post-processing preset '{preset_name}'")
        preset = self.post_process_presets[preset_name]
        self.active_post_process_preset = preset_name
        self.audio.active_post_process_preset = preset_name
        self.audio.reverb_enabled = True
        self.audio.reverb_rt60 = preset.reverb_rt60
        self.audio.reverb_damping = preset.reverb_damping
        self.audio.reverb_wet = preset.reverb_wet
        # Optional: return EQ shaping (keep defaults stable unless preset opts in).
        try:
            hp = float(getattr(preset, "reverb_return_highpass_hz", 0.0) or 0.0)
            if hp > 1e-9:
                self.audio.reverb_return_highpass_hz = float(hp)
            hps = float(getattr(preset, "reverb_return_highpass_slope_db_per_oct", 0.0) or 0.0)
            if hps > 1e-9:
                self.audio.reverb_return_highpass_slope_db_per_oct = float(hps)
        except Exception:
            logger.debug("post-process preset: failed applying reverb return shaping", exc_info=True)
        self.audio.distortion_enabled = preset.distortion_mix > 0.0
        self.audio.distortion_drive = preset.distortion_drive
        self.audio.distortion_mix = preset.distortion_mix
        # Delay + distortion tone shaping for higher quality FX presets.
        try:
            self.audio.delay_bus_pingpong = float(getattr(preset, "delay_pingpong", getattr(self.audio, "delay_bus_pingpong", 0.0)))
            self.audio.delay_bus_feedback_highpass_hz = float(
                getattr(preset, "delay_feedback_highpass_hz", getattr(self.audio, "delay_bus_feedback_highpass_hz", 0.0))
            )
            self.audio.delay_bus_feedback_lowpass_hz = float(
                getattr(preset, "delay_feedback_lowpass_hz", getattr(self.audio, "delay_bus_feedback_lowpass_hz", 0.0))
            )
            self.audio.distortion_tone_highpass_hz = float(
                getattr(preset, "distortion_tone_highpass_hz", getattr(self.audio, "distortion_tone_highpass_hz", 0.0))
            )
            self.audio.distortion_tone_lowpass_hz = float(
                getattr(preset, "distortion_tone_lowpass_hz", getattr(self.audio, "distortion_tone_lowpass_hz", 0.0))
            )
        except Exception:
            logger.debug("post-process preset: failed applying delay/distortion tone shaping", exc_info=True)
        # DAW-like aux return level mirrors the preset mix by default.
        try:
            self.audio.distortion_bus_return_level = float(preset.distortion_mix)
        except Exception:
            logger.debug("post-process preset: failed applying distortion_bus_return_level", exc_info=True)

    def set_post_process_preset(self, preset_name: str):
        self._post_process_override_active = True
        self._apply_post_process_preset(preset_name)
        logger.info("Post-processing preset set to %s", preset_name)

    # ------------------------------------------------------------------
    # Sampler configuration façade
    # ------------------------------------------------------------------
    def _base_sampler_templates(self) -> Dict[str, Dict[str, Any]]:
        return build_sampler_templates(self)

    def _initialize_sampler_configurations(self) -> List[SamplerConfiguration]:
        return build_sampler_configurations(self)

    def rebuild_samplers(self) -> None:
        """
        Recompute `self.samplers` from the current CONFIG state.

        This is needed when audio-side knobs (e.g. `audio.drone_loop_volume`) are expected
        to reflect into sampler config fields like `amplitude_db` after presets/macros.
        """
        mode = getattr(self, "_performance_mode", None)
        self.samplers = self._initialize_sampler_configurations()
        if mode:
            apply_performance_mode(self, str(mode))

    @staticmethod
    def _infer_sample_pack_path(pack_name: str, sampler_name: str) -> str:
        return infer_sampler_pack_path(pack_name, sampler_name)

    # ------------------------------------------------------------------
    # Profile and preset façade
    # ------------------------------------------------------------------
    def set_sample_pack(self, pack_name: str):
        set_profile_sample_pack(self, pack_name)

    def scaffold_sample_pack(self, pack_name: str) -> Dict[str, Dict[str, int]]:
        return scaffold_profile_pack(self, pack_name)

    def set_conversation_preset(self, preset_name: str):
        set_profile_conversation_preset(self, preset_name)

    def set_style_profile(self, style_name: str):
        set_profile_style_profile(self, style_name)

    def _apply_layer(self, layer: Dict[str, Any]):
        apply_profile_layer(self, layer)
        try:
            self._apply_dialogue_macro()
        except Exception:
            logger.debug("failed applying dialogue macro after layer apply", exc_info=True)

    def _rebuild_from_active_layers(self):
        rebuild_profile_layers(self)
        try:
            self._apply_dialogue_macro()
        except Exception:
            logger.debug("failed applying dialogue macro after layer rebuild", exc_info=True)

    def export_conversation_preset(self, preset_name: str) -> Dict[str, Any]:
        return export_profile_preset(self, preset_name)

    def save_conversation_preset(self, new_name: str, source_name: Optional[str] = None) -> Dict[str, Any]:
        return save_profile_preset(self, new_name, source_name=source_name)

    def update_conversation_preset_field(self, preset_name: str, field_path: str, value: Any) -> Dict[str, Any]:
        return update_profile_preset_field(self, preset_name, field_path, value)

    # ------------------------------------------------------------------
    # Runtime toggles
    # ------------------------------------------------------------------
    def enable_cpu_intensive_features(self):
        self.set_performance_mode("high")
        logger.warning("CPU-intensive features enabled")

    def disable_cpu_intensive_features(self):
        self.set_performance_mode("low")
        logger.info("CPU-intensive features disabled")

    def set_performance_mode(self, mode: str = "balanced"):
        apply_performance_mode(self, mode)

    def effective_section_tempo_bpm(self, emotion=None) -> float:
        # BPM after global scale; emotion=None → no per-emotion tempo multiplier.
        base = float(getattr(self.composition, "default_tempo", 70.0))
        scale = max(0.25, min(4.0, float(getattr(self.composition, "global_tempo_scale", 1.0))))
        if emotion is None:
            return base * scale
        try:
            from data.audit import normalize_emotion_scalars

            em, _, _ = normalize_emotion_scalars(emotion)
        except Exception:
            em = float(getattr(emotion, "tempo_multiplier", 1.0) or 1.0)
        return base * scale * em

    # ------------------------------------------------------------------
    # Composition tuning helpers (interactive)
    # ------------------------------------------------------------------
    def set_composition_tight_profile(self, name: str) -> None:
        """
        Apply a curated set of composition knobs for quick interactive tuning.

        This writes directly into `CONFIG.composition` fields; it is intended for
        CLI workflows (switching between tight pop_ext and tight ambient behavior).
        """
        key = (name or "").strip().lower()
        from data.arrangement_tight_profiles import TIGHT_PROFILES
        if key not in TIGHT_PROFILES:
            raise ValueError(f"Unknown tight profile '{name}'")
        overrides = TIGHT_PROFILES[key]
        for k, v in overrides.items():
            setattr(self.composition, k, v)

    def set_producer_macro(self, name: str, amount: float = 1.0) -> None:
        """
        Apply high-level production macros for quick A/B tuning.

        Supported names:
        - "cinematic": wider space, smoother transitions, stronger motifs.
        - "club": tighter transients, denser bass/arp motion.
        - "intimate": drier/closer lead focus with less bus FX.
        - "narrative": stronger song-level blueprint/rerank/cadence contracts.
        """
        key = str(name or "").strip().lower()
        a = max(0.0, min(1.0, float(amount)))
        c = self.composition
        au = self.audio

        if key == "cinematic":
            c.transition_composer_strength = float(min(1.0, c.transition_composer_strength + 0.18 * a))
            c.transition_composer_phrase_handoff_enabled = True
            c.cross_lane_motif_bus_enabled = True
            c.cross_lane_motif_bus_strength = float(min(1.0, c.cross_lane_motif_bus_strength + 0.16 * a))
            c.hook_development = float(max(0.20, min(1.0, c.hook_development * (1.0 - 0.10 * a))))
            au.reverb_wet = float(max(0.0, min(1.0, au.reverb_wet + 0.10 * a)))
            au.delay_bus_return_level = float(max(0.0, min(1.0, au.delay_bus_return_level + 0.06 * a)))
            return

        if key == "club":
            c.bass_intelligence_enabled = True
            c.bass_intelligence_strength = float(min(1.0, c.bass_intelligence_strength + 0.14 * a))
            c.bass_density = float(max(0.5, min(4.0, c.bass_density + 0.40 * a)))
            c.arp_density_follow_melody = float(max(0.0, min(1.0, c.arp_density_follow_melody + 0.18 * a)))
            c.chord_rerank_change_bonus = float(max(0.0, min(0.6, c.chord_rerank_change_bonus + 0.08 * a)))
            au.multiband_makeup_db = float(max(-1.0, min(6.0, au.multiband_makeup_db + 0.35 * a)))
            au.master_limiter_threshold = float(max(0.70, min(0.98, au.master_limiter_threshold - 0.05 * a)))
            return

        if key == "intimate":
            c.melody_amount_scale = float(max(0.45, min(1.25, c.melody_amount_scale * (1.0 - 0.10 * a))))
            c.motif_use_chance = float(max(0.0, min(1.0, c.motif_use_chance + 0.06 * a)))
            c.transition_composer_strength = float(max(0.0, min(1.0, c.transition_composer_strength - 0.08 * a)))
            au.reverb_wet = float(max(0.0, min(1.0, au.reverb_wet * (1.0 - 0.40 * a))))
            au.delay_bus_return_level = float(max(0.0, min(1.0, au.delay_bus_return_level * (1.0 - 0.55 * a))))
            au.distortion_bus_return_level = float(max(0.0, min(1.0, au.distortion_bus_return_level * (1.0 - 0.30 * a))))
            return

        if key == "narrative":
            # Song-level structure and payoff shaping.
            c.whole_song_rerank_enabled = True
            c.song_blueprint_enabled = True
            c.song_blueprint_apply_targets_enabled = True
            c.cadence_first_harmony_enabled = True
            c.motif_lifecycle_enabled = True
            c.arrangement_contracts_enabled = True

            c.whole_song_rerank_blueprint_weight = float(
                max(0.0, min(1.0, max(float(getattr(c, "whole_song_rerank_blueprint_weight", 0.55) or 0.55), 0.60 + 0.30 * a)))
            )
            c.song_blueprint_target_strength = float(
                max(0.0, min(1.0, max(float(getattr(c, "song_blueprint_target_strength", 0.72) or 0.72), 0.74 + 0.22 * a)))
            )
            c.cadence_first_harmony_strength = float(
                max(0.0, min(1.0, max(float(getattr(c, "cadence_first_harmony_strength", 0.78) or 0.78), 0.80 + 0.18 * a)))
            )
            c.motif_lifecycle_strength = float(
                max(0.0, min(1.0, max(float(getattr(c, "motif_lifecycle_strength", 0.70) or 0.70), 0.72 + 0.20 * a)))
            )
            c.arrangement_contracts_strength = float(
                max(0.0, min(1.0, max(float(getattr(c, "arrangement_contracts_strength", 0.72) or 0.72), 0.74 + 0.18 * a)))
            )
            c.section_k_samples = int(max(3, min(8, max(int(getattr(c, "section_k_samples", 3) or 3), int(round(3 + 2 * a))))))
            c.section_pick_time_budget_s = float(
                max(0.2, min(3.0, max(float(getattr(c, "section_pick_time_budget_s", 0.75) or 0.75), 0.85 + 0.60 * a)))
            )
            return

        raise ValueError(f"Unknown producer macro '{name}'")

    # ------------------------------------------------------------------
    # Composition hook-safe preset
    # ------------------------------------------------------------------
    def set_composition_hook_safe_mode(self, enabled: bool = True) -> None:
        """
        Apply or clear a hook-safe tuning preset for composition knobs.

        Enabled:
        - Stronger hook/motif restatements and alignment.
        - Heavier Markov conditioning (phrase role / function / style).
        - Slightly stronger cadence shaping and anti-repetition.
        - More conservative harmonic rhythm/comping around hooks.
        Disabled:
        - Restores the original baseline CompositionConfiguration snapshot.
        """
        if not hasattr(self, "_base_composition"):
            # Fallback: nothing to restore; only apply forwards.
            self._base_composition = deepcopy(self.composition)

        if not enabled:
            # Restore the original composition snapshot.
            self.composition = deepcopy(self._base_composition)
            try:
                self.composition.hook_safe_mode = False
            except Exception:
                logger.debug("hook-safe mode: failed clearing hook_safe_mode flag", exc_info=True)
            return

        c = self.composition
        # Mark mode flag for downstream consumers (if they want to branch on it).
        try:
            c.hook_safe_mode = True
        except Exception:
            logger.debug("hook-safe mode: failed setting hook_safe_mode flag", exc_info=True)

        # Motif / hook behaviour.
        c.motif_use_chance = max(0.88, float(getattr(c, "motif_use_chance", 0.88)))
        c.motif_variation_prob = min(0.12, float(getattr(c, "motif_variation_prob", 0.12)))
        c.hook_transform_strength = max(0.62, float(getattr(c, "hook_transform_strength", 0.6)))
        c.hook_anchor_degree_strength = max(0.8, float(getattr(c, "hook_anchor_degree_strength", 0.7)))
        c.motif_melody_alignment_strength = max(
            0.35, float(getattr(c, "motif_melody_alignment_strength", 0.25))
        )

        # Markov conditioning and style.
        c.markov_style_strength = max(0.45, float(getattr(c, "markov_style_strength", 0.45)))
        c.melody_phrase_role_model_blend = max(
            0.6, float(getattr(c, "melody_phrase_role_model_blend", 0.5))
        )
        c.melody_phrase_role_rhythm_model_blend = max(
            0.35, float(getattr(c, "melody_phrase_role_rhythm_model_blend", 0.25))
        )
        c.melody_function_condition_blend = max(
            0.5, float(getattr(c, "melody_function_condition_blend", 0.35))
        )
        c.melody_function_rhythm_condition_blend = max(
            0.35, float(getattr(c, "melody_function_rhythm_condition_blend", 0.22))
        )
        c.melody_global_markov_blend = max(
            0.24, float(getattr(c, "melody_global_markov_blend", 0.18))
        )

        # Anti-repetition.
        c.melody_ngram_penalty_strength = max(
            0.45, float(getattr(c, "melody_ngram_penalty_strength", 0.35))
        )
        c.melody_ngram_decay = min(0.90, float(getattr(c, "melody_ngram_decay", 0.92)))
        c.melody_loop_penalty_mult = min(0.5, float(getattr(c, "melody_loop_penalty_mult", 0.6)))
        c.melody_rhythm_repeat_penalty_mult = min(
            0.6, float(getattr(c, "melody_rhythm_repeat_penalty_mult", 0.7))
        )

        # Cadence shaping.
        c.cadence_strength = max(1.30, float(getattr(c, "cadence_strength", 1.15)))
        c.melody_cadence_strength = max(1.25, float(getattr(c, "melody_cadence_strength", 1.10)))

        # Phrase-level reranking (hooks).
        c.melody_phrase_rerank_entry_leap_penalty = max(
            0.26, float(getattr(c, "melody_phrase_rerank_entry_leap_penalty", 0.20))
        )
        c.melody_phrase_rerank_cadence_land_bonus = max(
            0.42, float(getattr(c, "melody_phrase_rerank_cadence_land_bonus", 0.35))
        )
        c.melody_phrase_rerank_cadence_approach_bonus = max(
            0.24, float(getattr(c, "melody_phrase_rerank_cadence_approach_bonus", 0.18))
        )

        # Harmonic rhythm / comping synchronisation.
        c.harmonic_rhythm_tension_sensitivity = max(
            0.4, float(getattr(c, "harmonic_rhythm_tension_sensitivity", 0.0))
        )
        c.harmonic_rhythm_markov_strength = max(
            0.7, float(getattr(c, "harmonic_rhythm_markov_strength", 0.65))
        )
        c.chord_intra_bar_change_strength = min(
            0.25, float(getattr(c, "chord_intra_bar_change_strength", 0.35))
        )
        c.chord_comping_anticipation_prob = min(
            0.06, float(getattr(c, "chord_comping_anticipation_prob", 0.10))
        )

        # Best-of-K selection.
        c.bestofk_enabled = True
        c.bestofk_k = max(4, int(getattr(c, "bestofk_k", 4)))
        c.bestofk_temperature_jitter = min(
            0.08, float(getattr(c, "bestofk_temperature_jitter", 0.10))
        )


def effective_tempo_bpm_from_config(config, emotion=None) -> float:
    """BPM for tests/stubs without ConfigurationManager.effective_section_tempo_bpm."""
    fn = getattr(config, "effective_section_tempo_bpm", None)
    if callable(fn):
        return float(fn(emotion))
    composition = getattr(config, "composition", None)
    base = float(getattr(composition, "default_tempo", 70.0))
    scale = max(0.25, min(4.0, float(getattr(composition, "global_tempo_scale", 1.0))))
    if emotion is None:
        return base * scale
    try:
        from data.audit import normalize_emotion_scalars

        em, _, _ = normalize_emotion_scalars(emotion)
    except Exception:
        em = float(getattr(emotion, "tempo_multiplier", 1.0) or 1.0)
    return base * scale * em


CONFIG = ConfigurationManager()
# Default favors output quality (samplers + master chain) over fastest cold start.
CONFIG.set_performance_mode("quality")


def resolve_config(group: str, attr: str, default: Any, type_conv: Optional[Any] = None, *, config: Any = None) -> Any:
    """Safe lookup of CONFIG attributes with fallback to default.

    Prevents boilerplate try-except blocks.
    """
    try:
        cfg = config if config is not None else CONFIG
        g = getattr(cfg, group, None)
        if g is None:
            return default
        if not attr:
            return g
        val = getattr(g, attr, None)
        if val is None:
            return default
        if type_conv is not None:
            try:
                if type_conv is bool:
                    if isinstance(val, str):
                        return val.strip().lower() in ("true", "1", "yes", "on")
                    return bool(val)
                return type_conv(val)
            except Exception:
                return default
        return val
    except Exception:
        return default
