from __future__ import annotations

import time

from kenn.core.deliberative_plan import validate_deliberative_plan
from kenn.core.diagnostic_loop import (
    RESULT_SCHEMA,
    next_diagnostic_plan,
    record_diagnostic_result,
    start_diagnostic_loop,
)
from kenn.core.evidence import EvidenceFact, EvidencePacket
from kenn.core.session_context import build_session_context


def _context(*, plugin_frame=None) -> dict:
    return build_session_context(
        session_id="song-1",
        snapshot={
            "status": "connected", "tempo": 126.0, "is_playing": False,
            "tracks": [{"index": 0, "name": "Master Print", "type": "audio", "devices": []}],
        },
        plugin_frames=[plugin_frame] if plugin_frame else [],
    )


def _result(loop: dict, verdict: str = "contradicts") -> dict:
    return {
        "schema": RESULT_SCHEMA,
        "hypothesis_id": loop["active_hypothesis_id"],
        "verdict": verdict,
        "source": "user_observation",
        "source_turn_id": "turn-2",
        "observation": "The matched bypass did not change the distortion.",
    }


def test_current_measurement_ranks_a_test_but_never_claims_a_cause() -> None:
    context = _context(plugin_frame={
        "schema": "audio_feature_frame.v1", "peak_dbfs": -0.1,
        "clipped_samples": 8, "stereo_correlation": 0.8,
    })

    result = start_diagnostic_loop(
        goal="My distorted master sounds crushed and too loud after the limiter.", context=context,
    )

    assert result["ok"] is True
    loop = result["loop"]
    assert loop["status"] == "awaiting_test"
    assert loop["hypotheses"][0]["cause"] == "A specific stage is clipping or overshooting"
    assert "does not identify that stage" in loop["evidence_ranking"]
    assert loop["recommendation"] == ""
    assert loop["execution_authorized"] is False


def test_kick_bass_coexistence_routes_to_evidence_first_diagnosis() -> None:
    context = build_session_context(
        session_id="kick-bass",
        snapshot={
            "status": "connected",
            "tracks": [
                {"index": 0, "name": "Kick", "type": "audio", "devices": []},
                {"index": 1, "name": "Bass", "type": "midi", "devices": []},
            ],
        },
    )

    result = start_diagnostic_loop(
        goal="Help the kick and bass coexist without losing their weight.", context=context,
    )

    assert result["ok"] is True
    assert result["loop"]["status"] == "awaiting_test"
    assert "kick" in result["loop"]["symptom"].lower()
    assert result["loop"]["execution_authorized"] is False


def test_stale_plugin_measurement_cannot_reorder_current_diagnosis() -> None:
    stale = EvidencePacket(
        source="plugin_bus_snapshot",
        captured_at_age_seconds=30.0,
        facts=(EvidenceFact("clipped_samples", 8.0, "samples", "plugin_bus_snapshot"),),
        limitations=(),
        observed_at_epoch=time.time() - 30.0,
    )

    loop = start_diagnostic_loop(
        goal="My distorted master sounds crushed and too loud after the limiter.",
        context=_context(),
        evidence_packets=[stale],
    )["loop"]

    assert loop["hypotheses"][0]["cause"] == "The limiter or clipper is being asked to solve a mix-balance problem"
    assert loop["evidence_ranking"] == ""


def test_contradicting_one_hypothesis_advances_exactly_one_test() -> None:
    loop = start_diagnostic_loop(
        goal="My distorted master sounds crushed and too loud after the limiter.", context=_context(),
    )["loop"]
    first = loop["active_hypothesis_id"]

    updated = record_diagnostic_result(loop, _result(loop, "contradicts"))["loop"]

    assert updated["status"] == "awaiting_test"
    assert updated["active_hypothesis_id"] != first
    assert len(updated["results"]) == 1
    assert loop["results"] == []


def test_supported_hypothesis_yields_advisory_recommendation_not_execution() -> None:
    context = _context()
    loop = start_diagnostic_loop(
        goal="My distorted master sounds crushed and too loud after the limiter.", context=context,
    )["loop"]

    updated = record_diagnostic_result(loop, _result(loop, "supports"))["loop"]
    followup = next_diagnostic_plan(updated, context)

    assert updated["status"] == "recommendation_ready"
    assert updated["recommendation"]
    assert updated["execution_authorized"] is False
    assert followup["ok"] is True
    assert followup["plan"]["status"] == "needs_clarification"
    assert followup["plan"]["steps"][0]["action"] == "ask_user"
    assert followup["plan"]["steps"][0]["mutating"] is False
    assert validate_deliberative_plan(followup["plan"], context)["ok"] is True


def test_result_must_match_active_hypothesis_and_have_typed_source() -> None:
    loop = start_diagnostic_loop(
        goal="My distorted master sounds crushed and too loud after the limiter.", context=_context(),
    )["loop"]
    wrong = _result(loop)
    wrong["hypothesis_id"] = "hypothesis-99"
    untyped = _result(loop)
    untyped["source_turn_id"] = ""

    assert record_diagnostic_result(loop, wrong)["ok"] is False
    assert record_diagnostic_result(loop, untyped)["ok"] is False
    assert loop["results"] == []


def test_failed_receipt_cannot_support_hypothesis() -> None:
    loop = start_diagnostic_loop(
        goal="My distorted master sounds crushed and too loud after the limiter.", context=_context(),
    )["loop"]
    result = {
        "schema": RESULT_SCHEMA,
        "hypothesis_id": loop["active_hypothesis_id"],
        "verdict": "supports",
        "source": "verified_receipt",
        "evidence": {
            "schema": "kenn.ableton_action_receipt.v1", "receipt_id": "receipt-1",
            "status": "failed", "verified": True,
        },
    }

    rejected = record_diagnostic_result(loop, result)

    assert rejected["ok"] is False
    assert "verified applied receipt" in rejected["errors"][0]


def test_unsupported_or_stale_diagnosis_is_rejected() -> None:
    context = _context()
    unsupported = start_diagnostic_loop(goal="Tell me a joke", context=context)
    context["observed_at"] -= 301
    stale = start_diagnostic_loop(goal="My mix is muddy", context=context)

    assert unsupported["ok"] is False
    assert "clarification" in unsupported["errors"][0]
    assert stale["ok"] is False
    assert any("stale" in error for error in stale["errors"])


def test_changed_session_invalidates_old_diagnostic_followup() -> None:
    context = _context()
    loop = start_diagnostic_loop(
        goal="My distorted master sounds crushed and too loud after the limiter.", context=context,
    )["loop"]
    changed = _context()
    changed["transport"]["tempo"] = 127.0
    from kenn.core.session_context import refresh_session_context_fingerprint
    refresh_session_context_fingerprint(changed)

    result = next_diagnostic_plan(loop, changed)

    assert result["ok"] is False
    assert "state changed" in result["errors"][0]
