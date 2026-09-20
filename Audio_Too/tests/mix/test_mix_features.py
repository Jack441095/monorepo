"""Tests for the standardised mix feature vector extractor."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "studio" / "audio_analysis"))

from audio_analysis.mix_features import (
    extract_feature_vector,
    feature_vector_array,
    feature_vector_names,
    FEATURE_VECTOR_KEYS,
)


def _make_minimal_metrics() -> dict:
    """Return a metrics dict with every key that the feature vector reads."""
    return {
        "filename": "test.wav",
        "duration_seconds": 120.0,
        "sample_rate": 44100,
        "peak_dbfs": -3.21,
        "left_peak_dbfs": -3.5,
        "right_peak_dbfs": -4.1,
        "rms_dbfs_estimate": -18.5,
        "loudest_section_rms_dbfs": -12.3,
        "dynamic_range_estimate_db": 8.2,
        "crest_factor_db": 14.0,
        "true_peak_dbfs": -2.9,
        "integrated_lufs": -14.2,
        "leading_silence_seconds": 0.02,
        "trailing_silence_seconds": 0.15,
        "dc_offset": 0.0001,
        "stereo_balance": 0.02,
        "stereo_correlation": 0.85,
        "stereo_width_ratio": 0.35,
        "clipping_risk": False,
        "clipped_frames_estimate": 0,
        "bands": {
            "sub": 0.05, "bass": 0.10, "low_mids": 0.20,
            "mids": 0.35, "presence": 0.18, "sibilance": 0.08, "air": 0.04,
        },
        "perceptual_bands": {
            "sub": 0.02, "bass": 0.06, "low_mids": 0.15,
            "mids": 0.30, "presence": 0.25, "sibilance": 0.12, "air": 0.10,
        },
        "mid_bands": {
            "sub": 0.03, "bass": 0.08, "low_mids": 0.18,
            "mids": 0.32, "presence": 0.22, "sibilance": 0.10, "air": 0.07,
        },
        "side_bands": {
            "sub": 0.01, "bass": 0.02, "low_mids": 0.05,
            "mids": 0.08, "presence": 0.10, "sibilance": 0.06, "air": 0.04,
        },
        "correlation_bands": {
            "sub": 0.95, "bass": 0.90, "low_mids": 0.85,
            "mids": 0.80, "presence": 0.75, "sibilance": 0.70, "air": 0.65,
        },
        "perceptual_summary": {
            "dominant_band": "mids",
            "presence_share": 0.47,
            "low_end_share": 0.08,
            "description": "Fletcher-Munson style weighting puts the perceived focus around mids.",
        },
        "spectral_features": {
            "centroid_hz": 1200.5,
            "rolloff_85_hz": 8500.0,
            "high_frequency_share": 0.05,
        },
        "tonal_balance": {
            "profile": "balanced",
            "low_end_share": 0.15,
            "body_share": 0.55,
            "clarity_share": 0.30,
            "perceived_clarity_share": 0.35,
            "summary": "Balanced tonal profile.",
        },
        "dynamic_profile": {
            "profile": "controlled",
            "crest_factor_db": 14.0,
            "transient_margin_db": 3.2,
            "short_term_range_db": 6.5,
            "section_range_db": 8.1,
            "summary": "Controlled dynamics.",
        },
        "stereo_field": {
            "image": "stable",
            "low_side_share": 0.02,
            "low_band_correlation": 0.92,
            "summary": "Stable stereo image.",
        },
        "section_analysis": {
            "sections": [
                {"label": "Intro", "start": 0, "end": 10, "rms_dbfs": -22.0},
                {"label": "Verse", "start": 10, "end": 30, "rms_dbfs": -18.5},
                {"label": "Chorus", "start": 30, "end": 50, "rms_dbfs": -12.3},
            ],
            "highlights": {"loudest_section": {"label": "Chorus", "rms_dbfs": -12.3}},
        },
        "chords": {
            "estimated_key": "C Major",
            "key_confidence_score": 0.85,
            "key_confidence": "high",
            "progression": [
                {"chord": "C Maj", "start_time": 0.0, "confidence": "high", "confidence_score": 0.9},
            ],
            "sanity": {
                "notes": ["stable_progression"],
                "changes_per_minute": 8.0,
                "low_confidence_sections": 0,
                "complex_chord_ratio": 0.1,
                "named_sections": 2,
            },
        },
        "mix_goal": {"key": "premaster", "label": "Premaster"},
        "technical_score": 82,
    }


def test_extract_feature_vector_returns_all_keys() -> None:
    metrics = _make_minimal_metrics()
    vector = extract_feature_vector(metrics)

    assert isinstance(vector, dict)
    assert len(vector) > 50
    assert vector["duration_seconds"] == 120.0
    assert vector["sample_rate"] == 44100
    assert vector["peak_dbfs"] == -3.21
    assert vector["technical_score"] == 82


def test_extract_feature_vector_handles_empty_metrics() -> None:
    vector = extract_feature_vector({})
    assert vector == {}


def test_extract_feature_vector_handles_none() -> None:
    vector = extract_feature_vector(None)  # type: ignore[arg-type]
    assert vector == {}


def test_extract_feature_vector_all_values_are_numeric() -> None:
    metrics = _make_minimal_metrics()
    vector = extract_feature_vector(metrics)

    for key, value in vector.items():
        assert value is None or isinstance(value, (int, float)), (
            f"Key '{key}' has type {type(value).__name__}: {value!r}"
        )


def test_extract_feature_vector_clipping_risk_is_float() -> None:
    metrics = _make_minimal_metrics()
    metrics["clipping_risk"] = True
    vector = extract_feature_vector(metrics)
    assert vector["clipping_risk"] == 1.0

    metrics["clipping_risk"] = False
    vector = extract_feature_vector(metrics)
    assert vector["clipping_risk"] == 0.0


def test_extract_feature_vector_handles_n_a_lufs() -> None:
    metrics = _make_minimal_metrics()
    metrics["integrated_lufs"] = "n/a"
    vector = extract_feature_vector(metrics)
    assert vector["integrated_lufs"] is None


def test_extract_feature_vector_profiles_are_ints() -> None:
    metrics = _make_minimal_metrics()
    vector = extract_feature_vector(metrics)
    assert vector["tonal_profile"] in {0, 1, 2, 3, -1}
    assert vector["dynamics_profile"] in {0, 1, 2, 3, -1}
    assert vector["stereo_image"] in {0, 1, 2, 3, -1}


def test_extract_feature_vector_section_aggregates() -> None:
    metrics = _make_minimal_metrics()
    vector = extract_feature_vector(metrics)
    assert vector["section_count"] == 3.0
    assert vector["section_rms_min"] == -22.0
    assert vector["section_rms_max"] == -12.3
    assert vector["section_rms_mean"] is not None


def test_extract_feature_vector_empty_sections() -> None:
    metrics = _make_minimal_metrics()
    metrics["section_analysis"] = {"sections": [], "highlights": {}}
    vector = extract_feature_vector(metrics)
    assert vector["section_count"] == 0.0
    assert vector["section_rms_min"] is None
    assert vector["section_rms_max"] is None
    assert vector["section_rms_mean"] is None


def test_extract_feature_vector_no_chords() -> None:
    metrics = _make_minimal_metrics()
    metrics["chords"] = {}
    vector = extract_feature_vector(metrics)
    assert vector["key_confidence_score"] == 0.0
    assert vector["chord_changes_per_minute"] == 0.0
    assert vector["chord_complex_ratio"] == 0.0


def test_extract_feature_vector_unknown_goal() -> None:
    metrics = _make_minimal_metrics()
    metrics["mix_goal"] = {"key": "unknown_goal"}
    vector = extract_feature_vector(metrics)
    assert vector["mix_goal_key"] == -1.0


def test_feature_vector_array_order_matches_keys() -> None:
    metrics = _make_minimal_metrics()
    vector = extract_feature_vector(metrics)
    array = feature_vector_array(vector)

    assert isinstance(array, list)
    assert len(array) == len(FEATURE_VECTOR_KEYS)
    assert all(isinstance(v, float) for v in array)


def test_feature_vector_array_handles_missing_keys() -> None:
    vector = {"peak_dbfs": -3.21}
    array = feature_vector_array(vector)
    assert len(array) == len(FEATURE_VECTOR_KEYS)
    assert all(isinstance(v, float) for v in array)


def test_feature_vector_names_returns_strings() -> None:
    names = feature_vector_names()
    assert len(names) == len(FEATURE_VECTOR_KEYS)
    assert all(isinstance(n, str) for n in names)
    assert "technical_score" in names
    assert "peak_dbfs" in names
