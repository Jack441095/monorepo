"""A native meter receipt must reject false timing coverage and wrong windows."""

from __future__ import annotations

import copy
import json
import math
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "tooling" / "scripts"))
import profile_streaming_meter as profile


@pytest.mark.parametrize("repeats", [True, 2, 101, 3.5, math.nan])
def test_invalid_repeats_refuse_to_start_a_native_process(repeats, monkeypatch) -> None:
    monkeypatch.setattr(profile.subprocess, "run", lambda *a, **k: pytest.fail("native must not run"))
    with pytest.raises(ValueError, match="Repeats"):
        profile.run(Path("unavailable"), repeats)


@pytest.mark.parametrize("samples,rate", [(np.zeros((48, 1)), 48_000), (np.zeros((48, 2)), 32_000),
                                         (np.array([[math.nan, 0]]), 48_000), (np.empty((0, 2)), 48_000)])
def test_reference_rejects_unqualified_audio_instead_of_producing_a_number(samples, rate) -> None:
    with pytest.raises(ValueError, match="finite stereo"):
        profile.reference_trace(samples, rate)


def test_reference_warmup_is_exact_and_ready_silence_is_zero_energy() -> None:
    result = profile.reference_trace(np.zeros((144_000, 2), dtype=np.float32), 48_000)
    assert result.shape == (30, 6)
    assert np.array_equal(result[:, 0], np.arange(1, 31) * 4800)
    assert np.array_equal(result[:, 1], np.arange(1, 31) >= 4)
    assert np.array_equal(result[:, 2], np.arange(1, 31) >= 30)
    assert not result[:, 3:].any()


@pytest.mark.parametrize("column,delta", [(0, 1), (1, 1), (2, 1), (3, .01), (4, .01), (5, .01)])
def test_window_metadata_and_each_measurement_must_match(column, delta) -> None:
    # Readiness, capture position and each linear metric are independent evidence.
    expected = np.array([[4800, 0, 0, 0, 0, .1]], dtype=float)
    actual = expected.copy(); actual[0, column] += delta
    assert profile.compare_trace(actual, expected)["passed"] is False


@pytest.mark.parametrize("actual,expected", [(np.empty((0, 6)), np.empty((0, 6))),
                                            (np.zeros((1, 5)), np.zeros((1, 5))),
                                            (np.zeros((2, 6)), np.zeros((1, 6))),
                                            (np.full((1, 6), math.nan), np.zeros((1, 6)))])
def test_malformed_numeric_traces_cannot_pass(actual, expected) -> None:
    with pytest.raises(ValueError):
        profile.compare_trace(actual, expected)


@pytest.mark.parametrize("stdout", ["diagnostic", "4800,0,0,0,0,nan\n", "4800,0,0,0,0,0\n9600,0,0,0,0,0\n"])
def test_native_trace_refuses_diagnostics_nonfinite_or_wrong_row_counts(stdout, monkeypatch) -> None:
    monkeypatch.setattr(profile.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=stdout))
    with pytest.raises(ValueError):
        profile.native_trace(Path("native"), np.zeros((4800, 2), dtype=np.float32), 48_000)


def timing_payload() -> dict:
    return {
        "schema": "kenn.streaming_meter_native_profile.v1", "repeats": 3, "meter_bytes": 1056,
        "cells": [{"rate": rate, "inserts": inserts, "mode": mode, "warmup_ticks": 32,
                   "wall_ms": [1.0, 2.0, 3.0], "cpu_ms": [.5, 1.0, 1.5], "processing_passed": True}
                  for rate in profile.RATES for inserts in profile.INSERT_COUNTS for mode in profile.MODES],
    }


def test_timing_units_cover_all_serial_work_in_one_100ms_batch() -> None:
    result = profile.summarize_native_profile(timing_payload(), 3)
    assert len(result["cells"]) == 36
    assert result["candidate_storage_bytes_per_insert"] == 1056
    for cell in result["cells"]:
        assert cell["wall_mean_ms"] == 2.0
        assert cell["process_cpu_mean_ms"] == 1.0
        assert cell["projected_one_core_percent_at_10hz"] == 1.0
        assert cell["serial_100ms_budget_percent"] == 2.0


@pytest.mark.parametrize("fault", ["schema", "repeats", "storage", "missing", "duplicate", "mode",
                                   "cold", "samples", "negative", "nan", "processing"])
def test_native_timing_receipt_rejects_missing_coverage_and_invalid_measurements(fault) -> None:
    payload = timing_payload()
    if fault == "schema": payload["schema"] = "old"
    elif fault == "repeats": payload["repeats"] = 20
    elif fault == "storage": payload["meter_bytes"] = 0
    elif fault == "missing": payload["cells"].pop()
    elif fault == "duplicate": payload["cells"].append(copy.deepcopy(payload["cells"][0]))
    elif fault == "mode": payload["cells"][0]["mode"] = "other"
    elif fault == "cold": payload["cells"][0]["warmup_ticks"] = 3
    elif fault == "samples": payload["cells"][0]["wall_ms"].pop()
    elif fault == "negative": payload["cells"][0]["cpu_ms"][0] = -1
    elif fault == "nan": payload["cells"][0]["wall_ms"][0] = math.nan
    elif fault == "processing": payload["cells"][0]["processing_passed"] = False
    with pytest.raises(ValueError):
        profile.summarize_native_profile(payload, 3)


def test_failed_numerical_receipt_is_written_but_cli_fails(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(profile, "run", lambda *a, **k: {"passed": False})
    target = tmp_path / "failed.json"
    assert profile.main(["--binary", "unused", "--json-out", str(target)]) == 1
    assert json.loads(target.read_text())["passed"] is False


def test_dc_qualification_returns_json_boolean_not_numpy_scalar(monkeypatch) -> None:
    # The first real profile completed its work but failed to save because a
    # NumPy DC comparison leaked np.bool into the receipt.
    monkeypatch.setattr(profile, "RATES", (48_000,))
    monkeypatch.setattr(profile, "native_trace", lambda binary, samples, rate: profile.reference_trace(samples, rate))
    reports = profile.qualify(Path("unused"))
    json.dumps(reports, allow_nan=False)
    assert all(type(report["passed"]) is bool for report in reports)


@pytest.mark.parametrize("fixture", ["calibration", "changing_level", "dc", "peak_16"])
def test_compiled_streaming_meter_matches_continuous_reference(fixture) -> None:
    binary = os.getenv("KENN_STREAMING_METER_TEST_BINARY")
    if not binary:
        pytest.skip("Optional compiled streaming meter target is unavailable")  # Python-only environments cannot claim native qualification.
    samples = profile._fixture(48_000, fixture)
    actual = profile.native_trace(Path(binary), samples, 48_000)
    report = profile.compare_trace(actual, profile.reference_trace(samples, 48_000))
    assert report["passed"], report
