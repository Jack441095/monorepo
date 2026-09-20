"""Validation and abuse protection for the public enquiry endpoint."""

from __future__ import annotations

import re
import time
from collections import defaultdict
from threading import Lock

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
RATE_LIMITS: dict[str, tuple[int, int]] = {
    "enquiry": (5, 3600),
    "public_ask": (30, 3600),
    "public_tips": (30, 3600),
    "public_stem_upload": (10, 3600),
    "public_podcast_check": (10, 3600),
    "public_mix_doctor": (10, 3600),
    "public_delivery_check": (10, 3600),
    "public_stem_separate": (10, 3600),
    "public_automix_start": (10, 3600),
    "dashboard_login": (8, 15 * 60),
    "dashboard_write": (300, 60),
    "demo_write": (60, 60),
    "demo_login": (8, 15 * 60),
}

_attempts: dict[str, list[float]] = defaultdict(list)
_lock = Lock()


def client_key(address: tuple[str, int] | None) -> str:
    if not address:
        return "unknown"
    return address[0]


def is_rate_limited(address: tuple[str, int] | None, scope: str = "enquiry") -> bool:
    max_attempts, window_seconds = RATE_LIMITS.get(scope, RATE_LIMITS["enquiry"])
    key = f"{scope}:{client_key(address)}"
    now = time.time()
    with _lock:
        times = [stamp for stamp in _attempts[key] if now - stamp < window_seconds]
        if len(times) >= max_attempts:
            _attempts[key] = times
            return True
        times.append(now)
        _attempts[key] = times
    return False


def clear_rate_limit(address: tuple[str, int] | None, scope: str) -> None:
    key = f"{scope}:{client_key(address)}"
    with _lock:
        _attempts.pop(key, None)


def is_honeypot(payload: dict) -> bool:
    for field in ("company_website", "website", "_gotcha"):
        value = str(payload.get(field, "")).strip()
        if value:
            return True
    return False


def validate_enquiry_payload(payload: dict) -> dict:
    if is_honeypot(payload):
        raise HoneypotError()

    name = str(payload.get("name", "")).strip()
    email = str(payload.get("email", "")).strip()
    service = str(payload.get("service", "")).strip() or "Audio service"
    message = str(payload.get("message", "")).strip()
    deadline = str(payload.get("deadline", "")).strip()

    if len(name) < 2 or len(name) > 100:
        raise ValueError("Name must be between 2 and 100 characters.")
    if not EMAIL_RE.match(email) or len(email) > 254:
        raise ValueError("A valid email address is required.")
    if len(message) < 20 or len(message) > 5000:
        raise ValueError("Project details must be between 20 and 5000 characters.")
    if len(deadline) > 120:
        raise ValueError("Deadline is too long.")
    if len(service) > 120:
        raise ValueError("Service name is too long.")

    return {
        "name": name,
        "email": email,
        "service": service,
        "message": message,
        "deadline": deadline,
    }


class HoneypotError(Exception):
    """Bot filled a hidden field; treat as spam."""
