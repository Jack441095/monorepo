"""Compound EQ requests use the same retained targets as ordinary parameter recipes."""
from __future__ import annotations

import copy
import json
import math

import pytest

from kenn.core.fake_live import FakeLiveBackend
from kenn.core.live_action_service import LiveActionService
from kenn.core.live_command import handle_command
from kenn.core.live_recipe import LiveRecipeService, RECIPE_SCHEMA
from kenn.tests.test_parameter_targets import _as_a_browser_echoes_it


class GuardedEqBackend(FakeLiveBackend):
    requires_guarded_parameter_targets = True

    def get_device_parameters(self, track_index, device_index):
        # Command resolution and addressed inspection must see the same synthetic control values.
        device = self._addressed_buses[0]["devices"][device_index]
        return {"success": True, "device_name": device["name"], "parameters": copy.deepcopy(device["parameters"])}

    def set_device_parameter(self, *args):
        raise AssertionError("Compound EQ must never use a positional parameter setter")


def frequency_raw(hz):
    """Use the existing EQ taper for synthetic fixtures, without qualifying a Live measurement."""
    # 10 Hz is raw zero; 2200 is the 10 Hz to 22 kHz endpoint ratio. User cards remain bounded to 20 Hz..20 kHz.
    return math.log(hz / 10) / math.log(2200)


