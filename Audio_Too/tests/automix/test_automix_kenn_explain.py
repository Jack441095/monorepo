"""automix_kenn_explain.py reshapes an AutoMix render's persisted manifest
into KENN's existing kenn_mix_review_handoff.v1 schema, so a render's real
decisions_log/quality_gate become high-trust grounding evidence for a "why
did you do that" question -- reusing kenn/server_payloads.py's
mix_review_context_turn() unchanged, rather than adding new logic inside
KENN's chat orchestration.

The most important thing these tests verify is not just that the adapter's
output "looks right" structurally, but that it's actually accepted by
KENN's real, unmodified mix_review_context_turn() without raising and
without silently dropping the render's decisions -- that's the actual
contract this feature depends on.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

import automix_kenn_explain as explain

_KENN_ROOT = Path(__file__).resolve().parents[2] / "studio" / "kenn"
if str(_KENN_ROOT) not in sys.path:
    sys.path.insert(0, str(_KENN_ROOT))

from kenn.server_payloads import mix_review_context_turn  # noqa: E402


def _sample_manifest(**overrides) -> dict:
    manifest = {
        "project_id": "proj-123",
        "genre": "pop",
        "target_lufs": -14.0,
        "final_lufs": -14.05,
        "decisions_log": [
            "Iteration 1: Mix validated successfully. Score: 82/100, LUFS: -14.05.",
            "  - Clipping correction: true peak -0.7 dBTP exceeded the -1.0 dBTP ceiling; reduced bus drive by 1.0 dB.",
            "  - Master EQ correction: Cut 1.0 dB at 3500 Hz (Reduce master harshness).",
        ],
        "quality_gate": {
            "passed": True,
            "safety_passed": True,
            "hard_failures": [],
            "safety_diagnostics": [],
            "technical_score": 82,
            "minimum_score": 65,
            "advisory_score_passed": True,
        },
        "relationships": [
            {"description": "Vocal masks Guitar in the 2-4kHz range", "relationship_type": "masking"},
        ],
    }
    manifest.update(overrides)
    return manifest


def test_build_context_from_typical_manifest_has_expected_shape() -> None:
    context = explain.build_mix_review_context_from_manifest(_sample_manifest())
    assert context["schema"] == "kenn_mix_review_handoff.v1"
    assert "proj-123" in context["title"]
    assert "pop" in context["title"]
    assert any("Clipping correction" in line for line in context["context_lines"])
    assert context["metrics"]["target_lufs"] == -14.0
    assert context["metrics"]["final_lufs"] == -14.05
    assert context["technical_metrics"]["technical_score"] == 82
    assert context["judgment"]["passed"] is True
    assert context["priority_actions"][0]["action"] == "Vocal masks Guitar in the 2-4kHz range"


def test_resource_receipt_is_available_as_explicit_operational_context() -> None:
    context = explain.build_mix_review_context_from_manifest(_sample_manifest(
        resource_profile={
            "schema": "automix.resource_profile.v1",
            "stages": [{"stage": "reference_matched", "elapsed_ms": 23158.6, "peak_rss_bytes": 2254057472}],
        },
    ))

    assert any("reference matching reached 23.2s" in line for line in context["context_lines"])
    assert any("2150 MiB peak RSS" in line for line in context["context_lines"])


def test_quality_receipt_differentiates_safety_from_advisory_quality() -> None:
    context = explain.build_mix_review_context_from_manifest(_sample_manifest(
        quality_receipt={
            "schema": "automix.quality_receipt.v1",
            "verification_available": True,
            "measured_deltas": {"integrated_lufs": -3.2},
            "safety_gate": {
                "safety_passed": True,
                "advisory_score_passed": False,
                "technical_score": 40,
                "minimum_score": 65,
            },
        },
    ))

    assert any("delivery safety passed, but the advisory technical score" in line for line in context["context_lines"])
    assert context["technical_metrics"]["source_to_delivery_lufs_delta"] == -3.2


def test_mix_graph_summary_and_uncertainty_reach_kenn_context() -> None:
    context = explain.build_mix_review_context_from_manifest(_sample_manifest(
        mix_graph={
            "schema": "audio-too.mix-graph.v1",
            "nodes": [
                {"kind": "stem", "name": "kick.wav"},
                {"kind": "stem", "name": "bass.wav"},
                {"kind": "section", "name": "section-001"},
            ],
            "edges": [
                {"type": "routes_to"}, {"type": "active_in"}, {"type": "kick_bass_competition"},
            ],
            "warnings": ["Role for 'bass.wav' remains ambiguous; do not use it as an automatic priority decision."],
        },
    ))

    assert any("2 uploaded stem node(s), 1 activity section(s), and 1 measured relationship" in line for line in context["context_lines"])
    assert any("Mix graph uncertainty" in line for line in context["context_lines"])


def test_build_context_output_is_accepted_by_real_kenn_function() -> None:
    """The actual contract: feed the adapter's output into KENN's real,
    unmodified mix_review_context_turn() and confirm it round-trips into a
    proper history turn containing the render's real decisions -- not just
    that our own code thinks the shape is right."""
    context = explain.build_mix_review_context_from_manifest(_sample_manifest())
    turn = mix_review_context_turn(context)
    assert turn is not None
    assert turn["role"] == "user"
    assert "Clipping correction" in turn["content"]
    assert "Master EQ correction" in turn["content"]
    assert "proj-123" in turn["content"]
    assert "technical_score" in turn["content"] or "82" in turn["content"]


def test_safety_diagnostics_become_flags_and_reach_kenn() -> None:
    manifest = _sample_manifest(
        quality_gate={
            "passed": False,
            "safety_passed": False,
            "hard_failures": ["true_peak_exceeded"],
            "safety_diagnostics": ["True peak -0.2 dBTP exceeds -1.0 dBTP ceiling by 0.8 dB."],
            "technical_score": 40,
            "minimum_score": 65,
            "advisory_score_passed": False,
        },
    )
    context = explain.build_mix_review_context_from_manifest(manifest)
    assert context["flags"][0]["detail"] == "True peak -0.2 dBTP exceeds -1.0 dBTP ceiling by 0.8 dB."
    turn = mix_review_context_turn(context)
    assert "True peak -0.2 dBTP exceeds" in turn["content"]


def test_empty_decisions_log_produces_honest_placeholder() -> None:
    manifest = _sample_manifest(decisions_log=[])
    context = explain.build_mix_review_context_from_manifest(manifest)
    assert any("No per-render decisions" in line for line in context["context_lines"])
    turn = mix_review_context_turn(context)
    assert turn is not None


def test_long_decisions_log_is_capped_not_unbounded() -> None:
    manifest = _sample_manifest(decisions_log=[f"Decision {i}" for i in range(200)])
    context = explain.build_mix_review_context_from_manifest(manifest)
    # +1 intro line, +1 truncation notice
    assert len(context["context_lines"]) <= explain._MAX_CONTEXT_LINES + 2
    assert any("more decisions not shown" in line for line in context["context_lines"])


def test_missing_optional_fields_do_not_crash() -> None:
    minimal_manifest = {"project_id": "proj-x"}
    context = explain.build_mix_review_context_from_manifest(minimal_manifest)
    assert context["schema"] == "kenn_mix_review_handoff.v1"
    turn = mix_review_context_turn(context)
    assert turn is not None


def test_non_dict_manifest_returns_empty_dict() -> None:
    assert explain.build_mix_review_context_from_manifest(None) == {}
    assert explain.build_mix_review_context_from_manifest([1, 2, 3]) == {}


def test_non_list_relationships_and_decisions_log_do_not_crash() -> None:
    """A caller could plausibly pass a manifest with malformed types (e.g.
    from a corrupted or partial write) -- must degrade gracefully, not
    raise."""
    manifest = _sample_manifest(decisions_log="not a list", relationships={"not": "a list"})
    context = explain.build_mix_review_context_from_manifest(manifest)
    assert context["schema"] == "kenn_mix_review_handoff.v1"
    assert "priority_actions" not in context


def test_find_latest_manifest_artifact_returns_none_when_no_render_exists(monkeypatch) -> None:
    monkeypatch.setattr(explain.artifact_store, "list_for_project", lambda project_id, limit=500: [])
    assert explain.find_latest_manifest_artifact("no-such-project") is None


def test_find_latest_manifest_artifact_filters_by_kind(monkeypatch) -> None:
    items = [
        {"id": "a1", "kind": "audio.automix.mix"},
        {"id": "a2", "kind": "audio.automix.manifest"},
        {"id": "a3", "kind": "audio.automix.report"},
    ]
    monkeypatch.setattr(explain.artifact_store, "list_for_project", lambda project_id, limit=500: items)
    result = explain.find_latest_manifest_artifact("proj-123")
    assert result == {"id": "a2", "kind": "audio.automix.manifest"}


def test_build_context_for_project_returns_none_with_no_artifact(monkeypatch) -> None:
    monkeypatch.setattr(explain, "find_latest_manifest_artifact", lambda project_id: None)
    assert explain.build_mix_review_context_for_project("proj-123") is None


def test_build_context_for_project_end_to_end(monkeypatch, tmp_path) -> None:
    import json

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(_sample_manifest()), encoding="utf-8")

    monkeypatch.setattr(
        explain, "find_latest_manifest_artifact", lambda project_id: {"id": "artifact-1"}
    )
    monkeypatch.setattr(explain.artifact_store, "resolve_path", lambda artifact_id: manifest_path)

    context = explain.build_mix_review_context_for_project("proj-123")
    assert context is not None
    assert context["schema"] == "kenn_mix_review_handoff.v1"
    turn = mix_review_context_turn(context)
    assert "Clipping correction" in turn["content"]


def _stub_answer_payload(monkeypatch, *, capture: dict | None = None):
    def fake(question, limit=4, history=None, *, allow_llm=True, profile=False, session_id=""):
        if capture is not None:
            capture["question"] = question
            capture["history"] = history
        return {
            "answer": "You had a true-peak overshoot, so the limiter pulled the bus drive down 1 dB.",
            "sources": [],
            "weak_match": False,
            "found": True,
            "grounding": {"score": 100, "approved_note": True},
        }

    monkeypatch.setattr("kenn.core.chat_answer.answer_payload", fake)


def test_ask_kenn_about_render_rejects_empty_question() -> None:
    result = explain.ask_kenn_about_render("proj-123", "   ")
    assert result == {"ok": False, "error": "A question is required."}


def test_ask_kenn_about_render_grounded_when_render_exists(monkeypatch) -> None:
    capture: dict = {}
    _stub_answer_payload(monkeypatch, capture=capture)
    monkeypatch.setattr(
        explain, "build_mix_review_context_for_project", lambda project_id: explain.build_mix_review_context_from_manifest(_sample_manifest())
    )

    result = explain.ask_kenn_about_render("proj-123", "Why did the bus drive change?")

    assert result["ok"] is True
    assert result["grounded"] is True
    assert "limiter" in result["answer"].lower()
    assert capture["question"] == "Why did the bus drive change?"
    assert len(capture["history"]) == 1
    assert "Clipping correction" in capture["history"][0]["content"]


def test_ask_kenn_about_render_ungrounded_when_no_render_exists(monkeypatch) -> None:
    capture: dict = {}
    _stub_answer_payload(monkeypatch, capture=capture)
    monkeypatch.setattr(explain, "build_mix_review_context_for_project", lambda project_id: None)

    result = explain.ask_kenn_about_render("proj-123", "How do I mix a kick drum?")

    assert result["ok"] is True
    assert result["grounded"] is False
    assert capture["history"] == []


def test_ask_kenn_about_render_reports_honest_error_when_kenn_unavailable(monkeypatch) -> None:
    def broken_answer_payload(*args, **kwargs):
        raise RuntimeError("model not loaded")

    monkeypatch.setattr("kenn.core.chat_answer.answer_payload", broken_answer_payload)
    monkeypatch.setattr(explain, "build_mix_review_context_for_project", lambda project_id: None)

    result = explain.ask_kenn_about_render("proj-123", "Why is this so quiet?")

    assert result["ok"] is False
    assert "model not loaded" in result["error"]
