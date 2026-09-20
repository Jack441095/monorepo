"""Tests for the quality predictor module."""

from __future__ import annotations

from audio_analysis.integration.quality_predictor import (
    train_from_history,
    predict_quality,
    quality_snapshot,
    compute_training_readiness,
)


def _make_labelled_record(
    decision: str,
    *,
    score: float = 75.0,
    crest: float = 8.5,
    rms: float = -18.0,
    peak: float = -3.0,
    correlation: float = 0.85,
    width: float = 0.70,
    sub: float = 0.25,
    low_mids: float = 0.15,
    presence: float = 0.12,
    dynamic_range: float = 14.0,
    dc_offset: float = 0.0,
    centroid: float = 2500.0,
) -> dict:
    return {
        "decision": decision,
        "features": {
            "peak_dbfs": peak,
            "rms_dbfs_estimate": rms,
            "crest_factor_db": crest,
            "true_peak_dbfs": peak - 1.5,
            "integrated_lufs": rms + 4.0,
            "stereo_correlation": correlation,
            "stereo_width_ratio": width,
            "stereo_balance": 0.0,
            "dynamic_range_estimate_db": dynamic_range,
            "dc_offset": dc_offset,
            "clipped_frames_estimate": 0.0,
            "clipping_risk": 0.0,
            "bands_sub": sub,
            "bands_bass": 0.18,
            "bands_low_mids": low_mids,
            "bands_mids": 0.20,
            "bands_presence": presence,
            "bands_sibilance": 0.05,
            "bands_air": 0.05,
            "perceptual_bands_sub": sub * 0.8,
            "perceptual_bands_bass": 0.15,
            "perceptual_bands_low_mids": low_mids * 0.8,
            "perceptual_bands_mids": 0.22,
            "perceptual_bands_presence": presence * 1.1,
            "perceptual_bands_sibilance": 0.08,
            "perceptual_bands_air": 0.09,
            "perceived_presence_share": presence * 0.9,
            "perceived_low_end_share": sub * 1.2,
            "centroid_hz": centroid,
            "rolloff_85_hz": 8000.0,
            "high_frequency_share": 0.12,
            "tonal_low_end_share": 0.35,
            "tonal_body_share": 0.35,
            "tonal_clarity_share": 0.30,
            "tonal_perceived_clarity_share": 0.28,
            "dynamic_crest_factor_db": crest,
            "dynamic_transient_margin_db": 6.0,
            "dynamic_short_term_range_db": 5.0,
            "dynamic_section_range_db": 8.0,
            "stereo_low_side_share": 0.03,
            "stereo_low_band_correlation": 0.85,
            "section_rms_mean": rms,
            "section_count": 8.0,
            "correlation_sub": 0.90,
            "correlation_bass": 0.85,
            "correlation_low_mids": 0.75,
            "correlation_mids": 0.80,
            "correlation_presence": 0.80,
            "correlation_sibilance": 0.75,
            "correlation_air": 0.70,
            "technical_score": score,
        },
    }


def test_train_from_history_returns_model_with_no_data() -> None:
    model = train_from_history([])
    assert model["training_count"] == 0
    assert model["feature_weights"] == {}
    assert model["feature_importance"] == []
    assert model["decision_threshold"] == 0.5


def test_train_from_history_learns_from_labelled_data() -> None:
    # 5 accepted (good quality)
    accepted = [
        _make_labelled_record("yes", crest=10.0, rms=-16.0, peak=-2.0, dynamic_range=16.0)
        for _ in range(5)
    ]
    # 5 rejected (poor quality)
    rejected = [
        _make_labelled_record("no", crest=3.0, rms=-22.0, peak=-6.0, dynamic_range=6.0)
        for _ in range(5)
    ]
    records = accepted + rejected

    model = train_from_history(records)

    assert model["training_count"] == 10
    assert model["accepted_count"] == 5
    assert model["rejected_count"] == 5
    assert len(model["feature_weights"]) > 0
    assert len(model["feature_importance"]) > 0


def test_train_from_history_assigns_weights_correctly() -> None:
    # Use small variations so std > 0 for effect size calculation
    accepted = [
        _make_labelled_record("yes", crest=11.8 + i * 0.2, sub=0.15 - i * 0.01)
        for i in range(5)
    ]
    rejected = [
        _make_labelled_record("no", crest=3.2 - i * 0.1, sub=0.48 + i * 0.02)
        for i in range(5)
    ]

    model = train_from_history(accepted + rejected)

    # crest_factor_db should have a positive weight (higher crest = accepted)
    crest_weight = model["feature_weights"].get("crest_factor_db", 0)
    assert crest_weight > 0, f"Expected positive crest weight, got {crest_weight}"

    # bands_sub should have a negative weight (more sub = rejected in this case)
    sub_weight = model["feature_weights"].get("bands_sub", 0)
    assert sub_weight < 0, f"Expected negative sub weight, got {sub_weight}"


