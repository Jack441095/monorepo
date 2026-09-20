#!/usr/bin/env python3
"""
Golden-metrics harness for the analysis system.

WHY THIS EXISTS
---------------
The analysis hot path is about to get efficiency refactors (a shared spectral
frontend so N analyzers stop each recomputing the same FFT; a numpy/numba
loudness inner loop to kill the Python-list `.tolist()` churn in loudness.py).
Those refactors are only safe if we can prove they produce the SAME NUMBERS,
just faster. This harness is that proof.

It runs `analyze_wav` over a fixed, deterministic synthetic corpus, extracts a
curated set of stable scalar metrics (loudness, true-peak, RMS, crest, band
shares, resonances, stereo, spectral features, tonal balance, technical score),
and compares them against a committed golden snapshot.

USAGE
-----
    # First time / intentional metric change — write the snapshot:
    python scripts/eval/golden_metrics.py --update

    # Check current code against the snapshot (also runs as a pytest test):
    python scripts/eval/golden_metrics.py --check

    # Verify a refactor preserves outputs within a tolerance (not bit-exact):
    python scripts/eval/golden_metrics.py --check --rel-tol 1e-6 --abs-tol 1e-4

This is glue over the existing `mix_review.analyze_wav` engine — it adds no new
analysis. It is a REGRESSION GUARD, not a quality gate: it says "the numbers did
not move", never "the numbers are good".
"""

from __future__ import annotations

import argparse
import io
import json
import math
import sys
import wave
from pathlib import Path
from typing import Any

import numpy as np

# The committed snapshot lives next to the test that consumes it.
GOLDEN_PATH = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "audio_analysis"
    / "golden"
    / "analysis_metrics_golden.json"
)

SAMPLE_RATE = 44100

# High-cardinality / per-frame fields that are noise for a regression snapshot:
# they are large, order-sensitive, and not what the efficiency refactors touch.
# Everything else scalar is kept.
_NOISE_SUBSTRINGS = (
    "vectorscope_points",
    "correlation_timeline",
    "windowed_rms",
    "spectrum_magnitudes",
    ".magnitudes",
    "per_frame",
    "chords.progression",
    # High-cardinality per-event / per-section lists: deterministic but
    # order- and length-sensitive, and NOT what the spectral/loudness
    # efficiency refactors touch. The summary scalars (resonances top-N,
    # section highlights, band shares, LRA scalar) are kept instead.
    "transient_analysis.events",
    "groove_analysis.deviations",
    "section_analysis.sections",
    "loudness_range_by_section",
    "goal_target_checks.checks",
)


