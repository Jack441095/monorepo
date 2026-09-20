#!/usr/bin/env python3
"""
Run a repeatable realtime baseline matrix (init, playback stats, audio quality, profiling).

Examples:
  .venv/bin/python tools/rt_baseline_suite.py
  .venv/bin/python tools/rt_baseline_suite.py --seconds 12 --output-dir .cache/rt_baseline
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from audiogen_core.config_utils import resolve_project_path


def _run_health(
    *,
    performance: str,
    profile: bool,
    seconds: float,
    out_dir: Path,
) -> Dict[str, Any]:
    env = os.environ.copy()
    env["AUDIOGEN_PERF_MODE"] = performance
    env["AUDIOGEN_STARTUP_PROFILE"] = "1" if profile else "0"
    env["AUDIOGEN_RT_PROFILE"] = "1" if profile else "0"
    env["AUDIOGEN_RT_BAR_LOG"] = "1" if profile else "0"
    env["AUDIOGEN_RT_CPROFILE"] = "0"
    env["AUDIOGEN_TEST_SUBPROCESS"] = "1"

    script = _REPO / "tools" / "rt_playback_health_check.py"
    # Inline extended run by importing after patching CONFIG would be heavier; use benchmark for duration.
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(_REPO),
        env=env,
        capture_output=True,
        text=True,
    )
    payload: Dict[str, Any] = {
        "kind": "health_check",
        "performance": performance,
        "profile": profile,
        "returncode": int(proc.returncode),
        "stderr_tail": "\n".join((proc.stderr or "").splitlines()[-40:]),
    }
    try:
        lines = [ln for ln in (proc.stdout or "").splitlines() if ln.strip().startswith("{")]
        if lines:
            payload["report"] = json.loads(lines[-1])
    except Exception as exc:
        payload["parse_error"] = str(exc)
    (out_dir / f"health_{performance}{'_profile' if profile else ''}.json").write_text(
        json.dumps(payload, indent=2, default=str)
    )
    return payload


def _run_benchmark(
    *,
    performance: str,
    seconds: float,
    emotion: str,
    out_dir: Path,
) -> Dict[str, Any]:
    env = os.environ.copy()
    env["AUDIOGEN_TEST_SUBPROCESS"] = "1"
    out_path = out_dir / f"benchmark_{performance}_{emotion}.json"
    cmd = [
        sys.executable,
        str(_REPO / "tools" / "benchmark_realtime_audio.py"),
        "--seconds",
        str(seconds),
        "--emotion",
        emotion,
        "--performance",
        performance,
        "--output",
        str(out_path),
    ]
    proc = subprocess.run(cmd, cwd=str(_REPO), env=env, capture_output=True, text=True)
    payload: Dict[str, Any] = {
        "kind": "benchmark",
        "performance": performance,
        "returncode": int(proc.returncode),
        "output_path": str(out_path),
    }
    if out_path.is_file():
        try:
            payload["report"] = json.loads(out_path.read_text())
        except Exception as exc:
            payload["read_error"] = str(exc)
    if proc.returncode != 0:
        payload["stderr_tail"] = "\n".join((proc.stderr or "").splitlines()[-30:])
    return payload


def _run_profiled_bars(performance: str, bars: int = 6) -> Dict[str, Any]:
    """Headless player loop with per-bar stage timings (no PortAudio required)."""
    from audio.audio_container import AudioContainer
    from audio.RT_player import PolyphonicPlayer
    from composition.engine import CompositionGenerator
    from audiogen_core.config import CONFIG
    from data.music_data import EMOTIONS
    from utils.numba_warmup import warmup_numba_kernels

    os.environ["AUDIOGEN_RT_PROFILE"] = "1"
    os.environ["AUDIOGEN_RT_BAR_LOG"] = "1"
    try:
        CONFIG.audio.rt_render_profile_enabled = True
    except Exception:
        pass

    CONFIG.set_performance_mode(performance)
    CONFIG.audio.target_buffer_bars = 8
    CONFIG.audio.startup_preroll_bars = 2
    try:
        CONFIG.rebuild_samplers()
    except Exception:
        pass
    try:
        warmup_numba_kernels()
    except Exception:
        pass

    gen = CompositionGenerator(enable_perf_monitoring=False)

    class _Adapter:
        def __init__(self, g):
            self.gen = g

        def generate_section_events(self, emotion, root, bars, **kwargs):
            self.gen.runtime_generation_mode = kwargs.get("runtime_mode", "normal")
            return self.gen.generate_section(
                emotion,
                root,
                bars,
                target_notes_per_bar=kwargs.get("target_notes_per_bar", 6.0),
                section_index=int(kwargs.get("section_index", 0) or 0),
            )

    container = AudioContainer.create_from_config(CONFIG)
    player = PolyphonicPlayer(_Adapter(gen), CONFIG, container=container)
    renderer = player.renderer

    stage_sums = {"mono": 0.0, "chords": 0.0, "mix": 0.0, "master": 0.0, "total": 0.0}
    gen_ms: List[float] = []
    tiers: List[str] = []

    t0 = time.perf_counter()
    try:
        player.start()
        player.load_emotion(0 if EMOTIONS else 0, 60)
        deadline = time.perf_counter() + max(4.0, float(bars) * 3.5)
        seen = 0
        while time.perf_counter() < deadline and seen < int(bars):
            time.sleep(0.15)
            st = renderer.last_stage_timing_ms or {}
            if float(st.get("total", 0.0) or 0.0) <= 0.0:
                continue
            seen += 1
            for k in stage_sums:
                stage_sums[k] += float(st.get(k, 0.0) or 0.0)
            stats = player.get_stats()
            gen_ms.append(float(stats.get("last_gen_time_ms", 0.0) or 0.0))
            tiers.append(str(stats.get("quality_tier", "")))
    finally:
        player.stop()

    n = max(1, seen)
    avg_stages = {k: round(stage_sums[k] / n, 3) for k in stage_sums}
    return {
        "kind": "profiled_bars",
        "performance": performance,
        "bars_sampled": int(seen),
        "wall_seconds": round(time.perf_counter() - t0, 3),
        "avg_stage_ms": avg_stages,
        "avg_gen_ms": round(sum(gen_ms) / max(1, len(gen_ms)), 2) if gen_ms else 0.0,
        "max_gen_ms": round(max(gen_ms), 2) if gen_ms else 0.0,
        "quality_tiers_seen": sorted(set(t for t in tiers if t)),
        "final_stats": player.get_stats(),
        "audio_config": {
            "sample_rate": int(getattr(CONFIG.audio, "sample_rate", 0) or 0),
            "buffer_size": int(getattr(CONFIG.audio, "buffer_size", 0) or 0),
            "reverb_rt60": float(getattr(CONFIG.audio, "reverb_rt60", 0.0) or 0.0),
            "reverb_wet": float(getattr(CONFIG.audio, "reverb_wet", 0.0) or 0.0),
            "delay_bus_enabled": bool(getattr(CONFIG.audio, "delay_bus_enabled", False)),
        },
    }


def _summarize(matrix: List[Dict[str, Any]]) -> Dict[str, Any]:
    summary: Dict[str, Any] = {"runs": len(matrix), "by_performance": {}}
    for row in matrix:
        perf = str(row.get("performance") or row.get("report", {}).get("performance") or "unknown")
        bucket = summary["by_performance"].setdefault(perf, [])
        bucket.append(row)
    return summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=12.0, help="Benchmark playback duration per mode")
    ap.add_argument("--emotion", default="neutral")
    ap.add_argument("--output-dir", default=".cache/rt_baseline")
    ap.add_argument("--skip-profile-bars", action="store_true")
    args = ap.parse_args()

    out_dir = resolve_project_path(str(args.output_dir))
    out_dir.mkdir(parents=True, exist_ok=True)

    matrix: List[Dict[str, Any]] = []
    for perf in ("low", "high"):
        matrix.append(_run_health(performance=perf, profile=False, seconds=float(args.seconds), out_dir=out_dir))
        matrix.append(
            _run_benchmark(
                performance=perf,
                seconds=float(args.seconds),
                emotion=str(args.emotion),
                out_dir=out_dir,
            )
        )
        if not args.skip_profile_bars:
            try:
                matrix.append(_run_profiled_bars(perf, bars=8))
            except Exception as exc:
                matrix.append(
                    {
                        "kind": "profiled_bars",
                        "performance": perf,
                        "error": str(exc),
                    }
                )

    matrix.append(_run_health(performance="low", profile=True, seconds=float(args.seconds), out_dir=out_dir))

    summary = _summarize(matrix)
    summary_path = out_dir / "baseline_summary.json"
    summary_path.write_text(json.dumps({"matrix": matrix, "summary": summary}, indent=2, default=str))
    print(json.dumps(summary, indent=2, default=str))
    print(f"\nWrote {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
