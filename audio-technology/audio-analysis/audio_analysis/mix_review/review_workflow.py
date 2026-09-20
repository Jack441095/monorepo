from __future__ import annotations

from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime, timezone
import json
import logging
import threading
import wave
from pathlib import Path
from typing import Callable
from uuid import uuid4

ANALYSIS_TIMEOUT_SECONDS = 180

logger = logging.getLogger(__name__)

# Global flag: set to False to disable automatic upload deletion
_AUTO_DELETE_UPLOADS = True


def set_auto_delete_uploads(enabled: bool) -> None:
    """Enable or disable automatic deletion of uploaded audio after analysis.

    When enabled (default), the original audio file is deleted immediately
    after the report JSON is saved. The report retains all extracted metrics.
    Reference audio files are also deleted unless keep_reference is set.
    """
    global _AUTO_DELETE_UPLOADS
    _AUTO_DELETE_UPLOADS = enabled
    logger.info("Auto-delete uploads set to %s", enabled)


@dataclass(frozen=True)
class ReviewArtifactRegistry:
    prepare: Callable
    register: Callable
    discard: Callable
    public: Callable
    by_external_key: Callable
    emit: Callable


@dataclass(frozen=True)
class ReviewWorkflowContext:
    analyze_wav: Callable
    compare_metrics: Callable
    comparison_advice: Callable
    connect: Callable
    find_similar_reviews: Callable
    generate_mix_critique: Callable
    generate_prose_summary: Callable
    init_reviews_table: Callable
    latest_review_for_title: Callable
    max_upload_bytes: int
    now: Callable
    priority_actions: Callable
    reference_by_id: Callable
    reference_envelope_for_genre: Callable
    reference_coaching: Callable
    refresh_closed_loop_payloads: Callable
    refresh_report_interpretation: Callable
    report_root: Path
    report_summary: Callable
    revision_agent_plan: Callable
    revision_coaching: Callable
    revision_impact_summary: Callable
    revision_lesson: Callable
    upload_root: Path
    validate_wav_upload: Callable
    version_advice: Callable
    artifact_registry: ReviewArtifactRegistry | None = None
    # Stage 10 — optional so existing ``ReviewWorkflowContext(...)`` call sites
    # (including tests) that predate this wiring keep working unchanged; when
    # absent, ``apply_version_and_reference_context`` simply skips these fields.
    generate_mix_review_critique: Callable | None = None
    classify_mix_style: Callable | None = None
    # D1.7 (docs/KENN_FUTURE_PLAN.md Phase 1) -- project continuity for the
    # reference track a song_project is being mixed against. Optional for
    # the same reason as the two fields above: existing
    # ReviewWorkflowContext(...) call sites (including tests) predate this
    # wiring and keep working unchanged when absent.
    get_song_project: Callable | None = None
    set_project_reference_track: Callable | None = None


def _media_type(filename: str) -> str:
    return {
        ".wav": "audio/wav",
        ".wave": "audio/wav",
        ".aiff": "audio/aiff",
        ".aif": "audio/aiff",
        ".flac": "audio/flac",
        ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4",
    }.get(Path(filename).suffix.lower(), "application/octet-stream")


def _register_source_artifact(
    conn,
    prepared,
    *,
    review_id: str,
    safe_name: str,
    review_title: str,
    version_label: str,
    project_id: str,
    context: ReviewWorkflowContext,
) -> dict | None:
    registry = context.artifact_registry
    if registry is None or prepared is None:
        return None
    return registry.register(
        conn,
        prepared,
        kind="audio.source.mix_review",
        media_type=_media_type(safe_name),
        producer="mix-review",
        producer_version="1.0.0",
        project_id=project_id,
        external_key=f"mix-review-source:{review_id}",
        source_uri=f"mix-review://{review_id}/source",
        metadata={
            "original_name": safe_name,
            "title": review_title,
            "version_label": version_label,
        },
    )


