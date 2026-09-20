#!/usr/bin/env python3
"""
Full realtime audit: health check, baseline matrix, pytest RT subset, summary JSON.

  .venv/bin/python tools/rt_full_audit.py
  .venv/bin/python tools/rt_full_audit.py --output-dir .cache/rt_full_audit
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from audiogen_core.config_utils import resolve_project_path


def _run(cmd: List[str], *, env: Dict[str, str] | None = None) -> Dict[str, Any]:
    proc = subprocess.run(
        cmd,
        cwd=str(_REPO),
        env=env,
        capture_output=True,
        text=True,
    )
    return {
        "cmd": cmd,
        "returncode": int(proc.returncode),
        "stdout_tail": "\n".join((proc.stdout or "").splitlines()[-25:]),
        "stderr_tail": "\n".join((proc.stderr or "").splitlines()[-25:]),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output-dir", default=".cache/rt_full_audit")
    ap.add_argument("--benchmark-seconds", type=float, default=12.0)
    ap.add_argument("--skip-pytest", action="store_true")
    ap.add_argument("--skip-slow-pytest", action="store_true")
    ap.add_argument("--run-fx-ab", action="store_true", help="Run tools/rt_fx_ab_compare.py into output-dir/fx_ab")
    args = ap.parse_args()

    out_dir = resolve_project_path(str(args.output_dir))
    out_dir.mkdir(parents=True, exist_ok=True)
    py = str(_REPO / ".venv" / "bin" / "python")
    if not Path(py).is_file():
        py = sys.executable

    report: Dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "repo": str(_REPO),
        "python": py,
        "steps": [],
    }

    env_base = os.environ.copy()
    env_base["AUDIOGEN_TEST_SUBPROCESS"] = "1"

    # 1) Fast pytest subset (CI-aligned)
    if not args.skip_pytest:
        t0 = time.perf_counter()
        fast = _run(
            [py, "-m", "pytest", "tests", "-q", "-m", "not slow", "--tb=line"],
            env=env_base,
        )
        fast["elapsed_s"] = round(time.perf_counter() - t0, 2)
        report["steps"].append({"name": "pytest_not_slow", **fast})

    # 2) Song upgrade + snapshots
    t0 = time.perf_counter()
    targeted = _run(
        [
            py,
            "-m",
            "pytest",
            "tests/test_song_upgrade_profile.py",
            "tests/test_section_generation_snapshots.py",
            "tests/test_global_reverb_return.py",
            "tests/test_rt_performance_health.py::TestPlaybackStatsSchema::test_get_stats_includes_latency_and_underrun_fields",
            "-q",
            "--tb=line",
        ],
        env=env_base,
    )
    targeted["elapsed_s"] = round(time.perf_counter() - t0, 2)
    report["steps"].append({"name": "pytest_rt_targeted", **targeted})

    # 3) Baseline suite (low + high)
    t0 = time.perf_counter()
    baseline_cmd = [
        py,
        str(_REPO / "tools" / "rt_baseline_suite.py"),
        "--seconds",
        str(float(args.benchmark_seconds)),
        "--output-dir",
        str(out_dir / "baseline"),
        "--skip-profile-bars",
    ]
    baseline = _run(baseline_cmd, env=env_base)
    baseline["elapsed_s"] = round(time.perf_counter() - t0, 2)
    report["steps"].append({"name": "rt_baseline_suite", **baseline})
    summary_path = out_dir / "baseline" / "baseline_summary.json"
    if summary_path.is_file():
        try:
            report["baseline"] = json.loads(summary_path.read_text())
        except Exception as exc:
            report["baseline_error"] = str(exc)

    # 4) Health check with profiling (high perf)
    env_prof = dict(env_base)
    env_prof["AUDIOGEN_PERF_MODE"] = "high"
    env_prof["AUDIOGEN_STARTUP_PROFILE"] = "1"
    env_prof["AUDIOGEN_RT_PROFILE"] = "1"
    t0 = time.perf_counter()
    health = _run([py, str(_REPO / "tools" / "rt_playback_health_check.py")], env=env_prof)
    health["elapsed_s"] = round(time.perf_counter() - t0, 2)
    report["steps"].append({"name": "rt_playback_health_high", **health})

    if args.run_fx_ab:
        t0 = time.perf_counter()
        fx_ab = _run(
            [
                py,
                str(_REPO / "tools" / "rt_fx_ab_compare.py"),
                "--output-dir",
                str(out_dir / "fx_ab"),
            ],
            env=env_base,
        )
        fx_ab["elapsed_s"] = round(time.perf_counter() - t0, 2)
        report["steps"].append({"name": "rt_fx_ab_compare", **fx_ab})
        fx_summary = out_dir / "fx_ab" / "fx_ab_summary.json"
        if fx_summary.is_file():
            try:
                report["fx_ab"] = json.loads(fx_summary.read_text())
            except Exception as exc:
                report["fx_ab_error"] = str(exc)

    # 5) Slow pytest (isolated subprocess per test — can take several minutes)
    if not args.skip_slow_pytest:
        t0 = time.perf_counter()
        slow = _run(
            [py, "-m", "pytest", "tests", "-q", "-m", "slow", "--tb=line"],
            env=env_base,
        )
        slow["elapsed_s"] = round(time.perf_counter() - t0, 2)
        report["steps"].append({"name": "pytest_slow", **slow})

    ok = all(int(s.get("returncode", 1)) == 0 for s in report["steps"])
    report["ok"] = bool(ok)

    out_path = out_dir / "full_audit_report.json"
    out_path.write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps({"ok": ok, "report": str(out_path)}, indent=2))
    if report.get("baseline"):
        print("\n--- baseline summary (by_performance) ---")
        for perf, rows in (report["baseline"].get("summary", {}) or {}).get("by_performance", {}).items():
            for row in rows:
                if row.get("kind") == "benchmark" and row.get("report"):
                    r = row["report"]
                    st = (r.get("playback_stats") or {})
                    stage = r.get("stage_summary") or {}
                    print(
                        f"{perf}: tier={r.get('quality_tier')} "
                        f"last_gen_ms={st.get('last_gen_time_ms')} "
                        f"max_gen_ms={st.get('max_gen_time_ms')} "
                        f"culprit={st.get('gen_culprit')} "
                        f"dominant_stage={stage.get('dominant_stage')} "
                        f"max_ratio={stage.get('render_ratio_max')} "
                        f"underruns={r.get('buffer_underruns')}"
                    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
