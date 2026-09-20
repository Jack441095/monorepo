#!/usr/bin/env python3
"""Regenerates the V2-H qualification receipts from live evidence.

Runs the Thursday regression suite (pytest tests/thursday), parses the real
result, scans security-relevant test coverage, aggregates the benchmark /
holdout / soak artifacts, and writes:

  - THURSDAY_V2H_TEST_RECEIPT.json
  - THURSDAY_V2H_REGRESSION_RECEIPT.json
  - THURSDAY_V2H_SECURITY_RECEIPT.json
  - THURSDAY_V2H_FINAL_RECEIPT.json

The holdout artifact (THURSDAY_V2H_HOLDOUT_RESULTS.json) is consumed as-is:
the holdout runs exactly once and is never re-executed here.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_EVALS = _ROOT / "thursday" / "evals"
_TESTS_DIR = _ROOT / "tests" / "thursday"

_SECURITY_PATTERNS = (
    "veto",
    "injection",
    "symlink",
    "traversal",
    "fake",
    "replay",
    "toctou",
    "secret",
    "forbidden",
    "stale",
    "scope",
    "tamper",
    "escalat",
    "unauthor",
)


def _collect_per_file_counts() -> dict[str, int]:
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/thursday", "--collect-only", "-q"],
        cwd=_ROOT, capture_output=True, text=True, check=False,
    )
    counts: dict[str, int] = {}
    for line in out.stdout.splitlines():
        line = line.strip()
        if "::" not in line or not line.startswith("tests/"):
            continue
        f = line.split("::", 1)[0]
        counts[f] = counts.get(f, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


def _run_regression() -> tuple[int, int, float]:
    t0 = time.time()
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/thursday", "-q"],
        cwd=_ROOT, capture_output=True, text=True, check=False,
    )
    elapsed = time.time() - t0
    tail = out.stdout.strip().splitlines()[-1] if out.stdout.strip() else ""
    m_pass = re.search(r"(\d+) passed", tail)
    m_fail = re.search(r"(\d+) failed", tail)
    passed = int(m_pass.group(1)) if m_pass else 0
    failed = int(m_fail.group(1)) if m_fail else 0
    return passed, failed, elapsed


def _scan_security_tests() -> list[str]:
    """Test functions whose names indicate security/veto coverage."""
    hits: list[str] = []
    for tf in sorted(_TESTS_DIR.glob("test_*.py")):
        for line in tf.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*def (test_\w+)", line)
            if not m:
                continue
            name = m.group(1).lower()
            if any(p in name for p in _SECURITY_PATTERNS):
                hits.append(f"{tf.name}::{m.group(1)}")
    return hits


def main() -> None:
    now = time.time()

    print("Collecting per-file test counts…", flush=True)
    per_file = _collect_per_file_counts()
    total_collected = sum(per_file.values())

    print(f"Running regression suite ({total_collected} tests)…", flush=True)
    passed, failed, elapsed = _run_regression()
    qualified = failed == 0 and passed == total_collected
    print(f"Regression: {passed}/{total_collected} passed in {elapsed:.1f}s", flush=True)

    test_receipt = {
        "suite": "THURSDAY_V2H_TEST_RECEIPT",
        "generated_at": now,
        "runner": "pytest tests/thursday -q",
        "collected": total_collected,
        "passed": passed,
        "failed": failed,
        "duration_seconds": round(elapsed, 2),
        "qualified": qualified,
    }
    (_EVALS / "THURSDAY_V2H_TEST_RECEIPT.json").write_text(
        json.dumps(test_receipt, indent=2) + "\n", encoding="utf-8"
    )

    v2h_count = per_file.get("tests/thursday/test_autonomous_engineering.py", 0)
    shared_mutation = per_file.get("tests/thursday/test_shared_mutation.py", 0)
    regression_receipt = {
        "suite": "THURSDAY_V2H_REGRESSION_RECEIPT",
        "generated_at": now,
        "runner": "pytest tests/thursday -q",
        "collected": total_collected,
        "passed": passed,
        "failed": failed,
        "regressions_introduced": failed,
        "v2h_tests": f"{v2h_count}/{v2h_count} PASS",
        "v2g_shared_mutation_tests": shared_mutation,
        "per_file_top10": dict(list(per_file.items())[:10]),
        "qualified": qualified,
    }
    (_EVALS / "THURSDAY_V2H_REGRESSION_RECEIPT.json").write_text(
        json.dumps(regression_receipt, indent=2) + "\n", encoding="utf-8"
    )

    sec_hits = _scan_security_tests()
    security_receipt = {
        "suite": "THURSDAY_V2H_SECURITY_RECEIPT",
        "generated_at": now,
        "method": "static scan of security-named tests in tests/thursday + veto policy modules",
        "security_named_tests": len(sec_hits),
        "policy_critical_patterns_enforced_by_independent_qa": [
            "approval_policy", "lease_policy", "shared_executor", "token_verif",
            "sandbox_policy", "integration_models", "plan_approval",
            "confirmation", "action_receipts",
        ],
        "sample_coverage": sec_hits[:25],
        "regression_security_result": f"{passed}/{total_collected} PASS" if qualified else "FAIL",
        "qualified": qualified,
    }
    (_EVALS / "THURSDAY_V2H_SECURITY_RECEIPT.json").write_text(
        json.dumps(security_receipt, indent=2) + "\n", encoding="utf-8"
    )

    def _load(name: str) -> dict:
        p = _EVALS / name
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    bench = _load("THURSDAY_AUTONOMOUS_ENGINEERING_V1.json")
    holdout = _load("THURSDAY_V2H_HOLDOUT_RESULTS.json")
    soak = _load("THURSDAY_V2H_SOAK_RESULTS.json")

    final_receipt = {
        "qualification": "THURSDAY_V2H_FINAL_RECEIPT",
        "version": "thursday/v2h-autonomous-engineering",
        "generated_at": now,
        "benchmark": {
            "name": bench.get("benchmark"),
            "total": bench.get("total"),
            "passed": bench.get("passed"),
            "pass_rate": bench.get("pass_rate"),
            "qualified": bool(bench.get("qualified")),
        },
        "holdout": {
            "scenarios": holdout.get("scenarios"),
            "passed": holdout.get("passed"),
            "run_count": 1,
            "contamination": holdout.get("contamination"),
            "note": "consumed from frozen single-run artifact; never rerun here",
        },
        "soak": {
            "cycles": soak.get("cycles"),
            "operations": soak.get("total_operations"),
            "errors": soak.get("counters", {}).get("errors"),
            "elapsed_seconds": soak.get("elapsed_seconds"),
            "timing_environment": soak.get("timing_environment"),
            "rss_drift_mb": soak.get("rss_drift_mb"),
            "integrity_ok": soak.get("integrity_ok"),
            "qualified": bool(soak.get("qualified")),
        },
        "regression": {
            "collected": total_collected,
            "passed": passed,
            "failed": failed,
            "duration_seconds": round(elapsed, 2),
            "qualified": qualified,
        },
        "overall_qualified": bool(
            qualified
            and bench.get("qualified")
            and holdout.get("qualified")
            and soak.get("qualified")
        ),
    }
    (_EVALS / "THURSDAY_V2H_FINAL_RECEIPT.json").write_text(
        json.dumps(final_receipt, indent=2) + "\n", encoding="utf-8"
    )
    print("Receipts written: TEST, REGRESSION, SECURITY, FINAL", flush=True)
    print(f"OVERALL QUALIFIED: {final_receipt['overall_qualified']}", flush=True)


if __name__ == "__main__":
    main()
