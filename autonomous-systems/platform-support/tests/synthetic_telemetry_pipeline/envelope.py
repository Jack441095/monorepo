"""Envelope schema v1 + fail-closed privacy guards."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from synthetic_telemetry_pipeline.catalog import CATALOG, PrivacyLevel, Product

FORBIDDEN_KEYS = frozenset(
    {
        "audio",
        "waveform",
        "samples",
        "filename",
        "path",
        "filepath",
        "file_path",
        "content",
        "text",
        "prompt",
        "response",
        "email",
        "name",
        "message",
        "ip",
        "user_agent",
    }
)

AUDIO_EXTENSIONS = (".wav", ".aiff", ".aif", ".flac", ".mp3", ".ogg", ".sd", ".wv")
PATH_MARKERS = ("/users/", "c:\\", "~/")

OUTCOMES = frozenset({"success", "failure", "cancelled", "timeout", "rejected"})
ERROR_CODE_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)*$")
FEATURE_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
HEX_RE = re.compile(r"^[0-9a-f]{32}$")

REQUIRED_FIELDS = (
    "event_id",
    "event_version",
    "timestamp",
    "product",
    "action",
    "outcome",
    "feature_version",
    "privacy_level",
)


class TelemetryViolation(Exception):
    """Fail-closed: bad telemetry raises, it is never silently passed or repaired."""


@dataclass(frozen=True)
class Envelope:
    event_id: str
    event_version: int
    timestamp: str
    product: str
    action: str
    outcome: str
    feature_version: str
    privacy_level: str
    session_id: str | None = None
    duration_ms: float | None = None
    error_code: str = ""
    params: dict[str, str] = field(default_factory=dict)


def _reject_forbidden_keys(payload: object, where: str) -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if str(key).lower() in FORBIDDEN_KEYS:
                raise TelemetryViolation(f"forbidden key {key!r} at {where}")
            _reject_forbidden_keys(value, f"{where}.{key}")
    elif isinstance(payload, list):
        for index, item in enumerate(payload):
            _reject_forbidden_keys(item, f"{where}[{index}]")


def _reject_leaky_strings(value: object) -> None:
    if not isinstance(value, str):
        return
    lowered = value.lower()
    if any(marker in lowered for marker in PATH_MARKERS):
        raise TelemetryViolation("value looks like a filesystem path")
    if any(lowered.endswith(ext) for ext in AUDIO_EXTENSIONS):
        raise TelemetryViolation("value looks like an audio filename")


def validate_envelope_dict(data: dict) -> Envelope:
    """Validate raw dict against schema v1 + catalog; returns typed envelope."""
    _reject_forbidden_keys(data, "envelope")
    for field_name in REQUIRED_FIELDS:
        if field_name not in data:
            raise TelemetryViolation(f"missing required field {field_name!r}")

    if not isinstance(data["event_id"], str) or not HEX_RE.match(data["event_id"]):
        raise TelemetryViolation("event_id must be 32 lowercase hex chars")
    try:
        uuid.UUID(hex=data["event_id"])
    except ValueError as exc:
        raise TelemetryViolation("event_id is not a valid uuid4") from exc
    if int(data["event_version"]) != 1:
        raise TelemetryViolation("unsupported event_version")

    try:
        parsed_ts = datetime.fromisoformat(str(data["timestamp"]))
    except ValueError as exc:
        raise TelemetryViolation("timestamp must be ISO 8601") from exc
    if parsed_ts.tzinfo is None:
        raise TelemetryViolation("timestamp must be timezone-aware UTC")
    parsed_ts.astimezone(UTC)

    try:
        product = Product(data["product"])
    except ValueError as exc:
        raise TelemetryViolation(f"unknown product {data['product']!r}") from exc

    spec = CATALOG.get(data["action"])
    if spec is None:
        raise TelemetryViolation(f"action {data['action']!r} not in catalog")
    if spec.product is not product:
        raise TelemetryViolation(
            f"action {data['action']} belongs to product {spec.product.value}"
        )

    level = str(data["privacy_level"])
    if level == "L0":
        raise TelemetryViolation("L0 content must never enter the pipeline")
    try:
        declared = PrivacyLevel(level)
    except ValueError as exc:
        raise TelemetryViolation(f"unknown privacy_level {level!r}") from exc
    if declared is not spec.privacy_level:
        raise TelemetryViolation(
            f"{data['action']} requires {spec.privacy_level.value}, got {declared.value}"
        )
    if product is Product.WEBSITE and data.get("session_id") is not None:
        raise TelemetryViolation("website events are cookieless: no session_id allowed")
    if product is not Product.WEBSITE and not data.get("session_id"):
        raise TelemetryViolation("desktop events require a rotating session_id")

    if data["outcome"] not in OUTCOMES:
        raise TelemetryViolation(f"invalid outcome {data['outcome']!r}")
    error_code = str(data.get("error_code", ""))
    if error_code and not ERROR_CODE_RE.match(error_code):
        raise TelemetryViolation(f"error_code grammar violation: {error_code!r}")

    feature_version = data["feature_version"]
    if not isinstance(feature_version, str) or not FEATURE_VERSION_RE.match(feature_version):
        raise TelemetryViolation("feature_version must be semver X.Y.Z")

    duration_ms = data.get("duration_ms")
    if duration_ms is not None:
        if not isinstance(duration_ms, (int, float)) or isinstance(duration_ms, bool):
            raise TelemetryViolation("duration_ms must be numeric")
        if duration_ms < 0:
            raise TelemetryViolation("duration_ms must be non-negative")

    params = data.get("params", {})
    if not isinstance(params, dict):
        raise TelemetryViolation("params must be a flat object")
    param_map = spec.param_map
    extra = set(params) - set(param_map)
    missing = set(param_map) - set(params)
    if extra:
        raise TelemetryViolation(f"undeclared params: {sorted(extra)}")
    if missing:
        raise TelemetryViolation(f"missing declared params: {sorted(missing)}")
    for key, value in params.items():
        if not isinstance(value, str):
            raise TelemetryViolation(f"param {key!r} must be an enum string")
        _reject_leaky_strings(value)
        allowed = param_map[key]
        if value not in allowed:
            raise TelemetryViolation(
                f"param {key!r}={value!r} outside closed vocabulary {sorted(allowed)}"
            )

    return Envelope(
        event_id=data["event_id"],
        event_version=int(data["event_version"]),
        timestamp=data["timestamp"],
        product=data["product"],
        action=data["action"],
        outcome=data["outcome"],
        feature_version=feature_version,
        privacy_level=level,
        session_id=data.get("session_id"),
        duration_ms=duration_ms,
        error_code=error_code,
        params=dict(params),
    )


def envelope_to_wire(env: Envelope) -> dict:
    wire = {
        "event_id": env.event_id,
        "event_version": env.event_version,
        "timestamp": env.timestamp,
        "product": env.product,
        "session_id": env.session_id,
        "action": env.action,
        "outcome": env.outcome,
        "duration_ms": env.duration_ms,
        "error_code": env.error_code,
        "feature_version": env.feature_version,
        "privacy_level": env.privacy_level,
        "params": dict(env.params),
    }
    _reject_forbidden_keys(wire, "wire")
    return wire
