"""Tests for session_report.py — concise engineer-facing report builder.

Covers:
- build_session_report()         — 5 scenario tests
"""

from __future__ import annotations


from audio_analysis.integration.session_report import build_session_report


def _make_report(overrides: dict | None = None) -> dict:
    base = {
        "title": "My Mix",
        "version_label": "v2",
        "summary": "A solid pop mix with some low-end buildup.",
        "metrics": {
            "filename": "my_mix.wav",
            "technical_score": 78,
            "technical_rating": "Good",
            "mix_goal": {"key": "premaster", "label": "Premaster"},
        },
        "action_plan": [
            {"focus": "low_mids", "action": "Cut 3 dB at 250 Hz", "reason": "Muddy"},
            {"focus": "stereo_width", "action": "Widen by 5%", "reason": "Narrow"},
        ],
        "ableton_repair_templates": [
            {"device_chain": "EQ Eight, Utility", "move": "Cut 250 Hz", "target": "Mids", "check": "A/B bypass"},
        ],
        "flags": [
            {"label": "low_muds"},
        ],
        "comparison_advice": ["The low end is louder than the reference."],
        "version_advice": ["Improved clarity from v1."],
    }
    if overrides:
        for k, v in overrides.items():
            base[k] = v
    return base


class TestBuildSessionReport:

    def test_basic_structure(self):
        """Report has all required top-level keys."""
        report = _make_report()
        result = build_session_report(report)
        assert result["schema"] == "audio_too.session_report.v1"
        assert "title" in result
        assert "mix_target" in result
        assert "summary" in result
        assert "fix_first" in result
        assert "fix_next" in result
        assert "leave_alone" in result
        assert "v2_export_checklist" in result
        assert "client_summary" in result
        assert "kenn_memory_lines" in result

    def test_fix_first_from_actions(self):
        """fix_first comes from the first action."""
        report = _make_report()
        result = build_session_report(report)
        assert "low_mids" in result["fix_first"]

    def test_leave_alone_fallback(self):
        """No lesson_cards or protect → fallback text."""
        report = _make_report({"lesson_cards": [], "closed_loop_action_plan": {}})
        result = build_session_report(report)
        assert len(result["leave_alone"]) > 0

    def test_version_label_preserved(self):
        report = _make_report({"version_label": "v3"})
        result = build_session_report(report)
        assert result["version_label"] == "v3"

    def test_unknown_report(self):
        """Missing fields handled gracefully."""
        result = build_session_report({})
        assert result["schema"] == "audio_too.session_report.v1"
        assert result["title"] is not None

    def test_kenn_memory_lines(self):
        """Memory lines include track, target, summary, fix info."""
        report = _make_report()
        result = build_session_report(report)
        lines = result["kenn_memory_lines"]
        assert any("My Mix" in line for line in lines)
        assert any("Premaster" in line or "premaster" in line for line in lines)
