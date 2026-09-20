#!/usr/bin/env python3
"""Compare two read-only domain-router receipts on one verified file set.

This evaluator treats the verified drum/sample set as an expected
``music_sample`` domain.  It does not infer fine-grained semantic labels and
does not modify audio or promote model output.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any


def _key(path: str, marker: str) -> str:
    token = marker.rstrip("/") + "/"
    return path.split(token, 1)[-1] if token in path else path


def _read_receipt(path: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows or rows[0].get("record_type") != "slo_label_free_domain_router_receipt":
        raise ValueError(f"not a domain-router receipt: {path}")
    return rows[0], {str(row["path"]): row for row in rows[1:] if "path" in row}


def _wilson(successes: int, total: int, z: float = 1.959963984540054) -> float | None:
    if total <= 0:
        return None
    p = successes / total
    den = 1.0 + z * z / total
    centre = p + z * z / (2.0 * total)
    spread = z * math.sqrt((p * (1.0 - p) + z * z / (4.0 * total)) / total)
    return max(0.0, (centre - spread) / den)


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    routes = Counter(str(row.get("domain_suggestion")) for row in rows)
    suggestions = [row for row in rows if row.get("status") == "suggest"]
    music = sum(row.get("domain_suggestion") == "music_sample" for row in rows)
    music_suggest = sum(row.get("domain_suggestion") == "music_sample" for row in suggestions)
    n = len(rows)
    return {
        "n_files": n,
        "route_counts": dict(sorted(routes.items())),
        "expected_domain": "music_sample",
        "expected_domain_count": music,
        "expected_domain_rate": music / n if n else None,
        "expected_domain_rate_wilson_lower_95": _wilson(music, n),
        "suggest_count": len(suggestions),
        "suggest_expected_domain_count": music_suggest,
        "suggest_expected_domain_precision": music_suggest / len(suggestions) if suggestions else None,
        "suggest_expected_domain_precision_wilson_lower_95": _wilson(music_suggest, len(suggestions)),
    }


def evaluate(labels: Path, baseline: Path, candidate: Path, out: Path,
             marker: str = "sample_pack_testing") -> dict[str, Any]:
    label_rows = list(csv.DictReader(labels.open(newline="", encoding="utf-8")))
    expected: dict[str, str] = {}
    conflicts: set[str] = set()
    for row in label_rows:
        key = _key(str(row["path"]), marker)
        label = str(row["label"])
        if key in expected and expected[key] != label:
            conflicts.add(key)
        else:
            expected.setdefault(key, label)
    expected = {key: value for key, value in expected.items() if key not in conflicts}

    base_header, base_rows = _read_receipt(baseline)
    cand_header, cand_rows = _read_receipt(candidate)
    paired: list[dict[str, Any]] = []
    for key, label in expected.items():
        base = next((row for path, row in base_rows.items() if _key(path, marker) == key), None)
        cand = next((row for path, row in cand_rows.items() if _key(path, marker) == key), None)
        if base is not None and cand is not None:
            paired.append({"key": key, "verified_label": label, "baseline": base, "candidate": cand})

    base_eval = [row["baseline"] for row in paired]
    cand_eval = [row["candidate"] for row in paired]
    base_correct = [row.get("domain_suggestion") == "music_sample" for row in base_eval]
    cand_correct = [row.get("domain_suggestion") == "music_sample" for row in cand_eval]
    changed = sum(a != b for a, b in zip(base_correct, cand_correct))
    result = {
        "record_type": "slo_label_free_domain_router_pair_evaluation",
        "schema_version": "1.0.0",
        "labels": str(labels),
        "baseline_receipt": str(baseline),
        "candidate_receipt": str(candidate),
        "marker": marker,
        "n_label_rows": len(label_rows),
        "n_unique_nonconflicting_labels": len(expected),
        "n_conflicting_keys_excluded": len(conflicts),
        "n_paired_files": len(paired),
        "baseline": {"header": base_header, **_metrics(base_eval)},
        "candidate": {"header": cand_header, **_metrics(cand_eval)},
        "paired": {
            "n_changed_expected_domain_decisions": changed,
            "candidate_improved_count": sum(not a and b for a, b in zip(base_correct, cand_correct)),
            "candidate_worsened_count": sum(a and not b for a, b in zip(base_correct, cand_correct)),
        },
        "safety": {
            "read_only": True,
            "audio_read": False,
            "semantic_labels_created": False,
            "rename_actions": False,
            "source_audio_modified": False,
            "model_output_promoted": False,
        },
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--marker", default="sample_pack_testing")
    args = parser.parse_args()
    result = evaluate(args.labels, args.baseline, args.candidate, args.out, args.marker)
    print(json.dumps({"out": str(args.out), "n_paired_files": result["n_paired_files"], "read_only": True}, indent=2))


if __name__ == "__main__":
    main()
