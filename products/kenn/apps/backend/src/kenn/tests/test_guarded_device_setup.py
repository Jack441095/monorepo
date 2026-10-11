"""Production setup confirms insertion before granting authority over freshly observed controls."""
from __future__ import annotations

import copy
import json
import math

import pytest

from kenn.core.fake_live import FakeLiveBackend
from kenn.core.live_action_service import LiveActionService, DEVICE_INSERTION_PROPOSAL_SCHEMA
from kenn.core.live_command import handle_command
from kenn.core.live_recipe import LiveRecipeService, RECIPE_SCHEMA


class GuardedSetupBackend(FakeLiveBackend):
    requires_guarded_parameter_targets = True

    def insert_device_with_result(self, track_index, device_name, insertion_index):
        result = super().insert_device_with_result(track_index, device_name, insertion_index)
        if result.get("success"):
            # Keep synthetic addressed objects and positional inventory on the same newly inserted device.
            bus = next(row for row in self._addressed_buses if row["index"] == track_index)
            bus["devices"].insert(insertion_index, {
                "name": device_name, "parameters": self._devices[(track_index, insertion_index)]["parameters"],
            })
        return result

    def remove_device_with_result(self, track_index, device_index, device_name):
        result = super().remove_device_with_result(track_index, device_index, device_name)
        if result.get("success"):
            # The shared insertion Undo removes the synthetic object too; fixture bookkeeping is not a host write.
            next(row for row in self._addressed_buses if row["index"] == track_index)["devices"].pop(device_index)
        return result

    def set_device_parameter(self, *args):
        raise AssertionError("Production setup must not use a positional parameter setter")


