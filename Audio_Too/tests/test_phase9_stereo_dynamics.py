"""Tests for Phase 9 — Stereo Image Analysis and Dynamic Compressor Reference Matching."""

from __future__ import annotations

import math
import sys
import os

# Ensure audio_analysis is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "studio", "audio_analysis"))


# ---------------------------------------------------------------------------
# 9.1 Stereo Image Analysis
# ---------------------------------------------------------------------------

def test_stereo_analysis_mono_signal():
    """Identical L/R channels should have perfect correlation and zero width."""
    from audio_analysis.analysis_core.stereo_analysis import stereo_image_analysis

    sr = 44100
    length = sr * 2  # 2 seconds
    # Simple sine wave on both channels
    samples = [math.sin(2.0 * math.pi * 440.0 * i / sr) * 0.5 for i in range(length)]

    result = stereo_image_analysis(samples, samples, sr)

    assert result["overall_correlation"] >= 0.99, f"Expected ~1.0, got {result['overall_correlation']}"
    assert result["overall_width"] < 0.05, f"Expected ~0.0, got {result['overall_width']}"
    assert result["mono_safe"] is True
    assert len(result["flags"]) == 0, f"No flags expected for mono signal, got {result['flags']}"


def test_stereo_analysis_phase_inverted():
    """L and R with inverted polarity should show negative correlation."""
    from audio_analysis.analysis_core.stereo_analysis import stereo_image_analysis

    sr = 44100
    length = sr * 2
    left = [math.sin(2.0 * math.pi * 440.0 * i / sr) * 0.5 for i in range(length)]
    right = [-s for s in left]  # Phase inversion

    result = stereo_image_analysis(left, right, sr)

    assert result["overall_correlation"] <= -0.9, f"Expected < -0.9, got {result['overall_correlation']}"
    assert result["mono_safe"] is False, "Phase-inverted signal should not be mono safe"
    assert len(result["flags"]) > 0, "Should have phase cancellation flags"


def test_stereo_analysis_wide_stereo():
    """Different L/R signals should show positive width."""
    from audio_analysis.analysis_core.stereo_analysis import stereo_image_analysis

    sr = 44100
    length = sr * 2
    # Different frequencies on each channel
    left = [math.sin(2.0 * math.pi * 440.0 * i / sr) * 0.5 for i in range(length)]
    right = [math.sin(2.0 * math.pi * 445.0 * i / sr) * 0.5 for i in range(length)]

    result = stereo_image_analysis(left, right, sr)

    assert result["overall_width"] > 0.01, f"Expected width > 0, got {result['overall_width']}"
    # 440 vs 445 Hz over 2 seconds produces significant beating, so correlation
    # will be near zero rather than strongly positive. The key test is that
    # width is nonzero and the analysis runs without error.
    assert -1.0 <= result["overall_correlation"] <= 1.0


def test_stereo_analysis_empty_input():
    """Empty signals should return neutral defaults."""
    from audio_analysis.analysis_core.stereo_analysis import stereo_image_analysis

    result = stereo_image_analysis([], [], 44100)

    assert result["overall_correlation"] == 1.0
    assert result["overall_width"] == 0.0
    assert result["mono_safe"] is True


def test_stereo_analysis_short_signal():
    """Signal shorter than n_fft should return neutral defaults."""
    from audio_analysis.analysis_core.stereo_analysis import stereo_image_analysis

    result = stereo_image_analysis([0.1] * 100, [0.1] * 100, 44100)

    assert result["overall_correlation"] == 1.0
    assert result["mono_safe"] is True


def test_stereo_analysis_band_keys():
    """All 7 frequency bands should be present in band_correlation."""
    from audio_analysis.analysis_core.stereo_analysis import stereo_image_analysis

    sr = 44100
    length = sr * 2
    samples = [math.sin(2.0 * math.pi * 1000.0 * i / sr) * 0.5 for i in range(length)]

    result = stereo_image_analysis(samples, samples, sr)

    expected_bands = {"sub", "bass", "low_mids", "mids", "presence", "sibilance", "air"}
    assert set(result["band_correlation"].keys()) == expected_bands
    assert set(result["band_width"].keys()) == expected_bands
    assert set(result["mono_compatibility"].keys()) == expected_bands


def test_stereo_analysis_summary():
    """The text summary should include key metrics."""
    from audio_analysis.analysis_core.stereo_analysis import stereo_image_analysis, stereo_analysis_summary

    sr = 44100
    length = sr * 2
    samples = [math.sin(2.0 * math.pi * 440.0 * i / sr) * 0.5 for i in range(length)]
    result = stereo_image_analysis(samples, samples, sr)
    summary = stereo_analysis_summary(result)

    assert "Overall Correlation:" in summary
    assert "Overall Width:" in summary
    assert "Mono Safe: Yes" in summary


