from collections import defaultdict, deque
from copy import deepcopy
import json
from threading import Event, Lock, Thread
import time
import urllib.error
import urllib.request

from fastapi.testclient import TestClient
import pytest

import kenn.server_rate_limit as rate_limit
from kenn.core import answer_upgrades, chat_answer, confirmation, live_action_service, live_receipt_journal
from kenn.core.fake_live import FakeLiveBackend
from kenn.core.live_action_service import LiveActionService
from kenn.core.live_recipe import LiveRecipeService
from kenn.routes.daw_routes import handle_confirmation_revoke


@pytest.fixture(autouse=True)
def isolated_cancellation_state(monkeypatch, tmp_path):
    monkeypatch.setattr(confirmation, "_USED_TOKENS", set())
    monkeypatch.setattr(confirmation, "_ISSUED_TOKENS", {})
    monkeypatch.setattr(confirmation, "_REVOKED_TOKENS", set())
    monkeypatch.setattr(answer_upgrades, "_RESULTS", {})
    monkeypatch.setattr(answer_upgrades, "_TURNS", {})
    monkeypatch.setattr(answer_upgrades, "_BUSY", Lock())
    monkeypatch.setattr(answer_upgrades, "log_outcome", lambda *args: None)
    monkeypatch.setattr(live_receipt_journal, "JOURNAL_PATH", tmp_path / "receipts.jsonl")
    monkeypatch.setattr(rate_limit, "RATE_BUCKETS", defaultdict(deque))
    monkeypatch.setenv("KENN_ALLOW_DAW_CONTROL", "1")
    monkeypatch.setenv("KENN_LLM_ENABLED", "0")


