#!/usr/bin/env python3
"""Project class-conditional gates onto unseen embeddings for review only."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
from pathlib import Path
from typing import Any

import numpy as np

SD = Path(__file__).resolve().parent


def _infer_module():
    spec = importlib.util.spec_from_file_location("slo_full_taxonomy_infer", SD / "full_taxonomy_infer.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gates", type=Path,
                    default=SD / "results_class_conditional_gates_granularity_v1.json")
    ap.add_argument("--embeddings", type=Path,
                    default=SD / "candidate_embeddings_testing_v1.npz")
    ap.add_argument("--model", type=Path,
                    default=SD / "full_taxonomy_model_granularity_v1.npz")
    ap.add_argument("--identity", type=Path,
                    default=SD / "results_content_identity_testing_v1.json")
    ap.add_argument("--near", type=Path,
                    default=SD / "results_near_duplicate_candidates_testing_v1.json")
    ap.add_argument("--out", type=Path,
                    default=SD / "results_class_conditional_gate_testing_review_v1.json")
    ap.add_argument("--csv", type=Path,
                    default=SD / "class_conditional_gate_testing_review_v1.csv")
    ap.add_argument("--cards-out", type=Path,
                    default=SD / "results_class_conditional_gate_testing_cards_v1.json")
    args = ap.parse_args()

    gate_payload = json.loads(args.gates.read_text(encoding="utf-8"))
    robust = gate_payload.get("robust_candidate_classes", [])
    gate_by_class = {
        cls: float(gate_payload["classes"][cls]["conservative_threshold"])
        for cls in robust
    }
    if not gate_by_class:
        raise SystemExit("FAIL CLOSED: no robust class-conditional gates")
    identity = json.loads(args.identity.read_text(encoding="utf-8"))
    exact_group_by_path: dict[str, tuple[str, int]] = {}
    for group_id, members in identity.get("duplicate_content_groups", {}).items():
        for member in members:
            exact_group_by_path[str(member)] = (str(group_id), len(members))
    near = json.loads(args.near.read_text(encoding="utf-8"))
    near_group_by_path: dict[str, tuple[str, int]] = {}
    for index, group in enumerate(near.get("groups", []), start=1):
        members = group.get("member_paths", [])
        for member in members:
            near_group_by_path[str(member)] = (f"near-{index:04d}", len(members))
    infer = _infer_module()
    z = np.load(args.embeddings, allow_pickle=True)
    X = np.asarray(z["emb"], dtype=np.float32)
    paths = [str(p) for p in z["paths"]]
    errors = [str(e) for e in z.get("errors", np.asarray([""] * len(paths)))]
    if len(paths) != len(X) or len(errors) != len(paths) or any(errors):
        raise SystemExit("FAIL CLOSED: testing embeddings are misaligned or contain errors")
    model = infer.load_model(str(args.model))
    labels, conf, sim, accepted = infer.predict(X, model)
    rows: list[dict[str, Any]] = []
    for path, label, confidence, similarity, global_accept in zip(paths, labels, conf, sim, accepted):
        label = str(label)
        threshold = gate_by_class.get(label)
        if threshold is None:
            continue
        class_gate = bool(float(confidence) >= threshold)
        similarity_gate = bool(float(similarity) >= model["similarity_gate_95"])
        if class_gate and similarity_gate:
            exact_group, exact_count = exact_group_by_path.get(path, ("", 1))
            near_group, near_count = near_group_by_path.get(path, ("", 1))
            rows.append({
                "path": path,
                "candidate_class": label,
                "confidence": float(confidence),
                "similarity": float(similarity),
                "class_gate_threshold": threshold,
                "similarity_gate_threshold": float(model["similarity_gate_95"]),
                "global_gate_would_accept": bool(global_accept),
                "exact_duplicate_group": exact_group,
                "exact_duplicate_count": exact_count,
                "near_duplicate_group": near_group,
                "near_duplicate_count": near_count,
                "action": "review_candidate_only",
                "auto_approved": False,
            })
    rows.sort(key=lambda r: (-r["confidence"], -r["similarity"], r["path"]))
    counts: dict[str, int] = {c: 0 for c in gate_by_class}
    global_counts: dict[str, int] = {c: 0 for c in gate_by_class}
    for row in rows:
        counts[row["candidate_class"]] += 1
        if row["global_gate_would_accept"]:
            global_counts[row["candidate_class"]] += 1
    payload = {
        "record_type": "slo_class_conditional_gate_testing_review",
        "schema_version": "1.0.0",
        "method_version": "class_conditional_gate_projection_v1",
        "safety": {"read_only": True, "source_audio_modified": False,
                   "production_model_changed": False, "rename_actions": False,
                   "auto_approved": False},
        "source_gates": str(args.gates.resolve()),
        "source_embeddings": str(args.embeddings.resolve()),
        "source_model": str(args.model.resolve()),
        "source_identity": str(args.identity.resolve()),
        "source_near_duplicates": str(args.near.resolve()),
        "candidate_classes": gate_by_class,
        "testing_summary": {
            "n_input": len(paths),
            "n_review_candidates": len(rows),
            "counts_by_class": counts,
            "global_gate_subset_counts_by_class": global_counts,
            "n_exact_duplicate_candidates": sum(bool(r["exact_duplicate_group"]) for r in rows),
            "n_near_duplicate_candidates": sum(bool(r["near_duplicate_group"]) for r in rows),
        },
        "decision": "review-only projection; training-corpus gates are not new-domain qualification",
        "rows": rows,
    }
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    with args.csv.open("w", newline="", encoding="utf-8") as handle:
        fields = ["path", "candidate_class", "confidence", "similarity",
                  "class_gate_threshold", "similarity_gate_threshold",
                  "global_gate_would_accept", "exact_duplicate_group",
                  "exact_duplicate_count", "near_duplicate_group",
                  "near_duplicate_count", "action", "auto_approved"]
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    card_spec = importlib.util.spec_from_file_location("slo_audio_definition_card", SD / "audio_definition_card.py")
    card_mod = importlib.util.module_from_spec(card_spec)
    assert card_spec.loader is not None
    card_spec.loader.exec_module(card_mod)
    cards = []
    errors = []
    for row in rows:
        try:
            cards.append(card_mod.analyse_file(row["path"]))
        except Exception as exc:
            errors.append({"path": row["path"], "error": str(exc)})
    args.cards_out.write_text(json.dumps({
        "record_type": "slo_class_conditional_gate_testing_cards",
        "schema_version": "1.0.0",
        "safety": payload["safety"],
        "n_requested": len(rows), "n_cards": len(cards),
        "n_errors": len(errors), "cards": cards, "errors": errors,
    }, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["testing_summary"], indent=2))
    print(f"wrote {args.out}")
    print(f"wrote {args.csv}")
    print(f"wrote {args.cards_out} ({len(cards)} cards; {len(errors)} errors)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
