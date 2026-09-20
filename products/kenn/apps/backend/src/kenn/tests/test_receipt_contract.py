from __future__ import annotations

import time

from kenn.core.receipt_contract import (
    StageTimer,
    classify_retry_safety,
    new_correlation_id,
    resolve_correlation_id,
)


def test_new_correlation_id_is_unique_and_bounded() -> None:
    a, b = new_correlation_id(), new_correlation_id()
    assert a != b
    assert a.startswith("corr-")
    assert len(a) < 128


def test_resolve_correlation_id_preserves_a_caller_supplied_id() -> None:
    assert resolve_correlation_id("caller-tracked-id-123") == "caller-tracked-id-123"


def test_resolve_correlation_id_mints_one_when_absent() -> None:
    resolved = resolve_correlation_id("")
    assert resolved.startswith("corr-")
    resolved_none = resolve_correlation_id(None)
    assert resolved_none.startswith("corr-")


def test_resolve_correlation_id_bounds_length() -> None:
    huge = "x" * 10_000
    assert len(resolve_correlation_id(huge)) == 128


def test_classify_retry_safety_verified_success_is_safe() -> None:
    assert classify_retry_safety(verified=True, status="applied") == "safe"


def test_classify_retry_safety_ambiguous_outcomes_require_inspection() -> None:
    assert classify_retry_safety(verified=False, status="failed_verification") == "requires_inspection"
    assert classify_retry_safety(verified=False, status="transport_uncertain") == "requires_inspection"


def test_classify_retry_safety_rejected_before_write_is_unsafe() -> None:
    # e.g. stale-state or bad-token rejections never reached Live at all --
    # still "unsafe" to blindly retry with the same token/idempotency key,
    # but for a different reason than an ambiguous in-flight write.
    assert classify_retry_safety(verified=False, status="failed") == "unsafe"


def test_stage_timer_only_reports_stages_actually_marked() -> None:
    timer = StageTimer()
    timer.mark("snapshot")
    result = timer.as_ms()
    assert set(result.keys()) == {"snapshot", "total"}


def test_stage_timer_reports_positive_elapsed_time_in_order() -> None:
    timer = StageTimer()
    time.sleep(0.01)
    timer.mark("snapshot")
    time.sleep(0.01)
    timer.mark("write")
    time.sleep(0.01)
    timer.mark("readback")
    result = timer.as_ms()
    assert set(result.keys()) == {"snapshot", "write", "readback", "total"}
    assert result["snapshot"] > 0
    assert result["write"] > 0
    assert result["readback"] > 0
    assert result["total"] >= result["snapshot"] + result["write"] + result["readback"] - 1  # rounding slack


def test_stage_timer_with_no_marks_reports_empty() -> None:
    timer = StageTimer()
    assert timer.as_ms() == {}
