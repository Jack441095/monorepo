"""Background worker for processing automated mixdown jobs in Website context."""

from __future__ import annotations

import copy
import json
import multiprocessing
import os
import platform
import time
import threading
import tempfile
import traceback
import zipfile
from pathlib import Path
from datetime import datetime

import numpy as np

# Fix python path imports
import sys
parent_dir = Path(__file__).resolve().parent.parent
repo_root = parent_dir.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))
if str(repo_root / "studio" / "audio_analysis") not in sys.path:
    sys.path.insert(0, str(repo_root / "studio" / "audio_analysis"))

from app.db import connect, now
from app import delivery_service, delivery_worker, email_notify, retention
import artifact_store
import event_store
import musical_role_feedback
import stem_uploads
from app.archive_safety import extract_zip_safely
from app.path_safety import safe_child, validate_identifier
from audio_analysis.utils.audio_io import read_wav_mono
from audio_analysis.analysis_core.dsp_metrics import spectral_bands
from audio_analysis.mixdown.stem_classifier import classify_stems
from audio_analysis.mixdown.stem_prep import prepare_stems
from audio_analysis.mixdown.musical_roles import apply_role_corrections, infer_musical_roles
from audio_analysis.mixdown.arrangement import infer_arrangement
from audio_analysis.mixdown.relationships import infer_relationships
from audio_analysis.mixdown.mono_compatibility import analyze_mono_compatibility
from audio_analysis.mixdown.automation_preview import build_automation_preview
from audio_analysis.integration.session_mix_graph import build_session_mix_graph
from audio_analysis.mixdown.arrangement import apply_arrangement_corrections
from audio_analysis.analysis_core.phase_polarity_detection import correct_stem_polarity
from audio_analysis.analysis_core.tempo_key_consistency import analyze_stems_for_tempo_consistency
from audio_analysis.analysis_core.pitch_correction_detection import detect_pitch_correction_signature
from audio_analysis.analysis_core.limiter_fingerprint_detection import detect_limiter_fingerprint
from audio_analysis.analysis_core.sidechain_detection import analyze_stems_for_dynamics
from audio_analysis.mixdown.stem_analysis import analyze_stems_masking
from audio_analysis.mixdown.mix_decision_engine import generate_mix_plan
from audio_analysis.mixdown.mix_renderer import (
    mix_and_render_stems, refine_mix_if_needed, render_unprocessed_stem_sum,
)
from audio_analysis.mixdown.mix_validator import validate_and_correct_mix
from audio_analysis.mixdown.mix_delivery import package_mixdown_delivery
from audio_analysis.integration.kenn_advisor import evaluate_advisor_shadow, mix_plan_revision
from audio_analysis.integration.advisor_preview import render_advisor_previews
from audio_analysis.integration.project_features import (
    estimate_project_tempo,
    extract_compressor_threshold_target,
    extract_project_features,
    record_project_training_row,
)

# Root directories
BUSINESS_ROOT = Path(__file__).resolve().parent.parent
UPLOAD_ROOT = BUSINESS_ROOT / "data" / "stem_uploads"
MIX_OUTPUT_ROOT = BUSINESS_ROOT / "data" / "mix_outputs"
REFERENCE_TRACKS_ROOT = repo_root / "reference_tracks"

# Maps the decision-engine genre (job.genre / the UI's #genreSelect value) to
# a curated reference_tracks/<folder>/ genre library, so a user gets spectral
# matching without uploading their own reference. Only genres with a real
# curated folder are listed here (see reference_tracks/README.md for the
# curation rules) -- everything else still requires an uploaded reference.
_GENRE_REFERENCE_FOLDER = {
    "pop": "pop",
    "hip_hop": "hiphop_rnb",
    "edm": "electronic",
    "acoustic": "acoustic",
    "cinematic": "cinematic",
}


def default_reference_dir(genre: str) -> Path | None:
    """The curated genre-folder reference for ``genre``, if one exists and has
    at least one audio file in it -- else None (caller falls back to no match)."""
    folder = _GENRE_REFERENCE_FOLDER.get(genre)
    if not folder:
        return None
    d = REFERENCE_TRACKS_ROOT / folder
    if not d.is_dir():
        return None
    from audio_analysis.mixdown.spectral_match import AUDIO_SUFFIXES
    if not any(f.suffix.lower() in AUDIO_SUFFIXES for f in d.iterdir() if f.is_file()):
        return None
    return d

# Thread control
_worker_thread = None
_stop_event = threading.Event()
AUTOMIX_JOB_TIMEOUT_SECONDS = max(1.0, float(os.getenv("AUTOMIX_JOB_TIMEOUT_SECONDS", "600")))
# Reference matching adds a complete probe render before the validated render.
# Keep that optional cost bounded for long projects unless the caller makes an
# explicit informed opt-in in the job preferences.
REFERENCE_MATCH_MAX_DURATION_SECONDS = max(
    1.0, float(os.getenv("AUTOMIX_REFERENCE_MATCH_MAX_DURATION_SECONDS", "120"))
)

# Resource limits
MAX_STEMS_COUNT = stem_uploads.MAX_AUTOMIX_STEMS
MAX_SINGLE_FILE_BYTES = stem_uploads.MAX_AUTOMIX_SOURCE_BYTES
MAX_AUDIO_DURATION_SECONDS = stem_uploads.MAX_AUTOMIX_DURATION_SECONDS
# Per-stem before/after runs a full Mix Review analysis (before + after) per
# stem -- real but not cheap. Capped well under MAX_STEMS_COUNT so a large
# project still gets its overall before/after promptly; see the "stems"
# best-effort block below.
MAX_PER_STEM_COMPARISON = 16


def _resource_snapshot(started_at: float) -> dict:
    """Return a small, portable-enough offline-worker resource receipt.

    This runs only inside AutoMix's isolated child process.  ``ru_maxrss`` is
    bytes on macOS and KiB on Linux, so normalise it before exposing the value
    in a job artifact.  Failure to read process metrics must never affect an
    audio delivery.
    """
    snapshot = {"elapsed_ms": round((time.perf_counter() - started_at) * 1000.0, 1)}
    try:
        import resource

        max_rss = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        snapshot["peak_rss_bytes"] = max_rss if platform.system() == "Darwin" else max_rss * 1024
    except Exception:
        snapshot["peak_rss_bytes"] = None
    return snapshot


def _take_probe_wav(render_result: dict) -> bytes:
    """Keep only a probe's encoded WAV and release its large render buffers.

    Reference matching needs the rendered WAV, but not the decoded master
    arrays, per-stem renders, plan copy, or diagnostic arrays returned by the
    renderer.  Holding two of those dictionaries while making the width probe
    was the source of a large avoidable RSS spike on real projects.
    """
    wav_bytes = render_result.get("mixdown_wav_bytes")
    if not isinstance(wav_bytes, bytes):
        raise RuntimeError("Reference probe did not produce WAV bytes.")
    render_result.clear()
    return wav_bytes


def apply_reference_width_policy(
    plan,
    *,
    match_bands: list[dict],
    probe_wav_bytes: bytes,
    reference_path: Path,
    compute_width_factor,
) -> dict:
    """Apply an optional width nudge only when it needs no extra render.

    Once tonal bands have changed the master bus, a pre-EQ width measurement is
    stale and a post-EQ one needs another complete render.  Treat that as a
    resource-policy decision, not an invisible quality compromise.
    """
    if match_bands:
        reason = (
            "Reference width nudge skipped: tonal reference matching already requires "
            "a validated second render, and a third whole-project probe exceeds the "
            "safe offline render budget."
        )
        plan.decisions_log.append(reason)
        return {"applied": False, "reason": "third_render_budget"}
    width_factor = compute_width_factor(probe_wav_bytes, reference_path)
    if width_factor is None:
        return {"applied": False, "reason": "no_safe_width_delta"}
    plan.bus.reference_width_factor = width_factor
    return {"applied": True, "factor": width_factor}


