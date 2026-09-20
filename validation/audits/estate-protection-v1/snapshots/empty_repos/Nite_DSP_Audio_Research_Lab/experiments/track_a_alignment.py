"""Track A — Layer alignment: methods, ground truth, abstention, sweeps."""
import os
import sys
import json
import numpy as np
from scipy import signal as sps
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from lab import synth as S, features as F  # noqa: E402
from lab.registry import save_json, register_experiment, stats, LAB_ROOT  # noqa: E402

SR = 48000
DUR = 0.35
MAX_MS = 12.0


def frac_delay(x, delay_ms):
    d = delay_ms * SR / 1000.0
    n = np.arange(len(x))
    if abs(d) < 1e-9:
        return x.copy()
    base = int(np.floor(d))
    frac = d - base
    taps = np.arange(-16, 17)
    acc = np.zeros_like(x)
    for t in taps:
        idx = n - base - t
        valid = (idx >= 0) & (idx < len(x))
        w = 0.5 * (1 + np.cos(np.pi * t / 16.0))
        acc[valid] += x[idx[valid]] * w * np.sinc(t + frac)
    return acc


def make_layer(family, seed, variant):
    g = {
        "kick": lambda: S.kick(SR, DUR, f_start=100 + 30 * variant, f_end=42 + 8 * variant,
                               decay=0.18 + 0.06 * variant, click=0.3, seed=seed),
        "snare": lambda: S.snare(SR, DUR, tone_f=170 + 40 * variant, noise_mix=0.55 + 0.15 * variant,
                                  decay=0.11 + 0.05 * variant, seed=seed),
        "bass": lambda: S.bass_note(SR, DUR, 45 + 12 * variant, sustain=False, decay=0.22,
                                     sub=0.5, seed=seed),
        "tom": lambda: S.kick(SR, DUR, f_start=180 + 60 * variant, f_end=90 + 20 * variant,
                               decay=0.22, click=0.1, seed=seed),
        "perc": lambda: S.noise_burst(SR, DUR, decay=0.07 + 0.03 * variant, lp=None,
                                       hp=1500 + 800 * variant, seed=seed),
    }[family]()
    return g


FILTERS = {
    "none": None,
    "lp200": ("lowpass", 220),
    "hp2k": ("highpass", 2000),
    "bp1k4k": ("bandpass", (900, 4200)),
}


def apply_filter(x, spec):
    if spec is None:
        return x
    kind, fc = spec
    return S.filter_signal(x, SR, kind, fc)


def aligned_case(family_a, family_b, seed, delay_ms, polarity, filt_key, snr_db, level_db):
    a = make_layer(family_a, seed, 0)
    b = make_layer(family_b, seed + 7777, 1)
    b = apply_filter(b, FILTERS[filt_key])
    b = b / (np.max(np.abs(b)) + 1e-12) * (np.max(np.abs(a)) * 10 ** (level_db / 20))
    if snr_db is not None:
        g = S.rng(seed + 99)
        b = b + g.standard_normal(len(b)) * np.max(np.abs(b)) * 10 ** (-snr_db / 20)
    b = polarity * frac_delay(b, delay_ms)
    return a, b, {"delay_ms_true": delay_ms, "polarity_true": polarity}


def control_case(kind, seed):
    n = int(DUR * SR)
    if kind == "different_instruments":
        a = S.pad_chord(SR, DUR, [110, 165, 220], seed=seed)
        b = S.noise_burst(SR, DUR, decay=0.02, hp=3000, seed=seed + 5)
    elif kind == "decorrelated_noise":
        a = S.rng(seed).standard_normal(n) * 0.1
        b = S.rng(seed + 31).standard_normal(n) * 0.1
    elif kind == "reverb_tail":
        a = S.kick(SR, DUR, seed=seed)
        tail = S.reverb_tail(SR, DUR, decay=0.5, channels=1, pre_delay_s=0.05, seed=seed)[:, 0] * 0.6
        b = tail
    elif kind == "loose_double":
        a = make_layer("snare", seed, 0)
        jit = S.rng(seed + 3).uniform(8, 25)
        b = frac_delay(make_layer("snare", seed + 41, 0), float(jit)) * 0.8
    elif kind == "freq_dependent":
        a = make_layer("snare", seed, 0)
        lo = S.filter_signal(a, SR, "lowpass", 500)
        hi = S.filter_signal(a, SR, "highpass", 2000)
        hi = frac_delay(hi, 4.0)
        b = lo * 0.7 + hi * 0.7
        b = b / (np.max(np.abs(b)) + 1e-12) * np.max(np.abs(a))
    elif kind == "healthy_pair_zero":
        a = make_layer("kick", seed, 0)
        b = make_layer("kick", seed + 13, 1)
    else:
        raise ValueError(kind)
    return a, b, {"control_kind": kind}


