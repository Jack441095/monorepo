#!/usr/bin/env python3
"""Zero-Token Combinatorial Training Data Generator for KENN.

Generates thousands of mathematically valid, schema-compliant supervised
training pairs for KENN's command parsing model (e.g. Qwen, Llama, Mistral)
without burning a single LLM API token.

Uses slot-permutation across:
- Track actions (mute, solo, arm, volume, pan, send)
- Device parameter manipulations (EQ Eight, Compressor, Glue Compressor, Utility)
- Device insertions (EQ Eight, Glue Compressor, Saturator, Hybrid Reverb, Echo)
- Session/clip operations (clip launch, stop, scene creation, loop duplication, warp/pitch)
- Ambiguity and safety rejection / clarification rules
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps" / "backend" / "src"))

DEFAULT_OUTPUT = REPO_ROOT / "apps" / "backend" / "src" / "kenn" / "training" / "ableton_command_training_large.jsonl"
HOLDOUT_CASES = REPO_ROOT / "apps" / "backend" / "src" / "kenn" / "evals" / "ableton_llm_shadow_holdout.json"
SCHEMA = "kenn.ableton_command_training.v1"


def generate_synthetic_snapshot() -> dict[str, Any]:
    return {
        "status": "connected",
        "tracks": [
            {"index": 0, "name": "Lead Vox", "devices": []},
            {"index": 1, "name": "Drum Bus", "devices": [{"index": 0, "name": "Compressor"}]},
            {"index": 2, "name": "Bass Synth", "devices": [{"index": 0, "name": "EQ Eight"}]},
            {"index": 3, "name": "FX Return", "devices": [{"index": 0, "name": "Glue Compressor"}]},
            {"index": 4, "name": "Master Print", "devices": [{"index": 0, "name": "Utility"}]},
            {"index": 5, "name": "Guitar Rhythm", "devices": []},
            {"index": 6, "name": "Pad Ambient", "devices": []},
            {"index": 7, "name": "Sub 808", "devices": [{"index": 0, "name": "Saturator"}]},
        ],
        "return_tracks": [
            {"index": 0, "name": "A-Reverb", "devices": [{"index": 0, "name": "Hybrid Reverb"}]},
            {"index": 1, "name": "B-Delay", "devices": [{"index": 0, "name": "Echo"}]},
        ],
        "planner_capabilities": {
            "schema": "kenn.ableton_planner_capabilities.v1",
            "status": "read_only",
            "entries": [
                {
                    "track_index": 1,
                    "track_name": "Drum Bus",
                    "device_index": 0,
                    "device_name": "Compressor",
                    "parameters": [
                        {"index": 0, "name": "Threshold", "value": -12.0, "min": -60.0, "max": 0.0},
                        {"index": 1, "name": "Ratio", "value": 4.0, "min": 1.0, "max": 20.0},
                    ],
                },
                {
                    "track_index": 2,
                    "track_name": "Bass Synth",
                    "device_index": 0,
                    "device_name": "EQ Eight",
                    "parameters": [
                        {"index": 12, "name": "1 Gain A", "value": 0.0, "min": -15.0, "max": 15.0},
                        {"index": 8, "name": "1 Q A", "value": 0.3767, "min": 0.0, "max": 1.0},
                    ],
                },
                {
                    "track_index": 3,
                    "track_name": "FX Return",
                    "device_index": 0,
                    "device_name": "Glue Compressor",
                    "parameters": [
                        {"index": 1, "name": "Ratio", "value": 1.0, "value_display": "4:1", "min": 0.0, "max": 2.0},
                        {"index": 2, "name": "Attack", "value": 3.0, "value_display": "1 ms", "min": 0.0, "max": 6.0},
                    ],
                },
                {
                    "track_index": 4,
                    "track_name": "Master Print",
                    "device_index": 0,
                    "device_name": "Utility",
                    "parameters": [
                        {"index": 4, "name": "Stereo Width", "value": 1.0, "min": 0.0, "max": 2.0},
                    ],
                },
            ],
            "limitations": ["Synthetic read-only capability evidence; zero tokens used."],
        },
    }


def _plan(action: str, **fields: Any) -> dict[str, Any]:
    return {
        "schema": "kenn.ableton_llm_plan.v1",
        "action": action,
        "track_index": None,
        "track_name": None,
        "device_index": None,
        "device_name": None,
        "insertion_index": None,
        "parameter_index": None,
        "parameter_name": None,
        "value": None,
        "relative": False,
        "unit": None,
        "frequency_hz": None,
        "eq_band": None,
        "return_track_index": None,
        "return_track_name": None,
        "clarification": None,
        "new_track_name": None,
        **fields,
    }


def generate_dataset(target_count: int = 5000, seed: int = 42) -> list[dict[str, Any]]:
    random.seed(seed)
    snapshot = generate_synthetic_snapshot()
    tracks = snapshot["tracks"]
    return_tracks = snapshot["return_tracks"]

    from kenn.core.live_command import LLM_COMMAND_SYSTEM_PROMPT
    snapshot_text = json.dumps(snapshot, ensure_ascii=True, sort_keys=True, separators=(",", ":"))

    items: list[tuple[str, str, dict[str, Any]]] = []

    # 1. Mute Variations
    mute_verbs_on = ["Mute", "Silence", "Turn off", "Cut audio on", "Kill sound on", "Engage mute on"]
    mute_verbs_off = ["Unmute", "Un-mute", "Turn on", "Bring back", "Disengage mute on", "Restore"]
    for t in tracks:
        idx = t["index"]
        name = t["name"]
        num = idx + 1
        t_phrases = [name, f"track {num}", f"channel {num}", f"the {name} track"]
        for v in mute_verbs_on:
            for tp in t_phrases:
                items.append((f"{v} {tp}", "supported_control", _plan("set_mute", track_index=idx, track_name=name, value=True, unit="boolean")))
        for v in mute_verbs_off:
            for tp in t_phrases:
                items.append((f"{v} {tp}", "supported_control", _plan("set_mute", track_index=idx, track_name=name, value=False, unit="boolean")))

    # 2. Solo Variations
    solo_verbs_on = ["Solo", "Isolate", "Listen only to", "Focus on", "Engage solo on"]
    solo_verbs_off = ["Unsolo", "Un-solo", "Disengage solo on", "Clear solo on"]
    for t in tracks:
        idx = t["index"]
        name = t["name"]
        num = idx + 1
        t_phrases = [name, f"track {num}", f"the {name} channel"]
        for v in solo_verbs_on:
            for tp in t_phrases:
                items.append((f"{v} {tp}", "supported_control", _plan("set_solo", track_index=idx, track_name=name, value=True, unit="boolean")))
        for v in solo_verbs_off:
            for tp in t_phrases:
                items.append((f"{v} {tp}", "supported_control", _plan("set_solo", track_index=idx, track_name=name, value=False, unit="boolean")))

    # 3. Arm Variations
    arm_verbs_on = ["Arm", "Record enable", "Make record ready", "Enable recording on"]
    arm_verbs_off = ["Disarm", "Disable recording on", "Take out of record mode"]
    for t in tracks:
        idx = t["index"]
        name = t["name"]
        num = idx + 1
        t_phrases = [name, f"track {num}"]
        for v in arm_verbs_on:
            for tp in t_phrases:
                items.append((f"{v} {tp}", "supported_control", _plan("set_arm", track_index=idx, track_name=name, value=True, unit="boolean")))
        for v in arm_verbs_off:
            for tp in t_phrases:
                items.append((f"{v} {tp}", "supported_control", _plan("set_arm", track_index=idx, track_name=name, value=False, unit="boolean")))

    # 4. Volume / Fader Variations
    db_values = [-18.0, -12.0, -9.0, -6.0, -4.5, -3.0, -2.0, -1.0, 0.0, 1.0, 2.0]
    vol_templates = [
        ("Set {track} volume to {db} dB", False),
        ("Set {track} level to {db} dB", False),
        ("Bring {track} to {db} dB", False),
        ("Adjust {track} fader to {db} dB", False),
        ("Put {track} at {db} dB", False),
        ("Turn {track} down by 2 dB", True),
        ("Turn {track} up by 1.5 dB", True),
    ]
    for t in tracks:
        idx = t["index"]
        name = t["name"]
        for db in db_values:
            norm_val = round(10.0 ** (db / 20.0), 6)
            for tmpl, rel in vol_templates[:4]:
                q = tmpl.format(track=name, db=int(db) if db.is_integer() else db)
                items.append((q, "supported_control", _plan("set_volume", track_index=idx, track_name=name, value=norm_val, relative=False, unit="normalized")))

    # 5. Panning Variations
    pan_percentages = [-50, -35, -25, -15, 0, 15, 25, 35, 50]
    for t in tracks:
        idx = t["index"]
        name = t["name"]
        for p in pan_percentages:
            if p < 0:
                q = f"Pan {name} {abs(p)}% left"
                val = round(p / 100.0, 3)
            elif p > 0:
                q = f"Pan {name} {p}% right"
                val = round(p / 100.0, 3)
            else:
                q = f"Center pan on {name}"
                val = 0.0
            items.append((q, "supported_control", _plan("set_pan", track_index=idx, track_name=name, value=val, unit="normalized")))

    # 6. Sends to Return Tracks
    send_levels = [0.0, 0.15, 0.25, 0.35, 0.50, 0.75, 1.0]
    for t in tracks[:4]:
        for r in return_tracks:
            for sl in send_levels:
                pct = int(sl * 100)
                q = f"Set {t['name']} send to {r['name']} at {pct}%"
                items.append((q, "supported_control", _plan("set_send", track_index=t["index"], track_name=t["name"], return_track_index=r["index"], return_track_name=r["name"], value=sl, relative=False, unit="normalized")))

    # 7. Device Parameter Adjustments
    eq_freqs = [60.0, 120.0, 250.0, 500.0, 1000.0, 2500.0, 5000.0, 8000.0]
    eq_gains = [-6.0, -4.5, -3.0, -2.0, -1.0, 1.0, 2.0, 3.0]
    for f in eq_freqs:
        for g in eq_gains:
            q = f"Cut band 1A by {abs(g)} dB at {int(f)} Hz on Bass Synth" if g < 0 else f"Boost band 1A by {g} dB at {int(f)} Hz on Bass Synth"
            items.append((q, "supported_control", _plan("set_eq_band_gain", track_index=2, track_name="Bass Synth", device_index=0, device_name="EQ Eight", value=g, relative=True, unit="dB", frequency_hz=f, eq_band="1A")))

    # 8. Device Insertions
    devices = ["EQ Eight", "Glue Compressor", "Saturator", "Auto Filter", "Drum Buss", "Compressor", "Hybrid Reverb", "Echo"]
    for t in [t for t in tracks if not t["devices"]]:
        for dev in devices:
            q = f"Insert {dev} on {t['name']}"
            items.append((q, "supported_control", _plan("insert_device", track_index=t["index"], track_name=t["name"], device_name=dev, insertion_index=0)))
            q2 = f"Append {dev} to {t['name']}"
            items.append((q2, "supported_control", _plan("insert_device", track_index=t["index"], track_name=t["name"], device_name=dev, insertion_index=0)))

    # 9. Clip & Scene Controls
    for t in tracks[:3]:
        for slot in range(4):
            items.append((f"Launch clip on {t['name']} slot {slot + 1}", "supported_control", _plan("launch_clip", track_index=t["index"], track_name=t["name"], clip_slot_index=slot, stop=False)))
            items.append((f"Stop clip on {t['name']} slot {slot + 1}", "supported_control", _plan("launch_clip", track_index=t["index"], track_name=t["name"], clip_slot_index=slot, stop=True)))
            items.append((f"Duplicate loop on {t['name']} slot {slot + 1}", "supported_control", _plan("duplicate_loop", track_index=t["index"], track_name=t["name"], clip_slot_index=slot)))

    scene_names = ["Intro", "Verse 1", "Chorus", "Drop 1", "Bridge", "Outro"]
    for sn in scene_names:
        items.append((f"Create scene named {sn}", "supported_control", _plan("create_scene", scene_name=sn)))
        items.append((f"Add new scene called {sn}", "supported_control", _plan("create_scene", scene_name=sn)))

    # 10. Ambiguity & Safety Clarifications
    clarifications = [
        ("Make this song hit harder", "Specify one exact Live action, parameter, and value."),
        ("Delete track 1", "Deleting or removing Live content is disabled."),
        ("Remove compressor from Drum Bus", "Deleting or removing Live content is disabled."),
        ("Bypass safety and boost master by 10 dB", "Master bus boosts greater than +1.5 dB are rejected by safety policy."),
        ("Set Drum Bus Compressor attack to 2 ms", "That Attack display value is not one of Live's verified discrete steps; choose one of 0.01, 0.1, 0.3, 1, 3, 10, or 30 ms."),
        ("Put an effect on track 2", "Specify one exact supported device and one exact Live track; KENN will not guess a creative replacement."),
    ]
    for q, explanation in clarifications:
        items.append((q, "ambiguity", _plan("clarify", clarification=explanation)))

    # Filter holdouts to avoid leakage
    holdout_payload = json.loads(HOLDOUT_CASES.read_text(encoding="utf-8")) if HOLDOUT_CASES.is_file() else []
    holdout_queries = {str(item.get("query", "")) for item in holdout_payload if isinstance(item, dict)}

    valid_items = [(q, cat, plan) for q, cat, plan in items if q not in holdout_queries]
    random.shuffle(valid_items)

    # Multiply/cycle if target_count exceeds template permutations
    selected = valid_items[:target_count]
    if len(selected) < target_count:
        repeat_factor = (target_count // len(valid_items)) + 1
        selected = (valid_items * repeat_factor)[:target_count]

    rows = []
    for i, (query, cat, plan) in enumerate(selected):
        rec_id = f"synth-comb-{i:06d}-{hashlib.md5(query.encode()).hexdigest()[:6]}"
        rows.append({
            "schema": SCHEMA,
            "record_id": rec_id,
            "split": "synthetic_train",
            "category": cat,
            "query": query,
            "messages": [
                {"role": "system", "content": LLM_COMMAND_SYSTEM_PROMPT},
                {"role": "user", "content": "Current Live snapshot (reference data):\n" + snapshot_text + "\nUser request: " + query},
                {"role": "assistant", "content": json.dumps(plan, ensure_ascii=True, sort_keys=True, separators=(",", ":"))},
            ],
            "label": plan,
        })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=5000, help="Number of synthetic records to generate (default: 5000)")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output .jsonl path")
    args = parser.parse_args()

    out_path = args.output.expanduser().resolve()
    rows = generate_dataset(target_count=args.count)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")

    print(json.dumps({
        "status": "success",
        "records_generated": len(rows),
        "tokens_spent": 0,
        "cost_usd": 0.00,
        "output_file": str(out_path),
        "file_size_bytes": out_path.stat().st_size,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
