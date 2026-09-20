"""Tests for Fletcher-Munson / ISO 226 equal loudness contours and advice integration."""

from __future__ import annotations

import pytest
from audio_analysis.analysis_core.dsp_metrics import equal_loudness_contour, equal_loudness_gain
from audio_analysis.analysis_core.fletcher_munson_advice import fm_mix_critique
from audio_analysis.mix_review.mix_review import goal_target_checks
from audio_analysis.integration.handoff import kenn_handoff


def test_equal_loudness_contour_calculation():
    # 1 kHz reference check (should match phon level)
    for phon in [20, 40, 60, 80]:
        assert equal_loudness_contour(1000, phon) == pytest.approx(phon, abs=0.5)
        
    # Low frequency roll-off sensitivity check
    assert equal_loudness_contour(50, 60) > equal_loudness_contour(1000, 60)


def test_equal_loudness_gain_factor():
    # At 1 kHz, gain is 1.0 (0 dB)
    assert equal_loudness_gain(1000, 60) == pytest.approx(1.0, abs=0.01)
    
    # Low frequency has less sensitivity, meaning gain factor is small
    assert equal_loudness_gain(20, 60) < 0.1


def test_fm_mix_critique_generation():
    perceived = {
        "sub": 0.22,
        "bass": 0.22,
        "low_mids": 0.20,
        "mids": 0.10,
        "presence": 0.05,
        "air": 0.05
    }
    # Bottom heavy, low presence
    advice = fm_mix_critique({}, perceived, [], 60)
    assert any("bottom-heavy" in msg for msg in advice)
    assert any("Presence" in msg and "low" in msg for msg in advice)


def test_dynamic_goal_target_checks():
    # Mock metrics that satisfy other premaster requirements to avoid unrelated warnings
    metrics = {
        "mix_goal": {"key": "premaster", "label": "Premaster"},
        "peak_dbfs": -2.0,
        "true_peak_dbfs": -2.0,
        "crest_factor_db": 10.0,
        "stereo_correlation": 0.5,
        "tonal_balance": {"low_end_share": 0.54},
    }
    
    # 60 phon - low_end_share is above premaster limit (0.52) -> warn
    checks_60 = goal_target_checks(metrics, 60.0)
    low_end_60 = next(c for c in checks_60["checks"] if "low-end" in c["label"].lower())
    assert low_end_60["status"] == "warn"
    
    # 40 phon - limits are loosened (allow more low end raw share to compensate for roll-off) -> pass!
    checks_40 = goal_target_checks(metrics, 40.0)
    low_end_40 = next(c for c in checks_40["checks"] if "low-end" in c["label"].lower())
    assert low_end_40["status"] == "pass"


def test_handoff_payload_contains_equal_loudness():
    report = {
        "title": "Test Mix",
        "summary": "Nice track.",
        "metrics": {
            "technical_score": 85,
            "peak_dbfs": -1.2,
            "rms_dbfs_estimate": -14.0,
            "perceptual_bands": {
                "sub": 0.05,
                "bass": 0.20,
                "low_mids": 0.20,
                "mids": 0.30,
                "presence": 0.20,
                "air": 0.05
            },
            "perceptual_summary": {
                "dominant_band": "mids"
            }
        }
    }
    payload = kenn_handoff(report)
    assert payload["schema"] == "kenn_mix_review_handoff.v1"
    assert "Fletcher-Munson" in payload["context"]
    assert "perceived loudness shares" in payload["context"].lower()
