"""Tests for mix_features.py — feature vector extraction for ML models.

Covers:
- extract_feature_vector()  — 8 scenario tests
- metric_float()            — 4 edge-case tests
- _band_shares()            — 2 tests
- _tonal_profile_int()      — 2 tests
- _dynamics_profile_int()   — 2 tests
- _stereo_image_int()       — 2 tests
- _band_correlations()      — 2 tests
- _goal_key_int()           — 2 tests
- feature_vector_array()    — 2 tests
- helper accessors          — 3 tests
"""

from __future__ import annotations


from audio_analysis.mix_features import (
    extract_feature_vector,
    metric_float,
    _band_shares,
    _tonal_profile_int,
    _dynamics_profile_int,
    _stereo_image_int,
    _band_correlations,
    _goal_key_int,
    feature_vector_array,
    feature_vector_names,
    FEATURE_VECTOR_KEYS,
)


# ==============================================================================
#  Helpers
# ==============================================================================

def _minimal_metrics(**overrides: object) -> dict:
    """Minimal metrics with all optional nested keys."""
    m: dict = {
        "duration_seconds": 120.0,
        "sample_rate": 44100,
        "peak_dbfs": -3.2,
        "left_peak_dbfs": -3.5,
        "right_peak_dbfs": -3.8,
        "rms_dbfs_estimate": -18.5,
        "loudest_section_rms_dbfs": -12.0,
        "dynamic_range_estimate_db": 28.0,
        "crest_factor_db": 14.2,
        "true_peak_dbfs": -2.8,
        "integrated_lufs": -16.0,
        "leading_silence_seconds": 0.05,
        "trailing_silence_seconds": 0.1,
        "stereo_balance": 1.02,
        "stereo_correlation": 0.82,
        "stereo_width_ratio": 0.48,
        "dc_offset": 0.001,
        "clipping_risk": False,
        "clipped_frames_estimate": 0,
        "technical_score": 85,
        "bands": {
            "sub": 0.06, "bass": 0.12, "low_mids": 0.10,
            "mids": 0.38, "presence": 0.16, "sibilance": 0.08, "air": 0.04,
        },
        "perceptual_bands": {
            "sub": 0.04, "bass": 0.09, "low_mids": 0.08,
            "mids": 0.35, "presence": 0.18, "sibilance": 0.10, "air": 0.06,
        },
        "mid_bands": {
            "sub": 0.05, "bass": 0.10, "low_mids": 0.09,
            "mids": 0.36, "presence": 0.17, "sibilance": 0.09, "air": 0.05,
        },
        "side_bands": {
            "sub": 0.01, "bass": 0.03, "low_mids": 0.01,
            "mids": 0.02, "presence": 0.02, "sibilance": 0.01, "air": 0.01,
        },
        "correlation_bands": {
            "sub": 0.85, "bass": 0.80, "low_mids": 0.82,
            "mids": 0.78, "presence": 0.75, "sibilance": 0.70, "air": 0.65,
        },
        "perceptual_summary": {"presence_share": 0.22, "low_end_share": 0.18},
        "spectral_features": {"centroid_hz": 1800, "rolloff_85_hz": 5200, "high_frequency_share": 0.12},
        "tonal_balance": {
            "profile": "Balanced",
            "low_end_share": 0.18,
            "body_share": 0.48,
            "clarity_share": 0.34,
            "perceived_clarity_share": 0.28,
        },
        "dynamic_profile": {
            "profile": "Controlled",
            "crest_factor_db": 14.2,
            "transient_margin_db": 8.5,
            "short_term_range_db": 6.0,
            "section_range_db": 5.5,
        },
        "stereo_field": {
            "image": "Stable",
            "low_side_share": 0.02,
            "low_band_correlation": 0.82,
        },
        "section_analysis": {
            "sections": [
                {"rms_dbfs": -18.0},
                {"rms_dbfs": -15.0},
                {"rms_dbfs": -20.0},
            ],
        },
        "chords": {
            "estimated_key": "C Major",
            "key_confidence_score": 0.82,
            "sanity": {
                "changes_per_minute": 2.5,
                "complex_chord_ratio": 0.15,
                "named_sections": 4,
            },
        },
        "mix_goal": {"key": "premaster", "label": "Premaster", "target": ""},
    }
    for k, v in overrides.items():
        if isinstance(v, dict) and isinstance(m.get(k), dict):
            m[k].update(v)
        else:
            m[k] = v
    return m


