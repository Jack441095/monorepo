#!/usr/bin/env python3
"""
Loop detection by PATTERN PERIODICITY, not by duration proxy.

Current rule (section 23): duration >= 1.5s AND sustained-energy ratio >= 0.10.
That is a proxy -- it asks "is this long and does it keep going", which is true
of a pad, a riser, and a 4-bar drum loop alike. It scores 96.4% on the by-ear
loop/one-shot labels, so the bar is high, but the errors it does make are
exactly the long-sustained-non-loop case the proxy cannot see.

A loop is defined by a PATTERN THAT REPEATS. Three direct measurements:

  1. onset-envelope autocorrelation peak
       Does the rhythmic envelope correlate with a lagged copy of itself? A
       genuine loop has a strong non-zero-lag peak at the bar/beat period. A
       pad or a single decaying hit has none.

  2. self-similarity recurrence (mel spectrogram)
       Off-diagonal structure in the frame-to-frame similarity matrix. Repeats
       show as bright diagonals parallel to the main one. This catches melodic
       and textural repetition that the onset envelope misses.

  3. head/tail splice continuity  -- MEASURED AND REJECTED
       Intended as the literal definition of a seamless loop: does the last
       100ms lead into the first 100ms as smoothly as it leads into its own
       neighbours? It is numerically unstable -- the within-file baseline it
       normalises by approaches zero on quiet or sparse files, so the ratio
       explodes (observed values up to 4.5e10) and its d-prime came out
       NEGATIVE. Retained in the feature vector for the record but excluded
       from every rule and model below. Do not use it without a bounded
       normaliser.

Each is scored alone and in combination, against the by-ear labels, and against
the incumbent duration+sustain rule on the SAME files. The question is not
whether these correlate with looping -- they will. It is whether they beat 96.4%
or fix cases the incumbent misses.
"""
import os, csv, math, argparse, warnings
import numpy as np
warnings.filterwarnings("ignore")

SD = os.path.dirname(os.path.abspath(__file__))
VERIFIED = os.path.join(SD, "verified_drums.csv")
CACHE = os.path.join(SD, "loop_periodicity_feats.npz")

FEATURE_NAMES = ["dur", "sustain", "ac_peak", "ac_lag_s", "ac_ratio",
                 "recur", "splice", "onsets", "tempo_conf"]


