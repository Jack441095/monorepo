"""Stage J, use case #1 — tests for project_glm.py.

There is currently zero real historical AutoMix job data to train a
production model on (checked directly against the live DB during this
stage's own scoping: 33 automix_jobs rows but no persisted MixPlan
history). These tests instead prove the fitting/evaluation machinery
itself is statistically correct, using synthetic data with a known
linear relationship -- the same honest split this codebase already uses
elsewhere (e.g. song_rerank_model.py's own tests fit against synthetic
metrics, not unavailable production audit data).
"""

from __future__ import annotations

import numpy as np
import pytest

from audio_analysis.integration.project_features import PROJECT_FEATURE_NAMES
from audio_analysis.integration.project_glm import (
    MIN_HELDOUT_ROWS,
    MIN_TRAINING_ROWS,
    ProjectGLM,
    compute_project_training_readiness,
    evaluate_project_glm,
    fit_project_glm,
)


def _synthetic_rows(n: int, *, seed: int = 0) -> list[dict]:
    """Rows with a known linear relationship: target depends mostly on
    mean_crest_factor_db and stem_count, with small noise on everything
    else -- lets the test assert the fit recovers the dominant signal."""
    rng = np.random.default_rng(seed)
    rows = []
    for _ in range(n):
        features = {name: float(rng.normal(0, 1)) for name in PROJECT_FEATURE_NAMES}
        features["stem_count"] = float(rng.integers(2, 20))
        features["mean_crest_factor_db"] = float(rng.normal(12, 3))
        target = -0.8 * features["mean_crest_factor_db"] + 0.05 * features["stem_count"] + rng.normal(0, 0.2)
        rows.append({"features": features, "target_value": target})
    return rows


def test_readiness_reports_not_ready_below_threshold() -> None:
    rows = [{"features": {}, "target_value": 1.0}] * 5
    readiness = compute_project_training_readiness(rows)
    assert readiness["ready"] is False
    assert readiness["total"] == 5
    assert "Need at least" in readiness["recommended"]


def test_readiness_reports_ready_above_threshold() -> None:
    rows = _synthetic_rows(MIN_TRAINING_ROWS + MIN_HELDOUT_ROWS + 5)
    readiness = compute_project_training_readiness(rows)
    assert readiness["ready"] is True
    assert "ready" in readiness["recommended"].lower()


def test_readiness_ignores_rows_with_missing_target() -> None:
    rows = _synthetic_rows(30)
    rows[0]["target_value"] = None
    readiness = compute_project_training_readiness(rows)
    assert readiness["total"] == 29


def test_fit_raises_below_minimum_rows() -> None:
    rows = _synthetic_rows(MIN_TRAINING_ROWS - 1)
    with pytest.raises(ValueError):
        fit_project_glm(rows, target_name="test_target")


def test_fit_recovers_the_dominant_known_relationship() -> None:
    """The synthetic target is mostly -0.8 * mean_crest_factor_db -- the
    fitted model's largest-magnitude coefficient should be on that feature
    and have the correct (negative) sign."""
    rows = _synthetic_rows(200, seed=1)
    model = fit_project_glm(rows, target_name="test_target")

    top = model.coefficients()[0]
    assert top["feature"] == "mean_crest_factor_db"
    assert top["weight"] < 0


def test_model_round_trips_through_dict() -> None:
    rows = _synthetic_rows(200, seed=2)
    model = fit_project_glm(rows, target_name="test_target")
    restored = ProjectGLM.from_dict(model.to_dict())
    assert restored.feature_names == model.feature_names
    assert restored.target_name == model.target_name
    np.testing.assert_allclose(restored.weights, model.weights)
    assert restored.bias == pytest.approx(model.bias)


def test_model_round_trips_through_file(tmp_path) -> None:
    rows = _synthetic_rows(200, seed=3)
    model = fit_project_glm(rows, target_name="test_target")
    path = tmp_path / "model.json"
    model.save(path)
    restored = ProjectGLM.load(path)
    assert restored.predict(rows[0]["features"]) == pytest.approx(model.predict(rows[0]["features"]))


def test_evaluate_reports_low_error_on_held_out_synthetic_data() -> None:
    train_rows = _synthetic_rows(300, seed=4)
    held_out_rows = _synthetic_rows(60, seed=5)
    model = fit_project_glm(train_rows, target_name="test_target")

    metrics = evaluate_project_glm(model, held_out_rows)
    assert metrics["n"] == 60
    # Synthetic target has stdev on the order of a few units (mostly from
    # mean_crest_factor_db ~ N(12, 3) scaled by 0.8) -- a correctly-fitted
    # model should track it closely, noise floor aside.
    assert metrics["mae"] < 1.0
    assert metrics["corr"] > 0.9


def test_evaluate_on_empty_rows_returns_zeroed_metrics() -> None:
    rows = _synthetic_rows(50, seed=6)
    model = fit_project_glm(rows, target_name="test_target")
    metrics = evaluate_project_glm(model, [])
    assert metrics == {"n": 0, "mae": 0.0, "corr": 0.0}
