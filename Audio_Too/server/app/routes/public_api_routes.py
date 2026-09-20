"""Public API GET routes — no authentication required."""

from pathlib import Path
from urllib.parse import parse_qs, urlparse

import automix_jobs
import automix_public_tokens
import business_chat
import hub_status
import portfolio
import stem_separation_bridge
import stem_separation_tokens


def handle_public_get(handler, parsed_path: str) -> bool:
    """Handle public GET routes. Returns True if handled, False to fall through."""
    parsed = urlparse("https://host" + parsed_path)

    if parsed.path == "/api/public/business":
        try:
            handler.send_json(200, business_chat.public_catalog())
        except FileNotFoundError as exc:
            handler.send_json(500, {"error": str(exc)})
        return True

    if parsed.path == "/api/hub/status":
        handler.send_json(200, hub_status.hub_snapshot())
        return True

    if parsed.path == "/api/portfolio":
        try:
            handler.send_json(200, portfolio.load_portfolio())
        except Exception as exc:
            handler.send_json(500, {"error": f"Invalid portfolio_data.json: {exc}"})
        return True

    if parsed.path == "/api/public/tips":
        handler.send_json(200, __import__("studio_tips").public_catalog())
        return True

    if parsed.path == "/api/public/tips/suggest":
        query = parse_qs(parsed.query).get("q", [""])[0]
        try:
            limit = int(parse_qs(parsed.query).get("limit", ["8"])[0])
        except ValueError:
            limit = 8
        handler.send_json(200, __import__("studio_tips").suggest_questions(query, limit=limit))
        return True

    if parsed.path == "/api/public/stem-upload/info":
        token = parse_qs(parsed.query).get("token", [""])[0]
        handler.send_json(200, __import__("stem_uploads").upload_info(token))
        return True

    if parsed.path == "/api/public/automix-start/status":
        query = parse_qs(parsed.query)
        job_id = query.get("id", [""])[0].strip()
        token = query.get("token", [""])[0]
        if not job_id or not automix_public_tokens.verify_job_token(job_id, token):
            handler.send_json(404, {"error": "Job not found."})
            return True
        job = automix_jobs.get_job_status(job_id)
        if not job:
            handler.send_json(404, {"error": "Job not found."})
            return True
        # Public-safe allowlist only -- never leak result_path (a server
        # filesystem path) or the raw style_prefs blob.
        handler.send_json(200, {
            "ok": True,
            "id": job.get("id", ""),
            "project_id": job.get("project_id", ""),
            "status": job.get("status", ""),
            "progress": job.get("progress", 0),
            "genre": job.get("genre", ""),
            "error": job.get("error_message", "") if job.get("status") == "failed" else "",
            "created_at": job.get("created_at", ""),
            "updated_at": job.get("updated_at", ""),
        })
        return True

    if parsed.path == "/api/public/stem-separate/status":
        query = parse_qs(parsed.query)
        job_id = query.get("id", [""])[0].strip()
        token = query.get("token", [""])[0]
        if not job_id or not stem_separation_tokens.verify_job_token(job_id, token):
            handler.send_json(404, {"error": "Job not found."})
            return True
        job = stem_separation_bridge.job_status(job_id)
        if not job:
            handler.send_json(404, {"error": "Job not found."})
            return True
        stems_ready = sorted((job.get("result") or {}).get("stems") or {})
        handler.send_json(200, {
            "ok": True,
            "id": job["id"],
            "status": job["status"],
            "progress": job["progress"],
            "message": job["message"],
            "error": job["error"],
            "stems_ready": stems_ready,
        })
        return True

    if parsed.path == "/api/public/stem-separate/download":
        query = parse_qs(parsed.query)
        job_id = query.get("id", [""])[0].strip()
        token = query.get("token", [""])[0]
        stem = query.get("stem", ["all"])[0].strip().lower()
        if not job_id or not stem_separation_tokens.verify_job_token(job_id, token):
            handler.send_json(404, {"error": "Job not found."})
            return True
        if stem == "all":
            zip_path = stem_separation_bridge.job_zip_path(job_id)
            if not zip_path:
                handler.send_json(404, {"error": "Stems not ready or job not found."})
                return True
            handler.send_file(zip_path, "application/zip", filename=f"stems-{job_id}.zip")
            return True
        if stem not in stem_separation_bridge.STEM_NAMES:
            handler.send_json(400, {"error": f"Unknown stem {stem!r}."})
            return True
        stem_path = stem_separation_bridge.job_stem_path(job_id, stem)
        if not stem_path:
            handler.send_json(404, {"error": "Stem not ready or job not found."})
            return True
        handler.send_file(stem_path, "audio/wav", filename=f"{Path(stem_path).stem}-{job_id}.wav")
        return True

    return False