def reference_match_budget_decision(prepared_stems: list[dict], style_prefs: dict) -> dict:
    """Decide whether the optional probe render fits the configured budget."""
    durations = []
    for stem in prepared_stems:
        samples = stem.get("samples")
        sample_rate = stem.get("sample_rate")
        if samples is None or isinstance(sample_rate, bool) or not isinstance(sample_rate, (int, float)) or sample_rate <= 0:
            continue
        durations.append(len(samples) / float(sample_rate))
    duration = max(durations, default=0.0)
    explicit_opt_in = bool(style_prefs.get("allow_long_reference_match", False))
    allowed = explicit_opt_in or duration <= REFERENCE_MATCH_MAX_DURATION_SECONDS
    return {
        "allowed": allowed,
        "duration_seconds": round(duration, 3),
        "limit_seconds": REFERENCE_MATCH_MAX_DURATION_SECONDS,
        "explicit_opt_in": explicit_opt_in,
        "reason": "within_budget" if allowed else "duration_budget_exceeded",
    }

# Valid state machine transitions
VALID_TRANSITIONS = {
    "queued": {"claimed"},
    "claimed": {"preparing", "classifying", "failed", "cancelled"},
    "preparing": {"classifying", "analysing", "failed", "cancelled"},
    "classifying": {"preparing", "analysing", "failed", "cancelled"},
    "analysing": {"deciding", "failed", "cancelled"},
    "deciding": {"processing", "failed", "cancelled"},
    "processing": {"packaging", "failed", "cancelled"},
    "packaging": {"complete", "failed", "cancelled"},
    "complete": set(),
    "failed": set(),
    "cancelled": set()
}


def start_automix_worker() -> None:
    """Start the background worker thread (legacy method)."""
    global _worker_thread
    if _worker_thread is not None and _worker_thread.is_alive():
        return

    _cleanup_expired_outputs()
    _stop_event.clear()
    _worker_thread = threading.Thread(target=_worker_loop, name="AutomixWorker", daemon=True)
    _worker_thread.start()
    print("[automix_worker] Background worker thread started successfully.", flush=True)


def stop_automix_worker() -> None:
    """Stop the background worker thread."""
    _stop_event.set()
    if _worker_thread:
        _worker_thread.join(timeout=5.0)
        print("[automix_worker] Background worker thread stopped.", flush=True)


def start_worker(worker_id: str | None = None) -> None:
    """Start the standalone worker polling loop."""
    if not worker_id:
        worker_id = f"worker-{os.getpid()}"
    print(f"[automix_worker] Standalone worker starting (ID: {worker_id})...", flush=True)

    # Clean outputs directory
    MIX_OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    _cleanup_expired_outputs()

    # 1. Recover abandoned/timed-out jobs
    recover_abandoned_jobs(worker_id)
    delivery_worker.recover_abandoned_deliveries()

    # 2. Main execution loop
    while not _stop_event.is_set():
        try:
            delivery = delivery_worker.process_one(worker_id)
            job = _claim_next_job(worker_id)
            if job:
                _run_job_with_timeout(job)
            elif not delivery:
                time.sleep(2.0)
        except KeyboardInterrupt:
            print("[automix_worker] Worker interrupted. Stopping...", flush=True)
            break
        except Exception as exc:
            print(f"[automix_worker] Error in worker loop: {exc}", flush=True)
            time.sleep(5.0)


def _cleanup_expired_outputs() -> None:
    """Apply automix retention on worker startup without blocking job recovery."""
    try:
        removed = retention.cleanup_expired_mix_outputs(run=True)
        if removed:
            print(f"[automix_worker] Removed {removed} expired mix output file(s).", flush=True)
    except Exception as exc:
        print(f"[automix_worker] Retention cleanup failed: {exc}", flush=True)


def recover_abandoned_jobs(worker_id: str) -> None:
    """Reset abandoned or timed out jobs back to queued status."""
    timestamp = now()
    with connect() as conn:
        # Find jobs in claimed/active states whose lease has expired, or jobs belonging to this worker
        rows = conn.execute(
            """SELECT id, status, iteration_count FROM automix_jobs
               WHERE (status IN ('claimed', 'preparing', 'classifying', 'analysing', 'deciding', 'processing', 'packaging'))
               AND (lease_expiry_at < ? OR worker_id = ?)""",
            (timestamp, worker_id)
        ).fetchall()

        for row in rows:
            job_id = row["id"]
            current_status = row["status"]
            iters = row["iteration_count"] or 0

            if iters >= 3:
                print(f"[automix_worker] Failing job {job_id} due to retry limit exceeded", flush=True)
                conn.execute(
                    """UPDATE automix_jobs SET status = 'failed', error_message = 'Job failed: exceeded retry limit', updated_at = ?
                       WHERE id = ?""",
                    (timestamp, job_id)
                )
            else:
                print(f"[automix_worker] Recovering abandoned job {job_id} (previous status: {current_status})", flush=True)
                conn.execute(
                    """UPDATE automix_jobs SET status = 'queued', iteration_count = ?, worker_id = NULL, lease_expiry_at = NULL, updated_at = ?
                       WHERE id = ?""",
                    (iters + 1, timestamp, job_id)
                )
        conn.commit()


