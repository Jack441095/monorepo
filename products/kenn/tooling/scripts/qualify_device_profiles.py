#!/usr/bin/env python3
"""Qualify candidate device profiles on real Live, then write the ones that pass.

    qualify_device_profiles.py [--apply] [--device "Operator"] [--parameter "Filter Freq"] [--endpoint URL]

USE A DISPOSABLE SET, with your monitors low. For each candidate parameter (from build_device_profiles.py) whose device
sits on a regular track, this sets it at three raw values (about 20%, 50% and 80% of its range), reads Live's own display
string back, and restores the original value through KENN's confirmed undo. A parameter passes only if, at all three points:

- the write, the undo and the exact-replay rejection all pass (the existing qualify_ableton_live_device.py checks), and
- the display Live showed is within tolerance of what the candidate mapping predicted for that raw value.

Passing parameters are written, with the transcript, to core/device_profiles/<device>.json, which core/device_units.py loads.
Failed ones are reported and change nothing. A dB control is never tested above 0 dB, so a gain knob can't get loud.
Without --apply it only checks that each proposal can be made; Live isn't written.

Devices that live only on a return or the master, and devices inside racks, can't be qualified this way.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any, Callable

KENN_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(KENN_ROOT / "apps" / "backend" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
DEFAULT_CANDIDATES = KENN_ROOT / "tooling" / "data" / "device_profile_candidates"
DEFAULT_PROFILES = KENN_ROOT / "apps" / "backend" / "src" / "kenn" / "core" / "device_profiles"
DEFAULT_TRANSCRIPTS = KENN_ROOT / "tooling" / "data" / "device_qualification"
FRACTIONS = (0.2, 0.5, 0.8)
SKIP_PARAMETERS = {"device on"}
_SHOWN = re.compile(r"^\s*(?P<mantissa>[-+]?\d+(?:\.(?P<decimals>\d+))?)\s*(?P<unit>[a-zA-Z%]*)")
_UNIT_SCALE = {"khz": 1000.0, "s": 1000.0}


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")


def to_profile(candidate_device: str, entry: dict[str, Any]) -> Any:
    from kenn.core.device_units import DeviceUnitProfile, normalize_unit

    return DeviceUnitProfile(candidate_device, entry["parameter"], normalize_unit(entry["unit"]), entry["raw_min"], entry["raw_max"],
                             entry["display_min"], entry["display_max"], tuple(entry.get("raw_values") or ()),
                             tuple(entry.get("display_values") or ()), entry["mapping"])


def pick_raw_values(profile: Any, current: float | None) -> list[float]:
    """Three distinct raw values across the range; a dB control's range stops at 0 dB, and none equals the current value."""
    from kenn.core.device_units import profile_raw_to_display

    span = profile.raw_max - profile.raw_min
    top = profile.raw_max
    if profile.display_unit == "db":
        shown, _ = profile_raw_to_display(profile, top)
        while shown is not None and shown > 0.0 and top > profile.raw_min:
            top -= 0.01 * span
            shown, _ = profile_raw_to_display(profile, top)
    values: list[float] = []
    for fraction in FRACTIONS:
        raw = round(profile.raw_min + fraction * (top - profile.raw_min), 6)
        if current is not None and abs(raw - current) < 1e-6:
            raw = round(raw + 0.03 * span if raw + 0.03 * span <= top else raw - 0.03 * span, 6)
        if raw not in values:
            values.append(raw)
    return values


def within_tolerance(profile: Any, raw: float, shown: str) -> tuple[bool, dict[str, Any]]:
    """Whether Live's display string agrees with the mapping's prediction, and the numbers behind the answer."""
    from kenn.core.device_units import profile_raw_to_display
    from measure_device_parameters import parse_display

    predicted, _ = profile_raw_to_display(profile, raw)
    parsed = parse_display(shown)
    detail: dict[str, Any] = {"raw": raw, "shown": shown, "predicted": predicted}
    if predicted is None or parsed is None:
        return False, {**detail, "reason": "the display could not be read as a number"}
    value, unit = parsed
    if unit != profile.display_unit:
        return False, {**detail, "reason": f"Live showed {unit}, the mapping says {profile.display_unit}"}
    found = _SHOWN.match(shown)
    scale = _UNIT_SCALE.get(found.group("unit").casefold(), 1.0) if found else 1.0
    half_digit = 0.5 * scale * 10 ** -len((found.group("decimals") or "") if found else "")
    span = abs(profile.display_max - profile.display_min)
    tolerance = half_digit + (0.01 * abs(predicted) if profile.mapping == "log" else 0.005 * span)
    detail.update({"observed": value, "tolerance": round(tolerance, 6)})
    return abs(value - predicted) <= tolerance, detail


