"""Repair-note drafting and repair validation/retesting."""

from __future__ import annotations

import re

import demo_feedback

from ._shared import _source_lines, _source_texts, _topic_list


def draft_agent_item(payload: dict) -> dict:
    source = str(payload.get("source", "")).strip()
    source_id = str(payload.get("source_id", "")).strip()
    question = str(payload.get("question", "")).strip()
    topics = payload.get("topics") if isinstance(payload.get("topics"), list) else []
    if source == "gap" and source_id:
        import ableton_bridge

        return ableton_bridge.create_note_from_gap(source_id)
    if source == "feedback" and source_id:
        return create_note_from_feedback(source_id)
    if not question:
        return {"ok": False, "error": "question is required."}
    import ableton_bridge

    return ableton_bridge.create_note_from_question_api(question, topics)


def _repair_note_template(row: dict) -> str:
    from kenn.retrieval.retrieval import query_topics
    from kenn.training.research import slugify

    question = str(row.get("question", "")).strip()
    title = re.sub(r"\s+", " ", question.rstrip("?"))[:70].title() or "Feedback Repair Note"
    topics = _topic_list(row.get("topics") or [])
    topic_hits = list(dict.fromkeys([*topics, *query_topics(question)]))
    tag_parts = [topic.replace("_", " ") for topic in topic_hits[:8]]
    tag_parts.extend(word for word in re.findall(r"[a-z0-9]+", question.lower()) if len(word) > 3)
    tags = ", ".join(dict.fromkeys([*tag_parts, "ableton", "workflow", "repair"]))[:140]
    comment = str(row.get("comment", "")).strip() or "No tester comment was provided."
    answer = str(row.get("answer", "")).strip() or "No answer payload was captured."
    sources = _source_lines(row.get("sources") or [])
    note_id = slugify(title)
    return f"""# {title}

Type: Production workflow
Tags: {tags}
Status: Draft
Source title: LLM feedback repair
Source creator:
Source URL:
Source ID: {row.get("id", "")}

Short answer:
Replace this with the corrected answer to: {question}

Try this:
1. Write the most practical first action in Ableton.
2. Add device names, starting settings, or routing details that make the answer testable.
3. Add a listening check so the user knows whether the fix is working.

Why it matters:
Explain the mistake this repair prevents and why the corrected workflow is more reliable.

Repair context:
Tester comment: {comment}
Original confidence: {row.get("confidence", "")}
Original source quality: {row.get("source_quality", "")}
Channel: {row.get("channel", "")}
Repair ID: {note_id}

Failed answer:
{answer}

Captured sources:
{sources}

Personal notes:
Use the context above to write a clean approved note. Remove the failed answer section before approving if it is no longer useful.

Related questions:
- Rephrase the original question as a follow-up a client might ask.
- What should I check before applying this in a paid session?
"""


def create_note_from_feedback(feedback_id: str) -> dict:
    from kenn.training.research import NOTES_DIR, ensure_files, slugify

    row = demo_feedback.get_feedback(feedback_id)
    if not row:
        return {"ok": False, "error": "Feedback item not found."}
    if row.get("rating") != "not_useful":
        return {"ok": False, "error": "Only needs-work feedback can create a repair note."}
    if str(row.get("repair_status", "open")).lower() not in {"", "open"}:
        return {"ok": False, "error": f"Feedback is already {row.get('repair_status')}."}

    ensure_files()
    question = str(row.get("question", "")).strip()
    title = re.sub(r"\s+", " ", question.rstrip("?"))[:70].title() or "Feedback Repair Note"
    path = NOTES_DIR / f"{slugify(title)}-repair.md"
    suffix = 2
    while path.exists():
        path = NOTES_DIR / f"{slugify(title)}-repair-{suffix}.md"
        suffix += 1
    path.write_text(_repair_note_template(row), encoding="utf-8")
    demo_feedback.mark_repair_status(feedback_id, "drafted", note_file=path.name)
    return {
        "ok": True,
        "note": path.name,
        "message": f"Repair draft created: {path.name}. Edit, approve, rebuild, then run evals.",
    }


def repair_validation(row: dict, payload: dict) -> dict:
    sources = payload.get("sources") or []
    source_texts = _source_texts(sources)
    confidence = str(payload.get("confidence", "")).lower()
    source_quality = str(payload.get("source_quality", "")).lower()
    repair_note = str(row.get("repair_note", "")).lower()
    old_top = str(row.get("top_source", "")).lower()

    checks = {
        "confidence_ok": confidence in {"medium", "high"},
        "source_quality_ok": source_quality == "high",
        "note_backed": any(" note" in text or "md" in text or "note" in text for text in source_texts),
        "repair_note_used": not repair_note or any(repair_note in text for text in source_texts),
        "old_top_not_primary": True,
    }
    if old_top and sources:
        first_text = source_texts[0] if source_texts else ""
        checks["old_top_not_primary"] = old_top not in first_text or bool(repair_note and repair_note in first_text)
    resolved = all(checks.values())
    failed = [name for name, ok in checks.items() if not ok]
    return {
        "resolved": resolved,
        "checks": checks,
        "failed_checks": failed,
        "confidence": payload.get("confidence", ""),
        "source_quality": payload.get("source_quality", ""),
        "top_source": sources[0].get("label", "") if sources and isinstance(sources[0], dict) else "",
    }


def retest_feedback_repair(feedback_id: str) -> dict:
    import ableton_bridge

    row = demo_feedback.get_feedback(feedback_id)
    if not row:
        return {"ok": False, "error": "Feedback item not found."}
    if row.get("rating") != "not_useful":
        return {"ok": False, "error": "Only needs-work feedback can be retested."}
    if str(row.get("repair_status", "")).lower() not in {"drafted", "needs_review"}:
        return {"ok": False, "error": "Create a repair draft before retesting this feedback."}

    payload = ableton_bridge.ask(str(row.get("question", "")), limit=8, allow_llm=False)
    validation = repair_validation(row, payload)
    status = "resolved" if validation["resolved"] else "needs_review"
    demo_feedback.mark_repair_result(feedback_id, status, payload, note_file=str(row.get("repair_note", "")))
    return {
        "ok": True,
        "feedback_id": feedback_id,
        "status": status,
        **validation,
        "answer_preview": str(payload.get("answer", ""))[:500],
    }
