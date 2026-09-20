#!/usr/bin/env python3
"""Build a read-only time-window manifest for physical-card candidates."""

from __future__ import annotations

import argparse
import concurrent.futures
import importlib.util
import json
from pathlib import Path
from typing import Any


VERSION = "label_free_segment_manifest_v1"
MODULE_PATH = Path(__file__).with_name("audio_segment_windows.py")


def _segment(item: tuple[str, str, dict[str, Any]]) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    logical_path, analysis_path, params = item
    try:
        spec = importlib.util.spec_from_file_location("slo_audio_segment_windows", MODULE_PATH)
        if spec is None or spec.loader is None:
            raise RuntimeError("cannot load segmenter")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        result = module.segment(analysis_path, **params)
        result["path"] = logical_path
        result["analysis_path"] = str(Path(analysis_path).resolve())
        return result, None
    except Exception as exc:
        return None, {"path": logical_path, "analysis_path": analysis_path, "error": str(exc)}


def _read_cards(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("record_type") not in {"slo_label_free_physical_cards", "slo_audio_definition_cards"}:
        raise ValueError("input is not a physical-card payload")
    safety = payload.get("safety") or {}
    if safety.get("semantic_labels_created") or safety.get("rename_actions"):
        raise ValueError("physical-card payload is not read-only")
    cards = payload.get("cards")
    if not isinstance(cards, list):
        raise ValueError("physical-card payload has no cards")
    return cards


def build(cards_path: Path, out: Path, limit: int = 500, workers: int = 1,
          min_duration: float = 0.08, merge_gap: float = 0.15,
          threshold_db: float = 6.0, max_segments: int = 64) -> dict[str, Any]:
    if limit < 0 or workers < 1:
        raise ValueError("limit must be non-negative and workers must be positive")
    cards = _read_cards(cards_path)[:limit]
    params = {"min_duration": min_duration, "merge_gap": merge_gap,
              "threshold_db": threshold_db, "max_segments": max_segments}
    items = [(str(card["path"]), str(card.get("analysis_path") or card["path"]), params)
             for card in cards if card.get("path")]
    if workers == 1:
        results = [_segment(item) for item in items]
    else:
        with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(_segment, items))
    windows = [item for item, error in results if item is not None]
    errors = [error for item, error in results if error is not None]
    payload = {
        "record_type": "slo_label_free_segment_manifest",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "source_cards": str(cards_path.resolve()),
        "n_requested": len(items),
        "n_segmented": len(windows),
        "n_errors": len(errors),
        "records": windows,
        "errors": errors,
        "safety": {
            "read_only": True,
            "semantic_labels_created": False,
            "ground_truth_read": False,
            "rename_actions": False,
            "source_audio_modified": False,
            "windows_are_not_semantic_labels": True,
            "human_approval_required": True,
        },
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cards", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--min-duration", type=float, default=0.08)
    parser.add_argument("--merge-gap", type=float, default=0.15)
    parser.add_argument("--threshold-db", type=float, default=6.0)
    parser.add_argument("--max-segments", type=int, default=64)
    args = parser.parse_args()
    result = build(args.cards, args.out, args.limit, args.workers,
                   args.min_duration, args.merge_gap, args.threshold_db,
                   args.max_segments)
    print(json.dumps({"out": str(args.out), "n_segmented": result["n_segmented"],
                      "n_errors": result["n_errors"], "read_only": True}, indent=2))


if __name__ == "__main__":
    main()
