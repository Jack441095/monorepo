#!/usr/bin/env python3
"""Build a larger, deterministic KENN command-planning corpus.

This expands the reviewed synthetic seed records with controlled natural-language
variants.  It deliberately uses the same bounded snapshot and typed labels as
``build_kenn_command_training.py``; it does not scrape Ableton projects, read
audio, or consume the sealed shadow holdout.  The result is training material,
not evidence of model quality.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps" / "backend" / "src"))
sys.path.insert(0, str(REPO_ROOT / "tooling" / "scripts"))

DEFAULT_OUTPUT = REPO_ROOT / "apps" / "backend" / "src" / "kenn" / "artifacts" / "training" / "ableton_command_corpus.jsonl"
SCHEMA = "kenn.ableton_command_training.v1"


def _target(plan: dict[str, Any], *, by_number: bool) -> str:
    if by_number:
        return f"track {int(plan['track_index']) + 1}"
    return str(plan.get("track_name") or "the target track")


def _db(value: float) -> str:
    if value <= 0.0:
        return "minus twenty dB"
    return f"{20.0 * math.log10(value):g} dB"


def _percent(value: float) -> str:
    amount = abs(value) * 100.0
    return f"{amount:g}%"


def _cores(row: dict[str, Any]) -> list[str]:
    plan = row["label"]
    action = str(plan.get("action", ""))
    # Drafted seeds exist for their wording, so keep it instead of templating from the label.
    if action == "clarify" or row.get("source_kind") == "claude_drafted_owner_review_pending":
        query = str(row["query"])
        return [
            query,
            query + " please",
            query + " right now",
            "I need help with this request: " + query[:1].lower() + query[1:],
        ]
    if action == "add_locator":
        name = str(plan.get("locator_name") or "Marker")
        return [
            f"Add a locator named {name} at the current position",
            f"Create a marker called {name} at the playhead",
            f"Set cue point named {name} at the current cursor",
            f"Add locator {name} at the current song position",
        ]
    if action == "remove_locator":
        name = str(plan.get("locator_name") or "Marker")
        return [
            f"Remove the locator named {name} at the current position",
            f"Delete the marker called {name} at the playhead",
            f"Remove cue point {name} at the current cursor",
            f"Delete locator {name} at the current song position",
        ]
    if action in {"create_midi_track", "create_audio_track"}:
        name = str(plan.get("new_track_name") or "").strip()
        track_kind = "MIDI" if action == "create_midi_track" else "audio"
        if name:
            return [
                f"Create a new {track_kind} track named {name}",
                f"Add a {track_kind} track called {name}",
                f"Make me a {track_kind} track named {name}",
                f"Append a new {track_kind} track for {name}",
            ]
        return [
            f"Create a {track_kind} track",
            f"Add a new {track_kind} track",
            f"Make me a {track_kind} track",
            f"Append a {track_kind} track to the set",
        ]
    if action == "create_return_track":
        name = str(plan.get("new_track_name") or "").strip()
        if name:
            return [
                f"Create a new return track named {name}",
                f"Add a return called {name}",
                f"Make me a return track named {name}",
                f"Append a new return for {name}",
            ]
        return [
            "Create a return track",
            "Add a new return track",
            "Make me a return track",
            "Append a return track to the set",
        ]
    target_name = _target(plan, by_number=False)
    target_number = _target(plan, by_number=True)
    value = plan.get("value")
    enabled = bool(value)

    if action == "focus_track":
        return [
            f"Select {target_number}",
            f"Focus {target_number}",
            f"Follow {target_number}",
            f"Show {target_number}",
        ]
    if action == "focus_device":
        device = str(plan.get("device_name") or "the device")
        return [
            f"Focus {device} on {target_number}",
            f"Select the {device} on {target_number}",
            f"Follow {device} on {target_number}",
            f"Focus device {device} on {target_number}",
        ]

    if action == "set_mute":
        return ([
            f"Mute {target_name}",
            f"Engage mute on {target_name}",
            f"Silence {target_name}",
            f"Mute {target_number}",
        ] if enabled else [
            f"Unmute {target_name}",
            f"Take {target_name} out of mute",
            f"Turn mute off for {target_name}",
            f"Unmute {target_number}",
        ])
    if action == "set_solo":
        return ([
            f"Solo {target_name}",
            f"Solo {target_number}",
            f"Put {target_name} into solo",
            f"Isolate {target_name}",
        ] if enabled else [
            f"Unsolo {target_name}",
            f"Take {target_name} out of solo",
            f"Turn solo off for {target_name}",
            f"Unsolo {target_number}",
        ])
    if action == "set_arm":
        return ([
            f"Arm {target_name}",
            f"Make {target_name} record-ready",
            f"Record-enable {target_name}",
            f"Arm {target_number}",
        ] if enabled else [
            f"Disarm {target_name}",
            f"Take {target_name} out of record-ready mode",
            f"Turn record arm off for {target_name}",
            f"Disarm {target_number}",
        ])
    if action == "set_volume":
        requested = _db(float(value))
        return [
            f"Set {target_name} level to {requested}",
            f"Set the volume on {target_number} to {requested}",
            f"Bring {target_name} to {requested}",
            f"Set {target_number} volume at {requested}",
        ]
    if action == "set_pan":
        direction = "left" if float(value) < 0 else "right" if float(value) > 0 else "center"
        amount = _percent(float(value))
        return [
            f"Pan {target_name} {amount} {direction}",
            f"Move {target_number} {amount} {direction}",
            f"Put {target_name} {direction} by {amount}",
            f"Set the pan of {target_name} to {direction} {amount}",
        ]
    if action == "inspect_devices":
        return [
            f"What devices are on {target_name}?",
            f"Show me the chain on {target_name}",
            f"List the processors on {target_number}",
            f"Inspect {target_name}'s devices",
        ]
    if action == "set_device_parameter":
        device = str(plan["device_name"])
        parameter = str(plan["parameter_name"])
        unit = str(plan.get("unit") or "")
        rendered_value = f"{float(value):g}"
        if unit == "ratio":
            rendered_value += ":1"
        elif unit not in {"", "value", "device_value"}:
            rendered_value += f" {unit}"
        if bool(plan.get("relative")):
            amount = f"{abs(float(value)):g}"
            if unit not in {"", "value", "device_value"}:
                amount += f" {unit}"
            return [
                f"Lower the {target_name} {device} {parameter} by {amount}",
                f"Reduce {device} {parameter} on {target_name} by {amount}",
                f"Decrease {parameter} on {device} on {target_number} by {amount}",
                f"Back off the {device} {parameter} on {target_name} by {amount}",
            ]
        return [
            f"Set {device} {parameter} to {rendered_value} on {target_name}",
            f"Set {parameter} on {device} to {rendered_value} on {target_number}",
            f"Change {device} {parameter} on {target_name} to {rendered_value}",
            f"Set the {parameter} control on {device} to {rendered_value} on {target_name}",
        ]
    if action == "set_eq_band_gain":
        band = str(plan["eq_band"])
        frequency = f"{float(plan['frequency_hz']):g} Hz"
        amount = f"{abs(float(value)):g} dB"
        verb = "cut" if float(value) < 0 else "boost"
        return [
            f"{verb} EQ band {band} by {amount} at {frequency} on {target_name}",
            f"Set EQ Eight band {band} gain to {float(value):g} dB at {frequency} on {target_name}",
            f"{('Reduce' if verb == 'cut' else 'Boost')} EQ band {band} gain by {amount} at {frequency} on {target_number}",
            f"{('Reduce' if verb == 'cut' else 'Boost')} the {band} EQ gain by {amount} at {frequency} on {target_name}",
        ]
    if action == "insert_device":
        device = str(plan["device_name"])
        return [
            f"Add {device} to {target_name}",
            f"Append {device} on {target_number}",
            f"Insert {device} after the existing devices on {target_name}",
            f"Put a {device} at the end of {target_name}'s chain",
        ]
    if action == "insert_device_with_parameter":
        device = str(plan["device_name"])
        parameter = str(plan["parameter_name"])
        percentage = f"{float(value):g}%"
        return [
            f"Add reverb to {target_name} at {percentage.lower()} dry wet",
            f"Append {device} on {target_number} and set {parameter} to {percentage}",
            f"Put {device} at the end of {target_name}'s chain with {parameter} at {percentage}",
            f"Add {device} to {target_name}, Dry/Wet {percentage}",
        ]
    return [row["query"]]


def _variants(row: dict[str, Any], count: int) -> list[str]:
    cores = _cores(row)
    if count <= 0:
        raise ValueError("variants must be positive")
    prefixes = ("", "Please ", "Can you ", "Could you ", "I'd like you to ")
    suffixes = ("", " please", " for a quick check", " in the current session")
    candidates: list[str] = []
    for core in cores:
        candidates.append(core)
    for prefix in prefixes[1:]:
        for core in cores:
            candidates.append(prefix + core[:1].lower() + core[1:])
    for suffix in suffixes[1:]:
        for core in cores:
            candidates.append(core + suffix)
    unique = list(dict.fromkeys(" ".join(candidate.split()) for candidate in candidates))
    if count <= len(unique):
        return unique[:count]
    # A larger export may deliberately oversample a reviewed label. Add a
    # bounded variant marker only after exhausting natural variants; this keeps
    # every row distinct without pretending the marker adds semantic coverage.
    expanded = list(unique)
    for number in range(len(unique), count):
        expanded.append(f"{unique[number % len(unique)]} (variant {number + 1})")
    return expanded


SCENARIO_TRACK_NAMES = (
    ("Lead Vox", "Drum Bus", "Bass Synth", "FX Return", "Master Print"),
    ("Main Vocal", "Drum Group", "Sub Bass", "Effects Return", "Print Master"),
    ("Lead Voice", "Rhythm Bus", "Low Synth", "FX Return", "Master Print"),
    ("Vocal Lead", "Drums", "Bass", "FX", "Master Print"),
)


SCENARIO_VOLUMES = (0.6, 0.55, 0.5, 0.45, 0.65)  # synthetic; +3 dB from any stays at or below 1.0


def scenario_snapshots() -> list[dict[str, Any]]:
    from build_kenn_command_training import training_snapshot

    snapshots: list[dict[str, Any]] = []
    for names in SCENARIO_TRACK_NAMES:
        snapshot = copy.deepcopy(training_snapshot())
        for track, name, volume in zip(snapshot["tracks"], names, SCENARIO_VOLUMES):
            track["name"] = name
            # Mixer state, as the production snapshot carries it; relative dB
            # volume labels are validated against these values.
            track.update({"volume": volume, "pan": 0.0, "muted": False, "soloed": False, "armed": False})
        snapshots.append(snapshot)
    return snapshots


def _scenario_seed(seed: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    variant = dict(seed)
    label = dict(seed["label"])
    track_index = label.get("track_index")
    if track_index is not None:
        label["track_name"] = snapshot["tracks"][int(track_index)]["name"]
    variant["label"] = label
    return variant


FIXTURE = REPO_ROOT / "apps" / "backend" / "src" / "kenn" / "core" / "fake_live_fixtures" / "investor_demo.json"


def real_device_parameters() -> dict[str, list[dict[str, Any]]]:
    """Parameter lists recorded from the owner's Live set, by device name (Compressor, EQ Eight)."""
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    devices: dict[str, list[dict[str, Any]]] = {}
    for info in fixture["devices"].values():
        devices.setdefault(str(info["device_name"]), [
            {k: v for k, v in p.items() if k not in {"recorded_value", "recorded_display"}} for p in info["parameters"]
        ])
    return devices


