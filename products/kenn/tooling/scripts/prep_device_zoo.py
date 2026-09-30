#!/usr/bin/env python3
"""Preflight and fake-Live rehearsal for the wave-1 device zoo (Live night 1).

    prep_device_zoo.py [--only "EQ Eight,Compressor"] [--skip-dry-run] [--commands]

Two halves, neither of which touches Live:

**Preflight.** Every wave-1 name is checked against the exact browser names in ``core/stock_devices.py``, so a typo
is caught here rather than as a silent skip in ``measure_all_devices.py`` (which matches ``--only`` on the name Live
reports). For each device we also report whether KENN can insert it -- four of the twelve cannot, and the set has to be
dragged in by hand -- and how many parameters the qualifier will skip because ``device_units.py`` already has a
hand-verified profile for them.

**Rehearsal.** The real ``measure_all_devices.sweep``, the real ``build_device_profiles.build`` and the real
``qualify_device_candidates.run`` are run against ``FakeLiveBackend`` on ``fake_live_fixtures/device_zoo_wave1.json``.
That proves our wiring: the sweep finds each device once, the evidence files land where the builder looks, candidates
classify, and every candidate is locatable on a regular track -- the failure that costs a Live night, because
``qualify_device_candidates.locate()`` only searches ``state["tracks"]`` and reports a return-only device as
"not on a regular track in the open set".

What the rehearsal does **not** prove: the numbers. ``FakeLiveBackend`` has no display-table method, so the ``measure``
callable below synthesises ``(raw, display)`` samples from the fixture's recorded formats and runs them through the real
``classify()``. Mapping detection is therefore exercised, but Live's actual ranges and strings are what the night
measures.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

KENN_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(KENN_ROOT / "apps" / "backend" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

ZOO_FIXTURE = KENN_ROOT / "apps" / "backend" / "src" / "kenn" / "core" / "fake_live_fixtures" / "device_zoo_wave1.json"

# Wave 1 of the device factory, in the order A3 sweeps them. The names have to be Live's own: measure_all_devices
# keys its evidence files and its --only filter on the name the device reports, and the qualifier locates a device by
# that same string.
WAVE_ONE: tuple[str, ...] = (
    "EQ Eight", "Compressor", "Utility", "Limiter", "Reverb", "Hybrid Reverb",
    "Delay", "Echo", "Saturator", "Auto Filter", "Glue Compressor", "Multiband Dynamics",
)

# Why a wave-1 device is not in DEVICE_INSERTION_ALLOWLIST. Only the name is machine-checkable; the reason is not,
# and a set that cannot be built by script has to be built by hand, so it is written down rather than inferred.
NOT_INSERTABLE: dict[str, str] = {
    # AbletonOSC's browser search resolves this to Convolution Reverb, so inserting by name puts the wrong device in.
    "Reverb": "AbletonOSC's browser search resolved \"Reverb\" to Convolution Reverb on real Live (2026-09-05)",
    # Same trap one folder over: "Delay" landed on Align Delay.
    "Delay": "AbletonOSC's browser search resolved \"Delay\" to Align Delay on real Live (2026-09-05)",
    # Refused deliberately, not an oversight: the setup set and the plan validator agree on not offering it.
    "Limiter": "deliberately refused -- the planner prompt and validate_llm_plan do not offer it",
    # Not an insertion gap: the 2026-09-21 unit probe found Utility | Gain had no usable points and the real
    # control is Output, which had no profile at all. That is a measurement job, not a naming one.
    "Utility": "not a naming problem -- the 2026-09-21 probe found the real control is Utility | Output, which has no profile",
}


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")


def preflight(devices: tuple[str, ...]) -> dict[str, Any]:
    """Names, insertability and existing coverage for the wave, with the problems that would waste a Live night."""
    from kenn.core import device_units
    from kenn.core.live_action_service import DEVICE_INSERTION_ALLOWLIST
    from kenn.core.stock_devices import STOCK_DEVICES, stock_device_name

    covered: dict[str, list[str]] = {}
    for profile in device_units.EVIDENCE_BACKED_PROFILES:
        covered.setdefault(profile.device_name, []).append(profile.parameter_name)

    rows, problems = [], []
    for name in devices:
        exact = stock_device_name(name)
        if exact is None:
            problems.append(f"{name!r} is not a Live 12 Suite browser name; check the spelling against STOCK_DEVICES")
        elif exact != name:
            # Casefolded matching hides this in the sweep, so it is worth saying out loud.
            problems.append(f"{name!r} does not match the browser name's casing {exact!r}; profiles are keyed by name")
        rows.append({
            "device": name,
            "insertable": name in DEVICE_INSERTION_ALLOWLIST,
            "reason": NOT_INSERTABLE.get(name, ""),
            "hand_verified": sorted(covered.get(name, []), key=str.casefold),
            "known": name in STOCK_DEVICES,
        })
    for label, path in (("evidence", KENN_ROOT / "tooling" / "data" / "measured_devices"),
                        ("candidates", KENN_ROOT / "tooling" / "data" / "device_profile_candidates"),
                        ("profiles", KENN_ROOT / "apps" / "backend" / "src" / "kenn" / "core" / "device_profiles"),
                        ("transcripts", KENN_ROOT / "tooling" / "data" / "device_qualification")):
        if not path.parent.is_dir():
            problems.append(f"the {label} folder's parent is missing: {path.parent}")
    if not ZOO_FIXTURE.is_file():
        problems.append(f"the zoo fixture is missing: {ZOO_FIXTURE}")
    return {"rows": rows, "problems": problems}


# Live's ratio display is "4.00 : 1", so the unit is more than one token.
_END = re.compile(r"^\s*(?P<value>[-+]?\d+(?:\.\d+)?)\s*(?P<unit>.*?)\s*$")


def _interpolated_display(parameter: dict[str, Any], raw: float, low: float, high: float, match: re.Match[str]) -> str:
    """Live's display for a sampled raw value, interpolated between the two ends the fixture records."""
    fraction = (raw - float(parameter["min"])) / (float(parameter["max"]) - float(parameter["min"]))
    unit, decimals = match.group("unit"), len(match.group("value").partition(".")[2])
    return f"{low + (high - low) * fraction:.{decimals}f} {unit}".strip()


