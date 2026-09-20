#!/usr/bin/env python3
"""Read-only audit of future taxonomy readiness.

This deliberately does not scan audio, create labels, train a model, or modify
the source library. It summarises the existing candidate prediction receipt
against the current production label set and the dormant real-world taxonomy.
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path
from typing import Any


CURRENT_PRODUCTION_CLASSES = {
    "Bass Hit", "Bass Loop", "Bass One-Shot", "Bass Reese", "Clap", "Crash",
    "Drum Fill", "Drum Loop", "FX", "Foley", "Foley Loop", "Hi-Hat",
    "Hi-Hat Loop", "Impact", "Kick", "Kick Loop", "Music Loop", "Other/none",
    "Pad", "Percussion", "Percussion Loop", "Rimshot", "Riser", "SFX", "Snare",
    "Synth", "Synth Loop", "Synth One-Shot", "Vocal Loop", "Vocal Phrase",
    "Vocal One-Shot", "Weather/Nature Atmos", "Chord Loop",
}

REAL_WORLD_PREFIXES = {
    "animal": {"Bird", "Mammal", "Insect", "Amphibian", "Reptile", "Marine animal"},
    "human": {"Speech", "Laugh", "Cry", "Cough or sneeze"},
    "environment": {"Weather", "Water", "Fire", "Wind", "Nature ambience"},
    "mechanical": {"Engine", "Vehicle", "Machine"},
    "impact_material": {"Metal", "Wood", "Glass", "Stone", "Paper"},
}


def load_prediction_rows(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    header: dict[str, Any] | None = None
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if line_number == 1 and record.get("record_type", "").endswith("predictions"):
                header = record
            else:
                rows.append(record)
    if header is None:
        raise ValueError(f"missing prediction receipt header in {path}")
    return header, rows


def classify_candidate_label(label: str) -> str:
    """Return a reporting domain without enabling a production class."""
    if label in CURRENT_PRODUCTION_CLASSES:
        return "current_music_sample"
    lowered = label.lower()
    if any(token in lowered for token in ("animal", "bird", "mammal", "insect", "amphib")):
        return "future_animal"
    if any(token in lowered for token in ("weather", "nature", "water", "wind", "fire", "ambience")):
        return "future_environment"
    if any(token in lowered for token in ("engine", "vehicle", "machine", "mechanical")):
        return "future_mechanical"
    if any(token in lowered for token in ("speech", "laugh", "cough", "sneeze", "human")):
        return "future_human"
    return "unmapped_candidate"


def build_report(predictions_path: Path, taxonomy_path: Path) -> dict[str, Any]:
    header, rows = load_prediction_rows(predictions_path)
    taxonomy = json.loads(taxonomy_path.read_text(encoding="utf-8"))
    counts: collections.Counter[str] = collections.Counter()
    domains: collections.Counter[str] = collections.Counter()
    for row in rows:
        label = str(row.get("full_taxonomy_class") or row.get("predicted_class") or "")
        counts[label] += 1
        domains[classify_candidate_label(label)] += 1
    unmapped = sorted(label for label in counts if classify_candidate_label(label) == "unmapped_candidate")
    future = sorted(label for label in counts if classify_candidate_label(label).startswith("future_"))
    return {
        "record_type": "slo_taxonomy_readiness_audit",
        "schema_version": "1.0.0",
        "safety": {
            "read_only": True,
            "audio_scanned": False,
            "labels_created": False,
            "source_files_modified": False,
            "production_taxonomy_changed": False,
            "rename_plan_applied": False,
        },
        "inputs": {
            "predictions": str(predictions_path.resolve()),
            "predictions_record_type": header.get("record_type"),
            "taxonomy": str(taxonomy_path.resolve()),
            "taxonomy_status": taxonomy.get("status"),
        },
        "summary": {
            "prediction_rows": len(rows),
            "distinct_predicted_labels": len(counts),
            "domain_counts": dict(sorted(domains.items())),
            "future_or_unmapped_labels": future + unmapped,
            "unmapped_labels": unmapped,
        },
        "predicted_label_counts": dict(sorted(counts.items())),
        "next_gate": "human labels plus collection-held-out evaluation before activating any future domain",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--taxonomy", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = build_report(args.predictions, args.taxonomy)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
