"""Standardised numeric feature vector for mix review reports.

This module extracts a flat, numeric-only feature vector from any
mix review report's metrics dict. The vector is the canonical input
for ML components (anomaly detection, quality prediction, etc.).

Usage:
    >>> from mix_features import extract_feature_vector
    >>> report = analyze_wav(file_bytes, "mix.wav")
    >>> vector = extract_feature_vector(report["metrics"])
    >>> vector["peak_dbfs"]
    -3.21

All values are floats or None. No strings, booleans, or nested dicts.
"""

from __future__ import annotations



def metric_float(value: object, fallback: float | None = None) -> float | None:
    """Safely coerce a value to float, returning fallback on failure."""
    if value is None:
        return fallback
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        if value in {"n/a", "N/A", ""}:
            return fallback
        try:
            return float(value)
        except (ValueError, TypeError):
            return fallback
    return fallback


def _band_shares(metrics: dict, prefix: str) -> dict[str, float]:
    """Extract per-band shares from a nested bands dict."""
    bands = metrics.get(prefix) or {}
    if not isinstance(bands, dict):
        return {}
    return {
        f"{prefix}_{name}": metric_float(bands.get(name), 0.0)
        for name in ("sub", "bass", "low_mids", "mids", "presence", "sibilance", "air")
    }


def _tonal_profile_int(metrics: dict) -> int:
    """Map tonal profile string to integer."""
    profile = str((metrics.get("tonal_balance") or {}).get("profile", "")).lower()
    mapping = {
        "low-weighted": 0,
        "balanced": 1,
        "mid-focused": 2,
        "bright": 3,
    }
    return mapping.get(profile, -1)


def _dynamics_profile_int(metrics: dict) -> int:
    """Map dynamic profile string to integer."""
    profile = str((metrics.get("dynamic_profile") or {}).get("profile", "")).lower()
    mapping = {
        "compressed": 0,
        "controlled": 1,
        "uneven": 2,
        "spiky": 3,
    }
    return mapping.get(profile, -1)


def _stereo_image_int(metrics: dict) -> int:
    """Map stereo image string to integer."""
    image = str((metrics.get("stereo_field") or {}).get("image", "")).lower()
    mapping = {
        "narrow": 0,
        "stable": 1,
        "very wide": 2,
        "phase risk": 3,
    }
    return mapping.get(image, -1)


def _band_correlations(metrics: dict) -> dict[str, float]:
    """Extract per-band correlation values."""
    corr = metrics.get("correlation_bands") or {}
    if not isinstance(corr, dict):
        return {}
    return {
        f"correlation_{name}": metric_float(corr.get(name), 1.0)
        for name in ("sub", "bass", "low_mids", "mids", "presence", "sibilance", "air")
    }


def _spectral_centroid_hz(metrics: dict) -> float | None:
    return metric_float((metrics.get("spectral_features") or {}).get("centroid_hz"))


def _spectral_rolloff_hz(metrics: dict) -> float | None:
    return metric_float((metrics.get("spectral_features") or {}).get("rolloff_85_hz"))


def _high_frequency_share(metrics: dict) -> float | None:
    return metric_float((metrics.get("spectral_features") or {}).get("high_frequency_share"))


def _goal_key_int(metrics: dict) -> int:
    """Map mix goal key to integer for categorical encoding."""
    goal = metrics.get("mix_goal")
    if not isinstance(goal, dict):
        return -1
    key = str(goal.get("key", "")).strip()
    known = {
        "premaster": 0,
        "club": 1,
        "pop_vocal": 2,
        "rap_vocal": 3,
        "podcast": 4,
        "game_audio": 5,
        "master": 6,
        "edm": 7,
        "acoustic": 8,
        "rock": 9,
        "cinematic": 10,
        "lo_fi": 11,
        "jazz": 12,
        "hip_hop": 13,
    }
    return known.get(key, -1)


