#!/usr/bin/env python3
"""Qualify one real, reversible Ableton device-parameter mutation.

The target parameter is resolved by the name returned from Live; no device or
parameter index is invented. All OSC access goes through the running KENN
companion's HTTP endpoints, so this script never competes for AbletonOSC's
single reply socket. The script uses a disposable set, requires an explicit
test value, rejects an exact replay, restores the original value via a fresh
confirmed inverse, and emits only redacted receipt/exchange metadata.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any


def _receipt_summary(receipt: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(receipt, dict):
        return {"present": False}
    return {
        "present": True,
        "receipt_id": receipt.get("receipt_id"),
        "action": receipt.get("action"),
        "status": receipt.get("status"),
        "verified": receipt.get("verified"),
        "target": receipt.get("target"),
        "before": receipt.get("before"),
        "requested": receipt.get("requested"),
        "readback": receipt.get("readback"),
        "write_exchange": receipt.get("write_exchange"),
        "readback_exchange": receipt.get("readback_exchange"),
    }


def _blocked(message: str, *, target: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "schema": "kenn.ableton_real_device_qualification.v1",
        "evidence_kind": "real_live",
        "status": "blocked",
        "target": target or {},
        "error": message,
        "limitations": [
            "No device or parameter was created by this runner.",
            "A blocked result is not device-parameter qualification evidence.",
        ],
    }


def _get(endpoint: str, path: str) -> dict[str, Any]:
    with urllib.request.urlopen(endpoint.rstrip("/") + path, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _display_value(endpoint: str, track_index: int, device_index: int, parameter_index: int) -> str | None:
    """Read one targeted Ableton UI value without expanding bulk inspection."""
    try:
        result = _get(
            endpoint,
            f"/api/ableton/osc/device-parameter-value-string?track_index={track_index}"
            f"&device_index={device_index}&parameter_index={parameter_index}",
        )
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return None
    value = result.get("value_string") if isinstance(result, dict) and result.get("success") else None
    return str(value) if value not in (None, "") else None


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


def _proposal_summary(proposal: dict[str, Any]) -> dict[str, Any]:
    """Return reviewable proposal fields without exposing a confirmation token."""
    target = proposal.get("target")
    if not isinstance(target, dict):
        target = {
            "target": target,
            "track_index": proposal.get("track_index"),
            "track_name": proposal.get("track_name"),
            "device_index": proposal.get("device_index"),
            "device_name": proposal.get("device_name"),
            "parameter_index": proposal.get("parameter_index"),
            "parameter": proposal.get("parameter") or proposal.get("parameter_name"),
        }
        target = {key: value for key, value in target.items() if value is not None}
    return {
        "action_id": proposal.get("action_id") or proposal.get("id"),
        "action": proposal.get("action") or proposal.get("operation"),
        "target": target,
        "before": proposal.get("before"),
        "after": proposal.get("after") if proposal.get("after") is not None else proposal.get("value"),
        "unit": proposal.get("unit"),
        "relative": proposal.get("relative"),
        "reason": proposal.get("reason"),
        "valid_range": proposal.get("valid_range"),
    }


def qualify(*, endpoint: str, track_index: int, device_index: int, parameter_name: str, value: float, session_id: str, apply: bool = False) -> dict[str, Any]:
    try:
        state = _get(endpoint, "/api/ableton/osc/session")
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return _blocked(f"KENN companion session probe failed: {type(exc).__name__}: {exc}")
    if state.get("status") != "connected":
        return _blocked("Ableton Live is not connected or returned no usable snapshot.")

    tracks = [item for item in state.get("tracks", []) if isinstance(item, dict)]
    track = next((item for item in tracks if item.get("index") == track_index), None)
    target = {"track_index": track_index, "device_index": device_index, "parameter_name": parameter_name}
    if track is None:
        return _blocked("Target track index is not present in the current Live snapshot.", target=target)
    target["track_name"] = str(track.get("name", ""))
    devices = track.get("devices") or []
    device = devices[device_index] if 0 <= device_index < len(devices) else None
    if not isinstance(device, dict):
        return _blocked("Target device is not present in the current Live snapshot.", target=target)
    target["device_name"] = str(device.get("name", ""))

    try:
        inspected = _get(endpoint, f"/api/ableton/osc/device-parameters?track_index={track_index}&device_index={device_index}")
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return _blocked(f"KENN companion parameter probe failed: {type(exc).__name__}: {exc}.", target=target)
    if not inspected.get("success"):
        return _blocked(f"Live device inspection failed: {inspected.get('error', 'unknown error')}.", target=target)
    parameters = inspected.get("parameters") or []
    matches = [item for item in parameters if isinstance(item, dict) and str(item.get("name", "")) == parameter_name]
    if len(matches) != 1:
        return _blocked("Parameter name was not present exactly once in the Live response.", target=target)
    parameter = matches[0]
    parameter_index = int(parameter.get("index", -1))
    target["parameter_index"] = parameter_index
    target["unit"] = "device_value"
    if parameter_index < 0:
        return _blocked("Live returned an invalid parameter index.", target=target)
    before = float(parameter.get("value"))
    minimum = float(parameter.get("min"))
    maximum = float(parameter.get("max"))
    target["valid_range"] = [minimum, maximum]
    display_before = _display_value(endpoint, track_index, device_index, parameter_index)
    if display_before is not None:
        target["display_before"] = display_before
    if not minimum <= value <= maximum:
        return _blocked("Requested test value is outside the inspected Live parameter range.", target=target)
    if abs(value - before) <= 1e-6:
        return _blocked("Requested test value equals the current value; choose a distinct in-range value.", target=target)

    plan = {
        "schema": "kenn.ableton_llm_plan.v1",
        "action": "set_device_parameter",
        "track_index": track_index,
        "track_name": str(track.get("name", "")),
        "device_index": device_index,
        "device_name": str(device.get("name", "")),
        "parameter_index": parameter_index,
        "parameter_name": parameter_name,
        "value": value,
        "relative": False,
        "unit": "device_value",
    }
    proposed = _post(endpoint, "/api/ableton/command", {
        "command": f"qualify {parameter_name}", "session_id": session_id, "llm_plan": plan,
    })
    if proposed.get("status") != "confirmation_required" or not isinstance(proposed.get("proposal"), dict):
        return {**_blocked(proposed.get("error") or proposed.get("answer", "Device proposal failed."), target=target), "status": "failed"}
    proposal = proposed["proposal"]
    if not apply:
        return {
            "schema": "kenn.ableton_real_device_qualification.v1",
            "evidence_kind": "real_live",
            "status": "proposal_ready",
            "changed": False,
            "target": target,
            "inspected": {"parameter_index": parameter_index, "before": before, "display_before": display_before, "min": minimum, "max": maximum},
            "proposal": _proposal_summary(proposal),
            "limitations": [
                "Proposal-only mode performed no Live write.",
                "Rerun the same inspected target with --apply only after reviewing the proposal on a disposable set.",
            ],
        }
    executed = _post(endpoint, "/api/ableton/command", {
        "command": f"qualify {parameter_name}", "session_id": session_id, "proposal": proposal,
        "confirm_token": str(proposal.get("confirmation_token", "")),
        "idempotency_key": str(proposal.get("action_id") or proposal.get("id") or ""),
    })
    receipt = executed.get("receipt")
    row: dict[str, Any] = {
        "schema": "kenn.ableton_real_device_qualification.v1",
        "evidence_kind": "real_live",
        "target": target,
        "inspected": {"parameter_index": parameter_index, "before": before, "display_before": display_before, "min": minimum, "max": maximum},
        "write": _receipt_summary(receipt),
    }
    display_after = _display_value(endpoint, track_index, device_index, parameter_index)
    if display_after is not None:
        row["display_after"] = display_after
    replay = _post(endpoint, "/api/ableton/command", {
        "command": f"qualify {parameter_name}", "session_id": session_id, "proposal": proposal,
        "confirm_token": str(proposal.get("confirmation_token", "")),
        "idempotency_key": str(proposal.get("action_id") or proposal.get("id") or ""),
    })
    row["replay_rejected"] = not bool(replay.get("ok"))

    executed_ok = bool(executed.get("ok")) or executed.get("status") == "applied"
    undo_proposed = _post(endpoint, "/api/ableton/osc/undo", {"receipt": receipt, "session_id": session_id}) if executed_ok and receipt else {"ok": False}
    undo_executed: dict[str, Any] = {}
    if isinstance(undo_proposed.get("proposal"), dict):
        undo = undo_proposed["proposal"]
        undo_executed = _post(endpoint, "/api/ableton/osc/undo", {
            "receipt": receipt, "proposal": undo, "session_id": session_id,
            "confirm_token": str(undo.get("confirmation_token", "")),
            "idempotency_key": str(undo.get("action_id") or undo.get("id") or ""),
        })
    row["undo"] = _receipt_summary(undo_executed.get("receipt"))
    display_restored = _display_value(endpoint, track_index, device_index, parameter_index)
    if display_restored is not None:
        row["display_restored"] = display_restored
    try:
        final = _get(endpoint, f"/api/ableton/osc/device-parameters?track_index={track_index}&device_index={device_index}")
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        final = {"success": False}
    final_parameters = final.get("parameters") or [] if final.get("success") else []
    final_match = next((item for item in final_parameters if isinstance(item, dict) and int(item.get("index", -1)) == parameter_index), None)
    restored = final_match.get("value") if final_match else None
    row["restored_readback"] = restored
    display_restored_ok = (
        display_before is None
        or (
            display_restored is not None
            and " ".join(display_restored.split()).casefold()
            == " ".join(display_before.split()).casefold()
        )
    )
    row["display_restored_verified"] = display_restored_ok
    row["status"] = "passed" if (
        executed_ok
        and undo_executed.get("ok")
        and row["replay_rejected"]
        and restored is not None
        and abs(float(restored) - before) <= 1e-4
        and display_restored_ok
    ) else "failed"
    if row["status"] == "failed":
        row["error"] = executed.get("error") or undo_executed.get("error") or "device restoration or replay check failed"
    row["limitations"] = [
        "This qualifies one device parameter and KENN receipt undo, not native Live Edit Undo.",
        "The set must be disposable; no device was created by this runner.",
    ]
    return row


def qualify_sweep(
    *,
    endpoint: str,
    track_index: int,
    device_index: int,
    parameter_name: str,
    values: list[float],
    session_id: str,
    apply: bool = False,
    interval_seconds: float = 10.0,
) -> dict[str, Any]:
    """Collect a bounded multi-point mapping candidate with restore per point."""
    if not 2 <= len(values) <= 20:
        raise ValueError("A calibration sweep requires 2-20 test values.")
    normalized_values = [float(value) for value in values]
    if len(set(normalized_values)) != len(normalized_values):
        raise ValueError("Calibration sweep values must be unique.")
    rows: list[dict[str, Any]] = []
    expected_status = "passed" if apply else "proposal_ready"
    for index, value in enumerate(normalized_values):
        if index and interval_seconds > 0:
            time.sleep(interval_seconds)
        row = qualify(
            endpoint=endpoint,
            track_index=track_index,
            device_index=device_index,
            parameter_name=parameter_name,
            value=value,
            session_id=f"{session_id}-{index + 1}",
            apply=apply,
        )
        rows.append(row)
        if row.get("status") != expected_status:
            break

    complete = len(rows) == len(normalized_values) and all(
        row.get("status") == expected_status for row in rows
    )
    targets = [row.get("target") for row in rows if isinstance(row.get("target"), dict)]
    identities = {
        (
            target.get("track_index"), target.get("track_name"),
            target.get("device_index"), target.get("device_name"),
            target.get("parameter_index"), target.get("parameter_name"),
        )
        for target in targets
    }
    identity_stable = len(identities) == 1 and len(targets) == len(rows)
    samples = [
        {
            "requested_raw": row.get("write", {}).get("requested"),
            "display_after": row.get("display_after"),
        }
        for row in rows
        if row.get("status") == "passed"
    ]
    display_complete = apply and all(
        str(row.get("display_after") or "").strip() for row in rows
    )
    status = expected_status if complete and identity_stable and (not apply or display_complete) else "failed"
    return {
        "schema": "kenn.ableton_real_device_calibration_sweep.v1",
        "evidence_kind": "real_live" if apply else "proposal_only",
        "status": status,
        "changed": False,
        "target_identity_stable": identity_stable,
        "display_samples_complete": display_complete,
        "requested_values": normalized_values,
        "completed_points": len(rows),
        "samples": samples,
        "rows": rows,
        "mapping_candidate_only": True,
        "limitations": [
            "Every applied sample is independently restored before the next sample starts.",
            "This report never creates or promotes a DeviceUnitProfile automatically.",
            "A human must review the raw/display pairs, mapping shape, receipt evidence, and Live version.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8090", help="KENN companion URL")
    parser.add_argument("--track-index", type=int, required=True)
    parser.add_argument("--device-index", type=int, required=True)
    parser.add_argument("--parameter-name", required=True)
    parser.add_argument(
        "--value",
        type=float,
        action="append",
        required=True,
        help="Raw Live test value; repeat 2-20 times for a restored calibration sweep.",
    )
    parser.add_argument("--session-id", default=f"device-qualification-{int(time.time())}")
    parser.add_argument("--apply", action="store_true", help="perform the reversible qualification after proposal-only checks")
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=10.0,
        help="Pause between sweep points to stay below the supervised HTTP rate limit.",
    )
    args = parser.parse_args()
    if min(args.track_index, args.device_index) < 0:
        parser.error("track and device indices must be non-negative")
    if args.interval_seconds < 0:
        parser.error("--interval-seconds must be non-negative")
    if len(args.value) == 1:
        result = qualify(
            endpoint=args.endpoint,
            track_index=args.track_index,
            device_index=args.device_index,
            parameter_name=args.parameter_name,
            value=args.value[0],
            session_id=args.session_id,
            apply=args.apply,
        )
    else:
        try:
            result = qualify_sweep(
                endpoint=args.endpoint,
                track_index=args.track_index,
                device_index=args.device_index,
                parameter_name=args.parameter_name,
                values=args.value,
                session_id=args.session_id,
                apply=args.apply,
                interval_seconds=args.interval_seconds,
            )
        except ValueError as exc:
            parser.error(str(exc))
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result.get("status") in {"passed", "proposal_ready"} else (2 if result.get("status") == "blocked" else 1)


if __name__ == "__main__":
    raise SystemExit(main())
