"""Tests for build_source_vs_delivery_comparison() -- the "raw upload vs
finished mixdown" before/after evidence for an AutoMix render.
"""

from __future__ import annotations

import numpy as np

from audio_analysis.mix_review.source_delivery_comparison import (
    build_quality_receipt,
    build_source_vs_delivery_comparison,
)
from audio_analysis.mixdown.stem_prep import write_wav

SR = 44100
DURATION_S = 3.0
_BAND_KEYS = {"sub", "bass", "low_mids", "mids", "presence", "sibilance", "air"}


def _tone_wav(amplitude: float, freq: float = 440.0) -> bytes:
    n = int(SR * DURATION_S)
    t = np.arange(n) / SR
    signal = (amplitude * np.sin(2 * np.pi * freq * t)).tolist()
    return write_wav(signal, signal, SR, bit_depth=16)


def test_louder_after_mix_shows_a_positive_lufs_delta():
    quiet_source = _tone_wav(0.05)
    loud_delivery = _tone_wav(0.5)

    comparison = build_source_vs_delivery_comparison(quiet_source, loud_delivery)

    assert comparison["before"]["integrated_lufs"] < comparison["after"]["integrated_lufs"]
    assert comparison["deltas"]["integrated_lufs"] > 0


def test_before_and_after_expose_the_7_band_spectral_split():
    wav = _tone_wav(0.2)

    comparison = build_source_vs_delivery_comparison(wav, wav)

    assert set(comparison["before"]["bands"]) == _BAND_KEYS
    assert set(comparison["after"]["bands"]) == _BAND_KEYS
    assert set(comparison["before"]["perceptual_bands"]) == _BAND_KEYS
    assert set(comparison["after"]["perceptual_bands"]) == _BAND_KEYS


def test_identical_before_and_after_have_near_zero_deltas():
    wav = _tone_wav(0.2)

    comparison = build_source_vs_delivery_comparison(wav, wav)

    for key, delta in comparison["deltas"].items():
        assert delta is not None, key
        assert abs(delta) < 0.05, (key, delta)


def test_returns_the_expected_top_level_shape():
    wav = _tone_wav(0.2)

    comparison = build_source_vs_delivery_comparison(wav, wav)

    assert set(comparison) == {"before", "after", "deltas"}
    assert set(comparison["deltas"]) == {
        "integrated_lufs", "true_peak_dbfs", "crest_factor_db",
        "stereo_correlation", "technical_score",
    }


def test_quality_receipt_preserves_provenance_deltas_and_gate() -> None:
    wav = _tone_wav(0.2)
    comparison = build_source_vs_delivery_comparison(wav, wav)
    receipt = build_quality_receipt(comparison, {
        "passed": True, "safety_passed": True, "advisory_score_passed": True,
        "technical_score": 81, "minimum_score": 65, "hard_failures": [],
    })

    assert receipt["schema"] == "automix.quality_receipt.v1"
    assert receipt["verification_available"] is True
    assert receipt["source_feature_set"]["source_hash"] == receipt["delivery_feature_set"]["source_hash"]
    assert receipt["measured_deltas"] == comparison["deltas"]
    assert receipt["safety_gate"]["passed"] is True
    assert receipt["safety_gate"]["safety_passed"] is True
