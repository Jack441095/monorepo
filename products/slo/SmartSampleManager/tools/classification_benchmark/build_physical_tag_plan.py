#!/usr/bin/env python3
"""Build a non-semantic technical-tag plan from definition cards.

The output is an evidence/search layer, not a classifier and not a rename plan.
It never invents instrument names; all tags come from measured signal facets or
explicitly provisional temporal heuristics.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


VERSION = "physical_tag_plan_v1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tag_row(card: dict[str, Any]) -> dict[str, Any]:
    signal = card.get("signal", {})
    source = card.get("source", {})
    spectrum = card.get("spectrum", {})
    temporal = card.get("temporal", {})
    pitch = card.get("pitch", {})
    spatial = card.get("spatial", {})
    tags = list(card.get("heuristic_tags", []))
    form = str(temporal.get("form_hint", "mixed_or_uncertain_form"))
    tags.append(form)
    tempo = temporal.get("estimated_tempo_bpm")
    periodicity = temporal.get("periodicity_strength")
    if tempo is not None and periodicity is not None and float(periodicity) >= 0.55:
        tags.append("tempo_estimated")
    return {
        "path": str(card.get("path", "")),
        "action": "metadata_suggest",
        "semantic_label": None,
        "technical_tags": sorted(set(tags)),
        "form_hint": form,
        "form_hint_confidence": temporal.get("form_hint_confidence"),
        "duration_seconds": source.get("analysis_duration_seconds"),
        "estimated_tempo_bpm": tempo,
        "periodicity_strength": periodicity,
        "spectral_centroid_hz": spectrum.get("spectral_centroid_hz"),
        "low_band_energy_ratio": spectrum.get("low_band_energy_ratio"),
        "high_band_energy_ratio": spectrum.get("high_band_energy_ratio"),
        "harmonic_energy_ratio": spectrum.get("harmonic_energy_ratio"),
        "rms_dbfs": signal.get("rms_dbfs"),
        "peak_dbfs": signal.get("peak_dbfs"),
        "median_f0_hz": pitch.get("median_f0_hz"),
        "voiced_frame_fraction": pitch.get("voiced_frame_fraction"),
        "stereo_correlation": spatial.get("stereo_correlation"),
        "uncertainty_reasons": list(card.get("uncertainty_reasons", [])),
    }


def build_plan(cards_path: Path, out_path: Path) -> dict[str, Any]:
    payload = json.loads(cards_path.read_text(encoding="utf-8"))
    if payload.get("record_type") != "slo_audio_definition_cards":
        raise ValueError("input is not slo_audio_definition_cards")
    rows = [_tag_row(card) for card in payload.get("cards", [])]
    if any(not row["path"] for row in rows):
        raise ValueError("definition card has no path")
    if len({row["path"] for row in rows}) != len(rows):
        raise ValueError("definition cards contain duplicate paths")
    header = {
        "record_type": "slo_physical_tag_plan",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "source_cards": str(cards_path.resolve()),
        "source_cards_sha256": _sha256(cards_path),
        "n_files": len(rows),
        "safety": {
            "read_only": True,
            "semantic_labels_created": False,
            "rename_actions": False,
            "source_audio_modified": False,
            "technical_tags_are_not_ground_truth": True,
        },
    }
    with out_path.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(header) + "\n")
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    return header


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cards", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    header = build_plan(args.cards, args.out)
    print(json.dumps({"n_files": header["n_files"], "out": str(args.out), "read_only": True}, indent=2))


if __name__ == "__main__":
    main()
