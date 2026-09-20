# core/config_samplers.py
# Project module `config_samplers` (core).

import logging
from copy import deepcopy
from pathlib import Path

from audiogen_core.config_utils import resolve_project_path

logger = logging.getLogger(__name__)

def base_sampler_templates(config):
    return {
        "bass": {
            "name": "bass",
            "file_path": "samples/bass.wav",
            "root_midi": 29,
            "use_pitch_tracking_lowpass": True,
            "lowpass_harmonic_multiplier": 4.0,
            "lowpass_min_cutoff": 150.0,
            "lowpass_max_cutoff": 350.0,
            "use_dynamic_filter": True,
            "channel": 0,
            "filter_order": 1,
            # Bass should speak immediately; any extra attack reads as "soft" / less pluck.
            "adsr_attack": 0.05,
            "adsr_decay": 6.0,
            "adsr_sustain": 0.0,
            "adsr_release": 0.0,
            "envelope_curve": "linear",
            "amplitude_db": -12.0,
            "quality_mode": config.QualityMode.MEDIUM,
            "transposition_quality_mode": "auto",
            "use_velocity_crossfade": False,
            # Add LPF envelope articulation (drone is excluded; bass is not).
            "filter_envelope_enabled": True,
            "filter_attack": 0.01,
            "filter_decay": 0.12,
            "filter_sustain": 0.0,
            "filter_release": 0.08,
            "filter_base_cutoff": 140.0,
            "filter_peak_cutoff": 520.0,
            "filter_env_curve": "exponential",
            # Keep only a tiny anti-click fade; larger fades dull transients.
            "attack_fade_ms": 0.4,
            "loop_crossfade_ms": 8.0,

        },
        "chords": {
            "name": "chords",
            "file_path": "samples/chords.wav",
            "root_midi": 60,
            "loop_enabled": True,
            # Static low-pass only (no filter envelope / shimmer).
            "use_pitch_tracking_lowpass": False,
            "fixed_lowpass_hz": 1000.0,
            "fixed_lowpass_q": 0.707,
            "channel": 1,
            "filter_order": 2,
            "adsr_attack": 0.01,
            "adsr_decay": 32.0,
            "adsr_sustain": 0.0,
            "adsr_release": 1.0,
            "envelope_curve": "linear",
            "filter_envelope_enabled": True,
            "filter_attack": 0.02,
            "filter_decay": 0.25,
            "filter_sustain": 0.0,
            "filter_release": 0.75,
            "filter_base_cutoff": 650.0,
            "filter_peak_cutoff": 2400.0,
            "filter_env_curve": "exponential",
            "amplitude_db": -9.0,
            "quality_mode": config.QualityMode.HIGH,
            "transposition_quality_mode": "auto",
            "attack_fade_ms": 2.0,
            "loop_crossfade_ms": 12.0,
            "random_start_within_loop": True,
            "shimmer_enabled": False,
            # chords are polyphonic – classic_mode and portamento not typically used
        },
        "melody": {
            "name": "melody",
            "file_path": "samples/melody.wav",
            "root_midi": 60,
            "channel": 2,
            "filter_order": 2,
            # Pitch-tracked lowpass (keytracking): tuned for brighter arps without harshness.
            "use_pitch_tracking_lowpass": False,
            "lowpass_harmonic_multiplier": 3.8,
            "lowpass_min_cutoff": 1000.0,
            "lowpass_max_cutoff": 9500.0,
            # "Simpler-ish" character (CPU friendly)
            "filter_model": "biquad",
            "filter_q": 0.95,
            "filter_drive": 0.08,
            "vel_to_cutoff": 0.35,
            "start_jitter_ms": 7.0,
            "adsr_attack": 0.00,
            "adsr_decay": 0.2,
            "adsr_sustain": 0,
            "adsr_release": 0.2,
            "envelope_curve": "linear",
            "filter_envelope_enabled": True,
            "filter_attack": 0.02,
            "filter_decay": 0.1,
            "filter_sustain": 0.0,
            "filter_release": 0.5,
            "filter_base_cutoff": 2000.0,
            "filter_peak_cutoff": 10000.0,
            "filter_env_curve": "exponential",
            "amplitude_db": -12.0,
            "quality_mode": config.QualityMode.HIGH,
            "transposition_quality_mode": "auto",
            # Classic hardware sampler settings:
            "classic_mode": True,           # pitch = speed, loop points in original sample
            # Monophonic legato glide on overlaps (12 ms).
            "portamento_time": 0.020,
            "portamento_probability": 0.55,
            # Allow glides even when notes are back-to-back (no overlap).
            "portamento_gate_ms": 25.0,
            # Avoid softening the pick/transient.
            "attack_fade_ms": 0.0,
            "loop_crossfade_ms": 8.0,       # small crossfade reduces loop clicks
            # Optional: define loop points in the original sample (in samples)
            # "loop_start": 16000,
            # "loop_end": 64000,
        },
        "arp": {
            "name": "arp",
            # Reuse the melody sample by default (packs can override).
            "file_path": "samples/arp.wav",
            "root_midi": 60,
            "channel": 3,
            "filter_order": 2,
            "use_pitch_tracking_lowpass": False,
            "lowpass_harmonic_multiplier": 3.6,
            "lowpass_min_cutoff": 700.0,
            "lowpass_max_cutoff": 9800.0,
            "filter_model": "biquad",
            "filter_q": 0.85,
            "filter_drive": 0.05,
            "vel_to_cutoff": 0.25,
            "start_jitter_ms": 2.0,
            # Plucky instruments should start immediately.
            "adsr_attack": 0.0,
            "adsr_decay": 0.15,
            "adsr_sustain": 0,
            "adsr_release": 0.16,
            "envelope_curve": "linear",
            "filter_envelope_enabled": True,
            "filter_attack": 0.02,
            "filter_decay": 0.10,
            "filter_sustain": 0.0,
            "filter_release": 0.32,
            "filter_base_cutoff": 1100.0,
            "filter_peak_cutoff": 7600.0,
            "filter_env_curve": "exponential",
            # Arp is dense and often perceptually masked; stage it slightly hotter by default.
            "amplitude_db": -12.0,
            "quality_mode": config.QualityMode.MEDIUM,
            "transposition_quality_mode": "auto",
            "classic_mode": True,
            # Slightly more audible glide than melody (still subtle).
            "portamento_time": 0.020,
            "portamento_probability": 0.70,
            "portamento_gate_ms": 25.0,
            "attack_fade_ms": 0.0,
            "loop_crossfade_ms": 6.0,
        },
        "drone": {
            "name": "drone",
            "file_path": "samples/drone.wav",
            "root_midi": 60,
            "loop_enabled": True,
            "channel": 4,
            "use_pitch_tracking_lowpass": False,
            "filter_order": 1,
            "disable_filter": True,
            "adsr_attack": 0.5,
            "adsr_decay": 0.0,
            "adsr_sustain": 1.0,
            "adsr_release": 1.0,
            "envelope_curve": "linear",
            "amplitude_db": -24.0,
            "quality_mode": config.QualityMode.LOW,
            "transposition_quality_mode": "fast",
            "attack_fade_ms": 8.0,
            "loop_crossfade_ms": 20.0,
            # Drone usually doesn't need portamento
        },
        "counter_melody": {
            "name": "counter_melody",
            # Reuse lead sample by default; packs may override.
            "file_path": "samples/melody.wav",
            "root_midi": 60,
            "channel": 5,
            "filter_order": 2,
            "use_pitch_tracking_lowpass": False,
            "lowpass_harmonic_multiplier": 3.6,
            "lowpass_min_cutoff": 900.0,
            "lowpass_max_cutoff": 9200.0,
            "filter_model": "biquad",
            "filter_q": 0.92,
            "filter_drive": 0.06,
            "vel_to_cutoff": 0.30,
            "start_jitter_ms": 3.0,
            # Plucky instruments should start immediately.
            "adsr_attack": 0.0,
            "adsr_decay": 0.28,
            "adsr_sustain": 0,
            "adsr_release": 0.45,
            "envelope_curve": "linear",
            "filter_envelope_enabled": True,
            "filter_attack": 0.02,
            "filter_decay": 0.12,
            "filter_sustain": 0.78,
            "filter_release": 0.45,
            "filter_base_cutoff": 2200.0,
            "filter_peak_cutoff": 9800.0,
            "filter_env_curve": "exponential",
            "amplitude_db": -13.0,
            "quality_mode": config.QualityMode.HIGH,
            "transposition_quality_mode": "auto",
            "classic_mode": True,
            "portamento_time": 0.020,
            "portamento_probability": 0.45,
            "portamento_gate_ms": 25.0,
            "attack_fade_ms": 0.0,
            "loop_crossfade_ms": 8.0,
        },
    }


