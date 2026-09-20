#!/usr/bin/env python3
"""KENN_GOLDEN_BENCHMARK_V1: deterministic black-box qualification.

This program imports the product's current Mix Review entry point read-only.
It generates synthetic PCM in memory; no product fixtures, customer files, or
audio uploads are written.  Ground truth describes injected signal properties,
not aesthetic preferences.
"""
from __future__ import annotations

import io
import json
import math
import os
import platform
import resource
import struct
import sys
import time
import wave
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT.parent / "Audio_Too"
sys.path[:0] = [str(PRODUCT), str(PRODUCT / "business" / "app"), str(PRODUCT / "business" / "agents"), str(PRODUCT / "studio" / "audio_analysis")]
# The product cache is otherwise eligible to write inside Audio_Too.  Keep all
# evaluation side effects inside this isolated workspace.
os.environ.setdefault("AUDIO_TOO_ANALYSIS_CACHE", str(ROOT / "results" / "product_cache"))
from audio_analysis.mix_review import mix_review  # noqa: E402

VERSION = "KENN_GOLDEN_BENCHMARK_V1"
SEED = 20260823
SR = 48_000
DURATION = 0.75
RNG = np.random.default_rng(SEED)

EXPECTED = {
    "clipping": {"Clipping risk"}, "headroom": {"Low headroom"},
    "dc": {"DC offset"}, "bass_excess": {"Heavy sub", "Low-end heavy balance"},
    "hf_excess": {"Bright top end", "Perceived harshness"},
    "resonance": {"Harsh resonance"}, "mud": {"Low-mid build-up"},
    "harshness": {"Perceived harshness", "Harsh resonance"},
    "lr_imbalance": {"Stereo imbalance"}, "anti_phase": {"Mono risk", "Low-End Phase Cancellation"},
    "wide_bass": {"Side Bass Mud", "Low-End Phase Cancellation"},
    "over_compression": {"Low dynamics", "Over-compressed (LRA)"},
    "transient_peaks": {"Spiky transients", "Loudness spike"},
    "silence": {"Low presence"}, "near_silence": set(), "noise": set(),
}


def db(x: float) -> float:
    return 10 ** (x / 20)


def base_audio(seed: int, *, channels: int = 2) -> np.ndarray:
    rng = np.random.default_rng(seed)
    t = np.arange(int(SR * DURATION)) / SR
    # A non-stereotyped musical proxy: low fundamental, body, transient detail,
    # and modest decorrelated ambience at safe headroom.
    mono = (.19 * np.sin(2 * np.pi * 72 * t) + .12 * np.sin(2 * np.pi * 220 * t)
            + .08 * np.sin(2 * np.pi * 880 * t) + .035 * np.sin(2 * np.pi * 3400 * t))
    env = .72 + .28 * np.maximum(0, np.sin(2 * np.pi * 2.1 * t))
    mono *= env
    if channels == 1:
        return mono[:, None]
    side = .018 * np.sin(2 * np.pi * 1600 * t + .45) + .004 * rng.standard_normal(len(t))
    return np.column_stack((mono + side, mono - side))


