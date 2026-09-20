#!/usr/bin/env python3
"""
Learned fusion over ALL signals, vs the hand-written rule cascade.

We have four signals, each measured best at something different:
  Perch (1536-D)  sharp transients   -- Crash +17pp, Snare +7pp over CLAP
  CLAP  (512-D)   timbre / texture   -- Percussion +5pp, Foley +4pp over Perch
  handcrafted 33  physical signature -- Kick 93%, beating both deep encoders
  filename tokens naming evidence    -- 81% precision on 82% coverage
  temporal        duration/onsets/decay -- loop vs one-shot at 94%

fusion_classify.py combines them with a rule cascade (trust filename if its
measured precision >= 0.75, else acoustic, duration fixes loop/one-shot). That
reached 77.9%. But the rules are hand-written thresholds; the per-class
strengths above say the right source varies by class, which a model can learn.

This trains a single classifier over the concatenated signals -- including the
filename detection as a one-hot feature rather than a hard override -- and
compares it against the rule cascade on the SAME files.

Ground truth: the 649 by-ear labels (the only non-circular labels available).
"""
import os, csv, argparse, warnings
import numpy as np
warnings.filterwarnings("ignore")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VERIFIED = os.path.join(SCRIPT_DIR, "verified_drums.csv")
EMB_CACHE = os.path.join(SCRIPT_DIR, "bioacoustic_emb.npz")
TEMPORAL_CACHE = os.path.join(SCRIPT_DIR, "learned_fusion_temporal.npz")


def temporal_feats(paths):
    """duration, onset count, decay ratio, is_loop -- cached (slow to compute)."""
    if os.path.exists(TEMPORAL_CACHE):
        z = np.load(TEMPORAL_CACHE, allow_pickle=True)
        if len(z["T"]) == len(paths): return z["T"]
    import fusion_renamer as fr
    T = []
    for i, p in enumerate(paths):
        d = fr.dur_of(p); o = fr.onset_count(p); dr = fr.decay_ratio(p)
        T.append([min(d / 10, 1.0), min(o / 40, 1.0), min(dr, 2.0) / 2.0,
                  1.0 if (d >= 2.5 and o >= 8 and dr >= 0.25) else 0.0])
        if i and i % 150 == 0: print(f"  temporal {i}/{len(paths)}", flush=True)
    T = np.array(T, dtype=np.float32)
    np.savez(TEMPORAL_CACHE, T=T)
    return T


def filename_onehot(paths, classes):
    """Filename detection as a FEATURE (one-hot + confidence) rather than a
    hard override, so the model can learn when to trust it."""
    import name_detect as nd
    idx = {c: i for i, c in enumerate(classes)}
    F = np.zeros((len(paths), len(classes) + 1), dtype=np.float32)
    for i, p in enumerate(paths):
        c, tok = nd.detect(os.path.basename(p))
        if c is not None and c in idx:
            F[i, idx[c]] = 1.0
        else:
            F[i, -1] = 1.0            # "no filename evidence" flag
    return F


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-class", type=int, default=15)
    a = ap.parse_args()

    rows = [r for r in csv.DictReader(open(VERIFIED))
            if r["label"] not in ("__skip__", "Misc/Review") and os.path.exists(r["path"])]
    paths = [r["path"] for r in rows]
    y = np.array([r["label"] for r in rows])

    if not os.path.exists(EMB_CACHE):
        print("run bioacoustic_bakeoff.py first (needs cached Perch/CLAP embeddings)"); return 1
    z = np.load(EMB_CACHE); Xp, Xc = z["perch"], z["clap"]
    assert len(Xp) == len(paths), f"cache/label mismatch {len(Xp)} vs {len(paths)}"

    import drum_detector_features as ddf
    Xd = np.array([ddf.extract(p) if ddf.extract(p) is not None else np.zeros(33, np.float32)
                   for p in paths])
    T = temporal_feats(paths)
    classes_all = sorted(set(y))
    Fn = filename_onehot(paths, classes_all)

    from collections import Counter
    cnt = Counter(y)
    viable = [c for c in cnt if cnt[c] >= a.min_class]
    m = np.isin(y, viable)
    print(f"\n{m.sum()} files, {len(viable)} classes (>= {a.min_class} examples)")
    print(f"signals: perch{Xp.shape[1]} clap{Xc.shape[1]} dsp{Xd.shape[1]} "
          f"temporal{T.shape[1]} filename{Fn.shape[1]}\n")

    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import make_pipeline
    from sklearn.model_selection import cross_val_predict

    def run(X, name):
        clf = make_pipeline(StandardScaler(),
                            LogisticRegression(max_iter=3000, class_weight="balanced"))
        pred = cross_val_predict(clf, X[m], y[m], cv=5)
        acc = 100 * (pred == y[m]).mean()
        print(f"  {name:34} {acc:5.1f}%")
        return pred

    print("ablation -- what each signal adds:")
    run(np.hstack([Xp, Xc]), "Perch+CLAP (encoders only)")
    run(np.hstack([Xp, Xc, Xd]), "+ handcrafted DSP")
    run(np.hstack([Xp, Xc, Xd, T]), "+ temporal (duration/onset/decay)")
    best = run(np.hstack([Xp, Xc, Xd, T, Fn]), "+ filename  = FULL LEARNED FUSION")

    # rule-based cascade on the same files, for a like-for-like comparison
    rule = None
    fe = os.path.join(SCRIPT_DIR, "fusion_eval.npz")
    if os.path.exists(fe):
        z2 = np.load(fe, allow_pickle=True)
        ry, rf = z2["y"], z2["fusion"]
        if len(ry) == len(y) and (ry == y).all():
            rule = rf[m]
            print(f"\n  {'rule cascade (fusion_classify)':34} {100*(rule==y[m]).mean():5.1f}%")

    print("\nper-class recall:")
    print(f"  {'class':>16} {'n':>4} {'learned':>9}" + ("  rule" if rule is not None else ""))
    for c in sorted(viable, key=lambda k: -cnt[k]):
        sel = y[m] == c
        line = f"  {c:>16} {int(sel.sum()):4d} {100*(best[sel]==c).mean():8.0f}%"
        if rule is not None: line += f" {100*(rule[sel]==c).mean():5.0f}%"
        print(line)


if __name__ == "__main__":
    raise SystemExit(main())
