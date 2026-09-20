"""Standalone-extraction compatibility shims.

Thursday's live deployment (`Audio_Too/thursday`) runs inside the Audio_Too
Flask app and can import small, stable primitives directly from the
`audio_too` platform package (`audio_too.contracts`, `audio_too.errors`).
The standalone extraction (this repo) does not have `audio_too` on its path
and must not depend on it for anything genuinely self-contained.

This module vendors the minimal subset of those primitives that:
  1. is small and semantically stable (unlikely to drift from the source of
     truth in a way that matters), and
  2. is needed at *import time* by modules in this package (so it can't be
     deferred behind a lazy, call-time import the way real cross-repo
     integration points are — see docs/EXTRACTION_COUPLING.md).

Do NOT add anything here that is a genuine shared contract object validated
elsewhere (e.g. `audio_too.contracts.Capability`, `CommandEnvelope`,
`ResultEnvelope`) — those stay as lazy, typed-error imports so a schema drift
between the two repos fails loudly instead of silently forking behavior.
See docs/EXTRACTION_COUPLING.md for the full list of what's deferred and why.

Source of truth for everything vendored below:
`Audio_Too/audio_too/errors.py` and `Audio_Too/audio_too/contracts.py`
(`PermissionScope`). If those change upstream, re-sync by hand — there is no
automated check tying this file to the Audio_Too copy.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PublicErrorCode(str, Enum):
    """Vendored from audio_too.errors.PublicErrorCode."""

    INVALID_REQUEST = "invalid_request"
    INVALID_COMMAND = "invalid_command"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    PERMISSION_DENIED = "permission_denied"
    RATE_LIMITED = "rate_limited"
    OPERATION_TIMEOUT = "operation_timeout"
    SERVICE_UNAVAILABLE = "service_unavailable"
    EXECUTION_ERROR = "execution_error"
    INTERNAL_ERROR = "internal_error"


@dataclass(frozen=True)
class PublicErrorDetails:
    """Vendored from audio_too.errors.PublicErrorDetails.

    Note: the upstream version also has ``to_contract_error()``, converting
    this into an ``audio_too.contracts.ContractError``. That method is
    intentionally dropped here — ``ContractError`` is part of the real
    cross-repo contract surface (see command_gateway.py / EXTRACTION_COUPLING
    .md), not something this shim vendors.
    """

    code: PublicErrorCode
    message: str
    retryable: bool = False
    http_status: int = 500

    def to_payload(self, *, error_id: str = "") -> dict:
        payload = {
            "error": self.message,
            "error_code": self.code.value,
            "retryable": self.retryable,
        }
        if error_id:
            payload["error_id"] = error_id
        return payload


class PublicError(Exception):
    """Vendored from audio_too.errors.PublicError.

    An expected failure carrying an explicitly safe public representation.
    """

    def __init__(
        self,
        code: PublicErrorCode,
        message: str,
        *,
        retryable: bool = False,
        http_status: int = 500,
    ) -> None:
        self.details = PublicErrorDetails(code, message, retryable, http_status)
        super().__init__(message)


class PermissionScope(str, Enum):
    """Vendored from audio_too.contracts.PermissionScope.

    A fixed, small vocabulary describing how strongly a capability touches
    the world. Used as a dataclass field type/default in
    thursday/registry/core.py, which needs a real value at import time.
    """

    READ = "read"
    ANALYZE = "analyze"
    PROPOSE = "propose"
    MUTATE_LOCAL = "mutate_local"
    COMMUNICATE_EXTERNAL = "communicate_external"
