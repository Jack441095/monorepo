"""Public ML API — anomaly detection, quality prediction, feature importance.

Thin wrappers that delegate to modules in ``audio_analysis_tool/``.
Kept separate from ``mix_review.py`` to keep the public API surface clean.
"""

from __future__ import annotations

import sys
from pathlib import Path

BUSINESS_ROOT = Path(__file__).resolve().parent
if str(BUSINESS_ROOT) not in sys.path:
    sys.path.insert(0, str(BUSINESS_ROOT))

import statistics as _statistics
from audio_analysis.mix_review.review_store import connect as _connect
from audio_analysis.mix_review.review_store import load_feature_history as _load_feature_history
from audio_analysis.mix_review.review_store import load_feedback_training_data as _load_feedback_training_data


def __getattr__(name: str) -> object:
    """Lazy import of heavy modules so callers only pay for what they use."""
    import importlib

    _delegates: dict[str, tuple[str, str]] = {
        "detect_anomalies": ("anomaly_detector", "detect_anomalies"),
        "anomaly_report_for_report": ("anomaly_detector", "anomaly_report"),
        "predict_quality": ("quality_predictor", None),
        "quality_predictor_status": ("quality_predictor", None),
        "scoring_feature_importance": ("mix_review", "_scoring_feature_importance"),
        "revision_narrative_for_report": ("revision_narrative", "build_revision_narrative"),
    }

    if name not in _delegates:
        msg = f"module {__name__!r} has no attribute {name!r}"
        raise AttributeError(msg)

    mod_name, func_name = _delegates[name]
    mod = importlib.import_module(mod_name)

    if func_name is None:
        # Module-level function — re-export it
        return getattr(mod, name)

    return getattr(mod, func_name)


def detect_anomalies(
    report: dict,
    history: list[dict] | None = None,
    *,
    goal_key: str | None = None,
) -> dict:
    """Detect anomalous metrics in a review report against historical data.

    Args:
        report: A report dict from review_by_id() or analyze_wav().
        history: Optional list of feature history records. Fetches from DB if None.
        goal_key: If provided, compare only against same-goal reviews.

    Returns:
        Dict with outlier_count, outliers, global_anomaly_score, narrative.
    """
    from audio_analysis.analysis_core.anomaly_detector import detect_anomalies as _run_detect
    from audio_analysis.mix_features import extract_feature_vector

    metrics = report.get("metrics") or {}
    vector = extract_feature_vector(metrics)
    if not vector:
        return {
            "ok": False,
            "error": "Could not extract feature vector.",
            "outlier_count": 0,
            "outliers": [],
        }

    if history is None:
        from audio_analysis.mix_review.review_store import load_feature_history as _load

        history = _load(connect_func=_connect, limit=2000)
        history = history or []

    return _run_detect(vector, history, goal_key=goal_key)


def anomaly_report_for_report(
    report: dict,
    history: list[dict] | None = None,
    *,
    goal_key: str | None = None,
) -> dict:
    """Full anomaly report: all-feature percentiles + outlier summary."""
    from audio_analysis.analysis_core.anomaly_detector import anomaly_report as _run_report
    from audio_analysis.mix_features import extract_feature_vector

    metrics = report.get("metrics") or {}
    vector = extract_feature_vector(metrics)
    if not vector:
        return {"ok": False, "error": "Could not extract feature vector."}

    if history is None:
        from audio_analysis.mix_review.review_store import load_feature_history as _load

        history = _load(connect_func=_connect, limit=2000)
        history = history or []

    return _run_report(vector, history, goal_key=goal_key)


def predict_quality(
    report: dict,
    model: dict | None = None,
) -> dict:
    """Predict whether a mix review report would be accepted.

    Args:
        report: A report dict from review_by_id() or analyze_wav().
        model: Trained model dict. If None, trains from DB feedback data.

    Returns:
        Dict with accepted (bool), confidence, score, improvement_areas, narrative.
    """
    from audio_analysis.integration.quality_predictor import quality_snapshot, train_from_history, compute_training_readiness
    from audio_analysis.mix_features import extract_feature_vector

    metrics = report.get("metrics") or {}
    vector = extract_feature_vector(metrics)
    if not vector:
        return {
            "ok": False,
            "error": "Could not extract feature vector.",
            "accepted": True,
            "confidence": 0.5,
        }

    if model is None:
        labelled = _load_feedback_training_data(connect_func=_connect, limit=2000)
        if not labelled:
            return {
                "ok": True,
                "accepted": True,
                "confidence": 0.5,
                "score": 0.5,
                "note": "No labelled feedback data available. Defaulting to optimistic prediction.",
                "improvement_areas": [],
            }
        readiness = compute_training_readiness(labelled)
        if not readiness["ready"]:
            return {
                "ok": True,
                "accepted": True,
                "confidence": 0.5,
                "score": 0.5,
                "note": f"Training not ready: {readiness['recommended']}",
                "improvement_areas": [],
                "training_readiness": readiness,
            }
        model = train_from_history(labelled)

    return quality_snapshot(vector, model)


def quality_predictor_status() -> dict:
    """Return current training readiness: how much labelled data exists."""
    from audio_analysis.integration.quality_predictor import compute_training_readiness

    labelled = _load_feedback_training_data(connect_func=_connect, limit=5000) or []
    readiness = compute_training_readiness(labelled)
    return {
        "ok": True,
        "labelled_records": len(labelled),
        "ready": readiness["ready"],
        **readiness,
    }


def scoring_feature_importance() -> dict:
    """Return top features ranked by correlation with quality score.

    Uses the historical feature vectors (not just labelled feedback)
    to show which metrics most influence the technical score.

    Returns:
        Dict with features (list of {name, correlation}) and count.
    """
    from audio_analysis.analysis_core.anomaly_detector import ANOMALY_FEATURES as _features

    history = _load_feature_history(connect_func=_connect, limit=2000) or []
    # Collect values per feature + scores
    feature_values: dict[str, list[float]] = {f: [] for f in _features}
    scores: list[float] = []

    for entry in history:
        features = entry.get("features") if isinstance(entry.get("features"), dict) else {}
        score = features.get("technical_score")
        if score is None:
            continue
        scores.append(float(score))
        for f in _features:
            v = features.get(f)
            if v is not None and isinstance(v, (int, float)):
                feature_values[f].append(float(v))
            else:
                feature_values[f].append(0.0)  # Align lengths

    results: list[dict] = []
    for f in _features:
        vals = feature_values[f]
        if len(vals) < 5 or len(scores) < 5:
            continue
        # Trim to same length
        min_len = min(len(vals), len(scores))
        corr = _statistics.correlation(vals[:min_len], scores[:min_len])
        results.append({
            "feature": f,
            "correlation": round(corr, 4),
            "abs_correlation": round(abs(corr), 4),
            "sample_count": min_len,
        })

    results.sort(key=lambda r: -r["abs_correlation"])
    return {
        "ok": True,
        "feature_count": len(results),
        "historical_reviews": len(history),
        "features": results[:30],
    }
