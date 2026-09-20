#!/usr/bin/env python3
"""
Task 7 -- does the decision policy actually make SLO safer?

The success criterion is not accuracy. It is:

  auto_rename precision MUST beat the raw classifier's precision,
  and Percussion must never appear in auto_rename.

If the auto-rename tier is no more precise than acting on everything, the policy
is decoration. Measured collection-held-out, gates fitted on training folds.
"""
import os, csv, json, argparse, warnings
import numpy as np
warnings.filterwarnings("ignore")
SD = os.path.dirname(os.path.abspath(__file__))
import eval_corpus_v2 as ec, incumbent_receipt as ir, per_class_gating as pg
import mw_features as mwf, name_detect as nd, decision_policy as dp
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.preprocessing import StandardScaler
from collections import Counter

OUT = os.path.join(SD, "results_decision_policy.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--splits", type=int, default=5)
    ap.add_argument("--target", type=float, default=0.90)
    a = ap.parse_args()

    d = ec.load(); keep = np.isin(d["y"], ec.DRUM10)
    X, y, g = d["X"][keep], d["y"][keep], d["vendor"][keep]
    paths = [p for p, k in zip(d["paths"], keep) if k]
    M, mask = mwf.load_aligned(paths)
    if not mask.all():
        X, y, g = X[mask], y[mask], g[mask]
        paths = [p for p, k in zip(paths, mask) if k]
    Mz = StandardScaler().fit_transform(M)
    XM = np.hstack([X, Mz / (np.linalg.norm(Mz, axis=1, keepdims=True) + 1e-9)])
    fn = [nd.detect(os.path.basename(p))[0] for p in paths]
    C = ec.DRUM10
    print(f"{len(y)} files, {len(set(g))} collections, target {a.target:.0%}\n")

    tiers = ["auto_rename", "suggest", "review", "never_act"]
    agg = {t: {"n": 0, "correct": 0} for t in tiers}
    raw_acted = raw_correct = 0
    per_seed_auto, per_seed_raw = [], []
    percussion_in_auto = 0
    ir_in_auto = 0

    for s in range(a.seeds):
        cv = StratifiedGroupKFold(a.splits, shuffle=True, random_state=s)
        s_auto_n = s_auto_c = s_raw_n = s_raw_c = 0
        for tr, te in cv.split(X, y, groups=g):
            assert not (set(g[tr]) & set(g[te])), "collection leak"
            inner = StratifiedGroupKFold(3, shuffle=True, random_state=s)
            itr, ical = next(inner.split(X[tr], y[tr], groups=g[tr]))
            pc, cc = ir.centroid_fit_predict(XM[tr][itr], y[tr][itr],
                                             XM[tr][ical], C)
            thr = pg.global_threshold(cc, (pc == y[tr][ical]).astype(float),
                                      a.target + 0.03)
            p_te, c_te = ir.centroid_fit_predict(XM[tr], y[tr], XM[te], C)
            for k, i in enumerate(te):
                dec = dp.decide(predicted_class=p_te[k], confidence=float(c_te[k]),
                                path=paths[i], filename_class=fn[i],
                                threshold=thr, arm="multi-window audio")
                ok = int(p_te[k] == y[i])
                agg[dec.action]["n"] += 1
                agg[dec.action]["correct"] += ok
                if dec.action == "auto_rename":
                    s_auto_n += 1; s_auto_c += ok
                    if p_te[k] == "Percussion":
                        percussion_in_auto += 1
                    if dp.is_impulse_response(paths[i]):
                        ir_in_auto += 1
                # raw classifier acting on everything above the same gate
                if c_te[k] >= thr:
                    s_raw_n += 1; s_raw_c += ok
        per_seed_auto.append(100 * s_auto_c / max(s_auto_n, 1))
        per_seed_raw.append(100 * s_raw_c / max(s_raw_n, 1))
        raw_acted += s_raw_n; raw_correct += s_raw_c

    tot = sum(agg[t]["n"] for t in tiers)
    print(f"  {'action':12} {'files':>8} {'share':>8} {'precision':>11}")
    res = {}
    for t in tiers:
        n = agg[t]["n"]
        prec = 100 * agg[t]["correct"] / max(n, 1)
        res[t] = {"share": round(100 * n / tot, 1),
                  "precision": round(prec, 1) if n else None, "n": n}
        print(f"  {t:12} {n:8d} {100*n/tot:7.1f}% "
              + (f"{prec:10.1f}%" if n else "         --"))

    auto = float(np.mean(per_seed_auto)); raw = float(np.mean(per_seed_raw))
    print(f"\n  SAFETY TEST -- auto_rename must beat the raw classifier")
    print(f"    raw classifier acting above the same gate : {raw:.1f}% precision")
    print(f"    auto_rename tier                          : {auto:.1f}% precision")
    print(f"    delta                                     : {auto-raw:+.1f}pp"
          f"   {'PASS' if auto > raw else 'FAIL'}")
    print(f"    per-seed auto: {[round(v,1) for v in per_seed_auto]}")
    print(f"\n  Percussion in auto_rename : {percussion_in_auto}  "
          f"{'PASS' if percussion_in_auto == 0 else 'FAIL'}")
    print(f"  impulse responses in auto : {ir_in_auto}  "
          f"{'PASS' if ir_in_auto == 0 else 'FAIL'}")
    cov = res["auto_rename"]["share"] + res["suggest"]["share"]
    print(f"\n  user-facing coverage: {res['auto_rename']['share']:.1f}% acted on "
          f"automatically, {res['suggest']['share']:.1f}% suggested "
          f"({cov:.1f}% total labelled), {res['review']['share']:.1f}% review, "
          f"{res['never_act']['share']:.1f}% never-act")
    json.dump({"target": a.target, "seeds": a.seeds, "tiers": res,
               "auto_rename_precision": round(auto, 2),
               "raw_classifier_precision": round(raw, 2),
               "delta_pp": round(auto - raw, 2),
               "auto_per_seed": [round(v, 2) for v in per_seed_auto],
               "percussion_in_auto_rename": percussion_in_auto,
               "impulse_responses_in_auto_rename": ir_in_auto,
               "policy_version": dp.POLICY_VERSION},
              open(OUT, "w"), indent=2)
    print(f"\nwrote {os.path.basename(OUT)}")


if __name__ == "__main__":
    main()
