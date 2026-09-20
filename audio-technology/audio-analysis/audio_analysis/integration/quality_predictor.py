"""Quality predictor for mix reviews using feedback-labelled feature vectors.

Learns which features correlate with "accepted" vs "rejected" feedback
decisions, then predicts whether a new mix will be accepted and which
metrics need the most improvement.

Works from pure Python stats (no sklearn required). Gets more accurate
as more labelled data accumulates in the mix_feedback_features table.

Usage:
    >>> from audio_analysis.integration.quality_predictor import predict_quality, train_from_history
    >>> from audio_analysis.mix_review.review_store import load_feedback_training_data
    >>> labelled = load_feedback_training_data(connect_func=connect)
    >>> model = train_from_history(labelled)
    >>> report = analyze_wav(file_bytes, "mix.wav")
    >>> from mix_features import extract_feature_vector
    >>> vector = extract_feature_vector(report["metrics"])
    >>> prediction = predict_quality(model, vector)
    >>> prediction["accepted"]
    True
    >>> prediction["confidence"]
    0.87
    >>> prediction["improvement_areas"][0]["metric"]
    'crest_factor_db'
"""

from __future__ import annotations

import math


try:
    import numpy as np  # noqa: F401

    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False


# Features known to correlate with mix quality decisions
QUALITY_FEATURES = [
    "peak_dbfs",
    "rms_dbfs_estimate",
    "crest_factor_db",
    "true_peak_dbfs",
    "integrated_lufs",
    "momentary_max_lufs",
    "short_term_max_lufs",
    "loudness_range_lu",
    "stereo_correlation",
    "stereo_width_ratio",
    "stereo_balance",
    "dynamic_range_estimate_db",
    "dc_offset",
    "clipped_frames_estimate",
    "clipping_risk",
    "bands_sub", "bands_bass", "bands_low_mids", "bands_mids",
    "bands_presence", "bands_sibilance", "bands_air",
    "perceptual_bands_sub", "perceptual_bands_bass", "perceptual_bands_low_mids",
    "perceptual_bands_mids", "perceptual_bands_presence",
    "perceptual_bands_sibilance", "perceptual_bands_air",
    "perceived_presence_share", "perceived_low_end_share",
    "centroid_hz", "rolloff_85_hz", "high_frequency_share",
    "tonal_low_end_share", "tonal_body_share", "tonal_clarity_share",
    "tonal_perceived_clarity_share",
    "dynamic_crest_factor_db", "dynamic_transient_margin_db",
    "dynamic_short_term_range_db", "dynamic_section_range_db",
    "stereo_low_side_share", "stereo_low_band_correlation",
    "section_rms_mean", "section_count",
    "correlation_sub", "correlation_bass", "correlation_low_mids",
    "correlation_mids", "correlation_presence",
    "correlation_sibilance", "correlation_air",
]


def _label_score(decision: str) -> float:
    """Convert a feedback decision to a numeric quality score."""
    d = str(decision).strip().lower()
    # Accepted / positive decisions
    if d in {"yes", "good", "approved", "helpful", "correct", "use", "accepted"}:
        return 1.0
    if d in {"revise", "needs_work", "almost", "partial"}:
        return 0.5
    # Non-actionable / neutral
    if d in {"skip", "note", "unrelated"}:
        return None
    # Rejected / negative decisions
    return 0.0


def _feature_mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _feature_std(values: list[float], mean: float) -> float:
    if len(values) < 2:
        return 0.0
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(variance) if variance > 0 else 0.0


def _pearson_correlation(x: list[float], y: list[float]) -> float:
    """Pearson correlation coefficient between two lists."""
    n = len(x)
    if n < 3:
        return 0.0
    mean_x = _feature_mean(x)
    mean_y = _feature_mean(y)
    std_x = _feature_std(x, mean_x)
    std_y = _feature_std(y, mean_y)
    if std_x == 0 or std_y == 0:
        return 0.0
    cov = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n)) / (n - 1)
    return max(-1.0, min(1.0, cov / (std_x * std_y)))


