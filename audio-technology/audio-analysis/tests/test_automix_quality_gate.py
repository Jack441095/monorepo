"""AutoMix output-quality gate, as a pytest check (audit fix Stage 1, 2026-07-08).

docs/AUTOMIX_CODEBASE_AUDIT_2026-07-08.md P0: the quality benchmark
(scripts/eval/automix_quality_benchmark.py) was a standalone script nothing called
-- a future regression in the limiter/validator chain (the exact clipping bug fixed
same day) could ship silently again. This wraps its verdict as a real test, and it's
also wired into scripts/eval/full_test_suite.py's automix-quality-gate check and
`main.py automix-quality-gate`.

This is slower than a typical unit test (runs the full render/validate chain across
2 stem profiles x 5 genres x 3 loudness targets) -- marked so it can be skipped from
a fast local loop if needed, but it must run in CI / the full release suite.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "scripts" / "eval" / "automix_quality_benchmark.py"


@pytest.mark.slow
def test_automix_quality_gate_passes() -> None:
    # timeout=480 (set 2026-07-08, never revisited) started failing this test
    # with a subprocess.TimeoutExpired on 2026-07-18 -- confirmed via a direct
    # run that the benchmark isn't hung, it's just genuinely ~45s/combo now
    # (30 combos => ~1350s needed) after per-render overhead grew across the
    # pipeline since this budget was set. Not a regression from any single
    # change; raised with real headroom instead of chasing the exact cause.
    result = subprocess.run(
        [sys.executable, str(BENCHMARK)],
        capture_output=True,
        text=True,
        timeout=1800,
        cwd=ROOT,
    )
    assert result.returncode == 0, (
        "AutoMix quality gate failed (limiter/LUFS regression?):\n"
        + result.stdout[-3000:] + result.stderr[-1000:]
    )