# ==============================================================================
#  metric_float
# ==============================================================================

class TestMetricFloat:
    def test_none(self):
        assert metric_float(None) is None
        assert metric_float(None, 0.0) == 0.0

    def test_int_float(self):
        assert metric_float(42) == 42.0
        assert metric_float(3.14) == 3.14

    def test_string_values(self):
        assert metric_float("12.5") == 12.5
        assert metric_float("n/a") is None
        assert metric_float("N/A") is None
        assert metric_float("") is None

    def test_invalid_types(self):
        assert metric_float([1, 2]) is None
        assert metric_float({}) is None
        assert metric_float([1, 2], -1.0) == -1.0


# ==============================================================================
#  _band_shares
# ==============================================================================

class TestBandShares:
    def test_normal_bands(self):
        metrics = {"bands": {"sub": 0.1, "bass": 0.2, "mids": 0.5}}
        result = _band_shares(metrics, "bands")
        assert result["bands_sub"] == 0.1
        assert result["bands_bass"] == 0.2
        assert result["bands_mids"] == 0.5
        # Missing bands default to 0.0
        assert result["bands_low_mids"] == 0.0

    def test_missing_bands_dict(self):
        """No bands in metrics → all defaults returned (0.0)."""
        result = _band_shares({}, "bands")
        assert len(result) == 7
        assert all(v == 0.0 for v in result.values())
        for name in ("sub", "bass", "low_mids", "mids", "presence", "sibilance", "air"):
            assert f"bands_{name}" in result


# ==============================================================================
#  _tonal_profile_int
# ==============================================================================

class TestTonalProfileInt:
    def test_known_profiles(self):
        assert _tonal_profile_int({"tonal_balance": {"profile": "Low-weighted"}}) == 0
        assert _tonal_profile_int({"tonal_balance": {"profile": "Balanced"}}) == 1
        assert _tonal_profile_int({"tonal_balance": {"profile": "Mid-focused"}}) == 2
        assert _tonal_profile_int({"tonal_balance": {"profile": "Bright"}}) == 3

    def test_unknown_profile(self):
        assert _tonal_profile_int({"tonal_balance": {"profile": "Unknown"}}) == -1
        assert _tonal_profile_int({}) == -1


# ==============================================================================
#  _dynamics_profile_int
# ==============================================================================

class TestDynamicsProfileInt:
    def test_known_profiles(self):
        assert _dynamics_profile_int({"dynamic_profile": {"profile": "Compressed"}}) == 0
        assert _dynamics_profile_int({"dynamic_profile": {"profile": "Controlled"}}) == 1
        assert _dynamics_profile_int({"dynamic_profile": {"profile": "Uneven"}}) == 2
        assert _dynamics_profile_int({"dynamic_profile": {"profile": "Spiky"}}) == 3

    def test_unknown_profile(self):
        assert _dynamics_profile_int({"dynamic_profile": {"profile": "Flat"}}) == -1
        assert _dynamics_profile_int({}) == -1


# ==============================================================================
#  _stereo_image_int
# ==============================================================================

class TestStereoImageInt:
    def test_known_images(self):
        assert _stereo_image_int({"stereo_field": {"image": "Narrow"}}) == 0
        assert _stereo_image_int({"stereo_field": {"image": "Stable"}}) == 1
        assert _stereo_image_int({"stereo_field": {"image": "Very wide"}}) == 2
        assert _stereo_image_int({"stereo_field": {"image": "Phase risk"}}) == 3

    def test_unknown_image(self):
        assert _stereo_image_int({"stereo_field": {"image": "Wide"}}) == -1
        assert _stereo_image_int({}) == -1


# ==============================================================================
#  _band_correlations
# ==============================================================================

