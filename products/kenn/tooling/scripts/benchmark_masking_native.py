#!/usr/bin/env python3
"""Compare the optional native masking-band path with the NumPy reference."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import statistics
import struct
import sys
import time
import wave
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = REPO_ROOT / "apps" / "backend" / "src"
MIX_REVIEW_ROOT = REPO_ROOT / "packages" / "mix-review"
for path in (SOURCE_ROOT, MIX_REVIEW_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def _wav_bytes(*, seconds: float, sample_rate: int, frequency_hz: float) -> bytes:
    count = int(seconds * sample_rate)
    values = np.rint(
        0.2 * 32767.0 * np.sin(2.0 * np.pi * frequency_hz * np.arange(count) / sample_rate)
    ).astype("<i2")
    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(values.tobytes())
    return output.getvalue()


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def run(*, backend: str, seconds: float, stems: int, repeats: int) -> dict[str, Any]:
    if backend == "native":
        os.environ["KENN_DSP_NATIVE"] = "1"
        os.environ["KENN_DSP_MASKING_NATIVE"] = "1"
    else:
        os.environ["KENN_DSP_NATIVE"] = "0"
        os.environ["KENN_DSP_MASKING_NATIVE"] = "0"

    from core.masking_analysis import analyze_stem_masking

    sample_rate = 48_000
    fixtures = [
        (f"stem{index}", _wav_bytes(seconds=seconds, sample_rate=sample_rate, frequency_hz=110.0 + index * 80.0))
        for index in range(stems)
    ]
    source_hash = hashlib.sha256(b"".join(payload for _label, payload in fixtures)).hexdigest()
    for _ in range(2):
        analyze_stem_masking(fixtures)
    samples_ms: list[float] = []
    result: dict[str, Any] | None = None
    for _ in range(repeats):
        started = time.perf_counter()
        result = analyze_stem_masking(fixtures)
        samples_ms.append((time.perf_counter() - started) * 1000.0)
    assert result is not None
    findings_json = json.dumps(result.get("findings", []), sort_keys=True, separators=(",", ":"))
    return {
        "schema": "kenn.dsp_masking_benchmark.v1",
        "candidate": backend,
        "fixture": {
            "generator": "deterministic sine PCM16 WAV stems",
            "seconds": seconds,
            "sample_rate_hz": sample_rate,
            "stems": stems,
            "sha256": source_hash,
        },
        "repeats": repeats,
        "implementation": result.get("implementation"),
        "ok": result.get("ok") is True,
        "finding_count": len(result.get("findings", [])),
        "findings_sha256": hashlib.sha256(findings_json.encode("utf-8")).hexdigest(),
        "samples_ms": [round(value, 3) for value in samples_ms],
        "mean_ms": round(statistics.mean(samples_ms), 3),
        "p50_ms": round(_percentile(samples_ms, 0.50), 3),
        "p95_ms": round(_percentile(samples_ms, 0.95), 3),
        "max_ms": round(max(samples_ms), 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=("native", "reference"), required=True)
    parser.add_argument("--seconds", type=float, default=5.0)
    parser.add_argument("--stems", type=int, default=8)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    if args.seconds <= 0 or args.stems < 2 or args.repeats <= 0:
        parser.error("seconds/repeats must be positive and stems must be at least 2")
    result = run(backend=args.backend, seconds=args.seconds, stems=args.stems, repeats=args.repeats)
    rendered = json.dumps(result, indent=2)
    print(rendered)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(rendered + "\n", encoding="utf-8")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