def extract_feature_vector(metrics: dict) -> dict[str, float | None]:
    """Extract a flat, numeric-only feature vector from a mix review metrics dict.

    Returns a dict with ~55 numeric keys suitable for ML model input.
    All values are floats or None. No strings, booleans, or nested structures.

    Keys follow a consistent naming pattern:
    - Top-level metrics use their exact metric key (e.g. peak_dbfs)
    - Nested values use underscore notation (e.g. bands_sub, tonal_profile)
    """
    if not metrics:
        return {}

    vector: dict[str, float | None] = {}

    # --- Core level/loudness metrics ---
    for key in (
        "duration_seconds",
        "sample_rate",
        "peak_dbfs",
        "left_peak_dbfs",
        "right_peak_dbfs",
        "rms_dbfs_estimate",
        "loudest_section_rms_dbfs",
        "dynamic_range_estimate_db",
        "crest_factor_db",
        "true_peak_dbfs",
        "leading_silence_seconds",
        "trailing_silence_seconds",
        "stereo_balance",
        "stereo_correlation",
        "stereo_width_ratio",
    ):
        vector[key] = metric_float(metrics.get(key))

    # --- LUFS (can be "n/a") ---
    vector["integrated_lufs"] = metric_float(metrics.get("integrated_lufs"))
    vector["momentary_max_lufs"] = metric_float(metrics.get("momentary_max_lufs"))
    vector["short_term_max_lufs"] = metric_float(metrics.get("short_term_max_lufs"))
    vector["loudness_range_lu"] = metric_float(metrics.get("loudness_range_lu"))

    # --- DC offset ---
    vector["dc_offset"] = metric_float(metrics.get("dc_offset"))

    # --- Clipping (boolean to float) ---
    vector["clipping_risk"] = 1.0 if metrics.get("clipping_risk") else 0.0
    vector["clipped_frames_estimate"] = metric_float(metrics.get("clipped_frames_estimate"), 0.0)

    # --- Spectral bands (raw, perceptual, mid, side) ---
    vector.update(_band_shares(metrics, "bands"))
    vector.update(_band_shares(metrics, "perceptual_bands"))
    vector.update(_band_shares(metrics, "mid_bands"))
    vector.update(_band_shares(metrics, "side_bands"))
    vector.update(_band_correlations(metrics))

    # --- Perceptual summary ---
    ps = metrics.get("perceptual_summary") or {}
    if isinstance(ps, dict):
        vector["perceived_presence_share"] = metric_float(ps.get("presence_share"))
        vector["perceived_low_end_share"] = metric_float(ps.get("low_end_share"))

    # --- Spectral features ---
    vector["centroid_hz"] = _spectral_centroid_hz(metrics)
    vector["rolloff_85_hz"] = _spectral_rolloff_hz(metrics)
    vector["high_frequency_share"] = _high_frequency_share(metrics)

    # --- Tonal balance ---
    tb = metrics.get("tonal_balance") or {}
    if isinstance(tb, dict):
        vector["tonal_low_end_share"] = metric_float(tb.get("low_end_share"))
        vector["tonal_body_share"] = metric_float(tb.get("body_share"))
        vector["tonal_clarity_share"] = metric_float(tb.get("clarity_share"))
        vector["tonal_perceived_clarity_share"] = metric_float(tb.get("perceived_clarity_share"))
    vector["tonal_profile"] = float(_tonal_profile_int(metrics))

    # --- Dynamic profile ---
    dp = metrics.get("dynamic_profile") or {}
    if isinstance(dp, dict):
        vector["dynamic_crest_factor_db"] = metric_float(dp.get("crest_factor_db"))
        vector["dynamic_transient_margin_db"] = metric_float(dp.get("transient_margin_db"))
        vector["dynamic_short_term_range_db"] = metric_float(dp.get("short_term_range_db"))
        vector["dynamic_section_range_db"] = metric_float(dp.get("section_range_db"))
    vector["dynamics_profile"] = float(_dynamics_profile_int(metrics))

    # --- Stereo field ---
    sf = metrics.get("stereo_field") or {}
    if isinstance(sf, dict):
        vector["stereo_low_side_share"] = metric_float(sf.get("low_side_share"))
        vector["stereo_low_band_correlation"] = metric_float(sf.get("low_band_correlation"))
    vector["stereo_image"] = float(_stereo_image_int(metrics))

    # --- Section analysis aggregates ---
    sections = metrics.get("section_analysis") or {}
    if isinstance(sections, dict):
        section_list = sections.get("sections")
        if isinstance(section_list, list) and section_list:
            rms_values = [
                metric_float(s.get("rms_dbfs"), -99.0)
                for s in section_list
            ]
            real_values = [v for v in rms_values if v is not None and v > -99.0]
            if real_values:
                vector["section_rms_min"] = min(real_values)
                vector["section_rms_max"] = max(real_values)
                vector["section_rms_mean"] = sum(real_values) / len(real_values)
            else:
                vector["section_rms_min"] = None
                vector["section_rms_max"] = None
                vector["section_rms_mean"] = None
        else:
            vector["section_rms_min"] = None
            vector["section_rms_max"] = None
            vector["section_rms_mean"] = None
        vector["section_count"] = float(len(section_list)) if isinstance(section_list, list) else 0.0

    # --- Chord/key confidence ---
    chords = metrics.get("chords") or {}
    if isinstance(chords, dict):
        vector["key_confidence_score"] = metric_float(chords.get("key_confidence_score"), 0.0)
        sanity = chords.get("sanity") or {}
        if isinstance(sanity, dict):
            vector["chord_changes_per_minute"] = metric_float(sanity.get("changes_per_minute"), 0.0)
            vector["chord_complex_ratio"] = metric_float(sanity.get("complex_chord_ratio"), 0.0)
            vector["chord_named_sections"] = metric_float(sanity.get("named_sections"), 0.0)

    # --- Goal context (categorical as int) ---
    vector["mix_goal_key"] = float(_goal_key_int(metrics))

    # --- Technical score (label to be predicted) ---
    vector["technical_score"] = metric_float(metrics.get("technical_score"))

    return vector


