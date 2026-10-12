"""Recipe children retain the same guarded target through Apply, recovery and Undo."""
from __future__ import annotations

import copy
import json

import pytest

from kenn.core.fake_live import FakeLiveBackend
from kenn.core.live_action_service import LiveActionService
from kenn.core.live_recipe import LiveRecipeService
from kenn.tests.test_parameter_targets import _as_a_browser_echoes_it


class GuardedRecipeBackend(FakeLiveBackend):
    requires_guarded_parameter_targets = True

    def get_device_parameters(self, track_index, device_index):
        # Both transport surfaces expose the same synthetic object; this is no measured Live metadata.
        device = self._addressed_buses[0]["devices"][device_index]
        return {"success": True, "device_name": device["name"], "parameters": copy.deepcopy(device["parameters"])}

    def set_device_parameter(self, *args):
        raise AssertionError("A guarded recipe must never use the positional setter")


@pytest.fixture
def guarded(tmp_path, monkeypatch):
    from kenn.core import live_action_service, live_receipt_journal

    monkeypatch.setattr(live_action_service.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(live_receipt_journal, "JOURNAL_PATH", tmp_path / "receipts.jsonl")
    parameter = {"index": 4, "name": "Drive", "value": 0.25, "min": 0, "max": 1,
                 "quantized": False, "is_enabled": True, "state": 0, "automation_state": 0, "macro_controlled": False}
    device = {"name": "Test Filter", "parameters": [parameter, {**parameter, "index": 9, "name": "Cutoff"}]}
    buses = [{"kind": kind, "index": 0, "name": "Bus", "devices": [copy.deepcopy(device), copy.deepcopy(device)]}
             for kind in ("track", "return", "master")]
    buses[0]["devices"].append({"name": "Instrument Rack", "chains": [{"name": "Bass", "devices": [
        {"name": "Audio Effect Rack", "chains": [{"name": "Filter", "devices": [copy.deepcopy(device)]}]}]}]})
    fixture = {"schema": "kenn.fake_live_fixture.v1", "session": {"tracks": [
        {"index": 0, "name": "Bus", "volume": 0.4, "devices": [{"name": "Test Filter"}, {"name": "Test Filter"}]}]},
        "addressed_buses": buses}
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(fixture))
    backend = GuardedRecipeBackend(path)
    return backend, LiveRecipeService(LiveActionService(backend)), f"guarded-{tmp_path.name}"


def step(*, kind="track", path=None, index=4, name="Drive", value=0.75):
    return {"action": "set_device_parameter", "address": {"kind": kind, "index": 0, "device_path": path or [1]},
            "device_name": "Test Filter", "parameter_index": index, "parameter": name, "value": value, "unit": "raw"}


def propose(guarded, steps=None):
    backend, recipes, session = guarded
    result = recipes.propose_recipe(steps or [step()], reason="Explicit test recipe", session_id=session)
    assert result["ok"], result
    assert backend.writes == []
    return result["proposal"]


def execute(guarded, card):
    # Apply and Undo echo the card through browser JSON, where integral floats lose their decimal point.
    card = _as_a_browser_echoes_it(card)
    return guarded[1].execute_recipe(card, confirm_token=card["confirmation_token"], session_id=guarded[2])


@pytest.mark.parametrize("kind,path", [("track", [1]), ("return", [1]), ("master", [1]), ("track", [2, 0, 0, 0, 0])])
def test_guarded_recipe_applies_and_undoes_the_same_bus_or_rack_parameter(guarded, kind, path):
    backend, recipes, session = guarded
    card = propose(guarded, [step(kind=kind, path=path)])
    result = execute(guarded, card)
    assert result["ok"] and result["receipt"]["verified"]
    assert backend.writes == [("addressed_parameter", card["steps"][0]["target_address"], 4, 0.75)]
    child_receipt = result["receipt"]["step_receipts"][0]
    assert child_receipt["target"]["observation_token"] == card["steps"][0]["observation_token"]
    inverse = recipes.propose_undo(result["receipt"], session_id=session)
    assert inverse["ok"], inverse
    assert execute(guarded, inverse["proposal"])["receipt"]["verified"]
    assert backend.get_addressed_parameter(card["steps"][0]["target_address"], 4)["parameters"][0]["value"] == 0.25
    assert len(backend.writes) == 2
    assert not execute(guarded, card)["ok"]


