#!/usr/bin/env python3
"""Validate and optionally apply an SLO JSONL rename plan.

Default mode is a complete read-only validation. Applying requires --apply,
--approve-auto, a matching duplicate guard, and an independent approval-gate
receipt. Suggestions are never applied unless the caller also passes
--include-suggest --approve-suggest. Every source is checked against the
plan's edge signature immediately before mutation, and every move is journaled
in the format consumed by undo_slo_sort.py.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import time


def signature(path):
    st = os.stat(path)
    h = hashlib.sha256()
    h.update(str(st.st_size).encode())
    with open(path, "rb") as f:
        h.update(f.read(65536))
        if st.st_size > 131072:
            f.seek(-65536, os.SEEK_END)
            h.update(f.read(65536))
    return {"size": int(st.st_size), "mtime_ns": int(st.st_mtime_ns),
            "edge_sha256": h.hexdigest()}


def read_plan(path):
    with open(path) as f:
        header = json.loads(next(f))
        rows = [json.loads(line) for line in f if line.strip()]
    if header.get("record_type") != "slo_rename_plan":
        raise ValueError("not an SLO rename plan")
    if int(header.get("n_files", -1)) != len(rows):
        raise ValueError("plan row count does not match its header")
    return header, rows


def read_duplicate_guard(path):
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    if payload.get("record_type") != "slo_rename_duplicate_guard_audit":
        raise ValueError("not an SLO duplicate-guard audit")
    return {os.path.abspath(row["path"]): row for row in payload.get("rows", [])}, payload


def read_approval_gate(path, plan_path):
    """Load the independent approval-gate receipt for exactly one plan."""
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    if payload.get("record_type") != "slo_rename_approval_gate_audit":
        raise ValueError("not an SLO rename approval-gate audit")
    plan_hash = hashlib.sha256(open(plan_path, "rb").read()).hexdigest()
    if payload.get("source_plan_sha256") != plan_hash:
        raise ValueError("approval gate does not match this plan")
    by_path = {}
    for row in payload.get("rows", []):
        path_value = row.get("path")
        if not isinstance(path_value, str):
            raise ValueError("approval gate contains a row without a path")
        path_value = os.path.abspath(path_value)
        if path_value in by_path:
            raise ValueError(f"approval gate contains duplicate path: {path_value}")
        by_path[path_value] = row
    return by_path, payload


def selected(rows, include_suggest):
    allowed = {"auto_rename"}
    if include_suggest:
        allowed.add("suggest")
    return [r for r in rows if r.get("decision", {}).get("action") in allowed
            and r.get("destination")]


def validate(header, rows, include_suggest, duplicate_guard=None):
    problems = []
    root = os.path.abspath(header["source_root"])
    seen_dest = set()
    for row in selected(rows, include_suggest):
        src, dst = os.path.abspath(row["path"]), os.path.abspath(row["destination"])
        if duplicate_guard is not None:
            guard_row = duplicate_guard.get(src)
            if guard_row is None:
                problems.append(f"duplicate guard has no row: {src}")
            elif guard_row.get("flags"):
                problems.append(f"duplicate guard flags {guard_row['flags']}: {src}")
        try:
            inside = os.path.commonpath([root, src]) == root and \
                     os.path.commonpath([root, dst]) == root
        except ValueError:
            inside = False
        if not inside:
            problems.append(f"path outside source root: {src}")
        if src == dst:
            problems.append(f"source equals destination: {src}")
        if src in seen_dest or dst in seen_dest:
            problems.append(f"duplicate planned path: {dst}")
        seen_dest.add(src); seen_dest.add(dst)
        if not os.path.isfile(src):
            problems.append(f"source missing: {src}")
        elif row.get("signature") != signature(src):
            problems.append(f"source changed since plan: {src}")
        if os.path.lexists(dst):
            problems.append(f"destination already exists: {dst}")
    return problems


def validate_approval_gate(rows, approval_gate, include_suggest=False):
    """Require an independent ready status for every selected action row."""
    problems = []
    for row in selected(rows, include_suggest=include_suggest):
        path = os.path.abspath(row["path"])
        gate_row = approval_gate.get(path)
        if gate_row is None:
            problems.append(f"approval gate has no row: {path}")
            continue
        if gate_row.get("status") != "ready_for_explicit_approval":
            reasons = ",".join(gate_row.get("reasons", [])) or "not ready"
            problems.append(f"approval gate blocks {path}: {reasons}")
    return problems


def journal_path(root):
    return os.path.join(root, f".slo_rename_plan_journal_{time.strftime('%Y%m%d_%H%M%S')}_{os.getpid()}.csv")


def apply(rows, include_suggest, journal):
    selected_rows = selected(rows, include_suggest)
    with open(journal, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["version", "operation", "status", "source",
                    "destination", "timestamp"])
        for row in selected_rows:
            src, dst = os.path.abspath(row["path"]), os.path.abspath(row["destination"])
            # Re-check at the last possible moment; a plan is not a lock.
            if not os.path.isfile(src) or os.path.lexists(dst):
                raise RuntimeError(f"filesystem changed during apply: {src}")
            if row.get("signature") != signature(src):
                raise RuntimeError(f"source changed during apply: {src}")
            w.writerow(["1", "move", "PLANNED", src, dst, time.strftime("%Y-%m-%dT%H:%M:%S%z")])
            f.flush(); os.fsync(f.fileno())
            os.rename(src, dst)
            w.writerow(["1", "move", "COMMITTED", src, dst, time.strftime("%Y-%m-%dT%H:%M:%S%z")])
            f.flush(); os.fsync(f.fileno())
    return len(selected_rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("plan")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--approve-auto", action="store_true")
    ap.add_argument("--include-suggest", action="store_true")
    ap.add_argument("--approve-suggest", action="store_true")
    ap.add_argument("--duplicate-guard",
                    help="matching read-only duplicate-guard receipt; required for --apply")
    ap.add_argument("--approval-gate",
                    help="matching read-only approval-gate receipt; required for --apply")
    args = ap.parse_args()
    header, rows = read_plan(args.plan)
    if args.include_suggest and not args.approve_suggest:
        raise SystemExit("REFUSED: --include-suggest requires --approve-suggest")
    if args.apply and not args.approve_auto:
        raise SystemExit("REFUSED: --apply requires --approve-auto")
    if args.include_suggest and not args.approve_auto:
        raise SystemExit("REFUSED: suggestions also require --approve-auto")

    duplicate_guard = None
    if args.duplicate_guard:
        duplicate_guard, guard_payload = read_duplicate_guard(args.duplicate_guard)
        plan_hash = hashlib.sha256(open(args.plan, "rb").read()).hexdigest()
        if guard_payload.get("source_plan_sha256") != plan_hash:
            raise SystemExit("REFUSED: duplicate guard does not match this plan")
    if args.apply and not args.duplicate_guard:
        raise SystemExit("REFUSED: --apply requires --duplicate-guard")

    approval_gate = None
    if args.approval_gate:
        try:
            approval_gate, _ = read_approval_gate(args.approval_gate, args.plan)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise SystemExit(f"REFUSED: invalid approval gate: {exc}")
    if args.apply and not args.approval_gate:
        raise SystemExit("REFUSED: --apply requires --approval-gate")

    chosen = selected(rows, args.include_suggest)
    problems = validate(header, rows, args.include_suggest, duplicate_guard)
    if args.apply and approval_gate is not None:
        problems.extend(validate_approval_gate(rows, approval_gate, args.include_suggest))
    print(f"validated plan: {len(rows)} rows, {len(chosen)} selected")
    if problems:
        print("REFUSED: validation failed:")
        for p in problems[:40]:
            print(f"  - {p}")
        if len(problems) > 40:
            print(f"  ... and {len(problems)-40} more")
        return 2
    if not args.apply:
        print("dry run only; apply additionally requires --approve-auto, "
              "--duplicate-guard, and --approval-gate")
        return 0

    journal = journal_path(os.path.abspath(header["source_root"]))
    try:
        count = apply(rows, args.include_suggest, journal)
    except Exception as exc:
        print(f"REFUSED during apply: {exc}")
        print(f"partial journal: {journal}")
        return 2
    print(f"applied {count} rename(s)")
    print(f"journal: {journal}")
    print(f"undo: python3 undo_slo_sort.py {journal}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
