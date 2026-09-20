from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass
class PostProcessingPreset:
    name: str
    reverb_rt60: float
    reverb_damping: float
    reverb_wet: float
    distortion_drive: float
    distortion_mix: float
    # Optional: shape the global reverb return to avoid low-mid mud.
    # When 0, the preset doesn't override the current config's values.
    reverb_return_highpass_hz: float = 0.0
    reverb_return_highpass_slope_db_per_oct: float = 0.0
    delay_pingpong: float = 0.0
    delay_feedback_highpass_hz: float = 0.0
    delay_feedback_lowpass_hz: float = 0.0
    distortion_tone_highpass_hz: float = 0.0
    distortion_tone_lowpass_hz: float = 0.0


def default_post_process_presets() -> Dict[str, PostProcessingPreset]:
    # Keep this as a function so callers always get a fresh dict.
    return {
        "calm": PostProcessingPreset(
            name="calm",
            reverb_rt60=10.0,
            reverb_damping=0.68,
            reverb_wet=0.45,
            reverb_return_highpass_hz=0.0,
            reverb_return_highpass_slope_db_per_oct=0.0,
            distortion_drive=1.25,
            distortion_mix=0.05,
            delay_pingpong=0.22,
            delay_feedback_highpass_hz=160.0,
            delay_feedback_lowpass_hz=9200.0,
            distortion_tone_highpass_hz=140.0,
            distortion_tone_lowpass_hz=9500.0,
        ),
        # Shorter, clearer space for melodic/topline material.
        "melodic": PostProcessingPreset(
            name="melodic",
            reverb_rt60=3.4,
            reverb_damping=0.58,
            reverb_wet=0.33,
            reverb_return_highpass_hz=950.0,
            reverb_return_highpass_slope_db_per_oct=12.0,
            distortion_drive=1.20,
            distortion_mix=0.04,
            delay_pingpong=0.16,
            delay_feedback_highpass_hz=200.0,
            delay_feedback_lowpass_hz=9000.0,
            distortion_tone_highpass_hz=160.0,
            distortion_tone_lowpass_hz=9500.0,
        ),
        "ambient": PostProcessingPreset(
            name="ambient",
            reverb_rt60=10.0,
            reverb_damping=0.48,
            reverb_wet=0.60,
            reverb_return_highpass_hz=0.0,
            reverb_return_highpass_slope_db_per_oct=0.0,
            distortion_drive=1.15,
            distortion_mix=0.03,
            delay_pingpong=0.44,
            delay_feedback_highpass_hz=180.0,
            delay_feedback_lowpass_hz=7800.0,
            distortion_tone_highpass_hz=160.0,
            distortion_tone_lowpass_hz=9000.0,
        ),
        "lush_long": PostProcessingPreset(
            name="lush_long",
            reverb_rt60=13.5,
            reverb_damping=0.44,
            reverb_wet=0.36,
            reverb_return_highpass_hz=0.0,
            reverb_return_highpass_slope_db_per_oct=0.0,
            distortion_drive=1.12,
            distortion_mix=0.02,
            # Vintage dark delay: tighter low end + rolled-off highs in the feedback loop.
            delay_pingpong=0.46,
            delay_feedback_highpass_hz=240.0,
            delay_feedback_lowpass_hz=5200.0,
            distortion_tone_highpass_hz=180.0,
            distortion_tone_lowpass_hz=8500.0,
        ),
        "aggressive": PostProcessingPreset(
            name="aggressive",
            reverb_rt60=10.0,
            reverb_damping=0.72,
            reverb_wet=0.12,
            reverb_return_highpass_hz=0.0,
            reverb_return_highpass_slope_db_per_oct=0.0,
            distortion_drive=2.8,
            distortion_mix=0.28,
            delay_pingpong=0.12,
            delay_feedback_highpass_hz=220.0,
            delay_feedback_lowpass_hz=6500.0,
            distortion_tone_highpass_hz=220.0,
            distortion_tone_lowpass_hz=7500.0,
        ),
    }
