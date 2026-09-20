#!/usr/bin/env python3
"""Build a blind, resumable label-tool manifest from review collections.

The review planner and the by-ear labeler intentionally use different
schemas. This bridge selects reviewable actions, assigns deterministic IDs,
and hides the model's predicted class by default so a human label is not
biased toward the prediction. It writes paths and queue provenance only; it
never creates labels, changes the review plan, or touches audio.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Iterable


VERSION = "label_manifest_from_review_v1"
VALID_ACTIONS = {"auto_rename", "suggest", "review", "never_act"}


def _collection(path: str, source_root: str | os.PathLike[str] | None) -> str:
    if source_root is None:
        return os.path.dirname(path)
    root = os.path.abspath(os.fspath(source_root))
    try:
        relative = os.path.relpath(path, root)
    except ValueError:
        return os.path.dirname(path)
    if relative == os.pardir or relative.startswith(os.pardir + os.sep):
        return os.path.dirname(path)
    return relative.split(os.sep)[0]


def build_manifest(payload: dict[str, Any], actions: Iterable[str],
                   limit: int = 0, show_prediction: bool = False,
                   source_root: str | os.PathLike[str] | None = None,
                   balanced: bool = False) -> list[dict[str, Any]]:
    if payload.get("record_type") != "slo_review_collections":
        raise ValueError("collections input must be slo_review_collections")
    selected = []
    for action in actions:
        if action not in VALID_ACTIONS:
            raise ValueError(f"unknown review action: {action}")
        selected.extend(payload.get("collections", {}).get(action, []))

    if balanced and source_root is None:
        raise ValueError("balanced selection requires --source-root")
    ordered = sorted(selected, key=lambda value: os.path.abspath(str(value.get("path", ""))))
    if balanced:
        by_collection: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
        for item in ordered:
            path = item.get("path")
            if isinstance(path, str):
                by_collection[_collection(os.path.abspath(path), source_root)].append(item)
        ordered = []
        queues = [by_collection[key] for key in sorted(by_collection)]
        while any(queues) and (not limit or len(ordered) < limit):
            for queue in queues:
                if queue and (not limit or len(ordered) < limit):
                    ordered.append(queue.popleft())

    rows = []
    seen: set[str] = set()
    for item in ordered:
        path = item.get("path")
        if not isinstance(path, str) or not os.path.isabs(path):
            raise ValueError("review item path must be absolute")
        path = os.path.abspath(path)
        if path in seen:
            raise ValueError(f"duplicate path in review collections: {path}")
        seen.add(path)
        row = {"id": len(rows), "path": path, "hint": "",
               "collection": _collection(path, source_root)}
        if show_prediction:
            row["hint"] = str(item.get("predicted_class") or "")
        rows.append(row)
        if limit and len(rows) >= limit:
            break
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collections", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--actions", default="suggest,review",
                        help="comma-separated queue actions; default: suggest,review")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--source-root", type=Path,
                        help="root used to identify top-level collections")
    parser.add_argument("--balanced", action="store_true",
                        help="select round-robin across collections")
    parser.add_argument("--show-prediction", action="store_true",
                        help="show predicted class as a non-authoritative hint")
    args = parser.parse_args()
    if args.limit < 0:
        raise SystemExit("--limit must be non-negative")
    payload = json.loads(args.collections.read_text(encoding="utf-8"))
    actions = [value.strip() for value in args.actions.split(",") if value.strip()]
    if not actions:
        raise SystemExit("--actions must contain at least one action")
    manifest = build_manifest(payload, actions, args.limit, args.show_prediction,
                              args.source_root, args.balanced)
    args.out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "record_type": "slo_blind_label_manifest",
        "method_version": VERSION,
        "n_items": len(manifest),
        "actions": actions,
        "show_prediction": args.show_prediction,
        "balanced": args.balanced,
        "n_collections": len({row["collection"] for row in manifest}),
        "read_only": True,
    }, indent=2))


if __name__ == "__main__":
    main()
