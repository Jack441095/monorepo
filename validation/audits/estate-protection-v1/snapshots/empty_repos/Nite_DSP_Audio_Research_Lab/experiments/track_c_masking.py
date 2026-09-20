"""Track C - Masking intelligence: TF critical-band features vs static overlap, benign vs problematic."""
import os
import sys
import json
import numpy as np
from scipy import signal as sps
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from lab import synth as S, features as F  # noqa: E402
from lab.registry import save_json, LAB_ROOT  # noqa: E402

SR = 48000
DUR = 1.2
N = int(DUR * SR)

RATIOS = [1.0, 1.122, 1.189, 1.335, 1.498, 2.0]
LEVEL_DIFFS = [-12, -6, 0, 6]
OVERLAPS = ["full", "alternating", "offset50"]
MASKEE_KINDS = ["lead", "vocal", "pluck"]
MASKER_KINDS = ["pad", "swell", "arp"]
SEEDS = [0, 1, 2]


def hz2bark(f):
    return 13 * np.arctan(0.00076 * f) + 3.5 * np.arctan((f / 7500.0) ** 2)


def make_maskee(kind, f0, seed):
    if kind == "lead":
        x = S.harmonic_tone(SR, DUR, f0, amps=(1, 0.55, 0.4, 0.28, 0.18, 0.12), seed=seed)
    elif kind == "vocal":
        base = S.harmonic_tone(SR, DUR, f0, amps=(1, 0.7, 0.5, 0.42, 0.3, 0.22, 0.15, 0.1), seed=seed)
        vib = 1 + 0.004 * np.sin(2 * np.pi * 5.2 * np.arange(N) / SR)
        t = np.arange(N) / SR
        x = S.harmonic_tone(SR, DUR, f0, amps=(1, 0.7, 0.5, 0.42, 0.3, 0.22), seed=seed) * (0.8 + 0.2 * np.sin(2 * np.pi * 4.7 * t))
        f1 = sps.butter(2, [f0 * 1.6 / (SR / 2), f0 * 2.4 / (SR / 2)], "bandpass", output="sos")
        f2 = sps.butter(2, [2600 / (SR / 2), 3600 / (SR / 2)], "bandpass", output="sos")
        x = x + 0.6 * sps.sosfilt(f1, base) + 0.25 * sps.sosfilt(f2, base)
    elif kind == "pluck":
        x = S.harmonic_tone(SR, DUR, f0, amps=(1, 0.6, 0.45, 0.3), decay=0.35, seed=seed)
    else:
        raise ValueError(kind)
    return S._norm(x, 0.5)


def make_masker(kind, f_root, seed):
    if kind == "pad":
        x = S.pad_chord(SR, DUR, [f_root, f_root * 1.5], seed=seed)
    elif kind == "swell":
        n = N
        g = S.rng(seed + 40)
        x = g.standard_normal(n)
        lo = max(60.0, f_root * 0.7)
        hi = min(15000.0, f_root * 1.6)
        sos = sps.butter(2, [lo / (SR / 2), hi / (SR / 2)], "bandpass", output="sos")
        env = np.hanning(n) ** 0.5
        x = sps.sosfilt(sos, x) * env
        x = S._norm(x, 0.5)
    elif kind == "arp":
        evs = []
        for i in range(8):
            f = f_root * (1.0 if i % 3 else 1.5)
            tone = S.harmonic_tone(SR, 0.14, f, amps=(1, 0.4, 0.2), decay=0.06, seed=seed * 10 + i)
            evs.append((i * 0.15, 1.0, tone))
        x = S.place(evs, SR, DUR)
    else:
        raise ValueError(kind)
    return S._norm(x, 0.5)


def gate(x, mode, seed):
    if mode == "full":
        return x
    n = len(x)
    if mode == "alternating":
        g = np.zeros(n)
        seg = int(0.15 * SR)
        phase = 0 if seed % 2 == 0 else seg // 2
        for i in range(8):
            s = phase + 2 * i * seg
            e = min(n, s + seg)
            if s < n:
                g[s:e] = 1.0
        return x * g
    if mode == "offset50":
        d = int(0.3 * SR)
        out = np.zeros(n)
        out[d:] = x[:-d]
        return out * 0.9
    raise ValueError(mode)


