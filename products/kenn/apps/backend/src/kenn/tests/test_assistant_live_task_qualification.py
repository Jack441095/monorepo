from __future__ import annotations

import importlib.util
import json
import stat

import pytest
from pathlib import Path

from kenn.core.mcp_facade import KennTransportError


SCRIPT = Path(__file__).resolve().parents[5] / "tooling" / "scripts" / "qualify_assistant_live_task.py"
spec = importlib.util.spec_from_file_location("assistant_live_qualification", SCRIPT)
runner = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(runner)


class FakeFacade:
    planner_provider = "test-provider"
    planner_id = "test-model"

    def __init__(self, *, restore: bool = True):
        self.calls: list[tuple[str, dict]] = []
        self.mutated = False
        self.restore = restore

    def _context(self) -> dict:
        fingerprint = "initial-fingerprint" if not self.mutated else "changed-fingerprint"
        return {
            "schema": "kenn.session_context.v1",
            "session_id": "real-session",
            "snapshot_fingerprint": fingerprint,
            "transport": {"status": "connected"},
        }

    def _dispatch(self, name: str, args: dict) -> dict:
        self.calls.append((name, args))
        if name == "kenn_context":
            return self._context()
        if name == "plan_assistant_task":
            return {
                "ok": True,
                "planner_source": "model_sketch",
                "task": {
                    "task_id": "task-1",
                    "plan": {"steps": [{"step_id": "inspect"}, {"step_id": "propose"}]},
                },
                "next_step": {"mode": "inspect", "step_id": "inspect"},
            }
        if name == "record_assistant_observation":
            return {"ok": True, "next_step": {"mode": "prepare_live_proposal", "step_id": "propose"}}
        if name == "create_live_proposal":
            return {
                "ok": True,
                "status": "confirmation_required",
                "changed": False,
                "proposal": {
                    "schema": "kenn.ableton_action_proposal.v1",
                    "action_id": "action-1",
                    "confirmation_token": "proposal-secret",
                },
                "assistant_task": {"next_step": {"mode": "wait_for_confirmation"}},
            }
        if name == "apply_live_proposal":
            if self.mutated:
                return {"ok": False, "status": "rejected", "error": "already executed"}
            self.mutated = True
            return {
                "ok": True,
                "status": "applied",
                "changed": True,
                "receipt": {
                    "receipt_id": "receipt-1", "action_id": "action-1",
                    "status": "applied", "verified": True,
                    "confirmation_token": "receipt-secret",
                },
                "assistant_task": {
                    "task": {"task_id": "task-1", "status": "completed"},
                    "next_step": {"mode": "complete"},
                },
            }
        if name == "undo_live_receipt" and "proposal" not in args:
            return {
                "ok": True,
                "status": "confirmation_required",
                "proposal": {"action_id": "undo-1", "confirmation_token": "undo-secret"},
            }
        if name == "undo_live_receipt":
            if self.restore:
                self.mutated = False
            return {
                "ok": True,
                "status": "applied",
                "receipt": {"receipt_id": "undo-receipt", "action_id": "undo-1", "status": "applied", "verified": True},
            }
        raise AssertionError(name)


def test_assistant_live_qualification_is_proposal_only_by_default() -> None:
    facade = FakeFacade()

    result = runner.qualify(
        facade=facade, goal="Safely adjust the selected track",
        command="Set selected track pan to 10%", session_id="real-session",
    )

    assert result["status"] == "proposal_ready"
    assert result["changed"] is False
    assert facade.mutated is False
    assert not any(name in {"apply_live_proposal", "undo_live_receipt"} for name, _ in facade.calls)
    assert "secret" not in str(result)


@pytest.mark.parametrize("context_patch", [
    {"snapshot_fingerprint": ""},
    {"session_id": "different-session"},
])
def test_assistant_live_qualification_requires_initial_context_identity(context_patch: dict) -> None:
    class InvalidContextFacade(FakeFacade):
        def _context(self) -> dict:
            return {**super()._context(), **context_patch}

    facade = InvalidContextFacade()
    result = runner.qualify(
        facade=facade, goal="Safely adjust the selected track",
        command="Set selected track pan to 10%", session_id="real-session", apply=True,
    )

    assert result["status"] == "blocked"
    assert result["stage"] == "context"
    assert result["changed"] is False
    assert facade.mutated is False
    assert not any(name == "apply_live_proposal" for name, _ in facade.calls)


