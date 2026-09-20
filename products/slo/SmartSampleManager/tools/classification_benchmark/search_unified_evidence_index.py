#!/usr/bin/env python3
"""Search the unified SLO evidence index without changing decisions or files.

This is a local, deterministic discovery surface. It supports controlled text
synonyms, exact factor filters, numeric physical-evidence filters, and duplicate
inspection. It never turns a search match into a label or rename action.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any


VERSION = "unified_evidence_search_v1"

SYNONYMS = {
    "bd": "kick", "bassdrum": "kick", "bass-drum": "kick",
    "hh": "hi-hat", "hihat": "hi-hat", "hat": "hi-hat",
    "snare-drum": "snare", "clap": "clap", "tamb": "shaker",
    "tambourine": "shaker", "atmo": "atmosphere",
}


def load_records(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("record_type") != "slo_audio_evidence_record":
                raise ValueError(f"unexpected record type at line {line_no}")
            content_id = str(row.get("content_id") or "")
            if not content_id or content_id in seen:
                raise ValueError(f"duplicate or missing content_id at line {line_no}")
            seen.add(content_id)
            records.append(row)
    return records, {"path": str(path.resolve()), "n_records": len(records)}


def _normalise(text: Any) -> str:
    return re.sub(r"[^a-z0-9-]+", " ", str(text or "").lower()).strip()


def parse_query(text: str) -> dict[str, Any]:
    normalized = _normalise(text)
    raw_terms = normalized.split() if normalized else []
    terms: list[str] = []
    resolved: list[str] = []
    for term in raw_terms:
        mapped = SYNONYMS.get(term, term)
        terms.append(mapped)
        resolved.append(mapped if mapped != term else term)
    return {"text": text, "normalized": normalized, "terms": terms,
            "resolved_terms": resolved}


def _claim(row: dict[str, Any], name: str) -> str:
    claim = row.get(name)
    return _normalise(claim.get("value") if isinstance(claim, dict) else "")


def _prediction_text(row: dict[str, Any]) -> str:
    prediction = row.get("metadata", {}).get("prediction", {})
    if not isinstance(prediction, dict):
        return ""
    return _normalise(prediction.get("label"))


def _search_text(row: dict[str, Any]) -> str:
    metadata = row.get("metadata", {})
    aliases = metadata.get("aliases", []) if isinstance(metadata, dict) else []
    values = [row.get("source_path"), _claim(row, "identity"),
              _claim(row, "family"), _claim(row, "form"),
              _prediction_text(row), *aliases]
    return " ".join(_normalise(value) for value in values)


def _number(value: Any) -> float | None:
    try:
        number = float(value)
        return number if number == number and abs(number) != float("inf") else None
    except (TypeError, ValueError):
        return None


def _measurement(row: dict[str, Any], name: str) -> float | None:
    measurement = row.get("measurements", {}).get(name)
    return _number(measurement.get("value")) if isinstance(measurement, dict) else None


def _matches(row: dict[str, Any], query: dict[str, Any], filters: dict[str, Any]) -> bool:
    if any(term not in _search_text(row) for term in query["terms"]):
        return False
    family = filters.get("family")
    if family and _claim(row, "family") != _normalise(family):
        return False
    form = filters.get("form")
    if form and _claim(row, "form") != _normalise(form):
        return False
    label = filters.get("predicted_label")
    if label and _prediction_text(row) != _normalise(label):
        return False
    if filters.get("action"):
        prediction = row.get("metadata", {}).get("prediction", {})
        if not isinstance(prediction, dict) or prediction.get("action") != filters["action"]:
            return False
    if filters.get("duplicate_only") and not row.get("duplicate_group"):
        return False
    for name in filters.get("has_measurement", []):
        if _measurement(row, name) is None:
            return False
    for name, minimum in filters.get("min_measurements", {}).items():
        value = _measurement(row, name)
        if value is None or value < minimum:
            return False
    for name, maximum in filters.get("max_measurements", {}).items():
        value = _measurement(row, name)
        if value is None or value > maximum:
            return False
    return True


def _score(row: dict[str, Any], query: dict[str, Any]) -> tuple[int, float, str]:
    text = _search_text(row)
    exact_hits = sum(1 for term in query["terms"] if term in text)
    claim = row.get("identity", {})
    confidence = _number(claim.get("confidence")) if isinstance(claim, dict) else 0.0
    return exact_hits, confidence or 0.0, str(row.get("source_path", ""))


def search(records: list[dict[str, Any]], text: str = "", *, family: str | None = None,
           form: str | None = None, predicted_label: str | None = None,
           action: str | None = None, has_measurement: list[str] | None = None,
           min_measurements: dict[str, float] | None = None,
           max_measurements: dict[str, float] | None = None,
           duplicate_only: bool = False, limit: int = 100) -> dict[str, Any]:
    if limit < 1:
        raise ValueError("limit must be positive")
    query = parse_query(text)
    filters = {
        "family": family, "form": form, "predicted_label": predicted_label,
        "action": action, "has_measurement": has_measurement or [],
        "min_measurements": min_measurements or {},
        "max_measurements": max_measurements or {},
        "duplicate_only": duplicate_only,
    }
    matched = [row for row in records if _matches(row, query, filters)]
    matched.sort(key=lambda row: (-_score(row, query)[0], -_score(row, query)[1],
                                  _score(row, query)[2]))
    result = {
        "record_type": "slo_unified_evidence_search_results",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "query": query,
        "filters": filters,
        "n_input": len(records),
        "n_matched": min(len(matched), limit),
        "results": matched[:limit],
        "safety": {
            "read_only": True,
            "source_audio_modified": False,
            "metadata_written": False,
            "semantic_labels_created": False,
            "decisions_changed": False,
            "rename_actions": False,
            "unknown_values_filled": False,
            "similarity_is_not_class_probability": True,
        },
    }
    return result


def _parse_measurements(values: list[str] | None) -> dict[str, float]:
    parsed: dict[str, float] = {}
    for value in values or []:
        if "=" not in value:
            raise ValueError("measurement filters must use NAME=VALUE")
        name, threshold = value.split("=", 1)
        if not name:
            raise ValueError("measurement name is empty")
        parsed[name] = float(threshold)
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--query", default="")
    parser.add_argument("--family")
    parser.add_argument("--form")
    parser.add_argument("--predicted-label")
    parser.add_argument("--action", choices=("auto_rename", "suggest", "review", "never_act"))
    parser.add_argument("--has-measurement", action="append", default=[])
    parser.add_argument("--min-measurement", action="append", default=[])
    parser.add_argument("--max-measurement", action="append", default=[])
    parser.add_argument("--duplicate-only", action="store_true")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    records, source = load_records(args.index)
    result = search(records, args.query, family=args.family, form=args.form,
                    predicted_label=args.predicted_label, action=args.action,
                    has_measurement=args.has_measurement,
                    min_measurements=_parse_measurements(args.min_measurement),
                    max_measurements=_parse_measurements(args.max_measurement),
                    duplicate_only=args.duplicate_only, limit=args.limit)
    result["index"] = source
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"n_input": result["n_input"], "n_matched": result["n_matched"],
                      "query": result["query"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
