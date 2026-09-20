"""Track E - Stereo/phase intelligence: false-positive robustness of width/correlation detectors."""
import os
import sys
import json
import numpy as np
from scipy import signal as sps

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from lab import synth as S, features as F  # noqa: E402
from lab.registry import save_json, stats, LAB_ROOT  # noqa: E402

SR = 48000
DUR = 1.0
N = int(DUR * SR)


def bandpass(x, lo, hi):
    sos = sps.butter(4, [max(lo, 20) / (SR / 2), min(hi, SR / 2 - 100) / (SR / 2)], "bandpass", output="sos")
    return sps.sosfilt(sos, x)


def haas_widen(mono, delay_ms=12.0):
    d = int(delay_ms * SR / 1000)
    l = np.zeros(N)
    r = np.zeros(N)
    l[: N] = mono
    r[d:] = mono[: N - d]
    return np.stack([l, r], axis=1)


def make_cases(seed):
    g = S.rng(seed)
    cases = []
    kickm = S.kick(SR, DUR, seed=seed)
    bassm = S.bass_note(SR, DUR, 55.0, sustain=True, seed=seed + 1)
    padm = S.pad_chord(SR, DUR, [220, 277, 330], seed=seed + 2)
    reverb = S.reverb_tail(SR, DUR, decay=0.6, channels=2, seed=seed + 3)

    def norm(x, pk=0.5):
        return x / (np.max(np.abs(x)) + 1e-12) * pk

    kickm, bassm, padm = map(norm, (kickm, bassm, padm))
    reverb = reverb / (np.max(np.abs(reverb)) + 1e-12) * 0.25

    st_pad = np.stack([padm, np.roll(padm, int(0.0004 * SR))], axis=1)

    cases.append({"kind": "side_heavy_bass", "label": "problem", "sig": np.stack([bassm, np.zeros(N)], axis=1)})
    cases.append({"kind": "antiphase_lowband", "label": "problem",
                  "sig": np.stack([bandpass(kickm, 30, 150), -bandpass(kickm, 30, 150)], axis=1) + np.stack([padm * 0.3, padm * 0.3], axis=1)})
    cases.append({"kind": "bass_only_right_55hz", "label": "problem",
                  "sig": np.stack([kickm * 0.8, kickm * 0.8], axis=1) + np.stack([np.zeros(N), bassm], axis=1)})
    cases.append({"kind": "haas_widened_guitar", "label": "healthy",
                  "sig": haas_widen(S.harmonic_tone(SR, DUR, 330, seed=seed + 5))})
    cases.append({"kind": "wide_reverb_return", "label": "healthy", "sig": reverb})
    cases.append({"kind": "detuned_wide_pad", "label": "healthy", "sig": st_pad})
    cases.append({"kind": "narrow_kick_bass_mono", "label": "healthy",
                  "sig": np.stack([kickm + bassm, kickm + bassm], axis=1)})
    cases.append({"kind": "slight_balance_offset", "label": "healthy",
                  "sig": np.stack([padm * 1.06, padm * 0.94], axis=1)})
    return cases


def analyse(sig):
    m = F.stereo_metrics(sig)
    l, r = sig[:, 0], sig[:, 1]
    mono = sig.mean(axis=1)
    total_e = float(np.sum(l**2 + r**2)) + 1e-20
    band_info = {}
    for name, (lo, hi) in {"sub": (20, 120), "low": (120, 400), "mid": (400, 2000), "high": (2000, 16000)}.items():
        lb, rb = bandpass(l, lo, hi), bandpass(r, lo, hi)
        el, er = float(np.sum(lb**2)), float(np.sum(rb**2))
        active = (el + er) / 2 >= 10 ** (-45 / 10) * total_e / 2
        denom = np.sqrt(el * er) + 1e-20
        c = float(np.sum(lb * rb) / denom) if min(el, er) > 1e-12 else None
        side = (lb - rb) / 2
        mid = (lb + rb) / 2
        side_ratio = float(np.sum(side**2) / (np.sum(side**2) + np.sum(mid**2) + 1e-20))
        spec = np.abs(np.fft.rfft(side * np.hanning(len(side)), 8192)) + 1e-15
        freqs_side = np.fft.rfftfreq(8192, 1 / SR)
        m_sub = (freqs_side >= lo) & (freqs_side <= hi)
        p = spec[m_sub]
        if len(p) > 4 and np.sum(p) > 1e-12:
            flatness = float(np.exp(np.mean(np.log(p))) / np.mean(p))
            tonality_prom_db = -10 * np.log10(flatness + 1e-12)
        else:
            tonality_prom_db = 0.0
        band_info[name] = {"corr": c, "active": bool(active), "side_ratio": side_ratio,
                           "tonality_prom_db": tonality_prom_db,
                           "collapse_db": float(10 * np.log10(((el + er) / 2 + 1e-20) / (np.sum(bandpass(mono, lo, hi)**2) + 1e-20)))}
    sub = band_info["sub"]
    naive_flag = bool(m["correlation"] < 0.2)
    lb_full = bandpass(l, 20, 120)
    rb_full = bandpass(r, 20, 120)
    el, er = float(np.sum(lb_full**2)), float(np.sum(rb_full**2))
    sub_active = (el + er) >= 10 ** (-40 / 10)
    side_sig = lb_full - rb_full
    side_f0 = F.estimate_f0_autocorr(side_sig, SR, 30.0, 200.0) if np.max(np.abs(side_sig)) > 1e-4 else None
    flag_antiphase = bool(sub_active and sub["corr"] is not None and sub["corr"] < -0.5)
    flag_one_sided = bool(sub_active and min(el, er) < 0.05 * max(el, er))
    flag_tonal_side = bool(sub_active and sub["side_ratio"] > 0.25 and side_f0 is not None)
    bandaware_flag = bool(flag_antiphase or flag_one_sided or flag_tonal_side)
    reason = "+".join(r for r, v in (("antiphase", flag_antiphase), ("one_sided", flag_one_sided),
                                     ("tonal_side", flag_tonal_side)) if v)
    return {
        "broadband_corr": m["correlation"],
        "mono_loss_db": m["mono_loss_db"],
        "band_detail": band_info,
        "naive_detector_flag": naive_flag,
        "bandaware_detector_flag": bandaware_flag,
        "flag_reason": reason,
        "side_f0_est_hz": side_f0,
    }


