"""scripts/benchmark_audio_analysis.py computes a "qualified" verdict but had
no test enforcing it, and its own main() always returned 0 regardless of
that verdict -- a real regression here would silently report success to
anything relying on the exit code rather than parsing the JSON. Fixed the
exit code and added this test so the real benchmark is asserted green.
"""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "tooling" / "scripts"))

from benchmark_audio_analysis import _wav_bytes, run


def test_benchmark_is_qualified(monkeypatch) -> None:
    # This assertion is about the deterministic Python benchmark contract,
    # not whichever optional native candidate the surrounding test process
    # happens to enable. Keep it stable in both native and fallback CI jobs.
    monkeypatch.setenv("KENN_DSP_NATIVE", "0")
    monkeypatch.setenv("KENN_DSP_MASKING_NATIVE", "0")
    result = run(long_seconds=2.0, workers=2)
    assert result["qualified"] is True, result
    assert result["schema"] == "kenn.dsp_benchmark.v1"
    assert result["candidate"] == "python-stdlib-reference"
    assert result["passed"] is True
    assert result["stage_samples_ms"]
    assert result["build_type"] == "python-reference"
    assert all(case["warmups"] == 3 for case in result["cases"])
    assert all(case["ok"] and case["within_input_limit"] for case in result["cases"])
    assert all(case["p95_ms"] >= case["p50_ms"] for case in result["cases"])
    assert result["concurrency"]["all_ok"] and result["concurrency"]["all_complete"]


def test_benchmark_accepts_external_fixture(tmp_path: Path) -> None:
    fixture = tmp_path / "owned-mix.wav"
    fixture.write_bytes(_wav_bytes(seconds=0.25, sample_rate=48_000))

    result = run(long_seconds=1.0, workers=1, repeats=1, fixture_paths=[fixture])

    assert result["fixture"]["kind"] == "external_wav"
    assert result["fixture"]["sources"][0]["path"] == str(fixture)
    assert result["fixture"]["sources"][0]["sha256"]
    assert result["cases"][0]["label"] == "owned-mix"
    assert result["cases"][0]["wav"]["sample_rate_hz"] == 48_000
    assert result["qualified"] is True
