"""Thursday Macro Engine — loads and executes YAML-defined macros.

Macros are stored as YAML files in the macros/ directory and define
reusable sequences of actions, triggers, and conditional steps.
"""

from __future__ import annotations

import logging
import os
import re
import time
import yaml
from pathlib import Path
from typing import Any, Callable
from datetime import datetime, date

MACROS_DIR = Path(__file__).resolve().parent
logger = logging.getLogger(__name__)


class MacroStep:
    """A single step within a macro."""

    def __init__(self, step_def: dict):
        self.service = step_def.get("service")
        self.say = step_def.get("say")
        self.ask = step_def.get("ask")
        self.if_condition = step_def.get("if")

    def is_service(self) -> bool:
        return self.service is not None

    def is_say(self) -> bool:
        return self.say is not None

    def is_ask(self) -> bool:
        return self.ask is not None

    def is_conditional(self) -> bool:
        return self.if_condition is not None


class Macro:
    """A named, triggerable macro (YAML-defined workflow)."""

    def __init__(self, name: str, data: dict, filepath: str | None = None):
        self.name = name
        self.description = data.get("description", "")
        self.triggers = data.get("triggers", {})
        self.requires = data.get("requires", [])
        self.filepath = filepath
        self.steps = [MacroStep(s) for s in data.get("steps", [])]

    def matches_trigger(self, text: str) -> bool:
        """Check if user input matches this macro's trigger phrase."""
        text_lower = text.lower().strip()

        # Check phrase triggers
        phrase = self.triggers.get("phrase", "")
        if phrase:
            if phrase.endswith("*"):
                prefix = phrase[:-1].lower()
                if text_lower.startswith(prefix):
                    return True
            elif phrase.lower() in text_lower:
                return True

        # Check regex triggers
        for pattern in self.triggers.get("patterns", []):
            if re.search(pattern, text_lower):
                return True

        # Check exact name match
        if self.name.lower() in text_lower:
            return True

        return False

    def extract_params(self, text: str) -> dict:
        """Extract parameters from a trigger match.

        E.g., "onboard Sarah" with trigger "onboard *" → {client_name: "Sarah"}.
        """
        params = {}
        phrase = self.triggers.get("phrase", "")

        if phrase.endswith("*"):
            prefix = phrase[:-1].lower().strip()
            if text.lower().startswith(prefix):
                param_text = text[len(prefix):].strip()
                if param_text:
                    # Map positional params to required fields
                    if self.requires:
                        params[self.requires[0]] = _clean_name(param_text)
        return params

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "triggers": self.triggers,
            "requires": self.requires,
            "steps": [
                {"service": s.service, "say": s.say, "ask": s.ask}
                for s in self.steps
            ],
        }


def _clean_name(text: str) -> str:
    """Clean a extracted name parameter."""
    words = text.strip().rstrip(".,!?;:").split()
    return " ".join(w.capitalize() for w in words if w)


# ─── Public API ──────────────────────────────────────────────────────────


def load_macros() -> list[Macro]:
    """Load all macros from the macros directory.

    Scans for *.yaml and *.yml files and parses them into Macro objects.
    """
    macros = []
    for path in sorted(MACROS_DIR.glob("*.yaml")) + sorted(MACROS_DIR.glob("*.yml")):
        if path.name.startswith("__"):
            continue
        try:
            data = yaml.safe_load(path.read_text())
            if data and "steps" in data:
                name = data.get("name", path.stem.replace("_", " ").title())
                macros.append(Macro(name, data, filepath=str(path)))
        except (yaml.YAMLError, OSError) as e:
            print(f"Warning: Could not load macro {path.name}: {e}")
            continue

    return macros


def find_matching_macro(text: str) -> Macro | None:
    """Find the best-matching macro for the given text.

    Args:
        text: The user's request.

    Returns:
        Matching Macro or None.
    """
    for macro in load_macros():
        if macro.matches_trigger(text):
            return macro
    return None


class MacroStepError(Exception):
    """Raised when a macro step fails."""
    pass


