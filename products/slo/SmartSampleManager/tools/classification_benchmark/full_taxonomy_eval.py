#!/usr/bin/env python3
"""Collection-held-out evaluation of every currently labelled taxonomy class.

This is deliberately separate from the frozen DRUM10 receipts. Those receipts
answer a historical product question; this report answers the current product
question: how much of the taxonomy can the incumbent name on an unseen
collection? Classes are never silently dropped: the report records every
label, its support, and the reason it is not eligible for the primary grouped
benchmark (too few examples or too few collections).

The default primary set requires at least five examples in at least five
collections. Lower-support classes remain in the diagnostic inventory and are
candidates for the next breadth-first label batch.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time

import numpy as np

SD = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(SD, "corpus_v2.npz")
OUT = os.path.join(SD, "results_full_taxonomy_eval_v1.json")


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(corpus_path=CORPUS):
    import sample_library_inventory as inv

    z = np.load(corpus_path, allow_pickle=True)
    paths = [os.path.abspath(str(p)) for p in z["paths"]]
    labels = np.asarray(z["labels"]).astype(str)
    X = np.asarray(z["emb"], dtype=np.float32)
    if not (len(paths) == len(labels) == len(X)):
        raise SystemExit("FAIL CLOSED: corpus paths, labels and embeddings are misaligned")

    # A duplicate path is one physical sample, not two independent examples.
    # Keep the first occurrence only, and fail if duplicate rows disagree.
    seen = {}
    keep = []
    for i, p in enumerate(paths):
        if p in seen:
            j = seen[p]
            if labels[i] != labels[j]:
                raise SystemExit(f"FAIL CLOSED: duplicate path has conflicting labels: {p}")
        else:
            seen[p] = i
            keep.append(i)
    keep = np.asarray(keep, dtype=int)
    paths, labels, X = [paths[i] for i in keep], labels[keep], X[keep]
    attrs = [inv.attribute(p) for p in paths]
    vendor = np.asarray([a[1] for a in attrs])
    pack = np.asarray([f"{a[1]}||{a[2]}" for a in attrs])
    family = np.asarray([inv.family_id(a[1], a[2], os.path.basename(p))
                         for a, p in zip(attrs, paths)])
    return dict(paths=paths, labels=labels, X=X, vendor=vendor, pack=pack,
                family=family, duplicate_rows=int(len(z["paths"]) - len(paths)))


def eligible_classes(d, min_examples, min_groups):
    result = {}
    for c in sorted(set(d["labels"])):
        m = d["labels"] == c
        n = int(m.sum())
        ng = int(len(set(d["vendor"][m])))
        reasons = []
        if n < min_examples:
            reasons.append(f"examples<{min_examples}")
        if ng < min_groups:
            reasons.append(f"collections<{min_groups}")
        result[c] = {"examples": n, "collections": ng,
                     "eligible": not reasons, "excluded_reasons": reasons}
    return result


def evaluate(d, classes, seeds, splits):
    from sklearn.metrics import f1_score, precision_recall_fscore_support
    from sklearn.model_selection import StratifiedGroupKFold
    import incumbent_receipt as ir

    m = np.isin(d["labels"], classes)
    X, y, groups = d["X"][m], d["labels"][m], d["vendor"][m]
    classes = list(classes)
    per_seed, f1s, cov90, cov95 = [], [], [], []
    last_pred = None
    for seed in range(seeds):
        oof = np.empty(len(y), dtype=object)
        conf = np.zeros(len(y), dtype=float)
        cv = StratifiedGroupKFold(n_splits=splits, shuffle=True,
                                  random_state=seed)
        for tr, te in cv.split(X, y, groups=groups):
            overlap = set(groups[tr]) & set(groups[te])
            if overlap:
                raise AssertionError(f"collection leakage: {sorted(overlap)[:3]}")
            p, c = ir.centroid_fit_predict(X[tr], y[tr], X[te], classes)
            oof[te], conf[te] = p, c
        correct = (oof == y).astype(float)
        per_seed.append(100 * float(correct.mean()))
        f1s.append(100 * f1_score(y, oof.astype(str), average="macro",
                                  zero_division=0))
        cov90.append(ir.coverage_at(conf, correct, 0.90))
        cov95.append(ir.coverage_at(conf, correct, 0.95))
        last_pred = oof

    p, r, f, support = precision_recall_fscore_support(
        y, last_pred.astype(str), labels=classes, zero_division=0)
    per_class = {
        c: {"precision": round(100 * float(p[i]), 1),
            "recall": round(100 * float(r[i]), 1),
            "f1": round(100 * float(f[i]), 1),
            "n": int(support[i])}
        for i, c in enumerate(classes)
    }
    return {
        "n_files": int(len(y)),
        "n_classes": len(classes),
        "n_collections": int(len(set(groups))),
        "classes": classes,
        "accuracy_mean": round(float(np.mean(per_seed)), 2),
        "accuracy_sd": round(float(np.std(per_seed)), 2),
        "per_seed": [round(float(x), 2) for x in per_seed],
        "macro_f1": round(float(np.mean(f1s)), 2),
        "coverage_at_90_precision": round(float(np.mean(cov90)), 1),
        "coverage_at_95_precision": round(float(np.mean(cov95)), 1),
        "per_class": per_class,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--splits", type=int, default=5)
    ap.add_argument("--min-examples", type=int, default=5)
    ap.add_argument("--min-collections", type=int, default=5)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--corpus", default=CORPUS)
    args = ap.parse_args()
    if args.splits < 2:
        raise SystemExit("--splits must be >= 2")

    d = load(args.corpus)
    inventory = eligible_classes(d, args.min_examples, args.min_collections)
    classes = [c for c, v in inventory.items() if v["eligible"]]
    if len(classes) < 2:
        raise SystemExit("FAIL CLOSED: fewer than two eligible classes")
    print(f"corpus {len(d['labels'])} unique files, {len(inventory)} labels, "
          f"{len(set(d['vendor']))} collections")
    print(f"primary set: {len(classes)} classes, >= {args.min_examples} examples "
          f"and >= {args.min_collections} collections")
    result = evaluate(d, classes, args.seeds, args.splits)
    print(f"  accuracy {result['accuracy_mean']}% +/- {result['accuracy_sd']} "
          f"{result['per_seed']}")
    print(f"  macro-F1 {result['macro_f1']}  coverage@90/95 "
          f"{result['coverage_at_90_precision']}% / "
          f"{result['coverage_at_95_precision']}%")
    print("\nlabels excluded from primary grouped score:")
    for c, v in inventory.items():
        if not v["eligible"]:
            print(f"  {c:25} n={v['examples']:3} collections={v['collections']:2} "
                  f"({', '.join(v['excluded_reasons'])})")

    z = np.load(args.corpus, allow_pickle=True)
    payload = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "protocol": {
            "split": "StratifiedGroupKFold by vendor/collection",
            "incumbent": "StandardScaler -> L2 -> cosine nearest centroid on frozen corpus_v2 embeddings",
            "seeds": args.seeds, "splits": args.splits,
            "min_examples": args.min_examples,
            "min_collections": args.min_collections,
        },
        "identity": {
            "corpus_sha256": sha256(args.corpus),
            "n_rows_on_disk": int(len(z["labels"])),
            "n_unique_paths": len(d["paths"]),
            "duplicate_rows_removed": d["duplicate_rows"],
            "label_hash": hashlib.sha256("\n".join(d["labels"]).encode()).hexdigest(),
            "path_hash": hashlib.sha256("\n".join(d["paths"]).encode()).hexdigest(),
            "embedding_hash": hashlib.sha256(np.ascontiguousarray(d["X"]).tobytes()).hexdigest(),
        },
        "label_inventory": inventory,
        "primary_result": result,
        "note": "Classes excluded for sparse collection support remain targets for breadth-first labelling; they are not treated as failed classes.",
    }
    with open(args.out, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    raise SystemExit(main())
