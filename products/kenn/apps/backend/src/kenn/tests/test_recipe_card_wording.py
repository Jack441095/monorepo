"""Recipe and undo cards name the target, the value now and the value after, in the units Live shows.

Each case here was read off the fake demo set in the 8 Oct 2026 recipe requal, where the card a producer
would have pressed Apply on was either unreadable or claimed a change it was not going to make.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from kenn.core.fake_live import FakeLiveBackend
from kenn.core.live_action_service import LiveActionService
from kenn.core.live_command import handle_command
from kenn.core.live_receipt_journal import record_receipt


@pytest.fixture()
def kenn(monkeypatch, tmp_path):
    from kenn.core import live_receipt_journal

    monkeypatch.setattr(live_receipt_journal, "JOURNAL_PATH", tmp_path / "receipts.jsonl")
    monkeypatch.setenv("KENN_ALLOW_DAW_CONTROL", "1")
    for name in ("KENN_LIVE_LLM_ENABLED", "KENN_LLM_ENABLED", "KENN_LLM_ENABLED_COMMAND"):
        monkeypatch.delenv(name, raising=False)
    fake = FakeLiveBackend()
    service = LiveActionService(fake)
    session = f"wording-{tmp_path.name}"

    def ask(text: str) -> dict:
        return handle_command(text, session_id=session, service=service)

    def do(text: str) -> dict:
        proposal = ask(text).get("proposal") or {}
        assert proposal.get("confirmation_token"), text
        applied = handle_command(text, session_id=session, service=service, proposal=proposal,
                                 confirm_token=proposal["confirmation_token"], idempotency_key=proposal.get("action_id"))
        record_receipt(applied["receipt"], session_id=session)
        return applied

    def index(name: str) -> int:
        return next(t["index"] for t in service.snapshot()["tracks"] if t["name"] == name)

    return SimpleNamespace(ask=ask, do=do, fake=fake, index=index)


def test_undoing_a_recipe_lists_each_value_it_puts_back(kenn) -> None:
    # It used to read "I can set recipe on 'ableton_recipe' from None to None" for all 14 undoable recipes.
    kenn.do("Push the synth back")
    card = kenn.ask("Undo that")
    assert card["status"] == "confirmation_required"
    assert "None" not in card["answer"] and "ableton_recipe" not in card["answer"]
    assert card["answer"].startswith("To undo that, put these back:")
    assert "'Synth' send to A-Reverb 15% -> 0%" in card["answer"]
    assert "'Synth' volume -15.5 dB -> -14.0 dB" in card["answer"]
    # A second "Undo that" walks back further; it never redoes this card, so it must not promise to.
    assert "one Undo puts them all back" not in card["answer"]


def test_a_compressor_threshold_step_shows_the_db_it_moves_to(kenn) -> None:
    # It used to say only "(now 0.00 dB)", so the card never showed the -3 dB the recipe was about to set.
    card = kenn.ask("Tighten the drum bus")
    assert "Compressor Threshold on 'Drum Bus' 0.0 dB -> -3.0 dB" in card["answer"]


def test_undoing_a_compressor_threshold_recipe_shows_db_not_raw(kenn) -> None:
    kenn.do("Tighten the drum bus")
    card = kenn.ask("Undo that")
    assert "Compressor Threshold on 'Drum Bus' -3.0 dB -> 0.0 dB" in card["answer"]


def test_undoing_a_send_reads_in_percent(kenn) -> None:
    # It used to read "I can set set_send on 'Lead Vocal' from 0.4 normalized to 0 normalized".
    kenn.do("Set the delay send on the lead vocal to 40%")
    card = kenn.ask("Undo that")
    assert "send from 'Lead Vocal' to 'B-Delay' from 40% to 0%" in card["answer"]
    assert "normalized" not in card["answer"]


def test_the_low_end_mud_card_only_claims_the_moves_it_makes(kenn) -> None:
    # With no sub on the demo set it still promised to centre the sub bass panning.
    kenn.do("Set the synth to -4 dB")
    card = kenn.ask("Fix the low-end mud")
    assert card["answer"].startswith("To clear the low-end mud: turn 'Synth' down 2 dB")
    assert "sub" not in card["answer"].lower()


def test_a_panned_sub_bass_gets_centred_by_the_low_end_mud_recipe(kenn) -> None:
    # The translator read "panning" from track snapshots, which carry "pan", so this step never appeared.
    bass = kenn.index("Bass")
    kenn.fake.set_track_name(bass, "Sub Bass")
    kenn.fake.set_track_pan(bass, -0.3)
    card = kenn.ask("Fix the low-end mud")
    assert "centre 'Sub Bass'" in card["answer"]
    assert "'Sub Bass' pan 30% left -> centre" in card["answer"]
