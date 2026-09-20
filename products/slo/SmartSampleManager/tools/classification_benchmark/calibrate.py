#!/usr/bin/env python3
"""
Confidence calibration for the renamer's gate.

The renamer only acts above a confidence threshold, so the gate IS the product.
Section 21 showed the gate is poorly calibrated: genuine none-of-the-above files
scored 0.809 mean confidence. A softmax maximum is not a probability of being
correct, so the threshold does not mean what it appears to.

Calibration does not chase accuracy. It makes the accuracy we have USABLE, by
letting the renamer act on more files without dropping below its precision
target.

Method:
  - honest out-of-fold probabilities (cross_val_predict), never fit-and-score
  - reliability: in each confidence bin, does stated confidence match observed
    accuracy? Expected Calibration Error (ECE) summarises the gap.
  - temperature scaling: fit T on one half of the OOF logits, evaluate on the
    other half, so the reported gain is not fitted on its own test data.
  - headline metric: COVERAGE AT 95% PRECISION -- what fraction of files can be
    auto-renamed while keeping 95% of those renames correct.
"""
import os, csv, warnings
import numpy as np
warnings.filterwarnings("ignore")

SD = os.path.dirname(os.path.abspath(__file__))


def ece(conf, correct, bins=10):
    """Expected Calibration Error: mean |confidence - accuracy| per bin."""
    edges = np.linspace(0, 1, bins + 1)
    e, n = 0.0, len(conf)
    rows = []
    for i in range(bins):
        m = (conf > edges[i]) & (conf <= edges[i + 1])
        if m.sum() == 0: continue
        acc = correct[m].mean(); c = conf[m].mean()
        e += (m.sum() / n) * abs(c - acc)
        rows.append((edges[i], edges[i + 1], int(m.sum()), c, acc))
    return e, rows


def coverage_at_precision(conf, correct, target=0.95):
    """Largest fraction of files renameable while keeping precision >= target."""
    order = np.argsort(-conf)
    c = correct[order]
    cum = np.cumsum(c) / np.arange(1, len(c) + 1)
    ok = np.where(cum >= target)[0]
    if len(ok) == 0: return 0.0, 1.0
    k = ok[-1] + 1
    return k / len(c), conf[order][k - 1]


def main():
    rows = [r for r in csv.DictReader(open(os.path.join(SD, "verified_drums.csv")))
            if r["label"] not in ("__skip__", "Misc/Review") and os.path.exists(r["path"])]
    y = np.array([r["label"] for r in rows])
    z = np.load(os.path.join(SD, "bioacoustic_emb.npz"))
    X = np.hstack([z["perch"], z["clap"]])

    from collections import Counter
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import make_pipeline
    from sklearn.model_selection import cross_val_predict, StratifiedKFold

    cnt = Counter(y)
    # Foley dropped (section 19); Other/none KEPT so rejection stays expressible
    viable = [c for c in cnt if cnt[c] >= 15 and c not in ("Foley", "Foley Loop")]
    m = np.isin(y, viable)
    Xv, yv = X[m], y[m]
    print(f"{len(yv)} files, {len(viable)} classes (Other/none retained as a "
          f"rejection class -- see section 21)\n")

    clf = make_pipeline(StandardScaler(),
                        LogisticRegression(max_iter=3000, class_weight="balanced"))
    # honest out-of-fold decision values
    logits = cross_val_predict(clf, Xv, yv, cv=5, method="decision_function")
    classes = np.unique(yv)

    def softmax(l, T=1.0):
        e = np.exp(l / T - (l / T).max(1, keepdims=True))
        return e / e.sum(1, keepdims=True)

    def eval_at(T):
        p = softmax(logits, T)
        conf = p.max(1); pred = classes[p.argmax(1)]
        correct = (pred == yv).astype(float)
        return conf, correct

    conf0, correct0 = eval_at(1.0)
    e0, rel = ece(conf0, correct0)
    print("reliability BEFORE (does stated confidence match observed accuracy?)")
    print(f"  {'confidence bin':>16} {'n':>5} {'stated':>8} {'actual':>8} {'gap':>7}")
    for lo, hi, n, c, acc in rel:
        print(f"  {lo:6.1f}-{hi:<9.1f} {n:5d} {c:8.3f} {acc:8.3f} {c-acc:+7.3f}")
    print(f"  ECE = {e0:.4f}\n")

    # fit temperature on half, evaluate on the other half (no self-fitting)
    skf = StratifiedKFold(n_splits=2, shuffle=True, random_state=0)
    a, b = next(iter(skf.split(Xv, yv)))
    def nll(T, idx):
        p = softmax(logits[idx], T)
        yi = np.array([np.where(classes == t)[0][0] for t in yv[idx]])
        return -np.log(p[np.arange(len(idx)), yi] + 1e-12).mean()
    Ts = np.linspace(0.25, 8.0, 200)
    T = Ts[int(np.argmin([nll(t, a) for t in Ts]))]
    print(f"fitted temperature T = {T:.2f} (on half A, evaluated on half B)\n")

    confT, correctT = eval_at(T)
    eT, relT = ece(confT[b], correctT[b])
    e_before_b, _ = ece(conf0[b], correct0[b])
    print(f"held-out half B:  ECE {e_before_b:.4f} -> {eT:.4f}"
          f"   ({100*(e_before_b-eT)/max(e_before_b,1e-9):+.0f}%)\n")

    print("THE PRODUCT METRIC -- coverage at 95% precision (held-out half B):")
    for name, cc, corr in (("uncalibrated", conf0[b], correct0[b]),
                           ("temperature-scaled", confT[b], correctT[b])):
        cov, thr = coverage_at_precision(cc, corr, 0.95)
        print(f"  {name:20} rename {100*cov:5.1f}% of files at >=95% precision "
              f"(gate {thr:.3f})")
    for name, cc, corr in (("uncalibrated", conf0[b], correct0[b]),
                           ("temperature-scaled", confT[b], correctT[b])):
        cov, thr = coverage_at_precision(cc, corr, 0.98)
        print(f"  {name:20} rename {100*cov:5.1f}% at >=98% precision (gate {thr:.3f})")

    np.savez(os.path.join(SD, "calibration.npz"), T=T, classes=classes)
    print(f"\nsaved calibration.npz (T={T:.3f})")


if __name__ == "__main__":
    main()
