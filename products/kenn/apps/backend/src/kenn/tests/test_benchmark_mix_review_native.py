"""Offline comparison must prove execution and preserve refusals, not time fallback."""
from __future__ import annotations

import copy
import io
import os
from pathlib import Path
import sys
import wave

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "tooling/scripts"))
import benchmark_mix_review_native as bench


def _report(value=0.0):
    return {"ok": True, "metrics": {name: value for name in bench.METERS}, "findings": [],
            "proof": {name: {"attempts": 1, "successful": 1} for name in ("decode_pcm", "loudness_metrics")}}


@pytest.mark.parametrize("variant", ["decode_only", "loudness_only", "combined"])
def test_identical_fallback_is_not_native_qualification(variant):
    reference = _report()
    candidate = _report()
    for counts in candidate["proof"].values():
        counts["successful"] = 0
    assert not bench._compare(reference, candidate, variant, 1, False)["qualified"]


def test_meter_zero_survives_but_missing_meter_cannot_equal_it():
    reference = _report()
    candidate = _report()
    assert bench._compare(reference, candidate, "combined", 1, False)["qualified"]
    candidate["metrics"]["loudness_range_lu"] = None
    assert not bench._compare(reference, candidate, "combined", 1, False)["qualified"]


@pytest.mark.parametrize("change", ["meter", "finding", "nonfinite", "bool"])
def test_changed_analysis_cannot_qualify(change):
    reference, candidate = _report(), _report()
    if change == "meter":
        candidate["metrics"]["true_peak_dbtp"] = 0.02
    elif change == "finding":
        candidate["findings"] = [{"detected": True}]
    elif change == "nonfinite":
        candidate["metrics"]["true_peak_dbtp"] = float("nan")
    else:
        candidate["metrics"]["true_peak_dbtp"] = False
    assert not bench._compare(reference, candidate, "combined", 1, False)["qualified"]


def test_short_or_silent_refusal_still_requires_native_decode():
    reference, candidate = _report(None), _report(None)
    refusal = {"detected": False, "severity": "unknown", "explanation": "KENN abstained: short audio"}
    reference["findings"] = candidate["findings"] = [refusal]
    candidate["proof"]["loudness_metrics"]["successful"] = 0
    assert bench._compare(reference, candidate, "combined", 1, True)["qualified"]
    candidate["proof"]["decode_pcm"]["successful"] = 0
    assert not bench._compare(reference, candidate, "combined", 1, True)["qualified"]


@pytest.mark.parametrize("failure", [False, True])
def test_gates_and_wrappers_restore_after_success_or_exception(monkeypatch, failure):
    for index, name in enumerate(bench.GATES):
        if index % 2:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, "inherited-value")
    before = {name: os.environ.get(name) for name in bench.GATES}
    original = bench.native_fft.decode_pcm
    try:
        with bench._execution("reference"):
            assert all(os.environ[name] == "0" for name in bench.GATES)
            assert bench.native_fft.decode_pcm is not original
            if failure:
                raise RuntimeError("probe")
    except RuntimeError:
        assert failure
    assert {name: os.environ.get(name) for name in bench.GATES} == before
    assert bench.native_fft.decode_pcm is original


@pytest.mark.parametrize("variant,decode,loudness", [("reference", False, False), ("decode_only", True, False), ("loudness_only", False, True), ("combined", True, True)])
def test_variants_are_independent_of_inherited_opt_ins(monkeypatch, variant, decode, loudness):
    for name in bench.GATES:
        monkeypatch.setenv(name, "1")
    with bench._execution(variant):
        assert os.environ["KENN_DSP_NATIVE"] == str(int(decode or loudness))
        assert os.environ["KENN_DSP_MIX_REVIEW_DECODE_NATIVE"] == str(int(decode))
        assert os.environ["KENN_DSP_LOUDNESS_NATIVE"] == str(int(loudness))


def test_proof_counts_success_not_merely_attempts_and_excludes_warmup(monkeypatch):
    monkeypatch.setattr(bench.native_fft, "decode_pcm", lambda data: {"channels": [[0.1]], "channel_count": 1, "sample_rate": 48000})
    monkeypatch.setattr(bench.native_fft, "loudness_metrics", lambda data, rate: None)
    def analyze(data, **kwargs):
        bench.native_fft.decode_pcm(data)
        bench.native_fft.loudness_metrics([], 48000)
        return {"ok": True, "metrics": {}, "findings": []}
    monkeypatch.setattr(bench, "analyze_wav", analyze)
    measured = bench._measure(b"fixture", "combined", 2)
    assert measured["proof"] == {"decode_pcm": {"attempts": 2, "successful": 2},
                                "loudness_metrics": {"attempts": 2, "successful": 0}}
    assert len(measured["samples_ms"]) == 2


@pytest.mark.parametrize("kind", ["steady", "stepped", "anti_phase", "silence", "short"])
def test_fixtures_are_deterministic_pcm_and_never_write_audio(kind):
    payload = bench._wav_bytes(0.2, 44100, 2, kind)
    assert payload == bench._wav_bytes(0.2, 44100, 2, kind)
    with wave.open(io.BytesIO(payload)) as handle:
        assert (handle.getnchannels(), handle.getframerate(), handle.getnframes()) == (2, 44100, 8820)


def test_comparison_does_not_mutate_reports():
    reference, candidate = _report(), _report()
    before = copy.deepcopy((reference, candidate))
    bench._compare(reference, candidate, "combined", 1, False)
    assert (reference, candidate) == before