# ---- estimators -------------------------------------------------------------


def est_cc(a, b):
    lag, peak, sharp = F.cross_correlation_lag(a, b, SR, MAX_MS)
    ms = lag * 1000.0 / SR
    pol = 1.0 if peak >= 0 else -1.0
    conf = min(abs(peak), 1.0)
    return ms, pol, conf, {"peak_norm": peak, "sharpness": sharp}


def est_gcc(a, b):
    lag, peak, ratio = F.gcc_phat_lag(a, b, SR, MAX_MS)
    ms = lag * 1000.0 / SR
    pol = 1.0 if peak >= 0 else -1.0
    return ms, pol, min(ratio / 10.0, 1.0), {"ratio": ratio}


BANDS = ((20, 120), (120, 400), (400, 1200), (1200, 3500), (3500, 9000))


def _band_lags(a, b):
    lags = []
    weights = []
    for lo, hi in BANDS:
        sos_lo = sps.iirfilter(4, max(lo, 1.0) / (SR / 2), btype="highpass", output="sos") if lo > 20 else None
        sos_hi = sps.iirfilter(4, hi / (SR / 2), btype="lowpass", output="sos")
        fa = sps.sosfilt(sos_hi, a)
        fb = sps.sosfilt(sos_hi, b)
        if sos_lo is not None:
            fa = sps.sosfilt(sos_lo, fa)
            fb = sps.sosfilt(sos_lo, fb)
        ea = np.sum(fa * fa)
        eb = np.sum(fb * fb)
        if ea < 1e-8 or eb < 1e-8:
            continue
        lag, peak, sharp = F.cross_correlation_lag(fa, fb, SR, MAX_MS)
        if abs(lag) > MAX_MS * SR / 1000:
            continue
        lags.append(lag)
        weights.append(max(sharp, 1.01) * min(ea, eb) ** 0.25)
    return lags, weights


def est_multiband(a, b):
    lags, weights = _band_lags(a, b)
    info = {"n_bands": len(lags), "spread_ms": 0.0}
    if not lags:
        return 0.0, 1.0, 0.0, info
    med = float(np.median(lags))
    info["spread_ms"] = float((np.percentile(lags, 80) - np.percentile(lags, 20)) * 1000 / SR)
    ms = med * 1000.0 / SR
    _, peak, sharp = F.cross_correlation_lag(a, b, SR, MAX_MS)
    pol = 1.0 if peak >= 0 else -1.0
    conf = 1.0 / info["spread_ms"] if info["spread_ms"] > 0 else 1.0
    return ms, pol, min(conf, 1.0), info


