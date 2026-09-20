#!/usr/bin/env python3
"""Qualify one small, reversible two-step Live recipe through KENN's HTTP API.

The runner is proposal-only unless ``--apply`` is supplied.  In apply mode it
changes one existing track pan and one exact existing device parameter,
verifies both steps, rejects an exact replay, creates a fresh inverse recipe,
and verifies restoration.  It never creates tracks or devices and does not
print confirmation secrets.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any


def _get(endpoint: str, path: str) -> dict[str, Any]:
    with urllib.request.urlopen(endpoint.rstrip("/") + path, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _post(endpoint: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        endpoint.rstrip("/") + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
            body["_http_status"] = response.status
            return body
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            body = {"error": str(exc)}
        body["_http_status"] = exc.code
        return body


def _receipt_summary(receipt: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(receipt, dict):
        return {"present": False}
    return {
        "present": True,
        "schema": receipt.get("schema"),
        "receipt_id": receipt.get("receipt_id"),
        "status": receipt.get("status"),
        "verified": receipt.get("verified"),
        "step_count": receipt.get("step_count"),
    }


def _blocked(message: str, *, target: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "schema": "kenn.ableton_real_recipe_qualification.v1",
        "evidence_kind": "real_live",
        "status": "blocked",
        "target": target or {},
        "error": message,
        "limitations": [
            "No recipe mutation was completed by this result.",
            "A blocked result is not multi-step qualification evidence.",
        ],
    }


def _numeric(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result


def qualify(
    *,
    endpoint: str,
    track_index: int,
    device_index: int,
    parameter_name: str,
    device_value: float,
    pan_value: float,
    session_id: str,
    apply: bool = False,
) -> dict[str, Any]:
    try:
        state = _get(endpoint, "/api/ableton/osc/session")
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return _blocked(f"KENN companion session probe failed: {type(exc).__name__}: {exc}")

    if state.get("status") != "connected":
        return _blocked("Ableton Live is not connected or returned no usable snapshot.")
    tracks = [item for item in state.get("tracks", []) if isinstance(item, dict)]
    track = next((item for item in tracks if item.get("index") == track_index), None)
    target: dict[str, Any] = {
        "track_index": track_index,
        "device_index": device_index,
        "parameter_name": parameter_name,
    }
    if track is None:
        return _blocked("Target track index is not present in the current Live snapshot.", target=target)
    track_name = str(track.get("name", ""))
    target["track_name"] = track_name
    before_pan = _numeric(track.get("pan"))
    if before_pan is None or not -1.0 <= pan_value <= 1.0 or abs(pan_value - before_pan) <= 1e-6:
        return _blocked("Pan test value must be distinct and within Live's [-1, 1] range.", target=target)

    devices = track.get("devices") or []
    device = devices[device_index] if 0 <= device_index < len(devices) else None
    if not isinstance(device, dict):
        return _blocked("Target device is not present in the current Live snapshot.", target=target)
    device_name = str(device.get("name", ""))
    target["device_name"] = device_name

    try:
        inspected = _get(endpoint, f"/api/ableton/osc/device-parameters?track_index={track_index}&device_index={device_index}")
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return _blocked(f"KENN companion parameter probe failed: {type(exc).__name__}: {exc}.", target=target)
    if not inspected.get("success"):
        return _blocked(f"Live device inspection failed: {inspected.get('error', 'unknown error')}.", target=target)
    matches = [item for item in inspected.get("parameters", []) if isinstance(item, dict) and str(item.get("name", "")) == parameter_name]
    if len(matches) != 1:
        return _blocked("Parameter name was not present exactly once in the Live response.", target=target)
    parameter = matches[0]
    parameter_index = int(parameter.get("index", -1))
    before_device = _numeric(parameter.get("value"))
    minimum = _numeric(parameter.get("min"))
    maximum = _numeric(parameter.get("max"))
    target.update({"parameter_index": parameter_index, "valid_range": [minimum, maximum]})
    if parameter_index < 0 or before_device is None or minimum is None or maximum is None:
        return _blocked("Live returned an incomplete numeric parameter description.", target=target)
    if not minimum <= device_value <= maximum or abs(device_value - before_device) <= 1e-6:
        return _blocked("Device test value must be distinct and within the inspected Live range.", target=target)

    plan = {
        "schema": "kenn.ableton_llm_plan.v1",
        "action": "recipe",
        "steps": [
            {"action": "set_pan", "track_index": track_index, "track_name": track_name, "value": pan_value, "relative": False, "unit": "normalized"},
            {
                "action": "set_device_parameter",
                "track_index": track_index,
                "track_name": track_name,
                "device_index": device_index,
                "device_name": device_name,
                "parameter_index": parameter_index,
                "parameter_name": parameter_name,
                "value": device_value,
                "relative": False,
                "unit": "device_value",
            },
        ],
    }
    proposed = _post(endpoint, "/api/ableton/command", {"command": "qualify two-step recipe", "session_id": session_id, "llm_plan": plan})
    proposal = proposed.get("proposal")
    if proposed.get("status") != "confirmation_required" or not isinstance(proposal, dict):
        return {**_blocked(proposed.get("error") or proposed.get("answer", "Recipe proposal failed."), target=target), "status": "failed"}

    row: dict[str, Any] = {
        "schema": "kenn.ableton_real_recipe_qualification.v1",
        "evidence_kind": "real_live",
        "status": "proposal_only" if not apply else "running",
        "target": target,
        "steps": {
            "pan": {"before": before_pan, "requested": pan_value},
            "device_parameter": {"before": before_device, "requested": device_value, "parameter_index": parameter_index},
        },
        "proposal": {"schema": proposal.get("schema"), "step_count": proposal.get("step_count"), "changed": proposed.get("changed", False)},
    }
    if not apply:
        return row

    executed = _post(endpoint, "/api/ableton/command", {
        "command": "qualify two-step recipe",
        "session_id": session_id,
        "proposal": proposal,
        "confirm_token": str(proposal.get("confirmation_token", "")),
        "idempotency_key": str(proposal.get("action_id") or proposal.get("id") or ""),
    })
    receipt = executed.get("receipt")
    row["write"] = _receipt_summary(receipt)
    executed_ok = bool(executed.get("ok")) or executed.get("status") == "applied"

    replay = _post(endpoint, "/api/ableton/command", {
        "command": "qualify two-step recipe",
        "session_id": session_id,
        "proposal": proposal,
        "confirm_token": str(proposal.get("confirmation_token", "")),
        "idempotency_key": str(proposal.get("action_id") or proposal.get("id") or ""),
    })
    row["replay_rejected"] = not bool(replay.get("ok"))

    undo_executed: dict[str, Any] = {}
    undo_proposed: dict[str, Any] = {}
    if executed_ok and isinstance(receipt, dict):
        undo_proposed = _post(endpoint, "/api/ableton/osc/undo", {"receipt": receipt, "session_id": session_id})
        undo = undo_proposed.get("proposal")
        if isinstance(undo, dict):
            undo_executed = _post(endpoint, "/api/ableton/osc/undo", {
                "receipt": receipt,
                "proposal": undo,
                "session_id": session_id,
                "confirm_token": str(undo.get("confirmation_token", "")),
                "idempotency_key": str(undo.get("action_id") or undo.get("id") or ""),
            })
    row["undo"] = _receipt_summary(undo_executed.get("receipt"))
    if undo_proposed and not isinstance(undo_proposed.get("proposal"), dict):
        row["undo_proposal_error"] = undo_proposed.get("error") or "No inverse recipe proposal was returned."

    try:
        final_state = _get(endpoint, "/api/ableton/osc/session")
        final_track = next((item for item in final_state.get("tracks", []) if isinstance(item, dict) and item.get("index") == track_index), None)
        final_inspected = _get(endpoint, f"/api/ableton/osc/device-parameters?track_index={track_index}&device_index={device_index}")
        final_match = next((item for item in final_inspected.get("parameters", []) if isinstance(item, dict) and int(item.get("index", -1)) == parameter_index), None)
    except (OSError, urllib.error.URLError, json.JSONDecodeError, TypeError, ValueError):
        final_track, final_match = None, None
    restored_pan = _numeric(final_track.get("pan")) if isinstance(final_track, dict) else None
    restored_device = _numeric(final_match.get("value")) if isinstance(final_match, dict) else None
    row["restored_readback"] = {"pan": restored_pan, "device_parameter": restored_device}
    row["status"] = "passed" if (
        executed_ok
        and isinstance(receipt, dict)
        and receipt.get("schema") == "kenn.ableton_recipe_receipt.v1"
        and receipt.get("verified") is True
        and undo_executed.get("ok")
        and row["replay_rejected"]
        and restored_pan is not None
        and restored_device is not None
        and abs(restored_pan - before_pan) <= 1e-4
        and abs(restored_device - before_device) <= 1e-4
    ) else "failed"
    if row["status"] == "failed":
        row["error"] = (
            executed.get("error")
            or undo_executed.get("error")
            or row.get("undo_proposal_error")
            or "recipe restoration or replay check failed"
        )
    row["limitations"] = [
        "This qualifies one two-step recipe on the current disposable Live set.",
        "It does not qualify arbitrary autonomous multi-step editing or native Live Cmd-Z.",
    ]
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8090")
    parser.add_argument("--track-index", type=int, required=True)
    parser.add_argument("--device-index", type=int, required=True)
    parser.add_argument("--parameter-name", required=True)
    parser.add_argument("--device-value", type=float, required=True)
    parser.add_argument("--pan-value", type=float, required=True)
    parser.add_argument("--session-id", default=f"recipe-qualification-{int(time.time())}")
    parser.add_argument("--apply", action="store_true", help="perform the reversible qualification after proposal-only checks")
    args = parser.parse_args()
    if min(args.track_index, args.device_index) < 0:
        parser.error("track and device indices must be non-negative")
    result = qualify(
        endpoint=args.endpoint,
        track_index=args.track_index,
        device_index=args.device_index,
        parameter_name=args.parameter_name,
        device_value=args.device_value,
        pan_value=args.pan_value,
        session_id=args.session_id,
        apply=args.apply,
    )
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result.get("status") in {"passed", "proposal_only"} else (2 if result.get("status") == "blocked" else 1)


if __name__ == "__main__":
    raise SystemExit(main())
