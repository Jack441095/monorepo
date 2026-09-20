#!/usr/bin/env python3
"""Resolve a controlled natural-language discovery query into evidence facets.

This is a local, deterministic alternative to a cloud text search. Only terms
in the explicit vocabulary are resolved. Unknown terms remain visible in the
receipt and never become labels or class predictions.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
from pathlib import Path
from typing import Any


SD = Path(__file__).resolve().parent
VERSION = "describe_sound_query_v1"


def _load_facets():
    spec = importlib.util.spec_from_file_location("filter_definition_cards", SD / "filter_definition_cards.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


VOCAB = {
    "loop": {"form": "possibly_loop"},
    "loops": {"form": "possibly_loop"},
    "one-shot": {"form": "possibly_one_shot"},
    "oneshot": {"form": "possibly_one_shot"},
    "one": {"form": "possibly_one_shot"},
    "shot": {"form": "possibly_one_shot"},
    "sustained": {"form": "possibly_sustained"},
    "sustain": {"form": "possibly_sustained"},
    "dark": {"max_centroid": 2500.0},
    "bright": {"min_centroid": 3500.0},
    "airy": {"min_centroid": 3500.0},
    "low": {"min_low_band": 0.5},
    "sub": {"min_low_band": 0.65},
    "transient": {"tag": "transient_dense"},
    "transients": {"tag": "transient_dense"},
    "noisy": {"tag": "noisy_or_inharmonic"},
    "wide": {"tag": "wide_or_decorrelated"},
}


def parse_query(text: str) -> dict[str, Any]:
    normalized = re.sub(r"[^a-z0-9-]+", " ", text.lower()).strip()
    terms = normalized.split() if normalized else []
    filters: dict[str, Any] = {}
    resolved: list[str] = []
    unmatched: list[str] = []
    index = 0
    while index < len(terms):
        term = terms[index]
        if term == "one" and index + 1 < len(terms) and terms[index + 1] == "shot":
            key = "one-shot"
            index += 2
        else:
            key = term
            index += 1
        mapping = VOCAB.get(key)
        if mapping is None:
            unmatched.append(key)
            continue
        conflict = any(name in filters and filters[name] != value for name, value in mapping.items())
        if conflict:
            unmatched.append(key)
            continue
        filters.update(mapping)
        resolved.append(key)
    return {"text": text, "normalized": normalized, "filters": filters,
            "resolved_terms": resolved, "unmatched_terms": unmatched}


def _class_matches(row: dict[str, Any], query_terms: list[str], available_classes: set[str]) -> bool:
    if not query_terms:
        return True
    predicted = str(row.get("predicted_class") or "").lower()
    # A text token can narrow to a class only when that class already exists in
    # the supplied data; no new class name is manufactured here.
    hints = [cls.lower() for cls in available_classes if any(term in cls.lower() for term in query_terms)]
    return not hints or any(hint in predicted for hint in hints)


def search(payload: dict[str, Any], text: str, limit: int = 100) -> dict[str, Any]:
    facets = _load_facets()
    query = parse_query(text)
    rows = facets._flatten(payload)
    classes = {str(row.get("predicted_class")) for row in rows if row.get("predicted_class")}
    query_terms = [term for term in query["normalized"].split() if term not in VOCAB]
    # Keep unsupported words visible, but use exact existing-class tokens as a
    # discovery narrowing signal.
    class_terms = [term for term in query_terms if any(term in cls.lower() for cls in classes)]
    query["unmatched_terms"] = [term for term in query["unmatched_terms"] if term not in class_terms]
    query["resolved_terms"] = list(query["resolved_terms"]) + class_terms
    candidates = [row for row in rows if facets._matches(row, query["filters"])
                  and _class_matches(row, class_terms, classes)]
    candidates.sort(key=lambda row: str(row.get("path", "")))
    result = {
        "record_type": "slo_describe_sound_query_results",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "query": query,
        "class_terms_used": class_terms,
        "n_input": len(rows),
        "n_matched": min(len(candidates), limit),
        "results": candidates[:limit],
        "safety": {
            "read_only": True,
            "text_created_labels": False,
            "text_overrode_waveform": False,
            "unsupported_terms_preserved": True,
            "rename_actions": False,
        },
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    result = search(payload, args.query, args.limit)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"n_input": result["n_input"], "n_matched": result["n_matched"], "query": result["query"]}, indent=2))


if __name__ == "__main__":
    main()
