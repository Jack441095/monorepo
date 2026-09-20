"""Track B - Low-end intelligence: kick/bass interaction predictors vs constructed ground truth."""
import os
import sys
import json
import numpy as np
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from lab import synth as S, features as F  # noqa: E402
from lab.registry import save_json, stats, LAB_ROOT  # noqa: E402

SR = 48000
BEAT = 0.55
N_BEATS = 4
DUR = BEAT * N_BEATS

KICK_F = [40.0, 48.0, 56.0, 64.0]
BASS_F = [41.2, 46.25, 49.0, 55.0, 61.74, 65.41, 73.42]
ENVS = [("sustain", 0.30), ("decay", 0.15), ("decay", 0.35), ("decay", 0.70)]
TIMINGS = [0.0, 0.010, 0.025]
POLARITIES = [1, -1]
SIDECHAIN = ["none", "duck"]
PHASES = [0.0, 90.0, 180.0]
SEEDS = [0, 1]


_KICK_CACHE = {}


def get_kick(kf, seed):
    key = (kf, seed)
    if key not in _KICK_CACHE:
        dur = BEAT * 0.9
        n = int(dur * SR)
        t = np.arange(n) / SR
        click_n = min(int(0.008 * SR), n)
        g = S.rng(seed + 500 + int(kf))
        cl = np.zeros(n)
        c = g.standard_normal(click_n)
        c -= c.mean()
        cl[:click_n] = c / (np.max(np.abs(c)) + 1e-12)
        f = kf + (kf * 2.6 - kf) * np.exp(-t / 0.010)
        ph = 2 * np.pi * np.cumsum(f) / SR
        body = np.sin(ph) * np.exp(-t / 0.045)
        tail = np.sin(2 * np.pi * kf * t) * np.exp(-t / 0.30)
        x = body * 0.8 + tail * 0.9 + 0.22 * cl
        m = np.max(np.abs(x)) + 1e-12
        _KICK_CACHE[key] = x * 0.85 / m
    return _KICK_CACHE[key]


def build_pair(kick_f, bass_f, env_kind, decay, timing_s, pol, sidechain, phase_deg, seed):
    n = int(DUR * SR)
    kick = get_kick(kick_f, seed)
    bass_dur = BEAT * N_BEATS if env_kind == "sustain" else decay + 0.05
    bass_note = S.bass_note(SR, bass_dur, bass_f, sustain=(env_kind == "sustain"), decay=decay,
                            sub=0.55, seed=seed + 31)
    period_s = 1.0 / bass_f
    phase_shift_ms = phase_deg / 360.0 * period_s * 1000.0
    k_track = np.zeros(n)
    b_track = np.zeros(n)
    for i in range(N_BEATS):
        s = int((i * BEAT) * SR)
        seg = kick[: min(len(kick), n - s)]
        k_track[s:s + len(seg)] += seg
        bs = int((i * BEAT + timing_s) * SR)
        seg_b = bass_note[: min(len(bass_note), n - bs)] if i % 2 == 0 else None
        if env_kind == "sustain":
            if i == 0:
                seg_b = bass_note[: min(len(bass_note), n - bs)]
        if seg_b is not None:
            b_track[bs:bs + len(seg_b)] += seg_b
    if phase_shift_ms > 0:
        b_track = S.delay_signal(b_track, SR, phase_shift_ms)
    b_track *= pol

    def norm_rms(x, target_db=-14):
        r = np.sqrt(np.mean(x**2)) + 1e-12
        return x * (10 ** (target_db / 20) / r)

    k_track, b_track = norm_rms(k_track), norm_rms(b_track)
    if sidechain == "duck":
        duck = np.ones(n)
        for i in range(N_BEATS):
            s0 = int(i * BEAT * SR)
            d = int(0.14 * SR)
            e = min(n, s0 + d)
            duck[s0:e] = np.linspace(0.25, 1.0, e - s0)
        b_track *= duck
    g = S.rng(seed + 77)
    amb = g.standard_normal(n) * 0.0008
    return k_track, b_track + amb


