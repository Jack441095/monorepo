"""Corrections move the last whole-track change to the track the producer meant ("no, I meant the snare")."""

from __future__ import annotations

import pytest

from kenn.core.fake_live import FakeLiveBackend
from kenn.core.live_action_service import LiveActionService
from kenn.core.live_command import handle_command


@pytest.fixture()
def live(monkeypatch, tmp_path):
    from kenn.core import live_receipt_journal

    monkeypatch.setattr(live_receipt_journal, "JOURNAL_PATH", tmp_path / "receipts.jsonl")
    monkeypatch.setenv("KENN_ALLOW_DAW_CONTROL", "1")
    for name in ("KENN_LIVE_LLM_ENABLED", "KENN_LLM_ENABLED", "KENN_LLM_ENABLED_COMMAND"):
        monkeypatch.delenv(name, raising=False)
    service = LiveActionService(FakeLiveBackend())
    session = f"correction-{tmp_path.name}"

    def say(command, *, apply=False):
        result = handle_command(command, session_id=session, service=service)
        proposal = result.get("proposal")
        if apply and proposal:
            return handle_command(command, session_id=session, service=service, proposal=proposal,
                                  confirm_token=proposal.get("confirmation_token"),
                                  idempotency_key=proposal.get("action_id"))
        return result

    return say


@pytest.mark.parametrize("first, correction, track, action", [
    ("Bring the bass down 2 dB", "no, I meant the snare", "Snare / Clap", "set_volume"),
    ("Bring the bass down 2 dB", "sorry, the kick", "Kick", "set_volume"),
    ("mute the hats", "not the hats, the kick", "Kick", "set_mute"),
    ("pan the synth 20% left", "actually the vocal", "Lead Vocal", "set_pan"),
    ("mute the hats", "no, the kick instead", "Kick", "set_mute"),
])
def test_a_correction_moves_the_change_to_the_track_meant(live, first, correction, track, action) -> None:
    live(first)
    result = live(correction)
    assert result["status"] == "confirmation_required"
    assert result["proposal"]["action"] == action and result["proposal"]["track_name"] == track
    assert result["context_resolution"]["resolution"] == "correction"


def test_an_applied_change_is_left_alone_and_the_answer_says_so(live) -> None:
    live("Bring the bass down 2 dB", apply=True)
    result = live("no, I meant the snare")
    assert result["proposal"]["track_name"] == "Snare / Clap"
    assert "Bass is still applied" in result["answer"] and "undo" in result["answer"]


@pytest.mark.parametrize("reply", ["no, the other one", "no, the bass", "no, the snare and the kick"])
def test_unclear_corrections_still_ask(live, reply) -> None:
    live("Bring the bass down 2 dB")
    assert live(reply)["status"] == "clarification_required"
