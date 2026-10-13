"""Ableton Live project and render detector for KENN.

Detects the active Ableton Live project document (.als) and locates rendered
audio files, bounces, and mixdowns inside the project structure.
"""

from __future__ import annotations

import glob
import logging
import os
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger("kenn.ableton_project_detector")


def get_live_window_title() -> Optional[str]:
    """Query macOS Accessibility/System Events for Ableton Live's active standard document window."""
    try:
        import subprocess

        # Queries Live's standard document window (subrole AXStandardWindow).
        # Live 12 sets window 1's title to the active set name e.g. "Untitled" or "outer shell 2026-kenn-test".
        script = '''
tell application "System Events"
    if exists (process "Live") then
        tell process "Live"
            repeat with w in windows
                try
                    if subrole of w is "AXStandardWindow" then
                        return name of w as string
                    end if
                end try
            end repeat
            if (count of windows) > 0 then
                return name of window 1 as string
            end if
        end tell
    end if
end tell
return ""
'''
        res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=1.5)
        if res.returncode == 0 and res.stdout.strip():
            raw = res.stdout.strip()
            # Clean dirty indicator * and project brackets e.g. "outer shell 2026-kenn-test [outer shell 2026 Project]*"
            cleaned = re.sub(r"\s*\*+$", "", raw)
            cleaned = re.sub(r"\s*\[[^\]]+\]$", "", cleaned)
            cleaned = re.sub(r"\.als$", "", cleaned, flags=re.I)
            title = cleaned.strip()
            if title:
                return title
    except Exception as exc:
        logger.debug("Failed to query Live window title via osascript: %s", exc)
    return None


def detect_active_ableton_project() -> Optional[Dict[str, Any]]:
    """Detect the active Ableton Live project document (.als) and set metadata.

    First queries the running Live instance's active window title (macOS System Events).
    If Live is running an 'Untitled' set, returns an Untitled project without stale bounces.
    If Live has a saved project active, matches the window title against Live's Log.txt
    and common project roots. If Live is offline or non-macOS, falls back to the most
    recently loaded project from Log.txt.
    """
    active_title = get_live_window_title()

    # 1. Active Live session is open with an Untitled set
    if active_title and active_title.lower().startswith("untitled"):
        return {
            "als_path": "",
            "project_dir": "",
            "project_name": active_title,
            "is_saved": False,
        }

    pref_patterns = [
        os.path.expanduser("~/Library/Preferences/Ableton/Live 12*"),
        os.path.expanduser("~/Library/Preferences/Ableton/Live 11*"),
    ]
    log_dirs: List[str] = []
    for pattern in pref_patterns:
        log_dirs.extend(sorted(glob.glob(pattern), reverse=True))

    log_candidates: List[str] = []
    for log_dir in log_dirs:
        log_file = os.path.join(log_dir, "Log.txt")
        if not os.path.exists(log_file):
            continue
        try:
            # Read last 800 KB of log for performance
            with open(log_file, "r", errors="ignore") as f:
                lines = [line.strip() for line in f if "Loading document" in line]

            for line in reversed(lines):
                match = re.search(r'Loading document "([^"]+\.als)"', line)
                if not match:
                    continue
                als_path = match.group(1)
                # Ignore default templates and factory tracks
                if "DefaultLiveSet.als" in als_path or (
                    "Templates" in als_path and "Projects" not in als_path
                ):
                    continue
                if os.path.exists(als_path):
                    log_candidates.append(als_path)
        except Exception as exc:
            logger.debug("Failed to read Ableton log %s: %s", log_file, exc)

    # 2. If Live has a named saved set active, match against Log.txt or filesystem
    if active_title:
        target_clean = active_title.lower()
        for als_path in log_candidates:
            base = os.path.splitext(os.path.basename(als_path))[0].lower()
            if target_clean == base:
                return {
                    "als_path": als_path,
                    "project_dir": os.path.dirname(als_path),
                    "project_name": os.path.splitext(os.path.basename(als_path))[0],
                    "is_saved": True,
                }

        # Search standard Ableton project directories
        search_roots = [
            "/Volumes/Jack_Gandy_1TB_SSD/Ableton Projects",
            os.path.expanduser("~/Music/Ableton/Live Projects"),
            os.path.expanduser("~/Documents/Ableton"),
        ]
        for root in search_roots:
            if not os.path.isdir(root):
                continue
            cand_direct = os.path.join(root, f"{active_title}.als")
            if os.path.isfile(cand_direct):
                return {
                    "als_path": cand_direct,
                    "project_dir": os.path.dirname(cand_direct),
                    "project_name": active_title,
                    "is_saved": True,
                }
            cand_nested = os.path.join(root, f"{active_title} Project", f"{active_title}.als")
            if os.path.isfile(cand_nested):
                return {
                    "als_path": cand_nested,
                    "project_dir": os.path.dirname(cand_nested),
                    "project_name": active_title,
                    "is_saved": True,
                }

        # Named set but ALS file not yet located on disk
        return {
            "als_path": "",
            "project_dir": "",
            "project_name": active_title,
            "is_saved": False,
        }

    # 3. Live is offline/closed: fallback to the most recent loaded project in Log.txt
    if log_candidates:
        als_path = log_candidates[0]
        return {
            "als_path": als_path,
            "project_dir": os.path.dirname(als_path),
            "project_name": os.path.splitext(os.path.basename(als_path))[0],
            "is_saved": True,
        }

    return None


