"""Five-turn API journeys exercise authority and context without model inference."""

from __future__ import annotations

from threading import Event, Lock

import pytest
from fastapi.testclient import TestClient

from kenn.core import answer_upgrades, chat_answer, confirmation, live_command, live_receipt_journal, session_memory
from kenn.core.live_action_service import LiveActionService
from kenn.routes import daw_command_handler
from kenn.routes.fastapi_app import app
from kenn.tests.test_live_command import FakeLive
from kenn.tests.test_parameter_targets import target


@pytest.fixture
def api(monkeypatch, tmp_path):
    import kenn.core.live_action_service as services

    monkeypatch.setenv("KENN_ALLOW_DAW_CONTROL", "1")
    monkeypatch.setenv("KENN_LLM_ENABLED", "0")
    monkeypatch.setattr(session_memory, "DB_PATH", tmp_path / "chat.db")
    monkeypatch.setattr(session_memory, "CHATS_DIR", tmp_path / "chats")
    monkeypatch.setattr(session_memory, "SESSION_FILE", tmp_path / "session.json")
    monkeypatch.setattr(live_receipt_journal, "JOURNAL_PATH", tmp_path / "receipts.jsonl")
    monkeypatch.setattr(answer_upgrades, "_RESULTS", {})
    monkeypatch.setattr(answer_upgrades, "_TURNS", {})
    monkeypatch.setattr(answer_upgrades, "_BUSY", Lock())
    monkeypatch.setattr(answer_upgrades, "log_outcome", lambda *args: None)
    monkeypatch.setattr(confirmation, "_ISSUED_TOKENS", {})
    monkeypatch.setattr(confirmation, "_USED_TOKENS", set())
    monkeypatch.setattr(confirmation, "_REVOKED_TOKENS", set())
    client = TestClient(app)

    def bind(service):
        monkeypatch.setattr(services, "LiveActionService", lambda *args, **kwargs: service)

        def command(text, **kwargs):
            # Only the provider is disabled. Parsing, context, confirmation and writes use the public route's handler.
            kwargs["allow_llm"] = False
            return live_command.handle_command(text, service=service, **kwargs)

        monkeypatch.setattr(daw_command_handler, "_get_handle_command", lambda: command)
        return client

    return bind


def command(client, text, session="journey", **kwargs):
    response = client.post("/api/ableton/command", json={"command": text, "session_id": session, **kwargs})
    assert response.status_code in (200, 409), response.text
    return response.json()


def apply(client, proposal, session="journey"):
    return command(client, "Apply that", session, proposal=proposal, confirm_token=proposal["confirmation_token"])


def test_five_turn_duplicate_device_clarification_corrected_target_revision_and_apply(api):
    # The old name parser silently selected the first Compressor; the API must show both copies before approval.
    fake = FakeLive()
    fake.state["tracks"][2]["devices"].append({"index": 1, "name": "Compressor"})
    client = api(LiveActionService(fake))
    first = command(client, "set Compressor Threshold on Vocal to -18 dB")
    assert first["status"] == "clarification_required" and "proposal" not in first
    assert [row["number"] for row in first["intent"]["device_choices"]] == [1, 2]
    second = command(client, "set Compressor device 2 Threshold on Vocal to -18 dB")
    assert second["proposal"]["device_index"] == 1
    third = command(client, "set Compressor device 2 Threshold on Vocal to -16 dB")
    assert third["proposal"]["after"] != second["proposal"]["after"]
    fourth = command(client, "show Compressor device 2 parameters on Vocal")
    assert fourth["changed"] is False and fake.writes == []
    fifth = apply(client, third["proposal"])
    assert fifth["receipt"]["verified"] is True
    assert fake.writes == [("threshold", 2, 1, 0, third["proposal"]["after"])]


def test_five_turn_other_compressor_that_one_and_relative_change_require_exact_selection(api):
    fake = FakeLive()
    fake.state["tracks"][2]["devices"].append({"index": 1, "name": "Compressor"})
    client = api(LiveActionService(fake))
    command(client, "set Compressor device 1 Threshold on Vocal to -18 dB")
    second = command(client, "the other compressor")
    assert second["status"] == "clarification_required" and len(second["intent"]["device_choices"]) == 2
    third = command(client, "that one")
    assert third["changed"] is False and "proposal" not in third
    fourth = command(client, "lower Compressor device 2 Threshold on Vocal by 2 dB")
    assert fourth["proposal"]["device_index"] == 1 and fake.writes == []
    fifth = apply(client, fourth["proposal"])
    assert fifth["receipt"]["verified"] is True and len(fake.writes) == 1


