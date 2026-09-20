#!/usr/bin/env python3
"""Install KENN's pinned AbletonOSC Remote Script into Ableton Live.

The vendored package is kept in ``integrations/ableton-osc`` so a fresh KENN
checkout can reproduce the Live-side runtime without cloning a moving branch.
The installer is intentionally conservative: replacing an existing package
requires ``--replace`` and the old package is moved to a sibling backup first.
"""

from __future__ import annotations

import argparse
import platform
import shutil
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIR = REPO_ROOT / "integrations" / "ableton-osc"
RUNTIME_FILES = ("__init__.py", "manager.py", "run-console.py")
RUNTIME_DIRS = ("abletonosc", "client", "pythonosc")


def _unique(paths: list[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.expanduser()
        if resolved not in seen:
            seen.add(resolved)
            result.append(resolved)
    return result


def _configured_remote_script_dirs() -> list[Path]:
    """Find User Library locations named in Live's local Library.cfg files."""
    if platform.system() != "Darwin":
        return []
    preferences = Path.home() / "Library" / "Preferences" / "Ableton"
    result: list[Path] = []
    for config in sorted(preferences.glob("Live*/Library.cfg")):
        try:
            root = ET.parse(config).getroot()
        except (ET.ParseError, OSError):
            continue
        for node in root.iter():
            if node.tag == "ProjectPath" and node.get("Value"):
                result.append(Path(node.get("Value", "")) / "User Library" / "Remote Scripts")
    return _unique(result)


def get_possible_remote_script_dirs() -> list[Path]:
    """Return configured and conventional Remote Scripts directories."""
    home = Path.home()
    if platform.system() == "Darwin":
        mounted = sorted(
            path
            for volume in Path("/Volumes").glob("*")
            for path in (volume / "User Library" / "Remote Scripts",)
            if path.is_dir()
        )
        candidates = [
            *_configured_remote_script_dirs(),
            *mounted,
            home / "Music" / "Ableton" / "User Library" / "Remote Scripts",
        ]
    elif platform.system() == "Windows":
        candidates = [home / "Documents" / "Ableton" / "User Library" / "Remote Scripts"]
    else:
        candidates = [home / "Ableton" / "User Library" / "Remote Scripts"]
    return _unique(candidates)


def select_default_target(paths: list[Path], *, repository_root: Path = REPO_ROOT) -> Path | None:
    """Choose a safe implicit target, or return ``None`` when ambiguous.

    A machine can retain several Ableton User Libraries across Live
    versions.  Picking the first existing directory can install a Remote
    Script where the running Live instance will never load it.  When KENN is
    itself on a mounted volume, prefer the one User Library on that same
    volume; otherwise require the caller to pass ``--target`` if more than one
    candidate exists.
    """
    existing = [path for path in paths if path.is_dir()]
    if len(existing) == 1:
        return existing[0]
    if not existing:
        return None
    root_parts = repository_root.resolve().parts
    if len(root_parts) >= 3 and root_parts[1] == "Volumes":
        same_volume = [path for path in existing if path.resolve().parts[:3] == root_parts[:3]]
        if len(same_volume) == 1:
            return same_volume[0]
    return None


def _copy_runtime(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    for name in RUNTIME_FILES:
        source_file = source / name
        if source_file.is_file():
            shutil.copy2(source_file, destination / name)
    for name in RUNTIME_DIRS:
        source_dir = source / name
        if source_dir.is_dir():
            shutil.copytree(
                source_dir,
                destination / name,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "logs"),
            )


def install_abletonosc(
    target_dir: Path,
    *,
    source_dir: Path = SOURCE_DIR,
    dry_run: bool = False,
    replace: bool = False,
) -> tuple[bool, str]:
    """Install the vendored runtime and return a user-readable result."""
    source_dir = source_dir.expanduser().resolve()
    target_dir = target_dir.expanduser().resolve()
    destination = target_dir / "AbletonOSC"
    if not (source_dir / "__init__.py").is_file() or not (source_dir / "abletonosc").is_dir():
        return False, f"AbletonOSC source is incomplete: {source_dir}"
    if destination.exists() and not replace:
        return False, f"{destination} already exists; rerun with --replace to preserve and replace it."
    if dry_run:
        replacement = f"; existing package would be backed up" if destination.exists() else ""
        return True, f"[DRY-RUN] Would install AbletonOSC to {destination}{replacement}."

    target_dir.mkdir(parents=True, exist_ok=True)
    backup = destination.with_name(destination.name + ".previous")
    if destination.exists():
        if backup.exists():
            backup = destination.with_name(destination.name + f".previous-{int(time.time())}")
        shutil.move(str(destination), str(backup))
    try:
        _copy_runtime(source_dir, destination)
    except Exception as exc:
        if destination.exists():
            shutil.rmtree(destination)
        if backup.exists():
            shutil.move(str(backup), str(destination))
        return False, f"Failed installing AbletonOSC: {exc}"
    backup_text = f" Previous package preserved at {backup}." if backup.exists() else ""
    return True, f"Installed AbletonOSC to {destination}.{backup_text}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Install KENN's pinned AbletonOSC Remote Script.")
    parser.add_argument("--target", type=Path, help="Remote Scripts directory; defaults to Live's configured User Library")
    parser.add_argument("--source", type=Path, default=SOURCE_DIR, help="AbletonOSC source directory")
    parser.add_argument("--replace", action="store_true", help="Move an existing package to a rollback backup before installing")
    parser.add_argument("--dry-run", action="store_true", help="Show the destination without copying files")
    parser.add_argument("--list-paths", action="store_true", help="List detected Remote Scripts directories and exit")
    args = parser.parse_args()

    paths = get_possible_remote_script_dirs()
    if args.list_paths:
        for path in paths:
            print(f"{'[EXISTS]' if path.exists() else '[NOT FOUND]'} {path}")
        return 0

    target = args.target.expanduser() if args.target else select_default_target(paths)
    if target is None:
        existing = [path for path in paths if path.is_dir()]
        if existing and not args.target:
            print("Multiple Ableton User Libraries were found; pass --target explicitly:", file=sys.stderr)
            for path in existing:
                print(f"  {path}", file=sys.stderr)
            return 2
        target = paths[0] if paths else None
    if target is None:
        print("Could not determine an Ableton Live Remote Scripts directory.", file=sys.stderr)
        return 1

    ok, message = install_abletonosc(target, source_dir=args.source, dry_run=args.dry_run, replace=args.replace)
    print(message)
    if ok:
        print("Restart Live, choose AbletonOSC in Preferences → Link / MIDI, and leave MIDI ports set to None.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
