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


def test_conversational_surgical_masking_remediation():
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
