"""Confirm one experimental export without creating another Live write authority.

The job module owns audio and reports; LiveActionService owns permission and
confirmation. No default runtime installs this candidate or exposes it over HTTP.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import uuid
from typing import Any

from kenn.core.action_policy import action_allowed
from kenn.core.actions.common import (
    _ACTION_LOCK, _IN_FLIGHT_IDEMPOTENCY_KEYS, _USED_IDEMPOTENCY_KEYS,
    _finish_idempotency_key,
)
from kenn.core.confirmation import consume_confirmation, issue_confirmation


OFFLINE_SCAN_PROPOSAL_SCHEMA = "kenn.offline_scan_proposal.v1"


def _contract_text(proposal: dict[str, Any]) -> str:
    # Hash before confirmation's numeric normalization: range strings and set
    # fingerprints must bind byte-for-byte, including a changed digit in a hash.
    contract = {key: value for key, value in proposal.items()
                if key not in {"confirmation_token", "confirmation_meta"}}
    encoded = json.dumps(contract, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class OfflineScanActionsMixin:
    """Gate an explicitly injected scan candidate with existing owner confirmations."""

    def _offline_scan_error(self) -> str:
        if os.getenv("KENN_EXPERIMENTAL_LIVE_EXPORT") != "1":
            # An installed helper alone must never make Live UI automation live.
            return "Offline export is disabled; the experimental export gate is closed."
        if not action_allowed("daw_control"):
            # Direct service callers receive the same policy as HTTP callers.
            return "Offline export is disabled by the existing DAW control policy."
        if self.offline_scans is None:
            # Range discovery and Live control profiles remain qualification gates.
            return "No qualified offline export candidate is configured."
        return ""

    def propose_offline_scan(
        self, *, source: dict[str, Any], export_request: dict[str, Any], session_id: str,
    ) -> dict[str, Any]:
        """Bind a producer-confirmed range and source to a single-use proposal.

        The injected job module must obtain a fresh fingerprint independently;
        snapshot() and its cached fallback cannot authenticate an entire set.
        """
        error = self._offline_scan_error()
        if error:
            return {"ok": False, "error": error}
        if not isinstance(session_id, str) or not session_id.strip() or len(session_id) > 256:
            # Anonymous proposals cannot isolate status, cancellation or reports.
            return {"ok": False, "error": "A bounded owner session is required."}
        try:
            validation = self.offline_scans.validate_current(source=source, export_request=export_request)
        except (TypeError, ValueError):
            # Validation neither opens Live nor allocates a job; an old set or
            # unsupported range cannot become a confirmable export contract.
            return {"ok": False, "error": "The current source and export range could not be validated."}
        proposal = {
            "schema": OFFLINE_SCAN_PROPOSAL_SCHEMA,
            "action_id": f"offline-scan-{uuid.uuid4().hex}",
            "action": "offline_scan",
            "source": copy.deepcopy(validation["source"]),
            "export_request": copy.deepcopy(validation["export_request"]),
            "requires_confirmation": True,
            "scope": "producer_confirmed_range",
        }
        token, meta = issue_confirmation(
            session_id=session_id, service_id="ableton_offline_scan", text=_contract_text(proposal),
        )
        proposal.update(confirmation_token=token, confirmation_meta=meta)
        return {"ok": True, "proposal": proposal}

    def execute_offline_scan(
        self, proposal: dict[str, Any], *, confirm_token: str, session_id: str,
        idempotency_key: str = "", correlation_id: str = "",
    ) -> dict[str, Any]:
        """Start an owned scan once; a failed start still consumes its confirmation."""
        error = self._offline_scan_error()
        if error:
            return {"ok": False, "error": error}
        if not isinstance(proposal, dict) or proposal.get("schema") != OFFLINE_SCAN_PROPOSAL_SCHEMA:
            # A different action contract must use its own confirmation service.
            return {"ok": False, "error": "Unsupported offline scan proposal."}
        if not isinstance(session_id, str) or not session_id.strip() or len(session_id) > 256:
            # Owner identity participates in both the token and retry namespace.
            return {"ok": False, "error": "A bounded owner session is required."}
        if not isinstance(idempotency_key, str) or not idempotency_key.strip() or len(idempotency_key) > 256:
            # A caller must explicitly distinguish a retry from a new scan.
            return {"ok": False, "error": "An offline scan idempotency key is required."}
        try:
            text = _contract_text(proposal)
        except (TypeError, ValueError):
            # Malformed browser payloads never reach the helper or token store.
            return {"ok": False, "error": "Invalid offline scan proposal."}
        key = f"offline_scan:{session_id}:{idempotency_key}"
        with _ACTION_LOCK:
            if key in _USED_IDEMPOTENCY_KEYS or key in _IN_FLIGHT_IDEMPOTENCY_KEYS:
                # The first request may still own Live's export dialog.
                return {"ok": False, "error": "This offline scan request has already been used."}
            if not consume_confirmation(
                confirm_token, session_id=session_id, service_id="ableton_offline_scan", text=text,
            ):
                # This also rejects foreign owners, edits, expiry and token replay.
                return {"ok": False, "error": "Offline scan confirmation is invalid or already used."}
            _IN_FLIGHT_IDEMPOTENCY_KEYS.add(key)
        try:
            return self.offline_scans.start(
                owner_id=session_id, source=proposal["source"], export_request=proposal["export_request"],
            )
        except Exception:
            # Do not repeat an uncertain export after a failed start; its job
            # module owns recovery and this request requires a fresh proposal.
            return {"ok": False, "error": "Offline scan could not start; inspect its owned job before retrying."}
        finally:
            _finish_idempotency_key(key)
