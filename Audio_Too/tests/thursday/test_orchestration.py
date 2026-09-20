"""Unit tests for Thursday V2-D Specialist Orchestration Control Plane."""

from __future__ import annotations

import pytest
from thursday.specialists import REGISTRY, SpecialistManifest
from thursday.orchestration_models import SpecialistTask, SpecialistResult, TaskStatus
from thursday.agent_orchestrator import CompanyOrchestrator
from thursday.reconciliation import SpecialistReconciliationService

def test_specialist_registration():
    spec = REGISTRY.get("engineering")
    assert spec is not None
    assert "owned_worktree" in spec.allowed_domains
    assert "production_database" in spec.forbidden_domains

def test_task_state_machine():
    task = SpecialistTask(
        task_id="t1", parent_objective_id="o1", specialist_id="engineering",
        task_type="LIGHT", objective="Test", scope="s"
    )
    assert task.status == TaskStatus.CREATED
    task.update_status(TaskStatus.VALIDATED)
    assert task.status == TaskStatus.VALIDATED
    
    with pytest.raises(ValueError):
        task.update_status(TaskStatus.ACCEPTED)

def test_plan_hash_immutability():
    task = SpecialistTask(
        task_id="t1", parent_objective_id="o1", specialist_id="engineering",
        task_type="LIGHT", objective="Test", scope="s"
    )
    h1 = task.calculate_plan_hash()
    task.objective = "Test Mutated"
    h2 = task.calculate_plan_hash()
    assert h1 != h2

def test_dependency_cycle_detection():
    orchestrator = CompanyOrchestrator("/Volumes/Jack_Gandy_1TB_SSD/Audio_Engineering_Company/Audio_Too")
    orchestrator.tasks["t1"] = SpecialistTask("t1", "o", "eng", "LIGHT", "Test", "s", dependencies=["t2"])
    orchestrator.tasks["t2"] = SpecialistTask("t2", "o", "eng", "LIGHT", "Test", "s", dependencies=["t1"])
    assert orchestrator.has_cycles() is True

def test_resource_budgets():
    orchestrator = CompanyOrchestrator("/Volumes/Jack_Gandy_1TB_SSD/Audio_Engineering_Company/Audio_Too")
    orchestrator.tasks["h1"] = SpecialistTask("h1", "o", "eng", "HEAVY", "Heavy 1", "s")
    orchestrator.tasks["h2"] = SpecialistTask("h2", "o", "eng", "HEAVY", "Heavy 2", "s")
    orchestrator.tasks["h3"] = SpecialistTask("h3", "o", "eng", "HEAVY", "Heavy 3", "s")
    
    dispatched = orchestrator.schedule_tasks()
    assert len(dispatched) == 2
    assert orchestrator.resources.heavy_running == 2

def test_forbidden_mutation_prevention():
    recon = SpecialistReconciliationService()
    task = SpecialistTask("t1", "o", "eng", "LIGHT", "Test", "s", forbidden_targets=["production_db"])
    res = SpecialistResult("t1", "SUCCESS", "Summary", files_modified=["/etc/production_db"])
    valid, msg = recon.validate_result(task, res)
    assert not valid
    assert "Unauthorized mutation" in msg

def test_claim_support():
    recon = SpecialistReconciliationService()
    task = SpecialistTask("t1", "o", "eng", "LIGHT", "Test", "s")
    res = SpecialistResult("t1", "SUCCESS", "Summary", failures=["Something crashed"])
    valid, msg = recon.validate_result(task, res)
    assert not valid
    assert "failures" in msg.lower()
