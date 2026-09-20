"""Full business snapshot exporter for Audio_Too.

Creates a single timestamped archive with all records, notes, and metadata
for safe-keeping, transfer, or archiving.
"""

from __future__ import annotations

import json
import shutil
import tarfile
from datetime import datetime
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parent.parent.parent
REPO_ROOT = ROOT.parent


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H%M%S")


def _collect_notes(agent_dir: str, sub_dir: str) -> list[tuple[str, str]]:
    """Collect .md note files from an agent's subdirectory.

    Returns list of (archive_name, content) tuples.
    """
    notes_dir = ROOT / "agents" / agent_dir / sub_dir
    results: list[tuple[str, str]] = []
    if notes_dir.is_dir():
        for fpath in sorted(notes_dir.iterdir()):
            if fpath.suffix == ".md":
                try:
                    content = fpath.read_text(encoding="utf-8")
                    archive_name = f"notes/{agent_dir}/{sub_dir}/{fpath.name}"
                    results.append((archive_name, content))
                except (OSError, UnicodeDecodeError):
                    pass
    return results


def create_snapshot(
    list_records: Callable[[str], list[dict]],
) -> str:
    """Create a timestamped tar.gz snapshot of the entire server.

    Includes:
    - All SQLite records exported as JSON
    - All project .md files
    - All lead .md files
    - All campaign .md files
    - All templates (Admin + Marketing)
    - Business profile
    - Activity log
    - DB file copy

    Returns path to the snapshot file.
    """
    timestamp = _now()
    snapshot_name = f"audio_too_snapshot_{timestamp}"
    snapshot_dir = ROOT / "agents" / "Shared" / "backups" / snapshot_name
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    # 1. Export all tables as JSON
    tables = [
        "clients", "projects", "leads", "invoices", "drafts",
        "campaigns", "followups", "enquiries", "sessions",
    ]
    for table in tables:
        try:
            records = list_records(table)
        except KeyError:
            records = []
        path = snapshot_dir / f"{table}.json"
        path.write_text(json.dumps(records, indent=2), encoding="utf-8")

    # 2. Copy SQLite DB
    db_path = REPO_ROOT / "data" / "audio_too.db"
    if db_path.exists():
        shutil.copy2(db_path, snapshot_dir / "audio_too.db")

    # 3. Copy activity log
    activity_log = ROOT / "agents" / "Shared" / "data" / "activity.jsonl"
    if activity_log.exists():
        shutil.copy2(activity_log, snapshot_dir / "activity.jsonl")

    # 4. Copy business profile
    profile = ROOT / "agents" / "Shared" / "business_profile.md"
    if profile.exists():
        shutil.copy2(profile, snapshot_dir / "business_profile.md")

    # 5. Collect all .md notes
    notes: list[tuple[str, str]] = []
    notes.extend(_collect_notes("Admin", "projects"))
    notes.extend(_collect_notes("Marketing", "leads"))
    notes.extend(_collect_notes("Marketing", "campaigns"))

    for archive_name, content in notes:
        target = snapshot_dir / archive_name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    # 6. Collect all templates
    templates: list[tuple[str, str]] = []
    templates.extend(_collect_notes("Admin", "templates"))
    templates.extend(_collect_notes("Admin", "workflows"))
    templates.extend(_collect_notes("Marketing", "templates"))

    for archive_name, content in templates:
        target = snapshot_dir / archive_name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    # 7. Write manifest
    manifest = {
        "snapshot": snapshot_name,
        "created": _now(),
        "tables": tables,
        "records": {},
        "notes": len(notes),
        "templates": len(templates),
    }
    for table in tables:
        json_path = snapshot_dir / f"{table}.json"
        if json_path.exists():
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
                manifest["records"][table] = len(data)
            except (json.JSONDecodeError, OSError):
                manifest["records"][table] = 0

    manifest_path = snapshot_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    # 8. Create tar.gz archive
    archive_path = ROOT / "agents" / "Shared" / "backups" / f"{snapshot_name}.tar.gz"
    with tarfile.open(str(archive_path), "w:gz") as tar:
        tar.add(str(snapshot_dir), arcname=snapshot_name)

    # 9. Clean up temp directory
    shutil.rmtree(snapshot_dir)

    # Build summary
    total_records = sum(manifest["records"].values())
    summary = (
        f"\U0001f4ca Business Snapshot Created\n"
        f"{'=' * 40}\n"
        f"  File: {archive_path}\n"
        f"  Size: {archive_path.stat().st_size / 1024:.0f} KB\n"
        f"  Tables: {len(tables)} ({total_records} total records)\n"
        f"  Notes: {len(notes)}\n"
        f"  Templates: {len(templates)}\n"
        f"\n  To restore, extract the archive and use:\n"
        f"  tar -xzf {archive_path.name} -C /path/to/restore/"
    )
    return summary


def list_snapshots() -> str:
    """List all available snapshots."""
    backups_dir = ROOT / "agents" / "Shared" / "backups"
    snapshots = sorted(backups_dir.glob("audio_too_snapshot_*.tar.gz"))
    if not snapshots:
        return "No snapshots found."

    lines = ["\U0001f4c2 Available Snapshots", "=" * 35]
    for s in snapshots:
        size_kb = s.stat().st_size / 1024
        lines.append(f"  {s.name} ({size_kb:.0f} KB)")
    lines.append(f"\nTotal: {len(snapshots)} snapshot(s)")
    return "\n".join(lines)
