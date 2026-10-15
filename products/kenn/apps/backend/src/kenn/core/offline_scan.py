"""Own one confirmed arrangement export through analysis and temporary-audio disposal.

The caller must use LiveActionService to authorize the export and supply a current
source fingerprint. This module neither discovers a bounce nor controls Live. Its
exporter is injected so an unqualified macOS helper cannot become a default path.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import fcntl
from io import BytesIO
import json
import os
from pathlib import Path
import re
import stat
import struct
import tempfile
from threading import Event, Lock, Thread
import time
from typing import Any, Callable
import unicodedata
import uuid
import wave

from .local_mix_review_service import LocalMixReviewService, MAX_UPLOAD_BYTES


MAX_JOBS = 64  # Metadata and unresolved writer leases share this hard job limit.
MAX_METADATA_BYTES = 2 * 1024 * 1024  # 2 MiB per receipt, never WAV payloads.
MAX_DURATION_SECONDS = 8 * 60  # 8 minutes of stereo 24-bit/48 kHz fits the 150 MiB upload cap.
WAV_NAME = "kenn-analysis.wav"
_JOB_ID = re.compile(r"scan-[0-9a-f]{32}\Z")
_TERMINAL = {"completed", "cancelled", "failed", "stale"}


class _ScanStopped(Exception):
    def __init__(self, state: str, message: str):
        super().__init__(message)
        self.state = state


class _ScanReviews(LocalMixReviewService):
    # This index is private to scan jobs and has the same 64-record retention
    # bound, including analyses that finish after cancellation was requested.
    MAX_REVIEWS = MAX_JOBS


def _identity(info: os.stat_result) -> dict[str, int]:
    return {"device": info.st_dev, "inode": info.st_ino, "size": info.st_size, "mtime_ns": info.st_mtime_ns}


class OfflineScanService:
    """Start at most one export; expose owner-bound status/cancel and private metadata.

    ``exporter(request, cancel_event)`` must return a closed-writer receipt, not
    merely report that its helper exited. ``read_source_fingerprint()`` must cover
    the relevant current set state. Callers must keep this candidate disabled
    until the real export mechanism and source identity are qualified.
    """

    def __init__(
        self,
        runtime_dir: Path | str,
        *,
        exporter: Callable[[dict[str, Any], Event], dict[str, Any]],
        read_source_fingerprint: Callable[[], str],
        reviewer: Any = None,
    ):
        configured = Path(runtime_dir).expanduser().absolute()
        if configured.is_symlink():
            raise ValueError("Offline scan runtime must not be a symlink.")
        configured.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.runtime_dir = configured.resolve()
        os.chmod(self.runtime_dir, 0o700)
        self._exporter = exporter
        self._read_source_fingerprint = read_source_fingerprint
        # This private index is separate from the HTTP Mix Review singleton: a
        # cancelled late analysis must never appear through its global review ID.
        self._reviewer = reviewer or _ScanReviews(self.runtime_dir / "review-metadata")
        self._guard = Lock()
        self._events: dict[str, Event] = {}

    @staticmethod
    def _confirmed_request(source: dict[str, Any], supplied: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(source, dict) or source.get("source_kind") != "arrangement_main":
            raise ValueError("Offline scan requires the current arrangement Main source.")
        if source.get("range_confirmed") is not True or source.get("tail_policy") != "within_range":
            raise ValueError("Confirm the arrangement range and within_range tail policy first.")
        fingerprint = source.get("fingerprint")
        if not isinstance(fingerprint, str) or not 1 <= len(fingerprint) <= 256:
            raise ValueError("Offline scan requires a bounded current source fingerprint.")
        allowed = {"schema", "action", "live_pid", "expected_window_title", "render_start", "render_length", "sample_rate", "timeout_seconds"}
        if not isinstance(supplied, dict) or set(supplied) - allowed:
            raise ValueError("The scan service owns its output path and fixed export format.")
        request = dict(supplied)
        if request.get("schema", "kenn.live_export_request.v1") != "kenn.live_export_request.v1" or request.get("action", "export") != "export":
            raise ValueError("Unsupported Live export request.")
        if type(request.get("live_pid")) is not int or not 0 < request["live_pid"] <= 2_147_483_647:
            raise ValueError("A specific Live process is required.")
        title = request.get("expected_window_title")
        # Foundation controlCharacters includes C1 and invisible format controls;
        # accepting them here would authorize a title the native helper rejects.
        if not isinstance(title, str) or not 1 <= len(title.encode("utf-8")) <= 512 or any(unicodedata.category(char) in {"Cc", "Cf"} for char in title):
            raise ValueError("A specific Live window title is required.")
        for key in ("render_start", "render_length"):
            value = request.get(key)
            # Live's musical-time strings are retained exactly; interpreting a
            # range from old file duration would silently scan a different mix.
            if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,6}\.[0-9]{1,2}\.[0-9]{1,2}", value):
                raise ValueError("Confirm exact Live render start and length strings.")
        if int(request["render_start"].split(".")[0]) == 0 or not any(int(part) for part in request["render_length"].split(".")):
            raise ValueError("The confirmed arrangement range must have a positive start and length.")
        if type(request.get("sample_rate")) is not int or request["sample_rate"] != 48000:
            raise ValueError("The scan candidate requires 48000 Hz stereo 24-bit PCM.")
        timeout = request.get("timeout_seconds")
        if type(timeout) is not int or not 1 <= timeout <= 600:
            raise ValueError("Export timeout must be an integer from 1 to 600 seconds.")
        request.update(schema="kenn.live_export_request.v1", action="export")
        return request

    def _lease(self):
        # flock also excludes another service instance or process and protects
        # recovery from deleting a writer that this process still owns.
        descriptor = os.open(self.runtime_dir / ".scan.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(descriptor)
            raise RuntimeError("Another offline scan or recovery is active.") from None
        return descriptor

    @contextmanager
    def _metadata_lock(self):
        # Export/analysis holds .scan.lock, but status and cancellation must stay
        # available. This separate short lock makes final publication and cancel
        # one ordered decision across backend instances and processes.
        descriptor = os.open(self.runtime_dir / ".metadata.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
                raise ValueError("Offline scan metadata lock ownership is invalid.")
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            os.close(descriptor)

    def validate_current(self, source: dict[str, Any], export_request: dict[str, Any]) -> dict[str, Any]:
        """Validate a confirmation preview without creating files or controlling Live."""
        request = self._confirmed_request(source, export_request)
        confirmed = {key: source[key] for key in ("source_kind", "fingerprint", "range_confirmed", "tail_policy")}
        try:
            self._current({"source": confirmed}, Event())
        except _ScanStopped as exc:
            # A preview for an old source must not become a confirmable proposal.
            raise ValueError(str(exc)) from None
        return {"source": confirmed, "export_request": request}

    def _job_dir(self, job_id: str) -> Path:
        if not isinstance(job_id, str) or not _JOB_ID.fullmatch(job_id):
            raise ValueError("Offline scan was not found.")
        return self.runtime_dir / job_id

    def _read_json(self, path: Path) -> dict[str, Any]:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor, "rb") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid() or info.st_size > MAX_METADATA_BYTES:
                raise ValueError("Offline scan metadata ownership is invalid.")
            value = json.load(handle)
        if not isinstance(value, dict):
            raise ValueError("Offline scan metadata is invalid.")
        return value

    def _check_directory(self, manifest: dict[str, Any]) -> Path:
        directory = self._job_dir(manifest["job_id"])
        info = directory.lstat()
        expected = manifest["directory_identity"]
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or (info.st_dev, info.st_ino) != (expected["device"], expected["inode"]):
            raise ValueError("Offline scan directory ownership changed.")
        return directory

    def _persist(self, manifest: dict[str, Any], receipt: dict[str, Any]) -> None:
        directory = self._check_directory(manifest)
        for name, value in (("manifest.json", manifest), ("receipt.json", receipt)):
            payload = json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")
            if len(payload) > MAX_METADATA_BYTES:
                raise ValueError("Offline scan metadata exceeds its 2 MiB limit.")
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=directory, prefix=".scan-", delete=False) as handle:
                    temporary = Path(handle.name)
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, directory / name)
            finally:
                if temporary is not None:
                    # Only this call's freshly created temporary file is ours.
                    temporary.unlink(missing_ok=True)

    def _load(self, job_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        directory = self._job_dir(job_id)
        if directory.is_symlink():
            raise ValueError("Offline scan directory ownership changed.")
        manifest = self._read_json(directory / "manifest.json")
        if manifest.get("schema") != "kenn.offline_scan_manifest.v1" or manifest.get("job_id") != job_id:
            raise ValueError("Offline scan manifest is invalid.")
        self._check_directory(manifest)
        receipt = self._read_json(directory / "receipt.json")
        if receipt.get("job_id") != job_id or receipt.get("owner_id") != manifest.get("owner_id"):
            raise ValueError("Offline scan receipt ownership changed.")
        return manifest, receipt

    def _prune(self) -> None:
        records = []
        for directory in self.runtime_dir.glob("scan-*"):
            try:
                manifest, receipt = self._load(directory.name)
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                # An incomplete manifest may be a crashed active export, so a
                # new dialog cannot be launched until it is inspected.
                raise RuntimeError("Unrecognized offline scan ownership requires inspection before another export.") from None
            if receipt["state"] not in _TERMINAL or receipt.get("audio_deleted") is not True:
                raise RuntimeError("An unresolved offline scan requires recovery before another export.")
            records.append((receipt["created_at"], manifest, receipt))
        while len(records) >= MAX_JOBS:
            eligible = sorted((record for record in records if record[2] and record[2]["state"] in _TERMINAL and record[2].get("audio_deleted") is True), key=lambda record: record[0])
            if not eligible:
                raise RuntimeError("Offline scan storage is full; unresolved exports require recovery.")
            record = eligible[0]
            directory = self._check_directory(record[1])
            # An unexpected file makes this directory ineligible, even if its
            # receipt looks old; imported files must not be swept up by pruning.
            if {path.name for path in directory.iterdir()} - {"manifest.json", "receipt.json", "cancel.requested"}:
                records[records.index(record)] = (float("inf"), None, None)
                continue
            for path in directory.iterdir():
                self._unlink_regular(path)
            directory.rmdir()
            records.remove(record)

    def start(self, owner_id: str, source: dict[str, Any], export_request: dict[str, Any]) -> dict[str, Any]:
        """Accept a confirmed export and return immediately; authorization belongs to the caller."""
        if not isinstance(owner_id, str) or not 1 <= len(owner_id) <= 256:
            raise ValueError("A bounded conversation owner is required.")
        preview = self.validate_current(source, export_request)
        request, source = preview["export_request"], preview["source"]
        with self._guard:
            lease = self._lease()
            try:
                with self._metadata_lock():
                    self._prune()
                    job_id = f"scan-{uuid.uuid4().hex}"
                    directory = self._job_dir(job_id)
                    directory.mkdir(mode=0o700)
                    request["output_path"] = str(directory / WAV_NAME)
                    manifest = {"schema": "kenn.offline_scan_manifest.v1", "job_id": job_id, "owner_id": owner_id, "directory_identity": _identity(directory.stat()), "writer_closed": False, "request": request}
                    receipt = {"ok": True, "schema": "kenn.offline_scan.v1", "job_id": job_id, "owner_id": owner_id, "state": "exporting", "created_at": time.time(), "source": source, "export_request": request, "audio_deleted": False, "limitations": ["Producer-confirmed arrangement Main range; effect tails are included only within that range.", "Experimental export candidate; automatic full-track scanning remains unqualified."]}
                    self._persist(manifest, receipt)
                    event = Event()
                    self._events[job_id] = event
                    worker = Thread(target=self._run, args=(manifest, receipt, event, lease), name=f"kenn-{job_id}", daemon=True)
                    try:
                        worker.start()
                    except Exception:
                        # Thread startup failed before the exporter could run;
                        # no stale event or unproven Live writer lease is left.
                        self._events.pop(job_id, None)
                        manifest["writer_closed"] = True
                        self._cleanup(manifest)
                        receipt.update(state="failed", error="Offline scan worker could not start.", audio_deleted=True, finished_at=time.time())
                        self._persist(manifest, receipt)
                        raise
                    return deepcopy(receipt)
            except BaseException:
                os.close(lease)
                raise

    def _current(self, receipt: dict[str, Any], event: Event) -> None:
        marker = self._job_dir(receipt["job_id"]) / "cancel.requested" if "job_id" in receipt else None
        if event.is_set() or (marker is not None and marker.exists()):
            raise _ScanStopped("cancelled", "Offline scan was cancelled; late results were discarded.")
        try:
            fingerprint = self._read_source_fingerprint()
        except Exception:
            # An unavailable readback cannot establish that the rendered source
            # still represents the current set, so no fresh result is published.
            raise _ScanStopped("stale", "Current source identity could not be verified.") from None
        if fingerprint != receipt["source"]["fingerprint"]:
            raise _ScanStopped("stale", "The source changed; scan the confirmed range again.")

    @staticmethod
    def _matching_export(result: dict[str, Any], request: dict[str, Any]) -> bool:
        return isinstance(result, dict) and result.get("schema") == "kenn.live_export_receipt.v1" and all(result.get(key) == request[key] for key in ("output_path", "render_start", "render_length", "sample_rate", "live_pid")) and result.get("channels") == 2

    def _wav_bytes(self, manifest: dict[str, Any]) -> bytes:
        directory = self._check_directory(manifest)
        descriptor = os.open(directory / WAV_NAME, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor, "rb") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid():
                raise ValueError("Export WAV must be a private, singly linked regular file.")
            if not 44 <= info.st_size <= MAX_UPLOAD_BYTES:
                raise ValueError("Export WAV is empty or exceeds the 150 MiB limit.")
            payload = handle.read(MAX_UPLOAD_BYTES + 1)
            if _identity(os.fstat(handle.fileno())) != _identity(info):
                raise ValueError("Export WAV changed after closed-writer completion.")
        if payload[:4] != b"RIFF" or payload[8:12] != b"WAVE" or struct.unpack_from("<I", payload, 4)[0] + 8 != len(payload):
            raise ValueError("Export is not a complete RIFF WAV.")
        with wave.open(BytesIO(payload), "rb") as audio:
            if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate(), audio.getcomptype()) != (2, 3, 48000, "NONE"):
                raise ValueError("Export WAV must be stereo 24-bit PCM at 48000 Hz.")
            frames = audio.getnframes()
            if not 0 < frames <= MAX_DURATION_SECONDS * 48000:
                raise ValueError("Export WAV exceeds the 8 minute duration limit or is empty.")
            if len(audio.readframes(frames)) != frames * 6:
                raise ValueError("Export WAV data is truncated.")
        manifest["audio_identity"] = _identity(info)
        return payload

    @staticmethod
    def _unlink_regular(path: Path, expected: dict[str, int] | None = None) -> bool:
        try:
            info = path.lstat()
        except FileNotFoundError:
            # A missing generated file already satisfies disposal, but an open
            # Live writer is handled separately and never reaches this branch.
            return False
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid() or (expected is not None and _identity(info) != expected):
            raise ValueError("Generated file ownership changed; cleanup was refused.")
        path.unlink()
        return True

    def _cleanup(self, manifest: dict[str, Any]) -> bool:
        if manifest["writer_closed"] is not True:
            raise ValueError("Live writer closure is unproven; audio cleanup remains pending.")
        directory = self._check_directory(manifest)
        self._unlink_regular(directory / WAV_NAME, manifest.get("audio_identity"))
        return self._unlink_regular(directory / "cancel.requested")

    def _run(self, manifest: dict[str, Any], receipt: dict[str, Any], event: Event, lease: int) -> None:
        review = None
        state, error = "completed", ""
        try:
            self._current(receipt, event)
            result = self._exporter(deepcopy(manifest["request"]), event)
            matching = self._matching_export(result, manifest["request"])
            manifest["writer_closed"] = matching and result.get("writer_closed") is True
            if not matching or result.get("status") != "completed" or not manifest["writer_closed"]:
                raise ValueError("Exporter did not prove completed, closed audio for this exact job.")
            self._current(receipt, event)
            payload = self._wav_bytes(manifest)
            with self._guard:
                with self._metadata_lock():
                    receipt["state"] = "analyzing"
                    self._persist(manifest, receipt)
            result = self._reviewer.save_review(payload, WAV_NAME)
            self._current(receipt, event)
            if not isinstance(result, dict) or result.get("ok") is not True or not isinstance(result.get("review"), dict) or result["review"].get("status") != "completed":
                raise ValueError("The existing Mix Review analyzer did not complete.")
            review = deepcopy(result["review"])
            if len(json.dumps(review).encode("utf-8")) > MAX_METADATA_BYTES // 2:
                # Reserve half the 2 MiB receipt for provenance and failures;
                # an oversized report cannot strand a worker in analyzing.
                raise ValueError("Mix Review metadata exceeds the 1 MiB report limit.")
        except _ScanStopped as exc:
            state, error = exc.state, str(exc)
            # Before export starts there is no writer to wait for. Once a helper
            # has been called, only its matching receipt or recovery proves this.
            if "result" not in locals():
                manifest["writer_closed"] = True
        except Exception as exc:
            # Failed exports are explicit: no first-bounce or simulated fallback.
            state, error = "failed", f"{type(exc).__name__}: {exc}"[:512]
        finally:
            with self._guard:
                try:
                    with self._metadata_lock():
                        try:
                            if self._cleanup(manifest):
                                # Keep a cross-backend cancellation after its
                                # marker is disposed with the generated WAV.
                                event.set()
                            receipt["audio_deleted"] = True
                        except (OSError, ValueError) as exc:
                            # Keep a possibly open/foreign file; publication
                            # waits for recovery to prove audio disposal.
                            receipt["cleanup_error"] = str(exc)[:512]
                            receipt["intended_state"] = state
                            state, review = "cleanup_pending", None
                        if event.is_set() and state == "completed":
                            state, review, error = "cancelled", None, "Offline scan was cancelled; late results were discarded."
                        if state == "completed":
                            try:
                                self._current(receipt, event)
                            except _ScanStopped as exc:
                                # Disposal can outlast analyzer readback, so
                                # commit rechecks the source under this lock.
                                state, review, error = exc.state, None, str(exc)
                        receipt.update(state=state, error=error, finished_at=time.time())
                        if state == "completed":
                            receipt["review"] = review
                        self._persist(manifest, receipt)
                finally:
                    self._events.pop(manifest["job_id"], None)
                    os.close(lease)

    def status(self, owner_id: str, job_id: str) -> dict[str, Any]:
        """Return only this owner's receipt, retaining historical evidence when stale."""
        with self._guard, self._metadata_lock():
            try:
                manifest, receipt = self._load(job_id)
                if manifest["owner_id"] != owner_id:
                    raise ValueError("Owner mismatch.")
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                # Missing, invalid and foreign jobs share a response, so status
                # does not reveal whether another conversation owns a job ID.
                return {"ok": False, "error": "Offline scan was not found."}
            if receipt["state"] == "completed":
                try:
                    self._current(receipt, Event())
                except _ScanStopped as exc:
                    receipt.update(state=exc.state, error=str(exc))
                    if exc.state == "cancelled":
                        # A cancellation marker is never a historical-source
                        # change and must not retain a late published report.
                        receipt.pop("review", None)
                    self._persist(manifest, receipt)
            if receipt["state"] not in _TERMINAL and (self._check_directory(manifest) / "cancel.requested").exists():
                receipt["cancel_requested"] = True
            return deepcopy(receipt)

    def cancel(self, owner_id: str, job_id: str) -> dict[str, Any]:
        """Request this owner's cancellation; writer closure is still required for disposal."""
        with self._guard, self._metadata_lock():
            try:
                manifest, receipt = self._load(job_id)
                if manifest["owner_id"] != owner_id:
                    raise ValueError("Owner mismatch.")
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                # Foreign cancellation must not disclose or touch another job.
                return {"ok": False, "error": "Offline scan was not found."}
            if receipt["state"] not in _TERMINAL:
                directory = self._check_directory(manifest)
                try:
                    descriptor = os.open(directory / "cancel.requested", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                except FileExistsError:
                    # Repeated cancellation is idempotent and does not rewrite a
                    # marker that the exporter may already be reading.
                    pass
                else:
                    os.close(descriptor)
                event = self._events.get(job_id)
                if event is not None:
                    event.set()
                receipt["cancel_requested"] = True
                # The marker also reaches a writer owned by another backend
                # instance. Do not overwrite its receipt with our stale copy.
            return deepcopy(receipt)

    def recover_abandoned(self, *, writer_is_absent: Callable[[dict[str, Any]], bool]) -> list[dict[str, Any]]:
        """Dispose abandoned owned WAVs only after closed receipt or proven writer absence.

        The supplied readback must prove Live cannot still write the target. A
        crashed helper process alone is insufficient. The runtime lease excludes
        active service workers, including workers in another backend process.
        """
        recovered = []
        with self._guard, self._metadata_lock():
            lease = self._lease()
            try:
                for directory in self.runtime_dir.glob("scan-*"):
                    try:
                        manifest, receipt = self._load(directory.name)
                        if receipt["state"] in _TERMINAL and receipt.get("audio_deleted") is True:
                            continue
                        if not manifest["writer_closed"] and writer_is_absent(deepcopy(manifest["request"])) is not True:
                            continue
                        manifest["writer_closed"] = True
                        self._cleanup(manifest)
                        # An interrupted analyzer cannot publish a result that
                        # bypassed the final source/cancellation checks.
                        receipt.update(state="cancelled", error="Interrupted scan audio was disposed after writer absence was verified.", audio_deleted=True, finished_at=time.time())
                        receipt.pop("review", None)
                        self._persist(manifest, receipt)
                        self._events.pop(manifest["job_id"], None)
                        recovered.append(deepcopy(receipt))
                    except (OSError, ValueError, KeyError, json.JSONDecodeError):
                        # Unknown or changed ownership remains untouched for
                        # manual inspection, never recursive directory deletion.
                        continue
            finally:
                os.close(lease)
        return recovered
