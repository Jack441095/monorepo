"""thursday/_compat.py vendors small, stable primitives from audio_too's
errors/contracts modules so `import thursday` works standalone (see
docs/EXTRACTION_COUPLING.md). These tests pin the vendored surface so a
future edit here can't silently drift from what the rest of the package
actually imports (thursday/errors.py, thursday/retry.py,
thursday/registry/core.py all depend on this shape).
"""

from __future__ import annotations

import pytest

from thursday._compat import PermissionScope, PublicError, PublicErrorCode, PublicErrorDetails


def test_public_error_code_values_are_stable() -> None:
    # thursday/errors.py maps its own error types onto these codes by name;
    # a renamed or removed member would silently break that mapping.
    expected = {
        "invalid_request", "invalid_command", "not_found", "conflict",
        "permission_denied", "rate_limited", "operation_timeout",
        "service_unavailable", "execution_error", "internal_error",
    }
    assert {m.value for m in PublicErrorCode} == expected


def test_permission_scope_values_are_stable() -> None:
    # thursday/registry/core.py's ServiceDef uses this as a dataclass field
    # default; an unexpected member changes what a bare ServiceDef() means.
    expected = {"read", "analyze", "propose", "mutate_local", "communicate_external"}
    assert {m.value for m in PermissionScope} == expected


def test_public_error_details_to_payload_shape() -> None:
    details = PublicErrorDetails(
        code=PublicErrorCode.NOT_FOUND, message="client not found",
        retryable=False, http_status=404,
    )
    payload = details.to_payload()
    assert payload == {
        "error": "client not found",
        "error_code": "not_found",
        "retryable": False,
    }


def test_public_error_details_to_payload_includes_error_id_when_given() -> None:
    details = PublicErrorDetails(code=PublicErrorCode.CONFLICT, message="stale")
    payload = details.to_payload(error_id="err-123")
    assert payload["error_id"] == "err-123"


def test_public_error_details_is_frozen() -> None:
    details = PublicErrorDetails(code=PublicErrorCode.INTERNAL_ERROR, message="x")
    with pytest.raises(Exception):
        details.code = PublicErrorCode.NOT_FOUND  # type: ignore[misc]


def test_public_error_carries_details_and_is_raisable() -> None:
    with pytest.raises(PublicError) as exc_info:
        raise PublicError(PublicErrorCode.RATE_LIMITED, "slow down", retryable=True, http_status=429)
    err = exc_info.value
    assert err.details.code is PublicErrorCode.RATE_LIMITED
    assert err.details.retryable is True
    assert err.details.http_status == 429
    assert str(err) == "slow down"


def test_public_error_details_has_no_to_contract_error() -> None:
    # Deliberately dropped -- ContractError is real cross-repo contract
    # surface (command_gateway.py), not something this shim vendors.
    # If this ever starts passing, someone re-added coupling here that
    # docs/EXTRACTION_COUPLING.md explicitly says not to.
    details = PublicErrorDetails(code=PublicErrorCode.INTERNAL_ERROR, message="x")
    assert not hasattr(details, "to_contract_error")
