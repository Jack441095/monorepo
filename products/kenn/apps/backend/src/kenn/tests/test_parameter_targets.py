"""Observed targets must survive proposal, Apply, readback and Undo unchanged."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from kenn.core.fake_live import FakeLiveBackend
from kenn.core.live_action_service import LiveActionService
from kenn.core.parameter_contract import indexed_parameter, validate_parameter
from kenn.routes import daw_routes

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "tooling/scripts"))
from qualify_parameter_targets import qualify
from recheck_recipes_fake import recheck


@pytest.fixture
def target(tmp_path):
    parameter = {"index": 4, "name": "Drive", "value": 0.25, "min": 0, "max": 1,
                 "quantized": False, "is_enabled": True, "state": 0,
                 "automation_state": 0, "macro_controlled": False}
    device = {"name": "Test Filter", "parameters": [parameter]}
    buses = [{"kind": kind, "index": 0, "name": "Duplicate", "devices": [copy.deepcopy(device), copy.deepcopy(device)]}
             for kind in ("track", "return", "master")]
    root = copy.deepcopy(device)
    for name in reversed(("Instrument Rack", "Audio Effect Rack", "MIDI Effect Rack", "Drum Rack")):
        root = {"name": name, "chains": [{"name": "Bass", "devices": [root]}]}
    buses[0]["devices"].append(root)
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps({"schema": "kenn.fake_live_fixture.v1", "session": {"tracks": []}, "addressed_buses": buses}))
    backend = FakeLiveBackend(path)
    return backend, LiveActionService(backend)


def candidate(service, *, kind="track", path=None, value=0.75, unit="raw", session="target-tests", **kwargs):
    return service.propose_addressed_parameter_action(
        address={"kind": kind, "index": 0, "device_path": path or [1]}, parameter_index=4,
        parameter_name="Drive", device_name="Test Filter", value=value, unit=unit, session_id=session, **kwargs)


def apply(service, proposal, session="target-tests"):
    return service.execute_device_action(proposal, confirm_token=proposal["confirmation_token"], session_id=session)


def test_existing_fifteen_recipe_commands_restore_mixer_and_device_state():
    # Insertion Undo must remove the device too; comparing only faders would miss a leaked Glue Compressor.
    report = recheck()
    assert report["passed"] == report["total"] == 15
    assert report["live_writes"] == 0 and report["model_run"] is False
    assert all(row["fake_writes"] > 0 and row["restored_to_baseline"] for row in report["recipes"])


@pytest.mark.parametrize("kind,path", [("track", [1]), ("return", [1]), ("master", [1]), ("track", [2, 0, 0, 0, 0, 0, 0, 0, 0])])
def test_duplicate_named_target_is_verified_and_exactly_undone(target, kind, path):
    backend, service = target
    proposal = candidate(service, kind=kind, path=path)["proposal"]
    assert backend.writes == []
    assert proposal["target_label"].endswith("Test Filter / Drive")
    result = apply(service, proposal)
    assert result["receipt"]["verified"] is True
    assert backend.writes == [("addressed_parameter", proposal["target_address"], 4, 0.75)]
    assert not apply(service, proposal)["ok"]
    inverse = service.propose_undo(result["receipt"], session_id="target-tests")["proposal"]
    assert apply(service, inverse)["receipt"]["verified"] is True
    assert backend.get_addressed_parameter(proposal["target_address"], 4)["parameters"][0]["value"] == 0.25
    assert len(backend.writes) == 2


@pytest.mark.parametrize("change", ["replace", "rename", "reorder", "remove", "reload", "expire"])
def test_apply_refuses_identical_replacements_and_stale_topology(target, change):
    # A replacement with identical names and values must not inherit the old object's authority.
    backend, service = target
    proposal = candidate(service)["proposal"]
    bus = backend._addressed_buses[0]
    if change == "replace":
        bus["devices"][1] = copy.deepcopy(bus["devices"][1])
    elif change == "rename":
        bus["name"] = "Renamed"
    elif change == "reorder":
        bus["devices"].reverse()
    elif change == "remove":
        del bus["devices"][1]
    elif change == "reload":
        backend._target_observations.clear()
    else:
        backend._target_observations[proposal["observation_token"]]["expires"] = 0
    assert not apply(service, proposal)["ok"]
    assert backend.writes == []


@pytest.mark.parametrize("field,value", [("device_name", "Imaginary"), ("parameter", "Imaginary"), ("before", 0.5),
                                         ("unit", "dB"), ("valid_range", [0, 2]), ("target_label", "Wrong target"), ("after_label", "Wrong option"),
                                         ("before_display", "Wrong current value"), ("after_display", "Wrong proposed value"),
                                         ("target_address", {"kind": "master", "index": 0, "device_path": [1]})])
def test_confirmation_refuses_tampered_identity_units_and_before_state(target, field, value):
    backend, service = target
    proposal = candidate(service)["proposal"]
    proposal[field] = value
    assert not apply(service, proposal)["ok"]
    assert backend.writes == []



def _as_a_browser_echoes_it(value):
    # JSON.stringify drops an integral float's ".0", so 1.0 comes back to the server as the int 1.
    return json.loads(json.dumps(value), parse_float=lambda text: int(float(text)) if float(text).is_integer() else float(text))


def test_cards_echoed_through_browser_json_still_apply_and_undo(target):
    # 11 Oct review: valid_range [0.0, 1.0] came back as [0, 1], the bound digest changed, and every device,
    # recipe and Undo card Applied from the web UI was refused while the Python round trip here passed.
    from kenn.core.live_recipe import LiveRecipeService

    backend, service = target
    result = apply(service, _as_a_browser_echoes_it(candidate(service)["proposal"]))
    assert result["ok"] and result["receipt"]["verified"] is True
    inverse = _as_a_browser_echoes_it(service.propose_undo(result["receipt"], session_id="target-tests")["proposal"])
    assert apply(service, inverse)["receipt"]["verified"] is True
    spec = {"action": "set_device_parameter", "address": {"kind": "track", "index": 0, "device_path": [1]},
            "device_name": "Test Filter", "parameter_index": 4, "parameter": "Drive", "value": 0.75, "unit": "raw"}
    recipes = LiveRecipeService(service)
    recipe = _as_a_browser_echoes_it(recipes.propose_recipe([spec], reason="Explicit drive", session_id="target-tests")["proposal"])
    assert recipes.execute_recipe(recipe, confirm_token=recipe["confirmation_token"], session_id="target-tests")["ok"]
    assert len(backend.writes) == 3


@pytest.mark.parametrize("lapse", ["five_minutes", "256_later_reads"])
def test_card_undo_outlives_the_observation_window(target, lapse):
    # 11 Oct review: Undo reread against an observation that expired after 300 s or was pushed out by 256 later
    # reads, so card Undo refused every change older than five minutes.
    backend, service = target
    receipt = apply(service, candidate(service)["proposal"])["receipt"]
    if lapse == "five_minutes":
        for row in backend._target_observations.values():
            row["expires"] = 0
    else:
        for _ in range(256):
            backend.get_addressed_parameter({"kind": "return", "index": 0, "device_path": [0]}, 4)
    inverse = service.propose_undo(receipt, session_id="target-tests")
    assert inverse["ok"], inverse
    assert apply(service, inverse["proposal"])["receipt"]["verified"] is True
    assert len(backend.writes) == 2


def test_undo_after_the_observation_window_still_refuses_a_same_name_replacement(target):
    # Keeping a used observation longer must not loosen the identity check it is kept for.
    backend, service = target
    receipt = apply(service, candidate(service)["proposal"])["receipt"]
    backend._target_observations.clear()
    bus = backend._addressed_buses[0]
    bus["devices"][1] = copy.deepcopy(bus["devices"][1])
    assert not service.propose_undo(receipt, session_id="target-tests")["ok"]
    assert len(backend.writes) == 1


def test_chat_undo_read_back_from_the_journal_refuses_a_same_name_replacement(target, tmp_path, monkeypatch):
    # 11 Oct review: the journal dropped observation_token along with the real secrets, so chat "undo that" ran
    # with no identity check and wrote to a Cmd-D copy left behind when the original was deleted.
    from kenn.core import live_receipt_journal as journal

    monkeypatch.setattr(journal, "JOURNAL_PATH", tmp_path / "receipts.jsonl")
    backend, service = target
    assert journal.record_receipt(apply(service, candidate(service)["proposal"])["receipt"], session_id="target-tests")
    receipt = journal.list_receipts(session_id="target-tests")[0]["receipt"]
    assert service.propose_undo(receipt, session_id="target-tests")["ok"]
    bus = backend._addressed_buses[0]
    bus["devices"][1] = copy.deepcopy(bus["devices"][1])
    assert not service.propose_undo(receipt, session_id="target-tests")["ok"]
    assert len(backend.writes) == 1


@pytest.mark.parametrize("identity", [None, "", "   "])
def test_undo_refuses_old_receipts_without_retained_device_identity(target, identity):
    # Receipts saved before 12 Oct lost observation_token in the journal; a matching name and value cannot
    # distinguish the original from a Cmd-D replacement, so even an otherwise valid old receipt must refuse.
    backend, service = target
    receipt = apply(service, candidate(service)["proposal"])["receipt"]
    receipt["target"].pop("observation_token")
    if identity is not None:
        receipt["target"]["observation_token"] = identity
    bus = backend._addressed_buses[0]
    bus["devices"][1] = copy.deepcopy(bus["devices"][1])

    inverse = service.propose_undo(receipt, session_id="target-tests")

    assert inverse["ok"] is False
    assert "identity" in inverse["error"].lower()
    assert len(backend.writes) == 1


def test_cross_session_apply_undo_and_independent_edit_are_refused(target):
    backend, service = target
    proposal = candidate(service)["proposal"]
    assert not apply(service, proposal, session="other-project")["ok"]
    result = apply(service, proposal)
    assert result["ok"]
    assert not service.propose_undo(result["receipt"], session_id="other-project")["ok"]
    backend._addressed_buses[0]["devices"][1]["parameters"][0]["value"] = 0.6
    assert not service.propose_undo(result["receipt"], session_id="target-tests")["ok"]
    assert len(backend.writes) == 1


@pytest.mark.parametrize("owner", [None, "other-project"])
def test_http_undo_cannot_rewrite_the_session_that_applied_the_receipt(target, tmp_path, monkeypatch, owner):
    # 12 Oct review: deleting or replacing client receipt.session_id minted an inverse in another project.
    from kenn.core import live_receipt_journal as journal
    from kenn.routes import daw_command_handler

    monkeypatch.setattr(journal, "JOURNAL_PATH", tmp_path / "receipts.jsonl")
    backend, service = target
    receipt = apply(service, candidate(service)["proposal"])["receipt"]
    assert journal.record_receipt(receipt, session_id="target-tests")
    echoed = _as_a_browser_echoes_it(receipt)
    echoed.pop("session_id")
    if owner is not None:
        echoed["session_id"] = owner
    monkeypatch.setattr(daw_command_handler, "_get_live_action_service", lambda: lambda: service)

    class Reply:
        def send_json(self, status, body):
            self.status, self.body = status, body

    reply = Reply()
    daw_command_handler.handle_osc_undo(reply, {"session_id": "other-project", "receipt": echoed})

    assert reply.status == 409, reply.body
    assert "proposal" not in reply.body
    assert len(backend.writes) == 1


@pytest.mark.parametrize("field,value", [("before", 0.1), ("action", "set_volume"), ("schema", "invented")])
def test_undo_refuses_changed_receipt_values_and_dispatch_fields(target, field, value):
    # Undo must derive its target and restore value from KENN's receipt, never an edited browser object.
    backend, service = target
    echoed = _as_a_browser_echoes_it(apply(service, candidate(service)["proposal"])["receipt"])
    echoed[field] = value
    inverse = service.propose_undo(echoed, session_id="target-tests")
    assert inverse["ok"] is False, inverse
    assert "proposal" not in inverse
    assert len(backend.writes) == 1


def test_guarded_undo_uses_journal_ownership_when_memory_receipt_is_gone(target, tmp_path, monkeypatch):
    # The journal drops receipt.session_id, so ownership must come from the server row after a restart.
    from kenn.core import live_receipt_journal as journal
    from kenn.core.actions import _RECEIPTS

    monkeypatch.setattr(journal, "JOURNAL_PATH", tmp_path / "receipts.jsonl")
    backend, service = target
    receipt = apply(service, candidate(service)["proposal"])["receipt"]
    assert journal.record_receipt(receipt, session_id="target-tests")
    _RECEIPTS.pop(receipt["receipt_id"])
    echoed = journal.list_receipts(session_id="target-tests")[0]["receipt"]
    assert not service.propose_undo(echoed, session_id="other-project")["ok"]
    echoed["before"] = 0.1
    assert not service.propose_undo(echoed, session_id="target-tests")["ok"]
    echoed["before"] = 0.25
    inverse = service.propose_undo(echoed, session_id="target-tests")
    assert inverse["ok"], inverse
    assert apply(service, inverse["proposal"])["receipt"]["verified"]
    assert len(backend.writes) == 2


@pytest.mark.parametrize("schema,service_name", [
    ("MIDI_CLIP_RECEIPT_SCHEMA", "MidiClipActionService"),
    ("CLIP_DUPLICATION_RECEIPT_SCHEMA", "ClipDuplicationActionService"),
    ("CLIP_RENAME_RECEIPT_SCHEMA", "ClipRenameActionService"),
    ("CLIP_AUDITION_RECEIPT_SCHEMA", "ClipAuditionActionService"),
    ("SAMPLE_IMPORT_RECEIPT_SCHEMA", "SampleImportService"),
])
def test_http_undo_authenticates_before_dispatching_an_edited_receipt_schema(target, monkeypatch, schema, service_name):
    # Clip/MIDI dispatch used to precede authentication, letting an edited device receipt mint another inverse.
    from kenn.routes import daw_command_handler

    backend, service = target
    receipt = _as_a_browser_echoes_it(apply(service, candidate(service)["proposal"])["receipt"])
    receipt["schema"] = getattr(daw_command_handler, schema)
    dispatched = []
    monkeypatch.setattr(daw_command_handler, "_get_live_action_service", lambda: lambda: service)
    monkeypatch.setattr(daw_command_handler, service_name, lambda: SimpleNamespace(
        propose_undo=lambda *_args, **_kwargs: dispatched.append(True) or {"ok": True, "proposal": {"action": "rename_clip"}}))

    class Reply:
        def send_json(self, status, body):
            self.status, self.body = status, body

    reply = Reply()
    daw_command_handler.handle_osc_undo(reply, {"session_id": "other-project", "receipt": receipt})

    assert reply.status == 409, reply.body
    assert "proposal" not in reply.body
    assert dispatched == []
    assert len(backend.writes) == 1


def test_undo_cannot_rebind_to_a_replacement_after_its_identity_checked_read(target, monkeypatch):
    # Rediscovering after receipt validation used to give an identical replacement its own Undo token.
    backend, service = target
    receipt = apply(service, candidate(service)["proposal"])["receipt"]
    read = backend.get_addressed_parameter
    calls = []
    def replace_after_read(address, parameter_index, reference=None):
        info = read(address, parameter_index, reference)
        calls.append(reference)
        if len(calls) == 1:
            bus = next(row for row in backend._addressed_buses if row["kind"] == "track")
            bus["devices"][1] = copy.deepcopy(bus["devices"][1])
        return info
    monkeypatch.setattr(backend, "get_addressed_parameter", replace_after_read)
    inverse = service.propose_undo(receipt, session_id="target-tests")
    assert len(calls) == 1 and inverse["ok"]
    assert not apply(service, inverse["proposal"])["ok"]
    assert len(backend.writes) == 1


@pytest.mark.parametrize("fault", [None, "replacement", "handler", "state_changed", "disabled"])
def test_regular_parameter_proposer_requires_guarded_capabilities_when_backend_requires_them(target, monkeypatch, fault):
    # Production bulk reads can inform language resolution, but must never authorize a positional fallback.
    backend, service = target
    monkeypatch.setattr(backend, "requires_guarded_parameter_targets", True, raising=False)
    address = {"kind": "track", "index": 0, "device_path": [1]}
    info = backend.get_addressed_parameter(address, 4)
    state = {"status": "online", "tracks": [{"index": 0, "name": "Duplicate", "devices": [{"name": "Test Filter"}, {"name": "Test Filter"}]}]}
    if fault == "handler":
        monkeypatch.setattr(backend, "get_addressed_parameter", lambda *args: {"success": False, "error": "Missing handler"})
    elif fault in {"state_changed", "disabled"}:
        parameter = backend._addressed_buses[0]["devices"][1]["parameters"][0]
        parameter["value" if fault == "state_changed" else "is_enabled"] = 0.5 if fault == "state_changed" else False
    result = service.propose_device_action(track_index=0, device_index=1, parameter_index=4, proposed_value=0.75,
                                           reason="Explicit request", session_id="target-tests", parameter_name="Drive", unit="raw",
                                           observed_state=state, observed_parameter_info=info)
    if fault in {"handler", "state_changed", "disabled"}:
        assert not result["ok"] and backend.writes == []
        return
    assert result["proposal"]["target_address"] == address
    if fault == "replacement":
        backend._addressed_buses[0]["devices"][1] = copy.deepcopy(backend._addressed_buses[0]["devices"][1])
        assert not apply(service, result["proposal"])["ok"] and backend.writes == []
    else:
        assert apply(service, result["proposal"])["receipt"]["verified"] is True


@pytest.mark.parametrize("field,value", [("min", None), ("max", float("nan")), ("value", float("inf")),
                                         ("is_enabled", False), ("state", 1), ("automation_state", 1),
                                         ("macro_controlled", True), ("state", None)])
def test_missing_or_protected_metadata_never_mints_confirmation(target, field, value):
    backend, service = target
    backend._addressed_buses[0]["devices"][1]["parameters"][0][field] = value
    assert not candidate(service)["ok"]
    assert backend.writes == []


@pytest.mark.parametrize("value,unit", [(2, "raw"), (float("nan"), "raw"), (True, "raw"), (10, "ms"), (800, "Hz"), (50, "%"), (4, "ratio")])
def test_unknown_physical_mapping_does_not_fall_back_to_raw(target, value, unit):
    backend, service = target
    assert not candidate(service, value=value, unit=unit)["ok"]
    assert backend.writes == []


def test_relative_raw_and_sparse_chooser_use_actual_values(target):
    backend, service = target
    assert candidate(service, value=0.1, relative=True)["proposal"]["after"] == pytest.approx(0.35)
    parameter = backend._addressed_buses[0]["devices"][1]["parameters"][0]
    parameter.update(value=2, min=2, max=11, quantized=True,
                     choices=[{"raw": 2, "label": "Peak"}, {"raw": 7, "label": "RMS"}, {"raw": 11, "label": "Auto"}])
    proposal = candidate(service, value="RMS", unit="choice")["proposal"]
    assert proposal["after"] == 7
    assert apply(service, proposal)["receipt"]["readback"] == 7
    assert not candidate(service, value="Invented", unit="choice")["ok"]
    assert not candidate(service, value=3, unit="raw")["ok"]
    parameter["choices"].append({"raw": 11, "label": "RMS"})
    assert not candidate(service, value="RMS", unit="choice")["ok"]


@pytest.mark.parametrize("semantic", ["choice", "physical"])
def test_addressed_undo_restores_raw_with_confirmation_bound_display_semantics(target, semantic):
    # Undo used raw units for restoration and lost the readable choice or dB value on its confirmation card.
    backend, service = target
    device = backend._addressed_buses[0]["devices"][1]
    parameter = device["parameters"][0]
    if semantic == "choice":
        parameter.update(value=2, min=2, max=11, quantized=True,
                         choices=[{"raw": 2, "label": "Peak"}, {"raw": 7, "label": "RMS"}, {"raw": 11, "label": "Auto"}])
        proposal = candidate(service, value="RMS", unit="choice")["proposal"]
    else:
        device["name"] = "Saturator"
        proposal = service.propose_addressed_parameter_action(
            address={"kind": "track", "index": 0, "device_path": [1]}, parameter_index=4,
            parameter_name="Drive", device_name="Saturator", value=0, unit="dB", session_id="target-tests")["proposal"]
    receipt = apply(service, proposal)["receipt"]
    inverse = service.propose_undo(receipt, session_id="target-tests")["proposal"]
    assert inverse["after"] == receipt["before"]
    if semantic == "choice":
        assert (inverse["before_label"], inverse["after_label"]) == ("RMS", "Peak")
    else:
        assert (inverse["before_display"], inverse["after_display"]) == ("0.0 dB", "-18.0 dB")
    assert apply(service, inverse)["receipt"]["verified"] is True


def test_guarded_production_backends_refuse_legacy_recipe_compound_and_recovery_writes(target, monkeypatch):
    # Positional compatibility paths must not bypass the retained-object requirement, even during rollback.
    from kenn.core.live_recipe import LiveRecipeService, RECIPE_SCHEMA
    from kenn.core.live_action_service import DEVICE_SETUP_PROPOSAL_SCHEMA, EQ_BAND_TUNING_GAIN_PROPOSAL_SCHEMA

    backend, service = target
    monkeypatch.setattr(backend, "requires_guarded_parameter_targets", True, raising=False)
    recipes = LiveRecipeService(service)
    step = {"action": "set_device_parameter"}
    result = recipes.execute_recipe({"schema": RECIPE_SCHEMA, "steps": [step]}, confirm_token="unused", session_id="target-tests")
    assert not result["ok"] and "guarded" in result["error"]
    assert recipes._apply_step(step)[0] is False
    assert recipes._restore_step({"action": "set_device_parameter"}) is False
    result = service.execute_eq_band_tuning_gain({"schema": EQ_BAND_TUNING_GAIN_PROPOSAL_SCHEMA}, confirm_token="unused", session_id="target-tests")
    assert not result["ok"] and "guarded" in result["error"]
    assert service._restore_device_parameter(0, 1, 4, 0.25)["attempted"] is False
    result = service.execute_device_setup_action({"schema": DEVICE_SETUP_PROPOSAL_SCHEMA}, confirm_token="unused", session_id="target-tests")
    assert not result["ok"] and "addressed" in result["error"]
    assert backend.writes == []


def test_undo_uses_qualified_choice_labels_when_host_only_exposes_raw_bounds(target, monkeypatch):
    from kenn.core import device_units

    backend, service = target
    parameter = backend._addressed_buses[0]["devices"][1]["parameters"][0]
    parameter.update(quantized=True, value=0, min=0, max=1)
    # This synthetic qualification stands in for an offline table; value_items alone never proves the raw mapping.
    monkeypatch.setattr(device_units, "find_choice", lambda *args: SimpleNamespace(options=((0, "Off"), (1, "On"))))
    proposal = candidate(service, value="On", unit="choice")["proposal"]
    receipt = apply(service, proposal)["receipt"]
    inverse = service.propose_undo(receipt, session_id="target-tests")["proposal"]
    assert inverse["unit"] == "value" and inverse["after"] == 0
    assert (inverse["before_label"], inverse["after_label"]) == ("On", "Off")
    assert apply(service, inverse)["receipt"]["verified"] is True


def test_missing_ack_is_reconciled_once_and_failed_readback_stays_unknown(target, monkeypatch):
    backend, service = target
    setter = backend.set_addressed_parameter
    def lost_ack(*args):
        setter(*args)
        return False
    monkeypatch.setattr(backend, "set_addressed_parameter", lost_ack)
    proposal = candidate(service)["proposal"]
    result = apply(service, proposal)
    assert result["receipt"]["verified"]
    assert result["receipt"]["write_acknowledgement"] == "unacknowledged_write_reconciled"
    assert len(backend.writes) == 1
    next_proposal = candidate(service, value=0.5)["proposal"]
    reader = backend.get_addressed_parameter
    def unavailable_after_send(*args):
        return {"success": False, "error": "missing reply"} if len(backend.writes) == 2 else reader(*args)
    monkeypatch.setattr(backend, "get_addressed_parameter", unavailable_after_send)
    result = apply(service, next_proposal)
    assert result["receipt"]["status"] == "unknown"
    assert result["receipt"]["retry_safe"] == "requires_inspection"
    assert not apply(service, next_proposal)["ok"]
    assert len(backend.writes) == 2


def test_partial_metadata_and_duplicate_indices_cannot_resolve_by_position():
    assert indexed_parameter([{"index": 4}, {"index": 4}], 4) is None
    assert indexed_parameter([{"index": 4}, {}], 1) is None
    assert validate_parameter({"name": "Drive", "value": 0.2}, 0.5)


def test_http_and_mcp_use_same_policy_and_service(target, monkeypatch):
    from kenn.core.mcp.live_proposals import create_parameter_proposal, inspect_parameter
    import kenn.core.live_action_service as owner
    import kenn.core.action_policy as policy
    backend, service = target
    monkeypatch.setattr(owner, "LiveActionService", lambda: service)
    monkeypatch.setattr(policy, "action_allowed", lambda name: name == "daw_control")
    payload = {"session_id": "target-tests", "address": {"kind": "return", "index": 0, "device_path": [1]},
               "parameter_index": 4, "device_name": "Test Filter", "parameter_name": "Drive", "value": 0.5, "unit": "raw"}
    class HTTP:
        def post(self, path, args):
            handler = daw_routes.handle_parameter_inspection if path.endswith("inspect") else daw_routes.handle_parameter_proposal
            return handler(args)[1]
    facade = SimpleNamespace(client=HTTP())
    inspection = inspect_parameter(facade, {key: payload[key] for key in ("address", "parameter_index")})
    assert inspection["ok"] and inspection["changed"] is False
    response = create_parameter_proposal(facade, payload)
    assert response["status"] == "confirmation_required" and response["changed"] is False
    assert backend.writes == []
    assert daw_routes.handle_parameter_proposal({**payload, "confirmation_token": "model-minted"})[0] == 400
    monkeypatch.setattr(policy, "action_allowed", lambda name: False)
    assert daw_routes.handle_parameter_proposal(payload)[0] == 403
    assert daw_routes.handle_parameter_inspection({key: payload[key] for key in ("address", "parameter_index")})[0] == 403


def test_missing_handler_is_explicit_without_constructing_a_proposal():
    result = candidate(LiveActionService(SimpleNamespace()))
    assert not result["ok"] and "cannot address" in result["error"]


def test_unqualified_chooser_does_not_invent_contiguous_intermediate_raw_values(target):
    backend, service = target
    parameter = backend._addressed_buses[0]["devices"][1]["parameters"][0]
    parameter.update(quantized=True, value=2, min=2, max=11, value_items=["A", "B", "C"])
    assert not candidate(service, value=7)["ok"]
    assert backend.writes == []


def test_five_turn_candidate_journey_preserves_exact_target_and_explicit_apply(target, monkeypatch):
    from kenn.routes import daw_command_handler
    import kenn.core.live_action_service as services
    import kenn.core.live_command as commands
    from kenn.core import action_policy, live_receipt_journal

    backend, service = target
    monkeypatch.setenv("KENN_ALLOW_DAW_CONTROL", "1")
    monkeypatch.setattr(action_policy, "action_allowed", lambda name: True)
    monkeypatch.setattr(services, "LiveActionService", lambda *args, **kwargs: service)
    monkeypatch.setattr(daw_command_handler, "_get_handle_command", lambda: lambda command, **kwargs: commands.handle_command(command, service=service, **kwargs))
    monkeypatch.setattr(daw_command_handler, "record_receipt", lambda *args, **kwargs: None)
    monkeypatch.setattr(live_receipt_journal, "record_receipt", lambda *args, **kwargs: None)
    payload = {"session_id": "target-tests", "address": {"kind": "return", "index": 0, "device_path": [1]},
               "parameter_index": 4, "parameter_name": "Drive", "device_name": "Test Filter", "value": 0.75, "unit": "raw"}
    # The stub supplies a candidate, never a token; real HTTP handlers retain authority through all five turns.
    turn1 = daw_routes.handle_parameter_inspection({key: payload[key] for key in ("address", "parameter_index")})[1]
    assert turn1["changed"] is False and turn1["parameters"][0]["value"] == 0.25
    turn2 = daw_routes.handle_parameter_proposal({**payload, "device_name": "Imaginary"})[1]
    assert turn2["ok"] is False and "proposal" not in turn2
    turn3 = daw_routes.handle_parameter_proposal(payload)[1]
    assert turn3["status"] == "confirmation_required" and backend.writes == []
    turn4 = daw_routes.handle_parameter_proposal({**payload, "value": 0.1, "relative": True})[1]
    assert turn4["proposal"]["after"] == pytest.approx(0.35) and backend.writes == []
    proposal = turn4["proposal"]
    _, turn5 = daw_routes.handle_live_command({"command": "Apply that", "session_id": "target-tests", "proposal": proposal,
                                             "confirm_token": proposal["confirmation_token"], "deterministic_only": True}, pending_proposals={})
    assert turn5.get("receipt", {}).get("verified") is True, turn5
    assert backend.writes == [("addressed_parameter", payload["address"], 4, pytest.approx(0.35))]
    inverse = service.propose_undo(turn5["receipt"], session_id="target-tests")["proposal"]
    assert apply(service, inverse)["receipt"]["verified"] is True
    assert backend.get_addressed_parameter(payload["address"], 4)["parameters"][0]["value"] == 0.25


def test_25_device_milestone_counts_fake_lifecycles_and_remaining_stock():
    report = qualify()
    assert (report["device_count"], report["parameter_count"], report["fake_writes"]) == (25, 92, 184)
    assert report["live_writes"] == 0
    assert all(row["fake_tested"] and not row["real_live_qualified"] and not row["observed_in_current_live"] for row in report["parameters"])
    assert len(report["remaining_stock"]) == 53


def test_five_turn_knowledge_to_apply_uses_registered_http_routes(target, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from kenn.core import chat_answer, live_command, live_receipt_journal, session_memory
    import kenn.core.live_action_service as services
    from kenn.routes import daw_command_handler
    from kenn.routes.fastapi_app import app

    backend, service = target
    monkeypatch.setenv("KENN_ALLOW_DAW_CONTROL", "1")
    monkeypatch.setattr(session_memory, "DB_PATH", tmp_path / "chat.db")
    monkeypatch.setattr(session_memory, "CHATS_DIR", tmp_path / "chats")
    monkeypatch.setattr(session_memory, "SESSION_FILE", tmp_path / "session.json")
    monkeypatch.setattr(live_receipt_journal, "JOURNAL_PATH", tmp_path / "receipts.jsonl")
    monkeypatch.setattr(services, "LiveActionService", lambda *args, **kwargs: service)
    monkeypatch.setattr(daw_command_handler, "_get_handle_command", lambda: lambda command, **kwargs: live_command.handle_command(command, service=service, **kwargs))
    # The provider's text is deliberately synthetic. This checks route delivery, not explanation correctness.
    monkeypatch.setattr(chat_answer, "_answer_payload", lambda *args, **kwargs: {
        "answer": "Synthetic advice: inspect Drive and prepare an explicit raw change.", "sources": [],
    })
    client = TestClient(app)
    address = {"kind": "master", "index": 0, "device_path": [1]}
    for question in ("What does Drive do?", "Suggest a value for that parameter."):
        advice = client.post("/api/ask", json={"question": question, "session_id": "target-tests"})
        assert advice.status_code == 200 and advice.json()["answer"].startswith("Synthetic advice")
        assert advice.json().get("receipt") is None and backend.writes == []
    observed = client.post("/api/ableton/parameter/inspect", json={"address": address, "parameter_index": 4}).json()
    assert observed["changed"] is False and observed["parameters"][0]["value"] == 0.25
    proposed = client.post("/api/ableton/parameter/proposal", json={
        "address": address, "parameter_index": 4, "device_name": "Test Filter", "parameter_name": "Drive",
        "value": 0.75, "unit": "raw", "session_id": "target-tests",
    }).json()
    assert proposed["status"] == "confirmation_required" and backend.writes == []
    # The response-to-request round trip must reproduce JSON.stringify's [0, 1], not Python's [0.0, 1.0].
    proposal = _as_a_browser_echoes_it(proposed["proposal"])
    applied = client.post("/api/ableton/command", json={
        "command": "Apply that", "proposal": proposal, "confirm_token": proposal["confirmation_token"],
        "session_id": "target-tests", "deterministic_only": True,
    }).json()
    assert applied["receipt"]["verified"] is True
    assert backend.writes == [("addressed_parameter", address, 4, 0.75)]


# The Stage 2/3 review left "the handler refuses quantized values that the fake accepts" unchecked (12 Oct). Checked
# 13 Oct: the handler refuses any quantized value other than the current one, min or max, and never sends chooser
# options; the backend refuses the same set for addressed writes because its callers pass no device name, so no
# measured profile is consulted. The fake only accepts an in-between value when a test hands it `choices`, which
# real Live never sends. These pin both halves, so the parity cannot slip unnoticed.
class _Chooser:
    name = original_name = "Detector"
    min, max, is_quantized, is_enabled, state, automation_state = 2.0, 11.0, True, True, 0, 0
    value_items = ("Peak", "RMS", "Auto")

    def __init__(self):
        self.value = 2.0

    def str_for_value(self, value):
        return str(value)


def _live_writer():
    import importlib.util

    # Loaded by file path: the Remote Script package is not importable from the backend's own path.
    path = Path(__file__).resolve().parents[5] / "integrations/ableton-osc/abletonosc/parameter_target.py"
    spec = importlib.util.spec_from_file_location("kenn_parameter_target_parity", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    chooser = _Chooser()
    track = SimpleNamespace(name="Bus", devices=[SimpleNamespace(name="Test Filter", class_name="Test",
                                                                 parameters=[chooser], chains=[])])
    return module.ParameterTargets(SimpleNamespace(tracks=[track], return_tracks=[track], master_track=track)), chooser


ADDRESS = {"kind": "track", "index": 0, "device_path": [0]}


def test_the_live_writer_never_sends_chooser_options():
    # The contract's `choices` branch accepts in-between raw values. It is safe only while this stays None,
    # because the writer below would refuse those values anyway.
    writer, _chooser = _live_writer()
    assert writer.read(ADDRESS, 0)["parameters"][0]["choices"] is None


@pytest.mark.parametrize("raw", [2.0, 7.0, 11.0])
def test_the_backend_refuses_exactly_the_chooser_values_the_live_writer_refuses(raw):
    writer, chooser = _live_writer()
    observed = writer.read(ADDRESS, 0)
    backend_accepts = validate_parameter(observed["parameters"][0], raw) is None
    try:
        writer.write(ADDRESS, 0, raw, observed)
        writer_accepts = True
    except ValueError:
        writer_accepts = False
    assert backend_accepts is writer_accepts
    assert chooser.value == (raw if writer_accepts else 2.0)


@pytest.mark.parametrize("value, unit", [(7, "raw"), ("RMS", "choice")])
def test_a_measured_chooser_profile_does_not_unlock_an_in_between_addressed_write(target, monkeypatch, value, unit):
    # A device_units profile can list raw 7 as "RMS", but the live writer would refuse 7 at Apply, after the
    # producer confirmed the card. Addressed proposals therefore refuse it up front, profile or not.
    from kenn.core import device_units

    backend, service = target
    parameter = backend._addressed_buses[0]["devices"][1]["parameters"][0]
    parameter.update(quantized=True, value=2, min=2, max=11)
    monkeypatch.setattr(device_units, "find_choice",
                        lambda *args: SimpleNamespace(options=((2, "Peak"), (7, "RMS"), (11, "Auto"))))
    assert not candidate(service, value=value, unit=unit)["ok"]
    assert backend.writes == []