def _effect_size(accepted_values: list[float], rejected_values: list[float]) -> float:
    """Cohen's d effect size between two groups.

    Positive means accepted > rejected. > 0.5 is a useful predictor.
    """
    if len(accepted_values) < 2 or len(rejected_values) < 2:
        return 0.0
    mean_a = _feature_mean(accepted_values)
    mean_r = _feature_mean(rejected_values)
    std_a = _feature_std(accepted_values, mean_a)
    std_r = _feature_std(rejected_values, mean_r)
    pooled = math.sqrt((std_a ** 2 + std_r ** 2) / 2)
    if pooled == 0:
        return 0.0
    return (mean_a - mean_r) / pooled


def _nan_safe(value: object) -> float | None:
    if value is None:
        return None
    try:
        v = float(value)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except (TypeError, ValueError, OverflowError):
        return None


def train_from_history(labelled_records: list[dict]) -> dict:
    """Train a simple quality predictor from feedback-labelled feature vectors.

    Args:
        labelled_records: List of dicts from load_feedback_training_data().
            Each must have 'decision' (str) and 'features' (dict).

    Returns:
        Model dict with keys:
            feature_weights: dict mapping feature name -> effect size (positive = higher value = better)
            decision_threshold: the score at which we predict "accepted"
            accepted_mean: per-feature mean for accepted decisions
            rejected_mean: per-feature mean for rejected decisions
            feature_importance: features sorted by absolute effect size
            training_count: number of labelled records used
            accepted_count: number of accepted records
            rejected_count: number of rejected records
    """
    # Separate accepted vs rejected
    accepted_features: dict[str, list[float]] = {}
    rejected_features: dict[str, list[float]] = {}
    scores: list[float] = []

    for record in labelled_records:
        decision = str(record.get("decision", ""))
        features = record.get("features")
        if not isinstance(features, dict):
            continue
        label = _label_score(decision)
        if label is None:
            continue
        scores.append(label)

        # Strictly greater than 0.5, not >=: "needs_work"/"revise"/"almost"/
        # "partial" score exactly 0.5 (see _label_score) and mean "this isn't
        # acceptable as-is" -- counting them as accepted would silently teach
        # the model that whatever features a needs-work mix had were a
        # success. Found 2026-07-12: this bucketed every needs_work record
        # into "accepted" in both this function and
        # compute_training_readiness() below.
        target_dict = accepted_features if label > 0.5 else rejected_features
        for feature in QUALITY_FEATURES:
            value = _nan_safe(features.get(feature))
            if value is None:
                continue
            if feature not in target_dict:
                target_dict[feature] = []
            target_dict[feature].append(value)

    ac_count = len([s for s in scores if s > 0.5])
    rej_count = len([s for s in scores if s <= 0.5])

    # Compute effect sizes per feature
    feature_weights: dict[str, float] = {}
    feature_means_accepted: dict[str, float] = {}
    feature_means_rejected: dict[str, float] = {}

    for feature in QUALITY_FEATURES:
        acc_vals = accepted_features.get(feature, [])
        rej_vals = rejected_features.get(feature, [])
        if len(acc_vals) < 2 or len(rej_vals) < 2:
            continue
        d = _effect_size(acc_vals, rej_vals)
        feature_weights[feature] = round(d, 4)
        feature_means_accepted[feature] = round(_feature_mean(acc_vals), 4)
        feature_means_rejected[feature] = round(_feature_mean(rej_vals), 4)

    # Sort by absolute effect size
    feature_importance = sorted(
        feature_weights.items(),
        key=lambda item: abs(item[1]),
        reverse=True,
    )

    # Decision threshold: mean of all training scores
    decision_threshold = _feature_mean(scores) if scores else 0.5

    return {
        "feature_weights": feature_weights,
        "feature_importance": feature_importance[:20],  # Top 20
        "decision_threshold": round(decision_threshold, 3),
        "accepted_mean": feature_means_accepted,
        "rejected_mean": feature_means_rejected,
        "training_count": len(scores),
        "accepted_count": ac_count,
        "rejected_count": rej_count,
    }


