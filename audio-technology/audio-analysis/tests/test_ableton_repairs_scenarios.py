"""Tests for ableton_repairs.py — Ableton repair template lookups.

Covers:
- ABLETON_REPAIR_LIBRARY            — 1 test (completeness check)
- ableton_repair_templates()         — 4 tests
"""

from __future__ import annotations


from audio_analysis.integration.ableton_repairs import (
    ABLETON_REPAIR_LIBRARY,
    ableton_repair_templates,
)


class TestAbletonRepairLibrary:

    def test_key_structure(self):
        """Every template has required keys."""
        for label, template in ABLETON_REPAIR_LIBRARY.items():
            for key in ("device_chain", "move", "target", "check"):
                assert key in template, f"Template '{label}' missing '{key}'"
                assert template[key], f"Template '{label}' has empty '{key}'"

    def test_minimum_count(self):
        """At least 12 repair templates defined."""
        assert len(ABLETON_REPAIR_LIBRARY) >= 12


class TestAbletonRepairTemplates:

    def test_known_flag_returns_repair(self):
        """Known flag → returns matching template."""
        flags = [{"label": "Low dynamics", "severity": "high"}]
        repairs = ableton_repair_templates(flags)
        assert len(repairs) == 1
        assert repairs[0]["flag"] == "Low dynamics"
        assert repairs[0]["severity"] == "high"

    def test_unknown_flag_falls_back(self):
        """Unknown flag → fallback reference template."""
        flags = [{"label": "Unknown issue", "severity": "high"}]
        repairs = ableton_repair_templates(flags)
        assert len(repairs) == 1
        assert repairs[0]["flag"] == "Reference listen"

    def test_empty_flags_fallback(self):
        """No flags → fallback template."""
        repairs = ableton_repair_templates([])
        assert len(repairs) == 1
        assert repairs[0]["flag"] == "Reference listen"

    def test_severity_ordering(self):
        """High severity flags come first."""
        flags = [
            {"label": "Low dynamics", "severity": "low"},
            {"label": "Heavy sub", "severity": "high"},
        ]
        repairs = ableton_repair_templates(flags, limit=2)
        assert repairs[0]["flag"] == "Heavy sub"
        assert repairs[1]["flag"] == "Low dynamics"

    def test_limit_respected(self):
        flags = [
            {"label": "Low dynamics", "severity": "high"},
            {"label": "Heavy sub", "severity": "high"},
            {"label": "Clipping risk", "severity": "high"},
        ]
        repairs = ableton_repair_templates(flags, limit=2)
        assert len(repairs) == 2

    def test_metrics_mentioned_in_fallback(self):
        """Fallback mentions the technical score."""
        flags = [{"label": "Unknown", "severity": "high"}]
        repairs = ableton_repair_templates(flags, metrics={"technical_score": 75})
        assert "75" in repairs[0].get("target", "")
