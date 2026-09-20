"""Persistence for podcast-check reports (migration 016), so a report can
be revisited/shared via a signed-token link -- the "like Mix Doctor"
treatment plan.md's own NEXT section calls for. Analysis is synchronous
(no background worker), so save_podcast_report() is called once the full
report already exists; there is no "pending" status to track.
"""

from __future__ import annotations

import json
from uuid import uuid4

from db import connect, now


def save_podcast_report(*, title: str, target: str, report: dict, html_report: str) -> str:
    """Persist a completed podcast-check report; returns the new report id."""
    report_id = str(uuid4())[:8]
    score = report.get("score") if isinstance(report, dict) else None
    with connect() as conn:
        conn.execute(
            """INSERT INTO podcast_reports
               (id, title, target, score, report_json, html_report, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (report_id, title[:160], target, score, json.dumps(report), html_report, now()),
        )
        conn.commit()
    return report_id


def get_podcast_report(report_id: str) -> dict | None:
    """Fetch a persisted podcast report by id, or None if it doesn't exist."""
    report_id = str(report_id or "").strip()
    if not report_id:
        return None
    with connect() as conn:
        row = conn.execute(
            "SELECT id, title, target, score, report_json, html_report, created_at "
            "FROM podcast_reports WHERE id = ? LIMIT 1",
            (report_id,),
        ).fetchone()
    if not row:
        return None
    item = dict(row)
    try:
        item["report"] = json.loads(item.pop("report_json"))
    except (TypeError, ValueError):
        item["report"] = {}
        item.pop("report_json", None)
    return item
