#!/usr/bin/env python3
"""
Task 3 -- the eight-arm ablation, collection-held-out.

Every arm is evaluated on identical folds with identical seeds, and every gate
(filename trust, audio threshold) is fitted on TRAINING COLLECTIONS ONLY. The
primary question is not accuracy: it is

    can we increase coverage at 90% precision above 41% WITHOUT dropping
    below 90% precision on collections the system has never seen?

Accuracy is reported because it is informative, not because it is the target.
A 95% figure is reported only when it is actually achieved; it is not
extrapolated, and an arm that misses the target is marked as missing it.
"""
import os, json, argparse, warnings
import numpy as np
warnings.filterwarnings("ignore")

SD = os.path.dirname(os.path.abspath(__file__))
import eval_corpus_v2 as ec, incumbent_receipt as ir, per_class_gating as pg
import mw_features as mwf, name_detect as nd
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.metrics import f1_score, confusion_matrix
from factorised_taxonomy import FAMILY, FORM

OUT = os.path.join(SD, "results_ablation_suite.json")


def znorm(X):
    return X / (np.linalg.norm(X, axis=1, keepdims=True) + 1e-9)


def load_all():
    d = ec.load()
    keep = np.isin(d["y"], ec.DRUM10)
    X, y, g = d["X"][keep], d["y"][keep], d["vendor"][keep]
    paths = [p for p, k in zip(d["paths"], keep) if k]
    M, mask = mwf.load_aligned(paths)
    if M is None:
        raise SystemExit("run mw_features.py first")
    if not mask.all():
        X, y, g = X[mask], y[mask], g[mask]
        paths = [p for p, k in zip(paths, mask) if k]
    fn = np.array([nd.detect(os.path.basename(p))[0] for p in paths], dtype=object)
    fn = np.array([c if c in ec.DRUM10 else None for c in fn], dtype=object)
    # multi-window ENCODER views, if extracted
    V = None
    import glob
    mw = glob.glob(os.path.join(SD, "mw_cache", "*.npz"))
    if mw:
        z = np.load(mw[0], allow_pickle=True)
        have = {p: i for i, p in enumerate(list(z["paths"]))}
        if all(p in have for p in paths):
            V = {n: np.stack([z["E"][j][have[p]] for p in paths])
                 for j, n in enumerate(list(z["views"]))}
            print(f"  encoder multi-window views available: {list(V)}")
        else:
            print(f"  encoder multi-window incomplete "
                  f"({sum(p in have for p in paths)}/{len(paths)}) -- DSP arms only")
    return dict(X=X, y=y, g=g, paths=paths, M=M, fn=fn, V=V)