def test_five_turn_make_it_slower_retains_parameter_but_requires_a_value(api):
    fake = FakeLive()
    client = api(LiveActionService(fake))
    command(client, "set Compressor Threshold on Vocal to -18 dB")
    second = command(client, "make it slower")
    assert second["status"] == "clarification_required" and "proposal" not in second
    assert second["context_resolution"]["device"] == "Compressor"
    third = command(client, "make it slower by 2 ms")
    assert third["changed"] is False and "proposal" not in third
    fourth = command(client, "show Compressor parameters on Vocal")
    assert fourth["changed"] is False
    fifth = command(client, "set Compressor Threshold on Vocal to -20 dB")
    assert fifth["status"] == "confirmation_required" and fake.writes == []


def test_five_turn_two_track_choices_and_correction_apply_only_the_selected_track(api):
    fake = FakeLive()
    fake.state["tracks"][1]["name"] = "Vocal"
    client = api(LiveActionService(fake))
    first = command(client, "mute Vocal")
    assert [row["number"] for row in first["track_choices"]] == [2, 3]
    second = command(client, "track 2")
    assert second["proposal"]["track_index"] == 1
    third = command(client, "no, the other one")
    assert third["proposal"]["track_index"] == 2
    fourth = command(client, "show tracks")
    assert fourth["changed"] is False and fake.writes == []
    fifth = apply(client, third["proposal"])
    assert fifth["receipt"]["verified"] is True
    assert not fake.state["tracks"][1]["muted"] and fake.state["tracks"][2]["muted"]


def test_five_turn_other_compressor_lists_devices_from_the_selected_duplicate_track(api):
    # Looking up the remembered name selected the first Vocal even after the producer explicitly chose track 3.
    fake = FakeLive()
    fake.state["tracks"][1]["name"] = "Vocal"
    fake.state["tracks"][2]["devices"].append({"index": 1, "name": "Compressor"})
    client = api(LiveActionService(fake))
    first = command(client, "mute Vocal")
    assert first["status"] == "clarification_required"
    second = command(client, "track 3")
    assert second["proposal"]["track_index"] == 2
    third = command(client, "set Compressor device 1 Threshold on Vocal track 3 to -18 dB")
    assert third["proposal"]["track_index"] == 2
    fourth = command(client, "the other compressor")
    assert [row["number"] for row in fourth["intent"]["device_choices"]] == [1, 2]
    fifth = command(client, "set Compressor device 2 Threshold on Vocal track 3 to -20 dB")
    assert fifth["proposal"]["track_index"] == 2 and fifth["proposal"]["device_index"] == 1
    assert fake.writes == []


def test_five_turn_advice_command_read_only_topic_change_and_incomplete_request(api, monkeypatch):
    fake = FakeLive()
    client = api(LiveActionService(fake))
    # Synthetic knowledge text tests delivery only; it cannot establish useful model explanations.
    monkeypatch.setattr(chat_answer, "_answer_payload", lambda *args, **kwargs: {"answer": "Synthetic knowledge advice.", "sources": []})
    first = client.post("/api/ask", json={"question": "What does mute do?", "session_id": "journey"}).json()
    assert first.get("receipt") is None
    second = command(client, "mute Bass")
    assert second["status"] == "confirmation_required"
    third = command(client, "show tracks")
    assert third["changed"] is False and "proposal" not in third
    fourth = client.post("/api/ask", json={"question": "What does reverb do?", "session_id": "journey"}).json()
    assert fourth.get("proposal") is None
    fifth = command(client, "set it")
    assert fifth["changed"] is False and "proposal" not in fifth and fake.writes == []


def test_five_turn_failed_job_and_unrun_analysis_use_the_real_analysis_guard(api, monkeypatch):
    client = api(LiveActionService(FakeLive()))
    monkeypatch.setattr(chat_answer, "latest_track_memory_lookup", lambda query: None)
    original = chat_answer._answer_payload

    def without_inference(*args, **kwargs):
        kwargs["allow_llm"] = False
        return original(*args, **kwargs)

    monkeypatch.setattr(chat_answer, "_answer_payload", without_inference)

    def failed():
        raise TimeoutError("synthetic provider timeout")

    turn = answer_upgrades.begin_turn("journey")
    job = answer_upgrades.start(failed, session_id="journey", turn_id=turn)
    with answer_upgrades._BUSY:
        pass
    assert answer_upgrades.get(job, session_id="journey")["status"] == "rejected"
    history = []
    for question in ("How did the analysis of my mix go?", "What were the results of the mix review?",
                     "Can you re-run the analysis?", "Run it again.", "What came out of the scan on my drums?"):
        response = client.post("/api/ask", json={"question": question, "session_id": "journey", "history": history})
        assert response.status_code == 200
        result = response.json()
        assert result["route"] == "no_analysis" and result["sources"] == []
        assert "haven't analysed a mix" in result["answer"] and result.get("receipt") is None
        history.extend([{"role": "user", "content": question}, {"role": "assistant", "content": result["answer"]}])