def lowpass(x, fc=130):
    return S.filter_signal(x, SR, "lowpass", fc)


def analyse_case(args):
    (kf, bf, ek, dec, tms, pol, sc, ph, seed) = args
    k, b = build_pair(kf, bf, ek, dec, tms, pol, sc, ph, seed)
    mix = k + b
    kl, bl = lowpass(k), lowpass(b)

    W = 4096
    nf = min(len(kl), len(bl)) // W
    frame_loss = []
    sel_ea = []
    sel_es = []
    for w in range(nf):
        wa = kl[w * W:(w + 1) * W]
        wb = bl[w * W:(w + 1) * W]
        ea, eb = float(np.sum(wa**2)), float(np.sum(wb**2))
        m = max(ea, eb) + 1e-20
        if ea >= 0.06 * m and eb >= 0.06 * m:
            es = float(np.sum((wa + wb)**2))
            sel_ea.append(ea + eb)
            sel_es.append(es)
            frame_loss.append(10 * np.log10((ea + eb + 1e-20) / (es + 1e-20)))
    if sel_ea:
        ea_tot, es_tot = sum(sel_ea), sum(sel_es)
        cancel_loss_db = 10 * np.log10((ea_tot + 1e-20) / (es_tot + 1e-20))
    else:
        cancel_loss_db = 0.0
    cancel_loss_p95_db = float(np.percentile(frame_loss, 95)) if frame_loss else 0.0

    n_total = len(kl)
    beat_corrs = []
    for i in range(N_BEATS):
        s = int(i * BEAT * SR)
        e = min(n_total, s + int(0.30 * SR))
        wa, wb = kl[s:e], bl[s:e]
        ea, eb = float(np.sum(wa**2)), float(np.sum(wb**2))
        if ea < 1e-6 or eb < 1e-6:
            continue
        c = float(np.sum(wa * wb) / (np.sqrt(ea * eb) + 1e-20))
        beat_corrs.append(c)
    worst_beat_corr = float(np.min(beat_corrs)) if beat_corrs else 0.0
    corr0 = float(np.mean(beat_corrs)) if beat_corrs else 0.0

    from scipy.signal import correlate as _corr
    cc = _corr(kl[: len(bl)], bl, mode="full", method="fft")
    mid = len(bl) - 1
    maxlag = 240
    lo, hi = max(0, mid - maxlag), min(len(cc), mid + maxlag + 1)
    seg = cc[lo:hi]
    k_abs = int(np.argmax(np.abs(seg)))
    ea_full, eb_full = np.sum(kl**2), np.sum(bl**2)
    best_mag = float(seg[k_abs] / (np.sqrt(ea_full * eb_full) + 1e-20))
    best_lag = (lo + k_abs) - mid

    win = int(0.03 * SR)
    pre_levels = []
    for i in range(1, N_BEATS):
        s = int(i * BEAT * SR)
        pre = b[max(0, s - win):s]
        if len(pre) < 8:
            continue
        pre_levels.append(float(np.sqrt(np.mean(pre**2))) / (np.max(np.abs(b)) + 1e-9))
    bass_decay_overlap_frac = float(np.mean(pre_levels)) if pre_levels else 0.0
    pk_sum = F.peak_dbfs(mix)
    pk_parts = max(F.peak_dbfs(k), F.peak_dbfs(b))
    headroom_waste_db = float(pk_parts - pk_sum)
    nfft = 1 << 16
    fa_mix = np.abs(np.fft.rfft(mix, nfft))
    freqs = np.fft.rfftfreq(nfft, 1 / SR)
    band = (freqs >= min(kf, bf) * 0.94) & (freqs <= max(kf, bf) * 1.06)
    overlap_band_energy_frac = float(np.sum(fa_mix[band]**2) / (np.sum(fa_mix**2) + 1e-20))
    overlap_hz_lo, overlap_hi = float(min(kf, bf) * 0.94), float(max(kf, bf) * 1.06)

    mask_next_kick = bool(bass_decay_overlap_frac > 0.10)
    cancellation_problem = bool(cancel_loss_db >= 3.0 or cancel_loss_p95_db >= 3.0 or worst_beat_corr <= -0.4)
    headroom_problem = bool(headroom_waste_db >= 4.0)
    any_problem = bool(cancellation_problem or mask_next_kick or headroom_problem)
    healthy = not any_problem
    return {
        "params": {"kick_f": kf, "bass_f": bf, "env": ek, "decay": dec, "timing_ms": tms * 1000,
                   "pol": pol, "sidechain": sc, "phase_deg": ph, "seed": seed},
        "meas": {"cancel_loss_db": float(cancel_loss_db), "cancel_loss_p95_db": cancel_loss_p95_db,
                 "corr0_lo": float(corr0), "worst_beat_corr_lo": worst_beat_corr,
                 "best_abs_corr_lo": best_mag, "best_lag_samples": int(best_lag),
                 "n_interaction_frames": len(sel_ea),
                 "bass_pre_onset_level": bass_decay_overlap_frac,
                 "headroom_waste_db": headroom_waste_db,
                 "overlap_band_energy_frac": overlap_band_energy_frac,
                 "overlap_band_hz": [overlap_hz_lo, overlap_hi]},
        "labels": {"cancellation": cancellation_problem, "mask_next_kick": mask_next_kick,
                   "headroom_waste": headroom_problem, "any_problem": any_problem,
                   "healthy_control": healthy},
    }


