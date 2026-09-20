#!/usr/bin/env python3
"""Inspect or explicitly roll KENN's versioned index back one validated version."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "studio" / "kenn"))

from kenn.retrieval.index_store import (  # noqa: E402
    CURRENT_FILENAME,
    INDEX_DIR,
    PREVIOUS_FILENAME,
    IndexValidationError,
    active_version_id,
    rollback_index,
)


def pointer(name: str) -> str:
    try:
        return (INDEX_DIR / name).read_text(encoding="ascii").strip()
    except OSError:
        return ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Perform the rollback; default is preview only.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    before = {
        "current_pointer": pointer(CURRENT_FILENAME),
        "previous_pointer": pointer(PREVIOUS_FILENAME),
        "active_version": active_version_id(INDEX_DIR),
    }
    report = {"ok": True, "applied": False, "before": before}
    if args.apply:
        try:
            selected = rollback_index(INDEX_DIR)
        except IndexValidationError as exc:
            report.update({"ok": False, "error": str(exc)})
        else:
            report.update(
                {
                    "applied": True,
                    "selected_version": selected,
                    "after": {
                        "current_pointer": pointer(CURRENT_FILENAME),
                        "previous_pointer": pointer(PREVIOUS_FILENAME),
                        "active_version": active_version_id(INDEX_DIR),
                    },
                }
            )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        mode = "applied" if report.get("applied") else "preview"
        print(f"KENN index rollback: {mode}")
        print(f"Current: {before['current_pointer'] or 'missing'}")
        print(f"Previous: {before['previous_pointer'] or 'missing'}")
        if report.get("error"):
            print(f"ERROR: {report['error']}")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
