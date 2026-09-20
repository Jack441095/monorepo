"""Anomaly detector for mix review feature vectors.

Compares any new mix's feature vector against the historical distribution
from previous reviews and flags metrics that are statistical outliers.

Uses robust z-score (median + IQR instead of mean + std) to handle
small datasets without numpy. Falls back to simple z-score for larger
datasets when numpy is available.

Usage:
    >>> from audio_analysis.analysis_core.anomaly_detector import detect_anomalies
    >>> from audio_analysis.mix_review.review_store import load_feature_history
    >>> history = load_feature_history(connect_func=connect)
    >>> report = analyze_wav(file_bytes, "mix.wav")
    >>> vector = extract_feature_vector(report["metrics"])
    >>> result = detect_anomalies(vector, history)
    >>> result["outlier_count"]
    2
    'crest_factor_db'
    >>> result["outliers"][0]["percentile"]
    3.2
"""

from __future__ import annotations

import math

try:
    import numpy as np

    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False


# Features that benefit from z-score detection (meaningful numeric range)
ANOMALY_FEATURES = [
    "peak_dbfs",
    "rms_dbfs_estimate",
    "crest_factor_db",
    "true_peak_dbfs",
    "integrated_lufs",
    "stereo_correlation",
    "stereo_width_ratio",
    "stereo_balance",
    "dynamic_range_estimate_db",
    "dc_offset",
    "clipped_frames_estimate",
    # Bands (raw)
    "bands_sub", "bands_bass", "bands_low_mids", "bands_mids",
    "bands_presence", "bands_sibilance", "bands_air",
    # Bands (perceptual)
    "perceptual_bands_sub", "perceptual_bands_bass", "perceptual_bands_low_mids",
    "perceptual_bands_mids", "perceptual_bands_presence", "perceptual_bands_sibilance",
    "perceptual_bands_air",
    # Side bands
    "side_bands_sub", "side_bands_bass", "side_bands_low_mids",
    "side_bands_mids", "side_bands_presence", "side_bands_sibilance", "side_bands_air",
    # Correlation bands
    "correlation_sub", "correlation_bass", "correlation_low_mids",
    "correlation_presence",
    # Tonal
    "tonal_low_end_share", "tonal_body_share", "tonal_clarity_share",
    "tonal_perceived_clarity_share",
    # Dynamics
    "dynamic_crest_factor_db", "dynamic_transient_margin_db",
    "dynamic_short_term_range_db", "dynamic_section_range_db",
    # Perceptual
    "perceived_presence_share", "perceived_low_end_share",
    "centroid_hz", "rolloff_85_hz", "high_frequency_share",
    # Stereo field
    "stereo_low_side_share", "stereo_low_band_correlation",
    # Section
    "section_rms_min", "section_rms_max", "section_rms_mean", "section_count",
]


def _percentile(sorted_values: list[float], q: float) -> float:
    """Linear interpolation percentile, same as numpy."""
    if not sorted_values:
        return 0.0
    n = len(sorted_values)
    if n == 1:
        return sorted_values[0]
    idx = q / 100.0 * (n - 1)
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return sorted_values[lo]
    frac = idx - lo
    return sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac


