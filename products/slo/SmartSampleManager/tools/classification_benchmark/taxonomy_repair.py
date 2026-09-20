#!/usr/bin/env python3
"""
Does splitting the incoherent classes actually help?

Coherence analysis found Percussion (-0.154), Foley (-0.115), Percussion Loop
(-0.108) and others have NEGATIVE silhouette -- they name several unrelated
sounds. Sound-anatomy found Percussion contains three physically distinct groups
(Tom / Shaker-Tambourine / Short Percussive Hit).

This tests whether acting on that improves the product.

NON-CIRCULARITY IS THE WHOLE DESIGN. A split discovered on the full corpus and
then scored on the full corpus proves nothing. Here the sub-classes are derived
INSIDE EACH TRAINING FOLD ONLY -- the held-out collections never influence how
the class is divided -- and predictions are mapped back to the PARENT label
before scoring, so the label space and the metric are identical to the
incumbent's. Any gain is therefore a real gain, not a relabelled metric.

Three ways of deriving the split are compared, because how you split matters:
  embedding   k-means on the encoder embedding (what the model finds similar)
  physics     k-means on interpretable descriptors (what a human can state)
  none        the incumbent
"""
import os, json, argparse, warnings
import numpy as np
warnings.filterwarnings("ignore")

SD = os.path.dirname(os.path.abspath(__file__))
import incumbent_receipt as ir, eval_corpus_v2 as ec, physics_cache as pc
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.metrics import f1_score

OUT = os.path.join(SD, "results_taxonomy_repair.json")
GATE = 2.0


def znorm(X):
    return X / (np.linalg.norm(X, axis=1, keepdims=True) + 1e-9)


def split_labels(Xtr, Ftr, ytr, targets, mode, k, seed):
    """Return sub-labels for the TRAINING fold plus the fitted splitters."""
    sub = np.array(ytr, dtype=object).copy()
    fitted = {}
    for cls in targets:
        m = ytr == cls
        if m.sum() < 4 * k:
            continue
        if mode == "embedding":
            Z = znorm(StandardScaler().fit_transform(Xtr[m]))
        else:
            sc = StandardScaler().fit(Ftr[m])
            Z = sc.transform(Ftr[m])
            fitted[(cls, "sc")] = sc
        km = KMeans(k, n_init=10, random_state=seed).fit(Z)
        fitted[cls] = km
        for j in range(k):
            sub[np.where(m)[0][km.labels_ == j]] = f"{cls}::{j}"
    return sub, fitted


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--splits", type=int, default=5)
    ap.add_argument("--k", type=int, default=3)
    a = ap.parse_args()

    d = ec.load()
    keep = np.isin(d["y"], ec.DRUM10)
    X, y, g = d["X"][keep], d["y"][keep], d["vendor"][keep]
    paths = [p for p, kk in zip(d["paths"], keep) if kk]
    classes = ec.DRUM10
    F, pmask = pc.load_aligned(paths)
    if F is None:
        raise SystemExit("no physics cache -- run physics_cache.py")
    if not pmask.all():
        n = int((~pmask).sum())
        print(f"dropping {n} file(s) with no physics descriptors "
              f"(undecodable), keeping every array aligned")
        X, y, g = X[pmask], y[pmask], g[pmask]
        paths = [p for p, k in zip(paths, pmask) if k]
    assert len(F) == len(y) == len(X) == len(g), "alignment failure"
    print(f"{len(y)} files, {len(set(g))} collections\n")

    CANDIDATES = {
        "none": [],
        "Percussion": ["Percussion"],
        "Percussion+PercLoop": ["Percussion", "Percussion Loop"],
        "Percussion+Foley": ["Percussion", "Foley"],
        "all three": ["Percussion", "Percussion Loop", "Foley"],
    }
    res = {}
    print(f"{'split':22} {'mode':10} {'acc':>15} {'macroF1':>8} {'cov@95':>8} "
          f"{'Perc rec':>9} {'delta':>8}")
    base_acc = None
    for name, targets in CANDIDATES.items():
        for mode in (["none"] if not targets else ["embedding", "physics"]):
            accs, f1s, covs, precs = [], [], [], []
            for s in range(a.seeds):
                cv = StratifiedGroupKFold(a.splits, shuffle=True, random_state=s)
                oof = np.empty(len(y), dtype=object); conf = np.zeros(len(y))
                for tr, te in cv.split(X, y, groups=g):
                    assert not (set(g[tr]) & set(g[te])), "collection leak"
                    if targets:
                        sub, _ = split_labels(X[tr], F[tr], y[tr], targets,
                                              mode, a.k, s)
                    else:
                        sub = y[tr]
                    cls = sorted(set(sub))
                    p, c = ir.centroid_fit_predict(X[tr], sub, X[te], cls)
                    # map every sub-label back to its PARENT before scoring
                    oof[te] = np.array([q.split("::")[0] for q in p])
                    conf[te] = c
                ok = oof != None
                corr = (oof == y).astype(float)
                accs.append(100 * float(corr[ok].mean()))
                f1s.append(100 * f1_score(y[ok], oof[ok].astype(str),
                                          average="macro", zero_division=0))
                covs.append(ir.coverage_at(conf, corr, 0.95))
                mm = y == "Percussion"
                precs.append(100 * float((oof[mm] == "Percussion").mean()))
            acc = float(np.mean(accs))
            if base_acc is None:
                base_acc = acc
            dl = acc - base_acc
            flag = "  <-- GATE" if dl >= GATE else ""
            print(f"{name:22} {mode:10} {acc:7.2f}% +-{np.std(accs):4.2f} "
                  f"{np.mean(f1s):7.2f} {np.mean(covs):7.1f}% "
                  f"{np.mean(precs):8.1f}% {dl:+7.2f}{flag}")
            res[f"{name}|{mode}"] = {
                "acc": round(acc, 2), "sd": round(float(np.std(accs)), 2),
                "per_seed": [round(v, 2) for v in accs],
                "macro_f1": round(float(np.mean(f1s)), 2),
                "cov95": round(float(np.mean(covs)), 1),
                "percussion_recall": round(float(np.mean(precs)), 1),
                "delta": round(dl, 2)}
    json.dump({"gate_pp": GATE, "k": a.k, "seeds": a.seeds, "results": res,
               "promoted": [k for k, v in res.items() if v["delta"] >= GATE]},
              open(OUT, "w"), indent=2)
    print(f"\npromoted: "
          f"{[k for k, v in res.items() if v['delta'] >= GATE] or 'NONE'}")
    print(f"wrote {os.path.basename(OUT)}")


if __name__ == "__main__":
    main()
