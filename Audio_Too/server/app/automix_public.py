"""Public, self-serve "upload stems, start an AutoMix job" flow.

The existing stem-upload/job-start path (automix.js's #uploadZone) is
authenticated dashboard-only (POST /api/v1/automix/uploads + a separate
job-start call), and the existing /api/public/stem-upload is for a
client delivering files against a pre-issued project token, not for
starting a fresh AutoMix render. This module is the public equivalent of
that authenticated flow: one call, a fresh project_id, multiple stem
files, and a real queued job -- mirrors stem_separation_bridge.py's
enqueue_separation() shape (validate -> store -> queue -> return job +
signed token) for the same reason: a public caller with no dashboard
session needs to both start and later poll a job.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from uuid import uuid4

import automix_jobs
import stem_uploads
from api_schemas import AutomixStartRequest

MAX_STEM_FILES = 32
_MIXDOWN_WAV_RE = re.compile(r"^mixdown_v\d+\.wav$")


def start_public_automix(
    files: list[tuple[bytes, str]],
    *,
    genre: str = "pop",
    style_prefs: dict | None = None,
    project_id: str = "",
) -> dict:
    """Store each (file_bytes, filename) pair as a stem upload under
    project_id, then queue a real AutoMix job. Returns
    ``{ok, project_id, job_id, status}`` or ``{ok: False, error}``.

    project_id: reuse an existing song_projects id (e.g. the caller's KENN
    chat session already has one via resolve_session_project() --
    docs/KENN_HUB_UNIFICATION_PLAN_2026-08-05.md Phase 2) so a revision
    later in the same conversation lands in the same project. If empty,
    mints a fresh synthetic id (the pre-existing behaviour, unchanged for
    any caller that doesn't yet track a project)."""
    if not files:
        return {"ok": False, "error": "No files provided."}
    if len(files) > MAX_STEM_FILES:
        return {"ok": False, "error": f"Too many files -- {MAX_STEM_FILES} max."}

    project_id = project_id or f"kenn-{uuid4().hex[:10]}"
    project_label = f"KENN upload {project_id}"

    for file_bytes, filename in files:
        try:
            stem_uploads.validate_automix_source(file_bytes, filename)
        except stem_uploads.UploadValidationError as exc:
            return {"ok": False, "error": f"{filename!r}: {exc}"}
        try:
            _status, result = stem_uploads.store_upload(
                stem_uploads.StemUploadRequest(
                    project_id=project_id,
                    file_bytes=file_bytes,
                    filename=filename,
                    project_label=project_label,
                    uploader_name="KENN",
                    notes="Uploaded via the KENN chat unified upload widget.",
                )
            )
        except stem_uploads.UploadValidationError as exc:
            return {"ok": False, "error": f"{filename!r}: {exc}"}
        if not result.get("ok"):
            return {"ok": False, "error": result.get("error") or f"Failed to store {filename!r}."}

    try:
        _job_status, job_response = automix_jobs.queue_job(
            AutomixStartRequest.from_payload({"project_id": project_id, "genre": genre, "style_prefs": style_prefs or {}})
        )
    except stem_uploads.SourceNotReady as exc:
        return {"ok": False, "error": str(exc)}
    if not job_response.get("ok"):
        return {"ok": False, "error": job_response.get("error") or "Could not start the AutoMix job."}

    return {
        "ok": True,
        "project_id": project_id,
        "job_id": job_response.get("job_id", ""),
        "status": job_response.get("status", ""),
    }


def delivery_zip_path(job_id: str) -> Path | None:
    """The completed job's packaged delivery ZIP (mixdown WAV + reports +
    manifest), or None if the job isn't complete or the file is gone."""
    job = automix_jobs.get_job_status(job_id)
    if not job or job.get("status") != "complete":
        return None
    result_path = job.get("result_path") or ""
    if not result_path:
        return None
    path = Path(result_path)
    return path if path.exists() else None


def delivery_wav_bytes(job_id: str) -> tuple[bytes, str] | None:
    """Extract the mixdown WAV straight out of the delivery ZIP (rather than
    relying on a separate on-disk copy that may or may not still exist) for
    inline playback. Returns ``(wav_bytes, filename)`` or None."""
    zip_path = delivery_zip_path(job_id)
    if not zip_path:
        return None
    try:
        with zipfile.ZipFile(zip_path) as zf:
            wav_names = [name for name in zf.namelist() if _MIXDOWN_WAV_RE.match(name)]
            if not wav_names:
                return None
            name = wav_names[0]
            return zf.read(name), name
    except (OSError, zipfile.BadZipFile):
        return None