def locate(state: dict[str, Any], device_name: str) -> tuple[int, int] | None:
    for track in state.get("tracks") or []:
        for position, device in enumerate(track.get("devices") or []):
            if str(device.get("name") or "").casefold() == device_name.casefold():
                return int(track["index"]), position
    return None


def qualify_parameter(candidate_device: str, entry: dict[str, Any], where: tuple[int, int], *, qualify: Callable[..., dict[str, Any]],
                      endpoint: str, apply: bool, pause: float, current: float | None) -> dict[str, Any]:
    profile = to_profile(candidate_device, entry)
    rows: list[dict[str, Any]] = []
    for number, raw in enumerate(pick_raw_values(profile, current), start=1):
        if number > 1 and pause:
            time.sleep(pause)
        row = qualify(endpoint=endpoint, track_index=where[0], device_index=where[1], parameter_name=entry["parameter"], value=raw,
                      session_id=f"qualify-{slug(candidate_device)}-{slug(entry['parameter'])}-{number}", apply=apply)
        record = {"raw": raw, "status": row.get("status"), "error": row.get("error"), "restored_readback": row.get("restored_readback"),
                  "display_before": (row.get("target") or {}).get("display_before"), "display_after": row.get("display_after")}
        if apply and row.get("status") == "passed":
            agrees, detail = within_tolerance(profile, raw, str(row.get("display_after") or ""))
            record.update({"mapping_agrees": agrees, "mapping": detail})
        rows.append(record)
        if row.get("status") not in ({"passed"} if apply else {"proposal_ready"}) or (apply and not record.get("mapping_agrees")):
            break
    ok = len(rows) >= 3 and all(r["status"] == ("passed" if apply else "proposal_ready") and (not apply or r.get("mapping_agrees")) for r in rows)
    return {"parameter": entry["parameter"], "passed": ok and apply, "checked": ok, "points": rows}


def write_profiles(profiles_dir: Path, transcripts_dir: Path, device: str, passed: list[tuple[dict[str, Any], dict[str, Any]]]) -> Path:
    """Merge the passed parameters into core/device_profiles/<device>.json (a re-qualified parameter replaces its old entry)."""
    profiles_dir.mkdir(parents=True, exist_ok=True)
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    target = profiles_dir / f"{slug(device)}.json"
    existing = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {"schema": "kenn.device_profiles.v1", "device": device, "profiles": []}
    by_name = {p["parameter"].casefold(): p for p in existing["profiles"]}
    transcript = transcripts_dir / f"{slug(device)}.json"
    log = json.loads(transcript.read_text(encoding="utf-8")) if transcript.exists() else {}
    for entry, result in passed:
        log[entry["parameter"]] = {"qualified_at": date.today().isoformat(), "points": result["points"]}
        by_name[entry["parameter"].casefold()] = {
            **{k: v for k, v in entry.items() if k != "qualification"},
            "qualification": {"status": "passed", "points": len(result["points"]), "qualified_at": date.today().isoformat(),
                              "transcript": str(transcript.relative_to(KENN_ROOT)) if transcript.is_relative_to(KENN_ROOT) else str(transcript)}}
    existing["profiles"] = sorted(by_name.values(), key=lambda p: p["parameter"].casefold())
    target.write_text(json.dumps(existing, indent=1) + "\n", encoding="utf-8")
    transcript.write_text(json.dumps(log, indent=1) + "\n", encoding="utf-8")
    return target


