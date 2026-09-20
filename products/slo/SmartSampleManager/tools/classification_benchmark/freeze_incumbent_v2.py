#!/usr/bin/env python3
"""
Freeze the incumbent on corpus v2 (the 500 new breadth-first labels included).

The v1 receipt stays valid and untouched -- it is pinned to its own dataset and
still verifies. This adds a SECOND receipt for the current corpus, so later
experiments are compared against the best current model rather than a superseded
one. Never edit v1 to make it agree with v2: the whole point of a receipt is
that it describes one fixed measurement.
"""
import os, json, time, hashlib, argparse, warnings
import numpy as np
warnings.filterwarnings("ignore")

SD = os.path.dirname(os.path.abspath(__file__))
import incumbent_receipt as ir
import eval_corpus_v2 as ec
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.metrics import (f1_score, precision_recall_fscore_support,
                             confusion_matrix)
from collections import Counter

OUT = os.path.join(SD, "incumbent_receipt_v2.json")
CORPUS = os.path.join(SD, "corpus_v2.npz")


def evaluate(d, seeds, splits):
    X, y, g = d["X"], d["y"], d["vendor"]
    classes = d["classes"]
    per_seed, f1s, worst, top2s = [], [], [], []
    cov = {90: [], 95: [], 98: []}
    fa = []
    oof_last = None
    for s in range(seeds):
        cv = StratifiedGroupKFold(splits, shuffle=True, random_state=s)
        oof = np.empty(len(y), dtype=object); conf = np.zeros(len(y))
        proba = np.zeros((len(y), len(classes)))
        fold = []
        for tr, te in cv.split(X, y, groups=g):
            assert not (set(g[tr]) & set(g[te])), "collection leak"
            p, c = ir.centroid_fit_predict(X[tr], y[tr], X[te], classes)
            oof[te], conf[te] = p, c
            fold.append(float((p == y[te]).mean()))
        ok = oof != None
        correct = (oof == y).astype(float)
        per_seed.append(100 * float(correct[ok].mean()))
        f1s.append(100 * f1_score(y[ok], oof[ok].astype(str), average="macro",
                                  zero_division=0))
        worst.append(100 * min(fold))
        for t in cov:
            cov[t].append(ir.coverage_at(conf, correct, t / 100))
        m = y == "Other/none"
        if m.any():
            fa.append(100 * float(((oof[m] != "Other/none") & (conf[m] >= 0.5)).mean()))
        oof_last = oof
    ok = oof_last != None
    p_, r_, f_, sup = precision_recall_fscore_support(
        y[ok], oof_last[ok].astype(str), labels=classes, zero_division=0)
    by_v = {}
    for v in sorted(set(g)):
        mm = (g == v) & ok
        if mm.sum() >= 8:
            by_v[v] = round(100 * float((oof_last[mm] == y[mm]).mean()), 1)
    return dict(accuracy_mean=round(float(np.mean(per_seed)), 2),
                accuracy_sd=round(float(np.std(per_seed)), 2),
                per_seed=[round(v, 2) for v in per_seed],
                macro_f1=round(float(np.mean(f1s)), 2),
                worst_fold=round(float(np.mean(worst)), 2),
                coverage_at_90=round(float(np.mean(cov[90])), 1),
                coverage_at_95=round(float(np.mean(cov[95])), 1),
                coverage_at_98=round(float(np.mean(cov[98])), 1),
                other_none_false_accept=round(float(np.mean(fa)), 2) if fa else None,
                worst_vendor=min(by_v, key=by_v.get) if by_v else None,
                worst_vendor_acc=min(by_v.values()) if by_v else None,
                by_vendor=by_v,
                per_class={c: dict(precision=round(100 * p_[i], 1),
                                   recall=round(100 * r_[i], 1),
                                   f1=round(100 * f_[i], 1), n=int(sup[i]))
                           for i, c in enumerate(classes)},
                confusion_matrix=confusion_matrix(
                    y[ok], oof_last[ok].astype(str), labels=classes).tolist())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--splits", type=int, default=5)
    a = ap.parse_args()

    res = {}
    for name, mapr in (("drum10", False), ("rejection_mapped", True)):
        d = ec.load(map_rejection=mapr)
        if not mapr:
            keep = np.isin(d["y"], ec.DRUM10)
            d = {k: (v[keep] if isinstance(v, np.ndarray) else
                     ([x for x, kk in zip(v, keep) if kk] if isinstance(v, list) else v))
                 for k, v in d.items()}
            d["classes"] = ec.DRUM10
        r = evaluate(d, a.seeds, a.splits)
        r["n_files"] = int(len(d["y"]))
        r["n_collections"] = len(set(d["vendor"]))
        res[name] = r
        print(f"{name:18} {r['accuracy_mean']:6.2f}% +-{r['accuracy_sd']:.2f}  "
              f"macroF1 {r['macro_f1']:5.2f}  cov@95 {r['coverage_at_95']:5.1f}%  "
              f"FA {r['other_none_false_accept']}%  n={r['n_files']}")

    z = np.load(CORPUS, allow_pickle=True)
    h = hashlib.sha256
    ident = {
        "corpus_v2_sha256": h(open(CORPUS, "rb").read()).hexdigest(),
        "n_rows": int(len(z["labels"])),
        "label_hash": h(np.ascontiguousarray(
            np.array(z["labels"]).astype("U40")).tobytes()).hexdigest(),
        "path_hash": h("\n".join(list(z["paths"])).encode()).hexdigest(),
        "feature_hash": h(np.ascontiguousarray(z["emb"]).tobytes()).hexdigest(),
        "label_sources": dict(Counter(list(z["source"]))),
    }
    json.dump({"generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
               "supersedes": "incumbent_receipt_v1.json (still valid for ITS "
                             "own dataset; do not edit it)",
               "incumbent": "nearest centroid on frozen Perch+CLAP",
               "rules": ir.RULES, "identity": ident,
               "seeds": a.seeds, "splits": a.splits, "results": res,
               "primary_result_vendor_held_out": res["drum10"]["accuracy_mean"]},
              open(OUT, "w"), indent=2)
    print(f"\nwrote {os.path.basename(OUT)}")
    r = res["drum10"]
    print(f"  coverage @90/95/98%: {r['coverage_at_90']}% / "
          f"{r['coverage_at_95']}% / {r['coverage_at_98']}%")
    print(f"  worst collection   : {r['worst_vendor']} ({r['worst_vendor_acc']}%)")
    print("\n  per-class recall (drum10):")
    for c, v in sorted(r["per_class"].items(), key=lambda t: -t[1]["n"]):
        print(f"    {c:>18} n={v['n']:4d}  precision {v['precision']:5.1f}%  "
              f"recall {v['recall']:5.1f}%")


if __name__ == "__main__":
    main()
