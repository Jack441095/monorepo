
"""Tests for quality_predictor.py — ML model training and prediction.

Covers:
- _label_score()                    — 4 tests
- _feature_mean()                   — 2 tests
- _feature_std()                    — 2 tests
- _pearson_correlation()            — 3 tests
- _effect_size()                    — 3 tests
- _nan_safe()                       — 3 tests
- train_from_history()              — 3 tests
- predict_quality()                 — 4 tests
- quality_snapshot()                — 2 tests
- compute_training_readiness()      — 3 tests
"""

from __future__ import annotations

import pytest

from audio_analysis.integration.quality_predictor import (
    _label_score,
    _feature_mean,
    _feature_std,
    _pearson_correlation,
    _effect_size,
    _nan_safe,
    train_from_history,
    predict_quality,
    quality_snapshot,
    compute_training_readiness,
)

# ==============================================================================
#  _label_score
# ==============================================================================

class TestLabelScore:

    def test_accepted(self):
        assert _label_score("yes") == 1.0
        assert _label_score("accepted") == 1.0
        assert _label_score("good") == 1.0

    def test_revise(self):
        assert _label_score("revise") == 0.5
        assert _label_score("needs_work") == 0.5
        assert _label_score("almost") == 0.5

    def test_skip(self):
        assert _label_score("skip") is None
        assert _label_score("unrelated") is None

    def test_rejected(self):
        assert _label_score("no") == 0.0
        assert _label_score("bad") == 0.0
        assert _label_score("rejected") == 0.0


# ==============================================================================
#  _feature_mean & _feature_std
# ==============================================================================

class TestFeatureMean:
    def test_empty(self):
        assert _feature_mean([]) == 0.0

    def test_normal(self):
        assert _feature_mean([1.0, 2.0, 3.0]) == 2.0


class TestFeatureStd:
    def test_single(self):
        assert _feature_std([5.0], 5.0) == 0.0

    def test_normal(self):
        std = _feature_std([1.0, 2.0, 3.0], 2.0)
        assert std == pytest.approx(1.0, abs=0.01)


# ==============================================================================
#  _pearson_correlation
# ==============================================================================

class TestPearsonCorrelation:

    def test_few_values(self):
        """< 3 values → 0.0."""
        assert _pearson_correlation([1.0], [2.0]) == 0.0

    def test_perfect_positive(self):
        x = [1.0, 2.0, 3.0]
        y = [2.0, 4.0, 6.0]
        assert _pearson_correlation(x, y) == pytest.approx(1.0, abs=0.01)

    def test_perfect_negative(self):
        x = [1.0, 2.0, 3.0]
        y = [6.0, 4.0, 2.0]
        assert _pearson_correlation(x, y) == pytest.approx(-1.0, abs=0.01)

    def test_zero_variance(self):
        assert _pearson_correlation([1.0, 1.0, 1.0], [2.0, 3.0, 4.0]) == 0.0


# ==============================================================================
#  _effect_size (Cohen's d)
# ==============================================================================

class TestEffectSize:

    def test_insufficient_data(self):
        assert _effect_size([1.0], [2.0]) == 0.0

    def test_no_difference(self):
        a = [1.0, 2.0, 3.0]
        b = [1.0, 2.0, 3.0]
        d = _effect_size(a, b)
        assert d == pytest.approx(0.0, abs=0.01)

    def test_large_difference(self):
        a = [10.0, 11.0, 10.5]
        b = [1.0, 2.0, 1.5]
        d = _effect_size(a, b)
        assert d > 0.5, f"Expected large positive effect, got {d}"


# ==============================================================================
#  _nan_safe
# ==============================================================================

class TestNanSafe:

    def test_none(self):
        assert _nan_safe(None) is None

    def test_nan(self):
        assert _nan_safe(float("nan")) is None

    def test_valid_float(self):
        assert _nan_safe(3.14) == 3.14

    def test_string(self):
        assert _nan_safe("3.14") == 3.14

    def test_bad_string(self):
        assert _nan_safe("n/a") is None


