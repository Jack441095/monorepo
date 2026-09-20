
"""Tests for ml_api.py — ML endpoint wrapper.

Covers:
- analyze_quality()            — 3 tests
- analyze_anomalies()          — 2 tests
"""

from __future__ import annotations


from ml_api import detect_anomalies, predict_quality


SAMPLE_VECTOR = {
    "peak_dbfs": -3.0,
    "rms_dbfs_estimate": -18.0,
    "crest_factor_db": 14.0,
    "stereo_correlation": 0.82,
    "bands_mids": 0.35,
    "perceptual_bands_mids": 0.40,
}


class TestAnalyzeQuality:

    def test_default_prediction(self):
        """No model → optimistic default."""
        result = predict_quality({"metrics": SAMPLE_VECTOR}, model=None)
        assert result["accepted"] is True
        assert result["confidence"] == 0.5

    def test_with_model(self):
        """Model provided → prediction."""
        model = {
            "feature_weights": {"peak_dbfs": 0.8, "crest_factor_db": 0.5},
            "accepted_mean": {"peak_dbfs": -3.0, "crest_factor_db": 14.0},
            "rejected_mean": {"peak_dbfs": -10.0, "crest_factor_db": 8.0},
            "decision_threshold": 0.5,
            "training_count": 10,
        }
        result = predict_quality({"metrics": SAMPLE_VECTOR}, model=model)
        assert result["score"] > 0.5
        assert len(result.get("metric_detail", {})) >= 1

    def test_empty_vector(self):
        """Empty vector → default."""
        result = predict_quality({"metrics": {}}, model=None)
        assert result["accepted"] is True


class TestAnalyzeAnomalies:

    def test_no_history(self):
        """No history → zero outliers."""
        result = detect_anomalies({"metrics": SAMPLE_VECTOR}, history=[])
        assert result["outlier_count"] == 0

    def test_with_history(self):
        """History with same values → no outliers."""
        history = [
            {"features": {"peak_dbfs": -3.0, "crest_factor_db": 14.0}},
            {"features": {"peak_dbfs": -3.5, "crest_factor_db": 13.5}},
            {"features": {"peak_dbfs": -2.8, "crest_factor_db": 14.5}},
        ]
        result = detect_anomalies({"metrics": SAMPLE_VECTOR}, history=history)
        # Should not flag anything extreme
        assert result["ok"] is True
