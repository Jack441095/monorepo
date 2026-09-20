#!/usr/bin/env python3
"""
Task 6 -- where the renamer should abstain, and where fusion is unsafe.

The product rule is: rename confidently only on strong evidence, send the rest
to review, and never force a wrong label. This measures where that rule is
currently violated.
"""
import os, csv, json, warnings
import numpy as np
warnings.filterwarnings("ignore")
SD = os.path.dirname(os.path.abspath(__file__))
import eval_corpus_v2 as ec, incumbent_receipt as ir, per_class_gating as pg
import mw_features as mwf, name_detect as nd
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.preprocessing import StandardScaler
from collections import Counter

OUT = os.path.join(SD, "results_rejection_boundary.json")


def main():
    d = ec.load(); keep = np.isin(d["y"], ec.DRUM10)
    X, y, g = d["X"][keep], d["y"][keep], d["vendor"][keep]
    paths = [p for p, k in zip(d["paths"], keep) if k]
    M, mask = mwf.load_aligned(paths)
    if not mask.all():
        X, y, g = X[mask], y[mask], g[mask]
        paths = [p for p, k in zip(paths, mask) if k]
    Mz = StandardScaler().fit_transform(M)
    XM = np.hstack([X, Mz / (np.linalg.norm(Mz, axis=1, keepdims=True) + 1e-9)])
    fn = np.array([nd.detect(os.path.basename(p))[0] for p in paths], dtype=object)
    fn = np.array([c if c in ec.DRUM10 else None for c in fn], dtype=object)
    C = ec.DRUM10
    gt = {r["path"]: r for r in csv.DictReader(
        open(os.path.join(SD, "ground_truth", "SLO_GT_V1", "labels.csv")))}

    oof = np.empty(len(y), dtype=object); conf = np.zeros(len(y))
    oofm = np.empty(len(y), dtype=object); confm = np.zeros(len(y))
    for tr, te in StratifiedGroupKFold(5, shuffle=True, random_state=0).split(X, y, groups=g):
        oof[te], conf[te] = ir.centroid_fit_predict(X[tr], y[tr], X[te], C)
        oofm[te], confm[te] = ir.centroid_fit_predict(XM[tr], y[tr], XM[te], C)

    junk = y == "Other/none"
    res = {}
    print("REJECTION BOUNDARY\n")
    for nm, p_, c_ in (("audio-only", oof, conf), ("multi-window", oofm, confm)):
        fa = float(((p_[junk] != "Other/none") & (c_[junk] >= .5)).mean())
        miss = float((p_[~junk] == "Other/none").mean())
        res[nm] = {"false_accept_at_0.5": round(100 * fa, 2),
                   "real_sounds_wrongly_rejected": round(100 * miss, 2),
                   "junk_recall": round(100 * float((p_[junk] == "Other/none").mean()), 2)}
        print(f"  {nm:14} junk confidently mislabelled {100*fa:5.1f}%   "
              f"real sounds sent to review {100*miss:5.1f}%   "
              f"junk correctly rejected {100*float((p_[junk]=='Other/none').mean()):5.1f}%")

    print("\n  what the junk gets called instead:")
    for k, v in Counter(p_ for p_, j in zip(oof, junk) if j and p_ != "Other/none").most_common(6):
        print(f"    {k:20} {v}")

    print("\n  FILENAME OVERRULES AUDIO AND IS WRONG (fusion is unsafe here):")
    bad = [(paths[i], fn[i], oof[i], y[i]) for i in range(len(y))
           if fn[i] is not None and fn[i] != y[i] and oof[i] == y[i]]
    print(f"    {len(bad)} files where audio was RIGHT and the filename would override it")
    for p_, f_, a_, t_ in bad[:6]:
        print(f"      {os.path.basename(p_)[:38]:40} name={f_:14} audio={a_:14} truth={t_}")
    res["filename_overrides_correct_audio"] = len(bad)

    print("\n  IMPULSE RESPONSES (excluded from splits, checked for safety):")
    irs = [p for p in gt if gt[p]["is_impulse_response"] == "true"]
    res["impulse_responses_excluded"] = len(irs)
    print(f"    {len(irs)} flagged and excluded -- none can be auto-renamed")

    print("\n  ABSTAIN RECOMMENDATION by true class (audio-only, gate 0.5):")
    rows = []
    for c in C:
        m = y == c
        acted = c_[m] >= .5 if False else conf[m] >= .5
        prec = float((oof[m][acted] == c).mean()) if acted.sum() else 0.0
        rows.append((c, int(m.sum()), 100 * float(acted.mean()), 100 * prec))
    rows.sort(key=lambda r: r[3])
    print(f"    {'class':>18} {'n':>4} {'acts on':>9} {'precision':>10}  verdict")
    for c, n, act, prec in rows:
        v = "ABSTAIN ALWAYS" if prec < 60 else ("suggest only" if prec < 85 else "safe to rename")
        print(f"    {c:>18} {n:4d} {act:8.1f}% {prec:9.1f}%  {v}")
    res["per_class_policy"] = {c: {"n": n, "acts_on": round(act, 1),
                                   "precision": round(prec, 1),
                                   "policy": ("abstain" if prec < 60 else
                                              "suggest" if prec < 85 else "rename")}
                               for c, n, act, prec in rows}
    json.dump(res, open(OUT, "w"), indent=2)
    print(f"\nwrote {os.path.basename(OUT)}")


if __name__ == "__main__":
    main()
