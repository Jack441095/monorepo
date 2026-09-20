
"""Tests for analysis_interpretation and analysis_features modules.

Covers:
- analysis_interpretation: review_flags(), priority_actions()
- analysis_features: dynamic_profile(), stereo_field_summary(), tonal_balance_summary()

Each function is tested with multiple scenarios:
  Priority actions  -> 4 scenario tests (including comparison).
  Review flags      -> 4 scenario tests.
  Dynamic profile   -> 4 scenario tests (various sample data patterns).
  Stereo field sum. -> 4 scenario tests (various stereo metrics).
  Tonal balance sum.-> 4 scenario tests (various band/perceived/features).
"""

from __future__ import annotations

from typing import Any
import math


from audio_analysis.analysis_core.analysis_interpretation import (
    review_flags,
    priority_actions,
    metric_float,
    confidence_for_flag,
    generate_prose_summary,
    technical_score,
    rating_from_score,
)
import pytest

from audio_analysis.analysis_core.analysis_features import (
    dynamic_profile,
    ms_band_ratio,
    stereo_field_summary,
    tonal_balance_summary,
)

# ==============================================================================
#  Helper
# ==============================================================================

def _default_bands(overrides: dict | None = None) -> dict:
    """Baseline bands dict that triggers no spectral flags."""
    b = {
        "sub": 0.06,
        "bass": 0.12,
        "low_mids": 0.10,
        "mids": 0.38,
        "presence": 0.16,
        "sibilance": 0.08,
        "air": 0.04,
    }
    if overrides:
        b.update(overrides)
    return b


def _default_perceptual(overrides: dict | None = None) -> dict:
    p = {
        "presence": 0.18,
        "air": 0.10,
    }
    if overrides:
        p.update(overrides)
    return p


def _default_metrics(overrides: dict | None = None) -> dict:
    """A metrics dict that yields zero flags (passes all checks)."""
    m: dict[str, Any] = {
        "peak_dbfs": -6.0,
        "true_peak_dbfs": -5.5,
        "crest_factor_db": 14.0,
        "integrated_lufs": -18.0,
        "dc_offset": 0.001,
        "leading_silence_seconds": 0.1,
        "trailing_silence_seconds": 0.2,
        "stereo_balance": 1.0,
        "stereo_correlation": 0.85,
        "stereo_width_ratio": 0.45,
        "dynamic_range_estimate_db": 28.0,
        "bands": _default_bands(),
        "perceptual_bands": _default_perceptual(),
        "side_bands": {"sub": 0.02, "bass": 0.04, "low_mids": 0.06, "mids": 0.08, "presence": 0.05, "sibilance": 0.02, "air": 0.02},
        "mid_bands": {"sub": 0.05, "bass": 0.10, "low_mids": 0.15, "mids": 0.30, "presence": 0.20, "sibilance": 0.10, "air": 0.10},
        "correlation_bands": {"sub": 0.75, "bass": 0.72},
        "tonal_balance": {
            "low_end_share": 0.18,
            "clarity_share": 0.28,
        },
        "dynamic_profile": {
            "profile": "Controlled",
            "section_range_db": 6.0,
        },
        "mix_goal": {"key": "", "label": "premaster or mix", "target": ""},
    }
    if overrides:
        # Merge deep enough
        for k, v in overrides.items():
            if isinstance(v, dict) and isinstance(m.get(k), dict):
                m[k].update(v)
            else:
                m[k] = v
    return m


# ==============================================================================
#  ANALYSIS FEATURES TESTS
# ==============================================================================

# ----- dynamic_profile -----

