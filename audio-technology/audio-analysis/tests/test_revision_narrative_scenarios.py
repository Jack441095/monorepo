"""Tests for revision_narrative.py — human-readable diff between mix versions.

Covers:
- build_revision_narrative()        — 5 scenario tests
- format_narrative_for_agent()      — 1 test
- version_diff()                    — 3 tests
- Helper extraction functions       — via scenario outputs
"""

from __future__ import annotations


from audio_analysis.mix_review.revision_narrative import build_revision_narrative, format_narrative_for_agent, version_diff


# ==============================================================================
#  Base fixtures
# ==============================================================================

def _make_report(overrides: dict | None = None) -> dict:
    """Helper: builds a minimal report with default values."""
    base = {
        "version_label": "v2",
        "metrics": {
            "technical_score": 75.0,
            "crest_factor_db": 14.0,
            "rms_dbfs_estimate": -18.0,
            "stereo_width_ratio": 0.45,
            "stereo_correlation": 0.82,
            "peak_dbfs": -3.2,
            "mix_goal": {"key": "premaster", "label": "Premaster"},
            "tonal_balance": {"profile": "Balanced"},
            "dynamic_profile": {"profile": "Controlled"},
            "stereo_field": {"image": "Stable"},
            "perceptual_summary": {"dominant_band": "mids"},
        },
        "flags": [],
    }
    if overrides:
        # Deep merge for nested dicts
        for k, v in overrides.items():
            if isinstance(v, dict) and isinstance(base.get(k), dict):
                base[k].update(v)
            else:
                base[k] = v
    return base


# ==============================================================================
#  build_revision_narrative
# ==============================================================================

