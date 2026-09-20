#!/usr/bin/env python3
"""Qualify KENN's supported reversible Live mutations on a disposable set.

The script is intentionally explicit and conservative: it selects one existing
track, changes one supported field at a time, verifies the real readback,
rejects an exact replay, restores the starting value through a fresh confirmed
inverse, and reports only redacted exchange/receipt metadata. It never creates
tracks or devices and does not persist confirmation tokens. The track and clip
rename cases use temporary names and are restored before the runner exits. The
clip duplication case only targets a freshly verified empty slot and undoes by
deleting only the verified duplicate. MIDI note revision uses an existing MIDI
clip, tests both a non-empty replacement and an intentional clear, and restores
the original note set after each case.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from typing import Any, Callable


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


class CompanionQualificationClient:
    """Read-only Live client backed by the running KENN companion.

    The companion owns AbletonOSC's single reply socket.  Keeping this
    qualification client HTTP-only prevents a second process from binding
    UDP 11001 and makes the runner safe to use alongside the normal runtime.
    """

    def __init__(self, endpoint: str) -> None:
        self.endpoint = endpoint.rstrip("/")

    def _get(self, path: str) -> dict[str, Any]:
        return _get(self.endpoint, path)

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return _post(self.endpoint, path, payload)

    def query_session_state(self, *, include_mixer: bool = True) -> dict[str, Any]:
        return self._get("/api/ableton/osc/session")

    def query_session_topology(self) -> dict[str, Any]:
        return self._get("/api/ableton/osc/session?detail=topology")

    def get_midi_clip_state(self, track_index: int, clip_slot_index: int) -> dict[str, Any]:
        return self._get(f"/api/ableton/osc/midi-clip?track_index={track_index}&clip_slot_index={clip_slot_index}")

    def get_clip_slot_state(self, track_index: int, clip_slot_index: int) -> dict[str, Any]:
        return self._get(f"/api/ableton/osc/clip-slot?track_index={track_index}&clip_slot_index={clip_slot_index}")

    def get_current_song_time(self) -> float | None:
        result = self._get("/api/ableton/osc/song-time")
        value = result.get("current_song_time") if result.get("success") else None
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def get_locators_with_status(self) -> tuple[list[dict[str, Any]], bool]:
        result = self._get("/api/ableton/osc/locators")
        locators = result.get("locators")
        return (list(locators), True) if result.get("success") and isinstance(locators, list) else ([], False)


class CompanionMutationService:
    """HTTP façade for the same proposal/apply/undo boundary used by KENN."""

    def __init__(self, client: CompanionQualificationClient) -> None:
        self.client = client

    def snapshot(self) -> dict[str, Any]:
        return self.client.query_session_state()

    def _proposal_action(self, action: str, *, session_id: str, **payload: Any) -> dict[str, Any]:
        routes = {
            "set_volume": "/api/ableton/osc/volume",
            "set_pan": "/api/ableton/osc/pan",
            "set_mute": "/api/ableton/osc/mute",
            "set_solo": "/api/ableton/osc/solo",
            "set_arm": "/api/ableton/osc/arm",
            "transport_play": "/api/ableton/osc/transport/play",
            "transport_stop": "/api/ableton/osc/transport/stop",
        }
        return self.client._post(routes[action], {"session_id": session_id, **payload})

    def propose_track_action(self, action: str, *, track_index: int, track_name: str, value: Any, session_id: str) -> dict[str, Any]:
        fields = {"set_volume": "volume", "set_pan": "pan", "set_mute": "muted", "set_solo": "soloed", "set_arm": "armed"}
        if action in fields:
            return self._proposal_action(action, session_id=session_id, track_index=track_index, track_name=track_name, **{fields[action]: value})
        if action == "rename_track":
            return self.client._post("/api/ableton/command", {
                "command": f"rename track {track_index + 1} to {json.dumps(str(value))}",
                "deterministic_only": True,
                "session_id": session_id,
            })
        return {"ok": False, "error": f"Unsupported qualification action: {action}"}

    def propose_transport_action(self, action: str, *, session_id: str) -> dict[str, Any]:
        return self._proposal_action(action, session_id=session_id)

    def propose_locator_action(self, action: str, *, locator_name: str, session_id: str) -> dict[str, Any]:
        verb = "add" if action == "add_locator" else "remove"
        return self.client._post("/api/ableton/command", {
            "command": f'{verb} a locator named {json.dumps(locator_name)} at the current position',
            "deterministic_only": True,
            "session_id": session_id,
        })

    def propose_clip_rename(self, *, track_index: int, track_name: str, clip_slot_index: int, new_name: str, session_id: str) -> dict[str, Any]:
        return self.client._post("/api/ableton/clip-rename/proposal", {
            "track_index": track_index, "track_name": track_name, "clip_slot_index": clip_slot_index,
            "new_name": new_name, "session_id": session_id,
        })

    def propose_clip_duplication(self, *, source: dict[str, Any], target: dict[str, Any], session_id: str) -> dict[str, Any]:
        return self.client._post("/api/ableton/clip-duplication/proposal", {
            "source_track_index": source["track_index"], "source_track_name": source["track_name"],
            "source_clip_slot_index": source["clip_slot_index"], "target_track_index": target["track_index"],
            "target_track_name": target["track_name"], "target_clip_slot_index": target["clip_slot_index"],
            "session_id": session_id,
        })

    def propose_midi_update(self, *, target: dict[str, Any], notes: list[dict[str, Any]], session_id: str) -> dict[str, Any]:
        return self.client._post("/api/ableton/midi-clip/update-proposal", {
            "track_index": target["track_index"], "track_name": target["track_name"],
            "clip_slot_index": target["clip_slot_index"], "notes": notes, "session_id": session_id,
        })

    def execute(self, proposal: dict[str, Any], *, confirm_token: str, session_id: str, idempotency_key: str) -> dict[str, Any]:
        return self.client._post("/api/ableton/command", {
            "command": "qualification mutation", "proposal": proposal, "confirm_token": confirm_token,
            "session_id": session_id, "idempotency_key": idempotency_key,
        })

    def propose_undo(self, receipt: dict[str, Any] | None, *, session_id: str) -> dict[str, Any]:
        return self.client._post("/api/ableton/osc/undo", {"receipt": receipt, "session_id": session_id})

    def execute_undo(self, receipt: dict[str, Any], proposal: dict[str, Any], *, session_id: str) -> dict[str, Any]:
        return self.client._post("/api/ableton/osc/undo", {
            "receipt": receipt, "proposal": proposal, "confirm_token": proposal.get("confirmation_token", ""),
            "session_id": session_id, "idempotency_key": proposal.get("action_id", ""),
        })


def _notes_equal(expected: Any, actual: Any) -> bool:
    """Compare the bounded note representation without importing the OSC client."""
    if not isinstance(expected, list) or not isinstance(actual, list):
        return False
    def key(note: Any) -> tuple[Any, ...] | None:
        if not isinstance(note, dict):
            return None
        try:
            return (
                int(note["pitch"]), float(note["start_time"]), float(note["duration"]),
                int(note["velocity"]), bool(note.get("mute", False)),
            )
        except (KeyError, TypeError, ValueError):
            return None
    left = [key(note) for note in expected]
    right = [key(note) for note in actual]
    if any(item is None for item in left + right) or len(left) != len(right):
        return False
    return all(
        a[0] == b[0] and a[3:] == b[3:]
        and abs(a[1] - b[1]) <= 1e-5 and abs(a[2] - b[2]) <= 1e-5
        for a, b in zip(sorted(left), sorted(right))
    )


def _receipt_summary(receipt: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(receipt, dict):
        return {"present": False}
    return {
        "present": True,
        "receipt_id": receipt.get("receipt_id"),
        "status": receipt.get("status"),
        "verified": receipt.get("verified"),
        "write_exchange": receipt.get("write_exchange"),
        "readback_exchange": receipt.get("readback_exchange"),
    }


def _run_track_action(
    service: CompanionMutationService,
    *,
    action: str,
    field: str,
    target_value: Callable[[dict[str, Any]], Any],
    track_index: int,
    track_name: str,
    session_id: str,
) -> dict[str, Any]:
    initial = service.snapshot()
    track = next((item for item in initial.get("tracks", []) if item.get("index") == track_index), None)
    row: dict[str, Any] = {"action": action, "target": {"track_index": track_index, "track_name": track_name}}
    if not track:
        row.update({"status": "failed", "error": "target track disappeared before proposal"})
        return row
    before = track.get(field)
    requested = target_value(track)
    row.update({"before": before, "requested": requested})
    proposed = service.propose_track_action(
        action,
        track_index=track_index,
        track_name=track_name,
        value=requested,
        session_id=session_id,
    )
    if not proposed.get("ok"):
        row.update({"status": "failed", "error": proposed.get("error")})
        return row
    proposal = proposed["proposal"]
    executed = service.execute(
        proposal,
        confirm_token=proposal["confirmation_token"],
        session_id=session_id,
        idempotency_key=proposal["action_id"],
    )
    row["write"] = _receipt_summary(executed.get("receipt"))
    replay = service.execute(
        proposal,
        confirm_token=proposal["confirmation_token"],
        session_id=session_id,
        idempotency_key=proposal["action_id"],
    )
    row["replay_rejected"] = not bool(replay.get("ok"))
    receipt = executed.get("receipt")
    undo_proposed = service.propose_undo(receipt, session_id=session_id) if receipt else {"ok": False}
    undo_executed: dict[str, Any] = {}
    if undo_proposed.get("ok"):
        undo = undo_proposed["proposal"]
        undo_executed = service.execute(
            undo,
            confirm_token=undo["confirmation_token"],
            session_id=session_id,
            idempotency_key=undo["action_id"],
        )
    row["undo"] = _receipt_summary(undo_executed.get("receipt"))
    final = service.snapshot()
    final_track = next((item for item in final.get("tracks", []) if item.get("index") == track_index), None)
    restored = final_track.get(field) if final_track else None
    row["restored_readback"] = restored
    row["status"] = (
        "passed"
        if executed.get("ok")
        and undo_executed.get("ok")
        and row["replay_rejected"]
        and (restored == before or (isinstance(restored, (int, float)) and abs(float(restored) - float(before)) <= 1e-4))
        else "failed"
    )
    if row["status"] == "failed":
        row["error"] = executed.get("error") or undo_executed.get("error") or "restoration or replay check failed"
    return row


def _rename_test_value(current_name: str, track_index: int) -> str:
    """Return a bounded, disposable name that is unlikely to collide."""
    base = current_name.strip() or f"Track {track_index + 1}"
    suffix = f" [KENN qualification {track_index + 1}]"
    return (base[: max(1, 128 - len(suffix))] + suffix)[:128]


def _confirmed_transport_action(service: CompanionMutationService, *, action: str, session_id: str) -> dict[str, Any]:
    proposed = service.propose_transport_action(action, session_id=session_id)
    if not proposed.get("ok"):
        return proposed
    proposal = proposed["proposal"]
    return service.execute(
        proposal,
        confirm_token=proposal["confirmation_token"],
        session_id=session_id,
        idempotency_key=proposal["action_id"],
    )


def _undo_transport_receipt(service: CompanionMutationService, receipt: dict[str, Any] | None, *, session_id: str) -> dict[str, Any]:
    if not receipt:
        return {"ok": False, "error": "No verified transport receipt was produced."}
    proposed = service.propose_undo(receipt, session_id=session_id)
    if not proposed.get("ok"):
        return proposed
    proposal = proposed["proposal"]
    return service.execute(
        proposal,
        confirm_token=proposal["confirmation_token"],
        session_id=session_id,
        idempotency_key=proposal["action_id"],
    )


def _run_transport(service: CompanionMutationService, *, action: str, session_id: str) -> dict[str, Any]:
    initial_before = bool(service.snapshot().get("is_playing", False))
    expected_before = action == "transport_stop"
    row: dict[str, Any] = {"action": action, "before": expected_before, "requested": not expected_before}

    # Arrange the opposite state when necessary, using the same guarded
    # service. This makes both directions independently meaningful while
    # ensuring the runner restores the set's original transport state.
    setup_receipt: dict[str, Any] | None = None
    setup_restore: dict[str, Any] = {"ok": True}

    def restore_setup() -> dict[str, Any]:
        nonlocal setup_restore
        if setup_receipt and setup_restore.get("ok"):
            setup_restore = _undo_transport_receipt(
                service,
                setup_receipt,
                session_id=f"{session_id}:setup-undo:{action}",
            )
            row["setup_restore"] = _receipt_summary(setup_restore.get("receipt"))
        return setup_restore

    if initial_before != expected_before:
        setup_action = "transport_play" if expected_before else "transport_stop"
        setup = _confirmed_transport_action(service, action=setup_action, session_id=f"{session_id}:setup:{action}")
        row["setup"] = _receipt_summary(setup.get("receipt"))
        if not setup.get("ok"):
            row.update({"status": "failed", "error": setup.get("error") or "transport setup failed"})
            return row
        setup_receipt = setup.get("receipt")

    before = bool(service.snapshot().get("is_playing", False))
    row["before"] = before
    if before != expected_before:
        restore_setup()
        row.update({"status": "failed", "error": "could not establish the requested transport precondition"})
        return row

    proposed = service.propose_transport_action(action, session_id=session_id)
    if not proposed.get("ok"):
        restore_setup()
        row.update({"status": "failed", "error": proposed.get("error") or "transport proposal failed"})
        return row
    proposal = proposed["proposal"]
    executed = service.execute(
        proposal,
        confirm_token=proposal["confirmation_token"],
        session_id=session_id,
        idempotency_key=proposal["action_id"],
    )
    row["write"] = _receipt_summary(executed.get("receipt"))
    replay = service.execute(
        proposal,
        confirm_token=proposal["confirmation_token"],
        session_id=session_id,
        idempotency_key=proposal["action_id"],
    )
    row["replay_rejected"] = not bool(replay.get("ok"))
    receipt = executed.get("receipt")
    undo_executed = _undo_transport_receipt(service, receipt, session_id=f"{session_id}:undo:{action}")
    row["undo"] = _receipt_summary(undo_executed.get("receipt"))
    row["restored_readback"] = bool(service.snapshot().get("is_playing", False))

    restore_setup()
    row["final_readback"] = bool(service.snapshot().get("is_playing", False))
    row["status"] = (
        "passed"
        if executed.get("ok")
        and undo_executed.get("ok")
        and row["replay_rejected"]
        and row["restored_readback"] == before
        and setup_restore.get("ok")
        and row["final_readback"] == initial_before
        else "failed"
    )
    if row["status"] == "failed":
        row["error"] = executed.get("error") or undo_executed.get("error") or setup_restore.get("error") or "restoration or replay check failed"
    return row


def _run_locator(service: CompanionMutationService, *, locator_name: str, session_id: str) -> dict[str, Any]:
    """Qualify one temporary locator add/remove lifecycle at the current cursor."""
    proposal_service = service
    client = getattr(service, "client", service)
    if not hasattr(proposal_service, "propose_locator_action"):
        # Keep the deterministic fake-Live helper contract used by unit tests
        # and local diagnosis, while the real runner uses the HTTP façade.
        from kenn.core.live_action_service import LiveActionService
        proposal_service = LiveActionService(service)
        client = service
    row: dict[str, Any] = {"action": "add_locator", "locator_name": locator_name}
    proposed = proposal_service.propose_locator_action("add_locator", locator_name=locator_name, session_id=session_id)
    if not proposed.get("ok"):
        return {**row, "status": "failed", "error": proposed.get("error")}
    proposal = proposed["proposal"]
    row["locator_time_beats"] = proposal.get("locator_time_beats")
    executed = proposal_service.execute(
        proposal,
        confirm_token=proposal["confirmation_token"],
        session_id=session_id,
        idempotency_key=proposal["action_id"],
    )
    row["write"] = _receipt_summary(executed.get("receipt"))
    replay = proposal_service.execute(
        proposal,
        confirm_token=proposal["confirmation_token"],
        session_id=session_id,
        idempotency_key=proposal["action_id"],
    )
    row["replay_rejected"] = not bool(replay.get("ok"))
    receipt = executed.get("receipt")
    undo_proposed = proposal_service.propose_undo(receipt, session_id=f"{session_id}:undo") if receipt else {"ok": False}
    undo_executed: dict[str, Any] = {}
    if undo_proposed.get("ok"):
        undo = undo_proposed["proposal"]
        undo_executed = proposal_service.execute(
            undo,
            confirm_token=undo["confirmation_token"],
            session_id=f"{session_id}:undo",
            idempotency_key=undo["action_id"],
        )
    row["undo"] = _receipt_summary(undo_executed.get("receipt"))
    locators, available = client.get_locators_with_status()
    row["restored_readback"] = bool(available) and not any(
        isinstance(item, dict)
        and str(item.get("name", "")) == locator_name
        and abs(float(item.get("time_beats", -1)) - float(row["locator_time_beats"])) <= 1e-4
        for item in locators
    )
    row["status"] = "passed" if executed.get("ok") and row["replay_rejected"] and undo_executed.get("ok") and row["restored_readback"] else "failed"
    if row["status"] == "failed":
        row["error"] = executed.get("error") or undo_executed.get("error") or "locator restoration or replay check failed"
    return row


def _find_clip_pair(client: Any, tracks: list[dict[str, Any]], *, max_slots: int = 16) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Find one existing clip and one empty slot without changing Live."""
    source: dict[str, Any] | None = None
    for track in tracks:
        track_index = int(track.get("index", -1))
        track_name = str(track.get("name", ""))
        if track_index < 0:
            continue
        for slot in range(max_slots):
            state = client.get_clip_slot_state(track_index, slot)
            if not isinstance(state, dict) or not state.get("success"):
                continue
            endpoint = {"track_index": track_index, "track_name": track_name, "clip_slot_index": slot, "state": state}
            if state.get("has_clip") and source is None:
                source = endpoint
            elif not state.get("has_clip") and source is not None and (track_index, slot) != (source["track_index"], source["clip_slot_index"]):
                return source, endpoint
    return source, None


