"""KENN Contradiction Registry module.

Detects, records, and resolves conflicting claims and measurements within the tip notes
and user correction history.
"""

from __future__ import annotations

import datetime
import json
import logging
import re
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from kenn.knowledge.reasoning import _get_conn, init_db

logger = logging.getLogger("kenn.knowledge.contradictions")

BROAD_TAGS = {
    "ableton",
    "tips",
    "live",
    "audio",
    "device",
    "effect",
    "rack",
    "production",
    "mixing",
    "mastering",
    "automix",
    "unknown",
}
_MEASUREMENT_CONTEXTS = (
    "threshold",
    "ceiling",
    "headroom",
    "release",
    "attack",
    "boost",
    "cut",
    "gain reduction",
    "gain",
    "frequency",
    "loudness",
    "target",
    "true peak",
    "peak",
    "slope",
    "buffer",
)


def extract_measurement_claims(text: str) -> dict[tuple[str, str], set[float]]:
    """Associate measurements with nearby parameter names, not only their unit."""
    claims: dict[tuple[str, str], set[float]] = {}
    pattern = re.compile(r"(-?\d+(?:\.\d+)?)\s*(db|hz|khz|lufs|ms)\b", re.IGNORECASE)
    lowered = text.lower()
    for match in pattern.finditer(text):
        context_window = lowered[max(0, match.start() - 48) : match.start()]
        matches = [
            (context_window.rfind(name), name)
            for name in _MEASUREMENT_CONTEXTS
            if re.search(rf"\b{re.escape(name)}\b", context_window)
        ]
        context = max(matches)[1] if matches else "unspecified"
        claims.setdefault((context, match.group(2).lower()), set()).add(float(match.group(1)))
    return claims


def parse_note_metadata(note_path: Path) -> dict[str, Any] | None:
    """Parse approved note metadata headers from markdown files."""
    try:
        content = note_path.read_text(encoding="utf-8")
        metadata = {
            "source_name": note_path.name,
            "title": note_path.stem,
            "type": "Note",
            "tags": [],
            "status": "Draft",
            "contradiction_key": "",
            "content": content,
        }
        
        # Read header lines
        for line in content.splitlines()[:15]:
            line_str = line.strip()
            if not line_str:
                continue
            if ":" in line_str:
                key, val = line_str.split(":", 1)
                key = key.strip().lower()
                val = val.strip()
                if key == "type":
                    metadata["type"] = val
                elif key == "tags":
                    metadata["tags"] = [t.strip().lower() for t in val.split(",") if t.strip()]
                elif key == "status":
                    metadata["status"] = val
                elif key == "contradiction-key":
                    metadata["contradiction_key"] = val.strip().lower()
            elif line_str.startswith("#"):
                metadata["title"] = line_str.lstrip("# ").strip()
                
        return metadata
    except Exception as e:
        logger.warning(f"Failed to parse note {note_path}: {e}")
        return None


