"""Tests for comparison.py — reference-track comparison logic.

Covers:
- compare_metrics()      — 4 scenario tests
- comparison_advice()    — 6 scenario tests
- reference_coaching()   — 6 scenario tests
- version_advice()       — 4 scenario tests
- revision_coaching()    — 4 scenario tests
"""

from __future__ import annotations


from audio_analysis.integration.comparison import (
    compare_metrics,
    comparison_advice,
    match_score,
    reference_coaching,
    version_advice,
    revision_coaching,
)

BANDS = [
    ("sub", 20, 60),
    ("bass", 60, 250),
    ("low_mids", 250, 500),
    ("mids", 500, 2000),
    ("presence", 2000, 6000),
    ("sibilance", 6000, 8000),
    ("air", 8000, 16000),
]


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def _mix(**overrides: object) -> dict:
    """Baseline mix metrics dict."""
    m = {
        "peak_dbfs": -6.0,
        "rms_dbfs_estimate": -18.0,
        "crest_factor_db": 14.0,
        "stereo_width_ratio": 0.45,
        "stereo_correlation": 0.85,
        "integrated_lufs": -16.0,
        "true_peak_dbfs": -5.5,
        "loudest_section_rms_dbfs": -12.0,
        "bands": {
            "sub": 0.06, "bass": 0.12, "low_mids": 0.10,
            "mids": 0.38, "presence": 0.16, "sibilance": 0.08, "air": 0.04,
        },
        "perceptual_bands": {
            "sub": 0.04, "bass": 0.09, "low_mids": 0.08,
            "mids": 0.35, "presence": 0.18, "sibilance": 0.10, "air": 0.06,
        },
        "mix_goal": {"key": "premaster", "label": "Premaster", "target": ""},
    }
    for k, v in overrides.items():
        if isinstance(v, dict) and isinstance(m.get(k), dict):
            m[k].update(v)
        else:
            m[k] = v
    return m


def _ref(**overrides: object) -> dict:
    """Baseline reference metrics dict."""
    return _mix(**overrides)


def metric_float(val: object, default: float = 0.0) -> float:
    try:
        return float(val) if val not in {None, "", "n/a"} else default
    except (ValueError, TypeError):
        return default


def mix_goal_info(value: str) -> dict:
    return {"key": value, "label": value.capitalize() if value else "Premaster", "target": ""}


# ==============================================================================
#  compare_metrics
# ==============================================================================

class TestCompareMetrics:

    def test_identical_mix_and_ref(self):
        """Same metrics → all deltas = 0."""
        m = _mix()
        c = compare_metrics(m, _ref(), BANDS)
        assert c["rms_delta_db"] == 0
        assert c["peak_delta_db"] == 0
        assert c["crest_delta_db"] == 0
        assert c["largest_spectral_difference"]["delta"] == 0
        assert c["largest_perceptual_difference"]["delta"] == 0
        assert c["lufs_delta_db"] == 0

    def test_louder_mix(self):
        """Mix is louder across the board."""
        m = _mix(peak_dbfs=-3.0, rms_dbfs_estimate=-14.0, integrated_lufs=-12.0)
        c = compare_metrics(m, _ref(), BANDS)
        assert c["rms_delta_db"] == 4.0  # -14 - (-18)
        assert c["peak_delta_db"] == 3.0
        assert c["lufs_delta_db"] == 4.0  # -12 - (-16)

    def test_quieter_mix(self):
        """Mix is quieter than reference."""
        m = _mix(peak_dbfs=-9.0, rms_dbfs_estimate=-22.0, integrated_lufs=-20.0)
        c = compare_metrics(m, _ref(), BANDS)
        assert c["rms_delta_db"] == -4.0
        assert c["lufs_delta_db"] == -4.0

    def test_different_band_energy(self):
        """Different band energy → largest delta reported correctly."""
        m = _mix(bands={"sub": 0.20, "bass": 0.30, "low_mids": 0.12, "mids": 0.20, "presence": 0.06, "sibilance": 0.02, "air": 0.01})
        c = compare_metrics(m, _ref(), BANDS)
        # Largest spectral delta should be sub (0.20-0.06=0.14) or bass (0.30-0.12=0.18)
        assert c["largest_spectral_difference"]["band"] in ("bass", "sub"), (
            f"Expected bass or sub, got {c['largest_spectral_difference']}"
        )
        assert abs(c["largest_spectral_difference"]["delta"]) > 0.1, (
            f"Delta should be large, got {c['largest_spectral_difference']}"
        )


