#!/usr/bin/env python3
"""Aggregate privacy-safe supervised-pilot logs for Beta+ qualification."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "kenn.supervised_pilot_evaluation.v1"
LOG_SCHEMA = "kenn.supervised_pilot_session.v1"
DEFAULT_MATRIX = REPO_ROOT / "docs" / "ABLETON_LIVE_SUPPORT_MATRIX.json"
SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}")
COMMIT_RE = re.compile(r"[0-9a-f]{40}")
PREFLIGHT_FIELDS = (
    "disposable_set_confirmed", "auto_mode_disabled", "no_unsaved_production_work",
    "supported_configuration_confirmed", "undo_visible_before_mutation", "diagnostics_privacy_checked",
)
SAFETY_FIELDS = ("unauthorized_mutations", "false_success_receipts", "lost_undos", "companion_crashes", "unrecoverable_states")
MAX_RECEIPT_EVIDENCE_BYTES = 5 * 1024 * 1024
MAX_RECEIPT_UNCOMPRESSED_BYTES = 5 * 1024 * 1024


class PilotEvidenceError(ValueError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PilotEvidenceError(f"{path.name}: unreadable JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise PilotEvidenceError(f"{path.name}: root must be an object")
    return value


def _head() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise PilotEvidenceError("could not resolve candidate Git revision") from exc


def _release_bucket(namespace: str, value: str, revision: str) -> str:
    """Create an opaque grouping commitment scoped to one release revision."""
    material = f"{revision}\0{namespace}\0{value}".encode("utf-8")
    return "sha256:" + hashlib.sha256(material).hexdigest()


def _receipt_evidence(
    log_path: Path, log: dict[str, Any], minimum_events: int,
) -> tuple[str, str, set[str]]:
    filename = str(log.get("receipt_evidence_file") or "").strip()
    declared = str(log.get("receipt_evidence_sha256") or "").lower()
    if not filename or Path(filename).name != filename or not filename.endswith(".zip"):
        raise PilotEvidenceError("receipt evidence must be a sibling ZIP filename")
    if not SHA256_RE.fullmatch(declared):
        raise PilotEvidenceError("receipt evidence requires a sha256-prefixed digest")
    path = log_path.parent / filename
    try:
        payload = path.read_bytes()
        if len(payload) > MAX_RECEIPT_EVIDENCE_BYTES:
            raise PilotEvidenceError("receipt evidence exceeds the size limit")
        actual = "sha256:" + hashlib.sha256(payload).hexdigest()
        if actual != declared:
            raise PilotEvidenceError("receipt evidence SHA-256 mismatch")
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            names = [member.filename for member in members]
            expected_names = {"manifest.json", "diagnostics.json", "lifecycle-events.json"}
            if len(names) != len(expected_names) or set(names) != expected_names:
                raise PilotEvidenceError("receipt evidence has an unexpected file set")
            if any(member.flag_bits & 0x1 for member in members):
                raise PilotEvidenceError("receipt evidence must not contain encrypted members")
            if sum(member.file_size for member in members) > MAX_RECEIPT_UNCOMPRESSED_BYTES:
                raise PilotEvidenceError("receipt evidence uncompressed content exceeds the size limit")
            manifest = json.loads(archive.read("manifest.json"))
            diagnostics_bytes = archive.read("diagnostics.json")
            events_bytes = archive.read("lifecycle-events.json")
            events_document = json.loads(events_bytes)
        if not isinstance(manifest, dict) or not isinstance(events_document, dict):
            raise PilotEvidenceError("receipt evidence JSON roots must be objects")
        events = events_document.get("events")
        if manifest.get("schema") != "kenn.support_bundle.v1":
            raise PilotEvidenceError("receipt evidence has an unexpected manifest schema")
        if str(manifest.get("source_revision") or "").lower() != str(log.get("source_git_commit") or "").lower():
            raise PilotEvidenceError("receipt evidence source revision does not match the session log")
        manifest_files = manifest.get("files") if isinstance(manifest.get("files"), dict) else {}
        bundled_files = {"diagnostics.json": diagnostics_bytes, "lifecycle-events.json": events_bytes}
        if set(manifest_files) != set(bundled_files) or any(
            manifest_files.get(name) != hashlib.sha256(content).hexdigest()
            for name, content in bundled_files.items()
        ):
            raise PilotEvidenceError("receipt evidence manifest integrity hashes do not match")
        if not isinstance(events, list) or len(events) < minimum_events:
            raise PilotEvidenceError("receipt evidence does not contain enough lifecycle events")
        verified_receipt_ids = [
            str(event.get("receipt_id") or "").strip()
            for event in events if isinstance(event, dict) and event.get("verified") is True
        ]
        if (
            len(verified_receipt_ids) < minimum_events
            or any(not receipt_id for receipt_id in verified_receipt_ids)
            or len(set(verified_receipt_ids)) != len(verified_receipt_ids)
        ):
            raise PilotEvidenceError(
                "receipt evidence does not contain enough uniquely identified verified events"
            )
    except (OSError, zipfile.BadZipFile, KeyError, json.JSONDecodeError, AttributeError) as exc:
        raise PilotEvidenceError(f"receipt evidence is unreadable: {exc}") from exc
    return actual, hashlib.sha256(events_bytes).hexdigest(), set(verified_receipt_ids)


def evaluate(log_paths: list[Path], *, matrix_path: Path = DEFAULT_MATRIX, source_revision: str | None = None) -> dict[str, Any]:
    revision = str(source_revision or _head()).lower()
    if not COMMIT_RE.fullmatch(revision):
        raise PilotEvidenceError("source revision must be a full 40-character Git commit")
    matrix = _load(matrix_path)
    supported = {str(row.get("id")) for row in matrix.get("supported_configurations", []) if isinstance(row, dict) and row.get("status") == "qualified"}
    if not supported:
        raise PilotEvidenceError("support matrix has no qualified configuration")
    rows = []
    seen_runs: set[str] = set()
    projects: set[str] = set()
    seen_receipts: set[str] = set()
    seen_event_receipts: set[str] = set()
    testers: set[str] = set()
    for path in log_paths:
        log = _load(path)
        run_id = str(log.get("run_id") or "").strip()
        project_id = str(log.get("project_id_sha256") or "").lower()
        tester_id = str(log.get("tester_id_sha256") or "").lower()
        preflight = log.get("preflight") if isinstance(log.get("preflight"), dict) else {}
        operations = log.get("operations") if isinstance(log.get("operations"), dict) else {}
        safety = log.get("safety") if isinstance(log.get("safety"), dict) else {}
        reasons = []
        receipt_bucket = ""
        if log.get("schema") != LOG_SCHEMA: reasons.append("schema")
        if not run_id or run_id in seen_runs: reasons.append("unique_run_id")
        if not SHA256_RE.fullmatch(project_id): reasons.append("project_hash")
        if not SHA256_RE.fullmatch(tester_id): reasons.append("tester_hash")
        if str(log.get("source_git_commit") or "").lower() != revision: reasons.append("source_revision")
        if str(log.get("support_configuration_id") or "") not in supported: reasons.append("support_configuration")
        try:
            started_at = datetime.fromisoformat(str(log.get("started_at") or ""))
            if started_at.tzinfo is None or started_at > datetime.now(timezone.utc): reasons.append("started_at")
        except ValueError:
            reasons.append("started_at")
        if any(preflight.get(field) is not True for field in PREFLIGHT_FIELDS): reasons.append("preflight")
        try:
            request_count = int(operations.get("request_count", -1)); mutation_count = int(operations.get("mutation_count", -1))
            readbacks = int(operations.get("readback_verified_count", -1)); undo_required = int(operations.get("undo_required_count", -1)); undo_verified = int(operations.get("undo_verified_count", -1))
            if min(request_count, mutation_count, readbacks, undo_required, undo_verified) < 1 or mutation_count > request_count or undo_required > mutation_count or readbacks != mutation_count or undo_verified != undo_required:
                reasons.append("operation_accounting")
            try:
                _archive_digest, event_digest, event_receipt_ids = _receipt_evidence(
                    path, log, mutation_count + undo_required,
                )
                if event_digest in seen_receipts or seen_event_receipts & event_receipt_ids:
                    reasons.append("unique_receipt_evidence")
                seen_receipts.add(event_digest)
                seen_event_receipts.update(event_receipt_ids)
                receipt_bucket = _release_bucket("receipt", event_digest, revision)
            except PilotEvidenceError:
                reasons.append("receipt_evidence")
            if any(int(safety.get(field, -1)) != 0 for field in SAFETY_FIELDS): reasons.append("safety_incident")
        except (TypeError, ValueError):
            reasons.append("numeric_fields")
        if log.get("session_result") != "pass" or log.get("tester_signoff") is not True: reasons.append("signoff")
        seen_runs.add(run_id); projects.add(project_id); testers.add(tester_id)
        rows.append({
            "run_id": run_id[:128],
            "project_bucket": _release_bucket("project", project_id, revision),
            "tester_bucket": _release_bucket("tester", tester_id, revision),
            "receipt_bucket": receipt_bucket,
            "passed": not reasons, "failures": sorted(set(reasons)),
        })
    metrics = {"session_count": len(rows), "passed_session_count": sum(row["passed"] for row in rows),
               "project_count": len(projects), "tester_count": len(testers),
               "bound_receipt_count": len(seen_receipts)}
    thresholds = {"minimum_sessions": metrics["session_count"] >= 10, "minimum_projects": metrics["project_count"] >= 3,
                  "receipt_evidence_bound": metrics["bound_receipt_count"] == metrics["session_count"],
                  "all_sessions_pass": metrics["passed_session_count"] == metrics["session_count"] and bool(rows)}
    return {"schema": SCHEMA, "generated_at": datetime.now(timezone.utc).isoformat(), "source_git_commit": revision,
            "evaluator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "support_matrix_sha256": hashlib.sha256(matrix_path.read_bytes()).hexdigest(), "metrics": metrics,
            "thresholds": thresholds, "qualified": all(thresholds.values()), "rows": rows,
            "privacy": {"stores_project_names": False, "stores_project_paths": False,
                        "stores_raw_project_hashes": False, "stores_tester_identities": False,
                        "stores_raw_tester_hashes": False, "release_scoped_buckets": True,
                        "stores_evidence_paths": False, "stores_prompts": False, "stores_audio": False},
            "limitations": ["This receipt qualifies only the exact candidate revision and declared support matrix."]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", action="append", type=Path, required=True)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--source-revision")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = evaluate([path.expanduser().resolve() for path in args.log], matrix_path=args.matrix.expanduser().resolve(), source_revision=args.source_revision)
    except PilotEvidenceError as exc:
        print(f"ERROR: {exc}")
        return 2
    target = args.output.expanduser().resolve(); target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["qualified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
