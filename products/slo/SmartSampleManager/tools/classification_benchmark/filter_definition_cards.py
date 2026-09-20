#!/usr/bin/env python3
"""Filter local definition-card or review-collection records by evidence facets.

Facet values are evidence, not semantic labels. Missing/uncertain values do not
match numeric filters, and this command never changes source files or model
decisions.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Iterable


VERSION = "evidence_facets_v1"


def _get(mapping: dict[str, Any], *keys: str) -> Any:
    value: Any = mapping
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _as_number(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _flatten(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object or list")
    if isinstance(payload.get("cards"), list):
        return [row for row in payload["cards"] if isinstance(row, dict)]
    if isinstance(payload.get("collections"), dict):
        rows = []
        for action, values in payload["collections"].items():
            for row in values:
                if not isinstance(row, dict):
                    continue
                item = dict(row)
                item["action"] = action
                item["facets"] = _get(row, "review_evidence", "facets")
                rows.append(item)
        return rows
    raise ValueError("input has no cards or review collections")


def _facet(row: dict[str, Any], name: str) -> Any:
    # Native cards use nested sections; review collections expose a flattened
    # review_evidence.facets object. Both are accepted.
    facets = row.get("facets")
    if isinstance(facets, dict) and name in facets:
        return facets[name]
    native = {
        "duration_seconds": ("source", "analysis_duration_seconds"),
        "form_hint": ("temporal", "form_hint"),
        "form_hint_confidence": ("temporal", "form_hint_confidence"),
        "estimated_tempo_bpm": ("temporal", "estimated_tempo_bpm"),
        "onset_density_per_second": ("temporal", "onset_density_per_second"),
        "median_f0_hz": ("pitch", "median_f0_hz"),
        "spectral_centroid_hz": ("spectrum", "spectral_centroid_hz"),
        "low_band_energy_ratio": ("spectrum", "low_band_energy_ratio"),
        "high_band_energy_ratio": ("spectrum", "high_band_energy_ratio"),
        "stereo_correlation": ("spatial", "stereo_correlation"),
    }
    path = native.get(name)
    return _get(row, *path) if path else row.get(name)


def _matches(row: dict[str, Any], filters: dict[str, Any]) -> bool:
    if filters.get("action") and row.get("action") != filters["action"]:
        return False
    if filters.get("form") and _facet(row, "form_hint") != filters["form"]:
        return False
    tags = row.get("heuristic_tags")
    if tags is None:
        tags = _facet(row, "heuristic_tags")
    if filters.get("tag") and filters["tag"] not in (tags or []):
        return False
    ranges = {
        "min_duration": "duration_seconds", "max_duration": "duration_seconds",
        "min_centroid": "spectral_centroid_hz", "max_centroid": "spectral_centroid_hz",
        "min_low_band": "low_band_energy_ratio", "max_low_band": "low_band_energy_ratio",
        "min_onset_density": "onset_density_per_second", "max_onset_density": "onset_density_per_second",
        "min_pitch": "median_f0_hz", "max_pitch": "median_f0_hz",
    }
    for option, facet_name in ranges.items():
        threshold = filters.get(option)
        if threshold is None:
            continue
        value = _as_number(_facet(row, facet_name))
        if value is None:
            return False
        if option.startswith("min_") and value < threshold:
            return False
        if option.startswith("max_") and value > threshold:
            return False
    return True


def filter_records(payload: Any, filters: dict[str, Any], limit: int | None = None) -> dict[str, Any]:
    rows = _flatten(payload)
    matched = [row for row in rows if _matches(row, filters)]
    matched.sort(key=lambda row: str(row.get("path", "")))
    if limit is not None:
        matched = matched[:limit]
    return {
        "record_type": "slo_evidence_facet_results",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "filters": filters,
        "n_input": len(rows),
        "n_matched": len(matched),
        "results": matched,
        "safety": {
            "read_only": True,
            "source_audio_modified": False,
            "labels_created": False,
            "decisions_changed": False,
            "unknown_values_filled": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--action", choices=("auto_rename", "suggest", "review", "never_act"))
    parser.add_argument("--form")
    parser.add_argument("--tag")
    parser.add_argument("--min-duration", type=float)
    parser.add_argument("--max-duration", type=float)
    parser.add_argument("--min-centroid", type=float)
    parser.add_argument("--max-centroid", type=float)
    parser.add_argument("--min-low-band", type=float)
    parser.add_argument("--max-low-band", type=float)
    parser.add_argument("--min-onset-density", type=float)
    parser.add_argument("--max-onset-density", type=float)
    parser.add_argument("--min-pitch", type=float)
    parser.add_argument("--max-pitch", type=float)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        raise SystemExit("--limit must be positive")
    filters = {key: value for key, value in {
        "action": args.action, "form": args.form, "tag": args.tag,
        "min_duration": args.min_duration, "max_duration": args.max_duration,
        "min_centroid": args.min_centroid, "max_centroid": args.max_centroid,
        "min_low_band": args.min_low_band, "max_low_band": args.max_low_band,
        "min_onset_density": args.min_onset_density, "max_onset_density": args.max_onset_density,
        "min_pitch": args.min_pitch, "max_pitch": args.max_pitch,
    }.items() if value is not None}
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    result = filter_records(payload, filters, args.limit)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"n_input": result["n_input"], "n_matched": result["n_matched"]}, indent=2))


if __name__ == "__main__":
    main()
