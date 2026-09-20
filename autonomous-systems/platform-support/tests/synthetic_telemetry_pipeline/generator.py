"""Deterministic synthetic event generation — no real user content possible."""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime, timedelta

from synthetic_telemetry_pipeline.catalog import CATALOG
from synthetic_telemetry_pipeline.envelope import Envelope, envelope_to_wire


def build_envelope(
    action: str,
    session_id: str | None,
    timestamp: str | None = None,
    outcome: str = "success",
    duration_ms: float | None = None,
    error_code: str = "",
    feature_version: str = "1.4.0",
    privacy_level: str | None = None,
    params: dict[str, str] | None = None,
    **param_overrides: str,
) -> Envelope:
    spec = CATALOG[action]
    merged = {key: min(values) for key, values in spec.param_map.items()}
    if params:
        merged.update(params)
    if param_overrides:
        merged.update(param_overrides)
        params = merged
    data = {
        "event_id": uuid.uuid4().hex,
        "event_version": 1,
        "timestamp": timestamp or datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "product": spec.product.value,
        "session_id": session_id,
        "action": action,
        "outcome": outcome,
        "duration_ms": duration_ms,
        "error_code": error_code,
        "feature_version": feature_version,
        "privacy_level": privacy_level or spec.privacy_level.value,
        "params": merged,
    }
    from synthetic_telemetry_pipeline.envelope import validate_envelope_dict

    return validate_envelope_dict(data)


def generate_synthetic_events(count: int, seed: int = 20260822) -> list[Envelope]:
    """Mixed-product synthetic traffic for pipeline tests."""
    rng = random.Random(seed)
    actions = [
        ("slo.search.executed", {"search_mode": "similar", "result_count_bucket": "11-50", "latency_bucket_ms": "<50"}),
        ("slo.scan.completed", {"indexed_count_bucket": "1k-10k", "duration_bucket_s": "10-60"}),
        ("slo.daw.drag_export", {"target_class": "daw", "drag_latency_bucket_ms": "<250"}),
        ("kenn.analysis.completed", {"analysis_scope": "full_mix", "track_count_bucket": "9-32", "duration_bucket_s": "5-30"}),
        ("kenn.automix.applied", {"change_count_bucket": "1-3", "undo_armed": "true"}),
        ("thu.capability.succeeded", {"capability_id": "audio.mix.analyze", "duration_bucket_ms": "<250"}),
        ("thu.alert.dismissed", {"alert_kind": "watcher", "age_bucket_h": "<1"}),
        ("web.product.view", {"from_page_class": "landing"}),
    ]
    base = datetime.now(UTC).replace(microsecond=0)
    envelopes: list[Envelope] = []
    for index in range(count):
        action, default_params = actions[index % len(actions)]
        spec = CATALOG[action]
        session = None if spec.product.value == "website" else uuid.uuid4().hex
        ts = (base - timedelta(minutes=rng.randint(0, 60 * 24 * 7))).isoformat().replace(
            "+00:00", "Z"
        )
        envelopes.append(
            build_envelope(action, session_id=session, timestamp=ts, params=dict(default_params))
        )
    return envelopes


def wire_dicts(envelopes: list[Envelope]) -> list[dict]:
    return [envelope_to_wire(env) for env in envelopes]
