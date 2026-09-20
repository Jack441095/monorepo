"""Bounded bridge for the LLM_AudioGen subsystem."""

from __future__ import annotations

import io
import json
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

import audiogen_job_store
import artifact_store
import portfolio_ops
# automix_jobs/stem_uploads/AutomixStartRequest are imported lazily inside
# queue_automix_from_stem_files(), not here: this module sits on server.py's
# very first import chain (server -> demo_routes -> ableton_bridge ->
# audiogen_bridge), which runs before server.py adds studio/audio_analysis to
# sys.path -- stem_uploads.py needs that path at import time. By the time
# queue_automix_from_stem_files() actually runs, server startup has long
# finished and the path is in place.

ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = ROOT.parent
AUDIOGEN_ROOT = REPO_ROOT / "studio" / "audiogen" / "audiogen"
PORTFOLIO_AUDIO = ROOT / "portfolio" / "audio"
HISTORY_PATH = REPO_ROOT / "data" / "audiogen_render_history.json"
QUEUE_PATH = REPO_ROOT / "data" / "audiogen_render_queue.json"
SUPPORTED_EMOTIONS_ORDER = [
    "admiration",
    "amusement",
    "anger",
    "annoyance",
    "approval",
    "caring",
    "confusion",
    "curiosity",
    "desire",
    "disappointment",
    "disapproval",
    "disgust",
    "embarrassment",
    "excitement",
    "fear",
    "gratitude",
    "grief",
    "joy",
    "love",
    "nervousness",
    "optimism",
    "pride",
    "realization",
    "relief",
    "remorse",
    "sadness",
    "surprise",
    "neutral",
]
SUPPORTED_EMOTIONS = set(SUPPORTED_EMOTIONS_ORDER)
_QUEUE_LOCK = threading.RLock()
_QUEUE_CONDITION = threading.Condition(_QUEUE_LOCK)
_QUEUE_LOADED = False
_WORKER_THREAD: threading.Thread | None = None
_WORKER_STOP = threading.Event()
_MAX_JOB_HISTORY = 40
_MAX_RENDER_HISTORY = 200
_JOB_LEASE_SECONDS = 30.0


def exists() -> bool:
    return AUDIOGEN_ROOT.exists() and (AUDIOGEN_ROOT / "main_llm.py").exists()


def python_cmd() -> list[str]:
    """Command prefix to invoke Python for AudioGen subprocess calls.

    Prefers the local AudioGen venv (studio/audiogen/audiogen/.venv) over the
    shared project venv. That local venv is native arm64 with a current numba
    (0.66) — the shared root venv is x86_64/Rosetta, where numba is capped at
    0.60.0 (last Intel-mac wheel) and fails to import against NumPy 2.x, so
    AudioGen's realtime DSP (mixer, master_bus, reverb, sampler) silently falls
    back to pure Python. Measured impact was severe: mixer eq_filters ran 5.9x
    over the realtime budget, master_bus full_rt 1.28x over; with numba working
    those dropped to 0.01x and 0.07x (500-19x faster). See docs/BACKLOG.md.

    `arch -arm64` is required even though the local venv's python is a
    universal2 binary: this bridge itself runs inside the shared x86_64/Rosetta
    process, and a process already running under Rosetta inherits x86_64 when
    it execs a universal2 child unless the arch is forced explicitly.
    """
    local = AUDIOGEN_ROOT / ".venv" / "bin" / "python"
    if local.exists():
        return ["arch", "-arm64", str(local)]
    return [sys.executable]


def _clean(value: object) -> str:
    return str(value or "").strip()


