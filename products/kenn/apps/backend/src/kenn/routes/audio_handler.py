"""Audio analysis, mix review, masking, and reference-comparison routes."""

from __future__ import annotations

import base64
import json
import uuid
from pathlib import Path
from typing import Any


def handle_mix_review_step(handler: Any, mix_review: Any, payload: dict) -> None:
    if not mix_review:
        handler.send_json(503, {"error": "Mix Review Lab is unavailable."})
        return
    try:
        result = mix_review.update_revision_agent_step(
            str(payload.get("review_id", "")),
            str(payload.get("step_id", "")),
            str(payload.get("status", "")),
        )
        handler.send_json(200 if result.get("ok") else 400, result)
    except Exception as exc:
        handler.send_json(500, {"error": f"Failed to update revision step: {exc}"})


def handle_audio_analysis(handler: Any, *, include_pink_noise_reference: bool = False) -> None:
    """Analyze one uploaded WAV with the KENN-owned analyzer.

    This endpoint is intentionally separate from the legacy Mix Review
    workflow: it returns the versioned spectral evidence contract and
    never writes audio or calls an external analyzer.
    """
    content_type = handler.headers.get("Content-Type", "")
    if "multipart/form-data" not in content_type:
        handler.send_json(400, {"ok": False, "error": "Expected multipart/form-data upload."})
        return
    try:
        length = int(handler.headers.get("Content-Length", "0"))
    except ValueError:
        handler.send_json(400, {"ok": False, "error": "Invalid Content-Length."})
        return
    from kenn.core.audio_analysis import MAX_INPUT_BYTES, analyze_wav

    if length <= 0:
        handler.send_json(400, {"ok": False, "error": "Upload body is required."})
        return
    if length > MAX_INPUT_BYTES + 2 * 1024 * 1024:
        handler.send_json(413, {"ok": False, "error": "Audio upload is too large."})
        return
    try:
        from kenn.server import _multipart_files

        body = handler.rfile.read(length)
        selected: tuple[bytes, str] | None = None
        for _name, payload, filename in _multipart_files(content_type, body):
            if filename.lower().endswith(".wav") or selected is None:
                selected = (payload, filename)
                if filename.lower().endswith(".wav"):
                    break
        if selected is None:
            handler.send_json(400, {"ok": False, "error": "No audio file attached."})
            return
        payload, filename = selected
        result = analyze_wav(
            payload,
            filename=filename,
            include_pink_noise_reference=include_pink_noise_reference,
        )
        handler.send_json(200 if result.get("ok") else 400, result)
    except Exception as exc:
        handler.send_json(400, {"ok": False, "error": f"Audio analysis upload failed: {exc}"})


