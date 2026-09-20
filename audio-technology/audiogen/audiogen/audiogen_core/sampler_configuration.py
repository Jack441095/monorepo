from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional


class QualityMode(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class SamplerConfiguration:
    name: str
    file_path: str
    root_midi: int = 60
    pre_gain_db: float = 0.0
    post_gain_db: float = 0.0
    # Per-sampler amplitude gain (post synthesis, pre mix).
    # Example: -12.0 = 12dB quieter than nominal.
    amplitude_db: float = 0.0
    # Backward compatible: legacy linear multiplier. If present and != 1.0, it is applied in addition.
    amplitude: float = 1.0
    use_pitch_tracking_lowpass: bool = True
    lowpass_harmonic_multiplier: float = 4.0
    lowpass_min_cutoff: float = 200.0
    lowpass_max_cutoff: float = 7500.0
    # Optional fixed low-pass (2-pole / ~12dB per octave) applied post-render.
    # If set > 0, this runs in addition to (or instead of) pitch-tracked filtering.
    fixed_lowpass_hz: float = 0.0
    fixed_lowpass_q: float = 0.707
    use_dynamic_filter: bool = False
    channel: int = 0
    filter_order: int = 2
    disable_filter: bool = False
    # CPU-friendly sampler "character" filter options
    filter_model: str = "butter"          # butter | biquad
    filter_q: float = 0.707               # used by biquad (0.707 = Butterworth-ish)
    filter_drive: float = 0.0             # subtle saturation pre-filter (0..~0.3)
    vel_to_cutoff: float = 0.0            # velocity -> cutoff amount (0..1)
    start_jitter_ms: float = 0.0          # random start jitter per note (ms)
    # If True, pick a random start point within the loop region (or whole sample if no loop points),
    # then rely on looping to fill the note duration. Great for pads/chords to avoid identical hits.
    random_start_within_loop: bool = False
    dc_block_enabled: bool = True         # remove DC/low drift after rendering
    dc_block_cutoff_hz: float = 12.0      # source-level DC blocker cutoff at sample load
    adsr_attack: float = 0.01
    adsr_decay: float = 0.1
    adsr_sustain: float = 0.7
    adsr_release: float = 0.2
    envelope_curve: str = "linear"
    velocity_layers: Optional[List[Dict[str, Any]]] = None

    # ------------------------------------------------------------------
    # Velocity dynamics control (post-ADSR, pre mix)
    #
    # Many packs sound better with reduced velocity-to-amplitude depth in
    # algorithmic playback (avoids "too jumpy" dynamics while keeping articulation).
    #
    # strength:
    # - 1.0 => full velocity mapping (legacy behavior)
    # - 0.0 => no velocity amplitude effect (always unity gain)
    # ------------------------------------------------------------------
    velocity_amplitude_strength: float = 1.0
    # Optional hard clamp after applying velocity mapping (None disables).
    velocity_amplitude_min: Optional[float] = None
    velocity_amplitude_max: Optional[float] = None

    # Quality and enhancements
    quality_mode: QualityMode = QualityMode.MEDIUM
    # Transposition interpolation mode:
    # - "fast": linear interpolation (realtime-safe default)
    # - "hq": cubic interpolation (higher quality, higher CPU)
    # - "auto": use cubic only when quality_mode is HIGH
    transposition_quality_mode: str = "fast"
    resample_quality: str = "kaiser_fast"
    use_velocity_crossfade: bool = True
    start_offset: float = 0.0               # seconds to skip from sample start
    anti_alias_upward: bool = False
    attack_fade_ms: float = 2.0
    edge_fade_min_ms: float = 1.2
    loop_crossfade_ms: float = 8.0          # crossfade for loops
    loop_enabled: bool = False              # if False, ignore loop_start/loop_end entirely
    # When random_start_within_loop is enabled and no loop points are provided, allow looping the
    # entire sample (crossfade is still applied if configured).
    loop_whole_sample_if_missing_points: bool = True
    note_cache_maxsize: int = 64
    adsr_cache_maxsize: int = 32

    # Optional "stable shimmer" for pads/chords: granular looping with a slowly drifting
    # loop window (plus occasional reseed). Designed to reduce obvious repetition.
    shimmer_enabled: bool = False
    shimmer_grain_ms: float = 220.0          # grain size in output time
    shimmer_overlap: float = 0.75            # 0..0.95 (higher = smoother, more CPU)
    shimmer_looplet_ms: float = 800.0        # size of loop window inside loop points
    shimmer_drift_seconds: float = 4.0       # LFO drift period across the loop window span
    shimmer_reseed_seconds: float = 24.0     # how often to randomize drift phase (0 = never)
    shimmer_spray_ms: float = 20.0           # per-grain random position offset (+/- ms)
    shimmer_pan_spread: float = 0.12         # per-grain random pan (+/-), 0..1
    shimmer_time_jitter: float = 0.0         # per-grain hop jitter fraction, 0..0.5

    # Classic hardware sampler behaviour (pitch = speed, loop in original sample)
    classic_mode: bool = True               # enables variable‑rate playback
    portamento_time: float = 0.0            # glide time in seconds (0 = off)
    # Probability that a legato overlap triggers a glide (0..1). Keeps glides occasional.
    portamento_probability: float = 1.0
    # Additional gate window (ms) to allow glides on back-to-back notes (no overlap).
    # If None, the runtime uses `portamento_time` as the gate duration.
    portamento_gate_ms: Optional[float] = None

    # Filter envelope
    filter_envelope_enabled: bool = False
    filter_attack: float = 0.01
    filter_decay: float = 0.1
    filter_sustain: float = 0.7
    filter_release: float = 0.2
    filter_base_cutoff: float = 2000.0
    filter_peak_cutoff: float = 8000.0
    filter_env_curve: str = "linear"