def infer_sample_pack_path(pack_name: str, sampler_name: str) -> str:
    if pack_name == "default":
        return f"samples/{sampler_name}.wav"
    directory_style = Path("samples") / pack_name / f"{sampler_name}.wav"
    if resolve_project_path(directory_style).exists() or resolve_project_path(Path("samples") / pack_name).is_dir():
        return str(directory_style)
    return f"samples/{sampler_name}_{pack_name}.wav"


def initialize_sampler_configurations(config):
    base_templates = base_sampler_templates(config)
    default_pack = config.sample_packs.get("default", {})
    active_pack = config.sample_packs.get(config.active_sample_pack, {})
    samplers = []

    for sampler_name in config.SAMPLER_ORDER:
        sampler_kwargs = deepcopy(base_templates[sampler_name])
        sampler_kwargs.update(default_pack.get(sampler_name, {}))
        pack_channel = active_pack.get(sampler_name)
        if sampler_name not in active_pack and config.active_sample_pack != "default":
            logger.warning(
                "Sample pack '%s' missing channel '%s'; falling back to default",
                config.active_sample_pack,
                sampler_name,
            )
        sampler_kwargs.update(pack_channel or {})
        inferred_path = infer_sample_pack_path(config.active_sample_pack, sampler_name)
        if (
            config.active_sample_pack != "default"
            and pack_channel is not None
            and "file_path" not in pack_channel
        ):
            sampler_kwargs["file_path"] = inferred_path
        s = config.SamplerConfiguration(**sampler_kwargs)
        # Global: reduce velocity→amplitude swings unless explicitly overridden by pack/template.
        if "velocity_amplitude_strength" not in sampler_kwargs:
            try:
                s.velocity_amplitude_strength = 0.6
            except Exception:
                pass
        samplers.append(s)
    # Map CONFIG.audio.drone_loop_volume into the drone sampler amplitude.
    # This keeps the UI/FX-facing control authoritative even when drone is rendered as sampler notes.
    try:
        base_vol = 0.4
        vol = float(getattr(getattr(config, "audio", None), "drone_loop_volume", base_vol) or base_vol)
        vol = max(0.0, min(2.0, vol))
        if base_vol > 1e-9 and vol > 1e-9:
            import math

            delta_db = 20.0 * math.log10(float(vol) / float(base_vol))
        else:
            delta_db = 0.0
        for s in samplers:
            if getattr(s, "name", "") == "drone":
                try:
                    s.amplitude_db = float(getattr(s, "amplitude_db", 0.0) or 0.0) + float(delta_db)
                except Exception:
                    pass
                break
    except Exception:
        pass
    return samplers
