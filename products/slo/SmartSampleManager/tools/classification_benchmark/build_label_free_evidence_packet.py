#!/usr/bin/env python3
"""Join label-free receipts into a reviewable, provenance-preserving packet.

The packet is the hand-off boundary between batch inference and a product
review UI.  It joins model agreement, optional domain routing, physical
definition cards and optional time-localized segment candidates by logical
path.  It never creates semantic labels, writes metadata, or performs file
actions.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


VERSION = "label_free_evidence_packet_v1"


def _safe_header(header: dict[str, Any], expected: set[str], name: str) -> None:
    if header.get("record_type") not in expected:
        raise ValueError(f"{name} has an unexpected record type")
    safety = header.get("safety") or {}
    if not safety.get("read_only"):
        raise ValueError(f"{name} is not read-only")
    if safety.get("semantic_labels_created") or safety.get("rename_actions"):
        raise ValueError(f"{name} contains mutation or semantic-label state")


def _load_jsonl(path: Path, expected: set[str], name: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        raise ValueError(f"{name} is empty")
    header = json.loads(lines[0])
    if not isinstance(header, dict):
        raise ValueError(f"{name} header is invalid")
    _safe_header(header, expected, name)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in lines[1:]:
        row = json.loads(line)
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            raise ValueError(f"{name} row has no path")
        key = row["path"]
        if key in seen:
            raise ValueError(f"duplicate {name} path: {key}")
        if row.get("semantic_label") is not None:
            raise ValueError(f"{name} contains a semantic label")
        seen.add(key)
        rows.append(row)
    return header, rows


def _path_key(path: str) -> str:
    # Do not resolve relative paths against the process cwd: receipts may be
    # produced on another machine.  Absolute paths are normalized only for
    # harmless lexical differences.
    value = str(path)
    return str(Path(value).resolve()) if value.startswith("/") else value


def _load_cards(path: Path | None) -> tuple[dict[str, Any] | None, dict[str, dict[str, Any]]]:
    if path is None:
        return None, {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("physical cards payload is invalid")
    _safe_header(payload, {
        "slo_label_free_physical_cards",
        "slo_audio_definition_cards",
        "slo_label_queue_audio_definition_cards",
    }, "physical cards")
    cards: dict[str, dict[str, Any]] = {}
    for card in payload.get("cards", []):
        if not isinstance(card, dict) or not isinstance(card.get("path"), str):
            raise ValueError("physical card has no path")
        key = _path_key(card["path"])
        if key in cards:
            raise ValueError(f"duplicate physical card path: {card['path']}")
        cards[key] = card
    return payload, cards


def _row_map(rows: list[dict[str, Any]], name: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = _path_key(str(row["path"]))
        if key in result:
            raise ValueError(f"duplicate {name} path after normalization: {row['path']}")
        result[key] = row
    return result


def _load_name_candidates(path: Path | None) -> tuple[dict[str, Any] | None, dict[str, dict[str, Any]]]:
    """Load review-only structured-name candidates keyed by logical path."""
    if path is None:
        return None, {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("record_type") != "slo_label_free_name_candidates":
        raise ValueError("name candidates payload has an unexpected record type")
    safety = payload.get("safety") or {}
    if (not safety.get("read_only") or safety.get("semantic_labels_created")
            or safety.get("semantic_label_created") or safety.get("rename_actions")
            or safety.get("rename_applied") or safety.get("metadata_written")):
        raise ValueError("name candidates payload is not read-only")
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise ValueError("name candidates rows are invalid")
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            raise ValueError("name candidate has no path")
        if row.get("semantic_label") is not None:
            raise ValueError("name candidates contain a semantic label")
        name_state = row.get("name_state")
        if name_state not in {"suggested_review_required", "review_required"}:
            raise ValueError("name candidate has an invalid review state")
        candidate_filename = row.get("candidate_filename")
        if not isinstance(candidate_filename, str) or not candidate_filename.strip():
            raise ValueError("name candidate has no filename")
        key = _path_key(row["path"])
        if key in result:
            raise ValueError(f"duplicate name candidate path: {row['path']}")
        result[key] = row
    return payload, result


def _load_fused_decisions(path: Path | None) -> tuple[dict[str, Any] | None, dict[str, dict[str, Any]]]:
    """Load the optional conservative open-world fusion receipt."""
    if path is None:
        return None, {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("record_type") not in {
            "slo_label_free_fused_decision_receipt",
            "slo_label_free_ood_gated_decision_receipt",
    }:
        raise ValueError("fused decisions payload has an unexpected record type")
    safety = payload.get("safety") or {}
    if (not safety.get("read_only") or safety.get("semantic_labels_created")
            or safety.get("rename_actions") or safety.get("source_audio_modified")
            or safety.get("auto_action_allowed")):
        raise ValueError("fused decisions payload is not read-only")
    result: dict[str, dict[str, Any]] = {}
    for row in payload.get("rows", []):
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            raise ValueError("fused decision has no path")
        if row.get("semantic_label") is not None:
            raise ValueError("fused decisions contain a semantic label")
        key = _path_key(row["path"])
        if key in result:
            raise ValueError(f"duplicate fused decision path: {row['path']}")
        result[key] = row
    return payload, result


def _load_clusters(path: Path | None) -> tuple[dict[str, Any] | None, dict[str, dict[str, Any]]]:
    """Load optional unsupervised discovery assignments."""
    if path is None:
        return None, {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("record_type") != "slo_label_free_cluster_manifest":
        raise ValueError("cluster manifest has an unexpected record type")
    safety = payload.get("safety") or {}
    if (not safety.get("read_only") or safety.get("semantic_labels_created")
            or safety.get("rename_actions") or safety.get("source_audio_modified")):
        raise ValueError("cluster manifest is not read-only")
    result: dict[str, dict[str, Any]] = {}
    for row in payload.get("rows", []):
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            raise ValueError("cluster row has no path")
        if row.get("semantic_label") is not None:
            raise ValueError("cluster manifest contains a semantic label")
        key = _path_key(row["path"])
        if key in result:
            raise ValueError(f"duplicate cluster path: {row['path']}")
        result[key] = row
    return payload, result


def _load_retrieval(path: Path | None) -> tuple[dict[str, Any] | None, dict[str, dict[str, Any]]]:
    """Load optional supervised-reference retrieval evidence."""
    if path is None:
        return None, {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("record_type") != "slo_label_free_retrieval_evidence":
        raise ValueError("retrieval evidence has an unexpected record type")
    safety = payload.get("safety") or {}
    if (not safety.get("read_only") or safety.get("semantic_labels_created")
            or safety.get("rename_actions") or safety.get("source_audio_modified")
            or safety.get("auto_action_allowed")):
        raise ValueError("retrieval evidence is not read-only")
    result: dict[str, dict[str, Any]] = {}
    for row in payload.get("rows", []):
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            raise ValueError("retrieval row has no path")
        if row.get("semantic_label") is not None:
            raise ValueError("retrieval evidence contains a semantic label")
        key = _path_key(row["path"])
        if key in result:
            raise ValueError(f"duplicate retrieval path: {row['path']}")
        result[key] = row
    return payload, result


def _load_fft_evidence(path: Path | None) -> tuple[dict[str, Any] | None, dict[str, dict[str, Any]]]:
    """Load the bounded, read-only native FFT evidence queue."""
    if path is None:
        return None, {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("record_type") != "slo_fft_evidence_review_queue":
        raise ValueError("FFT evidence payload has an unexpected record type")
    safety = payload.get("safety") or {}
    if (not safety.get("read_only") or safety.get("semantic_labels_created")
            or safety.get("rename_actions") or safety.get("source_audio_modified")
            or safety.get("training_data_created")):
        raise ValueError("FFT evidence payload is not read-only")
    result: dict[str, dict[str, Any]] = {}
    for row in payload.get("rows", []):
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            raise ValueError("FFT evidence row has no path")
        if row.get("semantic_label") is not None:
            raise ValueError("FFT evidence contains a semantic label")
        key = _path_key(row["path"])
        if key in result:
            raise ValueError(f"duplicate FFT evidence path: {row['path']}")
        status = row.get("fft_status")
        if status not in {"computed", "unresolved_local_audio", "decode_or_short_audio"}:
            raise ValueError("FFT evidence row has an invalid status")
        result[key] = row
    return payload, result


def build(ensemble: Path, out: Path, cards: Path | None = None,
          segments: Path | None = None, router: Path | None = None,
          specialists: Path | None = None, limit: int | None = None,
          names: Path | None = None,
          fused_decisions: Path | None = None,
          clusters: Path | None = None,
          retrieval: Path | None = None,
          fft_evidence: Path | None = None) -> dict[str, Any]:
    ensemble_header, ensemble_rows = _load_jsonl(
        ensemble, {"slo_label_free_ensemble_receipt"}, "ensemble receipt")
    ensemble_map = _row_map(ensemble_rows, "ensemble")
    cards_header, card_map = _load_cards(cards)

    segment_header: dict[str, Any] | None = None
    segment_map: dict[str, dict[str, Any]] = {}
    if segments is not None:
        segment_header, segment_rows = _load_jsonl(
            segments, {"slo_label_free_segment_classifier_receipt"}, "segment receipt")
        segment_map = _row_map(segment_rows, "segment")

    router_header: dict[str, Any] | None = None
    router_map: dict[str, dict[str, Any]] = {}
    if router is not None:
        router_header, router_rows = _load_jsonl(
            router, {"slo_label_free_domain_router_receipt"}, "domain router receipt")
        router_map = _row_map(router_rows, "domain router")

    specialist_header: dict[str, Any] | None = None
    specialist_map: dict[str, dict[str, Any]] = {}
    if specialists is not None:
        specialist_header, specialist_rows = _load_jsonl(
            specialists, {"slo_label_free_specialist_receipt",
                          "slo_label_free_specialist_ensemble_receipt"}, "specialist receipt")
        specialist_map = _row_map(specialist_rows, "specialist")

    names_header, name_map = _load_name_candidates(names)
    fused_header, fused_map = _load_fused_decisions(fused_decisions)
    clusters_header, cluster_map = _load_clusters(clusters)
    retrieval_header, retrieval_map = _load_retrieval(retrieval)
    fft_header, fft_map = _load_fft_evidence(fft_evidence)

    selected = ensemble_rows if limit is None else ensemble_rows[:max(0, limit)]
    rows: list[dict[str, Any]] = []
    for ensemble_row in selected:
        path = str(ensemble_row["path"])
        key = _path_key(path)
        segment_row = segment_map.get(key)
        router_row = router_map.get(key)
        specialist_row = specialist_map.get(key)
        name_row = name_map.get(key)
        fused_row = fused_map.get(key)
        cluster_row = cluster_map.get(key)
        retrieval_row = retrieval_map.get(key)
        fft_row = fft_map.get(key)
        card = card_map.get(key)
        output_row = {
            "path": path,
            "semantic_label": None,
            "review_state": "suggestion_review_required" if ensemble_row.get("status") == "suggest" else "review_required",
            "ensemble": ensemble_row,
            "domain_route": router_row,
            "specialist": specialist_row,
            "name_candidate": name_row,
            "fused_decision": fused_row,
            "cluster_discovery": cluster_row,
            "retrieval": retrieval_row,
            "fft_evidence": None,
            "physical": card,
            "segments": segment_row,
            "coverage": {
                "ensemble": True,
                "domain_route": router_row is not None,
                "specialist": specialist_row is not None,
                "name_candidate": name_row is not None,
                "physical": card is not None,
                "segments": segment_row is not None,
                "fused_decision": fused_row is not None,
                "cluster_discovery": cluster_row is not None,
                "retrieval": retrieval_row is not None,
                "fft_evidence": fft_row is not None,
            },
            "safety": {
                "read_only": True,
                "semantic_label_created": False,
                "metadata_written": False,
                "rename_applied": False,
                "human_approval_required": True,
            },
        }
        if fused_decisions is None:
            output_row["coverage"].pop("fused_decision", None)
            output_row.pop("fused_decision", None)
        if clusters is None:
            output_row["coverage"].pop("cluster_discovery", None)
            output_row.pop("cluster_discovery", None)
        if retrieval is None:
            output_row["coverage"].pop("retrieval", None)
            output_row.pop("retrieval", None)
        if fft_row is not None:
            output_row["fft_evidence"] = {
                "semantic_label": None,
                "status": fft_row.get("fft_status"),
                "values": fft_row.get("fft_evidence"),
                "candidate_lanes": fft_row.get("fft_candidate_lanes", []),
            }
        else:
            output_row.pop("fft_evidence", None)
        if fft_evidence is None:
            output_row["coverage"].pop("fft_evidence", None)
        rows.append(output_row)
    rows.sort(key=lambda row: row["path"])
    payload = {
        "record_type": "slo_label_free_evidence_packet",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "source_receipt": str(ensemble.resolve()),
        "source_method_versions": {
            "ensemble": ensemble_header.get("method_version"),
            "physical": cards_header.get("method_version") if cards_header else None,
            "segments": segment_header.get("method_version") if segment_header else None,
            "domain_router": router_header.get("method_version") if router_header else None,
            "specialist": specialist_header.get("method_version") if specialist_header else None,
            "name_candidates": names_header.get("method_version") if names_header else None,
            "fused_decision": fused_header.get("method_version") if fused_header else None,
            "cluster_discovery": clusters_header.get("method_version") if clusters_header else None,
            "retrieval": retrieval_header.get("method_version") if retrieval_header else None,
            "fft_evidence": fft_header.get("method_version") if fft_header else None,
        },
        "n_rows": len(rows),
        "coverage": {
            "ensemble": len(rows),
            "domain_route": sum(row["coverage"]["domain_route"] for row in rows),
            "specialist": sum(row["coverage"]["specialist"] for row in rows),
            "name_candidate": sum(row["coverage"]["name_candidate"] for row in rows),
            "physical": sum(row["coverage"]["physical"] for row in rows),
            "segments": sum(row["coverage"]["segments"] for row in rows),
        },
        "rows": rows,
        "safety": {
            "read_only": True,
            "semantic_labels_created": False,
            "ground_truth_read": False,
            "training_data_created": False,
            "rename_actions": False,
            "source_audio_modified": False,
            "human_approval_required": True,
        },
    }
    if fused_decisions is not None:
        payload["coverage"]["fused_decision"] = sum(
            row["coverage"].get("fused_decision", False) for row in rows)
    if clusters is not None:
        payload["coverage"]["cluster_discovery"] = sum(
            row["coverage"].get("cluster_discovery", False) for row in rows)
    if retrieval is not None:
        payload["coverage"]["retrieval"] = sum(
            row["coverage"].get("retrieval", False) for row in rows)
    if fft_evidence is not None:
        payload["coverage"]["fft_evidence"] = sum(
            row["coverage"].get("fft_evidence", False) for row in rows)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ensemble", type=Path, required=True)
    parser.add_argument("--cards", type=Path)
    parser.add_argument("--segments", type=Path)
    parser.add_argument("--router", type=Path)
    parser.add_argument("--specialists", type=Path)
    parser.add_argument("--names", type=Path,
                        help="optional review-only structured-name candidates JSON")
    parser.add_argument("--fused-decision", type=Path,
                        help="optional conservative open-world fusion receipt JSON")
    parser.add_argument("--clusters", type=Path,
                        help="optional unsupervised embedding cluster manifest JSON")
    parser.add_argument("--retrieval", type=Path,
                        help="optional supervised-reference retrieval evidence JSON")
    parser.add_argument("--fft-evidence", type=Path,
                        help="optional read-only native FFT evidence queue JSON")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    result = build(args.ensemble, args.out, args.cards, args.segments, args.router,
                   args.specialists, args.limit, args.names, args.fused_decision, args.clusters,
                   args.retrieval, args.fft_evidence)
    print(json.dumps({"out": str(args.out), "n_rows": result["n_rows"],
                      "coverage": result["coverage"], "read_only": True}, indent=2))


if __name__ == "__main__":
    main()