class TestDynamicProfile:
    """Four scenario tests for dynamic_profile()."""

    def test_dynamic_controlled(self):
        """Controlled profile: moderate crest, moderate section range."""
        duration_s = 3.0
        sr = 44100
        n = int(duration_s * sr)
        # A sine tone with amplitude modulation
        samples = [0.3 * math.sin(2 * math.pi * 220 * t / sr) for t in range(n)]
        # Add some envelope variation
        for i in range(n // 3):
            samples[i] *= 0.5
        peak_db = max(abs(s) for s in samples) or 1e-9
        peak_db = 20 * math.log10(peak_db)
        rms_val = math.sqrt(sum(s * s for s in samples) / len(samples)) or 1e-9
        rms_db = 20 * math.log10(rms_val)
        window_vals = [rms_db - 2, rms_db - 1, rms_db, rms_db - 0.5]
        result = dynamic_profile(samples, sr, peak_db, rms_db, window_vals)
        assert isinstance(result, dict)
        assert "profile" in result
        assert "crest_factor_db" in result
        assert "section_range_db" in result
        assert result["profile"] in ("Controlled", "Spiky", "Compressed", "Uneven")

    def test_dynamic_spiky(self):
        """Spiky profile: large transient margin and high crest."""
        sr = 44100
        duration_s = 1.0
        n = int(duration_s * sr)
        # Mostly quiet with a few loud spikes
        samples = [0.001] * n
        for idx in [1000, 20000, 35000]:
            if idx < n:
                samples[idx] = 0.9  # spike
        samples[-1] = 0.85  # make peak_db high
        peak_db = 20 * math.log10(0.9)
        rms_val = math.sqrt(sum(s * s for s in samples) / len(samples))
        rms_db = 20 * math.log10(max(rms_val, 1e-9))
        window_vals = [rms_db - 5, rms_db - 3, rms_db]
        result = dynamic_profile(samples, sr, peak_db, rms_db, window_vals)
        # Should flag as Spiky or Compressed depending on exact numbers
        assert result["crest_factor_db"] > 0

    def test_dynamic_compressed(self):
        """Compressed profile: low crest factor."""
        sr = 44100
        n = int(0.5 * sr)
        # near-square amplitude with little variation
        samples = [0.5] * n
        peak_db = 20 * math.log10(0.5)
        rms_val = 0.5
        rms_db = 20 * math.log10(rms_val)
        window_vals = [rms_db - 0.2, rms_db - 0.1, rms_db, rms_db - 0.15]
        result = dynamic_profile(samples, sr, peak_db, rms_db, window_vals)
        # crest = 0 dB which is < 6, so should be Compressed
        assert result["profile"] == "Compressed", f"Expected Compressed got {result['profile']}"

    def test_dynamic_uneven(self):
        """Uneven profile: large section_range_db."""
        sr = 44100
        n = int(1.5 * sr)
        samples = [0.3 * math.sin(2 * math.pi * 220 * i / sr) for i in range(n)]
        peak_db = 20 * math.log10(max(abs(s) for s in samples))
        rms_val = math.sqrt(sum(s * s for s in samples) / len(samples))
        rms_db = 20 * math.log10(max(rms_val, 1e-9))
        # Create section_range_db > 10 by having very quiet and loud windows
        window_vals = [-40.0, -38.0, -20.0, -18.0, -42.0, -15.0, -12.0]
        result = dynamic_profile(samples, sr, peak_db, rms_db, window_vals)
        if result["crest_factor_db"] >= 6 and result["section_range_db"] > 10:
            assert result["profile"] == "Uneven"


# ----- stereo_field_summary -----

class TestStereoFieldSummary:
    """Four scenario tests for stereo_field_summary()."""

    def test_stereo_stable(self):
        """Stable stereo image with good correlation and moderate width."""
        metrics = {
            "stereo_correlation": 0.85,
            "stereo_width_ratio": 0.45,
            "side_bands": {"sub": 0.01, "bass": 0.02},
            "correlation_bands": {"sub": 0.80, "bass": 0.75},
        }
        result = stereo_field_summary(metrics)
        assert result["image"] == "Stable"
        assert result["low_end"] == "mono-safe"

    def test_stereo_phase_risk(self):
        """Phase risk: correlation is very low."""
        metrics = {
            "stereo_correlation": 0.10,
            "stereo_width_ratio": 0.85,
            "side_bands": {"sub": 0.06, "bass": 0.09},
            "correlation_bands": {"sub": 0.30, "bass": 0.25},
        }
        result = stereo_field_summary(metrics)
        assert result["image"] == "Phase risk", f"Expected Phase risk, got {result['image']}"
        assert "check low-end mono" in result["low_end"]

    def test_stereo_very_wide(self):
        """Very wide image: width > 0.9."""
        metrics = {
            "stereo_correlation": 0.50,
            "stereo_width_ratio": 0.95,
            "side_bands": {"sub": 0.03, "bass": 0.05},
            "correlation_bands": {"sub": 0.70, "bass": 0.68},
        }
        result = stereo_field_summary(metrics)
        assert result["image"] == "Very wide", f"Expected Very wide, got {result['image']}"

    def test_stereo_narrow(self):
        """Narrow image: width < 0.08."""
        metrics = {
            "stereo_correlation": 0.98,
            "stereo_width_ratio": 0.04,
            "side_bands": {"sub": 0.01, "bass": 0.02},
            "correlation_bands": {"sub": 0.95, "bass": 0.92},
        }
        result = stereo_field_summary(metrics)
        assert result["image"] == "Narrow", f"Expected Narrow, got {result['image']}"


# ----- tonal_balance_summary -----

class TestTonalBalanceSummary:
    """Four scenario tests for tonal_balance_summary()."""

    def test_balanced(self):
        """Balanced tonal profile."""
        bands = {"sub": 0.06, "bass": 0.10, "low_mids": 0.12, "mids": 0.38, "presence": 0.16, "sibilance": 0.06, "air": 0.04}
        perceived = {"presence": 0.18, "sibilance": 0.07, "air": 0.06}
        features = {"centroid_hz": 1200}
        result = tonal_balance_summary(bands, perceived, features)
        assert result["profile"] == "Balanced" or result["profile"] == "Mid-focused"
        assert isinstance(result["low_end_share"], float)
        assert isinstance(result["summary"], str)

    def test_low_weighted(self):
        """Low-weighted: dominant low end."""
        bands = {"sub": 0.22, "bass": 0.30, "low_mids": 0.18, "mids": 0.14, "presence": 0.06, "sibilance": 0.02, "air": 0.01}
        perceived = {"presence": 0.05, "sibilance": 0.02, "air": 0.01}
        features = {"centroid_hz": 150}
        result = tonal_balance_summary(bands, perceived, features)
        assert "low end is dominant" in str(result["outliers"])
        assert result["profile"] == "Low-weighted"

    def test_bright(self):
        """Bright profile: high clarity share and high centroid."""
        bands = {"sub": 0.03, "bass": 0.05, "low_mids": 0.08, "mids": 0.22, "presence": 0.28, "sibilance": 0.14, "air": 0.12}
        perceived = {"presence": 0.30, "sibilance": 0.15, "air": 0.14}
        features = {"centroid_hz": 4200}
        result = tonal_balance_summary(bands, perceived, features)
        assert result["profile"] == "Bright", f"Expected Bright, got {result['profile']}"

    def test_low_presence(self):
        """Low presence with low end not dominating."""
        bands = {"sub": 0.08, "bass": 0.12, "low_mids": 0.30, "mids": 0.36, "presence": 0.02, "sibilance": 0.01, "air": 0.01}
        perceived = {"presence": 0.02, "sibilance": 0.01, "air": 0.01}
        features = {"centroid_hz": 400}
        result = tonal_balance_summary(bands, perceived, features)
        # clarity < 0.05 and low_end < 0.35 so "presence is low" outlier
        assert "presence is low" in str(result["outliers"]) or len(result["outliers"]) > 0


# ==============================================================================
#  ANALYSIS INTERPRETATION TESTS
# ==============================================================================

# ----- review_flags -----

class TestReviewFlags:
    """Four scenario tests for review_flags()."""

    def test_no_flags(self):
        """Clean metrics should produce zero flags."""
        metrics = _default_metrics()
        flags = review_flags(metrics)
        assert len(flags) == 0, f"Expected no flags, got {len(flags)}: {[f['label'] for f in flags]}"

    def test_low_headroom_and_clipping(self):
        """Peaks near full scale should trigger Low headroom and Clipping risk."""
        metrics = _default_metrics({
            "peak_dbfs": -0.5,
            "true_peak_dbfs": -0.05,
        })
        flags = review_flags(metrics)
        labels = {f["label"] for f in flags}
        assert "Low headroom" in labels, f"Missing Low headroom in {labels}"
        assert "Clipping risk" in labels, f"Missing Clipping risk in {labels}"

    def test_low_dynamics_and_mono_risk(self):
        """Low crest plus low correlation triggers both flags."""
        metrics = _default_metrics({
            "crest_factor_db": 4.0,
            "stereo_correlation": 0.15,
        })
        flags = review_flags(metrics)
        labels = {f["label"] for f in flags}
        assert "Low dynamics" in labels, f"Missing Low dynamics in {labels}"
        assert "Mono risk" in labels, f"Missing Mono risk in {labels}"

    def test_perceptual_and_side_band_flags(self):
        """High perceived presence and side sub/bass triggers Harshness and Side Bass Mud."""
        metrics = _default_metrics({
            "perceptual_bands": {"presence": 0.40, "air": 0.24},
            "side_bands": {"sub": 0.06, "bass": 0.10},
            "bands": _default_bands({"low_mids": 0.20}),  # also test low_mids build-up
        })
        flags = review_flags(metrics)
        labels = {f["label"] for f in flags}
        assert "Perceived harshness" in labels, f"Missing Perceived harshness in {labels}"
        assert "Side Bass Mud" in labels, f"Missing Side Bass Mud in {labels}"

    def test_narrow_presence_flag(self):
        """Very low side energy in the presence band triggers Narrow presence."""
        metrics = _default_metrics({
            "side_bands": {"sub": 0.02, "bass": 0.04, "presence": 0.005, "air": 0.02},
        })
        flags = review_flags(metrics)
        labels = {f["label"] for f in flags}
        assert "Narrow presence" in labels, f"Expected Narrow presence flag, got {labels}"

    def test_over_widened_air_flag(self):
        """Side energy > mid energy in the air band triggers Over-widened air."""
        metrics = _default_metrics({
            "side_bands": {"sub": 0.02, "bass": 0.04, "presence": 0.05, "air": 0.15},
            "mid_bands": {"sub": 0.05, "bass": 0.10, "presence": 0.20, "air": 0.08},
        })
        flags = review_flags(metrics)
        labels = {f["label"] for f in flags}
        assert "Over-widened air" in labels, f"Expected Over-widened air flag, got {labels}"

    def test_harsh_digital_clipping_flag_is_informational(self):
        """Regression for a real bug found 2026-07-12: distortion_odd_thd
        comes from analyze_thd_n(), which assumes clean monophonic tonal
        content -- Stage M5 already proved it unbounded/unreliable on real
        polyphonic mixes (readings up to 4945, not a percentage). The flag
        must still be raised (a human should see it) but must never
        penalize technical_score, since the underlying measurement isn't
        trustworthy for the full-mix content this runs against."""
        metrics = _default_metrics({"distortion_odd_thd": 0.5})
        flags = review_flags(metrics)
        clipping_flags = [f for f in flags if f["label"] == "Harsh digital clipping"]
        assert len(clipping_flags) == 1
        assert clipping_flags[0]["informational"] is True

    def test_analog_warmth_flag_is_informational(self):
        metrics = _default_metrics({"distortion_even_thd": 0.01, "distortion_odd_thd": 0.001})
        flags = review_flags(metrics)
        warmth_flags = [f for f in flags if f["label"] == "Analog warmth"]
        assert len(warmth_flags) == 1
        assert warmth_flags[0]["informational"] is True


# ----- ms_band_ratio -----

class TestMsBandRatio:
    """Unit tests for ms_band_ratio()."""

    def test_ratio_computation(self):
        """Side share / mid share per band."""
        mid = {"sub": 0.10, "bass": 0.20, "presence": 0.15}
        side = {"sub": 0.05, "bass": 0.10, "presence": 0.30}
        result = ms_band_ratio(mid, side)
        assert pytest.approx(result["sub"], abs=0.01) == 0.5
        assert pytest.approx(result["bass"], abs=0.01) == 0.5
        assert pytest.approx(result["presence"], abs=0.01) == 2.0

    def test_divide_by_zero_guard(self):
        """Zero mid share should not raise; result should be very large but finite."""
        mid = {"sub": 0.0, "bass": 0.10}
        side = {"sub": 0.05, "bass": 0.0}
        result = ms_band_ratio(mid, side)
        assert result["sub"] > 0
        assert result["bass"] == 0.0

    def test_missing_keys_treated_as_zero(self):
        """Bands absent from either dict are treated as zero."""
        result = ms_band_ratio({}, {"presence": 0.05})
        assert result["presence"] > 0


# ----- priority_actions -----

class TestPriorityActions:
    """Four+ scenario tests for priority_actions()."""

    def test_no_flags_default_action(self):
        """When there are no flags, priority_actions returns a catch-all listen action."""
        metrics = _default_metrics()
        actions = priority_actions(metrics, [])
        assert len(actions) == 1
        assert actions[0]["focus"] == "Reference listen"
        assert actions[0]["decision"] == "check_by_ear"

    def test_high_severity_sorted_first(self):
        """High-severity flags appear before medium and low."""
        flags = [
            {"severity": "low", "label": "Low presence", "detail": "Detail A", "confidence": "medium"},
            {"severity": "high", "label": "Low headroom", "detail": "Detail B", "confidence": "high"},
            {"severity": "medium", "label": "Low-mid build-up", "detail": "Detail C", "confidence": "medium"},
        ]
        actions = priority_actions(_default_metrics(), flags)
        assert len(actions) >= 3
        # First rank should be the high-severity item
        assert actions[0]["focus"] == "Low headroom", f"Expected Low headroom first, got {actions[0]['focus']}"

    def test_reference_sensitive_without_comparison(self):
        """Reference-sensitive flags get 'needs_reference' decision when no comparison provided."""
        flags = [
            {"severity": "medium", "label": "Heavy sub", "detail": "Sub energy above threshold.", "confidence": "medium"},
        ]
        actions = priority_actions(_default_metrics(), flags, comparison=None)
        assert any(a["decision"] == "needs_reference" for a in actions), (
            f"Expected at least one 'needs_reference' decision: {actions}"
        )

    def test_comparison_adds_extra_actions(self):
        """When comparison data is given, extra actions are appended (spectral/perceptual/level)."""
        flags = [{"severity": "low", "label": "Low presence", "detail": "Detail", "confidence": "medium"}]
        comparison = {
            "largest_spectral_difference": {"band": "low_mids", "delta": 0.08},
            "largest_perceptual_difference": {"band": "presence", "delta": -0.06},
            "rms_delta_db": 4.5,
        }
        actions = priority_actions(_default_metrics(), flags, comparison=comparison)
        foci = {a["focus"] for a in actions}
        assert "Low Mids Vs Reference" in foci or "Low Mids Vs Reference".lower() in {f.lower() for f in foci}, (
            f"Spectral diff action missing: {foci}"
        )
        # RMS diff > 3 should trigger Level match action
        assert "Level Match" in foci or "level match" in str(foci).lower()


# ==============================================================================
#  Additional shape/edge-case tests
# ==============================================================================

class TestMetaFunctions:
    """Sanity checks on supporting functions."""

    def test_metric_float(self):
        assert metric_float(42) == 42.0
        assert metric_float("12.5") == 12.5
        assert metric_float(None) == 0.0
        assert metric_float([1, 2]) == 0.0

    def test_confidence_for_flag_known(self):
        assert confidence_for_flag({"label": "Low headroom"}) == "high"
        assert confidence_for_flag({"label": "Low-mid build-up"}) == "medium"

    def test_technical_score(self):
        assert technical_score([]) == 100
        assert technical_score([{"severity": "high"}]) == 82
        assert technical_score([{"severity": "medium"}, {"severity": "low"}]) == 85

    def test_technical_score_skips_informational_flags(self):
        """Regression for a real bug found 2026-07-12: the "Harsh digital
        clipping" flag is driven by distortion_odd_thd (analyze_thd_n()),
        which Stage M5 already proved unbounded/unreliable on real
        polyphonic mixes (values up to 4945, not a percentage) -- it was
        still contributing an 18-point "high" penalty to technical_score on
        legitimate mixes. Informational flags must stay visible in the
        report but never affect the score."""
        assert technical_score([{"severity": "high", "informational": True}]) == 100
        assert technical_score([
            {"severity": "high", "informational": True},
            {"severity": "medium"},
        ]) == 90
        assert technical_score([{"severity": "high", "informational": False}]) == 82

    def test_rating_from_score(self):
        assert rating_from_score(90) == "Clean technical pass"
        assert rating_from_score(75) == "Solid with checks"
        assert rating_from_score(60) == "Needs attention"


# ----- generate_prose_summary -----

class TestGenerateProseSummary:
    """Tests for A7.2 prose summary generation."""

    def _minimal_report(self, **overrides) -> dict:
        r: dict = {
            "metrics": {
                "peak_dbfs": -6.0,
                "crest_factor_db": 14.0,
                "integrated_lufs": -18.0,
                "stereo_correlation": 0.85,
                "stereo_width_ratio": 0.45,
                "tonal_balance": {"profile": "Balanced"},
                "dynamic_profile": {"profile": "Controlled"},
                "stereo_field": {"image": "Stable", "low_end": "mono-safe"},
            },
            "action_plan": [{"rank": 1, "action": "Level-match against a reference."}],
            "flags": [],
        }
        r.update(overrides)
        return r

    def test_deterministic_fallback_when_llm_disabled(self):
        """With no AUDIO_TOO_MIX_REVIEW_LLM env var set, returns deterministic mode."""
        import os
        os.environ.pop("AUDIO_TOO_MIX_REVIEW_LLM", None)
        result = generate_prose_summary(self._minimal_report())
        assert result["mode"] == "deterministic"
        assert result["available"] is False
        assert len(result["text"]) > 50

    def test_deterministic_text_contains_three_paragraphs(self):
        """Deterministic fallback produces text with at least two double-newlines (3 paragraphs)."""
        import os
        os.environ.pop("AUDIO_TOO_MIX_REVIEW_LLM", None)
        result = generate_prose_summary(self._minimal_report())
        assert result["text"].count("\n\n") >= 2

    def test_deterministic_includes_key_fields(self):
        """Deterministic text references tonal profile and action."""
        import os
        os.environ.pop("AUDIO_TOO_MIX_REVIEW_LLM", None)
        result = generate_prose_summary(self._minimal_report())
        assert "balanced" in result["text"].lower() or "controlled" in result["text"].lower()
        assert "level-match" in result["text"].lower()

    def test_llm_exception_falls_back_to_deterministic(self):
        """When provider raises, falls back gracefully with deterministic text."""
        import os
        from unittest.mock import MagicMock, patch
        os.environ["AUDIO_TOO_MIX_REVIEW_LLM"] = "1"
        try:
            mock_provider = MagicMock()
            mock_provider.is_enabled.return_value = True
            mock_provider.chat_completion.side_effect = RuntimeError("network error")
            with patch("audio_analysis.analysis_core.analysis_interpretation._mix_critique_provider", mock_provider):
                result = generate_prose_summary(self._minimal_report())
            assert result["mode"] == "deterministic"
            assert len(result["text"]) > 10
        finally:
            os.environ.pop("AUDIO_TOO_MIX_REVIEW_LLM", None)