def fake_measure(client: Any, kind: str, index: int, device_index: int, samples: int) -> dict[str, Any]:
    """Stand-in for measure_device_parameters.measure, because the fake has no display-table method.

    Interpolates each continuous parameter between the display strings its fixture entry records at each end of the
    control's travel, then hands the pairs to the real classify(), so unit normalisation and mapping detection are the
    shipping code paths. The log and table branches of classify() are not reachable this way -- the fake cannot know
    Live's real curves -- and are pinned directly in test_measure_device_parameters.py instead.
    """
    from measure_device_parameters import classify, parse_display

    listing = client.get_bus_device_parameters(kind, index, device_index)
    if not listing.get("success"):
        raise SystemExit(f"the fake did not list the device's parameters: {listing.get('error')}")
    parameters = []
    for parameter in listing.get("parameters", []):
        position, name = int(parameter["index"]), str(parameter["name"])
        entry: dict[str, Any] = {"index": position, "name": name, "min": parameter.get("min"),
                                 "max": parameter.get("max"), "quantized": bool(parameter.get("quantized"))}
        if entry["quantized"]:
            span = int(round(float(parameter["max"]) - float(parameter["min"]))) + 1
            rows = [[float(raw), str(label)] for raw, label in (parameter.get("options") or [])]
            entry["options"] = rows[:max(2, min(span, 200))]
            parameters.append(entry)
            continue
        shown_at, shown_to = parameter.get("value_display"), parameter.get("end_display")
        low, high, match = parse_display(str(shown_at or "")), parse_display(str(shown_to or "")), _END.match(str(shown_at or ""))
        if not (low and high and match):
            entry["error"] = "the fixture records no readable display at both ends of this parameter"
            parameters.append(entry)
            continue
        points = []
        for step in range(samples):
            raw = float(parameter["min"]) + (float(parameter["max"]) - float(parameter["min"])) * step / max(1, samples - 1)
            points.append((round(raw, 6), _interpolated_display(parameter, raw, float(low[0]), float(high[0]), match)))
        entry.update(classify(points))
        parameters.append(entry)
    return {"device": str(listing.get("device_name") or ""), "kind": kind, "index": index,
            "device_index": device_index, "parameters": parameters}


