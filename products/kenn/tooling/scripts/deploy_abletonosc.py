#!/usr/bin/env python3
"""Deploy the repo's AbletonOSC Remote Script into Live's User Library.

Plan-only by default: prints what differs. ``--apply`` backs the installed copy
up under ``.runtime/``, copies changed files, clears ``__pycache__`` and writes a
deploy stamp. ``--reload`` then asks the running Live to hot-reload AbletonOSC
(no restart) and checks ``/live/kenn/version`` through the KENN companion.
Files outside AbletonOSC's reload list still need a Live restart; the tool
says so rather than claiming they are live.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from abletonosc_bundle import HOT_RELOADABLE, SOURCE_DIR, STAMP_RELATIVE, bundle_files, bundle_hash  # noqa: E402

KENN_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TARGET = Path(os.environ.get(
    "KENN_ABLETONOSC_TARGET", "/Volumes/Jack_Gandy_1TB_SSD/User Library/Remote Scripts/AbletonOSC"
))


def _plan(target: Path) -> dict[str, list[str]]:
    changed, new = [], []
    for relative in bundle_files(SOURCE_DIR):
        installed = target / relative
        if not installed.is_file():
            new.append(relative)
        elif installed.read_bytes() != (SOURCE_DIR / relative).read_bytes():
            changed.append(relative)
    installed_only = [r for r in bundle_files(target) if r not in set(bundle_files(SOURCE_DIR))]
    return {"changed": changed, "new": new, "installed_only": installed_only}


def _git_commit() -> str:
    try:
        return subprocess.run(["git", "-C", str(KENN_ROOT), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _send_reload() -> None:
    sys.path.insert(0, str(SOURCE_DIR))
    from pythonosc.udp_client import SimpleUDPClient

    SimpleUDPClient("127.0.0.1", 11000).send_message("/live/api/reload", [])


def _running_version(companion: str) -> dict:
    with urllib.request.urlopen(companion.rstrip("/") + "/api/ableton/remote-script", timeout=5) as response:
        return json.loads(response.read())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--apply", action="store_true", help="back up, copy, and stamp the installed script")
    parser.add_argument("--reload", action="store_true", help="hot-reload AbletonOSC in the running Live after --apply")
    parser.add_argument("--companion", default="http://127.0.0.1:8090")
    args = parser.parse_args()

    target = args.target
    if not (target / "abletonosc").is_dir():
        print(json.dumps({"status": "refused", "reason": f"No installed AbletonOSC at {target}"}, indent=2))
        return 2
    plan = _plan(target)
    touched = plan["changed"] + plan["new"]
    restart_needed = sorted(r for r in touched if r not in HOT_RELOADABLE)
    report: dict = {"target": str(target), "repo_hash": bundle_hash(), **plan, "restart_required_for": restart_needed}
    if not args.apply:
        print(json.dumps({"status": "plan_only", **report}, indent=2))
        return 0

    backup = KENN_ROOT / ".runtime" / f"remote-script-backup-{time.strftime('%Y%m%d-%H%M%S')}"
    shutil.copytree(target, backup, ignore=shutil.ignore_patterns("logs", "__pycache__"))
    for relative in touched:
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SOURCE_DIR / relative, destination)
    for cache in target.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)
    stamp = {"content_hash": bundle_hash(), "git_commit": _git_commit(),
             "deployed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    (target / STAMP_RELATIVE).write_text(json.dumps(stamp, indent=2) + "\n", encoding="utf-8")
    report.update({"status": "applied", "backup": str(backup), "stamp": stamp, "installed_hash": bundle_hash(target)})

    if args.reload:
        _send_reload()
        time.sleep(1.5)
        try:
            running = _running_version(args.companion)
        except Exception as exc:  # companion may be down; report instead of failing the deploy
            running = {"success": False, "error": str(exc)}
        report["running"] = running
        report["running_matches_repo"] = running.get("content_hash") == stamp["content_hash"]
        if restart_needed:
            report["note"] = "Some changed files are not hot-reloadable; restart Live for them to take effect."
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
