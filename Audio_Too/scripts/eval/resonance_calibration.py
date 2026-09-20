#!/usr/bin/env python3
"""
Resonance-detector calibration harness (workstream #2).

Runs analysis_core.resonance_detection.detect_resonant_bands on every stem of the
three real tracks, at the current thresholds and across a sweep, and reports what
gets flagged so we can judge precision (real problem vs musical content).

Precision heuristic: a flagged band that sits near a stem's spectral centroid /
fundamental is likely MUSICAL (false positive); a flagged band well above the
centroid, narrow and persistent, is more likely a genuine harsh resonance.

Read-only. Writes a JSON + markdown report; does not modify detector or renderer.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from datetime import datetime

REPO = Path(__file__).resolve().parent.parent.parent
ANALYSIS = REPO / "studio" / "audio_analysis"
sys.path.insert(0, str(ANALYSIS))

from audio_analysis.analysis_core.resonance_detection import detect_resonant_bands  # noqa: E402
from audio_analysis.utils.audio_io import read_wav_mono  # noqa: E402

# IMPORTANT: read FULL-RATE (max_samples=0) so the detector sees true frequencies.
# read_wav_mono with max_samples>0 low-pass-decimates but still reports the original
# sample_rate, warping every FFT bin→Hz mapping (the documented decoder bug). We then
# slice a bounded time window from the full-rate signal to keep detection fast and
# memory bounded to one stem at a time.
ANALYSIS_WINDOW_SECONDS = 12.0

TRACKS = {
    "dream_of_you": REPO / "testing_track_stems" / "dream_of_you" / "WAVs",
    "reggueton_pop": REPO / "testing_track_stems" / "reggueton_pop" / "WAV's",
    "stranger": REPO / "testing_track_stems" / "stranger" / "WAVs",
}

# Threshold grid to sweep (prominence_db, persistence).
SWEEP = [
    (6.0, 0.4),   # current defaults
    (8.0, 0.5),
    (9.0, 0.5),
    (10.0, 0.6),
    (12.0, 0.6),
]


def _spectral_centroid_hz(samples: list[float], sr: int) -> float:
    """Rough spectral centroid — the 'musical center of mass' of the stem.
    Used only as a false-positive heuristic (a flag near the centroid is
    more likely to be the instrument's own body, not a harsh resonance)."""
    try:
        import numpy as np
        x = np.asarray(samples, dtype=float)
        if x.size < 2048:
            return 0.0
        win = x[: 1 << (int(np.log2(x.size)))]
        mag = np.abs(np.fft.rfft(win * np.hanning(win.size)))
        freqs = np.fft.rfftfreq(win.size, 1.0 / sr)
        total = mag.sum()
        return float((freqs * mag).sum() / total) if total > 0 else 0.0
    except Exception:
        return 0.0


def _read_stem(path: Path) -> tuple[list[float], int]:
    # Full-rate decode (correct SR / frequencies), then slice a bounded window.
    data = read_wav_mono(path.read_bytes(), max_samples=0)
    sr = int(data["sample_rate"])
    samples = data["samples"]
    window = int(ANALYSIS_WINDOW_SECONDS * sr)
    # Take a window from ~25% into the stem to avoid intro silence/fades.
    start = min(len(samples) // 4, max(0, len(samples) - window))
    return samples[start:start + window], sr


def calibrate_track(track: str, wav_dir: Path) -> dict:
    if not wav_dir.exists():
        return {"track": track, "error": f"missing dir {wav_dir}"}

    stems = sorted(p for p in wav_dir.glob("*.wav") if not p.name.startswith("."))
    print(f"\n{'='*70}\n{track}  ({len(stems)} stems)\n{'='*70}")

    stem_reports = []
    for stem_path in stems:
        name = stem_path.stem
        try:
            samples, sr = _read_stem(stem_path)
        except Exception as e:
            print(f"  ⚠️  {name}: read failed ({e})")
            continue

        centroid = _spectral_centroid_hz(samples, sr)

        # Current-default flags
        default_bands = detect_resonant_bands(samples, sr)

        # Sweep
        sweep_counts = {}
        for prom, pers in SWEEP:
            bands = detect_resonant_bands(
                samples, sr,
                prominence_threshold_db=prom,
                persistence_threshold=pers,
            )
            sweep_counts[f"p{prom}_per{pers}"] = len(bands)

        # Precision heuristic on the current-default flags: how many sit within
        # half an octave of the centroid (likely musical, not a harsh resonance)?
        near_centroid = 0
        for b in default_bands:
            f = b["frequency_hz"]
            if centroid > 0 and 0.66 * centroid <= f <= 1.5 * centroid:
                near_centroid += 1

        report = {
            "stem": name,
            "sample_rate": sr,
            "spectral_centroid_hz": round(centroid, 1),
            "default_flag_count": len(default_bands),
            "default_flags": default_bands[:8],
            "near_centroid_flags": near_centroid,
            "sweep_counts": sweep_counts,
        }
        stem_reports.append(report)

        flag_str = ", ".join(
            f"{b['frequency_hz']:.0f}Hz(p{b['mean_prominence_db']:.1f}/{b['persistence']:.2f})"
            for b in default_bands[:5]
        ) or "none"
        fp_flag = " ⚠️FP?" if near_centroid and near_centroid == len(default_bands) and default_bands else ""
        print(f"  {name:<34} centroid={centroid:6.0f}Hz  flags={len(default_bands):>2}  [{flag_str}]{fp_flag}")

    total_default = sum(r["default_flag_count"] for r in stem_reports)
    total_near = sum(r["near_centroid_flags"] for r in stem_reports)
    return {
        "track": track,
        "num_stems": len(stem_reports),
        "total_default_flags": total_default,
        "total_near_centroid_flags": total_near,
        "suspected_fp_rate": round(total_near / total_default, 3) if total_default else 0.0,
        "stems": stem_reports,
    }


def main():
    out_dir = REPO / "artifacts" / "resonance_calibration_2026-07-16"
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for track, wav_dir in TRACKS.items():
        results.append(calibrate_track(track, wav_dir))

    # Aggregate sweep totals across all stems/tracks
    sweep_totals = {f"p{p}_per{pr}": 0 for p, pr in SWEEP}
    for r in results:
        for stem in r.get("stems", []):
            for k, v in stem["sweep_counts"].items():
                sweep_totals[k] += v

    summary = {
        "timestamp": datetime.now().isoformat(),
        "analysis_window_seconds": ANALYSIS_WINDOW_SECONDS,
        "sweep_grid": SWEEP,
        "sweep_totals_all_stems": sweep_totals,
        "tracks": results,
    }

    (out_dir / "resonance_calibration.json").write_text(json.dumps(summary, indent=2))

    print(f"\n{'='*70}\nSWEEP TOTALS (flags across ALL stems, all 3 tracks)\n{'='*70}")
    for (p, pr) in SWEEP:
        key = f"p{p}_per{pr}"
        tag = "  ← current default" if (p, pr) == (6.0, 0.4) else ""
        print(f"  prominence>={p:<4} persistence>={pr:<4} → {sweep_totals[key]:>4} flags{tag}")

    print("\nPer-track suspected false-positive rate (flags near centroid / total):")
    for r in results:
        if "suspected_fp_rate" in r:
            print(f"  {r['track']:<16} {r['total_default_flags']:>3} flags, "
                  f"~{r['suspected_fp_rate']*100:.0f}% near-centroid (suspect musical)")

    print(f"\nSaved: {out_dir / 'resonance_calibration.json'}")


if __name__ == "__main__":
    main()
