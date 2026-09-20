#!/usr/bin/env python3
"""Controlled BEATs bake-off against the current SLO audio representation.

This is a research-only, read-only experiment.  It does not download a model,
change production weights, modify source audio, or create labels.  The caller
supplies an official/approved BEATs source checkout and checkpoint explicitly.

The evaluation deliberately uses the existing by-ear rows and the same
collection-held-out protocol used for SLO claims.  A result from random CV is
reported only as a diagnostic; it is never used as a promotion decision.

Example::

  python3 beats_bakeoff.py \
    --beats-source /tmp/unilm/beats \
    --checkpoint /tmp/BEATs_iter3_plus_AS20K.pt \
    --seeds 3 --splits 5

The generated receipt is disposable research evidence.  BEATs is not wired
into the product by this script.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

SD = Path(__file__).resolve().parent
VERIFIED = SD / "verified_drums.csv"
BASELINE = SD / "bioacoustic_emb.npz"
DEFAULT_OUT = SD / "results_beats_bakeoff_v1.json"


def file_sha256(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def load_rows():
    rows = [r for r in csv.DictReader(VERIFIED.open())
            if r["label"] not in ("__skip__", "Misc/Review")
            and os.path.exists(r["path"])]
    if not rows:
        raise SystemExit("FAIL CLOSED: no usable verified rows")
    z = np.load(BASELINE)
    if len(rows) != len(z["perch"]) or len(rows) != len(z["clap"]):
        raise SystemExit(
            f"FAIL CLOSED: verified rows={len(rows)} but baseline cache "
            f"has perch={len(z['perch'])}, clap={len(z['clap'])}")

    # The cache was generated from this exact filtered order.  Remove repeated
    # paths only when their labels agree, slicing every matrix identically.
    seen = {}
    keep = []
    for i, row in enumerate(rows):
        p = os.path.abspath(row["path"])
        if p in seen:
            j = seen[p]
            if rows[j]["label"] != row["label"]:
                raise SystemExit(
                    f"FAIL CLOSED: repeated path has conflicting labels: {p}")
        else:
            seen[p] = i
            keep.append(i)

    rows = [rows[i] for i in keep]
    base = {"perch": z["perch"][keep], "clap": z["clap"][keep]}
    paths = [os.path.abspath(r["path"]) for r in rows]
    labels = np.asarray([r["label"] for r in rows])

    # Importing the inventory module gives the canonical vendor/pack/family
    # attribution used by domain_generalization_eval.py.
    sys.path.insert(0, str(SD))
    import sample_library_inventory as inv  # noqa: E402

    attrs = [inv.attribute(p) for p in paths]
    vendor = np.asarray([a[1] for a in attrs])
    pack = np.asarray([f"{a[1]}||{a[2]}" for a in attrs])
    family = np.asarray([
        inv.family_id(a[1], a[2], os.path.basename(p))
        for a, p in zip(attrs, paths)
    ])
    if (vendor == "").any() or len(set(paths)) != len(paths):
        raise SystemExit("FAIL CLOSED: empty vendor or duplicate path remains")
    return dict(rows=rows, paths=paths, labels=labels, vendor=vendor,
                pack=pack, family=family, baseline=base)


def load_beats(source: Path, checkpoint: Path, device: str):
    """Load official BEATs implementation/checkpoint without mutating it."""
    sys.path.insert(0, str(source))
    from BEATs import BEATs, BEATsConfig  # type: ignore
    import torch

    ckpt = torch.load(str(checkpoint), map_location="cpu", weights_only=False)
    model = BEATs(BEATsConfig(ckpt["cfg"]))
    model.load_state_dict(ckpt["model"])
    model.eval()
    model.to(torch.device(device))
    return model, torch


def extract_beats(paths, source: Path, checkpoint: Path, device: str,
                  seconds: float, batch_size: int):
    import librosa
    import soundfile as sf

    model, torch = load_beats(source, checkpoint, device)
    sr = 16_000
    n = int(sr * seconds)
    out = []
    for start in range(0, len(paths), batch_size):
        wavs = []
        for path in paths[start:start + batch_size]:
            y, sr0 = sf.read(path, dtype="float32", always_2d=False)
            if y.ndim > 1:
                y = y.mean(axis=1)
            if sr0 != sr:
                y = librosa.resample(y, orig_sr=sr0, target_sr=sr)
            y = np.asarray(y[:n], dtype=np.float32)
            x = np.zeros(n, dtype=np.float32)
            x[:len(y)] = y
            wavs.append(x)
        batch = torch.from_numpy(np.stack(wavs)).to(torch.device(device))
        with torch.inference_mode():
            # Padding is intentionally omitted: every input is a deterministic
            # fixed-length view, matching the fixed-window SLO preprocessing.
            frame_features, _ = model.extract_features(batch, padding_mask=None)
            pooled = frame_features.mean(dim=1).detach().cpu().numpy()
        out.append(pooled.astype(np.float32))
        done = min(start + batch_size, len(paths))
        print(f"  BEATs {done}/{len(paths)}", flush=True)
    return np.concatenate(out, axis=0)


def groups_for(d, mode):
    if mode == "vendor":
        return d["vendor"]
    if mode == "pack":
        return d["pack"]
    if mode == "family":
        return d["family"]
    if mode == "random":
        return None
    raise ValueError(mode)


def predict_centroid(x_train, y_train, x_test, classes):
    from sklearn.preprocessing import StandardScaler

    scaler = StandardScaler().fit(x_train)
    a = scaler.transform(x_train)
    b = scaler.transform(x_test)
    a /= np.maximum(np.linalg.norm(a, axis=1, keepdims=True), 1e-12)
    b /= np.maximum(np.linalg.norm(b, axis=1, keepdims=True), 1e-12)
    centroids = []
    for c in classes:
        if not np.any(y_train == c):
            raise SystemExit(
                f"FAIL CLOSED: class {c!r} is absent from a training fold")
        v = a[y_train == c].mean(axis=0)
        v /= max(np.linalg.norm(v), 1e-12)
        centroids.append(v)
    return np.asarray(classes)[np.argmax(b @ np.asarray(centroids).T, axis=1)]


def evaluate(x, labels, groups, mode, seeds, splits):
    from sklearn.metrics import accuracy_score, f1_score
    from sklearn.model_selection import StratifiedGroupKFold, StratifiedKFold

    classes = np.asarray(sorted(set(labels)))
    scores = []
    for seed in seeds:
        if mode == "random":
            splitter = StratifiedKFold(n_splits=splits, shuffle=True,
                                       random_state=seed)
            iterator = splitter.split(x, labels)
        else:
            splitter = StratifiedGroupKFold(n_splits=splits, shuffle=True,
                                            random_state=seed)
            iterator = splitter.split(x, labels, groups)
        fold_acc = []
        fold_f1 = []
        for train, test in iterator:
            if mode != "random":
                overlap = set(groups[train]) & set(groups[test])
                if overlap:
                    raise SystemExit(f"FAIL CLOSED: group leakage in {mode}: {overlap}")
            pred = predict_centroid(x[train], labels[train], x[test], classes)
            fold_acc.append(float(accuracy_score(labels[test], pred)))
            fold_f1.append(float(f1_score(labels[test], pred, average="macro",
                                          zero_division=0)))
        scores.append({"seed": int(seed), "accuracy": float(np.mean(fold_acc)),
                       "macro_f1": float(np.mean(fold_f1)),
                       "fold_accuracy": fold_acc})
    return scores


def summarize(scores):
    a = np.asarray([x["accuracy"] for x in scores], dtype=float)
    f = np.asarray([x["macro_f1"] for x in scores], dtype=float)
    return {"accuracy_mean": float(a.mean()),
            "accuracy_sd": float(a.std(ddof=1)) if len(a) > 1 else 0.0,
            "macro_f1_mean": float(f.mean()),
            "macro_f1_sd": float(f.std(ddof=1)) if len(f) > 1 else 0.0,
            "per_seed": scores}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--beats-source", required=True, type=Path,
                    help="directory containing BEATs.py and backbone.py")
    ap.add_argument("--checkpoint", required=True, type=Path)
    ap.add_argument("--cache", type=Path,
                    default=SD / "beats_embeddings_v1.npz")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--device", default="cpu", choices=("cpu", "mps"))
    ap.add_argument("--seconds", type=float, default=10.0)
    ap.add_argument("--batch-size", type=int, default=4)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--splits", type=int, default=5)
    ap.add_argument("--min-class", type=int, default=15,
                    help="minimum rows per class, matching the canonical evaluator")
    args = ap.parse_args()

    for p in (args.beats_source / "BEATs.py", args.beats_source / "backbone.py",
              args.checkpoint):
        if not p.exists():
            raise SystemExit(f"missing required input: {p}")

    d = load_rows()
    if args.cache.exists():
        cache = np.load(args.cache, allow_pickle=False)
        cache_paths = cache["paths"].astype(str).tolist()
        if cache_paths != d["paths"]:
            raise SystemExit("FAIL CLOSED: BEATs cache path order is stale")
        beats = cache["embeddings"].astype(np.float32)
        cache_hit = True
    else:
        beats = extract_beats(d["paths"], args.beats_source, args.checkpoint,
                              args.device, args.seconds, args.batch_size)
        if len(beats) != len(d["paths"]):
            raise SystemExit("FAIL CLOSED: BEATs output row count mismatch")
        np.savez_compressed(args.cache, embeddings=beats,
                            paths=np.asarray(d["paths"], dtype=str),
                            checkpoint_sha256=file_sha256(args.checkpoint),
                            seconds=np.asarray(args.seconds))
        cache_hit = False

    # Use only classes with enough observations for every requested grouped
    # fold, as the canonical grouped evaluator does.
    from collections import Counter
    counts = Counter(d["labels"])
    viable = sorted(c for c, n in counts.items() if n >= args.min_class)
    mask = np.isin(d["labels"], viable)
    labels = d["labels"][mask]
    groups = {k: groups_for({"vendor": d["vendor"][mask],
                             "pack": d["pack"][mask],
                             "family": d["family"][mask]}, k)
              for k in ("vendor", "pack", "family", "random")}
    perch = d["baseline"]["perch"][mask]
    clap = d["baseline"]["clap"][mask]
    beats = beats[mask]
    features = {
        "perch+clap_incumbent": np.hstack([perch, clap]),
        "beats": beats,
        "beats+perch+clap": np.hstack([perch, clap, beats]),
    }
    seeds = list(range(args.seeds))
    result = {
        "record_type": "slo_beats_bakeoff",
        "schema_version": "1.0.0",
        "safety": "research-only; read-only; no production or source-audio mutation",
        "checkpoint": str(args.checkpoint),
        "checkpoint_sha256": file_sha256(args.checkpoint),
        "beats_source": str(args.beats_source),
        "n_rows": int(mask.sum()),
        "n_classes": len(viable),
        "classes": viable,
        "cache_hit": cache_hit,
        "preprocessing": {"sample_rate": 16000, "seconds": args.seconds,
                           "device": args.device},
        "evaluation": {"seeds": seeds, "splits": args.splits,
                        "grouping": "vendor (primary), pack/family/random diagnostics",
                        "estimator": "standardized L2 cosine nearest centroid"},
        "results": {},
    }
    for name, x in features.items():
        print(f"evaluating {name}", flush=True)
        result["results"][name] = {}
        for mode in ("vendor", "pack", "family", "random"):
            result["results"][name][mode] = summarize(
                evaluate(x, labels, groups[mode], mode, seeds, args.splits))
    # A simple paired vendor delta is the only promotion-relevant comparison.
    base = result["results"]["perch+clap_incumbent"]["vendor"]["per_seed"]
    for name in ("beats", "beats+perch+clap"):
        cur = result["results"][name]["vendor"]["per_seed"]
        result["results"][name]["vendor"]["paired_delta_pp"] = [
            100.0 * (b["accuracy"] - a["accuracy"])
            for a, b in zip(base, cur)
        ]
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"out": str(args.out), "n_rows": int(mask.sum()),
                      "cache_hit": cache_hit,
                      "vendor": {k: result["results"][k]["vendor"]["accuracy_mean"]
                                 for k in features}}, indent=2))


if __name__ == "__main__":
    main()
