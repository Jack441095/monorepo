#!/usr/bin/env python3
"""Extract physical definition cards for a label-free review queue.

Cards describe measurable waveform properties and provisional form hints. They
never create semantic labels, ground truth, metadata, or rename actions.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import importlib.util
import json
from pathlib import Path
from typing import Any


VERSION = "label_free_physical_cards_v1"
MODULE_PATH = Path(__file__).with_name("audio_definition_card.py")


def _load_card_module():
    spec = importlib.util.spec_from_file_location("slo_audio_definition_card", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load audio definition card module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_queue(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("record_type") != "slo_label_free_review_queue":
        raise ValueError("input is not a label-free review queue")
    safety = payload.get("safety") or {}
    if not safety.get("read_only") or safety.get("semantic_labels_created") or safety.get("rename_actions"):
        raise ValueError("review queue is not read-only")
    rows = payload.get("rows")
    if not isinstance(rows, list) or any(not isinstance(row, dict) or not row.get("path") for row in rows):
        raise ValueError("review queue rows are invalid")
    return payload, rows


def _analyse(item: tuple[str, str]) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    logical_path, analysis_path = item
    try:
        card = _load_card_module().analyse_file(analysis_path)
        # Keep the receipt path stable even when analysis uses a local mirror.
        card["path"] = logical_path
        card["analysis_path"] = str(Path(analysis_path).resolve())
        return card, None
    except Exception as exc:
        return None, {"path": logical_path, "analysis_path": analysis_path, "error": str(exc)}


def build(queue: Path, out: Path, limit: int = 500, workers: int = 1,
          source_prefix: str | None = None, analysis_root: Path | None = None) -> dict[str, Any]:
    if limit < 0 or workers < 1:
        raise ValueError("limit must be non-negative and workers must be positive")
    source, rows = _read_queue(queue)
    selected = rows[:limit]
    paths = [str(row["path"]) for row in selected]
    if (source_prefix is None) != (analysis_root is None):
        raise ValueError("source_prefix and analysis_root must be supplied together")
    source_root = Path(source_prefix).resolve() if source_prefix else None
    analysis_root = analysis_root.resolve() if analysis_root else None
    analysis_items: list[tuple[str, str]] = []
    for logical_path in paths:
        candidate = Path(logical_path)
        if source_root is not None and analysis_root is not None:
            try:
                relative = candidate.relative_to(source_root)
            except ValueError as exc:
                raise ValueError(f"queue path is outside source_prefix: {logical_path}") from exc
            candidate = analysis_root / relative
        analysis_items.append((logical_path, str(candidate)))
    if workers == 1:
        results = [_analyse(item) for item in analysis_items]
    else:
        with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(_analyse, analysis_items))
    cards = [card for card, error in results if card is not None]
    errors = [error for card, error in results if error is not None]
    payload = {
        "record_type": "slo_label_free_physical_cards",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "source_queue": str(queue.resolve()),
        "source_queue_method_version": source.get("method_version"),
        "n_requested": len(paths),
        "n_cards": len(cards),
        "n_errors": len(errors),
        "cards": cards,
        "errors": errors,
        "safety": {
            "read_only": True,
            "semantic_labels_created": False,
            "ground_truth_read": False,
            "rename_actions": False,
            "source_audio_modified": False,
            "heuristics_are_not_ground_truth": True,
            "human_approval_required": True,
        },
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--source-prefix",
                        help="logical path prefix in the queue when analysing a local mirror")
    parser.add_argument("--analysis-root", type=Path,
                        help="local root corresponding to --source-prefix")
    args = parser.parse_args()
    result = build(args.queue, args.out, args.limit, args.workers,
                   args.source_prefix, args.analysis_root)
    print(json.dumps({"out": str(args.out), "n_requested": result["n_requested"],
                      "n_cards": result["n_cards"], "n_errors": result["n_errors"],
                      "read_only": True}, indent=2))


if __name__ == "__main__":
    main()
