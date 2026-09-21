"""KENN Reflection, Critique, and Correction Ingestion module.

Responsible for post-answer self-critique checks and processing user
corrections to build a lesson library and adapt source trust ratings.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import re
import sqlite3
import uuid
from typing import Any

from kenn.knowledge.reasoning import _get_conn, init_db, get_reasoning_trace
from kenn.knowledge.trust_scores import record_correction, get_source_trust

logger = logging.getLogger("kenn.knowledge.reflection")


def extract_measurements(text: str) -> dict[str, set[float]]:
    """Extract numerical measurements with their units (db, hz, khz, lufs, ms)."""
    measurements = {}
    matches = re.findall(r'(-?\d+(?:\.\d+)?)\s*(db|hz|khz|lufs|ms)\b', text, re.IGNORECASE)
    for val, unit in matches:
        unit = unit.lower()
        try:
            measurements.setdefault(unit, set()).add(float(val))
        except ValueError:
            pass
    return measurements


def post_answer_critique(
    query: str,
    answer: str,
    results: list[tuple[float, dict]],
    reasoning_traces: list[dict[str, Any]],
    answer_mode: str = "",
) -> dict[str, Any]:
    """Run deterministic and optional LLM critique passes on a generated answer."""
    warnings = []
    contradictions = []
    unsupported_claims = []
    passed = True

    # 1. Citations check: verify KENN only cites retrieved sources
    try:
        from kenn.core.chat_retrieval import source_label
        result_labels = {source_label(chunk) for _, chunk in (results or [])}
        result_names = {chunk.get("source", "") for _, chunk in (results or [])} | {
            chunk.get("title", "") for _, chunk in (results or [])
        }

        # Parse citations under "Sources:" block
        citations = []
        in_sources = False
        for line in answer.split("\n"):
            line_str = line.strip()
            if line_str.lower().startswith("sources:"):
                in_sources = True
                continue
            if in_sources:
                if not line_str:
                    continue
                if line_str.startswith(("-", "*", "•")):
                    cit = line_str.lstrip("-*• ").strip()
                    citations.append(cit)
                elif line_str.lower().startswith(("you could", "avoid", "why it matters", "listening check")):
                    in_sources = False

        for cit in citations:
            found = False
            for label in result_labels:
                if cit in label or label in cit:
                    found = True
                    break
            for name in result_names:
                if name and (cit in name or name in cit):
                    found = True
                    break
            if not found:
                warnings.append(f"Citation mismatch: answer cites '{cit}' which is not in retrieved results.")
                unsupported_claims.append(f"Cited source '{cit}' not supported by retrieved chunks.")
                passed = False
    except Exception as e:
        logger.warning(f"Citations critique pass failed: {e}")

    # 2. Contradiction check: check measurements against past reasoning
    try:
        new_measurements = extract_measurements(answer)
        for trace in (reasoning_traces or []):
            trace_measurements = extract_measurements(trace.get("conclusion", ""))
            for unit, values in trace_measurements.items():
                if unit in new_measurements:
                    # If they share a unit but have no values in common
                    if not (values & new_measurements[unit]):
                        msg = (
                            f"Contradiction warning: past trace ({trace['trace_id'][:8]}) "
                            f"mentions {list(values)} {unit}, but new answer states {list(new_measurements[unit])} {unit}."
                        )
                        contradictions.append(msg)
                        warnings.append(msg)
                        passed = False
    except Exception as e:
        logger.warning(f"Contradictions critique pass failed: {e}")

    # 3. LLM-assisted critique pass (env-gated)
    if os.environ.get("KENN_CRITIQUE_LLM_ENABLED") == "1":
        try:
            from kenn.llm.llm_rewrite import is_enabled as llm_enabled
            if llm_enabled():
                from kenn.llm.llm_rewrite import critique_answer
                # Format context excerpts
                from kenn.llm.llm_rewrite import build_context_block
                from kenn.core.chat_retrieval import source_label
                context_block = build_context_block(results, source_label)


                past_str = "\n".join(
                    f"Q: {t['query']} -> C: {t['conclusion']}" for t in (reasoning_traces or [])
                )
                llm_critique = critique_answer(query, answer, context_block, past_str)
                if llm_critique and not llm_critique.get("passed", True):
                    passed = False
                    for warning in llm_critique.get("warnings", []):
                        warnings.append(f"LLM Critique: {warning}")
                    for claim in llm_critique.get("unsupported_claims", []):
                        unsupported_claims.append(claim)
        except Exception as e:
            logger.warning(f"LLM-assisted critique pass failed: {e}")

    return {
        "passed": passed,
        "warnings": warnings,
        "contradictions": contradictions,
        "unsupported_claims": unsupported_claims,
    }


def ingest_correction(trace_id: str, correction_text: str, user_id: str = "default") -> dict[str, Any] | None:
    """Record a user correction, generate a lesson, and downgrade cited source trust."""
    init_db()
    trace = get_reasoning_trace(trace_id)
    if not trace:
        logger.warning(f"Cannot ingest correction: trace_id {trace_id} not found.")
        return None

    query = trace["query"]
    conclusion = trace["conclusion"]
    created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # 1. Generate lesson learned
    lesson_text = f"Query: '{query}'. User corrected conclusion '{conclusion}' with '{correction_text}'."
    try:
        from kenn.llm.llm_rewrite import is_enabled as llm_enabled
        if llm_enabled():
            from kenn.llm.llm_rewrite import generate_lesson
            smart_lesson = generate_lesson(query, conclusion, correction_text)
            if smart_lesson:
                lesson_text = smart_lesson.strip()
    except Exception as e:
        logger.warning(f"Failed to generate smart lesson: {e}")

    # 2. Update trace outcome and correction details
    try:
        with _get_conn() as conn:
            conn.execute(
                """
                UPDATE knowledge_reasoning
                SET outcome = 'user_corrected', correction = ?, lessons = ?
                WHERE trace_id = ?
                """,
                (correction_text, json.dumps([lesson_text]), trace_id)
            )
            # Sync to FTS
            try:
                conn.execute(
                    """
                    UPDATE knowledge_reasoning_fts
                    SET lessons = ?
                    WHERE trace_id = ?
                    """,
                    (json.dumps([lesson_text]), trace_id)
                )
            except sqlite3.OperationalError:
                pass

            # Save to knowledge_lessons table
            lesson_id = str(uuid.uuid4())
            topics_str = " ".join(trace.get("tags") or [])
            conn.execute(
                """
                INSERT INTO knowledge_lessons (lesson_id, created_at, topic, lesson, source_trace_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (lesson_id, created_at, topics_str, lesson_text, trace_id)
            )
    except (sqlite3.Error, OSError) as e:
        logger.warning(f"Database error writing correction/lesson: {e}")

    # 3. Penalize cited sources in source_trust
    penalized_sources = []
    try:
        # Load the raw evidence chunks from database to get their original source filenames
        evidence_ids = trace.get("evidence_ids") or []
        with _get_conn() as conn:
            # Look up chunks in active index or resolve from database
            # We will use source names directly if stored.
            # To resolve source names from chunk IDs, we can match chunk details.
            # However, since chunks are indexed files, we can also extract from trace tags or search.
            # In Phase 1, we computed evidence_ids by hashing source+page+kind+text.
            # Let's search active chunks JSON to resolve chunk IDs to source filenames!
            from kenn.core.chat_retrieval import load_chunks
            chunks = load_chunks()
            from kenn.knowledge.reasoning import get_chunk_id


            chunk_map = {get_chunk_id(c): c for c in chunks}
            for chunk_id in evidence_ids:
                chunk = chunk_map.get(chunk_id)
                if chunk and chunk.get("source"):
                    source_name = chunk["source"]
                    record_correction(source_name)
                    penalized_sources.append({
                        "source": source_name,
                        "new_trust": get_source_trust(source_name),
                    })
    except Exception as e:
        logger.warning(f"Failed to record source trust corrections: {e}")

    return {
        "lesson": lesson_text,
        "penalized_sources": penalized_sources,
    }