def test_five_turn_cancel_restart_and_supersession_discard_late_answers(api, monkeypatch):
    client = api(LiveActionService(FakeLive()))
    monkeypatch.setattr(chat_answer, "_answer_payload", lambda *args, **kwargs: {"answer": "Synthetic knowledge advice.", "sources": []})
    client.post("/api/ask", json={"question": "What does EQ do?", "session_id": "journey"})
    entered, release = Event(), Event()

    def late():
        entered.set()
        assert release.wait(5)
        return {"llm_enhanced": True, "answer": "Superseded advice"}

    job = answer_upgrades.start(late, session_id="journey", turn_id=answer_upgrades._TURNS["journey"]["id"])
    try:
        assert entered.wait(5)
        client.post("/api/ask", json={"question": "What does compression do?", "session_id": "journey"})
        assert answer_upgrades.get(job, session_id="journey") == {"status": "expired"}
        assert client.post("/api/session/clear", json={"session_id": "journey"}).status_code == 200
        assert answer_upgrades.start(lambda: {}, session_id="journey") is None
    finally:
        release.set()
        with answer_upgrades._BUSY:
            pass
    fourth = client.post("/api/ask", json={"question": "What does EQ do?", "session_id": "journey"}).json()
    assert fourth["turn_id"]
    # The displayed trace id is separate from the internal delivery owner used by background jobs.
    fresh = answer_upgrades.start(lambda: {"llm_enhanced": True, "answer": "Fresh synthetic advice"},
                                 session_id="journey", turn_id=answer_upgrades._TURNS["journey"]["id"])
    with answer_upgrades._BUSY:
        pass
    assert answer_upgrades.get(fresh, session_id="journey")["status"] == "accepted"
    client.post("/api/ask", json={"question": "What does reverb do?", "session_id": "other-project"})
    assert answer_upgrades.get(job, session_id="journey") == {"status": "expired"}
    assert answer_upgrades.get(fresh, session_id="other-project") == {"status": "expired"}
    assert answer_upgrades.get(fresh, session_id="journey")["status"] == "accepted"


def test_five_turn_project_switch_does_not_share_targets_or_confirmations(api):
    fake = FakeLive()
    client = api(LiveActionService(fake))
    first = command(client, "mute Bass", "project-a")
    second = command(client, "make it louder", "project-b")
    assert second["changed"] is False and "proposal" not in second
    third = apply(client, first["proposal"], "project-b")
    assert third["changed"] is False and fake.writes == []
    fourth = client.post("/api/session/clear", json={"session_id": "project-a"})
    assert fourth.status_code == 200
    fifth = apply(client, first["proposal"], "project-a")
    assert fifth["changed"] is False and fake.writes == []


@pytest.mark.parametrize("manual_edit", [False, True])
def test_five_turn_undo_verifies_restoration_or_refuses_an_intervening_manual_edit(api, target, manual_edit):
    backend, service = target
    client = api(service)
    address = {"kind": "return", "index": 0, "device_path": [1]}
    observed = client.post("/api/ableton/parameter/inspect", json={"address": address, "parameter_index": 4}).json()
    assert observed["changed"] is False
    proposed = client.post("/api/ableton/parameter/proposal", json={"address": address, "parameter_index": 4,
        "parameter_name": "Drive", "device_name": "Test Filter", "value": 0.75, "unit": "raw", "session_id": "journey"}).json()
    applied = apply(client, proposed["proposal"])
    assert applied["receipt"]["verified"] is True
    undo = command(client, "Undo that")
    assert undo["status"] == "confirmation_required"
    if manual_edit:
        # A producer's manual edit is outside KENN's write log and must survive the stale Undo card.
        backend._addressed_buses[1]["devices"][1]["parameters"][0]["value"] = 0.6
    fifth = apply(client, undo["proposal"])
    assert fifth["changed"] is not manual_edit
    assert len(backend.writes) == (1 if manual_edit else 2)
    assert backend.get_addressed_parameter(address, 4)["parameters"][0]["value"] == (0.6 if manual_edit else 0.25)