class TestBuildRevisionNarrative:

    def test_no_previous_report(self):
        """No previous report → initial verdict."""
        report = _make_report()
        result = build_revision_narrative(report, None)
        assert result["verdict"] == "initial"
        assert "no previous version" in result["narrative"].lower()

    def test_improved_score(self):
        """Score improved by > 2 points → positive narrative."""
        current = _make_report({"metrics": {"technical_score": 85.0}})
        previous = _make_report({"metrics": {"technical_score": 70.0}, "version_label": "v1"})
        result = build_revision_narrative(current, previous)
        assert result["score_delta"] == 15.0
        assert result["verdict"] == "mixed"  # default, no revision_impact provided
        assert "improved" in result["narrative"].lower()

    def test_dropped_score(self):
        """Score dropped by > 2 points → negative narrative."""
        current = _make_report({"metrics": {"technical_score": 55.0}})
        previous = _make_report({"metrics": {"technical_score": 80.0}, "version_label": "v1"})
        result = build_revision_narrative(current, previous)
        assert result["score_delta"] == -25.0
        assert "dropped" in result["narrative"].lower()

    def test_cleared_flags(self):
        """Flags removed → 'cleared' section in narrative."""
        current = _make_report({"flags": []})
        previous = _make_report({
            "flags": [
                {"label": "low_dynamics"},
                {"label": "heavy_compression"},
            ],
            "version_label": "v1",
        })
        result = build_revision_narrative(current, previous)
        assert "low_dynamics" in result["cleared"]
        assert "heavy_compression" in result["cleared"]
        assert "Cleared" in result["narrative"]

    def test_new_flags(self):
        """New flags → 'New' section in narrative."""
        current = _make_report({
            "flags": [
                {"label": "sub_too_loud"},
                {"label": "clipping_risk"},
            ],
        })
        previous = _make_report({"flags": [{"label": "low_dynamics"}], "version_label": "v1"})
        result = build_revision_narrative(current, previous)
        assert "sub_too_loud" in result["new_flags"]
        assert "clipping_risk" in result["new_flags"]
        assert "low_dynamics" not in result["new_flags"]

    def test_tonal_profile_shift(self):
        """Tonal profile changed → mentioned in narrative."""
        current = _make_report({"metrics": {"tonal_balance": {"profile": "Bright"}}})
        previous = _make_report({"metrics": {"tonal_balance": {"profile": "Balanced"}}, "version_label": "v1"})
        result = build_revision_narrative(current, previous)
        assert "Tonal profile" in result["narrative"]
        assert "Balanced" in result["narrative"]
        assert "Bright" in result["narrative"]

    def test_dominant_band_shift(self):
        """Dominant band changed → mentioned."""
        current = _make_report({"metrics": {"perceptual_summary": {"dominant_band": "bass"}}})
        previous = _make_report({"metrics": {"perceptual_summary": {"dominant_band": "mids"}}, "version_label": "v1"})
        result = build_revision_narrative(current, previous)
        assert "dominant band" in result["narrative"].lower()

    def test_metric_deltas(self):
        """Significant metric movements → included in narrative."""
        current = _make_report({"metrics": {"crest_factor_db": 18.0, "rms_dbfs_estimate": -12.0}})
        previous = _make_report({"metrics": {"crest_factor_db": 12.0, "rms_dbfs_estimate": -20.0}, "version_label": "v1"})
        result = build_revision_narrative(current, previous)
        assert "crest" in result.get("deltas", {})
        assert "rms" in result.get("deltas", {})
        narrative = result.get("narrative", "")
        assert "crest" in narrative.lower() or "rms" in narrative.lower() or "Metric movements" in narrative

    def test_unchanged_flags(self):
        """Flags that persist → 'Still present' section."""
        current = _make_report({"flags": [{"label": "needs_sub_tuning"}]})
        previous = _make_report({"flags": [{"label": "needs_sub_tuning"}], "version_label": "v1"})
        result = build_revision_narrative(current, previous)
        assert "needs_sub_tuning" in result["unchanged_flags"]
        assert "Still present" in result["narrative"]

    def test_version_comparison_used(self):
        """Pre-computed version_comparison contributes deltas."""
        current = _make_report()
        previous = _make_report({"version_label": "v1"})
        comp = {"rms_delta_db": 3.5, "crest_delta_db": 2.1}
        result = build_revision_narrative(current, previous, version_comparison=comp)
        assert result["deltas"].get("rms") == 3.5
        assert result["deltas"].get("crest") == 2.1

    def test_revision_impact_verdict(self):
        """revision_impact verdict passed through."""
        current = _make_report({"metrics": {"technical_score": 85.0}})
        previous = _make_report({"metrics": {"technical_score": 70.0}, "version_label": "v1"})
        impact = {"verdict": "improved"}
        result = build_revision_narrative(current, previous, revision_impact=impact)
        assert result["verdict"] == "improved"

    def test_action_summary_with_new_flags(self):
        """New flags drive the action summary."""
        current = _make_report({"flags": [{"label": "clipping_risk"}]})
        previous = _make_report({"version_label": "v1"})
        result = build_revision_narrative(current, previous)
        assert "Address new flag" in result.get("action_summary", "")
        assert "clipping_risk" in result["action_summary"]

    def test_narrative_line(self):
        """narrative_line is a compact single-line string."""
        current = _make_report({"flags": [{"label": "clipping_risk"}], "version_label": "v2"})
        previous = _make_report({"version_label": "v1"})
        result = build_revision_narrative(current, previous)
        line = result.get("narrative_line", "")
        assert "v2:" in line
        assert len(line) > 0


# ==============================================================================
#  format_narrative_for_agent
# ==============================================================================

class TestFormatNarrativeForAgent:
    def test_combines_narrative_and_action(self):
        narrative = {
            "narrative": "Score improved by 10 points.\nCleared: loudness_issue.",
            "action_summary": "Good progress.",
        }
        text = format_narrative_for_agent(narrative)
        assert "Score improved" in text
        assert "Good progress." in text


# ==============================================================================
#  version_diff
# ==============================================================================

class TestVersionDiff:

    def test_no_previous(self):
        current = _make_report({"version_label": "v1"})
        result = version_diff(current, None)
        assert result["ok"] is True
        assert result["version_label_a"] == "initial"

    def test_two_versions(self):
        current = _make_report({"version_label": "v2", "flags": []})
        previous = _make_report({"version_label": "v1", "flags": [{"label": "low_dynamics"}]})
        result = version_diff(current, previous)
        assert result["ok"] is True
        assert result["version_label_a"] == "v1"
        assert result["version_label_b"] == "v2"
        assert "low_dynamics" in result["cleared"]

    def test_version_labels_use_fallbacks(self):
        current = _make_report()
        current.pop("version_label", None)
        previous = _make_report()
        previous.pop("version_label", None)
        result = version_diff(current, previous)
        assert result["version_label_a"] == "previous"
        assert result["version_label_b"] == "current"
