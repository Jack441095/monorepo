"""Unit tests for the release-health gate logic itself (Stage E,
docs/AUDIO_MVP_MASTER_PLAN.md).

These test the pure evaluate_*()/combine_gate() functions in
scripts/eval/release_health_check.py against known-good and known-bad inputs
-- they do not run the real KENN/TTS/AutoMix pipelines (that's what running
the script for real does; see the plan doc for the actual measured numbers).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "scripts" / "eval") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "eval"))

import release_health_check as rhc  # noqa: E402


# --- evaluate_latency (KENN retrieval / TTS) --------------------------------

def test_evaluate_latency_passes_when_steady_state_under_slo():
    result = rhc.evaluate_latency("kenn", [0.30, 0.02, 0.03, 0.10], slo_s=0.5)
    assert result["ok"] is True
    assert result["failures"] == []
    assert result["cold_start_s"] == 0.30
    assert result["steady_state_max_s"] == 0.10


def test_evaluate_latency_fails_when_steady_state_over_slo():
    result = rhc.evaluate_latency("tts", [5.6, 0.25, 2.3, 0.22], slo_s=2.0)
    assert result["ok"] is False
    assert len(result["failures"]) == 1
    assert "steady-state max 2.300s exceeds SLO 2.000s" in result["failures"][0]


def test_evaluate_latency_ignores_cold_start_spike():
    """A slow first call (model load) must not fail the gate by itself --
    only steady-state performance is gated, matching the plan doc's own
    cold-start-vs-steady-state distinction for both KENN and TTS."""
    result = rhc.evaluate_latency("tts", [7.44, 0.9, 1.1, 1.0], slo_s=2.0)
    assert result["ok"] is True
    assert result["cold_start_s"] == 7.44


def test_evaluate_latency_no_samples_fails_closed():
    result = rhc.evaluate_latency("kenn", [], slo_s=0.5)
    assert result["ok"] is False
    assert "no samples collected" in result["failures"][0]


def test_evaluate_latency_single_sample_gates_on_it():
    """With only one sample there is no steady-state data to separate out --
    the single sample must still be gated, not silently skipped."""
    result = rhc.evaluate_latency("kenn", [10.0], slo_s=0.5)
    assert result["ok"] is False


# --- evaluate_render_ratios (AutoMix <=2x real-time) ------------------------

def test_evaluate_render_ratios_passes_under_slo():
    result = rhc.evaluate_render_ratios(
        {"pop": 0.7, "edm": 1.35, "jazz": 1.0}, slo_ratio=2.0
    )
    assert result["ok"] is True
    assert result["worst_case"] == "edm"
    assert result["worst_ratio"] == 1.35


def test_evaluate_render_ratios_fails_over_slo():
    result = rhc.evaluate_render_ratios(
        {"pop": 0.7, "edm": 2.5, "jazz": 1.0}, slo_ratio=2.0
    )
    assert result["ok"] is False
    assert "edm" in result["failures"][0]


def test_evaluate_render_ratios_empty_fails_closed():
    result = rhc.evaluate_render_ratios({}, slo_ratio=2.0)
    assert result["ok"] is False


# --- evaluate_quality_summary (automix_quality_benchmark.py summary) -------

def test_evaluate_quality_summary_passes_on_known_good_baseline():
    """Mirrors the real 30/30 baseline from the plan doc."""
    summary = {"gate_lufs_within_tolerance_rate": 1.0, "gate_clipping_rate": 0.0}
    result = rhc.evaluate_quality_summary(summary, min_tolerance_rate=0.9, max_clipping_rate=0.0)
    assert result["ok"] is True


def test_evaluate_quality_summary_fails_on_low_tolerance_rate():
    summary = {"gate_lufs_within_tolerance_rate": 0.5, "gate_clipping_rate": 0.0}
    result = rhc.evaluate_quality_summary(summary, min_tolerance_rate=0.9, max_clipping_rate=0.0)
    assert result["ok"] is False
    assert "tolerance rate" in result["failures"][0]


def test_evaluate_quality_summary_any_clipping_is_unconditional_fail():
    """Never trade away true-peak/clipping safety to make a number pass."""
    summary = {"gate_lufs_within_tolerance_rate": 1.0, "gate_clipping_rate": 0.05}
    result = rhc.evaluate_quality_summary(summary, min_tolerance_rate=0.9, max_clipping_rate=0.0)
    assert result["ok"] is False
    assert "clipping" in result["failures"][0]


def test_evaluate_quality_summary_missing_summary_fails_closed():
    result = rhc.evaluate_quality_summary({}, min_tolerance_rate=0.9, max_clipping_rate=0.0)
    assert result["ok"] is False


# --- evaluate_genre_matrix (9/10-style baseline) ----------------------------

def test_evaluate_genre_matrix_passes_at_documented_baseline():
    """The current documented baseline is 9/10 (EDM is a known DSP-depth
    limit, not silently hidden) -- this must pass at the 90% threshold."""
    cases = {f"case_{i}": {"passed": True, "clipping": False} for i in range(9)}
    cases["edm"] = {"passed": False, "clipping": False}
    result = rhc.evaluate_genre_matrix(cases, min_pass_rate=0.9)
    assert result["ok"] is True
    assert result["pass_rate"] == 0.9
    assert result["failed_cases"] == ["edm"]


def test_evaluate_genre_matrix_fails_on_regression_below_baseline():
    """A drop to 7/10 (a real regression, not the known EDM gap alone) must
    fail the gate."""
    cases = {f"case_{i}": {"passed": True, "clipping": False} for i in range(7)}
    cases["edm"] = {"passed": False, "clipping": False}
    cases["jazz"] = {"passed": False, "clipping": False}
    cases["podcast"] = {"passed": False, "clipping": False}
    result = rhc.evaluate_genre_matrix(cases, min_pass_rate=0.9)
    assert result["ok"] is False
    assert result["pass_rate"] == 0.7


def test_evaluate_genre_matrix_clipping_is_unconditional_fail_even_at_high_pass_rate():
    """Even a 9/10 pass rate must fail if any case actually clips -- pass
    rate alone can never paper over a true-peak/clipping safety violation."""
    cases = {f"case_{i}": {"passed": True, "clipping": False} for i in range(9)}
    cases["edm"] = {"passed": True, "clipping": True}
    result = rhc.evaluate_genre_matrix(cases, min_pass_rate=0.9)
    assert result["ok"] is False
    assert any("clipping" in f for f in result["failures"])


def test_evaluate_genre_matrix_empty_fails_closed():
    result = rhc.evaluate_genre_matrix({}, min_pass_rate=0.9)
    assert result["ok"] is False


# --- combine_gate ------------------------------------------------------------

def test_combine_gate_all_pass():
    categories = {
        "a": {"ok": True, "failures": []},
        "b": {"ok": True, "failures": []},
    }
    overall = rhc.combine_gate(categories)
    assert overall["ok"] is True
    assert overall["failures"] == []


def test_combine_gate_one_failure_fails_overall():
    categories = {
        "a": {"ok": True, "failures": []},
        "b": {"ok": False, "failures": ["b broke"]},
    }
    overall = rhc.combine_gate(categories)
    assert overall["ok"] is False
    assert overall["failures"] == ["b broke"]


def test_combine_gate_aggregates_failures_from_all_categories():
    categories = {
        "a": {"ok": False, "failures": ["a broke"]},
        "b": {"ok": False, "failures": ["b broke", "b broke again"]},
        "c": {"ok": True, "failures": []},
    }
    overall = rhc.combine_gate(categories)
    assert overall["ok"] is False
    assert overall["failures"] == ["a broke", "b broke", "b broke again"]


# --- Model dependency integrity (2026-07-11, closes the "silently missing
# model" hole -- see release_health_check.py's own module docstring for the
# real incident this was built in response to) ------------------------------

def test_check_dir_nonempty_fails_when_path_does_not_exist(tmp_path):
    result = rhc._check_dir_nonempty(tmp_path / "does-not-exist")
    assert result["ok"] is False
    assert "does not exist" in result["reason"]


def test_check_dir_nonempty_fails_when_path_is_a_file(tmp_path):
    f = tmp_path / "not-a-dir"
    f.write_text("hello")
    result = rhc._check_dir_nonempty(f)
    assert result["ok"] is False
    assert "not a directory" in result["reason"]


def test_check_dir_nonempty_fails_on_empty_or_near_empty_directory(tmp_path):
    """An empty/near-empty directory (e.g. left by a partial copy) is exactly
    as broken as a missing one and must not pass a bare .exists() check."""
    d = tmp_path / "partial-copy"
    d.mkdir()
    (d / "tiny.txt").write_text("x")
    result = rhc._check_dir_nonempty(d, min_bytes=1024)
    assert result["ok"] is False
    assert "1 bytes" in result["reason"]


def test_check_dir_nonempty_passes_on_a_real_populated_directory(tmp_path):
    d = tmp_path / "real-model"
    d.mkdir()
    (d / "weights.bin").write_bytes(b"x" * 2048)
    result = rhc._check_dir_nonempty(d, min_bytes=1024)
    assert result["ok"] is True
    assert result["total_bytes"] == 2048


def test_check_manifest_artifacts_fails_when_manifest_missing(tmp_path):
    result = rhc._check_manifest_artifacts(tmp_path / "active_manifest.json")
    assert result["ok"] is False
    assert "does not exist" in result["reason"]


def test_check_manifest_artifacts_fails_when_claimed_file_is_missing(tmp_path):
    """Reproduces the real 2026-07-11 AudioGen incident: a manifest claiming
    an artifact is active/promoted while the file itself is gone from disk."""
    import json

    manifest = tmp_path / "active_manifest.json"
    manifest.write_text(json.dumps({
        "artifacts": [{"destination": "chord_markov.pkl"}],
        "stages": {"active": {"artifacts": [{"destination": "stages/active/chord_markov.pkl"}]}},
    }))
    result = rhc._check_manifest_artifacts(manifest)
    assert result["ok"] is False
    assert "chord_markov.pkl" in str(result["missing"])


def test_check_manifest_artifacts_passes_when_all_claimed_files_exist(tmp_path):
    import json

    (tmp_path / "stages" / "active").mkdir(parents=True)
    (tmp_path / "chord_markov.pkl").write_bytes(b"x")
    (tmp_path / "stages" / "active" / "chord_markov.pkl").write_bytes(b"x")
    manifest = tmp_path / "active_manifest.json"
    manifest.write_text(json.dumps({
        "artifacts": [{"destination": "chord_markov.pkl"}],
        "stages": {"active": {"artifacts": [{"destination": "stages/active/chord_markov.pkl"}]}},
    }))
    result = rhc._check_manifest_artifacts(manifest)
    assert result["ok"] is True
    assert result["expected_count"] == 2


def test_evaluate_model_dependencies_passes_when_all_checks_ok():
    checks = {"kenn_lora": {"ok": True}, "kenn_mlx": {"ok": True}}
    result = rhc.evaluate_model_dependencies(checks)
    assert result["ok"] is True
    assert result["failures"] == []


def test_evaluate_model_dependencies_fails_and_names_the_broken_check():
    checks = {
        "kenn_lora": {"ok": True},
        "kenn_mlx": {"ok": False, "reason": "kenn-mlx does not exist"},
    }
    result = rhc.evaluate_model_dependencies(checks)
    assert result["ok"] is False
    assert "kenn_mlx" in result["failures"][0]
    assert "kenn-mlx does not exist" in result["failures"][0]


def test_measure_model_dependencies_against_the_real_restored_repo_state():
    """End-to-end (real filesystem, no mocking): confirms the currently
    restored KENN/AudioGen model artifacts actually pass this check today --
    the exact regression guard this incident needed."""
    checks = rhc.measure_model_dependencies()
    result = rhc.evaluate_model_dependencies(checks)
    assert result["ok"] is True, result["failures"]
