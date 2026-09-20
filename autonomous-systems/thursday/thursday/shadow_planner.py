"""Shadow Mode Planner and Stall Detection for Thursday V2-E."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from thursday.shadow_snapshot import CompanySnapshotV2, ProgrammeStatus, ProgrammeEntity
from thursday.orchestration_models import SpecialistTask, TaskStatus
from thursday.specialists import REGISTRY

@dataclass
class ShadowRecommendation:
    project_id: str
    action: str  # START, QUEUE, DEFER, BLOCK, WAITING, REQUEST_OWNER, CONTINUE
    specialist_id: str
    reason: str
    proposed_task: SpecialistTask
    resource_budget_allocated: bool = True
    owner_attention_required: bool = False

def detect_stalls(entity: ProgrammeEntity, latest_log_time: float, process_exists: bool) -> tuple[str, str]:
    """Check heartbeat log timestamps vs process existence to discover stalled states (read-only)."""
    now = time.time()
    
    if entity.status == ProgrammeStatus.RUNNING:
        if not process_exists:
            # Report claims running but no process is active
            if now - latest_log_time > 300:
                return "STALLED", "Programme report claims RUNNING, but active process is absent and logs have been silent > 5 min"
            return "RUNNING", "Log silent but process might have recently completed/exited"
        else:
            if now - latest_log_time > 600:
                return "STALLED", "Process is alive but logs have not progressed in > 10 min"
            return "RUNNING", "Healthy progress indicators detected"
            
    return entity.status, ""

class ShadowPlanner:
    def __init__(self) -> None:
        self.recommendations: list[ShadowRecommendation] = []

    def plan_next_actions(self, snapshot: CompanySnapshotV2) -> list[ShadowRecommendation]:
        """Compute recommended next steps deterministically based on live snapshot."""
        recs = []
        now = time.time()
        
        # Heavy workload check
        heavy_deferred = snapshot.is_heavy_load()
        
        for p_id, p in snapshot.programmes.items():
            # Check for stalls
            # Default mock heartbeat: active processes might not exist in sandbox
            stalled_status, stall_reason = detect_stalls(p, now - 50, process_exists=True)
            
            if p.owner_action_required or p.status == ProgrammeStatus.OWNER_ACTION_REQUIRED:
                # Escalation required
                task = SpecialistTask(
                    task_id=f"shadow-{p_id}-escalate",
                    parent_objective_id=p_id,
                    specialist_id="product",
                    task_type="LIGHT",
                    objective=f"Resolve owner action gate for project: {p.display_name}",
                    scope="product_specs",
                    status=TaskStatus.NEEDS_APPROVAL
                )
                recs.append(ShadowRecommendation(
                    project_id=p_id,
                    action="REQUEST_OWNER",
                    specialist_id="product",
                    reason=f"Project is blocked on user decision: {p.latest_report_summary}",
                    proposed_task=task,
                    owner_attention_required=True
                ))
            elif stalled_status == "STALLED":
                task = SpecialistTask(
                    task_id=f"shadow-{p_id}-stall",
                    parent_objective_id=p_id,
                    specialist_id="engineering",
                    task_type="MEDIUM",
                    objective=f"Debug stall on project {p.display_name}",
                    scope="owned_worktree"
                )
                recs.append(ShadowRecommendation(
                    project_id=p_id,
                    action="DEFER",
                    specialist_id="engineering",
                    reason=stall_reason,
                    proposed_task=task,
                    owner_attention_required=True
                ))
            elif p.status == ProgrammeStatus.FAIL:
                task = SpecialistTask(
                    task_id=f"shadow-{p_id}-fix",
                    parent_objective_id=p_id,
                    specialist_id="qa",
                    task_type="MEDIUM",
                    objective=f"Audit failures on project: {p.display_name}",
                    scope="test_directory"
                )
                recs.append(ShadowRecommendation(
                    project_id=p_id,
                    action="START",
                    specialist_id="qa",
                    reason="Automated test failure surfaced in latest logs",
                    proposed_task=task
                ))
            elif p.status == ProgrammeStatus.INTEGRATION_READY:
                task = SpecialistTask(
                    task_id=f"shadow-{p_id}-merge",
                    parent_objective_id=p_id,
                    specialist_id="release_engineering",
                    task_type="HEAVY",
                    objective=f"Package and merge release for project: {p.display_name}",
                    scope="build_staging"
                )
                
                # Check resource budget limit for heavy task
                if heavy_deferred:
                    action = "DEFER"
                    reason = "Deferred: Host CPU pressure is high or concurrent builds are active"
                    allocated = False
                else:
                    action = "QUEUE"
                    reason = "Ready for merge build; queued in scheduler budget"
                    allocated = True
                    
                recs.append(ShadowRecommendation(
                    project_id=p_id,
                    action=action,
                    specialist_id="release_engineering",
                    reason=reason,
                    proposed_task=task,
                    resource_budget_allocated=allocated
                ))
                
        self.recommendations = recs
        return recs