def _run_clip_rename(service: CompanionMutationService, *, endpoint: dict[str, Any], session_id: str) -> dict[str, Any]:
    target = {key: endpoint[key] for key in ("track_index", "track_name", "clip_slot_index")}
    original_name = str((endpoint.get("state") or {}).get("clip_name", ""))
    temporary_name = (original_name[:96] + " [KENN clip qualification]")[:128] or "KENN clip qualification"
    row: dict[str, Any] = {"action": "rename_clip", "target": target, "before": original_name, "requested": temporary_name}
    if not hasattr(service, "propose_clip_rename"):
        from kenn.core.clip_rename_service import ClipRenameActionService
        proposal_service = ClipRenameActionService(service)
    else:
        proposal_service = service
    proposed = proposal_service.propose(**target, new_name=temporary_name, session_id=session_id) if hasattr(proposal_service, "propose") else proposal_service.propose_clip_rename(**target, new_name=temporary_name, session_id=session_id)
    if not proposed.get("ok"):
        return {**row, "status": "failed", "error": proposed.get("error")}
    proposal = proposed["proposal"]
    execute = service.execute if hasattr(service, "propose_clip_rename") else proposal_service.execute
    executed = execute(proposal, confirm_token=proposal["confirmation_token"], session_id=session_id, idempotency_key=proposal["action_id"])
    row["write"] = _receipt_summary(executed.get("receipt"))
    replay = execute(proposal, confirm_token=proposal["confirmation_token"], session_id=session_id, idempotency_key=proposal["action_id"])
    row["replay_rejected"] = not bool(replay.get("ok"))
    receipt = executed.get("receipt")
    propose_undo = service.propose_undo if hasattr(service, "propose_clip_rename") else proposal_service.propose_undo
    undo_proposed = propose_undo(receipt, session_id=f"{session_id}:undo") if receipt else {"ok": False}
    undo_executed: dict[str, Any] = {}
    if undo_proposed.get("ok"):
        undo = undo_proposed["proposal"]
        undo_executed = (
            service.execute_undo(receipt, undo, session_id=f"{session_id}:undo")
            if hasattr(service, "propose_clip_rename") else
            proposal_service.execute_undo(undo, confirm_token=undo["confirmation_token"], session_id=f"{session_id}:undo", idempotency_key=undo["action_id"])
        )
    row["undo"] = _receipt_summary(undo_executed.get("receipt"))
    final = service.client.get_clip_slot_state(target["track_index"], target["clip_slot_index"])
    row["restored_readback"] = final.get("clip_name") if isinstance(final, dict) else None
    row["status"] = "passed" if executed.get("ok") and row["replay_rejected"] and undo_executed.get("ok") and row["restored_readback"] == original_name else "failed"
    if row["status"] == "failed":
        row["error"] = executed.get("error") or undo_executed.get("error") or "clip rename restoration or replay check failed"
    return row


