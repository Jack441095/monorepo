#!/usr/bin/env python3
"""
Phase 4 -- re-evaluate after the new domain-coverage labels.

Two questions, kept separate because they are not the same question.

1. SAME TEN CLASSES, MORE DATA. Restricting to the ten classes the frozen
   incumbent was measured on, does adding labels from new collections improve
   collection-held-out accuracy? This is a legitimate learning-curve point: the
   class set is identical, only the corpus grew.

2. DOES PRECISE REJECTION DATA FIX FALSE ACCEPTANCE? The new batch produced many
   non-drum labels (Bass Reese, Synth One-Shot, Vocal Loop, Pad, ...). From the
   drum model's point of view every one of those is a CORRECT REJECTION, labelled
   far more precisely than a bare Other/none. Mapping them all to the rejection
   class tests whether more rejection material reduces the 36.59% false-accept
   rate, which the incumbent receipt identifies as the binding product risk.

What this is NOT: a like-for-like delta against the frozen 65.31%. That figure
was measured on a different corpus. Where the corpora differ, it is reported as
a new measurement, not an improvement.
"""
import os, json, argparse, warnings
import numpy as np
warnings.filterwarnings("ignore")

SD = os.path.dirname(os.path.abspath(__file__))
import sample_library_inventory as inv
import incumbent_receipt as ir
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.metrics import f1_score
from collections import Counter

CORPUS = os.path.join(SD, "corpus_v2.npz")
RECEIPT = os.path.join(SD, "incumbent_receipt_v1.json")
OUT = os.path.join(SD, "results_corpus_v2.json")

DRUM10 = ["Clap", "Crash", "Drum Loop", "Foley", "Hi-Hat", "Kick",
          "Other/none", "Percussion", "Percussion Loop", "Snare"]


def load(map_rejection=False, min_class=15):
    z = np.load(CORPUS, allow_pickle=True)
    paths = list(z["paths"]); X = z["emb"]; y = np.array(z["labels"])
    src = np.array(z["source"])
    if map_rejection:
        y = np.array(["Other/none" if lab not in DRUM10 else lab for lab in y])
    att = [inv.attribute(p) for p in paths]
    vendor = np.array([a[1] for a in att])
    family = np.array([inv.family_id(a[1], a[2], os.path.basename(p))
                       for a, p in zip(att, paths)])
    cnt = Counter(y)
    viable = sorted(c for c in cnt if cnt[c] >= min_class)
    m = np.isin(y, viable)
    return dict(X=X[m], y=y[m], vendor=vendor[m], family=family[m],
                src=src[m], classes=viable,
                paths=[p for p, k in zip(paths, m) if k])


def run(d, seeds=8, splits=5):
    X, y, g = d["X"], d["y"], d["vendor"]
    classes = d["classes"]
    accs, f1s, covs, fas = [], [], [], []
    for s in range(seeds):
        cv = StratifiedGroupKFold(splits, shuffle=True, random_state=s)
        oof = np.empty(len(y), dtype=object); conf = np.zeros(len(y))
        for tr, te in cv.split(X, y, groups=g):
            assert not (set(g[tr]) & set(g[te])), "collection leak"
            p, c = ir.centroid_fit_predict(X[tr], y[tr], X[te], classes)
            oof[te], conf[te] = p, c
        ok = oof != None
        correct = (oof == y).astype(float)
        accs.append(100 * float(correct[ok].mean()))
        f1s.append(100 * f1_score(y[ok], oof[ok].astype(str), average="macro",
                                  zero_division=0))
        covs.append(ir.coverage_at(conf, correct, 0.95))
        mm = y == "Other/none"
        if mm.any():
            fas.append(100 * float(((oof[mm] != "Other/none") & (conf[mm] >= 0.5)).mean()))
    return dict(acc=round(float(np.mean(accs)), 2), sd=round(float(np.std(accs)), 2),
                per_seed=[round(v, 2) for v in accs],
                macro_f1=round(float(np.mean(f1s)), 2),
                cov95=round(float(np.mean(covs)), 1),
                false_accept=round(float(np.mean(fas)), 2) if fas else None,
                n=int(len(y)), n_classes=len(classes),
                n_collections=len(set(d["vendor"])))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=8)
    a = ap.parse_args()
    base = json.load(open(RECEIPT))
    v1 = base["results"]["vendor"]
    print(f"FROZEN INCUMBENT (v1 corpus): {v1['accuracy_mean']}% "
          f"+-{v1['accuracy_sd']}, {base['identity']['n_files_evaluated']} files, "
          f"false-accept {v1['other_none_false_accept']}%\n")

    res = {}
    print("1. SAME TEN CLASSES, larger corpus")
    d = load(map_rejection=False)
    d = {k: (v if k not in ("X","y","vendor","family","src") else v) for k, v in d.items()}
    keep = np.isin(d["y"], DRUM10)
    d10 = dict(X=d["X"][keep], y=d["y"][keep], vendor=d["vendor"][keep],
               family=d["family"][keep], src=d["src"][keep], classes=DRUM10,
               paths=[p for p, k in zip(d["paths"], keep) if k])
    r = run(d10, a.seeds); res["same_10_classes"] = r
    print(f"   {r['n']} files, {r['n_collections']} collections, "
          f"{r['n_classes']} classes")
    print(f"   accuracy {r['acc']}% +-{r['sd']}   macroF1 {r['macro_f1']}   "
          f"cov@95 {r['cov95']}%   false-accept {r['false_accept']}%")
    print(f"   vs frozen {v1['accuracy_mean']}%  -> {r['acc']-v1['accuracy_mean']:+.2f}pp "
          f"(corpus grew from {base['identity']['n_files_evaluated']} to {r['n']})")

    print("\n2. NON-DRUM LABELS MAPPED TO REJECTION")
    dr = load(map_rejection=True)
    r2 = run(dr, a.seeds); res["rejection_mapped"] = r2
    print(f"   {r2['n']} files, {r2['n_collections']} collections, "
          f"{r2['n_classes']} classes")
    print(f"   accuracy {r2['acc']}% +-{r2['sd']}   macroF1 {r2['macro_f1']}   "
          f"cov@95 {r2['cov95']}%")
    print(f"   Other/none FALSE ACCEPT {r2['false_accept']}%  "
          f"vs frozen {v1['other_none_false_accept']}%  "
          f"-> {r2['false_accept']-v1['other_none_false_accept']:+.2f}pp")

    json.dump({"frozen_v1": v1, "results": res}, open(OUT, "w"), indent=2)
    print(f"\nwrote {os.path.basename(OUT)}")


if __name__ == "__main__":
    main()