def _claim_next_job(worker_id: str) -> dict | None:
    """Atomically find and claim the next queued job for this worker."""
    with connect() as conn:
        row = conn.execute(
            "SELECT id FROM automix_jobs WHERE status = 'queued' ORDER BY created_at ASC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        job_id = row["id"]

        lease_seconds = AUTOMIX_JOB_TIMEOUT_SECONDS + 30
        lease_expiry = datetime.fromtimestamp(time.time() + lease_seconds).strftime("%Y-%m-%d %H:%M:%S")
        timestamp = now()

        cursor = conn.execute(
            """UPDATE automix_jobs
               SET status = 'claimed', worker_id = ?, claimed_at = ?, lease_expiry_at = ?, updated_at = ?
               WHERE id = ? AND status = 'queued'""",
            (worker_id, timestamp, lease_expiry, timestamp, job_id)
        )
        conn.commit()

        if cursor.rowcount > 0:
            job_row = conn.execute("SELECT * FROM automix_jobs WHERE id = ?", (job_id,)).fetchone()
            return dict(job_row)
    return None


def _worker_loop() -> None:
    """Legacy polling loop for background threads."""
    MIX_OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    worker_id = f"thread-worker-{threading.get_ident()}"
    recover_abandoned_jobs(worker_id)
    delivery_worker.recover_abandoned_deliveries()

    while not _stop_event.is_set():
        try:
            delivery = delivery_worker.process_one(worker_id)
            job = _claim_next_job(worker_id)
            if job:
                _run_job_with_timeout(job)
            elif not delivery:
                time.sleep(2.0)
        except Exception as exc:
            print(f"[automix_worker] Error in worker loop: {exc}", flush=True)
            traceback.print_exc()
            time.sleep(5.0)


def _get_next_queued_job() -> dict | None:
    """Query database for the oldest queued or interrupted job (legacy support)."""
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM automix_jobs WHERE status = 'queued' ORDER BY created_at ASC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None


def _update_job_status(
    job_id: str,
    status: str,
    error_message: str = "",
    result_path: str = "",
    iteration_count: int | None = None,
) -> None:
    """Update job status and append an immutable transition event following state machine."""
    timestamp = now()
    message = error_message or result_path
    lease_seconds = AUTOMIX_JOB_TIMEOUT_SECONDS + 30
    lease_expiry = datetime.fromtimestamp(time.time() + lease_seconds).strftime("%Y-%m-%d %H:%M:%S")

    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT status, project_id, worker_id, correlation_id FROM automix_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        if not row:
            raise KeyError(f"Automix job not found: {job_id}")
        from_status = str(row["status"])
        if status != from_status and status not in VALID_TRANSITIONS.get(from_status, set()):
            raise ValueError(f"Invalid Automix status transition: {from_status} -> {status}")

        if iteration_count is None:
            conn.execute(
                """UPDATE automix_jobs
                   SET status = ?, error_message = ?, result_path = ?, heartbeat_at = ?, lease_expiry_at = ?, updated_at = ?
                   WHERE id = ?""",
                (status, error_message, result_path, timestamp, lease_expiry, timestamp, job_id),
            )
        else:
            conn.execute(
                """UPDATE automix_jobs
                   SET status = ?, error_message = ?, result_path = ?, iteration_count = ?, heartbeat_at = ?, lease_expiry_at = ?, updated_at = ?
                   WHERE id = ?""",
                (status, error_message, result_path, iteration_count, timestamp, lease_expiry, timestamp, job_id),
            )
        conn.execute(
            """INSERT INTO automix_job_events (id, job_id, status, message, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (os.urandom(8).hex(), job_id, status, message, timestamp, timestamp),
        )
        event_store.append_in_transaction(
            conn,
            event_type=f"automix.job.{status}",
            aggregate_type="job",
            aggregate_id=job_id,
            project_id=str(row["project_id"] or ""),
            correlation_id=str(row["correlation_id"] or "") or f"automix-job:{job_id}",
            actor_id=str(row["worker_id"] or "automix"),
            payload={"from_status": from_status, "status": status},
        )
        conn.commit()


def _run_job_with_timeout(
    job: dict,
    *,
    timeout_seconds: float | None = None,
    process_factory=None,
) -> bool:
    """Run one job in a killable child process and fail it after the deadline."""
    timeout = AUTOMIX_JOB_TIMEOUT_SECONDS if timeout_seconds is None else max(0.01, timeout_seconds)
    factory = process_factory or multiprocessing.get_context("spawn").Process
    process = factory(target=_process_job, args=(job,), daemon=False)
    process.start()
    process.join(timeout)

    if process.is_alive():
        process.terminate()
        process.join(5.0)
        message = f"Automix job exceeded the {timeout:g}-second processing limit."
        _update_job_status(job["id"], "failed", error_message=message)
        return False

    if process.exitcode not in (0, None):
        _update_job_status(
            job["id"],
            "failed",
            error_message=f"Automix worker process exited with code {process.exitcode}.",
        )
        return False
    return True


def _get_project_uploader_email(project_id: str) -> str:
    """Retrieve uploader email from stem_uploads table for notification."""
    with connect() as conn:
        row = conn.execute(
            "SELECT uploader_email FROM stem_uploads WHERE project_id = ? ORDER BY created_at DESC LIMIT 1",
            (project_id,),
        ).fetchone()
        return row["uploader_email"] if row and row["uploader_email"] else ""


def _require_quality_gate(render_result: dict) -> None:
    """Stop delivery on objective render-safety failures, not taste diagnostics."""
    gate = render_result.get("quality_gate", {})
    if gate.get("passed", False):
        return
    failures = gate.get("hard_failures") or ["render safety was not established"]
    raise RuntimeError("Mix failed delivery safety gate: " + "; ".join(map(str, failures)))


def _register_delivery_artifacts(job_id: str, project_id: str, delivery: dict) -> dict:
    """Atomically register one AutoMix delivery graph and return public records."""
    source_ids = tuple(
        item["id"]
        for item in artifact_store.list_for_project(project_id, limit=500)
        if item.get("kind") == "audio.source.upload"
    )
    version = int(delivery["version"])
    entries = [
        ("mix", Path(delivery["wav_path"]), "audio.automix.mix", "audio/wav"),
        ("report", Path(delivery["report_path"]), "audio.automix.report", "text/html"),
        (
            "decisions_markdown",
            Path(delivery["decisions_md_path"]),
            "audio.automix.decisions",
            "text/markdown",
        ),
        (
            "manifest",
            Path(delivery["decisions_json_path"]),
            "audio.automix.manifest",
            "application/json",
        ),
    ]
    for output_format, raw_path in sorted((delivery.get("additional_format_paths") or {}).items()):
        media_type = {"flac": "audio/flac", "mp3": "audio/mpeg"}.get(
            output_format, "application/octet-stream"
        )
        entries.append(
            (
                f"mix_{output_format}",
                Path(raw_path),
                f"audio.automix.mix.{output_format}",
                media_type,
            )
        )
    entries.append(
        ("package", Path(delivery["zip_path"]), "audio.automix.package", "application/zip")
    )

    prepared = {}
    try:
        for key, path, _kind, _media in entries:
            prepared[key] = artifact_store.prepare_blob(path)
    except Exception:
        for blob in prepared.values():
            artifact_store.discard_unreferenced_blob(blob)
        for _key, path, _kind, _media in entries:
            path.unlink(missing_ok=True)
        raise
    registered: dict[str, dict] = {}
    try:
        with artifact_store.db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            for key, path, kind, media_type in entries:
                if key == "mix":
                    parents = source_ids
                elif key == "package":
                    parents = tuple(item["id"] for item in registered.values())
                else:
                    parents = (registered["mix"]["id"],)
                registered[key] = artifact_store.register_prepared(
                    conn,
                    prepared[key],
                    kind=kind,
                    media_type=media_type,
                    producer="automix",
                    producer_version="1.0.0",
                    project_id=project_id,
                    external_key=f"automix-job:{job_id}:{key}",
                    source_uri=f"automix://{project_id}/v{version}/{path.name}",
                    parent_ids=parents,
                    metadata={
                        "job_id": job_id,
                        "version": version,
                        "filename": path.name,
                    },
                )
            conn.commit()
    except Exception:
        for blob in prepared.values():
            artifact_store.discard_unreferenced_blob(blob)
        for _key, path, _kind, _media in entries:
            path.unlink(missing_ok=True)
        raise
    return {key: artifact_store.public_record(item) for key, item in registered.items()}


def _register_advisor_shadow_receipt(job_id: str, project_id: str, receipt: dict) -> dict:
    """Persist an immutable shadow receipt without placing it in the customer package."""
    source_ids = tuple(
        item["id"]
        for item in artifact_store.list_for_project(project_id, limit=500)
        if item.get("kind") == "audio.source.upload"
    )
    path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".json",
            prefix="automix-advisor-shadow-",
            delete=False,
        ) as handle:
            json.dump(receipt, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            path = Path(handle.name)
        item = artifact_store.register_file(
            path,
            kind="audio.automix.advisor-shadow",
            media_type="application/json",
            producer="automix-advisor-shadow",
            producer_version="1.0.0",
            project_id=project_id,
            external_key=f"automix-job:{job_id}:advisor-shadow",
            source_uri=f"automix://{project_id}/{job_id}/advisor-shadow.json",
            parent_ids=source_ids,
            metadata={
                "job_id": job_id,
                "status": receipt.get("status", "unknown"),
                "operation_count": int(receipt.get("operation_count", 0)),
                "source_plan_revision": receipt.get("source_plan_revision", ""),
            },
        )
        return artifact_store.public_record(item)
    finally:
        if path is not None:
            path.unlink(missing_ok=True)


def _register_advisor_preview_artifacts(
    job_id: str,
    project_id: str,
    shadow_artifact_id: str,
    preview: dict,
) -> dict:
    """Atomically register one baseline and its per-operation candidate WAVs."""
    wav_items = [("baseline", preview["baseline"]["mixdown_wav_bytes"])] + [
        (f"candidate-{item['operation_index']}", item["render"]["mixdown_wav_bytes"])
        for item in preview["candidates"]
    ]
    paths: dict[str, Path] = {}
    prepared = {}
    try:
        for key, wav_bytes in wav_items:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                suffix=".wav",
                prefix=f"automix-advisor-{key}-",
                delete=False,
            ) as handle:
                handle.write(wav_bytes)
                paths[key] = Path(handle.name)
            prepared[key] = artifact_store.prepare_blob(paths[key])
        with artifact_store.db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            baseline = artifact_store.register_prepared(
                conn,
                prepared["baseline"],
                kind="audio.automix.advisor-preview-baseline",
                media_type="audio/wav",
                producer="automix-advisor-preview",
                producer_version="1.0.0",
                project_id=project_id,
                external_key=f"automix-job:{job_id}:advisor-preview:baseline",
                source_uri=f"automix://{project_id}/{job_id}/advisor-preview/baseline.wav",
                parent_ids=(shadow_artifact_id,),
                metadata={
                    "job_id": job_id,
                    "source_plan_revision": preview["source_plan_revision"],
                    "role": "baseline",
                    "measured_lufs": preview["baseline_lufs"],
                },
            )
            candidates = []
            for item in preview["candidates"]:
                index = int(item["operation_index"])
                record = artifact_store.register_prepared(
                    conn,
                    prepared[f"candidate-{index}"],
                    kind="audio.automix.advisor-preview",
                    media_type="audio/wav",
                    producer="automix-advisor-preview",
                    producer_version="1.0.0",
                    project_id=project_id,
                    external_key=f"automix-job:{job_id}:advisor-preview:{index}",
                    source_uri=(
                        f"automix://{project_id}/{job_id}/advisor-preview/candidate-{index}.wav"
                    ),
                    parent_ids=(baseline["id"], shadow_artifact_id),
                    metadata={
                        "job_id": job_id,
                        "source_plan_revision": preview["source_plan_revision"],
                        "operation_index": index,
                        "role": "candidate",
                        "measured_lufs": item["measured_lufs"],
                        "loudness_bias_lu": item["loudness_bias_lu"],
                        "rms_delta": item["rms_delta"],
                        "shadow_artifact_id": shadow_artifact_id,
                    },
                )
                candidates.append(
                    {
                        "operation_index": index,
                        "preview_artifact_id": record["id"],
                        "measured_lufs": item["measured_lufs"],
                        "loudness_bias_lu": item["loudness_bias_lu"],
                        "rms_delta": item["rms_delta"],
                    }
                )
            conn.commit()
    except Exception:
        for blob in prepared.values():
            artifact_store.discard_unreferenced_blob(blob)
        raise
    finally:
        for path in paths.values():
            path.unlink(missing_ok=True)
    return {
        "schema": preview["schema"],
        "baseline_artifact_id": baseline["id"],
        "sample_rate": preview["sample_rate"],
        "duration_samples": preview["duration_samples"],
        "candidates": candidates,
        "rejected": preview["rejected"],
        "truncated_operations": preview["truncated_operations"],
    }


def build_per_stem_before_after(
    prepared_stems: list[dict],
    delivered_plan,
    source_stem_audio: dict,
    source_sample_rate: int,
    *,
    mix_goal: str = "premaster",
) -> dict:
    """Which stem did AutoMix actually change, not just the summed mix.

    Re-renders once with capture_stem_audio=True to get each stem's fully
    processed audio exactly as delivered, pairs it by name with the raw
    (unprocessed) stem audio captured before any correction ran, and runs
    the same before/after comparison used for the overall mix on each pair.
    Capped at MAX_PER_STEM_COMPARISON stems (a full Mix Review analysis per
    stem, before and after, is not cheap) -- a project over the cap still
    gets every other stem's comparison, just not all of them; the caller can
    see how many were skipped via "stems_total" vs len("stems").

    Pure with respect to its own DB/IO surface (no job-status writes, no
    disk writes) so it's directly unit-testable, unlike _process_job()
    itself -- callers still need to write the result to disk/DB themselves.
    """
    from audio_analysis.mix_review.source_delivery_comparison import (
        build_source_vs_delivery_comparison,
    )
    from audio_analysis.mixdown.stem_prep import write_wav

    stem_capture = mix_and_render_stems(prepared_stems, delivered_plan, capture_stem_audio=True)
    delivered_stem_audio = stem_capture.get("stem_audio") or {}
    common_names = [name for name in source_stem_audio if name in delivered_stem_audio]
    truncated = len(common_names) > MAX_PER_STEM_COMPARISON

    per_stem = {}
    for name in common_names[:MAX_PER_STEM_COMPARISON]:
        before_l, before_r = source_stem_audio[name]
        after_l, after_r = delivered_stem_audio[name]
        before_wav = write_wav(before_l.tolist(), before_r.tolist(), source_sample_rate)
        after_wav = write_wav(after_l.tolist(), after_r.tolist(), source_sample_rate)
        per_stem[name] = build_source_vs_delivery_comparison(before_wav, after_wav, mix_goal=mix_goal)

    return {"stems": per_stem, "stems_truncated": truncated, "stems_total": len(common_names)}


def apply_opt_in_engine_corrections(plan, style_prefs: dict) -> None:
    """Turn on masking/mono-compat/proactive-crest corrections when the user
    explicitly asked for them via style_prefs. All three default False on
    MixPlan itself -- a 2026-07-20 change flipped them on globally with no
    blind-A/B validation and had to be reverted (see mix_decision_engine.py's
    comment on apply_masking_corrections). That incident was about changing
    the DEFAULT for every render with no evidence; explicitly opting in per
    render at the user's own request is a different thing -- it changes
    nothing for anyone who doesn't ask for it. Mutates `plan` in place and
    appends a decisions_log entry for each one actually enabled."""
    if bool(style_prefs.get("masking_corrections", False)):
        plan.apply_masking_corrections = True
        plan.decisions_log.append("Masking corrections enabled by user preference.")
    if bool(style_prefs.get("mono_compat_correction", False)):
        plan.apply_mono_compat_correction = True
        plan.decisions_log.append("Mono-compatibility correction enabled by user preference.")
    if bool(style_prefs.get("proactive_crest_reduction", False)):
        plan.apply_proactive_crest_reduction = True
        plan.decisions_log.append("Proactive crest-factor reduction enabled by user preference.")
    if bool(style_prefs.get("deesser", False)):
        plan.apply_deesser = True
        plan.decisions_log.append("De-esser sibilance control enabled by user preference.")


def _process_job(job: dict) -> None:
    """Execute the full 8-phase mixdown pipeline for a job."""
    job_id = job["id"]
    project_id = validate_identifier(job["project_id"], label="project ID")
    genre = job.get("genre", "pop") or "pop"
    profile_started_at = time.perf_counter()
    resource_stages: list[dict] = []

    def record_resource_stage(stage: str) -> None:
        receipt = {"stage": stage, **_resource_snapshot(profile_started_at)}
        resource_stages.append(receipt)
        rss = receipt.get("peak_rss_bytes")
        rss_text = f", peak RSS {rss / (1024 * 1024):.1f} MiB" if isinstance(rss, int) else ""
        print(f"[automix_worker] Resource receipt {stage}: {receipt['elapsed_ms']:.0f} ms{rss_text}.", flush=True)

    print(f"[automix_worker] Processing job {job_id} for project {project_id} (genre: {genre})...", flush=True)

    try:
        # A. Setup paths
        stem_uploads.require_source_ready(project_id, upload_root=UPLOAD_ROOT)
        project_upload_dir = safe_child(UPLOAD_ROOT, project_id)

        # B. Extra unzipping step if stems were uploaded as a single zip
        extracted_dir = project_upload_dir / "extracted"
        zip_files = list(project_upload_dir.glob("*.zip"))

        if zip_files:
            _update_job_status(job_id, "preparing", "Unpacking ZIP file...")
            extracted_dir.mkdir(parents=True, exist_ok=True)
            for zf in zip_files:
                if zf.stat().st_size > MAX_SINGLE_FILE_BYTES:
                    raise ValueError(f"Zip file {zf.name} size exceeds limit of {MAX_SINGLE_FILE_BYTES // 1024 // 1024}MB.")
                with zipfile.ZipFile(zf, "r") as zip_ref:
                    extract_zip_safely(zip_ref, extracted_dir)

        # C. Scan for audio files
        scan_dir = extracted_dir if extracted_dir.exists() else project_upload_dir
        audio_suffixes = {".wav", ".aif", ".aiff", ".flac", ".mp3", ".m4a"}

        audio_paths = []
        for p in scan_dir.rglob("*"):
            if p.is_file() and p.suffix.lower() in audio_suffixes:
                # Exclude temporary and hidden files
                if not p.name.startswith(".") and not p.name.startswith("._"):
                    audio_paths.append(p)

        if not audio_paths:
            raise ValueError("No valid audio stems found in the project directory.")

        # Resource limits validations
        if len(audio_paths) > MAX_STEMS_COUNT:
            raise ValueError(f"Project exceeds limit of {MAX_STEMS_COUNT} audio stems (found {len(audio_paths)}).")

        # D. Read raw stem file bytes
        stems_raw = []
        for ap in audio_paths:
            if ap.stat().st_size > MAX_SINGLE_FILE_BYTES:
                raise ValueError(f"Audio stem {ap.name} size exceeds limit of {MAX_SINGLE_FILE_BYTES // 1024 // 1024}MB.")
            stems_raw.append({
                "name": ap.name,
                "file_bytes": ap.read_bytes(),
            })

        print(f"[automix_worker] Found {len(stems_raw)} audio stems for project {project_id}.", flush=True)

        # 1. Classification (Phase M1.1)
        _update_job_status(job_id, "classifying")
        profiles = classify_stems(stems_raw, read_wav_mono_fn=read_wav_mono, max_samples=131072)

        # 2. Preparation & Alignment (Phase M1.2)
        _update_job_status(job_id, "preparing")
        prepared_stems = prepare_stems(
            stems_raw,
            read_wav_mono_fn=read_wav_mono,
            target_sample_rate=44100,
            trim=True,
            normalise=False,
            max_samples=0,  # Process full duration!
            masking_preview_max_samples=65536,  # piggyback analyze_stems_masking's preview onto this decode
        )
        record_resource_stage("prepared")

        # Before/after baseline: an unprocessed unity-gain sum of the raw
        # stems, for the before/after comparison built once delivery is
        # ready (Stage 5.5 below). Computed into frozen WAV bytes right now,
        # before correct_stem_polarity or anything else mutates prepared_stems
        # in place -- otherwise a later reference to prepared_stems here would
        # silently reflect post-correction audio instead of the true upload.
        # Best-effort: a baseline problem must never block the real render.
        source_raw_wav_bytes = None
        source_stem_audio = None
        source_sample_rate = 44100
        try:
            _raw_baseline = render_unprocessed_stem_sum(prepared_stems)
            source_raw_wav_bytes = _raw_baseline["mixdown_wav_bytes"]
            source_stem_audio = _raw_baseline["stem_audio"]
            source_sample_rate = int(prepared_stems[0]["sample_rate"])
        except Exception as exc:
            print(f"[automix_worker] Before/after baseline skipped ({exc.__class__.__name__}).", flush=True)

        # Attach each stem's piggybacked masking preview (computed above, in
        # the same decode pass as the full-rate audio) onto stems_raw by name
        # so step 3 below can reuse it instead of re-parsing file_bytes.
        # Captured now, before correct_stem_polarity mutates prepared_stems,
        # so masking analysis keeps seeing pre-correction audio -- exactly
        # what the independent re-decode below has always analyzed.
        _preview_by_name = {
            s["name"]: (s.get("masking_preview_samples"), s.get("masking_preview_sample_rate"))
            for s in prepared_stems
        }
        for _s in stems_raw:
            _preview = _preview_by_name.get(_s.get("name"))
            if _preview and _preview[0] is not None:
                _s["masking_preview_samples"], _s["masking_preview_sample_rate"] = _preview

        # Validate prepared duration limit
        for stem in prepared_stems:
            samples = stem.get("samples")
            sr = stem.get("sample_rate", 44100)
            if samples is not None and len(samples) / sr > MAX_AUDIO_DURATION_SECONDS:
                raise ValueError(f"Audio file {stem.get('name')} duration exceeds limit of {MAX_AUDIO_DURATION_SECONDS} seconds.")

        # 2B. Phase/polarity correction across related stems (Stage M2) --
        # best-effort, never blocks delivery: a multi-mic'd source (kick
        # in/out, DI+amp, doubled vocal takes) with one mic out of polarity
        # causes destructive cancellation when summed. Mutates prepared_stems
        # in place so the fix propagates into rendering below.
        try:
            polarity_sr = prepared_stems[0].get("sample_rate", 44100) if prepared_stems else 44100
            prepared_stems, polarity_report = correct_stem_polarity(prepared_stems, polarity_sr)
            for name, entry in polarity_report.items():
                fixes = []
                if entry["polarity_flipped"]:
                    fixes.append(f"polarity flipped (rel. '{entry['inverted_relative_to']}')")
                if entry["time_shifted"]:
                    fixes.append(f"delayed {entry['lag_samples_corrected']} samples (aligned to '{entry['aligned_to']}')")
                corrected_corr = entry["corrected_correlation"]
                corrected_str = f"{corrected_corr:.2f}" if corrected_corr is not None else "n/a"
                print(
                    f"[automix_worker] Corrected '{name}': {', '.join(fixes)} "
                    f"(correlation {entry['original_correlation']:.2f} -> {corrected_str}, "
                    f"verified={entry['fix_verified']}).",
                    flush=True,
                )
        except Exception as exc:
            print(f"[automix_worker] Phase/polarity correction failed; continuing without it: {exc}", flush=True)

        # 3. Masking Analysis (Phase M3)
        _update_job_status(job_id, "analysing")
        masking_results = analyze_stems_masking(stems_raw, read_wav_mono=read_wav_mono, spectral_bands=spectral_bands)

        # 4. Deciding (Phase M3)
        _update_job_status(job_id, "deciding")
        style_prefs_str = job.get("style_prefs", "{}") or "{}"
        style_prefs = json.loads(style_prefs_str)

        # M8.4b: Use explicit target_lufs if set by the user via the platform preset selector
        if "_target_lufs" in style_prefs:
            target_lufs = float(style_prefs["_target_lufs"])
        else:
            target_lufs = -14.0
            comp_slider = style_prefs.get("compressed_dynamic", 0.5)  # 0.0 to 1.0
            if comp_slider < 0.5:
                target_lufs = -16.0 + (comp_slider / 0.5) * 2.0
            else:
                target_lufs = -14.0 + ((comp_slider - 0.5) / 0.5) * 3.0

        # Check for uploaded reference track. If present, we spectral-MATCH the
        # mix to it after a first render (the correct LOG-band engine in
        # spectral_match.py) rather than the linear analyze_reference_track path
        # (which reads bass as ~0 and can't drive the low end). So the decision
        # engine runs WITHOUT reference_profile; the match is a post-render pass
        # below. Log the filename only, never the full server-side path.
        reference_dir = safe_child(UPLOAD_ROOT, project_id, "reference")
        references = sorted(reference_dir.glob("reference.*")) if reference_dir.exists() else []
        ref_path = references[0] if references else reference_dir / "reference.wav"
        has_reference = ref_path.exists()
        reference_is_curated_default = False
        if has_reference:
            print(f"[automix_worker] Found reference track '{ref_path.name}'. "
                  f"Will spectral-match the mix to it.", flush=True)
        else:
            # No reference uploaded -- fall back to a curated genre-average
            # library (reference_tracks/<folder>/) so the user still gets
            # spectral matching without supplying their own reference. Only
            # engages for genres with a real curated folder; other genres
            # render exactly as before (no match). Resolve aliases the same
            # way generate_mix_plan will below (mix_decision_engine.resolve_genre)
            # so e.g. genre="house"/"techno" still finds the "edm" folder --
            # this lookup used to run on the raw string and silently miss
            # every alias, even though the mixing engine itself resolves them.
            from audio_analysis.mixdown.mix_decision_engine import resolve_genre
            resolved_genre, _resolve_note = resolve_genre(genre)
            default_ref = default_reference_dir(resolved_genre)
            if default_ref is not None:
                ref_path = default_ref
                has_reference = True
                reference_is_curated_default = True
                print(f"[automix_worker] No reference uploaded; using the curated "
                      f"'{default_ref.name}' genre reference library.", flush=True)

        plan = generate_mix_plan(
            profiles, masking_results,
            genre=genre, target_lufs=target_lufs,
            reference_profile=None,
            connect_func=connect,  # M8.3: pass DB connection for feedback-learned corrections
        )
        inferred_roles = infer_musical_roles(profiles, prepared_stems)
        musical_roles = apply_role_corrections(
            inferred_roles,
            style_prefs.get("musical_role_corrections"),
        )
        plan.musical_roles = [role.to_dict() for role in musical_roles]
        inferred_arrangement = infer_arrangement(prepared_stems)
        plan.arrangement = apply_arrangement_corrections(
            inferred_arrangement,
            style_prefs.get("arrangement_corrections"),
            [str(stem.get("name")) for stem in prepared_stems],
        ).to_dict()
        plan.mono_compatibility = analyze_mono_compatibility(
            prepared_stems, plan.arrangement
        ).to_dict()
        existing_dynamics = analyze_stems_for_dynamics(
            prepared_stems,
            profiles,
            prepared_stems[0]["sample_rate"] if prepared_stems else 44_100,
        )
        plan.relationships = [relationship.to_dict() for relationship in infer_relationships(
            profiles, masking_results, musical_roles, plan.arrangement, prepared_stems,
            existing_dynamics,
        )]
        plan.mix_graph = build_session_mix_graph(
            project_id=project_id,
            musical_roles=plan.musical_roles,
            arrangement=plan.arrangement,
            relationships=plan.relationships,
        )
        plan.automation_preview = build_automation_preview(plan.relationships).to_dict()
        record_resource_stage("planned")
        ambiguous_roles = [role.stem_name for role in musical_roles if role.ambiguous]
        plan.decisions_log.append(
            f"Musical-role contract v1 attached for {len(musical_roles)} stems; "
            f"{len(ambiguous_roles)} ambiguous role(s) withheld from role-driven DSP."
        )
        plan.decisions_log.append(
            f"Arrangement v1 detected {len(plan.arrangement['sections'])} activity section(s); "
            f"source={plan.arrangement['inference_source']}; semantic verse/chorus labels were "
            "not inferred."
        )
        plan.decisions_log.append(
            f"Relationship v1 found {len(plan.relationships)} simultaneous pair/group finding(s); "
            "none were applied automatically."
        )
        plan.decisions_log.append(
            "Mono compatibility v1 measured "
            f"{plan.mono_compatibility['measured_stereo_stems']} stereo stem(s): "
            f"status={plan.mono_compatibility['status']}, "
            f"problematic summed sections="
            f"{plan.mono_compatibility['problematic_summed_sections']}; "
            "evidence only, no automatic DSP."
        )
        plan.decisions_log.append(
            f"Automation preview v1 coordinated {len(plan.automation_preview['moves'])} bounded "
            "offline move(s); production processing remains disabled."
        )
        musical_role_feedback.record_applied_corrections(
            job_id=job_id,
            project_id=project_id,
            source_plan_revision=mix_plan_revision(plan),
            inferred_roles=inferred_roles,
            applied_roles=musical_roles,
        )

        # Stage J (use case #1): capture a (project features -> rule-engine
        # parameter) training row for every job, so a GLM has real data to
        # train on once enough jobs accumulate. Recorded against the plain
        # rule-engine plan (before Stage H's advisor, if enabled, touches
        # it below) since this is meant to model the rule engine's own
        # decision-making, not a KENN-adjusted one. Best-effort, never
        # blocks delivery -- nothing here reads back into this job.
        try:
            project_tempo_sr = prepared_stems[0].get("sample_rate", 44100) if prepared_stems else 44100
            tempo_bpm, tempo_confidence = estimate_project_tempo(prepared_stems, project_tempo_sr)
            project_features = extract_project_features(
                profiles, genre=genre, target_lufs=target_lufs,
                tempo_bpm=tempo_bpm, tempo_confidence=tempo_confidence,
            )
            record_project_training_row(
                job_id=job_id, project_id=project_id, genre=genre,
                features=project_features,
                target_name="mean_compressor_threshold_db",
                target_value=extract_compressor_threshold_target(plan),
                connect_func=connect,
            )
        except Exception as exc:
            print(f"[automix_worker] Stage J project-feature capture failed, continuing: {exc}", flush=True)

        # Stage H: the user opt-in currently means shadow evaluation only.  The
        # proposal is validated and persisted, but the rule-engine plan remains
        # byte-for-byte authoritative until the roadmap's promotion gate passes.
        kenn_autonomous_enabled = bool(style_prefs.get("autonomous_kenn"))
        shadow_receipt = None
        shadow_artifact_record = None
        shadow_source_plan = None
        if kenn_autonomous_enabled:
            shadow_source_plan = copy.deepcopy(plan)
            shadow_receipt = evaluate_advisor_shadow(
                plan,
                profiles,
                genre,
                target_lufs,
                correlation_id=str(job.get("correlation_id") or "") or f"automix-job:{job_id}",
            )
            try:
                shadow_artifact_record = _register_advisor_shadow_receipt(
                    job_id, project_id, shadow_receipt
                )
            except Exception as exc:
                print(
                    f"[automix_worker] Advisor shadow receipt persistence failed: {exc}",
                    flush=True,
                )
            plan.decisions_log.append(
                "KENN advisor shadow evaluation completed without applying changes "
                f"(status={shadow_receipt['status']}; "
                f"operations={shadow_receipt['operation_count']})."
            )

        # Stage M3: flag stems whose own detected tempo clearly disagrees with
        # the rest of the project (a possible wrong take or unquantized
        # element) -- a reported flag for human judgment, not an auto-fail,
        # best-effort so a detector failure never blocks delivery.
        try:
            tempo_sr = prepared_stems[0].get("sample_rate", 44100) if prepared_stems else 44100
            tempo_flags = analyze_stems_for_tempo_consistency(prepared_stems, tempo_sr)
            for name, flag in tempo_flags.items():
                plan.decisions_log.append(
                    f"Flagged '{name}' for review: its detected tempo ({flag['own_bpm']:.1f} BPM) "
                    f"is {flag['deviation_pct']:.0f}% off the rest of the project's consensus tempo "
                    f"({flag['consensus_bpm']:.1f} BPM) -- possibly a wrong take or unquantized "
                    f"element; please confirm this is intentional."
                )
        except Exception as exc:
            print(f"[automix_worker] Tempo consistency check failed; continuing without it: {exc}", flush=True)

        # Stage M4a: flag vocal stems that show a hard-pitch-correction
        # signature (frame-by-frame pitch locked to the equal-tempered grid)
        # -- a diagnostic annotation KENN can cite, not an auto-fail.
        # Restricted to stems classified as vocal: the detector assumes
        # monophonic melodic content, which a polyphonic instrument stem
        # (piano, guitar chords) would give a meaningless pitch track for.
        try:
            vocal_names = {p.name for p in profiles if p.instrument == "vocal"}
            for stem in prepared_stems:
                if stem["name"] not in vocal_names:
                    continue
                samples = np.asarray(stem["samples"], dtype=np.float64)
                sr = stem.get("sample_rate", 44100)
                pitch_flag = detect_pitch_correction_signature(samples, sr)
                if pitch_flag["pitch_correction_detected"]:
                    plan.decisions_log.append(
                        f"Note on '{stem['name']}': its pitch track reads as unusually stable "
                        f"(cents std-dev {pitch_flag['cents_std']:.1f}, "
                        f"{pitch_flag['near_grid_share']:.0%} of voiced frames within "
                        f"5 cents of the equal-tempered grid) -- consistent with hard pitch "
                        f"correction already applied upstream."
                    )
        except Exception as exc:
            print(f"[automix_worker] Pitch-correction check failed; continuing without it: {exc}", flush=True)

        # Stage M5: flag non-percussive stems that already show a brickwall
        # limiter's ceiling-clustering fingerprint -- a diagnostic annotation,
        # not an auto-fail. Percussive one-shot instruments (kick, snare,
        # drum busses/loops) are excluded: real testing showed they trigger
        # the same clustering signature from repeated similar-peak transient
        # hits, unrelated to limiting (see the detector's own module docstring).
        _PERCUSSIVE_INSTRUMENTS = {"kick", "snare", "hihat", "percussion", "full_drum_bus"}
        try:
            non_percussive_names = {p.name for p in profiles if p.instrument not in _PERCUSSIVE_INSTRUMENTS}
            for stem in prepared_stems:
                if stem["name"] not in non_percussive_names:
                    continue
                samples = np.asarray(stem["samples"], dtype=np.float64)
                sr = stem.get("sample_rate", 44100)
                limiter_flag = detect_limiter_fingerprint(samples, sr)
                if limiter_flag["limiter_fingerprint_detected"]:
                    plan.decisions_log.append(
                        f"Note on '{stem['name']}': its peak samples cluster densely near its own "
                        f"ceiling (ratio {limiter_flag['clustering_ratio']:.3f}) -- consistent with a "
                        f"brickwall limiter already applied upstream; it may have little remaining "
                        f"transient headroom for further peak-limiting-adjacent processing."
                    )
        except Exception as exc:
            print(f"[automix_worker] Limiter fingerprint check failed; continuing without it: {exc}", flush=True)

        # Modulate decisions based on style sliders
        bright_slider = style_prefs.get("bright_warm", 0.5)
        if abs(bright_slider - 0.5) > 0.1:
            for stem_c in plan.stems:
                if stem_c.instrument in ("vocal", "guitar", "keys", "snare"):
                    shelf_gain = (bright_slider - 0.5) * 4.0
                    stem_c.eq_bands.append({
                        "type": "highshelf",
                        "frequency": 8000.0,
                        "gain_db": shelf_gain,
                        "q": 0.707,
                        "reason": f"Adjusted via bright/warm preference slider ({bright_slider:.2f})",
                    })
            plan.decisions_log.append(f"Modulated mix plan brightness based on user slider preference: {bright_slider:.2f}")

        wet_slider = style_prefs.get("dry_wet", 0.5)
        if abs(wet_slider - 0.5) > 0.1:
            multiplier = wet_slider / 0.5
            for stem_c in plan.stems:
                stem_c.reverb_send = min(1.0, stem_c.reverb_send * multiplier)
                stem_c.delay_send = min(1.0, stem_c.delay_send * multiplier)
            plan.decisions_log.append(f"Modulated mix plan spatial sends based on user slider preference: {wet_slider:.2f}")

        wide_slider = style_prefs.get("narrow_wide", 0.5)
        if abs(wide_slider - 0.5) > 0.1:
            multiplier = wide_slider / 0.5
            for stem_c in plan.stems:
                stem_c.stereo_width = min(2.0, stem_c.stereo_width * multiplier)
            plan.decisions_log.append(f"Modulated mix plan stereo width based on user slider preference: {wide_slider:.2f}")

        apply_opt_in_engine_corrections(plan, style_prefs)

        feedback_history = style_prefs.get("feedback_history")
        if not isinstance(feedback_history, list) or not feedback_history:
            single = style_prefs.get("feedback", "").strip()
            feedback_history = [single] if single else []
        if feedback_history:
            # Never log the raw feedback text -- it's the customer's own
            # free-text input, exactly the "customer prompts leaked to logs"
            # case to avoid. Length/count only. Applied in order so a later
            # revision's ask stacks on top of earlier ones rather than
            # replacing them (every revision still rebuilds the plan from
            # scratch, so without re-applying prior feedback here it would
            # simply be lost).
            print(f"[automix_worker] Applying {len(feedback_history)} accumulated revision feedback entries", flush=True)
            from audio_analysis.mixdown.mix_decision_engine import apply_revision_feedback
            for entry in feedback_history:
                text = str(entry or "").strip()
                if text:
                    apply_revision_feedback(plan, text)

        # 5. Reference spectral match (two-pass): if a reference was uploaded,
        # render once to measure the mix's spectrum, derive a boost-biased
        # log-band master match-EQ toward the reference, and fold it into the
        # plan so the validated render below moves the mix's tonal balance
        # toward the reference. Best-effort: any failure just renders normally.
        probe_wav_bytes = None  # pre-match baseline, for the evidence report below
        match_bands: list = []
        reference_budget = reference_match_budget_decision(prepared_stems, style_prefs)
        if has_reference and not reference_budget["allowed"]:
            plan.decisions_log.append(
                f"Reference spectral match skipped: project duration {reference_budget['duration_seconds']:.1f}s "
                f"exceeds the {reference_budget['limit_seconds']:.0f}s safe probe-render budget. "
                "Set allow_long_reference_match only when you explicitly accept the additional offline render cost."
            )
            print("[automix_worker] Reference match skipped by duration budget.", flush=True)
        elif has_reference:
            try:
                from audio_analysis.mixdown.spectral_match import (
                    compute_reference_match_bands, compute_reference_width_factor,
                )
                probe_wav_bytes = _take_probe_wav(mix_and_render_stems(prepared_stems, plan))
                match_bands = compute_reference_match_bands(probe_wav_bytes, ref_path)
                if match_bands:
                    plan.bus.bus_eq_bands.extend(match_bands)
                    print(f"[automix_worker] Reference match: {len(match_bands)} master EQ band(s) applied.", flush=True)

                # Gentle stereo-width nudge toward the reference -- deliberately
                # NOT a hard match (aggressive M/S widening risks phase/mono
                # issues); see compute_reference_width_factor's docstring for
                # the safety bounds (35% similarity weight, 15% deadband, +/-15%
                # hard clamp).
                # Do not secretly pay for a third complete project render just
                # to estimate an optional width nudge after tonal matching.
                # The validated delivery render is already the second full
                # pass. A pre-EQ width measurement would be misleading after
                # a large low-end correction, so skip the nudge transparently
                # when spectral bands were applied; an engineer can still
                # revisit width from the delivered comparison.
                width_result = apply_reference_width_policy(
                    plan,
                    match_bands=match_bands,
                    probe_wav_bytes=probe_wav_bytes,
                    reference_path=ref_path,
                    compute_width_factor=compute_reference_width_factor,
                )
                if width_result.get("applied"):
                    print(
                        f"[automix_worker] Reference width: nudged x{width_result['factor']:.3f} "
                        "(similar-to, not matched).",
                        flush=True,
                    )
            except Exception as exc:
                print(f"[automix_worker] Reference match skipped ({exc.__class__.__name__}); rendering without it.", flush=True)
        record_resource_stage("reference_matched")

        # 6. Processing & Validation Loop (Phase M4 & M5)
        _update_job_status(job_id, "processing")
        render_result = validate_and_correct_mix(
            prepared_stems,
            plan,
            render_fn=mix_and_render_stems,
            max_iterations=3,
        )
        record_resource_stage("validated")
        try:
            _require_quality_gate(render_result)
        except RuntimeError:
            raise

        # M8.2 — Multi-pass refinement (best-effort; never blocks delivery)
        try:
            render_result = refine_mix_if_needed(
                prepared_stems, render_result, plan, connect_func=connect
            )
        except Exception as exc:
            print(f"[automix_worker] Multi-pass refinement failed for job {job_id}, "
                  f"delivering first-pass mix: {exc}", flush=True)
        render_result["kenn_autonomous"] = False
        render_result["kenn_advisor_mode"] = "shadow" if kenn_autonomous_enabled else "off"
        preview_summary = None
        if (
            shadow_receipt is not None
            and shadow_receipt.get("status") == "valid"
            and shadow_artifact_record is not None
            and shadow_source_plan is not None
            and isinstance(shadow_receipt.get("proposal"), dict)
        ):
            try:
                preview = render_advisor_previews(
                    prepared_stems,
                    shadow_source_plan,
                    shadow_receipt["proposal"],
                )
                preview_summary = _register_advisor_preview_artifacts(
                    job_id,
                    project_id,
                    shadow_artifact_record["artifact_id"],
                    preview,
                )
            except Exception as exc:
                print(f"[automix_worker] Advisor A/B preview failed: {exc}", flush=True)
        if shadow_receipt is not None:
            proposal = shadow_receipt.get("proposal")
            render_result["kenn_advisor_shadow"] = {
                "artifact_id": (
                    shadow_artifact_record.get("artifact_id", "")
                    if shadow_artifact_record is not None
                    else ""
                ),
                "status": shadow_receipt.get("status", "provider_error"),
                "operation_count": int(shadow_receipt.get("operation_count", 0)),
                "operations": (
                    proposal.get("operations", []) if isinstance(proposal, dict) else []
                ),
                "preview": preview_summary,
            }

        # 5.5 Match evidence report: before (pre-match probe) vs after (final
        # delivered mix) vs the reference target, plus KENN's grounded
        # explanations for the applied bands -- the same artifact
        # scripts/eval/match_track.py produces offline, now for web-UI jobs
        # too (curated-genre-default or user-uploaded reference alike).
        # Best-effort: a report problem must never block delivery.
        # MUST run before Stage 6 (packaging) writes mix_report_v<N>.html:
        # /api/automix/report/'s "*.html" glob serves the newest file in the
        # project dir by mtime, so mix_report_v<N>.html has to be written
        # *after* match_report.html to keep the two report routes distinct.
        #
        # match_report.html is a FIXED filename (not versioned like
        # mix_report_v<N>.html), so it must be actively removed whenever this
        # run doesn't (re)write one -- otherwise a later revision that drops
        # reference matching (e.g. genre changed to one with no curated
        # folder) would leave an earlier run's report sitting there, and
        # /api/automix/match-report/<project_id> would keep silently serving
        # it as if it described the mix actually being delivered now. Found
        # 2026-07-30 in a review of this same feature, before any real job
        # hit it.
        match_report_path = safe_child(MIX_OUTPUT_ROOT, project_id) / "match_report.html"
        # D2.3 (docs/KENN_FUTURE_PLAN.md Phase 2): the raw evidence dict
        # this block already computes (score_before/score_after, per-band
        # deltas, applied EQ moves) is exactly what a proactive
        # reference-comparison chat message needs -- persisted alongside
        # the HTML report so it's queryable without re-parsing the report
        # markup. Closes the storage/query half of D2.3; a chat surface
        # that actually polls this and injects a message isn't built this
        # round (same "storage now, surfacing later" split already used
        # for D1.7 and D1.5).
        match_evidence_path = safe_child(MIX_OUTPUT_ROOT, project_id) / "match_evidence.json"
        match_report_written = False
        if has_reference and probe_wav_bytes is not None:
            try:
                from audio_analysis.mix_review.match_report import (
                    build_match_evidence, render_match_report_html,
                )
                evidence = build_match_evidence(
                    probe_wav_bytes, render_result["mixdown_wav_bytes"], ref_path,
                    applied_bands=match_bands, genre=genre,
                )
                ref_label = ("your uploaded reference" if not reference_is_curated_default
                             else f"{ref_path.name} reference")
                html = render_match_report_html(
                    evidence, mix_label=project_id, ref_label=ref_label,
                )
                match_report_path.parent.mkdir(parents=True, exist_ok=True)
                match_report_path.write_text(html, encoding="utf-8")
                match_evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
                match_report_written = True
                print(f"[automix_worker] Match evidence report: score "
                      f"{evidence['score_before']} -> {evidence['score_after']}.", flush=True)
            except Exception as exc:
                print(f"[automix_worker] Match evidence report skipped ({exc.__class__.__name__}).", flush=True)
        if not match_report_written:
            match_report_path.unlink(missing_ok=True)
            match_evidence_path.unlink(missing_ok=True)

        # Build the core before/after evidence before packaging so the
        # downloadable manifest contains a durable quality receipt. Per-stem
        # detail is added after delivery below; it is useful but not required
        # to establish source/delivery provenance or the safety result.
        source_delivery_comparison = None
        if source_raw_wav_bytes is not None:
            try:
                from audio_analysis.mix_review.source_delivery_comparison import (
                    build_quality_receipt, build_source_vs_delivery_comparison,
                )
                delivered_plan = render_result.get("mix_plan")
                mix_goal = str(getattr(delivered_plan, "mix_goal", "") or "premaster")
                source_delivery_comparison = build_source_vs_delivery_comparison(
                    source_raw_wav_bytes, render_result["mixdown_wav_bytes"], mix_goal=mix_goal,
                )
                render_result["quality_receipt"] = build_quality_receipt(
                    source_delivery_comparison, render_result.get("quality_gate"),
                )
            except Exception as exc:
                print(f"[automix_worker] Quality receipt comparison skipped ({exc.__class__.__name__}).", flush=True)

        # 6. Packaging & Delivery (Phase M6)
        _update_job_status(job_id, "packaging")
        render_result["resource_profile"] = {
            "schema": "automix.resource_profile.v1",
            "stages": list(resource_stages),
        }
        uploader_email = _get_project_uploader_email(project_id)
        export_formats = tuple(
            item
            for item in style_prefs.get("export_formats", [])
            if isinstance(item, str) and item.lower() in {"flac", "mp3"}
        )

        download_url_template = "http://127.0.0.1:8080/api/automix/download/{}"

        delivery = package_mixdown_delivery(
            project_id=project_id,
            render_result=render_result,
            output_dir=MIX_OUTPUT_ROOT,
            recipient_email=uploader_email if uploader_email else None,
            download_url_template=download_url_template,
            additional_formats=export_formats,
            correlation_id=str(job.get("correlation_id") or "") or f"automix-job:{job_id}",
        )
        delivery["artifacts"] = _register_delivery_artifacts(job_id, project_id, delivery)

        # Before/after evidence: the raw upload baseline (captured above,
        # before any correction touched it) vs the finished delivered
        # mixdown -- "what did AutoMix actually change," independent of
        # whether a reference track was involved. Same version number as
        # the manifest for this render. Best-effort: never block a
        # completed delivery over a report problem.
        if source_delivery_comparison is not None:
            try:
                delivered_plan = render_result.get("mix_plan")
                mix_goal = str(getattr(delivered_plan, "mix_goal", "") or "premaster")
                comparison = source_delivery_comparison

                # Per-stem breakdown: which stem actually changed, not just
                # the summed mix. Best-effort within the best-effort block --
                # a per-stem failure keeps the overall comparison above, it
                # just skips the "stems" key.
                if source_stem_audio and delivered_plan is not None:
                    try:
                        comparison.update(
                            build_per_stem_before_after(
                                prepared_stems, delivered_plan, source_stem_audio,
                                source_sample_rate, mix_goal=mix_goal,
                            )
                        )
                    except Exception as exc:
                        print(
                            f"[automix_worker] Per-stem before/after skipped ({exc.__class__.__name__}).",
                            flush=True,
                        )

                comparison_path = (
                    safe_child(MIX_OUTPUT_ROOT, project_id)
                    / f"source_vs_delivery_v{delivery['version']}.json"
                )
                comparison_path.write_text(json.dumps(comparison, indent=2), encoding="utf-8")
            except Exception as exc:
                print(f"[automix_worker] Before/after comparison skipped ({exc.__class__.__name__}).", flush=True)

        if uploader_email and email_notify.smtp_delivery_enabled():
            delivery_service.queue_automix_notification(
                job_id=job_id,
                project_id=project_id,
                destination=uploader_email,
                version=int(delivery["version"]),
                download_url=download_url_template.format(project_id),
            )

        # Complete!
        _update_job_status(
            job_id,
            "complete",
            result_path=delivery["zip_path"],
            iteration_count=len(render_result.get("history", [])),
        )
        # zip_path is already persisted as result_path in _update_job_status
        # above -- don't also leak the raw server-side path into logs.
        print(f"[automix_worker] Job {job_id} completed successfully.", flush=True)

    except Exception as exc:
        err_msg = f"{exc.__class__.__name__}: {str(exc)}"
        print(f"[automix_worker] Job {job_id} failed: {err_msg}", flush=True)
        traceback.print_exc()
        _update_job_status(job_id, "failed", error_message=err_msg)


if __name__ == "__main__":
    # Lets this file run as a standalone process (e.g. the Docker
    # automix-worker service, see scripts/docker-entrypoint.sh) via
    # start_worker()'s polling loop, separate from start_automix_worker()'s
    # in-process background-thread mode used when the main server owns the
    # worker itself.
    start_worker()
