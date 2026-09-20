"""Creative Lab: metrics functions.

Split out of creative_lab.py (was 1,261 lines) — see docs/BACKLOG.md.
"""

from __future__ import annotations

import re
from uuid import uuid4

import demo_feedback

from .constants import (
    MAX_EVENTS,
    MAX_FEEDBACK,
    MAX_SESSIONS,
    REPAIR_STOPWORDS,
)

from .storage import (
    _load,
    _safe_int,
    _save,
    now,
)


def quality_metrics(data: dict | None = None) -> dict:
    data = data or _load()
    sessions = data.get("sessions", [])
    feedback = data.get("feedback", [])
    event_counts: dict[str, int] = {}
    scores: list[int] = []
    generated_audio = 0
    mix_reviews = 0
    for session in sessions:
        for event in session.get("events", []) if isinstance(session.get("events"), list) else []:
            event_type = str(event.get("type") or "note")
            event_counts[event_type] = event_counts.get(event_type, 0) + 1
            if event_type in {"audiogen_loop", "audiogen_full_song"}:
                generated_audio += 1
            if event_type == "mix_review":
                mix_reviews += 1
                score = event.get("technical_score")
                if score not in ("", None):
                    scores.append(_safe_int(score))
    ratings: dict[str, int] = {}
    for item in feedback:
        rating = str(item.get("rating") or "unknown")
        ratings[rating] = ratings.get(rating, 0) + 1
    negative = ratings.get("wrong_direction", 0) + ratings.get("bad_source", 0)
    positive = ratings.get("good_idea", 0) + ratings.get("useful_generation_prompt", 0)
    total_rated = positive + negative
    repair_items = [item for item in feedback if item.get("rating") in {"wrong_direction", "bad_source"}]
    repair_attempts = 0
    passed_attempts = 0
    top_three_attempts = 0
    regressions_added = 0
    open_repairs = 0
    for item in repair_items:
        history = item.get("repair_history") if isinstance(item.get("repair_history"), list) else []
        repair_attempts += len(history)
        passed_attempts += sum(1 for run in history if run.get("eval_passed") is True)
        top_three_attempts += sum(
            1
            for run in history
            if (run.get("source_ranking") or {}).get("repair_note_in_top_three") is True
        )
        if item.get("main_eval_promoted_at"):
            regressions_added += 1
        if item.get("repair_status") not in {"regression_added", "promoted_passed"}:
            open_repairs += 1
    return {
        "sessions": len(sessions),
        "events": sum(event_counts.values()),
        "feedback": len(feedback),
        "generated_audio": generated_audio,
        "mix_reviews": mix_reviews,
        "positive_feedback": positive,
        "negative_feedback": negative,
        "approval_rate": round((positive / total_rated) * 100) if total_rated else None,
        "average_mix_score": round(sum(scores) / len(scores)) if scores else None,
        "repair_attempts": repair_attempts,
        "repair_pass_rate": round((passed_attempts / repair_attempts) * 100) if repair_attempts else None,
        "repair_top_three_rate": round((top_three_attempts / repair_attempts) * 100) if repair_attempts else None,
        "repair_regressions_added": regressions_added,
        "repair_open": open_repairs,
        "event_counts": event_counts,
        "ratings": ratings,
    }


