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

from benchmark_audio_analysis import run


def test_benchmark_is_qualified() -> None:
    result = run(long_seconds=2.0, workers=2)
    assert result["qualified"] is True, result
    assert all(case["ok"] and case["within_input_limit"] for case in result["cases"])
    assert result["concurrency"]["all_ok"] and result["concurrency"]["all_complete"]