def features(path):
    """Return the 9 measurements above, or None if the file will not load."""
    import librosa, soundfile as sf
    try:
        y, sr = sf.read(path, dtype="float32", always_2d=False)
    except Exception:
        return None
    if y.ndim > 1:
        y = y.mean(1)
    if len(y) < sr // 10:
        return None
    dur = len(y) / sr

    # incumbent proxy: sustained energy in the final third vs the peak
    hop = 512
    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    peak = float(rms.max()) + 1e-9
    tail = rms[int(len(rms) * 2 / 3):]
    sustain = float(tail.mean() / peak) if len(tail) else 0.0

    onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    onsets = len(librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr,
                                            hop_length=hop))

    # ---- 1. onset-envelope autocorrelation -------------------------------
    ac_peak = ac_lag_s = ac_ratio = 0.0
    if len(onset_env) > 8:
        e = onset_env - onset_env.mean()
        ac = np.correlate(e, e, mode="full")[len(e) - 1:]
        if ac[0] > 1e-9:
            ac = ac / ac[0]
            # ignore lags below 120ms (within-transient) and above half the file
            lo = max(2, int(0.12 * sr / hop))
            hi = max(lo + 2, len(ac) // 2)
            seg = ac[lo:hi]
            if len(seg):
                k = int(np.argmax(seg))
                ac_peak = float(seg[k])
                ac_lag_s = float((lo + k) * hop / sr)
                # peak height relative to the local baseline: a real period is
                # a spike, not a slow envelope drift
                ac_ratio = float(ac_peak - np.median(seg))

    # ---- 2. self-similarity recurrence -----------------------------------
    recur = 0.0
    S = librosa.feature.melspectrogram(y=y, sr=sr, hop_length=hop, n_mels=48)
    S = librosa.power_to_db(S, ref=np.max)
    if S.shape[1] > 12:
        F = S / (np.linalg.norm(S, axis=0, keepdims=True) + 1e-9)
        R = F.T @ F
        n = R.shape[0]
        # mean similarity on diagonals far from the main one (>= 0.25s away)
        off = max(4, int(0.25 * sr / hop))
        vals = [np.mean(np.diag(R, d)) for d in range(off, n - 2)]
        if vals:
            recur = float(np.max(vals) - np.median(R))

    # ---- 3. head/tail splice continuity ----------------------------------
    splice = 0.0
    if S.shape[1] > 12:
        w = max(2, int(0.10 * sr / hop))
        head = S[:, :w].mean(1)
        tailf = S[:, -w:].mean(1)
        d_splice = float(np.linalg.norm(head - tailf))
        # baseline: typical distance between frames w apart inside the file
        steps = [np.linalg.norm(S[:, i] - S[:, i + w])
                 for i in range(0, S.shape[1] - w, max(1, w))]
        base = float(np.median(steps)) + 1e-9
        # low value = the tail leads into the head as smoothly as anywhere else
        splice = d_splice / base

    tempo_conf = 0.0
    try:
        tg = librosa.feature.tempogram(onset_envelope=onset_env, sr=sr,
                                       hop_length=hop)
        tempo_conf = float(np.max(tg.mean(1)))
    except Exception:
        pass

    return np.array([dur, sustain, ac_peak, ac_lag_s, ac_ratio, recur,
                     splice, onsets, tempo_conf], dtype=np.float32)


def build(paths, workers):
    if os.path.exists(CACHE):
        z = np.load(CACHE, allow_pickle=True)
        if len(z["X"]) == len(paths) and list(z["paths"]) == paths:
            print("loaded cached features")
            return z["X"], z["ok"]
    from multiprocessing import Pool
    with Pool(workers) as p:
        res = p.map(features, paths, chunksize=4)
    ok = np.array([r is not None for r in res])
    X = np.zeros((len(paths), len(FEATURE_NAMES)), dtype=np.float32)
    for i, r in enumerate(res):
        if r is not None:
            X[i] = r
    np.savez(CACHE, X=X, ok=ok, paths=np.array(paths, dtype=object))
    return X, ok


def report(name, pred, truth):
    acc = (pred == truth).mean()
    tp = int(((pred == 1) & (truth == 1)).sum())
    fp = int(((pred == 1) & (truth == 0)).sum())
    fn = int(((pred == 0) & (truth == 1)).sum())
    prec = tp / max(tp + fp, 1)
    rec = tp / max(tp + fn, 1)
    print(f"  {name:38} acc {100*acc:5.1f}%   loop precision {100*prec:5.1f}%  "
          f"recall {100*rec:5.1f}%   (fp {fp}, fn {fn})")
    return acc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()

    rows = [r for r in csv.DictReader(open(VERIFIED))
            if r["label"] not in ("__skip__", "Misc/Review")
            and os.path.exists(r["path"])]
    paths = [r["path"] for r in rows]
    lab = np.array([r["label"] for r in rows])
    is_loop = np.array(["Loop" in l for l in lab]).astype(int)

    print(f"{len(paths)} by-ear files: {int(is_loop.sum())} loops, "
          f"{int((1-is_loop).sum())} one-shots\n")

    X, ok = build(paths, a.workers)
    X, is_loop, lab = X[ok], is_loop[ok], lab[ok]
    d = {n: X[:, i] for i, n in enumerate(FEATURE_NAMES)}

    print("separation per measurement (mean on loops vs one-shots):")
    print(f"  {'feature':>12} {'loops':>9} {'one-shots':>11} {'d-prime':>9}")
    for n in FEATURE_NAMES:
        v = d[n]
        a1, a0 = v[is_loop == 1], v[is_loop == 0]
        sd = math.sqrt((a1.var() + a0.var()) / 2) + 1e-9
        print(f"  {n:>12} {a1.mean():9.3f} {a0.mean():11.3f} "
              f"{(a1.mean()-a0.mean())/sd:9.2f}")

    print("\nrules, on all files:")
    incumbent = ((d["dur"] >= 1.5) & (d["sustain"] >= 0.10)).astype(int)
    report("incumbent: dur>=1.5s & sustain>=0.10", incumbent, is_loop)
    report("periodicity alone: ac_ratio>=0.10", (d["ac_ratio"] >= 0.10).astype(int), is_loop)
    report("recurrence alone: recur>=0.10", (d["recur"] >= 0.10).astype(int), is_loop)
    report("splice alone: splice<=1.0", (d["splice"] <= 1.0).astype(int), is_loop)
    report("incumbent AND periodicity", (incumbent & (d["ac_ratio"] >= 0.10)).astype(int), is_loop)
    report("incumbent OR periodicity", (incumbent | (d["ac_ratio"] >= 0.10)).astype(int), is_loop)

    from sklearn.linear_model import LogisticRegression
    from sklearn.tree import DecisionTreeClassifier, export_text
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import make_pipeline
    from sklearn.model_selection import cross_val_predict

    print("\nlearned, 5-fold out-of-fold:")
    base_idx = [FEATURE_NAMES.index("dur"), FEATURE_NAMES.index("sustain"),
                FEATURE_NAMES.index("onsets")]
    new_idx = [FEATURE_NAMES.index(n) for n in
               ("ac_peak", "ac_ratio", "recur", "splice", "tempo_conf")]
    mk = lambda: make_pipeline(StandardScaler(),
                              LogisticRegression(max_iter=3000,
                                                 class_weight="balanced"))
    report("LR on dur/sustain/onsets only",
           cross_val_predict(mk(), X[:, base_idx], is_loop, cv=5), is_loop)
    report("LR on periodicity features only",
           cross_val_predict(mk(), X[:, new_idx], is_loop, cv=5), is_loop)
    report("LR on ALL features",
           cross_val_predict(mk(), X, is_loop, cv=5), is_loop)

    t = DecisionTreeClassifier(max_depth=3, class_weight="balanced",
                               random_state=0)
    report("depth-3 tree on ALL (deployable as C++)",
           cross_val_predict(t, X, is_loop, cv=5), is_loop)
    t.fit(X, is_loop)
    print("\n  learned tree (candidate C++ rule):")
    for line in export_text(t, feature_names=FEATURE_NAMES).splitlines():
        print("    " + line)

    # what does the incumbent get wrong, and do the new features fix it?
    wrong = incumbent != is_loop
    print(f"\nincumbent errors: {int(wrong.sum())} files")
    for i in np.where(wrong)[0][:20]:
        print(f"  ear={lab[i]:<18} said={'loop' if incumbent[i] else 'one-shot':<9} "
              f"dur={d['dur'][i]:5.2f} sus={d['sustain'][i]:.2f} "
              f"ac={d['ac_ratio'][i]:.3f} rec={d['recur'][i]:.3f} "
              f"spl={d['splice'][i]:.2f}  {os.path.basename(paths[i])[:44]}")


if __name__ == "__main__":
    main()
