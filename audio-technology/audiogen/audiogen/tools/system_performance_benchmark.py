#!/usr/bin/env python3
"""
Whole-system performance benchmark (local).

This orchestrates:
- Offline composition wall times (section + arranged song)
- Realtime bar/stage profiling (via tools/benchmark_realtime_audio.py)
- Optional DSP micro-benchmark gates (mixer/master scripts)

Example:
  .venv/bin/python tools/system_performance_benchmark.py --gate
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
from typing import Any, Dict, List, Optional

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from audiogen_core.config_utils import resolve_project_path


def _float_env(name: str, default: float) -> float:
    raw = str(os.environ.get(name, "") or "").strip()
    if not raw:
        return float(default)
    try:
        return float(raw)
    except Exception:
        return float(default)


def _int_env(name: str, default: int) -> int:
    raw = str(os.environ.get(name, "") or "").strip()
    if not raw:
        return int(default)
    try:
        return int(raw)
    except Exception:
        return int(default)


def _tail(text: str, *, max_lines: int = 30) -> str:
    lines = (text or "").splitlines()
    return "\n".join(lines[-max_lines:])


def _run_subprocess(cmd: List[str]) -> Dict[str, Any]:
    proc = subprocess.run(
        cmd,
        cwd=str(_REPO),
        text=True,
        capture_output=True,
        env=os.environ.copy(),
    )
    return {
        "cmd": list(cmd),
        "returncode": int(proc.returncode),
        "stdout_tail": _tail(proc.stdout),
        "stderr_tail": _tail(proc.stderr),
    }


def _evaluate_offline_caps(
    offline: Dict[str, Any],
    *,
    max_section_ms: float,
    max_song_ms: float,
) -> Dict[str, Any]:
    failures: List[str] = []
    section_ms = float(((offline.get("section_8bar") or {}).get("wall_ms", 0.0)) or 0.0)
    song_ms = float(((offline.get("arranged_song_ambient") or {}).get("wall_ms", 0.0)) or 0.0)
    if float(max_section_ms) > 0.0 and section_ms > float(max_section_ms):
        failures.append(f"offline section wall_ms {section_ms:.2f} > allowed {float(max_section_ms):.2f}")
    if float(max_song_ms) > 0.0 and song_ms > float(max_song_ms):
        failures.append(f"offline arranged song wall_ms {song_ms:.2f} > allowed {float(max_song_ms):.2f}")
    return {"ok": not failures, "failures": failures}


def _evaluate_underruns(rt_report: Dict[str, Any], *, max_underruns: int) -> Dict[str, Any]:
    failures: List[str] = []
    stats = dict(rt_report.get("playback_stats") or {})
    underruns = int(stats.get("buffer_underruns", rt_report.get("buffer_underruns", 0)) or 0)
    if int(max_underruns) >= 0 and underruns > int(max_underruns):
        failures.append(f"buffer underruns {underruns} > allowed {int(max_underruns)}")
    return {"ok": not failures, "failures": failures}


def _write_summary(out_dir: Path, report: Dict[str, Any]) -> str:
    offline = dict(report.get("offline_composition") or {})
    rt = dict(report.get("rt_benchmark") or {})
    rt_sum = dict(rt.get("stage_gate_summary") or rt.get("stage_summary") or {})
    stage_gate = dict(rt.get("stage_gate") or {})
    cold_gate = dict(rt.get("cold_start_gate") or {})
    offline_gate = dict(report.get("offline_gate") or {})
    underrun_gate = dict(report.get("underrun_gate") or {})
    dsp = dict(report.get("dsp") or {})
    dsp_ok = bool(dsp.get("ok", True))

    lines = []
    lines.append("System performance benchmark")
    lines.append(f"timestamp_utc: {report.get('timestamp_utc')}")
    lines.append(f"ok: {report.get('ok')}")
    lines.append("")
    lines.append("Offline:")
    lines.append(f"- section_8bar.wall_ms: {(offline.get('section_8bar') or {}).get('wall_ms')}")
    lines.append(f"- arranged_song_ambient.wall_ms: {(offline.get('arranged_song_ambient') or {}).get('wall_ms')}")
    if not offline_gate.get("ok", True):
        lines.append(f"- offline_gate_failures: {offline_gate.get('failures')}")
    lines.append("")
    lines.append("Realtime:")
    lines.append(f"- bars_profiled: {rt_sum.get('bars_profiled')}")
    lines.append(f"- render_ratio_max: {rt_sum.get('render_ratio_max')}")
    lines.append(f"- render_ratio_p95: {rt_sum.get('render_ratio_p95')}")
    lines.append(f"- total_p95_ms: {rt_sum.get('total_p95_ms')}")
    lines.append(f"- master_p95_ms: {(rt_sum.get('stage_p95_ms') or {}).get('master')}")
    lines.append(f"- spike_bars: {rt_sum.get('spike_bars')}")
    lines.append(f"- chord_cache_delta_max: {rt_sum.get('chord_cache_delta_max')}")
    lines.append(f"- over_budget_bars: {rt_sum.get('over_budget_bars')}")
    if not stage_gate.get("ok", True):
        lines.append(f"- stage_gate_failures: {stage_gate.get('failures')}")
    if not cold_gate.get("ok", True):
        lines.append(f"- cold_start_gate_failures: {cold_gate.get('failures')}")
    if not underrun_gate.get("ok", True):
        lines.append(f"- underrun_gate_failures: {underrun_gate.get('failures')}")
    lines.append("")
    lines.append(f"DSP included: {bool(dsp.get('included', False))} (ok={dsp_ok})")
    if bool(dsp.get("included", False)) and not dsp_ok:
        lines.append(f"- dsp_failures: {dsp.get('failures')}")

    path = out_dir / "summary.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Local whole-system performance benchmark.")
    ap.add_argument("--output-dir", default=".cache/system_performance_benchmark")
    ap.add_argument("--emotion", default="neutral")
    ap.add_argument("--root", type=int, default=60)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--performance", choices=("low", "high", "balanced", "quality", "maximum"), default="low")
    ap.add_argument("--rt-seconds", type=float, default=8.0)
    ap.add_argument("--gate", action="store_true", help="Exit non-zero when enabled thresholds fail.")
    ap.add_argument("--include-dsp", action="store_true", help="Run mixer/master DSP scripts and attach results.")
    args = ap.parse_args(argv)

    # Generous local defaults; override via env vars.
    max_section_ms = _float_env("SYS_BENCH_MAX_SECTION_MS", 120_000.0)
    max_song_ms = _float_env("SYS_BENCH_MAX_SONG_MS", 180_000.0)
    max_render_ratio = _float_env("SYS_BENCH_MAX_RENDER_RATIO", 0.85)
    max_over_budget_bars = _int_env("SYS_BENCH_MAX_OVER_BUDGET_BARS", 0)
    max_underruns = _int_env("SYS_BENCH_MAX_UNDERRUNS", 0)
    min_profiled_bars = _int_env("SYS_BENCH_MIN_PROFILED_BARS", 1)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = resolve_project_path(str(args.output_dir)) / f"run_{timestamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    from tools.benchmark_realtime_audio import run_realtime_benchmark
    from tools.system_full_audit import audit_config_snapshot, audit_offline_composition

    report: Dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "repo": str(_REPO),
        "config": audit_config_snapshot(),
        "args": {
            "emotion": str(args.emotion),
            "root": int(args.root),
            "seed": int(args.seed),
            "performance": str(args.performance),
            "rt_seconds": float(args.rt_seconds),
            "gate": bool(args.gate),
            "include_dsp": bool(args.include_dsp),
        },
        "thresholds": {
            "SYS_BENCH_MAX_SECTION_MS": float(max_section_ms),
            "SYS_BENCH_MAX_SONG_MS": float(max_song_ms),
            "SYS_BENCH_MAX_RENDER_RATIO": float(max_render_ratio),
            "SYS_BENCH_MAX_OVER_BUDGET_BARS": int(max_over_budget_bars),
            "SYS_BENCH_MAX_UNDERRUNS": int(max_underruns),
            "SYS_BENCH_MIN_PROFILED_BARS": int(min_profiled_bars),
        },
    }

    # Offline timing
    t0 = time.perf_counter()
    offline = audit_offline_composition(emotion_name=str(args.emotion), root=int(args.root), seed=int(args.seed))
    report["offline_composition"] = offline
    report["offline_elapsed_s"] = round(time.perf_counter() - t0, 2)
    report["offline_gate"] = _evaluate_offline_caps(
        offline,
        max_section_ms=float(max_section_ms),
        max_song_ms=float(max_song_ms),
    )

    # Realtime benchmark (stage profile + optional gate data)
    rt = run_realtime_benchmark(
        seconds=float(args.rt_seconds),
        emotion=str(args.emotion),
        root=int(args.root),
        performance=str(args.performance),
        max_render_ratio=float(max_render_ratio),
        max_over_budget_bars=int(max_over_budget_bars),
        min_profiled_bars=int(min_profiled_bars),
        gate_warmup_bars=1,
        max_cold_start_ms=0.0,
    )
    report["rt_benchmark"] = rt
    report["underrun_gate"] = _evaluate_underruns(rt, max_underruns=int(max_underruns))

    # Optional DSP scripts
    dsp: Dict[str, Any] = {"included": bool(args.include_dsp), "ok": True, "steps": [], "failures": []}
    if bool(args.include_dsp):
        steps = [
            ["bash", str(_REPO / "scripts" / "run_mixer_dsp_gate.sh")],
            ["bash", str(_REPO / "scripts" / "run_master_bus_dsp_gate.sh")],
        ]
        for cmd in steps:
            dsp["steps"].append(_run_subprocess(cmd))
        failures = [s for s in (dsp.get("steps") or []) if int(s.get("returncode", 0)) != 0]
        if failures:
            dsp["ok"] = False
            dsp["failures"] = [
                {"cmd": f.get("cmd"), "returncode": f.get("returncode"), "stderr_tail": f.get("stderr_tail")}
                for f in failures
            ]
    report["dsp"] = dsp

    gates_ok = bool((rt.get("stage_gate") or {}).get("ok", True)) and bool((rt.get("cold_start_gate") or {}).get("ok", True))
    ok = bool(report["offline_gate"]["ok"]) and bool(gates_ok) and bool(report["underrun_gate"]["ok"]) and bool(dsp.get("ok", True))
    report["ok"] = bool(ok)

    report_path = out_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    summary_path = _write_summary(out_dir, report)

    print(
        json.dumps(
            {
                "ok": bool(report["ok"]),
                "report": str(report_path),
                "summary": str(summary_path),
            },
            indent=2,
            sort_keys=True,
        )
    )

    if bool(args.gate) and not bool(report["ok"]):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