def handle_audio_analysis_compare(handler: Any) -> None:
    """Compare two WAV analyses without retaining either source file."""
    content_type = handler.headers.get("Content-Type", "")
    if "multipart/form-data" not in content_type:
        handler.send_json(400, {"ok": False, "error": "Expected multipart/form-data upload."})
        return
    try:
        length = int(handler.headers.get("Content-Length", "0"))
    except ValueError:
        handler.send_json(400, {"ok": False, "error": "Invalid Content-Length."})
        return
    from kenn.core.audio_analysis import MAX_INPUT_BYTES, analyze_wav

    if length <= 0 or length > (2 * MAX_INPUT_BYTES + 4 * 1024 * 1024):
        handler.send_json(413 if length > 0 else 400, {"ok": False, "error": "Two bounded WAV uploads are required."})
        return
    try:
        from kenn.server import _multipart_files

        files = [item for item in _multipart_files(content_type, handler.rfile.read(length)) if item[2].lower().endswith(".wav")]
        if len(files) < 2:
            handler.send_json(400, {"ok": False, "error": "Attach two WAV files for comparison."})
            return
        first_name, first_bytes, first_filename = files[0]
        second_name, second_bytes, second_filename = files[1]
        if len(first_bytes) > MAX_INPUT_BYTES or len(second_bytes) > MAX_INPUT_BYTES:
            handler.send_json(413, {"ok": False, "error": "Each WAV file exceeds the analysis size limit."})
            return
        first = analyze_wav(first_bytes, filename=first_filename)
        second = analyze_wav(second_bytes, filename=second_filename)
        if not first.get("ok") or not second.get("ok"):
            handler.send_json(400, {"ok": False, "error": "Both WAV files must analyze successfully.", "analysis_a": first, "analysis_b": second})
            return
        metrics_a = first.get("metrics", {})
        metrics_b = second.get("metrics", {})
        deltas = {}
        for key in sorted(set(metrics_a) & set(metrics_b)):
            if isinstance(metrics_a[key], (int, float)) and isinstance(metrics_b[key], (int, float)):
                deltas[key] = {
                    "a": metrics_a[key],
                    "b": metrics_b[key],
                    "delta_b_minus_a": round(float(metrics_b[key]) - float(metrics_a[key]), 6),
                }
        handler.send_json(200, {
            "schema": "kenn.audio_analysis.comparison.v1",
            "ok": True,
            "analysis_version": first.get("analysis_version"),
            "comparable_settings": first.get("analysis_version") == second.get("analysis_version"),
            "source_a": {"filename": first_filename, "input_hash": first.get("input_hash")},
            "source_b": {"filename": second_filename, "input_hash": second.get("input_hash")},
            "analysis_a": first,
            "analysis_b": second,
            "metric_deltas": deltas,
            "limitations": [
                "Deltas compare measured fields only; they do not establish that a mix is musically better.",
                "Files are analyzed in memory and source audio is not retained by this endpoint.",
            ],
        })
    except Exception as exc:
        handler.send_json(400, {"ok": False, "error": f"Audio comparison failed: {exc}"})


def handle_mix_review_masking(handler: Any) -> None:
    """Analyze frequency-band energy competition across 2+ uploaded stems.

    Deliberately separate from ``handle_mix_review``: masking is a
    question about multiple isolated sources competing for the same
    frequency space, which a single finished mixdown cannot answer, so
    this takes several named stem uploads instead of one mixed file.
    """
    content_type = handler.headers.get("Content-Type", "")
    if "multipart/form-data" not in content_type:
        handler.send_json(400, {"ok": False, "error": "Expected multipart/form-data upload."})
        return
    try:
        length = int(handler.headers.get("Content-Length", "0"))
    except ValueError:
        handler.send_json(400, {"ok": False, "error": "Invalid Content-Length."})
        return
    from kenn.core.local_mix_review_service import analyze_stem_masking, MAX_UPLOAD_BYTES, _masking_engine

    max_total = _masking_engine.MAX_STEMS * MAX_UPLOAD_BYTES + 4 * 1024 * 1024
    if length <= 0 or length > max_total:
        handler.send_json(413 if length > 0 else 400, {"ok": False, "error": "One or more bounded WAV stem uploads are required."})
        return
    try:
        from kenn.server import _multipart_files

        files = [item for item in _multipart_files(content_type, handler.rfile.read(length)) if item[2].lower().endswith(".wav")]
        if len(files) < 2:
            handler.send_json(400, {"ok": False, "error": "Attach at least 2 WAV stems to analyze masking between them."})
            return
        oversized = [filename for _name, payload, filename in files if len(payload) > MAX_UPLOAD_BYTES]
        if oversized:
            handler.send_json(413, {"ok": False, "error": f"Stem(s) exceed the analysis size limit: {', '.join(oversized)}"})
            return
        stems = [(Path(filename).stem[:96], payload) for _name, payload, filename in files]
        result = analyze_stem_masking(stems)
        handler.send_json(200 if result.get("ok") else 400, result)
    except Exception as exc:
        handler.send_json(500, {"ok": False, "error": f"Masking analysis failed: {exc}"})