def test_existing_flat_recipe_spec_is_upgraded_to_a_guarded_parameter(guarded):
    card = propose(guarded, [{"action": "set_device_parameter", "track_index": 0, "track_name": "Bus",
                             "device_index": 1, "parameter_index": 4, "parameter": "Drive", "value": 0.75}])
    assert card["steps"][0]["target_address"] == {"kind": "track", "index": 0, "device_path": [1]}
    assert execute(guarded, card)["receipt"]["verified"]


def test_recipe_undo_cannot_rewrite_ownership_or_drop_its_guarded_steps(guarded):
    # Editing the parent used to evade session checks by changing its owner or replacing all device children.
    backend, recipes, session = guarded
    receipt = execute(guarded, propose(guarded))["receipt"]
    echoed = _as_a_browser_echoes_it(receipt)
    echoed["session_id"] = "another-project"
    assert not recipes.propose_undo(echoed, session_id="another-project")["ok"]
    echoed["session_id"] = session
    echoed["step_receipts"] = [{"action": "set_volume", "target": {"track_index": 0, "track_name": "Bus"},
                               "before": 0.1, "readback": 0.4}]
    assert not recipes.propose_undo(echoed, session_id=session)["ok"]
    assert len(backend.writes) == 1


def test_recipe_undo_recovers_recorded_children_from_the_journal(guarded):
    # Only the parent is journalled; children must retain the same recorded owner when memory is cleared.
    from kenn.core.actions import _RECEIPTS
    from kenn.core import live_receipt_journal as journal

    backend, recipes, session = guarded
    receipt = execute(guarded, propose(guarded))["receipt"]
    assert journal.record_receipt(receipt, session_id=session)
    _RECEIPTS.pop(receipt["receipt_id"])
    for child in receipt["step_receipts"]:
        _RECEIPTS.pop(child["receipt_id"])
    echoed = journal.list_receipts(session_id=session)[0]["receipt"]
    assert not recipes.propose_undo(echoed, session_id="another-project")["ok"]
    inverse = recipes.propose_undo(echoed, session_id=session)
    assert inverse["ok"], inverse
    assert execute(guarded, inverse["proposal"])["receipt"]["verified"]
    assert len(backend.writes) == 2


@pytest.mark.parametrize("field,value", [("target_address", {"kind": "master", "index": 0, "device_path": [1]}),
                                        ("observation_token", "replacement"), ("topology", "replacement"),
                                        ("parameter_guard", {}), ("after_display", "invented display"),
                                        ("valid_range", [-10, 10]), ("after", 0.9)])
def test_recipe_confirmation_binds_guarded_target_semantics_and_readable_values(guarded, field, value):
    # The previous parent token omitted these fields, allowing a card to change its approved target or display.
    card = propose(guarded)
    card["steps"][0][field] = value
    assert not execute(guarded, card)["ok"]
    assert guarded[0].writes == []


def test_recipe_refuses_nonfinite_confirmation_without_leaving_an_inflight_key(guarded):
    backend, recipes, session = guarded
    card = propose(guarded)
    original = copy.deepcopy(card)
    card["steps"][0]["after"] = float("nan")
    assert "invalid" in execute(guarded, card)["error"]
    assert backend.writes == []
    assert execute(guarded, original)["ok"]


def test_guarded_recipe_requires_the_original_session_and_parent_confirmation(guarded):
    backend, recipes, session = guarded
    card = propose(guarded)
    assert not recipes.execute_recipe(card, confirm_token="", session_id=session)["ok"]
    assert not recipes.execute_recipe(card, confirm_token=card["confirmation_token"], session_id="another-project")["ok"]
    assert backend.writes == []


