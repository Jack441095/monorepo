#!/usr/bin/env python3
"""Install the AudioToo_Bridge Ableton Remote Script into Live's User Library.

Ableton's User Library location is NOT fixed to the documented default --
it's whatever a user last configured in Preferences > File/Folder, and can
live anywhere (an external drive, a network share, etc). Jack's own machine
has it repointed to a non-default path, found the hard way by grepping
Ableton's own Log.txt. This script auto-detects the real, currently-in-use
path the same way rather than assuming the documented default, and only
falls back to that default (with a clear warning) if detection fails.

See docs/KENN_HUB_UNIFICATION_PLAN_2026-08-05.md, Phase 4, for the
"Ableton Remote Script distribution" open thread this closes.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REMOTE_SCRIPT_SRC = REPO_ROOT / "studio" / "kenn" / "remote_script" / "AudioToo_Bridge"
DEFAULT_USER_LIBRARY = Path.home() / "Music" / "Ableton" / "User Library"

# Ableton has no documented API or plain-text config exposing the
# currently-configured User Library path. The one reliable signal observed
# in practice: every "Message Box: file already exists" log entry embeds
# the real path a preset/rack was being saved into, which lives under the
# actual User Library root.
_LOG_PATH_RE = re.compile(r'"([^"]*User Library)[/\\]')


def ableton_log_files() -> list[Path]:
    """All per-version Ableton Log.txt files, most recently modified first."""
    prefs_root = Path.home() / "Library" / "Preferences" / "Ableton"
    if not prefs_root.is_dir():
        return []
    return sorted(
        prefs_root.glob("Live */Log.txt"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def detect_user_library(log_files: list[Path] | None = None) -> Path | None:
    """Best-effort auto-detection of the actual configured User Library path.

    Scans logs newest-first, and within each log favors the most recent
    matching line, so a stale reference to a since-abandoned library
    location doesn't win over the current one. Returns None if nothing
    resolvable was found -- callers should fall back to the documented
    default or ask the user explicitly.
    """
    for log_file in log_files if log_files is not None else ableton_log_files():
        try:
            text = log_file.read_text(errors="ignore")
        except OSError:
            continue
        matches = _LOG_PATH_RE.findall(text)
        for match in reversed(matches):
            candidate = Path(match)
            if candidate.is_dir():
                return candidate
    return None


def install(target_library: Path, *, dry_run: bool = False) -> Path:
    """Copy AudioToo_Bridge into <target_library>/Remote Scripts/."""
    dest = target_library / "Remote Scripts" / "AudioToo_Bridge"
    if dry_run:
        print(f"[DRY RUN] Would copy {REMOTE_SCRIPT_SRC} -> {dest}")
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(
        REMOTE_SCRIPT_SRC,
        dest,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    print(f"[OK] Installed AudioToo_Bridge to {dest}")
    return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target-dir",
        type=str,
        help="Explicit Ableton User Library path (skips auto-detection)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without copying any files",
    )
    args = parser.parse_args(argv)

    if not REMOTE_SCRIPT_SRC.is_dir():
        print(f"[ERROR] Remote script source not found at {REMOTE_SCRIPT_SRC}", file=sys.stderr)
        return 1

    if args.target_dir:
        target = Path(args.target_dir).expanduser()
        source = "explicit --target-dir"
    else:
        detected = detect_user_library()
        if detected:
            target = detected
            source = "auto-detected from Ableton's Log.txt"
        else:
            target = DEFAULT_USER_LIBRARY
            source = (
                "documented default -- auto-detection found nothing. If your "
                "Ableton User Library is repointed to a custom location, "
                "re-run with --target-dir pointing at it instead."
            )

    print(f"[INFO] Using User Library: {target}\n       ({source})")
    if not target.is_dir():
        print(
            f"[ERROR] {target} does not exist. Open Ableton once to create the "
            "default User Library, or pass --target-dir with the correct path.",
            file=sys.stderr,
        )
        return 1

    install(target, dry_run=args.dry_run)

    if not args.dry_run:
        print(
            "\nNext step: open Ableton Live > Preferences > Link, Tempo & MIDI > "
            "Control Surface, and select 'AudioToo_Bridge' from the dropdown. "
            "Restart Ableton first if it doesn't appear in the list."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
