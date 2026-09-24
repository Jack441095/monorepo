#!/usr/bin/env python3
"""Build KENN's Ableton Live device coverage map from the installed Live and KENN's code.

For every device Live ships (read from the Live app's own device folders):
  knows   - KENN's knowledge notes cover it (a dedicated note, a draft awaiting owner
            review, or mentions)
  sees    - KENN can read it in a set (generic parameter reads work for any device)
  inserts - KENN may add a new instance (DEVICE_INSERTION_ALLOWLIST), and whether
            the instant rule parser recognises its name
  sets    - parameters KENN can set in real units (measured profiles in
            device_units.py; EQ Eight band gain has its own action)
Writes JSON and a Markdown table. Nothing touches Live.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

KENN_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(KENN_ROOT / "apps" / "backend" / "src"))
NOTES = KENN_ROOT / "apps" / "backend" / "src" / "kenn" / "Training_Data_Notes"
DEFAULT_LIVE = Path("/Applications/Ableton Live 12 Suite.app")
CATEGORIES = ("Instruments", "Audio Effects", "MIDI Effects")


def live_devices(app: Path) -> dict[str, list[str]]:
    resources = app / "Contents" / "App-Resources"
    devices: dict[str, list[str]] = {}
    for category in CATEGORIES:
        names: set[str] = set()
        for base in ("Builtin/Devices", "Core Library/Devices"):
            folder = resources / base / category
            if folder.is_dir():
                for entry in folder.iterdir():
                    name = entry.name.replace(".adv", "").replace(".amxd", "")
                    if not name.startswith(".") and name not in {"Ableton Folder Info", "Legacy"} and not name.startswith("Max "):
                        names.add(name)
        devices[category] = sorted(names)
    return devices


def live_version(app: Path) -> str:
    plist = app / "Contents" / "Info.plist"
    match = re.search(r"<key>CFBundleShortVersionString</key>\s*<string>([^<]+)</string>", plist.read_text(errors="ignore")) if plist.exists() else None
    return match.group(1) if match else "unknown"


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")


def knowledge(device: str, ableton_notes: dict[str, str], device_slugs: set[str]) -> dict[str, Any]:
    """A note whose filename names the device (dedicated or topic note), else mentions by exact name.

    Filename match is on whole slug words (plural allowed), skipping look-alikes
    that are part of another device's name ("Reverb" in "hybrid-reverb").
    """
    words = slug(device).split("-")
    covering = []
    for name in ableton_notes:
        tokens = name[len("ableton-"):-len(".md")].split("-")
        for i in range(len(tokens) - len(words) + 1):
            window = tokens[i:i + len(words)]
            if window[:-1] != words[:-1] or window[-1] not in {words[-1], words[-1] + "s"}:
                continue
            longer = "-".join(tokens[max(0, i - 1):i + len(words)])
            if i > 0 and longer != slug(device) and longer in device_slugs:
                continue
            if i > 0 and tokens[i - 1] == "device":  # "device-delay-compensation" is latency, not Delay
                continue
            covering.append(name)
            break
    pattern = re.compile(rf"(?<![\w-]){re.escape(device)}(?![\w-])")
    mentions = sorted(name for name, text in ableton_notes.items() if pattern.search(text))
    approved = [n for n in covering if not _is_draft(ableton_notes[n])]
    level = "note" if approved else "draft" if covering else ("mentioned" if mentions else "none")
    return {"level": level, "notes": sorted(covering), "mentions": len(mentions)}


def _is_draft(text: str) -> bool:
    """A note awaiting owner review (Status: Draft...); KENN's index leaves these out."""
    status = next((line.split(":", 1)[1].strip() for line in text.splitlines() if line.lower().startswith("status:")), "")
    return status.casefold().startswith("draft")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--live-app", type=Path, default=DEFAULT_LIVE)
    parser.add_argument("--out-json", type=Path, required=True)
    parser.add_argument("--out-md", type=Path, required=True)
    args = parser.parse_args()

    from kenn.core import live_intent
    from kenn.core.device_units import EVIDENCE_BACKED_PROFILES
    from kenn.core.live_action_service import DEVICE_INSERTION_ALLOWLIST

    ableton_notes = {p.name: p.read_text(encoding="utf-8", errors="ignore") for p in sorted(NOTES.glob("ableton-*.md"))}
    parser_names = {canonical for canonical, _ in live_intent._INSERT_DEVICE_ALIASES}
    profiles: dict[str, list[str]] = {}
    for profile in EVIDENCE_BACKED_PROFILES:
        unit = {"db": "dB", "hz": "Hz"}.get(profile.display_unit.casefold(), profile.display_unit)
        profiles.setdefault(profile.device_name, []).append(f"{profile.parameter_name} ({unit})")
    profiles.setdefault("EQ Eight", []).append("band gain (dB, on an existing tuned band)")

    devices = live_devices(args.live_app)
    device_slugs = {slug(n) for names in devices.values() for n in names}
    rows = []
    for category, names in devices.items():
        for name in names:
            rows.append({
                "device": name, "category": category, "knows": knowledge(name, ableton_notes, device_slugs),
                "sees": True,
                "inserts": name in DEVICE_INSERTION_ALLOWLIST,
                "insert_by_name_in_rule_parser": name in parser_names,
                "sets": profiles.get(name, []),
            })
    summary = {
        "live_version": live_version(args.live_app), "devices": len(rows),
        "by_category": {c: len(n) for c, n in devices.items()},
        "knows_note": sum(r["knows"]["level"] == "note" for r in rows),
        "knows_draft_note": sum(r["knows"]["level"] == "draft" for r in rows),
        "knows_mentioned": sum(r["knows"]["level"] == "mentioned" for r in rows),
        "knows_none": sum(r["knows"]["level"] == "none" for r in rows),
        "sees": len(rows), "inserts": sum(r["inserts"] for r in rows),
        "devices_with_settable_parameters": sum(bool(r["sets"]) for r in rows),
        "settable_parameters": sum(len(r["sets"]) for r in rows),
        "ableton_notes": len(ableton_notes),
    }
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps({"summary": summary, "devices": rows}, indent=1) + "\n", encoding="utf-8")

    lines = [f"| Device | Category | Knows | Sees | Inserts | Sets in real units |", "|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: (CATEGORIES.index(r["category"]), r["device"])):
        knows = {"note": "own note", "draft": "own note (draft, owner review)", "mentioned": f"mentioned in {r['knows']['mentions']} notes",
                 "none": "—"}[r["knows"]["level"]]
        inserts = ("yes" + ("" if r["insert_by_name_in_rule_parser"] else " (AI planner only)")) if r["inserts"] else "—"
        lines.append(f"| {r['device']} | {r['category']} | {knows} | yes | {inserts} | {', '.join(r['sets']) or '—'} |")
    args.out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