def _register_report_artifact(
    conn,
    prepared,
    *,
    review_id: str,
    report_name: str,
    review_title: str,
    mix_goal: str,
    project_id: str,
    source_artifact_id: str,
    context: ReviewWorkflowContext,
) -> dict | None:
    registry = context.artifact_registry
    if registry is None or prepared is None:
        return None
    return registry.register(
        conn,
        prepared,
        kind="audio.analysis.mix_review",
        media_type="application/json",
        producer="mix-review",
        producer_version="1.0.0",
        project_id=project_id,
        external_key=f"mix-review-report:{review_id}",
        source_uri=f"mix-review://{review_id}/report",
        parent_ids=(source_artifact_id,) if source_artifact_id else (),
        metadata={
            "report_name": report_name,
            "title": review_title,
            "mix_goal": mix_goal,
        },
    )


def _public_artifacts(
    source: dict | None,
    report: dict | None,
    *,
    context: ReviewWorkflowContext,
) -> dict:
    registry = context.artifact_registry
    if registry is None:
        return {}
    return {
        key: registry.public(item)
        for key, item in (("source", source), ("report", report))
        if item is not None
    }


def _emit_review_event(
    conn,
    *,
    review_id: str,
    status: str,
    project_id: str,
    context: ReviewWorkflowContext,
    source_artifact_id: str = "",
    report_artifact_id: str = "",
    correlation_id: str = "",
) -> None:
    registry = context.artifact_registry
    if registry is None:
        return
    registry.emit(
        conn,
        event_type=f"mix_review.{status}",
        aggregate_type="mix_review",
        aggregate_id=review_id,
        project_id=project_id,
        correlation_id=correlation_id or f"mix-review:{review_id}",
        actor_id="mix-review",
        payload={
            "status": status,
            "source_artifact_id": source_artifact_id,
            "report_artifact_id": report_artifact_id,
        },
    )


def mix_review_status(review_id: str, *, init_reviews_table: Callable, connect: Callable, read_report: Callable) -> dict:
    review_id = str(review_id or "").strip()
    if not review_id:
        return {"ok": False, "error": "Missing review ID."}
    init_reviews_table()
    with connect() as conn:
        row = conn.execute(
            "SELECT id, title, status, error, report_name FROM mix_reviews WHERE id = ? LIMIT 1",
            (review_id,),
        ).fetchone()
    if not row:
        return {"ok": False, "error": "Review not found."}
    item = dict(row)
    status = item.get("status") or "completed"
    err = item.get("error")

    res = {
        "ok": True,
        "id": item["id"],
        "title": item["title"],
        "status": status,
        "error": err
    }
    if status == "completed":
        report = read_report(str(item.get("report_name", "")))
        if report:
            res["review"] = {**item, **report}
    return res