def main():
    results = []
    for seed in range(40):
        for case in make_cases(100 + seed):
            r = {"seed": seed, "kind": case["kind"], "label": case["label"]}
            r.update(analyse(case["sig"]))
            results.append(r)

    def perf(det_key):
        tp = sum(1 for r in results if r[det_key] and r["label"] == "problem")
        fp = sum(1 for r in results if r[det_key] and r["label"] == "healthy")
        fn = sum(1 for r in results if not r[det_key] and r["label"] == "problem")
        tn = sum(1 for r in results if not r[det_key] and r["label"] == "healthy")
        return {"recall": round(tp / max(tp + fn, 1), 3), "false_positive_rate": round(fp / max(fp + tn, 1), 3),
                "tp": tp, "fp": fp, "fn": fn, "tn": tn}

    fp_by_kind_naive = {}
    fp_by_kind_band = {}
    for r in results:
        if r["label"] == "healthy":
            fp_by_kind_naive.setdefault(r["kind"], []).append(int(r["naive_detector_flag"]))
            fp_by_kind_band.setdefault(r["kind"], []).append(int(r["bandaware_detector_flag"]))

    out = {
        "benchmark_id": "STEREO_BENCH_1.0",
        "n_cases": len(results),
        "healthy_fraction": round(float(np.mean([r["label"] == "healthy" for r in results])), 3),
        "naive_broadband_corr_detector": perf("naive_detector_flag"),
        "bandaware_side_sub_detector": perf("bandaware_detector_flag"),
        "healthy_false_positives_by_kind": {
            k: {"naive_rate": round(float(np.mean(v)), 3), "bandaware_rate": round(float(np.mean(fp_by_kind_band[k])), 3)}
            for k, v in fp_by_kind_naive.items()},
        "problem_recall_by_kind": {},
    }
    for kind in sorted({r["kind"] for r in results if r["label"] == "problem"}):
        sel = [r for r in results if r["kind"] == kind]
        out["problem_recall_by_kind"][kind] = {
            "naive": round(float(np.mean([r["naive_detector_flag"] for r in sel])), 3),
            "bandaware": round(float(np.mean([r["bandaware_detector_flag"] for r in sel])), 3)}
    save_json(os.path.join(LAB_ROOT, "results", "track_e_stereo_results.json"), out)
    lines = [
        "# Track E - Stereo/Phase Intelligence STEREO_BENCH_1.0",
        "",
        f"Cases: {len(results)} (healthy fraction {out['healthy_fraction']:.0%})",
        "",
        "| Detector | Recall | Healthy FP rate |",
        "|---|---|---|",
        f"| Naive broadband corr<0.2 | {out['naive_broadband_corr_detector']['recall']} | {out['naive_broadband_corr_detector']['false_positive_rate']} |",
        f"| Band-aware side/sub detector | {out['bandaware_side_sub_detector']['recall']} | {out['bandaware_side_sub_detector']['false_positive_rate']} |",
        "",
        "## Healthy-case false positives by construction kind",
        "",
        "| Case | Naive FP | Band-aware FP |",
        "|---|---|---|",
    ]
    for k, v in out["healthy_false_positives_by_kind"].items():
        lines.append(f"| {k} | {v['naive_rate']} | {v['bandaware_rate']} |")
    lines += ["", "## Problem-case recall by kind", ""]
    for k, v in out["problem_recall_by_kind"].items():
        lines.append(f"- {k}: naive={v['naive']} bandaware={v['bandaware']}")
    with open(os.path.join(LAB_ROOT, "results", "track_e_stereo_report.md"), "w") as f:
        f.write("\n".join(lines))
    print(json.dumps(out["naive_broadband_corr_detector"]), json.dumps(out["bandaware_side_sub_detector"]))


if __name__ == "__main__":
    main()
