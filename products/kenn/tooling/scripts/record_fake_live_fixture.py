#!/usr/bin/env python3
"""Record the open Live set into a replayable fixture for KENN's fake backend.

Read-only: it never writes to Live. Stop the KENN companion first, because
AbletonOSC replies on UDP 11001. Pan, volume, and selection are normalised to
the investor-demo reset state unless ``--as-is`` is given, so a recording made
after a rehearsal still replays the reset fixture.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

KENN_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(KENN_ROOT / "apps" / "backend" / "src"))

from kenn.ableton_osc_bridge import AbletonOSCClient  # noqa: E402

DEFAULT_OUT = KENN_ROOT / "apps" / "backend" / "src" / "kenn" / "core" / "fake_live_fixtures" / "investor_demo.json"
DEMO_SELECTED_TRACK = 3  # Drum Bus


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--as-is", action="store_true", help="keep current mixer and selection values")
    args = parser.parse_args()

    client = AbletonOSCClient()
    probe = client.probe_connection()
    if probe.get("status") != "connected":
        print(json.dumps({"status": "refused", "reason": "Live not reachable", "probe": probe}, indent=2))
        return 2

    state = client.query_session_state(include_mixer=True, force_refresh=True)
    returns, returns_available = client.get_return_tracks_with_status()
    devices: dict[str, dict] = {}
    for track in state.get("tracks", []):
        t = int(track["index"])
        for d, _device in enumerate(track.get("devices") or []):
            info = client.get_device_parameters(t, d)
            if not info.get("success"):
                continue
            for parameter in info["parameters"]:
                shown = client.get_device_parameter_value_string(t, d, int(parameter["index"]))
                parameter["value_display"] = shown.get("value_string") if shown.get("success") else None
            devices[f"{t}:{d}"] = info
    sends = {
        str(track["index"]): [client.get_track_send(int(track["index"]), s) for s in range(len(returns))]
        for track in state.get("tracks", [])
    }

    world: dict[str, dict] = {}

    def keep(key: str, result: dict) -> None:
        if isinstance(result, dict) and result.get("success"):
            world[key] = {k: v for k, v in result.items() if k != "success"}

    for track in state.get("tracks", []):
        keep(f"device_tree:track:{int(track['index'])}", client.get_device_tree("track", int(track["index"])))
    buses = [("return", int(r["index"]), len(r.get("devices") or [])) for r in returns] + [("master", -1, None)]
    for kind, index, _count in buses:
        mixer = client.get_bus_mixer(kind, index)
        keep(f"bus_mixer:{kind}:{index}", mixer)
        keep(f"device_tree:{kind}:{index}", client.get_device_tree(kind, index))
        for device_index in range(len(mixer.get("devices") or [])):
            keep(f"device_parameters:{kind}:{index}:{device_index}",
                 client.get_bus_device_parameters(kind, index, device_index))

    if not args.as_is:
        for track in state.get("tracks", []):
            track["pan"] = 0.0
        state["selected_track_index"] = DEMO_SELECTED_TRACK

    fixture = {
        "schema": "kenn.fake_live_fixture.v1",
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "normalised_to_reset": not args.as_is,
        "session": state,
        "return_tracks": returns if returns_available else [],
        "devices": devices,
        "sends": sends,
        "selected_device": {"track_index": DEMO_SELECTED_TRACK, "device_index": 0},
        "world": world,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(fixture, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "recorded",
        "out": str(args.out),
        "tracks": [t.get("name") for t in state.get("tracks", [])],
        "devices": {k: v.get("device_name") for k, v in devices.items()},
        "returns": [r.get("name") for r in returns],
        "world_sections": sorted(world),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
