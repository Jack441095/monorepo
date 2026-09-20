"""Worktree Lease Policy and Sandbox Security Guards for Thursday V2-E."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

@dataclass
class LeaseReceipt:
    lease_id: str
    task_id: str
    workspace: str
    worktree: str
    allowed_paths: list[str] = field(default_factory=list)
    read_only: bool = True
    owner: str = "thursday"
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    source_sha: str = ""

class SandboxLeasePolicy:
    def __init__(self) -> None:
        self._leases: dict[str, LeaseReceipt] = {}

    def issue_lease(self, task_id: str, worktree: str, allowed_paths: list[str], duration: float = 300, sha: str = "", read_only: bool = True) -> LeaseReceipt:
        lease_id = f"lease-{task_id}-{int(time.time())}"
        receipt = LeaseReceipt(
            lease_id=lease_id,
            task_id=task_id,
            workspace="/Volumes/Jack_Gandy_1TB_SSD/Audio_Engineering_Company/Audio_Too",
            worktree=worktree,
            allowed_paths=allowed_paths,
            read_only=read_only,
            expires_at=time.time() + duration,
            source_sha=sha
        )
        self._leases[lease_id] = receipt
        return receipt

    def validate_lease_write_attempt(self, lease_id: str, path: str, current_sha: str, write_enabled: bool) -> tuple[bool, str]:
        """Validate lease validity and block escapes (fails closed)."""
        # 1. Structural Shadow mode override check
        if not write_enabled:
            return False, "FORBIDDEN: Write attempt rejected. Friday/Thursday is running in READ-ONLY Shadow Mode."

        lease = self._leases.get(lease_id)
        if not lease:
            return False, "FORBIDDEN: Invalid lease ID. No active lease found."
            
        # 2. Expiry check
        if time.time() > lease.expires_at:
            return False, "FORBIDDEN: Lease has expired."
            
        # 3. Read-only policy constraint check
        if lease.read_only:
            return False, "FORBIDDEN: Write attempt rejected on read-only lease."

        # 4. SHA change/stale check
        if lease.source_sha and lease.source_sha != current_sha:
            return False, "FORBIDDEN: Codebase SHA changed after lease issuance. Lease is stale."

        # 5. Path traversal security checks
        norm_path = os.path.normpath(path)
        if ".." in norm_path or norm_path.startswith("../"):
            return False, "FORBIDDEN: Path traversal attempt detected (symlink/relative escape)."
            
        allowed = False
        for ok_path in lease.allowed_paths:
            if norm_path.startswith(os.path.normpath(ok_path)):
                allowed = True
                break
                
        if not allowed:
            return False, f"FORBIDDEN: Mutation target outside allowed lease path: {norm_path}"
            
        return True, "Lease is valid for write"


def macos_sandboxing_recommendation() -> str:
    """Returns the evidence-based recommendation study for future macOS containerization."""
    return (
        "NITE DSP macOS Isolation Study:\n"
        "1. sandbox-exec: C-level sandbox API. Offers fine-grained filesystem control but deprecated in newer macOS.\n"
        "2. Filesystem ACLs: Dedicated local user context (e.g., '_thursday_worker') with POSIX ACLs restricted to staging worktrees.\n"
        "3. Git Worktrees: Separate local checkouts per task prevent head/index contamination on master.\n"
        "Recommendation for V2-F: Implement dedicated task-scoped git worktrees run under a restricted temporary OS user with ACL confinement."
    )
