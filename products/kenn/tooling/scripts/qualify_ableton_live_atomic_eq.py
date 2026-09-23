#!/usr/bin/env python3
"""Qualify KENN's atomic EQ Eight insertion and exact-band setup.

The runner is proposal-only unless ``--apply`` is supplied. Apply mode is for
an explicitly disposable Live set: it confirms one insert-and-tune proposal,
checks every control readback, rejects replay, performs the identity-bound
undo, and independently verifies that the original device chain was restored.
Confirmation secrets are never included in the printed result.
"""

from __future__ import annotations

import argparse
import json
import re
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
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        return {
            "ok": False,
            "status": "transport_failed",
            "error": f"KENN companion request failed: {type(exc).__name__}: {exc}",
        }


def _device_chain(track: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(track, dict):
        return []
    return [
        {"index": item.get("index"), "name": str(item.get("name", ""))}
        for item in track.get("devices", [])
        if isinstance(item, dict)
    ]


def _track(state: dict[str, Any], index: int) -> dict[str, Any] | None:
    matches = [
        item for item in state.get("tracks", [])
        if isinstance(item, dict) and item.get("index") == index
    ]
    return matches[0] if len(matches) == 1 else None


def _receipt_summary(receipt: Any) -> dict[str, Any]:
    if not isinstance(receipt, dict):
        return {"present": False}
    parameter_results = receipt.get("parameter_results")
    return {
        "present": True,
        "schema": receipt.get("schema"),
        "receipt_id": receipt.get("receipt_id"),
        "status": receipt.get("status"),
        "verified": receipt.get("verified"),
        "operation": receipt.get("operation"),
        "parameter_results": [
            {
                "parameter_index": item.get("parameter_index"),
                "parameter_name": item.get("parameter_name"),
                "requested": item.get("requested"),
                "readback": item.get("readback"),
                "verified": item.get("verified"),
                "write_acknowledgement": item.get("write_acknowledgement"),
            }
            for item in parameter_results or []
            if isinstance(item, dict)
        ],
    }


def _blocked(message: str, *, target: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "schema": "kenn.ableton_atomic_eq_qualification.v1",
        "evidence_kind": "real_live",
        "status": "blocked",
        "target": target or {},
        "error": message,
        "limitations": [
            "No EQ mutation was completed by this result.",
            "A blocked or proposal-only result is not real-Live mutation qualification evidence.",
        ],
    }


def qualify(
    *,
    endpoint: str,
    track_index: int,
    eq_band: str,
    frequency_hz: float,
    gain_db: float,
    session_id: str,
    apply: bool = False,
) -> dict[str, Any]:
    band = str(eq_band).strip().upper()
    target: dict[str, Any] = {"track_index": track_index, "eq_band": band}
    if not re.fullmatch(r"[1-8][AB]", band):
        return _blocked("EQ band must be one exact identity from 1A through 8B.", target=target)
    if (
        not 20.0 <= frequency_hz <= 20_000.0
        or not -15.0 <= gain_db <= 15.0
        or abs(gain_db) <= 1e-9
    ):
        return _blocked("Frequency must be 20–20000 Hz and gain must be a non-zero value from -15 to 15 dB.", target=target)
    try:
        initial_state = _get(endpoint, "/api/ableton/osc/session")
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return _blocked(f"KENN companion session probe failed: {type(exc).__name__}: {exc}", target=target)
    if initial_state.get("status") != "connected":
        return _blocked("Ableton Live is not connected or returned no usable snapshot.", target=target)
    initial_track = _track(initial_state, track_index)
    if initial_track is None:
        return _blocked("Target track index is not present exactly once in the Live snapshot.", target=target)
    track_name = str(initial_track.get("name", "")).strip()
    before_devices = _device_chain(initial_track)
    target.update({"track_name": track_name, "before_devices": before_devices})
    if not track_name:
        return _blocked("The target track has no usable name.", target=target)
    if any(item["name"].strip().casefold() == "eq eight" for item in before_devices):
        return _blocked("The target already contains EQ Eight; choose a disposable track without one.", target=target)

    command = (
        f"add an EQ to {track_name} and boost band {band} by {abs(gain_db):g} dB "
        f"at {frequency_hz:g} Hz"
        if gain_db >= 0
        else f"add an EQ to {track_name} and cut band {band} by {abs(gain_db):g} dB at {frequency_hz:g} Hz"
    )
    proposed = _post(endpoint, "/api/ableton/command", {"command": command, "session_id": session_id})
    proposal = proposed.get("proposal")
    expected_names = [
        f"{band[:-1]} Filter On {band[-1]}",
        f"{band[:-1]} Frequency {band[-1]}",
        f"{band[:-1]} Gain {band[-1]}",
    ]
    specs = proposal.get("parameter_specs") if isinstance(proposal, dict) else None
    expected_specs = [
        {"role": "enable", "name": expected_names[0], "display_value": 1.0, "unit": "boolean"},
        {"role": "frequency", "name": expected_names[1], "display_value": frequency_hz, "unit": "Hz"},
        {"role": "gain", "name": expected_names[2], "display_value": gain_db, "unit": "dB"},
    ]
    proposal_valid = (
        proposed.get("status") == "confirmation_required"
        and proposed.get("changed") is False
        and isinstance(proposal, dict)
        and proposal.get("operation") == "insert_eq_band_tuning_gain"
        and proposal.get("track_index") == track_index
        and proposal.get("track_name") == track_name
        and proposal.get("eq_band") == band
        and specs == expected_specs
    )
    if not proposal_valid:
        return {
            **_blocked(proposed.get("error") or proposed.get("answer", "Atomic EQ proposal failed."), target=target),
            "status": "failed",
        }

    try:
        proposal_state = _get(endpoint, "/api/ableton/osc/session")
        proposal_chain = _device_chain(_track(proposal_state, track_index))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        proposal_chain = None
    row: dict[str, Any] = {
        "schema": "kenn.ableton_atomic_eq_qualification.v1",
        "evidence_kind": "real_live",
        "status": "proposal_only" if not apply else "running",
        "target": target,
        "requested": {"frequency_hz": frequency_hz, "gain_db": gain_db},
        "proposal": {
            "schema": proposal.get("schema"),
            "operation": proposal.get("operation"),
            "insertion_index": proposal.get("insertion_index"),
            "parameter_names": expected_names,
            "changed": proposed.get("changed"),
        },
        "proposal_preserved_device_chain": proposal_chain is not None and proposal_chain == before_devices,
    }
    if proposal_chain is None or proposal_chain != before_devices:
        row.update({"status": "failed", "error": "Device chain changed before confirmation; stop and inspect Live."})
        return row
    if not apply:
        row["limitations"] = [
            "No confirmation token was submitted and no Live mutation was requested.",
            "Rerun with --apply only on a disposable set after reviewing the exact proposal.",
        ]
        return row

    executed = _post(endpoint, "/api/ableton/command", {
        "command": command,
        "session_id": session_id,
        "proposal": proposal,
        "confirm_token": str(proposal.get("confirmation_token", "")),
        "idempotency_key": str(proposal.get("action_id", "")),
    })
    receipt = executed.get("receipt")
    row["write"] = _receipt_summary(receipt)
    parameter_results = receipt.get("parameter_results") if isinstance(receipt, dict) else None
    executed_ok = (
        (bool(executed.get("ok")) or executed.get("status") == "applied")
        and isinstance(receipt, dict)
        and receipt.get("verified") is True
        and receipt.get("operation") == "insert_eq_band_tuning_gain"
        and isinstance(parameter_results, list)
        and len(parameter_results) == 3
        and all(isinstance(item, dict) and item.get("verified") is True for item in parameter_results)
    )

    replay = _post(endpoint, "/api/ableton/command", {
        "command": command,
        "session_id": session_id,
        "proposal": proposal,
        "confirm_token": str(proposal.get("confirmation_token", "")),
        "idempotency_key": str(proposal.get("action_id", "")),
    })
    row["replay_rejected"] = not bool(replay.get("ok")) and replay.get("status") != "applied"

    undo_proposed: dict[str, Any] = {}
    undo_executed: dict[str, Any] = {}
    if executed_ok:
        undo_proposed = _post(endpoint, "/api/ableton/osc/undo", {"receipt": receipt, "session_id": session_id})
        undo = undo_proposed.get("proposal")
        if isinstance(undo, dict):
            undo_executed = _post(endpoint, "/api/ableton/osc/undo", {
                "receipt": receipt,
                "proposal": undo,
                "session_id": session_id,
                "confirm_token": str(undo.get("confirmation_token", "")),
                "idempotency_key": str(undo.get("action_id", "")),
            })
    row["undo"] = _receipt_summary(undo_executed.get("receipt"))
    if undo_proposed and not isinstance(undo_proposed.get("proposal"), dict):
        row["undo_proposal_error"] = undo_proposed.get("error") or "No identity-bound undo proposal was returned."

    try:
        final_state = _get(endpoint, "/api/ableton/osc/session")
        final_devices = _device_chain(_track(final_state, track_index))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        final_devices = None
    row["restored_readback"] = {"devices": final_devices}
    restored = final_devices is not None and final_devices == before_devices
    row["status"] = "passed" if (
        executed_ok
        and row["replay_rejected"]
        and undo_executed.get("ok")
        and isinstance(undo_executed.get("receipt"), dict)
        and undo_executed["receipt"].get("verified") is True
        and restored
    ) else "failed"
    if row["status"] == "failed":
        row["error"] = (
            executed.get("error")
            or undo_executed.get("error")
            or row.get("undo_proposal_error")
            or "Atomic EQ apply, replay rejection, undo, or restoration did not verify."
        )
    row["limitations"] = [
        "This qualifies one exact insert-enable-frequency-gain transaction on the current disposable set.",
        "It does not qualify arbitrary devices, bands, autonomous edits, or native Live Cmd-Z.",
    ]
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8090")
    parser.add_argument("--track-index", type=int, required=True)
    parser.add_argument("--eq-band", default="2A")
    parser.add_argument("--frequency-hz", type=float, default=5000.0)
    parser.add_argument("--gain-db", type=float, default=3.0)
    parser.add_argument("--session-id", default=f"atomic-eq-qualification-{int(time.time())}")
    parser.add_argument("--apply", action="store_true", help="mutate and restore only an explicitly disposable Live set")
    args = parser.parse_args()
    if args.track_index < 0:
        parser.error("track index must be non-negative")
    result = qualify(
        endpoint=args.endpoint,
        track_index=args.track_index,
        eq_band=args.eq_band,
        frequency_hz=args.frequency_hz,
        gain_db=args.gain_db,
        session_id=args.session_id,
        apply=args.apply,
    )
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result.get("status") in {"passed", "proposal_only"} else (2 if result.get("status") == "blocked" else 1)


if __name__ == "__main__":
    raise SystemExit(main())
