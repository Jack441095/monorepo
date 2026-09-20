"""Synthetic telemetry pipeline — TEST-ONLY reference implementation.

Implements the V1 architecture in NITE_DSP_TELEMETRY_ARCHITECTURE.md well enough to
prove its privacy invariants executable. Not shipped, not imported by any product,
zero network, stdlib only.
"""

from synthetic_telemetry_pipeline.catalog import CATALOG, EventSpec, PrivacyLevel
from synthetic_telemetry_pipeline.envelope import (
    FORBIDDEN_KEYS,
    Envelope,
    TelemetryViolation,
    envelope_to_wire,
    validate_envelope_dict,
)
from synthetic_telemetry_pipeline.generator import (
    build_envelope,
    generate_synthetic_events,
)
from synthetic_telemetry_pipeline.pipeline import (
    CollectorIngest,
    ConsentState,
    DailyAggregator,
    LocalStore,
    SessionManager,
    trim_store,
)

__all__ = [
    "CATALOG",
    "FORBIDDEN_KEYS",
    "CollectorIngest",
    "ConsentState",
    "DailyAggregator",
    "Envelope",
    "EventSpec",
    "LocalStore",
    "PrivacyLevel",
    "SessionManager",
    "TelemetryViolation",
    "build_envelope",
    "envelope_to_wire",
    "generate_synthetic_events",
    "trim_store",
    "validate_envelope_dict",
]
