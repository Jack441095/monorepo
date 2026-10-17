"""Tests for Before/After Acoustic Comparison and Re-grading (Milestone E10).

Guarantees:
- Captures pre-apply analysis meters and grade snapshot, bound to the action receipt.
- Computes acoustic deltas with explicit units (dBTP, LUFS, dB, %, correlation).
- Verifies that re-measuring and re-grading reflects the applied change and agrees with the comparison.
- Serves before/after comparison on request by receipt_id.
- Validates re-grading against original baseline analysis.
- REST API integration tests using FastAPI TestClient.
"""

from __future__ import annotations

import math
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from kenn.core.fake_live import FakeLiveBackend
from kenn.core.live_action_service import LiveActionService
from kenn.core.session_memory import (
    get_before_after_comparison,
    save_before_after_comparison,
)
from kenn.core.suggestion_levers import (
    apply_suggestion_lever,
    build_before_after_comparison,
    generate_suggestion_levers,
    regrade_against_original,
)
from kenn.routes.fastapi_app import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_apply_captures_before_snapshot_and_grade() -> None:
    """Verifies that applying a lever binds pre-apply analysis meters and grade to the receipt."""
    backend = FakeLiveBackend()
    service = LiveActionService(backend)

    # Initial session snapshot with low-mid mud
    meters_before = {
        "true_peak_dbtp": -1.2,
        "integrated_lufs": -14.0,
        "correlation": 0.60,
        "crest_factor_db": 10.0,
        "spectral_energy": {"low_mid_200_500hz": 0.42, "sub_20_60hz": 0.20, "air_10_20khz": 0.15},
    }
    grade_before = {
        "points": 50.0,
        "points_available": 60.0,
        "full_marks": 100.0,
        "parts": [
            {"part": "technical_health", "points": 23.0, "points_available": 30.0},
            {"part": "declared_target", "points": 27.0, "points_available": 30.0},
        ],
    }

    session_snapshot = backend.query_session_state(include_mixer=True)
    levers = generate_suggestion_levers(grade_before, session_snapshot, meters=meters_before)
    mud_lever = next((l for l in levers if "low-mid" in l["lever_id"]), None)
    assert mud_lever is not None

    # Apply lever with pre-apply meters and grade passed
    result = apply_suggestion_lever(
        mud_lever,
        service,
        session_id="session_before_after",
        pre_apply_meters=meters_before,
        pre_apply_grade=grade_before,
    )

    assert result["ok"] is True
    receipt = result.get("receipt")
    assert receipt is not None
    assert receipt["before_snapshot"] == meters_before
    assert receipt["before_grade"] == grade_before
    assert receipt["lever_applied"]["lever_id"] == mud_lever["lever_id"]


def test_build_before_after_comparison_metrics_and_deltas() -> None:
    """Verifies delta calculations across all acoustic dimensions with units."""
    before_snapshot = {
        "true_peak_dbtp": -0.4,
        "integrated_lufs": -13.5,
        "correlation": 0.35,
        "crest_factor_db": 7.5,
        "bands": {
            "low_mid": 0.44,  # 44% mud
            "sub": 0.35,
            "air": 0.08,  # 8% dull
        },
    }
    after_snapshot = {
        "true_peak_dbtp": -1.2,  # -0.8 dBTP improvement
        "integrated_lufs": -14.0,  # -0.5 LUFS
        "correlation": 0.65,  # +0.30 improvement
        "crest_factor_db": 9.5,  # +2.0 dB improvement
        "bands": {
            "low_mid": 0.34,  # -10% drop into safe zone
            "sub": 0.30,
            "air": 0.14,  # +6% sheen
        },
    }
    before_grade = {"points": 45.0, "points_available": 60.0}
    after_grade = {"points": 58.0, "points_available": 60.0}

    lever = {
        "lever_id": "lever-low-mid-mud",
        "title": "Clear Low-Mid Mud",
    }

    comparison = build_before_after_comparison(
        before_snapshot=before_snapshot,
        after_snapshot=after_snapshot,
        before_grade=before_grade,
        after_grade=after_grade,
        lever=lever,
    )

    assert comparison["schema"] == "kenn.before_after_comparison.v1"
    deltas = comparison["deltas"]

    # True peak
    assert deltas["true_peak_dbtp"]["delta"] == -0.8
    assert deltas["true_peak_dbtp"]["unit"] == "dBTP"

    # Integrated loudness
    assert deltas["integrated_lufs"]["delta"] == -0.5
    assert deltas["integrated_lufs"]["unit"] == "LUFS"

    # Correlation
    assert deltas["correlation"]["delta"] == 0.30
    assert deltas["correlation"]["unit"] == "correlation"

    # Low-mid energy
    assert deltas["low_mid_energy_pct"]["delta"] == -10.0
    assert deltas["low_mid_energy_pct"]["unit"] == "%"

    # Crest factor
    assert deltas["crest_factor_db"]["delta"] == 2.0
    assert deltas["crest_factor_db"]["unit"] == "dB"

    # Grade score
    assert deltas["grade_score"]["delta"] == 13.0
    assert deltas["grade_score"]["unit"] == "points"

    # Regrade agreement
    assert comparison["regrade_agrees"] is True

    # Auditory summary
    summary = comparison["auditory_change_summary"]
    assert "Low-mid energy dropped by 10.0%" in summary
    assert "Grade score gained +13.0 points" in summary
    assert "Stereo correlation improved by +0.30" in summary


