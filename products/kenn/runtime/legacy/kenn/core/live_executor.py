"""Live Control Executor for Ableton Live 12.

Applies verified, HMAC-signed ActionProposal payloads, performs read-back verification against Live,
emits execution receipts, and handles single-parameter undo restoration.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from kenn.ableton_osc_bridge import AbletonOSCClient, live_client
from kenn.core.confirmation import consume_confirmation
from kenn.plugin_actions import validate_apply_request, SCHEMA

logger = logging.getLogger(__name__)

RECEIPT_SCHEMA = "kenn.execution_receipt.v1"
BATCH_RECEIPT_SCHEMA = "kenn.batch_execution_receipt.v1"


class LiveExecutor:
    """Legacy executor retained for rollback-test compatibility.

    Production mutation entry points use ``LiveActionService``. Direct use of
    this legacy executor is disabled by default so a batch proposal cannot
    bypass the shared target, confirmation, idempotency, and receipt policy.
    The explicit opt-in exists only for isolated compatibility tests while
    batch migration is pending.
    """

    def __init__(self, osc_client: Optional[AbletonOSCClient] = None, *, allow_legacy_mutation: bool = False):
        self.osc_client = osc_client or live_client
        self.allow_legacy_mutation = allow_legacy_mutation

    def apply_batch_proposal(
        self,
        batch_proposal: Dict[str, Any],
        confirm_token: str,
        session_id: str = "default_session",
    ) -> Dict[str, Any]:
        """Apply a confirmed BatchActionProposal with atomic rollback on any step failure."""
        if not self.allow_legacy_mutation:
            return {"ok": False, "error": "Legacy batch Live mutation is disabled; use LiveActionService."}
        valid_res = validate_apply_request(batch_proposal)
        if not valid_res.get("ok"):
            return {"ok": False, "error": f"Invalid batch proposal payload: {valid_res.get('error')}"}

        child_proposals = batch_proposal.get("proposals", [])
        token_parts: list[str] = []
        for p in child_proposals:
            t_idx = int(p.get("track_index", 0))
            d_idx = int(p.get("device_index", 0))
            p_idx = int(p.get("parameter_index", 0))
            val = float(p.get("after", 0.0))
            token_parts.append(f"{t_idx}:{d_idx}:{p_idx}:{val}")

        req_text = f"set_batch_device_parameter:{';'.join(token_parts)}"
        is_verified = consume_confirmation(
            confirm_token,
            session_id=session_id,
            service_id="ableton_control",
            text=req_text,
        )

        if not is_verified:
            return {"ok": False, "error": "Invalid, mismatched, or expired confirmation token for batch action."}

        applied_receipts: list[dict[str, Any]] = []
        rollback_needed = False
        failure_error = ""

        # Execute each step sequentially
        for idx, child in enumerate(child_proposals):
            track_idx = int(child.get("track_index", 0))
            device_idx = int(child.get("device_index", 0))
            param_idx = int(child.get("parameter_index", 0))
            proposed_val = float(child.get("after", 0.0))

            # Snapshot pre-write state
            pre_info = self.osc_client.get_device_parameters(track_idx, device_idx)
            if not pre_info.get("success"):
                rollback_needed = True
                failure_error = f"Step {idx} pre-write Live state query failed: {pre_info.get('error')}"
                break

            params = pre_info.get("parameters", [])
            if param_idx < 0 or param_idx >= len(params):
                rollback_needed = True
                failure_error = f"Step {idx} target parameter index out of bounds."
                break

            before_val = float(params[param_idx].get("value", 0.0))
            param_name = params[param_idx].get("name", "")
            expected_name = str(child.get("parameter", ""))
            expected_device = str(child.get("device_name", ""))
            if expected_device and str(pre_info.get("device_name", "")) != expected_device:
                rollback_needed = True
                failure_error = f"Step {idx} device identity changed since proposal."
                break
            if expected_name and param_name != expected_name:
                rollback_needed = True
                failure_error = f"Step {idx} parameter identity changed since proposal."
                break
            if "before" in child and abs(before_val - float(child["before"])) > 0.01:
                rollback_needed = True
                failure_error = f"Step {idx} parameter value changed since proposal."
                break
            valid_range = child.get("valid_range") or []
            if len(valid_range) == 2 and not float(valid_range[0]) <= proposed_val <= float(valid_range[1]):
                rollback_needed = True
                failure_error = f"Step {idx} proposed value is outside the current parameter range."
                break

            # Execute parameter write
            write_success = self.osc_client.set_device_parameter(track_idx, device_idx, param_idx, proposed_val)
            if not write_success:
                rollback_needed = True
                failure_error = f"Step {idx} write rejected by Ableton Live."
                break

            # Read-back verification
            time.sleep(0.05)
            post_info = self.osc_client.get_device_parameters(track_idx, device_idx)
            post_val = float(proposed_val)
            step_verified = False
            if post_info.get("success"):
                post_params = post_info.get("parameters", [])
                if 0 <= param_idx < len(post_params):
                    post_val = float(post_params[param_idx].get("value", 0.0))
                    step_verified = abs(post_val - proposed_val) <= 0.01

            applied_receipts.append({
                "action_id": child.get("id"),
                "track_index": track_idx,
                "device_index": device_idx,
                "parameter_index": param_idx,
                "parameter_name": param_name,
                "before_value": before_val,
                "requested_value": proposed_val,
                "readback_value": post_val,
                "verified": step_verified,
            })
            if not step_verified:
                rollback_needed = True
                failure_error = f"Step {idx} read-back verification failed."
                break

        # Atomic Rollback on Failure
        if rollback_needed:
            logger.warning(f"Batch transaction failed at step {len(applied_receipts)}. Initiating atomic rollback...")
            rollback_complete = True
            for receipt in reversed(applied_receipts):
                restored = False
                # UDP loss can affect both the restore write and its
                # readback. Retry as a bounded transaction and report failure
                # if Live still cannot confirm the original value.
                for _ in range(8):
                    self.osc_client.set_device_parameter(
                        receipt["track_index"],
                        receipt["device_index"],
                        receipt["parameter_index"],
                        receipt["before_value"],
                    )
                    check = self.osc_client.get_device_parameters(
                        receipt["track_index"], receipt["device_index"]
                    )
                    params = check.get("parameters", []) if check.get("success") else []
                    if receipt["parameter_index"] < len(params):
                        current = float(params[receipt["parameter_index"]].get("value", 0.0))
                        if abs(current - float(receipt["before_value"])) <= 0.01:
                            restored = True
                            break
                rollback_complete = rollback_complete and restored
            return {
                "ok": False,
                "error": f"Batch transaction aborted and {'atomically rolled back' if rollback_complete else 'rollback could not be verified'}. Root cause: {failure_error}",
                "rolled_back": rollback_complete,
                "steps_completed": len(applied_receipts),
            }

        batch_receipt = {
            "schema": BATCH_RECEIPT_SCHEMA,
            "batch_id": batch_proposal.get("id"),
            "status": "applied",
            "timestamp": time.time(),
            "step_count": len(applied_receipts),
            "step_receipts": applied_receipts,
            "undo_payload": {
                "schema": BATCH_RECEIPT_SCHEMA,
                "batch_id": batch_proposal.get("id"),
                "restore_steps": [
                    {
                        "track_index": r["track_index"],
                        "device_index": r["device_index"],
                        "parameter_index": r["parameter_index"],
                        "restore_value": r["before_value"],
                    }
                    for r in reversed(applied_receipts)
                ],
            },
        }
        return {"ok": True, "receipt": batch_receipt}

    def undo_batch_action(self, batch_undo_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Restore all parameters changed in a batch transaction in reverse order."""
        restore_steps = batch_undo_payload.get("restore_steps", [])
        if not restore_steps:
            return {"ok": False, "error": "Invalid batch undo payload."}

        undone_count = 0
        for step in restore_steps:
            res = self.undo_action(step)
            if res.get("ok"):
                undone_count += 1

        return {
            "ok": True,
            "status": "undone",
            "batch_id": batch_undo_payload.get("batch_id"),
            "undone_steps": undone_count,
            "total_steps": len(restore_steps),
        }

    def apply_proposal(
        self,
        proposal: Dict[str, Any],
        confirm_token: str,
        session_id: str = "default_session",
    ) -> Dict[str, Any]:
        """Apply a confirmed ActionProposal after verifying HMAC token and performing readback verification."""
        if not self.allow_legacy_mutation:
            return {"ok": False, "error": "Legacy Live mutation is disabled; use LiveActionService."}
        if proposal.get("schema") == "kenn.batch_action_proposal.v1":
            return self.apply_batch_proposal(proposal, confirm_token, session_id=session_id)
        # 1. Validate proposal structure
        valid_res = validate_apply_request(proposal)
        if not valid_res.get("ok"):
            return {"ok": False, "error": f"Invalid proposal payload: {valid_res.get('error')}"}

        target = proposal.get("target")
        track_idx = int(proposal.get("track_index", 0))
        device_idx = int(proposal.get("device_index", 0))
        param_idx = int(proposal.get("parameter_index", 0))
        proposed_val = float(proposal.get("after", 0.0))

        # 2. Verify HMAC confirmation token binding
        req_text = f"set_device_parameter:{track_idx}:{device_idx}:{param_idx}:{proposed_val}"
        is_verified = consume_confirmation(
            confirm_token,
            session_id=session_id,
            service_id="ableton_control",
            text=req_text,
        )

        if not is_verified:
            return {"ok": False, "error": "Invalid, mismatched, or expired confirmation token."}

        # 3. Snapshot pre-write value from Live
        pre_info = self.osc_client.get_device_parameters(track_idx, device_idx)
        if not pre_info.get("success"):
            return {"ok": False, "error": f"Failed pre-write Live state query: {pre_info.get('error')}"}

        params = pre_info.get("parameters", [])
        if param_idx < 0 or param_idx >= len(params):
            return {"ok": False, "error": "Target parameter index out of bounds."}

        before_val = float(params[param_idx].get("value", 0.0))
        param_name = params[param_idx].get("name", "")
        if proposal.get("device_name") and str(pre_info.get("device_name", "")) != str(proposal.get("device_name")):
            return {"ok": False, "error": "Live device identity changed since the proposal was created."}
        if proposal.get("parameter") and param_name != proposal.get("parameter"):
            return {"ok": False, "error": "Live parameter identity changed since the proposal was created."}
        if "before" in proposal and abs(before_val - float(proposal["before"])) > 0.01:
            return {"ok": False, "error": "Live parameter value changed since the proposal was created; make a new proposal."}

        # 4. Execute parameter write to Ableton Live
        write_success = self.osc_client.set_device_parameter(
            track_idx, device_idx, param_idx, proposed_val
        )

        if not write_success:
            return {"ok": False, "error": "Ableton Live rejected or failed to acknowledge parameter write."}

        # 5. Read-back verification
        time.sleep(0.05)  # brief pause for DAW update roundtrip
        post_info = self.osc_client.get_device_parameters(track_idx, device_idx)
        verified = False
        post_val = float(proposed_val)

        if post_info.get("success"):
            post_params = post_info.get("parameters", [])
            if 0 <= param_idx < len(post_params):
                post_val = float(post_params[param_idx].get("value", 0.0))
                # Tolerant check for float rounding
                verified = abs(post_val - proposed_val) <= 0.01

        # 6. Build execution receipt. An unverified write is a failure, not a
        # successful execution claim; the caller must inspect/recover it.
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "action_id": proposal.get("id"),
            "status": "applied" if verified else "applied_unverified",
            "verified": verified,
            "timestamp": time.time(),
            "target": target,
            "track_index": track_idx,
            "device_index": device_idx,
            "parameter_index": param_idx,
            "parameter_name": param_name,
            "before_value": before_val,
            "requested_value": proposed_val,
            "readback_value": post_val,
            "undo_payload": {
                "target": target,
                "track_index": track_idx,
                "device_index": device_idx,
                "parameter_index": param_idx,
                "parameter_name": param_name,
                "restore_value": before_val,
            },
        }

        if not verified:
            return {"ok": False, "error": "Live write was sent but read-back verification failed; no successful execution receipt was issued.", "receipt": receipt}
        return {"ok": True, "receipt": receipt}

    def undo_action(self, undo_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Restore previous parameter value using an execution receipt's undo payload."""
        if undo_payload.get("schema") == BATCH_RECEIPT_SCHEMA:
            return self.undo_batch_action(undo_payload)
        try:
            track_idx = int(undo_payload["track_index"])
            device_idx = int(undo_payload["device_index"])
            param_idx = int(undo_payload["parameter_index"])
            restore_val = float(undo_payload.get("restore_value", undo_payload.get("value", 0.0)))
        except (KeyError, TypeError, ValueError) as exc:
            return {"ok": False, "error": f"Invalid undo payload parameters: {exc}"}

        success = self.osc_client.set_device_parameter(track_idx, device_idx, param_idx, restore_val)
        if not success:
            return {"ok": False, "error": "Failed to apply undo parameter restoration to Ableton Live."}

        # Verification readback
        post_info = self.osc_client.get_device_parameters(track_idx, device_idx)
        verified = False
        if post_info.get("success"):
            params = post_info.get("parameters", [])
            if 0 <= param_idx < len(params):
                current_val = float(params[param_idx].get("value", 0.0))
                verified = abs(current_val - restore_val) <= 0.01

        if not verified:
            return {
                "ok": False,
                "status": "undo_unverified",
                "error": "Undo write was sent but Live read-back verification failed.",
                "verified": False,
                "restored_value": restore_val,
            }
        return {
            "ok": True,
            "status": "undone",
            "verified": verified,
            "restored_value": restore_val,
            "track_index": track_idx,
            "device_index": device_idx,
            "parameter_index": param_idx,
        }
