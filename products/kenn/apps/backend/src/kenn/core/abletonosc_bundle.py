"""Which files make up KENN's AbletonOSC Remote Script, and their content hash.

Shared by the deploy tool, the demo preflight and the app's first-run setup so "what is deployed" and
"what the repo expects" are computed the same way.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from kenn.paths import INTEGRATIONS_ROOT

SOURCE_DIR = INTEGRATIONS_ROOT / "ableton-osc"
STAMP_NAME = "kenn_deploy_stamp.json"
STAMP_RELATIVE = f"abletonosc/{STAMP_NAME}"

_EXCLUDED_DIRS = {"tests", "client", "logs", "__pycache__", ".git", ".github"}
_EXCLUDED_FILES = {"run-console.py", ".DS_Store", ".gitignore"}

# AbletonOSC's /live/api/reload re-imports only these modules; any other
# changed file needs a Live restart to take effect.
HOT_RELOADABLE = {
    "abletonosc/application.py", "abletonosc/clip.py", "abletonosc/clip_slot.py",
    "abletonosc/device.py", "abletonosc/handler.py", "abletonosc/osc_server.py",
    "abletonosc/scene.py", "abletonosc/song.py", "abletonosc/track.py", "abletonosc/view.py",
    "abletonosc/__init__.py",
}


def bundle_files(root: Path = SOURCE_DIR) -> list[str]:
    """Relative POSIX paths of every deployable file under ``root``."""
    files: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in _EXCLUDED_DIRS for part in relative.parts[:-1]):
            continue
        name = relative.name
        if name in _EXCLUDED_FILES or name == STAMP_NAME or name.startswith("test_") or path.suffix in {".md", ".pyc"}:
            continue
        files.append(relative.as_posix())
    return files


def bundle_hash(root: Path = SOURCE_DIR) -> str:
    digest = hashlib.sha256()
    for relative in bundle_files(root):
        digest.update(relative.encode("utf-8") + b"\0")
        digest.update((root / relative).read_bytes() + b"\0")
    return digest.hexdigest()


__all__ = ["HOT_RELOADABLE", "SOURCE_DIR", "STAMP_NAME", "STAMP_RELATIVE", "bundle_files", "bundle_hash"]