# ==============================================================================
#  comparison_advice
# ==============================================================================

class TestComparisonAdvice:

    def test_no_advice_close_match(self):
        """Small deltas → catch-all advice about closeness."""
        comp = {
            "rms_delta_db": 0.5, "peak_delta_db": 0.3, "crest_delta_db": 0.2,
            "loudest_section_delta_db": 0.1, "stereo_width_delta": 0.02,
            "correlation_delta": 0.01, "lufs_delta_db": 0.3, "true_peak_delta_db": 0.1,
            "band_delta": {n: 0.0 for n, _, _ in BANDS},
            "perceptual_band_delta": {n: 0.0 for n, _, _ in BANDS},
            "largest_spectral_difference": {"band": "", "delta": 0.0},
            "largest_perceptual_difference": {"band": "", "delta": 0.0},
        }
        advice = comparison_advice(comp)
        assert len(advice) == 1
        assert "broadly close" in advice[0]

    def test_loudness_difference_triggers_lufs_advice(self):
        """Large LUFS delta > 1.5 → loudness advice."""
        comp = {
            "rms_delta_db": 2.0, "peak_delta_db": 0.3, "crest_delta_db": 0.2,
            "loudest_section_delta_db": 0.1, "stereo_width_delta": 0.02,
            "correlation_delta": 0.01, "lufs_delta_db": -3.5, "true_peak_delta_db": 0.1,
            "band_delta": {n: 0.0 for n, _, _ in BANDS},
            "perceptual_band_delta": {n: 0.0 for n, _, _ in BANDS},
            "largest_spectral_difference": {"band": "", "delta": 0.0},
            "largest_perceptual_difference": {"band": "", "delta": 0.0},
        }
        advice = comparison_advice(comp)
        lufs_items = [a for a in advice if "LUFS" in a]
        assert len(lufs_items) >= 1
        assert "quieter" in lufs_items[0]

    def test_lufs_none_falls_back_to_rms(self):
        """LUFS delta is None → falls back to RMS loudness advice."""
        comp = {
            "rms_delta_db": 4.0, "peak_delta_db": 0.3, "crest_delta_db": 0.2,
            "loudest_section_delta_db": 0.1, "stereo_width_delta": 0.02,
            "correlation_delta": 0.01, "lufs_delta_db": None, "true_peak_delta_db": 0.1,
            "band_delta": {n: 0.0 for n, _, _ in BANDS},
            "perceptual_band_delta": {n: 0.0 for n, _, _ in BANDS},
            "largest_spectral_difference": {"band": "", "delta": 0.0},
            "largest_perceptual_difference": {"band": "", "delta": 0.0},
        }
        advice = comparison_advice(comp)
        rms_items = [a for a in advice if "RMS" in a]
        assert len(rms_items) >= 1
        assert "louder" in rms_items[0]

    def test_crest_delta_triggers_advice(self):
        """Crest delta < -3 → dynamics flattening advice."""
        comp = {
            "rms_delta_db": 0.5, "peak_delta_db": 0.3, "crest_delta_db": -4.0,
            "loudest_section_delta_db": 0.1, "stereo_width_delta": 0.02,
            "correlation_delta": 0.01, "lufs_delta_db": 0.3, "true_peak_delta_db": 0.1,
            "band_delta": {n: 0.0 for n, _, _ in BANDS},
            "perceptual_band_delta": {n: 0.0 for n, _, _ in BANDS},
            "largest_spectral_difference": {"band": "", "delta": 0.0},
            "largest_perceptual_difference": {"band": "", "delta": 0.0},
        }
        advice = comparison_advice(comp)
        crest_items = [a for a in advice if "crest" in a]
        assert len(crest_items) >= 1
        assert "less crest" in crest_items[0] or "flattening" in crest_items[0]

    def test_width_and_tonal_delta(self):
        """Width > 0.25 and spectral delta > 0.04 both trigger."""
        comp = {
            "rms_delta_db": 0.5, "peak_delta_db": 0.3, "crest_delta_db": 0.2,
            "loudest_section_delta_db": 0.1, "stereo_width_delta": 0.30,
            "correlation_delta": 0.01, "lufs_delta_db": 0.3, "true_peak_delta_db": 0.1,
            "band_delta": {"sub": 0.06, "bass": 0.02, "low_mids": 0.01, "mids": -0.02, "presence": 0.0, "sibilance": 0.0, "air": 0.0},
            "perceptual_band_delta": {"sub": 0.0, "bass": 0.0, "low_mids": 0.0, "mids": 0.0, "presence": 0.05, "sibilance": 0.0, "air": 0.0},
            "largest_spectral_difference": {"band": "sub", "delta": 0.06},
            "largest_perceptual_difference": {"band": "presence", "delta": 0.05},
        }
        advice = comparison_advice(comp)
        width_items = [a for a in advice if "wider" in a]
        tonal_items = [a for a in advice if "tonal difference" in a or "biggest" in a]
        assert len(width_items) >= 1, f"Missing width advice: {advice}"
        assert len(tonal_items) >= 1, f"Missing tonal advice: {advice}"


