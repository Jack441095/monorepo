"""A producer who changes their mind can see the old value and put it back.

`record_preference` deactivates the previous value for a key. That is right for answering a question and wrong for
the Stage 4 gate's "testers can find and delete any memory": saying "actually, I master to -9, not -12" used to
leave the -12 row unreachable through any API. The rows were already retained, just never readable.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kenn.core.assistant_profile_memory import MAX_PREFERENCES, PREFERENCE_KEYS, AssistantProfileStore

KEY = "arrangement_preference"


@pytest.fixture()
def store(tmp_path: Path) -> AssistantProfileStore:
    return AssistantProfileStore(db_path=tmp_path / "profile.db")


def _record(store: AssistantProfileStore, value: str, turn: str) -> dict:
    return store.record_preference(session_id="set-a", key=KEY, value=value,
                                   source_turn_id=turn, user_statement=f"I prefer {value}")


def test_recording_a_second_value_hides_the_first_but_does_not_delete_it(store) -> None:
    first = _record(store, "-12 dB", "t1")
    _record(store, "-9 dB", "t2")
    assert [p["value"] for p in store.current_preferences("set-a")] == ["-9 dB"]
    history = store.preference_history("set-a")
    assert [p["value"] for p in history] == ["-12 dB"]
    assert history[0]["preference_id"] == first["preference"]["preference_id"]


def test_restoring_moves_the_value_back_rather_than_adding_a_second_live_row(store) -> None:
    first = _record(store, "-12 dB", "t1")
    _record(store, "-9 dB", "t2")
    result = store.restore_preference(session_id="set-a", preference_id=first["preference"]["preference_id"])
    assert result["ok"] and result["restored"] is True
    assert [p["value"] for p in store.current_preferences("set-a")] == ["-12 dB"]
    assert [p["value"] for p in store.preference_history("set-a")] == ["-9 dB"]


def test_restoring_something_already_active_is_a_no_op_not_an_error(store) -> None:
    current = _record(store, "-9 dB", "t1")
    result = store.restore_preference(session_id="set-a", preference_id=current["preference"]["preference_id"])
    assert result["ok"] and result["restored"] is False
    assert [p["value"] for p in store.current_preferences("set-a")] == ["-9 dB"]


def test_another_sessions_preference_cannot_be_restored(store) -> None:
    """Session ids are the isolation boundary; restoring across one would move another set's memory."""
    first = _record(store, "-12 dB", "t1")
    store.record_preference(session_id="set-b", key=KEY, value="-6 dB", source_turn_id="t2", user_statement="x")
    assert store.restore_preference(session_id="set-b", preference_id=first["preference"]["preference_id"])["ok"] is False


def test_an_unknown_preference_id_is_reported_rather_than_silently_ignored(store) -> None:
    _record(store, "-9 dB", "t1")
    assert store.restore_preference(session_id="set-a", preference_id="nope")["ok"] is False


def test_history_can_be_narrowed_to_one_key(store) -> None:
    _record(store, "-12 dB", "t1")
    _record(store, "-9 dB", "t2")
    store.record_preference(session_id="set-a", key="genre", value="drum and bass", source_turn_id="t3",
                            user_statement="x")
    assert [p["value"] for p in store.preference_history("set-a", key=KEY)] == ["-12 dB"]
    assert len(store.preference_history("set-a", key="genre")) == 0


def test_the_history_survives_the_retention_bound_that_keeps_the_newest_inactive_rows(store) -> None:
    """record_preference prunes inactive rows past MAX_PREFERENCES, so the restore window is that wide, not wider."""
    first = _record(store, "-0 dB", "t0")
    for step in range(MAX_PREFERENCES + 4):
        _record(store, f"-{step + 1} dB", f"t{step + 1}")
    history = store.preference_history("set-a")
    assert len(history) <= MAX_PREFERENCES
    # Newest first, and the most recent superseded value is still restorable rather than pruned away.
    assert store.restore_preference(session_id="set-a", preference_id=history[0]["preference_id"])["ok"] is True


def test_the_handlers_expose_history_and_restore() -> None:
    from kenn.routes.chat_routes import handle_preference_history, handle_restore_preference
    assert callable(handle_preference_history) and callable(handle_restore_preference)
    assert handle_preference_history("")[0] == 400
    assert handle_restore_preference({"session_id": "", "preference_id": ""})[0] == 400
    assert KEY in PREFERENCE_KEYS
