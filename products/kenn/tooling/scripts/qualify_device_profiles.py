#!/usr/bin/env python3
"""Qualify candidate device-unit profiles on real Live: write, read Live's display back, restore exactly.

    qualify_device_profiles.py --measurement compressor.json --track 3 --device 0 --output evidence.json

A measurement from measure_device_parameters.py gives each continuous control's mapping (linear, log or a measured
table). This turns the ones KENN needs into DeviceUnitProfile candidates (tables thinned to landmark values), then for
each target value: converts it to a raw value with the candidate, writes it, reads Live's own display string back,
and checks it within tolerance. Targets between landmarks test the interpolation, not just the stored points. Every
control goes back to its exact starting raw value afterwards, checked by readback.

Stop the KENN companion first (it holds AbletonOSC's reply port). Changes one device on the open set and restores
it; run it on the demo set.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

KENN_ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(KENN_ROOT / "apps" / "backend" / "src"), str(KENN_ROOT / "tooling" / "scripts")]

from kenn.core import device_units  # noqa: E402
from kenn.core.device_units import DeviceUnitProfile  # noqa: E402
from measure_device_parameters import parse_display  # noqa: E402

# Landmarks people ask for; the table keeps the measured point nearest each one.
LANDMARKS = {
    "ratio": (1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0, 8.0, 10.0, 15.0, 20.0, 30.0, 50.0, 100.0),
    "ms": (0.01, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 50.0, 75.0, 100.0, 150.0, 200.0, 300.0, 500.0, 750.0,
           1000.0, 1500.0, 2000.0, 3000.0),
}
# Values people ask for, including ones between landmarks.
TARGETS = {
    ("Compressor", "Ratio"): (2.0, 3.0, 4.0, 7.0, 10.0),
    ("Compressor", "Attack"): (0.1, 1.0, 5.0, 10.0, 30.0, 100.0),
    ("Compressor", "Release"): (10.0, 50.0, 100.0, 250.0, 500.0, 1000.0),
}
RELATIVE_TOLERANCE = 0.03  # Live shows 3 significant figures; 3% is well inside one display step at these values


def candidate(device: str, parameter: dict) -> DeviceUnitProfile | None:
    unit, mapping = parameter.get("unit"), parameter.get("mapping")
    if mapping == "log":
        return DeviceUnitProfile(device, parameter["name"], unit, parameter["raw_min"], parameter["raw_max"],
                                 parameter["display_min"], parameter["display_max"], mapping="log")
    if mapping == "table" and unit in LANDMARKS:
        points = sorted((float(raw), float(parse_display(text)[0]) if isinstance(text, str) else float(text))
                        for raw, text in parameter["points"])
        kept: list[tuple[float, float]] = []
        for mark in LANDMARKS[unit]:
            if not points[0][1] <= mark <= points[-1][1]:
                continue
            nearest = min(points, key=lambda p: abs(p[1] - mark))
            if not kept or nearest[1] > kept[-1][1]:
                kept.append(nearest)
        for end in (points[0], points[-1]):
            if end not in kept:
                kept.append(end)
        kept.sort(key=lambda p: p[1])
        return DeviceUnitProfile(device, parameter["name"], unit, kept[0][0], kept[-1][0], kept[0][1], kept[-1][1],
                                 raw_values=tuple(p[0] for p in kept), display_values=tuple(p[1] for p in kept),
                                 mapping="table")
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--measurement", type=Path, required=True)
    parser.add_argument("--track", type=int, required=True)
    parser.add_argument("--device", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    from kenn.ableton_osc_bridge import AbletonOSCClient

    measurement = json.loads(args.measurement.read_text())
    device = measurement["device"]
    wanted = {name for (dev, name) in TARGETS if dev == device}
    profiles = {p["name"]: candidate(device, p) for p in measurement["parameters"] if p.get("name") in wanted}
    profiles = {name: profile for name, profile in profiles.items() if profile is not None}
    # Use the candidates for conversion, exactly as KENN would once they're promoted.
    device_units.EVIDENCE_BACKED_PROFILES = tuple(profiles.values()) + device_units.EVIDENCE_BACKED_PROFILES

    client = AbletonOSCClient()
    info = client.get_device_parameters(args.track, args.device)
    if not info.get("success") or info.get("device_name") != device:
        print(f"expected {device} at track {args.track} device {args.device}; Live has {info.get('device_name')}")
        return 2
    by_name = {p["name"]: p for p in info["parameters"]}
    rows, all_ok = [], True
    for name, profile in profiles.items():
        index, original = int(by_name[name]["index"]), float(by_name[name]["value"])
        checks = []
        for target in TARGETS[(device, name)]:
            raw, error = device_units.display_to_raw(device_name=device, parameter_name=name, value=target,
                                                     unit=profile.display_unit)
            if error:
                checks.append({"target": target, "error": error}); all_ok = False; continue
            client.set_device_parameter(args.track, args.device, index, raw)
            time.sleep(0.25)
            shown = client.get_device_parameter_value_string(args.track, args.device, index)
            parsed = parse_display(str(shown.get("value_string"))) if shown.get("success") else None
            ok = parsed is not None and abs(parsed[0] - target) <= RELATIVE_TOLERANCE * abs(target)
            all_ok &= ok
            checks.append({"target": target, "raw": raw, "live_shows": shown.get("value_string"), "ok": ok})
            print(f"{'PASS' if ok else 'FAIL'} {device} {name} {target:g} -> raw {raw:.4f} -> Live shows {shown.get('value_string')}")
        client.set_device_parameter(args.track, args.device, index, original)
        time.sleep(0.25)
        now = next(p for p in client.get_device_parameters(args.track, args.device)["parameters"] if p["name"] == name)
        restored = abs(float(now["value"]) - original) <= 1e-6
        all_ok &= restored
        print(f"{'PASS' if restored else 'FAIL'} {device} {name} restored to raw {original:g} (now {now['value']})")
        rows.append({"parameter": name, "profile": asdict(profile), "checks": checks, "original_raw": original,
                     "restored_exactly": restored})
    args.output.write_text(json.dumps({"schema": "kenn.device_profile_qualification.v1",
                                       "generated_at": datetime.now(timezone.utc).isoformat(), "device": device,
                                       "track_index": args.track, "device_index": args.device, "qualified": all_ok,
                                       "parameters": rows}, indent=1) + "\n")
    print(f"\n{device}: {'qualified' if all_ok else 'NOT qualified'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
