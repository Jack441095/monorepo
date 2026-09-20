"""Regression coverage for stereo-preserving AutoMix rendering."""

from __future__ import annotations

import numpy as np

from audio_analysis.mixdown.mix_decision_engine import BusMixConfig, MixPlan, StemMixConfig
from audio_analysis.mixdown.mix_renderer import mix_and_render_stems


def test_renderer_keeps_distinct_source_channels_through_stem_processing() -> None:
    sample_rate = 16_000
    time = np.arange(sample_rate) / sample_rate
    left = 0.12 * np.sin(2.0 * np.pi * 330.0 * time)
    right = 0.08 * np.sin(2.0 * np.pi * 660.0 * time)
    prepared = [{
        "name": "Keys.wav",
        "samples": (0.5 * (left + right)).tolist(),
        "left_samples": left.tolist(),
        "right_samples": right.tolist(),
        "stereo_preserved": True,
        "sample_rate": sample_rate,
    }]
    plan = MixPlan(
        stems=[StemMixConfig(
            stem_name="Keys.wav", instrument="keys", mono_below_hz=0.0
        )],
        bus=BusMixConfig(limiter_ceiling_db=-1.0),
        genre="rock",
        target_lufs=-14.0,
    )

    result = mix_and_render_stems(prepared, plan, capture_stem_audio=True)
    rendered_left, rendered_right = result["stem_audio"]["Keys.wav"]

    assert not np.allclose(rendered_left, rendered_right)
    assert np.corrcoef(rendered_left, left)[0, 1] > 0.999
    assert np.corrcoef(rendered_right, right)[0, 1] > 0.999
