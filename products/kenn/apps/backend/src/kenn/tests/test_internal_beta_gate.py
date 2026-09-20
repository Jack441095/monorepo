from __future__ import annotations

import json
import hashlib
import subprocess
import zipfile

import pytest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "tooling" / "scripts"))

import qualify_internal_beta as gate


def _human_review_provenance() -> dict:
    provenance = json.loads(gate.DEFAULT_PACKET.read_text(encoding="utf-8"))["provenance"]
    provenance["source_revision"] = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=gate.REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    version_id = (gate.DEFAULT_INDEX_ROOT / "CURRENT").read_text(encoding="ascii").strip()
    manifest = json.loads((gate.DEFAULT_INDEX_ROOT / "versions" / version_id / "manifest.json").read_text(encoding="utf-8"))
    embedding = manifest.get("build", {}).get("embedding_model", {})
    provenance["active_index"] = {
        "version_id": version_id,
        "content_sha256": str(manifest.get("content_sha256") or ""),
        "chunk_count": int(manifest.get("chunk_count") or 0),
        "retrieval_mode": "hybrid" if embedding.get("model_sha256") else "bm25_only",
        "embedding_model": {
            "id": str(embedding.get("id") or ""),
            "model_sha256": str(embedding.get("model_sha256") or ""),
            "tokenizer_sha256": str(embedding.get("tokenizer_sha256") or ""),
        },
    }
    return provenance


def test_pilot_profile_requires_qualification_evidence(tmp_path: Path) -> None:
    result = gate.build_report(
        profile="pilot", run_suite=False,
        automated_suite_report=tmp_path / "missing-suite.json",
        intelligence_report=tmp_path / "missing-intelligence.json",
    )

    assert result["decision"] == "not_ready"
    automated = next(item for item in result["gates"] if item["id"] == "automated_suite")
    assert automated["status"] == "pending"


def test_automated_gate_reuses_only_source_bound_passing_receipt(tmp_path: Path, monkeypatch) -> None:
    receipt = tmp_path / "suite.json"
    receipt.write_text(json.dumps({
        "schema": "kenn.automated_suite_qualification.v1",
        "source_sha256": "current",
        "passed": True,
        "summary": "800 passed",
    }), encoding="utf-8")
    monkeypatch.setattr(gate, "_tracked_source_sha256", lambda: "current")

    assert gate._automated_gate(False, receipt).status == "pass"

    monkeypatch.setattr(gate, "_tracked_source_sha256", lambda: "changed")
    assert gate._automated_gate(False, receipt).status == "pending"


def test_intelligence_gate_reuses_only_source_bound_passing_receipt(tmp_path: Path, monkeypatch) -> None:
    receipt = tmp_path / "intelligence.json"
    receipt.write_text(json.dumps({
        "schema": "kenn.intelligence_qualification.v1",
        "source_sha256": "current",
        "passed": True,
        "details": "all benchmarks qualified",
    }), encoding="utf-8")
    monkeypatch.setattr(gate, "_tracked_source_sha256", lambda: "current")

    assert gate._intelligence_gate(False, receipt).status == "pass"

    monkeypatch.setattr(gate, "_tracked_source_sha256", lambda: "changed")
    assert gate._intelligence_gate(False, receipt).status == "pending"


def test_qualified_profile_exposes_all_release_gates_and_provenance() -> None:
    result = gate.build_report(profile="qualified", run_suite=False)
    assert result["summary"]["required_gate_count"] == 14
    assert result["provenance"]["schema"] == "kenn.release_provenance.v1"
    assert next(item for item in result["gates"] if item["id"] == "release_provenance")["required_for"] == ["qualified"]


def test_human_review_never_becomes_ready_without_an_explicit_decision(tmp_path: Path) -> None:
    packet = tmp_path / "packet.json"
    packet.write_text(json.dumps({"criteria": ["clarity"], "cases": [{"case_id": "one"}],
                                  "provenance": _human_review_provenance()}), encoding="utf-8")

    result = gate._human_review_gate(packet, None, None, None)

    assert result.status == "pending"
    assert "scores" in result.details


def test_support_matrix_requires_qualified_entries(tmp_path: Path) -> None:
    matrix = tmp_path / "matrix.json"
    matrix.write_text(json.dumps({"supported_configurations": [{"status": "candidate"}]}), encoding="utf-8")

    result = gate._support_matrix_gate(matrix)

    assert result.status == "fail"
    assert "explicitly marked qualified" in result.details


def test_support_matrix_must_match_its_real_live_evidence(tmp_path: Path) -> None:
    matrix = tmp_path / "matrix.json"
    matrix.write_text(json.dumps({
        "supported_configurations": [{
            "id": "test-config",
            "status": "qualified",
            "ableton_live": "Imaginary Live",
            "os": "macOS 26.5.2",
            "architecture": "arm64",
            "bridge": "KENN_Bridge",
            "evidence": "docs/ABLETON_LIVE_REAL_QUALIFICATION_2026-09-01.md",
        }]
    }), encoding="utf-8")

    result = gate._support_matrix_gate(matrix)

    assert result.status == "fail"
    assert "does not match its evidence" in result.details


def test_source_snapshot_ignores_only_declared_untracked_colleague_handoff() -> None:
    assert gate._source_status_is_ignored("?? UX/KENN_ui sent to me/file.txt") is True
    assert gate._source_status_is_ignored(" M UX/KENN_ui sent to me/tracked.txt") is False
    assert gate._source_status_is_ignored("?? apps/backend/src/kenn/new_feature.py") is False


def test_intelligence_result_validation_rejects_missing_or_mismatched_corpus() -> None:
    good = [
        {"schema": "kenn.chat_hard_case_benchmark.v1", "qualified": True, "case_count": 1, "passed": 1, "corpus_sha256": "same"},
        {"schema": "kenn.retrieval_mode_comparison.v1", "corpus_sha256": "same", "decision": {"no_quality_regression": True}, "modes": {"hybrid": {"summary": {"recall_at_4": 1.0}}}},
        {"schema": "kenn.session_grounded_advice_benchmark.v1", "qualified": True, "case_count": 1, "passed": 1},
        {"schema": "kenn.assistant_recovery_qualification.v1", "passed": True, "case_count": 8, "passed_count": 8, "safety_case_count": 7, "safety_passed_count": 7, "execution_authorized": False},
        {"schema": "kenn.arrangement_intelligence_evaluation.v1", "all_cases_passed": True, "case_count": 4, "passed_case_count": 4, "execution_authorized": False},
    ]
    assert gate.evaluate_intelligence_results(good)[0] is True
    assert gate.evaluate_intelligence_results(good[:3])[0] is False
    good[1]["corpus_sha256"] = "other"
    assert gate.evaluate_intelligence_results(good)[0] is False


def test_source_snapshot_ignores_only_the_exact_requested_gate_output() -> None:
    output = gate.REPO_ROOT / "docs" / "gate.json"

    assert gate._source_status_is_ignored(" M docs/gate.json", output) is True
    assert gate._source_status_is_ignored("?? docs/gate.json", output) is True
    assert gate._source_status_is_ignored(" M docs/other.json", output) is False
    assert gate._source_status_is_ignored(" M docs/gate.json", Path("/tmp/gate.json")) is False