def apply_version_and_reference_context(
    report: dict,
    *,
    review_id: str,
    review_title: str,
    version_label: str,
    reference_report: dict | None,
    reference_safe_name: str,
    saved_reference: dict | None,
    context: ReviewWorkflowContext,
) -> dict:
    report["title"] = review_title
    report["version_label"] = version_label.strip()[:80]

    previous = context.latest_review_for_title(review_title)
    if previous:
        version_comparison = context.compare_metrics(report["metrics"], previous["metrics"])
        report["previous_version"] = {
            "id": previous.get("id"),
            "title": previous.get("title"),
            "created_at": previous.get("created_at"),
            "version_label": previous.get("version_label", ""),
        }
        report["version_comparison"] = version_comparison
        report["version_advice"] = context.version_advice(version_comparison)
        report["revision_impact"] = context.revision_impact_summary(report, previous)
        report["revision_coaching"] = context.revision_coaching(report, previous)

    reference_metrics = None
    reference_payload = None
    if reference_report:
        reference_metrics = reference_report["metrics"]
        reference_payload = {
            "filename": reference_safe_name,
            "metrics": reference_metrics,
            "stored_name": f"{review_id}_reference_{reference_safe_name}",
        }
    elif saved_reference:
        reference_metrics = saved_reference.get("metrics") or {}
        reference_payload = {
            "id": saved_reference.get("id"),
            "name": saved_reference.get("name"),
            "style": saved_reference.get("style", ""),
            "filename": saved_reference.get("original_name", ""),
            "metrics": reference_metrics,
            "saved": True,
            "stored_name": saved_reference.get("stored_name", ""),
        }
    else:
        mix_goal_dict = report["metrics"].get("mix_goal") or {}
        goal_key = str(mix_goal_dict.get("key") or "").strip().lower()
        from audio_analysis.analysis_core.genre_profiles import (
            GENRE_SEED_PROFILES,
            build_reference_envelope,
            map_40_to_7_bands,
        )
        if goal_key in GENRE_SEED_PROFILES:
            seed = GENRE_SEED_PROFILES[goal_key]
            bands_7 = map_40_to_7_bands(seed["profile"])
            envelope = context.reference_envelope_for_genre(goal_key)
            if envelope is None:
                envelope = build_reference_envelope([seed["profile"]])
            reference_metrics = {
                "bands": bands_7,
                "perceptual_bands": bands_7,
                "log_bands_40": seed["profile"],
                "crest_factor_db": seed["crest_factor_db"],
                "integrated_lufs": seed["lufs_max"],
                "stereo_correlation": seed["stereo_correlation"],
                "loudness_range_lu": seed.get("lra_min", 5.0),
                "genre_envelope": envelope,
            }
            reference_payload = {
                "id": f"genre_{goal_key}",
                "name": seed["name"],
                "style": "Curated Genre Profile",
                "filename": f"{seed['name']} Reference",
                "metrics": reference_metrics,
                "saved": True,
                "virtual": True,
            }

    if reference_metrics and reference_payload:
        comparison = context.compare_metrics(report["metrics"], reference_metrics)
        report["reference"] = reference_payload
        report["reference_id"] = reference_payload.get("id")
        report["comparison"] = comparison
        report["comparison_advice"] = context.comparison_advice(comparison)
        report["reference_coaching"] = context.reference_coaching(comparison, report["metrics"], reference_payload)
        report["summary"] = context.report_summary(report["metrics"], report.get("flags", []), comparison)
        report["action_plan"] = context.priority_actions(report["metrics"], report.get("flags", []), comparison)
        report["revision_lesson"] = context.revision_lesson(report)
        context.refresh_report_interpretation(report)

    report["revision_agent"] = context.revision_agent_plan(report)
    report["mix_critique"] = context.generate_mix_critique(report)
    report["prose_summary"] = context.generate_prose_summary(report)
    # Stage 10 — additive fields, distinct from the legacy "mix_critique"
    # above: an AI-augmented critique that specifically covers the Stage 10
    # metrics (section-LRA spread, stereo asymmetry, transient preservation,
    # stem masking), plus deterministic style classification. Both read only
    # from `report`/`report["metrics"]`, which are always populated by this
    # point, so neither can fail for lack of input; best-effort guarded
    # anyway since this is late in the pipeline and must never block a
    # review from completing.
    if context.generate_mix_review_critique is not None:
        try:
            report["mix_review_critique"] = context.generate_mix_review_critique(report)
        except Exception:
            logger.warning("Stage 10 mix review critique failed; omitted from report.", exc_info=True)
    if context.classify_mix_style is not None:
        try:
            report["mix_style"] = context.classify_mix_style(report)
        except Exception:
            logger.warning("Stage 10 mix style classification failed; omitted from report.", exc_info=True)
    context.refresh_closed_loop_payloads(report)
    return report


def _attach_stem_analysis(report: dict, stems: list[dict] | None) -> None:
    """Stage 10 — best-effort stem-solo / frequency-masking analysis.

    Only runs when the caller supplies decoded/raw stem audio explicitly
    (``stems``, as ``{"name": str, "file_bytes": bytes}`` dicts); the
    standard single-file upload flow has no stems, so this is a no-op for
    the overwhelming majority of reviews. Never raises -- failures are
    logged and simply omitted from the report, matching the "best-effort,
    never blocks delivery" pattern used for the Stage 9 KENN explanations
    wiring in report_rendering.py.
    """
    if not stems or len(stems) < 2:
        return
    try:
        from audio_analysis.analysis_core.analysis_core import stem_frequency_masking
        from audio_analysis.mixdown.stem_solo import stem_spectrum_comparison
        from audio_analysis.utils.audio_io_api import read_wav_mono as _read_wav_mono

        report["stem_masking"] = stem_frequency_masking(stems, read_wav_mono=_read_wav_mono)
        report["stem_solo"] = stem_spectrum_comparison(stems, read_wav_mono=_read_wav_mono)
    except Exception:
        logger.warning("Stem-solo/masking analysis failed; omitted from report.", exc_info=True)