def _clean_bounce_label(filename: str) -> tuple[str, str]:
    """Return a tuple of (clean_display_label, kind) for an audio file."""
    name = filename
    name = re.sub(r"\.[a-zA-Z0-9]+$", "", name)  # strip extension
    name = re.sub(r"\s*\[[\d\s-]+\](-\d+)?$", "", name)  # strip [timestamp]-1
    name = re.sub(r"^\s*Bounce\s*", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s*\((Freeze|Bounce)\)", "", name)
    name = name.strip(" -_")

    lower = name.lower()
    if not name or lower in ("main", "master", "mix", "final", "outter", "outer"):
        return ("Master (Main Mix)", "master")
    return (f"Stem: {name}", "stem")


def find_project_bounces(project_dir: str) -> List[Dict[str, Any]]:
    """Locate master bounces, renders, and exported audio in an Ableton project.

    Searches the project root and standard Ableton bounce subdirectories
    ('Samples/Processed/Bounce', 'Bounces', 'Exports', 'Renders').
    """
    if not project_dir or not os.path.isdir(project_dir):
        return []

    search_dirs = [
        project_dir,
        os.path.join(project_dir, "Samples", "Processed", "Bounce"),
        os.path.join(project_dir, "Samples", "Processed", "Consolidate"),
        os.path.join(project_dir, "Bounces"),
        os.path.join(project_dir, "Exports"),
        os.path.join(project_dir, "Renders"),
    ]

    candidates: List[Dict[str, Any]] = []
    seen_paths = set()

    for directory in search_dirs:
        if not os.path.isdir(directory):
            continue
        try:
            for fname in os.listdir(directory):
                if fname.startswith("."):
                    continue
                lower = fname.lower()
                if not lower.endswith((".wav", ".aif", ".aiff")):
                    continue

                fpath = os.path.join(directory, fname)
                if fpath in seen_paths:
                    continue
                seen_paths.add(fpath)

                try:
                    stat = os.stat(fpath)
                    # Filter out tiny audio snippets under 500 KB to focus on full stems/bounces
                    if stat.st_size < 500 * 1024:
                        continue

                    label, kind = _clean_bounce_label(fname)
                    is_main = kind == "master"
                    candidates.append({
                        "filename": fname,
                        "label": label,
                        "kind": kind,
                        "path": fpath,
                        "size_bytes": stat.st_size,
                        "modified_time": stat.st_mtime,
                        "is_main_bounce": is_main,
                    })
                except OSError:
                    continue
        except OSError:
            continue

    # Masters first, then stems by newest modified time
    candidates.sort(
        key=lambda c: (1 if c["kind"] == "master" else 0, c["modified_time"]),
        reverse=True,
    )
    return candidates
