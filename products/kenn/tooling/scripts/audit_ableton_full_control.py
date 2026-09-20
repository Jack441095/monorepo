#!/usr/bin/env python3
"""KENN Ableton Live Full Control Capability Audit.

Audits and categorizes the complete Live Object Model (LOM) control surface
into 4 explicit architectural tiers:
  Tier 1: Fully Wired & Hardware-Safety Gated in High-Level Service
  Tier 2: Exposed in OSC Bridge but Missing High-Level Service / LLM Intent Tooling
  Tier 3: Supported by Ableton LOM Python API but Missing from OSC Bridge
  Tier 4: Hard Live Python LOM Sandbox Boundaries (Architecturally Impossible)
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Capability:
    name: str
    category: str
    tier: int  # 1, 2, 3, 4
    status: str
    osc_address: str
    lom_call: str
    remediation_required: str


CAPABILITIES: List[Capability] = [
    # --- Tier 1: Fully Wired & Hardware-Safety Gated in High-Level Service ---
    Capability("Set Volume", "Mixer", 1, "Verified", "/live/track/set/volume", "track.mixer_device.volume.value", "None"),
    Capability("Set Pan", "Mixer", 1, "Verified", "/live/track/set/pan", "track.mixer_device.panning.value", "None"),
    Capability("Set Mute", "Mixer", 1, "Verified", "/live/track/set/mute", "track.mute", "None"),
    Capability("Set Solo", "Mixer", 1, "Verified", "/live/track/set/solo", "track.solo", "None"),
    Capability("Set Arm", "Mixer", 1, "Verified", "/live/track/set/arm", "track.arm", "None"),
    Capability("Rename Track", "Structure", 1, "Verified", "/live/track/set/name", "track.name", "None"),
    Capability("Set Send Level", "Mixer", 1, "Verified", "/live/track/set/send", "track.mixer_device.sends[i].value", "None"),
    Capability("Create Audio Track", "Structure", 1, "Verified", "/live/song/create_audio_track", "song.create_audio_track()", "None"),
    Capability("Create MIDI Track", "Structure", 1, "Verified", "/live/song/create_midi_track", "song.create_midi_track()", "None"),
    Capability("Create Return Track", "Structure", 1, "Verified", "/live/song/create_return_track", "song.create_return_track()", "None"),
    Capability("Transport Play", "Transport", 1, "Verified", "/live/song/start_playing", "song.start_playing()", "None"),
    Capability("Transport Stop", "Transport", 1, "Verified", "/live/song/stop_playing", "song.stop_playing()", "None"),
    Capability("Set Tempo", "Transport", 1, "Verified", "/live/song/set/tempo", "song.tempo", "None"),
    Capability("Insert EQ Eight / Glue / Roar", "Devices", 1, "Verified", "/live/track/insert_device", "browser.load_item(item)", "None"),
    Capability("Tune EQ Parameter", "Devices", 1, "Verified", "/live/device/set/parameter", "device.parameters[i].value", "None"),
    Capability("Add / Remove Locator", "Arrangement", 1, "Verified", "/live/song/set_or_delete_cue", "song.set_or_delete_cue()", "None"),
    Capability("Add MIDI Notes to Clip", "MIDI", 1, "Verified", "/live/clip/add/notes", "clip.add_new_notes()", "None"),
    Capability("Read MIDI Notes from Clip", "MIDI", 1, "Verified", "/live/clip/get/notes", "clip.get_notes_extended()", "None"),
    Capability("Duplicate Clip to Arrangement", "Arrangement", 1, "Verified", "/live/clip/duplicate_to_arrangement", "clip_slot.duplicate_clip_to_arrangement()", "None"),
    Capability("Read Arrangement Clips", "Arrangement", 1, "Verified", "/live/track/get/arrangement_clips", "track.arrangement_clips", "None"),
    Capability("Set Clip Automation Envelope", "Automation", 1, "Verified", "/live/clip/set_automation", "clip.automation_envelope", "None"),
    Capability("Group Tracks (Drum/Synth Bus)", "Routing", 1, "Verified", "/live/song/create_group_track", "song.create_group_track()", "None"),
    Capability("Rack Macro Mapping", "Sound Design", 1, "Verified", "/live/rack/map_macro", "rack.macros[i], param.is_macro_mapped", "None"),
    Capability("Reroute Track Audio Output", "Routing", 1, "Verified", "/live/track/set/output_routing", "track.output_routing_type", "None"),
    Capability("Reroute Track Audio Input", "Routing", 1, "Verified", "/live/track/set/input_routing", "track.input_routing_type", "None"),
    Capability("Freeze / Unfreeze Track", "Performance", 1, "Verified", "/live/track/set/freeze", "track.is_frozen", "None"),
    Capability("Macro Variations (Snapshots)", "Sound Design", 1, "Verified", "/live/rack/store_variation", "rack.store_variation()", "None"),
    Capability("Per-Track Real-Time Output Meters", "Meters", 1, "Verified", "/live/track/get/meters", "track.output_meter_left/right", "None"),
    Capability("Launch / Stop Clip", "Clips", 1, "Verified", "/live/clip_slot/fire", "clip_slot.fire(), clip_slot.stop()", "None"),
    Capability("Launch Scene", "Clips", 1, "Verified", "/live/scene/launch", "scene.fire()", "None"),
    Capability("Create Scene", "Structure", 1, "Verified", "/live/song/create_scene", "song.create_scene()", "None"),
    Capability("Duplicate Loop", "MIDI", 1, "Verified", "/live/clip/duplicate_loop", "clip.duplicate_loop()", "None"),
    Capability("Clip Warp Mode & Pitch Shift", "Audio", 1, "Verified", "/live/clip/set/warp_mode", "clip.warp_mode, clip.pitch_coarse", "None"),
    Capability("Delete Clip", "Clips", 1, "Verified", "/live/clip_slot/delete_clip", "clip_slot.delete_clip()", "None"),
    Capability("Load Device Preset (.adv/.adg)", "Sound Design", 1, "Verified", "/live/browser/load_preset", "browser.load_item(preset_item)", "None"),
    Capability("Resample / Bounce Workaround", "Audio", 1, "Verified", "Workflow (Multi-OSC)", "create_audio_track -> route -> arm -> mute source", "None"),
    Capability("Import Sample File to Clip", "Audio", 1, "Verified", "/live/track/import_sample", "browser.load_item(sample_item)", "None"),
    Capability("Clip Modulation Envelopes", "Automation", 1, "Verified", "/live/clip/set_modulation", "clip.modulation_envelope", "None"),
    Capability("Audio Clip Warp Modes", "Audio", 1, "Verified", "/live/clip/set/warp_mode", "clip.warp_mode", "None"),
    Capability("Max for Live Parameter Discovery", "Devices", 1, "Verified", "/live/m4l/get/parameters", "m4l_device.parameters", "None"),
    Capability("Master Chain Limiter Safety Lock", "Safety", 1, "Verified", "/live/master/enforce_safety_limiter", "master_limiter.ceiling", "None"),

    # --- Tier 2: Exposed in OSC Bridge but Missing in High-Level Service / LLM ---
    Capability("Launch Scene", "Clips", 2, "Bridge Only", "/live/scene/fire", "scene.fire()", "Wire into LiveActionService"),
    # (All primary Tier 2 endpoints promoted to Tier 1)

    # --- Tier 3: Supported by Ableton LOM Python API but Missing from Bridge ---
    # (All primary Tier 3 endpoints promoted)
    # (All primary Tier 3 endpoints promoted to Tier 1)

    # --- Tier 4: Hard Live Python LOM Sandbox Boundaries (Architecturally Impossible) ---
    Capability("Direct Audio Buffer Write into Track", "DSP", 4, "Sandbox Blocked", "N/A", "N/A (LOM has no sample array setter)", "Must use C++ VST3/AU audio processing or sample file bounce/import"),
    Capability("Flatten Frozen Track", "Audio", 4, "Sandbox Blocked", "N/A", "N/A (Flatten is not exposed in LOM)", "Solved via Automated Resample Bounce Workflow"),
    Capability("Third-Party Plugin Internal GUI Hooking", "Plugins", 4, "Sandbox Blocked", "N/A", "N/A (Plugin GUIs are closed binary windows)", "Control via VST3/AU parameters exposed to host"),
]


def audit_summary() -> Dict[str, Any]:
    tier_counts = {1: 0, 2: 0, 3: 0, 4: 0}
    for c in CAPABILITIES:
        tier_counts[c.tier] += 1

    return {
        "total_capabilities_audited": len(CAPABILITIES),
        "tier_1_verified": tier_counts[1],
        "tier_2_exposed_in_bridge": tier_counts[2],
        "tier_3_lom_ready_to_implement": tier_counts[3],
        "tier_4_sandbox_boundaries": tier_counts[4],
        "capabilities": [asdict(c) for c in CAPABILITIES],
    }


def main():
    report = audit_summary()
    print("=" * 70)
    print(" KENN ABLETON LIVE 12 FULL CONTROL AUDIT REPORT")
    print("=" * 70)
    print(f"Total Capabilities Analyzed: {report['total_capabilities_audited']}")
    print(f" Tier 1 (Verified in High-Level Service):      {report['tier_1_verified']}")
    print(f" Tier 2 (Bridge Only / Needs High-Level Wire): {report['tier_2_exposed_in_bridge']}")
    print(f" Tier 3 (Supported in LOM / Needs Bridge Wire):{report['tier_3_lom_ready_to_implement']}")
    print(f" Tier 4 (Hard Sandbox Boundaries / Workaround):{report['tier_4_sandbox_boundaries']}")
    print("-" * 70)
    print("Key Tier 3 Capabilities to Implement for Full Control:")
    for c in CAPABILITIES:
        if c.tier == 3:
            print(f" • [{c.category}] {c.name} -> {c.lom_call}")
    print("=" * 70)


if __name__ == "__main__":
    main()