def bark_tf_features(a, b):
    n_fft = 2048
    hop = 512
    fa = np.abs(sps.stft(a, fs=SR, nperseg=n_fft, noverlap=n_fft - hop, boundary=None, padded=False)[2])
    fb = np.abs(sps.stft(b, fs=SR, nperseg=n_fft, noverlap=n_fft - hop, boundary=None, padded=False)[2])
    freqs = np.fft.rfftfreq(n_fft, 1 / SR)
    bk = hz2bark(freqs)
    edges = np.unique(np.round(np.linspace(0, bk[-1], 25), 2))
    bands = []
    for i in range(len(edges) - 1):
        m = (bk >= edges[i]) & (bk < edges[i + 1])
        if np.any(m):
            bands.append(m)
    ea = fa**2 + 1e-20
    eb = fb**2 + 1e-20
    shares = []
    cooc = []
    asym = []
    for m_ in bands:
        Ea = ea[m_].sum(axis=0)
        Eb = eb[m_].sum(axis=0)
        act_a = Ea > 0.02 * Ea.max()
        act_b = Eb > 0.02 * Eb.max()
        both = act_a & act_b
        cooc.append(float(np.mean(both)))
        if np.any(both):
            mn = np.minimum(Ea[both], Eb[both])
            mx = np.maximum(Ea[both], Eb[both]) + 1e-20
            shares.extend((mn / mx).tolist())
            asym.extend((10 * np.log10((Ea[both] + 1e-20) / (Eb[both] + 1e-20))).tolist())
    tf_share_mean = float(np.mean(shares)) if shares else 0.0
    tf_share_p95 = float(np.percentile(shares, 95)) if shares else 0.0
    cooccupancy = float(np.mean(cooc))
    asym_median = float(np.median(asym)) if asym else 30.0
    static = float(np.sum(np.minimum(fa, fb)) / (np.sum(np.maximum(fa, fb)) + 1e-20))
    return {
        "static_overlap": static,
        "tf_share_mean": tf_share_mean,
        "tf_share_p95": tf_share_p95,
        "cooccupancy": cooccupancy,
        "level_asym_db": asym_median,
    }


def estimate_f0_guarded(x):
    f0 = F.estimate_f0_autocorr(x, SR, 50.0, 2000.0)
    return f0


def classify_construction(ratio, ldiff, overlap_mode, maskee_kind, masker_kind, f_m):
    musical = ratio in (1.0, 2.0)
    same_band = abs(hz2bark(f_m * ratio) - hz2bark(f_m)) < 1.2
    comparable = abs(ldiff) <= 9
    simultaneous = overlap_mode == "full"
    if musical and simultaneous and comparable:
        return "musical"
    if same_band and comparable and simultaneous:
        return "problematic"
    return "benign"


def analyse_case(job):
    (maskee_kind, masker_kind, ratio, ldiff, ov, seed) = job
    f_m = float(S.rng(seed + int(maskee_kind.__len__()) + MASKEE_KINDS.index(maskee_kind)).choice([330, 392, 440, 523]))
    f_root = f_m * ratio
    a = gate(make_maskee(maskee_kind, f_m, seed + 900), ov, seed)
    b = gate(make_masker(masker_kind, f_root, seed + 800), ov, seed)

    def rms_norm(x, target_db=-18):
        r = np.sqrt(np.mean(x**2)) + 1e-12
        return x * (10 ** (target_db / 20) / r)

    a = rms_norm(a)
    b = rms_norm(b) * 10 ** (-ldiff / 20)
    feats = bark_tf_features(a, b)
    f0a = estimate_f0_guarded(a)
    f0b = estimate_f0_guarded(b)
    feats["f0_est_ratio_ok"] = bool(f0a and f0b)
    if f0a and f0b:
        feats["bark_dist_est"] = float(abs(hz2bark(f0a) - hz2bark(f0b)))
    else:
        feats["bark_dist_est"] = 12.0
    label = classify_construction(ratio, ldiff, ov, maskee_kind, masker_kind, f_m)
    return {"params": {"maskee": maskee_kind, "masker": masker_kind, "ratio": ratio,
                       "level_diff_db": ldiff, "overlap": ov, "seed": seed, "f_maskee": f_m},
            "features": feats, "label": label}


def build_jobs():
    jobs = []
    for mk in MASKEE_KINDS:
        for nk in MASKER_KINDS:
            for r in RATIOS:
                for ld in LEVEL_DIFFS:
                    for ov in OVERLAPS:
                        for sd in SEEDS:
                            jobs.append((mk, nk, r, ld, ov, sd))
    return jobs


FEATURE_NAMES = ["static_overlap", "tf_share_mean", "tf_share_p95", "cooccupancy", "level_asym_db", "bark_dist_est"]


def main():
    jobs = build_jobs()
    print(f"cases: {len(jobs)}", flush=True)
    raw_path = os.path.join(LAB_ROOT, "results", "track_c_raw.jsonl")
    done = set()
    if os.path.exists(raw_path):
        with open(raw_path) as f:
            for line in f:
                try:
                    done.add(json.dumps(json.loads(line)["params"], sort_keys=True))
                except Exception:
                    pass
    jobs = [j for j in jobs if json.dumps({"maskee": j[0], "masker": j[1], "ratio": j[2],
                                           "level_diff_db": j[3], "overlap": j[4], "seed": j[5],
                                           "f_maskee": None}, sort_keys=True) not in done]
    print(f"remaining: {len(jobs)}", flush=True)
    n = 0
    with open(raw_path, "w") as sink, ProcessPoolExecutor(max_workers=2) as ex:
        for res in ex.map(analyse_case, jobs, chunksize=16):
            sink.write(json.dumps(res) + "\n")
            n += 1
            if n % 500 == 0:
                sink.flush()
                print(f"progress {n}", flush=True)
    results = [json.loads(l) for l in open(raw_path)]
    summarise(results)