def _median(values: list[float]) -> float:
    """Median of a list of floats."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    if n % 2 == 1:
        return sorted_vals[n // 2]
    return (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2.0


def _iqr(values: list[float]) -> float:
    """Interquartile range."""
    if len(values) < 4:
        return max(values) - min(values) if values else 0.0
    sorted_vals = sorted(values)
    return _percentile(sorted_vals, 75) - _percentile(sorted_vals, 25)


def _robust_z_score(value: float, median: float, iqr_value: float) -> float:
    """Modified z-score using median and IQR instead of mean/std.

    A robust z-score > 3.0 is a potential outlier.
    """
    if iqr_value == 0:
        return 0.0
    return (value - median) / (1.4826 * iqr_value)


def _classic_z_score(value: float, mean: float, std: float) -> float:
    """Standard z-score. |z| > 2.0 is unusual, > 3.0 is outlier."""
    if std == 0:
        return 0.0
    return (value - mean) / std


def _compute_stats_numpy(values: list[float]) -> dict:
    """Compute mean, std, median, q25, q75 using numpy."""
    arr = np.array(values, dtype=np.float64)
    return {
        "count": len(values),
        "mean": float(np.mean(arr)),
        "std": float(np.std(arr, ddof=1)) if len(values) > 1 else 0.0,
        "median": float(np.median(arr)),
        "q25": float(np.percentile(arr, 25)),
        "q75": float(np.percentile(arr, 75)),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
    }


def _compute_stats_pure(values: list[float]) -> dict:
    """Compute stats without numpy."""
    n = len(values)
    if n == 0:
        return {"count": 0, "mean": 0.0, "std": 0.0, "median": 0.0, "q25": 0.0, "q75": 0.0, "min": 0.0, "max": 0.0}
    s = sorted(values)
    mean_val = sum(values) / n
    variance = sum((v - mean_val) ** 2 for v in values) / (n - 1) if n > 1 else 0.0
    return {
        "count": n,
        "mean": mean_val,
        "std": math.sqrt(variance) if variance > 0 else 0.0,
        "median": _median(values),
        "q25": _percentile(s, 25),
        "q75": _percentile(s, 75),
        "min": s[0],
        "max": s[-1],
    }


def _compute_stats(values: list[float]) -> dict:
    if NUMPY_AVAILABLE:
        return _compute_stats_numpy(values)
    return _compute_stats_pure(values)


def _feature_statistics(
    history: list[dict],
    *,
    goal_key: str | None = None,
) -> dict[str, dict]:
    """Compute per-feature statistics from historical vectors.

    Args:
        history: List of dicts from load_feature_history().
        goal_key: If provided, only consider vectors with matching mix_goal_key.

    Returns:
        Dict mapping feature name -> {count, mean, std, median, q25, q75, min, max}.
    """
    # Collect values per feature
    feature_values: dict[str, list[float]] = {f: [] for f in ANOMALY_FEATURES}

    for entry in history:
        features = entry.get("features") if isinstance(entry.get("features"), dict) else {}
        entry_goal = str(entry.get("mix_goal_key", "")).strip()
        if goal_key and entry_goal and entry_goal != goal_key:
            continue
        for feature in ANOMALY_FEATURES:
            value = features.get(feature)
            if value is not None and isinstance(value, (int, float)) and not math.isnan(float(value)):
                feature_values[feature].append(float(value))

    stats: dict[str, dict] = {}
    for feature in ANOMALY_FEATURES:
        vals = feature_values[feature]
        if len(vals) < 3:  # Need at least 3 data points for meaningful stats
            stats[feature] = {"count": len(vals), "mean": 0.0, "std": 0.0, "median": 0.0, "q25": 0.0, "q75": 0.0, "min": 0.0, "max": 0.0}
        else:
            stats[feature] = _compute_stats(vals)
    return stats


def _z_score_outlier_flag(
    value: float | None,
    stats: dict,
    feature_name: str,
) -> dict | None:
    """Check if a single value is an outlier.

    Uses robust z-score when count < 10, classic z-score otherwise.
    """
    if value is None or stats.get("count", 0) < 3:
        return None

    count = stats["count"]
    median_val = stats["median"]
    iqr_val = stats["q75"] - stats["q25"]
    mean_val = stats["mean"]
    std_val = stats["std"]

    if count < 10:
        z = _robust_z_score(value, median_val, iqr_val)
        threshold = 3.0  # Robust: |z| > 3 = outlier
    else:
        z = _classic_z_score(value, mean_val, std_val)
        threshold = 2.5  # Classic: |z| > 2.5 = outlier (slightly relaxed for audio)

    abs_z = abs(z)
    if abs_z < threshold:
        return None

    # Determine severity
    if abs_z > 4.0:
        severity = "high"
    elif abs_z > 3.0:
        severity = "medium"
    else:
        severity = "low"

    # Estimate percentile
    direction = "high" if z > 0 else "low"
    # Simple percentile from normal approximation
    pct = min(50.0, max(0.0, 50.0 - abs_z * 10.0)) if direction == "high" else min(50.0, max(0.0, 50.0 - abs_z * 10.0))
    if direction == "high":
        percentile = 50.0 + pct
    else:
        percentile = 50.0 - pct

    return {
        "metric": feature_name,
        "value": value,
        "z_score": round(abs_z, 2),
        "direction": direction,
        "severity": severity,
        "percentile": round(min(100.0, max(0.0, percentile)), 1),
        "mean": round(mean_val, 4),
        "median": round(median_val, 4),
        "std": round(std_val, 4),
        "population": count,
    }


def detect_anomalies(
    feature_vector: dict[str, float | None],
    history: list[dict],
    *,
    goal_key: str | None = None,
    min_features: int = 3,
    max_outliers: int = 10,
) -> dict:
    """Detect anomalous metrics in a feature vector against historical data.

    Args:
        feature_vector: Dict from extract_feature_vector().
        history: List of dicts from load_feature_history() or load_feedback_training_data().
        goal_key: If provided, only compare against same-goal history.
        min_features: Minimum number of features to analyse.
        max_outliers: Maximum outliers to return.

    Returns:
        Dict with:
            ok: True if analysis succeeded.
            outlier_count: Number of anomalous metrics found.
            outliers: List of outlier dicts sorted by severity.
            global_anomaly_score: 0-100 summary score.
            stats_used: Number of features with enough data for comparison.
            stats_skipped: Number of features with insufficient data.
    """
    if not feature_vector:
        return {"ok": False, "error": "Empty feature vector.", "outlier_count": 0, "outliers": [], "global_anomaly_score": 0}

    stats = _feature_statistics(history, goal_key=goal_key)

    outliers: list[dict] = []
    stats_used = 0
    stats_skipped = 0

    for feature in ANOMALY_FEATURES:
        feature_stats = stats.get(feature, {})
        if feature_stats.get("count", 0) < min_features:
            stats_skipped += 1
            continue
        value = feature_vector.get(feature)
        flag = _z_score_outlier_flag(value, feature_stats, feature)
        if flag:
            outliers.append(flag)
            stats_used += 1
        else:
            stats_used += 1

    # Sort by severity then z-score
    severity_order = {"high": 0, "medium": 1, "low": 2}
    outliers.sort(key=lambda o: (severity_order.get(o.get("severity", "low"), 3), -abs(o.get("z_score", 0))))
    outliers = outliers[:max_outliers]

    # Global anomaly score: weighted by number and severity of outliers
    if not outliers:
        global_score = 0
    else:
        severity_weights = {"high": 15, "medium": 8, "low": 3}
        raw_score = sum(severity_weights.get(o.get("severity", "low"), 3) for o in outliers)
        # Scale: 0-100 where 1 high-severity outlier = ~15, 4+ medium = ~50
        global_score = min(100, int(raw_score * 2.5))

    return {
        "ok": True,
        "outlier_count": len(outliers),
        "outliers": outliers,
        "global_anomaly_score": global_score,
        "stats_used": stats_used,
        "stats_skipped": stats_skipped,
        "goal_key": goal_key or "all",
        "narrative": _anomaly_narrative(outliers, global_score),
        "results_by_feature": {
            o["metric"]: {
                "z_score": o["z_score"],
                "direction": o["direction"],
                "severity": o["severity"],
                "percentile": o["percentile"],
                "value": o["value"],
                "population_median": o["median"],
            }
            for o in outliers
        },
    }


def _anomaly_narrative(outliers: list[dict], global_score: int) -> str:
    """Build a human-readable summary of anomalies."""
    if not outliers:
        return "No unusual metrics detected. This mix is consistent with the historical profile."
    parts: list[str] = []
    high = [o for o in outliers if o.get("severity") == "high"]
    medium = [o for o in outliers if o.get("severity") == "medium"]
    low = [o for o in outliers if o.get("severity") == "low"]
    if high:
        label = "unusual" if len(high) == 1 else "unusual areas"
        parts.append(f"{len(high)} {label}: " + ", ".join(o.get("metric", "") for o in high))
    if medium:

        parts.append("Notable: " + ", ".join(o.get("metric", "") for o in medium))
    if low:
        parts.append("Slight: " + ", ".join(o.get("metric", "") for o in low))
    parts.append(f"Overall anomaly score: {global_score}/100.")
    return ". ".join(parts)


def anomaly_report(
    feature_vector: dict[str, float | None],
    history: list[dict],
    *,
    goal_key: str | None = None,
) -> dict:
    """Full anomaly report: outliers plus all-feature percentiles.

    Returns every feature's percentile rank against the history,
    not just the outliers. Useful for dashboards and LLM context.
    """
    stats = _feature_statistics(history, goal_key=goal_key)
    if not feature_vector:
        return {"ok": False, "error": "Empty feature vector."}

    all_percentiles: dict[str, dict] = {}
    for feature in ANOMALY_FEATURES:
        feature_stats = stats.get(feature, {})
        count = feature_stats.get("count", 0)
        value = feature_vector.get(feature)
        if value is None or count < 3:
            all_percentiles[feature] = {"status": "insufficient_data", "count": count, "value": value}
            continue
        median_val = feature_stats["median"]
        iqr_val = feature_stats["q75"] - feature_stats["q25"]
        z = _robust_z_score(value, median_val, iqr_val) if count < 10 else _classic_z_score(value, feature_stats["mean"], feature_stats["std"])
        # Approximate percentile from z-score
        approx_pct = min(99.9, max(0.1, 50.0 + z * 34.1)) if z >= 0 else min(99.9, max(0.1, 50.0 - abs(z) * 34.1))
        abs_z = abs(z)
        if abs_z > 3.0:
            status = "outlier"
        elif abs_z > 2.0:
            status = "unusual"
        else:
            status = "normal"
        all_percentiles[feature] = {
            "status": status,
            "z_score": round(z, 2),
            "percentile": round(approx_pct, 1),
            "value": value,
            "median": round(median_val, 4),
            "count": count,
        }

    anomalies = detect_anomalies(feature_vector, history, goal_key=goal_key)
    return {
        "ok": True,
        "outlier_count": anomalies["outlier_count"],
        "global_anomaly_score": anomalies["global_anomaly_score"],
        "narrative": anomalies["narrative"],
        "outliers": anomalies["outliers"],
        "feature_percentiles": all_percentiles,
        "stats_summary": {
            "features_with_data": sum(1 for s in stats.values() if s.get("count", 0) >= 3),
            "features_insufficient": sum(1 for s in stats.values() if 0 < s.get("count", 0) < 3),
            "features_empty": sum(1 for s in stats.values() if s.get("count", 0) == 0),
            "historical_reviews_used": len(history),
        },
    }