def est_onset(a, b):
    _, flux_a = F.onset_envelope(a, SR)
    _, flux_b = F.onset_envelope(b, SR)
    m = min(len(flux_a), len(flux_b))
    lag, peak, sharp = F.cross_correlation_lag(flux_a[:m], flux_b[:m], SR / (1024 // 4), MAX_MS)
    sr_odf = SR / 256.0
    ms = lag * 1000.0 / sr_odf
    pol = 1.0
    conf = min(abs(peak), 1.0)
    return ms, pol, conf, {}


def est_cancel(a, b):
    a0 = a - a.mean()
    b0 = b - b.mean()
    xab = sps.correlate(a0, b0, mode="full", method="fft")
    mid = len(b0) - 1
    maxlag = int(MAX_MS * SR / 1000)
    lo, hi = max(0, mid - maxlag), min(len(xab), mid + maxlag + 1)
    seg = np.abs(xab[lo:hi])
    k = int(np.argmax(seg))
    peak_idx = lo + k
    pol = float(np.sign(xab[peak_idx])) or 1.0
    if 0 < peak_idx < len(xab) - 1:
        L, C, R = abs(xab[peak_idx - 1]), abs(xab[peak_idx]), abs(xab[peak_idx + 1])
        denom = L - 2 * C + R
        delta = 0.5 * (L - R) / denom if abs(denom) > 1e-20 else 0.0
        delta = float(np.clip(delta, -0.5, 0.5))
    else:
        delta = 0.0
    lag_samples = (peak_idx - mid) + delta
    ms_best = -lag_samples * 1000.0 / SR
    e_naive = np.sum(a0**2) + np.sum(b0**2) + 2 * np.sum(a0 * b0)
    x_at = float(xab[peak_idx]) * (1 - abs(delta)) + float(xab[peak_idx + int(np.sign(delta))]) * abs(delta) if delta != 0 and 0 < peak_idx < len(xab) - 1 else float(xab[peak_idx])
    e_best = np.sum(a0**2) + np.sum(b0**2) - 2 * abs(x_at)
    depth = (e_naive - e_best) / (e_naive + 1e-20)
    return float(ms_best), pol, float(depth), {"cancel_depth": float(depth)}


METHODS = {"cc": est_cc, "gcc_phat": est_gcc, "multiband": est_multiband,
           "onset": est_onset, "cancellation": est_cancel}


def oracle_sum_rms(a, b, delay_ms, pol):
    bs = frac_delay(b, -delay_ms)
    return F.rms_db(a + pol * bs)


def evaluate_case(job):
    kind = job["kind"]
    if kind == "aligned":
        a, b, gt = aligned_case(job["fa"], job["fb"], job["seed"], job["delay"], job["pol"], job["filt"], job["snr"], job["lvl"])
        truth = {"has_alignment": True, **gt}
    else:
        a, b, extra = control_case(job["ckind"], job["seed"])
        truth = {"has_alignment": False, "control_kind": job["ckind"], **extra}
    res = {"job": {k: v for k, v in job.items()}, "truth": truth, "methods": {}}
    unaligned = F.rms_db(a + b)
    oracle_gain = 0.0
    if truth["has_alignment"]:
        orac = oracle_sum_rms(a, b, truth["delay_ms_true"], truth["polarity_true"])
        oracle_gain = orac - unaligned
        truth["oracle_gain_db"] = float(oracle_gain)
    truth["unaligned_rms"] = float(unaligned)
    for name, fn in METHODS.items():
        try:
            ms, pol, conf, info = fn(a, b)
            corrected = F.rms_db(a + pol * frac_delay(b, ms)) if abs(ms) <= MAX_MS else unaligned
            gain = corrected - unaligned
            err_ms = abs(ms - (-truth["delay_ms_true"])) if truth["has_alignment"] else None
            pol_ok = (pol == truth["polarity_true"]) if truth["has_alignment"] else None
            res["methods"][name] = {
                "est_ms": float(ms), "est_pol": float(pol), "conf": float(conf),
                "gain_db": float(gain), "err_ms": err_ms, "pol_ok": pol_ok, **info,
            }
        except Exception as e:
            res["methods"][name] = {"error": str(e)}
    return res


def build_jobs():
    jobs = []
    delays = [-10, -5, -2, -1, -0.5, -0.25, -0.1, 0.1, 0.25, 0.5, 1, 2, 5, 10]
    fam_pairs = [("kick", "kick"), ("kick", "bass"), ("snare", "perc"), ("tom", "kick"), ("bass", "bass")]
    for fa, fb in fam_pairs:
        for seed in range(4):
            for d in delays:
                for pol in (1, -1):
                    for filt in ("none", "lp200", "hp2k", "bp1k4k"):
                        for snr, lvl in ((None, 0), (20, 0), (10, 0), (None, -9)):
                            jobs.append({"kind": "aligned", "fa": fa, "fb": fb, "seed": seed + 10,
                                         "delay": d, "pol": pol, "filt": filt, "snr": snr, "lvl": lvl})
    controls = ["different_instruments", "decorrelated_noise", "reverb_tail",
                "loose_double", "freq_dependent", "healthy_pair_zero"]
    for ckind in controls:
        for seed in range(60):
            jobs.append({"kind": "control", "ckind": ckind, "seed": 500 + seed})
    return jobs


def main():
    jobs = build_jobs()
    print(f"cases: {len(jobs)}", flush=True)
    raw_path = os.path.join(LAB_ROOT, "results", "track_a_raw.jsonl")
    done_ids = set()
    if os.path.exists(raw_path):
        with open(raw_path) as f:
            for line in f:
                try:
                    r = json.loads(line)
                    done_ids.add(json.dumps(r["job"], sort_keys=True))
                except Exception:
                    pass
    jobs = [j for j in jobs if json.dumps(j, sort_keys=True) not in done_ids]
    print(f"remaining: {len(jobs)}", flush=True)
    n_done = 0
    with open(raw_path, "a") as sink, ProcessPoolExecutor(max_workers=6) as ex:
        for res in ex.map(evaluate_case, jobs, chunksize=8):
            sink.write(json.dumps(res) + "\n")
            n_done += 1
            if n_done % 250 == 0:
                sink.flush()
                print(f"progress {n_done}", flush=True)
    results = []
    with open(raw_path) as f:
        for line in f:
            results.append(json.loads(line))
    print(f"loaded {len(results)} results", flush=True)
    analyse(results)


def analyse(results):

    aligned = [r for r in results if r["truth"]["has_alignment"]]
    controls = [r for r in results if not r["truth"]["has_alignment"]]
    summary = {"n_aligned": len(aligned), "n_controls": len(controls), "methods": {}}

    for name in METHODS:
        errs = [r["methods"][name]["err_ms"] for r in aligned if "err_ms" in r["methods"][name]]
        gains = [r["methods"][name]["gain_db"] for r in results if "gain_db" in r["methods"][name]]
        pols = [r["methods"][name]["pol_ok"] for r in aligned if r["methods"][name].get("pol_ok") is not None]
        within_02 = float(np.mean([e <= 0.2 for e in errs]))
        within_05 = float(np.mean([e <= 0.5 for e in errs]))
        within_1 = float(np.mean([e <= 1.0 for e in errs]))
        summary["methods"][name] = {
            "abs_err_ms": stats(errs),
            "frac_within_0.2ms": within_02,
            "frac_within_0.5ms": within_05,
            "frac_within_1ms": within_1,
            "polarity_acc": float(np.mean(pols)),
            "mean_gain_db": stats(gains),
        }

    by_delay = {}
    aligned_delays = sorted({r["job"].get("delay") for r in aligned if r["job"].get("kind") == "aligned"})
    for name in METHODS:
        table = {}
        for d in aligned_delays:
            errs = [r["methods"][name]["err_ms"] for r in aligned
                    if r["job"].get("delay") == d and r["methods"][name].get("err_ms") is not None]
            table[str(d)] = round(float(np.median(errs)), 4) if errs else None
        by_delay[name] = table

    filt_perf = {}
    for name in METHODS:
        row = {}
        for fk in FILTERS:
            errs = [r["methods"][name]["err_ms"] for r in aligned
                    if r["job"].get("filt") == fk and r["methods"][name].get("err_ms") is not None]
            row[fk] = round(float(np.median(errs)), 4) if errs else None
        filt_perf[name] = row

    control_fp = {}
    for name in METHODS:
        row = {}
        for ck in sorted({r["truth"]["control_kind"] for r in controls}):
            gs = [r["methods"][name]["gain_db"] for r in controls if r["truth"]["control_kind"] == ck]
            row[ck] = {"median_gain_db": round(float(np.median(gs)), 3) if gs else None,
                       "intervened_frac": round(float(np.mean([g > 0.5 for g in gs])), 3) if gs else None}
        control_fp[name] = row

    util = {}
    for name in METHODS:
        rows = [(r["methods"][name]["conf"], r["methods"][name]["gain_db"], r["truth"]["has_alignment"]) for r in results]
        confs = [c for c, _, _ in rows]
        best_u, best_th = None, None
        for th in np.quantile(confs, np.linspace(0.05, 0.95, 37)):
            sel = rows if th <= min(confs) else [q for q in rows if q[0] >= th]
            hits = sum(1 for _, g, h in sel if h and g > 0.5)
            fps = sum(1 for _, g, h in sel if not h and g > 0.5)
            u = hits - 3 * fps
            if best_u is None or u > best_u:
                best_u, best_th = u, float(th)
        util[name] = {"best_threshold": best_th, "utility_hits_minus_3fp": best_u}

    out = {
        "benchmark_id": "ALIGN_BENCH_1.0",
        "sr": SR, "max_search_ms": MAX_MS,
        "n_cases_total": len(results),
        "summary_by_method": summary,
        "median_abs_err_by_true_delay_ms": by_delay,
        "median_abs_err_by_filter": filt_perf,
        "control_behaviour": control_fp,
        "abstention_utility_sweep": util,
    }
    save_json(os.path.join(LAB_ROOT, "results", "track_a_alignment_results.json"), out)

    lines = [
        "# Track A - Layer Alignment Benchmark ALIGN_BENCH_1.0",
        "",
        f"Cases: {len(results)} ({len(aligned)} with known offset/polarity ground truth; {len(controls)} no-alignment controls incl. healthy pairs)",
        "",
        "| Method | Median |err| ms | P95 |err| ms | <=0.2ms | <=1ms | Polarity acc | Mean gain dB |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, m in summary["methods"].items():
        e = m["abs_err_ms"]
        g = m["mean_gain_db"]
        lines.append(f"| {name} | {e['median']:.3f} | {e['p95']:.3f} | {m['frac_within_0.2ms']:.3f} | "
                     f"{m['frac_within_1ms']:.3f} | {m['polarity_acc']:.3f} | {g['mean']:.2f} |")
    lines += ["", "## Median |err| ms by true delay", ""]
    hdr = "| Method | " + " | ".join(by_delay["cc"].keys()) + " |"
    lines.append(hdr)
    lines.append("|" + "---|" * (len(by_delay["cc"]) + 1))
    for name, tbl in by_delay.items():
        lines.append("| " + name + " | " + " | ".join(str(v) for v in tbl.values()) + " |")
    lines += ["", "## Control behaviour (no-alignment cases)", "",
              "| Method | Control | median gain dB | intervened frac |", "|---|---|---|---|"]
    for name, row in control_fp.items():
        for ck, v in row.items():
            lines.append(f"| {name} | {ck} | {v['median_gain_db']} | {v['intervened_frac']} |")
    lines += ["", "## Abstention utility sweep (utility = correct improvements - 3x false interventions)", ""]
    for name, u in util.items():
        lines.append(f"- {name}: threshold={u['best_threshold']}, utility={u['utility_hits_minus_3fp']}")
    with open(os.path.join(LAB_ROOT, "results", "track_a_alignment_report.md"), "w") as f:
        f.write("\n".join(lines))

    reg_entry = {
        "experiment_id": "ALIGN_METHODS_1.0",
        "track": "A_layer_alignment",
        "research_question": "Can software reliably recommend layer timing/polarity alignment, and abstain when no meaningful alignment exists?",
        "hypothesis": "Cancellation-search and band-aware estimators beat naive full-band correlation on filtered/low-SNR layers; abstention via cancellation depth reduces false corrections.",
        "dataset": f"{len(results)} deterministic synthetic cases (5 layer-family pairs x 14 delays x 2 polarities x 4 filters x 4 SNR/level conds x 4 seeds; 360 controls incl. 60 healthy pairs)",
        "baseline": "full-band cross-correlation",
        "candidate": "GCC-PHAT, multi-band median, onset ODF, energy-cancellation search",
        "metrics": ["abs_err_ms distribution", "frac<=0.2/0.5/1ms", "polarity_acc", "gain_db after correction", "control intervention rate"],
        "status": "RUNNING_ANALYSIS",
        "artifacts": ["results/track_a_alignment_results.json", "results/track_a_alignment_report.md"],
        "limitations": "synthetic layers only; fractional-delay interpolation error floor ~0.02ms; no listening tests",
        "next_action": "analyse, ablate winner, replicate at 44.1k",
    }
    print("done", len(results))


if __name__ == "__main__":
    main()
