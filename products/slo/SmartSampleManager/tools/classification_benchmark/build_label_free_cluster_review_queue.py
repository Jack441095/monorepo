#!/usr/bin/env python3
"""Rank unsupervised clusters for specialist/taxonomy review.

This turns embedding clusters into a bounded review queue.  It intentionally
preserves cluster IDs and representative paths instead of inventing names or
semantic labels.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


VERSION = "label_free_cluster_review_queue_v1"


def _safe_payload(path: Path, record_type: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("record_type") != record_type:
        raise ValueError(f"expected {record_type}")
    safety = payload.get("safety") or {}
    if (not safety.get("read_only") or safety.get("semantic_labels_created")
            or safety.get("rename_actions") or safety.get("source_audio_modified")):
        raise ValueError("input is not read-only")
    return payload


def _packet_map(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    payload = _safe_payload(path, "slo_label_free_evidence_packet")
    result: dict[str, dict[str, Any]] = {}
    for row in payload.get("rows", []):
        if isinstance(row, dict) and isinstance(row.get("path"), str):
            result[row["path"]] = row
    return result


def build(cluster_manifest: Path, out: Path, packet: Path | None = None,
          limit: int = 100) -> dict[str, Any]:
    source = _safe_payload(cluster_manifest, "slo_label_free_cluster_manifest")
    rows = source.get("rows")
    if not isinstance(rows, list):
        raise ValueError("cluster manifest rows are invalid")
    packet_rows = _packet_map(packet)
    members: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            raise ValueError("cluster row is invalid")
        if row.get("semantic_label") is not None:
            raise ValueError("cluster rows contain semantic labels")
        members[int(row.get("cluster_id", -1))].append(row)

    queue: list[dict[str, Any]] = []
    for cluster_id, cluster_rows in members.items():
        evidence = [packet_rows[row["path"]] for row in cluster_rows if row["path"] in packet_rows]
        domain_counts = Counter(
            ((item.get("domain_route") or {}).get("domain_suggestion") or "unknown_or_mixture")
            for item in evidence
        )
        decision_counts = Counter(
            ((item.get("fused_decision") or {}).get("decision") or "unavailable")
            for item in evidence
        )
        size = len(cluster_rows)
        is_noise = cluster_id < 0
        # Large clusters affect many files; noise and clusters dominated by
        # unknown/review routes are more likely to reveal missing specialists.
        unknown_fraction = (sum(value for key, value in domain_counts.items()
                                 if key in {"unknown_or_mixture", "environment_sfx",
                                            "animal_bioacoustic", "mechanical_industrial"})
                            / len(evidence)) if evidence else 0.0
        priority = (1.0 if is_noise else min(1.0, size / 100.0)) * 0.55
        priority += unknown_fraction * 0.35
        priority += 0.10 if not evidence else 0.0
        representative = sorted(cluster_rows,
                                 key=lambda row: (row.get("distance_to_cluster_centroid") is None,
                                                   row.get("distance_to_cluster_centroid") or 0.0))[:8]
        queue.append({
            "cluster_id": cluster_id,
            "discovery_status": "noise_review" if is_noise else "cluster_hypothesis",
            "cluster_size": size,
            "review_priority": round(priority, 6),
            "representative_paths": [row["path"] for row in representative],
            "domain_counts": dict(sorted(domain_counts.items())),
            "fused_decision_counts": dict(sorted(decision_counts.items())),
            "packet_coverage": len(evidence),
            "semantic_label": None,
        })
    queue.sort(key=lambda row: (-row["review_priority"], -row["cluster_size"], row["cluster_id"]))
    if limit >= 0:
        queue = queue[:limit]
    result = {
        "record_type": "slo_label_free_cluster_review_queue",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "source_cluster_manifest": str(cluster_manifest.resolve()),
        "source_packet": str(packet.resolve()) if packet else None,
        "n_source_rows": len(rows),
        "n_source_clusters": len(members),
        "n_queued_clusters": len(queue),
        "rows": queue,
        "safety": {
            "read_only": True,
            "ground_truth_read": False,
            "semantic_labels_created": False,
            "rename_actions": False,
            "source_audio_modified": False,
            "human_approval_required": True,
            "cluster_names_created": False,
        },
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clusters", type=Path, required=True)
    parser.add_argument("--packet", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    result = build(args.clusters, args.out, args.packet, args.limit)
    print(json.dumps({"out": str(args.out), "n_queued_clusters": result["n_queued_clusters"],
                      "read_only": True}, indent=2))


if __name__ == "__main__":
    main()
