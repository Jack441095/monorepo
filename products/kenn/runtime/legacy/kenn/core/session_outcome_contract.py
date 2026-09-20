"""Privacy-safe contract for supervised KENN session outcome evidence.

The contract intentionally accepts only categories, latency totals, and
release-scoped opaque buckets. It must never become a route for prompts,
audio, paths, project names, or tester identities.
"""

from __future__ import annotations

from typing import Any


SCHEMA = "kenn.session_outcome.v1"
INTENT_CLASSES = frozenset({
    "advice", "analysis", "search", "navigation", "proposal", "apply",
    "undo", "recovery", "clarification", "unsupported",
})
EVIDENCE_CLASSES = frozenset({
    "live_snapshot", "measured_audio", "retrieval", "classifier", "user_correction",
    "official_ableton_manual", "curated_kenn_guidance", "reference_document",
    "manual_reference",
})
FRESHNESS = frozenset({"fresh", "stale_rejected", "unavailable"})
OUTCOMES = frozenset({"completed", "clarified", "abstained", "rejected", "failed", "recovered"})
VERDICTS = frozenset({"keep", "revise", "reject", "unsafe", "unreported"})
ROOT_CAUSES = frozenset({
    "session_perception", "classification", "retrieval", "musical_judgement",
    "intent_parsing", "planning_tool_selection", "target_resolution",
    "live_execution", "readback_recovery", "unsupported_capability",
    "unclear_request", "evaluation_ambiguity",
})
STAGES = ("context", "retrieval", "planning", "proposal", "apply", "readback", "undo")
FORBIDDEN_KEYS = frozenset({
    "prompt", "raw_prompt", "question", "audio", "audio_path", "project_path",
    "project_name", "tester_id", "tester_name", "user_name",
})
ALLOWED_KEYS = frozenset({
    "schema", "session_bucket", "project_bucket", "tester_bucket", "intent_class",
    "context_freshness", "evidence_classes", "lifecycle_outcome", "user_verdict",
    "reason_codes", "root_cause", "latency_ms", "contains_raw_prompt", "contains_audio",
})


def _contains_forbidden(value: Any) -> bool:
    if isinstance(value, dict):
        return any(str(key).lower() in FORBIDDEN_KEYS or _contains_forbidden(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_forbidden(item) for item in value)
    return False


def _one_of(value: Any, allowed: frozenset[str], field: str, failures: list[str]) -> None:
    if value not in allowed:
        failures.append(field)


def _bucket(value: Any, field: str, failures: list[str]) -> None:
    text = str(value or "")
    if not (text.startswith("sha256:") and len(text) == 71 and all(char in "0123456789abcdef" for char in text[7:].lower())):
        failures.append(field)


def validate(log: dict[str, Any]) -> list[str]:
    """Return stable validation failures; never coerce or retain unsafe input."""
    failures: list[str] = []
    if not isinstance(log, dict):
        return ["log"]
    if log.get("schema") != SCHEMA:
        failures.append("schema")
    if _contains_forbidden(log):
        failures.append("raw_content")
    if log.get("contains_raw_prompt") is not False or log.get("contains_audio") is not False:
        failures.append("privacy_declaration")
    _bucket(log.get("session_bucket"), "session_bucket", failures)
    _bucket(log.get("project_bucket"), "project_bucket", failures)
    _bucket(log.get("tester_bucket"), "tester_bucket", failures)
    _one_of(log.get("intent_class"), INTENT_CLASSES, "intent_class", failures)
    _one_of(log.get("context_freshness"), FRESHNESS, "context_freshness", failures)
    _one_of(log.get("lifecycle_outcome"), OUTCOMES, "lifecycle_outcome", failures)
    _one_of(log.get("user_verdict"), VERDICTS, "user_verdict", failures)
    evidence = log.get("evidence_classes")
    if not isinstance(evidence, list) or not evidence or any(item not in EVIDENCE_CLASSES for item in evidence):
        failures.append("evidence_classes")
    reason_codes = log.get("reason_codes")
    if not isinstance(reason_codes, list) or any(not isinstance(item, str) or not item.strip() or len(item) > 80 for item in reason_codes):
        failures.append("reason_codes")
    root_cause = log.get("root_cause")
    if root_cause is not None and root_cause not in ROOT_CAUSES:
        failures.append("root_cause")
    latency = log.get("latency_ms")
    if not isinstance(latency, dict) or set(latency) != set(STAGES):
        failures.append("latency_ms")
    elif any(not isinstance(latency[stage], int) or isinstance(latency[stage], bool) or latency[stage] < 0 for stage in STAGES):
        failures.append("latency_ms")
    if log.get("user_verdict") in {"revise", "reject", "unsafe"} and root_cause is None:
        failures.append("root_cause")
    return sorted(set(failures))