FEATURE_VECTOR_KEYS = [
    # Core level
    "duration_seconds", "sample_rate",
    "peak_dbfs", "left_peak_dbfs", "right_peak_dbfs",
    "rms_dbfs_estimate", "loudest_section_rms_dbfs",
    "dynamic_range_estimate_db", "crest_factor_db",
    "true_peak_dbfs", "integrated_lufs",
    "momentary_max_lufs", "short_term_max_lufs", "loudness_range_lu",
    "leading_silence_seconds", "trailing_silence_seconds",
    # Clipping / DC
    "dc_offset", "clipping_risk", "clipped_frames_estimate",
    # Stereo
    "stereo_balance", "stereo_correlation", "stereo_width_ratio",
    # Bands (raw)
    "bands_sub", "bands_bass", "bands_low_mids", "bands_mids",
    "bands_presence", "bands_sibilance", "bands_air",
    # Bands (perceptual)
    "perceptual_bands_sub", "perceptual_bands_bass", "perceptual_bands_low_mids",
    "perceptual_bands_mids", "perceptual_bands_presence", "perceptual_bands_sibilance",
    "perceptual_bands_air",
    # Bands (mid)
    "mid_bands_sub", "mid_bands_bass", "mid_bands_low_mids", "mid_bands_mids",
    "mid_bands_presence", "mid_bands_sibilance", "mid_bands_air",
    # Bands (side)
    "side_bands_sub", "side_bands_bass", "side_bands_low_mids", "side_bands_mids",
    "side_bands_presence", "side_bands_sibilance", "side_bands_air",
    # Correlation
    "correlation_sub", "correlation_bass", "correlation_low_mids", "correlation_mids",
    "correlation_presence", "correlation_sibilance", "correlation_air",
    # Perceptual summary
    "perceived_presence_share", "perceived_low_end_share",
    # Spectral features
    "centroid_hz", "rolloff_85_hz", "high_frequency_share",
    # Tonal balance
    "tonal_low_end_share", "tonal_body_share", "tonal_clarity_share",
    "tonal_perceived_clarity_share", "tonal_profile",
    # Dynamics
    "dynamic_crest_factor_db", "dynamic_transient_margin_db",
    "dynamic_short_term_range_db", "dynamic_section_range_db", "dynamics_profile",
    # Stereo field
    "stereo_low_side_share", "stereo_low_band_correlation", "stereo_image",
    # Section aggregates
    "section_rms_min", "section_rms_max", "section_rms_mean", "section_count",
    # Chords / key
    "key_confidence_score", "chord_changes_per_minute",
    "chord_complex_ratio", "chord_named_sections",
    # Goal context
    "mix_goal_key",
    # Target
    "technical_score",
]


def feature_vector_array(vector: dict[str, float | None]) -> list[float]:
    """Convert a feature vector dict to a fixed-order list of floats.

    Missing or None values become 0.0. The order matches FEATURE_VECTOR_KEYS
    (excluding 'technical_score' which is the prediction target).

    Returns a list of floats suitable for numpy/torch model input.
    The last element is the technical score (prediction target).
    """
    return [vector.get(key, 0.0) or 0.0 for key in FEATURE_VECTOR_KEYS]


def feature_vector_names() -> list[str]:
    """Return the list of feature names in order, for model interpretability."""
    return list(FEATURE_VECTOR_KEYS)
