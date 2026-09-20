from __future__ import annotations

import importlib.util
import json
import hashlib
import zipfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[5] / "tooling" / "scripts" / "evaluate_supervised_pilot.py"
module = importlib.util.module_from_spec(spec := importlib.util.spec_from_file_location("pilot_eval", SCRIPT))
assert spec.loader
spec.loader.exec_module(module)


def _inputs(tmp_path: Path, *, unsafe: bool = False) -> tuple[list[Path], Path, str]:
    revision = "a" * 40
    matrix = tmp_path / "matrix.json"
    matrix.write_text(json.dumps({"supported_configurations": [{"id": "supported", "status": "qualified"}]}))
    paths = []
    for index in range(10):
        evidence = tmp_path / f"run-{index}-support.zip"
        events = json.dumps({"events": [
            {"receipt_id": f"r-{index}-{event}", "verified": True}
            for event in range(4)
        ]}).encode()
        diagnostics = b"{}"
        manifest = {"schema": "kenn.support_bundle.v1", "source_revision": revision, "files": {
            "diagnostics.json": hashlib.sha256(diagnostics).hexdigest(),
            "lifecycle-events.json": hashlib.sha256(events).hexdigest(),
        }}
        with zipfile.ZipFile(evidence, "w") as archive:
            archive.writestr("manifest.json", json.dumps(manifest))
            archive.writestr("diagnostics.json", diagnostics)
            archive.writestr("lifecycle-events.json", events)
        log = {
            "schema": module.LOG_SCHEMA, "run_id": f"run-{index}",
            "project_id_sha256": "sha256:" + f"{index % 3:064x}", "source_git_commit": revision,
            "tester_id_sha256": "sha256:" + f"{index % 2 + 100:064x}",
            "receipt_evidence_file": evidence.name,
            "receipt_evidence_sha256": "sha256:" + hashlib.sha256(evidence.read_bytes()).hexdigest(),
            "support_configuration_id": "supported", "started_at": "2026-09-07T00:00:00+00:00",
            "preflight": {field: True for field in module.PREFLIGHT_FIELDS},
            "operations": {"request_count": 3, "mutation_count": 2, "readback_verified_count": 2, "undo_required_count": 2, "undo_verified_count": 2},
            "safety": {field: 0 for field in module.SAFETY_FIELDS},
            "session_result": "pass", "issue_ids": [], "tester_signoff": True,
        }
        if unsafe and index == 4: log["safety"]["false_success_receipts"] = 1
        path = tmp_path / f"run-{index}.json"; path.write_text(json.dumps(log)); paths.append(path)
    return paths, matrix, revision


def test_ten_safe_sessions_across_three_projects_qualify(tmp_path: Path) -> None:
    paths, matrix, revision = _inputs(tmp_path)
    result = module.evaluate(paths, matrix_path=matrix, source_revision=revision)
    assert result["qualified"] is True
    assert result["metrics"] == {"session_count": 10, "passed_session_count": 10, "project_count": 3,
                                 "tester_count": 2, "bound_receipt_count": 10}
    assert result["thresholds"]["receipt_evidence_bound"] is True
    assert len({row["project_bucket"] for row in result["rows"]}) == 3
    assert len({row["tester_bucket"] for row in result["rows"]}) == 2
    assert len({row["receipt_bucket"] for row in result["rows"]}) == 10
    assert all(row["project_bucket"].startswith("sha256:") for row in result["rows"])
    assert not any("project_id_sha256" in row or "tester_id_sha256" in row for row in result["rows"])


def test_any_safety_incident_fails_the_whole_pilot_receipt(tmp_path: Path) -> None:
    paths, matrix, revision = _inputs(tmp_path, unsafe=True)
    result = module.evaluate(paths, matrix_path=matrix, source_revision=revision)
    assert result["qualified"] is False
    assert result["thresholds"]["all_sessions_pass"] is False
    assert result["rows"][4]["failures"] == ["safety_incident"]


def test_revision_mismatch_and_incomplete_undo_accounting_fail(tmp_path: Path) -> None:
    paths, matrix, revision = _inputs(tmp_path)
    value = json.loads(paths[0].read_text()); value["source_git_commit"] = "b" * 40; value["operations"]["undo_verified_count"] = 1
    paths[0].write_text(json.dumps(value))
    result = module.evaluate(paths, matrix_path=matrix, source_revision=revision)
    assert result["qualified"] is False
    assert result["rows"][0]["failures"] == ["operation_accounting", "receipt_evidence", "source_revision"]