def _slug(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return text or "audiogen"


def status() -> dict:
    py = " ".join(python_cmd()) if exists() else ""
    audit_path = AUDIOGEN_ROOT / ".cache" / "system_full_audit" / "system_full_audit_report.json"
    latest_audit = {}
    if audit_path.exists():
        latest_audit = {
            "path": str(audit_path),
            "updated_at": datetime.fromtimestamp(audit_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        }
    return {
        "ok": exists(),
        "root": str(AUDIOGEN_ROOT),
        "python": py,
        "has_local_venv": (AUDIOGEN_ROOT / ".venv" / "bin" / "python").exists(),
        "has_main_llm": (AUDIOGEN_ROOT / "main_llm.py").exists(),
        "has_full_render": (AUDIOGEN_ROOT / "main_render_full_song.py").exists(),
        "has_audit": (AUDIOGEN_ROOT / "tools" / "system_full_audit.py").exists(),
        "latest_audit": latest_audit,
        "portfolio_audio_count": len(list(PORTFOLIO_AUDIO.glob("*"))) if PORTFOLIO_AUDIO.exists() else 0,
        "emotions": SUPPORTED_EMOTIONS_ORDER,
        "render_queue": render_queue_snapshot(),
        "render_history_count": len(list_render_history(limit=_MAX_RENDER_HISTORY)),
    }


def _run(cmd: list[str], *, timeout: int = 120) -> dict:
    if not exists():
        return {"ok": False, "error": "LLM_AudioGen is not present."}
    completed = subprocess.run(
        cmd,
        cwd=AUDIOGEN_ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "command": " ".join(cmd),
    }


def _run_streaming(cmd: list[str], *, timeout: int = 120, progress_callback=None) -> dict:
    if not exists():
        return {"ok": False, "error": "LLM_AudioGen is not present."}
    started = time.monotonic()
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    last_progress = 0.0
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=AUDIOGEN_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
    except OSError as exc:
        return {"ok": False, "error": str(exc), "command": " ".join(cmd)}

    def reader(pipe, sink: list[str]) -> None:
        if pipe is None:
            return
        try:
            for line in iter(pipe.readline, ""):
                sink.append(line.rstrip())
        finally:
            try:
                pipe.close()
            except OSError:
                pass

    threads = [
        threading.Thread(target=reader, args=(proc.stdout, stdout_lines), daemon=True),
        threading.Thread(target=reader, args=(proc.stderr, stderr_lines), daemon=True),
    ]
    for thread in threads:
        thread.start()
    if progress_callback:
        progress_callback(20, "AudioGen process started.")

    timed_out = False
    while proc.poll() is None:
        elapsed = time.monotonic() - started
        if elapsed > timeout:
            timed_out = True
            proc.kill()
            break
        if progress_callback and elapsed - last_progress >= 2.0:
            last_progress = elapsed
            progress = min(78, 20 + int(elapsed * 3))
            progress_callback(progress, "Composing and rendering full-song audio...")
        time.sleep(0.2)

    returncode = proc.wait()
    for thread in threads:
        thread.join(timeout=1)
    stdout = "\n".join(line for line in stdout_lines if line).strip()
    stderr = "\n".join(line for line in stderr_lines if line).strip()
    if timed_out:
        return {
            "ok": False,
            "returncode": returncode,
            "stdout": stdout,
            "stderr": stderr,
            "error": f"AudioGen render timed out after {timeout}s.",
            "command": " ".join(cmd),
            "duration_seconds": round(time.monotonic() - started, 2),
        }
    if progress_callback:
        progress_callback(82, "AudioGen process finished; collecting render output.")
    return {
        "ok": returncode == 0,
        "returncode": returncode,
        "stdout": stdout,
        "stderr": stderr,
        "command": " ".join(cmd),
        "duration_seconds": round(time.monotonic() - started, 2),
    }


def _last_json_line(stdout: str) -> dict:
    for line in reversed((stdout or "").splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return {}


def test_command(args: list[str] | None = None) -> dict:
    cmd = [*python_cmd(), "-m", "pytest", "-m", "not slow", "-q", *(args or [])]
    return _run(cmd, timeout=240)


def audit_command(args: list[str] | None = None) -> dict:
    script = AUDIOGEN_ROOT / "tools" / "system_full_audit.py"
    cmd = [*python_cmd(), str(script), *(args or [])]
    return _run(cmd, timeout=300)


def phrase_command(
    *,
    emotion: str,
    bars: int = 8,
    seed: str = "",
    wav_out: str | Path | None = None,
    include_events: bool = False,
) -> dict:
    emotion = _clean(emotion) or "joy"
    if emotion not in SUPPORTED_EMOTIONS:
        emotion = "joy"
    safe_bars = max(1, min(32, int(bars or 8)))
    cmd = [
        *python_cmd(),
        str(AUDIOGEN_ROOT / "main_llm.py"),
        "--emotion",
        emotion,
        "--bars",
        str(safe_bars),
        "--no-play",
    ]
    if seed:
        cmd.extend(["--seed", str(seed)])
    if wav_out:
        cmd.extend(["--wav-out", str(wav_out)])
    if include_events:
        cmd.append("--include-events")

    result = _run(cmd, timeout=180)
    result["result"] = _last_json_line(result.get("stdout", ""))
    return result


def render_command(*, emotion: str, k: int = 3, args: list[str] | None = None) -> dict:
    emotion = _clean(emotion) or "joy"
    if emotion not in SUPPORTED_EMOTIONS:
        emotion = "joy"
    cmd = [
        *python_cmd(),
        str(AUDIOGEN_ROOT / "main_render_full_song.py"),
        "--emotion",
        emotion,
        "--k",
        str(max(1, min(12, int(k or 3)))),
        *(args or []),
    ]
    return _run(cmd, timeout=300)


def render_command_stream(
    *,
    emotion: str,
    k: int = 3,
    args: list[str] | None = None,
    progress_callback=None,
) -> dict:
    emotion = _clean(emotion) or "joy"
    if emotion not in SUPPORTED_EMOTIONS:
        emotion = "joy"
    cmd = [
        *python_cmd(),
        str(AUDIOGEN_ROOT / "main_render_full_song.py"),
        "--emotion",
        emotion,
        "--k",
        str(max(1, min(12, int(k or 3)))),
        *(args or []),
    ]
    return _run_streaming(cmd, timeout=300, progress_callback=progress_callback)


def _portfolio_src(wav_path: Path) -> str:
    return f"/portfolio/audio/{wav_path.name}"


def _latest_matching_wav(export_dir: Path, prefix: str) -> Path | None:
    matches = sorted(
        export_dir.glob(f"{prefix}*.wav"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return matches[0] if matches else None


def list_render_history(limit: int = 25) -> list[dict]:
    if not HISTORY_PATH.exists():
        return []
    try:
        items = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(items, list):
        return []
    return [item for item in reversed(items[-max(1, min(_MAX_RENDER_HISTORY, int(limit or 25))) :]) if isinstance(item, dict)]


def _append_render_history(entry: dict) -> None:
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    items = list(reversed(list_render_history(limit=_MAX_RENDER_HISTORY)))
    clean = {
        "id": entry.get("id") or uuid.uuid4().hex[:12],
        "kind": entry.get("kind", "audio"),
        "emotion": entry.get("emotion", ""),
        "bars": entry.get("bars", ""),
        "project_id": entry.get("project_id", ""),
        "src": entry.get("src", ""),
        "wav_path": entry.get("wav_path", ""),
        "portfolio_title": entry.get("portfolio_title", ""),
        "artifact_id": entry.get("artifact_id", ""),
        "created_at": entry.get("created_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    items.append(clean)
    HISTORY_PATH.write_text(json.dumps(items[-_MAX_RENDER_HISTORY:], indent=2) + "\n", encoding="utf-8")


def _load_queue_locked() -> None:
    global _QUEUE_LOADED
    if _QUEUE_LOADED:
        return
    audiogen_job_store.import_legacy_json(QUEUE_PATH)
    audiogen_job_store.recover_expired()
    _QUEUE_LOADED = True


def _job_public(job: dict) -> dict:
    return {
        "id": job.get("id", ""),
        "status": job.get("status", "queued"),
        "emotion": job.get("emotion", "joy"),
        "bars": job.get("bars", 4),
        "k": job.get("k", 1),
        "publish": bool(job.get("publish", True)),
        "project_id": job.get("project_id", ""),
        "progress": int(job.get("progress", 0)),
        "message": job.get("message", ""),
        "created_at": job.get("created_at", ""),
        "started_at": job.get("started_at", ""),
        "finished_at": job.get("finished_at", ""),
        "cancel_requested": bool(job.get("cancel_requested", False)),
        "result": job.get("result") or None,
        "error": job.get("error", ""),
        "genre": job.get("genre", ""),
        "style_prefs": job.get("style_prefs") or {},
        "chain_to_automix": bool(job.get("chain_to_automix", False)),
        "automix_job_id": job.get("automix_job_id", ""),
    }


def _ensure_worker() -> None:
    global _WORKER_THREAD
    with _QUEUE_CONDITION:
        if _WORKER_THREAD is not None and _WORKER_THREAD.is_alive():
            return
        _WORKER_STOP.clear()
        _WORKER_THREAD = threading.Thread(
            target=_render_worker_loop,
            name="audiogen-render-worker",
            daemon=True,
        )
        _WORKER_THREAD.start()


def stop_render_worker(timeout: float = 5.0) -> None:
    """Stop the in-process render worker without abandoning its active render."""
    global _WORKER_THREAD
    with _QUEUE_CONDITION:
        _WORKER_STOP.set()
        _QUEUE_CONDITION.notify_all()
        worker = _WORKER_THREAD
    if worker is not None:
        worker.join(timeout=max(0.0, timeout))
    if worker is None or not worker.is_alive():
        _WORKER_THREAD = None


def enqueue_full_song_render(
    *,
    emotion: str = "",
    bars: int = 4,
    k: int = 1,
    publish: bool = True,
    project_id: str = "",
    chain_to_automix: bool = False,
    genre: str = "",
    style_prefs: dict | None = None,
) -> dict:
    chosen = _clean(emotion) or "joy"
    if chosen not in SUPPORTED_EMOTIONS:
        chosen = "joy"
    safe_bars = max(1, min(16, int(bars or 4)))
    safe_k = max(1, min(4, int(k or 1)))
    with _QUEUE_CONDITION:
        _load_queue_locked()
        job = audiogen_job_store.create(
            emotion=chosen,
            bars=safe_bars,
            candidate_count=safe_k,
            publish=bool(publish),
            project_id=_clean(project_id),
            genre=_clean(genre),
            style_prefs=style_prefs,
            chain_to_automix=bool(chain_to_automix),
        )
        audiogen_job_store.trim(_MAX_JOB_HISTORY)
        _QUEUE_CONDITION.notify()
    _ensure_worker()
    return {"ok": True, "job": _job_public(job)}


def render_job(job_id: str) -> dict:
    with _QUEUE_LOCK:
        _load_queue_locked()
        job = audiogen_job_store.get(_clean(job_id))
        if not job:
            return {"ok": False, "error": "Render job not found."}
        return {"ok": True, "job": _job_public(job)}


def render_job_events(job_id: str) -> dict:
    """Read-only lookup of a render job's immutable event log.

    Thin wrapper around audiogen_job_store.events(), which already exists
    and is already covered by test_audiogen_job_store.py but was never
    exposed over HTTP -- added to back the AudioGen UI's "generation
    trace" panel (queued -> running -> completed/failed, with real
    timestamps) without touching the write path, the job schema, or any
    existing endpoint.
    """
    clean_id = _clean(job_id)
    with _QUEUE_LOCK:
        _load_queue_locked()
        job = audiogen_job_store.get(clean_id)
        if not job:
            return {"ok": False, "error": "Render job not found."}
        events = audiogen_job_store.events(clean_id)
    return {
        "ok": True,
        "job_id": clean_id,
        "events": [
            {
                "status": event.get("status", ""),
                "message": event.get("message", ""),
                "progress": int(event.get("progress", 0) or 0),
                "worker_id": event.get("worker_id", ""),
                "created_at": event.get("created_at", ""),
            }
            for event in events
        ],
    }


def render_queue_snapshot(limit: int = 12) -> dict:
    with _QUEUE_LOCK:
        _load_queue_locked()
        jobs = [_job_public(job) for job in audiogen_job_store.recent(limit)]
    return {
        "running": [job for job in jobs if job["status"] == "running"],
        "queued": [job for job in jobs if job["status"] == "queued"],
        "recent": jobs,
    }


def cancel_render_job(job_id: str) -> dict:
    with _QUEUE_CONDITION:
        _load_queue_locked()
        job = audiogen_job_store.request_cancel(_clean(job_id))
        if not job:
            return {"ok": False, "error": "Render job not found."}
        _QUEUE_CONDITION.notify()
        return {"ok": True, "job": _job_public(job)}


def retry_render_job(job_id: str) -> dict:
    with _QUEUE_LOCK:
        _load_queue_locked()
        job = audiogen_job_store.get(_clean(job_id))
        if not job:
            return {"ok": False, "error": "Render job not found."}
    return enqueue_full_song_render(
        emotion=str(job.get("emotion", "joy")),
        bars=int(job.get("bars", 4) or 4),
        k=int(job.get("k", 1) or 1),
        publish=bool(job.get("publish", True)),
        project_id=str(job.get("project_id", "")),
        chain_to_automix=bool(job.get("chain_to_automix", False)),
        genre=str(job.get("genre", "")),
        style_prefs=job.get("style_prefs") or None,
    )


def _render_worker_loop() -> None:
    worker_id = f"audiogen-{uuid.uuid4().hex[:12]}"
    while not _WORKER_STOP.is_set():
        with _QUEUE_CONDITION:
            _load_queue_locked()
            audiogen_job_store.recover_expired()
            job = audiogen_job_store.claim_next(worker_id, lease_seconds=_JOB_LEASE_SECONDS)
            while job is None and not _WORKER_STOP.is_set():
                _QUEUE_CONDITION.wait(timeout=2.0)
                if _WORKER_STOP.is_set():
                    return
                audiogen_job_store.recover_expired()
                job = audiogen_job_store.claim_next(
                    worker_id, lease_seconds=_JOB_LEASE_SECONDS
                )
            if job is None:
                return

        heartbeat_stop = threading.Event()

        def maintain_lease() -> None:
            while not heartbeat_stop.wait(_JOB_LEASE_SECONDS / 3):
                if not audiogen_job_store.heartbeat(
                    job["id"], worker_id, lease_seconds=_JOB_LEASE_SECONDS
                ):
                    return

        heartbeat_thread = threading.Thread(
            target=maintain_lease,
            name=f"audiogen-heartbeat-{job['id']}",
            daemon=True,
        )
        heartbeat_thread.start()

        def progress_callback(progress: int, message: str) -> None:
            audiogen_job_store.heartbeat(
                job["id"],
                worker_id,
                lease_seconds=_JOB_LEASE_SECONDS,
                progress=progress,
                message=message,
            )

        try:
            result = render_full_song_for_web(
                emotion=str(job.get("emotion", "joy")),
                bars=int(job.get("bars", 4) or 4),
                k=int(job.get("k", 1) or 1),
                publish=bool(job.get("publish", True)),
                project_id=str(job.get("project_id", "")),
                artifact_external_key=f"audiogen-job:{job['id']}",
                progress_callback=progress_callback,
                chain_to_automix=bool(job.get("chain_to_automix", False)),
                genre=str(job.get("genre", "")),
                style_prefs=job.get("style_prefs") or None,
            )
        except Exception as exc:  # pragma: no cover - defensive worker boundary
            result = {"ok": False, "error": str(exc)}
        finally:
            heartbeat_stop.set()
            heartbeat_thread.join(timeout=1.0)

        automix_chain_job_id = ((result or {}).get("automix") or {}).get("job_id")
        if automix_chain_job_id:
            audiogen_job_store.set_automix_job_id(job["id"], str(automix_chain_job_id))

        with _QUEUE_CONDITION:
            if audiogen_job_store.cancellation_requested(job["id"]):
                status = "cancelled"
                message = "Render completed after cancel was requested; result was not promoted in the UI."
                error = ""
            elif result.get("ok"):
                status = "completed"
                message = "Full song render complete."
                error = ""
                _append_render_history(
                    {
                        "id": job.get("id"),
                        "kind": "full_song",
                        "emotion": job.get("emotion"),
                        "bars": job.get("bars"),
                        "project_id": job.get("project_id", ""),
                        "src": result.get("src", ""),
                        "wav_path": result.get("wav_path", ""),
                        "portfolio_title": (result.get("portfolio_entry") or {}).get("title", ""),
                        "artifact_id": (result.get("artifact") or {}).get("artifact_id", ""),
                    }
                )
            else:
                status = "failed"
                message = "Full song render failed."
                error = result.get("error", "AudioGen render failed.")
            audiogen_job_store.finish(
                job["id"],
                worker_id,
                status=status,
                message=message,
                result=result,
                error=error,
            )
            audiogen_job_store.trim(_MAX_JOB_HISTORY)
            _QUEUE_CONDITION.notify_all()


def _cleanup_audiogen_exports(export_dir: Path) -> None:
    """Delete the AudioGen export directory after the file has been copied to Portfolio.

    AudioGen's `main_render_full_song.py` writes WAVs and JSON reports to
    `exports/web/`. Once we've copied the file to Portfolio, these are just
    duplicates consuming ~16 MB per render.
    """
    if not export_dir.exists():
        return
    try:
        for item in list(export_dir.iterdir()):
            if item.is_file():
                item.unlink()
    except OSError:
        pass


def queue_automix_from_stem_files(
    *,
    project_id: str,
    genre: str,
    style_prefs: dict | None,
    stem_paths: dict[str, str],
) -> dict:
    """Zip AudioGen's captured per-instrument stems and feed them through
    AutoMix's own upload + job-creation calls -- the same two operations a
    user's "upload stems, then start a mix" flow makes -- so a chained
    AudioGen render becomes an ordinary AutoMix job with no special-casing
    anywhere downstream (worker, status polling, KENN explainability all
    just see a normal job).
    """
    import automix_jobs
    import stem_uploads
    from app.api_schemas import AutomixStartRequest

    project_id = str(project_id or "").strip()
    if not project_id:
        return {"ok": False, "error": "project_id is required to chain to AutoMix."}
    if not stem_paths:
        return {"ok": False, "error": "No stems were captured for this render."}

    buf = io.BytesIO()
    # ZIP_STORED (no compression), not ZIP_DEFLATED: found live 2026-08-07
    # running this chain end-to-end -- a generated stem with a long
    # near-silent/sustained passage (e.g. a quiet drone) compresses well
    # past archive_safety.py's MAX_ZIP_COMPRESSION_RATIO (1000:1), a real
    # zip-bomb guard on the read side (stem_uploads.py's
    # validate_automix_source) that correctly rejected the resulting
    # archive. WAV/PCM audio barely compresses anyway except in exactly
    # this silence-heavy case, so storing uncompressed sidesteps the
    # false-positive entirely rather than loosening a real security
    # guard to work around it.
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        for name, path_str in stem_paths.items():
            path = Path(path_str)
            if path.exists():
                zf.write(path, arcname=f"{name}.wav")
    zip_bytes = buf.getvalue()
    if len(zip_bytes) <= 22:  # empty zip is 22 bytes (end-of-central-directory record only)
        return {"ok": False, "error": "No stem files were found on disk to package."}

    try:
        _status, upload_response = stem_uploads.store_upload(
            stem_uploads.StemUploadRequest(
                project_id=project_id,
                file_bytes=zip_bytes,
                filename="audiogen-stems.zip",
                project_label=f"Project {project_id}",
                uploader_name="AudioGen",
                notes="Auto-generated stems chained from an AudioGen render.",
            )
        )
    except stem_uploads.UploadValidationError as exc:
        return {"ok": False, "error": f"Stem upload failed: {exc}"}
    if not upload_response.get("ok"):
        return {"ok": False, "error": upload_response.get("error") or "Stem upload failed."}

    try:
        _job_status, job_response = automix_jobs.queue_job(
            AutomixStartRequest(
                project_id=project_id,
                genre=str(genre or "pop"),
                style_prefs=dict(style_prefs or {}),
            )
        )
    except stem_uploads.SourceNotReady as exc:
        return {"ok": False, "error": str(exc)}
    if not job_response.get("ok"):
        return {"ok": False, "error": job_response.get("error") or "AutoMix job creation failed."}

    return {
        "ok": True,
        "upload_id": upload_response.get("upload_id", ""),
        "job_id": job_response.get("job_id", ""),
    }


_STEM_FILENAME_RE = re.compile(r"_stem_([a-z_]+)\.wav$")


def render_full_song_for_web(
    *,
    emotion: str = "",
    bars: int = 4,
    k: int = 1,
    publish: bool = True,
    project_id: str = "",
    artifact_external_key: str = "",
    progress_callback=None,
    chain_to_automix: bool = False,
    genre: str = "",
    style_prefs: dict | None = None,
) -> dict:
    chosen = _clean(emotion) or "joy"
    if chosen not in SUPPORTED_EMOTIONS:
        chosen = "joy"

    safe_bars = max(1, min(16, int(bars or 4)))
    safe_k = max(1, min(4, int(k or 1)))
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    prefix = f"kenn-full-song-{_slug(chosen)}-{stamp}"
    export_dir = AUDIOGEN_ROOT / "exports" / "web"
    PORTFOLIO_AUDIO.mkdir(parents=True, exist_ok=True)

    render_args = [
        "--bars",
        str(safe_bars),
        "--export-dir",
        str(export_dir),
        "--prefix",
        prefix,
    ]
    if chain_to_automix:
        render_args.append("--export-stems")
    result = (
        render_command_stream(
            emotion=chosen,
            k=safe_k,
            args=render_args,
            progress_callback=progress_callback,
        )
        if progress_callback
        else render_command(
            emotion=chosen,
            k=safe_k,
            args=render_args,
        )
    )
    if not result.get("ok"):
        return {
            "ok": False,
            "emotion": chosen,
            "error": result.get("stderr") or result.get("stdout") or "AudioGen full-song render failed.",
            "raw": result,
        }

    rendered_wav = _latest_matching_wav(export_dir, prefix)
    if not rendered_wav or not rendered_wav.exists():
        return {
            "ok": False,
            "emotion": chosen,
            "error": "AudioGen completed but no WAV was found.",
            "raw": result,
        }

    filename = f"{prefix}.wav"
    wav_path = PORTFOLIO_AUDIO / filename
    if progress_callback:
        progress_callback(88, "Copying rendered WAV into Portfolio/audio.")
    shutil.copy2(rendered_wav, wav_path)

    try:
        artifact = artifact_store.register_file(
            wav_path,
            kind="audio.generated.full_song",
            media_type="audio/wav",
            producer="audiogen",
            producer_version="1.0.0",
            project_id=_clean(project_id),
            external_key=_clean(artifact_external_key),
            source_uri=_portfolio_src(wav_path),
            metadata={
                "emotion": chosen,
                "bars": safe_bars,
                "candidate_count": safe_k,
                "filename": wav_path.name,
            },
        )
    except Exception as exc:
        wav_path.unlink(missing_ok=True)
        return {
            "ok": False,
            "emotion": chosen,
            "error": f"AudioGen rendered successfully but artifact registration failed: {exc}",
            "raw": result,
        }

    entry = None
    if publish:
        if progress_callback:
            progress_callback(94, "Publishing AudioGen render to portfolio.")
        published = portfolio_ops.publish_audio(
            wav_path.name,
            title=f"KENN AudioGen - {chosen.title()} full song",
            description=f"Full-song generative render from kenn AudioGen using the {chosen} emotion mode.",
        )
        entry = published.get("entry") if published.get("ok") else None

    automix_result = None
    if chain_to_automix:
        if progress_callback:
            progress_callback(96, "Uploading generated stems to AutoMix.")
        stem_paths: dict[str, str] = {}
        for stem_file in export_dir.glob(f"{prefix}*_stem_*.wav"):
            match = _STEM_FILENAME_RE.search(stem_file.name)
            if match:
                stem_paths[match.group(1)] = str(stem_file)
        automix_result = queue_automix_from_stem_files(
            # `chosen` is an emotion (joy/sadness/...), not a music genre --
            # AutoMix's own default ("pop") is the right fallback here, not
            # the AudioGen emotion name.
            project_id=project_id,
            genre=genre or "pop",
            style_prefs=style_prefs,
            stem_paths=stem_paths,
        )

    # Clean up the export directory — the WAV (and any stems, already
    # uploaded to AutoMix above) has been copied out of this scratch dir.
    _cleanup_audiogen_exports(export_dir)

    result_payload = {
        "ok": True,
        "emotion": chosen,
        "bars": safe_bars,
        "k": safe_k,
        "wav_path": str(wav_path),
        "src": _portfolio_src(wav_path),
        "portfolio_entry": entry,
        "artifact": artifact_store.public_record(artifact),
        "raw": result,
    }
    if automix_result is not None:
        result_payload["automix"] = automix_result
    return result_payload


def generate_for_kenn(
    prompt: str,
    *,
    emotion: str = "",
    bars: int = 8,
    publish: bool = True,
    project_id: str = "",
) -> dict:
    chosen = _clean(emotion) or infer_emotion(prompt)
    if chosen not in SUPPORTED_EMOTIONS:
        chosen = infer_emotion(prompt)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"kenn-audiogen-{_slug(chosen)}-{stamp}.wav"
    wav_path = PORTFOLIO_AUDIO / filename
    PORTFOLIO_AUDIO.mkdir(parents=True, exist_ok=True)

    result = phrase_command(emotion=chosen, bars=bars, wav_out=wav_path)
    payload = dict(result.get("result") or {})
    if not result.get("ok") or not payload.get("ok"):
        return {
            "ok": False,
            "emotion": chosen,
            "error": payload.get("error") or result.get("stderr") or "AudioGen generation failed.",
            "raw": result,
        }

    artifact = None
    if wav_path.exists():
        try:
            artifact = artifact_store.register_file(
                wav_path,
                kind="audio.generated.loop",
                media_type="audio/wav",
                producer="audiogen",
                producer_version="1.0.0",
                project_id=_clean(project_id),
                source_uri=_portfolio_src(wav_path),
                metadata={
                    "emotion": chosen,
                    "bars": max(1, int(bars or 1)),
                    "filename": wav_path.name,
                },
            )
        except Exception as exc:
            wav_path.unlink(missing_ok=True)
            return {
                "ok": False,
                "emotion": chosen,
                "error": f"AudioGen generated audio but artifact registration failed: {exc}",
                "raw": result,
            }

    entry = None
    if publish and wav_path.exists():
        published = portfolio_ops.publish_audio(
            wav_path.name,
            title=f"KENN AudioGen - {chosen.title()} chorus",
            description=f"Generated from kenn prompt: {_clean(prompt)[:160]}",
        )
        entry = published.get("entry") if published.get("ok") else None
    if wav_path.exists():
        _append_render_history(
            {
                "kind": "loop",
                "emotion": chosen,
                "bars": bars,
                "project_id": _clean(project_id),
                "src": _portfolio_src(wav_path),
                "wav_path": str(wav_path),
                "portfolio_title": (entry or {}).get("title", ""),
                "artifact_id": (artifact or {}).get("id", ""),
            }
        )

    return {
        "ok": True,
        "emotion": chosen,
        "bars": bars,
        "project_id": _clean(project_id),
        "wav_path": str(wav_path) if wav_path.exists() else "",
        "src": _portfolio_src(wav_path) if wav_path.exists() else "",
        "portfolio_entry": entry,
        "artifact": artifact_store.public_record(artifact) if artifact else None,
        "audiogen": payload,
    }


def infer_emotion(prompt: str) -> str:
    lowered = prompt.lower()
    for emotion in (
        "joy",
        "love",
        "sadness",
        "grief",
        "fear",
        "anger",
        "excitement",
        "relief",
        "curiosity",
        "neutral",
    ):
        if emotion in lowered:
            return emotion
    if "happy" in lowered or "uplifting" in lowered:
        return "joy"
    if "sad" in lowered or "melancholy" in lowered:
        return "sadness"
    if "dark" in lowered:
        return "fear"
    return "joy"


def generation_request_kind(prompt: str) -> str:
    if not prompt_requests_generation(prompt):
        return "none"
    lowered = prompt.lower()
    full_terms = (
        "full song",
        "whole song",
        "complete song",
        "full track",
        "whole track",
        "complete track",
        "arrangement",
        "render a song",
        "generate a song",
        "make a song",
        "compose a song",
    )
    loop_terms = (
        "chorus",
        "loop",
        "phrase",
        "melody",
        "hook",
        "riff",
        "idea",
        "sketch",
    )
    if any(term in lowered for term in full_terms):
        return "full_song"
    if requests_automix_chain(prompt):
        return "full_song"
    if any(term in lowered for term in loop_terms):
        return "loop"
    if "song" in lowered or "track" in lowered:
        return "full_song"
    return "clarify"


def prompt_requests_generation(prompt: str) -> bool:
    lowered = prompt.lower()
    music_objects = (
            "arrangement",
            "beat",
            "chorus",
            "composition",
            "instrumental",
            "loop",
            "melody",
            "music",
            "phrase",
            "song",
            "track",
    )
    has_music_object = any(word in lowered for word in music_objects)
    explicit_action = any(word in lowered for word in ("generate", "compose", "render"))
    natural_action = any(
        re.search(rf"\b{verb}\s+(?:me\s+)?(?:a|an|the|some|another)\s+[^?.]{{0,40}}\b{obj}\b", lowered)
        for verb in ("make", "create", "write")
        for obj in music_objects
    )
    has_action = explicit_action or natural_action
    if has_music_object and has_action:
        return True
    # D3.5 (docs/KENN_FUTURE_PLAN.md Phase 3): "my loop is too
    # repetitive, give me a variation" has no explicit generate/make
    # verb, but a variation request implies wanting a new generation --
    # requests_variation() is defined later in this module but resolved
    # at call time, so the forward reference is safe.
    return has_music_object and requests_variation(prompt)


_AUTOMIX_CHAIN_RE = re.compile(
    r"\bauto[\s-]?mix\b|\b(?:then|and)\s+(?:render|run|start)\s+(?:an?\s+)?(?:automix|auto[\s-]?mix|mix)\b|\bmix\s+pass\b",
    re.I,
)


def requests_automix_chain(prompt: str) -> bool:
    """True if a generation request also asks to chain straight into an
    AutoMix render (D3.2, docs/KENN_FUTURE_PLAN.md Phase 3) -- e.g.
    "generate drums and bassline, then render an AutoMix pass from
    these". Only meaningful for a full-song request (the chain needs
    `--export-stems`, a multi-instrument render, not a single loop) --
    callers gate on that separately."""
    return bool(_AUTOMIX_CHAIN_RE.search(prompt or ""))


_VARIATION_RE = re.compile(
    r"\btoo\s+repetitive\b|\b(?:give|try|generate)\s+(?:me\s+)?(?:a\s+)?(?:different|another|new)\s+(?:variation|version|take|idea)\b"
    r"|\btry\s+(?:a\s+)?(?:different|another)\s+(?:one|version|take)\b|\bswitch\s+it\s+up\b",
    re.I,
)


def requests_variation(prompt: str) -> bool:
    """True if the message reads as a request for an alternative take on
    something already generated (D3.5, docs/KENN_FUTURE_PLAN.md Phase 3,
    the buildable half -- "my loop is too repetitive, give me a
    variation"). Deliberately does NOT try to target a specific section
    ("my bass hits wrong note at bar 32" needs bar-precise generation/
    editing this doesn't have -- that half stays unbuilt). Re-running
    generation naturally produces a different render each time (no fixed
    seed pinning), so this is purely a trigger-phrase addition on top of
    the existing, already-tested generation pipeline -- no new DSP or
    generation capability needed."""
    return bool(_VARIATION_RE.search(prompt or ""))
