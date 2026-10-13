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


def detect_active_ableton_project() -> Optional[Dict[str, Any]]:
    """Scan Live's preferences log to find the most recently loaded project set.

    Live 12 writes 'Loading document "<path>"' to Log.txt on project open. We
    filter out built-in template files to identify the operator's active project.
    """
    pref_patterns = [
        os.path.expanduser("~/Library/Preferences/Ableton/Live 12*"),
        os.path.expanduser("~/Library/Preferences/Ableton/Live 11*"),
    ]
    log_dirs: List[str] = []
    for pattern in pref_patterns:
        log_dirs.extend(sorted(glob.glob(pattern), reverse=True))

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
                if not os.path.exists(als_path):
                    continue

                project_dir = os.path.dirname(als_path)
                project_name = os.path.splitext(os.path.basename(als_path))[0]
                return {
                    "als_path": als_path,
                    "project_dir": project_dir,
                    "project_name": project_name,
                }
        except Exception as exc:
            logger.debug("Failed to read Ableton log %s: %s", log_file, exc)

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
