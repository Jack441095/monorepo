"""Extensible Specialist Agent Registry for Thursday V2-D."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, List, Set, Dict, Optional
from thursday.orchestration_models import SpecialistTask, SpecialistResult

@dataclass
class SpecialistManifest:
    specialist_id: str
    version: str
    capabilities: list[str] = field(default_factory=list)
    allowed_domains: list[str] = field(default_factory=list)
    forbidden_domains: list[str] = field(default_factory=list)
    required_approvals: list[str] = field(default_factory=list)
    max_delegation_depth: int = 0
    can_modify_company_state: bool = False

class SpecialistRegistry:
    def __init__(self) -> None:
        self._specialists: dict[str, SpecialistManifest] = {}

    def register(self, manifest: SpecialistManifest) -> None:
        self._specialists[manifest.specialist_id] = manifest

    def get(self, specialist_id: str) -> Optional[SpecialistManifest]:
        return self._specialists.get(specialist_id)

    def list_all(self) -> list[SpecialistManifest]:
        return list(self._specialists.values())

    def route_task(self, task_type: str, objective: str) -> str:
        """Route a task deterministically based on type, capability, and keywords.
        
        LLM routing can fallback here, but deterministic constraints must be absolute.
        """
        obj_lower = objective.lower()
        
        # 1. Deterministic rules
        if "security" in obj_lower or "credentials" in obj_lower or "license" in obj_lower or "signing" in obj_lower:
            return "security"
        if "build failure" in obj_lower or "package" in obj_lower or "tar.gz" in obj_lower or "deploy" in obj_lower or "artifact" in obj_lower or "tarball" in obj_lower:
            return "release_engineering"
        if "test failure" in obj_lower or "regression" in obj_lower or "qa" in obj_lower or "audit" in obj_lower:
            return "qa"
        if "documentation" in obj_lower or "readme" in obj_lower or "docs" in obj_lower or "guide" in obj_lower:
            return "documentation"
        if "commercial" in obj_lower or "invoice" in obj_lower or "pricing" in obj_lower or "billing" in obj_lower or "revenue" in obj_lower:
            return "commercial"
        if "customer" in obj_lower or "ticket" in obj_lower or "support" in obj_lower:
            return "support"
        if "research" in obj_lower or "market" in obj_lower or "analysis" in obj_lower:
            return "research"
        if "compile" in obj_lower or "code" in obj_lower or "refactor" in obj_lower or "implementation" in obj_lower or "fix" in obj_lower:
            return "engineering"
        if "product" in obj_lower or "journey" in obj_lower or "user story" in obj_lower or "requirement" in obj_lower:
            return "product"
            
        # 2. Check capability registry fallback
        for spec in self.list_all():
            for cap in spec.capabilities:
                if cap in obj_lower:
                    return spec.specialist_id
                    
        return "engineering"  # General fallback

# Global Registry instance
REGISTRY = SpecialistRegistry()

# Initialize default specialist manifests
DEFAULT_SPECIALISTS = [
    SpecialistManifest(
        specialist_id="engineering",
        version="1.0.0",
        capabilities=["compile", "code", "implementation", "refactor"],
        allowed_domains=["owned_worktree"],
        forbidden_domains=["production_database", "customer_data"],
        required_approvals=["local_write"]
    ),
    SpecialistManifest(
        specialist_id="release_engineering",
        version="1.0.0",
        capabilities=["build", "package", "deploy"],
        allowed_domains=["build_staging"],
        forbidden_domains=["production_database"],
        required_approvals=["external_write", "production_mutation"]
    ),
    SpecialistManifest(
        specialist_id="product",
        version="1.0.0",
        capabilities=["product_design", "requirements"],
        allowed_domains=["product_specs"],
        forbidden_domains=[],
        required_approvals=[]
    ),
    SpecialistManifest(
        specialist_id="qa",
        version="1.0.0",
        capabilities=["regression", "testing", "quality_audit"],
        allowed_domains=["test_directory"],
        forbidden_domains=["production_database"],
        required_approvals=[]
    ),
    SpecialistManifest(
        specialist_id="research",
        version="1.0.0",
        capabilities=["market_analysis", "research"],
        allowed_domains=["temp_sandbox"],
        forbidden_domains=[],
        required_approvals=[]
    ),
    SpecialistManifest(
        specialist_id="commercial",
        version="1.0.0",
        capabilities=["pricing", "billing", "invoicing", "revenue"],
        allowed_domains=["commercial_sandbox"],
        forbidden_domains=["live_billing_system"],
        required_approvals=["external_write"]
    ),
    SpecialistManifest(
        specialist_id="support",
        version="1.0.0",
        capabilities=["support_tickets", "customer_relations"],
        allowed_domains=["support_sandbox"],
        forbidden_domains=["customer_live_emails"],
        required_approvals=["external_write"]
    ),
    SpecialistManifest(
        specialist_id="documentation",
        version="1.0.0",
        capabilities=["readme", "documentation", "installation_guide"],
        allowed_domains=["docs_directory"],
        forbidden_domains=[],
        required_approvals=["local_write"]
    ),
    SpecialistManifest(
        specialist_id="security",
        version="1.0.0",
        capabilities=["licensing", "security_audit", "signing"],
        allowed_domains=["security_keys"],
        forbidden_domains=["private_credentials"],
        required_approvals=["external_write"]
    ),
    SpecialistManifest(
        specialist_id="data",
        version="1.0.0",
        capabilities=["data_analysis", "telemetry"],
        allowed_domains=["analytics_sandbox"],
        forbidden_domains=[],
        required_approvals=[]
    )
]

for s in DEFAULT_SPECIALISTS:
    REGISTRY.register(s)


def run_specialist_with_llm(task: SpecialistTask) -> SpecialistResult:
    """Connect a limited real provider-backed specialist for documentation/research (no external writes)."""
    try:
        from nite_core.model_runtime import DEFAULT_LLM
    except ImportError:
        return SpecialistResult(
            task_id=task.task_id,
            status="FAILED",
            summary="LLM Model runtime unavailable",
            failures=["ImportError: audio_too.model_runtime"]
        )

    system_prompt = (
        f"You are the NITE DSP {task.specialist_id} specialist.\n"
        "Analyze the objective and input data, then return a structured JSON response matching the SpecialistResult schema.\n"
        "The JSON MUST have: status (SUCCESS or FAILED), summary (string), files_inspected (list), files_modified (list), confidence (float), failures (list).\n"
        "Return ONLY clean JSON. Do not include markdown code block syntax. No other text."
    )
    user_prompt = f"Objective: {task.objective}\nInputs: {json.dumps(task.inputs)}"
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    try:
        raw_res = DEFAULT_LLM.generate(messages, timeout=15)
        # Parse the JSON response
        data = json.loads(raw_res.strip("`").replace("json\n", "").strip())
        return SpecialistResult(
            task_id=task.task_id,
            status=data.get("status", "SUCCESS"),
            summary=data.get("summary", ""),
            files_inspected=data.get("files_inspected", []),
            files_modified=data.get("files_modified", []),
            confidence=data.get("confidence", 1.0),
            failures=data.get("failures", [])
        )
    except Exception as exc:
        return SpecialistResult(
            task_id=task.task_id,
            status="FAILED",
            summary=f"LLM execution failed: {exc}",
            failures=[str(exc)]
        )