def handle_mix_review(handler: Any, mix_review: Any) -> None:
    if not mix_review:
        handler.send_json(503, {"error": "Mix Review Lab is unavailable."})
        return
    content_type = handler.headers.get("Content-Type", "")
    if "multipart/form-data" not in content_type:
        handler.send_json(400, {"error": "Expected multipart/form-data upload."})
        return
    try:
        length = int(handler.headers.get("Content-Length", "0"))
    except ValueError:
        handler.send_json(400, {"error": "Invalid Content-Length."})
        return
    if length <= 0:
        handler.send_json(400, {"error": "Upload body is required."})
        return
    if length > mix_review.MAX_UPLOAD_BYTES:
        handler.send_json(413, {"error": "WAV upload is too large."})
        return
    try:
        from kenn.server import resolve_session_project

        body = handler.rfile.read(length)
        project_id = ""
        try:
            import stem_uploads
            fields = stem_uploads.parse_multipart_form(content_type, body)
            project_id = resolve_session_project(str(fields.get("session_id", "")).strip())
        except Exception:
            project_id = ""
        result = mix_review.handle_multipart_review(content_type, body, project_id_override=project_id)
        handler.send_json(200 if result.get("ok") else 400, result)
    except Exception as exc:
        handler.send_json(500, {"error": f"Mix review upload failed: {exc}"})


def handle_mix_reference(handler: Any, mix_review: Any) -> None:
    if not mix_review:
        handler.send_json(503, {"error": "Mix Review Lab is unavailable."})
        return
    content_type = handler.headers.get("Content-Type", "")
    if "multipart/form-data" not in content_type:
        handler.send_json(400, {"error": "Expected multipart/form-data upload."})
        return
    try:
        length = int(handler.headers.get("Content-Length", "0"))
    except ValueError:
        handler.send_json(400, {"error": "Invalid Content-Length."})
        return
    if length <= 0:
        handler.send_json(400, {"error": "Upload body is required."})
        return
    # The reference endpoint accepts two independently bounded WAVs. Keep
    # a small multipart allowance, but do not reject two valid inputs just
    # because their combined request exceeds a single-file limit.
    if length > (2 * mix_review.MAX_UPLOAD_BYTES + 2 * 1024 * 1024):
        handler.send_json(413, {"error": "Reference WAV uploads are too large."})
        return
    try:
        body = handler.rfile.read(length)
        result = mix_review.handle_multipart_reference(content_type, body)
        handler.send_json(201 if result.get("ok") else 400, result)
    except Exception as exc:
        handler.send_json(500, {"error": f"Reference upload failed: {exc}"})


def handle_mix_reference_json(handler: Any, mix_review: Any) -> None:
    if not mix_review:
        handler.send_json(503, {"error": "Mix Review Lab is unavailable."})
        return
    try:
        length = int(handler.headers.get("Content-Length", "0"))
        body = handler.rfile.read(length)
        payload = json.loads(body.decode("utf-8"))
    except Exception as exc:
        handler.send_json(400, {"error": f"Invalid JSON body: {exc}"})
        return

    mix_b64 = payload.get("mix_wav_base64") or payload.get("mix_base64") or ""
    ref_b64 = payload.get("ref_wav_base64") or payload.get("reference_base64") or ""
    mix_name = str(payload.get("mix_name") or "mix.wav").strip()
    ref_name = str(payload.get("ref_name") or "reference.wav").strip()

    if not mix_b64 or not ref_b64:
        handler.send_json(400, {"error": "Both mix_wav_base64 and ref_wav_base64 are required."})
        return

    try:
        mix_bytes = base64.b64decode(mix_b64)
        ref_bytes = base64.b64decode(ref_b64)
    except Exception as exc:
        handler.send_json(400, {"error": f"Invalid base64 payload: {exc}"})
        return

    try:
        from kenn.core.local_mix_review_service import compare_reference_audio
        result = compare_reference_audio(mix_bytes, mix_name, ref_bytes, ref_name)
        if not result.get("ok"):
            handler.send_json(400, result)
            return
        review_id = f"reference-{uuid.uuid4().hex}"
        review = {
            **result,
            "review_id": review_id,
            "status": "completed",
            "storage": "metadata_only",
            "audio_retained": False,
        }
        with mix_review._lock:
            mix_review._reviews[review_id] = review
            mix_review._prune_reviews()
            mix_review._persist()
        handler.send_json(200, {"ok": True, "review_id": review_id, "status": "completed", "review": review})
    except Exception as exc:
        import traceback
        traceback.print_exc()
        handler.send_json(500, {"error": f"Reference comparison failed: {exc}"})