def execute_macro(
    macro: Macro,
    handle_func: Callable,
    session: dict,
    params: dict | None = None,
    *,
    trigger_text: str = "",
    confirmed_token: str | None = None,
) -> list[str]:
    """Execute a macro, routing every registered-service step through the
    same authoritative safety gate (thursday.registry.request_risk +
    thursday.confirmation + thursday.action_receipts) the normal per-turn
    orchestrator dispatch and multi-step brain plans use.

    Previously a macro step calling a real registry service invoked
    `service_def.action()` directly, gated only by a keyword heuristic over
    the service id string itself (`_service_may_mutate`) — never through
    `request_risk()`/the HMAC confirmation-token system — and "confirmed"
    was a bare `text.lower().startswith("confirm <macro name>")` string
    match with no signature, session binding, or expiry (see
    docs/audits/2026-08-20-thursday-nitedsp-forensic-audit.md, P0-6). Any
    LOCAL_MUTATION/EXTERNAL_COMMUNICATION/DESTRUCTIVE step could run with
    zero real confirmation. This function now pauses at the first step that
    `request_risk()` classifies as confirmation-required, issues a real
    signed token via `issue_confirmation()`, and only resumes it via a
    verified `confirmed_token` (checked with `verify_confirmation()` and
    claimed via `claim_action()` so a replayed confirmation cannot
    duplicate the side effect) — structurally the same pause/resume
    contract `orchestrator._execute_plan_from`/`resume_brain_plan` already
    use for multi-step brain plans.

    Args:
        macro: The Macro to execute.
        handle_func: The orchestrator handle function (used only as a
            fallback for a step naming a service id that isn't registered —
            that path already re-enters the full orchestrator gate on its
            own, so it needs no additional gating here).
        session: The current session (real sessions from
            `session_manager.get_or_create_session()`; a plain `{"context":
            {}}` dict is also accepted for macros with no confirmation-
            requiring steps, since the pause path is the only one that
            persists to the session).
        params: Optional parameters extracted from the trigger match.
        trigger_text: The user's original request text. Used (a) to bind
            the confirmation token/receipt to a concrete request, exactly
            like the single-step and multi-step-plan paths, and (b) as the
            `text` argument to `request_risk()` for services whose
            classification depends on keyword content.
        confirmed_token: A verified confirmation token from a prior pause,
            supplied by the orchestrator's top-level "confirm <token>"
            handler after `verify_confirmation()` already succeeded there.
            Do not pass an unverified token — the caller is trusted to have
            checked it first, matching the existing single-step/plan resume
            contract.

    Returns:
        List of step result strings.
    """
    from thursday import client as api
    from thursday.registry import build_services, request_risk
    from thursday.confirmation import issue_confirmation
    from thursday.action_receipts import claim_action, complete_action, receipt_id_for_token
    from thursday.session_manager import get_context, update_context

    params = dict(params or {})
    context = get_context(session) if isinstance(session, dict) else {}
    if not isinstance(context, dict):
        context = {}
    session_id = str(session.get("session_id") or "") if isinstance(session, dict) else ""

    results: list[str] = []
    completed_stages: list[str] = []
    start_index = 0
    resuming = False
    resuming_receipt_id = ""
    gate_text = trigger_text or macro.name

    if confirmed_token:
        pending_macros = context.get("pending_macros")
        pending_entry = pending_macros.get(confirmed_token) if isinstance(pending_macros, dict) else None
        if not isinstance(pending_entry, dict) or pending_entry.get("macro_name") != macro.name:
            return ["That confirmation does not match a pending step of this macro. The action was not run."]
        pend_service_id = str(pending_entry.get("service_id") or "")
        pend_text = str(pending_entry.get("text") or "")
        resuming_receipt_id = receipt_id_for_token(confirmed_token)
        claim = claim_action(
            resuming_receipt_id, session_id=session_id, service_id=pend_service_id, text=pend_text,
        )
        if not claim.claimed:
            if claim.receipt.status == "completed":
                return [claim.receipt.response_text]
            return [f"That action is already being processed. Receipt: {claim.receipt.receipt_id}"]
        start_index = int(pending_entry.get("step_index", 0))
        results = list(pending_entry.get("results") or [])
        completed_stages = list(pending_entry.get("completed_stages") or [])
        params = dict(pending_entry.get("params") or params)
        gate_text = pend_text or gate_text
        resuming = True
        # Consume this token everywhere it's tracked (pending_macros AND the
        # top-level pending_confirmations/pending_confirmation slots the
        # orchestrator's "confirm <token>" interception checks) -- mirrors
        # orchestrator._pause_plan_for_confirmation's own resume-consumption
        # exactly, so a second "confirm <token>" for the same step falls
        # through to the receipt-based replay-safe path instead of finding a
        # stale pending_confirmations entry and mis-routing.
        remaining_macros = {t: v for t, v in pending_macros.items() if t != confirmed_token}
        remaining_confirmations = {
            t: v for t, v in (context.get("pending_confirmations") or {}).items()
            if t != confirmed_token
        }
        consume_updates: dict = {
            "pending_macros": remaining_macros,
            "pending_confirmations": remaining_confirmations,
        }
        current_pending_confirmation = context.get("pending_confirmation")
        if isinstance(current_pending_confirmation, dict) and current_pending_confirmation.get("token") == confirmed_token:
            consume_updates["pending_confirmation"] = None
        update_context(session, consume_updates)
        context = get_context(session)

    try:
        services = build_services(api)
    except Exception:
        logger.warning(
            "macro %r: service registry unavailable, running with no registered services "
            "(every service step falls back to the legacy NLU-routed handler)",
            macro.name,
            exc_info=True,
        )
        services = {}

    service_text = ""
    for i in range(start_index, len(macro.steps)):
        step = macro.steps[i]
        stage_num = i + 1
        stage_desc = f"Stage {stage_num}"
        if step.is_service():
            stage_desc += f" ({step.service})"
        elif step.is_say():
            stage_desc += " (Say)"
        elif step.is_ask():
            stage_desc += " (Ask)"

        try:
            if step.is_say():
                results.append(step.say)
                completed_stages.append(stage_desc)

            elif step.is_service():
                service_text = step.service
                if "{{" in service_text:
                    service_text = _interpolate(service_text, params)

                service_def = services.get(service_text)
                if service_def is None:
                    # Not a registered service id: keep the safe legacy NLU
                    # fallback, which re-enters orchestrator.handle() and so
                    # already re-applies the full risk/confirmation gate on
                    # its own -- no additional gating needed here.
                    result = _run_via_nlu_fallback(service_text, handle_func, session)
                    results.append(result)
                    completed_stages.append(stage_desc)
                    continue

                if resuming and i == start_index:
                    # This exact step's confirmation was already verified and
                    # claimed above -- run it once, do not re-pause. The
                    # receipt is completed once at the very end of this
                    # function (covering both "ran to completion" and "paused
                    # again at a later step"), not here.
                    result = _invoke_registered_service(service_def, service_text, api, session)
                    results.append(result)
                    completed_stages.append(stage_desc)
                    continue

                action_risk = request_risk(service_text, gate_text)
                if action_risk.requires_confirmation:
                    token, pending = issue_confirmation(
                        session_id=session_id, service_id=service_text, text=gate_text,
                    )
                    pending["risk"] = action_risk.value
                    now = int(time.time())
                    live_pending_macros = {
                        t: v for t, v in (context.get("pending_macros") or {}).items()
                        if isinstance(v, dict) and int(v.get("expires_at") or 0) > now
                    }
                    live_pending_macros[token] = {
                        **pending,
                        "macro_name": macro.name,
                        "step_index": i,
                        "results": results,
                        "completed_stages": completed_stages,
                        "params": params,
                    }
                    live_pending_confirmations = {
                        t: v for t, v in (context.get("pending_confirmations") or {}).items()
                        if isinstance(v, dict) and int(v.get("expires_at") or 0) > now
                    }
                    live_pending_confirmations[token] = pending
                    update_context(session, {
                        "pending_macros": live_pending_macros,
                        "pending_confirmations": live_pending_confirmations,
                        "pending_confirmation": pending,
                    })
                    results.append(
                        f"This step would run {service_def.name} with risk level "
                        f"'{action_risk.value}'. It has not run. "
                        f"To approve this exact step within five minutes, reply: confirm {token}"
                    )
                    if resuming:
                        complete_action(resuming_receipt_id, response_text="\n\n".join(results))
                    return results

                result = _invoke_registered_service(service_def, service_text, api, session)
                results.append(result)
                completed_stages.append(stage_desc)

            elif step.is_conditional():
                # Simple conditional: check if the previous result contains a keyword
                condition_text = step.if_condition
                if results and condition_text.lower() in results[-1].lower():
                    # Execute sub-steps (not fully utilized in YAMLs, but kept safe)
                    pass

            elif step.is_ask():
                results.append(f"[{macro.name} asks:] {step.ask}")
                completed_stages.append(stage_desc)

        except Exception as exc:
            reason = str(exc)
            stages_completed_str = ", ".join(completed_stages) if completed_stages else "None"

            # Formulate structured partial success error message
            err_msg = f"Stages {stages_completed_str} completed. {stage_desc} failed: {reason}."

            # Append recovery suggestion
            from thursday.errors import suggest_alternatives
            alternatives = suggest_alternatives(service_text if step.is_service() else reason)
            recovery_options = "\n".join(f"  - {alt}" for alt in alternatives)
            err_msg += f"\n\nRecovery suggestions:\n{recovery_options}"

            results.append(err_msg)
            break

    if resuming:
        complete_action(resuming_receipt_id, response_text="\n\n".join(results))
    return results


