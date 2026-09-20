#!/usr/bin/env python3
"""
License gate (roadmap R3): fails with a nonzero exit code while any
testing-assets manifest entry carries an unresolved placeholder license
(TODO-vendor-pack, TODO, unknown, empty, ...).

Run this before ANY model-training or benchmark work that touches
testing-assets -- e.g. in CI or manually:

    python3 scripts/check_asset_licenses.py

Blocked work must stay blocked until each stem has a real license string
(e.g. "vendor-pack-2026-09: <vendor> <agreement ref>"). Resolve by editing
the manifest entries, never by weakening this script.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PLACEHOLDER_MARKERS = ("todo", "unknown", "tbd", "placeholder", "")
ASSETS_ROOT = Path(__file__).resolve().parents[2] / "testing-assets"


def main() -> int:
    offenders: list[str] = []
    total_entries = 0
    for manifest in sorted(ASSETS_ROOT.rglob("*.json")):
        try:
            data = json.loads(manifest.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            print(f"ERROR: cannot parse {manifest}: {exc}")
            return 2

        # Walk every dict-looking node; manifests may nest (tracks -> stems).
        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                if "license" in node:
                    total_entries += 1
                    lic = node.get("license")
                    value = (lic or "").strip().lower() if isinstance(lic, str) else ""
                    if any(marker in value for marker in PLACEHOLDER_MARKERS):
                        name = node.get("name") or node.get("filename") or node.get("path") or "?"
                        offenders.append(f"{manifest.relative_to(ASSETS_ROOT)}: {name} -> {lic!r}")
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)

    print(f"Scanned {total_entries} licensed entries under {ASSETS_ROOT}")
    if offenders:
        print(f"\nBLOCKED: {len(offenders)} entries have unresolved license placeholders:\n")
        for line in offenders:
            print(f"  - {line}")
        print("\nResolve each with a real license string (vendor + agreement ref)")
        print("before using these assets for training or benchmarks (roadmap R3).")
        return 1
    print("OK: all entries carry a resolved license.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
