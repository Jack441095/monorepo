"""Deterministic improvement-agent queue, answer-quality queue, and repair plan."""

from __future__ import annotations

import demo_feedback
import lm_gaps
import tips_queries

from ._shared import _pkg, is_fixture_repair_signal, normalize_question, _topic_list


def demo_feedback_summary(limit: int = 25) -> dict:
    items = demo_feedback.list_feedback(limit=limit)
    analytics = demo_feedback.analytics(limit=limit)
    useful = sum(1 for item in items if item.get("rating") == "useful")
    needs_work = sum(1 for item in items if item.get("rating") == "not_useful")
    return {
        "total_recent": len(items),
        "useful": useful,
        "needs_work": needs_work,
        "analytics": analytics,
        "items": items,
    }


def _priority(reason: str, confidence: str = "", source_quality: str = "") -> int:
    score = 40
    if "tester marked" in reason:
        score += 35
    if "open gap" in reason:
        score += 30
    if str(confidence).lower() == "low":
        score += 20
    if str(source_quality).lower() in {"low", "weak"}:
        score += 15
    return score


def improvement_queue(limit: int = 12) -> dict:
    """Deterministic improvement-agent queue from gaps, tester feedback, and weak demo asks."""
    items: dict[str, dict] = {}
    covered_questions = _pkg().covered_eval_questions()
    covered_skipped = 0
    fixture_skipped = 0

    def add_item(
        *,
        source: str,
        source_id: str,
        question: str,
        reason: str,
        confidence: str = "",
        source_quality: str = "",
        topics=None,
        comment: str = "",
        top_source: str = "",
        answer: str = "",
        sources=None,
        repair_status: str = "",
    ) -> None:
        q = str(question or "").strip()
        key = normalize_question(q)
        if len(key) < 3:
            return
        nonlocal covered_skipped, fixture_skipped
        if is_fixture_repair_signal(question=q, top_source=str(top_source or "")):
            fixture_skipped += 1
            return
        if key in covered_questions:
            covered_skipped += 1
            return
        priority = _priority(reason, confidence, source_quality)
        existing = items.get(key)
        evidence = {
            "source": source,
            "id": str(source_id or ""),
            "reason": reason,
            "comment": str(comment or "")[:500],
            "top_source": str(top_source or "")[:240],
            "answer_preview": str(answer or "")[:700],
            "sources": sources if isinstance(sources, list) else [],
            "repair_status": str(repair_status or "open")[:40],
        }
        if existing:
            existing["priority"] = max(existing["priority"], priority)
            existing["evidence"].append(evidence)
            if not existing.get("confidence") and confidence:
                existing["confidence"] = confidence
            if not existing.get("source_quality") and source_quality:
                existing["source_quality"] = source_quality
            existing["topics"] = sorted({*existing.get("topics", []), *_topic_list(topics)})
            if answer and not existing.get("answer_preview"):
                existing["answer_preview"] = str(answer)[:700]
            if top_source and not existing.get("top_source"):
                existing["top_source"] = str(top_source)[:240]
            return
        items[key] = {
            "id": f"improve-{len(items) + 1}",
            "source": source,
            "source_id": str(source_id or ""),
            "question": q,
            "priority": priority,
            "confidence": str(confidence or ""),
            "source_quality": str(source_quality or ""),
            "topics": _topic_list(topics),
            "answer_preview": str(answer or "")[:700],
            "top_source": str(top_source or "")[:240],
            "evidence": [evidence],
            "recommendation": "Draft or expand an approved note, rebuild the index, then run evals.",
        }

    for gap in lm_gaps.list_gaps_filtered(status="open", limit=50):
        add_item(
            source="gap",
            source_id=str(gap.get("id", "")),
            question=str(gap.get("question", "")),
            reason="open gap from weak retrieval",
            confidence=str(gap.get("confidence", "")),
            topics=gap.get("topics") or [],
            top_source=str(gap.get("top_source", "")),
        )

    feedback = demo_feedback.list_feedback(limit=100)
    for row in feedback:
        if row.get("rating") != "not_useful":
            continue
        repair_status = str(row.get("repair_status", "open")).lower()
        if repair_status not in {"", "open", "needs_review"}:
            continue
        reason = (
            "repair retest still needs work"
            if repair_status == "needs_review"
            else "tester marked answer as needs work"
        )
        add_item(
            source="feedback",
            source_id=str(row.get("id", "")),
            question=str(row.get("question", "")),
            reason=reason,
            confidence=str(row.get("confidence", "")),
            source_quality=str(row.get("source_quality", "")),
            comment=str(row.get("comment", "")),
            topics=row.get("topics") or [],
            top_source=str(row.get("top_source", "")),
            answer=str(row.get("answer", "")),
            sources=row.get("sources") or [],
            repair_status=str(row.get("repair_status", "")),
        )

    analytics = demo_feedback.analytics(limit=150)
    for row in analytics.get("questions", []):
        weak = str(row.get("confidence", "")).lower() == "low" or str(row.get("source_quality", "")).lower() == "low"
        if not weak:
            continue
        add_item(
            source="demo_question",
            source_id=str(row.get("id", "")),
            question=str(row.get("question", "")),
            reason="weak demo answer detected",
            confidence=str(row.get("confidence", "")),
            source_quality=str(row.get("source_quality", "")),
            top_source=str(row.get("top_source", "")),
        )

    for row in tips_queries.list_quality_issues(limit=50):
        warnings = row.get("self_check_warnings") or []
        reason = "answer self-check warning"
        if warnings:
            reason = f"answer self-check: {', '.join(str(item) for item in warnings[:2])}"
        add_item(
            source="self_check",
            source_id=str(row.get("id", "")),
            question=str(row.get("question", "")),
            reason=reason,
            confidence=str(row.get("confidence", "")),
            source_quality=str(row.get("source_quality", "")),
            topics=row.get("topics") or [],
            top_source=str(row.get("top_source", "")),
            comment=", ".join(str(item) for item in warnings),
            repair_status="open",
        )

    ranked = sorted(items.values(), key=lambda item: (-int(item["priority"]), item["question"].lower()))
    for item in ranked:
        item["evidence_count"] = len(item.get("evidence", []))
    return {
        "total": len(ranked),
        "items": ranked[: max(1, min(50, limit))],
        "covered_skipped": covered_skipped,
        "fixture_skipped": fixture_skipped,
    }


