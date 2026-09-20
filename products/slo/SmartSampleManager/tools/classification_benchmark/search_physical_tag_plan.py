#!/usr/bin/env python3
"""Search the label-free physical-tag plan without creating labels or actions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def load_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        records = [json.loads(line) for line in handle if line.strip()]
    if not records or records[0].get("record_type") != "slo_physical_tag_plan":
        raise ValueError("input must begin with slo_physical_tag_plan")
    header, rows = records[0], records[1:]
    if int(header.get("n_files", -1)) != len(rows):
        raise ValueError("physical-tag plan row count mismatch")
    return rows


def search(rows: list[dict[str, Any]], *, tag: str | None = None,
           form: str | None = None, path_contains: str | None = None,
           min_duration: float | None = None, max_duration: float | None = None,
           min_low_band: float | None = None, max_centroid: float | None = None,
           limit: int = 0) -> list[dict[str, Any]]:
    needle = path_contains.lower() if path_contains else None
    out = []
    for row in rows:
        if tag and tag not in row.get("technical_tags", []):
            continue
        if form and row.get("form_hint") != form:
            continue
        if needle and needle not in str(row.get("path", "")).lower():
            continue
        duration = _number(row.get("duration_seconds"))
        if min_duration is not None and (duration is None or duration < min_duration):
            continue
        if max_duration is not None and (duration is None or duration > max_duration):
            continue
        low_band = _number(row.get("low_band_energy_ratio"))
        if min_low_band is not None and (low_band is None or low_band < min_low_band):
            continue
        centroid = _number(row.get("spectral_centroid_hz"))
        if max_centroid is not None and (centroid is None or centroid > max_centroid):
            continue
        out.append(row)
        if limit and len(out) >= limit:
            break
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--tag")
    parser.add_argument("--form")
    parser.add_argument("--path-contains")
    parser.add_argument("--min-duration", type=float)
    parser.add_argument("--max-duration", type=float)
    parser.add_argument("--min-low-band", type=float)
    parser.add_argument("--max-centroid", type=float)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.limit < 0:
        raise SystemExit("--limit must be non-negative")
    rows = search(load_rows(args.plan), tag=args.tag, form=args.form,
                  path_contains=args.path_contains,
                  min_duration=args.min_duration,
                  max_duration=args.max_duration,
                  min_low_band=args.min_low_band,
                  max_centroid=args.max_centroid,
                  limit=args.limit)
    payload = {
        "record_type": "slo_physical_tag_search_results",
        "schema_version": "1.0.0",
        "query": {key: value for key, value in vars(args).items()
                  if key not in {"plan", "out"} and value is not None},
        "n_results": len(rows),
        "rows": rows,
        "safety": {"read_only": True, "semantic_labels_created": False,
                    "rename_actions": False, "source_audio_modified": False},
    }
    text = json.dumps(payload, indent=2) + "\n"
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
