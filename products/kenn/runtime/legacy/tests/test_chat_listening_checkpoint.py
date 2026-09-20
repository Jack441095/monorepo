"""Integration tests for server.Handler._maybe_handle_checkpoint_reply()
and _maybe_attach_checkpoint() (D2.4, docs/KENN_FUTURE_PLAN.md Phase 2)."""

from __future__ import annotations

import sys
from pathlib import Path

LM = Path(__file__).resolve().parent.parent.parent / "studio" / "kenn" / "kenn"
sys.path.insert(0, str(LM))

import pytest  # noqa: E402
import server  # noqa: E402
from kenn.core import session_memory  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_session_db(tmp_path, monkeypatch):
    monkeypatch.setattr(session_memory, "DB_PATH", tmp_path / "kenn.db")
    yield


def _reply(question: str, session_id: str = "s1") -> dict | None:
    return server.Handler._maybe_handle_checkpoint_reply(None, question, session_id)


def _attach(result: dict, session_id: str = "s1") -> dict:
    return server.Handler._maybe_attach_checkpoint(None, result, session_id)


def test_no_pending_checkpoint_falls_through():
    assert _reply("yes") is None


def test_attach_then_accept_round_trip():
    result = _attach({"contains_unvalidated_suggestions": True, "answer": "..."})
    assert result["listening_checkpoint"] == "the suggested EQ move"
    assert session_memory.get_pending_checkpoint("s1")["description"] == "the suggested EQ move"

    reply = _reply("yes")
    assert reply["checkpoint_response"] == "accepted"
    assert session_memory.get_pending_checkpoint("s1") is None


def test_attach_then_reject_round_trip():
    _attach({"contains_unvalidated_suggestions": True})
    reply = _reply("no")
    assert reply["checkpoint_response"] == "rejected"
    assert session_memory.get_pending_checkpoint("s1") is None


def test_unrelated_reply_falls_through_and_clears_the_checkpoint():
    _attach({"contains_unvalidated_suggestions": True})
    reply = _reply("how do I saturate sub bass?")
    assert reply is None
    # One-shot: even though it didn't match, the checkpoint is gone --
    # a much later unrelated "yes" must never resurrect it.
    assert session_memory.get_pending_checkpoint("s1") is None


def test_attach_does_nothing_for_a_plain_answer():
    result = _attach({"answer": "general advice", "found": True})
    assert "listening_checkpoint" not in result
    assert session_memory.get_pending_checkpoint("s1") is None


def test_attach_is_a_no_op_without_a_session_id():
    result = _attach({"contains_unvalidated_suggestions": True}, session_id="")
    assert "listening_checkpoint" not in result


def test_different_sessions_do_not_share_checkpoints():
    server.Handler._maybe_attach_checkpoint(None, {"contains_unvalidated_suggestions": True}, "s1")
    assert _reply("yes", session_id="s2") is None


@pytest.fixture()
def isolated_business_db(tmp_path, monkeypatch):
    WEBSITE = Path(__file__).resolve().parent.parent.parent / "business" / "app"
    sys.path.insert(0, str(WEBSITE))
    import db as business_db

    monkeypatch.setattr(business_db, "DB_PATH", tmp_path / "audio_too.db")
    monkeypatch.setattr(business_db, "AGENT_DATA", tmp_path / "legacy-json")
    monkeypatch.setattr(business_db, "_migration_done", False)
    business_db.init_db()
    yield business_db


def test_accept_persists_the_revision_outcome_as_kept(isolated_business_db):
    # §13.6.2 ("applied revisions log -- track what KENN applied +
    # whether you kept it"), added 2026-08-08.
    import song_projects

    project = song_projects.create_project()
    revision_id = song_projects.record_revision_request(project["id"], "make it brighter")

    _attach({
        "route": "automix_revision", "found": True,
        "automix_revision": {"ok": True, "job_id": "job-1"},
        "revision_history_id": revision_id,
    })
    _reply("yes")

    history = song_projects.get_revision_history(project["id"])
    assert history[0]["outcome"] == "kept"


def test_reject_persists_the_revision_outcome_as_reverted(isolated_business_db):
    import song_projects

    project = song_projects.create_project()
    revision_id = song_projects.record_revision_request(project["id"], "make it brighter")

    _attach({
        "route": "automix_revision", "found": True,
        "automix_revision": {"ok": True, "job_id": "job-1"},
        "revision_history_id": revision_id,
    })
    _reply("no")

    history = song_projects.get_revision_history(project["id"])
    assert history[0]["outcome"] == "reverted"


def test_checkpoint_without_a_revision_history_id_does_not_touch_song_projects():
    # An EQ-move-suggestion checkpoint has no revision_history row --
    # must not attempt to record an outcome for it.
    _attach({"contains_unvalidated_suggestions": True})
    reply = _reply("yes")
    assert reply["checkpoint_response"] == "accepted"
