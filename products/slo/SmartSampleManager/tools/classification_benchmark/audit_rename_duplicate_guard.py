#!/usr/bin/env python3
"""Audit a rename plan against exact and acoustic duplicate inventories.

The output is an independent safety receipt. It never edits the plan and never
changes the decision field. Exact aliases are unsafe to act on automatically;
near-duplicate membership is a review flag only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any


VERSION = "rename_duplicate_guard_v1"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if line.strip():
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"invalid JSON at {path}:{line_number}") from exc
                if not isinstance(value, dict):
                    raise ValueError(f"expected object at {path}:{line_number}")
                rows.append(value)
    return rows


def _path(value: Any) -> str | None:
    return os.path.abspath(value) if isinstance(value, str) else None


def _exact_map(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Normalise canonical-group and complete-hash identity receipts."""
    record_type = payload.get("record_type")
    if record_type in {None, "slo_canonical_duplicate_groups"} and "groups" in payload:
        groups = payload.get("groups", [])
    elif record_type == "slo_content_identity_manifest":
        # The identity manifest has already hashed every byte.  Convert its
        # duplicate-content map into the same canonical/alias view used by
        # the guard, preserving deterministic path ordering.
        groups = []
        for digest, members in payload.get("duplicate_content_groups", {}).items():
            ordered = sorted(_path(value) for value in members)
            if not ordered or any(value is None for value in ordered):
                raise ValueError(f"identity receipt has invalid group {digest}")
            groups.append({"canonical_path": ordered[0], "alias_paths": ordered[1:]})
    else:
        raise ValueError("exact receipt has an unexpected record type")

    exact_map: dict[str, dict[str, Any]] = {}
    for group_index, group in enumerate(groups):
        canonical = _path(group.get("canonical_path"))
        aliases = [_path(value) for value in group.get("alias_paths", [])]
        if not canonical or any(value is None for value in aliases):
            raise ValueError("exact duplicate receipt contains an invalid path")
        exact_map[canonical] = {"group_index": group_index, "role": "canonical", "canonical_path": canonical}
        for alias in aliases:
            if alias in exact_map:
                raise ValueError(f"path appears in multiple exact groups: {alias}")
            exact_map[alias] = {"group_index": group_index, "role": "alias", "canonical_path": canonical}
    return exact_map


def audit(plan_path: Path, exact_path: Path, near_path: Path) -> dict[str, Any]:
    plan_rows = _read_jsonl(plan_path)
    if not plan_rows or plan_rows[0].get("record_type") != "slo_rename_plan":
        raise ValueError("plan must begin with slo_rename_plan header")
    exact = json.loads(exact_path.read_text(encoding="utf-8"))
    near = json.loads(near_path.read_text(encoding="utf-8"))
    exact_map = _exact_map(exact)
    near_map: dict[str, list[int]] = {}
    for group_index, group in enumerate(near.get("groups", [])):
        for value in group.get("member_paths", []):
            path = _path(value)
            if path:
                near_map.setdefault(path, []).append(group_index)

    rows = []
    action_counts = Counter()
    flags = Counter()
    seen: set[str] = set()
    for row in plan_rows[1:]:
        path = _path(row.get("path"))
        if not path or path in seen:
            raise ValueError("plan contains a missing or duplicate path")
        seen.add(path)
        decision = row.get("decision")
        if not isinstance(decision, dict):
            raise ValueError(f"missing decision for {path}")
        action = decision.get("action")
        action_counts[action] += 1
        exact_info = exact_map.get(path)
        near_groups = near_map.get(path, [])
        row_flags = []
        if exact_info:
            row_flags.append("exact_duplicate_alias" if exact_info["role"] == "alias" else "exact_duplicate_canonical")
        if near_groups:
            row_flags.append("acoustic_near_duplicate")
        for flag in row_flags:
            flags[flag] += 1
        if action == "auto_rename" and exact_info:
            flags["auto_exact_duplicate_violation"] += 1
        rows.append({
            "path": path,
            "plan_action": action,
            "flags": row_flags,
            "exact_group": exact_info,
            "near_duplicate_group_indices": near_groups,
            "safe_to_auto_act": not exact_info and not near_groups and action == "auto_rename",
        })
    return {
        "record_type": "slo_rename_duplicate_guard_audit",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "source_plan": str(plan_path.resolve()),
        "source_plan_sha256": hashlib.sha256(plan_path.read_bytes()).hexdigest(),
        "source_exact_receipt": str(exact_path.resolve()),
        "source_exact_record_type": exact.get("record_type"),
        "source_near_receipt": str(near_path.resolve()),
        "n_plan_rows": len(rows),
        "plan_action_counts": dict(action_counts),
        "flag_counts": dict(flags),
        "rows": rows,
        "safety": {
            "read_only": True,
            "rename_plan_modified": False,
            "source_audio_modified": False,
            "auto_action_enabled": False,
            "exact_aliases_are_not_safe_to_auto_act": True,
            "acoustic_similarity_is_not_duplicate_proof": True,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--exact", type=Path, required=True)
    parser.add_argument("--near", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.plan, args.exact, args.near)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"n_plan_rows": result["n_plan_rows"], "plan_action_counts": result["plan_action_counts"], "flag_counts": result["flag_counts"]}, indent=2))


if __name__ == "__main__":
    main()
