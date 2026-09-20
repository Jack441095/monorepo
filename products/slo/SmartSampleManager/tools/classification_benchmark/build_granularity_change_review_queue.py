#!/usr/bin/env python3
"""Build a review-only queue for the granularity research-model changes.

The queue is deliberately evidence-first: it never creates a rename plan and
never mutates audio.  Rows are prioritised by gate transitions, rejection
boundaries, and duplicate risk so a human can audit the dangerous changes
before considering any production-model promotion.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

SD = Path(__file__).resolve().parent


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _attribute(path: str) -> tuple[str, str, str]:
    """Return root/vendor/pack using the inventory's stable attribution."""
    spec = importlib.util.spec_from_file_location("slo_inventory", SD / "sample_library_inventory.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    root, vendor, pack, _ = mod.attribute(path)
    return root, vendor, pack


def _load_cards(paths: list[str]) -> dict[str, dict[str, Any]]:
    if not paths:
        return {}
    spec = importlib.util.spec_from_file_location("slo_audio_cards", SD / "audio_definition_card.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    cards: dict[str, dict[str, Any]] = {}
    for path in paths:
        try:
            card = mod.analyse_file(path)
            cards[path] = card
        except Exception as exc:  # keep the review queue usable if one file is bad
            cards[path] = {"path": path, "error": str(exc)}
    return cards


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", type=Path,
                    default=SD / "results_granularity_model_candidate_effect_v1.json")
    ap.add_argument("--identity", type=Path,
                    default=SD / "results_content_identity_testing_v1.json")
    ap.add_argument("--near", type=Path,
                    default=SD / "results_near_duplicate_candidates_testing_v1.json")
    ap.add_argument("--out-json", type=Path,
                    default=SD / "results_granularity_change_review_queue_v1.json")
    ap.add_argument("--out-csv", type=Path,
                    default=SD / "granularity_change_review_queue_v1.csv")
    ap.add_argument("--cards", type=int, default=300,
                    help="number of highest-priority rows to analyse physically")
    ap.add_argument("--cards-out", type=Path,
                    default=SD / "results_granularity_change_definition_cards_v1.json")
    args = ap.parse_args()

    candidate = _load_json(args.candidate)
    identity = _load_json(args.identity)
    near = _load_json(args.near)

    exact_groups: dict[str, int] = {}
    exact_group_id: dict[str, str] = {}
    for group_id, members in identity.get("duplicate_content_groups", {}).items():
        for path in members:
            exact_groups[path] = len(members)
            exact_group_id[path] = str(group_id)

    near_groups: dict[str, int] = {}
    near_group_id: dict[str, str] = {}
    for index, group in enumerate(near.get("groups", []), start=1):
        members = group.get("member_paths", [])
        gid = f"near-{index:04d}"
        for path in members:
            near_groups[path] = len(members)
            near_group_id[path] = gid

    rows: list[dict[str, Any]] = []
    for raw in candidate.get("changed_rows", []):
        path = str(raw["path"])
        old = str(raw["old"])
        new = str(raw["new"])
        old_accept = bool(raw.get("old_accepted_at_95", False))
        new_accept = bool(raw.get("new_accepted_at_95", False))
        reasons: list[str] = []
        score = 0.0
        if not old_accept and new_accept:
            score += 100
            reasons.append("newly_accepted_at_95")
        if old_accept and not new_accept:
            score += 95
            reasons.append("lost_acceptance_at_95")
        if old in {"Other/none", "SFX"} or new in {"Other/none", "SFX"}:
            score += 40
            reasons.append("rejection_boundary")
        if old.endswith("Loop") != new.endswith("Loop"):
            score += 25
            reasons.append("one_shot_loop_boundary")
        if old in {"Kick", "Bass Hit", "Bass Reese"} or new in {"Kick", "Bass Hit", "Bass Reese"}:
            score += 20
            reasons.append("low_frequency_family_boundary")
        if exact_groups.get(path, 0) > 1:
            score += 22
            reasons.append("exact_duplicate_group")
        if near_groups.get(path, 0) > 1:
            score += 16
            reasons.append("near_duplicate_group")
        confidence_delta = float(raw["new_confidence"]) - float(raw["old_confidence"])
        similarity_delta = float(raw["new_similarity"]) - float(raw["old_similarity"])
        if float(raw["new_confidence"]) >= 0.90:
            score += 8
            reasons.append("high_new_confidence")
        if float(raw["new_similarity"]) >= 0.70:
            score += 6
            reasons.append("high_new_similarity")
        if not reasons:
            reasons.append("class_boundary_change")
        root, vendor, pack = _attribute(path)
        rows.append({
            "priority_score": round(score, 3),
            "review_reasons": reasons,
            "path": path,
            "root": root,
            "vendor": vendor,
            "pack": pack,
            "old_label": old,
            "new_label": new,
            "old_confidence": float(raw["old_confidence"]),
            "new_confidence": float(raw["new_confidence"]),
            "confidence_delta": round(confidence_delta, 6),
            "old_similarity": float(raw["old_similarity"]),
            "new_similarity": float(raw["new_similarity"]),
            "similarity_delta": round(similarity_delta, 6),
            "old_accepted_at_95": old_accept,
            "new_accepted_at_95": new_accept,
            "exact_duplicate_group": exact_group_id.get(path, ""),
            "exact_duplicate_count": exact_groups.get(path, 1),
            "near_duplicate_group": near_group_id.get(path, ""),
            "near_duplicate_count": near_groups.get(path, 1),
        })

    rows.sort(key=lambda r: (-r["priority_score"], r["path"]))
    for index, row in enumerate(rows, start=1):
        row["review_rank"] = index

    card_rows = rows[: max(0, args.cards)]
    cards = _load_cards([r["path"] for r in card_rows])
    card_errors = sum(1 for card in cards.values() if "error" in card)

    payload = {
        "record_type": "slo_granularity_change_review_queue",
        "schema_version": "1.0.0",
        "safety": {
            "read_only": True,
            "source_audio_modified": False,
            "rename_plan_created": False,
            "rename_actions": False,
            "production_model_changed": False,
        },
        "source_candidate": str(args.candidate),
        "source_identity": str(args.identity),
        "source_near_duplicates": str(args.near),
        "n_changed_rows": len(rows),
        "n_definition_cards_requested": len(card_rows),
        "n_definition_cards": len(cards) - card_errors,
        "n_definition_card_errors": card_errors,
        "priority_policy": [
            "gate transitions first",
            "rejection and one-shot/loop boundaries",
            "low-frequency family boundaries",
            "exact and acoustic near-duplicate groups",
            "high-confidence/high-similarity changes",
        ],
        "rows": rows,
        "definition_cards": cards,
    }
    args.out_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    args.cards_out.write_text(json.dumps({
        "record_type": "slo_granularity_change_definition_cards",
        "schema_version": "1.0.0",
        "safety": payload["safety"],
        "n_requested": len(card_rows),
        "n_cards": len(cards) - card_errors,
        "n_errors": card_errors,
        "cards": cards,
    }, indent=2) + "\n", encoding="utf-8")
    fieldnames = [
        "review_rank", "priority_score", "review_reasons", "path", "root", "vendor", "pack",
        "old_label", "new_label", "old_confidence", "new_confidence", "confidence_delta",
        "old_similarity", "new_similarity", "similarity_delta", "old_accepted_at_95",
        "new_accepted_at_95", "exact_duplicate_group", "exact_duplicate_count",
        "near_duplicate_group", "near_duplicate_count",
    ]
    with args.out_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            out["review_reasons"] = ";".join(out["review_reasons"])
            writer.writerow({key: out.get(key, "") for key in fieldnames})
    print(json.dumps({
        "n_changed_rows": len(rows),
        "n_definition_cards": len(cards) - card_errors,
        "n_definition_card_errors": card_errors,
        "top_rows": rows[:5],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
