"""Safe, backward-compatible JSON API error serialization."""

from __future__ import annotations

import logging

from nite_core import public_error_payload

logger = logging.getLogger(__name__)

DEFAULT_CODES = {
    400: "invalid_request",
    401: "authentication_required",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    413: "payload_too_large",
    422: "validation_error",
    429: "rate_limited",
}


def exception_payload(exc: BaseException, *, request_id: str = "") -> tuple[int, dict]:
    """Log an unexpected failure and produce the shared safe error shape."""
    logger.exception("Business API request failed", exc_info=exc)
    return public_error_payload(exc, error_id=request_id)


def send_public_exception(handler, exc: BaseException) -> None:
    request_id = handler.request_id() if callable(getattr(handler, "request_id", None)) else ""
    status, payload = exception_payload(exc, request_id=request_id)
    handler.send_json(status, payload)


def safe_error_payload(status: int, payload: dict, request_id: str) -> dict:
    if status < 400:
        return payload
    safe = {
        key: value
        for key, value in payload.items()
        if key not in {"error", "message", "code", "details", "traceback", "path", "error_id"}
    }
    if status >= 500:
        message = "The request could not be completed."
        code = "internal_error"
        details: object = {}
    else:
        message = str(payload.get("message") or payload.get("error") or "Request failed.")
        code = str(payload.get("code") or DEFAULT_CODES.get(status, "request_error"))
        details = payload.get("details") if isinstance(payload.get("details"), (dict, list)) else {}
    safe.update(
        {
            "error": message,
            "code": code,
            "message": message,
            "details": details,
            "request_id": request_id,
        }
    )
    return safe
