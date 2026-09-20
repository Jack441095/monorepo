from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ReverbFXConfig:
    enabled: bool = True
    rt60: float = 20.8
    damping: float = 0.62
    wet: float = 0.60

    predelay_ms: float = 28.0
    early_reflections_enabled: bool = True
    early_reflections_level: float = 0.24

    return_highpass_hz: float = 500.0
    return_highpass_slope_db_per_oct: float = 12.0
    return_lowpass_hz: float = 9500.0  # 0 disables
    return_lowpass_slope_db_per_oct: float = 12.0


@dataclass
class DelayFXConfig:
    enabled: bool = True
    time_ms: float = 320.0
    feedback: float = 0.21
    return_level: float = 0.72

    pingpong: float = 0.35
    feedback_highpass_hz: float = 180.0
    feedback_lowpass_hz: float = 3200.0
    feedback_filter_slope_db_per_oct: float = 12.0


@dataclass
class DistortionFXConfig:
    enabled: bool = True
    drive: float = 1.35
    mix: float = 0.08
    bus_enabled: bool = True
    bus_return_level: float = 0.08

    tone_highpass_hz: float = 140.0
    tone_lowpass_hz: float = 9000.0
    tone_slope_db_per_oct: float = 12.0


@dataclass
class EffectsConfiguration:
    reverb: ReverbFXConfig = ReverbFXConfig()
    delay: DelayFXConfig = DelayFXConfig()
    distortion: DistortionFXConfig = DistortionFXConfig()


def effects_from_audio_config(audio: Any) -> EffectsConfiguration:
    """
    Extract an `EffectsConfiguration` view from the existing `AudioConfiguration`.
    This is intentionally a pure adaptor so the codebase can migrate gradually.
    """
    a = audio
    return EffectsConfiguration(
        reverb=ReverbFXConfig(
            enabled=bool(getattr(a, "reverb_enabled", True)),
            rt60=float(getattr(a, "reverb_rt60", 10.0)),
            damping=float(getattr(a, "reverb_damping", 0.62)),
            wet=float(getattr(a, "reverb_wet", 0.24)),
            predelay_ms=float(getattr(a, "reverb_predelay_ms", 28.0)),
            early_reflections_enabled=bool(getattr(a, "reverb_early_reflections_enabled", True)),
            early_reflections_level=float(getattr(a, "reverb_early_reflections_level", 0.24)),
            return_highpass_hz=float(getattr(a, "reverb_return_highpass_hz", 500.0)),
            return_highpass_slope_db_per_oct=float(getattr(a, "reverb_return_highpass_slope_db_per_oct", 12.0)),
            return_lowpass_hz=float(getattr(a, "reverb_return_lowpass_hz", 9500.0)),
            return_lowpass_slope_db_per_oct=float(getattr(a, "reverb_return_lowpass_slope_db_per_oct", 12.0)),
        ),
        delay=DelayFXConfig(
            enabled=bool(getattr(a, "delay_bus_enabled", True)),
            time_ms=float(getattr(a, "delay_bus_time_ms", 320.0)),
            feedback=float(getattr(a, "delay_bus_feedback", 0.21)),
            return_level=float(getattr(a, "delay_bus_return_level", 0.32)),
            pingpong=float(getattr(a, "delay_bus_pingpong", 0.35)),
            feedback_highpass_hz=float(getattr(a, "delay_bus_feedback_highpass_hz", 180.0)),
            feedback_lowpass_hz=float(getattr(a, "delay_bus_feedback_lowpass_hz", 8200.0)),
            feedback_filter_slope_db_per_oct=float(
                getattr(a, "delay_bus_feedback_filter_slope_db_per_oct", 12.0)
            ),
        ),
        distortion=DistortionFXConfig(
            enabled=bool(getattr(a, "distortion_enabled", True)),
            drive=float(getattr(a, "distortion_drive", 1.35)),
            mix=float(getattr(a, "distortion_mix", 0.08)),
            bus_enabled=bool(getattr(a, "distortion_bus_enabled", True)),
            bus_return_level=float(getattr(a, "distortion_bus_return_level", 0.08)),
            tone_highpass_hz=float(getattr(a, "distortion_tone_highpass_hz", 140.0)),
            tone_lowpass_hz=float(getattr(a, "distortion_tone_lowpass_hz", 9000.0)),
            tone_slope_db_per_oct=float(getattr(a, "distortion_tone_slope_db_per_oct", 12.0)),
        ),
    )


