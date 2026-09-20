"""Task and Result contracts for Thursday V2-D Orchestration Control Plane."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, List, Set, Dict, Optional

class TaskStatus:
    # Active states
    CREATED = "CREATED"
    VALIDATED = "VALIDATED"
    QUEUED = "QUEUED"
    DISPATCHED = "DISPATCHED"
    RUNNING = "RUNNING"
    RESULT_RECEIVED = "RESULT_RECEIVED"
    VALIDATING = "VALIDATING"
    
    # Terminal/Exit states
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    NEEDS_APPROVAL = "NEEDS_APPROVAL"
    STALE = "STALE"

VALID_TRANSITIONS = {
    TaskStatus.CREATED: {TaskStatus.VALIDATED, TaskStatus.REJECTED, TaskStatus.CANCELLED},
    TaskStatus.VALIDATED: {TaskStatus.QUEUED, TaskStatus.REJECTED, TaskStatus.NEEDS_APPROVAL, TaskStatus.CANCELLED},
    TaskStatus.QUEUED: {TaskStatus.DISPATCHED, TaskStatus.BLOCKED, TaskStatus.CANCELLED},
    TaskStatus.DISPATCHED: {TaskStatus.RUNNING, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.RUNNING: {TaskStatus.RESULT_RECEIVED, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.BLOCKED},
    TaskStatus.RESULT_RECEIVED: {TaskStatus.VALIDATING, TaskStatus.FAILED, TaskStatus.REJECTED},
    TaskStatus.VALIDATING: {TaskStatus.ACCEPTED, TaskStatus.REJECTED, TaskStatus.NEEDS_APPROVAL, TaskStatus.FAILED, TaskStatus.STALE},
    # Terminal states can be updated to STALE if environment/code SHA changes
    TaskStatus.ACCEPTED: {TaskStatus.STALE},
    TaskStatus.REJECTED: {TaskStatus.CREATED},
    TaskStatus.FAILED: {TaskStatus.CREATED},
    TaskStatus.BLOCKED: {TaskStatus.QUEUED, TaskStatus.CANCELLED},
    TaskStatus.NEEDS_APPROVAL: {TaskStatus.QUEUED, TaskStatus.REJECTED, TaskStatus.CANCELLED},
}

@dataclass
class SpecialistTask:
    task_id: str
    parent_objective_id: str
    specialist_id: str
    task_type: str
    objective: str
    scope: str
    inputs: dict[str, Any] = field(default_factory=dict)
    permissions: list[str] = field(default_factory=list)
    forbidden_targets: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    status: str = TaskStatus.CREATED
    plan_hash: str = ""
    idempotency_key: str = ""
    
    def calculate_plan_hash(self) -> str:
        """Calculate a deterministic hash of the task envelope to prevent modification after approval."""
        payload = {
            "task_id": self.task_id,
            "parent_objective_id": self.parent_objective_id,
            "specialist_id": self.specialist_id,
            "objective": self.objective,
            "scope": self.scope,
            "inputs": self.inputs,
            "permissions": sorted(self.permissions),
            "forbidden_targets": sorted(self.forbidden_targets),
            "dependencies": sorted(self.dependencies)
        }
        serialized = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def update_status(self, new_status: str) -> None:
        """Safely transition task status checking rules."""
        allowed = VALID_TRANSITIONS.get(self.status, set())
        if new_status not in allowed:
            raise ValueError(f"Invalid transition from {self.status} to {new_status}")
        self.status = new_status


@dataclass
class SpecialistResult:
    task_id: str
    status: str  # SUCCESS, FAILED, ABSTAINED, BLOCKED
    summary: str
    evidence: dict[str, Any] = field(default_factory=dict)
    files_inspected: list[str] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    starting_sha: str = ""
    ending_sha: str = ""
    tests_executed: int = 0
    test_results: dict[str, Any] = field(default_factory=dict)
    artifacts: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    confidence: float = 1.0