class TestBandCorrelations:
    def test_normal_correlation(self):
        metrics = {"correlation_bands": {"sub": 0.9, "bass": 0.85, "mids": 0.75}}
        result = _band_correlations(metrics)
        assert result["correlation_sub"] == 0.9
        assert result["correlation_bass"] == 0.85
        assert result["correlation_mids"] == 0.75
        # Missing bands default to 1.0
        assert result["correlation_low_mids"] == 1.0

    def test_missing_corr_dict(self):
        """No correlation_bands → all defaults returned (1.0)."""
        result = _band_correlations({})
        assert len(result) == 7
        assert all(v == 1.0 for v in result.values())
        for name in ("sub", "bass", "low_mids", "mids", "presence", "sibilance", "air"):
            assert f"correlation_{name}" in result


# ==============================================================================
#  _goal_key_int
# ==============================================================================

class TestGoalKeyInt:
    def test_known_goals(self):
        assert _goal_key_int({"mix_goal": {"key": "premaster"}}) == 0
        assert _goal_key_int({"mix_goal": {"key": "club"}}) == 1
        assert _goal_key_int({"mix_goal": {"key": "podcast"}}) == 4
        assert _goal_key_int({"mix_goal": {"key": "hip_hop"}}) == 13

    def test_unknown_goal(self):
        assert _goal_key_int({"mix_goal": {"key": "custom"}}) == -1
        assert _goal_key_int({}) == -1
        assert _goal_key_int({"mix_goal": "not_a_dict"}) == -1


# ==============================================================================
#  extract_feature_vector
# ==============================================================================

