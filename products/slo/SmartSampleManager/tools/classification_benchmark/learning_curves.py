#!/usr/bin/env python3
"""
Grouped learning curves: does accuracy track LABEL COUNT or COLLECTION COUNT?

Every earlier learning curve in this project was measured under random CV and
plotted against raw label count only. Both choices hid the effect that matters:
random CV overstates unseen-collection accuracy, and label count conflates
"more data" with "more domains".

Here every curve is collection-held-out, and the same runs are plotted against
three different x-axes so the driver can be identified rather than assumed.
"""
import os, json, argparse, warnings
import numpy as np
warnings.filterwarnings("ignore")

SD = os.path.dirname(os.path.abspath(__file__))
import incumbent_receipt as ir
import eval_corpus_v2 as ec
from collections import Counter, defaultdict

OUT = os.path.join(SD, "results_learning_curves.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=14)
    a = ap.parse_args()
    d = ec.load(map_rejection=False)
    keep = np.isin(d["y"], ec.DRUM10)
    X, y, vend, fam = (d["X"][keep], d["y"][keep], d["vendor"][keep],
                       d["family"][keep])
    print(f"{len(y)} files, {len(set(vend))} collections, "
          f"{len(set(fam))} families\n")

    vc = Counter(vend)
    big = [v for v in vc if vc[v] >= 6]
    budgets = [100, 150, 200, 250, 300, 400, 500]
    rows = defaultdict(list)

    for run in range(a.runs):
        rng = np.random.RandomState(run)
        vs = list(big); rng.shuffle(vs)
        test_v = set(vs[: max(2, len(vs) // 4)])
        te = np.where(np.isin(vend, list(test_v)))[0]
        pool = np.where(~np.isin(vend, list(test_v)))[0]
        if len(te) < 40:
            continue
        perm = rng.permutation(pool)          # breadth-neutral random draw
        for b in budgets:
            if b > len(perm):
                continue
            idx = perm[:b]
            cls = sorted(set(y[idx]))
            if len(cls) < 4:
                continue
            p, _ = ir.centroid_fit_predict(X[idx], y[idx], X[te], cls)
            rows[b].append((100 * float((p == y[te]).mean()),
                            len(set(vend[idx])), len(set(fam[idx]))))

    print(f"{'labels':>7} {'collections':>12} {'families':>9} "
          f"{'accuracy':>12} {'runs':>5}")
    out = {}
    for b in budgets:
        if b not in rows or len(rows[b]) < 3:
            continue
        arr = np.array(rows[b])
        acc, nc, nf = arr[:, 0].mean(), arr[:, 1].mean(), arr[:, 2].mean()
        print(f"{b:7d} {nc:12.1f} {nf:9.1f} {acc:10.2f}% {len(arr):5d}")
        out[b] = {"accuracy": round(float(acc), 2),
                  "sd": round(float(arr[:, 0].std()), 2),
                  "collections": round(float(nc), 1),
                  "families": round(float(nf), 1),
                  "runs": int(len(arr))}

    ks = sorted(out)
    if len(ks) >= 3:
        L = np.log2([k for k in ks])
        C = np.log2([out[k]["collections"] for k in ks])
        A = np.array([out[k]["accuracy"] for k in ks])
        pl = np.polyfit(L, A, 1)[0]
        pc = np.polyfit(C, A, 1)[0]
        print(f"\n  +{pl:.2f}pp per doubling of LABELS")
        print(f"  +{pc:.2f}pp per doubling of COLLECTIONS")
        print("  (these are confounded in a random draw -- more labels bring "
              "more collections;\n   the breadth-vs-count experiment separates "
              "them at fixed budget)")
        out["slopes"] = {"pp_per_doubling_labels": round(float(pl), 2),
                         "pp_per_doubling_collections": round(float(pc), 2)}
    json.dump(out, open(OUT, "w"), indent=2)
    print(f"\nwrote {os.path.basename(OUT)}")


if __name__ == "__main__":
    main()
