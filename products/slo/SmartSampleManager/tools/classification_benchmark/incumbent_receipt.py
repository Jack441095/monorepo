#!/usr/bin/env python3
"""
Freeze the nearest-centroid incumbent.

Every later experiment must be judged against ONE fixed definition of the
incumbent, evaluated on ONE fixed dataset under ONE fixed split rule. Without
that, a later "+2pp" can come from a quietly changed filter, a different
normalization, or a different fold seed, and nobody would notice. This project
has already produced two false positives that way (the Other/none removal and
the LoRA control).

So this writes a receipt containing the hashes and rules that define the
measurement, plus the full incumbent result. `verify()` re-derives the hashes
and refuses to proceed if anything has drifted.

The receipt is the contract. If it fails to verify, the correct response is to
find out what changed -- not to regenerate the receipt.

Usage:
  python3 incumbent_receipt.py --freeze --seeds 8
  python3 incumbent_receipt.py --verify
"""
import os, csv, json, time, hashlib, argparse, warnings
import numpy as np
warnings.filterwarnings("ignore")

SD = os.path.dirname(os.path.abspath(__file__))
import domain_generalization_eval as dg          # noqa: E402
import sample_library_inventory as inv           # noqa: E402

OUT = os.path.join(SD, "incumbent_receipt_v1.json")
VERIFIED = os.path.join(SD, "verified_drums.csv")
EMB = os.path.join(SD, "bioacoustic_emb.npz")
SEALED = os.path.join(SD, "sealed_holdout_vendors_v1.json")


def sha(path, nbytes=None):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read(nbytes) if nbytes else f.read())
    return h.hexdigest()


def array_hash(a):
    return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()


# --------------------------------------------------------------------------
# the incumbent itself -- one definition, used everywhere
# --------------------------------------------------------------------------
def znorm(X):
    return X / (np.linalg.norm(X, axis=1, keepdims=True) + 1e-9)


def centroid_fit_predict(Xtr, ytr, Xte, classes):
    """THE incumbent: standardise, L2-normalise, cosine to class means.

    Returns (predictions, confidence) where confidence is a softmax over cosine
    similarities -- the renamer is confidence-gated, so the incumbent must
    expose a usable score, not only an argmax.
    """
    from sklearn.preprocessing import StandardScaler
    sc = StandardScaler().fit(Xtr)
    Ztr, Zte = znorm(sc.transform(Xtr)), znorm(sc.transform(Xte))
    C = znorm(np.vstack([Ztr[ytr == c].mean(0) for c in classes]))
    S = Zte @ C.T
    e = np.exp((S - S.max(1, keepdims=True)) * 8.0)
    return np.array(classes)[S.argmax(1)], (e / e.sum(1, keepdims=True)).max(1)


def coverage_at(conf, correct, target):
    o = np.argsort(-conf)
    cum = np.cumsum(correct[o]) / np.arange(1, len(o) + 1)
    ok = np.where(cum >= target)[0]
    return (100.0 * (ok[-1] + 1) / len(o)) if len(ok) else 0.0


def evaluate(d, mode, seeds, splits):
    from sklearn.metrics import (f1_score, precision_recall_fscore_support,
                                 confusion_matrix)
    X, y = d["feats"]["perch+clap"], d["y"]
    classes = d["classes"]
    per_seed, f1s, worst_folds, top2s = [], [], [], []
    cov = {90: [], 95: [], 98: []}
    fa_other = []
    oof_last = conf_last = None
    for s in range(seeds):
        oof = np.empty(len(y), dtype=object)
        conf = np.zeros(len(y))
        fold_acc = []
        for tr, te in dg.splits_for(mode, d, splits, s):
            p, c = centroid_fit_predict(X[tr], y[tr], X[te], classes)
            oof[te], conf[te] = p, c
            fold_acc.append(float((p == y[te]).mean()))
        ok = oof != None                                        # noqa: E711
        correct = (oof == y).astype(float)
        per_seed.append(100 * float(correct[ok].mean()))
        f1s.append(100 * f1_score(y[ok], oof[ok].astype(str), average="macro",
                                  zero_division=0))
        worst_folds.append(100 * min(fold_acc))
        for t in cov:
            cov[t].append(coverage_at(conf, correct, t / 100))
        # false accept: Other/none predicted as a real class at a 0.5 gate
        m = y == "Other/none"
        if m.any():
            fa_other.append(100 * float(((oof[m] != "Other/none")
                                         & (conf[m] >= 0.5)).mean()))
        oof_last, conf_last = oof, conf
    ok = oof_last != None                                       # noqa: E711
    p_, r_, f_, sup = precision_recall_fscore_support(
        y[ok], oof_last[ok].astype(str), labels=classes, zero_division=0)
    cm = confusion_matrix(y[ok], oof_last[ok].astype(str), labels=classes)
    by_vendor = {}
    for v in sorted(set(d["vendor"])):
        m = (d["vendor"] == v) & ok
        if m.sum() >= 8:
            by_vendor[v] = round(100 * float((oof_last[m] == y[m]).mean()), 1)
    return dict(
        accuracy_mean=round(float(np.mean(per_seed)), 2),
        accuracy_sd=round(float(np.std(per_seed)), 2),
        per_seed=[round(v, 2) for v in per_seed],
        macro_f1=round(float(np.mean(f1s)), 2),
        worst_fold=round(float(np.mean(worst_folds)), 2),
        coverage_at_90=round(float(np.mean(cov[90])), 1),
        coverage_at_95=round(float(np.mean(cov[95])), 1),
        coverage_at_98=round(float(np.mean(cov[98])), 1),
        other_none_false_accept=round(float(np.mean(fa_other)), 2) if fa_other else None,
        worst_vendor=min(by_vendor, key=by_vendor.get) if by_vendor else None,
        worst_vendor_acc=min(by_vendor.values()) if by_vendor else None,
        by_vendor=by_vendor,
        per_class={c: dict(precision=round(100 * p_[i], 1),
                           recall=round(100 * r_[i], 1),
                           f1=round(100 * f_[i], 1), n=int(sup[i]))
                   for i, c in enumerate(classes)},
        confusion_matrix=cm.tolist())


