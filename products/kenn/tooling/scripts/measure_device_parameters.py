#!/usr/bin/env python3
"""Measure every parameter of one Live device from Live's own display strings (read-only).

For D1 device qualification. For each parameter of the chosen device:

- continuous controls: Live's display string (``str_for_value``) at evenly spaced
  raw values, parsed into a number and unit (dB, Hz, ms, %, ratio or plain), then
  classified as ``linear``, ``log`` or a measured ``table`` mapping;
- quantized controls (switches, choosers): each option's label.

Writes an evidence JSON and a list of *candidate* ``DeviceUnitProfile`` lines. A
candidate becomes a real profile in ``core/device_units.py`` only after a
write -> readback -> exact-undo test on real Live. Nothing in the set is changed.

Needs Live open with KENN's AbletonOSC (the ``/live/kenn/get/display_table`` read)
and the AbletonOSC reply port free (stop the KENN companion while measuring).
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

KENN_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(KENN_ROOT / "apps" / "backend" / "src"))

_DISPLAY = re.compile(r"^\s*(?P<value>[-+]?(?:inf|\d+(?:\.\d+)?))\s*(?P<unit>[a-zA-Z%]+|:\s*1)?\s*$", re.I)
_UNIT_SCALE = {"khz": ("hz", 1000.0), "hz": ("hz", 1.0), "db": ("db", 1.0), "ms": ("ms", 1.0), "s": ("ms", 1000.0),
               "%": ("%", 1.0), ":1": ("ratio", 1.0), "": ("value", 1.0)}


def parse_display(text: str) -> tuple[float, str] | None:
    """Live's display ("-12.0 dB", "1.01 kHz", "4.00 : 1", "30.0 ms", "0.71") as (number, unit)."""
    match = _DISPLAY.match(str(text))
    if not match:
        return None
    unit = re.sub(r"\s+", "", (match.group("unit") or "")).casefold()
    if unit not in _UNIT_SCALE:
        return None
    canonical, scale = _UNIT_SCALE[unit]
    raw = match.group("value").casefold()
    value = (-math.inf if raw.startswith("-") else math.inf) if raw.lstrip("+-") == "inf" else float(raw) * scale
    return value, canonical


def _r_squared(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    mean_x, mean_y = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    syy = sum((y - mean_y) ** 2 for y in ys)
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    if sxx == 0 or syy == 0:
        return 0.0
    return (sxy * sxy) / (sxx * syy)


def classify(samples: list[tuple[float, str]]) -> dict[str, Any]:
    """Mapping for one continuous parameter from (raw, display) samples."""
    parsed = [(raw, parse_display(text)) for raw, text in samples]
    finite = [(raw, value, unit) for raw, got in parsed if got for value, unit in [got] if math.isfinite(value)]
    units = {unit for _raw, _value, unit in finite}
    if len(finite) < 3 or len(units) != 1:
        return {"mapping": "unparsed", "units": sorted(units), "examples": [text for _raw, text in samples[:3]]}
    unit = units.pop()
    raws = [raw for raw, _value, _unit in finite]
    values = [value for _raw, value, _unit in finite]
    result: dict[str, Any] = {"unit": unit, "raw_min": raws[0], "raw_max": raws[-1],
                              "display_min": values[0], "display_max": values[-1]}
    if _r_squared(raws, values) >= 0.9995:
        return {**result, "mapping": "linear"}
    if all(v > 0 for v in values) and _r_squared(raws, [math.log(v) for v in values]) >= 0.9995:
        return {**result, "mapping": "log"}
    # Otherwise keep a measured table: one point per distinct display value, both axes ascending.
    points: list[tuple[float, float]] = []
    for raw, value in zip(raws, values):
        if not points or (value > points[-1][1] and raw > points[-1][0]):
            points.append((round(raw, 6), value))
    descending = values[0] > values[-1]
    return {**result, "mapping": "table" if not descending else "table_descending", "points": points}


def candidate_profile(device: str, name: str, info: dict[str, Any]) -> str | None:
    if info.get("mapping") not in {"linear", "log"} or info.get("unit") == "value":
        return None
    unit = {"hz": "hz", "db": "db", "ms": "ms", "%": "%", "ratio": "ratio"}.get(info["unit"], info["unit"])
    extra = ', mapping="log"' if info["mapping"] == "log" else ""
    return (f'DeviceUnitProfile("{device}", "{name}", "{unit}", {info["raw_min"]:g}, {info["raw_max"]:g}, '
            f'{info["display_min"]:g}, {info["display_max"]:g}{extra}),')


def measure(client: Any, kind: str, index: int, device_index: int, samples: int) -> dict[str, Any]:
    listing = client.get_bus_device_parameters(kind, index, device_index)
    if not listing.get("success"):
        raise SystemExit(f"Live did not list the device's parameters: {listing.get('error')}")
    device = str(listing.get("device_name") or "")
    parameters = []
    for parameter in listing.get("parameters", []):
        position, name = int(parameter["index"]), str(parameter["name"])
        target = f"device:{device_index}:{position}"
        entry: dict[str, Any] = {"index": position, "name": name, "min": parameter.get("min"),
                                 "max": parameter.get("max"), "quantized": bool(parameter.get("quantized"))}
        if entry["quantized"]:
            span = int(round(float(parameter["max"]) - float(parameter["min"]))) + 1
            table = client.get_display_table(kind, index, target, max(2, min(span, 200)))
            entry["options"] = table.get("points", []) if table.get("success") else table.get("error")
        else:
            points: list[tuple[float, str]] = []
            pages = max(1, math.ceil(samples / 100))
            for page in range(pages):
                table = client.get_display_table(kind, index, target, 101, page / pages, (page + 1) / pages)
                if not table.get("success"):
                    entry["error"] = table.get("error")
                    break
                points.extend((float(raw), str(text)) for raw, text in table["points"])
            if "error" not in entry:
                entry.update(classify(sorted(set(points))))
        parameters.append(entry)
    return {"device": device, "kind": kind, "index": index, "device_index": device_index, "parameters": parameters}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--kind", choices=("track", "return", "master"), default="track")
    parser.add_argument("--index", type=int, required=True, help="track or return index (0-based)")
    parser.add_argument("--device-index", type=int, default=0)
    parser.add_argument("--samples", type=int, default=400, help="raw values per continuous parameter")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    from kenn.ableton_osc_bridge import AbletonOSCClient

    result = measure(AbletonOSCClient(), args.kind, args.index, args.device_index, args.samples)
    result["measured_at"] = date.today().isoformat()
    result["candidates"] = [line for p in result["parameters"]
                            if (line := candidate_profile(result["device"], p["name"], p))]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    kinds: dict[str, int] = {}
    for p in result["parameters"]:
        key = "quantized" if p["quantized"] else p.get("mapping", "error")
        kinds[key] = kinds.get(key, 0) + 1
    print(json.dumps({"device": result["device"], "parameters": len(result["parameters"]), "by_mapping": kinds,
                      "candidate_profiles": len(result["candidates"]), "out": str(args.out)}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
