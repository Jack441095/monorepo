"""LM gap workflow: log, draft notes, retest after index builds."""

from __future__ import annotations

import json
import re

from db import connect, now

import tips_gaps

OPEN = "open"
DRAFTED = "drafted"
RESOLVED = "resolved"
DISMISSED = "dismissed"


def normalize_question(question: str) -> str:
    return re.sub(r"\s+", " ", question.strip().lower())[:500]


def gap_is_resolved(payload: dict) -> bool:
    confidence = str(payload.get("confidence", "")).lower()
    if confidence not in {"high", "medium"}:
        return False
    sources = payload.get("sources") or []
    return any(str(item.get("kind", "")) == "note" for item in sources)


def summary() -> dict:
    tips_gaps.init_gaps_table()
    with connect() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS n FROM tips_gaps GROUP BY status"
        ).fetchall()
    counts = {str(row["status"]): int(row["n"]) for row in rows}
    return {
        "open": counts.get(OPEN, 0),
        "drafted": counts.get(DRAFTED, 0),
        "resolved": counts.get(RESOLVED, 0),
        "dismissed": counts.get(DISMISSED, 0),
    }


def list_gaps_filtered(*, status: str = "", limit: int = 50) -> list[dict]:
    if status == "all":
        return _list_all(limit=limit)
    return tips_gaps.list_gaps(status=status or OPEN, limit=limit)


def _list_all(limit: int) -> list[dict]:
    tips_gaps.init_gaps_table()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM tips_gaps
            WHERE status IN (?, ?, ?)
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (OPEN, DRAFTED, RESOLVED, max(1, min(200, limit))),
        ).fetchall()
    return [_row_dict(row) for row in rows]


def _row_dict(row) -> dict:
    item = dict(row)
    try:
        item["topics"] = json.loads(item.get("topics") or "[]")
    except json.JSONDecodeError:
        item["topics"] = []
    return item


def find_open_gap_id(question: str) -> str | None:
    needle = normalize_question(question)
    if not needle:
        return None
    tips_gaps.init_gaps_table()
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, question FROM tips_gaps WHERE status = ? ORDER BY created_at DESC LIMIT 200",
            (OPEN,),
        ).fetchall()
    for row in rows:
        if normalize_question(str(row["question"])) == needle:
            return str(row["id"])
    return None


def record_gap(question: str, payload: dict, *, channel: str = "unknown") -> dict | None:
    if not tips_gaps.should_record(payload):
        return None
    existing = find_open_gap_id(question)
    if existing:
        return {"id": existing, "deduped": True}
    row = tips_gaps.record_gap(question, payload, channel=channel)
    if row:
        row["deduped"] = False
    return row


def mark_resolved(gap_id: str, *, top_source: str = "", confidence: str = "") -> bool:
    tips_gaps.init_gaps_table()
    with connect() as conn:
        cur = conn.execute(
            """
            UPDATE tips_gaps
            SET status = ?, top_source = COALESCE(NULLIF(?, ''), top_source),
                confidence = COALESCE(NULLIF(?, ''), confidence), updated_at = ?
            WHERE id = ? AND status IN (?, ?)
            """,
            (RESOLVED, top_source, confidence, now(), gap_id.strip(), OPEN, DRAFTED),
        )
        conn.commit()
        return cur.rowcount > 0


def dismiss_gap(gap_id: str) -> bool:
    tips_gaps.init_gaps_table()
    with connect() as conn:
        cur = conn.execute(
            """
            UPDATE tips_gaps SET status = ?, updated_at = ?
            WHERE id = ? AND status IN (?, ?)
            """,
            (DISMISSED, now(), gap_id.strip(), OPEN, DRAFTED),
        )
        conn.commit()
        return cur.rowcount > 0


def retest_question(question: str) -> dict:
    import ableton_bridge

    return ableton_bridge.ask(question, limit=8, allow_llm=False)


def retest_gap(gap_id: str) -> dict:
    gap = tips_gaps.get_gap(gap_id)
    if not gap:
        return {"ok": False, "error": "Gap not found."}
    if gap.get("status") not in {OPEN, DRAFTED}:
        return {"ok": False, "error": f"Gap is {gap.get('status')}; only open/drafted can be retested."}
    payload = retest_question(str(gap.get("question", "")))
    resolved = gap_is_resolved(payload)
    if resolved:
        top = (payload.get("sources") or [{}])[0].get("label", "")
        mark_resolved(gap_id, top_source=str(top), confidence=str(payload.get("confidence", "")))
    return {
        "ok": True,
        "gap_id": gap_id,
        "resolved": resolved,
        "confidence": payload.get("confidence"),
        "top_source": (payload.get("sources") or [{}])[0].get("label", "") if payload.get("sources") else "",
        "answer_preview": str(payload.get("answer", ""))[:400],
    }


def retest_all_open() -> dict:
    gaps = tips_gaps.list_gaps(status=OPEN, limit=200)
    resolved_ids: list[str] = []
    still_weak: list[str] = []
    for gap in gaps:
        result = retest_gap(str(gap["id"]))
        if result.get("resolved"):
            resolved_ids.append(str(gap["id"]))
        else:
            still_weak.append(str(gap["id"]))
    return {
        "ok": True,
        "checked": len(gaps),
        "resolved": len(resolved_ids),
        "still_weak": len(still_weak),
        "resolved_ids": resolved_ids,
        "still_weak_ids": still_weak,
    }


def on_note_approved(note_file: str) -> dict:
    """After approve + build, retest gaps linked to this note."""
    tips_gaps.init_gaps_table()
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM tips_gaps WHERE status = ? AND note_file = ?",
            (DRAFTED, note_file),
        ).fetchall()
    resolved = 0
    for row in rows:
        result = retest_gap(str(row["id"]))
        if result.get("resolved"):
            resolved += 1
    return {"ok": True, "note": note_file, "resolved": resolved, "checked": len(rows)}
