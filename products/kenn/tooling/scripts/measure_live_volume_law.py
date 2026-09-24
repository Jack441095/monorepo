#!/usr/bin/env python3
"""Measure Live's mixer volume fader law from Live itself (read-only).

Asks AbletonOSC for Live's own display string (``str_for_value``) at 2,001
evenly spaced raw values of one track's volume fader, in pages small enough
for macOS UDP, and writes the cleaned (raw, dB) table that KENN's
``core/volume_law.py`` loads. Nothing in the set is written or moved. Needs
Live open with KENN's AbletonOSC deployed (deploy_abletonosc.py --apply --reload).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

KENN_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(KENN_ROOT / "apps" / "backend" / "src"))

from kenn.ableton_osc_bridge import AbletonOSCClient  # noqa: E402
from kenn.core import volume_law  # noqa: E402

PAGES = 20
PER_PAGE = 101


def read_table(client: AbletonOSCClient, kind: str, index: int, target: str) -> tuple[list[tuple[float, str]], dict]:
    samples: list[tuple[float, str]] = []
    info: dict = {}
    for page in range(PAGES):
        start, stop = page / PAGES, (page + 1) / PAGES
        result = client.get_display_table(kind, index, target, PER_PAGE, start, stop)
        if not result.get("success"):
            raise SystemExit(f"Live did not answer the {target} read: {result.get('error')}")
        info = {"name": result.get("name"), "min": result.get("min"), "max": result.get("max")}
        samples.extend((float(raw), str(text)) for raw, text in result["points"])
    return sorted(set(samples)), info


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--track", type=int, default=0, help="track index whose fader to read (any track works)")
    parser.add_argument("--out", type=Path, default=volume_law.TABLE_PATH)
    parser.add_argument("--raw-out", type=Path, help="also keep every (raw, display) sample here")
    args = parser.parse_args()

    client = AbletonOSCClient()
    version = client.get_remote_script_version()
    if not version.get("success"):
        raise SystemExit(version.get("error"))
    samples, info = read_table(client, "track", args.track, "volume")
    if info.get("min") != 0.0 or info.get("max") != 1.0:
        raise SystemExit(f"Unexpected fader range {info}; not writing a table.")
    points = volume_law.clean_points(samples)
    zero = [raw for raw, text in samples if volume_law.parse_db(text) == 0.0]
    table = {
        "what": "Ableton Live mixer track volume: raw value -> dB shown by Live (str_for_value), read-only",
        "live_version": _live_version(), "measured_at": date.today().isoformat(),
        "abletonosc": version.get("content_hash"), "samples": len(samples),
        "raw_for_0_db": [min(zero), max(zero)] if zero else None,
        "shown_at_raw_0": next((text for raw, text in samples if raw == 0.0), None),
        "points": [[raw, db] for raw, db in points],
    }
    args.out.write_text(json.dumps(table, indent=1) + "\n", encoding="utf-8")
    if args.raw_out:
        args.raw_out.write_text(json.dumps(samples) + "\n", encoding="utf-8")

    volume_law.law.cache_clear()
    old = {db: round(10 ** (db / 20.0), 3) for db in (-12.0, -6.0, -3.0, 0.0)}
    print(f"{len(samples)} samples -> {len(points)} points; 0 dB at raw {table['raw_for_0_db']}; "
          f"top {points[-1][1]:+.1f} dB; raw 0 shows {table['shown_at_raw_0']}")
    for db, before in old.items():
        print(f"  {db:+5.1f} dB: Live raw {volume_law.db_to_raw(db):.4f} (KENN used to send {before})")
    print(f"Wrote {args.out}")
    return 0


def _live_version() -> str:
    plist = Path("/Applications/Ableton Live 12 Suite.app/Contents/Info.plist")
    try:
        text = plist.read_text(errors="ignore")
        return text.split("<key>CFBundleShortVersionString</key>")[1].split("<string>")[1].split("</string>")[0]
    except (OSError, IndexError):
        return "unknown"


if __name__ == "__main__":
    raise SystemExit(main())
