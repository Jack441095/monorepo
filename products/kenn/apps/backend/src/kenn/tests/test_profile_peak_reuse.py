"""True-peak reuse evidence must preserve failures, timing coverage and history."""

from __future__ import annotations

import copy
import json
import math
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "tooling" / "scripts"))
import profile_peak_reuse as profile


@pytest.mark.parametrize("repeats", [True, 2, 31, 3.5, math.nan])
def test_invalid_repeats_do_not_start_native_comparison(repeats, monkeypatch) -> None:
    monkeypatch.setattr(profile.subprocess, "run", lambda *a, **k: pytest.fail("native must not run"))
    with pytest.raises(ValueError, match="Repeats"):
        profile.run(Path("missing"), Path("missing"), repeats)


@pytest.mark.parametrize("samples,rate,mode", [
    (np.zeros((4800, 1)), 48_000, "juce8"), (np.zeros((4800, 2)), 32_000, "juce8"),
    (np.zeros((4800, 2)), 48_000, "typo"), (np.zeros((4801, 2)), 48_000, "juce8"),
    (np.full((4800, 2), math.nan), 48_000, "juce8"), (np.empty((0, 2)), 48_000, "juce8"),
])
def test_invalid_audio_or_incomplete_interval_cannot_produce_evidence(samples, rate, mode, monkeypatch) -> None:
    monkeypatch.setattr(profile.subprocess, "run", lambda *a, **k: pytest.fail("native must not run"))
    with pytest.raises(ValueError, match="finite stereo"):
        profile.native_trace(Path("missing"), samples, rate, mode)


@pytest.mark.parametrize("fault", ["factor", "delay", "roundtrip", "missing", "nan", "negative", "heap", "diagnostic"])
def test_native_trace_rejects_wrong_units_missing_windows_and_invalid_numbers(fault, monkeypatch) -> None:
    payload = {"factor": 8, "upsampling_delay_frames": 38.625, "round_trip_delay_frames": 64.25,
               "peaks": [.5], "cpp_heap_calls": 0}
    if fault == "factor": payload["factor"] = 4
    elif fault == "delay": payload["upsampling_delay_frames"] = 64.25
    elif fault == "roundtrip": payload["round_trip_delay_frames"] = 38.625
    elif fault == "missing": payload["peaks"] = []
    elif fault == "nan": payload["peaks"] = [math.nan]
    elif fault == "negative": payload["peaks"] = [-.5]
    elif fault == "heap": payload["cpp_heap_calls"] = True
    stdout = "not a receipt" if fault == "diagnostic" else json.dumps(payload)
    monkeypatch.setattr(profile.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=stdout))
    with pytest.raises(ValueError):
        profile.native_trace(Path("unused"), np.zeros((4800, 2)), 48_000, "juce8")


def timing_cells() -> list[dict]:
    return [{"rate": rate, "inserts": inserts, "mode": mode, "warmup_ticks": 32,
             "cpp_heap_calls": 0, "checksum": 1.0, "wall_ms": [1.0, 2.0, 3.0], "cpu_ms": [.5, 1.0, 1.5]}
            for rate in profile.RATES for inserts in profile.INSERT_COUNTS for mode in profile.MODES]


def test_cpu_projection_represents_all_inserts_running_every_100ms() -> None:
    summaries = profile.summarize_timings(timing_cells(), 3)
    assert len(summaries) == 48
    assert all(cell["wall_mean_ms"] == 2.0 and cell["wall_max_ms"] == 3.0 for cell in summaries)
    assert all(cell["projected_one_core_percent_at_10hz"] == 1.0 for cell in summaries)


@pytest.mark.parametrize("fault", ["missing", "duplicate", "mode", "cold", "samples", "negative", "nan", "checksum", "heap"])
def test_timing_receipt_cannot_average_away_missing_or_invalid_work(fault) -> None:
    cells = timing_cells()
    if fault == "missing": cells.pop()
    elif fault == "duplicate": cells.append(copy.deepcopy(cells[0]))
    elif fault == "mode": cells[0]["mode"] = "typo"
    elif fault == "cold": cells[0]["warmup_ticks"] = 0
    elif fault == "samples": cells[0]["wall_ms"].pop()
    elif fault == "negative": cells[0]["cpu_ms"][0] = -1
    elif fault == "nan": cells[0]["wall_ms"][0] = math.nan
    elif fault == "checksum": cells[0]["checksum"] = 0
    elif fault == "heap": cells[0]["cpp_heap_calls"] = -1
    with pytest.raises(ValueError):
        profile.summarize_timings(cells, 3)