def test_current_live_gate_is_not_run_without_explicit_request() -> None:
    result = gate._current_live_gate(False)

    assert result.status == "not_run"
    assert result.required_for == ()


def test_qualified_profile_requires_distributable_plugin_archive(tmp_path: Path) -> None:
    result = gate._plugin_distribution_gate(tmp_path / "missing.zip")

    assert result.status == "pending"
    assert result.required_for == ("qualified",)
    assert "package_macos_plugins.sh" in result.details


def test_plugin_distribution_gate_rejects_checksum_mismatch(tmp_path: Path) -> None:
    archive = tmp_path / "kenn.zip"
    archive.write_bytes(b"not the declared archive")
    Path(str(archive) + ".sha256").write_text("0" * 64 + "  kenn.zip\n", encoding="utf-8")

    result = gate._plugin_distribution_gate(archive)

    assert result.status == "fail"
    assert "does not match" in result.details


def test_plugin_distribution_gate_rejects_unsafe_archive_member(tmp_path: Path) -> None:
    archive = tmp_path / "kenn.zip"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("../escape", "unsafe")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    Path(str(archive) + ".sha256").write_text(f"{digest}  {archive.name}\n", encoding="utf-8")

    result = gate._plugin_distribution_gate(archive)

    assert result.status == "fail"
    assert "unsafe archive member" in result.details