def test_predict_quality_accepts_good_mix() -> None:
    # Slight variation so groups have std > 0
    accepted = [
        _make_labelled_record("yes", crest=10.0 + i * 0.2, dynamic_range=15.0 + i * 0.2, dc_offset=0.0)
        for i in range(5)
    ]
    rejected = [
        _make_labelled_record("no", crest=2.0 - i * 0.1, dynamic_range=5.0 - i * 0.2, dc_offset=0.05 + i * 0.01)
        for i in range(5)
    ]
    model = train_from_history(accepted + rejected)

    # A good mix should be accepted
    good_vector = {
        "peak_dbfs": -2.0,
        "rms_dbfs_estimate": -16.0,
        "crest_factor_db": 11.0,
        "true_peak_dbfs": -3.5,
        "integrated_lufs": -12.0,
        "stereo_correlation": 0.88,
        "stereo_width_ratio": 0.72,
        "stereo_balance": 0.0,
        "dynamic_range_estimate_db": 15.0,
        "dc_offset": 0.0,
        "clipped_frames_estimate": 0.0,
        "clipping_risk": 0.0,
        "bands_sub": 0.22,
        "bands_bass": 0.18,
        "bands_low_mids": 0.14,
        "bands_mids": 0.20,
        "bands_presence": 0.13,
        "bands_sibilance": 0.05,
        "bands_air": 0.08,
        "perceptual_bands_sub": 0.18,
        "perceptual_bands_bass": 0.15,
        "perceptual_bands_low_mids": 0.11,
        "perceptual_bands_mids": 0.22,
        "perceptual_bands_presence": 0.14,
        "perceptual_bands_sibilance": 0.08,
        "perceptual_bands_air": 0.12,
        "perceived_presence_share": 0.24,
        "perceived_low_end_share": 0.30,
        "centroid_hz": 2800.0,
        "rolloff_85_hz": 9000.0,
        "high_frequency_share": 0.14,
        "tonal_low_end_share": 0.32,
        "tonal_body_share": 0.35,
        "tonal_clarity_share": 0.33,
        "tonal_perceived_clarity_share": 0.30,
        "dynamic_crest_factor_db": 11.0,
        "dynamic_transient_margin_db": 7.0,
        "dynamic_short_term_range_db": 6.0,
        "dynamic_section_range_db": 9.0,
        "stereo_low_side_share": 0.03,
        "stereo_low_band_correlation": 0.85,
        "section_rms_mean": -16.0,
        "section_count": 8.0,
        "correlation_sub": 0.92,
        "correlation_bass": 0.88,
        "correlation_low_mids": 0.78,
        "correlation_mids": 0.82,
        "correlation_presence": 0.80,
        "correlation_sibilance": 0.75,
        "correlation_air": 0.70,
        "technical_score": 85.0,
    }

    prediction = predict_quality(model, good_vector)

    assert prediction["accepted"] is True
    assert prediction["score"] >= model["decision_threshold"]
    assert prediction["confidence"] >= 0.5
    assert len(prediction["improvement_areas"]) == 0