def _run_clip_duplication(service: CompanionMutationService, *, source: dict[str, Any], target: dict[str, Any], session_id: str) -> dict[str, Any]:
    source_args = {key: source[key] for key in ("track_index", "track_name", "clip_slot_index")}
    target_args = {key: target[key] for key in ("track_index", "track_name", "clip_slot_index")}
    row: dict[str, Any] = {"action": "duplicate_clip", "source": source_args, "target": target_args}
    if not hasattr(service, "propose_clip_duplication"):
        from kenn.core.clip_duplication_service import ClipDuplicationActionService
        proposal_service = ClipDuplicationActionService(service)
    else:
        proposal_service = service
    proposed = proposal_service.propose(
        source_track_index=source_args["track_index"], source_track_name=source_args["track_name"], source_clip_slot_index=source_args["clip_slot_index"],
        target_track_index=target_args["track_index"], target_track_name=target_args["track_name"], target_clip_slot_index=target_args["clip_slot_index"], session_id=session_id,
    ) if hasattr(proposal_service, "propose") else proposal_service.propose_clip_duplication(source=source, target=target, session_id=session_id)
    if not proposed.get("ok"):
        return {**row, "status": "failed", "error": proposed.get("error")}
    proposal = proposed["proposal"]
    execute = service.execute if hasattr(service, "propose_clip_duplication") else proposal_service.execute
    executed = execute(proposal, confirm_token=proposal["confirmation_token"], session_id=session_id, idempotency_key=proposal["action_id"])
    row["write"] = _receipt_summary(executed.get("receipt"))
    replay = execute(proposal, confirm_token=proposal["confirmation_token"], session_id=session_id, idempotency_key=proposal["action_id"])
    row["replay_rejected"] = not bool(replay.get("ok"))
    receipt = executed.get("receipt")
    propose_undo = service.propose_undo if hasattr(service, "propose_clip_duplication") else proposal_service.propose_undo
    undo_proposed = propose_undo(receipt, session_id=f"{session_id}:undo") if receipt else {"ok": False}
    undo_executed: dict[str, Any] = {}
    if undo_proposed.get("ok"):
        undo = undo_proposed["proposal"]
        undo_executed = (
            service.execute_undo(receipt, undo, session_id=f"{session_id}:undo")
            if hasattr(service, "propose_clip_duplication") else
            proposal_service.execute_undo(undo, confirm_token=undo["confirmation_token"], session_id=f"{session_id}:undo", idempotency_key=undo["action_id"])
        )
    row["undo"] = _receipt_summary(undo_executed.get("receipt"))
    final = service.client.get_clip_slot_state(target_args["track_index"], target_args["clip_slot_index"])
    row["restored_readback"] = not bool(final.get("has_clip")) if isinstance(final, dict) else False
    row["status"] = "passed" if executed.get("ok") and row["replay_rejected"] and undo_executed.get("ok") and row["restored_readback"] else "failed"
    if row["status"] == "failed":
        row["error"] = executed.get("error") or undo_executed.get("error") or "clip duplication undo or replay check failed"
    return row


