"""What a change does when Live misbehaves: never "applied" unless Live confirms, and never left half-done.

A fake Live with faults injected at the boundary: a write Live refuses, one that times out, one it acknowledges but
never applies, one that lands on another value; Live going offline or being changed by hand between the proposal and
Apply; a replayed, altered, expired or pre-restart confirmation; an undo after the fader moved; a recipe that fails
on its second step.
"""

from __future__ import annotations

import secrets
import types

import pytest

from kenn.core import confirmation
from kenn.core.fake_live import FakeLiveBackend
from kenn.core.live_action_service import LiveActionService
from kenn.core.live_command import handle_command


class FaultyLive:
    """FakeLiveBackend with named methods replaced by a fault, and a log of every call made to it."""

    def __init__(self) -> None:
        self.real = FakeLiveBackend()
        self.faults: dict = {}
        self.calls: list[str] = []

    def __getattr__(self, name):
        target = getattr(self.real, name)
        if not callable(target):
            return target

        def call(*args, **kwargs):
            self.calls.append(name)
            fault = self.faults.get(name)
            return fault(target, *args, **kwargs) if fault else target(*args, **kwargs)

        return call

    def writes(self, method: str) -> int:
        return self.calls.count(method)

    def track(self, name: str) -> dict:
        return next(t for t in self.real.query_session_state()["tracks"] if t["name"] == name)


def refused(real, *args, **kwargs):
    return False


def times_out(real, *args, **kwargs):
    raise TimeoutError("OSC timeout")


def acknowledged_but_dropped(real, *args, **kwargs):
    return True


@pytest.fixture()
def rig(monkeypatch, tmp_path):
    from kenn.core import live_receipt_journal

    monkeypatch.setattr(live_receipt_journal, "JOURNAL_PATH", tmp_path / "receipts.jsonl")
    monkeypatch.setenv("KENN_ALLOW_DAW_CONTROL", "1")
    for name in ("KENN_LIVE_LLM_ENABLED", "KENN_LLM_ENABLED", "KENN_LLM_ENABLED_COMMAND"):
        monkeypatch.delenv(name, raising=False)
    live = FaultyLive()
    service = LiveActionService(live)

    class Rig:
        def __init__(self) -> None:
            self.live, self.service = live, service

        def propose(self, text):
            return handle_command(text, session_id="chaos", service=self.service, allow_llm=False)

        def apply(self, text, proposed, service=None):
            proposal = proposed["proposal"]
            return handle_command(text, session_id="chaos", service=service or self.service, proposal=proposal,
                                  confirm_token=proposal.get("confirmation_token", ""),
                                  idempotency_key=str(proposal.get("action_id") or proposal.get("id") or ""), allow_llm=False)

    return Rig()


# text, the backend write method, how to read the value back, a value Live might land on instead
CASES = {
    "volume": ("set the bass to -6 dB", "set_track_volume", lambda live: live.track("Bass")["volume"], lambda v: v * 0.5 + 0.1),
    "pan": ("pan the bass 30% left", "set_track_pan", lambda live: live.track("Bass")["pan"], lambda v: v + 0.5),
    "mute": ("mute the bass", "set_track_mute", lambda live: live.track("Bass")["muted"], None),
    "solo": ("solo the bass", "set_track_solo", lambda live: live.track("Bass")["soloed"], None),
    "arm": ("arm the bass", "set_track_arm", lambda live: live.track("Bass")["armed"], None),
    "rename": ("rename the synth to Pads", "set_track_name", lambda live: live.real.query_session_state()["tracks"][5]["name"], lambda v: f"{v}!"),
    "send": ("send the bass to the reverb at 30%", "set_track_send", lambda live: live.real.get_track_send(4, 0), lambda v: v * 0.5),
    "device": ("set the Drum Bus compressor threshold to -20 dB", "set_device_parameter",
               lambda live: next(p for p in live.real.get_device_parameters(3, 0)["parameters"] if p["name"] == "Threshold")["value"],
               lambda v: v * 0.5 + 0.1),
}


def proposal_and_before(rig, name):
    text, method, read, _ = CASES[name]
    proposed = rig.propose(text)
    assert proposed["status"] == "confirmation_required", proposed.get("answer")
    return text, method, read, proposed, read(rig.live)