def summarise(results):
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import confusion_matrix

    X = np.array([[r["features"][k] for k in FEATURE_NAMES] for r in results])
    y = np.array([r["label"] for r in results])
    seeds = np.array([r["params"]["seed"] for r in results])

    def eval_split(train_mask, test_mask, name):
        tr, te = np.where(train_mask)[0], np.where(test_mask)[0]
        out = {"n_train": int(train_mask.sum()), "n_test": int(test_mask.sum())}
        mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-9
        lr = LogisticRegression(max_iter=2000, C=1.0)
        ytr_bin = (y[tr] == "problematic").astype(int)
        yte_bin = (y[te] == "problematic").astype(int)
        lr.fit((X[tr] - mu) / sd, ytr_bin)
        p = lr.predict_proba((X[te] - mu) / sd)[:, 1]
        pred = (p >= 0.5).astype(int)
        cm = confusion_matrix(yte_bin, pred, labels=[0, 1]).tolist()
        acc = float(np.mean(pred == yte_bin))
        musical_idx = np.where(y[te] == "musical")[0]
        benign_idx = np.where(y[te] == "benign")[0]
        out.update({
            "binary_accuracy_problematic_vs_rest": acc,
            "confusion_rows_true_0_1": cm,
            "musical_flagged_problematic_rate": float(np.mean(p[musical_idx] >= 0.5)),
            "benign_flagged_problematic_rate": float(np.mean(p[benign_idx] >= 0.5)),
        })
        base_static = X[te][:, FEATURE_NAMES.index("static_overlap")]
        th_grid = np.quantile(X[tr][:, 0], np.linspace(0.3, 0.99, 40))
        best = None
        for th in th_grid:
            bp = (base_static >= th).astype(int)
            hits = np.mean(bp[yte_bin == 1])
            fpb = np.mean(bp[yte_bin == 0])
            u = hits - fpb
            if best is None or u > best[0]:
                best = (u, float(th), hits, fpb)
        out["baseline_static_rule_best"] = {"threshold": best[1], "recall": best[2], "fp_rate": best[3]}
        return out

    split_in = eval_split(seeds < 2, seeds == 2, "same families, held-out seed")
    out = {"benchmark_id": "MASK_BENCH_1.0",
           "n_cases": len(results),
           "label_counts": {k: int(v) for k, v in zip(*np.unique(y, return_counts=True))},
           "split_same_family_heldout_seed": split_in}

    ablations = {}
    for drop in ["tf_share_p95", "cooccupancy", "level_asym_db", "bark_dist_est"]:
        keep = [k for k in FEATURE_NAMES if k != drop]
        Xi = X[:, [FEATURE_NAMES.index(k) for k in keep]]
        tr, te = np.where(seeds < 2)[0], np.where(seeds == 2)[0]
        mu, sd = Xi[tr].mean(0), Xi[tr].std(0) + 1e-9
        lr = LogisticRegression(max_iter=2000)
        lr.fit((Xi[tr] - mu) / sd, (y[tr] == "problematic").astype(int))
        p = lr.predict_proba((Xi[te] - mu) / sd)[:, 1]
        acc = float(np.mean((p >= 0.5) == (y[te] == "problematic")))
        ablations[f"minus_{drop}"] = acc
    out["ablations_holdout_seed2_acc"] = ablations
    save_json(os.path.join(LAB_ROOT, "results", "track_c_masking_results.json"), out)

    lines = [
        "# Track C - Masking Intelligence MASK_BENCH_1.0",
        "",
        f"Cases: {len(results)}; labels by construction: {out['label_counts']}",
        "",
        f"Held-out-seed binary accuracy (problematic vs rest): {split_in['binary_accuracy_problematic_vs_rest']:.3f}",
        f"MUSICAL unison/octave doublings flagged problematic: {split_in['musical_flagged_problematic_rate']:.3f}",
        f"Benign flagged problematic: {split_in['benign_flagged_problematic_rate']:.3f}",
        "",
        f"Static-overlap-only baseline: threshold={split_in['baseline_static_rule_best']['threshold']:.3f} "
        f"recall={split_in['baseline_static_rule_best']['recall']:.3f} fp={split_in['baseline_static_rule_best']['fp_rate']:.3f}",
        "",
        "## Ablations (hold-out seed 2 accuracy)",
        "",
    ]
    for k, v in ablations.items():
        lines.append(f"- {k}: {v:.3f}")
    with open(os.path.join(LAB_ROOT, "results", "track_c_masking_report.md"), "w") as f:
        f.write("\n".join(lines))
    print("track C analysis written", flush=True)


if __name__ == "__main__":
    main()
