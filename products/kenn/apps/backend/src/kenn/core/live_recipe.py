"""Bounded, confirmation-gated Ableton recipes.

Recipes are deliberately narrower than arbitrary automation.  They contain
one to three already-typed track, transport, or device-parameter proposals,
share one confirmation token, verify every step, and restore completed steps
in reverse order when a later step fails.
"""

from __future__ import annotations

import json
import math
import time
import uuid
from threading import Lock
from typing import Any

from kenn.core.confirmation import consume_confirmation, issue_confirmation
from kenn.core.idempotency_bounds import prune_if_needed
from kenn.core.live_action_service import (
    LiveActionService,
    SUPPORTED_TRACK_ACTIONS,
    SUPPORTED_TRANSPORT_ACTIONS,
    _find_return_track,
    _values_match,
)


RECIPE_SCHEMA = "kenn.ableton_recipe_proposal.v1"
RECIPE_RECEIPT_SCHEMA = "kenn.ableton_recipe_receipt.v1"
MAX_RECIPE_STEPS = 3
RECIPE_ACTIONS = set(SUPPORTED_TRACK_ACTIONS) | set(SUPPORTED_TRANSPORT_ACTIONS) | {"set_device_parameter", "set_send"}
_USED_IDEMPOTENCY_KEYS: set[str] = set()
_IN_FLIGHT_IDEMPOTENCY_KEYS: set[str] = set()
_LOCK = Lock()


def _mark_used(key: str) -> None:
    """Call under _LOCK: record a finished key and keep the set bounded."""
    prune_if_needed(_USED_IDEMPOTENCY_KEYS)
    _USED_IDEMPOTENCY_KEYS.add(key)
    _IN_FLIGHT_IDEMPOTENCY_KEYS.discard(key)


def _recipe_text(recipe: dict[str, Any]) -> str:
    """Return the stable token text for the exact recipe contents."""
    steps = []
    for step in recipe.get("steps", []):
        steps.append({
            key: step.get(key)
            for key in (
                "action", "track_index", "track_name", "device_index", "device_name",
                "parameter_index", "parameter", "return_track_index", "return_track_name", "before", "after", "unit",
            )
        })
    material = {"steps": steps}
    if isinstance(recipe.get("source_evidence"), dict):
        material["source_evidence"] = recipe["source_evidence"]
    return "set_recipe:" + json.dumps(material, sort_keys=True, separators=(",", ":"))


def _safe_source_evidence(value: Any) -> dict[str, Any] | None:
    """Keep review provenance bounded and immutable inside a recipe token."""
    if not isinstance(value, dict):
        return None
    result: dict[str, Any] = {
        "schema": "kenn.mix_review_evidence.v1",
        "review_id": str(value.get("review_id", "")).strip()[:128],
        "status": str(value.get("status", "unknown")).strip()[:64],
        "source_scope": "uploaded_or_rendered_audio",
        "live_target_inference_allowed": False,
    }
    recommendations: list[dict[str, Any]] = []
    for item in value.get("recommendations") or []:
        if not isinstance(item, dict):
            continue
        recommendations.append({
            key: str(item.get(key, "")).strip()[:512]
            for key in ("title", "category", "severity", "confidence", "description", "suggestedAction")
            if item.get(key) not in (None, "")
        })
        if len(recommendations) >= 6:
            break
    result["recommendations"] = recommendations
    result["limitations"] = [
        "Findings describe uploaded/rendered audio, not current Live state.",
        "The review does not identify a responsible Live track or device.",
    ]
    if not result["review_id"]:
        return None
    return result


def _exact_track(state: dict[str, Any], index: int, name: str) -> dict[str, Any] | None:
    tracks = [item for item in state.get("tracks", []) if isinstance(item, dict)]
    matches = [item for item in tracks if item.get("index") == index]
    if len(matches) != 1:
        return None
    if name and str(matches[0].get("name", "")) != name:
        return None
    return matches[0]