def prompt_leaderboard(data: dict | None = None, limit: int = 10) -> list[dict]:
    data = data or _load()
    rows: dict[tuple[str, str], dict] = {}
    for session in data.get("sessions", []):
        for event in session.get("events", []) if isinstance(session.get("events"), list) else []:
            prompt = str(event.get("prompt") or "").strip()
            if not prompt:
                continue
            emotion = str(event.get("emotion") or "").strip() or "unknown"
            key = (prompt.lower(), emotion.lower())
            row = rows.setdefault(
                key,
                {
                    "prompt": prompt,
                    "emotion": emotion,
                    "uses": 0,
                    "useful_votes": 0,
                    "latest_src": "",
                    "latest_at": "",
                },
            )
            row["uses"] += 1
            if event.get("src"):
                row["latest_src"] = event.get("src")
            row["latest_at"] = event.get("created_at") or row["latest_at"]
    for item in data.get("feedback", []):
        if item.get("rating") != "useful_generation_prompt":
            continue
        prompt = str(item.get("prompt") or "").strip()
        if not prompt:
            continue
        emotion = str(item.get("emotion") or "").strip() or "unknown"
        key = (prompt.lower(), emotion.lower())
        row = rows.setdefault(
            key,
            {
                "prompt": prompt,
                "emotion": emotion,
                "uses": 0,
                "useful_votes": 0,
                "latest_src": "",
                "latest_at": "",
            },
        )
        row["useful_votes"] += 1
        if item.get("src"):
            row["latest_src"] = item.get("src")
        row["latest_at"] = item.get("created_at") or row["latest_at"]
    ranked = sorted(rows.values(), key=lambda row: (row["useful_votes"], row["uses"], row["latest_at"]), reverse=True)
    return ranked[: max(1, min(50, int(limit or 10)))]


def repair_recommendations(data: dict | None = None, limit: int = 8) -> list[dict]:
    data = data or _load()
    recommendations = []
    for item in reversed(data.get("feedback", [])):
        if item.get("rating") not in {"wrong_direction", "bad_source"}:
            continue
        history = item.get("repair_history") if isinstance(item.get("repair_history"), list) else []
        latest = history[-1] if history else {}
        ranking = latest.get("source_ranking") or {}
        question = item.get("question", "Creative Lab repair")
        if not item.get("repair_note"):
            recommendations.append(
                {
                    "feedback_id": item.get("id", ""),
                    "kind": "create_draft",
                    "priority": "high",
                    "title": "Create a repair draft",
                    "reason": "This negative KENN feedback has no draft repair note yet.",
                    "action": "Create repair draft from the queue.",
                    "question": question,
                }
            )
            continue
        if not history:
            recommendations.append(
                {
                    "feedback_id": item.get("id", ""),
                    "kind": "promote_repair",
                    "priority": "high",
                    "title": "Promote and test the repair",
                    "reason": "A draft exists but has not been rebuilt and evaluated.",
                    "action": "Promote repair to approve the note, rebuild KENN, and run the draft eval.",
                    "question": question,
                }
            )
            continue
        if latest.get("eval_passed") is not True:
            recommendations.append(
                {
                    "feedback_id": item.get("id", ""),
                    "kind": "manual_fix",
                    "priority": "high",
                    "title": "Fix the repair note",
                    "reason": "; ".join(str(x) for x in latest.get("failures", [])[:3]) or "The latest repair eval failed.",
                    "action": "Edit the repair note, then rerun the repair eval.",
                    "question": question,
                }
            )
            continue
        if not ranking.get("repair_note_in_top_three"):
            recommendations.append(
                {
                    "feedback_id": item.get("id", ""),
                    "kind": "improve_source_rank",
                    "priority": "medium",
                    "title": "Improve repair-note ranking",
                    "reason": "The eval passes, but the repair note is not ranking in the top 3 sources.",
                    "action": "Improve title/tags/source wording, rebuild, and rerun the repair eval.",
                    "question": question,
                }
            )
            continue
        if not item.get("main_eval_promoted_at"):
            recommendations.append(
                {
                    "feedback_id": item.get("id", ""),
                    "kind": "promote_eval",
                    "priority": "medium",
                    "title": "Add passing case to regression suite",
                    "reason": "The repair passes and ranks well, but is not permanent test coverage yet.",
                    "action": "Add the passing case to KENN/evals/questions.json.",
                    "question": question,
                }
            )
    return recommendations[: max(1, min(30, int(limit or 8)))]


