#!/usr/bin/env python3
"""Read-only: list numbers in approved notes that Live's measured parameter ranges rule out.

    check_notes_against_measurements.py [NOTES_DIR]

Uses the profiles in core/device_units.py plus any evidence files in tooling/data/measured_devices/ (or
KENN_MEASURED_DEVICES_DIR). Prints one line per finding; writes nothing and doesn't touch the contradiction registry
(the index build does that).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

KENN_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(KENN_ROOT / "apps" / "backend" / "src"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    from kenn.retrieval.build_index import NOTES_DIR

    parser.add_argument("notes_dir", nargs="?", type=Path, default=NOTES_DIR, help="folder of markdown notes (the index build's default)")
    args = parser.parse_args()

    from kenn.knowledge.contradictions import parse_note_metadata
    from kenn.knowledge.measured_facts import check_note, load_facts

    facts = load_facts()
    checked = flagged = 0
    for path in sorted(args.notes_dir.glob("*.md")):
        meta = parse_note_metadata(path)
        if not meta or meta["status"].strip().lower() != "approved" or path.name.startswith("measured-"):
            continue
        checked += 1
        for item in check_note(meta["content"], str(meta["title"]), facts):
            flagged += 1
            print(f"{path.name}: {item['device']} {item['parameter']} {item['claimed']:g} {item['unit']} "
                  f"(Live: {item['measured_low']:g} to {item['measured_high']:g}) | {item['sentence'][:100]}")
    print(f"\n{checked} approved notes checked against {len(facts)} measured parameters: {flagged} finding(s)")
    return 1 if flagged else 0


if __name__ == "__main__":
    raise SystemExit(main())