def scan_for_contradictions(notes_dir: Path) -> list[dict[str, Any]]:
    """Scan training notes and user corrections for conflicting measurements under the same topic."""
    init_db()
    
    # Clean/resolve notes_dir
    notes_dir = Path(notes_dir).expanduser()
    if not notes_dir.exists():
        return []

    # 1. Load approved notes
    notes_meta = []
    for note_path in sorted(notes_dir.glob("*.md")):
        meta = parse_note_metadata(note_path)
        if meta and meta["status"].strip().lower() == "approved":
            meta["measurements"] = extract_measurement_claims(meta["content"])
            notes_meta.append(meta)

    detected = []

    # 2. Compare notes against each other
    for i, note_a in enumerate(notes_meta):
        tags_a = set(note_a["tags"]) - BROAD_TAGS
        measurements_a = note_a["measurements"]
        if not tags_a or not measurements_a:
            continue

        for note_b in notes_meta[i + 1:]:
            tags_b = set(note_b["tags"]) - BROAD_TAGS
            measurements_b = note_b["measurements"]
            if not tags_b or not measurements_b:
                continue

            contradiction_key = str(note_a.get("contradiction_key") or "")
            if not contradiction_key or contradiction_key != str(
                note_b.get("contradiction_key") or ""
            ):
                continue

            # Check if they share a specific topic/tag
            shared_tags = tags_a & tags_b
            if shared_tags:
                for (context, unit), values_a in measurements_a.items():
                    if (context, unit) in measurements_b and context != "unspecified":
                        values_b = measurements_b[(context, unit)]
                        # If disjoint values, we have a contradiction!
                        if not (values_a & values_b):
                            # Determine type
                            c_type = "measurement_mismatch"
                            type_a = note_a.get("type", "Note").lower()
                            type_b = note_b.get("type", "Note").lower()
                            if ("transcript" in type_a and "manual" in type_b) or ("transcript" in type_b and "manual" in type_a):
                                c_type = "transcript_vs_manual"

                            desc = (
                                f"Conflicting {context} {unit} settings for claim '{contradiction_key}'. "
                                f"Note '{note_a['source_name']}' has {list(values_a)} {unit}, "
                                f"but '{note_b['source_name']}' has {list(values_b)} {unit}."
                            )
                            conflict = {
                                "type": c_type,
                                "source_a": note_a["source_name"],
                                "source_b": note_b["source_name"],
                                "description": desc,
                                "conflicting_data": {
                                    "shared_tags": list(shared_tags),
                                    "contradiction_key": contradiction_key,
                                    "unit": unit,
                                    "measurement_context": context,
                                    "values_a": list(values_a),
                                    "values_b": list(values_b),
                                },
                            }
                            conflict["contradiction_id"] = save_contradiction(
                                c_type,
                                note_a["source_name"],
                                note_b["source_name"],
                                desc,
                                conflict["conflicting_data"],
                            )
                            detected.append(conflict)

    _resolve_stale_measurement_detections(
        {(item["source_a"], item["source_b"]) for item in detected}
    )

    # 3. Compare notes against user corrections (lessons)
    try:
        from kenn.knowledge import list_lessons
        lessons = list_lessons()
        for lesson in lessons:
            lesson_tags = set(lesson["topic"].split()) - BROAD_TAGS
            lesson_measurements = extract_measurement_claims(lesson["lesson"])
            if not lesson_tags or not lesson_measurements:
                continue

            for note in notes_meta:
                note_tags = set(note["tags"]) - BROAD_TAGS
                shared_tags = lesson_tags & note_tags
                if shared_tags:
                    for (context, unit), val_lesson in lesson_measurements.items():
                        if context != "unspecified" and (context, unit) in note["measurements"]:
                            val_note = note["measurements"][(context, unit)]
                            if not (val_lesson & val_note):
                                desc = (
                                    f"User correction contradicts approved note '{note['source_name']}' "
                                    f"under topic '{list(shared_tags)[0]}'. Lesson has {list(val_lesson)} {unit}, "
                                    f"but note has {list(val_note)} {unit}."
                                )
                                conflict = {
                                    "type": "user_correction_invalidation",
                                    "source_a": f"lesson:{lesson['lesson_id'][:8]}",
                                    "source_b": note["source_name"],
                                    "description": desc,
                                    "conflicting_data": {
                                        "shared_tags": list(shared_tags),
                                        "unit": unit,
                                        "measurement_context": context,
                                        "lesson_values": list(val_lesson),
                                        "note_values": list(val_note),
                                    },
                                }
                                conflict["contradiction_id"] = save_contradiction(
                                    "user_correction_invalidation",
                                    f"lesson:{lesson['lesson_id']}",
                                    note["source_name"],
                                    desc,
                                    conflict["conflicting_data"],
                                )
                                detected.append(conflict)
    except Exception as e:
        logger.warning(f"Error checking user corrections against notes: {e}")

    return detected


def _resolve_stale_measurement_detections(current_pairs: set[tuple[str, str]]) -> None:
    """Retire old machine findings no longer reproduced by the current rules."""
    normalized = {frozenset(pair) for pair in current_pairs}
    try:
        with _get_conn() as conn:
            rows = conn.execute(
                """SELECT contradiction_id, source_a, source_b
                   FROM knowledge_contradictions
                   WHERE status = 'open'
                     AND type IN ('measurement_mismatch', 'transcript_vs_manual')"""
            ).fetchall()
            stale = [
                row["contradiction_id"]
                for row in rows
                if frozenset((row["source_a"], row["source_b"])) not in normalized
            ]
            conn.executemany(
                """UPDATE knowledge_contradictions
                   SET status = 'resolved', resolution = 'superseded_by_context_aware_scan'
                   WHERE contradiction_id = ?""",
                [(contradiction_id,) for contradiction_id in stale],
            )
    except (sqlite3.Error, OSError) as exc:
        logger.warning(f"Failed to reconcile stale contradiction detections: {exc}")