def render(fault: str | None, severity: int, seed: int, channels: int = 2) -> np.ndarray:
    x = base_audio(seed, channels=channels)
    t = np.arange(len(x)) / SR
    s = severity / 5
    if fault == "clipping": x = np.clip(x * (1 + 4.5 * s), -.88, .88)
    elif fault == "headroom": x *= .55 + .5 * s
    elif fault == "dc": x += .01 + .12 * s
    elif fault == "bass_excess": x += (.08 + .48 * s) * np.sin(2 * np.pi * 48 * t)[:, None]
    elif fault == "hf_excess": x += (.025 + .22 * s) * np.sin(2 * np.pi * 11000 * t)[:, None]
    elif fault == "resonance": x += (.02 + .25 * s) * np.sin(2 * np.pi * 3150 * t)[:, None]
    elif fault == "mud": x += (.04 + .24 * s) * np.sin(2 * np.pi * 260 * t)[:, None]
    elif fault == "harshness": x += (.03 + .22 * s) * np.sin(2 * np.pi * 3600 * t)[:, None]
    elif fault == "lr_imbalance": x[:, 1] *= 1 - .12 * s
    elif fault == "anti_phase" and x.shape[1] == 2: x[:, 1] = -x[:, 0]
    elif fault == "wide_bass" and x.shape[1] == 2:
        bass = (.06 + .3 * s) * np.sin(2 * np.pi * 65 * t); x[:, 0] += bass; x[:, 1] -= bass
    elif fault == "over_compression": x = np.tanh(x * (2 + 8 * s)) * (.32 + .08 * (1-s))
    elif fault == "transient_peaks":
        for point in range(0, len(x), max(1, len(x)//6)): x[point:point+12] += .2 + .65*s
    elif fault == "silence": x *= 0
    elif fault == "near_silence": x *= 0.0002
    elif fault == "noise": x = (.015 + .22 * s) * np.random.default_rng(seed).standard_normal(x.shape)
    return np.clip(x, -1, 1)


def wav_bytes(x: np.ndarray, sr: int) -> bytes:
    buf = io.BytesIO()
    pcm = np.round(np.clip(x, -1, 1) * 32767).astype("<i2")
    with wave.open(buf, "wb") as out:
        out.setnchannels(x.shape[1]); out.setsampwidth(2); out.setframerate(sr); out.writeframes(pcm.tobytes())
    return buf.getvalue()


def cases() -> list[dict]:
    rows = []
    # Controls include deliberate bright/dark/low-crest/wide-but-compatible material.
    controls = [(None, 0, "healthy"), ("hf_excess", 1, "intentional_bright"), ("bass_excess", 1, "genre_low_end"),
                ("over_compression", 1, "intentional_density"), (None, 0, "mono_control")]
    for rep in range(10):
        for fault, sev, group in controls:
            rows.append({"id": f"{group}-{rep:02d}", "faults": [] if fault is None else [fault], "severity": sev, "group": group, "healthy": True, "channels": 1 if group == "mono_control" else 2})
    single = list(EXPECTED)
    for fault in single:
        for sev in range(1, 6):
            for rep in range(2):
                rows.append({"id": f"{fault}-s{sev}-{rep}", "faults": [fault], "severity": sev, "group": "single_fault", "healthy": False, "channels": 2})
    pairs = [("mud", "over_compression"), ("harshness", "headroom"), ("wide_bass", "anti_phase"),
             ("clipping", "hf_excess"), ("bass_excess", "hf_excess"), ("lr_imbalance", "resonance")]
    for rep in range(5):
        for pair in pairs:
            rows.append({"id": f"multi-{'-'.join(pair)}-{rep}", "faults": list(pair), "severity": 4, "group": "multi_fault", "healthy": False, "channels": 2})
    # 50 controls + 160 single fault + 30 multi = 240 controlled cases.
    return rows


def detected(labels: set[str], fault: str) -> bool:
    return bool(labels & EXPECTED[fault])


def main() -> None:
    started = time.perf_counter(); raw = []
    for index, case in enumerate(cases()):
        audio = base_audio(SEED + index, channels=case["channels"])
        for fault in case["faults"]: audio = render(fault, case["severity"], SEED + index, case["channels"]) if len(case["faults"]) == 1 else audio
        if len(case["faults"]) > 1:
            # Inject each compound defect cumulatively, using its delta from base.
            for fault in case["faults"]: audio += render(fault, case["severity"], SEED + index, case["channels"]) - base_audio(SEED + index, channels=case["channels"])
            audio = np.clip(audio, -1, 1)
        began = time.perf_counter()
        try:
            # Full report is required: the product deliberately suppresses
            # interpretations/flags in its lightweight metering path.
            report = mix_review.analyze_wav(wav_bytes(audio, SR), case["id"] + ".wav", light=False)
            flags = [str(f.get("label")) for f in report.get("flags", [])]
            metrics = report.get("metrics", {})
            error = None
        except Exception as exc:  # benchmark reports errors rather than hiding them
            flags, metrics, error = [], {}, f"{type(exc).__name__}: {exc}"
        labels = set(flags)
        result = {**case, "flags": flags, "metric_keys": sorted(metrics), "runtime_s": round(time.perf_counter()-began, 4), "error": error,
                  "detected": {fault: detected(labels, fault) for fault in case["faults"]}}
        raw.append(result)
    by_fault = {}
    for fault in EXPECTED:
        subset = [r for r in raw if fault in r["faults"]]
        hits = sum(r["detected"].get(fault, False) for r in subset)
        by_fault[fault] = {"cases": len(subset), "recall": round(hits / len(subset), 4), "hits": hits}
    healthy = [r for r in raw if r["healthy"]]
    fp = sum(bool(r["flags"]) for r in healthy)
    multi = [r for r in raw if r["group"] == "multi_fault"]
    multi_total = sum(len(r["faults"]) for r in multi)
    multi_hits = sum(sum(r["detected"].values()) for r in multi)
    output = {"benchmark": VERSION, "seed": SEED, "case_count": len(raw), "healthy_controls": len(healthy),
              "single_fault": sum(r["group"] == "single_fault" for r in raw), "multi_fault": len(multi),
              "environment": {"python": sys.version.split()[0], "numpy": np.__version__, "platform": platform.platform()},
              "results": raw, "summary": {"per_fault": by_fault, "healthy_false_positive_rate": round(fp/max(1,len(healthy)),4),
              "multi_fault_recall": round(multi_hits/max(1,multi_total),4), "analysis_runtime_s": round(time.perf_counter()-started,3),
              "mean_case_runtime_s": round(sum(r["runtime_s"] for r in raw)/len(raw),4), "errors": sum(r["error"] is not None for r in raw),
              "flag_counts": dict(Counter(flag for r in raw for flag in r["flags"]))},
              "limitations": ["A synthetic defect is not a universal artistic error.", "Recall is measured only against current product flag labels and their documented signal meaning.", "Live LLM behavioural qualification was not run; this benchmark uses deterministic DSP reports."]}
    destination = ROOT / "results" / "KENN_GOLDEN_BENCHMARK_V1_results.json"
    destination.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps(output["summary"], indent=2))


if __name__ == "__main__": main()
