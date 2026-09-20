"""Thursday orchestrator v3 — ambient intelligence with compound request
handling, disambiguation, personality, user profile, calendar awareness,
and proactive suggestions.

Flow:
  1. Load/session
  2. User profile + mood detection
  3. Expand shortcuts
  4. Check pending alerts + proactive checks
  5. Detect compound request → split or handle
  6. Resolve pronouns/entities
  7. Classify intent
  8. Detect ambiguity → ask clarification or proceed
  9. Score + select service
  10. Execute via unified client
  11. Record usage + learning
  12. Personality-format response
  13. Save context + turn to session
"""

from __future__ import annotations

import datetime
import logging
import re
import sys
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Any

from thursday.repo_root import audio_too_root

ROOT = audio_too_root()

# Ensure paths
if str(ROOT / "business" / "agents") not in sys.path:
    sys.path.insert(0, str(ROOT / "business" / "agents"))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from thursday.session_manager import (
    get_or_create_session,
    save_session,
    add_turn,
    update_context,
    get_context,
)
from thursday.intent import classify_intent
from thursday.resolver import resolve_request, temporal_date_range
from thursday.registry import build_services, request_risk, score_by_triggers
from thursday.confirmation import issue_confirmation, verify_confirmation
from thursday.action_receipts import (
    claim_action,
    complete_action,
    get_receipt,
    receipt_id_for_token,
)
from thursday.command_gateway import AssistantResultText
from thursday import client as api
from thursday.formatter import format_response, format_help
from thursday.monitor import (
    run_checks,
    get_pending_alerts,
    format_alerts,
    should_check,
    top_actionable_suggestion,
    mark_checked,
    acknowledge_all,
)
from thursday.errors import MissingInfoError, ServiceExecutionError
from thursday.retry import DEFAULT_RETRY_POLICY, with_retry
from thursday.compound import is_compound, split_compound_request, CompoundQueue
from thursday.disambiguator import (
    detect_ambiguity,
    ask_clarification,
    handle_clarification_reply,
)
from thursday import daily_brief
from thursday.macros.__init__ import find_matching_macro, execute_macro
from thursday.ops import macro_analytics as _macro_analytics
from thursday.ops import structured_commands as _structured_commands
# `find_matching_macro`/`execute_macro` above are imported from the exact
# module path `thursday.macros.__init__` (not `thursday.macros`) -- Python
# registers those as two *distinct* module objects in sys.modules, each with
# its own globals. Any bare `load_macros()` call resolves against whichever
# module it textually lives in, so the macro-resume branch below looks it up
# via this same qualified module object rather than a fresh
# `from thursday.macros import load_macros`, which would silently bind to
# the *other* module object instead.
from thursday.macros import __init__ as _macros_module
import thursday.user_profile as user_profile
import thursday.personality as personality
import thursday.diagnostics as diagnostics
from thursday.feedback import (
    record_feedback,
    get_suggested_sequences,
    get_auto_correct,
)
import time


from thursday.redaction import get_logger as _get_redacting_logger

logger = _get_redacting_logger(__name__)


def _kenn_contract_text(answer: str, raw_result: object) -> str:
    payload = getattr(raw_result, "kenn_payload", None)
    if not isinstance(payload, dict):
        return answer
    metadata = {
        key: payload[key]
        for key in (
            "answer_mode",
            "answer_quality",
            "diagnostic_reason",
            "generation_validation",
            "grounding_mode",
            "intent_guard",
            "weak_match",
        )
        if key in payload
    }
    return AssistantResultText(
        answer,
        {
            "route": str(payload.get("route") or ""),
            "confidence": str(payload.get("confidence") or "unknown"),
            "grounding": dict(payload.get("grounding") or {}),
            "sources": tuple(payload.get("sources") or ()),
            "suggestions": tuple(
                item if isinstance(item, dict) else {"label": str(item)}
                for item in (payload.get("related_questions") or ())
                if item
            ),
            "metadata": metadata,
        },
    )


_FOLLOWUP_PATTERN = re.compile(
    r"^(?:and\b|also\b|but\b|why\b|how about\b|what about\b|what next\b|"
    r"what should i do next\b|can you explain\b|tell me more\b|go deeper\b)",
    re.IGNORECASE,
)
_COMMON_REQUEST_CORRECTIONS = {
    "ableon": "ableton",
    "analise": "analyse",
    "buisness": "business",
    "calender": "calendar",
    "compresion": "compression",
    "diagnotics": "diagnostics",
    "invioce": "invoice",
    "reserch": "research",
    "reveiw": "review",
    "sidechian": "sidechain",
}


def _inherit_followup_intent(text: str, intent, session: dict):
    """Carry the previous intent only for explicit conversational follow-ups."""
    if not _FOLLOWUP_PATTERN.search(text.strip()):
        return intent
    previous = next(
        (turn for turn in reversed(session.get("turns", [])) if turn.get("role") == "user"),
        None,
    )
    if not previous or previous.get("intent") in {None, "unknown", "contextual", "greeting", "help"}:
        return intent
    if (
        previous.get("intent") == "calendar_scheduling"
        and re.search(r"\b(?:what|how)\s+about\s+next\s+week\b", text, re.IGNORECASE)
    ):
        return type(intent)(
            "calendar_scheduling",
            confidence=max(float(intent.confidence), 0.85),
            entities=intent.entities,
            requires_context=True,
        )
    if intent.name not in {"unknown", "contextual"}:
        return intent
    return type(intent)(
        str(previous["intent"]),
        confidence=max(float(intent.confidence), 0.75),
        entities=intent.entities,
        requires_context=True,
    )


@dataclass(frozen=True)
class RequestDecision:
    """Canonical normalized classification used by every Thursday interface."""

    resolved_text: str
    resolved_entities: dict
    intent: object
    execution_target: str
    brain_decision: Any | None = None


def normalize_request_text(text: str, profile_id: str = "default") -> str:
    """Apply user shortcuts and learned spelling corrections exactly once."""
    normalized = user_profile.expand_shortcuts(text, profile_id)
    for misspelling, correction in _COMMON_REQUEST_CORRECTIONS.items():
        normalized = re.sub(
            rf"\b{re.escape(misspelling)}\b",
            correction,
            normalized,
            flags=re.IGNORECASE,
        )
    try:
        auto_correct = get_auto_correct()
        normalized = auto_correct.apply_spelling(normalized)
    except Exception:
        logger.warning("auto_correct.apply_spelling failed, using unnormalized text", exc_info=True)
    return normalized


def classify_request(text: str, session: dict) -> RequestDecision:
    """Resolve context and classify through Thursday's canonical decision path."""
    context = get_context(session)
    try:
        resolved_text, resolved_entities = resolve_request(text, context)
    except Exception:
        logger.warning("resolve_request failed, falling back to raw text", exc_info=True)
        resolved_text = text
        resolved_entities = {}
    intent = classify_intent(resolved_text, context)
    # Captured before follow-up inheritance below can rewrite intent.name to
    # a guessed prior-turn intent -- the brain-gating decision needs to know
    # how ambiguous the *current* message actually is on its own regex
    # merits, not the inherited guess.
    raw_intent_name = intent.name
    intent = _inherit_followup_intent(resolved_text, intent, session)
    execution_target = "orchestrator"

    # ── LLM Brain Gating ──
    # Latency: only pay for an LLM routing call when the deterministic regex
    # classifier could not confidently place the raw message. "unknown" and
    # "contextual" are exactly the two categories responsible both for
    # generic chit-chat falling through with a canned error, and for the
    # pronoun-triggered misroute (e.g. "tell Jasmine her horses suck" hits
    # "contextual" on the word "her", then blindly inherits an unrelated
    # prior service/slot). Every regex-confident category (business_ops,
    # financial, production_qa, calendar_scheduling, ...) keeps its existing
    # instant deterministic/kenn_stream path -- most requests never touch
    # the LLM at all, only the ambiguous ones that need real reasoning do.
    brain_decision = None
    from thursday.brain import looks_like_audio_engineering_question
    is_audio_q = looks_like_audio_engineering_question(resolved_text)
    brain_enabled = (
        (os.environ.get("AUDIO_TOO_LLM_ENABLED") == "1"
         or os.environ.get("THURSDAY_BRAIN_ENABLED") == "1")
        and not is_audio_q
    )
    if brain_enabled and raw_intent_name in ("unknown", "contextual"):
        try:
            from thursday.brain import decide

            # chat_only=True: the regex classifier already looked at this
            # exact message and found no actionable intent (that's why we're
            # here at all -- see the comment above). There is no legitimate
            # case for trusting the model's own judgment to invoke a service
            # or subagent on that basis -- live-testing showed excluding just
            # "kenn" wasn't enough, the model invented a different wrong
            # service call instead of a plain reply. chat_only structurally
            # forbids any tool call here, so it can only talk or abstain; it
            # also skips build_services(api)'s ~60-service registry build,
            # which chat_only makes irrelevant anyway. Genuine production
            # questions never reach this path -- they take the kenn_stream
            # fast path via the deterministic production_qa match below.
            brain_decision = decide(
                session=session,
                services={},
                subagents=[],
                user_text=resolved_text,
                chat_only=True,
            )
            # "abstain" counts as brain-handled too (not just chat/plan/
            # subagent): it's a legitimate answer, not a failure, and must
            # route to handle()'s brain block (which replies with a plain
            # decline) rather than falling through to the deterministic
            # stage-14 default -- which treats any leftover unknown/
            # contextual intent as "probably a production question" and
            # asks KENN. That fallthrough was live-verified as the actual
            # remaining cause of chit-chat reaching KENN (2026-07-27).
            if brain_decision and brain_decision.type in ("chat", "plan", "subagent", "abstain"):
                execution_target = "brain"
        except Exception as e:
            logger.warning(f"LLM brain decide failed, falling back to deterministic: {e}")

    if execution_target != "brain":
        if (
            intent.name == "production_qa"
            and not is_compound(text)
            and find_matching_macro(text) is None
        ):
            execution_target = "kenn_stream"
            
    return RequestDecision(resolved_text, resolved_entities, intent, execution_target, brain_decision)


