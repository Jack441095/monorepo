"""The reuse profile must expose clip-meter limits before enabling live LUFS."""

from __future__ import annotations

import importlib.util
import json
import math
import os
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "tooling" / "scripts"))
import profile_live_loudness as profile


@pytest.mark.parametrize("repeats", [True, 2, 101, 3.5, math.nan])
def test_invalid_repeat_count_stops_before_loading_native(repeats, monkeypatch) -> None:
    monkeypatch.setattr(profile, "_load_native", lambda: pytest.fail("native must not load"))
    with pytest.raises(ValueError, match="repeats"):
        profile.run(repeats=repeats)


@pytest.mark.parametrize("kwargs", [{"rates": ()}, {"rates": (1,)}, {"windows": (0.1,)},
                                   {"insert_counts": (0,)}, {"insert_counts": (True,)},
                                   {"rates": (48_000.0,)}, {"rates": (48_000, 48_000)}])
def test_profile_matrix_rejects_unsupported_work_before_loading_native(kwargs, monkeypatch) -> None:
    monkeypatch.setattr(profile, "_load_native", lambda: pytest.fail("native must not load"))
    with pytest.raises(ValueError):
        profile.run(**kwargs)


def test_missing_native_module_cannot_silently_time_the_reference(monkeypatch) -> None:
    def unavailable(name):
        raise ImportError("not installed")
    monkeypatch.setattr(profile.importlib, "import_module", unavailable)
    with pytest.raises(RuntimeError, match="must be built"):
        profile._load_native()


def test_older_native_module_without_loudness_cannot_emit_a_receipt(monkeypatch) -> None:
    monkeypatch.setattr(profile.importlib, "import_module", lambda name: object())
    with pytest.raises(RuntimeError, match="no loudness_metrics"):
        profile._load_native()


@pytest.mark.parametrize("left,right", [(None, -20.0), (-20.0, None), (math.nan, -20.0),
                                        (math.inf, -20.0), (-19.0, -20.0)])
def test_metric_mismatch_never_becomes_a_passing_numeric_receipt(left, right) -> None:
    result = profile._parity({"integrated_lufs": left, "true_peak_dbtp": -1},
                             {"integrated_lufs": right, "true_peak_dbtp": -1})
    assert result["passed"] is False
    # Non-finite deltas must be absence, not invalid JSON numbers.
    json.dumps(result["absolute_deltas_db"], allow_nan=False)


def test_missing_metric_keys_are_not_mistaken_for_measured_silence() -> None:
    assert profile._parity({}, {})["passed"] is False
    silence = {"integrated_lufs": None, "true_peak_dbtp": None}
    assert profile._parity(silence, silence)["passed"] is True


def test_batch_timing_counts_complete_serial_work_and_excludes_buffer_preparation(monkeypatch) -> None:
    # Known clocks catch per-insert/batch and milliseconds/percent conversion mistakes.
    wall = iter((0, 2_000_000, 10_000_000, 14_000_000, 20_000_000, 26_000_000))
    cpu = iter((0, 1_000_000, 10_000_000, 12_000_000, 20_000_000, 23_000_000))
    monkeypatch.setattr(profile.time, "perf_counter_ns", lambda: next(wall))
    monkeypatch.setattr(profile.time, "process_time_ns", lambda: next(cpu))
    inputs = [np.zeros((8, 2), dtype=np.float32) for _ in range(8)]
    calls = []
    result = profile._measure_batch(lambda values, rate: calls.append((id(values), rate)), inputs, 48_000, 3)
    assert len(calls) == 8 * (profile.WARMUPS + 3)
    assert result["input_bytes"] == 8 * 8 * 2 * 4
    assert result["wall_mean_ms"] == 4
    assert result["process_cpu_mean_ms"] == 2
    assert result["projected_one_core_cpu_percent_at_10hz"] == 2
    assert result["projected_serial_wall_percent_at_10hz"] == 4
    assert result["wall_max_ms"] == 6


def test_failed_parity_receipt_is_saved_but_cli_exits_unsuccessfully(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr(profile, "run", lambda **kwargs: {"passed": False, "reason": "parity"})
    target = tmp_path / "failed.json"
    assert profile.main(["--json-out", str(target)]) == 1
    assert json.loads(target.read_text())["passed"] is False
    assert json.loads(capsys.readouterr().out)["reason"] == "parity"


@pytest.fixture
def native():
    if importlib.util.find_spec("kenn.core._kenn_dsp_native") is None:
        pytest.skip("optional native DSP module is not built")
    return profile._load_native()


def test_short_term_candidate_probe_exposes_gating_and_filter_restart(native) -> None:
    probes = profile.semantic_probes(native)
    # The existing gated clip result must never be relabelled as short-term LUFS.
    assert probes["gating"]["difference_db"] > 6.0
    restarted = probes["filter_restart"]["native_restarted_400ms_lufs"]
    continuous = probes["filter_restart"]["reference_continuous_tail_400ms_lufs"]
    assert restarted > continuous + 20.0


def test_native_clip_reuse_receipt_preserves_runtime_flags_and_has_numeric_parity(native, monkeypatch) -> None:
    monkeypatch.setenv("KENN_DSP_NATIVE", "0")
    monkeypatch.setenv("KENN_DSP_LOUDNESS_NATIVE", "0")
    result = profile.run(repeats=3, rates=(48_000,), windows=(0.4,), insert_counts=(1, 8))
    assert result["passed"] is True
    assert result["schema"] == "kenn.live_loudness_reuse_profile.v1"
    assert result["update_hz"] == 10
    assert [row["inserts"] for row in result["cases"][0]["native_batches"]] == [1, 8]
    assert all(value > 0 for value in result["cases"][0]["native_batches"][1]["samples_wall_ms"])
    assert "Do not attach" in result["promotion_decision"]
    assert len(result["identity"]["native_binary_sha256"]) == 64
    assert os.environ["KENN_DSP_NATIVE"] == "0"
    assert os.environ["KENN_DSP_LOUDNESS_NATIVE"] == "0"
    json.dumps(result, allow_nan=False)


def test_reference_inter_sample_peak_exceeds_discrete_peak_on_known_phase_signal() -> None:
    rate = 48_000  # samples per second; a 12 kHz sine sampled at pi/4 misses its analogue peak.
    t = np.arange(round(0.4 * rate)) / rate
    signal = np.ascontiguousarray(np.column_stack((0.99 * np.sin(2 * np.pi * rate / 4 * t + np.pi / 4),) * 2), dtype=np.float32)
    metrics = profile.reference_metrics(signal, rate)
    sample_peak = 20 * math.log10(float(np.max(np.abs(signal))))
    assert metrics["true_peak_dbtp"] > sample_peak + 2.5
