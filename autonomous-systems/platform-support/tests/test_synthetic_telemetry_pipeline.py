"""Synthetic analytics pipeline tests — encodes NITE_DSP_TELEMETRY_ARCHITECTURE.md V1.

Test-only reference implementation under tests/synthetic_telemetry_pipeline/.
Proves the privacy invariants before any production telemetry is ever deployed.
Zero network, zero real user content.
"""

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from synthetic_telemetry_pipeline import (
    CATALOG,
    CollectorIngest,
    ConsentState,
    DailyAggregator,
    LocalStore,
    SessionManager,
    TelemetryViolation,
    build_envelope,
    envelope_to_wire,
    generate_synthetic_events,
    trim_store,
    validate_envelope_dict,
)

NOW = datetime(2026, 8, 22, 12, 0, 0, tzinfo=UTC)
TS = "2026-08-22T11:00:00+00:00"


def _wire(env) -> dict:
    return envelope_to_wire(env)


# --- 1. Envelope validation ---------------------------------------------------


def test_envelope_requires_core_fields():
    env = build_envelope("slo.search.executed", session_id=uuid.uuid4().hex, timestamp=TS)
    for required in (
        "event_id",
        "timestamp",
        "product",
        "action",
        "outcome",
        "feature_version",
        "privacy_level",
    ):
        data = _wire(env)
        del data[required]
        with pytest.raises(TelemetryViolation):
            validate_envelope_dict(data)


def test_envelope_rejects_unknown_action_and_bad_error_code():
    base = _wire(build_envelope("slo.search.executed", session_id="a" * 32, timestamp=TS))
    unknown = dict(base, action="slo.search.freeform_hack")
    with pytest.raises(TelemetryViolation):
        validate_envelope_dict(unknown)
    bad_code = dict(base, error_code="Scan Failed!")
    with pytest.raises(TelemetryViolation):
        validate_envelope_dict(bad_code)


def test_param_outside_closed_vocabulary_rejected():
    base = _wire(build_envelope("slo.search.executed", session_id="a" * 32, timestamp=TS))
    hacked = dict(base, params=dict(base["params"], search_mode="regex_over_files"))
    with pytest.raises(TelemetryViolation):
        validate_envelope_dict(hacked)


# --- 2. Forbidden content guards (the core promise) ---------------------------


@pytest.mark.parametrize(
    "probe",
    ["filename", "path", "file_path", "audio", "content", "text", "prompt", "user_agent"],
)
def test_forbidden_keys_rejected(probe):
    base = _wire(build_envelope("slo.search.executed", session_id="a" * 32, timestamp=TS))
    base["params"] = dict(base["params"])
    base["params"][probe] = "harmless-looking"
    with pytest.raises(TelemetryViolation):
        validate_envelope_dict(base)


def test_nested_payload_cannot_smuggle_forbidden_keys():
    base = _wire(build_envelope("kenn.analysis.completed", session_id="a" * 32, timestamp=TS))
    base["params"] = {"nested": {"meta": {"filepath": "/x"}}}
    with pytest.raises(TelemetryViolation):
        validate_envelope_dict(base)


@pytest.mark.parametrize(
    "leak",
    ["/Users/jack/Kick_808.wav", "C:\\Samples\\loop.aiff", "~/Music/bounce.flac"],
)
def test_path_and_audio_extension_heuristics_fail_closed(leak):
    base = _wire(build_envelope("kenn.analysis.completed", session_id="a" * 32, timestamp=TS))
    spec = CATALOG["kenn.analysis.completed"]
    base["params"] = {key: min(values) for key, values in spec.param_map.items()}
    # even a declared enum slot must never carry a path-shaped value
    first_key = next(iter(base["params"]))
    base["params"][first_key] = leak
    with pytest.raises(TelemetryViolation):
        validate_envelope_dict(base)


def test_l0_is_rejected_outright():
    base = _wire(build_envelope("slo.search.executed", session_id="a" * 32, timestamp=TS))
    with pytest.raises(TelemetryViolation):
        validate_envelope_dict(dict(base, privacy_level="L0"))


def test_declared_privacy_level_must_match_catalog():
    base = _wire(build_envelope("slo.search.executed", session_id="a" * 32, timestamp=TS))
    with pytest.raises(TelemetryViolation):
        validate_envelope_dict(dict(base, privacy_level="L3"))
    crash = _wire(
        build_envelope(
            "diag.crash",
            session_id="a" * 32,
            timestamp=TS,
            app_phase="scan",
        )
    )
    with pytest.raises(TelemetryViolation):
        validate_envelope_dict(dict(crash, privacy_level="L2"))


def test_website_events_are_cookieless_no_session_ids():
    web = build_envelope("web.product.view", session_id=None, timestamp=TS)
    assert validate_envelope_dict(_wire(web)).session_id is None
    desktop_shape = dict(_wire(web), session_id="a" * 32)
    with pytest.raises(TelemetryViolation):
        validate_envelope_dict(desktop_shape)


# --- 3. Consent gating --------------------------------------------------------


