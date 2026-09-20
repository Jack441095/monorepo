#!/usr/bin/env python3
"""
Are Percussion and Other/none classes, or dumping grounds?

Phase 2 found nearest centroid beats logistic regression by +3.03pp
vendor-held-out, but it loses 12pp on exactly two classes: Percussion and
Other/none. A single centroid is a good model of a class that is one thing and a
bad model of a class that is several. That the two losses land precisely on the
project's two suspected catch-alls is a testable claim, not a coincidence.

Three experiments:

  1. COHERENCE. Mean cosine of each file to its class centroid, plus the
     silhouette of the class against the rest. A coherent class is tight and
     separated; a dumping ground is neither.

  2. SPLITTING. Cluster inside a class -- fitted on the TRAINING FOLD ONLY, so
     no test file influences the sub-classes -- give each sub-cluster its own
     centroid, and map predictions back to the parent label for scoring. If the
     class is genuinely multi-modal this should recover the lost recall. If it
     does not, the class is not merely multi-modal, it is unlearnable from this
     representation.

  3. SEPARATING REJECTION FROM CLASSIFICATION. The product is a confidence-gated
     renamer, so "I don't know" is safety-critical. Compare treating Other/none
     as a 10th class against dropping it from the classifier entirely and
     rejecting on centroid distance instead. Scored on precision at coverage
     over ALL files, with Other/none counted correct only when rejected.

Everything is vendor-held-out with repeated seeds.
"""
import os, json, argparse, warnings
import numpy as np
warnings.filterwarnings("ignore")

SD = os.path.dirname(os.path.abspath(__file__))
import domain_generalization_eval as dg   # noqa: E402

OUT = os.path.join(SD, "results_class_coherence_v1.json")
REJECT_CLASSES = ("Other/none",)


def znorm(X):
    return X / (np.linalg.norm(X, axis=1, keepdims=True) + 1e-9)


def fit_centroids(Z, y, classes):
    C = np.vstack([Z[y == c].mean(0) for c in classes])
    return znorm(C)


def coherence_table(d):
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import silhouette_samples
    X, y = d["feats"]["perch+clap"], d["y"]
    classes = sorted(set(y))
    Z = znorm(StandardScaler().fit_transform(X))
    sil = silhouette_samples(Z, y, metric="cosine")
    rows = {}
    for c in classes:
        m = y == c
        cen = Z[m].mean(0)
        cen /= np.linalg.norm(cen) + 1e-9
        coh = float((Z[m] @ cen).mean())
        # how many DISTINCT packs does the class draw from, relative to its size
        packs = len(set(d["pack"][m]))
        rows[c] = dict(n=int(m.sum()), coherence=round(coh, 4),
                       silhouette=round(float(sil[m].mean()), 4),
                       packs=packs, packs_per_file=round(packs / m.sum(), 3))
    return rows


def eval_split(d, seeds, splits, k_map):
    """Centroid model where named classes are split into k sub-centroids.

    Clusters are fitted inside the training fold only; predictions map back to
    the parent label before scoring, so the label space is unchanged.
    """
    from sklearn.preprocessing import StandardScaler
    from sklearn.cluster import KMeans
    from sklearn.metrics import f1_score
    X, y = d["feats"]["perch+clap"], d["y"]
    classes = sorted(set(y))
    accs, f1s, per_class = [], [], {c: [] for c in classes}
    for s in range(seeds):
        oof = np.empty(len(y), dtype=object)
        for tr, te in dg.splits_for("vendor", d, splits, s):
            sc = StandardScaler().fit(X[tr])
            Ztr, Zte = znorm(sc.transform(X[tr])), znorm(sc.transform(X[te]))
            cents, parents = [], []
            for c in classes:
                zc = Ztr[y[tr] == c]
                if len(zc) == 0:
                    continue
                k = k_map.get(c, 1)
                k = max(1, min(k, len(zc)))
                if k == 1:
                    cents.append(zc.mean(0)); parents.append(c)
                else:
                    km = KMeans(k, n_init=6, random_state=s).fit(zc)
                    for cc in km.cluster_centers_:
                        cents.append(cc); parents.append(c)
            C = znorm(np.vstack(cents))
            oof[te] = np.array(parents)[(Zte @ C.T).argmax(1)]
        ok = oof != None                                      # noqa: E711
        accs.append(100 * float((oof[ok] == y[ok]).mean()))
        f1s.append(100 * f1_score(y[ok], oof[ok].astype(str), average="macro",
                                  zero_division=0))
        for c in classes:
            m = y == c
            per_class[c].append(100 * float((oof[m] == c).mean()))
    return dict(acc=float(np.mean(accs)), sd=float(np.std(accs)),
                macro_f1=float(np.mean(f1s)),
                per_seed=[round(v, 2) for v in accs],
                per_class={c: round(float(np.mean(v)), 1)
                           for c, v in per_class.items()})


