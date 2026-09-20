#!/usr/bin/env python3
"""Plan owner review coverage needed to clear the research metadata gate.

This report is deliberately prospective: candidate options are treated as
possible destinations, never as labels. It combines the current manifest with
the taxonomy-gap queue and shows the remaining per-class source-family gaps so
review batches can be prioritized for evidence rather than volume.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


EXPECTED_CLASSES = [
    "Kick", "Snare", "Hi-Hat", "Clap", "Percussion", "Bass One-Shot",
    "Bass Loop", "Synth", "Synth Loop", "Vocal Phrase", "Vocal Loop",
    "Impact", "Riser", "Foley", "FX", "Atmosphere", "Music Loop",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_manifest(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
        raise ValueError("manifest must be a JSON list of objects")
    return payload


def _assignable_family_slots(
    queue: list[dict[str, str]],
    class_families: dict[str, set[str]],
) -> tuple[dict[str, int], dict[str, list[dict[str, str]]]]:
    """Maximum one-label-per-row matching into missing class/family slots.

    This is a small integral max-flow network.  Class capacity is the number
    of missing families, each class/family slot has capacity one, and each
    queue row can be assigned to at most one class.  A greedy class-first
    matcher is incorrect when (for example) Bass One-Shot and Bass Loop share
    the same candidate rows.
    """
    class_nodes: dict[str, int] = {}
    slot_nodes: dict[tuple[str, str], int] = {}
    row_nodes: dict[int, int] = {}
    edges: list[list[list[int]]] = []

    def new_node() -> int:
        edges.append([])
        return len(edges) - 1

    source = new_node()
    sink = new_node()

    def add_edge(left: int, right: int, capacity: int) -> int:
        forward = [right, capacity, len(edges[right])]
        reverse = [left, 0, len(edges[left])]
        edges[left].append(forward); edges[right].append(reverse)
        return len(edges[left]) - 1

    candidate_families: dict[str, list[str]] = {}
    for label in EXPECTED_CLASSES:
        needed = max(0, 5 - len(class_families[label]))
        families = sorted({row.get("sample_family_id", "").strip() for row in queue
                           if row.get("sample_family_id", "").strip()
                           and label in {x.strip() for x in row.get("candidate_parent_options", "").split("|")}
                           and row.get("sample_family_id", "").strip() not in class_families[label]})
        candidate_families[label] = families
        if needed:
            class_nodes[label] = new_node()
            add_edge(source, class_nodes[label], needed)

    for label, families in candidate_families.items():
        if label not in class_nodes:
            continue
        for family in families:
            slot_nodes[(label, family)] = new_node()
            add_edge(class_nodes[label], slot_nodes[(label, family)], 1)

    for row_index, row in enumerate(queue):
        row_nodes[row_index] = new_node()
        add_edge(row_nodes[row_index], sink, 1)
    for (label, family), slot_node in slot_nodes.items():
        for row_index, row in enumerate(queue):
            options = {x.strip() for x in row.get("candidate_parent_options", "").split("|") if x.strip()}
            if label in options and row.get("sample_family_id", "").strip() == family:
                add_edge(slot_node, row_nodes[row_index], 1)

    # Dinic's algorithm; the graph is small and all capacities are integral.
    flow = 0
    while True:
        level = [-1] * len(edges); level[source] = 0; queue_nodes = [source]
        for node in queue_nodes:
            for to, capacity, _ in edges[node]:
                if capacity > 0 and level[to] < 0:
                    level[to] = level[node] + 1; queue_nodes.append(to)
        if level[sink] < 0:
            break
        iters = [0] * len(edges)

        def send(node: int, amount: int) -> int:
            if node == sink:
                return amount
            while iters[node] < len(edges[node]):
                edge = edges[node][iters[node]]
                to, capacity, reverse_index = edge
                if capacity > 0 and level[to] == level[node] + 1:
                    pushed = send(to, min(amount, capacity))
                    if pushed:
                        edge[1] -= pushed; edges[to][reverse_index][1] += pushed
                        return pushed
                iters[node] += 1
            return 0

        while True:
            pushed = send(source, 1 << 30)
            if not pushed:
                break
            flow += pushed

    counts: Counter[str] = Counter()
    examples: dict[str, list[dict[str, str]]] = defaultdict(list)
    for (label, family), slot_node in slot_nodes.items():
        for to, capacity, reverse_index in edges[slot_node]:
            if to not in row_nodes.values() or capacity != 0:
                continue
            # A used slot->row edge has positive reverse capacity.
            row_index = next((index for index, node in row_nodes.items() if node == to), None)
            if row_index is None or edges[to][reverse_index][1] <= 0:
                continue
            counts[label] += 1
            if len(examples[label]) < 10:
                examples[label].append({"queue_id": queue[row_index].get("id", ""), "source_family": family})
    return dict(counts), dict(examples)


def build_plan(manifest_path: Path, queue_path: Path) -> dict[str, Any]:
    manifest = _load_manifest(manifest_path)
    with queue_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {"id", "candidate_parent_options", "collection", "sample_family_id",
                    "owner_label", "decision_status"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError("taxonomy-gap queue is missing required fields")
        queue = list(reader)

    known = [row for row in manifest
             if row.get("expected_subcategory") != "OOD" and row.get("ood") is not True]
    ood = [row for row in manifest
           if row.get("expected_subcategory") == "OOD" or row.get("ood") is True]
    class_families: dict[str, set[str]] = defaultdict(set)
    class_rows: Counter[str] = Counter()
    for row in known:
        label = str(row.get("expected_subcategory", ""))
        class_rows[label] += 1
        family = str(row.get("source_family", ""))
        if family:
            class_families[label].add(family)

    candidate_rows: dict[str, list[dict[str, str]]] = defaultdict(list)
    candidate_families: dict[str, set[str]] = defaultdict(set)
    completed_owner_rows = 0
    pending_owner_rows = 0
    for row in queue:
        owner_label = row.get("owner_label", "").strip()
        status = row.get("decision_status", "").strip().lower()
        completed = bool(owner_label) and status in {"approved", "adjudicated", "complete"}
        if completed:
            normalized = "OOD" if owner_label.upper() in {"OOD", "UNKNOWN"} else owner_label
            if normalized not in set(EXPECTED_CLASSES) | {"OOD"}:
                raise ValueError(f"queue row {row.get('id', '')} has unsupported owner_label: {owner_label!r}")
            completed_owner_rows += 1
            if normalized != "OOD":
                class_rows[normalized] += 1
                family = row.get("sample_family_id", "").strip()
                if family:
                    class_families[normalized].add(family)
            continue
        if owner_label or status not in {"", "pending"}:
            raise ValueError(f"queue row {row.get('id', '')} has an incomplete owner decision")
        pending_owner_rows += 1
        options = {option.strip() for option in row.get("candidate_parent_options", "").split("|") if option.strip()}
        for label in options & set(EXPECTED_CLASSES):
            candidate_rows[label].append(row)
            family = row.get("sample_family_id", "").strip()
            if family:
                candidate_families[label].add(family)

    assignable_slots, assignment_examples = _assignable_family_slots(queue, class_families)

    classes: dict[str, dict[str, Any]] = {}
    for label in EXPECTED_CLASSES:
        existing = class_families[label]
        possible = candidate_families[label]
        new_families = sorted(possible - existing)
        classes[label] = {
            "known_rows": class_rows[label],
            "existing_source_families": len(existing),
            "candidate_rows_offering_class": len(candidate_rows[label]),
            "candidate_source_families": len(possible),
            "new_source_families_available": len(new_families),
            "new_source_family_examples": new_families[:10],
            "source_families_needed_for_gate": max(0, 5 - len(existing)),
            "max_assignable_new_families": assignable_slots.get(label, 0),
            "gate_feasible_under_owner_assignment": (
                assignable_slots.get(label, 0) >= max(0, 5 - len(existing))
            ),
            "assignment_examples": assignment_examples.get(label, []),
            "candidate_ids": [row.get("id", "") for row in candidate_rows[label][:20]],
        }

    return {
        "record_type": "slo_taxonomy_gap_coverage_plan",
        "schema_version": "1.0.0",
        "manifest": str(manifest_path.resolve()),
        "manifest_sha256": sha256_file(manifest_path),
        "queue": str(queue_path.resolve()),
        "queue_sha256": sha256_file(queue_path),
        "manifest_rows": len(manifest),
        "queue_rows": len(queue),
        "completed_owner_rows": completed_owner_rows,
        "pending_owner_rows": pending_owner_rows,
        "known_rows": len(known),
        "ood_rows": len(ood),
        "known_vendor_count": len({str(row.get("vendor_id", "")) for row in known if row.get("vendor_id")}),
        "ood_vendor_count": len({str(row.get("vendor_id", "")) for row in ood if row.get("vendor_id")}),
        "joint_family_gate_feasible_under_owner_assignment": all(
            row["gate_feasible_under_owner_assignment"] for row in classes.values()
        ),
        "classes": classes,
        "policy": {
            "candidate_options_are_not_labels": True,
            "labels_created": False,
            "source_audio_modified": False,
            "production_policy_changed": False,
            "review_required": True,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    result = build_plan(args.manifest, args.queue)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(args.out), "manifest_rows": result["manifest_rows"],
                      "known_rows": result["known_rows"], "ood_rows": result["ood_rows"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
