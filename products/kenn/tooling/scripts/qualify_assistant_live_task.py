#!/usr/bin/env python3
"""Qualify one model-planned, reversible assistant task against real Ableton.

Proposal-only mode is the default. ``--apply`` is explicit authorization for
one disposable-set mutation followed by replay rejection and identity-bound
undo. A passing receipt requires the final session fingerprint to equal the
initial fingerprint. This runner never opens an AbletonOSC socket itself.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from typing import Any
from urllib.request import Request


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "backend" / "src"))

from kenn.core.assistant_coordinator import AssistantCoordinator  # noqa: E402
from kenn.core.assistant_task_memory import AssistantTaskStore  # noqa: E402
from kenn.core.mcp_facade import KennHTTPClient, KennMCPFacade  # noqa: E402
from kenn.core.ollama_deliberative import (  # noqa: E402
    OllamaDeliberativeGenerator, open_loopback_ollama, validate_ollama_base_url,
)


SCHEMA = "kenn.real_live_assistant_task_qualification.v1"
DEFAULT_PLANNER_BAKEOFF = ROOT / "evaluation" / "results" / "KENN_DELIBERATIVE_MODEL_BAKEOFF.json"
DEFAULT_TRANSFORMERS_TRANSPORT = ROOT / "tooling" / "scripts" / "serve_transformers_ollama_compat.py"
_SECRET_FIELDS = {"confirmation_token", "confirm_token", "token"}


def source_revision() -> str:
    """Return the bound source revision without making archives unrunnable.

    Release qualification still requires a real Git checkout through the
    external gate.  Sanitized source archives used for isolated tests have no
    ``.git`` directory, so they receive an explicit unavailable marker rather
    than failing during receipt construction.
    """
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"


def runner_sha256() -> str:
    return hashlib.sha256(Path(__file__).resolve().read_bytes()).hexdigest()


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _redact(item)
            for key, item in value.items()
            if str(key).casefold() not in _SECRET_FIELDS
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _blocked(message: str, *, stage: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "evidence_kind": "real_live",
        "status": "blocked",
        "stage": stage,
        "error": message,
        "changed": False,
        "events": _redact(events),
        "limitations": ["A blocked result is not real-Live assistant qualification evidence."],
    }


def _action_id(proposal: dict[str, Any]) -> str:
    return str(proposal.get("action_id") or proposal.get("id") or "")


def _context_summary(context: dict[str, Any]) -> dict[str, Any]:
    transport = context.get("transport") if isinstance(context.get("transport"), dict) else {}
    tracks = context.get("tracks") if isinstance(context.get("tracks"), list) else []
    return {
        "schema": context.get("schema"),
        "session_id": context.get("session_id"),
        "snapshot_fingerprint": context.get("snapshot_fingerprint"),
        "transport_status": transport.get("status"),
        "track_count": len(tracks),
        "available_actions": sorted(str(item) for item in (context.get("available_actions") or [])),
    }


def _post_write_failure(
    *, base: dict[str, Any], events: list[dict[str, Any]], facade: KennMCPFacade,
    session_id: str, initial_fingerprint: str, receipt: dict[str, Any],
    assistant_task_completed: bool, replay_rejected: bool, stage: str,
    error_type: str,
) -> dict[str, Any]:
    """Record uncertain recovery state without retrying a post-write operation."""
    events.append({"stage": stage, "error_type": error_type})
    final_fingerprint = ""
    try:
        final = facade._dispatch("kenn_context", {"session_id": session_id})
        if not isinstance(final, dict):
            raise TypeError("Recovery context response was not an object.")
        events.append({"stage": "recovery_context", "context": _context_summary(final)})
        if str(final.get("session_id") or "") != session_id:
            raise ValueError("Recovery context session identity did not match.")
        final_fingerprint = str(final.get("snapshot_fingerprint") or "")
    except Exception as exc:
        events.append({"stage": "recovery_context_failed", "error_type": type(exc).__name__})
    restored = bool(initial_fingerprint and final_fingerprint == initial_fingerprint)
    return {
        **base,
        "status": "failed" if restored else "transport_uncertain",
        "changed": False if restored else (True if final_fingerprint else None),
        "write_receipt": _redact(receipt),
        "assistant_task_completed": assistant_task_completed,
        "replay_rejected": replay_rejected,
        "final_snapshot_fingerprint": final_fingerprint or None,
        "restored_exactly": restored,
        "retry_allowed": False,
        "recovery_required": [] if restored else ["live_receipts", "live_snapshot", "manual_restore"],
        "error": "Post-write recovery was interrupted; no uncertain operation was retried.",
        "events": _redact(events),
    }


def write_evidence(path: Path, result: dict[str, Any]) -> None:
    """Atomically persist private real-session evidence."""
    destination = path.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    payload = (json.dumps(result, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        os.chmod(destination, 0o600)
        directory = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def qualified_planner_identity(path: Path, model: str) -> str:
    evidence = path.expanduser().resolve()
    try:
        data = json.loads(evidence.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"planner bake-off evidence is unavailable or invalid: {exc}") from exc
    recommended = str(data.get("recommended_model") or "")
    if str(model) != recommended:
        raise ValueError(
            f"model must exactly match the qualified planner recommendation {recommended!r}"
        )
    return hashlib.sha256(evidence.read_bytes()).hexdigest()


def qualified_planner_provider(path: Path) -> str:
    evidence = path.expanduser().resolve()
    try:
        data = json.loads(evidence.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"planner bake-off evidence is unavailable or invalid: {exc}") from exc
    provider = str(data.get("provider") or "").strip()
    if provider not in {"transformers", "ollama"}:
        raise ValueError("planner bake-off evidence has no supported provider identity")
    return provider


def verify_transformers_transport(base_url: str, model: str, source_path: Path) -> str:
    """Verify the loopback bridge is running the exact reviewed source file."""
    expected = hashlib.sha256(source_path.expanduser().resolve().read_bytes()).hexdigest()
    origin = validate_ollama_base_url(base_url)
    request = Request(origin + "/api/tags", method="GET")
    with open_loopback_ollama(request, timeout=5) as response:
        payload = json.loads(response.read())
    transport = payload.get("kenn_transport") if isinstance(payload, dict) else None
    models = payload.get("models") if isinstance(payload, dict) else None
    model_ids = {
        str(item.get("model") or item.get("name") or "")
        for item in models or [] if isinstance(item, dict)
    }
    if (
        not isinstance(transport, dict)
        or transport.get("schema") != "kenn.transformers_ollama_compat.v1"
        or transport.get("source_sha256") != expected
        or model not in model_ids
    ):
        raise ValueError("Transformers bridge identity does not match the reviewed source and model.")
    return expected


def qualify(
    *, facade: KennMCPFacade, goal: str, command: str, session_id: str,
    apply: bool = False, planner_evidence_sha256: str = "",
    planner_transport_sha256: str = "",
) -> dict[str, Any]:
    """Drive one bounded assistant trajectory through the existing MCP facade."""
    events: list[dict[str, Any]] = []
    try:
        initial = facade._dispatch("kenn_context", {"session_id": session_id})
        if not isinstance(initial, dict):
            raise TypeError("Initial context response was not an object.")
    except Exception as exc:
        return _blocked(f"Initial real-Live context failed: {type(exc).__name__}: {exc}", stage="context", events=events)
    events.append({"stage": "initial_context", "context": _context_summary(initial)})
    initial_transport = initial.get("transport") if isinstance(initial.get("transport"), dict) else {}
    if initial_transport.get("status") != "connected":
        return _blocked("Ableton Live is not connected.", stage="context", events=events)
    if str(initial.get("session_id") or "") != session_id:
        return _blocked("Initial context session identity did not match.", stage="context", events=events)
    initial_fingerprint = str(initial.get("snapshot_fingerprint") or "")
    if not initial_fingerprint:
        return _blocked("Initial context had no snapshot fingerprint.", stage="context", events=events)

    try:
        planned = facade._dispatch("plan_assistant_task", {"goal": goal, "session_id": session_id})
    except Exception as exc:
        return _blocked(f"Assistant planning failed: {type(exc).__name__}: {exc}", stage="plan", events=events)
    events.append({"stage": "planned", "result": planned})
    task = planned.get("task") if isinstance(planned.get("task"), dict) else None
    if not planned.get("ok") or task is None or planned.get("planner_source") != "model_sketch":
        return _blocked("A model-produced assistant task was not accepted.", stage="plan", events=events)
    task_id = str(task.get("task_id") or "")
    next_step = planned.get("next_step") if isinstance(planned.get("next_step"), dict) else {}

    inspected = 0
    while next_step.get("mode") == "inspect" and inspected < 3:
        step_id = str(next_step.get("step_id") or "")
        try:
            observed = facade._dispatch(
                "record_assistant_observation",
                {"task_id": task_id, "step_id": step_id, "session_id": session_id},
            )
        except Exception as exc:
            return _blocked(f"Assistant observation failed: {type(exc).__name__}: {exc}", stage="observation", events=events)
        events.append({"stage": "observed", "result": observed})
        next_step = observed.get("next_step") if isinstance(observed.get("next_step"), dict) else {}
        inspected += 1
    if next_step.get("mode") != "prepare_live_proposal":
        return _blocked("The model plan did not reach one bounded Live proposal.", stage="trajectory", events=events)
    proposal_step_id = str(next_step.get("step_id") or "")

    try:
        proposed = facade._dispatch(
            "create_live_proposal",
            {
                "command": command,
                "session_id": session_id,
                "assistant_task_id": task_id,
                "assistant_step_id": proposal_step_id,
            },
        )
    except Exception as exc:
        return _blocked(f"Proposal creation failed: {type(exc).__name__}: {exc}", stage="proposal", events=events)
    events.append({"stage": "proposal", "result": proposed})
    proposal = proposed.get("proposal") if isinstance(proposed.get("proposal"), dict) else None
    proposal_binding = proposed.get("assistant_task") if isinstance(proposed.get("assistant_task"), dict) else {}
    if (
        proposed.get("status") != "confirmation_required"
        or proposal is None
        or proposed.get("changed") is True
        or proposal_binding.get("next_step", {}).get("mode") != "wait_for_confirmation"
    ):
        return _blocked("KENN did not return a confirmation-only proposal.", stage="proposal", events=events)

    base = {
        "schema": SCHEMA,
        "evidence_kind": "real_live",
        "source_git_commit": source_revision(),
        "runner_sha256": runner_sha256(),
        "session_id": session_id,
        "planner_provider": facade.planner_provider,
        "planner_id": facade.planner_id,
        "planner_evidence_sha256": str(planner_evidence_sha256),
        "planner_transport_sha256": str(planner_transport_sha256),
        "task_id": task_id,
        "initial_snapshot_fingerprint": initial_fingerprint,
        "plan": _redact(task.get("plan")),
        "proposal": _redact(proposal),
        "events": _redact(events),
    }
    if not apply:
        return {
            **base,
            "status": "proposal_ready",
            "changed": False,
            "limitations": [
                "Proposal-only mode performed no Live write.",
                "Rerun with --apply only after reviewing the exact proposal on a disposable set.",
            ],
        }

    token = str(proposal.get("confirmation_token") or "")
    action_id = _action_id(proposal)
    if not token or not action_id:
        return {**base, "status": "failed", "changed": False, "error": "Proposal lacked confirmation identity."}
    apply_args = {
        "proposal": proposal,
        "confirm_token": token,
        "session_id": session_id,
        "idempotency_key": action_id,
        "assistant_task_id": task_id,
        "assistant_step_id": proposal_step_id,
    }
    try:
        executed = facade._dispatch("apply_live_proposal", apply_args)
        if not isinstance(executed, dict):
            raise TypeError("Apply response was not an object.")
    except Exception as exc:
        return _post_write_failure(
            base=base, events=events, facade=facade, session_id=session_id,
            initial_fingerprint=initial_fingerprint, receipt={},
            assistant_task_completed=False, replay_rejected=False,
            stage="apply_response_uncertain", error_type=type(exc).__name__,
        )
    receipt = executed.get("receipt") if isinstance(executed.get("receipt"), dict) else None
    execution_binding = executed.get("assistant_task") if isinstance(executed.get("assistant_task"), dict) else {}
    bound_task = execution_binding.get("task") if isinstance(execution_binding.get("task"), dict) else {}
    assistant_task_completed = bool(
        bound_task.get("task_id") == task_id
        and bound_task.get("status") == "completed"
        and execution_binding.get("next_step", {}).get("mode") == "complete"
    )
    events.append({"stage": "applied", "result": executed})
    if receipt is None:
        return _post_write_failure(
            base=base, events=events, facade=facade, session_id=session_id,
            initial_fingerprint=initial_fingerprint, receipt={},
            assistant_task_completed=assistant_task_completed,
            replay_rejected=False, stage="apply_receipt_missing",
            error_type="MissingReceipt",
        )
    write_verified = bool(
        receipt.get("status") == "applied"
        and receipt.get("verified") is True
        and str(receipt.get("action_id") or "") == action_id
    )

    replay_rejected = False
    try:
        replay = facade._dispatch("apply_live_proposal", {
            "proposal": proposal, "confirm_token": token, "session_id": session_id,
            "idempotency_key": action_id,
        })
        replay_rejected = not bool(replay.get("ok")) and replay.get("status") != "applied"
        events.append({"stage": "replay", "result": replay})
    except Exception as exc:
        # Replay verification is secondary to restoring the now-mutated set.
        # Record only the exception type: provider messages may contain request data.
        events.append({"stage": "replay_failed", "error_type": type(exc).__name__})

    try:
        undo_proposed = facade._dispatch("undo_live_receipt", {"receipt": receipt, "session_id": session_id})
        if not isinstance(undo_proposed, dict):
            raise TypeError("Undo proposal response was not an object.")
    except Exception as exc:
        return _post_write_failure(
            base=base, events=events, facade=facade, session_id=session_id,
            initial_fingerprint=initial_fingerprint, receipt=receipt,
            assistant_task_completed=assistant_task_completed,
            replay_rejected=replay_rejected, stage="undo_proposal_failed",
            error_type=type(exc).__name__,
        )
    undo = undo_proposed.get("proposal") if isinstance(undo_proposed.get("proposal"), dict) else None
    events.append({"stage": "undo_proposal", "result": undo_proposed})
    if undo is None:
        return _post_write_failure(
            base=base, events=events, facade=facade, session_id=session_id,
            initial_fingerprint=initial_fingerprint, receipt=receipt,
            assistant_task_completed=assistant_task_completed,
            replay_rejected=replay_rejected, stage="undo_proposal_missing",
            error_type="MissingUndoProposal",
        )
    try:
        undo_executed = facade._dispatch("undo_live_receipt", {
            "receipt": receipt,
            "proposal": undo,
            "session_id": session_id,
            "confirm_token": str(undo.get("confirmation_token") or ""),
            "idempotency_key": _action_id(undo),
        })
        if not isinstance(undo_executed, dict):
            raise TypeError("Undo response was not an object.")
    except Exception as exc:
        return _post_write_failure(
            base=base, events=events, facade=facade, session_id=session_id,
            initial_fingerprint=initial_fingerprint, receipt=receipt,
            assistant_task_completed=assistant_task_completed,
            replay_rejected=replay_rejected, stage="undo_apply_failed",
            error_type=type(exc).__name__,
        )
    events.append({"stage": "undo_applied", "result": undo_executed})
    try:
        final = facade._dispatch("kenn_context", {"session_id": session_id})
        if not isinstance(final, dict):
            raise TypeError("Final context response was not an object.")
        if str(final.get("session_id") or "") != session_id:
            raise ValueError("Final context session identity did not match.")
    except Exception as exc:
        return _post_write_failure(
            base=base, events=events, facade=facade, session_id=session_id,
            initial_fingerprint=initial_fingerprint, receipt=receipt,
            assistant_task_completed=assistant_task_completed,
            replay_rejected=replay_rejected, stage="final_context_failed",
            error_type=type(exc).__name__,
        )
    final_fingerprint = str(final.get("snapshot_fingerprint") or "")
    events.append({"stage": "final_context", "context": _context_summary(final)})
    restored = bool(initial_fingerprint and final_fingerprint == initial_fingerprint)
    undo_receipt = undo_executed.get("receipt") if isinstance(undo_executed.get("receipt"), dict) else {}
    undo_action_id = _action_id(undo)
    passed = bool(
        write_verified
        and assistant_task_completed
        and replay_rejected
        and undo_executed.get("ok")
        and undo_receipt.get("verified") is True
        and undo_receipt.get("status") == "applied"
        and bool(undo_action_id)
        and str(undo_receipt.get("action_id") or "") == undo_action_id
        and restored
    )
    return {
        **base,
        "status": "passed" if passed else "failed",
        "changed": not restored,
        "write_receipt": _redact(receipt),
        "assistant_task_completed": assistant_task_completed,
        "replay_rejected": replay_rejected,
        "undo_receipt": _redact(undo_receipt),
        "final_snapshot_fingerprint": final_fingerprint,
        "restored_exactly": restored,
        "events": _redact(events),
        "limitations": [
            "This qualifies one supervised reversible assistant action on a disposable set.",
            "It does not authorize autonomous or destructive operation.",
        ],
        **({"error": "The lifecycle was restored but did not satisfy write verification, replay rejection, or assistant-task completion."} if not passed else {}),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8090")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--model", required=True)
    parser.add_argument("--planner-bakeoff", type=Path, default=DEFAULT_PLANNER_BAKEOFF)
    parser.add_argument("--transformers-transport", type=Path, default=DEFAULT_TRANSFORMERS_TRANSPORT)
    parser.add_argument("--goal", required=True)
    parser.add_argument("--command", required=True)
    parser.add_argument("--session-id", default=f"assistant-live-{int(time.time())}")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        planner_evidence_sha256 = qualified_planner_identity(args.planner_bakeoff, args.model)
        planner_provider = qualified_planner_provider(args.planner_bakeoff)
    except ValueError as exc:
        parser.error(str(exc))
    planner_transport_sha256 = ""
    if planner_provider == "transformers":
        try:
            planner_transport_sha256 = verify_transformers_transport(
                args.ollama_url, args.model, args.transformers_transport,
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            parser.error(f"qualified Transformers bridge verification failed: {exc}")
    with tempfile.TemporaryDirectory(prefix="kenn-assistant-live-") as temporary:
        coordinator = AssistantCoordinator(AssistantTaskStore(Path(temporary) / "tasks.db"))
        planner = OllamaDeliberativeGenerator(model=args.model, base_url=args.ollama_url)
        facade = KennMCPFacade(
            KennHTTPClient(args.endpoint), coordinator=coordinator, planner=planner,
            planner_provider=planner_provider, planner_id=args.model,
        )
        result = qualify(
            facade=facade, goal=args.goal, command=args.command,
            session_id=args.session_id, apply=args.apply,
            planner_evidence_sha256=planner_evidence_sha256,
            planner_transport_sha256=planner_transport_sha256,
        )
    rendered = json.dumps(result, indent=2, sort_keys=True, default=str) + "\n"
    if args.output:
        write_evidence(args.output, result)
    print(rendered, end="")
    return 0 if result.get("status") in {"passed", "proposal_ready"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