def test_zero_activity_cannot_count_as_a_pilot_session(tmp_path: Path) -> None:
    paths, matrix, revision = _inputs(tmp_path)
    value = json.loads(paths[0].read_text())
    value["operations"] = {"request_count": 0, "mutation_count": 0, "readback_verified_count": 0, "undo_required_count": 0, "undo_verified_count": 0}
    paths[0].write_text(json.dumps(value))
    result = module.evaluate(paths, matrix_path=matrix, source_revision=revision)
    assert result["qualified"] is False
    assert result["rows"][0]["failures"] == ["operation_accounting"]


def test_missing_or_reused_receipt_evidence_cannot_qualify(tmp_path: Path) -> None:
    paths, matrix, revision = _inputs(tmp_path)
    first = json.loads(paths[0].read_text())
    second = json.loads(paths[1].read_text())
    second["receipt_evidence_file"] = first["receipt_evidence_file"]
    second["receipt_evidence_sha256"] = first["receipt_evidence_sha256"]
    paths[1].write_text(json.dumps(second))
    paths[2].with_name(json.loads(paths[2].read_text())["receipt_evidence_file"]).unlink()

    result = module.evaluate(paths, matrix_path=matrix, source_revision=revision)

    assert result["qualified"] is False
    assert result["rows"][1]["failures"] == ["unique_receipt_evidence"]
    assert result["rows"][2]["failures"] == ["receipt_evidence"]


def test_repackaged_or_unverified_events_cannot_create_new_sessions(tmp_path: Path) -> None:
    paths, matrix, revision = _inputs(tmp_path)
    first_log = json.loads(paths[0].read_text())
    second_log = json.loads(paths[1].read_text())
    first_bundle = paths[0].with_name(first_log["receipt_evidence_file"])
    second_bundle = paths[1].with_name(second_log["receipt_evidence_file"])
    with zipfile.ZipFile(first_bundle) as archive:
        events = archive.read("lifecycle-events.json")
    diagnostics = b'{"different":true}'
    manifest = {
        "schema": "kenn.support_bundle.v1", "source_revision": revision,
        "files": {
            "diagnostics.json": hashlib.sha256(diagnostics).hexdigest(),
            "lifecycle-events.json": hashlib.sha256(events).hexdigest(),
        },
    }
    with zipfile.ZipFile(second_bundle, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("diagnostics.json", diagnostics)
        archive.writestr("lifecycle-events.json", events)
    second_log["receipt_evidence_sha256"] = "sha256:" + hashlib.sha256(second_bundle.read_bytes()).hexdigest()
    paths[1].write_text(json.dumps(second_log))

    third_log = json.loads(paths[2].read_text())
    third_bundle = paths[2].with_name(third_log["receipt_evidence_file"])
    unverified = json.dumps({"events": [
        {"receipt_id": f"unverified-{index}", "verified": False} for index in range(4)
    ]}).encode()
    manifest["files"]["lifecycle-events.json"] = hashlib.sha256(unverified).hexdigest()
    with zipfile.ZipFile(third_bundle, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("diagnostics.json", diagnostics)
        archive.writestr("lifecycle-events.json", unverified)
    third_log["receipt_evidence_sha256"] = "sha256:" + hashlib.sha256(third_bundle.read_bytes()).hexdigest()
    paths[2].write_text(json.dumps(third_log))

    result = module.evaluate(paths, matrix_path=matrix, source_revision=revision)

    assert result["qualified"] is False
    assert result["rows"][1]["failures"] == ["unique_receipt_evidence"]
    assert result["rows"][2]["failures"] == ["receipt_evidence"]
    assert result["metrics"]["bound_receipt_count"] == 8


def test_bundle_revision_and_all_manifest_hashes_are_bound(tmp_path: Path) -> None:
    paths, matrix, revision = _inputs(tmp_path)
    log = json.loads(paths[0].read_text())
    bundle = paths[0].with_name(log["receipt_evidence_file"])
    events = json.dumps({"events": [
        {"receipt_id": f"replacement-{index}", "verified": True}
        for index in range(4)
    ]}).encode()
    diagnostics = b"{}"
    manifest = {"schema": "kenn.support_bundle.v1", "source_revision": "b" * 40, "files": {
        "diagnostics.json": hashlib.sha256(diagnostics).hexdigest(),
        "lifecycle-events.json": hashlib.sha256(events).hexdigest(),
    }}
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("diagnostics.json", diagnostics)
        archive.writestr("lifecycle-events.json", events)
    log["receipt_evidence_sha256"] = "sha256:" + hashlib.sha256(bundle.read_bytes()).hexdigest()
    paths[0].write_text(json.dumps(log))

    result = module.evaluate(paths, matrix_path=matrix, source_revision=revision)

    assert result["qualified"] is False
    assert result["rows"][0]["failures"] == ["receipt_evidence"]
