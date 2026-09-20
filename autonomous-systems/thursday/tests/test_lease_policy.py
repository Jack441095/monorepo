"""thursday/lease_policy.py — the V2-E sandbox lease/security guard
(docs/THURSDAY_EXECUTION_LEASE_POLICY_V1.md / THURSDAY_LEASE_AND_SANDBOX_
MODEL.md). Covers issue_lease() and the fail-closed checks in
validate_lease_write_attempt() -- shadow mode, unknown lease, expiry,
read-only, stale SHA, and path traversal -- each independently, so a future
edit can't quietly reorder or drop one of these checks.
"""

from __future__ import annotations

import time

from thursday.lease_policy import SandboxLeasePolicy


def test_issue_lease_uses_workspace_env_override(monkeypatch) -> None:
    monkeypatch.setenv("THURSDAY_AUDIO_TOO_WORKSPACE", "/tmp/fake-workspace")
    policy = SandboxLeasePolicy()
    receipt = policy.issue_lease("task-1", "/tmp/worktree", ["/tmp/worktree"])
    assert receipt.workspace == "/tmp/fake-workspace"
    assert receipt.task_id == "task-1"
    assert receipt.read_only is True  # default


def test_write_rejected_when_shadow_mode_disables_writes() -> None:
    policy = SandboxLeasePolicy()
    receipt = policy.issue_lease("t", "/wt", ["/wt"], read_only=False)
    ok, reason = policy.validate_lease_write_attempt(
        receipt.lease_id, "/wt/file.py", receipt.source_sha, write_enabled=False,
    )
    assert ok is False
    assert "Shadow Mode" in reason


def test_write_rejected_for_unknown_lease_id() -> None:
    policy = SandboxLeasePolicy()
    ok, reason = policy.validate_lease_write_attempt(
        "no-such-lease", "/wt/file.py", "", write_enabled=True,
    )
    assert ok is False
    assert "Invalid lease" in reason


def test_write_rejected_for_expired_lease() -> None:
    policy = SandboxLeasePolicy()
    receipt = policy.issue_lease("t", "/wt", ["/wt"], duration=-1, read_only=False)
    assert receipt.expires_at < time.time()
    ok, reason = policy.validate_lease_write_attempt(
        receipt.lease_id, "/wt/file.py", "", write_enabled=True,
    )
    assert ok is False
    assert "expired" in reason


def test_write_rejected_on_read_only_lease() -> None:
    policy = SandboxLeasePolicy()
    receipt = policy.issue_lease("t", "/wt", ["/wt"], read_only=True)
    ok, reason = policy.validate_lease_write_attempt(
        receipt.lease_id, "/wt/file.py", "", write_enabled=True,
    )
    assert ok is False
    assert "read-only lease" in reason


def test_write_rejected_when_sha_is_stale() -> None:
    policy = SandboxLeasePolicy()
    receipt = policy.issue_lease("t", "/wt", ["/wt"], read_only=False, sha="abc123")
    ok, reason = policy.validate_lease_write_attempt(
        receipt.lease_id, "/wt/file.py", "def456", write_enabled=True,
    )
    assert ok is False
    assert "stale" in reason


def test_write_rejected_for_path_traversal() -> None:
    # The traversal check runs on os.path.normpath(path): an absolute path
    # like "/wt/../../etc/passwd" normalizes straight to "/etc/passwd" with
    # no ".." segments left, so it's actually the *allowed-paths* check that
    # catches that case (see test_write_rejected_outside_allowed_paths).
    # This check fires for a relative path that still points above cwd
    # after normalization -- e.g. one that arrived without the leading "/"
    # a caller is supposed to always provide.
    policy = SandboxLeasePolicy()
    receipt = policy.issue_lease("t", "/wt", ["/wt"], read_only=False)
    ok, reason = policy.validate_lease_write_attempt(
        receipt.lease_id, "../../etc/passwd", receipt.source_sha, write_enabled=True,
    )
    assert ok is False
    assert "traversal" in reason


def test_write_rejected_outside_allowed_paths() -> None:
    policy = SandboxLeasePolicy()
    receipt = policy.issue_lease("t", "/wt", ["/wt/allowed"], read_only=False)
    ok, reason = policy.validate_lease_write_attempt(
        receipt.lease_id, "/wt/forbidden/file.py", receipt.source_sha, write_enabled=True,
    )
    assert ok is False
    assert "outside allowed lease path" in reason


def test_write_accepted_when_every_check_passes() -> None:
    policy = SandboxLeasePolicy()
    receipt = policy.issue_lease("t", "/wt", ["/wt/allowed"], read_only=False, sha="abc123")
    ok, reason = policy.validate_lease_write_attempt(
        receipt.lease_id, "/wt/allowed/file.py", "abc123", write_enabled=True,
    )
    assert ok is True
    assert reason == "Lease is valid for write"