def _attach_transient_preservation(
    report: dict, file_bytes: bytes, safe_name: str, pre_master_bytes: bytes | None
) -> None:
    """Stage 10 — best-effort transient-preservation comparison.

    Only runs when the caller supplies a ``pre_master_bytes`` render (e.g. a
    pre-limiter bounce of the same material) alongside the main upload --
    transient preservation is inherently a two-render comparison and has no
    meaningful single-file value, so it's opt-in rather than attempted
    against unrelated audio (e.g. a reference track). Never raises.
    """
    if not pre_master_bytes:
        return
    try:
        from audio_analysis.analysis_core.transient_groove import transient_preservation
        from audio_analysis.utils.audio_io_api import decode_audio_bytes, read_wav_mono

        pre_decoded = decode_audio_bytes(pre_master_bytes, f"pre_{safe_name}")
        post_decoded = decode_audio_bytes(file_bytes, safe_name)
        pre_data = read_wav_mono(pre_decoded["wav_bytes"])
        post_data = read_wav_mono(post_decoded["wav_bytes"])
        sample_rate = int(post_data.get("analysis_sample_rate") or post_data["sample_rate"])
        report["transient_preservation"] = transient_preservation(
            pre_data["samples"], post_data["samples"], sample_rate
        )
    except Exception:
        logger.warning("Transient-preservation comparison failed; omitted from report.", exc_info=True)


def _run_analysis(
    review_id: str,
    file_bytes: bytes,
    safe_name: str,
    mix_goal: str,
    reference_bytes: bytes | None,
    reference_safe_name: str,
    saved_reference: dict | None,
    review_title: str,
    version_label: str,
    report_name: str,
    *,
    context: ReviewWorkflowContext,
    phon_level: float = 60.0,
    stems: list[dict] | None = None,
    pre_master_bytes: bytes | None = None,
) -> dict:
    """Execute the actual analysis work. Runs inside a timeout wrapper."""
    report = context.analyze_wav(file_bytes, safe_name, mix_goal=mix_goal, phon_level=phon_level)
    reference_report = context.analyze_wav(reference_bytes, reference_safe_name, phon_level=phon_level) if reference_bytes else None

    _attach_stem_analysis(report, stems)
    _attach_transient_preservation(report, file_bytes, safe_name, pre_master_bytes)

    apply_version_and_reference_context(
        report,
        review_id=review_id,
        review_title=review_title,
        version_label=version_label,
        reference_report=reference_report,
        reference_safe_name=reference_safe_name,
        saved_reference=saved_reference,
        context=context,
    )

    report["id"] = review_id
    report["created_at"] = context.now()

    (context.report_root / report_name).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    # Populate summary cache and feature vector cache; then find similar reviews
    try:
        from audio_analysis.mix_review.review_store import _cache_report_summary, cache_feature_vector
        _cache_report_summary(report, context.connect)
        cache_feature_vector(report, connect_func=context.connect)
        try:
            from audio_analysis.mix_features import extract_feature_vector
            fv = extract_feature_vector(report.get("metrics") or {})
            report["similar_reviews"] = context.find_similar_reviews(
                fv, exclude_review_id=review_id
            )
        except Exception:
            report.setdefault("similar_reviews", [])
    except Exception:
        pass

    return report


def _cleanup_upload_files(
    stored_name: str,
    review_id: str,
    reference_safe_name: str,
    *,
    upload_root: Path,
) -> None:
    """Remove uploaded files after a failed analysis to prevent disk leaks."""
    for name in (stored_name, f"{review_id}_reference_{reference_safe_name}"):
        if not name:
            continue
        path = upload_root / name
        try:
            if path.exists():
                path.unlink()
        except OSError:
            pass