# ==============================================================================
#  reference_coaching
# ==============================================================================

class TestReferenceCoaching:

    def test_close_match_no_warnings(self):
        """Small deltas → level_match_required=False, next_move is tonal."""
        comp = {
            "rms_delta_db": 0.3, "crest_delta_db": 0.2, "stereo_width_delta": 0.02,
            "correlation_delta": 0.01, "lufs_delta_db": 0.4,
            "largest_spectral_difference": {"band": "sub", "delta": 0.01},
            "largest_perceptual_difference": {"band": "", "delta": 0.0},
        }
        result = reference_coaching(comp, _mix(), {"name": "Ref Track", "saved": True}, metric_float=metric_float, mix_goal_info=mix_goal_info)
        assert result["level_match_required"] is False
        assert result["reference"]["name"] == "Ref Track"
        assert "Levels are close enough" in result["level_message"]

    def test_level_match_required(self):
        """LUFS delta > 1.5 → level_match_required=True."""
        comp = {
            "rms_delta_db": 2.0, "crest_delta_db": 0.2, "stereo_width_delta": 0.02,
            "correlation_delta": 0.01, "lufs_delta_db": 3.0,
            "largest_spectral_difference": {"band": "", "delta": 0.0},
            "largest_perceptual_difference": {"band": "", "delta": 0.0},
        }
        result = reference_coaching(comp, _mix(), {"name": "Ref"}, metric_float=metric_float, mix_goal_info=mix_goal_info)
        assert result["level_match_required"] is True
        assert "Level-match first" in result["level_message"]
        assert "Level-match" in result["next_move"]

    def test_lufs_none_rms_used(self):
        """LUFS delta None → use RMS for level check."""
        comp = {
            "rms_delta_db": -2.0, "crest_delta_db": 0.2, "stereo_width_delta": 0.02,
            "correlation_delta": 0.01, "lufs_delta_db": None,
            "largest_spectral_difference": {"band": "", "delta": 0.0},
            "largest_perceptual_difference": {"band": "", "delta": 0.0},
        }
        result = reference_coaching(comp, _mix(), {"name": "Ref"}, metric_float=metric_float, mix_goal_info=mix_goal_info)
        # RMS delta = 2.0 > 1.5 so level match should be required
        assert result["level_match_required"] is True

    def test_tonal_delta_reported(self):
        """Spectral delta > 0.02 → tonal_message populated."""
        comp = {
            "rms_delta_db": 0.3, "crest_delta_db": 0.2, "stereo_width_delta": 0.02,
            "correlation_delta": 0.01, "lufs_delta_db": 0.4,
            "largest_spectral_difference": {"band": "low_mids", "delta": 0.06},
            "largest_perceptual_difference": {"band": "", "delta": 0.0},
        }
        result = reference_coaching(comp, _mix(), {"name": "Ref"}, metric_float=metric_float, mix_goal_info=mix_goal_info)
        assert "low_mids" in result["tonal_message"] or "low mids" in result["tonal_message"]
        assert "more" in result["tonal_message"]

    def test_crest_and_width_triggers(self):
        """Crest delta > 1.5 and width delta > 0.15 → specific messages."""
        comp = {
            "rms_delta_db": 0.3, "crest_delta_db": 2.5, "stereo_width_delta": -0.22,
            "correlation_delta": -0.10, "lufs_delta_db": 0.4,
            "largest_spectral_difference": {"band": "", "delta": 0.01},
            "largest_perceptual_difference": {"band": "", "delta": 0.0},
        }
        result = reference_coaching(comp, _mix(), {"name": "Ref"}, metric_float=metric_float, mix_goal_info=mix_goal_info)
        assert "more crest" in result["dynamics_message"]
        assert "narrower" in result["stereo_message"]
        # next_move should be dynamics since crest_delta > 1.5
        assert "crest" in result["next_move"] or "punch" in result["next_move"]

    def test_perceived_message_populated(self):
        """Perceptual delta > 0.03 → perceived_message populated."""
        comp = {
            "rms_delta_db": 0.3, "crest_delta_db": 0.2, "stereo_width_delta": 0.02,
            "correlation_delta": 0.01, "lufs_delta_db": 0.4,
            "largest_spectral_difference": {"band": "", "delta": 0.01},
            "largest_perceptual_difference": {"band": "presence", "delta": -0.05},
        }
        result = reference_coaching(comp, _mix(), {"name": "Ref"}, metric_float=metric_float, mix_goal_info=mix_goal_info)
        assert "presence" in result["perceived_message"]
        assert "less" in result["perceived_message"]


