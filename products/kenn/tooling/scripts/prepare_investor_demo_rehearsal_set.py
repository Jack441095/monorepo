#!/usr/bin/env python3
"""Place the Neon Proof stems into the open disposable investor-demo set.

Plan-only unless ``--apply``. Apply mode requires the open Live set to match the
reset fixture exactly (eight named tracks, empty arrangements, devices intact).
Kick and Synth are MIDI tracks in the fixture; each is replaced in place by an
audio track with the same name after verifying it carries no devices. Every
stem is placed at beat 0 through AbletonOSC's Places-allowlisted
``/live/track/import_arrangement_audio`` and read back. Live has no save API:
the operator saves the disposable copy afterwards.

Live's Browser does not list Places inside hidden folders such as
``.runtime``, so ``--stem-dir`` may point at a visible Place; every file there
must match the manifest SHA-256 before anything is imported.

Stop the KENN companion first: AbletonOSC replies on UDP 11001.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

KENN_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(KENN_ROOT / "integrations" / "ableton-osc"))

from client.client import AbletonOSCClient  # noqa: E402

AUDIO_DIR = KENN_ROOT / ".runtime" / "investor-demo-audio"
MIDI_TO_AUDIO = ("Kick", "Synth")
TIMEOUT = 3.0


def _q(client: AbletonOSCClient, address: str, *params):
    return client.query(address, tuple(params), timeout=TIMEOUT)


def _tracks(client: AbletonOSCClient) -> list[dict]:
    count = int(_q(client, "/live/song/get/num_tracks")[0])
    rows = []
    for i in range(count):
        rows.append({
            "index": i,
            "name": _q(client, "/live/track/get/name", i)[1],
            "audio": bool(_q(client, "/live/track/get/has_audio_input", i)[1]),
            "devices": list(_q(client, "/live/track/get/devices/name", i)[1:]),
            "clips": list(_q(client, "/live/track/get/arrangement_clips/name", i)[1:]),
        })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="mutate the open disposable set")
    parser.add_argument("--stem-dir", type=Path, default=AUDIO_DIR,
                        help="Place-visible folder holding manifest-identical stems")
    args = parser.parse_args()

    manifest = json.loads((AUDIO_DIR / "manifest.json").read_text())
    stems = [f for f in manifest["files"] if f["role"] == "ableton_stem"]
    expected = [f["track_name"] for f in stems]

    client = AbletonOSCClient()
    try:
        before = _tracks(client)
        problems = []
        if [t["name"] for t in before] != expected:
            problems.append(f"track names {[t['name'] for t in before]} != fixture {expected}")
        if any(t["clips"] for t in before):
            problems.append("arrangement already contains clips")
        for t in before:
            if t["name"] in MIDI_TO_AUDIO and t["devices"]:
                problems.append(f"{t['name']} carries devices; refusing to replace it")
        stem_dir = args.stem_dir.resolve()
        for f in stems:
            path = stem_dir / f["path"]
            if not path.is_file():
                problems.append(f"missing stem: {path}")
            elif hashlib.sha256(path.read_bytes()).hexdigest() != f["sha256"]:
                problems.append(f"hash mismatch vs manifest: {path}")
        if problems:
            print(json.dumps({"status": "refused", "problems": problems}, indent=2))
            return 2

        plan = [
            {"index": t["index"], "track": t["name"],
             "replace_midi_with_audio": not t["audio"], "stem": s["path"]}
            for t, s in zip(before, stems)
        ]
        if not args.apply:
            print(json.dumps({"status": "plan_only", "plan": plan}, indent=2))
            return 0

        for step in plan:
            if step["replace_midi_with_audio"]:
                i = step["index"]
                client.send_message("/live/song/create_audio_track", (i + 1,))
                time.sleep(0.4)
                client.send_message("/live/song/delete_track", (i,))
                time.sleep(0.4)
                client.send_message("/live/track/set/name", (i, step["track"]))
                time.sleep(0.2)

        results = []
        for step in plan:
            path = str(stem_dir / step["stem"])
            reply = client.query(
                "/live/track/import_arrangement_audio", (step["index"], 0.0, path), timeout=15.0
            )
            results.append({"track": step["track"], "ok": bool(reply[2]), "detail": reply[3]})

        after = _tracks(client)
        devices_before = {t["name"]: t["devices"] for t in before}
        checks = {
            "names_match": [t["name"] for t in after] == expected,
            "all_audio": all(t["audio"] for t in after),
            "one_clip_each": all(len(t["clips"]) == 1 for t in after),
            "devices_preserved": all(t["devices"] == devices_before[t["name"]] for t in after),
            "imports_ok": all(r["ok"] for r in results),
        }
        status = "passed" if all(checks.values()) else "failed"
        print(json.dumps({"status": status, "checks": checks, "imports": results,
                          "after": after}, indent=2))
        return 0 if status == "passed" else 1
    finally:
        client.stop()


if __name__ == "__main__":
    raise SystemExit(main())