def answer_quality_queue(limit: int = 20) -> dict:
    items = tips_queries.list_quality_issues(limit=limit)
    return {
        "total": len(items),
        "items": items,
    }


def repair_plan(
    *,
    gaps: dict | None = None,
    feedback: dict | None = None,
    agent_queue: dict | None = None,
    quality_queue: dict | None = None,
    training: dict | None = None,
    limit: int = 8,
) -> dict:
    """Prioritized operator plan for turning weak answers into better knowledge."""
    gaps = gaps or {}
    feedback = feedback or {}
    agent_queue = agent_queue or {}
    quality_queue = quality_queue or {}
    training = training or {}
    training_summary = training.get("summary") or {}
    diagnostics = training.get("diagnostics") or {}
    actions: list[dict] = []

    def add(priority: int, title: str, action: str, evidence: str, workflow: str, command: str = "") -> None:
        actions.append(
            {
                "priority": priority,
                "title": title,
                "action": action,
                "evidence": evidence,
                "workflow": workflow,
                "command": command,
            }
        )

    source_issues = int(training_summary.get("source_incorrect") or 0)
    fallback_issues = int(training_summary.get("should_fallback") or 0)
    route_issues = int(training_summary.get("route_incorrect") or 0)
    intent_issues = int(training_summary.get("intent_incorrect") or 0)
    if source_issues or fallback_issues:
        add(
            95,
            "Train retrieval away from bad matches",
            "Export hard negatives, then rebuild and rerun evals so KENN stops selecting confidently wrong sources.",
            f"{source_issues} wrong source label(s), {fallback_issues} should-fallback label(s).",
            "Review training rows → Export hard negatives → rebuild index → run evals.",
            "./audio-too eval",
        )
    if route_issues or fallback_issues:
        add(
            90,
            "Tighten routing and fallback behaviour",
            "Export route memory from reviewed records so small talk, wrong-system comments, and off-topic asks do not trigger random audio answers.",
            f"{route_issues} wrong route label(s), {fallback_issues} fallback label(s).",
            "Review route labels → Export route memory → retest awkward/non-audio prompts.",
            "./audio-too bench",
        )
    queue_items = agent_queue.get("items") or []
    if queue_items:
        top = queue_items[0]
        add(
            85,
            "Repair the top live weak answer",
            "Draft a focused approved note for the highest-priority queue item, approve it, rebuild, and retest the exact question.",
            f"{agent_queue.get('total', len(queue_items))} queued repair candidate(s). Top: {top.get('question', '')}",
            "Improvement agent queue → Draft note → Transcript Review → Approve → rebuild.",
            "./audio-too build",
        )
    quality_items = quality_queue.get("items") or []
    if quality_items:
        add(
            78,
            "Convert self-check failures into evals",
            "Draft eval cases from logged answer-quality warnings so regressions become visible in future runs.",
            f"{quality_queue.get('total', len(quality_items))} answer-quality warning(s).",
            "Answer quality queue → Draft eval → promote useful cases into questions.json.",
            "./audio-too eval",
        )
    open_gaps = int(gaps.get("open") or 0)
    if open_gaps:
        add(
            72,
            "Close open knowledge gaps",
            "Turn weak open gaps into short approved notes before adding broader documents.",
            f"{open_gaps} open gap(s), {gaps.get('drafted', 0)} drafted.",
            "Knowledge gaps → Create draft note → approve → rebuild.",
            "./audio-too build",
        )
    needs_work = int(feedback.get("needs_work") or 0)
    if needs_work:
        add(
            68,
            "Retest tester feedback repairs",
            "Use feedback rows to create repair notes and only mark them resolved when the repaired answer uses the new note.",
            f"{needs_work} recent tester answer(s) marked needs work.",
            "Tester feedback → Repair draft → Recheck repair.",
            "./audio-too bench",
        )
    issue_topics = diagnostics.get("issue_topics") or []
    if issue_topics:
        labels = ", ".join(f"{item.get('label')} ({item.get('count')})" for item in issue_topics[:3])
        add(
            60,
            "Add targeted data where failures cluster",
            "Prioritize small topic-specific notes over dumping in PDFs, then benchmark those topics.",
            f"Training issues cluster around: {labels}.",
            "Write focused notes → approve → eval by topic.",
            "./audio-too audit",
        )
    if intent_issues and not route_issues:
        add(
            55,
            "Improve intent labels",
            "Review intent mistakes so KENN can choose whether to troubleshoot, explain, compare, or ask a follow-up.",
            f"{intent_issues} wrong intent label(s).",
            "Training records → mark intent → export reviewed JSONL.",
            "./audio-too export-training",
        )
    if not actions:
        add(
            40,
            "Collect the next quality signal",
            "Run an audit or benchmark, then review any weak rows before adding new model complexity.",
            "No current repair blockers were found.",
            "Run audit → review failures → create focused notes.",
            "./audio-too audit",
        )

    ranked = sorted(actions, key=lambda item: (-item["priority"], item["title"]))
    return {
        "total": len(ranked),
        "items": ranked[: max(1, min(20, limit))],
    }
