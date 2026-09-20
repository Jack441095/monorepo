"""Canonical locations and non-destructive migration for Thursday runtime state."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent


def state_root() -> Path:
    """Return Thursday's external state root, honoring explicit overrides."""
    configured = os.environ.get("THURSDAY_STATE_DIR") or os.environ.get("AUDIO_TOO_STATE_DIR")
    if configured:
        base = Path(configured).expanduser()
        return base if os.environ.get("THURSDAY_STATE_DIR") else base / "thursday"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Audio_Too" / "thursday"
    if os.name == "nt":
        appdata = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        base = Path(appdata).expanduser() if appdata else Path.home() / "AppData" / "Local"
        return base / "Audio_Too" / "thursday"
    xdg = os.environ.get("XDG_STATE_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".local" / "state"
    return base / "audio-too" / "thursday"


def runtime_dir(name: str, env_var: str) -> Path:
    configured = os.environ.get(env_var, "").strip()
    return Path(configured).expanduser() if configured else state_root() / name


DATA_DIR = runtime_dir("user_data", "THURSDAY_DATA_DIR")
PROFILE_DIR = runtime_dir("profiles", "THURSDAY_PROFILE_DIR")
ANALYTICS_DIR = runtime_dir("analytics", "THURSDAY_ANALYTICS_DIR")
SESSION_DIR = runtime_dir("sessions", "THURSDAY_SESSION_DIR")
ALERTS_DIR = runtime_dir("alerts", "THURSDAY_ALERTS_DIR")
CALENDAR_DIR = runtime_dir("calendar_data", "THURSDAY_CALENDAR_DIR")
LOG_DIR = runtime_dir("logs", "THURSDAY_LOG_DIR")
MEMORY_DIR = runtime_dir("memory", "THURSDAY_MEMORY_DIR")
DOC_SEARCH_INDEX_DIR = runtime_dir("doc_search_index", "THURSDAY_DOC_SEARCH_INDEX_DIR")
BRIEFING_STAMP = state_root() / ".last_briefing.txt"
SESSION_FILE = Path(
    os.environ.get("THURSDAY_SESSION_FILE", str(state_root() / "current_session"))
).expanduser()

_LEGACY_DIRS = (
    "user_data",
    "profiles",
    "analytics",
    "sessions",
    "alerts",
    "calendar_data",
)


def _copy_missing(source: Path, destination: Path) -> int:
    copied = 0
    if not source.exists() or source.is_symlink():
        return copied
    if source.is_file():
        if not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            copied += 1
        return copied
    for item in sorted(source.rglob("*")):
        if not item.is_file() or item.is_symlink():
            continue
        target = destination / item.relative_to(source)
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)
        copied += 1
    return copied


def migrate_legacy_state(*, legacy_root: Path = PACKAGE_DIR) -> int:
    """Copy legacy in-repo state into the external tree without overwriting data.

    Source files are deliberately retained. This makes migration reversible and
    prevents an upgrade from deleting user-owned state.
    """
    destinations = {
        "user_data": DATA_DIR,
        "profiles": PROFILE_DIR,
        "analytics": ANALYTICS_DIR,
        "sessions": SESSION_DIR,
        "alerts": ALERTS_DIR,
        "calendar_data": CALENDAR_DIR,
    }
    copied = sum(
        _copy_missing(legacy_root / name, destinations[name]) for name in _LEGACY_DIRS
    )
    copied += _copy_missing(legacy_root / ".last_briefing.txt", BRIEFING_STAMP)
    copied += _copy_missing(Path.home() / ".audio_too_session", SESSION_FILE)
    return copied


def ensure_runtime_state() -> int:
    """Create the state root and perform the safe legacy import once per process."""
    state_root().mkdir(parents=True, exist_ok=True)
    return migrate_legacy_state()