# ==============================================================================
#  train_from_history
# ==============================================================================

class TestTrainFromHistory:

    def test_empty_history(self):
        model = train_from_history([])
        assert model["training_count"] == 0
        assert model["feature_weights"] == {}

    def test_basic_training(self):
        records = [
            {"decision": "yes", "features": {"peak_dbfs": -3.0, "crest_factor_db": 14.0, "rms_dbfs_estimate": -18.0}},
            {"decision": "yes", "features": {"peak_dbfs": -4.0, "crest_factor_db": 13.0, "rms_dbfs_estimate": -19.0}},
            {"decision": "no", "features": {"peak_dbfs": -10.0, "crest_factor_db": 8.0, "rms_dbfs_estimate": -25.0}},
            {"decision": "no", "features": {"peak_dbfs": -12.0, "crest_factor_db": 7.0, "rms_dbfs_estimate": -26.0}},
        ]
        model = train_from_history(records)
        assert model["training_count"] == 4
        assert model["accepted_count"] == 2
        assert model["rejected_count"] == 2
        assert "peak_dbfs" in model["feature_weights"]
        assert len(model["feature_importance"]) > 0

    def test_training_with_none_values(self):
        """Records with None feature values are handled gracefully."""
        records = [
            {"decision": "yes", "features": {"peak_dbfs": -3.0}},
            {"decision": "yes", "features": {"peak_dbfs": -4.0}},
            {"decision": "no", "features": {"peak_dbfs": -10.0}},
            {"decision": "no", "features": {"peak_dbfs": None}},
        ]
        model = train_from_history(records)
        # The None value should be filtered out, rejected still has 1 value → insufficient
        assert model["training_count"] >= 3


# ==============================================================================
#  predict_quality
# ==============================================================================

class TestPredictQuality:

    def test_empty_model(self):
        """Model with no weights → default optimistic prediction."""
        prediction = predict_quality({"feature_weights": {}}, {"peak_dbfs": -3.0})
        assert prediction["accepted"] is True
        assert prediction["confidence"] == 0.5
        assert "Insufficient" in prediction["note"]

    def test_basic_prediction(self):
        """Model with known weights → prediction is computed."""
        model = {
            "feature_weights": {"peak_dbfs": 0.8, "crest_factor_db": 0.5},
            "accepted_mean": {"peak_dbfs": -3.0, "crest_factor_db": 14.0},
            "rejected_mean": {"peak_dbfs": -10.0, "crest_factor_db": 8.0},
            "decision_threshold": 0.5,
            "training_count": 20,
        }
        # Value very close to accepted mean
        vector = {"peak_dbfs": -3.5, "crest_factor_db": 13.5}
        prediction = predict_quality(model, vector)
        assert prediction["score"] > 0.5
        assert prediction["features_analysed"] == 2

    def test_improvement_areas_flagged(self):
        """Value closer to rejected mean → appears in improvement_areas."""
        model = {
            "feature_weights": {"peak_dbfs": 0.8},
            "accepted_mean": {"peak_dbfs": -3.0},
            "rejected_mean": {"peak_dbfs": -10.0},
            "decision_threshold": 0.5,
            "training_count": 10,
        }
        vector = {"peak_dbfs": -9.0}  # close to rejected mean
        prediction = predict_quality(model, vector)
        assert len(prediction["improvement_areas"]) >= 1
        assert prediction["improvement_areas"][0]["metric"] == "peak_dbfs"

    def test_metric_detail_included(self):
        model = {
            "feature_weights": {"peak_dbfs": 0.8},
            "accepted_mean": {"peak_dbfs": -3.0},
            "rejected_mean": {"peak_dbfs": -10.0},
            "decision_threshold": 0.5,
            "training_count": 10,
        }
        vector = {"peak_dbfs": -5.0}
        prediction = predict_quality(model, vector)
        assert "peak_dbfs" in prediction["metric_detail"]
        detail = prediction["metric_detail"]["peak_dbfs"]
        assert detail["value"] == -5.0


