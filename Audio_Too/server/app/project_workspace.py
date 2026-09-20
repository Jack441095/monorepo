"""Project workspace aggregation for clients, audio, uploads, and review artifacts."""

from __future__ import annotations

import re
from pathlib import Path

import audiogen_bridge
import artifact_store
import event_store
from audio_analysis.mix_review import mix_review
import portfolio_ops
import stem_uploads
from db import list_records


def _clean(value: object) -> str:
    return str(value or "").strip()


def _matchable(value: object) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", _clean(value).lower()).split())


def _matches_project_text(project: dict, value: object) -> bool:
    text = _matchable(value)
    if not text:
        return False
    parts = [_matchable(project.get(field)) for field in ("id", "client", "project", "service", "source")]
    haystack = " ".join(parts)
    if any(part and (part in text or text in part) for part in parts):
        return True
    return text in haystack or haystack in text


def project_by_id(project_id: str) -> dict | None:
    needle = _clean(project_id)
    if not needle:
        return None
    for project in list_records("projects"):
        if _clean(project.get("id")) == needle:
            return project
    return None


def _project_invoices(project: dict) -> list[dict]:
    client = _clean(project.get("client")).lower()
    service = _clean(project.get("service")).lower()
    out = []
    for invoice in list_records("invoices"):
        invoice_client = _clean(invoice.get("client")).lower()
        invoice_service = _clean(invoice.get("service")).lower()
        if client and invoice_client == client:
            out.append(invoice)
            continue
        if client and client in invoice_client and (not service or service in invoice_service):
            out.append(invoice)
    return out


def _project_reviews(project: dict) -> list[dict]:
    reviews = []
    for review in mix_review.list_reviews(limit=100):
        if _matches_project_text(project, review.get("title")) or _matches_project_text(project, review.get("original_name")):
            reviews.append(review)
    return reviews


def _project_audio(project: dict) -> list[dict]:
    out = []
    for item in portfolio_ops.discover_audio_files():
        name = _clean(item.get("name") or Path(_clean(item.get("src"))).name)
        title = _clean(item.get("title"))
        if _matches_project_text(project, name) or _matches_project_text(project, title):
            out.append(item)
    for job in audiogen_bridge.render_queue_snapshot(limit=40).get("recent", []):
        if _clean(job.get("project_id")) == _clean(project.get("id")):
            out.append({"type": "audiogen_job", **job})
    return out


def workspace(project_id: str) -> dict:
    project = project_by_id(project_id)
    if not project:
        return {"ok": False, "error": "Project not found."}
    uploads = stem_uploads.list_uploads(project_id=_clean(project.get("id")))
    invoices = _project_invoices(project)
    reviews = _project_reviews(project)
    audio = _project_audio(project)
    artifacts = [
        artifact_store.public_record(item)
        for item in artifact_store.list_for_project(_clean(project.get("id")))
    ]
    timeline = event_store.list_for_project(_clean(project.get("id")), limit=200)
    return {
        "ok": True,
        "project": project,
        "uploads": uploads,
        "invoices": invoices,
        "mix_reviews": reviews,
        "audio": audio,
        "artifacts": artifacts,
        "timeline": timeline,
        "summary": {
            "uploads": len(uploads),
            "invoices": len(invoices),
            "mix_reviews": len(reviews),
            "audio": len(audio),
            "artifacts": len(artifacts),
            "events": len(timeline),
        },
    }