# ==============================================================================
#  version_advice
# ==============================================================================

class TestVersionAdvice:

    def test_no_changes(self):
        """All small deltas → catch-all advice."""
        comp = {
            "rms_delta_db": 0.3, "crest_delta_db": 0.2, "stereo_width_delta": 0.02,
            "correlation_delta": 0.01, "lufs_delta_db": 0.4,
            "largest_spectral_difference": {"band": "", "delta": 0.0},
            "largest_perceptual_difference": {"band": "", "delta": 0.0},
        }
        advice = version_advice(comp)
        assert len(advice) == 1
        assert "technically close" in advice[0]

    def test_lufs_delta_large(self):
        """LUFS delta > 1.0 → loudness version advice."""
        comp = {
            "rms_delta_db": 0.3, "crest_delta_db": 0.2, "stereo_width_delta": 0.02,
            "correlation_delta": 0.01, "lufs_delta_db": -2.0,
            "largest_spectral_difference": {"band": "", "delta": 0.0},
            "largest_perceptual_difference": {"band": "", "delta": 0.0},
        }
        advice = version_advice(comp)
        lufs_items = [a for a in advice if "LUFS" in a]
        assert len(lufs_items) >= 1
        assert "quieter" in lufs_items[0]

    def test_crest_and_width_version_changes(self):
        """Crest delta > 1.5 and width delta > 0.15 → both mentioned."""
        comp = {
            "rms_delta_db": 0.3, "crest_factor_db": -2.0, "stereo_width_delta": 0.20,
            "correlation_delta": 0.01, "lufs_delta_db": 0.4,
            "largest_spectral_difference": {"band": "", "delta": 0.0},
            "largest_perceptual_difference": {"band": "", "delta": 0.0},
        }
        advice = version_advice(comp)
        crest_items = [a for a in advice if "Dynamics" in a or "crest" in a or "punch" in a]
        width_items = [a for a in advice if "wider" in a]
        assert len(crest_items) >= 1
        assert len(width_items) >= 1

    def test_spectral_and_perceptual_version_changes(self):
        """Spectral and perceptual deltas > 0.03 → both mentioned."""
        comp = {
            "rms_delta_db": 0.3, "crest_delta_db": 0.2, "stereo_width_delta": 0.02,
            "correlation_delta": 0.01, "lufs_delta_db": 0.4,
            "largest_spectral_difference": {"band": "bass", "delta": 0.05},
            "largest_perceptual_difference": {"band": "presence", "delta": -0.04},
        }
        advice = version_advice(comp)
        spectral_items = [a for a in advice if "bass" in a]
        perceived_items = [a for a in advice if "presence" in a]
        assert len(spectral_items) >= 1, f"Missing bass spectral advice: {advice}"
        assert len(perceived_items) >= 1, f"Missing presence perceived advice: {advice}"


# ==============================================================================
#  revision_coaching
# ==============================================================================

