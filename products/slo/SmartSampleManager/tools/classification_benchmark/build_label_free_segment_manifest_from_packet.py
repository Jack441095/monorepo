#!/usr/bin/env python3
"""Build time-window evidence for every row in a label-free packet.

Unlike the physical-card subset builder, this command takes paths directly
from an immutable evidence packet so temporal coverage can scale to a complete
corpus.  It writes only a derived manifest; source audio is read, never
modified, and windows are not semantic labels.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import importlib.util
import json
from pathlib import Path
from typing import Any


VERSION = "label_free_segment_manifest_from_packet_v1"
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


def _read_packet(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("record_type") != "slo_label_free_evidence_packet":
        raise ValueError("input is not a label-free evidence packet")
    safety = payload.get("safety") or {}
    if (not safety.get("read_only") or safety.get("semantic_labels_created")
            or safety.get("rename_actions") or safety.get("source_audio_modified")):
        raise ValueError("evidence packet is not read-only")
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise ValueError("evidence packet rows are invalid")
    if any(row.get("semantic_label") is not None for row in rows if isinstance(row, dict)):
        raise ValueError("evidence packet contains semantic labels")
    return [row for row in rows if isinstance(row, dict) and isinstance(row.get("path"), str)]


def build(packet: Path, out: Path, limit: int | None = None, workers: int = 1,
          min_duration: float = 0.08, merge_gap: float = 0.15,
          threshold_db: float = 6.0, max_segments: int = 64) -> dict[str, Any]:
    if workers < 1 or (limit is not None and limit < 0):
        raise ValueError("workers must be positive and limit non-negative")
    rows = _read_packet(packet)
    if limit is not None:
        rows = rows[:limit]
    params = {"min_duration": min_duration, "merge_gap": merge_gap,
              "threshold_db": threshold_db, "max_segments": max_segments}
    items = [(str(row["path"]), str(row.get("analysis_path") or row["path"]), params)
             for row in rows]
    if workers == 1:
        results = [_segment(item) for item in items]
    else:
        with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(_segment, items))
    records = [result for result, error in results if result is not None]
    errors = [error for result, error in results if error is not None]
    payload = {
        "record_type": "slo_label_free_segment_manifest",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "source_packet": str(packet.resolve()),
        "n_requested": len(items),
        "n_segmented": len(records),
        "n_errors": len(errors),
        "n_windows": sum(len(record.get("windows") or []) for record in records),
        "records": records,
        "errors": errors,
        "safety": {
            "read_only": True,
            "semantic_labels_created": False,
            "ground_truth_read": False,
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
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--min-duration", type=float, default=0.08)
    parser.add_argument("--merge-gap", type=float, default=0.15)
    parser.add_argument("--threshold-db", type=float, default=6.0)
    parser.add_argument("--max-segments", type=int, default=64)
    args = parser.parse_args()
    result = build(args.packet, args.out, args.limit, args.workers,
                   args.min_duration, args.merge_gap, args.threshold_db,
                   args.max_segments)
    print(json.dumps({"out": str(args.out), "n_segmented": result["n_segmented"],
                      "n_windows": result["n_windows"], "n_errors": result["n_errors"],
                      "read_only": True}, indent=2))


if __name__ == "__main__":
    main()