def build_identity(d):
    rows = list(csv.DictReader(open(VERIFIED)))
    return {
        "verified_csv_sha256": sha(VERIFIED),
        "verified_csv_rows": len(rows),
        "embedding_npz_sha256": sha(EMB),
        "n_files_evaluated": int(len(d["y"])),
        "classes": d["classes"],
        "label_hash": array_hash(d["y"].astype("U32")),
        "path_hash": hashlib.sha256("\n".join(d["paths"]).encode()).hexdigest(),
        "feature_hash_perch_clap": array_hash(d["feats"]["perch+clap"]),
        "vendor_hash": array_hash(d["vendor"].astype("U128")),
        "family_hash": array_hash(d["family"].astype("U256")),
        "sealed_vendors": json.load(open(SEALED))["sealed_vendors"],
    }


RULES = {
    "deduplication": "by absolute path, first occurrence kept; conflicting "
                     "duplicate labels abort rather than pick one",
    "min_class_size": 15,
    "excluded_labels": ["__skip__", "Misc/Review"],
    "existence_filter": "os.path.exists at load time",
    "collection_parsing": "sample_library_inventory.attribute(); three roots "
                          "parsed separately; personal folders namespaced "
                          "'personal:<dir>'; vendor never empty",
    "family_normalisation": "sample_library_inventory.family_id(); separators "
                            "normalised BEFORE token rules; strips numeric "
                            "suffixes, note names, BPM, velocity, round robins; "
                            "preserves class words",
    "features": "Perch v2 (ONNX, 1536-D, 32kHz/5s) + CLAP music (512-D, 48kHz), "
                "concatenated to 2048-D, frozen",
    "head": "StandardScaler -> L2 normalise -> cosine to class means; "
            "confidence = softmax(8 * cosine)",
    "primary_metric": "vendor-grouped (collection-held-out) accuracy",
    "diagnostic_only": "random StratifiedKFold -- overstates by ~9.7pp",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--splits", type=int, default=5)
    a = ap.parse_args()

    d = dg.load_corpus(RULES["min_class_size"])
    ident = build_identity(d)

    if a.verify:
        if not os.path.exists(OUT):
            raise SystemExit("no receipt to verify -- run --freeze first")
        r = json.load(open(OUT))
        drift = [k for k, v in r["identity"].items()
                 if k in ident and ident[k] != v]
        if drift:
            print("RECEIPT VERIFICATION FAILED -- these have drifted:")
            for k in drift:
                print(f"  {k}\n    receipt: {str(r['identity'][k])[:70]}"
                      f"\n    now    : {str(ident[k])[:70]}")
            print("\nDo NOT regenerate the receipt to make this pass. Find out "
                  "what changed: a drifted dataset or feature hash invalidates "
                  "every comparison made against this incumbent.")
            return 1
        print(f"receipt verified -- dataset, features, labels and grouping "
              f"unchanged since {r['generated']}")
        print(f"  incumbent: {r['results']['vendor']['accuracy_mean']}% "
              f"collection-held-out")
        return 0

    print(f"{len(d['y'])} files, {len(d['classes'])} classes, "
          f"{a.seeds} seeds x {a.splits} folds")
    res = {}
    for mode in ("vendor", "pack", "family", "random"):
        res[mode] = evaluate(d, mode, a.seeds, a.splits)
        print(f"  {mode:8} {res[mode]['accuracy_mean']:6.2f}% "
              f"+-{res[mode]['accuracy_sd']:.2f}  macroF1 "
              f"{res[mode]['macro_f1']:.1f}  cov@95 "
              f"{res[mode]['coverage_at_95']:.1f}%")

    payload = {"generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
               "incumbent": "nearest centroid on frozen Perch+CLAP",
               "seeds": a.seeds, "splits": a.splits,
               "rules": RULES, "identity": ident, "results": res,
               "primary_result_vendor_held_out": res["vendor"]["accuracy_mean"],
               "note": "random CV is recorded as a DIAGNOSTIC only; it "
                       "overstates collection-held-out accuracy by ~9.7pp and "
                       "must never be used as a promotion baseline"}
    with open(OUT, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"\nfrozen -> {os.path.basename(OUT)}")
    v = res["vendor"]
    print(f"  primary (collection-held-out): {v['accuracy_mean']}% "
          f"+-{v['accuracy_sd']}  seeds {v['per_seed']}")
    print(f"  coverage @90/95/98% precision : {v['coverage_at_90']}% / "
          f"{v['coverage_at_95']}% / {v['coverage_at_98']}%")
    print(f"  Other/none false accept @0.5  : {v['other_none_false_accept']}%")
    print(f"  worst collection              : {v['worst_vendor']} "
          f"({v['worst_vendor_acc']}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
