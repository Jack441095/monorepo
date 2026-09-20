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
        # Checked before the "research" rule below: "marketing" contains
        # "market" as a substring, so without this ordering every marketing
        # task would be swallowed by the bare "market" check and routed to
        # research instead.
        if "marketing" in obj_lower or "advertising" in obj_lower or "campaign" in obj_lower or "outreach" in obj_lower or "social post" in obj_lower:
            return "marketing"
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
        specialist_id="marketing",
        version="1.0.0",
        capabilities=["marketing", "social_media", "campaign_planning", "outreach"],
        allowed_domains=["marketing_sandbox"],
        forbidden_domains=["live_ad_spend", "customer_live_emails"],
        required_approvals=["external_write"]
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
    """Legacy generic specialist path (kept for compatibility; prefer
    run_grounded_specialist below, which grounds the LLM in real ops
    evidence instead of asking it to invent the whole result).

    Routed via thursday.llm_provider (2026-09-18 audit fix) so
    THURSDAY_LLM_PROVIDER switching and THURSDAY_LLM_TIMEOUT apply here
    like every other LLM call site -- previously this called
    audio_too.model_runtime.DEFAULT_LLM directly with a hardcoded
    timeout=15, bypassing both.
    """
    try:
        from thursday.llm_provider import default_timeout, get_llm_provider
        provider = get_llm_provider()
    except Exception as exc:
        return SpecialistResult(
            task_id=task.task_id,
            status="FAILED",
            summary="LLM provider unavailable",
            failures=[f"{type(exc).__name__}: {exc}"]
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
        gen = provider.generate(messages, timeout=default_timeout())
        # DEFAULT_LLM.generate() returns an LLMResult (a dataclass with
        # .content/.model/.usage, not a plain string) -- extract .content
        # before parsing (same pattern as brain.py and every other call
        # site); calling .strip() on the result object itself was an
        # AttributeError on literally every invocation (found 2026-09-08).
        data = json.loads(gen.content.strip("`").replace("json\n", "").strip())
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


# ─── Grounded specialist execution (2026-09-08) ────────────────────────────
#
# run_specialist_with_llm() above asks the LLM to invent the entire
# SpecialistResult from scratch -- no real data, no grounding, just a
# generic "you are the {id} specialist" prompt. Real execution for the four
# specialists that actually have a real, deterministic data source in this
# repo (thursday/ops/*.py) works the same way Marketing/Research's fix did
# today: gather real facts first, then use the LLM ONLY to phrase a summary
# of facts it was actually given, never to invent the facts themselves.
#
# security/data have no real data source anywhere in this repo (no
# security_ops.py exists; macro_analytics.py only covers Thursday's own
# macro telemetry, not general business data) -- asking an LLM to answer
# for them would be exactly the fabrication risk every ops module in this
# codebase explicitly refuses elsewhere. They abstain immediately instead.

def _gather_commercial_evidence(task: SpecialistTask) -> str:
    import thursday.ops.finance_ops as finance_ops
    # Deliberately pricing only, not invoices: finance_ops.py's own module
    # docstring already declines to duplicate invoice listing, which is a
    # separate, subprocess-backed "invoices" service (thursday/client.py) --
    # adding that dependency here would trade this gatherer's determinism
    # and speed for a lookup that already has its own real entry point.
    return finance_ops.pricing_summary()


def _gather_support_evidence(task: SpecialistTask) -> str:
    import thursday.ops.support_ops as support_ops
    return support_ops.faq_lookup(task.objective) + "\n\n" + support_ops.known_issues()


def _gather_documentation_evidence(task: SpecialistTask) -> str:
    import thursday.ops.documentation_ops as documentation_ops
    import thursday.ops.doc_search_ops as doc_search_ops

    tracker = documentation_ops.launch_tracker_status()
    search = doc_search_ops.search_docs(task.objective, top_k=3)
    if search.get("ok"):
        lines = ["DOC SEARCH RESULTS", ""]
        for hit in search["hits"]:
            lines.append(
                f"  {hit['source']} (lines {hit['start_line']}-{hit['end_line']}, "
                f"score {hit['score']}): {hit['snippet'][:200]}"
            )
        search_block = "\n".join(lines)
    else:
        search_block = f"DOC SEARCH RESULTS\n\nEvidence missing — {search.get('error', 'search unavailable')}"
    return tracker + "\n\n" + search_block


def _gather_qa_evidence(task: SpecialistTask) -> str:
    import thursday.ops.qa_ops as qa_ops
    return qa_ops.beta_readiness_check()


_EVIDENCE_GATHERERS = {
    "commercial": _gather_commercial_evidence,
    "support": _gather_support_evidence,
    "documentation": _gather_documentation_evidence,
    "qa": _gather_qa_evidence,
}

_NO_DATA_SOURCE_MESSAGE = (
    "No real data source exists yet for the {specialist_id} specialist -- "
    "answering anyway would mean inventing facts, which this codebase "
    "consistently refuses to do (see thursday/ops/support_ops.py and "
    "thursday/ops/marketing_ops.py for the same discipline applied "
    "elsewhere). This isn't a bug: there's genuinely nothing real to "
    "ground an answer in yet."
)


def specialist_timeout() -> float:
    """Single timeout policy for specialist LLM calls (2026-09-18 audit
    unification). Fast deterministic phrasing (registry/handlers.py) uses
    default_timeout() directly; evidence-grounded phrasing here uses this:
    env floor via default_timeout(), minimum 90s for evidence-sized
    prompts -- measured 2026-09-08 at 60s/65s/60s+ on a healthy local
    model for ~2KB evidence blocks, so 90s is margin above observed
    latency, not a guess. default_timeout() still wins when
    THURSDAY_LLM_TIMEOUT is set higher.
    """
    from thursday.llm_provider import default_timeout
    return max(default_timeout(), 90.0)


def run_grounded_specialist(task: SpecialistTask) -> SpecialistResult:
    """Real execution for specialists with a real, deterministic data
    source in thursday/ops/*.py. The LLM's only job is phrasing a summary
    of evidence it was actually given -- it never authors the facts, and a
    failed LLM call still returns the real evidence gathered, not nothing.

    Specialists with no gatherer (security, data as of this writing)
    abstain immediately, with zero LLM calls -- see _NO_DATA_SOURCE_MESSAGE.
    """
    gatherer = _EVIDENCE_GATHERERS.get(task.specialist_id)
    if gatherer is None:
        return SpecialistResult(
            task_id=task.task_id,
            status="ABSTAINED",
            summary=_NO_DATA_SOURCE_MESSAGE.format(specialist_id=task.specialist_id),
            confidence=0.0,
        )

    evidence_block = gatherer(task)

    from thursday.llm_provider import default_timeout, get_llm_provider

    system_prompt = (
        f"You are the NITE DSP {task.specialist_id} specialist. You will be given real, "
        "already-verified evidence below -- use ONLY that evidence to answer. Never invent "
        "a fact, name, figure, or status beyond what's given; if the evidence says "
        "something is missing, say so plainly instead of guessing. Be concise (3-5 sentences)."
    )
    user_prompt = f"Objective: {task.objective}\n\nEvidence:\n{evidence_block}"
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    try:
        # Timeout policy: specialist_timeout() (see above for the 90s
        # floor rationale). The safety property (never fabricate; a slow/
        # failed call still returns the real gathered evidence, never
        # nothing) holds regardless of the exact value chosen here.
        timeout = specialist_timeout()
        result = get_llm_provider().generate(messages, timeout=timeout, json_mode=False)
        summary = (result.content or "").strip()
        if not summary:
            raise ValueError("LLM returned no content")
        return SpecialistResult(
            task_id=task.task_id,
            status="SUCCESS",
            summary=summary,
            evidence={"raw": evidence_block},
            confidence=0.8,
        )
    except Exception as exc:
        # The real evidence was still gathered even though phrasing it
        # failed -- returning it (rather than an empty result) is the same
        # "don't lose real data just because a later step failed" principle
        # thursday/plan_memory.py and thursday/training_export.py already
        # apply to their own fail-soft paths.
        return SpecialistResult(
            task_id=task.task_id,
            status="FAILED",
            summary=f"Evidence was gathered but the LLM phrasing step failed: {exc}",
            evidence={"raw": evidence_block},
            failures=[str(exc)],
        )
