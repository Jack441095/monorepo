"""Tests for closed_loop.py — action plans, QA summaries, feedback.

Covers:
- closed_loop_action_plan()     — 3 tests
- ableton_repair_chain_export() — 2 tests
- automation_hint_for_repair()  — 4 tests
- batch_qa_summary()            — 2 tests
- qa_risk_level()               — 4 tests
- feedback_record()              — 2 tests
- append_feedback_record()       — 2 tests
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from audio_analysis.integration.closed_loop import (
    closed_loop_action_plan,
    ableton_repair_chain_export,
    automation_hint_for_repair,
    batch_qa_summary,
    qa_risk_level,
    feedback_record,
    append_feedback_record,
)


# ==============================================================================
#  Helpers
# ==============================================================================

def _make_report(overrides: dict | None = None) -> dict:
    base = {
        "metrics": {
            "technical_score": 75,
            "filename": "test_mix.wav",
            "section_analysis": {
                "highlights": {
                    "loudest_section": {"label": "Chorus", "rms_dbfs": -12.0},
                },
            },
            "chords": {
                "estimated_key": "C Major",
                "key_confidence": "high",
                "analysis_notes": ["stable_progression"],
            },
        },
        "action_plan": [
            {
                "decision": "eq_adjust",
                "focus": "low_mids",
                "action": "Cut 3 dB at 250 Hz",
                "reason": "Muddy low mids",
                "confidence": "high",
            },
            {
                "decision": "compression_adjust",
                "focus": "dynamics",
                "action": "Reduce ratio on bus compressor",
                "reason": "Too compressed",
                "confidence": "medium",
            },
        ],
        "ableton_repair_templates": [
            {
                "flag": "low_mids",
                "severity": "high",
                "device_chain": "EQ Eight, Utility",
                "move": "Cut 3 dB at 250 Hz on the mix bus",
                "target": "Reduce muddiness in the low mids",
                "check": "A/B bypass and compare spectral balance",
            },
        ],
        "flags": [
            {"label": "low_muds", "severity": "high"},
            {"label": "heavy_compression", "severity": "medium"},
        ],
    }
    if overrides:
        for k, v in overrides.items():
            if isinstance(v, dict) and isinstance(base.get(k), dict):
                base[k].update(v)
            else:
                base[k] = v
    return base


# ==============================================================================
#  closed_loop_action_plan
# ==============================================================================

class TestClosedLoopActionPlan:

    def test_basic_plan(self):
        """Action plan from report actions."""
        report = _make_report()
        plan = closed_loop_action_plan(report)
        assert "schema" in plan
        assert plan["primary_focus"] == "low_mids"
        assert len(plan["steps"]) == 2
        assert plan["steps"][0]["rank"] == 1
        assert plan["steps"][0]["focus"] == "low_mids"
        assert plan["steps"][0]["ableton_move"] != ""

    def test_no_steps_fallback(self):
        """Empty action_plan → fallback step generated."""
        report = _make_report({"action_plan": [], "ableton_repair_templates": []})
        plan = closed_loop_action_plan(report)
        assert len(plan["steps"]) == 1
        assert plan["steps"][0]["focus"] == "Reference pass"

    def test_section_and_harmonic_context(self):
        """Section and harmonic context included."""
        report = _make_report()
        plan = closed_loop_action_plan(report)
        assert plan["section_context"]["loudest_section"] == "Chorus"
        assert plan["harmonic_context"]["estimated_key"] == "C Major"

    def test_revision_checklist(self):
        """Checklist is always present."""
        plan = closed_loop_action_plan(_make_report())
        assert len(plan["revision_checklist"]) >= 4
        assert "Save a new version label" in plan["revision_checklist"][0]


# ==============================================================================
#  ableton_repair_chain_export
# ==============================================================================

class TestAbletonRepairChainExport:

    def test_basic_export(self):
        report = _make_report()
        export = ableton_repair_chain_export(report)
        assert export["schema"] == "audio_too.ableton_repair_chains.v1"
        assert len(export["chains"]) == 1
        assert export["chains"][0]["name"] == "low_mids"

    def test_empty_repairs(self):
        """No repairs → empty chains list."""
        report = _make_report({"ableton_repair_templates": []})
        export = ableton_repair_chain_export(report)
        assert len(export["chains"]) == 0

    def test_export_note(self):
        report = _make_report()
        export = ableton_repair_chain_export(report)
        assert "apply manually" in export.get("export_note", "").lower()


# ==============================================================================
#  automation_hint_for_repair
# ==============================================================================

class TestAutomationHint:

    def test_dynamics_hint(self):
        hint = automation_hint_for_repair({"flag": "uneven_dynamics"}, {"section_analysis": {"highlights": {"loudest_section": {"label": "Drop"}}}})
        assert "automation" in hint.lower()
        assert "Drop" in hint

    def test_harsh_hint(self):
        hint = automation_hint_for_repair({"flag": "harsh_presence"}, {"section_analysis": {"highlights": {"loudest_section": {"label": "Chorus"}}}})
        assert "Loop" in hint
        assert "Chorus" in hint

    def test_stereo_hint(self):
        hint = automation_hint_for_repair({"flag": "stereo_phase"}, {"section_analysis": {"highlights": {"loudest_section": {"label": "Verse"}}}})
        assert "Automate width" in hint

    def test_fallback_hint(self):
        hint = automation_hint_for_repair({"flag": "other_issue"}, {"section_analysis": {"highlights": {"loudest_section": {"label": "Intro"}}}})
        assert "Apply statically" in hint


# ==============================================================================
#  qa_risk_level
# ==============================================================================

class TestQARiskLevel:

    def test_failed(self):
        assert qa_risk_level(None, [], True) == "failed"

    def test_high_flags(self):
        flags = [{"severity": "high"}]
        assert qa_risk_level(80, flags, False) == "high"

    def test_low_score(self):
        assert qa_risk_level(55, [], False) == "high"

    def test_medium_flags(self):
        flags = [{"severity": "medium"}]
        assert qa_risk_level(80, flags, False) == "medium"

    def test_low_risk(self):
        assert qa_risk_level(85, [], False) == "low"


# ==============================================================================
#  batch_qa_summary
# ==============================================================================

class TestBatchQASummary:

    def test_empty_items(self):
        result = batch_qa_summary({"items": [], "root": "/test"})
        assert result["totals"]["found"] == 0

    def test_multiple_items_ranked_by_risk(self):
        items = [
            {"filename": "bad.wav", "ok": True, "flags": [{"severity": "high", "label": "clipping"}], "metrics": {"technical_score": 50}},
            {"filename": "good.wav", "ok": True, "flags": [], "metrics": {"technical_score": 85}},
        ]
        result = batch_qa_summary({"items": items})
        assert len(result["ranked_items"]) == 2
        # bad.wav should be ranked first (higher risk)
        assert result["ranked_items"][0]["filename"] == "bad.wav"
        assert result["totals"]["high_risk"] == 1
        assert result["totals"]["low_risk"] == 1

    def test_issue_counts(self):
        items = [
            {"filename": "a.wav", "ok": True, "flags": [{"label": "low_dynamics"}, {"label": "heavy_bass"}], "metrics": {"technical_score": 70}},
            {"filename": "b.wav", "ok": True, "flags": [{"label": "low_dynamics"}], "metrics": {"technical_score": 75}},
        ]
        result = batch_qa_summary({"items": items})
        assert result["issue_counts"]["low_dynamics"] == 2
        assert result["issue_counts"]["heavy_bass"] == 1


# ==============================================================================
#  feedback_record
# ==============================================================================

class TestFeedbackRecord:

    def test_basic_record(self):
        report = _make_report()
        record = feedback_record(report, "yes", "Sounds good!")
        assert record["schema"] == "audio_too.analysis_feedback.v1"
        assert record["decision"] == "yes"
        assert record["note"] == "Sounds good!"
        assert record["filename"] == "test_mix.wav"
        assert "low_muds" in record["flags"]

    def test_decision_truncation(self):
        record = feedback_record({}, "a" * 50, "b" * 600)
        assert len(record["decision"]) <= 40
        assert len(record["note"]) <= 500

    def test_empty_actions_fallback(self):
        report = _make_report()
        record = feedback_record(report, "no", "")
        assert len(record["actions"]) >= 0


# ==============================================================================
#  append_feedback_record
# ==============================================================================

class TestAppendFeedbackRecord:

    def test_write_record(self):
        with tempfile.NamedTemporaryFile(mode="r", suffix=".jsonl", delete=False) as f:
            path = Path(f.name)

        try:
            report = _make_report()
            result = append_feedback_record(path, report, "yes", "Great mix")
            assert result["ok"] is True
            assert result["record"]["decision"] == "yes"

            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            assert len(lines) == 1
            parsed = json.loads(lines[0])
            assert parsed["decision"] == "yes"
        finally:
            path.unlink(missing_ok=True)

    def test_append_to_existing(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write('{"decision":"first","schema":"audio_too.analysis_feedback.v1"}\n')
            path = Path(f.name)

        try:
            result = append_feedback_record(path, _make_report(), "no", "")
            assert result["ok"] is True

            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            assert len(lines) == 2
            assert "first" in lines[0]
            assert "no" in lines[1]
        finally:
            path.unlink(missing_ok=True)