def apply_effects_to_audio_config(audio: Any, fx: EffectsConfiguration) -> None:
    """
    Apply an `EffectsConfiguration` onto the existing `AudioConfiguration`.
    This keeps current wiring (AudioContainer/MasterBus/Reverb) working unchanged.
    """
    r = fx.reverb
    d = fx.delay
    ds = fx.distortion

    setattr(audio, "reverb_enabled", bool(r.enabled))
    setattr(audio, "reverb_rt60", float(r.rt60))
    setattr(audio, "reverb_damping", float(r.damping))
    setattr(audio, "reverb_wet", float(r.wet))
    setattr(audio, "reverb_predelay_ms", float(r.predelay_ms))
    setattr(audio, "reverb_early_reflections_enabled", bool(r.early_reflections_enabled))
    setattr(audio, "reverb_early_reflections_level", float(r.early_reflections_level))
    setattr(audio, "reverb_return_highpass_hz", float(r.return_highpass_hz))
    setattr(audio, "reverb_return_highpass_slope_db_per_oct", float(r.return_highpass_slope_db_per_oct))
    setattr(audio, "reverb_return_lowpass_hz", float(r.return_lowpass_hz))
    setattr(audio, "reverb_return_lowpass_slope_db_per_oct", float(r.return_lowpass_slope_db_per_oct))

    setattr(audio, "delay_bus_enabled", bool(d.enabled))
    setattr(audio, "delay_bus_time_ms", float(d.time_ms))
    setattr(audio, "delay_bus_feedback", float(d.feedback))
    setattr(audio, "delay_bus_return_level", float(d.return_level))
    setattr(audio, "delay_bus_pingpong", float(d.pingpong))
    setattr(audio, "delay_bus_feedback_highpass_hz", float(d.feedback_highpass_hz))
    setattr(audio, "delay_bus_feedback_lowpass_hz", float(d.feedback_lowpass_hz))
    setattr(audio, "delay_bus_feedback_filter_slope_db_per_oct", float(d.feedback_filter_slope_db_per_oct))

    setattr(audio, "distortion_enabled", bool(ds.enabled))
    setattr(audio, "distortion_drive", float(ds.drive))
    setattr(audio, "distortion_mix", float(ds.mix))
    setattr(audio, "distortion_bus_enabled", bool(ds.bus_enabled))
    setattr(audio, "distortion_bus_return_level", float(ds.bus_return_level))
    setattr(audio, "distortion_tone_highpass_hz", float(ds.tone_highpass_hz))
    setattr(audio, "distortion_tone_lowpass_hz", float(ds.tone_lowpass_hz))
    setattr(audio, "distortion_tone_slope_db_per_oct", float(ds.tone_slope_db_per_oct))


def maybe_apply_effects_layer(audio: Any, fx_layer: Optional[dict]) -> None:
    """
    Convenience: apply a partial dict layer onto `EffectsConfiguration` and push
    into `audio`. Intended for future preset/UI migration.
    """
    if not isinstance(fx_layer, dict) or not fx_layer:
        return
    cur = effects_from_audio_config(audio)
    # Extremely small, explicit schema: only apply keys that exist.
    for section_name in ("reverb", "delay", "distortion"):
        sec = fx_layer.get(section_name)
        if not isinstance(sec, dict):
            continue
        obj = getattr(cur, section_name)
        for k, v in sec.items():
            if hasattr(obj, str(k)):
                setattr(obj, str(k), v)
    apply_effects_to_audio_config(audio, cur)