def test_failed_bounded_checks_write_their_scores_and_return_failure(monkeypatch, tmp_path) -> None:
    # A reviewable failing receipt must survive; a green CLI must not hide it.
    monkeypatch.setattr(profile, "run", lambda *a, **k: {"juce8_bounded_checks_passed": False, "accuracy": [{"passed": False}]})
    output = tmp_path / "failed.json"
    assert profile.main(["--binary", "unused", "--juce-source", "unused", "--json-out", str(output)]) == 1
    assert json.loads(output.read_text())["accuracy"][0]["passed"] is False


@pytest.fixture
def native_binary() -> Path:
    configured = os.environ.get("KENN_PEAK_REUSE_TEST_BINARY")
    if not configured:
        pytest.skip("Set KENN_PEAK_REUSE_TEST_BINARY to the standalone Release comparison tool.")
    binary = Path(configured)
    assert binary.is_file()
    return binary


@pytest.mark.parametrize("rate", profile.RATES)
def test_real_filters_separate_fir_attenuation_from_four_times_grid_miss(native_binary, rate) -> None:
    # The short filter and the 4x grid fail different known-amplitude tones;
    # JUCE 8x clears both without treating either baseline failure as silence.
    cases = {case["name"]: case for case in profile.tone_cases()}
    for name, failing_mode in (("short_fir_underread", "current"), ("four_times_grid_miss", "juce4")):
        samples = profile.tone(rate, cases[name])
        failing = profile.native_trace(native_binary, samples, rate, failing_mode)
        candidate = profile.native_trace(native_binary, samples, rate, "juce8")
        assert 20 * math.log10(failing["peaks"][-1] / .5) < profile.ERROR_BOUNDS_DB[0]
        assert profile.ERROR_BOUNDS_DB[0] <= 20 * math.log10(candidate["peaks"][-1] / .5) <= profile.ERROR_BOUNDS_DB[1]
        assert candidate["cpp_heap_calls"] == 0


@pytest.mark.parametrize("rate", profile.RATES)
def test_prepared_batched_and_single_frame_filters_preserve_boundary_history(native_binary, rate) -> None:
    for name, samples in profile._continuity_fixtures(rate).items():
        batched = profile.native_trace(native_binary, samples, rate, "juce8")
        single = profile.native_trace(native_binary, samples, rate, "juce8_frame")
        assert np.allclose(batched["peaks"], single["peaks"], rtol=0, atol=1e-12), name
        assert batched["cpp_heap_calls"] == single["cpp_heap_calls"] == 0
        if name == "silence": assert not any(batched["peaks"])


@pytest.mark.parametrize("kind", ["empty", "partial_frame", "partial_bin", "nan", "inf"])
def test_native_tool_rejects_bad_fixture_before_emitting_peak_json(native_binary, tmp_path, kind) -> None:
    samples = np.zeros((4800, 2), dtype="<f4")
    if kind == "nan": samples[20, 0] = math.nan
    elif kind == "inf": samples[20, 1] = math.inf
    contents = samples.tobytes()
    if kind == "empty": contents = b""
    elif kind == "partial_frame": contents = contents[:-1]
    elif kind == "partial_bin": contents = contents[:-8]
    fixture = tmp_path / "synthetic.f32"
    fixture.write_bytes(contents)
    result = subprocess.run([str(native_binary), "--trace", "juce8", "48000", str(fixture)], capture_output=True, text=True, timeout=10)
    assert result.returncode == 2
    assert not result.stdout


@pytest.mark.parametrize("arguments", [("--profile", "juce8", "48000", "64junk", "3"),
                                       ("--profile", "juce8", "48000tail", "64", "3"),
                                       ("--profile", "juce8", "32000", "64", "3"),
                                       ("--profile", "unknown", "48000", "64", "3"),
                                       ("--profile", "juce8", "48000", "2", "3")])
def test_native_cli_does_not_silently_select_another_matrix_cell(native_binary, arguments) -> None:
    result = subprocess.run([str(native_binary), *arguments], capture_output=True, text=True, timeout=10)
    assert result.returncode == 2
    assert not result.stdout


def test_real_profile_measures_cpu_and_wall_after_full_warmup(native_binary) -> None:
    cell = profile._call(native_binary, "--profile", "juce8", "48000", "8", "3")
    assert cell["warmup_ticks"] == 32 and cell["cpp_heap_calls"] == 0 and cell["checksum"] > 0
    assert len(cell["wall_ms"]) == len(cell["cpu_ms"]) == 3
    assert all(value > 0 for value in cell["wall_ms"] + cell["cpu_ms"])