def _find_parameter(info: dict[str, Any], index: int, name: str) -> dict[str, Any] | None:
    parameters = [item for item in info.get("parameters", []) if isinstance(item, dict)]
    exact = next((item for item in parameters if int(item.get("index", -1)) == index and str(item.get("name", "")) == name), None)
    if exact is not None:
        return exact
    # Preserve compatibility with old dense test doubles that omitted Live's
    # sparse parameter indices, but only after checking the exact name.
    if 0 <= index < len(parameters):
        candidate = parameters[index]
        if str(candidate.get("name", "")) == name:
            return candidate
    return None


def _step_target(step: dict[str, Any]) -> dict[str, Any]:
    action = str(step.get("action", ""))
    if action in SUPPORTED_TRACK_ACTIONS:
        return {
            "action": action,
            "track_index": int(step["track_index"]),
            "track_name": str(step.get("track_name", "")),
            "parameter": SUPPORTED_TRACK_ACTIONS[action][0],
        }
    if action in SUPPORTED_TRANSPORT_ACTIONS:
        return {"action": action, "parameter": "is_playing"}
    if action == "set_send":
        return {
            "action": action,
            "track_index": int(step["track_index"]),
            "track_name": str(step.get("track_name", "")),
            "return_track_index": int(step["return_track_index"]),
            "return_track_name": str(step.get("return_track_name", "")),
            "parameter": "send",
        }
    return {
        "action": action,
        "track_index": int(step["track_index"]),
        "track_name": str(step.get("track_name", "")),
        "device_index": int(step["device_index"]),
        "device_name": str(step.get("device_name", "")),
        "parameter_index": int(step["parameter_index"]),
        "parameter": str(step.get("parameter", "")),
    }


