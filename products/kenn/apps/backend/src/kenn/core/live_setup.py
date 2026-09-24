"""First-run setup for a tester's Mac: is Live ready for KENN, and install KENN's AbletonOSC.

Everything here runs inside the KENN app, without a terminal:

- ``setup_status()`` answers the three questions the setup page shows: is Ableton
  Live installed, is KENN's AbletonOSC Remote Script in Live's User Library (and
  the same version this app ships), and is Live connected right now;
- ``install_remote_script()`` copies the bundled AbletonOSC into the User Library.
  An existing copy is moved to a hidden ``.kenn-backups`` folder first, so Live
  never lists a stale backup as a control surface.

The User Library comes from the newest Live version's ``Library.cfg`` (Live
lets users move it, e.g. to an external drive), falling back to Live's default.
"""

from __future__ import annotations

import json
import re
import shutil
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kenn.core.abletonosc_bundle import SOURCE_DIR, STAMP_NAME, bundle_files, bundle_hash

PACKAGE_NAME = "AbletonOSC"


def _version_key(folder: Path) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", folder.name)) or (0,)


def live_apps(applications: Path = Path("/Applications")) -> list[Path]:
    return sorted(applications.glob("Ableton Live 12*.app"))


def user_library_remote_scripts(preferences: Path | None = None, home: Path | None = None) -> Path:
    """Remote Scripts folder of the User Library the newest Live uses."""
    home = home or Path.home()
    preferences = preferences or home / "Library" / "Preferences" / "Ableton"
    for folder in sorted(preferences.glob("Live 1*"), key=_version_key, reverse=True):
        config = folder / "Library.cfg"
        try:
            root = ET.parse(config).getroot()
        except (ET.ParseError, OSError):
            continue
        for node in root.iter("ProjectPath"):
            if node.get("Value"):
                return Path(node.get("Value", "")) / "User Library" / "Remote Scripts"
    return home / "Music" / "Ableton" / "User Library" / "Remote Scripts"


def installed_stamp(remote_scripts: Path) -> dict[str, Any] | None:
    try:
        return json.loads((remote_scripts / PACKAGE_NAME / "abletonosc" / STAMP_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def install_remote_script(remote_scripts: Path | None = None, *, source: Path = SOURCE_DIR) -> dict[str, Any]:
    """Copy the bundled AbletonOSC into Live's User Library (previous copy backed up)."""
    remote_scripts = remote_scripts or user_library_remote_scripts()
    if not (source / "__init__.py").is_file() or not (source / "abletonosc").is_dir():
        return {"ok": False, "error": f"The app's AbletonOSC copy is incomplete ({source})."}
    destination = remote_scripts / PACKAGE_NAME
    backup = None
    try:
        remote_scripts.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            backup = remote_scripts / ".kenn-backups" / f"{PACKAGE_NAME}-{time.strftime('%Y%m%d-%H%M%S')}"
            backup.parent.mkdir(exist_ok=True)
            shutil.move(str(destination), str(backup))
        # Exactly the deploy tool's file list, so both compute the same stamp.
        for relative in bundle_files(source):
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / relative, target)
        stamp = {"content_hash": bundle_hash(source), "git_commit": "kenn-app",
                 "deployed_at": datetime.now(timezone.utc).isoformat()}
        (destination / "abletonosc" / STAMP_NAME).write_text(json.dumps(stamp, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        if destination.exists() and backup is not None:
            shutil.rmtree(destination, ignore_errors=True)
            shutil.move(str(backup), str(destination))
        return {"ok": False, "error": f"Could not install AbletonOSC into {remote_scripts}: {exc}"}
    return {"ok": True, "installed_to": str(destination), "backup": str(backup) if backup else None,
            "next_step": "In Live, open Settings > Link, Tempo & MIDI and choose AbletonOSC as a Control Surface."}


def setup_status(live_client: Any = None, *, remote_scripts: Path | None = None) -> dict[str, Any]:
    """What the setup page shows: each check with a plain-English fix when it fails."""
    remote_scripts = remote_scripts or user_library_remote_scripts()
    apps = live_apps()
    stamp = installed_stamp(remote_scripts)
    expected = bundle_hash()
    installed = stamp is not None
    current = installed and stamp.get("content_hash") == expected
    connected = False
    if live_client is not None:
        try:
            connected = (live_client.probe_connection() or {}).get("status") == "connected"
        except Exception:
            connected = False
    checks = [
        {"id": "live_installed", "ok": bool(apps), "detail": apps[-1].name if apps else "",
         "fix": "" if apps else "Install Ableton Live 12 (Suite, Standard or Intro) in Applications."},
        {"id": "remote_script", "ok": current, "detail": str(remote_scripts / PACKAGE_NAME),
         "fix": "" if current else ("Update KENN's AbletonOSC (button below)." if installed
                                    else "Install KENN's AbletonOSC into Live (button below).")},
        {"id": "live_connected", "ok": connected, "detail": "",
         "fix": "" if connected else ("Open Live, then Settings > Link, Tempo & MIDI > Control Surface: choose AbletonOSC. "
                                      "Restart Live if you just installed it.")},
    ]
    return {"schema": "kenn.setup_status.v1", "ready": all(check["ok"] for check in checks),
            "remote_scripts": str(remote_scripts), "checks": checks}