# ==============================================================================
#  quality_snapshot
# ==============================================================================

class TestQualitySnapshot:

    def test_no_improvement_areas(self):
        model = {
            "feature_weights": {"peak_dbfs": 0.8},
            "accepted_mean": {"peak_dbfs": -3.0},
            "rejected_mean": {"peak_dbfs": -10.0},
            "decision_threshold": 0.5,
            "training_count": 10,
        }
        vector = {"peak_dbfs": -3.0}
        snapshot = quality_snapshot(vector, model)
        assert snapshot["ok"] is True
        assert "narrative" in snapshot

    def test_snapshot_with_improvements(self):
        model = {
            "feature_weights": {"peak_dbfs": 0.8, "crest_factor_db": 0.5},
            "accepted_mean": {"peak_dbfs": -3.0, "crest_factor_db": 14.0},
            "rejected_mean": {"peak_dbfs": -10.0, "crest_factor_db": 8.0},
            "decision_threshold": 0.5,
            "training_count": 10,
        }
        vector = {"peak_dbfs": -9.0, "crest_factor_db": 9.0}
        snapshot = quality_snapshot(vector, model)
        assert len(snapshot["improvement_areas"]) > 0
        assert snapshot["accepted"] is not None


# ==============================================================================
#  compute_training_readiness
# ==============================================================================

class TestComputeTrainingReadiness:

    def test_no_data(self):
        result = compute_training_readiness([])
        assert result["ready"] is False
        assert result["total"] == 0

    def test_not_enough_accepted(self):
        records = [
            {"decision": "yes", "features": {"peak_dbfs": -3.0}},
            {"decision": "yes", "features": {"peak_dbfs": -4.0}},
            {"decision": "no", "features": {"peak_dbfs": -10.0}},
            {"decision": "no", "features": {"peak_dbfs": -11.0}},
            {"decision": "no", "features": {"peak_dbfs": -12.0}},
        ]
        result = compute_training_readiness(records)
        assert result["ready"] is False
        assert result["accepted_count"] == 2
        assert result["rejected_count"] == 3

    def test_ready(self):
        records = [
            {"decision": "yes", "features": {"peak_dbfs": -3.0, "crest_factor_db": 14.0, "rms_dbfs_estimate": -18.0, "true_peak_dbfs": -2.0, "dc_offset": 0.001}},
            {"decision": "yes", "features": {"peak_dbfs": -4.0, "crest_factor_db": 13.0, "rms_dbfs_estimate": -19.0, "true_peak_dbfs": -3.0, "dc_offset": 0.002}},
            {"decision": "yes", "features": {"peak_dbfs": -5.0, "crest_factor_db": 12.0, "rms_dbfs_estimate": -20.0, "true_peak_dbfs": -4.0, "dc_offset": 0.001}},
            {"decision": "no", "features": {"peak_dbfs": -10.0, "crest_factor_db": 8.0, "rms_dbfs_estimate": -25.0, "true_peak_dbfs": -9.0, "dc_offset": 0.01}},
            {"decision": "no", "features": {"peak_dbfs": -12.0, "crest_factor_db": 7.0, "rms_dbfs_estimate": -26.0, "true_peak_dbfs": -11.0, "dc_offset": 0.015}},
            {"decision": "no", "features": {"peak_dbfs": -11.0, "crest_factor_db": 9.0, "rms_dbfs_estimate": -24.0, "true_peak_dbfs": -10.0, "dc_offset": 0.012}},
        ]
        result = compute_training_readiness(records)
        assert result["ready"] is True
        assert result["accepted_count"] >= 3
        assert result["rejected_count"] >= 3
        assert result["features_with_both"] >= 5
