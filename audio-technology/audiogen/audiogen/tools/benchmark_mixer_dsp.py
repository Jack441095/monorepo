#!/usr/bin/env python3
"""Benchmark AudioMixer strip DSP costs for realtime tuning."""

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
from audio.engine.mixer import AudioMixer  # noqa: E402


def _make_audio(*, channels: int, frames: int, rng: np.random.Generator, silent_every: int = 0) -> Dict[int, np.ndarray]:
    out: Dict[int, np.ndarray] = {}
    for ch in range(int(channels)):
        if silent_every > 0 and ch % int(silent_every) == 0:
            out[int(ch)] = np.zeros((int(frames), 2), dtype=np.float32)
        else:
            x = rng.normal(0.0, 0.08, size=(int(frames), 2)).astype(np.float32)
            out[int(ch)] = x
    return out


def _configure_mixer(mixer: AudioMixer, *, mode: str, sends: bool) -> None:
    mode = str(mode or "filters").strip().lower()
    for ch in mixer.channels:
        ch.volume = 0.5
        ch.pan = -0.15 if int(ch.index) % 2 else 0.12
        ch.reverb_send = 0.35 if sends and int(ch.index) in {1, 2, 3, 5} else 0.0
        ch.delay_send = 0.20 if sends and int(ch.index) in {2, 3, 5} else 0.0
        ch.distortion_send = 0.08 if sends and int(ch.index) == 3 else 0.0
        ch.eq_enabled = mode in {"eq", "eq_filters"}
        ch.eq_low_gain_db = 1.5
        ch.eq_mid_gain_db = -1.0
        ch.eq_high_gain_db = 0.75
        ch.filter_enabled = mode in {"filters", "eq_filters"}
        ch.highpass_hz = 30.0 + 20.0 * int(ch.index)
        ch.lowpass_hz = 9000.0 + 500.0 * int(ch.index)
        ch.filter_slope_db_per_oct = 12.0


def run_case(
    *,
    frames: int,
    channels: int,
    mode: str,
    iterations: int,
    warmup: int,
    sample_rate: int,
    sends: bool,
    silent_every: int,
) -> Dict[str, Any]:
    rng = np.random.default_rng(12345 + int(frames) + int(channels))
    mixer = AudioMixer(num_channels=int(channels), sample_rate=int(sample_rate))
    _configure_mixer(mixer, mode=str(mode), sends=bool(sends))
    audio = _make_audio(channels=int(channels), frames=int(frames), rng=rng, silent_every=int(silent_every))

    for _ in range(max(0, int(warmup))):
        mixer.mix_audio(audio)

    times_ms: List[float] = []
    for _ in range(max(1, int(iterations))):
        t0 = time.perf_counter()
        mixer.mix_audio(audio)
        times_ms.append((time.perf_counter() - t0) * 1000.0)

    mean_ms = float(statistics.mean(times_ms))
    p95_ms = float(sorted(times_ms)[int(max(0, min(len(times_ms) - 1, round(0.95 * (len(times_ms) - 1)))))])
    return {
        "frames": int(frames),
        "channels": int(channels),
        "mode": str(mode),
        "sends": bool(sends),
        "silent_every": int(silent_every),
        "iterations": int(iterations),
        "mean_ms": round(mean_ms, 4),
        "p95_ms": round(p95_ms, 4),
        "max_ms": round(max(times_ms), 4),
        "per_channel_mean_us": round((mean_ms * 1000.0) / max(1, int(channels)), 3),
        "realtime_ratio_at_70bpm": round(mean_ms / max(1e-9, (float(frames) / float(sample_rate)) * 1000.0), 5),
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Benchmark AudioMixer channel DSP and send routing.")
    parser.add_argument("--sample-rate", type=int, default=44100)
    parser.add_argument("--channels", type=int, default=7)
    parser.add_argument("--frames", default="256,512,1024,2048")
    parser.add_argument("--modes", default="none,filters,eq,eq_filters")
    parser.add_argument("--iterations", type=int, default=200)
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument("--sends", action="store_true")
    parser.add_argument("--silent-every", type=int, default=0)
    parser.add_argument("--output", default="")
    parser.add_argument(
        "--max-mean-ms",
        type=float,
        default=0.0,
        help="Optional gate: fail if any case mean_ms exceeds this value.",
    )
    parser.add_argument(
        "--max-p95-ms",
        type=float,
        default=0.0,
        help="Optional gate: fail if any case p95_ms exceeds this value.",
    )
    parser.add_argument(
        "--max-realtime-ratio",
        type=float,
        default=0.0,
        help="Optional gate: fail if any case realtime_ratio_at_70bpm exceeds this value.",
    )
    return parser


def _parse_int_csv(value: str) -> List[int]:
    return [int(x.strip()) for x in str(value or "").split(",") if x.strip()]


def _parse_csv(value: str) -> List[str]:
    return [x.strip() for x in str(value or "").split(",") if x.strip()]


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    rows = [
        run_case(
            frames=int(frames),
            channels=int(args.channels),
            mode=str(mode),
            iterations=int(args.iterations),
            warmup=int(args.warmup),
            sample_rate=int(args.sample_rate),
            sends=bool(args.sends),
            silent_every=int(args.silent_every),
        )
        for frames in _parse_int_csv(args.frames)
        for mode in _parse_csv(args.modes)
    ]
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
        if max_realtime_ratio > 0.0 and float(row["realtime_ratio_at_70bpm"]) > max_realtime_ratio:
            row_failures.append(f"realtime_ratio_at_70bpm {row['realtime_ratio_at_70bpm']} > {max_realtime_ratio}")
        if row_failures:
            failures.append(
                {
                    "frames": int(row["frames"]),
                    "mode": str(row["mode"]),
                    "sends": bool(row["sends"]),
                    "failures": row_failures,
                }
            )

    gate_enabled = bool(max_mean_ms > 0.0 or max_p95_ms > 0.0 or max_realtime_ratio > 0.0)
    payload = {
        "sample_rate": int(args.sample_rate),
        "case_count": int(len(rows)),
        "gate": {
            "enabled": gate_enabled,
            "ok": not failures,
            "max_mean_ms": max_mean_ms,
            "max_p95_ms": max_p95_ms,
            "max_realtime_ratio": max_realtime_ratio,
            "failure_count": int(len(failures)),
            "failures": failures,
        },
        "rows": rows,
    }
    if str(args.output or "").strip():
        out = resolve_project_path(str(args.output))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