def test_replaced_parameter_refuses_before_any_device_write_and_restores_prior_mixer_step(guarded):
    backend, recipes, session = guarded
    card = propose(guarded, [{"action": "set_volume", "track_index": 0, "value": 0.6}, step()])
    bus = backend._addressed_buses[0]
    bus["devices"][1] = copy.deepcopy(bus["devices"][1])
    result = execute(guarded, card)
    assert result["status"] == "failed_rolled_back"
    assert backend._session["tracks"][0]["volume"] == 0.4
    assert all(write[0] != "addressed_parameter" for write in backend.writes)


def test_later_stale_parameter_restores_only_the_verified_guarded_step(guarded):
    backend, recipes, session = guarded
    card = propose(guarded, [step(), step(index=9, name="Cutoff")])
    parameters = backend._addressed_buses[0]["devices"][1]["parameters"]
    parameters[1]["value"] = 0.5
    result = execute(guarded, card)
    assert result["status"] == "failed_rolled_back" and result["rollback"] == [True]
    assert [write[-1] for write in backend.writes] == [0.75, 0.25]
    assert [parameter["value"] for parameter in parameters] == [0.25, 0.5]


def test_recipe_does_not_retry_or_undo_an_unknown_guarded_write(guarded, monkeypatch):
    backend, recipes, session = guarded
    card = propose(guarded)
    original = backend.get_addressed_parameter
    def unavailable_after_write(*args, **kwargs):
        if backend.writes:
            raise OSError("Synthetic lost readback")
        return original(*args, **kwargs)
    monkeypatch.setattr(backend, "get_addressed_parameter", unavailable_after_write)
    result = execute(guarded, card)
    assert result["status"] == "partial_recovery" and result["rollback"] == [False]
    assert result["receipt"]["step_receipts"][0]["status"] == "unknown"
    assert len(backend.writes) == 1 and backend.writes[0][-1] == 0.75
    assert not recipes.propose_undo(result["receipt"], session_id=session)["ok"]


def test_recipe_rollback_preserves_a_manual_edit_to_an_earlier_verified_step(guarded, monkeypatch):
    # A later failure must not restore over a producer edit made after the first step's readback.
    backend, recipes, session = guarded
    card = propose(guarded, [step(), step(index=9, name="Cutoff")])
    parameters = backend._addressed_buses[0]["devices"][1]["parameters"]
    original = backend.get_addressed_parameter
    def edit_before_later_step(address, index, reference=None):
        if index == 9 and backend.writes:
            parameters[0]["value"] = 0.6
            parameters[1]["value"] = 0.5
        return original(address, index, reference)
    monkeypatch.setattr(backend, "get_addressed_parameter", edit_before_later_step)
    result = execute(guarded, card)
    assert result["status"] == "partial_recovery" and result["rollback"] == [False]
    assert len(backend.writes) == 1 and parameters[0]["value"] == 0.6


@pytest.mark.parametrize("change", ["mixer", "rename", "transport"])
def test_mixed_recipe_rollback_preserves_manual_mixer_transport_and_target_changes(guarded, monkeypatch, change):
    backend, recipes, session = guarded
    if change == "transport":
        # FakeLiveBackend stores transport state without logging it; record calls to detect a blind restore.
        for method in ("start_playback", "stop_playback"):
            original_writer = getattr(backend, method)
            def recorded_writer(original_writer=original_writer, method=method):
                backend.writes.append((method,))
                return original_writer()
            monkeypatch.setattr(backend, method, recorded_writer)
    first = {"action": "transport_play"} if change == "transport" else {"action": "set_volume", "track_index": 0, "value": 0.6}
    card = propose(guarded, [first, step()])
    original = backend.get_addressed_parameter
    def change_before_parameter(address, index, reference=None):
        if backend.writes:
            if change == "mixer":
                backend._session["tracks"][0]["volume"] = 0.8
            elif change == "rename":
                backend._session["tracks"][0]["name"] = "Replacement track"
            else:
                backend._session["is_playing"] = False
            backend._addressed_buses[0]["devices"][1]["parameters"][0]["value"] = 0.5
        return original(address, index, reference)
    monkeypatch.setattr(backend, "get_addressed_parameter", change_before_parameter)
    result = execute(guarded, card)
    assert result["status"] == "partial_recovery" and result["rollback"] == [False]
    assert len(backend.writes) == 1