class TestExtractFeatureVector:

    def test_empty_metrics(self):
        """Empty metrics → empty dict."""
        assert extract_feature_vector({}) == {}
        assert extract_feature_vector(None) == {}  # type: ignore[arg-type]

    def test_full_feature_vector(self):
        """Full realistic metrics → all keys present, correct types."""
        metrics = _minimal_metrics()
        vec = extract_feature_vector(metrics)
        # Core level keys should be present
        assert vec["peak_dbfs"] == -3.2
        assert vec["sample_rate"] == 44100.0
        assert vec["crest_factor_db"] == 14.2
        assert vec["integrated_lufs"] == -16.0
        assert vec["dc_offset"] == 0.001
        # Clipping
        assert vec["clipping_risk"] == 0.0
        assert vec["clipped_frames_estimate"] == 0.0
        # Bands
        assert vec["bands_sub"] == 0.06
        assert vec["bands_air"] == 0.04
        assert vec["perceptual_bands_sibilance"] == 0.10
        assert vec["side_bands_sub"] == 0.01
        assert vec["mid_bands_mids"] == 0.36
        # Correlations
        assert vec["correlation_sub"] == 0.85
        assert vec["correlation_air"] == 0.65
        # Perceptual summary
        assert vec["perceived_presence_share"] == 0.22
        assert vec["perceived_low_end_share"] == 0.18
        # Spectral features
        assert vec["centroid_hz"] == 1800.0
        assert vec["rolloff_85_hz"] == 5200.0
        assert vec["high_frequency_share"] == 0.12
        # Tonal balance
        assert vec["tonal_low_end_share"] == 0.18
        assert vec["tonal_body_share"] == 0.48
        assert vec["tonal_clarity_share"] == 0.34
        assert vec["tonal_perceived_clarity_share"] == 0.28
        assert vec["tonal_profile"] == 1.0  # Balanced = 1
        # Dynamics
        assert vec["dynamic_crest_factor_db"] == 14.2
        assert vec["dynamic_transient_margin_db"] == 8.5
        assert vec["dynamics_profile"] == 1.0  # Controlled = 1
        # Stereo field
        assert vec["stereo_low_side_share"] == 0.02
        assert vec["stereo_low_band_correlation"] == 0.82
        assert vec["stereo_image"] == 1.0  # Stable = 1
        # Section aggregates
        assert vec["section_count"] == 3.0
        assert vec["section_rms_min"] == -20.0
        assert vec["section_rms_max"] == -15.0
        assert vec["section_rms_mean"] == -17.666666666666668
        # Chords
        assert vec["key_confidence_score"] == 0.82
        assert vec["chord_changes_per_minute"] == 2.5
        assert vec["chord_complex_ratio"] == 0.15
        assert vec["chord_named_sections"] == 4.0
        # Goal
        assert vec["mix_goal_key"] == 0.0  # premaster = 0
        # Score
        assert vec["technical_score"] == 85.0

    def test_missing_nested_keys(self):
        """Missing optional nested dicts → safe defaults."""
        metrics = {
            "peak_dbfs": -6.0,
            "crest_factor_db": 12.0,
            "technical_score": 80,
        }
        vec = extract_feature_vector(metrics)
        assert vec["peak_dbfs"] == -6.0
        # Missing bands → defaults
        assert vec["bands_sub"] == 0.0
        assert vec["centroid_hz"] is None
        assert vec["tonal_profile"] == -1.0  # unknown → -1
        assert vec["dynamics_profile"] == -1.0
        assert vec["stereo_image"] == -1.0
        assert vec["mix_goal_key"] == -1.0
        assert vec["technical_score"] == 80.0

    def test_clipping_risk_conversion(self):
        """Boolean clipping_risk converts to 1.0/0.0 float."""
        vec_true = extract_feature_vector({"clipping_risk": True, "clipped_frames_estimate": 5})
        assert vec_true["clipping_risk"] == 1.0
        assert vec_true["clipped_frames_estimate"] == 5.0
        vec_false = extract_feature_vector({"clipping_risk": False})
        assert vec_false["clipping_risk"] == 0.0

    def test_empty_sections(self):
        """Empty section list → None for aggregates."""
        metrics = {"section_analysis": {"sections": []}}
        vec = extract_feature_vector(metrics)
        assert vec["section_count"] == 0.0
        assert vec["section_rms_min"] is None
        assert vec["section_rms_max"] is None
        assert vec["section_rms_mean"] is None

    def test_missing_sections_key(self):
        """No section_analysis at all → None for aggregates."""
        vec = extract_feature_vector({})
        assert "section_count" not in vec

    def test_n_a_integrated_lufs(self):
        """integrated_lufs = 'n/a' → None via metric_float."""
        metrics = {"integrated_lufs": "n/a"}
        vec = extract_feature_vector(metrics)
        assert vec["integrated_lufs"] is None

    def test_goal_key_mapping(self):
        """All known goal keys map correctly."""
        for key, expected in [
            ("premaster", 0.0), ("club", 1.0), ("pop_vocal", 2.0),
            ("rap_vocal", 3.0), ("podcast", 4.0), ("game_audio", 5.0),
            ("master", 6.0), ("edm", 7.0), ("acoustic", 8.0),
            ("rock", 9.0), ("cinematic", 10.0), ("lo_fi", 11.0),
            ("jazz", 12.0), ("hip_hop", 13.0),
        ]:
            vec = extract_feature_vector({"mix_goal": {"key": key}})
            assert vec["mix_goal_key"] == expected, f"{key} → {expected}"

    def test_feature_vector_keys_completeness(self):
        """All FEATURE_VECTOR_KEYS appear in output."""
        metrics = _minimal_metrics()
        vec = extract_feature_vector(metrics)
        for key in FEATURE_VECTOR_KEYS:
            assert key in vec, f"Missing key: {key}"
        assert len(vec) == len(FEATURE_VECTOR_KEYS)


# ==============================================================================
#  feature_vector_array & feature_vector_names
# ==============================================================================

class TestFeatureVectorArray:

    def test_returns_float_list(self):
        """feature_vector_array returns float list of length FEATURE_VECTOR_KEYS."""
        metrics = _minimal_metrics()
        vec = extract_feature_vector(metrics)
        arr = feature_vector_array(vec)
        assert isinstance(arr, list)
        assert len(arr) == len(FEATURE_VECTOR_KEYS)
        assert all(isinstance(v, float) for v in arr)

    def test_none_values_become_zero(self):
        """None values in the vector become 0.0 in the array."""
        vec = {k: None for k in FEATURE_VECTOR_KEYS}
        arr = feature_vector_array(vec)
        assert all(v == 0.0 for v in arr)

    def test_feature_vector_names(self):
        """feature_vector_names returns the same list as FEATURE_VECTOR_KEYS."""
        names = feature_vector_names()
        assert names == FEATURE_VECTOR_KEYS
        assert len(names) == len(set(names)), "Duplicate keys found!"
