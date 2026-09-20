#!/usr/bin/env python3
"""Benchmark MasterBus return FX and mastering DSP costs."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from audiogen_core.config_utils import resolve_project_path  # noqa: E402
from audio.engine.master_bus import MasterBus, MasterBusSettings  # noqa: E402
from audio.engine.reverb import RoomReverb  # noqa: E402


def _make_audio(*, frames: int, rng: np.random.Generator) -> Dict[str, np.ndarray]:
    t = np.arange(int(frames), dtype=np.float32) / 44100.0
    tone = np.sin(2.0 * np.pi * 110.0 * t).astype(np.float32) * 0.08
    noise = rng.normal(0.0, 0.04, size=(int(frames), 2)).astype(np.float32)
    dry = noise + np.column_stack([tone, tone]).astype(np.float32)
    return {
        "dry": dry.astype(np.float32, copy=False),
        "reverb": (dry * np.float32(0.45)).astype(np.float32, copy=False),
        "delay": (dry * np.float32(0.30)).astype(np.float32, copy=False),
        "distortion": (dry * np.float32(0.20)).astype(np.float32, copy=False),
    }


def _configure_bus(*, sample_rate: int, mode: str) -> MasterBus:
    mode = str(mode or "dry").strip().lower()
    limiter = mode in {"limiter_rt", "limiter_offline", "full_rt", "full_offline"}
    settings = MasterBusSettings(
        limiter_enabled=limiter,
        limiter_threshold=0.90,
        limiter_lookahead_ms=5.0,
        limiter_release=0.999,
        soft_clip_enabled=mode in {"full_rt", "full_offline"},
        soft_clip_drive=0.95,
    )
    bus = MasterBus(int(sample_rate), settings)
    bus.master_volume = 0.85
    bus.master_output_trim_db = 0.0
    bus.reverb_processor = RoomReverb(
        sample_rate=int(sample_rate),
        rt60=4.5,
        damping=0.62,
        wet=0.24,
        highpass_hz=450.0,
        predelay_ms=18.0,
        early_reflections_enabled=True,
        return_lowpass_hz=9000.0,
    )
    bus.reverb_return_wet = 0.34 if mode in {"returns_safe", "returns_high", "full_rt", "full_offline", "fast_path"} else 0.0
    bus.delay_enabled = mode in {"returns_safe", "returns_high", "full_rt", "full_offline", "fast_path"}
    bus.delay_return_level = 0.25 if bus.delay_enabled else 0.0
    bus.delay_time_ms = 260.0
    bus.delay_feedback = 0.10
    bus.distortion.enabled = mode in {"returns_high", "full_rt", "full_offline"}
    bus.distortion.drive = 1.45
    bus.distortion_return_level = 0.06 if bus.distortion.enabled else 0.0
    bus.master_true_peak_enabled = True
    bus.master_true_peak_oversample_factor = 2
    bus.master_true_peak_realtime_enabled = False

    if mode in {"eq", "full_rt", "full_offline"}:
        bus.master_eq_enabled = True
        bus._master_eq_bands = [
            ("lowshelf", 120.0, 0.8, 0.8),
            ("peaking", 650.0, -0.7, 1.1),
            ("peaking", 2600.0, 0.6, 1.2),
            ("highshelf", 8500.0, 0.7, 0.9),
        ]
        bus._master_eq_cache_key = None
    return bus


def run_case(
    *,
    frames: int,
    mode: str,
    iterations: int,
    warmup: int,
    sample_rate: int,
) -> Dict[str, Any]:
    mode = str(mode)
    rng = np.random.default_rng(24680 + int(frames))
    bus = _configure_bus(sample_rate=int(sample_rate), mode=mode)
    audio = _make_audio(frames=int(frames), rng=rng)
    use_returns = mode in {"returns_safe", "returns_high", "full_rt", "full_offline", "fast_path"}
    realtime = mode in {"limiter_rt", "full_rt", "fast_path"}
    fast_path = mode == "fast_path"
    reverb_tier = "high" if mode in {"returns_high", "full_offline"} else "safe"

    def _process_once() -> np.ndarray:
        return bus.process(
            audio["dry"],
            audio["reverb"] if use_returns else None,
            audio["delay"] if use_returns else None,
            audio["distortion"] if use_returns else None,
            fast_path=fast_path,
            realtime=realtime,
            reverb_quality_tier=reverb_tier,
        )

    for _ in range(max(0, int(warmup))):
        _process_once()

    times_ms: List[float] = []
    for _ in range(max(1, int(iterations))):
        t0 = time.perf_counter()
        _process_once()
        times_ms.append((time.perf_counter() - t0) * 1000.0)

    mean_ms = float(statistics.mean(times_ms))
    p95_ms = float(sorted(times_ms)[int(max(0, min(len(times_ms) - 1, round(0.95 * (len(times_ms) - 1)))))])
    return {
        "frames": int(frames),
        "mode": mode,
        "iterations": int(iterations),
        "mean_ms": round(mean_ms, 4),
        "p95_ms": round(p95_ms, 4),
        "max_ms": round(max(times_ms), 4),
        "realtime_ratio": round(mean_ms / max(1e-9, (float(frames) / float(sample_rate)) * 1000.0), 5),
        "reverb_quality_tier": reverb_tier if use_returns else "",
        "realtime": bool(realtime),
        "fast_path": bool(fast_path),
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Benchmark MasterBus returns, inserts, limiter, and mastering DSP.")
    parser.add_argument("--sample-rate", type=int, default=44100)
    parser.add_argument("--frames", default="512,1024,2048")
    parser.add_argument("--modes", default="dry,returns_safe,limiter_rt,eq,full_rt,full_offline")
    parser.add_argument("--iterations", type=int, default=120)
    parser.add_argument("--warmup", type=int, default=12)
    parser.add_argument("--output", default="")
    parser.add_argument("--max-mean-ms", type=float, default=0.0)
    parser.add_argument("--max-p95-ms", type=float, default=0.0)
    parser.add_argument("--max-realtime-ratio", type=float, default=0.0)
    return parser


def _parse_int_csv(value: str) -> List[int]:
    return [int(x.strip()) for x in str(value or "").split(",") if x.strip()]


def _parse_csv(value: str) -> List[str]:
    return [x.strip() for x in str(value or "").split(",") if x.strip()]


def _gate(rows: List[Dict[str, Any]], args: argparse.Namespace) -> Dict[str, Any]:
    failures: List[Dict[str, Any]] = []
    max_mean_ms = float(args.max_mean_ms)
    max_p95_ms = float(args.max_p95_ms)
    max_realtime_ratio = float(args.max_realtime_ratio)
    for row in rows:
        row_failures: List[str] = []
        if max_mean_ms > 0.0 and float(row["mean_ms"]) > max_mean_ms:
            row_failures.append(f"mean_ms {row['mean_ms']} > {max_mean_ms}")
        if max_p95_ms > 0.0 and float(row["p95_ms"]) > max_p95_ms:
            row_failures.append(f"p95_ms {row['p95_ms']} > {max_p95_ms}")
        if max_realtime_ratio > 0.0 and float(row["realtime_ratio"]) > max_realtime_ratio:
            row_failures.append(f"realtime_ratio {row['realtime_ratio']} > {max_realtime_ratio}")
        if row_failures:
            failures.append({"frames": int(row["frames"]), "mode": str(row["mode"]), "failures": row_failures})
    return {
        "enabled": bool(max_mean_ms > 0.0 or max_p95_ms > 0.0 or max_realtime_ratio > 0.0),
        "ok": not failures,
        "max_mean_ms": max_mean_ms,
        "max_p95_ms": max_p95_ms,
        "max_realtime_ratio": max_realtime_ratio,
        "failure_count": int(len(failures)),
        "failures": failures,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    rows = [
        run_case(
            frames=int(frames),
            mode=str(mode),
            iterations=int(args.iterations),
            warmup=int(args.warmup),
            sample_rate=int(args.sample_rate),
        )
        for frames in _parse_int_csv(args.frames)
        for mode in _parse_csv(args.modes)
    ]
    gate = _gate(rows, args)
    payload = {
        "sample_rate": int(args.sample_rate),
        "case_count": int(len(rows)),
        "gate": gate,
        "rows": rows,
    }
    if str(args.output or "").strip():
        out = resolve_project_path(str(args.output))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if bool(gate["ok"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