@pytest.fixture
def setup(tmp_path, monkeypatch):
    from kenn.core import live_action_service, live_receipt_journal

    monkeypatch.setattr(live_action_service.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(live_receipt_journal, "JOURNAL_PATH", tmp_path / "receipts.jsonl")
    continuous = {"quantized": False, "is_enabled": True, "state": 0, "automation_state": 0, "macro_controlled": False}
    # Reuse the fixture taper: 10 Hz is raw zero and 2200 is the 10 Hz to 22 kHz endpoint ratio.
    eq_parameters = [
        {**continuous, "index": 4, "name": "2 Filter On A", "value": 0, "min": 0, "max": 1, "quantized": True},
        {**continuous, "index": 12, "name": "2 Frequency A", "value": math.log(250 / 10) / math.log(2200), "min": 0, "max": 1},
        {**continuous, "index": 21, "name": "2 Gain A", "value": 0, "min": -15, "max": 15},
    ]
    fixture = {"schema": "kenn.fake_live_fixture.v1", "session": {"tracks": [
        {"index": 0, "name": "Bus", "devices": []},
        {"index": 1, "name": "Templates", "devices": [{"index": 0, "name": "EQ Eight"}, {"index": 1, "name": "Hybrid Reverb"}]}]},
        "devices": {"1:0": {"device_name": "EQ Eight", "parameters": eq_parameters}, "1:1": {
            "device_name": "Hybrid Reverb", "parameters": [
                {**continuous, "index": 8, "name": "Dry/Wet", "value": 0.8, "min": 0, "max": 1}]}},
        "addressed_buses": [{"kind": "track", "index": 0, "name": "Bus", "devices": []}]}
    path = tmp_path / "setup.json"
    path.write_text(json.dumps(fixture))
    backend = GuardedSetupBackend(path)
    return backend, LiveActionService(backend), f"setup-{tmp_path.name}"


def plan(setup, kind="eq"):
    _, service, session = setup
    if kind == "reverb":
        return service.propose_device_setup_action(track_index=0, track_name="Bus", device_name="Hybrid Reverb",
            parameter_name="Dry/Wet", parameter_display_value=25, parameter_unit="%", session_id=session)
    return service.propose_eq_band_setup_action(track_index=0, track_name="Bus", eq_band="2A",
        frequency_hz=5000, gain_db=3, session_id=session)


def apply(setup, card, session=None):
    return handle_command("", session_id=session or setup[2], service=setup[1], proposal=card,
        confirm_token=card["confirmation_token"], allow_llm=False)


@pytest.mark.parametrize("kind,indices", [("eq", [4, 12, 21]), ("reverb", [8])])
def test_setup_needs_two_applies_and_each_verified_stage_has_its_own_undo(setup, kind, indices):
    backend, service, session = setup
    templates = copy.deepcopy(backend._devices)
    insertion = plan(setup, kind)["proposal"]
    assert insertion["schema"] == DEVICE_INSERTION_PROPOSAL_SCHEMA and "steps" not in insertion and backend.writes == []
    first = apply(setup, insertion)
    assert first["status"] == "applied" and first["changed"] and first["receipt"]["verified"]
    assert first["receipt"]["action"] == "insert_device" and len(backend.writes) == 1
    card = first["next_proposal"]
    assert card["schema"] == RECIPE_SCHEMA and [row["parameter_index"] for row in card["steps"]] == indices
    assert all(row["target_address"]["device_path"] == [0] for row in card["steps"])
    original = copy.deepcopy(backend._addressed_buses[0]["devices"])
    assert "parameters have not been changed" in first["next_proposal_answer"]
    assert "Apply it separately" in first["answer"]
    second = apply(setup, card)
    assert second["receipt"]["verified"] and len(backend.writes) == 1 + len(indices)
    undo = LiveRecipeService(service).propose_undo(second["receipt"], session_id=session)
    assert apply(setup, undo["proposal"])["receipt"]["verified"]
    assert backend._addressed_buses[0]["devices"] == original
    removal = service.propose_undo(first["receipt"], session_id=session)
    assert apply(setup, removal["proposal"])["receipt"]["verified"]
    assert backend._addressed_buses[0]["devices"] == [] and backend._devices == templates
    assert not apply(setup, insertion)["changed"] and not apply(setup, card)["changed"]


@pytest.mark.parametrize("field", ["name", "display_value", "unit"])
def test_insertion_confirmation_binds_its_deferred_configuration_intent(setup, field):
    # The held insertion token cannot be reused to smuggle a different follow-up control into the new card.
    backend, _, _ = setup
    card = copy.deepcopy(plan(setup)["proposal"])
    card["configuration_specs"][1][field] = {"name": "3 Frequency A", "display_value": 1000, "unit": "value"}[field]
    assert not apply(setup, card)["changed"] and backend.writes == []


def test_nonfinite_configuration_payload_refuses_before_insertion(setup):
    backend, _, _ = setup
    card = copy.deepcopy(plan(setup)["proposal"])
    card["configuration_specs"][1]["display_value"] = float("nan")
    assert not apply(setup, card)["changed"] and backend.writes == []


@pytest.mark.parametrize("change", ["missing", "duplicate", "unindexed", "unknown_range", "disabled", "automated", "macro", "enable_range", "enable_semantics"])
def test_failed_configuration_inspection_keeps_verified_insertion_without_writing_controls(setup, monkeypatch, change):
    backend, _, _ = setup
    parameters = backend._templates["EQ Eight"]["parameters"]
    if change == "missing":
        parameters.pop()
    elif change == "duplicate":
        # Ambiguous positional inventory must refuse even when the addressed target itself is unique.
        original = backend.get_device_parameters
        def duplicate_inventory(*args):
            info = copy.deepcopy(original(*args))
            info["parameters"].append({**info["parameters"][2], "index": 99})
            return info
        monkeypatch.setattr(backend, "get_device_parameters", duplicate_inventory)
    elif change == "unindexed":
        parameters[2].pop("index")
    elif change == "unknown_range":
        parameters[2].update(min=0, max=1)
    elif change == "disabled":
        parameters[2]["is_enabled"] = False
    elif change == "automated":
        parameters[2]["automation_state"] = 1
    elif change == "macro":
        parameters[2]["macro_controlled"] = True
    elif change == "enable_range":
        parameters[0]["max"] = 2
    else:
        parameters[0]["quantized"] = False
    first = apply(setup, plan(setup)["proposal"])
    assert first["changed"] and first["receipt"]["verified"] and first["receipt"]["configuration_status"] == "unavailable"
    assert "next_proposal" not in first and "parameters were not changed" in first["answer"]
    assert backend.writes == [("insert_device", 0, 0, "EQ Eight")]


def test_configuration_inspection_outage_does_not_erase_insertion_or_remove_it(setup, monkeypatch):
    backend, _, _ = setup
    monkeypatch.setattr(backend, "get_device_parameters", lambda *args: (_ for _ in ()).throw(OSError("lost inspection")))
    first = apply(setup, plan(setup)["proposal"])
    assert first["changed"] and first["receipt"]["verified"] and "next_proposal" not in first
    assert backend.writes == [("insert_device", 0, 0, "EQ Eight")]


def test_each_setup_confirmation_stays_in_its_project(setup):
    backend, _, _ = setup
    card = plan(setup)["proposal"]
    assert not apply(setup, card, session="another-project")["changed"] and backend.writes == []
    first = apply(setup, card)
    assert first["changed"] and not apply(setup, first["next_proposal"], session="another-project")["changed"]
    assert len(backend.writes) == 1


def test_configuration_card_refuses_an_identical_replacement_without_reinserting(setup):
    backend, _, _ = setup
    first = apply(setup, plan(setup)["proposal"])
    devices = backend._addressed_buses[0]["devices"]
    devices[0] = copy.deepcopy(devices[0])
    second = apply(setup, first["next_proposal"])
    assert not second["changed"] and backend.writes == [("insert_device", 0, 0, "EQ Eight")]


def test_configuration_recovery_preserves_a_manual_frequency_change(setup):
    backend, _, _ = setup
    first = apply(setup, plan(setup)["proposal"])
    parameters = backend._addressed_buses[0]["devices"][0]["parameters"]
    parameters[1]["value"] = 0.7
    second = apply(setup, first["next_proposal"])
    assert not second["changed"] and second["receipt"]["status"] == "failed_rolled_back"
    assert parameters[0]["value"] == 0 and parameters[1]["value"] == 0.7 and parameters[2]["value"] == 0
    assert [row[0] for row in backend.writes] == ["insert_device", "addressed_parameter", "addressed_parameter"]


def test_replacement_between_configuration_observations_withholds_the_second_card(setup, monkeypatch):
    # No parameter approval can combine the first enable observation with a replacement's frequency/gain.
    backend, _, _ = setup
    original = backend.get_addressed_parameter
    replaced = False
    def replace_after_enable(address, index, reference=None):
        nonlocal replaced
        info = original(address, index, reference)
        if not replaced and index == 4 and reference is None and info.get("success"):
            devices = backend._addressed_buses[0]["devices"]
            devices[0] = copy.deepcopy(devices[0])
            replaced = True
        return info
    monkeypatch.setattr(backend, "get_addressed_parameter", replace_after_enable)
    first = apply(setup, plan(setup)["proposal"])
    assert first["changed"] and "next_proposal" not in first and len(backend.writes) == 1


def test_single_configuration_construction_retains_its_first_observation(setup, monkeypatch):
    # Use one control so another stale child cannot mask rediscovery after a one-time replacement.
    backend, service, _ = setup
    original = service.propose_addressed_parameter_action
    def replace_before_wet(**kwargs):
        if kwargs["parameter_index"] == 8:
            devices = backend._addressed_buses[0]["devices"]
            devices[0] = copy.deepcopy(devices[0])
        return original(**kwargs)
    monkeypatch.setattr(service, "propose_addressed_parameter_action", replace_before_wet)
    first = apply(setup, plan(setup, "reverb")["proposal"])
    assert first["changed"] and not apply(setup, first["next_proposal"])["changed"] and len(backend.writes) == 1


@pytest.mark.parametrize("write_happened", [False, True])
def test_lost_insertion_acknowledgement_never_sends_insertion_twice(setup, monkeypatch, write_happened):
    backend, _, _ = setup
    original = backend.insert_device_with_result
    def lose_ack(*args):
        if write_happened:
            original(*args)
        return {"success": False, "error": "acknowledgement lost"}
    monkeypatch.setattr(backend, "insert_device_with_result", lose_ack)
    card = plan(setup)["proposal"]
    first = apply(setup, card)
    assert first["changed"] is write_happened
    assert ("next_proposal" in first) is write_happened
    assert not apply(setup, card)["changed"] and len(backend.writes) == int(write_happened)


@pytest.mark.parametrize("failure", ["lost_ack", "confirmed_ack", "write_exception", "attribute_exception", "missing_track", "missing_track_after_ack", "bookkeeping_failure"])
def test_unobservable_insertion_stays_unknown_without_a_configuration_card_or_retry(setup, monkeypatch, failure):
    # A device can be inserted before either acknowledgement or readback fails; false/no-change would invite duplication.
    backend, service, _ = setup
    original_insert, original_snapshot = backend.insert_device_with_result, service.snapshot
    def insert_without_observable_result(*args):
        result = original_insert(*args)
        if failure == "write_exception":
            raise OSError("acknowledgement transport failed after insertion")
        if failure == "attribute_exception":
            raise AttributeError("internal acknowledgement field missing after insertion")
        return result if failure in {"confirmed_ack", "missing_track_after_ack"} else {"success": False, "error": "acknowledgement lost"}
    def unavailable_after_dispatch(**kwargs):
        if backend.writes:
            if failure.startswith("missing_track"):
                return {"status": "online", "tracks": []}
            raise OSError("insertion readback unavailable")
        return original_snapshot(**kwargs)
    monkeypatch.setattr(backend, "insert_device_with_result", insert_without_observable_result)
    if failure == "attribute_exception":
        # A legacy fallback would append a second device after the first method already inserted one.
        monkeypatch.setattr(backend, "create_device", lambda track, name: original_insert(track, name, 1)["success"], raising=False)
    monkeypatch.setattr(service, "snapshot", unavailable_after_dispatch)
    if failure == "bookkeeping_failure":
        from kenn.core import live_command
        monkeypatch.setattr(live_command, "record_shadow_result", lambda _result: (_ for _ in ()).throw(OSError("log unavailable")))
    from kenn.routes import daw_command_handler
    monkeypatch.setattr(daw_command_handler, "action_allowed", lambda _action: True)
    monkeypatch.setattr(daw_command_handler, "_get_handle_command",
        lambda: lambda command, **kwargs: handle_command(command, service=service, **kwargs))
    class Handler:
        def send_json(self, status, body):
            self.status, self.body = status, body
    card = plan(setup)["proposal"]
    handler = Handler()
    daw_command_handler.handle_live_command(handler, None, {},
        {"session_id": setup[2], "proposal": card, "confirmation_token": card["confirmation_token"]})
    first = handler.body
    assert handler.status == 409
    assert first["status"] == "unknown" and first["changed"] is None
    assert first["receipt"]["status"] == "unknown" and not first["receipt"]["verified"]
    assert first["receipt"]["write_attempted"] and first["receipt"]["retry_safe"] == "requires_inspection"
    assert "outcome is unknown" in first["answer"] and "next_proposal" not in first
    assert not apply(setup, card)["changed"] and backend.writes == [("insert_device", 0, 0, "EQ Eight")]


@pytest.mark.parametrize("phase", ["insertion", "configuration"])
def test_read_only_setup_refuses_before_dispatch_and_does_not_claim_an_unknown_write(setup, phase):
    # An explicitly read-only provider never dispatched a mutation; its refusal must remain distinguishable from lost acknowledgement.
    backend, _, _ = setup
    card = plan(setup)["proposal"]
    if phase == "configuration":
        card = apply(setup, card)["next_proposal"]
    before_writes = list(backend.writes)
    backend.read_only = True
    result = apply(setup, card)
    assert result["status"] == "failed" and result["changed"] is False
    if phase == "insertion":
        assert result["receipt"]["status"] == "failed" and result["receipt"]["write_attempted"] is False
    else:
        # Recipes exclude pre-dispatch refusals from their completed steps; there is nothing to compensate.
        assert result["receipt"]["step_receipts"] == [] and result["receipt"]["status"] == "failed_rolled_back"
    assert "read-only" in result["answer"]
    assert backend.writes == before_writes


def test_insertion_uses_legacy_writer_only_when_the_result_api_is_absent(setup, monkeypatch):
    backend, _, _ = setup
    original = backend.insert_device_with_result
    monkeypatch.setattr(backend, "insert_device_with_result", None)
    monkeypatch.setattr(backend, "create_device", lambda track, name: original(track, name, 0)["success"], raising=False)
    first = apply(setup, plan(setup)["proposal"])
    assert first["changed"] and first["receipt"]["verified"] and first["next_proposal"]["schema"] == RECIPE_SCHEMA
    assert backend.writes == [("insert_device", 0, 0, "EQ Eight")]


def test_token_only_http_client_must_confirm_the_registered_configuration_card_separately(setup, monkeypatch):
    # Full-proposal clients worked while token-only HTTP clients could not resolve the returned second card.
    from kenn.routes import daw_command_handler

    backend, service, session = setup
    monkeypatch.setattr(daw_command_handler, "action_allowed", lambda _action: True)
    monkeypatch.setattr(daw_command_handler, "_get_handle_command",
        lambda: lambda command, **kwargs: handle_command(command, service=service, **kwargs))
    class Handler:
        def send_json(self, status, body):
            self.status, self.body = status, body
    handler, pending = Handler(), {}
    insertion = plan(setup)["proposal"]
    daw_command_handler.handle_live_command(handler, None, pending,
        {"session_id": session, "proposal": insertion, "confirmation_token": insertion["confirmation_token"]})
    assert handler.status == 200 and handler.body["receipt"]["verified"] and len(backend.writes) == 1
    card = handler.body["next_proposal"]
    assert pending[card["confirmation_token"]] == card and card["schema"] == RECIPE_SCHEMA
    daw_command_handler.handle_live_command(handler, None, pending,
        {"session_id": session, "confirmation_token": card["confirmation_token"]})
    assert handler.status == 200 and handler.body["status"] == "applied" and handler.body["receipt"]["verified"]
    assert [row[0] for row in backend.writes] == ["insert_device"] + ["addressed_parameter"] * 3


@pytest.mark.parametrize("command,device", [
    ("add an EQ to Bus and boost band 2A by 3 dB at 5 kHz", "EQ Eight"),
    ("add reverb to Bus at 25% dry wet", "Hybrid Reverb"),
])
def test_setup_command_gateway_explains_that_first_apply_only_inserts(setup, command, device):
    backend, service, session = setup
    result = handle_command(command, session_id=session, service=service, allow_llm=False)
    assert result["status"] == "confirmation_required" and result["proposal_kind"] == "device_insertion"
    assert result["proposal"]["device_name"] == device and "This Apply only inserts the device" in result["answer"]
    assert backend.writes == []
    first = apply(setup, result["proposal"])
    assert first["changed"] and first["next_proposal"]["schema"] == RECIPE_SCHEMA and len(backend.writes) == 1