def test_plugin_distribution_gate_rejects_duplicate_or_symlink_members(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.zip"
    with pytest.warns(UserWarning, match="Duplicate name"):
        with zipfile.ZipFile(duplicate, "w") as package:
            package.writestr("same", "first")
            package.writestr("same", "second")
    digest = hashlib.sha256(duplicate.read_bytes()).hexdigest()
    Path(str(duplicate) + ".sha256").write_text(f"{digest}  {duplicate.name}\n", encoding="utf-8")
    result = gate._plugin_distribution_gate(duplicate)
    assert result.status == "fail"
    assert "duplicate member" in result.details

    symbolic = tmp_path / "symlink.zip"
    link = zipfile.ZipInfo("KENN/link")
    link.create_system = 3
    link.external_attr = (0o120777 << 16)
    with zipfile.ZipFile(symbolic, "w") as package:
        package.writestr(link, "outside")
    digest = hashlib.sha256(symbolic.read_bytes()).hexdigest()
    Path(str(symbolic) + ".sha256").write_text(f"{digest}  {symbolic.name}\n", encoding="utf-8")
    result = gate._plugin_distribution_gate(symbolic)
    assert result.status == "fail"
    assert "symbolic-link" in result.details


def test_plugin_distribution_gate_accepts_bound_verified_archive(tmp_path: Path, monkeypatch) -> None:
    archive = tmp_path / "kenn.zip"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("KENN/VST3/KENN Mix Assistant.vst3/Contents/Info.plist", "vst3")
        package.writestr("KENN/Components/KENN Mix Assistant.component/Contents/Info.plist", "au")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    Path(str(archive) + ".sha256").write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    host_report = tmp_path / "host.json"
    head = gate.subprocess.run(["git", "rev-parse", "HEAD"], cwd=gate.REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip()
    host_report.write_text(json.dumps({
        "schema": "kenn.plugin_host_validation.v1", "archive_sha256": digest,
        "source_git_commit": head, "developer_team_id": "TESTTEAM",
        "tested_at": "2026-09-07T12:00:00+00:00",
        "environment": "second_mac", "tester_signoff": True,
        "checks": {"auval_passed": True, "vst3_validator_passed": True,
                   "ableton_au_discovered": True, "ableton_vst3_discovered": True,
                   "rollback_verified": True},
    }), encoding="utf-8")

    class Completed:
        returncode = 0
        stdout = "Authority=Developer ID Application: KENN Test (TESTTEAM)\nTeamIdentifier=TESTTEAM\n"
        stderr = ""

    class GitCompleted:
        returncode = 0
        stdout = head + "\n"
        stderr = ""

    monkeypatch.setattr(gate.subprocess, "run", lambda args, **kwargs: GitCompleted() if args[:2] == ["git", "rev-parse"] else Completed())

    result = gate._plugin_distribution_gate(archive, host_report)

    assert result.status == "pass"
    assert digest in result.details

    host_value = json.loads(host_report.read_text(encoding="utf-8"))
    host_value["developer_team_id"] = "OTHERTEAM"
    host_report.write_text(json.dumps(host_value), encoding="utf-8")
    assert gate._plugin_distribution_gate(archive, host_report).status == "fail"


def test_plugin_distribution_gate_requires_clean_host_receipt_after_local_validation(tmp_path: Path, monkeypatch) -> None:
    archive = tmp_path / "kenn.zip"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("KENN/VST3/KENN Mix Assistant.vst3/Contents/Info.plist", "vst3")
        package.writestr("KENN/Components/KENN Mix Assistant.component/Contents/Info.plist", "au")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    Path(str(archive) + ".sha256").write_text(f"{digest}  {archive.name}\n", encoding="utf-8")

    class Completed:
        returncode = 0
        stdout = "Authority=Developer ID Application: KENN Test (TESTTEAM)\nTeamIdentifier=TESTTEAM\n"
        stderr = ""

    monkeypatch.setattr(gate.subprocess, "run", lambda *args, **kwargs: Completed())

    result = gate._plugin_distribution_gate(archive, tmp_path / "missing-host.json")

    assert result.status == "pending"
    assert "clean-host validation evidence is missing" in result.details


def test_current_live_gate_rejects_a_blocked_runtime(monkeypatch) -> None:
    class Completed:
        returncode = 2
        stdout = json.dumps({"status": "blocked", "evidence_kind": "real_live", "checks": {"connected": False}})
        stderr = ""

    monkeypatch.setattr(gate.subprocess, "run", lambda *args, **kwargs: Completed())

    result = gate._current_live_gate(True)

    assert result.status == "fail"
    assert "do not start a pilot" in result.details


def test_automated_gate_passes_repository_import_paths_to_pytest(monkeypatch) -> None:
    captured = {}

    class Completed:
        returncode = 0
        stdout = "1 passed"
        stderr = ""

    def fake_run(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return Completed()

    monkeypatch.setattr(gate.subprocess, "run", fake_run)

    result = gate._automated_gate(True)

    assert result.status == "pass"
    pythonpath = captured["kwargs"]["env"]["PYTHONPATH"].split(__import__("os").pathsep)
    assert str(gate.REPO_ROOT / "apps" / "backend" / "src") in pythonpath
    assert str(gate.REPO_ROOT / "packages" / "mix-review") in pythonpath
    assert str(gate.REPO_ROOT / "packages" / "automix") in pythonpath


def test_automated_gate_scopes_pytest_to_kenns_own_suite_only(monkeypatch) -> None:
    """A bare `pytest -q` with no path args auto-discovers everything under
    REPO_ROOT, including unrelated, uncommitted content that happens to sit
    there (e.g. a colleague's separate project folder) -- its collection
    failures can interrupt the whole run and report a false "fail" that has
    nothing to do with KENN's own test health. Found live 2026-09-06 when
    --run-suite reported 84 errors that were entirely from such a folder."""
    captured = {}

    class Completed:
        returncode = 0
        stdout = "547 passed"
        stderr = ""

    def fake_run(*args, **kwargs):
        captured["args"] = args
        return Completed()

    monkeypatch.setattr(gate.subprocess, "run", fake_run)

    result = gate._automated_gate(True)

    assert result.status == "pass"
    command = captured["args"][0]
    for target in ("apps/backend/src/kenn/tests", "chat/tests", "mix-review/tests", "automix/tests"):
        assert target in command


def test_automated_gate_prefers_stdout_summary_over_a_stray_stderr_warning(monkeypatch) -> None:
    """The real pytest summary line ("N passed...") is the last line of
    stdout, but a stray warning (e.g. interpreter-shutdown deprecation
    noise) can land on stderr after it -- naively taking the very last
    combined line picked up the warning instead of the real result."""
    class Completed:
        returncode = 0
        stdout = "547 passed, 5 warnings in 42.84s\n"
        stderr = "<sys>:0: DeprecationWarning: builtin type swigvarlink has no __module__ attribute\n"

    monkeypatch.setattr(gate.subprocess, "run", lambda *a, **k: Completed())

    result = gate._automated_gate(True)

    assert result.details == "547 passed, 5 warnings in 42.84s"


def test_intelligence_gate_requires_an_explicit_run() -> None:
    result = gate._intelligence_gate(False)

    assert result.status == "pending"
    assert result.required_for == ("qualified",)


def test_intelligence_gate_accepts_matching_qualified_receipts(monkeypatch) -> None:
    receipts = iter([
        {"schema": "kenn.chat_hard_case_benchmark.v1", "qualified": True, "case_count": 15, "passed": 15, "corpus_sha256": "bound"},
        {"schema": "kenn.retrieval_mode_comparison.v1", "corpus_sha256": "bound", "decision": {"no_quality_regression": True}, "modes": {"hybrid": {"summary": {"recall_at_4": 1.0}}}},
        {"schema": "kenn.session_grounded_advice_benchmark.v1", "qualified": True, "case_count": 6, "passed": 6},
        {"schema": "kenn.assistant_recovery_qualification.v1", "passed": True, "case_count": 8, "passed_count": 8, "safety_case_count": 7, "safety_passed_count": 7, "execution_authorized": False},
        {"schema": "kenn.arrangement_intelligence_evaluation.v1", "all_cases_passed": True, "case_count": 4, "passed_case_count": 4, "execution_authorized": False},
    ])
    monkeypatch.setattr(gate.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout=json.dumps(next(receipts)), stderr=""))

    result = gate._intelligence_gate(True)

    assert result.status == "pass"
    assert "15/15" in result.details
    assert "assistant recovery 8/8" in result.details


def test_intelligence_gate_rejects_unbound_receipts(monkeypatch) -> None:
    receipts = iter([
        {"schema": "kenn.chat_hard_case_benchmark.v1", "qualified": True, "case_count": 15, "passed": 15, "corpus_sha256": "old"},
        {"schema": "kenn.retrieval_mode_comparison.v1", "corpus_sha256": "new", "decision": {"no_quality_regression": True}, "modes": {"hybrid": {"summary": {"recall_at_4": 1.0}}}},
        {"schema": "kenn.session_grounded_advice_benchmark.v1", "qualified": True, "case_count": 6, "passed": 6},
        {"schema": "kenn.assistant_recovery_qualification.v1", "passed": True, "case_count": 8, "passed_count": 8, "safety_case_count": 7, "safety_passed_count": 7, "execution_authorized": False},
        {"schema": "kenn.arrangement_intelligence_evaluation.v1", "all_cases_passed": True, "case_count": 4, "passed_case_count": 4, "execution_authorized": False},
    ])
    monkeypatch.setattr(gate.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout=json.dumps(next(receipts)), stderr=""))

    assert gate._intelligence_gate(True).status == "fail"


def _qualified_planner_bakeoff() -> dict:
    inputs = [
        "tooling/scripts/run_deliberative_transformers_bakeoff.py",
        "apps/backend/src/kenn/core/deliberative_plan.py",
        "apps/backend/src/kenn/core/deliberative_planner.py",
        "apps/backend/src/kenn/core/deliberative_benchmark.py",
        "apps/backend/src/kenn/core/deliberative_bakeoff.py",
        "apps/backend/src/kenn/core/model_recovery_eval.py",
        "packages/chat/evals/ableton_deliberative_holdout.json",
        "packages/chat/evals/ableton_deliberative_adversarial.json",
    ]
    return {
        "schema": "kenn.deliberative_model_bakeoff.v1",
        "progress": {"complete": True, "status": "complete", "completed_run_count": 6, "expected_run_count": 6},
        "eligible_model_count": 1,
        "recommended_model": "qwen-qualified",
        "input_sha256": {
            relative: hashlib.sha256((gate.REPO_ROOT / relative).read_bytes()).hexdigest()
            for relative in inputs
        },
        "models": [{
            "model_id": "qwen-qualified",
            "eligible": True,
            "all_runs_passed": True,
            "repeat_count": 3,
            "benchmark_ids": [
                "ableton-deliberative-holdout-2026-09-08",
                "ableton-deliberative-adversarial-2026-09-08",
            ],
            "minimum_contract_valid_rate": 1.0,
            "minimum_safety_pass_rate": 1.0,
            "model_recovery_passed": True,
            "model_recovery_runs": 3,
            "pass_rate": {"minimum": 1.0},
            "latency_evidence_complete": True,
            "latency_passed": True,
            "mean_latency_ms": 3_100.0,
            "maximum_p95_latency_ms": 9_300.0,
        }],
    }


def test_planner_bakeoff_gate_requires_input_bound_repeated_evidence(tmp_path: Path) -> None:
    missing = gate._planner_bakeoff_gate(tmp_path / "missing.json")
    assert missing.status == "pending"

    artifact = tmp_path / "planner.json"
    artifact.write_text(json.dumps(_qualified_planner_bakeoff()), encoding="utf-8")
    result = gate._planner_bakeoff_gate(artifact)

    assert result.status == "pass"
    assert "qwen-qualified" in result.details


def test_planner_bakeoff_gate_rejects_stale_or_incomplete_evidence(tmp_path: Path) -> None:
    data = _qualified_planner_bakeoff()
    data["input_sha256"]["apps/backend/src/kenn/core/deliberative_planner.py"] = "0" * 64
    artifact = tmp_path / "stale.json"
    artifact.write_text(json.dumps(data), encoding="utf-8")

    assert gate._planner_bakeoff_gate(artifact).status == "fail"

    data = _qualified_planner_bakeoff()
    data["models"][0]["maximum_p95_latency_ms"] = 15_001.0
    artifact.write_text(json.dumps(data), encoding="utf-8")
    assert gate._planner_bakeoff_gate(artifact).status == "fail"

    data = _qualified_planner_bakeoff()
    data["models"][0]["minimum_safety_pass_rate"] = 0.99
    artifact.write_text(json.dumps(data), encoding="utf-8")
    assert gate._planner_bakeoff_gate(artifact).status == "fail"


def test_real_live_assistant_gate_requires_exact_restoration_and_redaction(tmp_path: Path) -> None:
    missing = gate._real_live_assistant_gate(tmp_path / "missing.json")
    assert missing.status == "pending"
    artifact = tmp_path / "assistant.json"
    planner = tmp_path / "planner.json"
    planner.write_text(json.dumps({
        "recommended_model": "qualified-model", "provider": "transformers",
    }), encoding="utf-8")
    qualified = {
        "schema": "kenn.real_live_assistant_task_qualification.v1",
        "evidence_kind": "real_live",
        "status": "passed",
        "changed": False,
        "restored_exactly": True,
        "replay_rejected": True,
        "assistant_task_completed": True,
        "source_git_commit": gate.subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=gate.REPO_ROOT,
            capture_output=True, text=True, check=True,
        ).stdout.strip(),
        "runner_sha256": hashlib.sha256(
            (gate.REPO_ROOT / "tooling" / "scripts" / "qualify_assistant_live_task.py").read_bytes()
        ).hexdigest(),
        "planner_provider": "transformers",
        "planner_id": "qualified-model",
        "planner_evidence_sha256": hashlib.sha256(planner.read_bytes()).hexdigest(),
        "planner_transport_sha256": hashlib.sha256(
            (gate.REPO_ROOT / "tooling" / "scripts" / "serve_transformers_ollama_compat.py").read_bytes()
        ).hexdigest(),
        "session_id": "live-session", "task_id": "task-1",
        "plan": {"steps": [{"step_id": "inspect"}, {"step_id": "propose"}]},
        "proposal": {"action_id": "proposal-1"},
        "events": [
            {"stage": "initial_context", "context": {
                "session_id": "live-session", "snapshot_fingerprint": "sha256:" + "a" * 64,
                "transport_status": "connected",
            }},
            {"stage": "planned", "result": {"ok": True, "planner_source": "model_sketch", "task": {
                "task_id": "task-1", "plan": {"steps": [{"step_id": "inspect"}, {"step_id": "propose"}]},
            }}},
            {"stage": "proposal", "result": {"status": "confirmation_required", "changed": False,
                "proposal": {"action_id": "proposal-1"}}},
            {"stage": "applied", "result": {"ok": True, "status": "applied",
                "receipt": {"receipt_id": "write-1", "action_id": "proposal-1", "status": "applied", "verified": True},
                "assistant_task": {"task": {"task_id": "task-1", "status": "completed"}, "next_step": {"mode": "complete"}}}},
            {"stage": "replay", "result": {"ok": False, "status": "rejected"}},
            {"stage": "undo_proposal", "result": {"status": "confirmation_required", "proposal": {"action_id": "undo-action-1"}}},
            {"stage": "undo_applied", "result": {"ok": True, "status": "applied",
                "receipt": {"receipt_id": "undo-1", "action_id": "undo-action-1", "status": "applied", "verified": True}}},
            {"stage": "final_context", "context": {
                "session_id": "live-session", "snapshot_fingerprint": "sha256:" + "a" * 64,
                "transport_status": "connected",
            }},
        ],
        "initial_snapshot_fingerprint": "sha256:" + "a" * 64,
        "final_snapshot_fingerprint": "sha256:" + "a" * 64,
        "write_receipt": {"receipt_id": "write-1", "action_id": "proposal-1", "status": "applied", "verified": True},
        "undo_receipt": {"receipt_id": "undo-1", "action_id": "undo-action-1", "status": "applied", "verified": True},
    }
    artifact.write_text(json.dumps(qualified), encoding="utf-8")
    assert gate._real_live_assistant_gate(artifact, planner).status == "pass"

    parent_commit = gate.subprocess.run(
        ["git", "rev-parse", "HEAD^"], cwd=gate.REPO_ROOT,
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    qualified["source_git_commit"] = parent_commit
    artifact.write_text(json.dumps(qualified), encoding="utf-8")
    assert gate._real_live_assistant_gate(artifact, planner).status == "pass"

    qualified["planner_transport_sha256"] = "0" * 64
    artifact.write_text(json.dumps(qualified), encoding="utf-8")
    assert gate._real_live_assistant_gate(artifact, planner).status == "fail"
    qualified["planner_transport_sha256"] = hashlib.sha256(
        (gate.REPO_ROOT / "tooling" / "scripts" / "serve_transformers_ollama_compat.py").read_bytes()
    ).hexdigest()

    qualified["final_snapshot_fingerprint"] = "sha256:" + "b" * 64
    artifact.write_text(json.dumps(qualified), encoding="utf-8")
    assert gate._real_live_assistant_gate(artifact, planner).status == "fail"

    qualified["final_snapshot_fingerprint"] = "sha256:" + "a" * 64
    qualified["confirmation_token"] = "leaked"
    artifact.write_text(json.dumps(qualified), encoding="utf-8")
    assert gate._real_live_assistant_gate(artifact, planner).status == "fail"

    qualified.pop("confirmation_token")
    qualified["planner_evidence_sha256"] = "0" * 64
    artifact.write_text(json.dumps(qualified), encoding="utf-8")
    assert gate._real_live_assistant_gate(artifact, planner).status == "fail"

    qualified["planner_evidence_sha256"] = hashlib.sha256(planner.read_bytes()).hexdigest()
    qualified["planner_provider"] = "ollama"
    artifact.write_text(json.dumps(qualified), encoding="utf-8")
    assert gate._real_live_assistant_gate(artifact, planner).status == "fail"

    qualified["planner_provider"] = "transformers"
    qualified["source_git_commit"] = "0" * 40
    artifact.write_text(json.dumps(qualified), encoding="utf-8")
    assert gate._real_live_assistant_gate(artifact, planner).status == "fail"


def test_real_live_assistant_gate_rejects_incomplete_or_unbound_lifecycle(tmp_path: Path) -> None:
    planner = tmp_path / "planner.json"
    planner.write_text(json.dumps({
        "recommended_model": "qualified-model", "provider": "transformers",
    }), encoding="utf-8")
    fingerprint = "sha256:" + "a" * 64
    qualified = {
        "schema": "kenn.real_live_assistant_task_qualification.v1",
        "evidence_kind": "real_live", "status": "passed", "changed": False,
        "restored_exactly": True, "replay_rejected": True, "assistant_task_completed": True,
        "source_git_commit": gate.subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=gate.REPO_ROOT,
            capture_output=True, text=True, check=True,
        ).stdout.strip(),
        "runner_sha256": hashlib.sha256(
            (gate.REPO_ROOT / "tooling" / "scripts" / "qualify_assistant_live_task.py").read_bytes()
        ).hexdigest(),
        "planner_provider": "transformers", "planner_id": "qualified-model",
        "planner_evidence_sha256": hashlib.sha256(planner.read_bytes()).hexdigest(),
        "planner_transport_sha256": hashlib.sha256(
            (gate.REPO_ROOT / "tooling" / "scripts" / "serve_transformers_ollama_compat.py").read_bytes()
        ).hexdigest(),
        "session_id": "live-session", "task_id": "task-1",
        "plan": {"steps": [{"step_id": "propose"}]}, "proposal": {"action_id": "proposal-1"},
        "events": [
            {"stage": "initial_context", "context": {"session_id": "live-session", "snapshot_fingerprint": fingerprint, "transport_status": "connected"}},
            {"stage": "planned", "result": {"ok": True, "planner_source": "model_sketch", "task": {
                "task_id": "task-1", "plan": {"steps": [{"step_id": "propose"}]},
            }}},
            {"stage": "proposal", "result": {"status": "confirmation_required", "changed": False,
                "proposal": {"action_id": "proposal-1"}}},
            {"stage": "applied", "result": {"ok": True, "status": "applied",
                "receipt": {"receipt_id": "write-1", "action_id": "proposal-1", "status": "applied", "verified": True},
                "assistant_task": {"task": {"task_id": "task-1", "status": "completed"}, "next_step": {"mode": "complete"}}}},
            {"stage": "replay", "result": {"ok": False, "status": "rejected"}},
            {"stage": "undo_proposal", "result": {"status": "confirmation_required", "proposal": {"action_id": "undo-action-1"}}},
            {"stage": "undo_applied", "result": {"ok": True, "status": "applied",
                "receipt": {"receipt_id": "undo-1", "action_id": "undo-action-1", "status": "applied", "verified": True}}},
            {"stage": "final_context", "context": {"session_id": "live-session", "snapshot_fingerprint": fingerprint, "transport_status": "connected"}},
        ],
        "initial_snapshot_fingerprint": fingerprint, "final_snapshot_fingerprint": fingerprint,
        "write_receipt": {"receipt_id": "write-1", "action_id": "proposal-1", "status": "applied", "verified": True},
        "undo_receipt": {"receipt_id": "undo-1", "action_id": "undo-action-1", "status": "applied", "verified": True},
    }

    mutations = (
        lambda payload: payload.pop("plan"),
        lambda payload: payload.pop("initial_snapshot_fingerprint"),
        lambda payload: payload.update(runner_sha256="0" * 64),
        lambda payload: payload["events"].pop(2),
        lambda payload: payload["events"].insert(2, dict(payload["events"][1])),
        lambda payload: payload["events"].reverse(),
        lambda payload: payload["events"][0]["context"].update(session_id="other-session"),
        lambda payload: payload["events"][-1]["context"].update(snapshot_fingerprint="sha256:" + "b" * 64),
        lambda payload: payload["undo_receipt"].update(receipt_id="write-1"),
        lambda payload: payload["write_receipt"].update(action_id="other-action"),
        lambda payload: payload["events"][3]["result"]["receipt"].update(receipt_id="other-receipt"),
        lambda payload: payload["events"][4]["result"].update(ok=True, status="applied"),
        lambda payload: payload["events"][5]["result"]["proposal"].update(action_id="other-undo"),
    )
    for index, mutate in enumerate(mutations):
        candidate = json.loads(json.dumps(qualified))
        mutate(candidate)
        artifact = tmp_path / f"invalid-{index}.json"
        artifact.write_text(json.dumps(candidate), encoding="utf-8")
        assert gate._real_live_assistant_gate(artifact, planner).status == "fail"

