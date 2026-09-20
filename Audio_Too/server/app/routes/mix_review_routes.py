"""Mix Review and audio analysis GET/POST routes."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import path_safety
import mix_report_tokens
import podcast_report_store
import podcast_report_tokens
from audio_analysis.mix_review import mix_doctor, mix_review
from app.media_streaming import send_audio_file_range


def handle_mix_report_public_get(handler, full_path: str) -> bool:
    """Public, signed-token, read-only Mix Doctor report view (`/mix-report/<id>`).

    Classified SIGNED_TOKEN in `audio_too.endpoint_policy`, so it is reachable
    without a dashboard session; access is scoped to a single review id by an
    HMAC token (or an authenticated dashboard user). Read-only: it renders an
    existing review and never accepts uploads or mutates anything.
    """
    parsed = urlparse(full_path)
    if not parsed.path.startswith("/mix-report/"):
        return False
    review_id = parsed.path[len("/mix-report/"):].strip("/")
    if review_id.endswith(".html"):
        review_id = review_id[:-5]

    # /mix-report/<id>/status -- a lightweight JSON poll for a review still
    # being analysed in the background (save_review's background=True path),
    # so a self-serve caller can check readiness without re-fetching/parsing
    # the full HTML report on every poll. Same SIGNED_TOKEN classification
    # as the report itself (endpoint_policy matches on the "/mix-report/"
    # prefix), same token check.
    is_status_poll = review_id.endswith("/status")
    if is_status_poll:
        review_id = review_id[: -len("/status")]

    token = parse_qs(parsed.query).get("token", [""])[0]
    if not (handler.authorized() or mix_report_tokens.verify_report_token(review_id, token)):
        if is_status_poll:
            handler.send_json(401, {"ok": False, "error": "Invalid or expired report link."})
        else:
            handler.send_bytes(401, b"Invalid or expired report link.", "text/plain; charset=utf-8")
        return True

    status = mix_review.mix_review_status(review_id)
    review = status.get("review") if status.get("ok") else None
    if not review:
        if is_status_poll:
            handler.send_json(404, {"ok": False, "error": "Mix report not found."})
        else:
            handler.send_bytes(404, b"Mix report not found.", "text/plain; charset=utf-8")
        return True

    if is_status_poll:
        handler.send_json(200, {
            "ok": True,
            "id": review_id,
            "status": review.get("status", "pending"),
            "error": review.get("error"),
        })
        return True

    html_body = mix_doctor.render_report_html(review)
    handler.send_bytes(200, html_body.encode("utf-8"), "text/html; charset=utf-8")
    return True


def handle_podcast_report_public_get(handler, full_path: str) -> bool:
    """Public, signed-token, read-only podcast-check report view
    (`/podcast-report/<id>`) -- the "like Mix Doctor" shareable link
    plan.md's own NEXT section calls for. Analysis is synchronous (no
    background worker), so the row already holds the fully-rendered HTML;
    this just serves it back after verifying the token.
    """
    parsed = urlparse(full_path)
    if not parsed.path.startswith("/podcast-report/"):
        return False
    report_id = parsed.path[len("/podcast-report/"):].strip("/")
    if report_id.endswith(".html"):
        report_id = report_id[:-5]

    token = parse_qs(parsed.query).get("token", [""])[0]
    if not (handler.authorized() or podcast_report_tokens.verify_podcast_report_token(report_id, token)):
        handler.send_bytes(401, b"Invalid or expired report link.", "text/plain; charset=utf-8")
        return True

    item = podcast_report_store.get_podcast_report(report_id)
    if not item:
        handler.send_bytes(404, b"Podcast report not found.", "text/plain; charset=utf-8")
        return True

    html_body = str(item.get("html_report", ""))
    handler.send_bytes(200, html_body.encode("utf-8"), "text/html; charset=utf-8")
    return True


def handle_mix_review_get(handler, parsed_path: str, business_root: str) -> bool:
    """Handle Mix Review GET routes. Returns True if handled."""
    parsed = urlparse("https://host" + parsed_path)
    path = parsed.path

    if path == "/api/admin/mix-review-status":
        query = parse_qs(parsed.query)
        review_id = query.get("id", [""])[0]
        handler.send_json(200, mix_review.mix_review_status(review_id))
        return True

    if path == "/api/admin/mix-review-audio":
        query = parse_qs(parsed.query)
        review_id = query.get("id", [""])[0]
        audio_type = query.get("type", ["mix"])[0]
        file_path = mix_review.review_audio_path(review_id, type=audio_type)
        if not file_path:
            handler.send_json(404, {"error": "Audio file not found."})
            return True
        send_audio_file_range(handler, file_path)
        return True

    if path == "/api/admin/mix-reference-audio":
        query = parse_qs(parsed.query)
        reference_id = query.get("id", [""])[0]
        file_path = mix_review.reference_audio_path(reference_id)
        if not file_path:
            handler.send_json(404, {"error": "Audio file not found."})
            return True
        send_audio_file_range(handler, file_path)
        return True

    if path == "/api/admin/mix-targets":
        handler.send_json(200, mix_review.get_mix_review_targets())
        return True

    if path == "/api/admin/mix-reviews":
        handler.send_json(200, {"items": mix_review.list_reviews()})
        return True

    if path == "/api/admin/mix-review-qa":
        query = parse_qs(parsed.query)
        portfolio_audio_root = Path(business_root) / "Portfolio" / "audio"
        subpath = query.get("path", [""])[0]
        try:
            scan_root = path_safety.safe_child(portfolio_audio_root, subpath) if subpath else portfolio_audio_root
        except ValueError as exc:
            handler.send_json(400, {"error": str(exc)})
            return True
        try:
            scan = mix_review.scan_audio_files(scan_root, recursive=query.get("recursive", ["1"])[0] != "0")
            scan["benchmark"] = mix_review.scan_audio_benchmark(scan)
            scan["qa"] = mix_review.batch_qa_summary(scan)
            handler.send_json(200, scan)
        except Exception as exc:
            handler.send_json(500, {"error": f"Mix review QA scan failed: {exc}"})
        return True

    if path == "/api/admin/mix-references":
        handler.send_json(200, {"items": mix_review.list_references()})
        return True

    if path.startswith("/api/admin/mix-review-report/"):
        report_ref = path.rsplit("/", 1)[-1]
        review_id = report_ref.rsplit(".", 1)[0]
        if report_ref.endswith(".json"):
            body = mix_review.report_json_bytes(review_id)
            if body is None:
                handler.send_json(404, {"error": "Mix review report not found."})
                return True
            handler.send_bytes(200, body, "application/json", filename=f"mix-review-{review_id}.json")
            return True
        if report_ref.endswith(".html"):
            html_body = mix_review.report_html(review_id)
            if html_body is None:
                handler.send_json(404, {"error": "Mix review report not found."})
                return True
            handler.send_bytes(200, html_body.encode("utf-8"), "text/html; charset=utf-8")
            return True

    if path == "/api/admin/mix-review-rack":
        try:
            query = parse_qs(parsed.query)
            review_id = query.get("id", [""])[0]
            adg_bytes = mix_review.generate_correction_rack(review_id)
            if not adg_bytes:
                handler.send_json(404, {"error": "Rack generation failed. Mix review not found."})
                return True
            handler.send_bytes(
                200,
                adg_bytes,
                "application/octet-stream",
                filename=f"Mix_Review_Correction_{review_id}.adg"
            )
        except Exception as exc:
            handler.send_json(500, {"error": f"Failed to generate Ableton rack: {exc}"})
        return True

    if path == "/api/admin/mix-review-match-preset":
        try:
            query = parse_qs(parsed.query)
            review_id = query.get("id", [""])[0]
            preset_format = query.get("format", ["ableton"])[0].strip().lower()

            # Ensure path holds the audio_analysis package parent for the import
            tool_path = str(Path(business_root).parent / "studio" / "audio_analysis")
            if tool_path not in sys.path:
                sys.path.append(tool_path)
            from audio_analysis.analysis_core import reference_matching

            review = mix_review.review_by_id(review_id)
            if not review:
                handler.send_json(404, {"error": "Mix review not found."})
                return True

            comparison = review.get("comparison") or {}
            eq_bands = comparison.get("eq_bands")

            if eq_bands:
                if preset_format in {"proq", "proq3", "ffp"}:
                    preset_bytes = reference_matching.export_pro_q3_preset(eq_bands)
                    preset_filename = f"Reference_Match_{review_id}.ffp"
                else:
                    preset_bytes = reference_matching.export_eq8_preset_parametric(eq_bands)
                    preset_filename = f"Reference_Match_{review_id}.adv"
            else:
                mix_bands = review.get("metrics", {}).get("perceptual_bands", {})
                reference_id = review.get("reference_id")
                if not reference_id:
                    handler.send_json(400, {"error": "This mix review was not compared against a reference track."})
                    return True

                if str(reference_id).startswith("genre_"):
                    goal_key = reference_id[6:]
                    from audio_analysis.analysis_core.genre_profiles import GENRE_SEED_PROFILES, map_40_to_7_bands
                    if goal_key in GENRE_SEED_PROFILES:
                        seed = GENRE_SEED_PROFILES[goal_key]
                        ref_bands = map_40_to_7_bands(seed["profile"])
                    else:
                        handler.send_json(404, {"error": f"Genre profile {goal_key} not found."})
                        return True
                else:
                    reference = mix_review.reference_by_id(reference_id)
                    if not reference:
                        handler.send_json(404, {"error": f"Reference track {reference_id} not found."})
                        return True

                    ref_bands = reference.get("metrics", {}).get("perceptual_bands", {})
                    if not ref_bands and "bands" in reference.get("metrics", {}):
                        from audio_analysis.analysis_core.dsp_metrics import perceived_loudness_contribution
                        phon_level = float(review.get("phon_level", 60.0))
                        ref_bands = perceived_loudness_contribution(reference["metrics"]["bands"], phon_level)

                if not ref_bands:
                    handler.send_json(400, {"error": "Reference track has no perceptual band metrics."})
                    return True

                matching_gains = reference_matching.compute_eq_matching_curve(mix_bands, ref_bands)
                if preset_format in {"proq", "proq3", "ffp"}:
                    handler.send_json(400, {"error": "Pro-Q export requires a 40-band reference profile."})
                    return True
                preset_bytes = reference_matching.export_eq8_preset_adv(matching_gains)
                preset_filename = f"Reference_Match_{review_id}.adv"

            handler.send_bytes(
                200,
                preset_bytes,
                "application/octet-stream",
                filename=preset_filename,
            )
        except Exception as exc:
            handler.send_json(500, {"error": f"Failed to generate EQ Eight match preset: {exc}"})
        return True

    if path == "/api/admin/mix-review-repair-chains":
        query = parse_qs(parsed.query)
        review_id = query.get("id", [""])[0]
        body = mix_review.repair_chains_json_bytes(review_id)
        if body is None:
            handler.send_json(404, {"error": "Mix review not found."})
            return True
        handler.send_bytes(
            200,
            body,
            "application/json",
            filename=f"mix-review-repair-chains-{review_id}.json",
        )
        return True

    return False


def handle_mix_review_post(handler, parsed_path: str, *, log_event: Callable[[str, str, str], None]) -> bool:
    """Handle Mix Review POST routes. Returns True if handled."""
    parsed = urlparse("https://host" + parsed_path)
    path = parsed.path

    if path == "/api/admin/mix-stems":
        try:
            result = mix_review.handle_stems_upload(handler.headers.get("Content-Type", ""), handler.read_body_bytes())
            if result.get("ok"):
                log_event("mix_stems_analyzed", "Stems masking analyzed", "dashboard")
            handler.send_json(200 if result.get("ok") else 400, result)
        except Exception as exc:
            handler.send_json(500, {"error": f"Stems masking upload failed: {exc}"})
        return True

    if path == "/api/admin/mix-review":
        try:
            result = mix_review.handle_multipart_review(
                handler.headers.get("Content-Type", ""),
                handler.read_body_bytes(),
                correlation_id=handler.request_id(),
            )
            if result.get("ok"):
                review = result.get("review", {})
                log_event("mix_review_created", review.get("title", ""), "dashboard")
            handler.send_json(201 if result.get("ok") else 400, result)
        except Exception as exc:
            handler.send_json(500, {"error": f"Mix review upload failed: {exc}"})
        return True

    if path == "/api/admin/mix-review-feedback":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        result = mix_review.record_review_feedback(
            str(payload.get("review_id", "")),
            str(payload.get("decision", "")),
            str(payload.get("note", "")),
        )
        if result.get("ok"):
            log_event("mix_review_feedback", f"{payload.get('decision', '')}: {payload.get('review_id', '')}", "dashboard")
        handler.send_json(201 if result.get("ok") else 400, result)
        return True

    if path == "/api/admin/music-analysis":
        try:
            result = mix_review.handle_multipart_music_analysis(handler.headers.get("Content-Type", ""), handler.read_body_bytes())
            if result.get("ok"):
                analysis = result.get("analysis", {})
                log_event("music_analysis_created", analysis.get("filename", ""), "dashboard")
            handler.send_json(200 if result.get("ok") else 400, result)
        except Exception as exc:
            handler.send_json(500, {"error": f"Music analysis upload failed: {exc}"})
        return True

    if path == "/api/admin/waveform":
        try:
            result = mix_review.handle_multipart_waveform(handler.headers.get("Content-Type", ""), handler.read_body_bytes())
            handler.send_json(200 if result.get("ok") else 400, result)
        except Exception as exc:
            handler.send_json(500, {"error": f"Waveform upload failed: {exc}"})
        return True

    if path == "/api/admin/mix-reference":
        try:
            result = mix_review.handle_multipart_reference(handler.headers.get("Content-Type", ""), handler.read_body_bytes())
            if result.get("ok"):
                reference = result.get("reference", {})
                log_event("mix_reference_created", reference.get("name", ""), "dashboard")
            handler.send_json(201 if result.get("ok") else 400, result)
        except Exception as exc:
            handler.send_json(500, {"error": f"Reference upload failed: {exc}"})
        return True

    if path == "/api/admin/mix-targets":
        try:
            payload = handler.read_json_body()
        except json.JSONDecodeError:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        result = mix_review.save_mix_review_targets(payload)
        if result.get("ok"):
            log_event("mix_targets_updated", "Mix review goals and targets calibrated", "dashboard")
        handler.send_json(200 if result.get("ok") else 400, result)
        return True

    if path == "/api/admin/mix-review/compare-ab":
        try:
            payload = handler.read_json_body()
        except Exception:
            handler.send_json(400, {"error": "Invalid JSON."})
            return True
        review_id_a = str(payload.get("review_id_a") or "").strip()
        review_id_b = str(payload.get("review_id_b") or "").strip()
        if not review_id_a or not review_id_b:
            handler.send_json(400, {"error": "review_id_a and review_id_b are required"})
            return True
        try:
            from audio_analysis.analysis_core.dsp_metrics import BANDS
            from audio_analysis.integration.comparison import compare_metrics, match_score
            report_a = mix_review.review_by_id(review_id_a)
            report_b = mix_review.review_by_id(review_id_b)
            if not report_a or not report_b:
                handler.send_json(404, {"error": "One or both reviews not found."})
                return True
            metrics_a = report_a.get("metrics") or {}
            metrics_b = report_b.get("metrics") or {}
            comparison = compare_metrics(metrics_a, metrics_b, BANDS)
            comparison["match_score"] = match_score(comparison)
            handler.send_json(200, {
                "ok": True,
                "comparison": comparison,
                "review_a": {
                    "id": review_id_a,
                    "title": report_a.get("title") or report_a.get("metrics", {}).get("filename", "Mix A"),
                    "bands": metrics_a.get("bands") or {},
                    "perceptual_bands": metrics_a.get("perceptual_bands") or {},
                    "integrated_lufs": metrics_a.get("integrated_lufs"),
                },
                "review_b": {
                    "id": review_id_b,
                    "title": report_b.get("title") or report_b.get("metrics", {}).get("filename", "Mix B"),
                    "bands": metrics_b.get("bands") or {},
                    "perceptual_bands": metrics_b.get("perceptual_bands") or {},
                    "integrated_lufs": metrics_b.get("integrated_lufs"),
                },
            })
        except Exception as exc:
            handler.send_json(500, {"error": f"A/B comparison failed: {exc}"})
        return True

    return False