def predict_quality(model: dict, feature_vector: dict[str, float | None]) -> dict:
    """Predict whether a mix will be accepted based on trained model.

    Args:
        model: Dict from train_from_history().
        feature_vector: Dict from extract_feature_vector().

    Returns:
        Dict with:
            accepted: True if predicted accepted (score > threshold).
            confidence: 0-1 confidence in the prediction.
            score: Numeric quality score (0-1).
            improvement_areas: List of features that need the most change,
                sorted by negative impact (metric below rejected mean).
            metric_detail: Per-metric comparison against accepted/rejected means.
    """
    if not model.get("feature_weights"):
        return {
            "accepted": True,
            "confidence": 0.5,
            "score": 0.5,
            "improvement_areas": [],
            "metric_detail": {},
            "note": "Insufficient training data. Defaulting to optimistic prediction.",
        }

    weights = model.get("feature_weights", {})
    accepted_mean = model.get("accepted_mean", {})
    rejected_mean = model.get("rejected_mean", {})
    threshold = model.get("decision_threshold", 0.5)

    total_weight = 0.0
    weighted_score = 0.0
    improvement_areas: list[dict] = []
    metric_detail: dict[str, dict] = {}

    for feature, weight in weights.items():
        value = _nan_safe(feature_vector.get(feature))
        if value is None:
            continue

        abs_w = abs(weight)
        total_weight += abs_w

        # The "ideal" is direction of accepted mean
        acc_mean = accepted_mean.get(feature, value)
        rej_mean = rejected_mean.get(feature, value)
        direction = "higher" if weight > 0 else "lower"

        # How far is this value from the accepted mean, in std-like units
        spread = abs(rej_mean - acc_mean) if abs(rej_mean - acc_mean) > 0.001 else 0.001
        # Normalised: closer to accepted mean = higher score
        dist_from_accepted = abs(value - acc_mean)
        dist_from_rejected = abs(value - rej_mean)
        feature_score = dist_from_rejected / (dist_from_accepted + dist_from_rejected + 0.001)
        feature_score = max(0.0, min(1.0, feature_score))

        weighted_score += feature_score * abs_w

        # If the value is closer to the rejected mean, flag for improvement
        if dist_from_rejected < dist_from_accepted:
            improvement_needed = dist_from_accepted / (spread + 0.001)
            improvement_areas.append({
                "metric": feature,
                "current_value": round(value, 4),
                "accepted_mean": round(acc_mean, 4) if acc_mean != value else None,
                "rejected_mean": round(rej_mean, 4) if rej_mean != value else None,
                "direction": direction,
                "improvement_needed": round(min(5.0, improvement_needed), 2),
                "impact_weight": round(abs_w, 3),
            })

        metric_detail[feature] = {
            "value": round(value, 4),
            "accepted_mean": round(acc_mean, 4) if acc_mean != value else None,
            "rejected_mean": round(rej_mean, 4) if rej_mean != value else None,
            "direction": direction,
            "score": round(feature_score, 3),
        }

    if total_weight == 0:
        score = 0.5
    else:
        score = weighted_score / total_weight

    # Sort improvement areas by impact
    improvement_areas.sort(key=lambda a: (-abs(a.get("impact_weight", 0)), -abs(a.get("improvement_needed", 0))))
    improvement_areas = improvement_areas[:6]

    accepted = score >= threshold
    # Confidence: distance from threshold, scaled 0-1
    confidence = min(1.0, max(0.0, 0.5 + abs(score - threshold) * 3.0))

    return {
        "accepted": accepted,
        "confidence": round(confidence, 3),
        "score": round(score, 3),
        "threshold": threshold,
        "improvement_areas": improvement_areas,
        "metric_detail": metric_detail,
        "features_analysed": len(metric_detail),
        "training_count": model.get("training_count", 0),
    }


def quality_snapshot(
    feature_vector: dict[str, float | None],
    model: dict,
) -> dict:
    """One-call quality snapshot: prediction + improvement actions.

    Returns a dict pre-formatted for agent/LLM context handoff.
    """
    prediction = predict_quality(model, feature_vector)
    if not prediction.get("improvement_areas"):
        return {
            "ok": True,
            "accepted": prediction["accepted"],
            "confidence": prediction["confidence"],
            "score": prediction["score"],
            "narrative": "No specific improvement areas identified.",
            "improvement_areas": [],
            "metric_detail": prediction.get("metric_detail", {}),
        }

    # Build a narrative
    parts: list[str] = []
    if prediction["accepted"]:
        parts.append(f"Likely accepted (confidence {prediction['confidence']:.0%}).")
    else:
        parts.append(f"May need revision (confidence {prediction['confidence']:.0%}).")

    top = prediction["improvement_areas"][:3]
    for area in top:
        metric = area["metric"]
        current = area["current_value"]
        accepted_mean = area.get("accepted_mean", "?")
        parts.append(f"  - {metric}: {current} vs accepted {accepted_mean}")

    return {
        "ok": True,
        "accepted": prediction["accepted"],
        "confidence": prediction["confidence"],
        "score": prediction["score"],
        "narrative": "\n".join(parts),
        "improvement_areas": prediction["improvement_areas"],
        "metric_detail": prediction.get("metric_detail", {}),
    }