class LiveRecipeService:
    """Plan and execute a small atomic-ish recipe through a Live client."""

    def __init__(self, service: LiveActionService | None = None):
        self.service = service or LiveActionService()
        self.client = self.service.client

    def propose_recipe(
        self,
        steps: list[dict[str, Any]],
        *,
        reason: str,
        session_id: str,
        source_evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build one exact recipe proposal without performing a Live write."""
        if not isinstance(steps, list) or not 1 <= len(steps) <= MAX_RECIPE_STEPS:
            return {"ok": False, "error": f"A recipe must contain between 1 and {MAX_RECIPE_STEPS} typed actions."}
        child_steps: list[dict[str, Any]] = []
        for position, spec in enumerate(steps, start=1):
            if not isinstance(spec, dict):
                return {"ok": False, "error": f"Recipe step {position} is not a typed action object."}
            action = str(spec.get("action", ""))
            if action not in RECIPE_ACTIONS:
                return {"ok": False, "error": f"Recipe step {position} uses unsupported action '{action}'."}
            try:
                if action in SUPPORTED_TRACK_ACTIONS:
                    result = self.service.propose_track_action(
                        action,
                        track_index=int(spec["track_index"]),
                        track_name=str(spec.get("track_name", "")),
                        value=spec.get("value"),
                        session_id=session_id,
                    )
                elif action in SUPPORTED_TRANSPORT_ACTIONS:
                    result = self.service.propose_transport_action(action, session_id=session_id)
                elif action == "set_send":
                    result = self.service.propose_send_action(
                        track_index=int(spec["track_index"]),
                        track_name=str(spec.get("track_name", "")),
                        return_track_index=int(spec["return_track_index"]),
                        return_track_name=str(spec.get("return_track_name", "")),
                        value=spec.get("value"),
                        session_id=session_id,
                    )
                else:
                    result = self.service.propose_device_action(
                        track_index=int(spec["track_index"]),
                        device_index=int(spec["device_index"]),
                        parameter_index=int(spec["parameter_index"]),
                        proposed_value=float(spec["value"]),
                        reason=reason,
                        session_id=session_id,
                        parameter_name=str(spec.get("parameter", spec.get("parameter_name", ""))),
                        unit=str(spec.get("unit", "")),
                        track_name=str(spec.get("track_name", "")),
                    )
            except (KeyError, TypeError, ValueError) as exc:
                return {"ok": False, "error": f"Recipe step {position} is missing an exact typed field: {exc}."}
            if not result.get("ok"):
                return {"ok": False, "error": f"Recipe step {position} could not be proposed: {result.get('error', 'Live target unavailable')}"}
            child = dict(result["proposal"])
            # The shared service's track proposals use ``action`` while the
            # legacy-compatible device proposal uses ``operation``. Recipes
            # expose one normalized action field so execution cannot silently
            # skip a typed device step.
            if not child.get("action") and child.get("operation"):
                child["action"] = child["operation"]
            # Child confirmation material is not valid for recipe execution;
            # the recipe gets one token bound to all exact child values.
            child.pop("confirmation_token", None)
            child.pop("confirmation_meta", None)
            child_steps.append(child)

        recipe = {
            "schema": RECIPE_SCHEMA,
            "action_id": f"recipe-{uuid.uuid4().hex}",
            "action": "recipe",
            "operation": "recipe",
            "target": "ableton_recipe",
            "steps": child_steps,
            "step_count": len(child_steps),
            "reason": str(reason)[:512],
            "confidence": 1.0,
            "risk": "local_multi_step_mutation",
            "requires_confirmation": True,
            "timestamp": time.time(),
        }
        safe_evidence = _safe_source_evidence(source_evidence)
        if safe_evidence is not None:
            recipe["source_evidence"] = safe_evidence
        token, meta = issue_confirmation(
            session_id=session_id,
            service_id="ableton_recipe",
            text=_recipe_text(recipe),
            ttl_seconds=300,
        )
        recipe["confirmation_token"] = token
        recipe["confirmation_meta"] = meta
        return {"ok": True, "proposal": recipe}

    def _apply_step(self, step: dict[str, Any]) -> tuple[bool, dict[str, Any], str]:
        """Apply one step after fresh identity checks and verify its readback."""
        action = str(step.get("action", ""))
        if action in SUPPORTED_TRACK_ACTIONS:
            state = self.service.snapshot()
            track = _exact_track(state, int(step["track_index"]), str(step.get("track_name", "")))
            field = SUPPORTED_TRACK_ACTIONS[action][0]
            if track is None:
                return False, {}, "track identity changed"
            before = track.get(field)
            if not _values_match(before, step.get("before")):
                return False, {}, f"{field} changed since the recipe was proposed"
            writers = {
                "set_volume": lambda: self.client.set_track_volume(int(step["track_index"]), float(step["after"])),
                "set_pan": lambda: self.client.set_track_pan(int(step["track_index"]), float(step["after"])),
                "set_mute": lambda: self.client.set_track_mute(int(step["track_index"]), bool(step["after"])),
                "set_solo": lambda: self.client.set_track_solo(int(step["track_index"]), bool(step["after"])),
                "set_arm": lambda: self.client.set_track_arm(int(step["track_index"]), bool(step["after"])),
                "rename_track": lambda: self.client.set_track_name(int(step["track_index"]), str(step["after"])),
            }
            write_error = ""
            try:
                write_ok = bool(writers[action]())
            except Exception as exc:
                write_ok = False
                write_error = f"{type(exc).__name__}: {exc}"
            post_name = "" if action == "rename_track" else str(step.get("track_name", ""))
            try:
                post = _exact_track(self.service.snapshot(), int(step["track_index"]), post_name)
                readback_error = ""
            except Exception as exc:
                post = None
                readback_error = f"{type(exc).__name__}: {exc}"
            readback = post.get(field) if post else None
            readback_matches = _values_match(readback, step.get("after"))
            changed = not _values_match(before, step.get("after"))
            verified = readback_matches and (write_ok or changed)
            receipt = {
                "action": action, "target": _step_target(step), "before": before,
                "requested": step.get("after"), "readback": readback, "verified": verified,
                "write_acknowledgement": "confirmed" if write_ok else ("unacknowledged_write_reconciled" if verified else "not_confirmed"),
                **({"write_error": write_error} if write_error else {}),
                **({"readback_error": readback_error} if readback_error else {}),
            }
            failure = readback_error or write_error or "track readback did not verify"
            return verified, receipt, "" if verified else failure

        if action in SUPPORTED_TRANSPORT_ACTIONS:
            state = self.service.snapshot()
            before = bool(state.get("is_playing", False))
            if before != bool(step.get("before")):
                return False, {}, "transport state changed since the recipe was proposed"
            write_error = ""
            try:
                write_ok = bool(self.client.start_playback() if action == "transport_play" else self.client.stop_playback())
            except Exception as exc:
                write_ok = False
                write_error = f"{type(exc).__name__}: {exc}"
            try:
                readback = bool(self.service.snapshot().get("is_playing", False))
                readback_error = ""
            except Exception as exc:
                readback = None
                readback_error = f"{type(exc).__name__}: {exc}"
            readback_matches = readback == bool(step.get("after"))
            changed = before != bool(step.get("after"))
            verified = readback_matches and (write_ok or changed)
            receipt = {
                "action": action, "target": _step_target(step), "before": before,
                "requested": step.get("after"), "readback": readback, "verified": verified,
                "write_acknowledgement": "confirmed" if write_ok else ("unacknowledged_write_reconciled" if verified else "not_confirmed"),
                **({"write_error": write_error} if write_error else {}),
                **({"readback_error": readback_error} if readback_error else {}),
            }
            failure = readback_error or write_error or "transport readback did not verify"
            return verified, receipt, "" if verified else failure

        if action == "set_send":
            state = self.service.snapshot()
            track = _exact_track(state, int(step["track_index"]), str(step.get("track_name", "")))
            if track is None:
                return False, {}, "track identity changed"
            try:
                return_tracks = self.client.get_return_tracks()
                return_track, return_error = _find_return_track(
                    return_tracks,
                    int(step["return_track_index"]),
                    str(step.get("return_track_name", "")),
                )
            except Exception as exc:
                return False, {}, f"return-track inspection failed: {type(exc).__name__}: {exc}"
            if return_error or return_track is None:
                return False, {}, return_error or "return-track identity changed"
            try:
                before = self.client.get_track_send(int(step["track_index"]), int(step["return_track_index"]))
            except Exception as exc:
                return False, {}, f"send inspection failed: {type(exc).__name__}: {exc}"
            if before is None or not _values_match(before, step.get("before")):
                return False, {}, "send value changed since the recipe was proposed"
            write_error = ""
            try:
                write_ok = bool(self.client.set_track_send(int(step["track_index"]), int(step["return_track_index"]), float(step["after"])))
            except Exception as exc:
                write_ok = False
                write_error = f"{type(exc).__name__}: {exc}"
            try:
                readback = self.client.get_track_send(int(step["track_index"]), int(step["return_track_index"]))
                readback_error = ""
            except Exception as exc:
                readback = None
                readback_error = f"{type(exc).__name__}: {exc}"
            readback_matches = readback is not None and _values_match(readback, step.get("after"))
            changed = not _values_match(before, step.get("after"))
            verified = readback_matches and (write_ok or changed)
            receipt = {
                "action": action, "target": _step_target(step), "before": before,
                "requested": step.get("after"), "readback": readback, "verified": verified,
                "write_acknowledgement": "confirmed" if write_ok else ("unacknowledged_write_reconciled" if verified else "not_confirmed"),
                **({"write_error": write_error} if write_error else {}),
                **({"readback_error": readback_error} if readback_error else {}),
            }
            failure = readback_error or write_error or "send readback did not verify"
            return verified, receipt, "" if verified else failure

        state = self.service.snapshot()
        track = _exact_track(state, int(step["track_index"]), str(step.get("track_name", "")))
        if track is None:
            return False, {}, "track identity changed"
        devices = track.get("devices") or []
        device_index = int(step["device_index"])
        device = devices[device_index] if 0 <= device_index < len(devices) else None
        if not isinstance(device, dict) or str(device.get("name", "")) != str(step.get("device_name", "")):
            return False, {}, "device identity changed"
        info = self.client.get_device_parameters(int(step["track_index"]), device_index)
        if not info.get("success"):
            return False, {}, "device inspection failed"
        parameter = _find_parameter(info, int(step["parameter_index"]), str(step.get("parameter", "")))
        if parameter is None or not _values_match(parameter.get("value"), step.get("before")):
            return False, {}, "device parameter changed since the recipe was proposed"
        requested = float(step["after"])
        write_error = ""
        try:
            write_ok = bool(self.client.set_device_parameter(int(step["track_index"]), device_index, int(step["parameter_index"]), requested))
        except Exception as exc:
            write_ok = False
            write_error = f"{type(exc).__name__}: {exc}"
        try:
            post_info = self.client.get_device_parameters(int(step["track_index"]), device_index)
            readback_error = ""
        except Exception as exc:
            post_info = {"success": False}
            readback_error = f"{type(exc).__name__}: {exc}"
        post_parameter = _find_parameter(post_info, int(step["parameter_index"]), str(step.get("parameter", ""))) if post_info.get("success") else None
        readback = post_parameter.get("value") if post_parameter else None
        readback_matches = _values_match(readback, requested)
        changed = not _values_match(parameter.get("value"), requested)
        verified = readback_matches and (write_ok or changed)
        receipt = {
            "action": action, "target": _step_target(step), "before": parameter.get("value"),
            "requested": requested, "readback": readback, "verified": verified,
            "write_acknowledgement": "confirmed" if write_ok else ("unacknowledged_write_reconciled" if verified else "not_confirmed"),
            **({"write_error": write_error} if write_error else {}),
            **({"readback_error": readback_error} if readback_error else {}),
        }
        failure = readback_error or write_error or "device readback did not verify"
        return verified, receipt, "" if verified else failure

    def _restore_step(self, receipt: dict[str, Any]) -> bool:
        target = receipt.get("target") or {}
        action = str(receipt.get("action", ""))
        try:
            if action in SUPPORTED_TRACK_ACTIONS:
                field = SUPPORTED_TRACK_ACTIONS[action][0]
                writers = {
                    "set_volume": lambda: self.client.set_track_volume(int(target["track_index"]), float(receipt["before"])),
                    "set_pan": lambda: self.client.set_track_pan(int(target["track_index"]), float(receipt["before"])),
                    "set_mute": lambda: self.client.set_track_mute(int(target["track_index"]), bool(receipt["before"])),
                    "set_solo": lambda: self.client.set_track_solo(int(target["track_index"]), bool(receipt["before"])),
                    "set_arm": lambda: self.client.set_track_arm(int(target["track_index"]), bool(receipt["before"])),
                    "rename_track": lambda: self.client.set_track_name(int(target["track_index"]), str(receipt["before"])),
                }
                try:
                    writers[action]()
                except Exception:
                    pass
                restore_name = str(receipt["before"]) if action == "rename_track" else str(target.get("track_name", ""))
                restored = _exact_track(self.service.snapshot(), int(target["track_index"]), restore_name)
                return restored is not None and _values_match(restored.get(field), receipt["before"])
            if action in SUPPORTED_TRANSPORT_ACTIONS:
                try:
                    self.client.start_playback() if bool(receipt["before"]) else self.client.stop_playback()
                except Exception:
                    pass
                return bool(self.service.snapshot().get("is_playing", False)) == bool(receipt["before"])
            if action == "set_send":
                try:
                    # A send belongs to both a source track and a return
                    # track.  Re-check the source identity before issuing a
                    # compensating write; otherwise a renamed/replaced track
                    # at the same index could receive the old send value.
                    source_track = _exact_track(
                        self.service.snapshot(),
                        int(target["track_index"]),
                        str(target.get("track_name", "")),
                    )
                    if source_track is None:
                        return False
                    return_track, return_error = _find_return_track(
                        self.client.get_return_tracks(),
                        int(target["return_track_index"]),
                        str(target.get("return_track_name", "")),
                    )
                    if return_error or return_track is None:
                        return False
                    self.client.set_track_send(int(target["track_index"]), int(target["return_track_index"]), float(receipt["before"]))
                    restored = self.client.get_track_send(int(target["track_index"]), int(target["return_track_index"]))
                    return restored is not None and _values_match(restored, receipt["before"])
                except Exception:
                    return False
            try:
                self.client.set_device_parameter(int(target["track_index"]), int(target["device_index"]), int(target["parameter_index"]), float(receipt["before"]))
            except Exception:
                pass
            info = self.client.get_device_parameters(int(target["track_index"]), int(target["device_index"]))
            parameter = _find_parameter(info, int(target["parameter_index"]), str(target.get("parameter", ""))) if info.get("success") else None
            return parameter is not None and _values_match(parameter.get("value"), receipt["before"])
        except Exception:
            return False

    def execute_recipe(
        self,
        recipe: dict[str, Any],
        *,
        confirm_token: str,
        session_id: str,
        idempotency_key: str = "",
    ) -> dict[str, Any]:
        """Execute a recipe with per-step verification and reverse rollback."""
        if not isinstance(recipe, dict) or recipe.get("schema") != RECIPE_SCHEMA:
            return {"ok": False, "error": "A valid KENN recipe proposal is required."}
        steps = recipe.get("steps")
        if not isinstance(steps, list) or not 1 <= len(steps) <= MAX_RECIPE_STEPS:
            return {"ok": False, "error": f"Recipes must contain between 1 and {MAX_RECIPE_STEPS} steps."}
        if not recipe.get("requires_confirmation") or str(recipe.get("confirmation_token", "")) != str(confirm_token):
            return {"ok": False, "error": "Confirmation is required for this exact recipe."}
        key = str(idempotency_key or recipe.get("action_id") or "").strip()
        if not key:
            return {"ok": False, "error": "An idempotency key is required for a recipe mutation."}
        with _LOCK:
            if key in _USED_IDEMPOTENCY_KEYS or key in _IN_FLIGHT_IDEMPOTENCY_KEYS:
                return {"ok": False, "error": "This recipe was already executed or is already in progress.", "idempotency_key": key}
            _IN_FLIGHT_IDEMPOTENCY_KEYS.add(key)
        if not consume_confirmation(confirm_token, session_id=session_id, service_id="ableton_recipe", text=_recipe_text(recipe)):
            with _LOCK:
                _IN_FLIGHT_IDEMPOTENCY_KEYS.discard(key)
            return {"ok": False, "error": "Invalid, expired, mismatched, or already-used recipe confirmation token."}

        applied: list[dict[str, Any]] = []
        failure = ""
        for position, step in enumerate(steps, start=1):
            try:
                verified, receipt, failure = self._apply_step(step)
            except Exception as exc:
                verified, receipt, failure = False, {}, f"step raised {type(exc).__name__}: {exc}"
            if receipt:
                applied.append(receipt)
            if not verified:
                failure = f"Step {position} failed: {failure}"
                break

        rollback_results = []
        if failure:
            for receipt in reversed(applied):
                rollback_results.append(self._restore_step(receipt))
            rolled_back = all(rollback_results) and len(rollback_results) == len(applied)
            with _LOCK:
                _mark_used(key)
            status = "failed_rolled_back" if rolled_back else "partial_recovery"
            error = f"Recipe aborted; {'all completed steps were restored' if rolled_back else 'rollback could not be fully verified'}. {failure}"
            failure_receipt = {
                "schema": RECIPE_RECEIPT_SCHEMA,
                "receipt_id": f"receipt-{uuid.uuid4().hex}",
                "action_id": recipe.get("action_id"),
                "action": "recipe",
                "idempotency_key": key,
                "status": status,
                "verified": False,
                "timestamp": time.time(),
                "step_count": len(applied),
                "step_receipts": applied,
                "rolled_back": rolled_back,
                "rollback": rollback_results,
                "retry_safe": "unsafe" if rolled_back else "requires_inspection",
                "error": error,
            }
            return {
                "ok": False,
                "status": status,
                "error": error,
                "rolled_back": rolled_back,
                "step_receipts": applied,
                "rollback": rollback_results,
                "receipt": failure_receipt,
            }

        with _LOCK:
            _mark_used(key)

        # Calculate net energy shift to provide zero-bias A/B audition loudness trim
        net_vol_delta = 0.0
        vol_step_count = 0
        for item in applied:
            if item.get("action") == "set_volume":
                try:
                    b = float(item.get("before", 0.85))
                    r = float(item.get("requested", b))
                    net_vol_delta += (r - b)
                    vol_step_count += 1
                except Exception:
                    pass
        # Approximate dB compensation: 1 fader unit ~ 25 dB in standard working range
        audition_trim_db = round(-net_vol_delta * 25.0, 2) if vol_step_count > 0 else 0.0

        receipt = {
            "schema": RECIPE_RECEIPT_SCHEMA,
            "receipt_id": f"receipt-{uuid.uuid4().hex}",
            "action_id": recipe.get("action_id"),
            "action": "recipe",
            "idempotency_key": key,
            "status": "applied",
            "verified": True,
            "timestamp": time.time(),
            "step_count": len(applied),
            "step_receipts": applied,
            "audition_loudness_trim_db": audition_trim_db,
            "undo_steps": [
                {"action": item["action"], "target": item["target"], "before": item["requested"], "requested": item["before"], "readback": item["requested"], "verified": False}
                for item in reversed(applied)
            ],
        }
        if isinstance(recipe.get("source_evidence"), dict):
            receipt["source_evidence"] = recipe["source_evidence"]
        return {"ok": True, "status": "applied", "receipt": receipt}

    def propose_undo(self, receipt: dict[str, Any], *, session_id: str) -> dict[str, Any]:
        """Create a fresh recipe proposal that reverses a verified recipe."""
        if not isinstance(receipt, dict) or receipt.get("schema") != RECIPE_RECEIPT_SCHEMA:
            return {"ok": False, "error": "A verified KENN recipe receipt is required for undo."}
        if receipt.get("status") != "applied" or not receipt.get("verified"):
            return {"ok": False, "error": "Only a verified applied recipe can be undone."}
        step_receipts = receipt.get("step_receipts")
        if not isinstance(step_receipts, list) or not step_receipts:
            return {"ok": False, "error": "Recipe receipt has no exact steps for undo."}
        inverse_steps: list[dict[str, Any]] = []
        for item in reversed(step_receipts):
            action = str(item.get("action", ""))
            target = item.get("target") or {}
            if action in SUPPORTED_TRACK_ACTIONS:
                inverse_steps.append({
                    "action": action,
                    "track_index": target.get("track_index"),
                    "track_name": target.get("track_name", ""),
                    "value": item.get("before"),
                })
            elif action in SUPPORTED_TRANSPORT_ACTIONS:
                inverse_steps.append({
                    "action": "transport_play" if bool(item.get("before")) else "transport_stop",
                })
            elif action == "set_device_parameter":
                inverse_steps.append({
                    "action": action,
                    "track_index": target.get("track_index"),
                    "track_name": target.get("track_name", ""),
                    "device_index": target.get("device_index"),
                    "device_name": target.get("device_name", ""),
                    "parameter_index": target.get("parameter_index"),
                    "parameter": target.get("parameter", ""),
                    "value": item.get("before"),
                    "unit": "",
                })
            elif action == "set_send":
                inverse_steps.append({
                    "action": action,
                    "track_index": target.get("track_index"),
                    "track_name": target.get("track_name", ""),
                    "return_track_index": target.get("return_track_index"),
                    "return_track_name": target.get("return_track_name", ""),
                    "value": item.get("before"),
                    "unit": "normalized",
                })
            else:
                return {"ok": False, "error": f"Recipe step '{action}' is not undoable."}
        return self.propose_recipe(
            inverse_steps,
            reason=f"Restore verified KENN recipe {receipt.get('receipt_id', '')}.",
            session_id=session_id,
            source_evidence=receipt.get("source_evidence"),
        )


__all__ = ["LiveRecipeService", "RECIPE_SCHEMA", "RECIPE_RECEIPT_SCHEMA", "MAX_RECIPE_STEPS"]