def _find_midi_clip(client: Any, tracks: list[dict[str, Any]], *, max_slots: int = 16) -> dict[str, Any] | None:
    """Find one readable existing MIDI clip without changing Live."""
    for track in tracks:
        track_index = int(track.get("index", -1))
        track_name = str(track.get("name", ""))
        if track_index < 0:
            continue
        for slot in range(max_slots):
            state = client.get_midi_clip_state(track_index, slot)
            if isinstance(state, dict) and state.get("success") and state.get("has_clip") and state.get("is_midi_clip"):
                return {
                    "track_index": track_index,
                    "track_name": track_name,
                    "clip_slot_index": slot,
                    "state": state,
                }
    return None


def _run_midi_clip_update(
    service: CompanionMutationService,
    *,
    endpoint: dict[str, Any],
    replacement_notes: list[dict[str, Any]],
    session_id: str,
) -> dict[str, Any]:
    """Qualify one exact MIDI note replacement and its identity-bound undo."""
    local_service = None
    client = getattr(service, "client", service)
    if not hasattr(service, "propose_midi_update"):
        from kenn.core.midi_clip_service import MidiClipActionService
        local_service = MidiClipActionService(service)
    target = {key: endpoint[key] for key in ("track_index", "track_name", "clip_slot_index")}
    initial = endpoint.get("state") if isinstance(endpoint.get("state"), dict) else client.get_midi_clip_state(
        target["track_index"], target["clip_slot_index"]
    )
    original_notes = initial.get("notes", []) if isinstance(initial, dict) else []
    row: dict[str, Any] = {
        "action": "update_midi_clip",
        "target": target,
        "requested_note_count": len(replacement_notes),
        "before_note_count": len(original_notes) if isinstance(original_notes, list) else None,
    }
    proposed = (
        service.propose_midi_update(target=target, notes=replacement_notes, session_id=session_id)
        if local_service is None else
        local_service.propose_update(**target, notes=replacement_notes, session_id=session_id)
    )
    if not proposed.get("ok"):
        return {**row, "status": "failed", "error": proposed.get("error")}
    proposal = proposed["proposal"]
    execute = service.execute if local_service is None else local_service.execute_update
    executed = execute(proposal, confirm_token=proposal["confirmation_token"], session_id=session_id, idempotency_key=proposal["action_id"])
    row["write"] = _receipt_summary(executed.get("receipt"))
    replay = execute(proposal, confirm_token=proposal["confirmation_token"], session_id=session_id, idempotency_key=proposal["action_id"])
    row["replay_rejected"] = not bool(replay.get("ok"))
    receipt = executed.get("receipt")
    propose_undo = service.propose_undo if local_service is None else local_service.propose_undo
    undo_proposed = propose_undo(receipt, session_id=f"{session_id}:undo") if receipt else {"ok": False}
    undo_executed: dict[str, Any] = {}
    if undo_proposed.get("ok"):
        undo = undo_proposed["proposal"]
        undo_executed = (
            service.execute_undo(receipt, undo, session_id=f"{session_id}:undo")
            if local_service is None else
            local_service.execute_update(undo, confirm_token=undo["confirmation_token"], session_id=f"{session_id}:undo", idempotency_key=undo["action_id"])
        )
    row["undo"] = _receipt_summary(undo_executed.get("receipt"))
    final = client.get_midi_clip_state(target["track_index"], target["clip_slot_index"])
    row["restored_readback"] = bool(
        isinstance(final, dict)
        and final.get("success")
        and final.get("has_clip")
        and final.get("is_midi_clip")
        and _notes_equal(original_notes, final.get("notes"))
    )
    row["status"] = (
        "passed"
        if executed.get("ok") and row["replay_rejected"] and undo_executed.get("ok") and row["restored_readback"]
        else "failed"
    )
    if row["status"] == "failed":
        row["error"] = executed.get("error") or undo_executed.get("error") or "MIDI note replacement or restoration failed"
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8090", help="KENN companion URL")
    parser.add_argument("--track-index", type=int, default=None)
    parser.add_argument("--session-id", default=f"qualification-{int(time.time())}")
    args = parser.parse_args()

    client = CompanionQualificationClient(args.endpoint)
    service = CompanionMutationService(client)
    state = service.snapshot()
    if state.get("status") != "connected":
        print(json.dumps({"schema": "kenn.ableton_real_mutation_qualification.v1", "evidence_kind": "real_live", "status": "blocked", "error": "Ableton Live is not connected or returned no usable snapshot."}, indent=2))
        return 2
    tracks = [track for track in state.get("tracks", []) if isinstance(track, dict)]
    if not tracks:
        print(json.dumps({"schema": "kenn.ableton_real_mutation_qualification.v1", "evidence_kind": "real_live", "status": "blocked", "error": "No existing Live track is available; no track will be created."}, indent=2))
        return 2
    track = next((item for item in tracks if item.get("index") == args.track_index), tracks[0]) if args.track_index is not None else tracks[0]
    track_index = int(track["index"])
    track_name = str(track.get("name", ""))
    results = [
        _run_track_action(service, action="set_volume", field="volume", target_value=lambda item: 0.74 if abs(float(item.get("volume", 0.0)) - 0.74) > 0.01 else 0.66, track_index=track_index, track_name=track_name, session_id=args.session_id),
        _run_track_action(service, action="set_pan", field="pan", target_value=lambda item: 0.2 if abs(float(item.get("pan", 0.0))) < 0.1 else 0.0, track_index=track_index, track_name=track_name, session_id=args.session_id),
        _run_track_action(service, action="set_mute", field="muted", target_value=lambda item: not bool(item.get("muted", False)), track_index=track_index, track_name=track_name, session_id=args.session_id),
        _run_track_action(service, action="set_solo", field="soloed", target_value=lambda item: not bool(item.get("soloed", False)), track_index=track_index, track_name=track_name, session_id=args.session_id),
        _run_track_action(service, action="set_arm", field="armed", target_value=lambda item: not bool(item.get("armed", False)), track_index=track_index, track_name=track_name, session_id=args.session_id),
        _run_track_action(service, action="rename_track", field="name", target_value=lambda item: _rename_test_value(str(item.get("name", "")), track_index), track_index=track_index, track_name=track_name, session_id=args.session_id),
        _run_transport(service, action="transport_play", session_id=args.session_id),
        _run_transport(service, action="transport_stop", session_id=args.session_id),
    ]
    locator_name = "KENN locator qualification"
    current_time = service.client.get_current_song_time()
    locators, locators_available = service.client.get_locators_with_status()
    locator_occupied = current_time is not None and any(
        isinstance(item, dict)
        and isinstance(item.get("time_beats"), (int, float))
        and abs(float(item["time_beats"]) - float(current_time)) <= 1e-4
        for item in locators
    ) if locators_available else True
    if current_time is None or not locators_available or locator_occupied:
        results.append({"action": "add_locator", "status": "failed", "error": "A readable stopped playhead without an existing locator at that position is required for locator qualification."})
    else:
        results.append(_run_locator(service, locator_name=locator_name, session_id=f"{args.session_id}:locator"))
    source_clip, target_clip = _find_clip_pair(client, tracks)
    if source_clip is None or target_clip is None:
        results.append({"action": "clip_actions", "status": "failed", "error": "A real existing clip and a separate empty Session View slot are required for clip qualification."})
    else:
        results.append(_run_clip_rename(service, endpoint=source_clip, session_id=f"{args.session_id}:clip-rename"))
        # Re-read after the rename has been restored so the source fingerprint
        # is current and the target remains explicitly empty.
        source_clip, target_clip = _find_clip_pair(client, tracks)
        if source_clip is None or target_clip is None:
            results.append({"action": "duplicate_clip", "status": "failed", "error": "Clip pair was not available after clip-rename restoration."})
        else:
            results.append(_run_clip_duplication(service, source=source_clip, target=target_clip, session_id=f"{args.session_id}:clip-duplication"))
    midi_clip = _find_midi_clip(client, tracks)
    if midi_clip is None:
        results.append({"action": "update_midi_clip", "status": "failed", "error": "An existing readable MIDI clip is required for note-revision qualification."})
    else:
        midi_state = midi_clip["state"]
        clip_length = float(midi_state.get("length", 0.0))
        note_duration = min(0.25, max(0.001, clip_length))
        replacement = [{"pitch": 36, "start_time": 0.0, "duration": note_duration, "velocity": 96, "mute": False}]
        results.append(_run_midi_clip_update(service, endpoint=midi_clip, replacement_notes=replacement, session_id=f"{args.session_id}:midi-update"))
        # The first case restores the original clip, so the clear case starts
        # from the same known state and proves the intentional empty-set path.
        results.append(_run_midi_clip_update(service, endpoint=midi_clip, replacement_notes=[], session_id=f"{args.session_id}:midi-clear"))
    unknown = service.propose_track_action("set_volume", track_index=999999, value=0.5, session_id=args.session_id)
    print(json.dumps({
        "schema": "kenn.ableton_real_mutation_qualification.v1",
        "evidence_kind": "real_live",
        "status": "passed" if all(row.get("status") == "passed" for row in results) and not unknown.get("ok") else "failed",
        "target": {"track_index": track_index, "track_name": track_name},
        "results": results,
        "unknown_track_refused": not bool(unknown.get("ok")),
        "unknown_track_error": unknown.get("error"),
        "limitations": [
            "This script qualifies the supported track/transport subset, temporary track and clip rename, one existing-clip-to-empty-slot duplication lifecycle, and reversible MIDI note replacement/clear cases.",
            "Device-parameter mutation, native Live Edit Undo, and crash/restart recovery require separate evidence.",
        ],
    }, indent=2, sort_keys=True))
    return 0 if all(row.get("status") == "passed" for row in results) and not unknown.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
