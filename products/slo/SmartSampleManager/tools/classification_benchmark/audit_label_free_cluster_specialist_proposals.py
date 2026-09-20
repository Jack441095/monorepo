#!/usr/bin/env python3
"""Audit clusters to prioritize specialist/routing improvements.

This is a label-free diagnostic: it measures domain and specialist agreement
inside each unsupervised cluster and emits review priorities, never semantic
names or training labels.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


VERSION = "audit_label_free_cluster_specialist_proposals_v1"


def _safe(path: Path, record_type: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("record_type") != record_type:
        raise ValueError(f"expected {record_type}")
    safety = payload.get("safety") or {}
    if (not safety.get("read_only") or safety.get("semantic_labels_created")
            or safety.get("rename_actions") or safety.get("source_audio_modified")):
        raise ValueError("input is not read-only")
    return payload


def _entropy(counter: Counter[str]) -> float | None:
    total = sum(counter.values())
    if not total:
        return None
    return -sum((count / total) * math.log(count / total)
                for count in counter.values() if count)


def audit(clusters: Path, packet: Path, out: Path, limit: int = 100) -> dict[str, Any]:
    cluster_payload = _safe(clusters, "slo_label_free_cluster_manifest")
    packet_payload = _safe(packet, "slo_label_free_evidence_packet")
    cluster_rows = cluster_payload.get("rows")
    packet_rows = packet_payload.get("rows")
    if not isinstance(cluster_rows, list) or not isinstance(packet_rows, list):
        raise ValueError("inputs must contain rows")
    packet_map = {row["path"]: row for row in packet_rows
                  if isinstance(row, dict) and isinstance(row.get("path"), str)}
    groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in cluster_rows:
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            raise ValueError("invalid cluster row")
        if row.get("semantic_label") is not None:
            raise ValueError("cluster row contains semantic label")
        groups[int(row.get("cluster_id", -1))].append(row)

    proposals: list[dict[str, Any]] = []
    for cluster_id, rows in groups.items():
        evidence = [packet_map[row["path"]] for row in rows if row["path"] in packet_map]
        domains = Counter(str((row.get("domain_route") or {}).get("domain_suggestion")
                              or "unknown_or_mixture") for row in evidence)
        specialists = Counter(str((row.get("specialist") or {}).get("specialist_suggestion")
                                  or "unavailable") for row in evidence)
        decisions = Counter(str((row.get("fused_decision") or {}).get("decision")
                                or "unavailable") for row in evidence)
        size = len(rows)
        dominant_domain, dominant_domain_count = domains.most_common(1)[0] if domains else (None, 0)
        specialist_values = sum(value for key, value in specialists.items() if key != "unavailable")
        unknown_count = sum(value for key, value in domains.items()
                            if key in {"unknown_or_mixture", "environment_sfx",
                                       "animal_bioacoustic", "mechanical_industrial"})
        domain_purity = dominant_domain_count / len(evidence) if evidence else 0.0
        unknown_fraction = unknown_count / len(evidence) if evidence else 0.0
        is_noise = cluster_id < 0
        if is_noise:
            proposal = "noise_review"
        elif unknown_fraction >= 0.4 or dominant_domain == "unknown_or_mixture":
            proposal = "new_specialist_or_ontology_review"
        elif domain_purity < 0.6:
            proposal = "improve_domain_router"
        elif specialist_values == 0:
            proposal = "specialist_missing_or_abstaining"
        else:
            proposal = "existing_specialist_cluster"
        priority = (0.45 if is_noise else min(0.45, size / 250.0))
        priority += 0.35 * unknown_fraction
        priority += 0.20 * (1.0 - domain_purity)
        proposals.append({
            "cluster_id": cluster_id,
            "cluster_size": size,
            "proposal": proposal,
            "review_priority": round(priority, 6),
            "dominant_domain": dominant_domain,
            "domain_purity": round(domain_purity, 6),
            "domain_entropy": round(_entropy(domains), 6) if domains else None,
            "specialist_label_entropy": round(_entropy(specialists), 6) if specialists else None,
            "unknown_route_fraction": round(unknown_fraction, 6),
            "domain_counts": dict(sorted(domains.items())),
            "specialist_counts": dict(sorted(specialists.items())),
            "fused_decision_counts": dict(sorted(decisions.items())),
            "packet_coverage": len(evidence),
            "semantic_label": None,
        })
    proposals.sort(key=lambda row: (-row["review_priority"], -row["cluster_size"], row["cluster_id"]))
    if limit >= 0:
        proposals = proposals[:limit]
    result = {
        "record_type": "slo_label_free_cluster_specialist_proposal_audit",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "source_cluster_manifest": str(clusters.resolve()),
        "source_packet": str(packet.resolve()),
        "n_source_clusters": len(groups),
        "n_queued_proposals": len(proposals),
        "proposals": proposals,
        "safety": {
            "read_only": True,
            "ground_truth_read": False,
            "semantic_labels_created": False,
            "training_data_created": False,
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
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    result = audit(args.clusters, args.packet, args.out, args.limit)
    print(json.dumps({"out": str(args.out), "n_queued_proposals": result["n_queued_proposals"],
                      "read_only": True}, indent=2))


if __name__ == "__main__":
    main()
