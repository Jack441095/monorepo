"""Track F - Resonance vs musical harmonic discrimination with near-miss discipline."""
import os
import sys
import json
import numpy as np
from scipy import signal as sps

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from lab import synth as S, features as F  # noqa: E402
from lab.registry import save_json, LAB_ROOT  # noqa: E402

SR = 48000
DUR = 1.0
N = int(DUR * SR)


def tone_with_peak(f0, peak_f, peak_q_db=18.0, persistent=True, seed=0, dur=DUR):
    n = int(dur * SR)
    t = np.arange(n) / SR
    g = S.rng(seed)
    x = np.sin(2 * np.pi * f0 * t) + 0.5 * np.sin(2 * np.pi * 2 * f0 * t) + 0.3 * np.sin(2 * np.pi * 3 * f0 * t)
    x += 0.02 * g.standard_normal(n)
    b, a = sps.iirpeak(peak_f, max(1.5, peak_q_db / 10), fs=SR)
    ring = sps.lfilter(b, a, 0.05 * g.standard_normal(n))
    if not persistent:
        env = np.ones(n)
        s = int(0.35 * SR)
        e = int(0.55 * SR)
        env[:s] = 0.0
        env[e:] = 0.0
        ring *= env
    return S._norm(x + 2.5 * ring)


def make_cases(seed):
    g = S.rng(seed)
    cases = []
    for f0 in [110.0, 146.83, 196.0, 220.0]:
        k = int(g.integers(3, 7))
        cases.append({"kind": "true_resonance", "label": "resonance",
                      "sig": tone_with_peak(f0, f0 * (k + 0.37), persistent=True, seed=seed * 10 + int(f0))})
        cases.append({"kind": "musical_harmonic", "label": "healthy_near_miss",
                      "sig": tone_with_peak(f0, f0 * k, persistent=True, seed=seed * 10 + int(f0) + 1)})
        cases.append({"kind": "temporary_peak", "label": "healthy_temporary",
                      "sig": tone_with_peak(f0, f0 * (k + 0.41), persistent=False, seed=seed * 10 + int(f0) + 2)})
    cases.append({"kind": "balanced_tone", "label": "healthy_control",
                  "sig": S.harmonic_tone(SR, DUR, 220.0, amps=(1, 0.4, 0.2, 0.1), seed=seed + 50)})
    cases.append({"kind": "filtered_noise", "label": "healthy_control",
                  "sig": S.noise_burst(SR, DUR, decay=10.0, lp=4000, hp=200, seed=seed + 60)})
    return cases


def detect(sig):
    peaks = F.spectral_peaks(sig, SR, n_fft=8192, prominence_db=10.0)
    if not peaks:
        return {"flag": False, "reason": "no_peaks", "persistence": 0.0}
    f0 = F.estimate_f0_autocorr(sig, SR, 50, 1000)
    best = None
    for f_pk, mag_db, prom in sorted(peaks, key=lambda p: -p[2])[:5]:
        pers = F.peak_persistence(sig, SR, f_pk, tol_frac=0.03, n_fft=4096, hop=1024)
        width_hz = None
        spec = 20 * np.log10(np.abs(np.fft.rfft(sig, 16384)) + 1e-12)
        freqs = np.fft.rfftfreq(16384, 1 / SR)
        i0 = int(np.argmin(np.abs(freqs - f_pk)))
        thr = spec[i0] - 3
        lo = i0
        while lo > 0 and spec[lo] > thr:
            lo -= 1
        hi = i0
        while hi < len(spec) - 1 and spec[hi] > thr:
            hi += 1
        width_hz = float(freqs[hi] - freqs[lo])
        is_harmonic = False
        if f0:
            ratio = f_pk / f0
            if abs(ratio - round(ratio)) < 0.06 and round(ratio) >= 1:
                is_harmonic = True
        cand = {"f": f_pk, "prom": prom, "persistence": pers, "width_hz": width_hz,
                "is_harmonic": is_harmonic,
                "score_no_harm_check": pers * min(prom / 20.0, 1.5),
                "score_full": (pers * min(prom / 20.0, 1.5)) * (0.15 if is_harmonic else 1.0)}
        if best is None or cand["score_full"] > best["score_full"]:
            best = cand
    flag_naive = bool(best["score_no_harm_check"] > 0.45 and best["persistence"] > 0.6)
    flag_full = bool(best["score_full"] > 0.45 and best["persistence"] > 0.6 and not best["is_harmonic"])
    return {"flag_naive_persistence_only": flag_naive, "flag_full_harmonicity": flag_full,
            "best_peak": best, "f0_est": f0}


def main():
    results = []
    for seed in range(25):
        for case in make_cases(300 + seed):
            d = detect(case["sig"])
            results.append({"seed": seed, "kind": case["kind"], "label": case["label"],
                            "flag_naive": d.get("flag_naive_persistence_only", False),
                            "flag_full": d.get("flag_full_harmonicity", False),
                            "persistence": d.get("best_peak", {}).get("persistence", 0.0),
                            "is_harmonic": d.get("best_peak", {}).get("is_harmonic", None)})

    def perf(key):
        out = {}
        for lab in ["resonance", "healthy_near_miss", "healthy_temporary", "healthy_control"]:
            sel = [r[key] for r in results if r["label"] == lab]
            out[lab] = round(float(np.mean(sel)), 3) if sel else None
        return out

    naive_perf = perf("flag_naive")
    full_perf = perf("flag_full")
    out = {
        "benchmark_id": "RESONANCE_BENCH_1.0",
        "n_cases": len(results),
        "flag_rate_by_label_naive_persistence_only": naive_perf,
        "flag_rate_by_label_full_detector": full_perf,
        "interpretation": {
            "resonance_recall_full": naive_perf and full_perf,
        },
    }
    save_json(os.path.join(LAB_ROOT, "results", "track_f_resonance_results.json"), out)
    lines = [
        "# Track F - Resonance vs Harmonics RESONANCE_BENCH_1.0",
        "",
        "| Label | Naive persistence-only flag rate | Full (harmonicity-aware) flag rate | Desired |",
        "|---|---|---|---|",
    ]
    desired = {"resonance": "FLAG", "healthy_near_miss": "no-flag", "healthy_temporary": "no-flag", "healthy_control": "no-flag"}
    for lab in ["resonance", "healthy_near_miss", "healthy_temporary", "healthy_control"]:
        lines.append(f"| {lab} | {naive_perf[lab]} | {full_perf[lab]} | {desired[lab]} |")
    lines += [
        "",
        "Near-miss FP reduction from harmonicity check: "
        f"{naive_perf['healthy_near_miss'] - full_perf['healthy_near_miss']:+.3f}",
    ]
    with open(os.path.join(LAB_ROOT, "results", "track_f_resonance_report.md"), "w") as f:
        f.write("\n".join(lines))
    print("naive:", naive_perf, "full:", full_perf)


if __name__ == "__main__":
    main()
