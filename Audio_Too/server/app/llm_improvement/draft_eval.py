"""Draft eval-case creation from tester feedback and self-check warnings."""

from __future__ import annotations

import json
import re

import demo_feedback
import tips_queries

from ._shared import EVAL_TERM_STOPWORDS, _display_path, _pkg, _slug, _topic_list


def _load_draft_eval_suite() -> dict:
    draft_eval_path = _pkg().DRAFT_EVAL_PATH
    if draft_eval_path.exists():
        try:
            data = json.loads(draft_eval_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    else:
        data = {}
    cases = data.get("cases")
    if not isinstance(cases, list):
        cases = []
    return {
        "version": int(data.get("version", 1) or 1),
        "description": data.get(
            "description",
            "Reviewable eval cases drafted from tester feedback. Promote selected cases into questions.json.",
        ),
        "cases": cases,
    }


def _feedback_eval_terms(row: dict) -> list[str]:
    terms: list[str] = []
    for topic in _topic_list(row.get("topics") or []):
        terms.append(topic.replace("_", " "))
    text = f"{row.get('question', '')} {row.get('comment', '')}"
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        if len(word) < 4 or word in EVAL_TERM_STOPWORDS:
            continue
        terms.append(word)
    return list(dict.fromkeys(terms))[:8]


def draft_eval_from_feedback(feedback_id: str) -> dict:
    row = demo_feedback.get_feedback(feedback_id)
    if not row:
        return {"ok": False, "error": "Feedback item not found."}
    if row.get("rating") != "not_useful":
        return {"ok": False, "error": "Only needs-work feedback can draft an eval case."}

    question = str(row.get("question", "")).strip()
    if not question:
        return {"ok": False, "error": "Feedback item has no question."}

    suite = _load_draft_eval_suite()
    case_id = f"feedback-{feedback_id}-{_slug(question)}"
    case = {
        "id": case_id,
        "question": question,
        "min_confidence": "medium",
        "min_source_quality": "high",
        "source_kinds_any": ["note"],
        "topics_must_include": _topic_list(row.get("topics") or [])[:4],
        "answer_must_include": _feedback_eval_terms(row),
        "source_must_include": [],
        "feedback": {
            "id": str(feedback_id),
            "comment": str(row.get("comment", ""))[:500],
            "failed_top_source": str(row.get("top_source", ""))[:240],
            "repair_note": str(row.get("repair_note", "")),
        },
    }
    repair_note = str(row.get("repair_note", "")).strip()
    if repair_note:
        case["source_must_include"] = [repair_note]
    else:
        case.pop("source_must_include", None)

    cases = [existing for existing in suite["cases"] if existing.get("id") != case_id]
    cases.append(case)
    suite["cases"] = sorted(cases, key=lambda item: str(item.get("id", "")))
    draft_eval_path = _pkg().DRAFT_EVAL_PATH
    draft_eval_path.parent.mkdir(parents=True, exist_ok=True)
    draft_eval_path.write_text(json.dumps(suite, indent=2) + "\n", encoding="utf-8")
    display_path = _display_path(draft_eval_path)
    return {
        "ok": True,
        "case": case,
        "path": display_path,
        "message": f"Draft eval saved: {display_path}",
    }


def draft_eval_from_query(query_id: str) -> dict:
    rows = tips_queries.list_queries(limit=200)
    row = next((item for item in rows if str(item.get("id", "")) == str(query_id)), None)
    if not row:
        return {"ok": False, "error": "Query not found."}
    question = str(row.get("question", "")).strip()
    if not question:
        return {"ok": False, "error": "Query has no question."}
    suite = _load_draft_eval_suite()
    warnings = row.get("self_check_warnings") or tips_queries.self_check_warnings(row)
    terms = _feedback_eval_terms(
        {
            "question": question,
            "comment": " ".join(str(item) for item in warnings),
            "topics": row.get("topics") or [],
        }
    )
    case_id = f"self-check-{query_id}-{_slug(question)}"
    case = {
        "id": case_id,
        "question": question,
        "min_confidence": "medium",
        "min_source_quality": "high",
        "source_kinds_any": ["note"],
        "topics_must_include": _topic_list(row.get("topics") or [])[:4],
        "answer_must_include": terms,
        "feedback": {
            "id": str(query_id),
            "comment": "Auto-drafted from answer self-check warnings.",
            "failed_top_source": str(row.get("top_source", ""))[:240],
            "warnings": warnings,
        },
    }
    cases = [existing for existing in suite["cases"] if existing.get("id") != case_id]
    cases.append(case)
    suite["cases"] = sorted(cases, key=lambda item: str(item.get("id", "")))
    draft_eval_path = _pkg().DRAFT_EVAL_PATH
    draft_eval_path.parent.mkdir(parents=True, exist_ok=True)
    draft_eval_path.write_text(json.dumps(suite, indent=2) + "\n", encoding="utf-8")
    display_path = _display_path(draft_eval_path)
    return {
        "ok": True,
        "case": case,
        "path": display_path,
        "message": f"Draft eval saved: {display_path}",
    }
