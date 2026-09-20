#!/usr/bin/env python3
"""Audit a relabelled research model on the fixed testing embeddings.

This is a review-only comparison.  It emits no rename plan and cannot approve
or apply an action.  The candidate embedding cache is already derived from
the testing library; source bytes are not opened or modified here.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from collections import Counter
from pathlib import Path

import numpy as np

SD = Path(__file__).resolve().parent


def infer_module():
    spec = importlib.util.spec_from_file_location("slo_full_taxonomy_infer", SD / "full_taxonomy_infer.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--embeddings", type=Path,
                    default=SD / "candidate_embeddings_testing_v1.npz")
    ap.add_argument("--old-model", type=Path,
                    default=SD / "full_taxonomy_model_v3.npz")
    ap.add_argument("--new-model", type=Path,
                    default=SD / "full_taxonomy_model_granularity_v1.npz")
    ap.add_argument("--out", type=Path,
                    default=SD / "results_granularity_model_candidate_effect_v1.json")
    args = ap.parse_args()

    infer = infer_module()
    z = np.load(args.embeddings, allow_pickle=True)
    X = np.asarray(z["emb"], dtype=np.float32)
    paths = [str(p) for p in z["paths"]]
    errors = [str(x) for x in z.get("errors", np.asarray([""] * len(paths)))]
    if len(paths) != len(X) or len(errors) != len(paths):
        raise SystemExit("FAIL CLOSED: candidate embeddings are misaligned")
    if any(errors):
        raise SystemExit("FAIL CLOSED: candidate embedding cache contains errors")

    old = infer.load_model(str(args.old_model))
    new = infer.load_model(str(args.new_model))
    old_labels, old_conf, old_sim, old_accept = infer.predict(X, old)
    new_labels, new_conf, new_sim, new_accept = infer.predict(X, new)
    changed = [
        {"path": p, "old": str(a), "new": str(b),
         "old_confidence": float(ca), "new_confidence": float(cb),
         "old_similarity": float(sa), "new_similarity": float(sb),
         "old_accepted_at_95": bool(oa), "new_accepted_at_95": bool(na)}
        for p, a, b, ca, cb, sa, sb, oa, na in zip(
            paths, old_labels, new_labels, old_conf, new_conf, old_sim, new_sim,
            old_accept, new_accept)
        if a != b
    ]
    result = {
        "record_type": "slo_granularity_model_candidate_effect",
        "schema_version": "1.0.0",
        "safety": "review-only; no rename plan; no source mutation",
        "n_files": len(paths),
        "old_model": str(args.old_model),
        "new_model": str(args.new_model),
        "old_accepted_at_95": int(old_accept.sum()),
        "new_accepted_at_95": int(new_accept.sum()),
        "label_changes": len(changed),
        "changed_label_pairs": {
            f"{a} -> {b}": int(n)
            for (a, b), n in Counter((r["old"], r["new"]) for r in changed).items()
        },
        "old_class_counts": dict(Counter(str(x) for x in old_labels)),
        "new_class_counts": dict(Counter(str(x) for x in new_labels)),
        "changed_rows": changed,
    }
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in (
        "n_files", "old_accepted_at_95", "new_accepted_at_95",
        "label_changes", "changed_label_pairs")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