def run(candidates_dir: Path, *, qualify: Callable[..., dict[str, Any]], state: dict[str, Any], endpoint: str, apply: bool, pause: float,
        profiles_dir: Path, transcripts_dir: Path, device_filter: str | None = None, parameter_filter: str | None = None,
        current_value: Callable[[int, int, str], float | None] = lambda *_: None) -> dict[str, Any]:
    from kenn.core import device_units

    summary: dict[str, Any] = {"passed": [], "failed": [], "skipped": []}
    for path in sorted(candidates_dir.glob("*.json")):
        candidate = json.loads(path.read_text(encoding="utf-8"))
        device = str(candidate.get("device") or "")
        if device_filter and device.casefold() != device_filter.casefold():
            continue
        where = locate(state, device)
        if where is None:
            summary["skipped"].append(f"{device}: not on a regular track in the open set")
            continue
        passed = []
        for entry in candidate.get("profiles") or []:
            name = str(entry["parameter"])
            if parameter_filter and name.casefold() != parameter_filter.casefold():
                continue
            if name.casefold() in SKIP_PARAMETERS:
                summary["skipped"].append(f"{device} / {name}: never toggled by the qualifier")
                continue
            if any(p.device_name.casefold() == device.casefold() and p.parameter_name.casefold() == name.casefold() for p in device_units.EVIDENCE_BACKED_PROFILES):
                summary["skipped"].append(f"{device} / {name}: hand-verified profile already exists")
                continue
            result = qualify_parameter(device, entry, where, qualify=qualify, endpoint=endpoint, apply=apply, pause=pause,
                                       current=current_value(where[0], where[1], name))
            if result["passed"]:
                passed.append((entry, result))
                summary["passed"].append(f"{device} / {name}")
            elif result["checked"]:
                summary["skipped"].append(f"{device} / {name}: proposals made, nothing written (rerun with --apply)")
            else:
                last = result["points"][-1] if result["points"] else {}
                why = last.get("error") or (last.get("mapping") or {}).get("reason") or (
                    f"Live showed {last['mapping']['shown']!r}, mapping predicted {last['mapping']['predicted']:g}" if last.get("mapping") else last.get("status"))
                summary["failed"].append(f"{device} / {name}: {why}")
        if passed:
            write_profiles(profiles_dir, transcripts_dir, device, passed)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--candidates-dir", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--profiles-dir", type=Path, default=DEFAULT_PROFILES)
    parser.add_argument("--transcripts-dir", type=Path, default=DEFAULT_TRANSCRIPTS)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8090", help="the running KENN companion")
    parser.add_argument("--device")
    parser.add_argument("--parameter")
    parser.add_argument("--pause", type=float, default=2.0, help="seconds between points")
    parser.add_argument("--apply", action="store_true", help="really write to Live (disposable set only) and save passing profiles")
    args = parser.parse_args()

    from qualify_ableton_live_device import _get, qualify

    if not args.candidates_dir.is_dir():
        print(f"No candidates in {args.candidates_dir}. Run build_device_profiles.py first.", file=sys.stderr)
        return 1
    state = _get(args.endpoint, "/api/ableton/osc/session")
    if state.get("status") != "connected":
        print("Live isn't connected to the KENN companion.", file=sys.stderr)
        return 1

    def current_value(track: int, device: int, parameter: str) -> float | None:
        listing = _get(args.endpoint, f"/api/ableton/osc/device-parameters?track_index={track}&device_index={device}")
        match = next((p for p in listing.get("parameters") or [] if p.get("name") == parameter), None)
        return float(match["value"]) if match and match.get("value") is not None else None

    summary = run(args.candidates_dir, qualify=qualify, state=state, endpoint=args.endpoint, apply=args.apply, pause=args.pause,
                  profiles_dir=args.profiles_dir, transcripts_dir=args.transcripts_dir, device_filter=args.device,
                  parameter_filter=args.parameter, current_value=current_value)
    for key in ("passed", "failed", "skipped"):
        if summary[key]:
            print(f"\n{key} ({len(summary[key])}):\n  " + "\n  ".join(summary[key]))
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