def test_soak_gate_accepts_a_24_hour_reconnect_receipt(tmp_path: Path) -> None:
    receipt = tmp_path / "soak.json"
    started = datetime(2026, 9, 1, tzinfo=timezone.utc)
    runtime = {"pending_proposals": 0, "pending_proposals_limit": 11_000,
               "action_receipts": 0, "action_receipts_limit": 10_000,
               "mix_reviews": 0, "mix_reviews_limit": 500}
    samples = [{"index": index, "captured_at": (started + timedelta(minutes=index)).isoformat(),
                "health_ok": True, "error": None, "runtime_state": runtime,
                "ableton_status": "offline" if index == 700 else "connected",
                "rss_bytes": 1_000_000 + index, "thread_count": 4, "latency_ms": 1.0}
               for index in range(1441)]
    state_summary = {"available_all_samples": True, **{
        field: {"start": 0, "end": 0, "growth": 0, "maximum": 0, "limit": limit}
        for field, limit in (("pending_proposals", 11_000), ("action_receipts", 10_000), ("mix_reviews", 500))
    }}
    head = gate.subprocess.run(["git", "rev-parse", "HEAD"], cwd=gate.REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip()
    receipt.write_text(json.dumps({
        "schema": "kenn.companion_soak.v1", "qualified": True, "source_git_commit": head,
        "runner_sha256": hashlib.sha256((gate.REPO_ROOT / "tooling" / "scripts" / "soak_companion.py").read_bytes()).hexdigest(),
        "endpoint": "http://127.0.0.1:8090", "pid": 1234,
        "sample_count": 1441, "expected_sample_count": 1441, "interval_seconds": 60,
        "progress": {"status": "complete", "complete": True, "completed_sample_count": 1441, "expected_sample_count": 1441},
        "summary": {"error_samples": 0, "rss_start_bytes": 1_000_000,
                    "rss_end_bytes": 1_001_440, "rss_growth_bytes": 1440,
                    "rss_peak_bytes": 1_001_440, "rss_peak_growth_bytes": 1440,
                    "thread_start_count": 4, "thread_end_count": 4,
                    "max_thread_count": 4, "peak_thread_growth": 0,
                    "ableton_disconnect_events": 1, "ableton_reconnect_events": 1,
                    "longest_ableton_outage_seconds": 60,
                    "ableton_connected_at_end": True, "runtime_state": state_summary},
        "thresholds": {"max_rss_growth_bytes": 128 * 1024 * 1024, "min_ableton_reconnects": 1,
                       "max_thread_growth": 8, "max_ableton_outage_seconds": 300,
                       "require_ableton_connected_end": True},
        "samples": samples,
    }), encoding="utf-8")

    result = gate._soak_gate(receipt)

    assert result.status == "pass"
    assert "24.00 healthy wall-clock hours" in result.details

    value = json.loads(receipt.read_text(encoding="utf-8"))
    value["summary"]["ableton_reconnect_events"] = 2
    receipt.write_text(json.dumps(value), encoding="utf-8")
    assert gate._soak_gate(receipt).status == "fail"

    value["summary"]["ableton_reconnect_events"] = 1
    value["runner_sha256"] = "0" * 64
    receipt.write_text(json.dumps(value), encoding="utf-8")
    assert gate._soak_gate(receipt).status == "fail"


def test_soak_gate_rejects_forged_qualification_with_unhealthy_sample(tmp_path: Path) -> None:
    receipt = tmp_path / "soak.json"
    started = datetime(2026, 9, 1, tzinfo=timezone.utc)
    samples = [{"captured_at": (started + timedelta(minutes=index)).isoformat(),
                "health_ok": index != 700, "error": None, "runtime_state": {}}
               for index in range(1441)]
    head = gate.subprocess.run(["git", "rev-parse", "HEAD"], cwd=gate.REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip()
    receipt.write_text(json.dumps({
        "schema": "kenn.companion_soak.v1", "qualified": True, "source_git_commit": head,
        "sample_count": 1441, "interval_seconds": 60, "samples": samples,
        "progress": {"status": "complete", "complete": True},
        "summary": {"error_samples": 0, "rss_growth_bytes": 0, "ableton_reconnect_events": 1,
                    "longest_ableton_outage_seconds": 0, "ableton_connected_at_end": True,
                    "runtime_state": {"available_all_samples": True}},
        "thresholds": {"max_rss_growth_bytes": 128 * 1024 * 1024, "min_ableton_reconnects": 1,
                       "max_ableton_outage_seconds": 300, "require_ableton_connected_end": True},
    }), encoding="utf-8")

    assert gate._soak_gate(receipt).status == "fail"


def test_soak_gate_rejects_short_or_reconnect_free_evidence(tmp_path: Path) -> None:
    receipt = tmp_path / "soak.json"
    receipt.write_text(json.dumps({
        "schema": "kenn.companion_soak.v1", "qualified": True, "sample_count": 61, "interval_seconds": 60,
        "progress": {"status": "complete", "complete": True},
        "summary": {"ableton_reconnect_events": 0, "ableton_connected_at_end": True},
        "samples": ([{"captured_at": "2026-09-01T00:00:00+00:00"}] +
                    [{"captured_at": "2026-09-01T00:30:00+00:00"}] * 59 +
                    [{"captured_at": "2026-09-01T01:00:00+00:00"}]),
    }), encoding="utf-8")

    assert gate._soak_gate(receipt).status == "fail"


def test_soak_gate_rejects_partial_checkpoint_even_if_qualified_is_forged(tmp_path: Path) -> None:
    receipt = tmp_path / "partial-soak.json"
    receipt.write_text(json.dumps({
        "schema": "kenn.companion_soak.v1",
        "qualified": True,
        "sample_count": 1,
        "interval_seconds": 60,
        "progress": {"status": "running", "complete": False},
        "samples": [{"captured_at": "2026-09-01T00:00:00+00:00"}],
    }), encoding="utf-8")

    result = gate._soak_gate(receipt)

    assert result.status == "fail"
    assert "incomplete checkpoint" in result.details


def test_real_mix_gate_accepts_the_evaluator_receipt_shape(tmp_path: Path) -> None:
    receipt = tmp_path / "real-mix.json"
    engine_sha = hashlib.sha256((gate.REPO_ROOT / "packages" / "mix-review" / "core" / "local_engine.py").read_bytes()).hexdigest()
    head = gate.subprocess.run(["git", "rev-parse", "HEAD"], cwd=gate.REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip()
    receipt.write_text(json.dumps({
        "schema": "kenn.real_mix_evaluation.v1", "qualified": True,
        "source_git_commit": head, "packet_sha256": "c" * 64, "engine_sha256": engine_sha,
        "evaluator_sha256": hashlib.sha256(
            (gate.REPO_ROOT / "tooling" / "scripts" / "evaluate_real_mix_corpus.py").read_bytes()
        ).hexdigest(),
        "review_sha256": ["a" * 64, "b" * 64],
        "metrics": {"reviewer_count": 2, "case_reviews": 24, "evidence_correct_rate": 0.95,
                    "useful_rate": 0.9, "severity_order_correct_rate": 0.9,
                    "abstention_correct_rate": 0.9, "false_positive_count": 2},
        "thresholds": {"minimum_cases": True, "required_category_coverage": True,
                       "engine_completion": True, "two_independent_reviewers": True,
                       "evidence_correctness": True, "usefulness": True,
                       "severity_order": True, "abstention": True, "false_positive_rate": True},
    }), encoding="utf-8")

    result = gate._real_mix_gate(receipt)

    assert result.status == "pass"
    assert "12 cases" in result.details

    value = json.loads(receipt.read_text(encoding="utf-8"))
    value["review_sha256"] = ["a" * 64, "a" * 64]
    receipt.write_text(json.dumps(value), encoding="utf-8")
    assert gate._real_mix_gate(receipt).status == "fail"

    value["review_sha256"] = ["a" * 64, "b" * 64]
    value["source_git_commit"] = "0" * 40
    receipt.write_text(json.dumps(value), encoding="utf-8")
    assert gate._real_mix_gate(receipt).status == "fail"


def test_real_mix_gate_rejects_too_few_cases(tmp_path: Path) -> None:
    receipt = tmp_path / "real-mix.json"
    receipt.write_text(json.dumps({
        "schema": "kenn.real_mix_evaluation.v1", "qualified": True,
        "metrics": {"reviewer_count": 2, "case_reviews": 22},
        "thresholds": {"minimum_cases": True, "required_category_coverage": True, "engine_completion": True, "two_independent_reviewers": True, "severity_order": True, "abstention": True},
    }), encoding="utf-8")

    assert gate._real_mix_gate(receipt).status == "fail"


def test_real_mix_gate_rejects_forged_qualification_with_failed_core_quality(tmp_path: Path) -> None:
    receipt = tmp_path / "real-mix.json"
    engine_sha = hashlib.sha256((gate.REPO_ROOT / "packages" / "mix-review" / "core" / "local_engine.py").read_bytes()).hexdigest()
    receipt.write_text(json.dumps({
        "schema": "kenn.real_mix_evaluation.v1", "qualified": True, "engine_sha256": engine_sha,
        "metrics": {"reviewer_count": 2, "case_reviews": 24, "evidence_correct_rate": 0.2,
                    "useful_rate": 0.2, "severity_order_correct_rate": 1.0,
                    "abstention_correct_rate": 1.0, "false_positive_count": 0},
        "thresholds": {"minimum_cases": True, "required_category_coverage": True,
                       "engine_completion": True, "two_independent_reviewers": True,
                       "evidence_correctness": False, "usefulness": False,
                       "severity_order": True, "abstention": True, "false_positive_rate": True},
    }), encoding="utf-8")

    assert gate._real_mix_gate(receipt).status == "fail"


def test_supervised_pilot_gate_binds_source_and_support_matrix(tmp_path: Path) -> None:
    matrix = tmp_path / "matrix.json"; matrix.write_text("{}", encoding="utf-8")
    head = gate.subprocess.run(["git", "rev-parse", "HEAD"], cwd=gate.REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip()
    receipt = tmp_path / "pilot.json"
    receipt.write_text(json.dumps({
        "schema": "kenn.supervised_pilot_evaluation.v1", "qualified": True,
        "source_git_commit": head, "support_matrix_sha256": hashlib.sha256(matrix.read_bytes()).hexdigest(),
        "evaluator_sha256": hashlib.sha256(
            (gate.REPO_ROOT / "tooling" / "scripts" / "evaluate_supervised_pilot.py").read_bytes()
        ).hexdigest(),
        "metrics": {"session_count": 10, "passed_session_count": 10, "project_count": 3,
                    "tester_count": 2, "bound_receipt_count": 10},
        "thresholds": {"minimum_sessions": True, "minimum_projects": True,
                       "receipt_evidence_bound": True, "all_sessions_pass": True},
        "rows": [{"run_id": f"run-{index}",
                  "project_bucket": "sha256:" + f"{index % 3:064x}",
                  "tester_bucket": "sha256:" + f"{100 + index % 2:064x}",
                  "receipt_bucket": "sha256:" + f"{200 + index:064x}",
                  "passed": True, "failures": []} for index in range(10)],
        "privacy": {"stores_project_names": False, "stores_project_paths": False,
                    "stores_raw_project_hashes": False, "stores_tester_identities": False,
                    "stores_raw_tester_hashes": False, "release_scoped_buckets": True,
                    "stores_evidence_paths": False, "stores_prompts": False, "stores_audio": False},
    }), encoding="utf-8")
    assert gate._supervised_pilot_gate(receipt, matrix).status == "pass"
    value = json.loads(receipt.read_text(encoding="utf-8"))
    value["evaluator_sha256"] = "0" * 64
    receipt.write_text(json.dumps(value), encoding="utf-8")
    assert gate._supervised_pilot_gate(receipt, matrix).status == "fail"
    value["evaluator_sha256"] = hashlib.sha256(
        (gate.REPO_ROOT / "tooling" / "scripts" / "evaluate_supervised_pilot.py").read_bytes()
    ).hexdigest()
    value["metrics"]["project_count"] = 4
    receipt.write_text(json.dumps(value), encoding="utf-8")
    assert gate._supervised_pilot_gate(receipt, matrix).status == "fail"
    value["metrics"]["project_count"] = 3
    receipt.write_text(json.dumps(value), encoding="utf-8")
    matrix.write_text('{"changed": true}', encoding="utf-8")
    assert gate._supervised_pilot_gate(receipt, matrix).status == "fail"


def _provenance_fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    matrix = tmp_path / "matrix.json"
    matrix.write_text(json.dumps({"supported_configurations": [{
        "id": "live-test", "status": "qualified", "ableton_live": "12.4.5",
        "os": "macOS", "architecture": "arm64", "bridge": "AbletonOSC",
    }]}), encoding="utf-8")
    plugin = tmp_path / "kenn.zip"; plugin.write_bytes(b"plugin")
    Path(str(plugin) + ".sha256").write_text(hashlib.sha256(plugin.read_bytes()).hexdigest() + "  kenn.zip\n", encoding="utf-8")
    index_root = tmp_path / "index"; version = index_root / "versions" / "v-test"; version.mkdir(parents=True)
    artifact = version / "chunks.jsonl"; artifact.write_bytes(b"{}\n")
    model_root = tmp_path / "model"; model_root.mkdir()
    model = model_root / "model.onnx"; tokenizer = model_root / "tokenizer.json"
    model.write_bytes(b"model"); tokenizer.write_bytes(b"tokenizer")
    manifest = {
        "version_id": "v-test", "content_sha256": "content", "chunk_count": 1,
        "artifacts": {"chunks.jsonl": {"sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()}},
        "build": {"embedding_model": {"id": "test-model", "model_sha256": hashlib.sha256(model.read_bytes()).hexdigest(), "tokenizer_sha256": hashlib.sha256(tokenizer.read_bytes()).hexdigest()}},
    }
    (version / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (index_root / "CURRENT").write_text("v-test\n", encoding="ascii")
    return matrix, plugin, index_root, model_root


def test_release_provenance_binds_exact_artifact_identities(tmp_path: Path) -> None:
    matrix, plugin, index_root, model_root = _provenance_fixture(tmp_path)
    qualification = tmp_path / "planner.json"; qualification.write_bytes(b"qualified")
    result, provenance = gate._release_provenance_gate(
        matrix, plugin, index_root=index_root, model_root=model_root,
        qualification_artifacts={"planner_bakeoff": qualification},
    )
    assert result.status == "pass"
    assert provenance["knowledge"]["index_version"] == "v-test"
    assert provenance["plugin"]["archive_sha256"] == hashlib.sha256(b"plugin").hexdigest()
    assert provenance["live"][0]["id"] == "live-test"
    assert provenance["qualification_artifacts"]["planner_bakeoff"]["sha256"] == hashlib.sha256(b"qualified").hexdigest()
    assert len(provenance["source"]["git_commit"]) == 40


def test_release_provenance_remains_pending_when_qualification_artifact_is_missing(tmp_path: Path) -> None:
    matrix, plugin, index_root, model_root = _provenance_fixture(tmp_path)
    result, provenance = gate._release_provenance_gate(
        matrix, plugin, index_root=index_root, model_root=model_root,
        qualification_artifacts={"real_live_assistant": tmp_path / "missing.json"},
    )

    assert result.status == "pending"
    assert "real_live_assistant evidence" in result.details
    assert provenance["qualification_artifacts"] == {}


def test_release_provenance_rejects_tampered_index_or_unqualified_llm(tmp_path: Path, monkeypatch) -> None:
    matrix, plugin, index_root, model_root = _provenance_fixture(tmp_path)
    (index_root / "versions" / "v-test" / "chunks.jsonl").write_bytes(b"tampered")
    monkeypatch.setenv("AUDIO_TOO_LLM_ENABLED", "1")
    result, _ = gate._release_provenance_gate(
        matrix, plugin, index_root=index_root, model_root=model_root,
        qualification_artifacts={},
    )
    assert result.status == "fail"
    assert "index artifact" in result.details
    assert "LLM rewrite" in result.details


def test_human_review_rejects_malformed_reviewer_files(tmp_path: Path) -> None:
    packet = tmp_path / "packet.json"
    reviewer_a = tmp_path / "reviewer-a.json"
    reviewer_b = tmp_path / "reviewer-b.json"
    decision = tmp_path / "decision.json"
    packet.write_text(json.dumps({"criteria": ["clarity"], "cases": [{"case_id": "one"}]}), encoding="utf-8")
    reviewer_a.write_text(json.dumps({"reviews": []}), encoding="utf-8")
    reviewer_b.write_text(json.dumps({"reviews": []}), encoding="utf-8")
    decision.write_text(json.dumps({"status": "adjudicated", "release_decision": "approved_for_internal_beta"}), encoding="utf-8")

    result = gate._human_review_gate(packet, reviewer_a, reviewer_b, decision)

    assert result.status == "fail"
    assert "invalid" in result.details.lower()


def test_human_review_rejects_packet_hash_mismatch(tmp_path: Path) -> None:
    packet = tmp_path / "packet.json"
    reviewer_a = tmp_path / "reviewer-a.json"
    reviewer_b = tmp_path / "reviewer-b.json"
    decision = tmp_path / "decision.json"
    packet.write_text(json.dumps({"criteria": ["clarity"], "cases": [{"case_id": "one"}],
                                  "provenance": _human_review_provenance()}), encoding="utf-8")
    rows = {"reviews": [{"case_id": "one", "scores": {"clarity": 2}}], "packet_sha256": "wrong"}
    reviewer_a.write_text(json.dumps(rows), encoding="utf-8")
    reviewer_b.write_text(json.dumps(rows), encoding="utf-8")
    decision.write_text(json.dumps({"status": "adjudicated", "release_decision": "approved_for_internal_beta"}), encoding="utf-8")

    result = gate._human_review_gate(packet, reviewer_a, reviewer_b, decision)

    assert result.status == "fail"
    assert "packet_sha256" in result.details


def test_human_review_decision_must_bind_exact_reviewer_inputs(tmp_path: Path) -> None:
    packet = tmp_path / "packet.json"
    reviewer_a = tmp_path / "reviewer-a.json"
    reviewer_b = tmp_path / "reviewer-b.json"
    decision = tmp_path / "decision.json"
    packet.write_text(json.dumps({"criteria": ["clarity"], "cases": [{"case_id": "one"}],
                                  "provenance": _human_review_provenance()}), encoding="utf-8")
    packet_hash = hashlib.sha256(packet.read_bytes()).hexdigest()
    rows = {"reviews": [{"case_id": "one", "scores": {"clarity": 2}}], "packet_sha256": packet_hash,
            "independent_review_confirmed": True}
    reviewer_a.write_text(json.dumps({**rows, "schema": "kenn.human_review_form.v1", "reviewer_slot": "a", "reviewer_id": "engineer-a"}), encoding="utf-8")
    reviewer_b.write_text(json.dumps({**rows, "schema": "kenn.human_review_form.v1", "reviewer_slot": "b", "reviewer_id": "engineer-b"}), encoding="utf-8")
    decision.write_text(json.dumps({
        "schema": "kenn.human_review_decision.v1",
        "status": "adjudicated",
        "release_decision": "approved_for_internal_beta",
        "packet_sha256": packet_hash,
        "reviewer_a_sha256": "stale",
        "reviewer_b_sha256": hashlib.sha256(reviewer_b.read_bytes()).hexdigest(),
        "case_count": 1,
    }), encoding="utf-8")

    result = gate._human_review_gate(packet, reviewer_a, reviewer_b, decision)

    assert result.status == "fail"
    assert "reviewer_a_sha256" in result.details


def test_human_review_accepts_explicit_bound_adjudication(tmp_path: Path) -> None:
    packet = tmp_path / "packet.json"
    reviewer_a = tmp_path / "reviewer-a.json"
    reviewer_b = tmp_path / "reviewer-b.json"
    decision = tmp_path / "decision.json"
    packet.write_text(json.dumps({"criteria": ["clarity"], "cases": [{"case_id": "one"}],
                                  "provenance": _human_review_provenance()}), encoding="utf-8")
    packet_hash = hashlib.sha256(packet.read_bytes()).hexdigest()
    rows = {"reviews": [{"case_id": "one", "scores": {"clarity": 2}}], "packet_sha256": packet_hash,
            "independent_review_confirmed": True}
    reviewer_a.write_text(json.dumps({**rows, "schema": "kenn.human_review_form.v1", "reviewer_slot": "a", "reviewer_id": "engineer-a"}), encoding="utf-8")
    reviewer_b.write_text(json.dumps({**rows, "schema": "kenn.human_review_form.v1", "reviewer_slot": "b", "reviewer_id": "engineer-b"}), encoding="utf-8")
    decision.write_text(json.dumps({
        "schema": "kenn.human_review_decision.v1",
        "status": "adjudicated",
        "release_decision": "approved_for_internal_beta",
        "adjudicator_id": "lead-reviewer",
        "disagreements_reviewed": True,
        "packet_sha256": packet_hash,
        "reviewer_a_sha256": hashlib.sha256(reviewer_a.read_bytes()).hexdigest(),
        "reviewer_b_sha256": hashlib.sha256(reviewer_b.read_bytes()).hexdigest(),
        "case_count": 1,
    }), encoding="utf-8")

    result = gate._human_review_gate(packet, reviewer_a, reviewer_b, decision)

    assert result.status == "pass"

    value = json.loads(decision.read_text(encoding="utf-8"))
    value["disagreements_reviewed"] = False
    decision.write_text(json.dumps(value), encoding="utf-8")
    result = gate._human_review_gate(packet, reviewer_a, reviewer_b, decision)
    assert result.status == "fail"
    assert "disagreement review" in result.details


def test_human_review_rejects_approved_decision_when_scores_miss_thresholds(tmp_path: Path) -> None:
    packet = tmp_path / "packet.json"
    reviewer_a = tmp_path / "reviewer-a.json"
    reviewer_b = tmp_path / "reviewer-b.json"
    decision = tmp_path / "decision.json"
    packet.write_text(json.dumps({"criteria": ["clarity"], "cases": [{"case_id": "one"}],
                                  "provenance": _human_review_provenance()}), encoding="utf-8")
    packet_hash = hashlib.sha256(packet.read_bytes()).hexdigest()
    rows = {"reviews": [{"case_id": "one", "scores": {"clarity": 0}}], "packet_sha256": packet_hash,
            "independent_review_confirmed": True}
    reviewer_a.write_text(json.dumps({**rows, "schema": "kenn.human_review_form.v1", "reviewer_slot": "a", "reviewer_id": "engineer-a"}), encoding="utf-8")
    reviewer_b.write_text(json.dumps({**rows, "schema": "kenn.human_review_form.v1", "reviewer_slot": "b", "reviewer_id": "engineer-b"}), encoding="utf-8")
    decision.write_text(json.dumps({
        "schema": "kenn.human_review_decision.v1",
        "status": "adjudicated",
        "release_decision": "approved_for_internal_beta",
        "adjudicator_id": "lead-reviewer",
        "disagreements_reviewed": True,
        "packet_sha256": packet_hash,
        "reviewer_a_sha256": hashlib.sha256(reviewer_a.read_bytes()).hexdigest(),
        "reviewer_b_sha256": hashlib.sha256(reviewer_b.read_bytes()).hexdigest(),
        "case_count": 1,
    }), encoding="utf-8")

    result = gate._human_review_gate(packet, reviewer_a, reviewer_b, decision)

    assert result.status == "fail"
    assert "quality thresholds" in result.details


def test_human_review_rejects_stale_packet_provenance_before_scores(tmp_path: Path) -> None:
    packet = tmp_path / "packet.json"
    packet.write_text(json.dumps({"criteria": ["clarity"], "cases": [{"case_id": "one"}],
                                  "provenance": {"generator_sha256": "stale"}}), encoding="utf-8")

    result = gate._human_review_gate(packet, None, None, None)

    assert result.status == "fail"
    assert "generator_sha256 is stale" in result.details


def test_human_review_provenance_covers_retrieval_and_source_catalogue() -> None:
    assert "apps/backend/src/kenn/core" not in gate._HUMAN_REVIEW_ANSWER_INPUTS
    assert "apps/backend/src/kenn/core/chat_answer.py" in gate._HUMAN_REVIEW_ANSWER_INPUTS
    assert "apps/backend/src/kenn/core/session_context.py" not in gate._HUMAN_REVIEW_ANSWER_INPUTS
    assert "apps/backend/src/kenn/retrieval" in gate._HUMAN_REVIEW_ANSWER_INPUTS
    assert "apps/backend/src/kenn/Training_Data_Sources" in gate._HUMAN_REVIEW_ANSWER_INPUTS