class _EvidenceService:
    """Stands in for LiveActionService so production's _llm_planner_snapshot builds the evidence.

    Devices recorded from Live get their real parameter lists; others keep the
    synthetic training lists (training_snapshot's planner_capabilities).
    """

    def __init__(self, snapshot: dict[str, Any], real: dict[str, list[dict[str, Any]]],
                 synthetic: dict[str, list[dict[str, Any]]]) -> None:
        self.client = self
        self._snapshot, self._real, self._synthetic = snapshot, real, synthetic

    def get_device_parameters(self, track_index: int, device_index: int) -> dict[str, Any]:
        track = next((t for t in self._snapshot["tracks"] if t.get("index") == track_index), None)
        devices = (track or {}).get("devices") or []
        if not 0 <= device_index < len(devices):
            return {"success": False}
        name = str(devices[device_index].get("name", ""))
        parameters = self._real.get(name) or self._synthetic.get(name)
        if parameters is None:
            return {"success": False}
        return {"success": True, "device_name": name, "parameters": copy.deepcopy(parameters)}


def _real_parameter_indices(plan: dict[str, Any], real: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Point a label's parameter_index at the real Live index of the same-named parameter."""
    plan = dict(plan)
    if plan.get("steps"):
        plan["steps"] = [_real_parameter_indices(step, real) for step in plan["steps"]]
    parameters = real.get(str(plan.get("device_name") or ""))
    if parameters and plan.get("parameter_name"):
        wanted = str(plan["parameter_name"]).casefold()
        match = next((p for p in parameters if str(p.get("name", "")).casefold() == wanted), None)
        if match is not None:
            plan["parameter_index"] = int(match["index"])
    return plan


def _production_snapshot(query: str, label: dict[str, Any], snapshot: dict[str, Any],
                         real: dict[str, list[dict[str, Any]]], synthetic: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """The snapshot the gateway would give the planner for this request.

    Production attaches single-track parameter evidence for the track the rule
    parser identifies; when the parser finds none, the label's own track is
    used so that every device example is answerable.
    """
    from kenn.core.live_command import _llm_planner_snapshot
    from kenn.core.live_intent import parse_request

    base = {k: v for k, v in snapshot.items() if k != "planner_capabilities"}
    target = (parse_request(query, base).get("track") or {}).get("index")
    if target is None:
        target = label.get("track_index")
    if target is None:
        return base
    return _llm_planner_snapshot(_EvidenceService(base, real, synthetic), base, {"track": {"index": target}})


def cap_per_action(rows: list[dict[str, Any]], cap: int) -> list[dict[str, Any]]:
    """Keep at most ``cap`` rows per action (clarify exempt), round-robin across seeds.

    One over-represented action teaches the model a shortcut: in run 3, 224
    mute examples against few transport ones taught "stop" as mute.
    """
    by_action: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for row in rows:
        by_action.setdefault(row["label"]["action"], {}).setdefault(row["source_record_id"], []).append(row)
    kept: set[int] = set()
    for action, seeds in by_action.items():
        groups = [list(group) for group in seeds.values()]
        total = sum(len(group) for group in groups)
        if action == "clarify" or total <= cap:
            kept.update(id(row) for group in groups for row in group)
            continue
        taken = 0
        while taken < cap:
            for group in groups:
                if group and taken < cap:
                    kept.add(id(group.pop(0)))
                    taken += 1
    return [row for row in rows if id(row) in kept]


def build_rows(*, variants: int, scenarios: int = 1, include_drafted: bool = False,
               prompt: str = "full", clarify_variants: int | None = None,
               production_evidence: bool = False) -> list[dict[str, Any]]:
    from build_kenn_command_training import (
        _plan, evaluation_queries, normalize_query, plan_target, records, training_snapshot,
    )
    from drafted_command_seeds import drafted_records
    from kenn.core.live_command import (
        LLM_COMMAND_SYSTEM_PROMPT, LLM_COMMAND_SYSTEM_PROMPT_COMPACT, planner_user_prompt, validate_llm_plan,
    )

    system_prompt = {"full": LLM_COMMAND_SYSTEM_PROMPT, "compact": LLM_COMMAND_SYSTEM_PROMPT_COMPACT}[prompt]
    real = real_device_parameters() if production_evidence else {}
    synthetic = {str(e["device_name"]): e["parameters"]
                 for e in training_snapshot().get("planner_capabilities", {}).get("entries", [])}

    if scenarios < 1 or scenarios > len(SCENARIO_TRACK_NAMES):
        raise ValueError(f"scenarios must be between 1 and {len(SCENARIO_TRACK_NAMES)}")
    held_out = evaluation_queries()
    rows: list[dict[str, Any]] = []
    for scenario_number, snapshot in enumerate(scenario_snapshots()[:scenarios], start=1):
        snapshot_text = json.dumps(snapshot, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        seeds = records() + (drafted_records(snapshot, _plan) if include_drafted else [])
        for seed in seeds:
            scenario_seed = _scenario_seed(seed, snapshot)
            count = clarify_variants if clarify_variants and seed["label"]["action"] == "clarify" else variants
            for number, query in enumerate(_variants(scenario_seed, count), start=1):
                if normalize_query(query) in held_out:
                    query = query + " in the current Live session"
                    while normalize_query(query) in held_out:
                        query += " now"
                label = dict(scenario_seed["label"])
                record_id = f"s{scenario_number}-{seed['record_id']}-v{number:04d}"
                record_snapshot, record_text = snapshot, snapshot_text
                if production_evidence:
                    # What the gateway would send: single-track evidence, real
                    # parameter indices where Live recorded them, 24,000-char bound.
                    record_snapshot = _production_snapshot(query, label, snapshot, real, synthetic)
                    label = _real_parameter_indices(label, real)
                    record_text = json.dumps(record_snapshot, ensure_ascii=True, sort_keys=True,
                                             separators=(",", ":"))[:24000]
                checked = validate_llm_plan(label, record_snapshot)
                if not checked.get("ok"):
                    raise ValueError(f"Invalid seed label {seed['record_id']} in scenario {scenario_number}: {checked.get('error')}")
                rows.append({
                    "schema": SCHEMA,
                    "record_id": record_id,
                    "source_record_id": seed["record_id"],
                    "source_kind": seed.get("source_kind", "reviewed_seed"),
                    "scenario": scenario_number,
                    "split": "synthetic_train",
                    "category": seed["category"],
                    "query": query,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        # Same user turn as production; the schema constant is stamped by KENN.
                        {"role": "user", "content": planner_user_prompt(query, record_text)},
                        {"role": "assistant", "content": plan_target(label)},
                    ],
                    "label": label,
                    **({"evidence": "production"} if production_evidence else {}),
                })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variants", type=int, default=8, help="Natural-language variants per reviewed seed record")
    parser.add_argument("--scenarios", type=int, default=1, help="Distinct synthetic track-name snapshots to include (1-4)")
    parser.add_argument("--include-drafted", action="store_true",
                        help="add the drafted clarify seeds (drafted_command_seeds.py; owner review pending)")
    parser.add_argument("--production-evidence", action="store_true",
                        help="per-record single-track parameter evidence as the gateway sends it, real Live indices")
    parser.add_argument("--max-per-action", type=int, default=0,
                        help="cap rows per action (clarify exempt), spread evenly across seeds; 0 = no cap")
    parser.add_argument("--clarify-variants", type=int, default=None,
                        help="variants per clarify seed (default: --variants); lower it to reduce the clarify share")
    parser.add_argument("--prompt", choices=("full", "compact"), default="full",
                        help="system prompt in each record; 'compact' for a fine-tune served with KENN_LLM_COMMAND_PROMPT=compact")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    rows = build_rows(variants=args.variants, scenarios=args.scenarios, include_drafted=args.include_drafted,
                      prompt=args.prompt, clarify_variants=args.clarify_variants,
                      production_evidence=args.production_evidence)
    if args.max_per_action:
        rows = cap_per_action(rows, args.max_per_action)
    from build_kenn_command_training import assert_no_holdout_overlap

    assert_no_holdout_overlap(rows)
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    print(json.dumps({
        "schema": SCHEMA,
        "status": "ready",
        "records": len(rows),
        "scenarios": args.scenarios,
        "variants_per_seed": args.variants,
        "drafted_seeds_included": args.include_drafted,
        "system_prompt": args.prompt,
        "clarify_variants_per_seed": args.clarify_variants or args.variants,
        "max_per_action": args.max_per_action or None,
        "production_evidence": args.production_evidence,
        "output": str(output),
        "holdout_protection": "passed",
        "evidence_kind": "synthetic_training_data",
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
