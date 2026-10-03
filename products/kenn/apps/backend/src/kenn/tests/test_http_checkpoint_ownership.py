"""Shortcut checkpoints must belong to the chat turn that reads or writes them."""

import json
import sys
import threading
from collections import defaultdict, deque
from types import SimpleNamespace
from urllib.request import Request, urlopen

import pytest

from kenn.core import answer_upgrades, session_memory


@pytest.fixture
def checkpoint_http(monkeypatch, tmp_path):
    import kenn.server as server
    import kenn.server_rate_limit as rate_limit

    monkeypatch.setattr(rate_limit, "RATE_BUCKETS", defaultdict(deque))
    monkeypatch.setattr(answer_upgrades, "_TURNS", {})
    monkeypatch.setattr(answer_upgrades, "_RESULTS", {})
    monkeypatch.setattr(answer_upgrades, "enabled", lambda: False)
    monkeypatch.setattr(session_memory, "DB_PATH", tmp_path / "sessions.db")
    monkeypatch.setattr(session_memory, "SESSION_FILE", tmp_path / "session.json")
    monkeypatch.setattr(server, "live_context_summary", lambda *args: None)
    monkeypatch.setattr(server, "demo_feedback", None)
    monkeypatch.setattr(server, "classify_non_request", lambda *args: None)
    monkeypatch.setattr(server, "answer_payload", lambda *args, **kwargs: {"answer": "Fixture explanation", "route": "production"})
    for name in ("_maybe_handle_live_inspection", "_maybe_handle_midi_generation", "_maybe_handle_live_command_from_chat",
                 "_maybe_run_explicit_tool_trigger", "_maybe_handle_project_analysis", "_maybe_handle_mix_revision"):
        monkeypatch.setattr(server.Handler, name, lambda *args, **kwargs: None)
    httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    worker = threading.Thread(target=lambda: httpd.serve_forever(poll_interval=0.01), daemon=True)
    worker.start()

    def post(path, question, session_id="song-a"):
        request = Request(
            f"http://127.0.0.1:{httpd.server_port}{path}",
            data=json.dumps({"question": question, "session_id": session_id, "stream": False}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request, timeout=5) as response:
            return json.load(response)

    try:
        yield post
    finally:
        httpd.shutdown()
        worker.join(timeout=5)
        httpd.server_close()


def supersede(kind):
    if kind == "cancel":
        answer_upgrades.invalidate("song-a")
    elif kind == "next_turn":
        answer_upgrades.begin_turn("song-a")
    elif kind == "other_chat":
        answer_upgrades.begin_turn("song-b")


@pytest.mark.parametrize("path", ["/api/ask", "/kenn/api/ask"])
@pytest.mark.parametrize("superseded_by", ["cancel", "next_turn", "other_chat", "none"])
def test_http_revision_shortcut_does_not_replace_a_checkpoint_after_its_turn_is_revoked(checkpoint_http, monkeypatch, path, superseded_by):
    import kenn.server as server

    # The discarded revision reply still saved a checkpoint for the next chat message.
    def revision(*args, **kwargs):
        supersede(superseded_by)
        session_memory.remember_pending_checkpoint("song-a", "newer checkpoint", 42)
        return {
            "answer": "Revision queued", "route": "automix_revision", "found": True,
            "automix_revision": {"ok": True}, "revision_history_id": 17,
        }

    monkeypatch.setattr(server.Handler, "_maybe_handle_mix_revision", revision)
    result = checkpoint_http(path, "Make the bass warmer")
    checkpoint = session_memory.get_pending_checkpoint("song-a")
    if superseded_by in {"cancel", "next_turn"}:
        assert result["answer_delivery_discarded"] is True
        assert checkpoint["description"] == "newer checkpoint"
        assert checkpoint["revision_history_id"] == 42
    else:
        assert result["listening_checkpoint"] == "the revision once it renders"
        assert checkpoint["description"] == result["listening_checkpoint"]
        assert checkpoint["revision_history_id"] == 17


@pytest.mark.parametrize("path", ["/api/ask", "/kenn/api/ask"])
@pytest.mark.parametrize("superseded_by", ["cancel", "next_turn", "other_chat", "none"])
@pytest.mark.parametrize("question, outcome", [("yes", "kept"), ("no", "reverted"), ("Explain compressor release", None)])
def test_http_old_checkpoint_reply_cannot_clear_or_rate_a_newer_checkpoint(checkpoint_http, monkeypatch, path, superseded_by, question, outcome):
    import kenn.server as server

    writes = []
    monkeypatch.setitem(sys.modules, "song_projects", SimpleNamespace(record_revision_outcome=lambda *args: writes.append(args)))

    def before_checkpoint(*args):
        supersede(superseded_by)
        session_memory.remember_pending_checkpoint("song-a", "current checkpoint", 42)
        return None

    monkeypatch.setattr(server.Handler, "_maybe_handle_live_command_from_chat", before_checkpoint)
    result = checkpoint_http(path, question)
    checkpoint = session_memory.get_pending_checkpoint("song-a")
    if superseded_by in {"cancel", "next_turn"}:
        assert result["answer_delivery_discarded"] is True
        assert checkpoint["description"] == "current checkpoint"
        assert writes == []
    else:
        assert checkpoint is None
        assert writes == ([(42, outcome)] if outcome else [])
        if outcome:
            assert result["checkpoint_response"] == ("accepted" if outcome == "kept" else "rejected")


@pytest.mark.parametrize("path", ["/api/ask", "/kenn/api/ask"])
@pytest.mark.parametrize("operation", ["read_reply", "save_revision"])
def test_http_checkpoint_storage_finishes_before_cancellation_can_replace_its_owner(checkpoint_http, monkeypatch, path, operation):
    import kenn.server as server

    # Revocation must wait for a started write, rather than slip between its check and save.
    entered, release, attempted, revoked = (threading.Event() for _ in range(4))
    responses = []
    failures = []
    session_memory.remember_pending_checkpoint("song-a", "previous checkpoint", 17)
    method = "clear_pending_checkpoint" if operation == "read_reply" else "remember_pending_checkpoint"
    persist = getattr(session_memory, method)

    def paused_storage(*args, **kwargs):
        entered.set()
        assert release.wait(3), "checkpoint write was not released"
        return persist(*args, **kwargs)

    monkeypatch.setattr(session_memory, method, paused_storage)
    if operation == "save_revision":
        monkeypatch.setattr(server.Handler, "_maybe_handle_mix_revision", lambda *args: {
            "answer": "Revision queued", "route": "automix_revision", "found": True,
            "automix_revision": {"ok": True}, "revision_history_id": 18,
        })

    def request():
        try:
            responses.append(checkpoint_http(path, "yes" if operation == "read_reply" else "Make the bass warmer"))
        except Exception as error:
            failures.append(error)

    def cancel():
        attempted.set()
        answer_upgrades.invalidate("song-a")
        revoked.set()
        persist_new = persist if operation == "save_revision" else session_memory.remember_pending_checkpoint
        persist_new("song-a", "newer checkpoint", 42)

    requester = threading.Thread(target=request)
    canceller = threading.Thread(target=cancel)
    requester.start()
    try:
        assert entered.wait(3), "request never reached checkpoint storage"
        canceller.start()
        assert attempted.wait(3)
        assert not revoked.wait(0.05), "cancellation overtook a checkpoint write"
    finally:
        release.set()
        requester.join(timeout=5)
        if canceller.ident is not None:
            canceller.join(timeout=5)
    assert not requester.is_alive() and not canceller.is_alive()
    assert failures == [] and len(responses) == 1
    assert session_memory.get_pending_checkpoint("song-a")["revision_history_id"] == 42
