#!/usr/bin/env python3
"""Dry-run or explicitly apply an undo for a SLO move journal.

The normal mode is a read-only validation/dry run. Applying requires the
--apply flag and refuses to guess: the journal must contain committed move
rows, every destination must still exist, and every original source must be
absent. Copy-mode journals are intentionally not undoable because the source
was never removed and deleting a copy would be an irreversible policy choice.
"""
from __future__ import annotations

import argparse
import csv
import os
import shutil
import sys


def read_committed(path: str):
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows or set(rows[0]) < {"operation", "status", "source", "destination"}:
        raise ValueError("journal has no supported header")
    committed = [r for r in rows
                 if r.get("status") == "COMMITTED" and r.get("operation") == "move"]
    copy_commits = [r for r in rows
                    if r.get("status") == "COMMITTED" and r.get("operation") == "copy"]
    if copy_commits and not committed:
        raise ValueError("copy-mode journal is not undoable")
    if copy_commits:
        raise ValueError("journal mixes copy and move rows; refusing to guess")
    return committed


def validate(rows):
    problems = []
    for r in rows:
        src, dst = r["source"], r["destination"]
        if not src or not dst:
            problems.append("empty source/destination")
            continue
        if os.path.exists(src):
            problems.append(f"original already exists: {src}")
        if not os.path.isfile(dst):
            problems.append(f"destination missing: {dst}")
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("journal")
    ap.add_argument("--apply", action="store_true",
                    help="perform the validated reverse moves")
    args = ap.parse_args(argv)
    try:
        rows = read_committed(args.journal)
        if not rows:
            raise ValueError("journal contains no committed move rows")
        problems = validate(rows)
    except (OSError, ValueError, KeyError) as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2
    if problems:
        print("REFUSED: journal state is not exactly reversible:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 2

    print(f"validated {len(rows)} committed move(s) from {args.journal}")
    for r in reversed(rows):
        print(f"  {r['destination']} -> {r['source']}")
    if not args.apply:
        print("dry run only; pass --apply to perform these moves")
        return 0

    # Re-check immediately before each mutation. If anything changed after the
    # initial validation, stop instead of overwriting or mixing user changes.
    for r in reversed(rows):
        src, dst = r["source"], r["destination"]
        if os.path.exists(src) or not os.path.isfile(dst):
            print(f"REFUSED during apply: state changed for {dst}", file=sys.stderr)
            return 2
        os.makedirs(os.path.dirname(src), exist_ok=True)
        shutil.move(dst, src)
    print("undo applied successfully")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
