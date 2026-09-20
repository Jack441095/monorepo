"""Hard-negative and route-memory training artifact exports."""

from __future__ import annotations

import json

from ._shared import _display_path, _pkg
from .training_records import training_records_snapshot


def hard_negative_record(item: dict) -> dict | None:
    review = item.get("review") or {}
    source_label = str(item.get("top_source_label") or item.get("top_source") or "").strip()
    source_id = str(item.get("top_source") or source_label).strip()
    should_negative = review.get("top_source_correct") is False or review.get("answer_policy") == "should_fallback"
    if not should_negative or not source_id:
        return None
    return {
        "schema": "kenn.hard_negative.v1",
        "case_id": str(item.get("case_id") or item.get("id") or ""),
        "question": str(item.get("question") or ""),
        "route": str(item.get("route") or ""),
        "intent": str(item.get("intent") or ""),
        "topics": list(item.get("topics") or []),
        "negative_source": source_id,
        "negative_source_label": source_label,
        "negative_source_kind": str(item.get("top_source_kind") or ""),
        "reason": "should fallback" if review.get("answer_policy") == "should_fallback" else "wrong top source",
        "review": review,
    }


def export_hard_negatives() -> dict:
    snapshot_data = training_records_snapshot(limit=500)
    negatives = [
        record
        for record in (hard_negative_record(item) for item in snapshot_data.get("items", []))
        if record is not None
    ]
    hard_negatives_path = _pkg().HARD_NEGATIVES_PATH
    hard_negatives_path.parent.mkdir(parents=True, exist_ok=True)
    hard_negatives_path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in negatives),
        encoding="utf-8",
    )
    return {
        "ok": True,
        "count": len(negatives),
        "path": _display_path(hard_negatives_path),
        "diagnostics": snapshot_data.get("diagnostics", {}),
    }


def route_memory_record(item: dict) -> dict | None:
    review = item.get("review") or {}
    route = str(item.get("route") or "")
    answer_policy = str(review.get("answer_policy") or "")
    route_incorrect = review.get("route_correct") is False
    should_fallback = answer_policy == "should_fallback"
    if not route_incorrect and not should_fallback:
        return None
    target_route = "out_of_scope" if should_fallback else str(review.get("target_route") or "unknown")
    return {
        "schema": "kenn.route_memory.v1",
        "case_id": str(item.get("case_id") or item.get("id") or ""),
        "question": str(item.get("question") or ""),
        "observed_route": route,
        "target_route": target_route,
        "answer_policy": answer_policy,
        "topics": list(item.get("topics") or []),
        "reason": "should fallback" if should_fallback else "route marked wrong",
        "review": review,
    }


def export_route_memory() -> dict:
    snapshot_data = training_records_snapshot(limit=500)
    records = [
        record
        for record in (route_memory_record(item) for item in snapshot_data.get("items", []))
        if record is not None
    ]
    route_memory_path = _pkg().ROUTE_MEMORY_PATH
    route_memory_path.parent.mkdir(parents=True, exist_ok=True)
    route_memory_path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )
    return {
        "ok": True,
        "count": len(records),
        "path": _display_path(route_memory_path),
        "diagnostics": snapshot_data.get("diagnostics", {}),
    }