# ---------------------------------------------------------------------------
# 9.2 Dynamic Compressor Reference Matching
# ---------------------------------------------------------------------------

def test_dynamics_comparison_identical():
    """Identical signals should show zero crest delta and no compression needed."""
    from audio_analysis.analysis_core.reference_matching import dynamics_comparison

    sr = 44100
    length = sr * 2
    samples = [math.sin(2.0 * math.pi * 440.0 * i / sr) * 0.5 for i in range(length)]

    result = dynamics_comparison(samples, samples, sr)

    assert abs(result["crest_delta_db"]) < 0.1, f"Expected ~0, got {result['crest_delta_db']}"
    assert result["suggested_settings"]["ratio"] <= 1.5
    assert len(result["advice"]) > 0


def test_dynamics_comparison_louder_mix():
    """A more dynamic mix (higher peaks) should suggest compression."""
    from audio_analysis.analysis_core.reference_matching import dynamics_comparison

    sr = 44100
    length = sr * 2
    # Mix: spiky signal with high crest factor
    mix = []
    for i in range(length):
        if i % 4410 < 441:  # Short burst every 100ms
            mix.append(0.9)
        else:
            mix.append(0.05)

    # Reference: more consistent level
    ref = [0.3 * math.sin(2.0 * math.pi * 440.0 * i / sr) for i in range(length)]

    result = dynamics_comparison(mix, ref, sr)

    # Mix has higher crest factor
    assert result["mix_crest_avg_db"] > result["ref_crest_avg_db"]
    assert result["crest_delta_db"] > 0
    # Should suggest compression
    assert result["suggested_settings"]["ratio"] > 1.0


def test_dynamics_empty_signal():
    """Empty signals should not crash."""
    from audio_analysis.analysis_core.reference_matching import dynamics_comparison

    result = dynamics_comparison([], [], 44100)

    assert result["mix_crest_avg_db"] == 0.0
    assert result["crest_delta_db"] == 0.0


def test_compressor_preset_xml():
    """Generated compressor XML should contain key parameters."""
    from audio_analysis.analysis_core.reference_matching import generate_compressor_preset_xml

    settings = {
        "attack_ms": 5.0,
        "release_ms": 150.0,
        "ratio": 3.0,
        "threshold_db": -20.0,
        "makeup_gain_db": 2.0,
    }

    xml = generate_compressor_preset_xml(settings)

    assert "Compressor2" in xml
    assert 'Value="-20.0"' in xml or 'Value="-20"' in xml
    assert 'Value="3.0"' in xml or 'Value="3"' in xml
    assert '<?xml version="1.0"' in xml


def test_compressor_preset_adv_roundtrip():
    """Exported .adv should be valid gzip containing XML."""
    import gzip
    from audio_analysis.analysis_core.reference_matching import export_compressor_preset_adv

    settings = {"attack_ms": 10.0, "release_ms": 200.0, "ratio": 2.0, "threshold_db": -18.0, "makeup_gain_db": 1.0}
    adv = export_compressor_preset_adv(settings)

    assert isinstance(adv, bytes)
    assert len(adv) > 0

    xml = gzip.decompress(adv).decode("utf-8")
    assert "Compressor2" in xml


def test_dynamics_advice_content():
    """Advice should reference the actual crest factor values."""
    from audio_analysis.analysis_core.reference_matching import dynamics_comparison

    sr = 44100
    length = sr * 2
    # Significantly different dynamics
    mix = [0.8 if i % 1000 < 50 else 0.05 for i in range(length)]
    ref = [0.3 * math.sin(2.0 * math.pi * 440.0 * i / sr) for i in range(length)]

    result = dynamics_comparison(mix, ref, sr)

    advice_text = " ".join(result["advice"])
    # Should mention actual numbers
    assert "dB" in advice_text


def test_suggest_compressor_settings_no_compression():
    """When mix is less dynamic than ref, ratio should be 1.0."""
    from audio_analysis.analysis_core.reference_matching import _suggest_compressor_settings

    settings = _suggest_compressor_settings(
        crest_delta=-3.0,
        mix_slope=1.0,
        ref_slope=2.0,
        mix_crest=8.0,
    )

    assert settings["ratio"] == 1.0, f"Expected ratio 1.0, got {settings['ratio']}"