def build_jobs():
    jobs = []
    for kf in KICK_F:
        for bf in BASS_F:
            for ek, dec in ENVS:
                for tms in TIMINGS:
                    for pol in POLARITIES:
                        for sc in SIDECHAIN:
                            for ph in PHASES:
                                for seed in SEEDS:
                                    jobs.append((kf, bf, ek, dec, tms, pol, sc, ph, seed))
    return jobs


def roc_auc(scores, labels):
    scores = np.asarray(scores, float)
    labels = np.asarray(labels, bool)
    if labels.all() or (~labels).all():
        return None
    order = np.argsort(scores)
    ranks = np.empty_like(order, dtype=float)
    ranks[order] = np.arange(1, len(scores) + 1)
    pos = ranks[labels].sum()
    n_pos, n_neg = labels.sum(), (~labels).sum()
    auc = (pos - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)
    return float(auc)


def main():
    jobs = build_jobs()
    print(f"cases: {len(jobs)}", flush=True)
    raw_path = os.path.join(LAB_ROOT, "results", "track_b_raw.jsonl")
    done = set()
    if os.path.exists(raw_path):
        with open(raw_path) as f:
            for line in f:
                try:
                    done.add(json.dumps(json.loads(line)["params"], sort_keys=True))
                except Exception:
                    pass
    jobs = [j for j in jobs if json.dumps(j[0] and {
        "kick_f": j[0], "bass_f": j[1], "env": j[2], "decay": j[3], "timing_ms": j[4] * 1000,
        "pol": j[5], "sidechain": j[6], "phase_deg": j[7], "seed": j[8]}, sort_keys=True) not in done]
    print(f"remaining: {len(jobs)}", flush=True)
    n = 0
    with open(raw_path, "a") as sink, ProcessPoolExecutor(max_workers=2) as ex:
        for res in ex.map(analyse_case, jobs, chunksize=32):
            sink.write(json.dumps(res) + "\n")
            n += 1
            if n % 500 == 0:
                sink.flush()
                print(f"progress {n}", flush=True)
    results = []
    with open(raw_path) as f:
        results = [json.loads(line) for line in f]
    summarise(results)


