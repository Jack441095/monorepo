"""Modular Mix Review and Reference Matching route handlers for KENN.

Handles:
- /api/mix-review-status
- /api/mix-review-report/<id>.json
- /api/mix-review/reference
- /api/mix-review/reference-match
- /api/mix-review/reference-preset/<id>.adv
"""

from __future__ import annotations

import base64
import uuid
from typing import Any


def handle_mix_review_status(review_id: str, mix_review_service: Any) -> tuple[int, dict[str, Any]]:
    """Retrieve metadata and results for an analyzed mix review."""
    if not mix_review_service:
        return 503, {"error": "Mix Review Lab is unavailable."}
    clean_id = str(review_id or "").strip()
    if not clean_id:
        return 400, {"error": "Review ID is required."}
    result = mix_review_service.mix_review_status(clean_id)
    if not result.get("ok"):
        return 404, result
    return 200, result


def handle_mix_review_report_json(review_id: str, mix_review_service: Any) -> tuple[int, bytes | None]:
    """Return JSON bytes for a completed mix review report."""
    if not mix_review_service:
        return 503, None
    clean_id = str(review_id or "").strip()
    if not clean_id:
        return 400, None
    body = mix_review_service.report_json_bytes(clean_id)
    if body is None:
        return 404, None
    return 200, body


def handle_mix_review_reference_json(
    payload: dict[str, Any],
    mix_review_service: Any,
) -> tuple[int, dict[str, Any]]:
    """Compare a mixdown against a commercial reference from JSON payload with base64 audio."""
    if not mix_review_service:
        return 503, {"error": "Mix Review Lab is unavailable."}

    mix_b64 = payload.get("mix_wav_base64") or payload.get("mix_base64") or ""
    ref_b64 = payload.get("ref_wav_base64") or payload.get("reference_base64") or ""
    mix_name = str(payload.get("mix_name") or "mix.wav").strip()
    ref_name = str(payload.get("ref_name") or "reference.wav").strip()

    if not mix_b64 or not ref_b64:
        return 400, {"error": "Both mix_wav_base64 and ref_wav_base64 are required."}

    try:
        mix_bytes = base64.b64decode(mix_b64)
        ref_bytes = base64.b64decode(ref_b64)
    except Exception as exc:
        return 400, {"error": f"Invalid base64 payload: {exc}"}

    try:
        from kenn.core.local_mix_review_service import compare_reference_audio
        result = compare_reference_audio(mix_bytes, mix_name, ref_bytes, ref_name)
        if not result.get("ok"):
            return 400, result
        review_id = f"reference-{uuid.uuid4().hex}"
        review = {
            **result,
            "review_id": review_id,
            "status": "completed",
            "storage": "metadata_only",
            "audio_retained": False,
        }
        with mix_review_service._lock:
            mix_review_service._reviews[review_id] = review
            mix_review_service._prune_reviews()
            mix_review_service._persist()
        return 200, {"ok": True, "review_id": review_id, "status": "completed", "review": review}
    except Exception as exc:
        return 500, {"error": f"Reference comparison failed: {exc}"}


def handle_reference_preset_download(
    review_id: str,
    mix_review_service: Any,
) -> tuple[int, bytes | None, str]:
    """Serve gzipped Ableton Live 12 EQ Eight (.adv) preset bytes for a reference match."""
    if not mix_review_service:
        return 503, None, ""
    clean_id = str(review_id or "").replace(".adv", "").strip()
    res = mix_review_service.mix_review_status(clean_id)
    review = res.get("review") or {}
    adv_b64 = (review.get("reference_comparison") or {}).get("eq8_preset_adv_base64")
    if not adv_b64:
        return 404, None, ""
    try:
        adv_bytes = base64.b64decode(adv_b64)
        return 200, adv_bytes, f"Reference_Match_{clean_id}.adv"
    except Exception:
        return 500, None, ""