def test_assistant_live_qualification_applies_rejects_replay_and_restores() -> None:
    facade = FakeFacade()

    result = runner.qualify(
        facade=facade, goal="Safely adjust the selected track",
        command="Set selected track pan to 10%", session_id="real-session", apply=True,
        planner_evidence_sha256="a" * 64,
    )

    assert result["status"] == "passed"
    assert result["replay_rejected"] is True
    assert result["restored_exactly"] is True
    assert result["assistant_task_completed"] is True
    assert result["planner_evidence_sha256"] == "a" * 64
    assert result["source_git_commit"] == runner.source_revision()
    assert result["runner_sha256"] == runner.runner_sha256()
    assert result["changed"] is False
    assert facade.mutated is False
    assert "secret" not in str(result)


@pytest.mark.parametrize("mismatch", ["write", "undo"])
def test_assistant_live_qualification_rejects_receipts_for_other_actions(mismatch: str) -> None:
    class MismatchedReceiptFacade(FakeFacade):
        def _dispatch(self, name: str, args: dict) -> dict:
            result = super()._dispatch(name, args)
            if (
                mismatch == "write"
                and name == "apply_live_proposal"
                and result.get("status") == "applied"
            ):
                result["receipt"]["action_id"] = "other-action"
            if (
                mismatch == "undo"
                and name == "undo_live_receipt"
                and "proposal" in args
                and result.get("status") == "applied"
            ):
                result["receipt"]["action_id"] = "other-undo"
            return result

    facade = MismatchedReceiptFacade()
    result = runner.qualify(
        facade=facade, goal="Safely adjust the selected track",
        command="Set selected track pan to 10%", session_id="real-session", apply=True,
    )

    assert result["status"] == "failed"
    assert result["restored_exactly"] is True
    assert result["changed"] is False
    assert facade.mutated is False


def test_assistant_live_qualification_fails_if_undo_does_not_restore_snapshot() -> None:
    facade = FakeFacade(restore=False)

    result = runner.qualify(
        facade=facade, goal="Safely adjust the selected track",
        command="Set selected track pan to 10%", session_id="real-session", apply=True,
    )

    assert result["status"] == "failed"
    assert result["restored_exactly"] is False
    assert result["changed"] is True


def test_replay_check_failure_still_attempts_and_verifies_undo() -> None:
    class ReplayFailureFacade(FakeFacade):
        apply_calls = 0

        def _dispatch(self, name: str, args: dict) -> dict:
            if name == "apply_live_proposal":
                self.apply_calls += 1
                if self.apply_calls == 2:
                    self.calls.append((name, args))
                    raise KennTransportError("response included proposal-secret")
            return super()._dispatch(name, args)

    facade = ReplayFailureFacade()
    result = runner.qualify(
        facade=facade, goal="Safely adjust the selected track",
        command="Set selected track pan to 10%", session_id="real-session", apply=True,
    )

    assert result["status"] == "failed"
    assert result["replay_rejected"] is False
    assert result["restored_exactly"] is True
    assert result["changed"] is False
    assert facade.mutated is False
    assert any(name == "undo_live_receipt" for name, _ in facade.calls)
    assert "proposal-secret" not in str(result)


def test_uncertain_undo_response_is_not_retried_and_snapshot_is_rechecked() -> None:
    class UncertainUndoFacade(FakeFacade):
        undo_apply_calls = 0

        def _dispatch(self, name: str, args: dict) -> dict:
            if name == "undo_live_receipt" and "proposal" in args:
                self.calls.append((name, args))
                self.undo_apply_calls += 1
                self.mutated = False  # Live restored before the response was lost.
                raise KennTransportError("response included undo-secret")
            return super()._dispatch(name, args)

    facade = UncertainUndoFacade()
    result = runner.qualify(
        facade=facade, goal="Safely adjust the selected track",
        command="Set selected track pan to 10%", session_id="real-session", apply=True,
    )

    assert result["status"] == "failed"
    assert result["restored_exactly"] is True
    assert result["changed"] is False
    assert result["retry_allowed"] is False
    assert result["recovery_required"] == []
    assert facade.undo_apply_calls == 1
    assert "undo-secret" not in str(result)


def test_recovery_snapshot_from_wrong_session_never_proves_restoration() -> None:
    class WrongSessionRecoveryFacade(FakeFacade):
        context_calls = 0

        def _context(self) -> dict:
            self.context_calls += 1
            context = super()._context()
            if self.context_calls > 1:
                context["session_id"] = "different-session"
                context["snapshot_fingerprint"] = "initial-fingerprint"
            return context

        def _dispatch(self, name: str, args: dict) -> dict:
            if name == "undo_live_receipt" and "proposal" in args:
                self.calls.append((name, args))
                raise KennTransportError("undo response interrupted")
            return super()._dispatch(name, args)

    facade = WrongSessionRecoveryFacade()
    result = runner.qualify(
        facade=facade, goal="Safely adjust the selected track",
        command="Set selected track pan to 10%", session_id="real-session", apply=True,
    )

    assert result["status"] == "transport_uncertain"
    assert result["restored_exactly"] is False
    assert result["changed"] is None
    assert result["recovery_required"] == ["live_receipts", "live_snapshot", "manual_restore"]


