#!/usr/bin/env python3
"""Audit whether a low-end-heavy tag adds information beyond Bright/Dark.

This is a descriptive, label-free feature audit.  It does not invent an
attribute ground truth and cannot authorize a production tag; it reports
coverage, overlap and class concentration so an owner can decide whether a
separate attribute-labeling pass is worthwhile.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np


VERSION = "low_end_heavy_redundancy_audit_v1"


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def audit(cards_path: Path, corpus_path: Path, threshold: float = 0.60) -> dict[str, Any]:
    cards_payload = _load(cards_path)
    cards = cards_payload.get("cards") if isinstance(cards_payload, dict) else None
    if not isinstance(cards, list) or not cards:
        raise ValueError("physical-card receipt must contain a non-empty cards list")
    corpus = np.load(corpus_path, allow_pickle=True)
    required = {"paths", "labels"}
    if not required.issubset(corpus.files):
        raise ValueError("corpus must contain paths and labels")
    labels_by_path = {str(path): str(label)
                      for path, label in zip(corpus["paths"], corpus["labels"])}

    rows: list[tuple[str, float, float]] = []
    for card in cards:
        if not isinstance(card, dict) or not card.get("path"):
            continue
        spectrum = card.get("spectrum") or {}
        low = spectrum.get("low_band_energy_ratio")
        centroid = spectrum.get("spectral_centroid_hz")
        label = labels_by_path.get(str(card["path"]))
        if label is None:
            continue
        try:
            low_value = float(low)
            centroid_value = float(centroid)
        except (TypeError, ValueError):
            continue
        if not np.isfinite(low_value) or not np.isfinite(centroid_value):
            continue
        rows.append((label, low_value, centroid_value))
    if not rows:
        raise ValueError("no finite card/corpus rows could be joined")

    low = np.asarray([row[1] for row in rows], dtype=np.float64)
    centroid = np.asarray([row[2] for row in rows], dtype=np.float64)
    low_mask = low >= float(threshold)
    dark_mask = (centroid > 0.0) & (centroid < 1200.0)
    overlap = low_mask & dark_mask
    concentration = Counter(label for (label, _, _), selected in zip(rows, low_mask) if selected)

    result = {
        "record_type": "slo_low_end_heavy_redundancy_audit",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "source_cards": str(cards_path.resolve()),
        "source_corpus": str(corpus_path.resolve()),
        "n_joined": len(rows),
        "threshold": float(threshold),
        "signal": {
            "low_band_energy_ratio_median": float(np.median(low)),
            "low_band_energy_ratio_p25": float(np.quantile(low, 0.25)),
            "low_band_energy_ratio_p75": float(np.quantile(low, 0.75)),
            "spectral_centroid_median_hz": float(np.median(centroid)),
            "pearson_low_ratio_vs_centroid": float(np.corrcoef(low, centroid)[0, 1]),
        },
        "coverage": {
            "low_end_heavy_candidate_count": int(np.sum(low_mask)),
            "low_end_heavy_candidate_share": float(np.mean(low_mask)),
            "dark_candidate_count": int(np.sum(dark_mask)),
            "dark_candidate_share": float(np.mean(dark_mask)),
            "overlap_count": int(np.sum(overlap)),
            "overlap_share_of_low_end_heavy": float(np.mean(dark_mask[low_mask])) if np.any(low_mask) else 0.0,
            "overlap_share_of_dark": float(np.mean(low_mask[dark_mask])) if np.any(dark_mask) else 0.0,
        },
        "class_concentration_of_low_end_heavy_candidates": dict(concentration.most_common()),
        "decision": "research_only; no low-end-heavy tag or policy change",
        "safety": {
            "attribute_ground_truth_created": False,
            "production_model_changed": False,
            "rename_actions": False,
            "source_audio_modified": False,
        },
        "recommendation": (
            "do_not_ship_without_attribute_labels: low-band energy is a useful "
            "physical descriptor but overlaps Dark and heterogeneous classes; "
            "collect explicit low-end-heavy owner labels before adding a tag"
        ),
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cards", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--threshold", type=float, default=0.60)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.cards, args.corpus, args.threshold)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"n_joined": result["n_joined"], "coverage": result["coverage"], "out": str(args.out)}, indent=2))


if __name__ == "__main__":
    main()