def _record_session_feedback(session: dict, user_text: str) -> None:
    """Record the prior assistant turn once, scoped to this session only."""
    state = session.get("feedback_state")
    if not isinstance(state, dict) or not state.get("turn_id") or state.get("recorded"):
        return
    created = float(state.get("created_epoch") or 0.0)
    dwell = max(0.0, time.time() - created) if created else None
    record_feedback(
        turn_id=str(state["turn_id"]),
        session_id=str(session.get("session_id") or ""),
        service_id=str(state.get("service_id") or ""),
        intent_name=str(state.get("intent_name") or ""),
        dwell_seconds=round(dwell, 1) if dwell is not None else None,
        had_followup=True,
        followup_type="continuation",
        response_text=str(state.get("response_text") or ""),
        user_text=user_text,
        plan_id=state.get("plan_id"),
    )
    state["recorded"] = True
    save_session(session)


def _attach_plan_id_to_feedback_state(session: dict, plan_id: str | None) -> None:
    """Stamp the plan_id a just-recorded plan_memory row used onto the
    session's feedback_state, so _record_session_feedback can forward it to
    feedback.record_feedback() and join the two stores later (see
    thursday.training_export). Must be called AFTER add_turn(session,
    "thursday", ...) -- add_turn replaces feedback_state wholesale, so
    stamping before it would be silently overwritten. A no-op if plan_id is
    None (save_plan_trace failed) or feedback_state isn't the expected shape.
    """
    if not plan_id:
        return
    state = session.get("feedback_state")
    if isinstance(state, dict):
        state["plan_id"] = plan_id


def _record_plan_trace(
    *,
    text: str,
    brain_decision: Any,
    service_id: str | None,
    status: str,
    result_summary: str = "",
    lesson: str | None = None,
    failure_reason: str | None = None,
) -> str | None:
    """Write a plan trace after a brain decision resolves (chat, abstain, or
    a completed/failed multi-step plan). Returns the plan_id used (or None
    on a fail-soft error), for the caller to stamp onto the session's
    feedback_state via _attach_plan_id_to_feedback_state -- this is the join
    key thursday.training_export uses to connect "what Thursday decided" to
    "how the user reacted."

    Best-effort only (mirrors plan_memory's own fail-soft guarantees): a
    logging failure here must never affect the response already computed,
    and this never runs before a mutation's confirmation/receipt has
    already been handled by the normal service-execution path above.

    failure_reason, when passed, overrides whatever brain_decision.failure_reason
    carries -- used at execution-time failure call sites (a "service_exception"
    happening after a successful brain decision is a different failure than
    the brain itself failing to decide at all).
    """
    try:
        from thursday.plan_memory import save_plan_trace
        return save_plan_trace(
            query=text,
            abstract=str(getattr(brain_decision, "abstract", "") or ""),
            steps=list(getattr(brain_decision, "steps", []) or []),
            status=status,
            service_id=service_id,
            executed_steps=[{"service_id": service_id, "kind": "service"}] if service_id else [],
            result_summary=result_summary,
            lesson=lesson,
            decision_type=getattr(brain_decision, "type", None),
            provider=getattr(brain_decision, "provider", None) or None,
            model=getattr(brain_decision, "model", None) or None,
            confidence=getattr(brain_decision, "confidence", None),
            latency_s=getattr(brain_decision, "latency_s", None) or None,
            failure_reason=failure_reason or getattr(brain_decision, "failure_reason", None),
            raw_step_count=getattr(brain_decision, "raw_step_count", 0),
        )
    except Exception:
        logger.warning("Failed to record plan trace for service_id=%s", service_id, exc_info=True)
        return None


# ─── Multi-step brain-plan execution ──────────────────────────────────────

# Hard cap on how many steps of a single brain plan will be executed in one
# turn. A longer plan falls back to the single-step path rather than running an
# unbounded LLM-authored sequence (docs/THURSDAY_KENN_AGENT_PLAN_2026-07-20.md
# invariant #2).
_MAX_PLAN_STEPS = 8

_SUBAGENT_STEP_SERVICE = {
    "admin": "admin_agent",
    "marketing": "marketing_agent",
    "research": "research_agent",
}

# SubagentRuntime entry-point names (thursday.subagent_runtime.register_default_agents)
# for the "parallel_swarm" brain-decision branch. Distinct from
# _SUBAGENT_STEP_SERVICE, which names the *service* (registry/handlers.py)
# that wraps the same underlying agent call for the sequential/single-step path.
_SUBAGENT_RUNTIME_AGENT_NAME = {
    "admin": "Admin",
    "marketing": "Marketing",
    "research": "Research",
}


def _map_brain_step_to_service(step: dict, services: dict) -> str | None:
    """Resolve a brain plan step to a concrete service_id, or None if it can't
    be mapped. Mirrors exactly the single-step mapping in the brain-routing
    block so a multi-step plan routes each step the same way a one-step plan
    already routes its only step."""
    if not isinstance(step, dict):
        return None
    kind = step.get("kind")
    if kind == "service":
        svc_id = step.get("service_id")
        return svc_id if svc_id in services else None
    if kind == "subagent":
        return _SUBAGENT_STEP_SERVICE.get(step.get("agent"))
    return None


