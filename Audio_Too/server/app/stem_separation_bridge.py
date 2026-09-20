"""Bounded bridge for the stem_separation subsystem (Demucs v4).

Mirrors audiogen_bridge.py's isolation shape: the real work (torch + Demucs)
only ever runs inside studio/stem_separation's own venv, invoked as a
subprocess -- this module, and the shared app process it lives in, never
import torch directly. Job durability (queue/claim/heartbeat/finish) is
handled by stem_separation_job_store.py, a near-identical sibling of
audiogen_job_store.py; the in-process worker loop below mirrors
audiogen_bridge.py's `_render_worker_loop`.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
import time
import uuid
import zipfile
from pathlib import Path

import stem_separation_job_store
from audio_analysis.utils.media_safety import (
    ensure_private_directory,
    validate_audio_duration,
    validate_media_upload,
    write_private_file,
)

ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = ROOT.parent
STEM_SEP_ROOT = REPO_ROOT / "studio" / "stem_separation" / "stem_separation"
UPLOAD_ROOT = ROOT / "data" / "stem_separation_jobs"
try:
    from stem_separation.core.separator import STEM_NAMES
except ImportError:
    STEM_NAMES = ("drums", "bass", "vocals", "other")

MAX_SOURCE_BYTES = 150 * 1024 * 1024
MAX_DURATION_SECONDS = 600

_QUEUE_LOCK = threading.RLock()
_QUEUE_CONDITION = threading.Condition(_QUEUE_LOCK)
_WORKER_THREAD: threading.Thread | None = None
_WORKER_STOP = threading.Event()
_JOB_LEASE_SECONDS = 60.0
_MAX_JOB_HISTORY = 100
_DEFAULT_TIMEOUT_SECONDS = 900  # Demucs on CPU can take several minutes for a full-length track


def exists() -> bool:
    return STEM_SEP_ROOT.exists() and (STEM_SEP_ROOT / "main_separate.py").exists()


def python_cmd() -> list[str]:
    """Command prefix to invoke Python for stem-separation subprocess calls.

    Prefers the local isolated venv (studio/stem_separation/stem_separation/.venv)
    over the shared project venv -- the shared venv deliberately excludes torch
    (see that package's pyproject.toml). `arch -arm64` forces native arch the
    same way audiogen_bridge.python_cmd() does: this bridge can run under
    Rosetta even when the local venv's python is a universal2 binary, and a
    process already under Rosetta inherits x86_64 on exec unless forced.
    """
    local = STEM_SEP_ROOT / ".venv" / "bin" / "python"
    if local.exists():
        return ["arch", "-arm64", str(local)]
    return [sys.executable]


def status() -> dict:
    return {
        "ok": exists(),
        "root": str(STEM_SEP_ROOT),
        "has_local_venv": (STEM_SEP_ROOT / ".venv" / "bin" / "python").exists(),
        "stems": list(STEM_NAMES),
    }


def _run(cmd: list[str], *, timeout: int) -> dict:
    if not exists():
        return {"ok": False, "error": "stem_separation is not present."}
    try:
        completed = subprocess.run(
            cmd, cwd=STEM_SEP_ROOT, capture_output=True, text=True, timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Separation timed out after {timeout}s.", "command": " ".join(cmd)}
    return {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "command": " ".join(cmd),
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


def separate_command(
    input_path: str | Path,
    output_dir: str | Path,
    *,
    model: str = "htdemucs",
    timeout: int = _DEFAULT_TIMEOUT_SECONDS,
) -> dict:
    cmd = [
        *python_cmd(),
        str(STEM_SEP_ROOT / "main_separate.py"),
        "--input", str(input_path),
        "--output-dir", str(output_dir),
        "--model", model,
    ]
    result = _run(cmd, timeout=timeout)
    result["result"] = _last_json_line(result.get("stdout", ""))
    return result


_AUTOMIX_CHAIN_RE = re.compile(
    r"\bauto[\s-]?mix\b|\b(?:then|and)\s+(?:render|run|start)\s+(?:an?\s+)?(?:automix|auto[\s-]?mix|mix)\b|\bmix\s+pass\b|\bre-?bake\s+the\s+mix\b",
    re.I,
)


def requests_automix_chain(prompt: str) -> bool:
    """True if a stem-separation request also asks to chain straight into
    an AutoMix render once separation finishes (D3.3,
    docs/KENN_FUTURE_PLAN.md Phase 3) -- e.g. "separate this into stems,
    then automix it" or "...re-bake the mix". Mirrors
    audiogen_bridge.requests_automix_chain() (same phrasing family, kept
    as a separate local copy rather than a shared import -- these two
    bridges aren't otherwise coupled, and it's one small regex)."""
    return bool(_AUTOMIX_CHAIN_RE.search(prompt or ""))


def validate_upload(data: bytes, filename: str) -> None:
    """Raises ValueError with a user-facing message on any validation failure."""
    if len(data) > MAX_SOURCE_BYTES:
        raise ValueError(f"File exceeds the {MAX_SOURCE_BYTES // (1024 * 1024)} MB limit.")
    validate_media_upload(data, filename)
    duration = validate_audio_duration(data, max_seconds=MAX_DURATION_SECONDS)
    if duration is None:
        raise ValueError(f"{Path(filename).name!r} could not be decoded as audio.")


def _job_dir(job_id: str) -> Path:
    return UPLOAD_ROOT / job_id


def enqueue_separation(
    file_bytes: bytes,
    filename: str,
    *,
    project_id: str = "",
    model: str = "htdemucs",
    chain_to_automix: bool = False,
    genre: str = "",
    style_prefs: dict | None = None,
) -> dict:
    """Validate, store, and queue a stem-separation job. Returns
    ``{ok, job}`` (job is the public job dict) or ``{ok: False, error}``.

    D3.3 (docs/KENN_FUTURE_PLAN.md Phase 3): ``chain_to_automix`` mirrors
    audiogen_bridge.py's identical AudioGen->AutoMix chain flag -- when
    set, the worker loop below feeds this job's own completed stems
    straight into a real AutoMix job once Demucs finishes, via the exact
    same ``queue_automix_from_stem_files()`` D3.2 already built (that
    function is generic over any ``stem_paths`` dict, not AudioGen-
    specific, so this reuses it unmodified)."""
    if not exists():
        return {"ok": False, "error": "Stem separation is not set up on this server yet."}
    try:
        validate_upload(file_bytes, filename)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    with _QUEUE_CONDITION:
        job = stem_separation_job_store.create(
            source_filename=Path(filename).name,
            model=model,
            project_id=project_id,
            genre=genre,
            style_prefs=style_prefs,
            chain_to_automix=chain_to_automix,
        )
        job_dir = ensure_private_directory(_job_dir(job["id"]))
        source_path = write_private_file(job_dir / f"source{Path(filename).suffix.lower()}", file_bytes)
        stem_separation_job_store.set_source_path(job["id"], str(source_path))
        stem_separation_job_store.trim(_MAX_JOB_HISTORY)
        _QUEUE_CONDITION.notify()
    _ensure_worker()
    return {"ok": True, "job": stem_separation_job_store.get(job["id"])}


def job_status(job_id: str) -> dict | None:
    return stem_separation_job_store.get(job_id)


def job_stem_path(job_id: str, stem_name: str) -> Path | None:
    job = stem_separation_job_store.get(job_id)
    if not job or job.get("status") != "completed":
        return None
    stems = (job.get("result") or {}).get("stems") or {}
    path_str = stems.get(stem_name)
    if not path_str:
        return None
    path = Path(path_str)
    return path if path.exists() else None


def resolve_stem_files_for_project(project_id: str) -> list[tuple[bytes, str]] | None:
    """Read the actual stem WAV bytes from a project's most recent
    completed separation job (G3, docs/KENN_IMPROVEMENT_PLAN.md) -- the
    "stem set" `run_automix`'s tool handler needs (`files: list[tuple[
    bytes, str]]`), unlike `run_mix_review`/`run_stem_separation`'s
    single-file source. None if there's no completed job for this
    project, or its stem files are no longer on disk."""
    job = stem_separation_job_store.get_latest_completed_for_project(project_id)
    if not job:
        return None
    stems = (job.get("result") or {}).get("stems") or {}
    if not stems:
        return None
    files: list[tuple[bytes, str]] = []
    for name, path_str in stems.items():
        path = Path(path_str)
        if not path.exists():
            continue
        files.append((path.read_bytes(), f"{name}.wav"))
    return files or None


def job_zip_path(job_id: str) -> Path | None:
    """Build (and cache) a zip of all completed stems for a job."""
    job = stem_separation_job_store.get(job_id)
    if not job or job.get("status") != "completed":
        return None
    stems = (job.get("result") or {}).get("stems") or {}
    if not stems:
        return None
    zip_path = _job_dir(job_id) / "stems.zip"
    if zip_path.exists():
        return zip_path
    # ZIP_STORED, not ZIP_DEFLATED -- see audiogen_bridge.py's
    # queue_automix_from_stem_files() for why: a near-silent stem can
    # compress past archive_safety.py's zip-bomb ratio guard on read,
    # and WAV/PCM audio barely benefits from DEFLATE anyway.
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as zf:
        for name, path_str in stems.items():
            path = Path(path_str)
            if path.exists():
                zf.write(path, arcname=f"{name}.wav")
    return zip_path if zip_path.exists() else None


def _ensure_worker() -> None:
    global _WORKER_THREAD
    with _QUEUE_CONDITION:
        if _WORKER_THREAD is not None and _WORKER_THREAD.is_alive():
            return
        _WORKER_STOP.clear()
        _WORKER_THREAD = threading.Thread(
            target=_separation_worker_loop, name="stem-separation-worker", daemon=True,
        )
        _WORKER_THREAD.start()


def stop_worker(timeout: float = 5.0) -> None:
    global _WORKER_THREAD
    with _QUEUE_CONDITION:
        _WORKER_STOP.set()
        _QUEUE_CONDITION.notify_all()
        worker = _WORKER_THREAD
    if worker is not None:
        worker.join(timeout=max(0.0, timeout))
    if worker is None or not worker.is_alive():
        _WORKER_THREAD = None


def _chain_to_automix(job: dict) -> None:
    """D3.3: feed a just-completed separation job's own stems into a real
    AutoMix job. Best-effort -- a chain failure must never make the
    separation job itself look failed (the separation genuinely
    succeeded; only the follow-on chain didn't), so this only logs via
    the job's own automix_job_id field, left blank on failure."""
    finished = stem_separation_job_store.get(job["id"])
    if not finished:
        return
    stems = (finished.get("result") or {}).get("stems") or {}
    if not stems:
        return
    try:
        import audiogen_bridge

        result = audiogen_bridge.queue_automix_from_stem_files(
            project_id=finished.get("project_id", ""),
            genre=finished.get("genre") or "pop",
            style_prefs=finished.get("style_prefs") or {},
            stem_paths=stems,
        )
        if result.get("ok"):
            stem_separation_job_store.set_automix_job_id(job["id"], result.get("job_id", ""))
    except Exception:  # pragma: no cover - defensive worker boundary
        pass


def _separation_worker_loop() -> None:
    worker_id = f"stem-sep-{uuid.uuid4().hex[:12]}"
    while not _WORKER_STOP.is_set():
        with _QUEUE_CONDITION:
            stem_separation_job_store.recover_expired()
            job = stem_separation_job_store.claim_next(worker_id, lease_seconds=_JOB_LEASE_SECONDS)
            while job is None and not _WORKER_STOP.is_set():
                _QUEUE_CONDITION.wait(timeout=2.0)
                if _WORKER_STOP.is_set():
                    return
                stem_separation_job_store.recover_expired()
                job = stem_separation_job_store.claim_next(worker_id, lease_seconds=_JOB_LEASE_SECONDS)
            if job is None:
                return

        heartbeat_stop = threading.Event()

        def maintain_lease() -> None:
            while not heartbeat_stop.wait(_JOB_LEASE_SECONDS / 3):
                if not stem_separation_job_store.heartbeat(job["id"], worker_id, lease_seconds=_JOB_LEASE_SECONDS):
                    return

        heartbeat_thread = threading.Thread(
            target=maintain_lease, name=f"stem-sep-heartbeat-{job['id']}", daemon=True,
        )
        heartbeat_thread.start()

        try:
            job_dir = _job_dir(job["id"])
            output_dir = job_dir / "stems"
            started = time.monotonic()
            result = separate_command(job["source_path"], output_dir, model=job.get("model") or "htdemucs")
            payload = result.get("result") or {}
            if not result.get("ok") or not payload.get("ok"):
                outcome = {
                    "status": "failed",
                    "error": payload.get("error") or result.get("stderr") or result.get("error") or "Separation failed.",
                }
            else:
                outcome = {
                    "status": "completed",
                    "result": {"stems": payload.get("stems", {}), "model": payload.get("model", "htdemucs")},
                }
        except Exception as exc:  # pragma: no cover - defensive worker boundary
            outcome = {"status": "failed", "error": str(exc)}
        finally:
            heartbeat_stop.set()
            heartbeat_thread.join(timeout=1.0)

        with _QUEUE_CONDITION:
            if outcome["status"] == "completed":
                stem_separation_job_store.finish(
                    job["id"], worker_id, status="completed",
                    message="Separation complete.", result=outcome["result"],
                )
            else:
                stem_separation_job_store.finish(
                    job["id"], worker_id, status="failed",
                    message="Separation failed.", error=outcome["error"],
                )
            stem_separation_job_store.trim(_MAX_JOB_HISTORY)
            _QUEUE_CONDITION.notify_all()

        if outcome["status"] == "completed" and job.get("chain_to_automix"):
            _chain_to_automix(job)
