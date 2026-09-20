#!/usr/bin/env python3
"""
Does MODELLING THE CLASSES THAT EXIST beat improving the model?

The incumbent models ten classes. Seven more already have >=15 by-ear labels and
are not modelled at all: Synth One-Shot (44), SFX (38), Synth Loop (32),
Bass Reese (27), Foley Loop (26), Vocal Loop (25), Rimshot (16). That is 208
labelled files -- 21% of viable data -- discarded, and in a real library every
one of those sounds must be forced into a drum class or sent to review.

Bass Reese is the most acoustically coherent class in the corpus (silhouette
0.507, ahead of Kick at 0.252) and the product cannot name it.

Adding classes normally COSTS accuracy: more ways to be wrong. The question is
whether it buys enough product coverage to be worth it, so both are measured.
"""
import os, json, argparse, warnings
import numpy as np
warnings.filterwarnings("ignore")
SD = os.path.dirname(os.path.abspath(__file__))
import eval_corpus_v2 as ec, incumbent_receipt as ir, per_class_gating as pg
import mw_features as mwf
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import f1_score
from collections import Counter

OUT = os.path.join(SD, "results_expanded_taxonomy.json")
EXTRA = ["Synth One-Shot", "SFX", "Synth Loop", "Bass Reese",
         "Foley Loop", "Vocal Loop", "Rimshot"]


def evaluate(X, y, g, classes, seeds, splits, target):
    accs, f1s, covs, precs = [], [], [], []
    per = {c: {"tp": 0, "fp": 0, "fn": 0} for c in classes}
    for s in range(seeds):
        cv = StratifiedGroupKFold(splits, shuffle=True, random_state=s)
        oof = np.empty(len(y), dtype=object); conf = np.zeros(len(y))
        for tr, te in cv.split(X, y, groups=g):
            assert not (set(g[tr]) & set(g[te])), "collection leak"
            inner = StratifiedGroupKFold(3, shuffle=True, random_state=s)
            itr, ical = next(inner.split(X[tr], y[tr], groups=g[tr]))
            pc, cc = ir.centroid_fit_predict(X[tr][itr], y[tr][itr], X[tr][ical], classes)
            thr = pg.global_threshold(cc, (pc == y[tr][ical]).astype(float), target + 0.03)
            p, c = ir.centroid_fit_predict(X[tr], y[tr], X[te], classes)
            oof[te], conf[te] = p, c
            if s == 0:
                for k, i in enumerate(te):
                    if conf[i] >= thr:
                        if p[k] == y[i]: per[p[k]]["tp"] += 1
                        else:
                            per[p[k]]["fp"] += 1
                            if y[i] in per: per[y[i]]["fn"] += 1
        ok = oof != None
        corr = (oof == y).astype(float)
        accs.append(100 * float(corr[ok].mean()))
        f1s.append(100 * f1_score(y[ok], oof[ok].astype(str), average="macro",
                                  zero_division=0))
        # coverage/precision at the calibrated gate
        acted = conf >= thr
        covs.append(100 * float(acted.mean()))
        precs.append(100 * float(corr[acted].mean()) if acted.sum() else 0.0)
    return dict(acc=round(float(np.mean(accs)), 2), sd=round(float(np.std(accs)), 2),
                macro_f1=round(float(np.mean(f1s)), 2),
                coverage=round(float(np.mean(covs)), 1),
                precision=round(float(np.mean(precs)), 1),
                per_class={c: {"precision": round(100*v["tp"]/max(v["tp"]+v["fp"],1),1),
                               "n_acted": v["tp"]+v["fp"]} for c, v in per.items()})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--target", type=float, default=0.90)
    a = ap.parse_args()
    d = ec.load(min_class=15)
    X0, y0, g0 = d["X"], d["y"], d["vendor"]
    paths = d["paths"]
    M, mask = mwf.load_aligned(paths)
    if not mask.all():
        X0, y0, g0 = X0[mask], y0[mask], g0[mask]
        paths = [p for p, k in zip(paths, mask) if k]
    Mz = StandardScaler().fit_transform(M)
    XM = np.hstack([X0, Mz / (np.linalg.norm(Mz, axis=1, keepdims=True) + 1e-9)])

    ten = ec.DRUM10
    expanded = sorted(set(ten) | set(EXTRA))
    m10 = np.isin(y0, ten)
    mex = np.isin(y0, expanded)
    print(f"10-class: {m10.sum()} files, {len(ten)} classes")
    print(f"expanded: {mex.sum()} files, {len(expanded)} classes "
          f"(+{mex.sum()-m10.sum()} files the product currently cannot name)\n")

    r10 = evaluate(XM[m10], y0[m10], g0[m10], ten, a.seeds, 5, a.target)
    rex = evaluate(XM[mex], y0[mex], g0[mex], expanded, a.seeds, 5, a.target)

    print(f"  {'model':16} {'files':>7} {'acc':>15} {'macroF1':>9} "
          f"{'coverage':>10} {'precision':>10}")
    for nm, r, n in (("10-class", r10, int(m10.sum())),
                     ("17-class", rex, int(mex.sum()))):
        print(f"  {nm:16} {n:7d} {r['acc']:7.2f}% +-{r['sd']:4.2f} "
              f"{r['macro_f1']:8.2f} {r['coverage']:9.1f}% {r['precision']:9.1f}%")

    print(f"\n  accuracy    {rex['acc']-r10['acc']:+.2f}pp"
          f"   (expected to fall: more ways to be wrong)")
    print(f"  macro-F1    {rex['macro_f1']-r10['macro_f1']:+.2f}")
    print(f"  precision   {rex['precision']-r10['precision']:+.2f}pp at the same target")

    # the product question: how many files can be named safely, in absolute terms
    act10 = r10["coverage"] / 100 * m10.sum()
    actex = rex["coverage"] / 100 * mex.sum()
    print(f"\n  PRODUCT VIEW -- files nameable at ~{a.target:.0%} precision:")
    print(f"    10-class: {act10:.0f} of {m10.sum()} labelled")
    print(f"    17-class: {actex:.0f} of {mex.sum()} labelled  "
          f"({actex-act10:+.0f} files)")

    print(f"\n  new classes, precision when acting (seed 0):")
    for c in EXTRA:
        v = rex["per_class"].get(c, {})
        if v.get("n_acted"):
            print(f"    {c:18} {v['precision']:5.1f}%  on {v['n_acted']:3d} acted")
    json.dump({"target": a.target, "seeds": a.seeds,
               "ten_class": r10, "expanded": rex,
               "extra_classes": EXTRA}, open(OUT, "w"), indent=2)
    print(f"\nwrote {os.path.basename(OUT)}")


if __name__ == "__main__":
    main()