def compute_training_readiness(labelled_records: list[dict]) -> dict:
    """Assess whether enough labelled data exists for a useful training run.

    Returns:
        Dict with:
            ready: True if enough data exists.
            accepted_count: Number of accepted-labelled records.
            rejected_count: Number of rejected-labelled records.
            total: Total labelled records.
            features_with_data: Number of features with both accepted/rejected values.
            recommended: Suggested next action.
    """
    accepted_features: dict[str, list[float]] = {}
    rejected_features: dict[str, list[float]] = {}
    accepted_count = 0
    rejected_count = 0

    for record in labelled_records:
        decision = str(record.get("decision", ""))
        features = record.get("features")
        if not isinstance(features, dict):
            continue
        label = _label_score(decision)
        if label is None:
            continue
        # See the matching note in train_from_history(): > 0.5, not >=, so
        # needs_work/revise/almost/partial (label == 0.5) count as rejected
        # for readiness purposes, not accepted.
        if label > 0.5:
            accepted_count += 1
            target = accepted_features
        else:
            rejected_count += 1
            target = rejected_features
        for feature in QUALITY_FEATURES:
            value = _nan_safe(features.get(feature))
            if value is not None:
                if feature not in target:
                    target[feature] = []
                target[feature].append(value)

    features_with_both = sum(
        1
        for f in QUALITY_FEATURES
        if len(accepted_features.get(f, [])) >= 2 and len(rejected_features.get(f, [])) >= 2
    )

    ready = accepted_count >= 3 and rejected_count >= 3 and features_with_both >= 5

    if ready:
        recommended = "Training ready. Run train_from_history() to build a predictor."
    elif accepted_count < 3:
        recommended = f"Need at least 3 accepted-labelled reviews (have {accepted_count})."
    elif rejected_count < 3:
        recommended = f"Need at least 3 rejected-labelled reviews (have {rejected_count})."
    else:
        recommended = f"Need more feature coverage across both groups (have {features_with_both}/5 with both labels)."

    return {
        "ready": ready,
        "total": accepted_count + rejected_count,
        "accepted_count": accepted_count,
        "rejected_count": rejected_count,
        "features_with_both": features_with_both,
        "recommended": recommended,
    }


def load_mix_modifiers(genre: str, *, connect_func, limit: int = 200) -> dict:
    """Return small data-driven corrections for the mix decision engine.

    M8.3 — Feedback Learning → Mix Rule Updates.

    Loads recent feedback-labelled mixes for the requested genre (or all genres
    if fewer than 10 genre-specific records exist), trains a quality predictor,
    and returns a ``corrections`` dict mapping DSP feature keys to small ±dB
    adjustments (capped at ±2 dB) that nudge future mixes toward accepted outcomes.

    Returns {} when insufficient data is available.
    """
    try:
        from audio_analysis.mix_review.review_store import load_feedback_training_data
    except ImportError:
        return {}

    try:
        records = load_feedback_training_data(connect_func=connect_func, limit=limit)
        # Prefer genre-specific records; fall back to all if fewer than 10
        genre_records = [r for r in records if str(r.get("mix_goal_key", "")) == genre]
        training = genre_records if len(genre_records) >= 10 else records
        if len(training) < 6:
            return {}

        model = train_from_history(training)
        weights = model.get("feature_weights", {})
        if not weights:
            return {}

        # Map feature effect sizes to DSP corrections (scale and cap)
        corrections: dict[str, float] = {}
        # Positive weight = higher value → accepted; nudge accepted direction by +0.5 dB
        for feature, effect in weights.items():
            if abs(effect) < 0.1:
                continue  # negligible effect; skip
            raw_correction = effect * 2.0  # scale: effect of 1.0 → 2 dB shift
            corrections[feature] = max(-2.0, min(2.0, round(raw_correction, 2)))

        return corrections
    except Exception:
        return {}