class TestRevisionCoaching:

    def test_no_previous_report(self):
        """No previous report → returns None."""
        result = revision_coaching({"metrics": {}}, None, metric_float=metric_float, mix_goal_info=mix_goal_info)
        assert result is None

    def test_improved_verdict(self):
        """Verdict 'improved' → positive headline."""
        current = {
            "metrics": _mix(technical_score=85),
            "flags": [],
            "version_comparison": {},
            "revision_impact": {"verdict": "improved", "improvements": ["Low end tightened"], "regressions": [], "checks": []},
        }
        previous = {"metrics": _mix(technical_score=70), "flags": [{"label": "Low-end mud"}]}
        result = revision_coaching(current, previous, metric_float=metric_float, mix_goal_info=mix_goal_info)
        assert result["verdict"] == "improved"
        assert "right direction" in result["headline"]
        assert result["score_delta"] == 15.0

    def test_regressed_verdict(self):
        """Verdict 'regressed' → warning headline."""
        current = {
            "metrics": _mix(technical_score=60),
            "flags": [{"label": "Clipping risk"}, {"label": "Low headroom"}],
            "version_comparison": {},
            "revision_impact": {"verdict": "regressed", "improvements": [], "regressions": ["Hot Mix", "Clipping risk"], "checks": []},
        }
        previous = {"metrics": _mix(technical_score=80), "flags": [{"label": "Low presence"}]}
        result = revision_coaching(current, previous, metric_float=metric_float, mix_goal_info=mix_goal_info)
        assert result["verdict"] == "regressed"
        assert "more technical risk" in result["headline"]
        assert "Clipping risk" in result["new_flags"]
        assert "Low presence" in result["cleared_flags"]

    def test_mixed_verdict(self):
        """Verdict 'mixed' → balanced headline."""
        current = {
            "metrics": _mix(technical_score=75),
            "flags": [{"label": "Low-mid build-up"}],
            "version_comparison": {},
            "revision_impact": {"verdict": "mixed", "improvements": [], "regressions": [], "checks": ["Check low-mids"]},
        }
        previous = {"metrics": _mix(technical_score=70), "flags": [{"label": "Low-mid build-up"}]}
        result = revision_coaching(current, previous, metric_float=metric_float, mix_goal_info=mix_goal_info)
        assert result["verdict"] == "mixed"
        assert "trade-offs" in result["headline"]

    def test_cleared_and_new_flags(self):
        """Cleared and new flags correctly computed."""
        current = {
            "metrics": _mix(technical_score=80),
            "flags": [{"label": "Low headroom"}],
            "version_comparison": {},
            "revision_impact": {"verdict": "similar", "improvements": [], "regressions": [], "checks": []},
        }
        previous = {
            "metrics": _mix(technical_score=75),
            "flags": [{"label": "Low headroom"}, {"label": "Mono risk"}, {"label": "Low dynamics"}],
        }
        result = revision_coaching(current, previous, metric_float=metric_float, mix_goal_info=mix_goal_info)
        assert "Mono risk" in result["cleared_flags"]
        assert "Low dynamics" in result["cleared_flags"]
        assert "Low headroom" in result["unchanged_flags"]
        assert len(result["new_flags"]) == 0


# ----- match_score -----

class TestMatchScore:
    """Tests for A8.2 match_score()."""

    def test_perfect_match_returns_100(self):
        """Identical tonal score + zero deltas should score 100."""
        comparison = {
            "tonal_balance_score": 1.0,
            "lufs_delta_db": 0.0,
            "stereo_width_delta": 0.0,
            "correlation_delta": 0.0,
        }
        assert match_score(comparison) == 100

    def test_large_lufs_delta_reduces_score(self):
        """A 6dB LUFS difference should eliminate the LUFS component (20 pts)."""
        comparison = {
            "tonal_balance_score": 1.0,
            "lufs_delta_db": 6.0,
            "stereo_width_delta": 0.0,
            "correlation_delta": 0.0,
        }
        score = match_score(comparison)
        assert score < 100
        assert score == 80  # 70 tonal + 0 lufs + 10 stereo

    def test_no_tonal_score_uses_neutral(self):
        """Missing tonal_balance_score uses neutral 35 pts."""
        comparison = {
            "tonal_balance_score": None,
            "lufs_delta_db": 0.0,
            "stereo_width_delta": 0.0,
            "correlation_delta": 0.0,
        }
        score = match_score(comparison)
        assert 30 <= score <= 70  # neutral ≈ 35 + 20 + 10 = 65

    def test_score_is_clamped_0_to_100(self):
        """Score never falls below 0 or above 100."""
        very_different = {
            "tonal_balance_score": 0.0,
            "lufs_delta_db": 24.0,
            "stereo_width_delta": 1.0,
            "correlation_delta": 1.0,
        }
        assert match_score(very_different) == 0

    def test_returns_integer(self):
        """match_score always returns an int."""
        comparison = {"tonal_balance_score": 0.75, "lufs_delta_db": 1.5, "stereo_width_delta": 0.1, "correlation_delta": 0.0}
        assert isinstance(match_score(comparison), int)
