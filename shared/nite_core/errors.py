"""Stable public error taxonomy shared by every Audio_Too interface."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .contracts import ContractError


class PublicErrorCode(str, Enum):
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
    code: PublicErrorCode
    message: str
    retryable: bool = False
    http_status: int = 500

    def to_contract_error(self) -> ContractError:
        return ContractError(
            code=self.code.value,
            message=self.message,
            retryable=self.retryable,
        )

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
    """An expected failure carrying an explicitly safe public representation."""

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


def public_error_details(exc: BaseException) -> PublicErrorDetails:
    """Map an exception without copying its internal message to the caller."""
    if isinstance(exc, PublicError):
        return exc.details
    if isinstance(exc, TimeoutError):
        return PublicErrorDetails(
            PublicErrorCode.OPERATION_TIMEOUT,
            "The operation timed out before it completed.",
            retryable=True,
            http_status=504,
        )
    if isinstance(exc, PermissionError):
        return PublicErrorDetails(
            PublicErrorCode.PERMISSION_DENIED,
            "This operation is not permitted.",
            http_status=403,
        )
    if isinstance(exc, FileNotFoundError):
        return PublicErrorDetails(
            PublicErrorCode.NOT_FOUND,
            "The requested resource was not found.",
            http_status=404,
        )
    if isinstance(exc, ValueError):
        return PublicErrorDetails(
            PublicErrorCode.INVALID_REQUEST,
            "The request is invalid.",
            http_status=400,
        )
    return PublicErrorDetails(
        PublicErrorCode.INTERNAL_ERROR,
        "The request could not be completed.",
        retryable=False,
        http_status=500,
    )


def public_error_payload(exc: BaseException, *, error_id: str = "") -> tuple[int, dict]:
    details = public_error_details(exc)
    return details.http_status, details.to_payload(error_id=error_id)
