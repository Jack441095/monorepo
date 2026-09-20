"""Operations for reviewing, editing, approving, and dismissing suggested note drafts."""

import json
import logging
import re
from pathlib import Path
from db import connect, now, upsert_record
import tips_gaps

logger = logging.getLogger(__name__)

WEBSITE_ROOT = Path(__file__).resolve().parent
ROOT_DIR = WEBSITE_ROOT.parent.parent
CANONICAL_NOTES_DIR = ROOT_DIR / "studio" / "kenn" / "kenn" / "Training_Data_Notes"
NOTES_DIR = CANONICAL_NOTES_DIR


def list_suggested_notes() -> list[dict]:
    """Retrieve all pending suggested note drafts."""
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM suggested_notes
            WHERE status = 'pending'
            ORDER BY created_at DESC
            """
        ).fetchall()
    out = []
    for r in rows:
        item = dict(r)
        try:
            item["source_cluster_queries"] = json.loads(item.get("source_cluster_queries") or "[]")
        except json.JSONDecodeError:
            item["source_cluster_queries"] = []
        out.append(item)
    return out


def get_suggested_note(draft_id: str) -> dict | None:
    """Retrieve a single suggested note draft."""
    with connect() as conn:
        row = conn.execute("SELECT * FROM suggested_notes WHERE id = ?", (draft_id.strip(),)).fetchone()
    if not row:
        return None
    item = dict(row)
    try:
        item["source_cluster_queries"] = json.loads(item.get("source_cluster_queries") or "[]")
    except json.JSONDecodeError:
        item["source_cluster_queries"] = []
    return item


def save_suggested_note_edits(draft_id: str, title: str, content: str) -> dict:
    """Save edits made to a suggested note before approval."""
    draft = get_suggested_note(draft_id)
    if not draft:
        return {"ok": False, "error": "Suggested note not found."}

    draft["title"] = title.strip()
    draft["content"] = content
    draft["updated_at"] = now()

    # Re-encode queries to match schema
    draft["source_cluster_queries"] = json.dumps(draft["source_cluster_queries"])

    upsert_record("suggested_notes", draft)
    return {"ok": True, "message": "Edits saved successfully."}


def slugify(value: str) -> str:
    """Convert a title to a filename-safe slug."""
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def approve_suggested_note(draft_id: str) -> dict:
    """Approve a draft, write it as a markdown file, link open gaps to it, and update DB status."""
    draft = get_suggested_note(draft_id)
    if not draft:
        return {"ok": False, "error": "Suggested note not found."}

    if draft.get("status") != "pending":
        return {"ok": False, "error": f"Suggested note status is {draft.get('status')}, not pending."}

    title = draft["title"]
    content = draft["content"]

    import sys
    kenn_parent = ROOT_DIR / "studio" / "kenn"
    if str(kenn_parent) not in sys.path:
        sys.path.insert(0, str(kenn_parent))
    from kenn.training.note_quality import validate_note_for_approval

    validation = validate_note_for_approval(content)
    if not validation["ok"]:
        return {"ok": False, "error": "Draft is not ready for approval.", **validation}

    # Ensure NOTES_DIR exists
    NOTES_DIR.mkdir(parents=True, exist_ok=True)

    # Determine unique note filename
    base_slug = slugify(title) or "suggested-note"
    filename = f"{base_slug}.md"
    path = NOTES_DIR / filename
    suffix = 2
    while path.exists():
        filename = f"{base_slug}-{suffix}.md"
        path = NOTES_DIR / filename
        suffix += 1

    # Write note file
    try:
        path.write_text(content, encoding="utf-8")
    except OSError as e:
        return {"ok": False, "error": f"Failed to write note file: {e}"}

    # Update suggested note status to approved
    with connect() as conn:
        conn.execute(
            "UPDATE suggested_notes SET status = 'approved', updated_at = ? WHERE id = ?",
            (now(), draft_id),
        )
        conn.commit()

    # Link all open gaps matching the source queries
    gaps_linked = 0
    queries = draft.get("source_cluster_queries") or []
    for q in queries:
        norm_q = re.sub(r"\s+", " ", q.strip().lower())
        # Query open gaps
        with connect() as conn:
            rows = conn.execute("SELECT id, question FROM tips_gaps WHERE status = 'open'").fetchall()
        for r in rows:
            norm_gap = re.sub(r"\s+", " ", r["question"].strip().lower())
            if norm_gap == norm_q:
                # Link gap to note
                if tips_gaps.link_gap_note(r["id"], filename):
                    gaps_linked += 1

    # Only the canonical note collection may replace KENN's live index. This
    # prevents tests, previews, or alternate draft folders from rebuilding the
    # production index from an incomplete corpus.
    index_warnings: list[str] = []
    if NOTES_DIR.resolve() == CANONICAL_NOTES_DIR.resolve():
        try:
            import sys
            kenn_parent = ROOT_DIR / "studio" / "kenn"
            if str(kenn_parent) not in sys.path:
                sys.path.insert(0, str(kenn_parent))
            from kenn.retrieval.build_index import build_index
            pdf_dir = ROOT_DIR / "studio" / "kenn" / "kenn" / "Training_Data_PDF"
            build_index(pdf_dir, NOTES_DIR)
        except Exception as exc:
            logger.warning("suggested_notes_ops: index rebuild failed for %s: %s", filename, exc)
            index_warnings.append(
                f"Index rebuild failed ({exc}); this note is not yet searchable. Rebuild the index manually."
            )

        # Trigger hot-reload on the running KENN server. Skip the reload
        # attempt (and don't warn) if the rebuild above already failed --
        # reloading a stale index isn't useful and would just double the noise.
        if not index_warnings:
            try:
                import urllib.request
                req = urllib.request.Request("http://127.0.0.1:8090/api/admin/reload-index", method="GET")
                with urllib.request.urlopen(req, timeout=3):
                    pass
            except Exception as exc:
                logger.warning("suggested_notes_ops: KENN hot-reload failed for %s: %s", filename, exc)
                index_warnings.append(
                    f"Index rebuilt but the running KENN server didn't hot-reload ({exc}); "
                    "restart it or call /api/admin/reload-index manually."
                )

    all_warnings = list(validation["warnings"]) + index_warnings
    message = f"Draft approved and saved as {filename}. Linked {gaps_linked} open gap(s)."
    if index_warnings:
        message += " Warning: " + " ".join(index_warnings)

    return {
        "ok": True,
        "note": filename,
        "gaps_linked": gaps_linked,
        "warnings": all_warnings,
        "index_ok": not index_warnings,
        "message": message,
    }


def dismiss_suggested_note(draft_id: str) -> dict:
    """Dismiss a suggested note draft."""
    draft = get_suggested_note(draft_id)
    if not draft:
        return {"ok": False, "error": "Suggested note not found."}

    with connect() as conn:
        cur = conn.execute(
            "UPDATE suggested_notes SET status = 'dismissed', updated_at = ? WHERE id = ? AND status = 'pending'",
            (now(), draft_id),
        )
        conn.commit()
        success = cur.rowcount > 0

    if success:
        return {"ok": True, "message": "Suggested note dismissed."}
    return {"ok": False, "error": "Suggested note is not in pending status."}


def run_manual_clustering() -> dict:
    """Manually run the gap clustering job from backend."""
    import sys
    sys.path.insert(0, str(ROOT_DIR / "studio" / "kenn" / "kenn" / "adaptive"))
    try:
        from gap_clustering import run_clustering
        count = run_clustering()
        return {"ok": True, "count": count, "message": f"Gap clustering completed. Generated {count} suggestion(s)."}
    except Exception as e:
        return {"ok": False, "error": str(e)}