def _mark_failed(
    review_id: str,
    error_message: str,
    *,
    context: ReviewWorkflowContext,
    project_id: str = "",
    correlation_id: str = "",
) -> None:
    """Mark the review as failed in the DB with a timestamp."""
    failed_at = datetime.now(timezone.utc).isoformat()
    try:
        with context.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "UPDATE mix_reviews SET status = ?, error = ? WHERE id = ?",
                ("failed", f"[{failed_at}] {error_message}", review_id),
            )
            _emit_review_event(
                conn,
                review_id=review_id,
                status="failed",
                project_id=project_id,
                context=context,
                correlation_id=correlation_id,
            )
            conn.commit()
    except Exception:
        pass


def background_analyze(
    review_id: str,
    file_bytes: bytes,
    safe_name: str,
    mix_goal: str,
    reference_bytes: bytes | None,
    reference_safe_name: str,
    saved_reference: dict | None,
    review_title: str,
    version_label: str,
    stored_name: str,
    report_name: str,
    file_size: int,
    project_id: str,
    source_artifact_id: str,
    *,
    context: ReviewWorkflowContext,
    phon_level: float = 60.0,
    stems: list[dict] | None = None,
    pre_master_bytes: bytes | None = None,
    correlation_id: str = "",
) -> None:
    try:
        with context.connect() as conn:
            conn.execute(
                "UPDATE mix_reviews SET status = ? WHERE id = ?",
                ("processing", review_id),
            )
            conn.commit()

        # Run the analysis with a timeout to prevent hangs on corrupt files
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                _run_analysis,
                review_id, file_bytes, safe_name, mix_goal,
                reference_bytes, reference_safe_name, saved_reference,
                review_title, version_label, report_name,
                context=context,
                phon_level=phon_level,
                stems=stems,
                pre_master_bytes=pre_master_bytes,
            )
            try:
                future.result(timeout=ANALYSIS_TIMEOUT_SECONDS)
            except FuturesTimeoutError:
                raise TimeoutError(
                    f"Analysis timed out after {ANALYSIS_TIMEOUT_SECONDS}s. "
                    f"The file may be corrupt or unusually long."
                )

        report_path = context.report_root / report_name
        prepared_report = (
            context.artifact_registry.prepare(report_path)
            if context.artifact_registry is not None
            else None
        )
        try:
            with context.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                report_artifact = _register_report_artifact(
                    conn,
                    prepared_report,
                    review_id=review_id,
                    report_name=report_name,
                    review_title=review_title,
                    mix_goal=mix_goal,
                    project_id=project_id,
                    source_artifact_id=source_artifact_id,
                    context=context,
                )
                conn.execute(
                    "UPDATE mix_reviews SET status = ?, error = ?, report_name = ? WHERE id = ?",
                    ("completed", None, report_name, review_id),
                )
                _emit_review_event(
                    conn,
                    review_id=review_id,
                    status="completed",
                    project_id=project_id,
                    context=context,
                    source_artifact_id=source_artifact_id,
                    report_artifact_id=str((report_artifact or {}).get("id", "")),
                    correlation_id=correlation_id,
                )
                conn.commit()
        except Exception:
            if prepared_report is not None and context.artifact_registry is not None:
                context.artifact_registry.discard(prepared_report)
            raise

        if _AUTO_DELETE_UPLOADS:
            try:
                from audio_analysis.utils.file_cleanup import cleanup_after_analysis

                cleanup_after_analysis(
                    review_id,
                    upload_root=context.upload_root,
                    connect_func=context.connect,
                    keep_reference=False,
                )
            except Exception:
                logger.warning("Failed to clean up uploads for %s", review_id, exc_info=True)

    except Exception as exc:
        logger.exception("background_analyze failed for review %s: %s", review_id, exc)
        _mark_failed(review_id, str(exc), context=context, project_id=project_id, correlation_id=correlation_id)
        _cleanup_upload_files(stored_name, review_id, reference_safe_name, upload_root=context.upload_root)