def repair_queue(data: dict | None = None, limit: int = 20) -> list[dict]:
    data = data or _load()
    items = []
    for item in reversed(data.get("feedback", [])):
        rating = item.get("rating")
        if rating not in {"wrong_direction", "bad_source"}:
            continue
        action = "Check source ranking and add/rewrite notes." if rating == "bad_source" else "Add a clearer target note or evaluation case."
        items.append(
            {
                "id": item.get("id", ""),
                "session_id": item.get("session_id", ""),
                "rating": rating,
                "target": item.get("target", ""),
                "question": item.get("question", ""),
                "answer": item.get("answer", "")[:600],
                "prompt": item.get("prompt", ""),
                "emotion": item.get("emotion", ""),
                "src": item.get("src", ""),
                "created_at": item.get("created_at", ""),
                "repair_status": item.get("repair_status", "open"),
                "repair_note": item.get("repair_note", ""),
                "eval_case_id": item.get("eval_case_id", ""),
                "main_eval_case_id": item.get("main_eval_case_id", ""),
                "main_eval_promoted_at": item.get("main_eval_promoted_at", ""),
                "last_eval_passed": item.get("last_eval_passed"),
                "last_eval_at": item.get("last_eval_at", ""),
                "repair_attempts": len(item.get("repair_history", [])) if isinstance(item.get("repair_history"), list) else 0,
                "priority": "source repair" if rating == "bad_source" else "answer repair",
                "action": action,
            }
        )
    return items[: max(1, min(50, int(limit or 20)))]


def snapshot(limit: int = 20) -> dict:
    data = _load()
    sessions = list(reversed(data["sessions"][-max(1, min(MAX_SESSIONS, int(limit or 20))) :]))
    feedback = list(reversed(data["feedback"][-max(1, min(MAX_FEEDBACK, int(limit or 20))) :]))
    return {
        "ok": True,
        "sessions": sessions,
        "feedback": feedback,
        "metrics": quality_metrics(data),
        "repair_queue": repair_queue(data, limit=10),
        "repair_recommendations": repair_recommendations(data, limit=8),
        "prompt_leaderboard": prompt_leaderboard(data, limit=10),
        "counts": {
            "sessions": len(data["sessions"]),
            "feedback": len(data["feedback"]),
        },
    }


def session_replay(session_id: str) -> dict:
    clean_id = str(session_id or "").strip()
    if not clean_id:
        return {"ok": False, "error": "Missing session id."}
    data = _load()
    session = next((item for item in data["sessions"] if item.get("id") == clean_id), None)
    if not session:
        return {"ok": False, "error": "Creative Lab session was not found."}
    feedback = [item for item in data["feedback"] if item.get("session_id") == clean_id]
    return {"ok": True, "session": session, "feedback": feedback}


def repair_comparison(feedback_id: str) -> dict:
    clean_id = str(feedback_id or "").strip()
    if not clean_id:
        return {"ok": False, "error": "Missing feedback id."}
    data = _load()
    item = next((row for row in data["feedback"] if row.get("id") == clean_id), None)
    if not item:
        return {"ok": False, "error": "Creative Lab feedback item was not found."}
    history = item.get("repair_history") if isinstance(item.get("repair_history"), list) else []
    latest = history[-1] if history else {}
    return {
        "ok": True,
        "feedback_id": clean_id,
        "question": item.get("question", ""),
        "rating": item.get("rating", ""),
        "target": item.get("target", ""),
        "repair_status": item.get("repair_status", "open"),
        "repair_note": item.get("repair_note", ""),
        "eval_case_id": item.get("eval_case_id", ""),
        "main_eval_case_id": item.get("main_eval_case_id", ""),
        "main_eval_promoted_at": item.get("main_eval_promoted_at", ""),
        "original": {
            "answer": item.get("answer", ""),
            "created_at": item.get("created_at", ""),
            "comment": item.get("comment", ""),
        },
        "latest": {
            "answer": latest.get("answer") or item.get("last_eval_answer", ""),
            "created_at": latest.get("created_at") or item.get("last_eval_at", ""),
            "passed": latest.get("eval_passed", item.get("last_eval_passed")),
            "failures": latest.get("failures") or item.get("last_eval_failures", []),
            "confidence": latest.get("confidence", ""),
            "source_quality": latest.get("source_quality", ""),
            "sources": latest.get("sources", []),
        },
        "history": history,
    }