def _run_via_nlu_fallback(service_text: str, handle_func: Callable, session: dict) -> str:
    """Route an unregistered macro step through the orchestrator's NLU
    pipeline (`handle_func`). Only used for step ids that aren't real
    registry ids; re-enters `orchestrator.handle()`, which already applies
    the full request_risk/confirmation gate on its own, so no separate
    gating is needed at this call site."""
    try:
        return handle_func(service_text, session)
    except Exception as exc:
        raise MacroStepError(str(exc)) from exc


def _invoke_registered_service(service_def, service_text: str, api, session: dict) -> str:
    """Invoke an already risk-cleared/confirmed registry service's action.

    Callers (`execute_macro`) are responsible for the request_risk /
    confirmation / idempotency-claim gate before this is ever called — this
    function performs no gating of its own, matching how `best_service.action`
    is invoked directly once the same gate has already cleared it in
    `orchestrator.handle()`.
    """
    try:
        from thursday.session_manager import get_context
    except ImportError:
        get_context = None

    handler_ctx: dict = {}
    if get_context is not None:
        try:
            handler_ctx = dict(get_context(session))
        except Exception:
            logger.warning(
                "macro step %r: get_context failed, running with an empty context "
                "(no current client/session data) instead of the real one",
                service_text,
                exc_info=True,
            )
            handler_ctx = {}
    try:
        from app.db import add_record as _add_record, update_record as _update_record, list_records as _list_records
    except ImportError:
        _list_records = lambda _name: []  # noqa: E731
        _add_record = lambda _name, record: record  # noqa: E731
        _update_record = lambda *_args, **_kwargs: None  # noqa: E731
    handler_ctx.setdefault("_list_records", _list_records)
    handler_ctx.setdefault("_add_record", _add_record)
    handler_ctx.setdefault("_update_record", _update_record)

    try:
        result = service_def.action(handler_ctx, api, "")
    except Exception as exc:
        logger.exception("Macro step failed service=%s", service_text)
        raise MacroStepError(f"Macro step '{service_text}' failed (error: {exc}).")

    if service_def.post_process:
        try:
            service_def.post_process(handler_ctx, result)
        except Exception:
            pass

    result = result or f"({service_text} returned no output)"
    if isinstance(result, str) and ("failed (error code:" in result or "failed (error:" in result):
        raise MacroStepError(result)
    return result


def _interpolate(text: str, params: dict) -> str:
    """Replace {{placeholder}} with actual parameter values."""
    for key, value in params.items():
        placeholder = "{{" + key + "}}"
        text = text.replace(placeholder, str(value))
    return text