def list_lessons() -> list[dict[str, Any]]:
    """List all registered lessons learned."""
    try:
        init_db()
        with _get_conn() as conn:
            rows = conn.execute("SELECT * FROM knowledge_lessons ORDER BY created_at DESC").fetchall()
            return [dict(row) for row in rows]
    except (sqlite3.Error, OSError) as e:
        logger.warning(f"Failed to list lessons: {e}")
        return []


def list_corrections() -> list[dict[str, Any]]:
    """List all traces containing user corrections."""
    try:
        init_db()
        with _get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM knowledge_reasoning WHERE outcome = 'user_corrected' ORDER BY created_at DESC"
            ).fetchall()
            results = []
            for row in rows:
                res = dict(row)
                try:
                    res["evidence_ids"] = json.loads(res["evidence_ids"])
                except Exception:
                    res["evidence_ids"] = []
                try:
                    res["lessons"] = json.loads(res["lessons"])
                except Exception:
                    res["lessons"] = []
                res["tags"] = res["tags"].split()
                results.append(res)
            return results
    except (sqlite3.Error, OSError) as e:
        logger.warning(f"Failed to list corrections: {e}")
        return []


def propose_maintenance() -> list[dict[str, Any]]:
    """Scan for stale notes, open contradictions, and coverage gaps."""
    init_db()
    proposals = []

    # 1. Contradictions
    try:
        from kenn.knowledge import list_contradictions
        for c in list_contradictions():
            proposals.append({
                "type": "contradiction",
                "source": c["contradiction_id"],
                "description": c["description"],
                "suggested_action": f"Resolve contradiction using strategy 'primary_a' ({c['source_a']}) or 'primary_b' ({c['source_b']}).",
            })
    except Exception as e:
        logger.warning(f"Failed to fetch contradictions for maintenance proposals: {e}")

    # 2. Low Trust Notes
    try:
        from kenn.knowledge import list_source_trust
        for t in list_source_trust():
            if t["trust_score"] < 0.7:
                proposals.append({
                    "type": "low_trust",
                    "source": t["source_name"],
                    "description": f"Note '{t['source_name']}' has low trust score of {t['trust_score']:.3f} due to {t['corrections_count']} corrections.",
                    "suggested_action": "Review note details, update measurements, or retrain the source to verify authenticity.",
                })
    except Exception as e:
        logger.warning(f"Failed to fetch trust scores for maintenance proposals: {e}")

    # 3. Coverage Gaps
    try:
        from collections import Counter
        lessons = list_lessons()
        topics = []
        for lesson in lessons:
            # Topic contains space-separated tags
            topics.extend(lesson["topic"].split())


        counter = Counter(topics)
        for topic, count in counter.items():
            if count >= 2:
                proposals.append({
                    "type": "coverage_gap",
                    "source": topic,
                    "description": f"Topic/tag '{topic}' has {count} user corrections, indicating consistent answering difficulty.",
                    "suggested_action": f"Create or update a manual/approved note specifically covering '{topic}' to reinforce correct advice.",
                })
    except Exception as e:
        logger.warning(f"Failed to detect coverage gaps: {e}")

    return proposals