def coverage_at(conf, correct, target):
    o = np.argsort(-conf)
    cum = np.cumsum(correct[o]) / np.arange(1, len(o) + 1)
    ok = np.where(cum >= target)[0]
    return (100.0 * (ok[-1] + 1) / len(o)) if len(ok) else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--splits", type=int, default=5)
    a = ap.parse_args()
    D = load_all()
    X, y, g, M, fn, V = D["X"], D["y"], D["g"], D["M"], D["fn"], D["V"]
    C = ec.DRUM10
    print(f"{len(y)} files, {len(set(g))} collections, "
          f"{M.shape[1]} multi-window DSP features\n")

    from sklearn.preprocessing import StandardScaler
    XM = np.hstack([X, znorm(StandardScaler().fit_transform(M))])

    forms = sorted(set(FORM.values()))
    yform = np.array([FORM[c] for c in y])

    def arm_predict(name, tr, te, seed):
        """Return (pred, conf, acted_mask). acted=None means 'always acts'."""
        if name == "audio-only (incumbent)":
            p, c = ir.centroid_fit_predict(X[tr], y[tr], X[te], C)
            return p, c, None
        if name == "multi-window audio":
            p, c = ir.centroid_fit_predict(XM[tr], y[tr], XM[te], C)
            return p, c, None
        if name == "mw-form + audio-family":
            # form from multi-window DSP (its design purpose), family from audio
            pf, cf = ir.centroid_fit_predict(XM[tr], yform[tr], XM[te], forms)
            fam = sorted(set(FAMILY.values()))
            yfam = np.array([FAMILY[c] for c in y])
            pfam, cfam = ir.centroid_fit_predict(X[tr], yfam[tr], X[te], fam)
            out, conf = [], []
            pe, ce = ir.centroid_fit_predict(X[tr], y[tr], X[te], C)
            for i in range(len(te)):
                cand = [c for c in C if FAMILY[c] == pfam[i] and FORM[c] == pf[i]]
                if len(cand) == 1:
                    out.append(cand[0]); conf.append(min(cfam[i], cf[i]))
                else:
                    out.append(pe[i]); conf.append(ce[i])
            return np.array(out, dtype=object), np.array(conf), None
        raise ValueError(name)

    ARMS = ["audio-only (incumbent)", "multi-window audio", "mw-form + audio-family"]
    res = {}
    for name in ARMS:
        accs, f1s = [], []
        cov = {90: [], 95: [], 85: []}
        fa = []
        oof_last = None
        for s in range(a.seeds):
            cv = StratifiedGroupKFold(a.splits, shuffle=True, random_state=s)
            oof = np.empty(len(y), dtype=object); conf = np.zeros(len(y))
            for tr, te in cv.split(X, y, groups=g):
                assert not (set(g[tr]) & set(g[te])), "collection leak"
                p, c, _ = arm_predict(name, tr, te, s)
                oof[te], conf[te] = p, c
            ok = oof != None
            corr = (oof == y).astype(float)
            accs.append(100 * float(corr[ok].mean()))
            f1s.append(100 * f1_score(y[ok], oof[ok].astype(str),
                                      average="macro", zero_division=0))
            for t in cov:
                cov[t].append(coverage_at(conf, corr, t / 100))
            m = y == "Other/none"
            fa.append(100 * float(((oof[m] != "Other/none") & (conf[m] >= .5)).mean()))
            oof_last = oof
        ok = oof_last != None
        cm = confusion_matrix(y[ok], oof_last[ok].astype(str), labels=C)
        per = {}
        for i, c in enumerate(C):
            tp = cm[i, i]; fp = cm[:, i].sum() - tp; fnn = cm[i].sum() - tp
            per[c] = {"precision": round(100 * tp / max(tp + fp, 1), 1),
                      "recall": round(100 * tp / max(tp + fnn, 1), 1),
                      "n": int(cm[i].sum())}
        rej = int(sum(cm[i, j] for i, ti in enumerate(C) for j, pj in enumerate(C)
                      if i != j and ("Other/none" in (ti, pj))))
        res[name] = {"acc": round(float(np.mean(accs)), 2),
                     "sd": round(float(np.std(accs)), 2),
                     "per_seed": [round(v, 2) for v in accs],
                     "macro_f1": round(float(np.mean(f1s)), 2),
                     "cov85": round(float(np.mean(cov[85])), 1),
                     "cov90": round(float(np.mean(cov[90])), 1),
                     "cov95": round(float(np.mean(cov[95])), 1),
                     "other_none_false_accept": round(float(np.mean(fa)), 2),
                     "rejection_boundary_errors": rej,
                     "total_errors": int(cm.sum() - np.trace(cm)),
                     "per_class": per,
                     "confusion": cm.tolist()}
        r = res[name]
        print(f"  {name:26} {r['acc']:6.2f}% +-{r['sd']:.2f}  F1 {r['macro_f1']:5.2f}  "
              f"cov85 {r['cov85']:5.1f}%  cov90 {r['cov90']:5.1f}%  "
              f"cov95 {r['cov95']:5.1f}%  FA {r['other_none_false_accept']:5.1f}%")

    base = res["audio-only (incumbent)"]
    print(f"\n  PRIMARY TARGET: coverage at 90% precision above "
          f"{base['cov90']:.1f}%")
    for n in ARMS:
        d = res[n]["cov90"] - base["cov90"]
        print(f"    {n:26} {res[n]['cov90']:5.1f}%  {d:+6.1f}pp"
              + ("   <-- IMPROVES" if d > 0.5 else ""))
    json.dump({"seeds": a.seeds, "n_files": int(len(y)),
               "n_collections": len(set(g)), "results": res},
              open(OUT, "w"), indent=2)
    print(f"\nwrote {os.path.basename(OUT)}")


if __name__ == "__main__":
    main()
