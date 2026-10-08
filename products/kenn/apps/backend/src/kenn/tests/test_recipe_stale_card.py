"""A recipe card applied after the set moved on aborts and puts back whatever it had already written.

The service-level rollback tests in test_live_command.py fake the failure inside the backend. These go through
handle_command the way the app does, and make the card stale the way a producer would: by changing the set
between reading the card and pressing Apply. Both scenarios are the 8 Oct 2026 recipe requal probes on fake Live.
"""

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
    fake = FakeLiveBackend()
    return fake, LiveActionService(fake), f"stale-card-{tmp_path.name}"


def _propose(service, session: str, text: str) -> dict:
    proposal = handle_command(text, session_id=session, service=service).get("proposal") or {}
    assert proposal.get("confirmation_token"), text
    return proposal


def _apply(service, session: str, text: str, proposal: dict) -> dict:
    return handle_command(text, session_id=session, service=service, proposal=proposal,
                          confirm_token=proposal["confirmation_token"], idempotency_key=proposal.get("action_id"))


def _track(service, name: str) -> dict:
    return next(t for t in service.snapshot()["tracks"] if t["name"] == name)


def test_a_renamed_track_stops_the_recipe_before_it_writes_anything(live) -> None:
    fake, service, session = live
    card = _propose(service, session, "Push the synth back")
    synth = _track(service, "Synth")
    fake.set_track_name(synth["index"], "Pad")
    before = service.snapshot()

    result = _apply(service, session, "Push the synth back", card)

    assert result["receipt"]["status"] == "failed_rolled_back"
    assert "track identity changed" in result["receipt"]["error"]
    # The card named 'Synth'; the track at that index is now 'Pad', and nothing on it may move.
    assert service.snapshot()["tracks"] == before["tracks"]


def test_a_stale_second_step_rolls_back_the_first_step_it_already_wrote(live) -> None:
    fake, service, session = live
    card = _propose(service, session, "Give the vocal some space")
    # Step 1 is the A-Reverb send and step 2 the B-Delay send, both from 0 %. Moving only step 2's send means step 1
    # passes its freshness check and is written before step 2 finds its before value gone.
    assert [step.get("return_track_name") for step in card["steps"]] == ["A-Reverb", "B-Delay"]
    vocal = _track(service, "Lead Vocal")["index"]
    reverb_before = fake.get_track_send(vocal, 0)
    fake.set_track_send(vocal, 1, 0.4)

    result = _apply(service, session, "Give the vocal some space", card)

    receipt = result["receipt"]
    assert receipt["status"] == "failed_rolled_back"
    assert "send value changed" in receipt["error"]
    assert fake.get_track_send(vocal, 0) == pytest.approx(reverb_before, abs=1e-4)
    # The producer's own 40 % stays; rollback only reverses what the recipe wrote.
    assert fake.get_track_send(vocal, 1) == pytest.approx(0.4, abs=1e-4)
