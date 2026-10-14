"""Test suite for KENN Natural Language Studio Co-Producer Wiring (Track 1 Chat Orchestration)."""

import pytest
from kenn.core.chat_answer import answer_payload
from kenn.orchestrator import get_orchestrator


def test_conversational_rack_synthesizer_neuro_reese():
    query = "build a neuro reese rack on track 1"
    res = answer_payload(query, session_id="test_chat_co_producer")
    assert res["found"] is True
    assert res["route"] == "rack_synthesizer"
    assert "Neuro Reese" in res["answer"]
    assert res["requires_confirmation"] is True
    assert res["confirmation_token"].startswith("rack_")

    prop = res["proposal"]
    assert prop["rack_id"] == "neuro_reese_saturator"
    assert prop["track_index"] == 1
    assert len(prop["variations"]) == 3
    assert len(prop["steps"]) == 10


def test_conversational_rack_synthesizer_catalog():
    query = "list available racks"
    res = answer_payload(query, session_id="test_chat_co_producer")
    assert res["found"] is True
    assert res["route"] == "rack_synthesizer"
    assert "12 Racks" in res["answer"]
    assert len(res["orchestration"]["racks"]) == 12


def test_conversational_neural_midi_bassline():
    query = "generate a bouncy bassline in F minor"
    res = answer_payload(query, session_id="test_chat_co_producer")
    assert res["found"] is True
    assert res["route"] == "neural_midi_generator"
    assert "F Minor" in res["answer"]
    assert res["requires_confirmation"] is True
    assert res["confirmation_token"].startswith("midi_prop_")

    prop = res["proposal"]
    assert prop["root_note"] == "F"
    assert prop["scale_name"] == "minor"
    assert len(prop["notes"]) >= 8


def test_conversational_surgical_masking_remediation(monkeypatch):
    # A kick and sub both at 0.85 is a clash the Doctor has a move for. With no session open the recipe is empty,
    # and an empty recipe is deliberately not confirmable (see the test below).
    monkeypatch.setattr("kenn.mixing_doctor.get_latest_session_state", lambda: {"tracks": [
        {"index": 0, "name": "Punchy Kick", "volume": 0.85, "panning": 0.0, "devices": []},
        {"index": 1, "name": "808 Sub Bass", "volume": 0.85, "panning": 0.0, "devices": []},
    ]})
    query = "fix the masking in my drop"
    res = answer_payload(query, session_id="test_chat_co_producer")
    assert res["found"] is True
    assert res["route"] == "surgical_masking_doctor"
    assert "Surgical Masking" in res["answer"]
    assert res["requires_confirmation"] is True
    assert res["confirmation_token"].startswith("doctor_remedy_")

    prop = res["proposal"]
    assert prop["schema"] == "kenn.surgical_masking_remediation.v1"
    assert "predicted_metrics" in prop
    assert "masking_reduction_percent" in prop["predicted_metrics"]


def _doctor_result(steps, metrics):
    return {
        "ok": True,
        "audit_summary": "Audit summary.",
        "proposal": {
            "steps": steps,
            "predicted_metrics": metrics,
            "confirmation_token": "doctor_remedy_abc",
        },
    }


def test_an_empty_recipe_gets_no_token_and_no_apply_button(monkeypatch):
    # Seen in the browser on 14 Oct: "Proposed Surgical Recipe (0 actions)" still came with a token and an Apply button.
    from kenn import orchestrator
    from kenn.core.session_doctor import SessionDoctor

    monkeypatch.setattr(
        SessionDoctor, "formulate_surgical_remediation_proposal",
        classmethod(lambda cls, *a, **k: _doctor_result([], {"masking_reduction_percent": 0.0})),
    )
    res = orchestrator._dispatch_surgical_masking(session_id="empty_recipe")

    assert res["requires_confirmation"] is False
    assert "confirmation_token" not in res and "proposal" not in res
    assert "nothing has changed" in res["message"]


def test_the_doctor_message_skips_estimates_that_are_zero_and_has_no_latex(monkeypatch):
    from kenn import orchestrator
    from kenn.core.session_doctor import SessionDoctor

    step = {"action": "set_volume", "track_name": "Kick", "reason": "Trim for headroom."}
    metrics = {"masking_reduction_percent": 40.0, "headroom_reclaimed_db": 0.8, "mono_correlation_delta": 0.0}
    monkeypatch.setattr(
        SessionDoctor, "formulate_surgical_remediation_proposal",
        classmethod(lambda cls, *a, **k: _doctor_result([step], metrics)),
    )
    res = orchestrator._dispatch_surgical_masking(session_id="one_step")

    assert res["requires_confirmation"] is True
    assert "Mono Phase Correlation" not in res["message"]
    assert "$" not in res["message"] and "\\le" not in res["message"]