def test_predict_quality_rejects_poor_mix() -> None:
    # Slight variation so groups have std > 0
    accepted = [
        _make_labelled_record("yes", crest=10.0 + i * 0.2, dynamic_range=15.0 + i * 0.2, dc_offset=0.0)
        for i in range(5)
    ]
    rejected = [
        _make_labelled_record("no", crest=2.0 - i * 0.1, dynamic_range=5.0 - i * 0.2, dc_offset=0.05 + i * 0.01)
        for i in range(5)
    ]
    model = train_from_history(accepted + rejected)

    # A bad mix should be rejected
    bad_vector = {
        "peak_dbfs": -0.2,
        "rms_dbfs_estimate": -5.0,
        "crest_factor_db": 1.5,
        "true_peak_dbfs": -1.7,
        "integrated_lufs": -1.0,
        "stereo_correlation": 0.40,
        "stereo_width_ratio": 0.30,
        "stereo_balance": 0.15,
        "dynamic_range_estimate_db": 3.0,
        "dc_offset": 0.08,
        "clipped_frames_estimate": 500.0,
        "clipping_risk": 1.0,
        "bands_sub": 0.65,
        "bands_bass": 0.15,
        "bands_low_mids": 0.08,
        "bands_mids": 0.05,
        "bands_presence": 0.03,
        "bands_sibilance": 0.02,
        "bands_air": 0.02,
        "perceptual_bands_sub": 0.55,
        "perceptual_bands_bass": 0.12,
        "perceptual_bands_low_mids": 0.06,
        "perceptual_bands_mids": 0.06,
        "perceptual_bands_presence": 0.04,
        "perceptual_bands_sibilance": 0.02,
        "perceptual_bands_air": 0.03,
        "perceived_presence_share": 0.05,
        "perceived_low_end_share": 0.60,
        "centroid_hz": 800.0,
        "rolloff_85_hz": 4000.0,
        "high_frequency_share": 0.03,
        "tonal_low_end_share": 0.60,
        "tonal_body_share": 0.25,
        "tonal_clarity_share": 0.15,
        "tonal_perceived_clarity_share": 0.12,
        "dynamic_crest_factor_db": 1.5,
        "dynamic_transient_margin_db": 2.0,
        "dynamic_short_term_range_db": 2.0,
        "dynamic_section_range_db": 3.0,
        "stereo_low_side_share": 0.15,
        "stereo_low_band_correlation": 0.40,
        "section_rms_mean": -5.0,
        "section_count": 6.0,
        "correlation_sub": 0.30,
        "correlation_bass": 0.45,
        "correlation_low_mids": 0.50,
        "correlation_mids": 0.55,
        "correlation_presence": 0.50,
        "correlation_sibilance": 0.60,
        "correlation_air": 0.65,
        "technical_score": 30.0,
    }

    prediction = predict_quality(model, bad_vector)

    assert prediction["accepted"] is False
    assert prediction["score"] < model["decision_threshold"]
    assert len(prediction["improvement_areas"]) > 0


def test_predict_quality_returns_improvement_areas() -> None:
    accepted = [
        _make_labelled_record("yes", crest=10.0 + i * 0.2, dynamic_range=15.0 + i * 0.2, presence=0.15)
        for i in range(5)
    ]
    rejected = [
        _make_labelled_record("no", crest=2.0 - i * 0.1, dynamic_range=5.0 - i * 0.2, presence=0.05)
        for i in range(5)
    ]
    model = train_from_history(accepted + rejected)

    mid_vector = {
        "peak_dbfs": -3.0,
        "rms_dbfs_estimate": -18.0,
        "crest_factor_db": 5.0,
        "true_peak_dbfs": -4.5,
        "integrated_lufs": -14.0,
        "stereo_correlation": 0.85,
        "stereo_width_ratio": 0.70,
        "stereo_balance": 0.0,
        "dynamic_range_estimate_db": 10.0,
        "dc_offset": 0.0,
        "clipped_frames_estimate": 0.0,
        "clipping_risk": 0.0,
        "bands_sub": 0.25,
        "bands_bass": 0.18,
        "bands_low_mids": 0.15,
        "bands_mids": 0.20,
        "bands_presence": 0.10,
        "bands_sibilance": 0.05,
        "bands_air": 0.05,
        "perceptual_bands_sub": 0.20,
        "perceptual_bands_bass": 0.15,
        "perceptual_bands_low_mids": 0.12,
        "perceptual_bands_mids": 0.22,
        "perceptual_bands_presence": 0.11,
        "perceptual_bands_sibilance": 0.08,
        "perceptual_bands_air": 0.09,
        "perceived_presence_share": 0.20,
        "perceived_low_end_share": 0.35,
        "centroid_hz": 2300.0,
        "rolloff_85_hz": 8000.0,
        "high_frequency_share": 0.12,
        "tonal_low_end_share": 0.35,
        "tonal_body_share": 0.35,
        "tonal_clarity_share": 0.30,
        "tonal_perceived_clarity_share": 0.28,
        "dynamic_crest_factor_db": 5.0,
        "dynamic_transient_margin_db": 6.0,
        "dynamic_short_term_range_db": 5.0,
        "dynamic_section_range_db": 8.0,
        "stereo_low_side_share": 0.03,
        "stereo_low_band_correlation": 0.85,
        "section_rms_mean": -18.0,
        "section_count": 8.0,
        "correlation_sub": 0.90,
        "correlation_bass": 0.85,
        "correlation_low_mids": 0.75,
        "correlation_mids": 0.80,
        "correlation_presence": 0.80,
        "correlation_sibilance": 0.75,
        "correlation_air": 0.70,
        "technical_score": 60.0,
    }

    prediction = predict_quality(model, mid_vector)

    # Should have improvement areas since values are between accepted/rejected
    assert len(prediction["improvement_areas"]) > 0
    assert "crest_factor_db" in [a["metric"] for a in prediction["improvement_areas"]]


