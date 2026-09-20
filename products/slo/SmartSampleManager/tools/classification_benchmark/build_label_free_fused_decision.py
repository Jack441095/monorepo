#!/usr/bin/env python3
"""Fuse domain, ensemble and specialist evidence into a conservative decision.

This is the open-world action boundary: a file receives a candidate label only
when the routed domain is supported, the two base CLAP views agree, the
specialist agrees with that label, and every required gate passes.  Otherwise
the row is explicitly abstained for review.  It never creates semantic labels
or performs file actions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


VERSION = "label_free_fused_decision_v1"


def _load(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("record_type") != "slo_label_free_evidence_packet":
        raise ValueError("input is not a label-free evidence packet")
    safety = payload.get("safety") or {}
    if (not safety.get("read_only") or safety.get("semantic_labels_created")
            or safety.get("rename_actions") or safety.get("source_audio_modified")):
        raise ValueError("evidence packet is not read-only")
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise ValueError("evidence packet rows are invalid")
    if any(row.get("semantic_label") is not None for row in rows if isinstance(row, dict)):
        raise ValueError("evidence packet contains semantic labels")
    return payload, [row for row in rows if isinstance(row, dict) and isinstance(row.get("path"), str)]


def _obj(row: dict[str, Any], name: str) -> dict[str, Any]:
    value = row.get(name)
    return value if isinstance(value, dict) else {}


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _decision(row: dict[str, Any], min_margin: float,
              require_specialist: bool) -> dict[str, Any]:
    route = _obj(row, "domain_route")
    ensemble = _obj(row, "ensemble")
    specialist = _obj(row, "specialist")
    domain = str(route.get("domain_suggestion") or specialist.get("domain_suggestion") or "unknown_or_mixture")
    candidate = ensemble.get("ensemble_suggestion")
    reasons: list[str] = []
    if not route:
        reasons.append("missing_domain_route")
    elif domain != "music_sample":
        reasons.append("non_music_or_unknown_domain")
    if not ensemble:
        reasons.append("missing_ensemble")
    elif ensemble.get("status") != "suggest":
        reasons.append("ensemble_abstained")
    if ensemble and ensemble.get("model_agreement") is not True:
        reasons.append("base_models_disagree")
    if not candidate:
        reasons.append("ensemble_has_no_candidate")
    if require_specialist:
        if not specialist:
            reasons.append("missing_specialist")
        else:
            if specialist.get("status") != "suggest" or specialist.get("specialist_status") != "scored":
                reasons.append("specialist_abstained")
            if specialist.get("specialist_suggestion") != candidate:
                reasons.append("specialist_disagrees")
    margins = [value for value in (_number(ensemble.get("margin_mean")),
                                   _number(specialist.get("margin")),
                                   _number(route.get("domain_margin")))
               if value is not None]
    min_observed_margin = min(margins) if margins else None
    if min_observed_margin is None or min_observed_margin < min_margin:
        reasons.append("margin_below_fusion_gate")
    scores = [value for value in (_number(ensemble.get("score_mean")),
                                  _number(specialist.get("specialist_score")),
                                  _number(route.get("domain_score")))
              if value is not None]
    confidence = min(scores) if scores else None
    accepted = not reasons
    domain_candidate = None
    if (domain != "music_sample" and specialist.get("specialist_status") == "scored"
            and specialist.get("status") == "suggest"
            and specialist.get("specialist_suggestion")):
        # Preserve useful open-world information without pretending that a
        # single specialist is a calibrated semantic truth.  This candidate
        # is always review-only and is deliberately separate from the music
        # taxonomy candidate below.
        domain_candidate = str(specialist["specialist_suggestion"])
    return {
        "path": row["path"],
        "semantic_label": None,
        "decision": "suggest" if accepted else ("unknown_domain" if domain != "music_sample" else "review"),
        "candidate_label": str(candidate) if accepted else None,
        "candidate_scope": "music_taxonomy" if accepted else (
            "open_world_domain" if domain_candidate else "none"),
        "domain_candidate_label": domain_candidate,
        "domain": domain,
        "confidence_floor": confidence,
        "min_observed_margin": min_observed_margin,
        "reasons": ["all_fusion_gates_passed"] if accepted else sorted(set(reasons)),
        "source_status": {
            "route": route.get("status"),
            "ensemble": ensemble.get("status"),
            "specialist": specialist.get("status"),
        },
        "model_agreement": ensemble.get("model_agreement"),
        "specialist_agreement": specialist.get("specialist_suggestion") == candidate if specialist else False,
    }


def build(packet: Path, out: Path, min_margin: float = 0.03,
          require_specialist: bool = True) -> dict[str, Any]:
    if min_margin < 0.0:
        raise ValueError("min_margin must be non-negative")
    header, rows = _load(packet)
    decisions = [_decision(row, min_margin, require_specialist) for row in rows]
    decisions.sort(key=lambda row: row["path"])
    payload = {
        "record_type": "slo_label_free_fused_decision_receipt",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "source_packet": str(packet.resolve()),
        "source_packet_sha256": hashlib.sha256(packet.read_bytes()).hexdigest(),
        "source_method_version": header.get("method_version"),
        "n_files": len(decisions),
        "n_suggest": sum(row["decision"] == "suggest" for row in decisions),
        "n_review": sum(row["decision"] == "review" for row in decisions),
        "n_unknown_domain": sum(row["decision"] == "unknown_domain" for row in decisions),
        "min_margin": min_margin,
        "require_specialist_agreement": require_specialist,
        "rows": decisions,
        "safety": {
            "read_only": True,
            "ground_truth_read": False,
            "semantic_labels_created": False,
            "rename_actions": False,
            "source_audio_modified": False,
            "auto_action_allowed": False,
            "human_approval_required": True,
        },
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--min-margin", type=float, default=0.03)
    parser.add_argument("--no-specialist", action="store_true",
                        help="research-only ablation; allow decisions without specialist agreement")
    args = parser.parse_args()
    result = build(args.packet, args.out, args.min_margin, not args.no_specialist)
    print(json.dumps({"out": str(args.out), "n_files": result["n_files"],
                      "n_suggest": result["n_suggest"], "n_review": result["n_review"],
                      "read_only": True}, indent=2))


if __name__ == "__main__":
    main()
