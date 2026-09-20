"""Training-record snapshot, review, and diagnostics."""

from __future__ import annotations

import json

from ._shared import (
    _clean_bool,
    _bump_counter,
    _display_path,
    _pkg,
    _slug,
    _top_counts,
    normalize_question,
)


def _record_id(record: dict) -> str:
    case_id = str(record.get("case_id") or "").strip()
    if case_id:
        return case_id[:160]
    question = str(record.get("question") or record.get("input") or "").strip()
    return _slug(normalize_question(question), fallback="training-record")


def _training_records_path():
    artifacts = _pkg().ARTIFACTS
    benchmark_dir = artifacts / "benchmarks"
    paths = sorted(
        benchmark_dir.glob("kenn_answer_records_*.jsonl"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if paths:
        return paths[0]
    exported = artifacts / "training" / "kenn_answer_records.jsonl"
    return exported if exported.exists() else None


def _read_jsonl(path) -> list[dict]:
    items: list[dict] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return items
    for line in lines:
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            items.append(item)
    return items


def _load_training_reviews() -> dict[str, dict]:
    review_path = _pkg().TRAINING_REVIEW_PATH
    if not review_path.exists():
        return {}
    try:
        data = json.loads(review_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    items = data.get("items", {})
    return items if isinstance(items, dict) else {}


def _write_training_reviews(items: dict[str, dict]) -> None:
    review_path = _pkg().TRAINING_REVIEW_PATH
    review_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "kenn.review_labels.v1",
        "items": items,
    }
    review_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _review_priority(record: dict, review: dict) -> dict:
    reasons: list[str] = []
    if record.get("eval_passed") is False:
        reasons.append("eval failed")
    if record.get("weak_match") is True:
        reasons.append("weak retrieval")
    if str(record.get("source_quality", "")).lower() in {"low", "weak"}:
        reasons.append("weak sources")
    for field, label in (
        ("route_correct", "route disputed"),
        ("intent_correct", "intent disputed"),
        ("top_source_correct", "top source disputed"),
    ):
        if review.get(field) is False:
            reasons.append(label)
    if review.get("answer_policy") == "should_fallback":
        reasons.append("should fallback")
    return {
        "needs_review": bool(reasons) or not review,
        "reasons": list(dict.fromkeys(reasons))[:5],
    }


def training_diagnostics(records: list[dict]) -> dict:
    routes: dict[str, int] = {}
    intents: dict[str, int] = {}
    topics: dict[str, int] = {}
    sources: dict[str, int] = {}
    issue_topics: dict[str, int] = {}
    issue_sources: dict[str, int] = {}
    issue_routes: dict[str, int] = {}
    route_confusion: dict[str, int] = {}
    issue_count = 0

    for item in records:
        review = item.get("review") or {}
        _bump_counter(routes, item.get("route", ""))
        _bump_counter(intents, item.get("intent", ""))
        for topic in item.get("topics") or item.get("expected_topics") or []:
            _bump_counter(topics, topic)
        source_label = item.get("top_source_label") or item.get("top_source") or "No source"
        _bump_counter(sources, source_label)
        has_issue = (
            item.get("eval_passed") is False
            or item.get("weak_match") is True
            or review.get("route_correct") is False
            or review.get("intent_correct") is False
            or review.get("top_source_correct") is False
            or review.get("answer_policy") == "should_fallback"
        )
        if not has_issue:
            continue
        issue_count += 1
        _bump_counter(issue_routes, item.get("route", ""))
        if review.get("route_correct") is False:
            _bump_counter(route_confusion, f"{item.get('route') or 'unknown'} -> review")
        if review.get("answer_policy") == "should_fallback" and item.get("route") != "out_of_scope":
            _bump_counter(route_confusion, f"{item.get('route') or 'unknown'} -> fallback")
        _bump_counter(issue_sources, source_label)
        for topic in item.get("topics") or item.get("expected_topics") or []:
            _bump_counter(issue_topics, topic)

    return {
        "issue_count": issue_count,
        "routes": _top_counts(routes),
        "intents": _top_counts(intents),
        "topics": _top_counts(topics),
        "sources": _top_counts(sources),
        "issue_routes": _top_counts(issue_routes),
        "route_confusion": _top_counts(route_confusion),
        "issue_topics": _top_counts(issue_topics),
        "issue_sources": _top_counts(issue_sources),
    }


def training_records_snapshot(limit: int = 100) -> dict:
    path = _training_records_path()
    reviews = _load_training_reviews()
    if path is None:
        return {
            "ok": True,
            "path": "",
            "items": [],
            "summary": {
                "total": 0,
                "shown": 0,
                "reviewed": len(reviews),
                "route_incorrect": 0,
                "intent_incorrect": 0,
                "source_incorrect": 0,
                "should_fallback": 0,
            },
            "message": "No training records yet. Run benchmark or export-training first.",
        }

    records = _read_jsonl(path)
    merged: list[dict] = []
    for record in records:
        record_id = _record_id(record)
        review = reviews.get(record_id, {})
        item = {**record, "id": record_id, "review": review}
        item["review_priority"] = _review_priority(record, review)
        merged.append(item)
    merged.sort(
        key=lambda item: (
            not item.get("review_priority", {}).get("needs_review", False),
            str(item.get("question", "")).lower(),
        )
    )
    shown = merged[: max(1, min(500, limit))]
    active_reviews = [reviews.get(_record_id(record), {}) for record in records]
    summary = {
        "total": len(records),
        "shown": len(shown),
        "reviewed": sum(1 for review in active_reviews if review),
        "route_incorrect": sum(1 for review in active_reviews if review.get("route_correct") is False),
        "intent_incorrect": sum(1 for review in active_reviews if review.get("intent_correct") is False),
        "source_incorrect": sum(1 for review in active_reviews if review.get("top_source_correct") is False),
        "should_fallback": sum(1 for review in active_reviews if review.get("answer_policy") == "should_fallback"),
    }
    pkg = _pkg()
    return {
        "ok": True,
        "path": _display_path(path),
        "review_path": _display_path(pkg.TRAINING_REVIEW_PATH),
        "reviewed_export_path": _display_path(pkg.REVIEWED_TRAINING_PATH),
        "hard_negatives_path": _display_path(pkg.HARD_NEGATIVES_PATH),
        "route_memory_path": _display_path(pkg.ROUTE_MEMORY_PATH),
        "items": shown,
        "summary": summary,
        "diagnostics": training_diagnostics(merged),
    }


def save_training_review(payload: dict) -> dict:
    record_id = str(payload.get("id") or payload.get("case_id") or "").strip()
    if not record_id:
        return {"ok": False, "error": "id is required."}
    answer_policy = str(payload.get("answer_policy") or "").strip().lower()
    if answer_policy not in {"", "should_answer", "should_fallback", "unsure"}:
        return {"ok": False, "error": "answer_policy must be should_answer, should_fallback, or unsure."}
    review = {
        "route_correct": _clean_bool(payload.get("route_correct")),
        "intent_correct": _clean_bool(payload.get("intent_correct")),
        "top_source_correct": _clean_bool(payload.get("top_source_correct")),
        "answer_policy": answer_policy,
        "notes": str(payload.get("notes") or "").strip()[:1000],
    }
    review = {key: value for key, value in review.items() if value not in (None, "")}
    reviews = _load_training_reviews()
    if review:
        reviews[record_id] = review
    else:
        reviews.pop(record_id, None)
    _write_training_reviews(reviews)
    return {
        "ok": True,
        "id": record_id,
        "review": reviews.get(record_id, {}),
        "reviewed": len(reviews),
        "path": _display_path(_pkg().TRAINING_REVIEW_PATH),
    }


def export_reviewed_training() -> dict:
    snapshot_data = training_records_snapshot(limit=500)
    records = snapshot_data.get("items", [])
    if not records:
        return {"ok": False, "error": "No training records to export."}
    reviewed_path = _pkg().REVIEWED_TRAINING_PATH
    reviewed_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, sort_keys=True) for record in records]
    reviewed_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "ok": True,
        "count": len(records),
        "path": _display_path(reviewed_path),
        "summary": snapshot_data.get("summary", {}),
    }
