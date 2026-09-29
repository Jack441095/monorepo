#!/usr/bin/env python3
"""Measure every device in the open Live set, once per device type (read-only).

    measure_all_devices.py [--out-dir DIR] [--only "EQ Eight,Compressor"] [--force] [--samples N]

Put one of each device you want KENN to learn on any track, return or the master (Live's browser: select a folder and
drag it in, or use a "device zoo" set), open the set with KENN's AbletonOSC running and the KENN companion stopped (the
AbletonOSC reply port has to be free), then run this. Each device's parameters are read through Live's own display
strings, the same way measure_device_parameters.py does one device, and written to ``<device>.json`` in the evidence
folder. A device that already has a file is skipped unless --force. Nothing in the set is changed.

Devices inside racks are not measured (the parameter reads address top-level devices); drag them out onto a track first.
Measure devices under their default names: KENN matches profiles by the name Live reports.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any, Callable

KENN_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(KENN_ROOT / "apps" / "backend" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
DEFAULT_OUT = KENN_ROOT / "tooling" / "data" / "measured_devices"


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")


def devices_in_set(client: Any) -> list[dict[str, Any]]:
    """Every top-level device on every track, return and the master: where to read it and what Live calls it."""
    found: list[dict[str, Any]] = []

    def read(kind: str, index: int, label: str) -> None:
        tree = client.get_device_tree(kind, index)
        for position, node in enumerate(tree.get("devices") or [] if tree.get("success") else []):
            found.append({"kind": kind, "index": index, "device_index": position, "on": label,
                          "name": str(node.get("name") or ""), "class_name": str(node.get("class_name") or ""),
                          "can_have_chains": bool(node.get("can_have_chains"))})

    state = client.query_session_state()
    for track in state.get("tracks") or []:
        read("track", int(track["index"]), str(track.get("name") or track["index"]))
    for item in state.get("return_tracks") or client.get_return_tracks() or []:
        read("return", int(item["index"]), str(item.get("name") or item["index"]))
    read("master", -1, "Master")
    return found


def sweep(client: Any, out_dir: Path, *, measure: Callable[..., dict[str, Any]], only: set[str] | None = None,
          force: bool = False, samples: int = 400, log: Callable[[str], None] = print) -> dict[str, list[str]]:
    summary: dict[str, list[str]] = {"measured": [], "skipped": [], "failed": [], "racks": []}
    seen: set[str] = set()
    out_dir.mkdir(parents=True, exist_ok=True)
    for device in devices_in_set(client):
        key = (device["class_name"] or device["name"]).casefold()
        label = f"{device['name']} on {device['on']}"
        if device["can_have_chains"]:
            summary["racks"].append(label)   # a rack's own parameters are macros; what's inside isn't reachable this way
        if only and device["name"].casefold() not in only:
            continue
        if key in seen:
            summary["skipped"].append(f"{label} (already measured this run)")
            continue
        seen.add(key)
        target = out_dir / f"{slug(device['name'])}.json"
        if target.exists() and not force:
            summary["skipped"].append(f"{label} (has evidence; use --force to redo)")
            continue
        try:
            result = measure(client, device["kind"], device["index"], device["device_index"], samples)
        except SystemExit as error:
            summary["failed"].append(f"{label}: {error}")
            continue
        except Exception as error:   # one bad device shouldn't end the sweep
            summary["failed"].append(f"{label}: {type(error).__name__}: {error}")
            continue
        result.update({"measured_at": date.today().isoformat(), "class_name": device["class_name"]})
        target.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
        summary["measured"].append(f"{device['name']} ({len(result['parameters'])} parameters)")
        log(f"measured {device['name']}: {len(result['parameters'])} parameters")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--only", help="comma-separated device names")
    parser.add_argument("--force", action="store_true", help="measure again even if a file exists")
    parser.add_argument("--samples", type=int, default=400)
    args = parser.parse_args()

    from kenn.ableton_osc_bridge import AbletonOSCClient
    from measure_device_parameters import measure

    only = {name.strip().casefold() for name in args.only.split(",") if name.strip()} if args.only else None
    summary = sweep(AbletonOSCClient(), args.out_dir, measure=measure, only=only, force=args.force, samples=args.samples)
    for key in ("measured", "skipped", "failed", "racks"):
        if summary[key]:
            print(f"\n{key} ({len(summary[key])}):\n  " + "\n  ".join(summary[key]))
    if not any(summary.values()):
        print("Found no devices in the open set. Is Live connected?", file=sys.stderr)
        return 1
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
