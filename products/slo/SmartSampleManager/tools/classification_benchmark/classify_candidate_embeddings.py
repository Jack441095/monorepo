#!/usr/bin/env python3
"""Apply the frozen full-taxonomy model to candidate embeddings.

This produces a comparison report only. Full-taxonomy predictions are not
auto-rename eligible until class-level precision is measured on unseen
collections; the output therefore defaults every row to review.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from collections import Counter

import numpy as np

import full_taxonomy_infer as infer

SD = os.path.dirname(os.path.abspath(__file__))
MODEL = os.path.join(SD, "full_taxonomy_model_v1.npz")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def prior_audio_prediction(prior):
    """Return the old audio fields across both receipt generations."""
    return (
        prior.get("audio_class", prior.get("old_audio_class", "")),
        prior.get("audio_confidence", prior.get("old_audio_confidence", 0.0)),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--embeddings", required=True)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default=MODEL)
    args = ap.parse_args()

    z = np.load(args.embeddings, allow_pickle=True)
    paths = [os.path.abspath(str(p)) for p in z["paths"]]
    emb = np.asarray(z["emb"], dtype=np.float32)
    errors = list(z["errors"])
    model_path = os.path.abspath(args.model)
    model = infer.load_model(model_path)
    labels, conf, sim, accepted = infer.predict(emb, model)

    old = {}
    with open(args.plan) as f:
        next(f)
        for line in f:
            row = json.loads(line)
            old[os.path.abspath(row["path"])] = row
    rows = []
    for p, lab, c, s, ok, err in zip(paths, labels, conf, sim, accepted, errors):
        prior = old.get(p, {})
        # Historical prediction receipts use ``old_audio_class`` while the
        # live rename-plan arm uses ``audio_class``.  Read both spellings so
        # model-change diagnostics cannot silently report zero disagreements.
        prior_audio_class, prior_audio_confidence = prior_audio_prediction(prior)
        rows.append({
            "path": p,
            "old_audio_class": prior_audio_class,
            "old_audio_confidence": prior_audio_confidence,
            "filename_class": prior.get("filename_class", ""),
            "full_taxonomy_class": str(lab),
            "full_taxonomy_confidence": round(float(c), 6),
            "full_taxonomy_similarity": round(float(s), 6),
            "accepted_at_calibrated_95": bool(ok) and not bool(err),
            "action": "review",
            "reason": ("embedding_error" if err else
                       "full-taxonomy class precision not yet qualified for action"),
            "embedding_error": err,
        })
    counts = Counter(r["full_taxonomy_class"] for r in rows if not r["embedding_error"])
    disagreements = sum(
        bool(r["old_audio_class"]) and
        r["old_audio_class"] != r["full_taxonomy_class"] for r in rows)
    accepted_count = sum(r["accepted_at_calibrated_95"] for r in rows)
    header = {
        "record_type": "slo_full_taxonomy_candidate_predictions",
        "schema_version": "1.0.0",
        "n_rows": len(rows),
        "model": os.path.basename(model_path),
        "model_sha256": sha256(model_path),
        "embedding_file": os.path.abspath(args.embeddings),
        "accepted_at_calibrated_95": accepted_count,
        "old_model_disagreements": disagreements,
        "predicted_class_counts": dict(counts),
        "safety": "predictions are review-only; no filesystem mutation is performed",
    }
    directory = os.path.dirname(os.path.abspath(args.out)) or "."
    fd, tmp = tempfile.mkstemp(prefix=".full_predictions_", suffix=".jsonl",
                               dir=directory)
    os.close(fd)
    try:
        with open(tmp, "w") as f:
            f.write(json.dumps(header, sort_keys=True) + "\n")
            for row in rows:
                f.write(json.dumps(row, sort_keys=True) + "\n")
        os.replace(tmp, args.out)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    print(f"wrote {args.out}: {len(rows)} rows")
    print(f"accepted at calibrated 95% gate: {accepted_count}; "
          f"old-model disagreements: {disagreements}")
    print("top classes:", counts.most_common(12))


if __name__ == "__main__":
    raise SystemExit(main())
