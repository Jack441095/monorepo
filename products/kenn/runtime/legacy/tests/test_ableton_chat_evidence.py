from __future__ import annotations

from kenn import server
from kenn.core.evidence import packets_from_history


def test_ableton_chat_context_requires_explicit_opt_in(monkeypatch) -> None:
    calls = []

    def latest():
        calls.append(True)
        return {"status": "connected", "tempo": 126, "tracks": [{"name": "Kick"}]}

    monkeypatch.setattr("kenn.mixing_doctor.get_latest_session_state", latest)
    assert server._ableton_session_context_turn(False) is None
    assert calls == []
    turn = server._ableton_session_context_turn(True)
    assert calls == [True]
    packet = packets_from_history([turn])[0]
    assert packet.source == "ableton_session_snapshot"
    assert {fact.name for fact in packet.facts} >= {"tempo", "track_count", "track_names"}


def test_ableton_chat_context_uses_cached_state_not_live_osc(monkeypatch) -> None:
    monkeypatch.setattr(
        "kenn.mixing_doctor.get_latest_session_state",
        lambda: {"status": "offline", "tracks": []},
    )
    assert server._ableton_session_context_turn(True) is None