def rehearse(devices: tuple[str, ...]) -> dict[str, Any]:
    """Run the real sweep, the real candidate builder and the real (unapplied) qualifier on the fake zoo."""
    import build_device_profiles
    import measure_all_devices
    import qualify_device_candidates
    from kenn.core.fake_live import FakeLiveBackend

    backend = FakeLiveBackend(ZOO_FIXTURE)
    only = {name.casefold() for name in devices}
    problems: list[str] = []

    with tempfile.TemporaryDirectory(prefix="kenn-zoo-") as raw_dir:
        evidence_dir = Path(raw_dir)
        summary = measure_all_devices.sweep(backend, evidence_dir, measure=fake_measure, only=only,
                                            log=lambda _line: None)
        found = sorted({path.stem for path in evidence_dir.glob("*.json")})
        expected = sorted(slug(name) for name in devices)
        if found != expected:
            problems.append(f"the sweep wrote {found}, expected {expected}")
        for failure in summary["failed"]:
            problems.append(f"the sweep failed on {failure}")

        candidates = []
        for path in sorted(evidence_dir.glob("*.json")):
            try:
                candidate = build_device_profiles.build(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError) as error:
                problems.append(f"build_device_profiles skipped {path.name}: {error}")
                continue
            (evidence_dir / "candidates").mkdir(exist_ok=True)
            (evidence_dir / "candidates" / path.name).write_text(json.dumps(candidate, indent=1), encoding="utf-8")
            candidates.append(candidate)

        # apply=False is the run the night does first anyway: it makes every proposal without writing, which is what
        # proves each candidate is on a regular track and each value converts to a legal proposal. A parameter that
        # lands in "skipped" as "proposals made, nothing written" has been rehearsed successfully.
        with tempfile.TemporaryDirectory(prefix="kenn-zoo-profiles-") as profiles_dir:
            proposals = qualify_device_candidates.run(
                evidence_dir / "candidates", qualify=lambda **_kw: {"status": "proposal_ready"},
                state=backend.query_session_state(), endpoint="", apply=False, pause=0.0,
                profiles_dir=Path(profiles_dir), transcripts_dir=evidence_dir / "transcripts")
        for failure in proposals["failed"]:
            problems.append(f"a proposal could not be made: {failure}")
        rehearsed = [line for line in proposals["skipped"] if "nothing written" in line]
        missing = [line for line in proposals["skipped"] if "not on a regular track" in line]

        totals = {"profiles": sum(len(c["profiles"]) for c in candidates),
                  "choosers": sum(len(c["choosers"]) for c in candidates),
                  "unmapped": sum(len(c["unmapped"]) for c in candidates)}
        unmapped_reasons: dict[str, list[str]] = {}
        for candidate in candidates:
            for entry in candidate["unmapped"]:
                unmapped_reasons.setdefault(entry["reason"], []).append(f"{candidate['device']} / {entry['parameter']}")

    if not rehearsed:
        problems.append("the rehearsal made no proposals at all, so it proved nothing")
    return {"devices_found": len(found), "candidates": len(candidates), "parameters": totals,
            "rehearsed": len(rehearsed), "not_on_a_track": missing, "unmapped_reasons": unmapped_reasons,
            "problems": problems}


def command_sequence(devices: tuple[str, ...]) -> list[str]:
    only = ",".join(devices)
    return [
        f'python3 tooling/scripts/measure_all_devices.py --only "{only}"',
        'python3 tooling/scripts/build_device_profiles.py --live-app "/Applications/Ableton Live 12 Suite.app"',
        'python3 tooling/scripts/qualify_device_candidates.py',
        'python3 tooling/scripts/qualify_device_candidates.py --apply',
    ]


def render_checklist(devices: tuple[str, ...], pre: dict[str, Any]) -> str:
    lines = [f"{'Track':<20} {'Drag by hand':<14} {'Already hand-verified':<24} Why", "|---|---|---|---|"]
    for row in pre["rows"]:
        verified = ", ".join(row["hand_verified"]) or "-"
        lines.append(f"{row['device']:<20} {'yes' if not row['insertable'] else 'no':<14} {verified:<24} {row['reason']}")
    hand = [row["device"] for row in pre["rows"] if not row["insertable"]]
    lines.append("")
    lines.append(f"One regular track per device, {len(devices)} tracks, default device names, nothing on a return or "
                 f"the master.")
    lines.append(f"KENN cannot insert {len(hand)} of them ({', '.join(hand)}), so drag those in from the browser.")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", help="comma-separated device names, default the whole wave-1 list")
    parser.add_argument("--skip-dry-run", action="store_true", help="preflight only")
    parser.add_argument("--commands", action="store_true", help="print the night's command sequence and stop")
    args = parser.parse_args()

    devices = tuple(name.strip() for name in args.only.split(",")) if args.only else WAVE_ONE
    if args.commands:
        print("\n".join(command_sequence(devices)))
        return 0

    pre = preflight(devices)
    print(f"Wave-1 device zoo: {len(devices)} devices\n")
    print(render_checklist(devices, pre))

    if pre["problems"]:
        print("\npreflight problems:")
        for problem in pre["problems"]:
            print(f"  {problem}")
    if args.skip_dry_run:
        return 1 if pre["problems"] else 0

    print("\nRehearsing the sweep, the candidate build and the qualifier on FakeLiveBackend...")
    report = rehearse(devices)
    print(f"  {report['devices_found']} devices measured, {report['candidates']} candidate files, "
          f"{report['parameters']['profiles']} candidate profiles, {report['parameters']['choosers']} choosers, "
          f"{report['parameters']['unmapped']} unmapped")
    print(f"  {report['rehearsed']} parameters reached a proposal without writing anything")
    for device in report["not_on_a_track"]:
        print(f"  not on a regular track: {device}")
    for problem in report["problems"]:
        print(f"  {problem}")
    for reason, entries in sorted(report["unmapped_reasons"].items()):
        print(f"  unmapped ({len(entries)}): {reason}")

    print("\nLive night 1, from products/kenn, with the companion stopped for the measure and running for the qualify:")
    for command in command_sequence(devices):
        print(f"  {command}")
    return 1 if pre["problems"] or report["problems"] else 0


if __name__ == "__main__":
    raise SystemExit(main())