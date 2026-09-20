#!/usr/bin/env python3
"""Create conservative prompt-bank proposals from cluster evidence.

Filename tokens are weak hints only.  The output is a review artifact for
designing specialist prompts; it never promotes a token to a semantic label or
training target.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


VERSION = "label_free_specialist_prompt_proposals_v1"
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z-]{3,}")
STOPWORDS = {
    "audio", "sample", "samples", "sound", "sounds", "loop", "loops", "one", "shot",
    "stereo", "mono", "bpm", "min", "max", "edit", "edited", "version", "vol", "volume",
    "pack", "kit", "official", "music", "recording", "wav", "flac", "final", "clean",
    "processed", "dry", "wet", "mix", "mixed", "master", "stereo", "left", "right",
    "kshmr", "cpa", "tcp", "bendji", "allonce", "diamaudix",
    "with", "that", "this", "from", "into", "high", "low", "open", "short", "tight",
    "lead", "heavy", "major", "minor", "like", "give", "reason", "remember", "nothing",
    "declare", "wanker", "sucha", "game", "skip", "dialogue", "crossnaders", "pound",
}


def _safe(path: Path, record_type: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("record_type") != record_type:
        raise ValueError(f"expected {record_type}")
    safety = payload.get("safety") or {}
    if (not safety.get("read_only") or safety.get("semantic_labels_created")
            or safety.get("rename_actions") or safety.get("source_audio_modified")):
        raise ValueError("input is not read-only")
    return payload


def _tokens(paths: list[str]) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    for path in paths:
        # Use only basenames: parent directories often contain vendor/pack
        # names that would create spurious specialist concepts.
        basename = Path(path).stem.lower()
        for token in TOKEN_RE.findall(basename):
            token = token.strip("-")
            if token and token not in STOPWORDS and not token.isdigit():
                counts[token] += 1
    descriptors = []
    for token, count in ((token, count) for token, count in counts.most_common() if count >= 2):
        if len(descriptors) >= 8:
            break
        descriptors.append({
            "descriptor": token,
            "evidence_count": count,
            "prompt_templates": [
                f"an audio sample described as {token}",
                f"a sound containing a {token} texture",
                f"a recording with {token} characteristics",
            ],
            "semantic_label": None,
        })
    return descriptors


def build(audit: Path, out: Path, limit: int = 100,
          clusters: Path | None = None) -> dict[str, Any]:
    source = _safe(audit, "slo_label_free_cluster_specialist_proposal_audit")
    proposals = source.get("proposals")
    if not isinstance(proposals, list):
        raise ValueError("proposal audit has no proposals")
    representative_map: dict[int, list[str]] = {}
    if clusters is not None:
        cluster_source = _safe(clusters, "slo_label_free_cluster_manifest")
        for summary in cluster_source.get("cluster_summaries", []):
            if isinstance(summary, dict) and isinstance(summary.get("cluster_id"), int):
                representative_map[summary["cluster_id"]] = [str(path) for path in
                                                               (summary.get("representative_paths") or [])]
    rows: list[dict[str, Any]] = []
    for proposal in proposals:
        if not isinstance(proposal, dict):
            continue
        cluster_id = int(proposal.get("cluster_id", -1))
        representatives = proposal.get("representative_paths") or representative_map.get(cluster_id, [])
        # Older audits may not carry representatives; retain the row but make
        # its lack of lexical evidence explicit.
        descriptors = _tokens([str(path) for path in representatives])
        rows.append({
            "cluster_id": cluster_id,
            "cluster_size": proposal.get("cluster_size"),
            "proposal": proposal.get("proposal"),
            "review_priority": proposal.get("review_priority"),
            "dominant_domain": proposal.get("dominant_domain"),
            "representative_paths": representatives,
            "candidate_descriptors": descriptors,
            "existing_specialist_labels_are_reference_only": True,
            "semantic_label": None,
        })
    rows.sort(key=lambda row: (-float(row.get("review_priority") or 0.0),
                               -(int(row.get("cluster_size") or 0)),
                               int(row.get("cluster_id") or -1)))
    if limit >= 0:
        rows = rows[:limit]
    result = {
        "record_type": "slo_label_free_specialist_prompt_proposals",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "source_audit": str(audit.resolve()),
        "source_cluster_manifest": str(clusters.resolve()) if clusters else None,
        "n_source_proposals": len(proposals),
        "n_rows": len(rows),
        "rows": rows,
        "safety": {
            "read_only": True,
            "ground_truth_read": False,
            "semantic_labels_created": False,
            "training_data_created": False,
            "rename_actions": False,
            "source_audio_modified": False,
            "human_approval_required": True,
            "candidate_names_created": False,
            "prompt_bank_promoted": False,
        },
        "limitations": [
            "basename tokens are weak lexical hints and may be pack/vendor jargon",
            "descriptors require owner review and audio verification before use",
            "no descriptor is a semantic label or training target",
        ],
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--clusters", type=Path,
                        help="optional cluster manifest providing representative paths")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    result = build(args.audit, args.out, args.limit, args.clusters)
    print(json.dumps({"out": str(args.out), "n_rows": result["n_rows"],
                      "read_only": True}, indent=2))


if __name__ == "__main__":
    main()