def eval_rejection(d, seeds, splits):
    """Reject on centroid distance instead of modelling Other/none as a class.

    Scored over ALL files: a real class is correct when predicted correctly and
    accepted; an Other/none file is correct only when REJECTED. Coverage is the
    accepted fraction, so this is directly comparable to the renamer's gate.
    """
    from sklearn.preprocessing import StandardScaler
    X, y = d["feats"]["perch+clap"], d["y"]
    real = [c for c in sorted(set(y)) if c not in REJECT_CLASSES]
    out = {"as_class": [], "as_rejection": []}
    for s in range(seeds):
        confA = np.zeros(len(y)); okA = np.zeros(len(y))
        confR = np.zeros(len(y)); okR = np.zeros(len(y))
        for tr, te in dg.splits_for("vendor", d, splits, s):
            sc = StandardScaler().fit(X[tr])
            Ztr, Zte = znorm(sc.transform(X[tr])), znorm(sc.transform(X[te]))
            # A: Other/none is a 10th class
            allc = sorted(set(y[tr]))
            CA = fit_centroids(Ztr, y[tr], allc)
            SA = Zte @ CA.T
            predA = np.array(allc)[SA.argmax(1)]
            confA[te] = SA.max(1)
            okA[te] = (predA == y[te]).astype(float)
            # R: classifier over real classes only; reject on similarity
            trr = tr[np.isin(y[tr], real)]
            CR = fit_centroids(znorm(sc.transform(X[trr])), y[trr], real)
            SR = Zte @ CR.T
            predR = np.array(real)[SR.argmax(1)]
            confR[te] = SR.max(1)
            is_junk = np.isin(y[te], REJECT_CLASSES)
            # accepted junk is always wrong; rejected junk is handled by coverage
            okR[te] = np.where(is_junk, 0.0, (predR == y[te]).astype(float))
        for key, conf, ok in (("as_class", confA, okA),
                              ("as_rejection", confR, okR)):
            o = np.argsort(-conf)
            cum = np.cumsum(ok[o]) / np.arange(1, len(o) + 1)
            hit = np.where(cum >= 0.95)[0]
            out[key].append(100 * (hit[-1] + 1) / len(o) if len(hit) else 0.0)
    return {k: dict(coverage_at_95=round(float(np.mean(v)), 1),
                    per_seed=[round(x, 1) for x in v]) for k, v in out.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=6)
    ap.add_argument("--splits", type=int, default=5)
    a = ap.parse_args()
    d = dg.load_corpus()
    print(f"{len(d['y'])} files, vendor-held-out, {a.seeds} seeds\n")

    print("1. CLASS COHERENCE -- is the class one thing?")
    coh = coherence_table(d)
    print(f"  {'class':>16} {'n':>4} {'coherence':>10} {'silhouette':>11} "
          f"{'packs':>6} {'packs/file':>11}")
    for c in sorted(coh, key=lambda k: coh[k]["coherence"]):
        r = coh[c]
        print(f"  {c:>16} {r['n']:4d} {r['coherence']:10.3f} "
              f"{r['silhouette']:11.3f} {r['packs']:6d} {r['packs_per_file']:11.3f}")

    print("\n2. SPLITTING the suspected dumping grounds")
    base = eval_split(d, a.seeds, a.splits, {})
    print(f"  {'model':38} {'acc':>15} {'macroF1':>9}")
    print(f"  {'single centroid per class (baseline)':38} "
          f"{base['acc']:7.1f}% +-{base['sd']:4.1f} {base['macro_f1']:8.1f}%")
    splits_tested = {"Percussion split into 2": {"Percussion": 2},
                     "Percussion split into 3": {"Percussion": 3},
                     "Other/none split into 3": {"Other/none": 3},
                     "both split into 3": {"Percussion": 3, "Other/none": 3},
                     "ALL classes into 2": {c: 2 for c in sorted(set(d["y"]))}}
    results = {"baseline": base}
    for name, kmap in splits_tested.items():
        r = eval_split(d, a.seeds, a.splits, kmap)
        results[name] = r
        print(f"  {name:38} {r['acc']:7.1f}% +-{r['sd']:4.1f} "
              f"{r['macro_f1']:8.1f}%  ({r['acc']-base['acc']:+.2f}pp)")

    print("\n  per-class recall on the two problem classes:")
    print(f"  {'model':38} {'Percussion':>11} {'Other/none':>11}")
    for name, r in results.items():
        print(f"  {name:38} {r['per_class'].get('Percussion', 0):10.1f}% "
              f"{r['per_class'].get('Other/none', 0):10.1f}%")

    print("\n3. REJECTION as a separate stage (the product question)")
    rej = eval_rejection(d, a.seeds, a.splits)
    print(f"  coverage at 95% precision, all files, Other/none correct only "
          f"if rejected:")
    print(f"    Other/none modelled as a 10th class : "
          f"{rej['as_class']['coverage_at_95']:5.1f}%")
    print(f"    rejection by centroid distance      : "
          f"{rej['as_rejection']['coverage_at_95']:5.1f}%")

    json.dump({"coherence": coh, "splitting": results, "rejection": rej,
               "seeds": a.seeds}, open(OUT, "w"), indent=2)
    print(f"\nwrote {os.path.basename(OUT)}")


if __name__ == "__main__":
    main()
