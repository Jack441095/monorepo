"""Specialist Evidence Validation, Conflict Resolution, and State Reconciliation."""

from __future__ import annotations

from typing import Any, List, Dict, Optional
from thursday.orchestration_models import SpecialistTask, SpecialistResult, TaskStatus
from thursday.company_state import CompanySnapshot

class SpecialistReconciliationService:
    def __init__(self) -> None:
        self._accepted_results: dict[str, SpecialistResult] = {}

    def validate_result(self, task: SpecialistTask, result: SpecialistResult) -> tuple[bool, str]:
        """Validate specialist result contracts and reject anomalies."""
        # 1. Task ID match
        if task.task_id != result.task_id:
            return False, "Task ID mismatch in result"
            
        # 2. Forbidden path check
        for path in result.files_modified:
            for forbidden in task.forbidden_targets:
                if forbidden in path:
                    return False, f"Unauthorized mutation of forbidden target: {path}"

        # 3. Exactly-once plan hash check
        expected_hash = task.calculate_plan_hash()
        if task.plan_hash and task.plan_hash != expected_hash:
            return False, "Plan hash mismatch — task envelope mutated after approval"

        # 4. Check for claim support (unsupported claims vs evidence)
        if result.status == "SUCCESS":
            if result.failures:
                return False, "Unsupported Claim: result reports SUCCESS but contains recorded failures"
            if result.confidence < 0.5:
                return False, "Unsupported Claim: result reports SUCCESS with low confidence"
                
        # 5. Check for injection attacks inside summary/evidence
        hostile_indicators = ("ignore previous instructions", "system override", "owner already approved", "modify main directly")
        for field_val in (result.summary, str(result.evidence)):
            for indicator in hostile_indicators:
                if indicator in field_val.lower():
                    return False, f"Malicious payload/injection detected in specialist output: '{indicator}'"

        return True, "Validation successful"

    def reconcile_results(self, tasks: dict[str, SpecialistTask], results: list[SpecialistResult]) -> dict[str, Any]:
        """Reconcile multiple specialist task outcomes conservatively.
        
        Conflict resolution: QA failure outranks engineering ready status.
        """
        outcome = {
            "status": "SUCCESS",
            "messages": [],
            "failed_tasks": [],
            "accepted_tasks": []
        }
        
        # Build status lookup map
        task_outcomes: dict[str, str] = {}
        for r in results:
            task = tasks.get(r.task_id)
            if not task:
                continue
                
            valid, msg = self.validate_result(task, r)
            if not valid:
                task.update_status(TaskStatus.REJECTED)
                outcome["status"] = "FAILED"
                outcome["messages"].append(f"Task {r.task_id} validation failed: {msg}")
                outcome["failed_tasks"].append(r.task_id)
                continue
                
            if r.status == "FAILED":
                task.update_status(TaskStatus.FAILED)
                task_outcomes[r.task_id] = "FAILED"
                outcome["failed_tasks"].append(r.task_id)
            elif r.status == "SUCCESS":
                task.update_status(TaskStatus.ACCEPTED)
                task_outcomes[r.task_id] = "SUCCESS"
                outcome["accepted_tasks"].append(r.task_id)
                self._accepted_results[r.task_id] = r
            else:
                task.update_status(TaskStatus.BLOCKED)
                task_outcomes[r.task_id] = "BLOCKED"
                
        # Conservative conflict resolution across DAG dependencies
        for t_id, task in tasks.items():
            # If any dependency failed, this task cannot be considered SUCCESS
            for dep in task.dependencies:
                dep_status = task_outcomes.get(dep)
                if dep_status == "FAILED":
                    task.update_status(TaskStatus.FAILED)
                    if t_id not in outcome["failed_tasks"]:
                        outcome["failed_tasks"].append(t_id)
                        
        if outcome["failed_tasks"]:
            outcome["status"] = "FAILED"
            outcome["messages"].append(f"Orchestration failure: {len(outcome['failed_tasks'])} tasks failed or blocked by conflicts.")
            
        return outcome
