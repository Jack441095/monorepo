"""Switches and choosers are set by the label Live shows for them, from qualified option tables only."""

from __future__ import annotations

import json

import pytest

from kenn.core import device_units
from kenn.core.fake_live import FakeLiveBackend
from kenn.core.live_action_service import LiveActionService
from kenn.core.live_command import handle_command

PASSED = {"status": "passed", "points": 3, "qualified_at": "2026-09-30"}
MODEL = {"parameter": "Model", "options": [{"raw": 0, "label": "Peak"}, {"raw": 1, "label": "RMS"}, {"raw": 2, "label": "Expand"}], "qualification": PASSED}
AUTO_RELEASE = {"parameter": "Auto Release On/Off", "options": [{"raw": 0, "label": "Off"}, {"raw": 1, "label": "On"}], "qualification": PASSED}


@pytest.fixture()
def live(tmp_path, monkeypatch):
    monkeypatch.setenv("KENN_ALLOW_DAW_CONTROL", "1")
    monkeypatch.setenv("KENN_LIVE_RECEIPT_JOURNAL", str(tmp_path / "receipts.jsonl"))
    monkeypatch.setattr(device_units, "PROFILES_DIR", tmp_path)
    (tmp_path / "compressor.json").write_text(json.dumps({"device": "Compressor", "profiles": [], "choosers": [MODEL, AUTO_RELEASE]}), encoding="utf-8")
    device_units.reload_profiles()
    service = LiveActionService(FakeLiveBackend())

    def say(text, *, apply=False):
        result = handle_command(text, session_id="choosers", service=service, allow_llm=False)
        if apply and result.get("proposal"):
            proposal = result["proposal"]
            return handle_command(text, session_id="choosers", service=service, proposal=proposal,
                                  confirm_token=proposal["confirmation_token"], idempotency_key=str(proposal.get("action_id") or proposal.get("id") or ""), allow_llm=False)
        return result

    yield say, service
    monkeypatch.undo()
    device_units.reload_profiles()


@pytest.mark.parametrize("text, parameter, after", [
    ("set the Drum Bus compressor model to RMS", "Model", "RMS"),
    ("set the compressor model to expand on the drum bus", "Model", "Expand"),
    ("turn auto release on on the Drum Bus compressor", "Auto Release On/Off", "On"),
    ("turn on the auto release on the drum bus compressor", "Auto Release On/Off", "On"),
    ("enable auto release on the drum bus compressor", "Auto Release On/Off", "On"),
    ("set the drum bus compressor auto release to on", "Auto Release On/Off", "On"),
])
def test_a_qualified_chooser_is_set_by_its_label(live, text, parameter, after) -> None:
    say, _ = live
    result = say(text)
    assert result["status"] == "confirmation_required"
    assert result["proposal"]["parameter"] == parameter and result["proposal"]["after_label"] == after
    assert f"to {after}." in result["answer"] and "from " in result["answer"]


def test_asking_for_the_state_it_is_already_in_changes_nothing(live) -> None:
    say, _ = live
    assert "already Peak" in say("set the Drum Bus compressor model to Peak")["answer"]
    assert "already Off" in say("turn off the auto release on the drum bus compressor")["answer"]


@pytest.mark.parametrize("text", [
    "what is the compressor model set to on the drum bus",   # a question
    "set the drum bus compressor model to gate",             # not one of Live's options
    "set the drum bus compressor model",                     # no option named
    "turn the drum bus compressor off",                      # the device's own on/off is still not in the qualified set
    "bypass the drum bus compressor",
    "disable the vocal compressor",
])
def test_anything_that_is_not_a_clear_choice_changes_nothing(live, text) -> None:
    say, _ = live
    result = say(text)
    assert result["status"] != "confirmation_required" or "after_label" not in result["proposal"], result


def test_a_chooser_nobody_qualified_is_not_set(live, tmp_path) -> None:
    say, _ = live
    (tmp_path / "compressor.json").write_text(json.dumps({"device": "Compressor", "profiles": [], "choosers": [{**MODEL, "qualification": None}]}), encoding="utf-8")
    device_units.reload_profiles()
    assert say("set the Drum Bus compressor model to RMS")["status"] == "clarification_required"


def test_a_chooser_changes_in_live_reads_back_and_undoes(live) -> None:
    say, service = live
    applied = say("set the Drum Bus compressor model to RMS", apply=True)
    assert applied["status"] == "applied" and applied["receipt"]["verified"] is True
    assert next(p for p in service.client.get_device_parameters(3, 0)["parameters"] if p["name"] == "Model")["value"] == 1.0
    undo = service.propose_undo(applied["receipt"], session_id="choosers")
    assert undo["ok"] is True
    undone = handle_command("undo", session_id="choosers", service=service, proposal=undo["proposal"],
                            confirm_token=undo["proposal"]["confirmation_token"], idempotency_key=str(undo["proposal"].get("action_id") or undo["proposal"].get("id") or ""), allow_llm=False)
    assert undone["status"] == "applied" and undone["receipt"]["verified"] is True
    assert next(p for p in service.client.get_device_parameters(3, 0)["parameters"] if p["name"] == "Model")["value"] == 0.0


def test_choosers_load_only_from_a_passed_qualification(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(device_units, "PROFILES_DIR", tmp_path)
    bad = [{**MODEL, "qualification": {"status": "failed", "points": 3, "qualified_at": "x"}},
           {**MODEL, "parameter": "One", "options": [{"raw": 0, "label": "Only"}]},                       # a chooser needs two options
           {**MODEL, "parameter": "Dup", "options": [{"raw": 0, "label": "A"}, {"raw": 1, "label": "a"}]},  # labels must differ
           {**MODEL, "parameter": "Blank", "options": [{"raw": 0, "label": " "}, {"raw": 1, "label": "B"}]}]
    (tmp_path / "x.json").write_text(json.dumps({"device": "Compressor", "choosers": bad}), encoding="utf-8")
    device_units.reload_profiles()
    assert device_units.qualified_choices() == ()
    monkeypatch.undo()
    device_units.reload_profiles()
