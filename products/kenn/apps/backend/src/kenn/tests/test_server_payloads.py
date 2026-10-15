"""Uploaded chat history keeps explicit intent when signal evidence is unqualified."""

from copy import deepcopy

import pytest

from kenn import server_payloads
from kenn.core.evidence import UPLOADED_SIGNAL_LIMITATION


def _handoff():
    return {
        "schema": "kenn_mix_review_handoff.v1",
        "title": "Producer's mix",
        "mix_goal_label": "Warm club mix",
        "session_goal": "Keep the vocal forward",
        "context": "Cached signal summary",
        "context_lines": ["Cached signal context", "Cached signal advice"],
        "metrics": {"rms_dbfs": -18.0, "peak_dbfs": -1.0},
        "flags": [{"severity": "warn", "label": "Peak", "detail": "Cached peak warning"}],
        "priority_actions": [{"rank": 1, "action": "Cached gain reduction"}],
        "judgment": {"technical_rating": "Excellent"},
        "technical_metrics": {"integrated_lufs": -12.0},
        "section_highlights": {"chorus": "Cached section imbalance"},
        "ableton_repair_templates": [{"device_chain": "EQ Eight", "move": "Cached EQ repair"}],
        "revision_steps": [{"action": "Cached revision move"}],
        "reference": {"title": "Cached reference analysis"},
        "reference_comparison": {"eq_bands": [{"freq": 100.0, "gain": -2.0}]},
        "mix_style": {"genre": {"genre_name": "House", "confidence": 0.9}},
        "leave_alone": ["Cached stereo judgment"],
        "previous_version": {"title": "Cached previous analysis"},
        "version_comparison": {"summary": "Cached improvement"},
        "version_advice": {"summary": "Cached revision advice"},
        "revision_impact": {"summary": "Cached impact"},
        "next_revision_plan": {"focus": "Cached plan", "steps": [{"action": "Cached step"}]},
    }


@pytest.mark.parametrize("metrics", [
    None, {}, [], {"rms_dbfs": None}, {"rms_dbfs": "-18"},
    {"rms_dbfs": True}, {"rms_dbfs": False}, {"rms_dbfs": float("nan")},
    {"rms_dbfs": float("inf")}, {"rms_dbfs": float("-inf")},
    {"rms_dbfs": 10**400}, {"rms_dbfs": -100.0}, {"rms_dbfs": -60.0},
])
def test_quiet_uploaded_handoff_rebuilds_history_without_cached_signal_claims(metrics, monkeypatch):
    # Cached prose and nested repairs used to bypass the typed measurement gate.
    context = _handoff()
    context["metrics"] = metrics
    before = deepcopy(context)
    monkeypatch.setattr(server_payloads, "_retrieve_approved_genre_evidence", lambda: pytest.fail("Quiet genre was evaluated"))

    turn = server_payloads.mix_review_context_turn(context)

    assert turn == {"role": "user", "content": "\n".join([
        "Mix Review Lab context for Producer's mix.",
        UPLOADED_SIGNAL_LIMITATION,
        "Selected mix target: Warm club mix",
        "Session goal: Keep the vocal forward",
    ])}
    assert context == before


def test_quiet_uploaded_handoff_bounds_identity_and_preserves_nested_explicit_goals():
    context = {
        "schema": "kenn_mix_review_handoff.v1",
        "title": "T" * 200,
        "session_context": {"mix_goal_label": "M" * 200, "session_goal": "G" * 400},
        "context": "Cached summary must not appear",
    }
    turn = server_payloads.mix_review_context_turn(context)
    assert turn["content"].splitlines() == [
        f"Mix Review Lab context for {'T' * 120}.",
        UPLOADED_SIGNAL_LIMITATION,
        f"Selected mix target: {'M' * 160}",
        f"Session goal: {'G' * 300}",
    ]


@pytest.mark.parametrize("rms_dbfs", [-59.9, -18.0])
def test_active_uploaded_handoff_retains_structured_narrative_and_reference_moves(rms_dbfs, monkeypatch):
    context = _handoff()
    context["metrics"]["rms_dbfs"] = rms_dbfs
    before = deepcopy(context)
    monkeypatch.setattr(server_payloads, "_retrieve_approved_genre_evidence", lambda: "genre-source@index:fixture")

    content = server_payloads.mix_review_context_turn(context)["content"]

    for marker in (
        "Cached signal context", "Cached signal advice", "Selected mix target: Warm club mix",
        "Session goal: Keep the vocal forward", f"rms dbfs={rms_dbfs}", "Cached peak warning",
        "Cached gain reduction", "Excellent", "integrated_lufs", "Cached section imbalance",
        "Cached EQ repair", "Cached revision move", "Cached reference analysis",
        "Reduce 2.0 dB around 100 Hz", "House-leaning", "Cached stereo judgment",
        "Cached previous analysis", "Cached improvement", "Cached revision advice",
        "Cached impact", "Cached plan", "Cached step",
    ):
        assert marker in content
    assert UPLOADED_SIGNAL_LIMITATION not in content
    assert context == before


def test_active_uploaded_handoff_keeps_freeform_summary_when_context_lines_are_absent():
    context = _handoff()
    del context["context_lines"]
    assert "Cached signal summary" in server_payloads.mix_review_context_turn(context)["content"]
