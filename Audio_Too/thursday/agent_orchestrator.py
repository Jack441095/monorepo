"""Company Orchestrator, Dependency DAG, and Resource Scheduler for Thursday V2-D."""

from __future__ import annotations

import collections
import subprocess
from dataclasses import dataclass, field
from typing import Any, List, Set, Dict, Optional
from thursday.orchestration_models import SpecialistTask, TaskStatus
from thursday.specialists import REGISTRY

@dataclass
class ResourceUsage:
    heavy_running: int = 0
    medium_running: int = 0
    light_running: int = 0

class RepositoryOwnershipService:
    def __init__(self, workspace_path: str) -> None:
        self.workspace_path = workspace_path
        self._leases: dict[str, dict[str, Any]] = {}

    def inspect_ownership(self) -> str:
        """Inspect workspace state to classify ownership safety."""
        try:
            res = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.workspace_path,
                capture_output=True,
                text=True,
                check=True
            )
            output = res.stdout.strip()
            if not output:
                return "OWNED_CLEAN"
            return "OWNED_DIRTY"
        except Exception:
            return "AMBIGUOUS"

    def acquire_lease(self, workstream: str, owner: str, duration_sec: float = 300) -> bool:
        import time
        now = time.time()
        # Clean stale leases
        self._leases = {k: v for k, v in self._leases.items() if v["expires_at"] > now}
        
        if workstream in self._leases:
            if self._leases[workstream]["owner"] != owner:
                return False
        
        self._leases[workstream] = {
            "owner": owner,
            "expires_at": now + duration_sec
        }
        return True

    def release_lease(self, workstream: str, owner: str) -> bool:
        if workstream in self._leases:
            if self._leases[workstream]["owner"] == owner:
                del self._leases[workstream]
                return True
        return False


class CompanyOrchestrator:
    def __init__(self, workspace_path: str) -> None:
        self.workspace_path = workspace_path
        self.tasks: dict[str, SpecialistTask] = {}
        self.ownership = RepositoryOwnershipService(workspace_path)
        self.resources = ResourceUsage()
        self.concurrency_limits = {
            "HEAVY": 2,
            "MEDIUM": 3,
            "LIGHT": 10
        }

    def decompose_objective(self, objective_id: str, description: str) -> list[SpecialistTask]:
        """Decompose a broad company objective into bounded specialist tasks."""
        desc_lower = description.lower()
        tasks = []
        
        if "smart sample manager" in desc_lower and "beta" in desc_lower:
            # Standard decomposition from मेगा Prompt
            tasks = [
                SpecialistTask(
                    task_id=f"{objective_id}-build",
                    parent_objective_id=objective_id,
                    specialist_id="release_engineering",
                    task_type="HEAVY",
                    objective="Qualify release candidate build",
                    scope="build_staging"
                ),
                SpecialistTask(
                    task_id=f"{objective_id}-qa",
                    parent_objective_id=objective_id,
                    specialist_id="qa",
                    task_type="MEDIUM",
                    objective="Run full regression test suite",
                    scope="test_directory",
                    dependencies=[f"{objective_id}-build"]
                ),
                SpecialistTask(
                    task_id=f"{objective_id}-product",
                    parent_objective_id=objective_id,
                    specialist_id="product",
                    task_type="LIGHT",
                    objective="Audit beta tester user journey",
                    scope="product_specs"
                ),
                SpecialistTask(
                    task_id=f"{objective_id}-docs",
                    parent_objective_id=objective_id,
                    specialist_id="documentation",
                    task_type="LIGHT",
                    objective="Prepare beta installation guide",
                    scope="docs_directory"
                )
            ]
        else:
            # General generic fallback decomposition
            tasks = [
                SpecialistTask(
                    task_id=f"{objective_id}-eng",
                    parent_objective_id=objective_id,
                    specialist_id=REGISTRY.route_task("engineering", description),
                    task_type="MEDIUM",
                    objective=description,
                    scope="owned_worktree"
                )
            ]
            
        for t in tasks:
            t.plan_hash = t.calculate_plan_hash()
            self.tasks[t.task_id] = t
            
        return tasks

    def has_cycles(self) -> bool:
        """Detect cycle in dependency graph using DFS."""
        visited: dict[str, int] = {}  # 0=unvisited, 1=visiting, 2=visited
        
        def dfs(task_id: str) -> bool:
            visited[task_id] = 1
            task = self.tasks.get(task_id)
            if task:
                for dep in task.dependencies:
                    if visited.get(dep, 0) == 1:
                        return True  # Cycle detected
                    if visited.get(dep, 0) == 0:
                        if dfs(dep):
                            return True
            visited[task_id] = 2
            return False

        for t_id in self.tasks:
            if visited.get(t_id, 0) == 0:
                if dfs(t_id):
                    return True
        return False

    def get_runnable_tasks(self) -> list[SpecialistTask]:
        """Get tasks whose dependencies are fully completed (ACCEPTED status)."""
        runnable = []
        for t in self.tasks.values():
            if t.status in (TaskStatus.CREATED, TaskStatus.QUEUED):
                deps_met = True
                for dep_id in t.dependencies:
                    dep_task = self.tasks.get(dep_id)
                    if not dep_task or dep_task.status != TaskStatus.ACCEPTED:
                        deps_met = False
                        break
                if deps_met:
                    runnable.append(t)
        return runnable

    def schedule_tasks(self) -> list[str]:
        """Schedule runnable tasks respecting concurrency limits."""
        dispatched_ids = []
        runnable = self.get_runnable_tasks()
        
        for t in runnable:
            t_type = t.task_type
            if t.status == TaskStatus.CREATED:
                t.update_status(TaskStatus.VALIDATED)
                
            if t_type == "HEAVY":
                if self.resources.heavy_running < self.concurrency_limits["HEAVY"]:
                    self.resources.heavy_running += 1
                    t.update_status(TaskStatus.QUEUED)
                    t.update_status(TaskStatus.DISPATCHED)
                    dispatched_ids.append(t.task_id)
            elif t_type == "MEDIUM":
                if self.resources.medium_running < self.concurrency_limits["MEDIUM"]:
                    self.resources.medium_running += 1
                    t.update_status(TaskStatus.QUEUED)
                    t.update_status(TaskStatus.DISPATCHED)
                    dispatched_ids.append(t.task_id)
            else:
                if self.resources.light_running < self.concurrency_limits["LIGHT"]:
                    self.resources.light_running += 1
                    t.update_status(TaskStatus.QUEUED)
                    t.update_status(TaskStatus.DISPATCHED)
                    dispatched_ids.append(t.task_id)
                    
        return dispatched_ids

    def complete_task(self, task_id: str, success: bool) -> None:
        """Release resources occupied by task on completion."""
        t = self.tasks.get(task_id)
        if not t:
            return
            
        t_type = t.task_type
        if t.status == TaskStatus.DISPATCHED or t.status == TaskStatus.RUNNING:
            if t_type == "HEAVY":
                self.resources.heavy_running = max(0, self.resources.heavy_running - 1)
            elif t_type == "MEDIUM":
                self.resources.medium_running = max(0, self.resources.medium_running - 1)
            else:
                self.resources.light_running = max(0, self.resources.light_running - 1)
                
        if success:
            t.status = TaskStatus.ACCEPTED
        else:
            t.status = TaskStatus.FAILED