def record_session_event(payload: dict) -> dict:
    data = _load()
    session_id = str(payload.get("session_id") or "").strip() or uuid4().hex[:12]
    event_type = str(payload.get("type") or "note").strip()[:60]
    event = {
        "id": uuid4().hex[:12],
        "type": event_type,
        "question": str(payload.get("question") or "").strip()[:1000],
        "answer": str(payload.get("answer") or "").strip()[:5000],
        "prompt": str(payload.get("prompt") or "").strip()[:1000],
        "emotion": str(payload.get("emotion") or "").strip()[:60],
        "src": str(payload.get("src") or "").strip()[:500],
        "review_id": str(payload.get("review_id") or "").strip()[:80],
        "technical_score": payload.get("technical_score"),
        "summary": str(payload.get("summary") or "").strip()[:1000],
        "created_at": now(),
    }
    event = {key: value for key, value in event.items() if value not in ("", None)}
    sessions = data["sessions"]
    session = next((item for item in sessions if item.get("id") == session_id), None)
    if not session:
        session = {
            "id": session_id,
            "title": str(payload.get("title") or "Creative Lab session").strip()[:140],
            "created_at": now(),
            "updated_at": now(),
            "events": [],
        }
        sessions.append(session)
    session["updated_at"] = now()
    if payload.get("title"):
        session["title"] = str(payload.get("title")).strip()[:140]
    events = session.get("events")
    if not isinstance(events, list):
        events = []
    events.append(event)
    session["events"] = events[-MAX_EVENTS:]
    _save(data)
    return {"ok": True, "session": session, "event": event}


def record_feedback(payload: dict) -> dict:
    data = _load()
    rating = str(payload.get("rating") or "").strip().lower()
    if rating not in {"good_idea", "wrong_direction", "bad_source", "useful_generation_prompt"}:
        return {"ok": False, "error": "Unknown feedback rating."}
    item = {
        "id": uuid4().hex[:12],
        "session_id": str(payload.get("session_id") or "").strip(),
        "rating": rating,
        "target": str(payload.get("target") or "").strip()[:80],
        "question": str(payload.get("question") or "").strip()[:1000],
        "answer": str(payload.get("answer") or "").strip()[:5000],
        "prompt": str(payload.get("prompt") or "").strip()[:1000],
        "emotion": str(payload.get("emotion") or "").strip()[:60],
        "src": str(payload.get("src") or "").strip()[:500],
        "comment": str(payload.get("comment") or "").strip()[:1000],
        "created_at": now(),
    }
    data["feedback"].append(item)
    _save(data)

    linked_feedback = None
    if rating in {"wrong_direction", "bad_source"} and item["question"]:
        linked_feedback = demo_feedback.record_feedback(
            {
                "question": item["question"],
                "answer": item["answer"],
                "rating": "not_useful",
                "comment": item["comment"] or rating.replace("_", " "),
                "channel": "creative_lab",
                "confidence": "",
                "source_quality": "low" if rating == "bad_source" else "",
            }
        )
    return {"ok": True, "feedback": item, "linked_feedback": linked_feedback}


def _repair_terms(item: dict) -> list[str]:
    terms = []
    text = f"{item.get('question', '')} {item.get('comment', '')}"
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        if len(word) < 4 or word in REPAIR_STOPWORDS:
            continue
        terms.append(word)
    target = str(item.get("target") or "").strip()
    if target:
        terms.append(target)
    return list(dict.fromkeys(terms))[:8]