def test_assistant_live_qualification_never_retries_uncertain_apply() -> None:
    class UncertainFacade(FakeFacade):
        def _dispatch(self, name: str, args: dict) -> dict:
            if name == "apply_live_proposal":
                self.calls.append((name, args))
                raise KennTransportError("apply response was interrupted")
            return super()._dispatch(name, args)

    facade = UncertainFacade()
    result = runner.qualify(
        facade=facade, goal="Safely adjust the selected track",
        command="Set selected track pan to 10%", session_id="real-session", apply=True,
    )

    assert result["status"] == "failed"
    assert result["changed"] is False
    assert result["restored_exactly"] is True
    assert result["retry_allowed"] is False
    assert result["recovery_required"] == []
    assert sum(name == "apply_live_proposal" for name, _ in facade.calls) == 1
    assert sum(name == "kenn_context" for name, _ in facade.calls) == 2


def test_unexpected_apply_failure_is_redacted_and_never_retried() -> None:
    class BrokenApplyFacade(FakeFacade):
        def _dispatch(self, name: str, args: dict) -> dict:
            if name == "apply_live_proposal":
                self.calls.append((name, args))
                raise ValueError("decoder exposed proposal-secret")
            return super()._dispatch(name, args)

    facade = BrokenApplyFacade()
    result = runner.qualify(
        facade=facade, goal="Safely adjust the selected track",
        command="Set selected track pan to 10%", session_id="real-session", apply=True,
    )

    assert result["status"] == "failed"
    assert result["events"][-2]["error_type"] == "ValueError"
    assert result["restored_exactly"] is True
    assert result["retry_allowed"] is False
    assert sum(name == "apply_live_proposal" for name, _ in facade.calls) == 1
    assert "proposal-secret" not in str(result)


def test_malformed_apply_response_is_uncertain_and_never_retried() -> None:
    class MalformedApplyFacade(FakeFacade):
        def _dispatch(self, name: str, args: dict):
            if name == "apply_live_proposal":
                self.calls.append((name, args))
                self.mutated = True
                return None
            return super()._dispatch(name, args)

    facade = MalformedApplyFacade()
    result = runner.qualify(
        facade=facade, goal="Safely adjust the selected track",
        command="Set selected track pan to 10%", session_id="real-session", apply=True,
    )

    assert result["status"] == "transport_uncertain"
    assert result["events"][-2]["error_type"] == "TypeError"
    assert result["retry_allowed"] is False
    assert result["changed"] is True
    assert result["restored_exactly"] is False
    assert result["recovery_required"] == ["live_receipts", "live_snapshot", "manual_restore"]
    assert sum(name == "apply_live_proposal" for name, _ in facade.calls) == 1


def test_uncertain_apply_with_unavailable_recovery_snapshot_stays_unknown() -> None:
    class UnobservableApplyFacade(FakeFacade):
        context_calls = 0

        def _dispatch(self, name: str, args: dict):
            if name == "kenn_context":
                self.context_calls += 1
                if self.context_calls > 1:
                    raise KennTransportError("private recovery failure")
            if name == "apply_live_proposal":
                self.calls.append((name, args))
                self.mutated = True
                raise KennTransportError("private apply failure")
            return super()._dispatch(name, args)

    facade = UnobservableApplyFacade()
    result = runner.qualify(
        facade=facade, goal="Safely adjust the selected track",
        command="Set selected track pan to 10%", session_id="real-session", apply=True,
    )

    assert result["status"] == "transport_uncertain"
    assert result["changed"] is None
    assert result["restored_exactly"] is False
    assert result["retry_allowed"] is False
    assert result["recovery_required"] == ["live_receipts", "live_snapshot", "manual_restore"]
    assert sum(name == "apply_live_proposal" for name, _ in facade.calls) == 1
    assert "private" not in str(result)


def test_missing_undo_proposal_reports_changed_state_and_manual_recovery() -> None:
    class MissingUndoFacade(FakeFacade):
        def _dispatch(self, name: str, args: dict) -> dict:
            if name == "undo_live_receipt" and "proposal" not in args:
                self.calls.append((name, args))
                return {"ok": False, "status": "failed"}
            return super()._dispatch(name, args)

    facade = MissingUndoFacade()
    result = runner.qualify(
        facade=facade, goal="Safely adjust the selected track",
        command="Set selected track pan to 10%", session_id="real-session", apply=True,
    )

    assert result["status"] == "transport_uncertain"
    assert result["restored_exactly"] is False
    assert result["changed"] is True
    assert result["retry_allowed"] is False
    assert result["recovery_required"] == ["live_receipts", "live_snapshot", "manual_restore"]
    assert facade.mutated is True