@pytest.fixture(params=["http", "prefixed_http", "fastapi"])
def cancellation_http(request, monkeypatch):
    from kenn import server
    from kenn.routes.fastapi_app import app

    fake = FakeLiveBackend()
    monkeypatch.setattr(live_action_service, "live_client", fake)
    if request.param == "fastapi":
        with TestClient(app) as client:
            def post(path, payload):
                response = client.post(path, json=payload)
                return response.status_code, response.json()
            yield post, fake
        return

    httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    worker = Thread(target=lambda: httpd.serve_forever(poll_interval=0.01), daemon=True)
    worker.start()
    prefix = "/kenn" if request.param == "prefixed_http" else ""

    def post(path, payload):
        req = urllib.request.Request(
            f"http://127.0.0.1:{httpd.server_port}{prefix}{path}",
            data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            response = urllib.request.urlopen(req, timeout=3)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            return response.status, json.load(response)

    try:
        yield post, fake
    finally:
        httpd.shutdown()
        httpd.server_close()
        worker.join(2)


def test_http_dismiss_revokes_a_held_proposal_before_echoed_apply(cancellation_http):
    # The browser echoes its proposal on Apply, so hiding/deleting a card was insufficient.
    post, fake = cancellation_http
    proposal = deepcopy(LiveActionService(fake).propose_transport_action("transport_play", session_id="owner")["proposal"])
    before = fake.query_session_state()
    token = proposal["confirmation_token"]

    status, dismissed = post("/api/ableton/confirmation/revoke", {"session_id": "owner", "confirm_token": token})
    assert status == 200
    assert dismissed == {"ok": True, "status": "revoked"}
    status, applied = post("/api/ableton/command", {
        "session_id": "owner", "command": "confirm", "confirm_token": token, "proposal": proposal,
    })

    assert status == 409
    assert applied["status"] == "failed"
    assert applied["changed"] is False
    assert fake.writes == []
    assert fake.query_session_state() == before


@pytest.mark.parametrize("dismiss", [True, False])
def test_http_recipe_has_no_hidden_pending_confirmations_after_dismiss_or_apply(cancellation_http, dismiss):
    post, fake = cancellation_http
    proposal = deepcopy(LiveRecipeService(LiveActionService(fake)).propose_recipe([
        {"action": "set_pan", "track_index": 5, "value": -1.0},
        {"action": "set_mute", "track_index": 5, "value": True},
    ], session_id="owner", reason="Producer requested pan and mute.")["proposal"])
    token = proposal["confirmation_token"]
    assert confirmation.pending_confirmation_count(session_id="owner") == 1
    before = fake.query_session_state()
    if dismiss:
        status, result = post("/api/ableton/confirmation/revoke", {"session_id": "owner", "confirm_token": token})
        assert status == 200
        assert result["status"] == "revoked"
    status, result = post("/api/ableton/command", {
        "session_id": "owner", "command": "confirm", "confirm_token": token, "proposal": proposal,
    })
    assert status == (409 if dismiss else 200)
    assert result["changed"] is not dismiss
    assert confirmation.pending_confirmation_count(session_id="owner") == 0
    if dismiss:
        assert fake.writes == []
        assert fake.query_session_state() == before


@pytest.mark.parametrize("terminal", ["revoked", "session_cancelled", "consumed", "expired"])
def test_yes_only_offers_a_confirmation_while_a_session_token_is_pending(monkeypatch, terminal):
    from kenn.core.session_context import record_live_exchange
    from kenn.server import _proposal_waiting

    monkeypatch.setattr(confirmation.time, "time", lambda: 100)
    binding = {"session_id": "owner", "service_id": "ableton_action", "text": "transport_play"}
    token, _ = confirmation.issue_confirmation(**binding, ttl_seconds=1)
    other, _ = confirmation.issue_confirmation(session_id="other", service_id="midi_clip", text="clip")
    record_live_exchange(session_id="owner", command="play", result={"status": "confirmation_required"})
    assert _proposal_waiting("owner")
    if terminal == "revoked":
        assert confirmation.revoke_confirmation(token, session_id="owner")
    elif terminal == "session_cancelled":
        assert confirmation.revoke_session_confirmations(session_id="owner") == 1
    elif terminal == "consumed":
        assert confirmation.consume_confirmation(token, **binding)
    else:
        monkeypatch.setattr(confirmation.time, "time", lambda: 101)

    assert not _proposal_waiting("owner")
    assert _proposal_waiting("other")
    assert other in confirmation._ISSUED_TOKENS
    assert not _proposal_waiting("")


def test_http_dismiss_cannot_revoke_another_chats_confirmation(cancellation_http):
    post, fake = cancellation_http
    proposal = LiveActionService(fake).propose_transport_action("transport_play", session_id="owner")["proposal"]
    token = proposal["confirmation_token"]

    status, rejected = post("/api/ableton/confirmation/revoke", {"session_id": "other", "confirm_token": token})
    assert status == 409
    assert rejected["ok"] is False
    assert rejected["status"] == "not_revoked"
    assert confirmation.verify_confirmation(token, session_id="owner", **{
        key: proposal["confirmation_meta"][key] for key in ("service_id", "text")
    })
    status, applied = post("/api/ableton/command", {
        "session_id": "owner", "command": "confirm", "confirm_token": token, "proposal": proposal,
    })
    assert status == 200
    assert applied["status"] == "applied"
    assert fake.query_session_state()["is_playing"] is True


@pytest.mark.parametrize("payload", [
    {}, {"session_id": None, "confirm_token": "token"}, {"session_id": "", "confirm_token": "token"},
    {"session_id": " owner", "confirm_token": "token"}, {"session_id": "owner ", "confirm_token": "token"},
    {"session_id": "s" * 129, "confirm_token": "token"}, {"session_id": "owner", "confirm_token": None},
    {"session_id": "owner", "confirm_token": 42}, {"session_id": "owner", "confirm_token": "t" * 513},
])
def test_revoke_route_rejects_unbound_or_coerced_inputs(payload):
    assert handle_confirmation_revoke(payload)[0] == 400


def test_http_revoke_rejects_an_unbound_session(cancellation_http):
    post, fake = cancellation_http
    token, _ = confirmation.issue_confirmation(session_id="", service_id="test", text="write")

    status, rejected = post("/api/ableton/confirmation/revoke", {"session_id": "", "confirm_token": token})

    assert status in {400, 422}
    assert confirmation.verify_confirmation(token, session_id="", service_id="test", text="write")
    assert fake.writes == []


@pytest.mark.parametrize("state", ["expired", "used", "revoked", "unknown"])
def test_http_does_not_report_terminal_or_unknown_tokens_as_cancelled(cancellation_http, monkeypatch, state):
    post, fake = cancellation_http
    token, record = confirmation.issue_confirmation(session_id="owner", service_id="test", text="write")
    if state == "expired":
        monkeypatch.setattr(confirmation.time, "time", lambda: record["expires_at"])
    elif state == "used":
        assert confirmation.consume_confirmation(token, session_id="owner", service_id="test", text="write")
    elif state == "revoked":
        assert confirmation.revoke_confirmation(token, session_id="owner")
    else:
        token = "unknown"

    status, rejected = post("/api/ableton/confirmation/revoke", {"session_id": "owner", "confirm_token": token})

    assert status == 409
    assert rejected["ok"] is False
    assert rejected["status"] == "not_revoked"
    assert fake.writes == []


@pytest.mark.parametrize("word", ["no", "n", "cancel", "abort", "reject", "stop action"])
def test_chat_cancel_revokes_only_its_pending_confirmations(word):
    owner, _ = confirmation.issue_confirmation(session_id="owner", service_id="test", text="write")
    other, _ = confirmation.issue_confirmation(session_id="other", service_id="test", text="write")

    result = chat_answer.answer_payload(word, session_id="owner")

    assert result["revoked_confirmations"] == 1
    assert result["answer_delivery_discarded"] is True
    assert result["inference_aborted"] is False
    assert "already executing" in result["answer"]
    assert "No changes were made" not in result["answer"]
    assert not confirmation.consume_confirmation(owner, session_id="owner", service_id="test", text="write")
    assert confirmation.consume_confirmation(other, session_id="other", service_id="test", text="write")


@pytest.mark.parametrize("session_id", ["", None, " owner", "owner "])
def test_unbound_chat_cancel_preserves_pending_tokens_and_answer_delivery(session_id):
    token, _ = confirmation.issue_confirmation(session_id="", service_id="test", text="write")
    owner, _ = confirmation.issue_confirmation(session_id="owner", service_id="test", text="write")
    answer_upgrades._RESULTS["answer"] = {"status": "pending", "session_id": "owner", "at": time.time()}

    result = chat_answer.answer_payload("cancel", session_id=session_id)

    assert result["revoked_confirmations"] == 0
    assert result["answer_delivery_discarded"] is False
    assert "could not revoke" in result["answer"]
    assert confirmation.consume_confirmation(token, session_id="", service_id="test", text="write")
    assert confirmation.consume_confirmation(owner, session_id="owner", service_id="test", text="write")
    assert answer_upgrades.get("answer", session_id="owner")["status"] == "pending"


def test_chat_cancel_discards_late_delivery_while_inference_keeps_its_slot():
    entered, release, finished = Event(), Event(), Event()
    answer_upgrades._RESULTS["other"] = {"status": "accepted", "session_id": "other", "answer": "Other advice", "at": time.time()}

    def write():
        entered.set()
        assert release.wait(2)
        finished.set()
        return {"llm_enhanced": True, "answer": "Cancelled chat's late answer"}

    upgrade = answer_upgrades.start(write, session_id="owner", turn_id=answer_upgrades.begin_turn("owner"))
    assert entered.wait(2)
    try:
        result = chat_answer.answer_payload("cancel", session_id="owner")
        assert result["revoked_confirmations"] == 0
        assert result["inference_aborted"] is False
        assert "No pending confirmations" in result["answer"]
        assert "inference may still be running" in result["answer"]
        assert answer_upgrades.get(upgrade, session_id="owner") == {"status": "expired"}
        assert answer_upgrades.get("other", session_id="other")["answer"] == "Other advice"
        assert answer_upgrades._BUSY.locked()
        assert answer_upgrades.start(lambda: {}, session_id="other") is None
        assert not finished.is_set()
    finally:
        release.set()
        with answer_upgrades._BUSY:
            pass
    assert finished.is_set()
    assert answer_upgrades.get(upgrade, session_id="owner") == {"status": "expired"}