def test_predict_quality_handles_no_model_weights() -> None:
    model = {"feature_weights": {}, "accepted_mean": {}, "rejected_mean": {}, "decision_threshold": 0.5, "training_count": 0}
    vector = {"crest_factor_db": 8.0, "rms_dbfs_estimate": -18.0}
    prediction = predict_quality(model, vector)

    assert prediction["accepted"] is True
    assert prediction["confidence"] == 0.5
    assert prediction["improvement_areas"] == []


def test_quality_snapshot_returns_readable_narrative() -> None:
    accepted = [
        _make_labelled_record("yes", crest=11.0 + i * 0.2, dynamic_range=16.0 + i * 0.2)
        for i in range(5)
    ]
    rejected = [
        _make_labelled_record("no", crest=2.0 - i * 0.1, dynamic_range=4.0 - i * 0.2)
        for i in range(5)
    ]
    model = train_from_history(accepted + rejected)

    vector = {
        "peak_dbfs": -2.5,
        "rms_dbfs_estimate": -17.0,
        "crest_factor_db": 10.0,
        "stereo_correlation": 0.85,
        "stereo_width_ratio": 0.70,
        "dynamic_range_estimate_db": 15.0,
        "dc_offset": 0.0,
        "clipped_frames_estimate": 0.0,
        "clipping_risk": 0.0,
    }

    snapshot = quality_snapshot(vector, model)

    assert snapshot["ok"] is True
    assert isinstance(snapshot["narrative"], str)
    assert len(snapshot["narrative"]) > 0


def test_compute_training_readiness_returns_not_ready_for_empty() -> None:
    readiness = compute_training_readiness([])
    assert readiness["ready"] is False
    assert readiness["total"] == 0


def test_compute_training_readiness_returns_ready_for_enough_data() -> None:
    accepted = [
        _make_labelled_record("yes") for _ in range(5)
    ]
    rejected = [
        _make_labelled_record("no") for _ in range(5)
    ]
    readiness = compute_training_readiness(accepted + rejected)

    assert readiness["ready"] is True
    assert readiness["accepted_count"] >= 3
    assert readiness["rejected_count"] >= 3


def test_compute_training_readiness_handles_neutral_decisions() -> None:
    records = [
        _make_labelled_record("skip"),
        _make_labelled_record("note"),
        _make_labelled_record("unrelated"),
    ]
    readiness = compute_training_readiness(records)
    assert readiness["total"] == 0  # No actionable labels
    assert readiness["ready"] is False


def test_needs_work_counts_as_rejected_not_accepted() -> None:
    """Regression for a real bug found 2026-07-12: "needs_work" (and
    "revise"/"almost"/"partial") score exactly 0.5 in _label_score(), and
    both train_from_history() and compute_training_readiness() used to
    bucket with `label >= 0.5`, silently counting every needs-work review
    as an *accepted* training example -- exactly backwards, since a user
    clicking "Needs work" is saying the mix is not acceptable as-is. Found
    while investigating why mix_feedback_features' real data was skewed
    100% accepted / 0% rejected."""
    records = [_make_labelled_record("needs_work") for _ in range(5)]
    readiness = compute_training_readiness(records)
    assert readiness["accepted_count"] == 0
    assert readiness["rejected_count"] == 5

    accepted = [_make_labelled_record("yes") for _ in range(5)]
    model = train_from_history(accepted + records)
    assert model["accepted_count"] == 5
    assert model["rejected_count"] == 5


def test_predict_quality_handles_missing_features_gracefully() -> None:
    accepted = [
        _make_labelled_record("yes") for _ in range(3)
    ]
    rejected = [
        _make_labelled_record("no") for _ in range(3)
    ]
    model = train_from_history(accepted + rejected)

    # Partial vector
    vector = {"crest_factor_db": 8.0, "rms_dbfs_estimate": -18.0}
    prediction = predict_quality(model, vector)

    assert "accepted" in prediction
    assert "confidence" in prediction
    assert "improvement_areas" in prediction
