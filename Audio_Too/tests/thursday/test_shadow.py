"""Unit tests for Thursday V2-E Live Shadow Mode and Sandbox Confinement."""

from __future__ import annotations

import time
import pytest
from thursday.shadow_snapshot import CompanySnapshotV2, HostSystemMetrics, collect_host_metrics
from thursday.shadow_planner import ShadowPlanner, detect_stalls
from thursday.lease_policy import SandboxLeasePolicy, macos_sandboxing_recommendation
from thursday.shadow_adapters import ADAPTERS

def test_shadow_adapters_read_only():
    for name, adapter in ADAPTERS.items():
        assert adapter.read_only is True
        assert "*" in adapter.forbidden_writes

def test_host_metrics_collection():
    metrics = collect_host_metrics(["python3"])
    assert metrics.cpu_percent >= 0.0
    assert metrics.memory_percent >= 0.0
    assert len(metrics.load_avg) == 3

def test_lease_validation_escapes():
    policy = SandboxLeasePolicy()
    lease = policy.issue_lease("t1", "worktree_a", ["worktree_a/staging"], sha="abc", read_only=False)
    
    # 1. Normal write blocked by shadow mode lock
    valid, msg = policy.validate_lease_write_attempt(lease.lease_id, "worktree_a/staging/file.txt", "abc", write_enabled=False)
    assert not valid
    assert "READ-ONLY Shadow Mode" in msg
    
    # 2. Write attempt outside allowed paths
    valid, msg = policy.validate_lease_write_attempt(lease.lease_id, "worktree_b/staging/file.txt", "abc", write_enabled=True)
    assert not valid
    assert "outside allowed lease path" in msg
    
    # 3. Path traversal escape
    valid, msg = policy.validate_lease_write_attempt(lease.lease_id, "worktree_a/staging/../../../etc/passwd", "abc", write_enabled=True)
    assert not valid
    assert "Path traversal attempt" in msg

    # 4. Stale SHA check
    valid, msg = policy.validate_lease_write_attempt(lease.lease_id, "worktree_a/staging/file.txt", "def", write_enabled=True)
    assert not valid
    assert "stale" in msg.lower()

def test_sandboxing_study():
    study = macos_sandboxing_recommendation()
    assert "macOS Isolation Study" in study
    assert "V2-F" in study
