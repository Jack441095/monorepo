"""Producer preferences and privacy-safe supervised session outcomes.

Every handler here was lifted verbatim out of ``KennMCPFacade._dispatch``.
``facade`` is the facade that called it, so the injected client, coordinator,
and stores stay the single owner of Live and of the task ledger.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from kenn.core.session_outcome_contract import SCHEMA as SESSION_OUTCOME_SCHEMA

if TYPE_CHECKING:  # pragma: no cover - import cycle broken for type checking only
    from kenn.core.mcp_facade import KennMCPFacade


def producer_profile(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    session_id = str(args.get("session_id", "")).strip()[:128]
    return {
        "ok": True,
        "schema": "kenn.producer_profile.v1",
        "session_id": session_id,
        "scope": "session_scoped",
        "memory": facade.profile_store.context_memory(session_id),
        "advisory_only": True,
        "live_mutation_authorized": False,
    }


def record_producer_preference(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    return facade.profile_store.record_preference(
        session_id=str(args.get("session_id", "")),
        key=str(args.get("key", "")),
        value=str(args.get("value", "")),
        source_turn_id=str(args.get("source_turn_id", "")),
        user_statement=str(args.get("user_statement", "")),
    )


def forget_producer_preference(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": facade.profile_store.forget_preference(
            session_id=str(args.get("session_id", "")), key=str(args.get("key", "")),
        ),
        "schema": "kenn.producer_profile.v1",
        "advisory_only": True,
        "live_mutation_authorized": False,
    }


def clear_producer_profile(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "schema": "kenn.producer_profile.v1",
        "cleared": facade.profile_store.clear_profile(str(args.get("session_id", ""))),
        "advisory_only": True,
        "live_mutation_authorized": False,
    }


def record_supervised_session_outcome(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    outcome = args.get("outcome")
    if not isinstance(outcome, dict):
        raise ValueError("outcome must be a privacy-safe session outcome object")
    result = facade.session_outcome_store.record(outcome)
    result.setdefault("schema", SESSION_OUTCOME_SCHEMA)
    result["advisory_only"] = True
    result["live_mutation_authorized"] = False
    return result


def supervised_session_outcome_summary(facade: KennMCPFacade, args: dict[str, Any]) -> dict[str, Any]:
    try:
        limit = int(args.get("limit", 100))
    except (TypeError, ValueError):
        raise ValueError("limit must be an integer")
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    return facade.session_outcome_store.summary(limit)