def test_regrade_agreement_flags_unexpected_regression() -> None:
    """Verifies that an action causing low-mid energy to increase when trying to cut mud is flagged."""
    before_snapshot = {
        "bands": {"low_mid": 0.35},
        "true_peak_dbtp": -1.2,
    }
    # Mistakenly boosted low-mid
    after_snapshot = {
        "bands": {"low_mid": 0.45},
        "true_peak_dbtp": -1.2,
    }
    before_grade = {"points": 55.0}
    after_grade = {"points": 50.0}

    lever = {"lever_id": "lever-low-mid-mud"}

    comparison = build_before_after_comparison(
        before_snapshot=before_snapshot,
        after_snapshot=after_snapshot,
        before_grade=before_grade,
        after_grade=after_grade,
        lever=lever,
    )

    assert comparison["regrade_agrees"] is False


def test_save_and_get_before_after_comparison() -> None:
    """Verifies persistent storage and retrieval of comparison bound to receipt."""
    receipt_id = "receipt-test-12345"
    before_snap = {"true_peak_dbtp": -0.5}
    after_snap = {"true_peak_dbtp": -1.2}
    comp_data = {
        "schema": "kenn.before_after_comparison.v1",
        "deltas": {"true_peak_dbtp": {"delta": -0.7, "unit": "dBTP"}},
        "regrade_agrees": True,
    }

    res = save_before_after_comparison(
        receipt_id=receipt_id,
        session_id="session_store_test",
        before_snapshot=before_snap,
        after_snapshot=after_snap,
        comparison=comp_data,
    )
    assert res["ok"] is True

    fetched = get_before_after_comparison(receipt_id)
    assert fetched is not None
    assert fetched["deltas"]["true_peak_dbtp"]["delta"] == -0.7
    assert fetched["regrade_agrees"] is True


def test_regrade_against_original() -> None:
    """Verifies complete re-grading against original baseline snapshot."""
    original_meters = {
        "true_peak_dbtp": 0.5,  # Clipping
        "integrated_lufs": -14.0,
        "correlation": 0.60,
        "crest_factor_db": 10.0,
        "spectral_energy": {"low_mid_200_500hz": 0.28, "sub_20_60hz": 0.20, "air_10_20khz": 0.15},
    }
    original_grade = {
        "points": 50.0,
        "points_available": 60.0,
        "parts": [
            {"part": "technical_health", "points": 23.0, "points_available": 30.0},
            {"part": "declared_target", "points": 27.0, "points_available": 30.0},
        ],
    }

    # After fader reduction
    current_meters = {
        "true_peak_dbtp": -1.2,  # Fixed
        "integrated_lufs": -15.0,
        "correlation": 0.60,
        "crest_factor_db": 10.0,
        "spectral_energy": {"low_mid_200_500hz": 0.28, "sub_20_60hz": 0.20, "air_10_20khz": 0.15},
    }

    lever = {"lever_id": "lever-true-peak-ceiling"}

    tech_report = {
        "mqm_score": 28.0,
        "points_available": 30.0,
        "meaning": "Clean master",
        "unscored": [],
    }

    res = regrade_against_original(
        current_meters=current_meters,
        original_meters=original_meters,
        original_grade=original_grade,
        technical_report=tech_report,
        request_text="Target -14 LUFS",
        applied_lever=lever,
    )

    assert res["regrade_agrees"] is True
    curr_grade = res["current_grade"]
    assert curr_grade["points"] >= 50.0
    comparison = res["comparison"]
    assert comparison["deltas"]["true_peak_dbtp"]["delta"] == -1.7


def test_before_after_rest_endpoints(client: TestClient) -> None:
    """Verifies REST endpoints for before/after comparison and regrading."""
    before_snap = {"true_peak_dbtp": -0.2, "bands": {"low_mid": 0.42}}
    after_snap = {"true_peak_dbtp": -1.2, "bands": {"low_mid": 0.32}}
    receipt_id = "receipt-http-999"

    # 1. Compare endpoint
    resp = client.post(
        "/api/mix/before-after/compare",
        json={
            "before_snapshot": before_snap,
            "after_snapshot": after_snap,
            "before_grade": {"points": 48.0},
            "after_grade": {"points": 56.0},
            "receipt_id": receipt_id,
            "session_id": "session_http",
        },
    )
    assert resp.status_code == 200
    comp = resp.json()["comparison"]
    assert comp["deltas"]["true_peak_dbtp"]["delta"] == -1.0
    assert comp["deltas"]["low_mid_energy_pct"]["delta"] == -10.0

    # 2. Get stored comparison by receipt_id
    resp = client.get(f"/api/mix/before-after/{receipt_id}")
    assert resp.status_code == 200
    fetched_comp = resp.json()["comparison"]
    assert fetched_comp["deltas"]["true_peak_dbtp"]["delta"] == -1.0

    # 3. Regrade endpoint
    resp = client.post(
        "/api/mix/before-after/regrade",
        json={
            "current_meters": {"true_peak_dbtp": -1.2, "integrated_lufs": -14.0},
            "original_meters": {"true_peak_dbtp": 0.2, "integrated_lufs": -13.0},
            "original_grade": {"points": 45.0},
            "technical_report": {"mqm_score": 28.0, "points_available": 30.0, "meaning": "OK"},
        },
    )
    assert resp.status_code == 200
    assert resp.json()["result"]["regrade_agrees"] is True