def test_malformed_undo_response_rechecks_snapshot_without_retrying() -> None:
    class MalformedUndoFacade(FakeFacade):
        undo_apply_calls = 0

        def _dispatch(self, name: str, args: dict):
            if name == "undo_live_receipt" and "proposal" in args:
                self.calls.append((name, args))
                self.undo_apply_calls += 1
                self.mutated = False
                return None
            return super()._dispatch(name, args)

    facade = MalformedUndoFacade()
    result = runner.qualify(
        facade=facade, goal="Safely adjust the selected track",
        command="Set selected track pan to 10%", session_id="real-session", apply=True,
    )

    assert result["status"] == "failed"
    assert result["restored_exactly"] is True
    assert result["changed"] is False
    assert result["retry_allowed"] is False
    assert facade.undo_apply_calls == 1


def test_assistant_live_qualification_requires_task_ledger_completion() -> None:
    class UnboundFacade(FakeFacade):
        def _dispatch(self, name: str, args: dict) -> dict:
            result = super()._dispatch(name, args)
            if name == "apply_live_proposal" and result.get("status") == "applied":
                result.pop("assistant_task", None)
            return result

    facade = UnboundFacade()
    result = runner.qualify(
        facade=facade, goal="Safely adjust the selected track",
        command="Set selected track pan to 10%", session_id="real-session", apply=True,
    )

    assert result["status"] == "failed"
    assert result["changed"] is False
    assert result["restored_exactly"] is True
    assert facade.mutated is False
    assert "assistant-task completion" in result["error"]


def test_real_live_evidence_write_is_atomic_private_and_complete(tmp_path: Path) -> None:
    destination = tmp_path / "nested" / "evidence.json"
    result = {"schema": runner.SCHEMA, "status": "proposal_ready", "changed": False}

    runner.write_evidence(destination, result)

    assert json.loads(destination.read_text(encoding="utf-8")) == result
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    assert list(destination.parent.glob(".*.tmp")) == []


def test_context_evidence_keeps_identity_but_not_live_track_contents() -> None:
    summary = runner._context_summary({
        "schema": "kenn.session_context.v1",
        "session_id": "session-1",
        "snapshot_fingerprint": "fingerprint-1",
        "transport": {"status": "connected", "tempo": 128.0},
        "tracks": [{"index": 0, "name": "Private unreleased song title"}],
        "available_actions": ["inspect_live"],
        "producer_preferences": [{"text": "private preference"}],
    })

    assert summary["snapshot_fingerprint"] == "fingerprint-1"
    assert summary["track_count"] == 1
    assert summary["available_actions"] == ["inspect_live"]
    assert "Private unreleased song title" not in str(summary)
    assert "private preference" not in str(summary)


def test_qualified_planner_identity_binds_exact_artifact_and_model(tmp_path: Path) -> None:
    artifact = tmp_path / "planner.json"
    artifact.write_text(json.dumps({"recommended_model": "qualified-model"}), encoding="utf-8")

    digest = runner.qualified_planner_identity(artifact, "qualified-model")

    assert len(digest) == 64
    with pytest.raises(ValueError, match="exactly match"):
        runner.qualified_planner_identity(artifact, "lookalike-model")


def test_qualified_planner_provider_is_read_from_bound_artifact(tmp_path: Path) -> None:
    artifact = tmp_path / "bakeoff.json"
    artifact.write_text(json.dumps({
        "recommended_model": "qualified-model", "provider": "transformers",
    }), encoding="utf-8")

    assert runner.qualified_planner_provider(artifact) == "transformers"

    artifact.write_text(json.dumps({
        "recommended_model": "qualified-model", "provider": "unknown",
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="provider"):
        runner.qualified_planner_provider(artifact)


def test_transformers_bridge_identity_binds_source_and_model(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "bridge.py"
    source.write_text("reviewed bridge\n", encoding="utf-8")
    digest = runner.hashlib.sha256(source.read_bytes()).hexdigest()

    class Response:
        def __enter__(self): return self
        def __exit__(self, *_args): return None
        def read(self):
            return json.dumps({
                "models": [{"model": "qualified-model"}],
                "kenn_transport": {
                    "schema": "kenn.transformers_ollama_compat.v1",
                    "source_sha256": digest,
                },
            }).encode()

    monkeypatch.setattr(runner, "open_loopback_ollama", lambda *_args, **_kwargs: Response())
    assert runner.verify_transformers_transport(
        "http://127.0.0.1:11435", "qualified-model", source,
    ) == digest

    with pytest.raises(ValueError, match="identity"):
        runner.verify_transformers_transport(
            "http://127.0.0.1:11435", "different-model", source,
        )