def summarise(results):
    m = [r["meas"] for r in results]
    L = [r["labels"] for r in results]

    def auc_for(feature_scores, label_key, invert=False):
        vals = [(-s if invert else s) for s in feature_scores]
        labs = [r[label_key] for r in L]
        return roc_auc(vals, labs)

    out = {
        "benchmark_id": "LOWEND_BENCH_1.0",
        "n_cases": len(results),
        "label_rates": {k: round(float(np.mean([r[k] for r in L])), 4) for k in L[0]},
        "auc": {},
    }
    feats = {
        "cancel_loss_db_direct_measure": (m, "cancel_loss_db", False),
        "lowband_zero_lag_corr_inverted": ([x["corr0_lo"] for x in m], "cancellation", True),
        "lowband_best_abs_corr": ([x["best_abs_corr_lo"] for x in m], "cancellation", False),
        "bass_pre_onset_level": ([x["bass_pre_onset_level"] for x in m], "mask_next_kick", False),
        "headroom_waste_db": ([x["headroom_waste_db"] for x in m], "headroom_waste", False),
    }
    for name, (vals, label, inv) in feats.items():
        out["auc"][name] = auc_for(vals, label, inv)

    healthy_idx = [i for i, r in enumerate(L) if r["healthy_control"]]
    out["healthy_controls_n"] = len(healthy_idx)
    out["healthy_fraction"] = round(len(healthy_idx) / len(results), 4)
    out["false_intervention_rate_if_always_fire"] = round(float(np.mean([not r["any_problem"] for r in L])), 4)

    cl = [x["cancel_loss_db"] for x in m]
    out["cancel_loss_db_stats"] = stats(cl)
    strong_cancel = [x["corr0_lo"] for x, l in zip(m, L) if l["cancellation"]]
    weak_cancel = [x["corr0_lo"] for x, l in zip(m, L) if l["headroom_waste"] or l["mask_next_kick"]]
    clean = [x["corr0_lo"] for x, l in zip(m, L) if not (l["cancellation"] or l["headroom_waste"] or l["mask_next_kick"])]
    out["corr0_lo_by_label"] = {
        "cancellation_cases": stats(strong_cancel),
        "other_problem_cases": stats(weak_cancel),
        "no_problem_cases": stats(clean),
    }
    rule_fp = float(np.mean([x["corr0_lo"] < -0.25 for x, l in zip(m, L) if not l["cancellation"]]))
    rule_tp = float(np.mean([x["corr0_lo"] < -0.25 for x, l in zip(m, L) if l["cancellation"]]))
    out["simple_rule_corr_lt_-0.25"] = {"recall": rule_tp, "false_positive_rate": rule_fp}

    save_json(os.path.join(LAB_ROOT, "results", "track_b_lowend_results.json"), out)
    lines = [
        "# Track B - Low-End Intelligence LOWEND_BENCH_1.0",
        "",
        f"Cases: {len(results)}; healthy controls: {out['healthy_fraction']:.0%}",
        "",
        "| Predictor | Label | AUC |",
        "|---|---|---|",
    ]
    for name, a in out["auc"].items():
        lines.append(f"| {name} | {'-'} | {a if a is not None else 'n/a'} |")
    lines += [
        "",
        f"Cancellation loss dB: median {out['cancel_loss_db_stats']['median']:.2f}, p95 {out['cancel_loss_db_stats']['p95']:.2f}",
        "",
        f"Rule 'low-band zero-lag corr < -0.25 predicts cancellation': recall={rule_tp:.3f}, FP rate={rule_fp:.3f}",
        "",
        "## corr0_lo distributions",
        "",
        "| Subset | n | mean | p05 | p95 |",
        "|---|---|---|---|---|",
    ]
    for key, st in out["corr0_lo_by_label"].items():
        if st.get("n"):
            lines.append(f"| {key} | {st['n']} | {st['mean']:.3f} | {st['p05']:.3f} | {st['p95']:.3f} |")
    with open(os.path.join(LAB_ROOT, "results", "track_b_lowend_report.md"), "w") as f:
        f.write("\n".join(lines))
    print("track B analysis written", flush=True)


if __name__ == "__main__":
    main()