def save_review(
    *,
    file_bytes: bytes,
    filename: str,
    title: str = "",
    version_label: str = "",
    mix_goal: str,
    reference_bytes: bytes | None = None,
    reference_filename: str = "",
    reference_id: str = "",
    project_id: str = "",
    background: bool = False,
    context: ReviewWorkflowContext,
    phon_level: float = 60.0,
    stems: list[dict] | None = None,
    pre_master_bytes: bytes | None = None,
    correlation_id: str = "",
) -> dict:
    validation = context.validate_wav_upload(file_bytes, filename, label="Mix")
    if not validation.get("ok"):
        return validation
    safe_name = str(validation["safe_name"])
    review_title = title.strip()[:160] or Path(safe_name).stem.replace("-", " ").replace("_", " ").title()
    reference_safe_name = ""

    # D1.7 (docs/KENN_FUTURE_PLAN.md Phase 1): project continuity for the
    # reference track. If this review's project already has a remembered
    # reference and the caller gave neither an explicit reference_id nor
    # raw reference_bytes, auto-apply the project's reference -- picking
    # one once per project means every later review/revision reuses it
    # without re-selecting. If the caller DID explicitly pick a saved
    # reference for a project that has none remembered yet, remember it
    # for next time (never overwrites an existing choice).
    explicit_reference_id = bool(reference_id)
    song_project = context.get_song_project(project_id) if project_id and context.get_song_project else None
    if not explicit_reference_id and not reference_bytes and song_project and song_project.get("reference_track_id"):
        reference_id = str(song_project["reference_track_id"])

    saved_reference = context.reference_by_id(reference_id) if reference_id and not reference_bytes else None
    if reference_id and not reference_bytes and not saved_reference:
        return {"ok": False, "error": "Saved reference not found."}

    if (
        explicit_reference_id
        and saved_reference
        and song_project is not None
        and not song_project.get("reference_track_id")
        and context.set_project_reference_track is not None
    ):
        context.set_project_reference_track(project_id, reference_id)
    if reference_bytes:
        ref_validation = context.validate_wav_upload(reference_bytes, reference_filename or "reference.wav", label="Reference")
        if not ref_validation.get("ok"):
            return ref_validation
        reference_safe_name = str(ref_validation["safe_name"])
        if len(file_bytes) + len(reference_bytes) > context.max_upload_bytes * 2:
            return {"ok": False, "error": f"Combined upload exceeds {(context.max_upload_bytes * 2) // (1024 * 1024)} MB limit."}

    context.init_reviews_table()
    review_id = str(uuid4())[:8]
    stored_name = f"{review_id}_{safe_name}"
    report_name = f"{review_id}.json"

    try:
        (context.upload_root / stored_name).write_bytes(file_bytes)
        if reference_bytes and reference_safe_name:
            (context.upload_root / f"{review_id}_reference_{reference_safe_name}").write_bytes(reference_bytes)
    except OSError as exc:
        return {"ok": False, "error": f"Failed to save upload files: {exc}"}

    prepared_source = None
    if context.artifact_registry is not None:
        try:
            prepared_source = context.artifact_registry.prepare(context.upload_root / stored_name)
        except Exception as exc:
            _cleanup_upload_files(
                stored_name,
                review_id,
                reference_safe_name,
                upload_root=context.upload_root,
            )
            return {"ok": False, "error": f"Failed to register mix source: {exc}"}

    created_time = context.now()
    if background:
        try:
            with context.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    """
                    INSERT INTO mix_reviews (id, title, original_name, stored_name, report_name, size_bytes, created_at, status, project_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [review_id, review_title, safe_name, stored_name, report_name, len(file_bytes), created_time, "pending", project_id],
                )
                source_artifact = _register_source_artifact(
                    conn,
                    prepared_source,
                    review_id=review_id,
                    safe_name=safe_name,
                    review_title=review_title,
                    version_label=version_label,
                    project_id=project_id,
                    context=context,
                )
                _emit_review_event(
                    conn,
                    review_id=review_id,
                    status="created",
                    project_id=project_id,
                    context=context,
                    source_artifact_id=str((source_artifact or {}).get("id", "")),
                    correlation_id=correlation_id,
                )
                conn.commit()
        except Exception as exc:
            if prepared_source is not None and context.artifact_registry is not None:
                context.artifact_registry.discard(prepared_source)
            _cleanup_upload_files(
                stored_name,
                review_id,
                reference_safe_name,
                upload_root=context.upload_root,
            )
            return {"ok": False, "error": f"Failed to create mix review: {exc}"}

        thread = threading.Thread(
            target=background_analyze,
            args=(
                review_id,
                file_bytes,
                safe_name,
                mix_goal,
                reference_bytes,
                reference_safe_name,
                saved_reference,
                review_title,
                version_label,
                stored_name,
                report_name,
                len(file_bytes),
                project_id,
                str((source_artifact or {}).get("id", "")),
            ),
            kwargs={
                "context": context,
                "phon_level": phon_level,
                "stems": stems,
                "pre_master_bytes": pre_master_bytes,
                "correlation_id": correlation_id,
            },
            daemon=True,
        )
        thread.start()

        return {
            "ok": True,
            "id": review_id,
            "status": "pending",
            "review": {
                "id": review_id,
                "title": review_title,
                "status": "pending",
                "created_at": created_time,
                "artifacts": _public_artifacts(source_artifact, None, context=context),
            },
        }
    try:
        report = context.analyze_wav(file_bytes, safe_name, mix_goal=mix_goal, phon_level=phon_level)
        reference_report = context.analyze_wav(reference_bytes, reference_safe_name, phon_level=phon_level) if reference_bytes else None
    except (wave.Error, ValueError) as exc:
        if prepared_source is not None and context.artifact_registry is not None:
            context.artifact_registry.discard(prepared_source)
        _cleanup_upload_files(
            stored_name,
            review_id,
            reference_safe_name,
            upload_root=context.upload_root,
        )
        return {"ok": False, "error": str(exc)}

    _attach_stem_analysis(report, stems)
    _attach_transient_preservation(report, file_bytes, safe_name, pre_master_bytes)

    apply_version_and_reference_context(
        report,
        review_id=review_id,
        review_title=review_title,
        version_label=version_label,
        reference_report=reference_report,
        reference_safe_name=reference_safe_name,
        saved_reference=saved_reference,
        context=context,
    )

    report["id"] = review_id
    report["created_at"] = created_time
    report_path = context.report_root / report_name
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    # Populate summary cache and feature vector cache; then find similar reviews
    try:
        from audio_analysis.mix_review.review_store import _cache_report_summary, cache_feature_vector
        _cache_report_summary(report, context.connect)
        cache_feature_vector(report, connect_func=context.connect)
        try:
            from audio_analysis.mix_features import extract_feature_vector
            review_id_val = report.get("id") or ""
            fv = extract_feature_vector(report.get("metrics") or {})
            report["similar_reviews"] = context.find_similar_reviews(
                fv, exclude_review_id=review_id_val
            )
        except Exception:
            report.setdefault("similar_reviews", [])
    except Exception:
        pass

    prepared_report = None
    try:
        if context.artifact_registry is not None:
            prepared_report = context.artifact_registry.prepare(report_path)
        with context.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                INSERT INTO mix_reviews (id, title, original_name, stored_name, report_name, size_bytes, created_at, status, project_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [review_id, review_title, safe_name, stored_name, report_name, len(file_bytes), created_time, "completed", project_id],
            )
            source_artifact = _register_source_artifact(
                conn,
                prepared_source,
                review_id=review_id,
                safe_name=safe_name,
                review_title=review_title,
                version_label=version_label,
                project_id=project_id,
                context=context,
            )
            report_artifact = _register_report_artifact(
                conn,
                prepared_report,
                review_id=review_id,
                report_name=report_name,
                review_title=review_title,
                mix_goal=mix_goal,
                project_id=project_id,
                source_artifact_id=str((source_artifact or {}).get("id", "")),
                context=context,
            )
            _emit_review_event(
                conn,
                review_id=review_id,
                status="created",
                project_id=project_id,
                context=context,
                source_artifact_id=str((source_artifact or {}).get("id", "")),
                correlation_id=correlation_id,
            )
            _emit_review_event(
                conn,
                review_id=review_id,
                status="completed",
                project_id=project_id,
                context=context,
                source_artifact_id=str((source_artifact or {}).get("id", "")),
                report_artifact_id=str((report_artifact or {}).get("id", "")),
                correlation_id=correlation_id,
            )
            conn.commit()
    except Exception as exc:
        for prepared in (prepared_source, prepared_report):
            if prepared is not None and context.artifact_registry is not None:
                context.artifact_registry.discard(prepared)
        report_path.unlink(missing_ok=True)
        _cleanup_upload_files(
            stored_name,
            review_id,
            reference_safe_name,
            upload_root=context.upload_root,
        )
        return {"ok": False, "error": f"Failed to persist mix review artifacts: {exc}"}

    if _AUTO_DELETE_UPLOADS:
        try:
            from audio_analysis.utils.file_cleanup import cleanup_after_analysis

            cleanup_after_analysis(
                review_id,
                upload_root=context.upload_root,
                connect_func=context.connect,
                keep_reference=False,
            )
        except Exception:
            logger.warning("Failed to clean up uploads for %s", review_id, exc_info=True)

    response_report = dict(report)
    response_report["artifacts"] = _public_artifacts(
        source_artifact, report_artifact, context=context
    )
    return {"ok": True, "review": response_report}


def handle_multipart_review(
    content_type: str,
    body: bytes,
    *,
    parse_multipart_form: Callable,
    save_review: Callable,
    correlation_id: str = "",
    project_id_override: str = "",
) -> dict:
    fields = parse_multipart_form(content_type, body)
    file_bytes = fields.get("file")
    if not isinstance(file_bytes, (bytes, bytearray)):
        return {"ok": False, "error": "Missing file field."}
    filename = str(fields.get("file__filename", "mix.wav"))
    reference_bytes = fields.get("reference")
    reference_filename = str(fields.get("reference__filename", "reference.wav"))
    reference_id = str(fields.get("reference_id", "")).strip()
    phon_level = 60.0
    try:
        if "phon_level" in fields:
            phon_level = float(fields["phon_level"])
    except (TypeError, ValueError):
        pass

    return save_review(
        file_bytes=bytes(file_bytes),
        filename=filename,
        title=str(fields.get("title", "")),
        version_label=str(fields.get("version", "")),
        mix_goal=str(fields.get("mix_goal", "")),
        reference_bytes=bytes(reference_bytes) if isinstance(reference_bytes, (bytes, bytearray)) else None,
        reference_filename=reference_filename,
        reference_id=reference_id,
        project_id=project_id_override or str(fields.get("project_id", "")).strip(),
        background=True,
        phon_level=phon_level,
        correlation_id=correlation_id,
    )


def handle_multipart_music_analysis(
    content_type: str,
    body: bytes,
    *,
    parse_multipart_form: Callable,
    default_mix_goal: str,
    validate_wav_upload: Callable,
    analyze_wav: Callable,
    music_analysis_from_report: Callable,
) -> dict:
    fields = parse_multipart_form(content_type, body)
    file_bytes = fields.get("file")
    if not isinstance(file_bytes, (bytes, bytearray)):
        return {"ok": False, "error": "Missing file field."}
    filename = str(fields.get("file__filename", "music.wav"))
    mix_goal = str(fields.get("mix_goal", default_mix_goal))
    validation = validate_wav_upload(bytes(file_bytes), filename, label="Music file")
    if not validation.get("ok"):
        return validation
    safe_name = str(validation["safe_name"])
    try:
        report = analyze_wav(bytes(file_bytes), safe_name, mix_goal=mix_goal)
    except (wave.Error, ValueError) as exc:
        return {"ok": False, "error": str(exc)}
    return {
        "ok": True,
        "analysis": music_analysis_from_report(report),
        "report": report,
    }
