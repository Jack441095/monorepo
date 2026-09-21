#!/usr/bin/env python3
"""Profile the KENN stem-masking DSP stage without changing its contract."""

from __future__ import annotations

import argparse
import cProfile
import io
import json
import math
import pstats
import struct
import sys
import wave
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))
SOURCE_ROOT = SCRIPT_ROOT.parents[1] / "apps" / "backend" / "src"
MIX_REVIEW_ROOT = SCRIPT_ROOT.parents[1] / "packages" / "mix-review" / "core"
for path in (SOURCE_ROOT, MIX_REVIEW_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from masking_analysis import analyze_stem_masking


def _wav_bytes(*, seconds: float, sample_rate: int, frequency_hz: float) -> bytes:
    count = int(seconds * sample_rate)
    frames = b"".join(
        struct.pack(
            "<h",
            int(round(0.2 * 32767.0 * math.sin(2.0 * math.pi * frequency_hz * index / sample_rate))),
        )
        for index in range(count)
    )
    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(frames)
    return output.getvalue()


def _stage_stats(profile: cProfile.Profile) -> dict[str, dict[str, float | int]]:
    stats = pstats.Stats(profile).stats
    result: dict[str, dict[str, float | int]] = {}
    for name in ("analyze_stem_masking", "_band_energy_over_time", "_mono_from_wav"):
        matching = [value for key, value in stats.items() if key[2] == name]
        if not matching:
            continue
        result[name] = {
            "calls": sum(value[0] for value in matching),
            "exclusive_ms": round(sum(value[2] for value in matching) * 1000.0, 3),
            "cumulative_ms": round(sum(value[3] for value in matching) * 1000.0, 3),
        }
    return result


def run(*, seconds: float, sample_rate: int, stems: int, repeats: int) -> dict[str, Any]:
    payloads = [
        (f"stem{index}", _wav_bytes(seconds=seconds, sample_rate=sample_rate, frequency_hz=110.0 + index * 80.0))
        for index in range(stems)
    ]
    profile = cProfile.Profile()
    profile.enable()
    result: dict[str, Any] | None = None
    for _ in range(repeats):
        result = analyze_stem_masking(payloads)
    profile.disable()
    assert result is not None
    stages = _stage_stats(profile)
    total_ms = float(stages.get("analyze_stem_masking", {}).get("cumulative_ms", 0.0))
    dominant = max(stages, key=lambda name: float(stages[name]["exclusive_ms"]), default="unknown")
    return {
        "schema": "kenn.dsp_profile.v1",
        "profile_version": "kenn.masking_analysis.profile.v1",
        "candidate": "python-numpy-reference",
        "fixture": {
            "generator": "deterministic mono PCM16 sine stems",
            "seconds": seconds,
            "sample_rate_hz": sample_rate,
            "stems": stems,
        },
        "repeats": repeats,
        "ok": result.get("ok") is True,
        "finding_count": len(result.get("findings", [])),
        "total_profiled_ms": total_ms,
        "stages": stages,
        "dominant_stage": dominant,
        "interpretation": (
            "The per-frame band-energy stage is the next native DSP candidate only if a complete "
            "real AutoMix request shows material end-to-end contribution; this synthetic profile "
            "does not justify a migration by itself."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=30.0)
    parser.add_argument("--sample-rate", type=int, default=48_000)
    parser.add_argument("--stems", type=int, default=8)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    if args.seconds <= 0 or args.sample_rate <= 0 or args.stems < 2 or args.repeats <= 0:
        parser.error("seconds/sample-rate/repeats must be positive and stems must be at least 2")
    result = run(
        seconds=args.seconds,
        sample_rate=args.sample_rate,
        stems=args.stems,
        repeats=args.repeats,
    )
    rendered = json.dumps(result, indent=2)
    print(rendered)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(rendered + "\n", encoding="utf-8")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