@pytest.mark.parametrize("poison", [None, {}, {"integrated_lufs": float("nan")}, {"integrated_lufs": False}, {"integrated_lufs": -14.0, "loudness_range_lu": 0.0}])
def test_rejected_loudness_result_does_not_prove_native_execution(monkeypatch, poison):
    monkeypatch.setattr(bench.native_fft, "loudness_metrics", lambda *a: poison)
    with bench._execution("combined") as proof:
        bench.native_fft.loudness_metrics([], 48000)
    assert proof["loudness_metrics"] == {"attempts": 1, "successful": 0}
    reference, candidate = _report(), _report()
    candidate["proof"]["loudness_metrics"] = proof["loudness_metrics"]
    assert not bench._compare(reference, candidate, "combined", 1, False)["qualified"]


@pytest.mark.parametrize("poison", [None, {}, {"channels": [[], []], "channel_count": 2, "sample_rate": 48000}])
def test_rejected_decode_result_does_not_prove_native_execution(poison):
    assert not bench._accepted_native_result("decode_pcm", poison)


@pytest.mark.parametrize("kwargs", [{"seconds": float("nan")}, {"seconds": float("inf")}, {"repeats": True}, {"sample_rate": False}, {"seconds": 1.0, "matrix": True}])
def test_invalid_workload_rejects_before_analysis(kwargs, monkeypatch):
    monkeypatch.setattr(bench, "analyze_wav", lambda *a, **k: pytest.fail("must reject before work"))
    params = {"seconds": 6.0, "sample_rate": 48000, "repeats": 1, **kwargs}
    with pytest.raises(ValueError):
        bench.run(**params)


def test_numpy_fallback_cannot_qualify_as_named_reference(monkeypatch):
    monkeypatch.setattr(bench.local_engine, "_pyln", None)
    monkeypatch.setattr(bench, "_measure", lambda *a: _report())
    monkeypatch.setattr(bench, "_metadata", lambda: {})
    result = bench.run(seconds=6.0, sample_rate=48000, repeats=1)
    assert not result["reference_available"]
    assert not result["qualified"]


def test_matrix_covers_rates_layouts_and_refusals_with_strict_json(monkeypatch):
    import json
    monkeypatch.setattr(bench, "_metadata", lambda: {})
    monkeypatch.setattr(bench, "_measure", lambda *a: _report())
    result = bench.run(seconds=6.0, sample_rate=48000, repeats=1, matrix=True)
    fixtures = [case["fixture"] for case in result["cases"]]
    assert len(fixtures) == 27
    assert {fixture["sample_rate_hz"] for fixture in fixtures} == {44100, 48000, 96000}
    assert {fixture["channels"] for fixture in fixtures} == {1, 2}
    assert {fixture["kind"] for fixture in fixtures} == {"steady", "stepped", "anti_phase", "silence", "short"}
    assert all(fixture["seconds"] == 0.2 for fixture in fixtures if fixture["kind"] == "short")
    # Stubbed healthy readings must fail the matrix's silent/short refusal cases.
    assert not result["qualified"]
    json.dumps(result, allow_nan=False)


def test_request_exception_restores_inherited_environment_and_observers(monkeypatch):
    monkeypatch.setenv("KENN_DSP_NATIVE", "0")
    before = {name: os.environ.get(name) for name in bench.GATES}
    original = bench.native_fft.loudness_metrics
    def fail(*a, **k):
        raise RuntimeError("request failed")
    monkeypatch.setattr(bench, "analyze_wav", fail)
    with pytest.raises(RuntimeError, match="request failed"):
        bench._measure(b"fixture", "combined", 1)
    assert {name: os.environ.get(name) for name in bench.GATES} == before
    assert bench.native_fft.loudness_metrics is original


def test_complete_native_zero_range_is_accepted_without_peak_fallback():
    assert bench._accepted_native_result("loudness_metrics", {
        "integrated_lufs": -14.0, "loudness_range_lu": 0.0, "true_peak_dbtp": -1.0})


def test_earlier_failed_request_cannot_hide_behind_healthy_last_report():
    reference, candidate = _report(), _report()
    reference["requests"] = [_report(), _report()]
    candidate["requests"] = [_report(), _report()]
    candidate["requests"][0]["metrics"]["integrated_lufs"] = 0.02
    comparison = bench._compare(reference, candidate, "combined", 2, False)
    assert not comparison["qualified"]
    assert not comparison["request_comparisons"][0]["qualified"]
    assert comparison["request_comparisons"][1]["qualified"]


def test_extra_native_calls_cannot_compensate_for_a_request_that_fell_back():
    reference, candidate = _report(), _report()
    reference["requests"] = [_report(), _report()]
    candidate["requests"] = [_report(), _report()]
    candidate["proof"]["loudness_metrics"]["successful"] = 2
    candidate["requests"][0]["proof"]["loudness_metrics"]["successful"] = 0
    candidate["requests"][1]["proof"]["loudness_metrics"]["successful"] = 2
    comparison = bench._compare(reference, candidate, "combined", 2, False)
    assert not comparison["qualified"]
    assert not comparison["execution_verified"]


def test_repeated_final_only_report_has_no_per_request_proof():
    assert not bench._compare(_report(), _report(), "combined", 2, False)["qualified"]


def test_measurement_snapshots_each_request_before_reused_result_changes(monkeypatch):
    report = {"ok": True, "metrics": {"integrated_lufs": -14.0}, "findings": []}
    calls = []
    def analyze(*a, **k):
        calls.append(None)
        report["metrics"]["integrated_lufs"] = -14.0 + len(calls)
        return report
    monkeypatch.setattr(bench, "analyze_wav", analyze)
    measured = bench._measure(b"fixture", "reference", 2)
    assert [item["metrics"]["integrated_lufs"] for item in measured["requests"]] == [-12.0, -11.0]
