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


def trace_payload(mode="juce8") -> dict:
    factor, delay, roundtrip = profile.METADATA[mode]
    iir = "iir" in mode
    return {"factor": factor, "upsampling_delay_frames": delay, "round_trip_delay_frames": roundtrip,
            "impulse_peak_frame": None if mode == "current" else 3.125 if iir else delay,
            "linear_phase": not iir, "peaks": [.5], "cpp_heap_calls": 0}


@pytest.mark.parametrize("mode", profile.MODES)
def test_valid_native_metadata_keeps_iir_impulse_separate_from_fixed_delay(mode, monkeypatch) -> None:
    payload = trace_payload(mode)
    monkeypatch.setattr(profile.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=json.dumps(payload)))
    assert profile.native_trace(Path("unused"), np.zeros((4800, 2)), 48_000, mode) == payload
    if "iir" in mode:
        assert payload["upsampling_delay_frames"] is None and payload["linear_phase"] is False


@pytest.mark.parametrize("fault", ["factor", "delay", "roundtrip", "impulse", "phase", "missing", "nan", "negative", "heap", "diagnostic"])
def test_native_trace_rejects_wrong_units_missing_windows_and_invalid_numbers(fault, monkeypatch) -> None:
    payload = trace_payload()
    if fault == "factor": payload["factor"] = 4
    elif fault == "delay": payload["upsampling_delay_frames"] = 64.25
    elif fault == "roundtrip": payload["round_trip_delay_frames"] = 38.625
    elif fault == "impulse": payload["impulse_peak_frame"] = 64.25
    elif fault == "phase": payload["linear_phase"] = False
    elif fault == "missing": payload["peaks"] = []
    elif fault == "nan": payload["peaks"] = [math.nan]
    elif fault == "negative": payload["peaks"] = [-.5]
    elif fault == "heap": payload["cpp_heap_calls"] = True
    stdout = "not a receipt" if fault == "diagnostic" else json.dumps(payload)
    monkeypatch.setattr(profile.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=stdout))
    with pytest.raises(ValueError):
        profile.native_trace(Path("unused"), np.zeros((4800, 2)), 48_000, "juce8")


@pytest.mark.parametrize("fault", ["fixed_delay", "linear_phase", "roundtrip"])
def test_iir_trace_cannot_present_a_frequency_dependent_phase_as_fixed_delay(fault, monkeypatch) -> None:
    # The IIR impulse maximum is not a group delay for a mixed signal.
    payload = trace_payload("juce8_iir")
    if fault == "fixed_delay": payload["upsampling_delay_frames"] = payload["impulse_peak_frame"]
    elif fault == "linear_phase": payload["linear_phase"] = True
    elif fault == "roundtrip": payload["round_trip_delay_frames"] = payload["impulse_peak_frame"]
    monkeypatch.setattr(profile.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=json.dumps(payload)))
    with pytest.raises(ValueError):
        profile.native_trace(Path("unused"), np.zeros((4800, 2)), 48_000, "juce8_iir")


@pytest.mark.parametrize("fault", ["architecture", "debug", "version"])
def test_unqualified_build_is_rejected_before_source_or_audio_probes(fault, monkeypatch) -> None:
    info = {"juce_version": "8.0.2", "assertions_enabled": False, "pointer_bits": 64,
            "compiled_arch": profile.platform.machine(), "current_meter_bytes": 1024, "compiler": "test"}
    if fault == "architecture": info["compiled_arch"] = "unknown"
    elif fault == "debug": info["assertions_enabled"] = True
    elif fault == "version": info["juce_version"] = "8.0.3"
    monkeypatch.setattr(profile, "_call", lambda *a: info)
    monkeypatch.setattr(profile.subprocess, "run", lambda *a, **k: pytest.fail("source probe must not run"))
    with pytest.raises(ValueError, match="Release"):
        profile.run(Path("unused"), Path("unused"), 3)


def timing_cells() -> list[dict]:
    return [{"rate": rate, "inserts": inserts, "mode": mode, "warmup_ticks": 32,
             "cpp_heap_calls": 0, "checksum": 1.0, "wall_ms": [1.0, 2.0, 3.0], "cpu_ms": [.5, 1.0, 1.5]}
            for rate in profile.RATES for inserts in profile.INSERT_COUNTS for mode in profile.PROFILE_MODES]


def test_cpu_projection_represents_all_inserts_running_every_100ms() -> None:
    summaries = profile.summarize_timings(timing_cells(), 3)
    assert len(summaries) == 84
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
@pytest.mark.parametrize("batched_mode,single_mode", profile.CONTINUITY_PAIRS)
def test_prepared_batched_and_single_frame_filters_preserve_boundary_history(native_binary, rate, batched_mode, single_mode) -> None:
    for name, samples in profile._continuity_fixtures(rate).items():
        batched = profile.native_trace(native_binary, samples, rate, batched_mode)
        single = profile.native_trace(native_binary, samples, rate, single_mode)
        assert np.allclose(batched["peaks"], single["peaks"], rtol=0, atol=1e-12), name
        assert batched["cpp_heap_calls"] == single["cpp_heap_calls"] == 0
        if name == "silence": assert not any(batched["peaks"])


@pytest.mark.parametrize("rate", profile.RATES)
def test_iir_can_pass_a_single_tone_while_changing_the_peak_of_a_cosine_pair(native_binary, rate) -> None:
    # Two aligned components reach exactly 0.5 together; nonlinear phase
    # changes their crest even though each component retains its own amplitude.
    pair = next(case for case in profile.paired_tone_cases()
                if case["frequencies"] == (.125, .375) and case["offset_frames"] == 0)
    single = {"frequency": .125, "phase_rad": 0.0}
    for mode in ("juce8_iir", "juce8_iir_float"):
        tone = profile.native_trace(native_binary, profile.tone(rate, single), rate, mode)
        mixed = profile.native_trace(native_binary, profile.paired_tone(rate, pair), rate, mode)
        assert profile.ERROR_BOUNDS_DB[0] <= 20 * math.log10(tone["peaks"][-1] / .5) <= profile.ERROR_BOUNDS_DB[1]
        assert 20 * math.log10(mixed["peaks"][-1] / .5) < profile.ERROR_BOUNDS_DB[0]
        assert mixed["upsampling_delay_frames"] is None and mixed["cpp_heap_calls"] == 0
    for mode in ("juce8", "juce8_float", "juce8_low", "juce8_low_float"):
        mixed = profile.native_trace(native_binary, profile.paired_tone(rate, pair), rate, mode)
        assert profile.ERROR_BOUNDS_DB[0] <= 20 * math.log10(mixed["peaks"][-1] / .5) <= profile.ERROR_BOUNDS_DB[1]


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
