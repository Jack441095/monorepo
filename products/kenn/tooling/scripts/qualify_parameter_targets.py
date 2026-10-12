#!/usr/bin/env python3
"""Exercise the shared parameter lifecycle on synthetic buses and racks, without Live."""

from __future__ import annotations

import argparse
import copy
from dataclasses import asdict
import json
import sys
import tempfile
from pathlib import Path

KENN_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(KENN_ROOT / "apps/backend/src"))


def fixture() -> tuple[dict, list[dict]]:
    """Return recorded raw metadata plus explicitly modeled controls and synthetic locations."""
    from kenn.core.fake_live import DEFAULT_FIXTURE

    zoo = json.loads(DEFAULT_FIXTURE.with_name("device_zoo_wave1.json").read_text())
    devices = [dict(name=row["device_name"], parameters=copy.deepcopy(row["parameters"]), provenance="recorded_reset_metadata") for row in zoo["devices"].values()]
    # These labels test contracts, not runtime exposure. No physical conversion is inferred from this fixture.
    modeled = {
        "Analog": "Osc1 Octave", "Operator": "Osc A Level", "Wavetable": "Osc 1 Position",
        "Simpler": "Volume", "Sampler": "Volume", "Drift": "Osc 1 Shape", "Meld": "Osc A Macro 1",
        "Instrument Rack": "Macro 1", "Audio Effect Rack": "Macro 1", "MIDI Effect Rack": "Macro 1",
        "Drum Rack": "Macro 1", "Arpeggiator": "Rate", "Pitch": "Pitch",
    }
    for name, control in modeled.items():
        devices.append({"name": name, "provenance": "modeled_unqualified_metadata", "parameters": [
            {"index": 0, "name": "Device On", "value": 1, "min": 0, "max": 1, "quantized": True},
            {"index": 4, "name": control, "value": 0.25, "min": 0, "max": 1, "quantized": False},
            {"index": 9, "name": "Synthetic chooser", "value": 2, "min": 2, "max": 11, "quantized": True,
             "choices": [{"raw": 2, "label": "A"}, {"raw": 7, "label": "B"}, {"raw": 11, "label": "C"}]},
        ]})
    buses, targets = [], []
    racks = ("Instrument Rack", "Audio Effect Rack", "MIDI Effect Rack", "Drum Rack")
    for position, device in enumerate(devices):
        for parameter in device["parameters"]:
            # Modeled permission flags make this an executable fake; they are never measured host evidence.
            parameter.update(is_enabled=True, state=0, automation_state=0, macro_controlled=False)
        kind = ("track", "return", "master")[position % 3]
        index = 0 if kind == "master" else position
        if kind == "master":
            bus = next((row for row in buses if row["kind"] == "master"), None)
        else:
            bus = None
        if bus is None:
            bus = {"kind": kind, "index": index, "name": "Master" if kind == "master" else f"Synthetic {kind} {index}", "devices": []}
            buses.append(bus)
        root_index = len(bus["devices"])
        path = [root_index]
        root = device
        if position % 4 == 0:
            # All four rack families appear on the same path; the innermost control survives every hop.
            for rack in reversed(racks):
                root = {"name": rack, "chains": [{"name": "Bass", "devices": [root]}]}
            path += [0, 0] * 4
        bus["devices"].append(root)
        for parameter in device["parameters"]:
            targets.append({"address": {"kind": kind, "index": index, "device_path": path}, "device_name": device["name"],
                            "parameter": copy.deepcopy(parameter), "metadata_provenance": device["provenance"]})
    return {"schema": "kenn.fake_live_fixture.v1", "session": {"tracks": []}, "addressed_buses": buses}, targets


def qualify() -> dict:
    """Record actual fake writes, replay refusal and exact observed Undo for each raw control."""
    from kenn.core.fake_live import FakeLiveBackend
    from kenn.core.live_action_service import LiveActionService
    from kenn.core.stock_devices import STOCK_DEVICE_CATEGORIES
    from kenn.core.device_units import all_profiles

    data, targets = fixture()
    rows = []
    with tempfile.TemporaryDirectory(prefix="kenn-parameter-qualification-") as directory:
        path = Path(directory) / "fixture.json"
        path.write_text(json.dumps(data))
        backend = FakeLiveBackend(path)
        service = LiveActionService(backend)
        for number, target in enumerate(targets):
            parameter = target["parameter"]
            before = float(parameter["value"])
            desired = next((float(row["raw"]) for row in parameter.get("choices", []) if row["raw"] != before), None)
            if desired is None:
                desired = float(parameter["min"] if before == parameter["max"] else parameter["max"])
            session = f"synthetic-parameter-{number}"
            arguments = {"address": target["address"], "parameter_index": parameter["index"], "device_name": target["device_name"],
                         "parameter_name": parameter["name"], "unit": "raw", "value": desired, "session_id": session}
            proposal = service.propose_addressed_parameter_action(**arguments)
            if not proposal.get("ok"):
                raise AssertionError(proposal)
            p = proposal["proposal"]
            applied = service.execute_device_action(p, confirm_token=p["confirmation_token"], session_id=session)
            if not applied.get("ok") or not applied["receipt"]["verified"]:
                raise AssertionError(applied)
            replay = service.execute_device_action(p, confirm_token=p["confirmation_token"], session_id=session)
            undo = service.propose_undo(applied["receipt"], session_id=session)
            if not undo.get("ok"):
                raise AssertionError(undo)
            u = undo["proposal"]
            restored = service.execute_device_action(u, confirm_token=u["confirmation_token"], session_id=session)
            observed = backend.get_addressed_parameter(target["address"], parameter["index"])["parameters"][0]["value"]
            invalid = service.propose_addressed_parameter_action(**{**arguments, "value": parameter["max"] + 1})
            passed = not replay.get("ok") and restored.get("ok") and observed == before and not invalid.get("ok")
            if not passed:
                raise AssertionError((replay, restored, observed, invalid))
            profiles = [profile for profile in all_profiles() if profile.device_name == target["device_name"] and profile.parameter_name == parameter["name"]]
            rows.append({**target, "catalog_version": "Live 12.4.6 recorded baseline; modeled entries unqualified", "installed": None,
                         "observed_in_current_live": False, "host_id": None, "raw_before": before, "raw_requested": desired,
                         "displayed_value": parameter.get("value_display"), "unit": "raw",
                         "conversion_provenance": [{"profile": asdict(profile), "owner": "kenn.core.device_units", "measurement_source": None} for profile in profiles],
                         "read": True, "propose": True, "apply": True, "readback": True, "undo": True,
                         "fake_tested": passed, "real_live_qualified": False,
                         "limitations": ["Synthetic topology and permission flags; chooser and modeled controls need host qualification."]})
        writes = len(backend.writes)
    exercised = {row["device_name"] for row in rows}
    return {"schema": "kenn.parameter_qualification.v1", "evidence_kind": "synthetic", "model_run": False, "live_writes": 0,
            "device_count": len(exercised), "parameter_count": len(rows), "fake_writes": writes, "parameters": rows,
            "remaining_stock": [{"device": name, "category": category, "reason": "No fake lifecycle in this run; current observation and real qualification unknown."}
                                for name, category in sorted(STOCK_DEVICE_CATEGORIES.items()) if name not in exercised],
            "additional_inventory": {"Packs": "unknown", "Max for Live": "unknown", "third_party_plugins": "unknown"}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = qualify()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: result[key] for key in ("evidence_kind", "device_count", "parameter_count", "fake_writes", "live_writes")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
