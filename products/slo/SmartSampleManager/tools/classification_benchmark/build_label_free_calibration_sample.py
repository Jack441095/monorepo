#!/usr/bin/env python3
"""Build a deterministic, stratified calibration manifest from AI evidence.

The output is a *sampling plan*, not a label set.  It deliberately mixes model
disagreements, boundary/abstention cases, non-music routes and a random audit
slice so a later owner-approved ear review can estimate selective precision and
OOD false-known rate without tuning on the same files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


VERSION = "label_free_calibration_sample_v2"
SD = Path(__file__).resolve().parent


def _read_packet(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if path.suffix.lower() == ".jsonl":
        lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not lines:
            raise ValueError("evidence receipt is empty")
        header, rows = lines[0], lines[1:]
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("evidence packet must be an object")
        header, rows = payload, payload.get("rows", [])
    if not isinstance(rows, list):
        raise ValueError("evidence packet rows must be a list")
    if not (header.get("safety") or {}).get("read_only", False):
        raise ValueError("source packet is not explicitly read-only")
    if any(row.get("semantic_label") is not None for row in rows):
        raise ValueError("source packet contains semantic labels")
    result = [row for row in rows if isinstance(row, dict) and row.get("path")]
    seen_paths: set[str] = set()
    for row in result:
        path_value = row.get("path")
        if not isinstance(path_value, str) or not Path(path_value).is_absolute():
            raise ValueError("evidence packet row paths must be absolute")
        if path_value in seen_paths:
            raise ValueError(f"evidence packet contains duplicate path: {path_value}")
        seen_paths.add(path_value)
    return header, result


def _read_sealed_holdout(path: Path | None) -> set[str]:
    """Return collection names reserved from calibration/model selection."""
    if path is None or not path.exists():
        return set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    names = payload.get("sealed_vendors", [])
    if not isinstance(names, list) or any(not isinstance(name, str) or not name for name in names):
        raise ValueError("sealed holdout must contain a list of collection names")
    return set(names)


def _nested(row: dict[str, Any], key: str) -> dict[str, Any]:
    value = row.get(key)
    return value if isinstance(value, dict) else {}


def _collection(path: str, marker: str) -> str:
    token = marker.rstrip("/") + "/"
    suffix = path.split(token, 1)[-1] if token in path else path
    return suffix.split("/", 1)[0] or "(root)"


def _stable(path: str, seed: int) -> float:
    digest = hashlib.sha256(f"{seed}:{path}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / float(1 << 64)


def _row_features(row: dict[str, Any], marker: str, seed: int) -> dict[str, Any]:
    ensemble = _nested(row, "ensemble")
    route = _nested(row, "domain_route")
    specialist = _nested(row, "specialist")
    model_disagreement = ensemble.get("model_agreement") is False
    specialist_disagreement = (
        ensemble.get("ensemble_suggestion") is not None
        and specialist.get("specialist_suggestion") is not None
        and ensemble.get("ensemble_suggestion") != specialist.get("specialist_suggestion")
    )
    margins = [float(value) for value in (
        ensemble.get("margin_mean"), route.get("domain_margin"), specialist.get("margin")
    ) if isinstance(value, (int, float)) and math.isfinite(float(value))]
    min_margin = min(margins) if margins else 1.0
    review = any(value == "review" for value in (
        ensemble.get("status"), route.get("status"), specialist.get("status")
    )) or row.get("review_state") == "review_required"
    domain = str(route.get("domain_suggestion") or specialist.get("domain_suggestion") or "unknown_or_mixture")
    disagreement = model_disagreement or specialist_disagreement
    boundary = review or min_margin < 0.08
    ood = domain not in {"music_sample", "unknown_or_mixture"}
    # Reserve a visible OOD/non-music lane even when the same row also has
    # model disagreement; otherwise the disagreement quota would consume every
    # specialist route and leave no explicit open-world calibration slice.
    if ood:
        lane = "non_music_route"
    elif disagreement:
        lane = "model_disagreement"
    elif boundary:
        lane = "boundary_or_abstention"
    else:
        lane = "random_audit"
    uncertainty = (1.0 if disagreement else 0.0) * 0.55
    uncertainty += max(0.0, min(1.0, (0.12 - min_margin) / 0.12)) * 0.35
    uncertainty += (0.10 if ood else 0.0)
    return {
        "path": str(row["path"]),
        "content_sha256": row.get("content_sha256") or ensemble.get("content_sha256") or route.get("content_sha256"),
        "collection": _collection(str(row["path"]), marker),
        "domain": domain,
        "lane": lane,
        "model_disagreement": disagreement,
        "route_status": route.get("status"),
        "ensemble_status": ensemble.get("status"),
        "specialist_status": specialist.get("status"),
        "min_observed_margin": min_margin,
        "uncertainty_priority": uncertainty,
        "stable_tiebreak": _stable(str(row["path"]), seed),
        "semantic_label": None,
    }


def _take_balanced(items: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    if count <= 0 or not items:
        return []
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        buckets[(str(item["domain"]), str(item["collection"]))].append(item)
    for bucket in buckets.values():
        bucket.sort(key=lambda item: (-float(item["uncertainty_priority"]), float(item["stable_tiebreak"]), item["path"]))
    picked: list[dict[str, Any]] = []
    keys = sorted(buckets)
    while len(picked) < count:
        progressed = False
        for key in keys:
            if buckets[key]:
                picked.append(buckets[key].pop(0))
                progressed = True
                if len(picked) >= count:
                    break
        if not progressed:
            break
    return picked


def build_sample(packet: Path, out: Path, limit: int = 500, marker: str = "sample_pack_testing",
                 seed: int = 42, sealed_holdout_path: Path | None = SD / "sealed_holdout_vendors_v1.json") -> dict[str, Any]:
    header, rows = _read_packet(packet)
    if limit < 0:
        raise ValueError("limit must be non-negative")
    features = [_row_features(row, marker, seed) for row in rows]
    n_source_rows = len(features)
    sealed_names = _read_sealed_holdout(sealed_holdout_path)
    sealed_hashes = {
        str(item["content_sha256"]).lower() for item in features
        if item["collection"] in sealed_names and item.get("content_sha256")
    }
    before_exclusions = len(features)
    features = [item for item in features if item["collection"] not in sealed_names
                and str(item.get("content_sha256") or "").lower() not in sealed_hashes]
    sealed_excluded = before_exclusions - len(features)
    # One exact-content representative is enough for calibration.  Otherwise
    # aliases can overweight a sound and make the later precision estimate
    # look better (or worse) than the deployment population.
    seen_content: set[str] = set()
    unique_features: list[dict[str, Any]] = []
    duplicate_content_excluded = 0
    for item in features:
        content = str(item.get("content_sha256") or "").lower()
        if content and content in seen_content:
            duplicate_content_excluded += 1
            continue
        if content:
            seen_content.add(content)
        unique_features.append(item)
    features = unique_features
    lanes = ["model_disagreement", "non_music_route", "boundary_or_abstention", "random_audit"]
    quotas = [0.40, 0.15, 0.25, 0.20]
    selected: list[dict[str, Any]] = []
    selected_paths: set[str] = set()
    for lane, quota in zip(lanes, quotas):
        pool = [item for item in features if item["lane"] == lane and item["path"] not in selected_paths]
        n = min(len(pool), int(round(limit * quota)))
        for item in _take_balanced(pool, n):
            selected.append(item)
            selected_paths.add(item["path"])
    if len(selected) < limit:
        remaining = [item for item in features if item["path"] not in selected_paths]
        for item in _take_balanced(remaining, limit - len(selected)):
            selected.append(item)
            selected_paths.add(item["path"])
    selected.sort(key=lambda item: (-float(item["uncertainty_priority"]), item["lane"], item["path"]))
    for index, item in enumerate(selected, 1):
        item["sample_index"] = index
        item["review_axes"] = ["domain", "structured_name", "abstention_decision"]
    lane_counts = defaultdict(int)
    domain_counts = defaultdict(int)
    collection_counts = defaultdict(int)
    for item in selected:
        lane_counts[item["lane"]] += 1
        domain_counts[item["domain"]] += 1
        collection_counts[item["collection"]] += 1
    payload = {
        "record_type": "slo_label_free_calibration_sample_manifest",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "source_packet": str(packet.resolve()),
        "source_packet_sha256": hashlib.sha256(packet.read_bytes()).hexdigest(),
        "source_method_version": header.get("method_version"),
        "marker": marker,
        "seed": seed,
        "n_source_rows": n_source_rows,
        "n_eligible_rows": len(features),
        "n_selected": len(selected),
        "lane_counts": dict(sorted(lane_counts.items())),
        "domain_counts": dict(sorted(domain_counts.items())),
        "collection_counts": dict(sorted(collection_counts.items())),
        "exclusions": {
            "sealed_holdout_path": str(sealed_holdout_path.resolve()) if sealed_holdout_path else None,
            "sealed_holdout_collections": sorted(sealed_names),
            "sealed_holdout_rows_excluded": sealed_excluded,
            "duplicate_content_rows_excluded": duplicate_content_excluded,
        },
        "rows": selected,
        "safety": {
            "read_only": True,
            "ground_truth_read": False,
            "semantic_labels_created": False,
            "audio_modified": False,
            "rename_actions": False,
            "human_ear_review_required_for_calibration": True,
            "random_audit_reserved": True,
        },
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--marker", default="sample_pack_testing")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--sealed-holdout", type=Path, default=SD / "sealed_holdout_vendors_v1.json",
                        help="collection holdout config excluded from calibration sampling")
    args = parser.parse_args()
    payload = build_sample(args.packet, args.out, args.limit, args.marker, args.seed, args.sealed_holdout)
    print(json.dumps({"out": str(args.out), "n_selected": payload["n_selected"], "read_only": True}, indent=2))


if __name__ == "__main__":
    main()