def _wav_bytes(signal: np.ndarray, *, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Encode a mono float signal in [-1, 1] as 16-bit PCM WAV bytes."""
    pcm = np.clip(signal, -1.0, 1.0)
    payload = (pcm * 32767.0).astype("<i2").tobytes()
    out = io.BytesIO()
    with wave.open(out, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(payload)
    return out.getvalue()


def _t(duration_s: float, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    return np.linspace(0, duration_s, int(sample_rate * duration_s), endpoint=False)


def build_corpus() -> dict[str, bytes]:
    """Deterministic synthetic clips spanning the spectral/dynamic space the
    analyzers care about. Fully seeded — identical bytes on every run.

    Kept intentionally varied (broadband / bass-heavy / bright / transient /
    longer-so-decimation-triggers) so the snapshot exercises the band, loudness,
    resonance, transient and stereo paths, not just one corner."""
    clips: dict[str, bytes] = {}

    # 1. Broadband multitone + light noise — every log-band has real energy.
    t = _t(6.0)
    sig = sum(0.12 * np.sin(2 * np.pi * f * t) for f in (60, 250, 1000, 4000, 12000))
    sig += 0.02 * np.random.default_rng(7).standard_normal(len(t))
    clips["broadband_6s"] = _wav_bytes(sig)

    # 2. Bass-heavy — exercises sub/bass bands + low-fundamental resonance path.
    t = _t(6.0)
    sig = 0.4 * np.sin(2 * np.pi * 55 * t) + 0.15 * np.sin(2 * np.pi * 110 * t)
    sig += 0.05 * np.sin(2 * np.pi * 1500 * t)
    clips["bass_heavy_6s"] = _wav_bytes(sig)

    # 3. Bright — exercises presence/air/sibilance + spectral centroid/rolloff.
    t = _t(6.0)
    sig = sum(0.15 * np.sin(2 * np.pi * f * t) for f in (3000, 6000, 9000, 13000))
    sig += 0.03 * np.random.default_rng(11).standard_normal(len(t))
    clips["bright_6s"] = _wav_bytes(sig)

    # 4. Transient train — exercises attack/onset/crest/transient-density path.
    t = _t(6.0)
    env = np.zeros(len(t))
    hop = int(SAMPLE_RATE * 0.5)
    decay = np.exp(-_t(0.12) * 40.0)
    for start in range(0, len(t) - len(decay), hop):
        env[start:start + len(decay)] += decay
    sig = env * np.sin(2 * np.pi * 220 * t)
    clips["transient_6s"] = _wav_bytes(sig)

    # 5. Longer broadband — long enough to trigger read_wav_mono decimation +
    #    the LUFS/band-ratio high-fidelity re-read paths in analyze_wav.
    t = _t(25.0)
    sig = sum(0.12 * np.sin(2 * np.pi * f * t) for f in (80, 300, 1200, 5000, 11000))
    sig += 0.02 * np.random.default_rng(23).standard_normal(len(t))
    clips["broadband_long_25s"] = _wav_bytes(sig)

    return clips


def _is_noise(path: str) -> bool:
    return any(sub in path for sub in _NOISE_SUBSTRINGS)


def _scalar_leaves(value: Any, prefix: str = "") -> dict[str, float]:
    """Flatten a report subtree to its numeric scalar leaves (bool excluded),
    dropping the high-cardinality per-frame noise fields."""
    out: dict[str, float] = {}
    if isinstance(value, bool):
        return out
    if isinstance(value, (int, float)):
        if not _is_noise(prefix):
            out[prefix.rstrip(".")] = float(value)
    elif isinstance(value, dict):
        for key, sub in value.items():
            out.update(_scalar_leaves(sub, f"{prefix}{key}."))
    elif isinstance(value, (list, tuple)):
        for idx, sub in enumerate(value):
            out.update(_scalar_leaves(sub, f"{prefix}{idx}."))
    return out


def extract_metrics(report: dict) -> dict[str, float]:
    """Curated, stable scalar surface of an analyze_wav report."""
    metrics: dict[str, float] = {}
    for section in ("metrics", "technical_metrics"):
        for path, val in _scalar_leaves(report.get(section, {})).items():
            metrics[f"{section}.{path}"] = val
    return metrics


def compute_all() -> dict[str, dict[str, float]]:
    """Run the analyzer over the whole corpus. Imported lazily so `--help`
    doesn't pay the analysis-package import/JIT cost."""
    from audio_analysis.mix_review import mix_review

    results: dict[str, dict[str, float]] = {}
    for name, wav in build_corpus().items():
        report = mix_review.analyze_wav(wav, f"{name}.wav", mix_goal="premaster")
        results[name] = extract_metrics(report)
    return results


def _round(results: dict[str, dict[str, float]], ndigits: int = 6) -> dict:
    return {clip: {k: round(v, ndigits) for k, v in sorted(m.items())}
            for clip, m in sorted(results.items())}


def load_golden() -> dict:
    if not GOLDEN_PATH.exists():
        raise FileNotFoundError(
            f"No golden snapshot at {GOLDEN_PATH}. Run with --update to create it."
        )
    return json.loads(GOLDEN_PATH.read_text())


def compare(
    current: dict[str, dict[str, float]],
    golden: dict[str, dict[str, float]],
    *,
    rel_tol: float = 0.0,
    abs_tol: float = 1e-9,
) -> list[str]:
    """Return a list of human-readable difference strings (empty == match)."""
    diffs: list[str] = []
    cur_clips, gold_clips = set(current), set(golden)
    for missing in sorted(gold_clips - cur_clips):
        diffs.append(f"[{missing}] clip missing from current run")
    for extra in sorted(cur_clips - gold_clips):
        diffs.append(f"[{extra}] clip not in golden (run --update if intended)")

    for clip in sorted(cur_clips & gold_clips):
        cur_m, gold_m = current[clip], golden[clip]
        for missing in sorted(set(gold_m) - set(cur_m)):
            diffs.append(f"[{clip}] metric dropped: {missing}")
        for extra in sorted(set(cur_m) - set(gold_m)):
            diffs.append(f"[{clip}] new metric: {extra} = {cur_m[extra]:.6g}")
        for key in sorted(set(cur_m) & set(gold_m)):
            a, b = cur_m[key], gold_m[key]
            if not math.isclose(a, b, rel_tol=rel_tol, abs_tol=abs_tol):
                diffs.append(
                    f"[{clip}] {key}: got {a:.8g}, golden {b:.8g} "
                    f"(Δ={a - b:+.3g})"
                )
    return diffs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--update", action="store_true",
                      help="Recompute and overwrite the golden snapshot.")
    mode.add_argument("--check", action="store_true",
                      help="Compare current code against the golden snapshot (default).")
    parser.add_argument("--rel-tol", type=float, default=0.0,
                        help="Relative tolerance for --check (default 0.0 = bit-exact).")
    parser.add_argument("--abs-tol", type=float, default=1e-9,
                        help="Absolute tolerance for --check (default 1e-9).")
    args = parser.parse_args(argv)

    if args.update:
        results = _round(compute_all())
        GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN_PATH.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")
        n_metrics = sum(len(m) for m in results.values())
        print(f"Wrote golden snapshot: {len(results)} clips, {n_metrics} metrics "
              f"-> {GOLDEN_PATH}")
        return 0

    # default and --check both land here
    current = _round(compute_all())
    golden = load_golden()
    diffs = compare(current, golden, rel_tol=args.rel_tol, abs_tol=args.abs_tol)
    if diffs:
        print(f"GOLDEN METRICS MISMATCH ({len(diffs)} difference(s)):")
        for line in diffs:
            print(f"  {line}")
        return 1
    n_metrics = sum(len(m) for m in current.values())
    print(f"OK — {len(current)} clips, {n_metrics} metrics match golden "
          f"(rel_tol={args.rel_tol}, abs_tol={args.abs_tol}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
