"""Evidence-first, one-hypothesis-at-a-time production diagnostic loops."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import math
import time
from typing import Any
from uuid import uuid4

from kenn.core.deliberative_plan import DeliberativePlan, DeliberativeStep
from kenn.core.diagnostic_framework import DiagnosticPlan, plan_for, rank_with_evidence
from kenn.core.evidence import EvidenceFact, EvidencePacket, current_for_diagnosis, from_ableton_session
from kenn.core.session_context import validate_session_context


LOOP_SCHEMA = "kenn.diagnostic_loop.v1"
RESULT_SCHEMA = "kenn.diagnostic_test_result.v1"
MAX_HYPOTHESES = 3
MAX_RESULTS = 3
VERDICTS = frozenset({"supports", "contradicts", "inconclusive"})
STATUSES = frozenset({"awaiting_test", "needs_clarification", "recommendation_ready", "exhausted"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def evidence_from_session_context(context: dict[str, Any]) -> list[EvidencePacket]:
    """Project sanitized context into existing causal-ranking evidence types."""
    packets: list[EvidencePacket] = []
    transport = context.get("transport") if isinstance(context.get("transport"), dict) else {}
    live = from_ableton_session({**transport, "tracks": context.get("tracks", [])})
    if live is not None:
        packets.append(live)

    age = max(0.0, time.time() - float(context.get("observed_at", time.time())))
    for measurement in context.get("measurements", []):
        if not isinstance(measurement, dict):
            continue
        metrics = measurement.get("metrics") if isinstance(measurement.get("metrics"), dict) else {}
        facts = tuple(
            EvidenceFact(str(name)[:128], float(value), "", "plugin_bus_snapshot", "measured")
            for name, value in metrics.items()
            if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))
        )
        if measurement.get("kind") == "plugin_feature_frame" and facts:
            packets.append(EvidencePacket(
                source="plugin_bus_snapshot",
                captured_at_age_seconds=age,
                facts=facts,
                limitations=(
                    "Current bus measurement cannot identify the responsible track, device, or audible cause.",
                ),
                observed_at_epoch=float(context.get("observed_at", time.time())),
            ))
        elif measurement.get("kind") == "mix_review" and facts:
            packets.append(EvidencePacket(
                source="mix_review_upload",
                captured_at_age_seconds=None,
                facts=tuple(
                    EvidenceFact(fact.name, fact.value, fact.unit, "mix_review_upload", fact.confidence)
                    for fact in facts
                ),
                limitations=(
                    "Uploaded-render measurements cannot identify a current Live track, device, or causal stage.",
                ),
            ))
    return packets


def _hypotheses(plan: DiagnosticPlan) -> list[dict[str, Any]]:
    return [
        {
            "hypothesis_id": f"hypothesis-{index}",
            "cause": _text(item.cause, 512),
            "why_plausible": _text(item.why_plausible, 1_024),
            "test": _text(item.test, 1_024),
            "if_confirmed": _text(item.if_confirmed, 1_024),
        }
        for index, item in enumerate(plan.hypotheses[:MAX_HYPOTHESES], start=1)
    ]


def validate_diagnostic_loop(loop: Any) -> dict[str, Any]:
    errors: list[str] = []
    if not isinstance(loop, dict) or loop.get("schema") != LOOP_SCHEMA:
        return {"ok": False, "errors": [f"Expected {LOOP_SCHEMA}."]}
    hypotheses = loop.get("hypotheses")
    results = loop.get("results")
    if not isinstance(hypotheses, list) or not 1 <= len(hypotheses) <= MAX_HYPOTHESES:
        errors.append("Diagnostic loop must contain one to three hypotheses.")
        hypotheses = []
    if not isinstance(results, list) or len(results) > MAX_RESULTS:
        errors.append("Diagnostic loop results must be a bounded list.")
        results = []
    ids = [item.get("hypothesis_id") for item in hypotheses if isinstance(item, dict)]
    string_ids = [item for item in ids if isinstance(item, str) and item]
    if len(ids) != len(hypotheses) or len(string_ids) != len(ids) or len(set(string_ids)) != len(string_ids):
        errors.append("Diagnostic hypothesis IDs must be non-empty and unique.")
    for position, hypothesis in enumerate(hypotheses, start=1):
        if not isinstance(hypothesis, dict):
            continue
        for field in ("cause", "why_plausible", "test", "if_confirmed"):
            if not isinstance(hypothesis.get(field), str) or not hypothesis[field].strip():
                errors.append(f"Hypothesis {position} requires non-empty {field} text.")
    raw_status = loop.get("status")
    status = raw_status if isinstance(raw_status, str) else ""
    if status not in STATUSES:
        errors.append("Diagnostic loop status is invalid.")
    active = loop.get("active_hypothesis_id")
    if status in {"awaiting_test", "needs_clarification"} and active not in ids:
        errors.append("Active diagnostic status requires a known hypothesis.")
    if status in {"recommendation_ready", "exhausted"} and active not in {None, ""}:
        errors.append("Terminal diagnostic status cannot retain an active hypothesis.")
    if loop.get("execution_authorized") is not False:
        errors.append("Diagnostic loops can never authorize execution.")
    if not _text(loop.get("snapshot_fingerprint"), 96).startswith("sha256:"):
        errors.append("Diagnostic loop requires a snapshot fingerprint.")
    return {"ok": not errors, "errors": errors, "schema": LOOP_SCHEMA}


def start_diagnostic_loop(
    *,
    goal: str,
    context: dict[str, Any],
    evidence_packets: list[EvidencePacket] | None = None,
) -> dict[str, Any]:
    checked = validate_session_context(context)
    if not checked.get("ok"):
        return {"ok": False, "errors": checked.get("errors", [])}
    diagnostic = plan_for(_text(goal, 1_024))
    if diagnostic is None:
        return {
            "ok": False,
            "errors": ["Goal does not identify a supported diagnostic symptom; clarification is required."],
        }
    packets = current_for_diagnosis(
        evidence_packets if evidence_packets is not None else evidence_from_session_context(context)
    )
    ranked, ranking = rank_with_evidence(diagnostic, packets)
    hypotheses = _hypotheses(ranked)
    created_at = _now()
    loop = {
        "schema": LOOP_SCHEMA,
        "loop_id": f"diagnostic-{uuid4().hex}",
        "goal": _text(goal, 1_024),
        "session_id": _text(context.get("session_id"), 128),
        "snapshot_fingerprint": context["snapshot_fingerprint"],
        "symptom": _text(ranked.symptom, 1_024),
        "issue_type": _text(ranked.issue_type, 1_024),
        "hypotheses": hypotheses,
        "active_hypothesis_id": hypotheses[0]["hypothesis_id"],
        "status": "awaiting_test",
        "results": [],
        "recommendation": "",
        "verification": _text(ranked.verification, 1_024),
        "question": _text(ranked.question, 1_024),
        "evidence_ranking": _text(ranking, 1_024),
        "execution_authorized": False,
        "created_at": created_at,
        "updated_at": created_at,
    }
    return {"ok": True, "loop": loop}


def _safe_result(result: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    if not isinstance(result, dict):
        return None, ["Diagnostic result must be an object."]
    errors: list[str] = []
    if result.get("schema") != RESULT_SCHEMA:
        errors.append(f"Result must use {RESULT_SCHEMA}.")
    hypothesis_id = _text(result.get("hypothesis_id"), 64)
    verdict = _text(result.get("verdict"), 32)
    source = _text(result.get("source"), 32)
    if not hypothesis_id:
        errors.append("hypothesis_id is required.")
    if verdict not in VERDICTS:
        errors.append("Result verdict must be supports, contradicts, or inconclusive.")
    if source not in {"user_observation", "measurement", "verified_receipt"}:
        errors.append("Result source is unsupported.")
    evidence = result.get("evidence") if isinstance(result.get("evidence"), dict) else {}
    identity: dict[str, Any] = {"schema": _text(evidence.get("schema"), 128)}
    if source == "user_observation":
        observation = _text(result.get("observation"), 1_000)
        source_turn_id = _text(result.get("source_turn_id"), 128)
        if not observation or not source_turn_id:
            errors.append("User observations require observation text and source_turn_id.")
        identity = {"source_turn_id": source_turn_id}
    elif source == "measurement":
        if evidence.get("schema") != "kenn.evidence.v1" or not isinstance(evidence.get("facts"), list) or not evidence["facts"]:
            errors.append("Measurement results require a typed non-empty evidence packet.")
        identity["fact_count"] = len(evidence.get("facts") or [])
        identity["source"] = _text(evidence.get("source"), 64)
    elif source == "verified_receipt":
        if (
            evidence.get("verified") is not True
            or evidence.get("status") not in {"applied", "completed", "success"}
            or not _text(evidence.get("receipt_id"), 128)
        ):
            errors.append("Receipt results require a verified applied receipt identity.")
        identity.update({
            "receipt_id": _text(evidence.get("receipt_id"), 128),
            "verified": evidence.get("verified") is True,
            "status": _text(evidence.get("status"), 64),
        })
    safe = {
        "schema": RESULT_SCHEMA,
        "result_id": f"diagnostic-result-{uuid4().hex}",
        "hypothesis_id": hypothesis_id,
        "verdict": verdict,
        "source": source,
        "observation": _text(result.get("observation"), 1_000),
        "evidence_identity": identity,
        "recorded_at": _now(),
    }
    return (None if errors else safe), errors


def record_diagnostic_result(loop: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    checked = validate_diagnostic_loop(loop)
    if not checked.get("ok"):
        return {"ok": False, "errors": checked["errors"]}
    if loop["status"] not in {"awaiting_test", "needs_clarification"}:
        return {"ok": False, "errors": ["Diagnostic loop is not awaiting a test result."]}
    if len(loop.get("results") or []) >= MAX_RESULTS:
        return {"ok": False, "errors": ["Diagnostic loop has reached its bounded result limit."]}
    safe, errors = _safe_result(result)
    if errors or safe is None:
        return {"ok": False, "errors": errors}
    if safe["hypothesis_id"] != loop["active_hypothesis_id"]:
        return {"ok": False, "errors": ["Result does not match the active hypothesis."]}

    updated = deepcopy(loop)
    updated["results"] = [*updated["results"], safe][-MAX_RESULTS:]
    active_index = next(
        index for index, item in enumerate(updated["hypotheses"])
        if item["hypothesis_id"] == updated["active_hypothesis_id"]
    )
    if safe["verdict"] == "supports":
        updated["recommendation"] = updated["hypotheses"][active_index]["if_confirmed"]
        updated["active_hypothesis_id"] = ""
        updated["status"] = "recommendation_ready"
    elif safe["verdict"] == "contradicts":
        next_index = active_index + 1
        if next_index < len(updated["hypotheses"]):
            updated["active_hypothesis_id"] = updated["hypotheses"][next_index]["hypothesis_id"]
            updated["status"] = "awaiting_test"
        else:
            updated["active_hypothesis_id"] = ""
            updated["status"] = "exhausted"
    else:
        updated["status"] = "needs_clarification"
    updated["updated_at"] = _now()
    return {"ok": True, "loop": updated}


def next_diagnostic_plan(loop: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Turn the current diagnostic state into one inert conversational step."""
    checked = validate_diagnostic_loop(loop)
    context_checked = validate_session_context(context)
    if not checked.get("ok") or not context_checked.get("ok"):
        return {"ok": False, "errors": [*checked.get("errors", []), *context_checked.get("errors", [])]}
    if loop.get("session_id") != context.get("session_id"):
        return {"ok": False, "errors": ["Diagnostic loop belongs to another session."]}
    if loop.get("snapshot_fingerprint") != context.get("snapshot_fingerprint"):
        return {"ok": False, "errors": ["Session state changed after this diagnosis began; refresh the diagnostic loop."]}

    if loop["status"] in {"awaiting_test", "needs_clarification"}:
        hypothesis = next(item for item in loop["hypotheses"] if item["hypothesis_id"] == loop["active_hypothesis_id"])
        objective = hypothesis["test"]
        rationale = hypothesis["why_plausible"]
    elif loop["status"] == "recommendation_ready":
        objective = "Ask whether the producer wants an exact bounded proposal for the confirmed next move: " + loop["recommendation"]
        rationale = "A supported hypothesis justifies a recommendation, but not an automatic Live mutation."
    else:
        objective = loop["question"] or "Ask for a more specific symptom or new observation."
        rationale = "The bounded hypothesis set was not supported; guessing another cause would overclaim."

    step = DeliberativeStep.create(
        step_id="diagnostic-followup",
        kind="clarification",
        action="ask_user",
        objective=objective,
        rationale=rationale,
        expected_evidence=["explicit producer observation or decision"],
    )
    plan = DeliberativePlan.create(
        goal=loop["goal"],
        context=context,
        status="needs_clarification",
        steps=[step],
        unknowns=[loop["question"]] if loop.get("question") else [],
        model_provider="deterministic",
        model_id="kenn-diagnostic-loop-v1",
    )
    return {"ok": True, "plan": plan.to_dict(), "execution_authorized": False}


__all__ = [
    "LOOP_SCHEMA", "RESULT_SCHEMA", "evidence_from_session_context",
    "next_diagnostic_plan", "record_diagnostic_result", "start_diagnostic_loop",
    "validate_diagnostic_loop",
]