def test_recipe_verifies_a_lost_acknowledgement_without_repeating_the_setter(guarded, monkeypatch):
    backend, recipes, session = guarded
    card = propose(guarded)
    original = backend.set_addressed_parameter
    def lose_ack(*args, **kwargs):
        assert original(*args, **kwargs)
        raise OSError("Synthetic lost acknowledgement")
    monkeypatch.setattr(backend, "set_addressed_parameter", lose_ack)
    result = execute(guarded, card)
    assert result["receipt"]["verified"] and len(backend.writes) == 1
    assert result["receipt"]["step_receipts"][0]["write_acknowledgement"] == "unacknowledged_write_reconciled"


@pytest.mark.parametrize("change", ["manual", "replace", "session"])
def test_guarded_recipe_undo_refuses_manual_edits_replacements_and_other_projects(guarded, change):
    backend, recipes, session = guarded
    card = propose(guarded)
    receipt = execute(guarded, card)["receipt"]
    device = backend._addressed_buses[0]["devices"][1]
    if change == "manual":
        device["parameters"][0]["value"] = 0.6
    elif change == "replace":
        backend._addressed_buses[0]["devices"][1] = copy.deepcopy(device)
    else:
        session = "another-project"
    assert not recipes.propose_undo(receipt, session_id=session)["ok"]
    assert len(backend.writes) == 1


def test_guarded_recipe_undo_card_cannot_rebind_after_its_original_object_is_checked(guarded, monkeypatch):
    # Re-proposing by position after receipt validation would let an identical replacement inherit Undo.
    backend, recipes, session = guarded
    card = propose(guarded)
    receipt = execute(guarded, card)["receipt"]
    original = backend.get_addressed_parameter
    replaced = False
    def replace_after_check(address, index, reference=None):
        nonlocal replaced
        info = original(address, index, reference)
        if reference and info.get("success") and not replaced:
            bus = backend._addressed_buses[0]
            bus["devices"][1] = copy.deepcopy(bus["devices"][1])
            replaced = True
        return info
    monkeypatch.setattr(backend, "get_addressed_parameter", replace_after_check)
    inverse = recipes.propose_undo(receipt, session_id=session)
    assert inverse["ok"]
    assert not execute(guarded, inverse["proposal"])["ok"]
    assert len(backend.writes) == 1


def test_mixer_only_recipe_undo_cannot_cross_project_sessions(guarded):
    # Mixer children have no device receipt guard; the parent must bind their Undo to the project.
    backend, recipes, _session = guarded
    card = propose(guarded, [{"action": "set_volume", "track_index": 0, "value": 0.6}])
    receipt = execute(guarded, card)["receipt"]
    assert not recipes.propose_undo(receipt, session_id="another-project")["ok"]
    assert len(backend.writes) == 1


def test_guarded_recipe_apply_uses_the_existing_http_command_gateway(guarded, monkeypatch):
    from functools import partial
    from kenn.core.live_command import handle_command
    from kenn.routes import daw_command_handler, daw_routes

    backend, recipes, session = guarded
    card = propose(guarded)
    monkeypatch.setenv("KENN_ALLOW_DAW_CONTROL", "1")
    monkeypatch.setattr(daw_command_handler, "_get_handle_command", lambda: partial(handle_command, service=recipes.service))
    status, result = daw_routes.handle_live_command(
        {"session_id": session, "proposal": card, "confirm_token": card["confirmation_token"]}, pending_proposals={},
    )
    assert status == 200 and result["receipt"]["verified"]
    assert len(backend.writes) == 1