@dataclass(frozen=True)
class StepResult:
    """Typed result of one executed plan step (Slice 2).

    Replaces the earlier ``(service_id, output_str)`` tuple so a later step, the
    final summary, and future consumers (actionable alerts, composition) have
    structured access to *which* service ran, its human name, its output, and
    whether it succeeded — not just a prose blob. Serialises to/from a plain
    dict for the ``pending_plans`` persistence that survives a confirmation
    round-trip.
    """

    service_id: str
    service_name: str
    output: str
    ok: bool = True

    def to_dict(self) -> dict:
        return {
            "service_id": self.service_id,
            "service_name": self.service_name,
            "output": self.output,
            "ok": self.ok,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StepResult":
        return cls(
            service_id=str(data.get("service_id", "")),
            service_name=str(data.get("service_name", data.get("service_id", ""))),
            output=str(data.get("output", data.get("result", ""))),
            ok=bool(data.get("ok", True)),
        )


def _combine_step_outputs(results: list[StepResult]) -> str:
    """Render an ordered list of step results into one response."""
    if not results:
        return ""
    if len(results) == 1:
        return results[0].output
    return "\n\n".join(f"Step {index}: {r.output}" for index, r in enumerate(results, 1))


def _execute_plan_from(
    mapped: list[str],
    start_index: int,
    *,
    first_is_preconfirmed: bool,
    prior_results: list[StepResult],
    services: dict,
    api,
    handler_ctx: dict,
    resolved_text: str,
) -> dict:
    """Run ``mapped[start_index:]`` in order, threading results forward.

    The one safety invariant (docs/THURSDAY_KENN_AGENT_PLAN_2026-07-20.md,
    Slice 1b): a step is executed here only if it does NOT require confirmation,
    OR it is the very first step *and* ``first_is_preconfirmed`` is True (i.e. the
    caller just verified an explicit confirmation token for exactly that step).
    Every other confirmation-requiring step *pauses* the plan — so no
    unconfirmed mutation is possible, even on resume.

    Returns a dict:
      - {"status": "completed", "results": [StepResult, ...]}
      - {"status": "paused", "results": [...done so far...],
         "pause_service_id": sid, "pause_index": i}
    """
    results: list[StepResult] = list(prior_results)
    for offset, service_id in enumerate(mapped[start_index:]):
        index = start_index + offset
        preconfirmed = offset == 0 and first_is_preconfirmed
        if not preconfirmed and request_risk(service_id, resolved_text).requires_confirmation:
            return {
                "status": "paused",
                "results": results,
                "pause_service_id": service_id,
                "pause_index": index,
            }
        svc = services[service_id]
        step_ctx = dict(handler_ctx)
        step_ctx["_prior_step_results"] = [r.to_dict() for r in results]
        try:
            out = svc.action(step_ctx, api, resolved_text)
        except Exception:
            logger.warning("multi-step plan: service '%s' raised; stopping sequence", service_id, exc_info=True)
            results.append(StepResult(service_id, svc.name, f"(step '{svc.name}' failed; stopped here)", ok=False))
            return {"status": "completed", "results": results}
        out = out or f"(Thursday: {svc.name} returned no output)"
        results.append(StepResult(service_id, svc.name, out, ok=True))
    return {"status": "completed", "results": results}


def _pause_plan_for_confirmation(
    session: dict,
    *,
    mapped: list[str],
    pause_index: int,
    done_results: list[StepResult],
    services: dict,
    resolved_text: str,
) -> str:
    """Issue a confirmation for the paused (risky) step and persist the plan so
    a later ``confirm <token>`` resumes it. Returns the user-facing prompt
    (with any already-completed safe steps' output prepended).

    Reuses the exact confirmation/receipt primitives the single-step gate uses;
    it does not modify that gate. The persisted plan records the full mapped
    step list and the index to resume at, plus the outputs already produced.
    """
    service_id = mapped[pause_index]
    service_name = services[service_id].name
    action_risk = request_risk(service_id, resolved_text)
    token, pending = issue_confirmation(
        session_id=str(session.get("session_id") or ""),
        service_id=service_id,
        text=resolved_text,
    )
    pending["risk"] = action_risk.value

    context = get_context(session)
    now = int(time.time())
    live_pending = {
        tok: entry
        for tok, entry in (context.get("pending_confirmations") or {}).items()
        if isinstance(entry, dict) and int(entry.get("expires_at") or 0) > now
    }
    live_pending[token] = pending
    pending_plans = {
        tok: plan
        for tok, plan in (context.get("pending_plans") or {}).items()
        if isinstance(plan, dict) and tok in live_pending
    }
    pending_plans[token] = {
        "mapped": mapped,
        "resume_index": pause_index,
        "done_results": [r.to_dict() for r in done_results],
        "resolved_text": resolved_text,
    }
    update_context(session, {
        "pending_confirmation": pending,
        "pending_confirmations": live_pending,
        "pending_plans": pending_plans,
    })

    prefix = _combine_step_outputs(done_results)
    prompt = (
        f"This next step would run {service_name} with risk level "
        f"'{action_risk.value}'. It has not run. "
        f"To approve this exact step within five minutes, reply: confirm {token}"
    )
    remaining_after = len(mapped) - pause_index - 1
    if remaining_after > 0:
        prompt += f" (then {remaining_after} more step(s) will continue)"
    return f"{prefix}\n\n{prompt}" if prefix else prompt


def run_brain_plan(
    steps: list[dict],
    *,
    session: dict,
    services: dict,
    api,
    handler_ctx: dict,
    resolved_text: str,
) -> str | None:
    """Execute a multi-step brain plan, pausing at the first step that requires
    confirmation and resuming after the user confirms (Slice 1b).

    Returns a combined response string (steps run + any pause prompt), or
    ``None`` to fall back to the single-step dispatch path for a plan that is
    single-step, unmappable, or over the step cap.

    Safe-by-construction: the executor never runs a confirmation-requiring step
    without an explicit verified token (handled on resume via the confirm
    block), and the existing single-step confirmation gate is untouched.
    """
    mapped: list[str] = []
    for step in steps or []:
        service_id = _map_brain_step_to_service(step, services)
        if service_id is None:
            return None  # an unmappable step → don't attempt a partial sequence
        mapped.append(service_id)

    if len(mapped) <= 1 or len(mapped) > _MAX_PLAN_STEPS:
        return None  # single-step (unchanged path) or over the safety cap

    outcome = _execute_plan_from(
        mapped, 0,
        first_is_preconfirmed=False,
        prior_results=[],
        services=services, api=api, handler_ctx=handler_ctx, resolved_text=resolved_text,
    )
    if outcome["status"] == "paused":
        return _pause_plan_for_confirmation(
            session,
            mapped=mapped,
            pause_index=outcome["pause_index"],
            done_results=outcome["results"],
            services=services,
            resolved_text=resolved_text,
        )
    return _combine_step_outputs(outcome["results"]) or None


def run_parallel_swarm(
    steps: list[dict],
    *,
    api,
    resolved_text: str,
) -> str | None:
    """Execute independently-parallelizable "subagent" brain-plan steps as a
    real dependency graph (thursday.taskgraph / SubagentRuntime.dispatch_graph)
    instead of the sequential brain-plan executor.

    Scoped conservatively on purpose: only proceeds when EVERY step maps to a
    subagent (admin/marketing/research) AND every one of them is risk-free
    (does not require confirmation). Any step needing approval, mixing in a
    "service" step, or failing to map returns None so the caller falls back
    to `run_brain_plan`'s sequential executor — which already has full
    pause/resume support. Building a second confirmation state machine for
    swarms is deliberately out of scope; a request that needs one just runs
    sequentially instead of in parallel.

    Returns the swarm's combined summary, or None to fall back.
    """
    from thursday.subagent_runtime import SubagentRuntime, register_default_agents
    from thursday.taskgraph import TaskGraph, TaskGraphError, TaskNode

    if len(steps) < 2 or len(steps) > _MAX_PLAN_STEPS:
        return None  # no parallelism to gain from a single step; over-cap falls back too

    agent_names: list[str] = []
    for step in steps:
        if not isinstance(step, dict) or step.get("kind") != "subagent":
            return None
        agent_key = step.get("agent")
        runtime_name = _SUBAGENT_RUNTIME_AGENT_NAME.get(agent_key)
        service_id = _SUBAGENT_STEP_SERVICE.get(agent_key)
        if runtime_name is None or service_id is None:
            return None
        if request_risk(service_id, resolved_text).requires_confirmation:
            return None  # any risky step: fall back to the pausable sequential path
        agent_names.append(runtime_name)

    graph = TaskGraph()
    try:
        for i, (step, agent_name) in enumerate(zip(steps, agent_names)):
            task_text = str(step.get("task") or resolved_text)
            graph.add_node(TaskNode(id=f"swarm_{i}", agent=agent_name, params=[task_text]))
    except TaskGraphError:
        return None

    register_default_agents(api)
    runtime = SubagentRuntime()
    swarm_result = runtime.dispatch_graph(graph, qc=True)

    if not swarm_result.agent_results:
        return None
    return swarm_result.final_summary or None


def resume_brain_plan(
    plan: dict,
    *,
    session: dict,
    services: dict,
    api,
    handler_ctx: dict,
) -> str:
    """Resume a paused plan after its confirmation token was verified. Runs the
    just-confirmed step (index ``resume_index``, pre-approved) then continues,
    pausing again at the next confirmation-requiring step. The caller is
    responsible for the receipt claim that prevents replaying the confirmed
    step."""
    mapped = list(plan.get("mapped") or [])
    resume_index = int(plan.get("resume_index") or 0)
    resolved_text = str(plan.get("resolved_text") or "")
    done_results = [StepResult.from_dict(d) for d in (plan.get("done_results") or [])]

    # Guard against a malformed/mismatched stored plan.
    if not mapped or resume_index >= len(mapped) or any(sid not in services for sid in mapped):
        return "That plan can no longer be resumed."

    outcome = _execute_plan_from(
        mapped, resume_index,
        first_is_preconfirmed=True,
        prior_results=done_results,
        services=services, api=api, handler_ctx=handler_ctx, resolved_text=resolved_text,
    )
    if outcome["status"] == "paused":
        return _pause_plan_for_confirmation(
            session,
            mapped=mapped,
            pause_index=outcome["pause_index"],
            done_results=outcome["results"],
            services=services,
            resolved_text=resolved_text,
        )
    return _combine_step_outputs(outcome["results"]) or "(plan completed with no output)"


def _build_handler_ctx(
    session: dict,
    context: dict,
    *,
    resolved_entities: dict,
    correlation_id: str,
    list_records,
    add_record,
    update_record,
) -> dict:
    """Build the ``handler_ctx`` passed to every service action. Extracted so the
    main dispatch and the paused-plan resume path build an identical context."""
    try:
        all_enquiries = list_records("enquiries") if list_records else []
    except Exception:
        logger.warning("list_records('enquiries') failed, continuing with none", exc_info=True)
        all_enquiries = []
    return {
        "_list_records": list_records,
        "_add_record": add_record,
        "_update_record": update_record,
        "_all_enquiries": all_enquiries,
        "_session_id": session.get("session_id", ""),
        "_temporal_range": temporal_date_range(resolved_entities),
        "_kenn_history": [
            {
                "role": "user" if turn.get("role") == "user" else "assistant",
                "content": str(turn.get("text") or ""),
            }
            for turn in session.get("turns", [])[-8:]
            if turn.get("role") in {"user", "thursday"}
        ],
        **context,
        "_correlation_id": correlation_id,
    }


# ─── Core handle function ─────────────────────────────────────────────────


def handle(
    text: str,
    session: dict | None = None,
    list_records: Callable[[str], list[dict]] | None = None,
    *,
    correlation_id: str = "",
) -> str:
    """Process a natural language request with full context and intelligence.

    Args:
        text: The user's request.
        session: Optional session dict. If None, creates/fetches one.
        list_records: Data access function.
        correlation_id: Trace id from the command envelope, if this call came
            through thursday/command_gateway.py, threaded into handler_ctx as
            "_correlation_id" so downstream service handlers (e.g. AutoMix)
            can carry it into the domain events they record.

    Returns:
        Formatted response string.
    """
    if list_records is None:
        try:
            from app.db import list_records as _lr
            list_records = _lr
        except ImportError:
            list_records = lambda _: []  # noqa: E731

    try:
        from app.db import add_record as _add_record, update_record as _update_record
    except ImportError:
        def _add_record(_name: str, record: dict) -> dict:
            return record

        def _update_record(
            _name: str, _identifier: str, _updates: dict, _fields: list[str] | None = None
        ) -> None:
            return None

    text = text.strip()
    if not text:
        return "Tell me what you need — try 'how's business' or 'help'."

    # 1. Load/create session
    if session is None:
        session = get_or_create_session()
    _record_session_feedback(session, text)
    context = get_context(session)

    # Most-recently-issued pending confirmation (drives the "yes"/"go ahead" implicit
    # shortcut below, and command_gateway.py's single-turn confirmation summary).
    # `pending_confirmations` (plural) is the durable, token-keyed store any *specific*
    # still-unexpired confirmation is looked up in -- a second risky action issuing a
    # new `pending_confirmation` must not make an earlier one un-confirmable. See
    # docs/audits/2026-07-19-thursday-multistep-scoping.md gap 2.
    pending_confirmation = context.get("pending_confirmation")
    pending_confirmations = context.get("pending_confirmations")
    if not isinstance(pending_confirmations, dict):
        pending_confirmations = {}
    if pending_confirmation and isinstance(pending_confirmation, dict):
        cleaned_input = re.sub(r"[^\w\s]", "", text.strip().lower())
        positive_phrases = {
            "yes", "y", "do it", "go ahead", "please", "confirm", "yep", "yeah", "ok", "okay",
            "please do", "approve", "do that", "run it", "run that", "confirm it"
        }
        if cleaned_input in positive_phrases or any(phrase in cleaned_input for phrase in ["go ahead", "do it", "please do", "run it"]):
            token = pending_confirmation.get("token")
            if token:
                text = f"confirm {token}"

    # Actionable-alert suggestion: a one-shot "reply yes to <show X>" offer stored
    # when alerts were last surfaced. An affirmative runs the (read-only) suggested
    # command; an in-flight pending confirmation always takes precedence, and the
    # suggestion is cleared either way so it cannot linger and fire on a later,
    # unrelated "yes".
    pending_suggestion = context.get("pending_suggestion")
    if isinstance(pending_suggestion, dict) and pending_suggestion.get("command"):
        already_confirming = bool(re.fullmatch(r"confirm\s+.+", text.strip(), re.IGNORECASE))
        cleaned = re.sub(r"[^\w\s]", "", text.strip().lower())
        suggestion_affirmatives = {
            "yes", "y", "yep", "yeah", "ok", "okay", "sure", "please", "yes please",
            "do it", "go ahead", "show me", "show them", "show it",
        }
        if not already_confirming and (
            cleaned in suggestion_affirmatives
            or any(p in cleaned for p in ["go ahead", "show me", "show them", "yes please"])
        ):
            text = str(pending_suggestion["command"])
        update_context(session, {"pending_suggestion": None})
        context = get_context(session)

    confirmed_service_id = ""
    confirmed_token = ""
    action_receipt_id = ""
    confirmation_match = re.fullmatch(
        r"confirm\s+([A-Za-z0-9_.:-]{1,127})", text, re.IGNORECASE
    )
    if confirmation_match:
        token = confirmation_match.group(1)
        matched_pending = pending_confirmations.get(token)
        if not isinstance(matched_pending, dict) and isinstance(pending_confirmation, dict):
            # Fallback for a session written before pending_confirmations existed, or
            # any path that only set the singular slot.
            if pending_confirmation.get("token") == token:
                matched_pending = pending_confirmation
        if not isinstance(matched_pending, dict):
            prior_receipt = get_receipt(
                receipt_id_for_token(token),
                session_id=str(session.get("session_id") or ""),
            )
            if prior_receipt and prior_receipt.status == "completed":
                return prior_receipt.response_text
            if prior_receipt and prior_receipt.status == "processing":
                return (
                    "That action is already being processed. "
                    f"Receipt: {prior_receipt.receipt_id}"
                )
            return "There is no pending action to confirm."
        pending_text = str(matched_pending.get("text") or "")
        pending_service = str(matched_pending.get("service_id") or "")
        if not verify_confirmation(
            token,
            session_id=str(session.get("session_id") or ""),
            service_id=pending_service,
            text=pending_text,
        ):
            return "That confirmation is invalid or expired. The action was not run."

        # If this verified token belongs to a paused multi-step plan, resume the
        # plan here rather than routing the single-service confirmed path. The
        # just-confirmed step is the only pre-approved one; the resume re-checks
        # risk on every subsequent step and pauses again at the next risky one,
        # so no unconfirmed mutation is possible across a resume. A receipt claim
        # keeps the confirmed step from being replayed.
        pending_plans_ctx = context.get("pending_plans")
        if isinstance(pending_plans_ctx, dict) and token in pending_plans_ctx:
            plan = pending_plans_ctx[token]
            resume_receipt_id = receipt_id_for_token(token)
            claim = claim_action(
                resume_receipt_id,
                session_id=str(session.get("session_id") or ""),
                service_id=pending_service,
                text=pending_text,
            )
            if not claim.claimed:
                if claim.receipt.status == "completed":
                    return claim.receipt.response_text
                return (
                    "That action is already being processed. "
                    f"Receipt: {claim.receipt.receipt_id}"
                )
            # Consume this token's pending state before resuming (the resume may
            # itself create a fresh pause with a new token).
            consumed_conf = {
                t: v for t, v in (context.get("pending_confirmations") or {}).items() if t != token
            }
            consumed_plans = {t: v for t, v in pending_plans_ctx.items() if t != token}
            resume_updates: dict = {
                "pending_confirmations": consumed_conf,
                "pending_plans": consumed_plans,
            }
            if isinstance(pending_confirmation, dict) and pending_confirmation.get("token") == token:
                resume_updates["pending_confirmation"] = None
            update_context(session, resume_updates)
            context = get_context(session)

            resume_services = build_services(api)
            resume_ctx = _build_handler_ctx(
                session,
                context,
                resolved_entities={},
                correlation_id=correlation_id,
                list_records=list_records,
                add_record=_add_record,
                update_record=_update_record,
            )
            resume_ctx["_list_records"] = list_records
            response = resume_brain_plan(
                plan,
                session=session,
                services=resume_services,
                api=api,
                handler_ctx=resume_ctx,
            )
            complete_action(resume_receipt_id, response_text=response)
            add_turn(session, "user", text, "brain_multi_step", None, {})
            add_turn(session, "thursday", response, "brain_multi_step", None, {})
            try:
                save_session(session)
            except Exception:
                logger.warning("save_session failed for session %s", session.get("session_id"), exc_info=True)
            return response

        # If this verified token belongs to a paused macro step, resume the
        # macro through the same authoritative gate (request_risk +
        # confirmation.py + action_receipts.py) that issued the pause —
        # closing the macro confirmation bypass (docs/audits/2026-08-20-
        # thursday-nitedsp-forensic-audit.md, P0-6). execute_macro() performs
        # its own claim_action() for the just-confirmed step internally, so no
        # separate claim happens here.
        pending_macros_ctx = context.get("pending_macros")
        if isinstance(pending_macros_ctx, dict) and token in pending_macros_ctx:
            macro_entry = pending_macros_ctx[token]
            macro_name = str(macro_entry.get("macro_name") or "")

            macro_obj = next((m for m in _macros_module.load_macros() if m.name == macro_name), None)
            if macro_obj is None:
                return "That macro is no longer available. The action was not run."
            _macro_start = time.monotonic()
            macro_results = execute_macro(
                macro_obj,
                handle,
                session,
                macro_entry.get("params") or {},
                trigger_text=pending_text,
                confirmed_token=token,
            )
            _macro_analytics.record_macro_execution(
                macro_name, macro_results, (time.monotonic() - _macro_start) * 1000, resumed=True,
            )
            combined = "\n\n".join(macro_results)
            add_turn(session, "user", text, "macro", macro_name, {})
            add_turn(session, "thursday", combined, "macro", macro_name, {})
            try:
                save_session(session)
            except Exception:
                logger.warning("save_session failed for session %s", session.get("session_id"), exc_info=True)
            return combined

        text = pending_text
        confirmed_service_id = pending_service
        confirmed_token = token
    elif pending_confirmation:
        update_context(session, {"pending_confirmation": None})
        context = get_context(session)

    # 2. Load user profile
    profile_id = context.get("profile_id", "default")
    profile = user_profile.get_profile(profile_id)

    # 3. Detect mood from text
    mood = user_profile.detect_mood(text)
    if mood:
        user_profile.set_mood(mood, profile_id)
        context["_mood"] = mood

    # 4. Normalize shortcuts and learned spelling through the shared path.
    text = normalize_request_text(text, profile_id)

    # 5. Check for macro match
    macro = find_matching_macro(text)
    if macro:
        params = macro.extract_params(text)
        # No `confirmed` shortcut here: any mutation-capable step gets
        # classified and (if needed) paused for a real confirmation token by
        # execute_macro() itself — see thursday/macros/__init__.py and the
        # "confirm <token>" resume branch above.
        _macro_start = time.monotonic()
        macro_results = execute_macro(macro, handle, session, params, trigger_text=text)
        _macro_analytics.record_macro_execution(
            macro.name, macro_results, (time.monotonic() - _macro_start) * 1000, resumed=False,
        )
        combined = "\n\n".join(macro_results)

        # Record usage
        user_profile.record_request(f"macro:{macro.name}", profile_id=profile_id)

        add_turn(session, "user", text, "macro", macro.name, params)
        add_turn(session, "thursday", combined, "macro", macro.name, {})
        try:
            save_session(session)
        except Exception:
            logger.warning("save_session failed for session %s", session.get("session_id"), exc_info=True)
        return combined

    # 5.5. Check for a structured command (task creation, marketing plans,
    # ad campaign plans, ...) before the fuzzy trigger-scoring loop below,
    # for the same reason macros are checked early: each of these has a
    # free-form text tail that can legitimately contain words belonging to
    # a totally unrelated service (e.g. "create task marketing: draft a
    # post" contains "marketing" and "draft post", both real triggers of
    # the marketing_agent service) -- thursday.registry.score_by_triggers
    # scans the *whole* input for trigger substrings with no concept of
    # "this part is free text, not a routing signal". See
    # thursday/structured_commands.py's module docstring for the live-CLI
    # bug (2026-09-02) that established this pattern.
    structured = _structured_commands.try_dispatch(text)
    if structured is not None:
        command_name, result = structured
        add_turn(session, "user", text, command_name, None, {})
        add_turn(session, "thursday", result, command_name, None, {})
        try:
            save_session(session)
        except Exception:
            logger.warning("save_session failed for session %s", session.get("session_id"), exc_info=True)
        return result

    # 6. Check for proactive alerts (if enough time has passed)
    alert_message = None
    if should_check():
        try:
            run_checks(list_records)
        except Exception:
            # Non-critical — don't block the request, but a recurring
            # failure here should be visible, not silent.
            logger.warning("run_checks failed; proactive alerts skipped this turn", exc_info=True)
        finally:
            mark_checked()

    pending_alerts = get_pending_alerts()
    if pending_alerts:
        formatted = format_alerts(pending_alerts)
        if formatted:
            alert_message = formatted
            # Actionable alerts: offer a safe, read-only one-word follow-up for the
            # highest-severity actionable alert, and remember it so the next turn's
            # "yes" runs it (consumed at the top of the next handle()).
            suggestion = top_actionable_suggestion(pending_alerts)
            if suggestion:
                alert_message += f"\n\nReply 'yes' and I'll {suggestion['label']}."
                try:
                    update_context(session, {"pending_suggestion": suggestion})
                    context = get_context(session)
                except Exception:
                    logger.warning("failed to persist pending_suggestion", exc_info=True)

    # 7. Daily briefing check (offer on first interaction of the day)
    briefing_available = (
        not user_profile.was_briefing_shown_today(profile_id)
        and profile.get("preferences", {}).get("daily_briefing", True)
    )
    show_briefing = False

    # 8. Detect and handle compound requests
    if is_compound(text):
        parts = split_compound_request(text)
        if len(parts) > 1:
            queue = CompoundQueue(parts, is_sequential=True)
            # Process each part through the handle function
            for part in parts:
                part_result = handle(
                    part.strip(),
                    session=session,
                    list_records=list_records,
                )
                queue.add_result(part_result)
            result = queue.summarize()

            add_turn(session, "user", text, "compound", None, {"parts": parts})
            add_turn(session, "thursday", result, "compound", None, {})
            try:
                save_session(session)
            except Exception:
                logger.warning("save_session failed for session %s", session.get("session_id"), exc_info=True)

            # Record usage
            user_profile.record_request("compound_request", profile_id=profile_id)

            if alert_message:
                acknowledge_all()
                result = f"{alert_message}\n\n{result}"
            return result

    # 9-10. Resolve context and classify through the shared decision path.
    decision = classify_request(text, session)
    resolved_text = decision.resolved_text
    resolved_entities = decision.resolved_entities
    intent = decision.intent

    # Briefings and routine alerts should not hijack a focused studio answer.
    # Critical alerts are still delivered immediately; routine alerts wait for
    # a business, calendar, diagnostics, or explicit briefing request.
    show_briefing = briefing_available and intent.name in {
        "business_ops", "calendar_scheduling", "macro"
    }
    alert_relevant_intents = {
        "business_ops", "calendar_scheduling", "client_mgmt", "financial",
        "system_diagnostics", "system", "macro",
    }
    has_critical_alert = any(
        str(item.get("severity", "")).lower() == "critical" for item in pending_alerts
    )
    if alert_message and (intent.name in alert_relevant_intents or has_critical_alert):
        acknowledge_all()
    else:
        alert_message = None

    # 10a. Handle voice character switching (KENN ↔ Thursday) — no alerts on voice switch
    if intent.name == "kenn_voice_mode":
        text_lower = resolved_text.lower()
        switching_to_kenn = re.search(r"\bkenn?\b", text_lower) and not re.search(
            r"\b(back\s+to|switch\s+to|talk\s+to|speak\s+with)\s+thursday\b", text_lower
        )
        if switching_to_kenn:
            update_context(session, {"active_voice": "kenn"})
            result = "Bringing KENN in for the production side — what do you want to know?"
        else:
            update_context(session, {"active_voice": "thursday"})
            result = "Back with you. What do you need?"
        add_turn(session, "user", text, "kenn_voice_mode", None, {})
        add_turn(session, "thursday", result, "kenn_voice_mode", None, {})
        try:
            save_session(session)
        except Exception:
            logger.warning("save_session failed for session %s", session.get("session_id"), exc_info=True)
        # No alerts on voice switching — not the right moment
        return result

    # 10b. Handle greetings naturally — no business alerts on hello.
    # Thursday is the primary assistant and always fronts greetings, even if the
    # session previously switched to KENN's voice. KENN is a specialist Thursday
    # consults for production questions (see stage 14), not a mode that takes over,
    # so a greeting also resets the session back to Thursday.
    if intent.name == "greeting":
        greeting_text = personality.get_greeting(profile, context)
        update_context(session, {"active_voice": "thursday"})
        result = f"{greeting_text} What do you need?"
        add_turn(session, "user", text, "greeting", None, {})
        add_turn(session, "thursday", result, "greeting", None, {})
        try:
            save_session(session)
        except Exception:
            logger.warning("save_session failed for session %s", session.get("session_id"), exc_info=True)
        return result

    # 10c. Help / capabilities — list what Thursday can do.
    if intent.name == "help":
        result = help_text(list_records)
        add_turn(session, "user", text, "help", None, {})
        add_turn(session, "thursday", result, "help", None, {})
        try:
            save_session(session)
        except Exception:
            logger.warning("save_session failed for session %s", session.get("session_id"), exc_info=True)
        return result

    # 11. Detect ambiguity and ask clarification if needed
    if context.get("pending_action") and "ambiguity" in str(context.get("pending_action", {})):
        # User is responding to a clarification
        pending = context.get("pending_action", {})
        if isinstance(pending, dict) and pending.get("type") == "ambiguity":
            # Handle the clarification reply
            resolved = handle_clarification_reply(text, pending)
            if resolved:
                update_context(session, resolved)
                context.update(resolved)
                # If resolved, the clarifying context is cleared; proceed.
                if not resolved.get("pending_action"):
                    # Re-process the original intent if it was clarified
                    original_text = pending.get("original_text", text)
                    return handle(
                        original_text,
                        session=session,
                        list_records=list_records,
                    )

    # 12. Detect ambiguity (for new requests)
    ambiguity = detect_ambiguity(resolved_text, intent, context, list_records)
    if ambiguity:
        clarification = ask_clarification(ambiguity)
        # Store the pending ambiguity for when the user replies
        pending_action = ambiguity.to_dict()
        pending_action["type"] = "ambiguity"
        pending_action["original_text"] = resolved_text
        update_context(session, {"pending_action": pending_action})
        try:
            save_session(session)
        except Exception:
            logger.warning("save_session failed for session %s", session.get("session_id"), exc_info=True)

        # Record usage
        user_profile.record_request("disambiguation", profile_id=profile_id)

        return clarification

    # 13. Build services and score them
    services = build_services(api)

    # Build handler context with data access functions (shared with the
    # paused-plan resume path via _build_handler_ctx).
    handler_ctx = _build_handler_ctx(
        session,
        context,
        resolved_entities=resolved_entities,
        correlation_id=correlation_id,
        list_records=list_records,
        add_record=_add_record,
        update_record=_update_record,
    )

    best_service_id = None
    best_service = None
    best_score = 0.0
    brain_routing_active = False

    # ── Brain Decision Routing ──
    if decision.execution_target == "brain" and decision.brain_decision:
        bd = decision.brain_decision
        if bd.type == "chat":
            # Found 2026-08-02 (Jack live report: empty reply + "Error: Load
            # failed" in the UI): this used to read bd.abstract here, but the
            # schema documents "abstract" as an internal one-line summary of
            # the model's reasoning ("Summary of your reasoning or planned
            # tasks"), not the actual reply -- so real chat questions came
            # back as plan-summary text like "Assisting in crafting an
            # empathetic text response" instead of an answer. "message" is
            # the dedicated field for the literal user-facing reply (see
            # build_brain_prompt); abstract is kept purely for internal
            # logs/traces now. Falling back to abstract only covers an
            # older/misbehaving model that ignores the new field.
            #
            # Found 2026-07-27 (Jack live-testing): a small local model
            # occasionally returns type="chat" with an empty/missing
            # message -- format_response() doesn't guard against a falsy
            # result, so the literal string "None" was shown to the user.
            result = (
                bd.message
                or bd.abstract
                or "Not sure what to say to that — try rephrasing, or ask for 'help'."
            )
            add_turn(session, "user", text, intent.name, None, resolved_entities)
            formatted = format_response(result, "Thursday Brain", "brain", context)
            add_turn(session, "thursday", formatted, intent.name, None, {})
            plan_id = _record_plan_trace(
                text=resolved_text, brain_decision=bd, service_id=None,
                status="chat", result_summary=formatted[:280],
            )
            _attach_plan_id_to_feedback_state(session, plan_id)
            try:
                save_session(session)
            except Exception:
                logger.warning("save_session failed for session %s", session.get("session_id"), exc_info=True)
            return formatted

        elif bd.type == "abstain":
            # Found 2026-07-27 (Jack live-testing): without this branch, an
            # "abstain" brain decision (a legitimate answer -- the model
            # genuinely doesn't know what the user means) fell through this
            # whole if/elif untouched and continued into stage 14 below,
            # whose "unknown"/"contextual" leftover default is to ask KENN --
            # exactly the casual-chat-routed-to-KENN behavior chat_only was
            # supposed to prevent. An explicit abstain here short-circuits
            # that fallthrough with a plain decline instead.
            result = (
                bd.question_for_user
                or "I'm not quite sure what you need there — try rephrasing, or ask for 'help' to see what I can do."
            )
            add_turn(session, "user", text, intent.name, None, resolved_entities)
            formatted = format_response(result, "Thursday Brain", "brain", context)
            add_turn(session, "thursday", formatted, intent.name, None, {})
            plan_id = _record_plan_trace(
                text=resolved_text, brain_decision=bd, service_id=None,
                status="abstained", result_summary=formatted[:280],
            )
            _attach_plan_id_to_feedback_state(session, plan_id)
            try:
                save_session(session)
            except Exception:
                logger.warning("save_session failed for session %s", session.get("session_id"), exc_info=True)
            return formatted

        elif bd.type in ("plan", "subagent", "parallel_swarm") and bd.steps:
            if bd.type == "parallel_swarm":
                # Genuinely independent subagent steps run as a real parallel
                # dependency graph instead of in sequence. Conservatively
                # scoped: run_parallel_swarm returns None (falling through to
                # the sequential run_brain_plan path below, unchanged) for
                # anything that mixes in a "service" step, is a single step,
                # or has any step that would require confirmation -- swarms
                # don't have a pause/resume mechanism, so a risky step just
                # runs sequentially instead of in parallel. See run_parallel_swarm.
                swarm_response = run_parallel_swarm(
                    bd.steps, api=api, resolved_text=resolved_text,
                )
                if swarm_response is not None:
                    add_turn(session, "user", text, intent.name, None, resolved_entities)
                    formatted = format_response(swarm_response, "Thursday Brain", "brain", context)
                    add_turn(session, "thursday", formatted, intent.name, None, {})
                    try:
                        save_session(session)
                    except Exception:
                        logger.warning("save_session failed for session %s", session.get("session_id"), exc_info=True)
                    plan_id = _record_plan_trace(
                        text=resolved_text,
                        brain_decision=bd,
                        service_id="brain_parallel_swarm",
                        status="completed",
                        result_summary=swarm_response[:280],
                    )
                    _attach_plan_id_to_feedback_state(session, plan_id)
                    try:
                        save_session(session)
                    except Exception:
                        logger.warning("save_session failed for session %s", session.get("session_id"), exc_info=True)
                    if alert_message:
                        acknowledge_all()
                        formatted = f"{alert_message}\n\n{formatted}"
                    return formatted
                # Falls through to the sequential plan executor below, exactly
                # as a "plan" decision would.

            # First try to run the plan as a real multi-step sequence. This
            # engages for a genuinely multi-step plan (running safe steps in
            # order and pausing at the first confirmation-requiring step, to be
            # resumed on `confirm <token>`); it returns None (falling through to
            # the single-step mapping below, unchanged) for a single-step,
            # unmappable, or over-cap plan. See run_brain_plan.
            plan_response = run_brain_plan(
                bd.steps,
                session=session,
                services=services,
                api=api,
                handler_ctx=handler_ctx,
                resolved_text=resolved_text,
            )
            if plan_response is not None:
                add_turn(session, "user", text, intent.name, None, resolved_entities)
                formatted = format_response(plan_response, "Thursday Brain", "brain", context)
                add_turn(session, "thursday", formatted, intent.name, None, {})
                try:
                    save_session(session)
                except Exception:
                    logger.warning("save_session failed for session %s", session.get("session_id"), exc_info=True)
                plan_id = _record_plan_trace(
                    text=resolved_text,
                    brain_decision=bd,
                    service_id="brain_multi_step",
                    status="completed",
                    result_summary=plan_response[:280],
                )
                _attach_plan_id_to_feedback_state(session, plan_id)
                try:
                    save_session(session)
                except Exception:
                    logger.warning("save_session failed for session %s", session.get("session_id"), exc_info=True)
                if alert_message:
                    acknowledge_all()
                    formatted = f"{alert_message}\n\n{formatted}"
                return formatted

            # Map subagent or service step to a service
            first_step = bd.steps[0]
            target_svc = None
            if first_step.get("kind") == "service":
                target_svc = first_step.get("service_id")
            elif first_step.get("kind") == "subagent":
                agent_name = first_step.get("agent")
                if agent_name == "admin":
                    target_svc = "admin_agent"
                elif agent_name == "marketing":
                    target_svc = "marketing_agent"
                elif agent_name == "research":
                    target_svc = "research_agent"
                    
            if target_svc and target_svc in services:
                best_service_id = target_svc
                best_service = services[target_svc]
                best_score = 1.0
                brain_routing_active = True

    entity_context = {
        "current_client": "client_name",
        "current_project": "project_name",
        "current_invoice": "invoice_id",
        "current_mix_review": "review_id",
        "current_audio_scan": "audio_path",
        "current_audiogen_job": "audiogen_job_id",
    }

    if not brain_routing_active:
        for svc_id, svc_def in services.items():
            try:
                trigger_score = score_by_triggers(resolved_text, svc_def.triggers)
                intent_score = 0.0
                if intent.name in svc_def.intents:
                    intent_score += intent.confidence * 2.0
                total_score = trigger_score + intent_score
                # If a service requires context that is missing, and trigger score is 0,
                # do not let pure intent scoring select it (which causes dead-end MissingInfoErrors).
                missing_req = [
                    key for key in svc_def.requires_context
                    if not handler_ctx.get(key) and not intent.entities.get(entity_context.get(key, ""))
                ]
                if missing_req and trigger_score == 0:
                    total_score = 0.0
            except Exception:
                logger.warning("Scoring failed for service '%s', treating as no match", svc_id, exc_info=True)
                total_score = 0.0

            if total_score > best_score:
                best_score = total_score
                best_service_id = svc_id
                best_service = svc_def

    # 14. Check if this needs KENN (production questions).
    # This is a studio assistant: once greetings, help, and business/studio
    # services have been ruled out (they return earlier or match a service with
    # score >= 0.5), a leftover unclassified question is far more likely a
    # production question than noise. Default it to KENN — which has its own
    # out-of-scope guard and abstains politely if truly off-topic — so Thursday
    # stops answering real production questions with "Not sure I caught that".
    # Regex intent-matching can never cover every natural phrasing ("how do I
    # make my mix louder", "help me with my mixdown"); this makes KENN the
    # sensible default instead of the dead-end.
    kenn_default_intents = {"production_qa", "unknown", "contextual"}
    from thursday.brain import looks_like_audio_engineering_question
    is_kenn_question = (
        intent.name in kenn_default_intents
        or looks_like_audio_engineering_question(resolved_text)
    )

    if best_service is None or best_score < 0.5:
        if is_kenn_question:
            _voice = context.get("_voice_mode", False)
            result = api.ask_kenn(resolved_text, fast=_voice)
            add_turn(session, "user", text, intent.name, "kenn", resolved_entities)
            try:
                save_session(session)
            except Exception:
                logger.warning("save_session failed for session %s", session.get("session_id"), exc_info=True)
            formatted = format_response(result, "KENN Knowledge Base", "kenn", context)
            add_turn(session, "thursday", formatted, intent.name, "kenn", {})

            # Record usage + learning
            user_profile.record_request("kenn", profile_id=profile_id)
            diagnostics.record_usage("kenn", intent.name)

            if alert_message:
                formatted = f"{alert_message}\n\n{formatted}"

            return _kenn_contract_text(formatted, result)
        else:
            from thursday.errors import suggest_alternatives
            alternatives = suggest_alternatives(resolved_text)
            msg = (
                "Not sure I caught that. "
                "Try asking a production question, say \"speak with KENN\", or ask about the business.\n\n"
                + "\n".join(f"  - {s}" for s in alternatives)
            )
            if alert_message:
                msg = f"{alert_message}\n\n{msg}"
            add_turn(session, "user", text, intent.name, None, resolved_entities)
            add_turn(session, "thursday", msg, intent.name, None, {})

            user_profile.record_request("unknown", profile_id=profile_id)
            return msg

    # 15. Execute the best service
    service_name = best_service.name
    service_id = best_service_id

    entity_context = {
        "current_client": "client_name",
        "current_project": "project_name",
        "current_invoice": "invoice_id",
        "current_mix_review": "review_id",
        "current_audio_scan": "audio_path",
        "current_audiogen_job": "audiogen_job_id",
    }
    for context_key, entity_key in entity_context.items():
        if intent.entities.get(entity_key):
            handler_ctx[context_key] = intent.entities[entity_key]
    missing_context = [
        key for key in best_service.requires_context
        if not handler_ctx.get(key) and not intent.entities.get(entity_context.get(key, ""))
    ]
    if missing_context:
        result = str(MissingInfoError(missing_context[0]))
        add_turn(session, "user", text, intent.name, service_id, {**resolved_entities, **intent.entities})
        formatted = format_response(result, service_name, service_id, context)
        add_turn(session, "thursday", formatted, intent.name, service_id, {})

        return f"{alert_message}\n\n{formatted}" if alert_message else formatted

    action_risk = request_risk(service_id, resolved_text)
    if action_risk.requires_confirmation and confirmed_service_id != service_id:
        token, pending = issue_confirmation(
            session_id=str(session.get("session_id") or ""),
            service_id=service_id,
            text=resolved_text,
        )
        pending["risk"] = action_risk.value
        # Keep every still-unexpired pending confirmation confirmable by explicit
        # token, not just the most recently issued one (a second risky step in a
        # compound request must not orphan the first's confirmation).
        now = int(time.time())
        live_pending = {
            tok: entry
            for tok, entry in pending_confirmations.items()
            if isinstance(entry, dict) and int(entry.get("expires_at") or 0) > now
        }
        live_pending[token] = pending
        update_context(session, {"pending_confirmation": pending, "pending_confirmations": live_pending})
        prompt = (
            f"This would run {service_name} with risk level "
            f"'{action_risk.value}'. The action has not run. "
            f"To approve this exact request within five minutes, reply: confirm {token}"
        )
        add_turn(
            session,
            "user",
            text,
            intent.name,
            service_id,
            {**resolved_entities, **intent.entities},
        )
        add_turn(session, "thursday", prompt, intent.name, service_id, {})
        return prompt

    if confirmed_service_id:
        # Consume before dispatch so failures and retries cannot replay approval.
        # Only clear the singular "most recent" slot if it's the one being consumed --
        # confirming an older, already-superseded token must not drop a newer pending
        # confirmation the user hasn't acted on yet.
        remaining_pending = {tok: v for tok, v in pending_confirmations.items() if tok != confirmed_token}
        context_updates: dict = {"pending_confirmations": remaining_pending}
        if isinstance(pending_confirmation, dict) and pending_confirmation.get("token") == confirmed_token:
            context_updates["pending_confirmation"] = None
        update_context(session, context_updates)
        context = get_context(session)
        handler_ctx["pending_confirmation"] = None
        action_receipt_id = receipt_id_for_token(confirmed_token)
        claim = claim_action(
            action_receipt_id,
            session_id=str(session.get("session_id") or ""),
            service_id=service_id,
            text=resolved_text,
        )
        if not claim.claimed:
            if claim.receipt.status == "completed":
                return claim.receipt.response_text
            return (
                "That action is already being processed. "
                f"Receipt: {claim.receipt.receipt_id}"
            )

    try:
        handler_ctx["_list_records"] = list_records

        if action_receipt_id:
            # Confirmed consequential action: execute exactly once. A retry
            # after a timeout could double-apply the side effect (the
            # receipt blocks foreign replays, not this action's own retry),
            # so transient failures here surface as honest failures instead.
            result = best_service.action(handler_ctx, api, resolved_text)
        else:
            result = with_retry(
                lambda: best_service.action(handler_ctx, api, resolved_text),
                DEFAULT_RETRY_POLICY,
            )

        if not result:
            result = f"(Thursday: {service_name} returned no output)"

        # Post-process context
        if best_service.post_process:
            try:
                best_service.post_process(handler_ctx, result)
            except Exception:
                pass

        # Merge resolved entities into context
        context_updates = {}
        for key, value in resolved_entities.items():
            if key in (
                "current_client", "current_project", "current_invoice",
                "current_mix_review", "current_audio_scan", "last_report",
                "last_search_query", "last_analyzed_track", "last_kenn_question",
            ):
                context_updates[key] = value

        # If client info was fetched, save the client name
        if intent.name == "client_mgmt" and "client_name" in intent.entities:
            context_updates["current_client"] = intent.entities["client_name"]
        for entity_key, context_key in {
            "project_name": "current_project",
            "invoice_id": "current_invoice",
            "review_id": "current_mix_review",
            "audio_path": "current_audio_scan",
            "audiogen_job_id": "current_audiogen_job",
        }.items():
            if intent.entities.get(entity_key):
                context_updates[context_key] = intent.entities[entity_key]
        if service_id == "kenn":
            context_updates["last_kenn_question"] = resolved_text

        # Update active voice based on the executed service agent
        if service_id == "admin_agent":
            context_updates["active_voice"] = "adam"
        elif service_id == "marketing_agent":
            context_updates["active_voice"] = "marketing"
        elif service_id == "research_agent":
            context_updates["active_voice"] = "research"
        elif service_id == "kenn":
            context_updates["active_voice"] = "kenn"
        else:
            # Standard services default to Thursday's voice
            context_updates["active_voice"] = "thursday"

        # Post-processors mutate handler_ctx
        for key in context:
            if key in handler_ctx and handler_ctx[key] != context.get(key):
                context_updates[key] = handler_ctx[key]

        # Capture IDs from responses for follow-up commands
        if service_id == "audiogen_render" and isinstance(result, str):
            match = re.search(r"Job ID:\s*([A-Za-z0-9_-]{8,64})", result)
            if match:
                context_updates["current_audiogen_job"] = match.group(1)

        # Track last visit time for returning-greeting detection
        context_updates["last_visit"] = datetime.datetime.now().isoformat()

        if context_updates:
            update_context(session, context_updates)
            context = get_context(session)

    except Exception as exc:
        logger.exception(
            "Thursday service failed service_id=%s session_id=%s",
            service_id,
            session.get("session_id", ""),
        )
        if brain_routing_active and decision.brain_decision:
            # No feedback_state stamping here: this fires before add_turn(session,
            # "thursday", ...) below (step 16, unreached on this path), so there is
            # no delivered response for the user to have reacted to -- correctly,
            # no accept/correct signal can exist for this row.
            _record_plan_trace(
                text=resolved_text,
                brain_decision=decision.brain_decision,
                service_id=service_id,
                status="failed",
                result_summary=str(exc),
                lesson=f"Avoid routing '{decision.brain_decision.abstract}' to service "
                       f"'{service_id}' the same way — it raised: {exc}",
                failure_reason="service_exception",
            )
        raise ServiceExecutionError(service_name) from exc

    # 16. Save turn to session
    add_turn(
        session,
        "user",
        text,
        intent.name,
        service_id,
        {**resolved_entities, **intent.entities},
    )
    try:
        save_session(session)
    except Exception:
        logger.warning("save_session failed for session %s", session.get("session_id"), exc_info=True)

    # 17. Record usage analytics + learning
    user_profile.record_request(service_id, profile_id=profile_id)
    diagnostics.record_usage(service_id, intent.name)

    if brain_routing_active and decision.brain_decision:
        plan_id = _record_plan_trace(
            text=resolved_text,
            brain_decision=decision.brain_decision,
            service_id=service_id,
            status="success",
            result_summary=str(result)[:500] if isinstance(result, str) else "",
        )
        _attach_plan_id_to_feedback_state(session, plan_id)
        try:
            save_session(session)
        except Exception:
            logger.warning("save_session failed for session %s", session.get("session_id"), exc_info=True)

    # 18. Get tone modifiers based on mood
    current_mood = user_profile.get_mood(profile_id)
    mood_modifiers = personality.get_mood_response_modifiers(current_mood)

    # 19. Format response with personality
    tone = {"style": mood_modifiers.get("style", "professional")}
    formatted = format_response(result, service_name, service_id, context, question=resolved_text)
    formatted = personality.format_with_tone(formatted, tone)

    # Add mood prefix if applicable
    mood_prefix = mood_modifiers.get("prefix")
    if mood_prefix and not formatted.startswith(mood_prefix):
        formatted = f"{mood_prefix}\n\n{formatted}"

    # 20. Daily briefing (on first interaction) — the canonical composer
    # with conversational framing (greeting, date, alerts, closing).
    if show_briefing and not alert_message:
        try:
            _, briefing = daily_brief.build_daily_brief(
                conversational=True,
                user_name=str(profile.get("user_name") or ""),
            )
            if briefing:
                # The conversational brief already opens with a time-based
                # greeting, so don't prepend another one — that produced a
                # duplicated "Good morning, Jack".
                formatted = f"{briefing}\n\n{formatted}"
                user_profile.mark_briefing_shown(profile_id)
        except Exception:
            # Non-critical -- the main response still returns without the
            # briefing, but a recurring failure should be visible.
            logger.warning("daily brief failed; continuing without it", exc_info=True)

    # 21. Prepend alerts if any
    if alert_message:
        formatted = f"{alert_message}\n\n{formatted}"

    # 22. Add suggested follow-ups based on learned patterns
    suggestion_added = False
    try:
        sequences = get_suggested_sequences(min_count=5)
        if sequences and not show_briefing:
            top_seq = sequences[0]
            if top_seq["suggest"] != service_id and top_seq["after"] != top_seq["suggest"]:
                formatted += (
                    f"\n\n*Suggestion:* After checking {top_seq['after']}, "
                    f"you often check {top_seq['suggest']}. "
                    f"Want me to run that too?"
                )
                suggestion_added = True
    except Exception:
        # Non-critical -- the main response still returns without a
        # sequence suggestion, but a recurring failure here should be visible.
        logger.warning("get_suggested_sequences failed; continuing without a sequence suggestion", exc_info=True)

    # 22b. Personalized suggestion from learned request/client patterns
    # (user_profile.get_suggestions() — frequent requests, frequent-client
    # shortcuts). This was computed every turn but never surfaced; only add
    # it when nothing else already offered a next step, to avoid stacking
    # suggestions the user didn't ask for.
    if not suggestion_added and not show_briefing:
        try:
            personal_suggestions = [
                s for s in user_profile.get_suggestions(profile_id)
                if s != "Start with a daily briefing"
            ]
            if personal_suggestions:
                formatted += f"\n\n*Suggestion:* {personal_suggestions[0]}"
        except Exception:
            # Non-critical -- the main response still returns without a
            # personalized suggestion, but a recurring failure here should
            # be visible.
            logger.warning("user_profile.get_suggestions failed; continuing without a personal suggestion", exc_info=True)

    if action_receipt_id:
        formatted = f"{formatted}\n\nAction receipt: {action_receipt_id}"
        receipt = complete_action(action_receipt_id, response_text=formatted)
        update_context(
            session,
            {
                "last_action_receipt": {
                    "receipt_id": receipt.receipt_id,
                    "service_id": receipt.service_id,
                    "status": receipt.status,
                }
            },
        )

    add_turn(session, "thursday", formatted, intent.name, service_id, {})

    return _kenn_contract_text(formatted, result) if service_id == "kenn" else formatted


# ─── Help text ────────────────────────────────────────────────────────────


def help_text(
    list_records: Callable[[str], list[dict]] | None = None,
) -> str:
    """Generate help text from all registered services."""
    from thursday.registry import build_services
    services = build_services(api)
    service_list = [svc.to_dict(service_id) for service_id, svc in services.items()]
    return format_help(service_list)
