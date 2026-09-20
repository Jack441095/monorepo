#!/usr/bin/env python3
"""Automated Ableton Live 12 Remote Script Installer for KENN.

Locates local Ableton Live Remote Scripts directories on macOS and Windows,
installs the KENN_Bridge Remote Script package, and provides step-by-step
activation instructions for Ableton Live.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_BRIDGE_DIR = REPO_ROOT / "integrations" / "ableton-remote-script" / "KENN_Bridge"



def get_possible_remote_script_dirs() -> list[Path]:
    """Return standard search paths for Ableton Live Remote Scripts by OS."""
    system = platform.system()
    home = Path.home()
    dirs: list[Path] = []

    if system == "Darwin":  # macOS
        # Live may use a User Library on a mounted volume. Prefer a mounted
        # library that already contains the legacy bridge or KENN_Bridge so a
        # replacement install follows Live's existing configuration instead
        # of silently landing in the home-folder library.
        mounted_libraries = sorted(
            path
            for volume in Path("/Volumes").glob("*")
            for path in (volume / "User Library" / "Remote Scripts",)
            if path.is_dir()
            and (
                (path / "AudioToo_Bridge").is_dir()
                or (path / "KENN_Bridge").is_dir()
            )
        )
        dirs.extend(mounted_libraries)

        # User Library (primary user-facing location)
        user_lib = home / "Music" / "Ableton" / "User Library" / "Remote Scripts"
        dirs.append(user_lib)

        # Standalone application bundles
        app_bundles = [
            Path("/Applications/Ableton Live 12 Suite.app/Contents/App-Resources/MIDI Remote Scripts"),
            Path("/Applications/Ableton Live 12 Standard.app/Contents/App-Resources/MIDI Remote Scripts"),
            Path("/Applications/Ableton Live 12 Intro.app/Contents/App-Resources/MIDI Remote Scripts"),
            Path("/Applications/Ableton Live 11 Suite.app/Contents/App-Resources/MIDI Remote Scripts"),
        ]
        dirs.extend([p for p in app_bundles if p.parent.exists()])

    elif system == "Windows":
        # Windows User Library
        win_user_lib = home / "Documents" / "Ableton" / "User Library" / "Remote Scripts"
        dirs.append(win_user_lib)

        # Windows AppData
        appdata = os.environ.get("APPDATA")
        if appdata:
            win_appdata = Path(appdata) / "Ableton"
            dirs.append(win_appdata)

    else:
        # Linux is not an officially supported Live desktop target, but this
        # fallback keeps discovery deterministic for headless regression
        # environments and Linux-based development hosts.
        dirs.append(home / "Ableton" / "User Library" / "Remote Scripts")

    return dirs


def install_bridge(target_dir: Path, *, dry_run: bool = False) -> tuple[bool, str]:
    """Copy KENN_Bridge source files into target Remote Scripts directory."""
    if not SOURCE_BRIDGE_DIR.exists():
        return False, f"Source bridge directory not found at: {SOURCE_BRIDGE_DIR}"

    dest_dir = target_dir / "KENN_Bridge"

    if dry_run:
        return True, f"[DRY-RUN] Would install KENN_Bridge to: {dest_dir}"

    try:
        dest_dir.parent.mkdir(parents=True, exist_ok=True)
        if dest_dir.exists():
            shutil.rmtree(dest_dir)

        shutil.copytree(
            SOURCE_BRIDGE_DIR,
            dest_dir,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        return True, f"Successfully installed KENN_Bridge to:\n  {dest_dir}"
    except Exception as exc:
        return False, f"Failed installing to {dest_dir}: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Install KENN Ableton Live 12 Remote Script (KENN_Bridge).")
    parser.add_argument("--target", type=Path, help="Explicit target directory for Remote Scripts")
    parser.add_argument("--dry-run", action="store_true", help="Print destination without copying files")
    parser.add_argument("--list-paths", action="store_true", help="List detected Remote Script search paths and exit")
    args = parser.parse_args()

    print("=========================================================")
    print(" KENN Ableton Live 12 Remote Script Installer")
    print("=========================================================\n")

    possible_dirs = get_possible_remote_script_dirs()

    if args.list_paths:
        print("Detected search locations:")
        for p in possible_dirs:
            exists_str = "[EXISTS]" if p.exists() else "[NOT FOUND]"
            print(f"  {exists_str} {p}")
        return 0

    target_dir: Path | None = args.target

    if not target_dir:
        # Pick the first existing path, or default to primary User Library
        for p in possible_dirs:
            if p.exists():
                target_dir = p
                break
        if not target_dir and possible_dirs:
            target_dir = possible_dirs[0]

    if not target_dir:
        print("ERROR: Could not locate a valid Remote Scripts directory.")
        print("Please specify one explicitly using --target <directory>.")
        return 1

    print(f"Target Remote Scripts location: {target_dir}")
    success, msg = install_bridge(target_dir, dry_run=args.dry_run)
    print(msg)

    if not success:
        return 1

    print("\n---------------------------------------------------------")
    print(" Ableton Live 12 Activation Instructions:")
    print("---------------------------------------------------------")
    print(" 1. Open Ableton Live 12.")
    print(" 2. Open Preferences (Cmd + , on Mac / Ctrl + , on Windows).")
    print(" 3. Select the 'Link / MIDI' tab.")
    print(" 4. In the 'Control Surface' dropdown list, select 'KENN_Bridge'.")
    print(" 5. Leave Input and Output ports set to 'None' (the bridge uses")
    print("    local UDP network sockets on port 11000).")
    print(" 6. KENN is now connected to your active session!\n")


    return 0


if __name__ == "__main__":
    sys.exit(main())
