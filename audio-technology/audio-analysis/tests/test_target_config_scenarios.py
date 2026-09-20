"""Tests for target_config.py — mix goal definitions and validation.

Covers:
- normalize_mix_goal()              — 4 tests
- mix_goal_info()                   — 2 tests
- normalize_target_check()          — 4 tests
- validated_goal_targets()          — 3 tests
- load_goal_targets()               — 2 tests
- get_mix_review_targets()          — 1 test
- save_mix_review_targets()         — 1 test
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from audio_analysis.analysis_core.target_config import (
    normalize_mix_goal,
    mix_goal_info,
    normalize_target_check,
    validated_goal_targets,
    load_goal_targets,
    get_mix_review_targets,
    save_mix_review_targets,
    MIX_GOALS,
    GOAL_TARGETS,
)


# ==============================================================================
#  normalize_mix_goal
# ==============================================================================

class TestNormalizeMixGoal:

    def test_valid_goal(self):
        assert normalize_mix_goal("premaster") == "premaster"
        assert normalize_mix_goal("club") == "club"

    def test_alias(self):
        assert normalize_mix_goal("electronic") == "club"
        assert normalize_mix_goal("pop") == "pop_vocal"
        assert normalize_mix_goal("rap") == "rap_vocal"
        assert normalize_mix_goal("dialogue") == "podcast"
        assert normalize_mix_goal("game") == "game_audio"

    def test_normalizes_format(self):
        assert normalize_mix_goal(" Pop vocal ") == "pop_vocal"
        assert normalize_mix_goal("CLUB") == "club"

    def test_fallback_to_default(self):
        assert normalize_mix_goal("invalid_goal_xyz") == "premaster"

    def test_empty(self):
        assert normalize_mix_goal("") == "premaster"


# ==============================================================================
#  mix_goal_info
# ==============================================================================

class TestMixGoalInfo:

    def test_returns_valid_goal_data(self):
        info = mix_goal_info("club")
        assert info["key"] == "club"
        assert "label" in info
        assert "description" in info
        assert "target" in info

    def test_returns_default_for_invalid(self):
        info = mix_goal_info("nonsense")
        assert info["key"] == "premaster"


# ==============================================================================
#  normalize_target_check
# ==============================================================================

class TestNormalizeTargetCheck:

    def test_valid_metric_check(self):
        result = normalize_target_check({
            "label": "Peak headroom",
            "metric": "peak_dbfs",
            "max": -1.0,
            "target": "Peak at or below -1 dBFS",
            "education": "Headroom is needed.",
        })
        assert result is not None
        assert result["metric"] == "peak_dbfs"
        assert result["max"] == -1.0

    def test_valid_path_check(self):
        result = normalize_target_check({
            "label": "Low-end proportion",
            "path": ["tonal_balance", "low_end_share"],
            "max": 0.52,
            "target": "Low end below 52%",
            "education": "Too much low end.",
        })
        assert result is not None
        assert result["path"] == ["tonal_balance", "low_end_share"]

    def test_invalid_no_metric_or_path(self):
        assert normalize_target_check({"label": "Missing"}) is None

    def test_invalid_empty_label(self):
        assert normalize_target_check({"label": "  ", "metric": "peak_dbfs"}) is None

    def test_non_dict(self):
        assert normalize_target_check("not a dict") is None

    def test_string_path(self):
        result = normalize_target_check({
            "label": "Test", "path": "tonal_balance.low_end_share", "target": "x",
        })
        assert result is not None
        assert result["path"] == ["tonal_balance", "low_end_share"]

    def test_invalid_min_value(self):
        result = normalize_target_check({
            "label": "Test", "metric": "peak_dbfs", "min": "not-a-number",
        })
        assert result is None


# ==============================================================================
#  validated_goal_targets
# ==============================================================================

class TestValidatedGoalTargets:

    def test_returns_defaults_when_empty(self):
        targets = validated_goal_targets({})
        assert "premaster" in targets
        assert "club" in targets
        assert "master" in targets
        assert len(targets["premaster"]["checks"]) > 0

    def test_overrides_with_custom(self):
        raw = {
            "goals": {
                "premaster": {
                    "summary": "Custom premaster checks",
                    "checks": [
                        {"label": "Custom peak", "metric": "peak_dbfs", "max": -2.0, "target": "Custom", "education": "Edu"},
                    ],
                },
            },
        }
        targets = validated_goal_targets(raw)
        assert targets["premaster"]["summary"] == "Custom premaster checks"
        assert targets["premaster"]["checks"][0]["max"] == -2.0

    def test_rejects_invalid_checks(self):
        raw = {
            "goals": {
                "premaster": {
                    "checks": [
                        {"label": "Bad check", "metric": "peak_dbfs", "min": "invalid"},
                    ],
                },
            },
        }
        targets = validated_goal_targets(raw)
        # Invalid check should be filtered out; fall back to original checks
        assert len(targets["premaster"]["checks"]) >= 4  # original checks preserved


# ==============================================================================
#  load_goal_targets
# ==============================================================================

class TestLoadGoalTargets:

    def test_missing_file_returns_defaults(self):
        path = Path("/nonexistent/path/goals.json")
        result = load_goal_targets(path)
        assert "premaster" in result

    def test_valid_file_loaded(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "goals": {
                    "premaster": {
                        "summary": "File loaded",
                        "checks": [
                            {"label": "Loaded check", "metric": "peak_dbfs", "max": -1.0, "target": "T", "education": "E"},
                        ],
                    },
                },
            }, f)
            path = Path(f.name)

        try:
            result = load_goal_targets(path)
            assert result["premaster"]["summary"] == "File loaded"
        finally:
            path.unlink(missing_ok=True)


# ==============================================================================
#  get_mix_review_targets
# ==============================================================================

class TestGetMixReviewTargets:

    def test_loads_targets(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "goals": {
                    "premaster": {
                        "summary": "Direct load",
                        "checks": [
                            {"label": "L", "metric": "peak_dbfs", "max": -1.0, "target": "T", "education": "E"},
                        ],
                    },
                },
            }, f)
            path = Path(f.name)

        try:
            result = get_mix_review_targets(path)
            assert "goals" in result
            assert result["goals"]["premaster"]["summary"] == "Direct load"
        finally:
            path.unlink(missing_ok=True)


# ==============================================================================
#  save_mix_review_targets
# ==============================================================================

class TestSaveMixReviewTargets:

    def test_saves_and_loads_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "mix_targets.json"
            data = {
                "goals": {
                    "premaster": {
                        "summary": "Saved",
                        "checks": [
                            {"label": "Saved check", "metric": "peak_dbfs", "max": -1.0, "target": "T", "education": "E"},
                        ],
                    },
                },
            }
            result = save_mix_review_targets(data, path=path)
            assert result["ok"] is True

            # Reload
            with open(path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            assert saved["goals"]["premaster"]["summary"] == "Saved"


# ==============================================================================
#  MIX_GOALS completeness
# ==============================================================================

class TestMixGoalsCompleteness:
    """Structural tests for the MIX_GOALS and GOAL_TARGETS constants."""

    def test_all_goals_have_targets(self):
        """Every MIX_GOALS key has a corresponding GOAL_TARGETS entry."""
        for key in MIX_GOALS:
            assert key in GOAL_TARGETS, f"Missing GOAL_TARGETS for {key}"

    def test_all_checks_have_required_keys(self):
        """Every check in GOAL_TARGETS has label, metric or path, target, education."""
        for goal_key, targets in GOAL_TARGETS.items():
            for check in targets.get("checks", []):
                assert "label" in check, f"Check in {goal_key} missing label"
                assert ("metric" in check) or ("path" in check), f"Check '{check.get('label')}' in {goal_key} missing metric or path"
                assert "target" in check, f"Check '{check.get('label')}' in {goal_key} missing target"
                assert "education" in check, f"Check '{check.get('label')}' in {goal_key} missing education"