@pytest.fixture
def eq(tmp_path, monkeypatch):
    from kenn.core import live_action_service, live_receipt_journal

    monkeypatch.setattr(live_action_service.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(live_receipt_journal, "JOURNAL_PATH", tmp_path / "receipts.jsonl")
    metadata = {"quantized": False, "is_enabled": True, "state": 0, "automation_state": 0, "macro_controlled": False}
    parameters = [
        {**metadata, "index": 6, "name": "1 Frequency A", "value": frequency_raw(250), "min": 0, "max": 1},
        {**metadata, "index": 17, "name": "1 Gain A", "value": 0.0, "min": -15, "max": 15},
    ]
    devices = [{"name": "EQ Eight", "parameters": copy.deepcopy(parameters)} for _ in range(2)]
    fixture = {"schema": "kenn.fake_live_fixture.v1", "session": {"tracks": [
        {"index": 0, "name": "Bus", "devices": [{"index": index, "name": "EQ Eight"} for index in range(2)]}]},
        "addressed_buses": [{"kind": "track", "index": 0, "name": "Bus", "devices": devices}]}
    path = tmp_path / "eq.json"
    path.write_text(json.dumps(fixture))
    backend = GuardedEqBackend(path)
    return backend, LiveActionService(backend), f"eq-{tmp_path.name}"


def plan(eq, **overrides):
    backend, service, session = eq
    frequency, gain = backend.get_device_parameters(0, 1)["parameters"]
    fields = {"track_index": 0, "track_name": "Bus", "device_index": 1, "device_name": "EQ Eight", "eq_band": "1A",
              "frequency_parameter": frequency, "frequency_before_hz": 250, "frequency_after_hz": 1000,
              "frequency_after_value": frequency_raw(1000), "gain_parameter": gain, "gain_after": 3,
              "reason": "Set the exact band to 1 kHz and +3 dB", "session_id": session}
    return service.propose_eq_band_tuning_gain(**{**fields, **overrides})


def apply(eq, card):
    # Compound EQ and its recipe Undo share the web card's JSON round trip.
    card = _as_a_browser_echoes_it(card)
    return eq[1].execute_eq_band_tuning_gain(card, confirm_token=card["confirmation_token"], session_id=eq[2])


def test_compound_eq_card_applies_and_undoes_only_the_selected_duplicate(eq):
    backend, service, session = eq
    original = copy.deepcopy(backend._addressed_buses[0]["devices"])
    card = plan(eq)["proposal"]
    assert card["schema"] == RECIPE_SCHEMA and backend.writes == []
    assert [child["parameter_index"] for child in card["steps"]] == [6, 17]
    assert [child["unit"] for child in card["steps"]] == ["hz", "db"]
    assert "Hz" in card["steps"][0]["after_display"] and "dB" in card["steps"][1]["after_display"]
    assert all(child["target_address"]["device_path"] == [1] for child in card["steps"])
    result = apply(eq, card)
    assert result["ok"] and result["receipt"]["verified"] and len(backend.writes) == 2
    assert backend._addressed_buses[0]["devices"][0] == original[0]
    inverse = LiveRecipeService(service).propose_undo(result["receipt"], session_id=session)
    assert inverse["ok"] and apply(eq, inverse["proposal"])["ok"]
    assert backend._addressed_buses[0]["devices"] == original and len(backend.writes) == 4
    assert not apply(eq, card)["ok"]


@pytest.mark.parametrize("gain", [-15.0, -3.0, 3.0, 15.0])
def test_compound_eq_native_db_gain_preserves_cuts_boosts_and_host_boundaries(eq, gain):
    backend, _, _ = eq
    card = plan(eq, gain_after=gain)["proposal"]
    assert card["steps"][1]["after"] == gain
    assert apply(eq, card)["ok"]
    assert backend._addressed_buses[0]["devices"][1]["parameters"][1]["value"] == gain


@pytest.mark.parametrize("change", ["wrong_band", "frequency_range", "gain_range", "missing_range", "nonfinite", "out_of_range"])
def test_compound_eq_refuses_unqualified_ranges_wrong_band_and_invalid_values(eq, change):
    backend, _, _ = eq
    frequency, gain = backend.get_device_parameters(0, 1)["parameters"]
    overrides = {}
    if change == "wrong_band":
        gain["name"] = "2 Gain A"
    elif change == "frequency_range":
        frequency.update(min=20, max=20000)
    elif change == "gain_range":
        gain.update(min=0, max=1)
    elif change == "missing_range":
        gain.pop("max")
    elif change == "nonfinite":
        overrides["frequency_after_hz"] = float("nan")
    else:
        overrides["gain_after"] = 16
    assert not plan(eq, frequency_parameter=frequency, gain_parameter=gain, **overrides)["ok"]
    assert backend.writes == []


def test_compound_eq_does_not_rebase_gain_when_it_moves_during_planning(eq, monkeypatch):
    # A relative gain resolved before fresh metadata must not silently become a different move.
    backend, _, _ = eq
    original = backend.get_addressed_parameter
    def move_before_guard(address, index, reference=None):
        if index == 17:
            backend._addressed_buses[0]["devices"][1]["parameters"][1]["value"] = 1.0
        return original(address, index, reference)
    monkeypatch.setattr(backend, "get_addressed_parameter", move_before_guard)
    assert not plan(eq)["ok"] and backend.writes == []


def test_compound_eq_refuses_a_host_gain_range_with_an_unknown_db_mapping(eq):
    # An observed 0..1 control is valid raw metadata but does not establish EQ Eight's native dB mapping.
    backend, _, _ = eq
    backend._addressed_buses[0]["devices"][1]["parameters"][1].update(min=0, max=1)
    assert not plan(eq, gain_after=0.5)["ok"] and backend.writes == []


@pytest.mark.parametrize("entry", ["addressed", "recipe", "flat"])
def test_single_eq_gain_cards_refuse_the_same_unqualified_host_range(eq, entry):
    # A global display profile must not let another card path apply 0.5 raw while calling it 0.5 dB.
    backend, service, session = eq
    backend._addressed_buses[0]["devices"][1]["parameters"][1].update(min=0, max=1)
    spec = {"action": "set_device_parameter", "address": {"kind": "track", "index": 0, "device_path": [1]},
            "device_name": "EQ Eight", "parameter_index": 17, "parameter": "1 Gain A", "value": 0.5, "unit": "dB"}
    if entry == "recipe":
        result = LiveRecipeService(service).propose_recipe([spec], reason="Explicit gain request", session_id=session)
    elif entry == "flat":
        result = service.propose_device_action(track_index=0, track_name="Bus", device_index=1, parameter_index=17,
                                               parameter_name="1 Gain A", proposed_value=0.5, unit="dB", reason="Explicit gain request", session_id=session)
    else:
        result = service.propose_addressed_parameter_action(address=spec["address"], parameter_index=17, value=0.5,
                                                            parameter_name="1 Gain A", device_name="EQ Eight", unit="dB", session_id=session)
    assert not result["ok"] and backend.writes == []


def test_compound_eq_refuses_an_observed_gain_from_another_band(eq):
    backend, _, _ = eq
    backend._addressed_buses[0]["devices"][1]["parameters"][1]["name"] = "2 Gain A"
    assert not plan(eq)["ok"] and backend.writes == []


def test_compound_eq_restores_frequency_when_gain_changes_before_its_write(eq):
    # Frequency may be verified before a stale second child refuses; only our frequency change is restored.
    backend, _, _ = eq
    card = plan(eq)["proposal"]
    device = backend._addressed_buses[0]["devices"][1]
    before = device["parameters"][0]["value"]
    device["parameters"][1]["value"] = 2.0
    result = apply(eq, card)
    assert not result["ok"] and result["receipt"]["status"] == "failed_rolled_back"
    assert device["parameters"][0]["value"] == before and device["parameters"][1]["value"] == 2.0
    assert len(backend.writes) == 2


def test_compound_eq_card_refuses_an_identical_replacement(eq):
    backend, _, _ = eq
    card = plan(eq)["proposal"]
    devices = backend._addressed_buses[0]["devices"]
    devices[1] = copy.deepcopy(devices[1])
    assert not apply(eq, card)["ok"] and backend.writes == []


def test_compound_eq_refuses_replacement_between_its_two_guarded_observations(eq, monkeypatch):
    # Matching names and raw values cannot join observations from two different EQ objects.
    backend, _, _ = eq
    original = backend.get_addressed_parameter
    def replace_after_frequency(address, index, reference=None):
        info = original(address, index, reference)
        if index == 6 and reference is None and info.get("success"):
            devices = backend._addressed_buses[0]["devices"]
            devices[1] = copy.deepcopy(devices[1])
        return info
    monkeypatch.setattr(backend, "get_addressed_parameter", replace_after_frequency)
    assert not plan(eq)["ok"] and backend.writes == []


def test_compound_eq_proposal_never_rediscovers_after_validating_its_original_observation(eq, monkeypatch):
    # A replacement after the retained reference is checked must leave a stale card, not gain a new approval.
    backend, _, _ = eq
    original = backend.get_addressed_parameter
    replaced = False
    def replace_after_check(address, index, reference=None):
        nonlocal replaced
        info = original(address, index, reference)
        if not replaced and index == 6 and reference and info.get("success"):
            devices = backend._addressed_buses[0]["devices"]
            devices[1] = copy.deepcopy(devices[1])
            replaced = True
        return info
    monkeypatch.setattr(backend, "get_addressed_parameter", replace_after_check)
    result = plan(eq)
    assert result["ok"]
    assert not apply(eq, result["proposal"])["ok"] and backend.writes == []


def test_compound_eq_refuses_when_retained_target_verification_loses_connection(eq, monkeypatch):
    # An inspection outage cannot establish that both controls still belong to the observed device.
    backend, _, _ = eq
    original = backend.get_addressed_parameter
    def disconnect_during_check(address, index, reference=None):
        if reference:
            raise OSError("inspection connection lost")
        return original(address, index, reference)
    monkeypatch.setattr(backend, "get_addressed_parameter", disconnect_during_check)
    result = plan(eq)
    assert not result["ok"] and "inspect it again" in result["error"] and backend.writes == []


def test_llm_compound_eq_candidate_returns_a_guarded_recipe_through_the_command_gateway(eq):
    backend, service, session = eq
    candidate = {"schema": "kenn.ableton_llm_plan.v1", "action": "set_eq_band_tuning_gain", "track_index": 0,
                 "track_name": "Bus", "device_index": 1, "device_name": "EQ Eight", "eq_band": "1A",
                 "frequency_hz": 1000, "value": 3, "relative": True, "unit": "dB"}
    result = handle_command("", session_id=session, service=service, llm_plan=candidate)
    assert result["status"] == "confirmation_required", result
    assert result["proposal_kind"] == "recipe" and result["proposal"]["schema"] == RECIPE_SCHEMA
    assert "Hz" in result["answer"] and "dB" in result["answer"] and backend.writes == []
    applied = handle_command("", session_id=session, service=service, proposal=result["proposal"], confirm_token=result["confirmation_token"])
    assert applied["changed"] and applied["receipt"]["verified"] and len(backend.writes) == 2