def _export(store: LocalStore, consent: ConsentState) -> list[str]:
    from synthetic_telemetry_pipeline.pipeline import BatchExporter

    return BatchExporter().export(store, consent)


def test_consent_all_off_emits_zero_batches():
    store = LocalStore()
    for env in generate_synthetic_events(20):
        store.append(env)
    assert _export(store, ConsentState()) == []


def test_usage_toggle_exports_l2_but_not_l3_and_diagnostics_toggle_gates_l3():
    from synthetic_telemetry_pipeline.catalog import PrivacyLevel

    store = LocalStore()
    l2_env = build_envelope("slo.favorite.toggled", session_id="a" * 32, timestamp=TS)
    crash_env = build_envelope(
        "diag.crash",
        session_id="a" * 32,
        timestamp=TS,
        app_phase="scan",
    )
    for env in (l2_env, crash_env):
        store.append(env)

    usage_only = json.loads(_export(store, ConsentState(usage_metrics=True))[0])
    assert len(usage_only) == 1
    assert usage_only[0]["privacy_level"] == PrivacyLevel.L2.value

    diag_only = json.loads(_export(store, ConsentState(diagnostics=True))[0])
    assert len(diag_only) == 1
    assert diag_only[0]["privacy_level"] == PrivacyLevel.L3.value

    both = _export(store, ConsentState(usage_metrics=True, diagnostics=True))
    total = sum(len(json.loads(batch)) for batch in both)
    assert total == 2


# --- 4. Aggregation, retention, rotation ---------------------------------------


def test_aggregator_dedupes_by_event_id_and_rolls_up():
    agg = DailyAggregator()
    env = build_envelope("slo.scan.completed", session_id="a" * 32, timestamp=TS)
    assert agg.add(env) is True
    assert agg.add(env) is False
    same_id = type(env)(**env.__dict__)
    assert agg.add(same_id) is False
    other = build_envelope("slo.scan.completed", session_id="b" * 32, timestamp=TS)
    assert agg.add(other) is True
    key = ("2026-08-22", "slo.scan.completed", "success", "1.4.0")
    assert agg.counts[key] == 2 and agg.total == 2


def test_retention_trimmer_drops_old_events_and_caps_size():
    store = LocalStore()
    old_ts = (NOW - timedelta(days=45)).isoformat().replace("+00:00", "Z")
    fresh_ts = (NOW - timedelta(days=1)).isoformat().replace("+00:00", "Z")
    store.append(build_envelope("slo.scan.started", "a" * 32, timestamp=old_ts, scan_kind="initial"))
    for i in range(3):
        store.append(
            build_envelope("slo.scan.started", "b" * 32, timestamp=fresh_ts, scan_kind="manual")
        )
    removed = trim_store(store, NOW, max_events=2)
    assert removed == 2
    assert all(event["timestamp"][:10] == "2026-08-21" for event in store.events)
    assert len(store.events) <= 2


def test_session_rotation_breaks_cross_session_linkage():
    manager = SessionManager(started_at=NOW)
    first = manager.current(now=NOW)
    later = NOW + timedelta(hours=25)
    rotated = manager.current(now=later)
    assert rotated != first
    assert manager.rotate(now=later) == rotated


# --- 5. End-to-end synthetic pipeline ------------------------------------------


def test_end_to_end_synthetic_pipeline_privacy_invariants():
    envelopes = generate_synthetic_events(500)
    store = LocalStore()
    for env in envelopes:
        store.append(env)

    consent = ConsentState(usage_metrics=True, diagnostics=True)
    batches = _export(store, consent)
    collector_today = CollectorIngest(day_pepper="pepper-day-1")
    accepted: list[dict] = []
    for batch in batches:
        accepted.extend(collector_today.ingest(batch))

    assert len(accepted) == 500

    serialized_batch = json.dumps(accepted).lower()
    for forbidden in (
        ".wav",
        ".aiff",
        ".flac",
        ".mp3",
        "/users/",
        "c:\\",
        '"filename"',
        '"path"',
        '"content"',
    ):
        assert forbidden not in serialized_batch

    known_actions = set(CATALOG)
    assert all(row["action"] in known_actions for row in accepted)

    raw_sessions = {env.session_id for env in envelopes if env.session_id}
    hashed_sessions = {row["session_id"] for row in accepted if row["session_id"]}
    assert raw_sessions and hashed_sessions
    assert not (raw_sessions & hashed_sessions)

    rehashed = CollectorIngest(day_pepper="pepper-day-2")
    day2_rows: list[dict] = []
    for batch in batches:
        day2_rows.extend(rehashed.ingest(batch))
    day1_map = {r["event_id"]: r["session_id"] for r in accepted if r["session_id"]}
    day2_map = {r["event_id"]: r["session_id"] for r in day2_rows if r["session_id"]}
    shared_ids = set(day1_map) & set(day2_map)
    assert shared_ids
    assert all(day1_map[eid] != day2_map[eid] for eid in shared_ids)

    assert collector_today.alarm_count == 0
    tampered = json.dumps([dict(json.loads(batches[0])[0], outcome="exploded")])
    collector_today.ingest(tampered)
    assert collector_today.alarm_count == 1
