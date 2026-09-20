"""Snapshot Audio_Too business and Ableton training data."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BUSINESS_ROOT = ROOT.parent.parent
REPO_ROOT = BUSINESS_ROOT.parent
DATA_DIR = ROOT / "data"
EXPORTS_DIR = ROOT / "backups"
DB_PATH = REPO_ROOT / "data" / "audio_too.db"
ABLETON_ROOT = REPO_ROOT / "studio" / "kenn" / "kenn"
ABLETON_SOURCES = ABLETON_ROOT / "Training_Data_Sources"
ABLETON_NOTES = ABLETON_ROOT / "Training_Data_Notes"


def backup_timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d-%H%M%S")


def run_backup() -> Path:
    stamp = backup_timestamp()
    target = EXPORTS_DIR / f"audio_too-{stamp}"
    target.mkdir(parents=True, exist_ok=True)

    json_dir = target / "agent_data"
    json_dir.mkdir(exist_ok=True)
    if DB_PATH.exists():
        import sys

        website_root = BUSINESS_ROOT / "app"
        if str(website_root) not in sys.path:
            sys.path.insert(0, str(website_root))
        import db as sqlite_db

        sqlite_db.init_db()
        for path in sqlite_db.export_json_snapshots():
            shutil.copy2(path, json_dir / path.name)
    else:
        for path in sorted(DATA_DIR.glob("*.json")):
            shutil.copy2(path, json_dir / path.name)

    activity = DATA_DIR / "activity.jsonl"
    if activity.exists():
        shutil.copy2(activity, target / "activity.jsonl")

    if DB_PATH.exists():
        import sqlite3
        src = sqlite3.connect(str(DB_PATH))
        dst = sqlite3.connect(str(target / "audio_too.db"))
        try:
            with src, dst:
                src.backup(dst)
        finally:
            src.close()
            dst.close()

    if ABLETON_SOURCES.exists():
        shutil.copytree(ABLETON_SOURCES, target / "ableton_sources", dirs_exist_ok=True)

    if ABLETON_NOTES.exists():
        shutil.copytree(ABLETON_NOTES, target / "ableton_notes", dirs_exist_ok=True)

    readme = target / "README.txt"
    readme.write_text(
        f"Audio_Too backup created {stamp}\n"
        "Primary store: data/audio_too.db. agent_data/*.json is an export snapshot only.\n",
        encoding="utf-8",
    )
    return target


def backup_status(*, stale_days: float = 7.0) -> dict:
    backups = sorted(
        (path for path in EXPORTS_DIR.glob("audio_too-*") if path.is_dir()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not backups:
        return {"latest": "", "age_days": None, "stale": True}
    latest = backups[0]
    age_days = (datetime.now().timestamp() - latest.stat().st_mtime) / 86400
    return {
        "latest": latest.name,
        "age_days": round(age_days, 1),
        "stale": age_days > stale_days,
    }
