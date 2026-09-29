#!/usr/bin/env python3
"""Candidate device profiles from measured evidence, and a coverage report of what is and isn't mapped.

    build_device_profiles.py [--evidence-dir DIR] [--out-dir DIR] [--live-app PATH]

For each device JSON that measure_device_parameters.py / measure_all_devices.py wrote, this writes
``<device>.json`` into the candidates folder with:

- ``profiles``: every continuous parameter Live showed in a unit KENN converts (dB, Hz, ms, %, ratio), as a linear,
  logarithmic or measured-table mapping. **No qualification block yet**: core/device_units.py ignores these until
  qualify_device_profiles.py has set, read back and restored each one on real Live;
- ``choosers``: switches and choosers, with the option Live shows for each raw value;
- ``unmapped``: parameters that can't be mapped, with the reason (Live showed no unit, or no readable number).

The coverage report says how many of Live's devices have been measured at all, and how many parameters are mapped,
qualified, chooser or unmapped. Nothing here touches Live.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

KENN_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(KENN_ROOT / "apps" / "backend" / "src"))
DEFAULT_EVIDENCE = KENN_ROOT / "tooling" / "data" / "measured_devices"
DEFAULT_OUT = KENN_ROOT / "tooling" / "data" / "device_profile_candidates"
_CONVERTIBLE = {"db", "hz", "ms", "%", "ratio"}
MAX_TABLE_POINTS = 64


def _thin(points: list[list[float]]) -> list[list[float]]:
    """At most MAX_TABLE_POINTS, always keeping the two ends."""
    if len(points) <= MAX_TABLE_POINTS:
        return points
    step = (len(points) - 1) / (MAX_TABLE_POINTS - 1)
    return [points[round(i * step)] for i in range(MAX_TABLE_POINTS)]


def classify_parameter(entry: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """("profile" | "chooser" | "unmapped", data) for one measured parameter."""
    name = str(entry.get("name") or "").strip()
    if not name or entry.get("error"):
        return "unmapped", {"parameter": name, "reason": f"Live gave no readable table ({entry.get('error') or 'no name'})"}
    if entry.get("quantized"):
        options = entry.get("options")
        rows = [{"raw": item[0], "label": str(item[1]).strip()} for item in options or []
                if isinstance(item, (list, tuple)) and len(item) > 1 and str(item[1]).strip()] if isinstance(options, list) else []
        if not rows:
            return "unmapped", {"parameter": name, "reason": "a chooser with no readable options"}
        return "chooser", {"parameter": name, "options": rows}
    mapping, unit = entry.get("mapping"), str(entry.get("unit") or "")
    if mapping == "unparsed":
        return "unmapped", {"parameter": name, "reason": f"Live's display isn't a number: {', '.join(map(str, entry.get('examples') or []))}"}
    if unit not in _CONVERTIBLE:
        return "unmapped", {"parameter": name, "reason": "Live shows a bare number with no unit, so KENN sets it by raw value only"}
    try:
        base = {"parameter": name, "unit": unit, "raw_min": float(entry["raw_min"]), "raw_max": float(entry["raw_max"]),
                "display_min": float(entry["display_min"]), "display_max": float(entry["display_max"])}
    except (KeyError, TypeError, ValueError):
        return "unmapped", {"parameter": name, "reason": "the evidence has no usable range"}
    if base["raw_max"] <= base["raw_min"]:
        return "unmapped", {"parameter": name, "reason": "the raw range is empty"}
    if mapping in {"linear", "log"}:
        if mapping == "log" and base["display_min"] <= 0:
            return "unmapped", {"parameter": name, "reason": "a logarithmic display that reaches zero"}
        return "profile", {**base, "mapping": mapping}
    if mapping in {"table", "table_descending"}:
        points = _thin([[float(raw), float(shown)] for raw, shown in entry.get("points") or []])
        if len(points) < 3:
            return "unmapped", {"parameter": name, "reason": "fewer than three measured points"}
        return "profile", {**base, "mapping": "table", "raw_values": [p[0] for p in points], "display_values": [p[1] for p in points]}
    return "unmapped", {"parameter": name, "reason": f"unknown mapping {mapping!r}"}


def build(evidence: dict[str, Any]) -> dict[str, Any]:
    device, measured_at = str(evidence.get("device") or "").strip(), str(evidence.get("measured_at") or "").strip()
    if not device or not measured_at:
        raise ValueError("evidence needs a device name and a measured_at date")
    result: dict[str, Any] = {"schema": "kenn.device_profile_candidates.v1", "device": device, "measured_at": measured_at,
                              "profiles": [], "choosers": [], "unmapped": []}
    for entry in evidence.get("parameters") or []:
        kind, data = classify_parameter(entry)
        result[{"profile": "profiles", "chooser": "choosers", "unmapped": "unmapped"}[kind]].append(data)
    return result


def qualified_parameters(device: str) -> set[str]:
    from kenn.core import device_units

    return {p.parameter_name.casefold() for p in device_units.all_profiles() if p.device_name.casefold() == device.casefold()}


def coverage(candidates: list[dict[str, Any]], installed: list[str] | None) -> dict[str, Any]:
    measured = {c["device"] for c in candidates}
    rows = []
    for c in candidates:
        done = qualified_parameters(c["device"])
        rows.append({"device": c["device"], "profiles": len(c["profiles"]),
                     "qualified": sum(1 for p in c["profiles"] if p["parameter"].casefold() in done),
                     "choosers": len(c["choosers"]), "unmapped": len(c["unmapped"])})
    report: dict[str, Any] = {"devices_measured": len(measured), "parameters": {
        key: sum(row[key] for row in rows) for key in ("profiles", "qualified", "choosers", "unmapped")}, "rows": rows}
    if installed is not None:
        report["devices_installed"] = len(installed)
        report["not_measured"] = sorted(set(installed) - measured)
    return report


def render(report: dict[str, Any]) -> str:
    lines = ["| Device | Candidate profiles | Qualified | Choosers | Unmapped |", "|---|---|---|---|---|"]
    lines += [f"| {r['device']} | {r['profiles']} | {r['qualified']} | {r['choosers']} | {r['unmapped']} |" for r in report["rows"]]
    total = report["parameters"]
    summary = (f"\n{report['devices_measured']} devices measured"
               + (f" of {report['devices_installed']} installed" if "devices_installed" in report else "")
               + f"; parameters: {total['profiles']} candidate profiles ({total['qualified']} already qualified), "
                 f"{total['choosers']} choosers, {total['unmapped']} unmapped.")
    missing = report.get("not_measured")
    return "\n".join(lines) + summary + (f"\nNot measured yet ({len(missing)}): {', '.join(missing)}" if missing else "")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--evidence-dir", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--live-app", type=Path, help="Live .app, to list installed devices that have no evidence yet")
    args = parser.parse_args()

    files = sorted(args.evidence_dir.glob("*.json")) if args.evidence_dir.is_dir() else []
    if not files:
        print(f"No evidence files in {args.evidence_dir}. Run measure_all_devices.py with Live open first.", file=sys.stderr)
        return 1
    args.out_dir.mkdir(parents=True, exist_ok=True)
    candidates = []
    for path in files:
        try:
            candidate = build(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError) as error:
            print(f"skipped {path.name}: {error}", file=sys.stderr)
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", candidate["device"].casefold()).strip("-")
        (args.out_dir / f"{slug}.json").write_text(json.dumps(candidate, indent=1) + "\n", encoding="utf-8")
        candidates.append(candidate)
    installed = None
    if args.live_app:
        from kenn.core.installed_devices import builtin_devices

        installed = builtin_devices(args.live_app)
    print(render(coverage(candidates, installed)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
