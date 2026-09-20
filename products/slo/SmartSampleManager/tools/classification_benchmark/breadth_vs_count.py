#!/usr/bin/env python3
"""
Does COLLECTION BREADTH beat RAW LABEL COUNT?

An earlier simulation concluded "label in any order". It was measured under
random CV -- which overstates unseen-collection accuracy by ~9.7pp -- and drew
its pool from the already-labelled population, so it could not test breadth
across collections because there were none in the pool. That conclusion was
explicitly reopened.

This tests it properly. Training sets of IDENTICAL SIZE are built two ways:

  concentrated  labels taken from as FEW collections as possible
  broad         labels spread across as MANY collections as possible

Both are evaluated on entirely held-out collections. If breadth matters, the
broad set wins at equal label count -- and that changes what to ask for in the
next labelling session.
"""
import os, json, argparse, warnings
import numpy as np
warnings.filterwarnings("ignore")

SD = os.path.dirname(os.path.abspath(__file__))
import incumbent_receipt as ir
import eval_corpus_v2 as ec
from collections import Counter, defaultdict

OUT = os.path.join(SD, "results_breadth_vs_count.json")


def build(sel_vendors, y, vendor, budget, rng, broad):
    """Pick `budget` training rows from the allowed vendors."""
    by_v = defaultdict(list)
    for i in sel_vendors:
        by_v[vendor[i]].append(i)
    for v in by_v:
        rng.shuffle(by_v[v])
    order = sorted(by_v, key=lambda v: -len(by_v[v]))
    picked = []
    if broad:
        r = 0
        while len(picked) < budget:
            added = 0
            for v in order:
                if r < len(by_v[v]):
                    picked.append(by_v[v][r]); added += 1
                    if len(picked) >= budget:
                        break
            if added == 0:
                break
            r += 1
    else:
        for v in order:
            for i in by_v[v]:
                picked.append(i)
                if len(picked) >= budget:
                    break
            if len(picked) >= budget:
                break
    return np.array(picked[:budget])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=12)
    a = ap.parse_args()

    d = ec.load(map_rejection=False)
    keep = np.isin(d["y"], ec.DRUM10)
    X, y, vend = d["X"][keep], d["y"][keep], d["vendor"][keep]
    print(f"{len(y)} files, {len(set(vend))} collections, {len(set(y))} classes\n")

    vc = Counter(vend)
    big = [v for v in vc if vc[v] >= 6]
    budgets = [120, 180, 240, 300, 360]
    res = {b: {"broad": [], "concentrated": []} for b in budgets}

    for run in range(a.runs):
        rng = np.random.RandomState(run)
        # hold out whole collections for testing
        vs = list(big); rng.shuffle(vs)
        test_v = set(vs[: max(2, len(vs) // 4)])
        te = np.where(np.isin(vend, list(test_v)))[0]
        tr_pool = np.where(~np.isin(vend, list(test_v)))[0]
        if len(te) < 40:
            continue
        for b in budgets:
            if len(tr_pool) < b:
                continue
            for mode, broad in (("broad", True), ("concentrated", False)):
                idx = build(tr_pool, y, vend, b, np.random.RandomState(run), broad)
                if len(idx) < b or len(set(y[idx])) < 4:
                    continue
                cls = sorted(set(y[idx]))
                p, _ = ir.centroid_fit_predict(X[idx], y[idx], X[te], cls)
                res[b][mode].append(100 * float((p == y[te]).mean()))

    print(f"{'budget':>7} {'concentrated':>26} {'broad':>26} {'delta':>8}")
    out = {}
    for b in budgets:
        c = np.array(res[b]["concentrated"]); w = np.array(res[b]["broad"])
        if len(c) < 3 or len(w) < 3:
            continue
        nc = np.array([len(set(vend[build(np.arange(len(y)), y, vend, b,
                                          np.random.RandomState(s), False)]))
                       for s in range(3)]).mean()
        nw = np.array([len(set(vend[build(np.arange(len(y)), y, vend, b,
                                          np.random.RandomState(s), True)]))
                       for s in range(3)]).mean()
        # PAIRED: both arms are evaluated on the same held-out collections in
        # the same run, so an unpaired test throws away that pairing and is far
        # too conservative -- between-run variance is dominated by WHICH
        # collections were held out, which is common to both arms.
        n = min(len(c), len(w))
        diff = w[:n] - c[:n]
        dlt = float(diff.mean())
        se = float(diff.std(ddof=1) / np.sqrt(n)) if n > 1 else float("inf")
        t = dlt / se if se > 0 else 0.0
        sig = "*" if abs(t) > 2 else " "
        print(f"{b:7d} {c.mean():8.1f}% ({nc:4.1f} colls) "
              f"{w.mean():8.1f}% ({nw:4.1f} colls) {dlt:+7.2f}{sig} "
              f" t={t:5.2f}  wins {int((diff>0).sum())}/{n}")
        out[b] = {"concentrated": round(float(c.mean()), 2),
                  "broad": round(float(w.mean()), 2),
                  "delta": round(float(dlt), 2),
                  "colls_concentrated": round(float(nc), 1),
                  "colls_broad": round(float(nw), 1),
                  "paired_t": round(float(t), 2),
                  "wins": int((diff > 0).sum()), "n_runs": int(n),
                  "significant": bool(abs(t) > 2)}
    print("\n  * = paired |t| > 2")
    json.dump(out, open(OUT, "w"), indent=2)
    print(f"wrote {os.path.basename(OUT)}")


if __name__ == "__main__":
    main()
