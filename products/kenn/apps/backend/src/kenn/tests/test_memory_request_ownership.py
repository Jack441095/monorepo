"""Explicit memory commands must retain their chat's request owner until saving."""

import pytest

from kenn.core import answer_upgrades, chat_answer, confirmation, project_memory_advisory, session_memory
from kenn.core.assistant_profile_memory import AssistantProfileStore


@pytest.mark.parametrize("surface", ["payload", "stream"])
@pytest.mark.parametrize("command", ["I like my vocals bright", "Forget preference creative_direction", "clear memory"])
@pytest.mark.parametrize("superseded_by", ["cancel", "next_turn", "other_chat"])
def test_superseded_memory_command_cannot_save_forget_or_clear_preferences(monkeypatch, tmp_path, surface, command, superseded_by):
    from kenn.core import live_action_service
    from kenn.core.fake_live import FakeLiveBackend

    # Delivery was discarded after cancellation, but the shortcut had already changed project memory.
    monkeypatch.setattr(answer_upgrades, "_TURNS", {})
    monkeypatch.setattr(answer_upgrades, "_RESULTS", {})
    monkeypatch.setattr(confirmation, "_ISSUED_TOKENS", {})
    monkeypatch.setattr(confirmation, "_REVOKED_TOKENS", set())
    monkeypatch.setattr(confirmation, "_USED_TOKENS", set())
    monkeypatch.setattr(session_memory, "DB_PATH", tmp_path / "sessions.db")
    fake = FakeLiveBackend()
    monkeypatch.setattr(live_action_service, "live_client", fake)
    store = AssistantProfileStore(tmp_path / "profile.db")
    for session in ("song-a", "song-b"):
        for key, value in (("creative_direction", "warm and vintage"), ("monitoring", "headphones")):
            assert store.record_preference(session_id=session, key=key, value=value,
                                           source_turn_id="fixture", user_statement=value)["ok"]

    def snapshot(session):
        return store.current_preferences(session), store.preference_history(session)

    before = snapshot("song-a")
    other_before = snapshot("song-b")

    def ask(query):
        if surface == "payload":
            return chat_answer.answer_payload(query, session_id="song-a", allow_llm=False)
        events = list(chat_answer.answer_payload_stream(query, session_id="song-a"))
        return [event["data"] for event in events if event["event"] == "metadata"][-1]

    interrupted = False

    def open_store():
        nonlocal interrupted
        if not interrupted:
            interrupted = True
            if superseded_by == "cancel":
                ask("cancel")
            else:
                answer_upgrades.begin_turn("song-a" if superseded_by == "next_turn" else "song-b")
        return store

    def forbidden(*args, **kwargs):
        raise AssertionError("Memory commands must not retrieve or generate")

    monkeypatch.setattr(project_memory_advisory, "AssistantProfileStore", open_store)
    monkeypatch.setattr(chat_answer, "_answer_payload_raw", forbidden)
    monkeypatch.setattr(chat_answer, "_answer_payload_stream_raw", forbidden)
    monkeypatch.setattr(session_memory, "get_semantic_cache_hit", forbidden)
    result = ask(command)
    if superseded_by == "other_chat":
        assert snapshot("song-a") != before
        assert result["answer"] and not result.get("answer_delivery_discarded")
    else:
        assert snapshot("song-a") == before
        assert result["answer"] == "" and result["answer_delivery_discarded"] is True
    assert snapshot("song-b") == other_before
    assert fake.writes == []
