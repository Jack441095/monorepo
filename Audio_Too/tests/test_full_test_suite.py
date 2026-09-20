from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "eval"))

import full_test_suite  # noqa: E402


def test_skip_budget_accepts_only_approved_reasons_within_caps() -> None:
    output = """SKIPPED [3] tests/live.py:10: Ollama not available
SKIPPED [2] tests/index.py:20: KENN index not built — run build first
10 passed, 5 skipped in 1.00s
"""

    report = full_test_suite.evaluate_pytest_skip_budget(
        output, {"Ollama not available": 3, "KENN index not built": 2}
    )

    assert report["ok"] is True
    assert report["reported_total"] == 5


def test_skip_budget_rejects_unknown_reason_even_when_total_is_small() -> None:
    output = """SKIPPED [1] tests/new.py:10: optional package silently missing
10 passed, 1 skipped in 1.00s
"""

    report = full_test_suite.evaluate_pytest_skip_budget(
        output, {"Ollama not available": 6}
    )

    assert report["ok"] is False
    assert "unapproved skip reasons" in report["failures"][0]


def test_skip_budget_rejects_growth_for_an_approved_reason() -> None:
    output = """SKIPPED [7] tests/live.py:10: Ollama not available
10 passed, 7 skipped in 1.00s
"""

    report = full_test_suite.evaluate_pytest_skip_budget(
        output, {"Ollama not available": 6}
    )

    assert report["ok"] is False
    assert "7 > 6" in report["failures"][0]


def test_skip_budget_requires_complete_reason_details() -> None:
    report = full_test_suite.evaluate_pytest_skip_budget(
        "10 passed, 2 skipped in 1.00s\n", {"Ollama not available": 6}
    )

    assert report["ok"] is False
    assert "reasons are incomplete" in report["failures"][0]


@pytest.mark.skipif(os.name != "posix", reason="process-group cleanup is POSIX-specific")
def test_run_check_timeout_kills_spawned_children(tmp_path: Path) -> None:
    marker = tmp_path / "child-survived"
    child = (
        "import pathlib,time; time.sleep(0.5); "
        f"pathlib.Path({str(marker)!r}).write_text('leaked')"
    )
    parent = (
        "import subprocess,sys,time; "
        f"subprocess.Popen([sys.executable, '-c', {child!r}]); time.sleep(5)"
    )

    result = full_test_suite.run_check(
        "timeout-cleanup", [sys.executable, "-c", parent], timeout=0.1
    )
    time.sleep(0.7)

    assert result.status == "fail"
    assert result.returncode == 124
    assert not marker.exists()


def test_markdown_report_includes_status_and_failure_log() -> None:
    payload = {
        "created_at": "2026-07-01T00:00:00+00:00",
        "status": "fail",
        "duration_seconds": 1.5,
        "environment": {
            "root_python": "python 3.12",
            "native_python": "python 3.13",
            "platform": "macOS",
        },
        "results": [
            {
                "name": "core-tests",
                "status": "fail",
                "duration_seconds": 1.0,
                "summary": "one failed",
                "log": "assertion failed",
            }
        ],
    }

    report = full_test_suite.report_markdown(payload)

    assert "Overall: **FAIL**" in report
    assert "core-tests" in report
    assert "assertion failed" in report


def test_batched_native_tests_recover_from_batch_only_failure(tmp_path, monkeypatch) -> None:
    files = [tmp_path / "test_one.py", tmp_path / "test_two.py"]
    for path in files:
        path.write_text("def test_ok(): assert True\n", encoding="utf-8")

    def fake_run(name, command, *, timeout, env=None):
        status = "fail" if "batch" in name else "pass"
        return full_test_suite.CheckResult(
            name=name,
            status=status,
            duration_seconds=0.01,
            command=command,
            returncode=1 if status == "fail" else 0,
            summary=status,
        )

    monkeypatch.setattr(full_test_suite, "ROOT", tmp_path)
    monkeypatch.setattr(full_test_suite, "run_check", fake_run)

    result = full_test_suite.run_pytest_batches(
        "native", [sys.executable], files, batch_size=2, timeout=30
    )

    assert result.status == "pass"
    assert "passed in file isolation" in result.summary


def test_known_failures_accepts_the_specific_expected_case_only(tmp_path, monkeypatch) -> None:
    """Regression for the 2026-07-11 P0-14 decision: a known, already-evidenced
    gap (EDM's crest-factor DSP-depth limit) shouldn't permanently block this
    gate, but a *different* failure in the same file -- a real regression --
    must still fail it. Covers both branches with one known_failures config."""
    files = [tmp_path / "test_genre_matrix.py", tmp_path / "test_other.py"]
    for path in files:
        path.write_text("def test_ok(): assert True\n", encoding="utf-8")

    def fake_run(name, command, *, timeout, env=None):
        if "batch" in name:
            return full_test_suite.CheckResult(
                name=name, status="fail", duration_seconds=0.01, command=command, returncode=1, summary="fail"
            )
        if name.endswith("test_genre_matrix.py"):
            return full_test_suite.CheckResult(
                name=name, status="fail", duration_seconds=0.01, command=command, returncode=1,
                summary="1 failed", log="FAILED test_genre_matrix.py::test_genre_loudness_profile_matrix[edm]",
            )
        return full_test_suite.CheckResult(
            name=name, status="pass", duration_seconds=0.01, command=command, returncode=0, summary="pass"
        )

    monkeypatch.setattr(full_test_suite, "ROOT", tmp_path)
    monkeypatch.setattr(full_test_suite, "run_check", fake_run)

    result = full_test_suite.run_pytest_batches(
        "audio-analysis-tests", [sys.executable], files, batch_size=2, timeout=30,
        known_failures={"test_genre_matrix.py": "edm"},
    )

    assert result.status == "pass"
    assert "known accepted failure" in result.summary
    assert "edm" in result.summary


def test_known_failures_still_fails_on_a_different_case_in_the_same_file(tmp_path, monkeypatch) -> None:
    files = [tmp_path / "test_genre_matrix.py"]
    files[0].write_text("def test_ok(): assert True\n", encoding="utf-8")

    def fake_run(name, command, *, timeout, env=None):
        if "batch" in name:
            return full_test_suite.CheckResult(
                name=name, status="fail", duration_seconds=0.01, command=command, returncode=1, summary="fail"
            )
        # A *different* case (jazz) fails -- not the known/accepted edm case.
        return full_test_suite.CheckResult(
            name=name, status="fail", duration_seconds=0.01, command=command, returncode=1,
            summary="1 failed", log="FAILED test_genre_matrix.py::test_genre_loudness_profile_matrix[jazz]",
        )

    monkeypatch.setattr(full_test_suite, "ROOT", tmp_path)
    monkeypatch.setattr(full_test_suite, "run_check", fake_run)

    result = full_test_suite.run_pytest_batches(
        "audio-analysis-tests", [sys.executable], files, batch_size=2, timeout=30,
        known_failures={"test_genre_matrix.py": "edm"},
    )

    assert result.status == "fail"
    assert "failing files" in result.summary
