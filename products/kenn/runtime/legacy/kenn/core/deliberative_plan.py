"""Typed, context-bound plans for KENN's deliberative assistant layer.

This module is deliberately model agnostic. A local or hosted model may emit a
candidate plan, but the candidate remains inert data until it passes this
contract. Passing validation still does not authorize execution: mutating work
may only be represented as a ``live_proposal`` and must subsequently travel
through KENN's existing confirmation-gated Live services.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import re
from typing import Any, Iterable

from kenn.core.session_context import validate_session_context


PLAN_SCHEMA = "kenn.deliberative_plan.v1"
STEP_SCHEMA = "kenn.deliberative_step.v1"
PLAN_SKETCH_SCHEMA = "kenn.deliberative_plan_sketch.v1"
MAX_STEPS = 8
MAX_LIST_ITEMS = 8
MAX_TEXT = 1_024

PLAN_STATUSES = frozenset({"ready", "needs_clarification", "refused"})
STEP_KINDS = frozenset({
    "inspection",
    "generation_job",
    "offline_render",
    "live_proposal",
    "clarification",
    "refusal",
})

# A deliberative step selects a bounded capability. It never contains a tool
# name, OSC address, Python expression, filesystem path, or executor payload.
KIND_ACTIONS = {
    "inspection": frozenset({
        "inspect_live",
        "inspect_device_capabilities",
        "review_generated_asset",
        "compare_offline_candidate",
    }),
    "generation_job": frozenset({"create_generation_job"}),
    "offline_render": frozenset({"create_offline_render", "bind_offline_render"}),
    "live_proposal": frozenset({"create_live_proposal", "revise_audition"}),
    "clarification": frozenset({"ask_user"}),
    "refusal": frozenset({"refuse"}),
}
ACTION_KINDS = {
    action: kind
    for kind, actions in KIND_ACTIONS.items()
    for action in actions
}

ACTION_EVIDENCE = {
    "inspect_live": ("fresh Live snapshot",),
    "inspect_device_capabilities": ("verified device capability matrix",),
    "review_generated_asset": ("verified completed generation artifact",),
    "compare_offline_candidate": ("verified completed offline-render receipt",),
    "create_generation_job": ("accepted generation-job receipt",),
    "revise_audition": ("typed confirmation-gated MIDI revision proposal",),
    "create_offline_render": ("accepted offline-render job receipt",),
    "bind_offline_render": ("accepted existing offline-render job receipt",),
    "create_live_proposal": ("typed confirmation-gated proposal",),
    "ask_user": ("user clarification",),
    "refuse": ("bounded-capability refusal",),
}

_STEP_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_FORBIDDEN_KEYS = frozenset({
    "arguments", "command", "code", "endpoint", "osc", "path", "payload",
    "shell", "tool", "tool_name", "url",
})
_FORBIDDEN_SKETCH_TEXT = re.compile(
    r"(?:```|https?://|file://|/(?:api|live|osc)/"
    r"|\b(?:confirmation_token|execution_authorized|tool_name)\b"
    r"|\bignore\s+(?:all|any|the|previous|prior|system|developer)\b"
    r"|\b(?:system|developer)\s+(?:prompt|message|instruction)s?\b"
    r"|\b(?:run|execute)\s+(?:python|javascript|shell|code|script)\b)",
    re.I,
)
_PLAN_FIELDS = frozenset({
    "schema", "goal", "session_id", "snapshot_fingerprint", "status", "steps",
    "assumptions", "unknowns", "model_provider", "model_id", "created_at",
    "execution_authorized",
})
_STEP_FIELDS = frozenset({
    "schema", "step_id", "kind", "action", "objective", "rationale",
    "depends_on", "expected_evidence", "mutating", "confirmation_required",
})
_SKETCH_FIELDS = frozenset({"schema", "steps", "assumptions", "unknowns"})
_SKETCH_STEP_FIELDS = frozenset({"action", "objective", "rationale"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _text(value: Any, *, limit: int = MAX_TEXT) -> str:
    return str(value or "").strip()[:limit]


def _contains_forbidden_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            str(key).strip().lower() in _FORBIDDEN_KEYS or _contains_forbidden_key(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_forbidden_key(item) for item in value)
    return False


def _contains_forbidden_sketch_text(value: Any) -> bool:
    if isinstance(value, str):
        return _FORBIDDEN_SKETCH_TEXT.search(value) is not None
    if isinstance(value, dict):
        return any(_contains_forbidden_sketch_text(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_forbidden_sketch_text(item) for item in value)
    return False


def _contains_forbidden_plan_prose(candidate: dict[str, Any]) -> bool:
    """Scan only model-authored prose, not the verbatim user goal."""
    prose = {
        "assumptions": candidate.get("assumptions"),
        "unknowns": candidate.get("unknowns"),
        "steps": [
            {
                "objective": step.get("objective"),
                "rationale": step.get("rationale"),
                "expected_evidence": step.get("expected_evidence"),
            }
            for step in (candidate.get("steps") or [])
            if isinstance(step, dict)
        ],
    }
    return _contains_forbidden_sketch_text(prose)


def _validate_text(value: Any, *, name: str, limit: int, required: bool = True) -> list[str]:
    if not isinstance(value, str):
        return [f"{name} must be a string."]
    if required and not value.strip():
        return [f"{name} is required."]
    if len(value) > limit:
        return [f"{name} exceeds {limit} characters."]
    return []


def _validate_text_list(value: Any, *, name: str, limit: int, required: bool = False) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return [f"{name} must be a list."]
    errors: list[str] = []
    if required and not value:
        errors.append(f"{name} must name expected evidence.")
    if len(value) > MAX_LIST_ITEMS:
        errors.append(f"{name} contains too many items.")
    for position, item in enumerate(value, start=1):
        errors.extend(_validate_text(item, name=f"{name} item {position}", limit=limit))
    return errors


@dataclass(frozen=True)
class DeliberativeStep:
    step_id: str
    kind: str
    action: str
    objective: str
    rationale: str
    depends_on: tuple[str, ...] = ()
    expected_evidence: tuple[str, ...] = ()
    mutating: bool = False
    confirmation_required: bool = False
    schema: str = STEP_SCHEMA

    @classmethod
    def create(
        cls,
        *,
        step_id: str,
        kind: str,
        action: str,
        objective: str,
        rationale: str,
        depends_on: tuple[str, ...] | list[str] = (),
        expected_evidence: tuple[str, ...] | list[str] = (),
    ) -> "DeliberativeStep":
        is_mutating = kind == "live_proposal"
        return cls(
            step_id=_text(step_id, limit=64),
            kind=_text(kind, limit=64),
            action=_text(action, limit=96),
            objective=_text(objective),
            rationale=_text(rationale),
            depends_on=tuple(_text(item, limit=64) for item in depends_on[:MAX_LIST_ITEMS]),
            expected_evidence=tuple(_text(item, limit=256) for item in expected_evidence[:MAX_LIST_ITEMS]),
            mutating=is_mutating,
            confirmation_required=is_mutating,
        )

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["depends_on"] = list(self.depends_on)
        result["expected_evidence"] = list(self.expected_evidence)
        return result


@dataclass(frozen=True)
class DeliberativePlan:
    goal: str
    session_id: str
    snapshot_fingerprint: str
    status: str
    steps: tuple[DeliberativeStep, ...]
    assumptions: tuple[str, ...] = ()
    unknowns: tuple[str, ...] = ()
    model_provider: str = "unknown"
    model_id: str = "unknown"
    created_at: str = field(default_factory=_now)
    schema: str = PLAN_SCHEMA
    execution_authorized: bool = False

    @classmethod
    def create(
        cls,
        *,
        goal: str,
        context: dict[str, Any],
        status: str,
        steps: tuple[DeliberativeStep, ...] | list[DeliberativeStep],
        assumptions: tuple[str, ...] | list[str] = (),
        unknowns: tuple[str, ...] | list[str] = (),
        model_provider: str = "unknown",
        model_id: str = "unknown",
    ) -> "DeliberativePlan":
        return cls(
            goal=_text(goal),
            session_id=_text(context.get("session_id"), limit=128),
            snapshot_fingerprint=_text(context.get("snapshot_fingerprint"), limit=96),
            status=_text(status, limit=64),
            steps=tuple(steps[:MAX_STEPS]),
            assumptions=tuple(_text(item, limit=256) for item in assumptions[:MAX_LIST_ITEMS]),
            unknowns=tuple(_text(item, limit=256) for item in unknowns[:MAX_LIST_ITEMS]),
            model_provider=_text(model_provider, limit=128) or "unknown",
            model_id=_text(model_id, limit=128) or "unknown",
        )

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["steps"] = [step.to_dict() for step in self.steps]
        result["assumptions"] = list(self.assumptions)
        result["unknowns"] = list(self.unknowns)
        return result


def validate_deliberative_plan(plan: Any, context: Any) -> dict[str, Any]:
    """Validate a candidate plan against the exact observed session context."""
    errors: list[str] = []
    context_result = validate_session_context(context)
    if not context_result.get("ok"):
        errors.extend(f"Invalid session context: {item}" for item in context_result.get("errors", []))
        return {"ok": False, "errors": errors, "schema": PLAN_SCHEMA}

    if isinstance(plan, DeliberativePlan):
        candidate = plan.to_dict()
    elif isinstance(plan, dict):
        candidate = plan
    else:
        return {"ok": False, "errors": ["Plan must be an object."], "schema": PLAN_SCHEMA}

    if _contains_forbidden_key(candidate):
        errors.append("Plan contains an executor payload or other forbidden control field.")
    if _contains_forbidden_plan_prose(candidate):
        errors.append("Plan contains instruction-like or executable model prose.")
    missing_plan_fields = sorted(_PLAN_FIELDS - set(candidate))
    if missing_plan_fields:
        errors.append("Plan is missing required fields: " + ", ".join(missing_plan_fields) + ".")
    unknown_plan_fields = sorted(set(candidate) - _PLAN_FIELDS)
    if unknown_plan_fields:
        errors.append("Plan contains unsupported fields: " + ", ".join(unknown_plan_fields) + ".")
    if candidate.get("schema") != PLAN_SCHEMA:
        errors.append(f"Expected {PLAN_SCHEMA}.")
    if candidate.get("execution_authorized") is not False:
        errors.append("Deliberative plans can never authorize execution.")
    errors.extend(_validate_text(candidate.get("goal"), name="Plan goal", limit=MAX_TEXT))
    if candidate.get("session_id") != context.get("session_id"):
        errors.append("Plan session_id does not match the session context.")
    if candidate.get("snapshot_fingerprint") != context.get("snapshot_fingerprint"):
        errors.append("Plan snapshot_fingerprint is stale or does not match the session context.")

    raw_status = candidate.get("status")
    status = raw_status if isinstance(raw_status, str) else ""
    if status not in PLAN_STATUSES:
        errors.append(f"Unsupported plan status: {status!r}.")
    for field_name in ("assumptions", "unknowns"):
        errors.extend(_validate_text_list(candidate.get(field_name), name=field_name, limit=256))
    for field_name in ("model_provider", "model_id"):
        errors.extend(_validate_text(candidate.get(field_name), name=field_name, limit=128))
    errors.extend(_validate_text(candidate.get("created_at"), name="created_at", limit=64))

    steps = candidate.get("steps")
    if not isinstance(steps, (list, tuple)) or not 1 <= len(steps) <= MAX_STEPS:
        errors.append(f"Plan must contain between 1 and {MAX_STEPS} steps.")
        steps = []

    seen: set[str] = set()
    prior_step_kinds: dict[str, str] = {}
    available_actions = set(context.get("available_actions") or [])
    kinds: list[str] = []
    for position, raw_step in enumerate(steps, start=1):
        if isinstance(raw_step, DeliberativeStep):
            step = raw_step.to_dict()
        elif isinstance(raw_step, dict):
            step = raw_step
        else:
            errors.append(f"Step {position} must be an object.")
            continue
        if _contains_forbidden_key(step):
            errors.append(f"Step {position} contains a forbidden control field.")
        missing_step_fields = sorted(_STEP_FIELDS - set(step))
        if missing_step_fields:
            errors.append(f"Step {position} is missing required fields: " + ", ".join(missing_step_fields) + ".")
        unknown_step_fields = sorted(set(step) - _STEP_FIELDS)
        if unknown_step_fields:
            errors.append(f"Step {position} contains unsupported fields: " + ", ".join(unknown_step_fields) + ".")
        if step.get("schema") != STEP_SCHEMA:
            errors.append(f"Step {position} must use {STEP_SCHEMA}.")
        raw_step_id = step.get("step_id")
        step_id = raw_step_id if isinstance(raw_step_id, str) else ""
        if not _STEP_ID.fullmatch(step_id):
            errors.append(f"Step {position} has an invalid step_id.")
        elif step_id in seen:
            errors.append(f"Step {position} duplicates step_id '{step_id}'.")
        raw_kind = step.get("kind")
        raw_action = step.get("action")
        kind = raw_kind if isinstance(raw_kind, str) else ""
        action = raw_action if isinstance(raw_action, str) else ""
        kinds.append(kind)
        if kind not in STEP_KINDS:
            errors.append(f"Step {position} has unsupported kind {kind!r}.")
        elif action not in KIND_ACTIONS[kind]:
            errors.append(f"Step {position} action {action!r} is invalid for kind {kind!r}.")
        errors.extend(_validate_text(step.get("objective"), name=f"Step {position} objective", limit=MAX_TEXT))
        errors.extend(_validate_text(step.get("rationale"), name=f"Step {position} rationale", limit=MAX_TEXT))
        dependencies = step.get("depends_on", [])
        dependency_errors = _validate_text_list(
            dependencies, name=f"Step {position} depends_on", limit=64,
        )
        errors.extend(dependency_errors)
        if not isinstance(dependencies, (list, tuple)):
            dependencies = []
        for dependency in dependencies:
            if isinstance(dependency, str) and dependency not in seen:
                errors.append(f"Step {position} dependency {dependency!r} must refer to an earlier step.")
        if kind not in {"clarification", "refusal"} and action not in available_actions:
            conditional_source_kind = {
                "review_generated_asset": "generation_job",
                "compare_offline_candidate": "offline_render",
            }.get(action)
            dependency_creates_capability = bool(
                conditional_source_kind
                and any(prior_step_kinds.get(str(dependency)) == conditional_source_kind for dependency in dependencies)
            )
            if not dependency_creates_capability:
                errors.append(f"Step {position} action {action!r} is unavailable in this session context.")
        evidence = step.get("expected_evidence", [])
        errors.extend(_validate_text_list(
            evidence, name=f"Step {position} expected_evidence", limit=256, required=True,
        ))
        should_mutate = kind == "live_proposal"
        if step.get("mutating") is not should_mutate:
            errors.append(f"Step {position} mutating flag does not match kind {kind!r}.")
        if step.get("confirmation_required") is not should_mutate:
            errors.append(f"Step {position} confirmation flag does not match kind {kind!r}.")
        seen.add(step_id)
        prior_step_kinds[step_id] = kind

    if status == "ready" and any(kind in {"clarification", "refusal"} for kind in kinds):
        errors.append("A ready plan cannot contain clarification or refusal steps.")
    if status == "needs_clarification" and (not kinds or kinds[-1] != "clarification" or "refusal" in kinds):
        errors.append("A needs_clarification plan must end with clarification and cannot contain refusal.")
    if status == "refused" and kinds != ["refusal"]:
        errors.append("A refused plan must contain exactly one refusal step.")

    return {
        "ok": not errors,
        "errors": errors,
        "schema": PLAN_SCHEMA,
        "execution_authorized": False,
        "step_count": len(steps),
        "mutating_step_count": sum(kind == "live_proposal" for kind in kinds),
    }


def deliberative_plan_json_schema(
    *, max_steps: int = MAX_STEPS, max_list_items: int = MAX_LIST_ITEMS,
) -> dict[str, Any]:
    """Return a bounded structural subset for constrained model decoding."""
    bounded_steps = max(1, min(MAX_STEPS, int(max_steps)))
    bounded_items = max(1, min(MAX_LIST_ITEMS, int(max_list_items)))
    all_actions = sorted({action for actions in KIND_ACTIONS.values() for action in actions})
    step = {
        "type": "object",
        "properties": {
            "schema": {"type": "string", "const": STEP_SCHEMA},
            "step_id": {"type": "string", "minLength": 1, "maxLength": 64},
            "kind": {"type": "string", "enum": sorted(STEP_KINDS)},
            "action": {"type": "string", "enum": all_actions},
            "objective": {"type": "string", "minLength": 1, "maxLength": MAX_TEXT},
            "rationale": {"type": "string", "minLength": 1, "maxLength": MAX_TEXT},
            "depends_on": {
                "type": "array", "maxItems": bounded_items,
                "items": {"type": "string", "minLength": 1, "maxLength": 64},
            },
            "expected_evidence": {
                "type": "array", "minItems": 1, "maxItems": bounded_items,
                "items": {"type": "string", "minLength": 1, "maxLength": 256},
            },
            "mutating": {"type": "boolean"},
            "confirmation_required": {"type": "boolean"},
        },
        "required": sorted(_STEP_FIELDS),
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "schema": {"type": "string", "const": PLAN_SCHEMA},
            "goal": {"type": "string", "minLength": 1, "maxLength": MAX_TEXT},
            "session_id": {"type": "string", "maxLength": 128},
            "snapshot_fingerprint": {"type": "string", "minLength": 8, "maxLength": 96},
            "status": {"type": "string", "enum": sorted(PLAN_STATUSES)},
            "steps": {"type": "array", "minItems": 1, "maxItems": bounded_steps, "items": step},
            "assumptions": {
                "type": "array", "maxItems": bounded_items,
                "items": {"type": "string", "maxLength": 256},
            },
            "unknowns": {
                "type": "array", "maxItems": bounded_items,
                "items": {"type": "string", "maxLength": 256},
            },
            "model_provider": {"type": "string", "minLength": 1, "maxLength": 128},
            "model_id": {"type": "string", "minLength": 1, "maxLength": 128},
            "created_at": {"type": "string", "minLength": 1, "maxLength": 64},
            "execution_authorized": {"type": "boolean", "const": False},
        },
        "required": sorted(_PLAN_FIELDS),
        "additionalProperties": False,
    }


def deliberative_plan_sketch_json_schema(
    *,
    max_steps: int = 3,
    max_list_items: int = 4,
    allowed_actions: Iterable[str] | None = None,
    allow_clarification: bool = True,
) -> dict[str, Any]:
    """Return the compact model-facing schema hydrated by trusted host code.

    Models choose semantic actions and prose only. Session identity,
    action kind, safety flags, evidence requirements, provider identity, and
    timestamps never need to be copied or invented by a model. KENN chains
    steps linearly because its coordinator exposes exactly one step at a time.
    """
    bounded_steps = max(1, min(MAX_STEPS, int(max_steps)))
    bounded_items = max(1, min(MAX_LIST_ITEMS, int(max_list_items)))
    if allowed_actions is None:
        action_choices = set(ACTION_KINDS)
    else:
        action_choices = {str(action) for action in allowed_actions} & set(ACTION_KINDS)
        action_choices.add("refuse")
        if allow_clarification:
            action_choices.add("ask_user")
        if "create_generation_job" in action_choices:
            action_choices.add("review_generated_asset")
        if "create_offline_render" in action_choices:
            action_choices.add("compare_offline_candidate")
    step = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": sorted(action_choices)},
            "objective": {"type": "string", "minLength": 1, "maxLength": MAX_TEXT},
            "rationale": {"type": "string", "minLength": 1, "maxLength": MAX_TEXT},
        },
        "required": sorted(_SKETCH_STEP_FIELDS),
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "schema": {"type": "string", "const": PLAN_SKETCH_SCHEMA},
            "steps": {"type": "array", "minItems": 1, "maxItems": bounded_steps, "items": step},
            "assumptions": {
                "type": "array", "maxItems": bounded_items,
                "items": {"type": "string", "maxLength": 256},
            },
            "unknowns": {
                "type": "array", "maxItems": bounded_items,
                "items": {"type": "string", "maxLength": 256},
            },
        },
        "required": sorted(_SKETCH_FIELDS),
        "additionalProperties": False,
    }


def hydrate_deliberative_plan_sketch(
    sketch: Any,
    *,
    goal: str,
    context: dict[str, Any],
    model_provider: str,
    model_id: str,
) -> dict[str, Any]:
    """Turn an untrusted compact sketch into a strict, context-bound plan."""
    errors: list[str] = []
    context_result = validate_session_context(context)
    if not context_result.get("ok"):
        errors.extend(f"Invalid session context: {item}" for item in context_result.get("errors", []))
    errors.extend(_validate_text(goal, name="Plan goal", limit=MAX_TEXT))
    if not isinstance(sketch, dict):
        errors.append("Plan sketch must be an object.")
        sketch = {}
    if _contains_forbidden_key(sketch):
        errors.append("Plan sketch contains an executor payload or forbidden control field.")
    if _contains_forbidden_sketch_text(sketch):
        errors.append("Plan sketch contains instruction-like or executable text.")
    missing = sorted(_SKETCH_FIELDS - set(sketch))
    if missing:
        errors.append("Plan sketch is missing required fields: " + ", ".join(missing) + ".")
    unsupported = sorted(set(sketch) - _SKETCH_FIELDS)
    if unsupported:
        errors.append("Plan sketch contains unsupported fields: " + ", ".join(unsupported) + ".")
    if sketch.get("schema") != PLAN_SKETCH_SCHEMA:
        errors.append(f"Expected {PLAN_SKETCH_SCHEMA}.")
    for field_name in ("assumptions", "unknowns"):
        errors.extend(_validate_text_list(sketch.get(field_name), name=field_name, limit=256))

    raw_steps = sketch.get("steps")
    if not isinstance(raw_steps, list) or not 1 <= len(raw_steps) <= MAX_STEPS:
        errors.append(f"Plan sketch must contain between 1 and {MAX_STEPS} steps.")
        raw_steps = []
    available_actions = set(context.get("available_actions") or [])
    terminal_actions = {"ask_user", "refuse"}
    steps: list[DeliberativeStep] = []
    for position, raw_step in enumerate(raw_steps, start=1):
        if not isinstance(raw_step, dict):
            errors.append(f"Sketch step {position} must be an object.")
            continue
        if _contains_forbidden_key(raw_step):
            errors.append(f"Sketch step {position} contains a forbidden control field.")
        missing_step = sorted(_SKETCH_STEP_FIELDS - set(raw_step))
        if missing_step:
            errors.append(
                f"Sketch step {position} is missing required fields: " + ", ".join(missing_step) + "."
            )
        unsupported_step = sorted(set(raw_step) - _SKETCH_STEP_FIELDS)
        if unsupported_step:
            errors.append(
                f"Sketch step {position} contains unsupported fields: " + ", ".join(unsupported_step) + "."
            )
        action = raw_step.get("action") if isinstance(raw_step.get("action"), str) else ""
        kind = ACTION_KINDS.get(action, "")
        if not kind:
            errors.append(f"Sketch step {position} has unsupported action {action!r}.")
        errors.extend(_validate_text(
            raw_step.get("objective"), name=f"Sketch step {position} objective", limit=MAX_TEXT,
        ))
        errors.extend(_validate_text(
            raw_step.get("rationale"), name=f"Sketch step {position} rationale", limit=MAX_TEXT,
        ))
        dependencies = [f"step-{position - 1}"] if position > 1 else []
        if kind and action not in available_actions and action not in terminal_actions:
            conditional_source = {
                "review_generated_asset": "generation_job",
                "compare_offline_candidate": "offline_render",
            }.get(action)
            dependency_creates_capability = bool(
                conditional_source
                and any(step.step_id in dependencies and step.kind == conditional_source for step in steps)
            )
            if not dependency_creates_capability:
                errors.append(f"Sketch step {position} action {action!r} is unavailable in this session context.")
        if kind:
            steps.append(DeliberativeStep.create(
                step_id=f"step-{position}",
                kind=kind,
                action=action,
                objective=raw_step.get("objective") if isinstance(raw_step.get("objective"), str) else "",
                rationale=raw_step.get("rationale") if isinstance(raw_step.get("rationale"), str) else "",
                depends_on=dependencies,
                expected_evidence=ACTION_EVIDENCE[action],
            ))

    actions = [step.action for step in steps]
    if actions == ["refuse"]:
        status = "refused"
    elif actions and actions[-1] == "ask_user" and "refuse" not in actions:
        status = "needs_clarification"
    else:
        status = "ready"
    plan = DeliberativePlan.create(
        goal=goal,
        context=context,
        status=status,
        steps=steps,
        assumptions=sketch.get("assumptions") if isinstance(sketch.get("assumptions"), list) else [],
        unknowns=sketch.get("unknowns") if isinstance(sketch.get("unknowns"), list) else [],
        model_provider=model_provider,
        model_id=model_id,
    ).to_dict()
    if not errors:
        checked = validate_deliberative_plan(plan, context)
        errors.extend(checked.get("errors", []))
    if errors:
        raise ValueError("Invalid plan sketch: " + "; ".join(errors))
    return plan


__all__ = [
    "ACTION_EVIDENCE",
    "ACTION_KINDS",
    "DeliberativePlan",
    "DeliberativeStep",
    "KIND_ACTIONS",
    "MAX_STEPS",
    "PLAN_SCHEMA",
    "PLAN_SKETCH_SCHEMA",
    "STEP_SCHEMA",
    "deliberative_plan_json_schema",
    "deliberative_plan_sketch_json_schema",
    "hydrate_deliberative_plan_sketch",
    "validate_deliberative_plan",
]