def save_contradiction(
    type_str: str,
    source_a: str,
    source_b: str,
    description: str,
    conflicting_data: dict[str, Any],
) -> str:
    """Save a detected contradiction to SQLite if an open one doesn't already exist."""
    init_db()
    try:
        with _get_conn() as conn:
            # Check if there is an active contradiction between these two sources
            row = conn.execute(
                """
                SELECT contradiction_id FROM knowledge_contradictions
                WHERE status = 'open' AND (
                    (source_a = ? AND source_b = ?) OR (source_a = ? AND source_b = ?)
                )
                """,
                (source_a, source_b, source_b, source_a)
            ).fetchone()
            if row:
                return row["contradiction_id"]

            cid = str(uuid.uuid4())
            created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            data_str = json.dumps(conflicting_data)
            conn.execute(
                """
                INSERT INTO knowledge_contradictions (
                    contradiction_id, created_at, type, status, source_a, source_b, description, conflicting_data
                ) VALUES (?, ?, ?, 'open', ?, ?, ?, ?)
                """,
                (cid, created_at, type_str, source_a, source_b, description, data_str)
            )
            return cid
    except (sqlite3.Error, OSError) as e:
        logger.warning(f"Failed to save contradiction: {e}")
        return ""


def list_contradictions() -> list[dict[str, Any]]:
    """List all open contradictions in the registry."""
    try:
        init_db()
        with _get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM knowledge_contradictions WHERE status = 'open' ORDER BY created_at DESC"
            ).fetchall()
            results = []
            for row in rows:
                r = dict(row)
                try:
                    r["conflicting_data"] = json.loads(r["conflicting_data"])
                except Exception:
                    r["conflicting_data"] = {}
                results.append(r)
            return results
    except (sqlite3.Error, OSError) as e:
        logger.warning(f"Failed to list contradictions: {e}")
        return []


def resolve_contradiction(contradiction_id: str, strategy: str, notes_dir: Path) -> bool:
    """Resolve a contradiction using the specified strategy (primary_a, primary_b, merged)."""
    init_db()
    notes_dir = Path(notes_dir).expanduser()
    try:
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM knowledge_contradictions WHERE contradiction_id = ? OR contradiction_id LIKE ?",
                (contradiction_id, f"{contradiction_id}%")
            ).fetchone()
            if not row:
                logger.warning(f"Contradiction {contradiction_id} not found.")
                return False

            cid = row["contradiction_id"]
            source_a = row["source_a"]
            source_b = row["source_b"]

            # Implement strategies
            success = True
            if strategy == "primary_a":
                # Keep Note A, deprecate Note B (turn B to Draft)
                if not source_b.startswith("lesson:"):
                    success = _deprecate_note(source_b, notes_dir)
            elif strategy == "primary_b":
                # Keep Note B, deprecate Note A (turn A to Draft)
                if not source_a.startswith("lesson:"):
                    success = _deprecate_note(source_a, notes_dir)
            elif strategy == "merged":
                # Merged indicates user resolved it manually
                pass
            else:
                logger.warning(f"Unknown resolution strategy: {strategy}")
                return False

            if success:
                conn.execute(
                    """
                    UPDATE knowledge_contradictions
                    SET status = 'resolved', resolution = ?
                    WHERE contradiction_id = ?
                    """,
                    (strategy, cid)
                )
                return True
            return False
    except (sqlite3.Error, OSError) as e:
        logger.warning(f"Failed to resolve contradiction: {e}")
        return False


def _deprecate_note(note_name: str, notes_dir: Path) -> bool:
    """Helper to update Status header to Draft in the note file."""
    filename = note_name if note_name.endswith(".md") else f"{note_name}.md"
    note_path = notes_dir / filename
    if not note_path.exists():
        candidates = list(notes_dir.glob(f"**/{filename}"))
        if candidates:
            note_path = candidates[0]
        else:
            logger.warning(f"Note file {note_name} not found in {notes_dir}")
            return False
            
    try:
        content = note_path.read_text(encoding="utf-8")
        # Regex replacement of Status: Approved to Status: Draft
        new_content = re.sub(
            r"^Status:\s*\S+", "Status: Draft", content, flags=re.MULTILINE | re.IGNORECASE
        )
        note_path.write_text(new_content, encoding="utf-8")
        return True
    except Exception as e:
        logger.warning(f"Failed to update Status header in {note_path}: {e}")
        return False