@pytest.mark.parametrize("fault", [refused, times_out, acknowledged_but_dropped], ids=lambda f: f.__name__)
@pytest.mark.parametrize("name", CASES)
def test_a_write_live_does_not_take_is_never_reported_as_applied(rig, name, fault) -> None:
    text, method, read, proposed, before = proposal_and_before(rig, name)
    rig.live.faults[method] = fault
    result = rig.apply(text, proposed)
    assert result["status"] != "applied" and (result.get("receipt") or {}).get("verified") is not True
    assert read(rig.live) == before


@pytest.mark.parametrize("name", [n for n, case in CASES.items() if case[3]])
def test_a_write_that_lands_on_another_value_is_put_back_and_says_so(rig, name) -> None:
    # Regression (chaos probe, 29 Sept): the change was reported as failed but Live was left at the odd value.
    text, method, read, proposed, before = proposal_and_before(rig, name)
    wrong, first = CASES[name][3], {"done": False}

    def lands_elsewhere_once(real, *args, **kwargs):   # Live clamps this write; a later write of a valid value is fine
        if first["done"]:
            return real(*args, **kwargs)
        first["done"] = True
        return real(*args[:-1], wrong(args[-1]))

    rig.live.faults[method] = lands_elsewhere_once
    result = rig.apply(text, proposed)
    receipt = result.get("receipt") or {}
    assert result["status"] != "applied" and receipt.get("verified") is not True
    assert read(rig.live) == pytest.approx(before) if name == "device" else read(rig.live) == before
    assert receipt["restore"]["restored"] is True and "put it back" in result["answer"]


def test_when_the_restore_also_fails_it_says_where_live_is_and_asks_for_a_look(rig) -> None:
    text, method, read, proposed, before = proposal_and_before(rig, "volume")
    rig.live.faults[method] = lambda real, index, value: real(index, 0.3)   # every write lands on 0.3, including the restore
    result = rig.apply(text, proposed)
    receipt = result["receipt"]
    assert receipt["restore"]["restored"] is False and receipt["retry_safe"] == "requires_inspection"
    assert "couldn't put it back" in result["answer"] and read(rig.live) == pytest.approx(0.3)


def test_a_readback_that_fails_after_the_write_is_flagged_for_inspection(rig) -> None:
    text, _, _, proposed, _ = proposal_and_before(rig, "mute")
    seen = {"n": 0}

    def readback_dies(real, *args, **kwargs):
        seen["n"] += 1
        if seen["n"] > 1:   # the first read is the pre-write check inside Apply
            raise ConnectionError("Live went away")
        return real(*args, **kwargs)

    rig.live.faults["query_session_state"] = readback_dies
    result = rig.apply(text, proposed)
    assert result["status"] != "applied" and result["receipt"]["retry_safe"] == "requires_inspection"


def test_live_going_offline_between_the_proposal_and_apply_writes_nothing(rig) -> None:
    text, method, _, proposed, _ = proposal_and_before(rig, "mute")
    rig.live.faults["query_session_state"] = lambda real, *a, **k: {"status": "offline", "tracks": []}
    result = rig.apply(text, proposed)
    assert result["status"] == "failed" and rig.live.writes(method) == 0


@pytest.mark.parametrize("name", ["mute", "volume", "pan", "send"])
def test_a_change_made_by_hand_after_the_proposal_makes_it_stale_and_writes_nothing(rig, name) -> None:
    text, method, read, proposed, before = proposal_and_before(rig, name)
    hand = {"mute": lambda: rig.live.real.set_track_mute(4, True), "volume": lambda: rig.live.real.set_track_volume(4, 0.2),
            "pan": lambda: rig.live.real.set_track_pan(4, 0.9), "send": lambda: rig.live.real.set_track_send(4, 0, 0.9)}[name]
    hand()
    result = rig.apply(text, proposed)
    assert result["status"] == "failed" and rig.live.writes(method) == 0 and read(rig.live) != before


def test_a_replayed_confirmation_writes_once(rig) -> None:
    text, method, _, proposed, _ = proposal_and_before(rig, "mute")
    assert rig.apply(text, proposed)["status"] == "applied"
    again = rig.apply(text, proposed)
    assert again["status"] == "failed" and rig.live.writes(method) == 1


