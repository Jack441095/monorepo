"""Automix GET/POST routes — auth-required mix job status, download, play, report, manifest, upload, reference, start, revise."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import path_safety
import stem_uploads
import automix_jobs
import advisor_feedback
import musical_role_feedback
import artifact_store
import idempotency
from app.api_schemas import (
    AutomixAdvisorFeedbackRequest,
    AutomixRevisionRequest,
    AutomixStartRequest,
    SchemaValidationError,
)


def _latest_mixdown_wav_bytes(business_root: str, project_id: str) -> bytes | None:
    """The most recently delivered mixdown_v<N>.wav for a project, or None if
    the project id is invalid or no render has completed yet. Shared by
    /api/automix/spectrum-match and /api/automix/waveform -- both need the
    real delivered audio, not a project_id string alone."""
    try:
        safe_project_id = path_safety.validate_identifier(project_id, label="project ID")
    except ValueError:
        return None
    proj_dir = path_safety.safe_child(Path(business_root) / "data" / "mix_outputs", safe_project_id)
    if not proj_dir.exists():
        return None
    wav_files = sorted(proj_dir.glob("mixdown_v*.wav"), key=lambda p: p.stat().st_mtime, reverse=True)
    return wav_files[0].read_bytes() if wav_files else None


def handle_automix_get(handler, parsed_path: str, business_root: str) -> bool:
    """Handle /api/automix/* GET routes. Returns True if handled, False to fall through."""
    parsed = urlparse("https://host" + parsed_path)
    path_only = parsed.path

    preview_prefixes = (
        "/api/automix/advisor-preview/",
        "/api/v1/automix/advisor-previews/",
    )
    preview_prefix = next(
        (prefix for prefix in preview_prefixes if path_only.startswith(prefix)),
        "",
    )
    if preview_prefix:
        artifact_id = path_only.removeprefix(preview_prefix)
        try:
            artifact_id = path_safety.validate_identifier(
                artifact_id, label="preview artifact ID"
            )
        except ValueError as exc:
            handler.send_json(400, {"error": str(exc)})
            return True
        artifact = artifact_store.get(artifact_id)
        allowed_kinds = {
            "audio.automix.advisor-preview",
            "audio.automix.advisor-preview-baseline",
        }
        if (
            artifact is None
            or artifact.get("status") != "active"
            or artifact.get("kind") not in allowed_kinds
        ):
            handler.send_json(404, {"error": "Advisor preview not found."})
            return True
        verification = artifact_store.verify(artifact_id)
        if not verification.get("ok"):
            handler.send_json(409, {"error": "Advisor preview failed integrity verification."})
            return True
        handler.send_file(
            artifact_store.resolve_path(artifact_id),
            "audio/wav",
            filename=f"advisor-preview-{artifact_id}.wav",
        )
        return True

    if path_only == "/api/automix/queue-health":
        handler.send_json(200, automix_jobs.queue_health())
        return True

    if path_only == "/api/automix/spectrum-match":
        from audio_analysis.mixdown.ltas_matcher import (
            calculate_40_band_ltas, expand_genre_profile_to_40_bands,
            generate_ltas_match_eq_bands, reference_target_40_band_ltas,
        )
        from audio_analysis.mixdown.mix_decision_engine import resolve_genre
        from audio_analysis.utils.audio_io import read_wav_mono
        import automix_worker

        query = parse_qs(parsed.query)
        genre = query.get("genre", ["pop"])[0]
        project_id = query.get("project_id", [""])[0]
        resolved_genre, _note = resolve_genre(genre)

        mix_40_bands = None
        wav_bytes = _latest_mixdown_wav_bytes(business_root, project_id) if project_id else None
        if wav_bytes is not None:
            decoded = read_wav_mono(wav_bytes, max_samples=0)
            mix_40_bands = calculate_40_band_ltas(decoded["samples"], int(decoded["sample_rate"]))

        if mix_40_bands is None:
            handler.send_json(404, {
                "ok": False,
                "error": "No delivered mixdown found for this project yet.",
            })
            return True

        # Prefer a real reference measured from the curated reference_tracks/
        # library (the same one spectral_match.py/match-report already use)
        # over the hand-tuned GENRE_LTAS_PROFILES estimate -- only genres
        # without a curated folder fall back to the estimate, and the
        # response says honestly which one was used rather than presenting
        # an estimate as a measurement.
        ref_dir = automix_worker.default_reference_dir(resolved_genre)
        ref_40_bands = reference_target_40_band_ltas(ref_dir) if ref_dir else None
        reference_source = "curated_reference_tracks"
        if ref_40_bands is None:
            ref_40_bands = expand_genre_profile_to_40_bands(resolved_genre)
            reference_source = "genre_profile_estimate"

        eq_recs = generate_ltas_match_eq_bands(
            mix_40_bands, genre=resolved_genre,
            ref_40_bands=ref_40_bands if reference_source == "curated_reference_tracks" else None,
        )
        handler.send_json(200, {
            "ok": True,
            "genre": resolved_genre,
            "mix_40_bands": mix_40_bands,
            "ref_40_bands": ref_40_bands,
            "reference_source": reference_source,
            "eq_recommendations": eq_recs,
        })
        return True

    waveform_prefix = "/api/automix/waveform/"
    if path_only.startswith(waveform_prefix):
        from audio_analysis.analysis_core.waveform import DEFAULT_POINTS, compute_waveform_peaks
        from audio_analysis.utils.audio_io import read_wav_mono

        project_id = path_only.removeprefix(waveform_prefix)
        wav_bytes = _latest_mixdown_wav_bytes(business_root, project_id)
        if wav_bytes is None:
            handler.send_json(404, {"ok": False, "error": "No delivered mixdown found for this project yet."})
            return True
        try:
            target_points = int(parse_qs(parsed.query).get("points", [str(DEFAULT_POINTS)])[0])
        except (TypeError, ValueError):
            target_points = DEFAULT_POINTS
        # as_arrays=True: compute_waveform_peaks immediately np.asarray()s
        # the returned samples anyway -- a waveform view needs the whole
        # track, so unlike the LTAS fix there's no slice to reorder around,
        # just a redundant list<->array round trip to skip (measured ~4x
        # faster on a real 205s track).
        decoded = read_wav_mono(wav_bytes, max_samples=0, as_arrays=True)
        peaks = compute_waveform_peaks(decoded["samples"], decoded["sample_rate"], target_points=target_points)
        handler.send_json(200, {"ok": True, **peaks})
        return True

    if path_only == "/api/automix/status":
        job_id = parse_qs(parsed.query).get("id", [""])[0]
        try:
            job_id = path_safety.validate_identifier(job_id, label="job ID")
        except ValueError as exc:
            handler.send_json(400, {"error": str(exc)})
            return True
        payload = automix_jobs.get_job_status(job_id)
        if payload:
            handler.send_json(200, payload)
        else:
            handler.send_json(404, {"error": "Job not found."})
        return True

    for prefix, ext, content_type, label in (
        ("/api/automix/download/", "*.zip", "application/zip", "Mixdown package"),
        ("/api/automix/play/", "*.wav", "audio/wav", "WAV preview file"),
        ("/api/automix/report/", "*.html", "text/html", "HTML report"),
        # Specific prefix (not "*.json") so this never collides with the
        # before-after comparison JSON written into the same project dir.
        ("/api/automix/manifest/", "mix_decisions_v*.json", "application/json", "Manifest JSON"),
        # Exact filename (not "*.html") so this never collides with the
        # versioned mix_report_v<N>.html glob served by /api/automix/report/.
        ("/api/automix/match-report/", "match_report.html", "text/html", "Match evidence report"),
        # D2.3 (docs/KENN_FUTURE_PLAN.md Phase 2) -- the raw evidence dict
        # behind match_report.html, exact filename (not "*.json") for the
        # same collision-avoidance reason as match-report above.
        ("/api/automix/match-evidence/", "match_evidence.json", "application/json", "Match evidence JSON"),
        (
            "/api/automix/before-after/", "source_vs_delivery_v*.json",
            "application/json", "Before/after comparison",
        ),
    ):
        if path_only.startswith(prefix):
            project_id = path_only.removeprefix(prefix)
            try:
                project_id = path_safety.validate_identifier(project_id, label="project ID")
                proj_dir = path_safety.safe_child(Path(business_root) / "data" / "mix_outputs", project_id)
            except ValueError as exc:
                handler.send_json(400, {"error": str(exc)})
                return True
            if proj_dir.exists():
                files = sorted(list(proj_dir.glob(ext)), key=lambda p: p.stat().st_mtime, reverse=True)
                if files:
                    handler.send_file(files[0], content_type, filename=files[0].name)
                    return True
            handler.send_json(404, {"error": f"{label} not found."})
            return True

    return False


def handle_automix_post(handler, parsed_path: str, business_root: str) -> bool:
    """Handle /api/automix/* POST routes. Returns True if handled, False to fall through."""
    parsed = urlparse("https://host" + parsed_path)
    path = parsed.path

    if path == "/api/automix/advisor-feedback":
        try:
            request = AutomixAdvisorFeedbackRequest.from_payload(handler.read_json_body())
            feedback = advisor_feedback.record_feedback(
                job_id=request.job_id,
                shadow_artifact_id=request.shadow_artifact_id,
                operation_index=request.operation_index,
                decision=request.decision,
                usefulness_rating=request.usefulness_rating,
                explanation_quality_rating=request.explanation_quality_rating,
                audible_improvement_rating=request.audible_improvement_rating,
                preview_artifact_id=request.preview_artifact_id,
                reason=request.reason,
            )
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        except SchemaValidationError as exc:
            handler.send_json(
                400,
                {"error": exc.message, "code": "validation_error", "details": exc.details},
            )
            return True
        except advisor_feedback.AdvisorFeedbackError as exc:
            handler.send_json(400, {"error": str(exc), "code": "invalid_feedback_lineage"})
            return True
        handler.send_json(
            201,
            {
                "ok": True,
                "feedback": {
                    "id": feedback["id"],
                    "decision": feedback["decision"],
                    "operation_index": feedback["operation_index"],
                    "has_audible_evidence": feedback["audible_improvement_rating"] is not None,
                },
            },
        )
        return True

    if path == "/api/automix/advisor-feedback/delete":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        unknown = set(payload) - {"feedback_id"} if isinstance(payload, dict) else {"body"}
        feedback_id = (
            str(payload.get("feedback_id", "")).strip() if isinstance(payload, dict) else ""
        )
        if unknown or not feedback_id:
            handler.send_json(
                400,
                {"error": "feedback_id is required and must be the only field."},
            )
            return True
        if advisor_feedback.delete_feedback(feedback_id):
            handler.send_json(200, {"ok": True, "deleted": True})
        else:
            handler.send_json(404, {"error": "Advisor feedback not found."})
        return True

    if path == "/api/automix/musical-role-corrections/delete":
        try:
            payload = handler.read_json_body()
            if not isinstance(payload, dict) or set(payload) != {"project_id"}:
                raise ValueError("Request must contain exactly project_id.")
            project_id = path_safety.validate_identifier(
                payload.get("project_id"), label="project ID"
            )
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        except ValueError as exc:
            handler.send_json(400, {"error": str(exc), "code": "validation_error"})
            return True
        deleted = musical_role_feedback.delete_corrections_for_project(project_id)
        handler.send_json(200, {"ok": True, "project_id": project_id, "deleted": deleted})
        return True

    if path == "/api/automix/upload":
        try:
            fields = stem_uploads.parse_multipart_form(handler.headers.get("Content-Type", ""), handler.read_body_bytes())
        except Exception as exc:
            handler.send_json(400, {"error": f"Failed to parse form: {exc}"})
            return True

        try:
            file_bytes = fields.get("file")
            if not isinstance(file_bytes, (bytes, bytearray)):
                raise stem_uploads.UploadValidationError("Missing file field.")
            project_id = str(fields.get("project_id", "")).strip()
            key = idempotency.header_value(handler.headers)
            status, response = stem_uploads.store_upload(
                stem_uploads.StemUploadRequest(
                    project_id=project_id,
                    file_bytes=bytes(file_bytes),
                    filename=str(fields.get("file__filename", "stems.zip")),
                    project_label=f"Project {project_id}",
                    uploader_name="Automix",
                    uploader_email=str(fields.get("email", "")),
                    notes="Automix Upload",
                ),
                idempotency_key=key,
            )
        except idempotency.IdempotencyConflict as exc:
            handler.send_json(
                409,
                {"error": str(exc), "code": "idempotency_conflict", "details": {}},
            )
            return True
        except stem_uploads.UploadValidationError as exc:
            handler.send_json(
                exc.status_code,
                {"error": str(exc), "code": "upload_validation_error", "details": {}},
            )
            return True
        except ValueError as exc:
            handler.send_json(
                400,
                {"error": str(exc), "code": "invalid_idempotency_key", "details": {}},
            )
            return True
        handler.send_json(status, response)
        return True

    if path == "/api/automix/reference/upload":
        try:
            fields = stem_uploads.parse_multipart_form(handler.headers.get("Content-Type", ""), handler.read_body_bytes())
        except Exception as exc:
            handler.send_json(400, {"error": f"Failed to parse form: {exc}"})
            return True

        file_bytes = fields.get("file")
        if not isinstance(file_bytes, (bytes, bytearray)):
            handler.send_json(400, {"error": "Missing file field."})
            return True
        if len(file_bytes) > stem_uploads.MAX_UPLOAD_BYTES:
            handler.send_json(413, {"error": "Reference upload exceeds the 500 MB file limit."})
            return True

        # Typed service: staged write + source-artifact registration + reference.uploaded
        # event + idempotency, all in one transaction with atomic finalize/rollback.
        try:
            key = idempotency.header_value(handler.headers)
            status, result = stem_uploads.store_reference(
                str(fields.get("project_id", "")),
                bytes(file_bytes),
                str(fields.get("file__filename", "reference.wav")),
                idempotency_key=key,
            )
        except ValueError as exc:
            handler.send_json(400, {"error": str(exc)})
            return True
        except idempotency.IdempotencyConflict as exc:
            handler.send_json(409, {"error": str(exc), "code": "idempotency_conflict", "details": {}})
            return True

        handler.send_json(status, result)
        return True

    if path == "/api/automix/start":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        try:
            request = AutomixStartRequest.from_payload(payload)
        except SchemaValidationError as exc:
            handler.send_json(
                400,
                {"error": exc.message, "code": "validation_error", "details": exc.details},
            )
            return True
        try:
            key = idempotency.header_value(handler.headers)
            status, response = automix_jobs.queue_job(request, idempotency_key=key)
        except stem_uploads.SourceNotReady as exc:
            handler.send_json(
                409,
                {"error": str(exc), "code": exc.code, "details": {"project_id": request.project_id}},
            )
            return True
        except idempotency.IdempotencyConflict as exc:
            handler.send_json(
                409,
                {"error": str(exc), "code": "idempotency_conflict", "details": {}},
            )
            return True
        except automix_jobs.InvalidMusicalRoleCorrection as exc:
            handler.send_json(
                400,
                {"error": str(exc), "code": exc.code, "details": {"field": "style_prefs"}},
            )
            return True
        except automix_jobs.InvalidArrangementCorrection as exc:
            handler.send_json(
                400,
                {"error": str(exc), "code": exc.code, "details": {"field": "style_prefs"}},
            )
            return True
        except ValueError as exc:
            handler.send_json(
                400,
                {"error": str(exc), "code": "invalid_idempotency_key", "details": {}},
            )
            return True
        handler.send_json(status, response)
        return True

    if path == "/api/automix/revise":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        try:
            request = AutomixRevisionRequest.from_payload(payload)
        except SchemaValidationError as exc:
            handler.send_json(
                400,
                {"error": exc.message, "code": "validation_error", "details": exc.details},
            )
            return True

        try:
            key = idempotency.header_value(handler.headers)
            status, response = automix_jobs.queue_revision(request, idempotency_key=key)
        except stem_uploads.SourceNotReady as exc:
            handler.send_json(
                409,
                {"error": str(exc), "code": exc.code, "details": {"project_id": request.project_id}},
            )
            return True
        except idempotency.IdempotencyConflict as exc:
            handler.send_json(
                409,
                {"error": str(exc), "code": "idempotency_conflict", "details": {}},
            )
            return True
        except automix_jobs.NoCompletedMix as exc:
            handler.send_json(400, {"error": str(exc), "code": "no_completed_mix", "details": {}})
            return True
        except ValueError as exc:
            handler.send_json(
                400,
                {"error": str(exc), "code": "invalid_idempotency_key", "details": {}},
            )
            return True
        handler.send_json(status, response)
        return True

    # M8.5 — Natural Language Mix Control
    if path == "/api/automix/nl-adjust":
        try:
            payload = handler.read_json_body()
        except Exception:
            handler.send_json(400, {"error": "Invalid JSON body."})
            return True
        project_id = str(payload.get("project_id") or "").strip()
        instruction = str(payload.get("instruction") or "").strip()
        if not project_id or not instruction:
            handler.send_json(400, {"error": "project_id and instruction are required."})
            return True
        try:
            from audio_analysis.integration.mix_intent import parse_mix_intent
            intent = parse_mix_intent(instruction, {})
            # Describe the proposed adjustment in human-readable form
            sign = "+" if intent["direction"] == "up" else "-"
            magnitude_map = {"subtle": "0.5 dB", "moderate": "1.5 dB", "strong": "3.0 dB"}
            magnitude_str = magnitude_map.get(intent["magnitude"], "1.5 dB")
            stem_label = intent["target_stem"] if intent["target_stem"] != "all" else "all stems"
            description = (
                f"Adjust {stem_label}: {sign}{magnitude_str} on "
                f"{intent['parameter'].replace('_', ' ')}."
            )
            handler.send_json(200, {
                "ok": True,
                "intent": intent,
                "instruction": instruction,
                "description": description,
                "note": (
                    "Intent parsed (preview only, not applied). To apply, submit this "
                    "same instruction as feedback via POST /api/automix/revise "
                    "(project_id + feedback)."
                ),
            })
        except Exception as exc:
            handler.send_json(500, {"ok": False, "error": str(exc)})
        return True

    # "Why did you do that" -- ground a KENN answer in this project's actual
    # latest render decisions (masking/limiter/EQ corrections and why),
    # rather than generic mixing advice.
    if path == "/api/automix/explain":
        try:
            payload = handler.read_json_body()
        except Exception:
            handler.send_json(400, {"error": "Invalid JSON body."})
            return True
        project_id = str(payload.get("project_id") or "").strip()
        question = str(payload.get("question") or "").strip()
        if not project_id or not question:
            handler.send_json(400, {"error": "project_id and question are required."})
            return True
        import automix_kenn_explain
        result = automix_kenn_explain.ask_kenn_about_render(project_id, question)
        handler.send_json(200 if result.get("ok") else 502, result)
        return True

    return False