@pytest.mark.parametrize("tamper", [
    lambda p: p.update(after=not p["after"]),
    lambda p: p.update(track_index=(p["track_index"] + 1) % 8),
    lambda p: p.update(confirmation_token="not-a-token"),
    lambda p: p.pop("confirmation_token"),
], ids=["changed value", "changed track", "made-up token", "no token"])
def test_an_altered_or_unsigned_proposal_writes_nothing(rig, tamper) -> None:
    text, method, _, proposed, before = proposal_and_before(rig, "mute")
    tamper(proposed["proposal"])
    result = rig.apply(text, proposed)
    assert result["status"] in {"failed", "requires_confirmation"} and rig.live.writes(method) == 0


def test_a_confirmation_from_before_a_companion_restart_is_dead(rig, monkeypatch) -> None:
    text, method, _, proposed, _ = proposal_and_before(rig, "mute")
    monkeypatch.setattr(confirmation, "_PROCESS_SECRET", secrets.token_bytes(32))   # what a new process starts with
    monkeypatch.setattr(confirmation, "_USED_TOKENS", set())
    result = rig.apply(text, proposed, service=LiveActionService(rig.live))
    assert result["status"] == "failed" and rig.live.writes(method) == 0


def test_an_expired_confirmation_is_dead(rig, monkeypatch) -> None:
    text, method, _, proposed, _ = proposal_and_before(rig, "mute")
    real_time = confirmation.time.time
    monkeypatch.setattr(confirmation, "time", types.SimpleNamespace(time=lambda: real_time() + confirmation.DEFAULT_TTL_SECONDS + 60))
    result = rig.apply(text, proposed)
    assert result["status"] == "failed" and rig.live.writes(method) == 0


def test_no_proposal_is_made_when_live_is_unreachable_or_returns_nonsense(rig) -> None:
    for broken in (lambda real, *a, **k: {"status": "offline", "tracks": []},
                   lambda real, *a, **k: {"status": "connected", "tracks": [{"index": 4}]},
                   times_out):
        rig.live.faults["query_session_state"] = broken
        result = rig.propose("mute the bass")
        assert result["status"] != "confirmation_required" and not result.get("proposal")
    assert not any(call.startswith("set_") for call in rig.live.calls)


def test_undo_is_refused_once_the_fader_has_been_moved_by_hand(rig) -> None:
    text, _, _, proposed, _ = proposal_and_before(rig, "volume")
    applied = rig.apply(text, proposed)
    rig.live.real.set_track_volume(4, 0.3)
    undo = rig.service.propose_undo(applied["receipt"], session_id="chaos")
    assert undo["ok"] is False and rig.live.track("Bass")["volume"] == pytest.approx(0.3)


def test_an_undo_can_only_be_done_once(rig) -> None:
    text, _, read, proposed, before = proposal_and_before(rig, "volume")
    applied = rig.apply(text, proposed)
    undo = rig.service.propose_undo(applied["receipt"], session_id="chaos")
    proposal = undo["proposal"]
    args = dict(session_id="chaos", service=rig.service, proposal=proposal, confirm_token=proposal["confirmation_token"],
                idempotency_key=str(proposal.get("action_id") or proposal.get("id") or ""), allow_llm=False)
    assert handle_command("undo", **args)["status"] == "applied" and read(rig.live) == pytest.approx(before)
    assert handle_command("undo", **args)["status"] == "failed"
    assert rig.service.propose_undo(applied["receipt"], session_id="chaos")["ok"] is False


def test_a_recipe_that_fails_on_its_second_step_restores_the_first(rig) -> None:
    proposed = rig.propose("mute the bass and mute the hats")
    assert proposed["proposal"]["schema"].endswith("recipe_proposal.v1")
    writes = {"n": 0}

    def second_write_fails(real, *args, **kwargs):
        writes["n"] += 1
        return False if writes["n"] == 2 else real(*args, **kwargs)

    rig.live.faults["set_track_mute"] = second_write_fails
    result = rig.apply("mute the bass and mute the hats", proposed)
    assert result["status"] != "applied" and result["receipt"]["rolled_back"] is True
    assert rig.live.track("Bass")["muted"] is False and rig.live.track("Hi-Hats")["muted"] is False
