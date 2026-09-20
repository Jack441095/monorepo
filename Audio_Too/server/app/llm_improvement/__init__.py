"""Dashboard helpers for Audio Tips LLM improvement workflow.

Split 2026-07-13 from a single 1,184-line flat module
(docs/codebase_scan_12_07.md §2.2, "large un-decomposed files") into this
package, layered by dependency (_shared -> training_records ->
exports/draft_eval/queue -> repair -> this file's snapshot()/run_command(),
the top of the call graph). Every name the flat module exposed is
re-exported here unchanged, so `import llm_improvement` +
`llm_improvement.whatever(...)` call sites (the only import style used
anywhere in this codebase) keep working with zero changes.
"""

from __future__ import annotations

import subprocess

import demo_feedback
import lm_gaps
import tips_queries

from ._shared import (
    ABLETON_ROOT,
    ARTIFACTS,
    DRAFT_EVAL_PATH,
    EVAL_TERM_STOPWORDS,
    FIXTURE_QUESTIONS,
    HARD_NEGATIVES_PATH,
    MAIN_EVAL_PATH,
    PYTHON,
    REPO_ROOT,
    ROOT,
    ROUTE_MEMORY_PATH,
    TRAINING_REVIEW_PATH,
    REVIEWED_TRAINING_PATH,
    _display_path,
    _slug,
    _source_lines,
    _source_texts,
    _topic_list,
    covered_eval_questions,
    is_fixture_repair_signal,
    latest_json,
    normalize_question,
    python_cmd,
)
from .draft_eval import (
    _feedback_eval_terms,
    _load_draft_eval_suite,
    draft_eval_from_feedback,
    draft_eval_from_query,
)
from .exports import (
    export_hard_negatives,
    export_route_memory,
    hard_negative_record,
    route_memory_record,
)
from .improvement_queue import (
    _priority,
    answer_quality_queue,
    demo_feedback_summary,
    improvement_queue,
    repair_plan,
)
from .repair import (
    _repair_note_template,
    create_note_from_feedback,
    draft_agent_item,
    repair_validation,
    retest_feedback_repair,
)
from .training_records import (
    _load_training_reviews,
    _read_jsonl,
    _record_id,
    _review_priority,
    _training_records_path,
    _write_training_reviews,
    export_reviewed_training,
    save_training_review,
    training_diagnostics,
    training_records_snapshot,
)

__all__ = [
    "ABLETON_ROOT",
    "ARTIFACTS",
    "DRAFT_EVAL_PATH",
    "EVAL_TERM_STOPWORDS",
    "FIXTURE_QUESTIONS",
    "HARD_NEGATIVES_PATH",
    "MAIN_EVAL_PATH",
    "PYTHON",
    "REPO_ROOT",
    "ROOT",
    "ROUTE_MEMORY_PATH",
    "TRAINING_REVIEW_PATH",
    "REVIEWED_TRAINING_PATH",
    "answer_quality_queue",
    "covered_eval_questions",
    "create_note_from_feedback",
    "demo_feedback",
    "demo_feedback_summary",
    "draft_agent_item",
    "draft_eval_from_feedback",
    "draft_eval_from_query",
    "export_hard_negatives",
    "export_reviewed_training",
    "export_route_memory",
    "hard_negative_record",
    "improvement_queue",
    "is_fixture_repair_signal",
    "latest_json",
    "lm_gaps",
    "normalize_question",
    "python_cmd",
    "repair_plan",
    "repair_validation",
    "retest_feedback_repair",
    "route_memory_record",
    "run_command",
    "save_training_review",
    "snapshot",
    "tips_queries",
    "training_diagnostics",
    "training_records_snapshot",
]


def snapshot() -> dict:
    gaps = lm_gaps.summary()
    latest_audit = latest_json(ARTIFACTS / "audits", "ableton_audit_*.json")
    latest_benchmark = latest_json(ARTIFACTS / "benchmarks", "ableton_benchmark_*.json")
    queries = tips_queries.list_queries(limit=10)
    feedback = demo_feedback_summary(limit=25)
    agent_queue = improvement_queue(limit=12)
    quality_queue = answer_quality_queue(limit=20)
    training = training_records_snapshot(limit=80)
    plan = repair_plan(
        gaps=gaps,
        feedback=feedback,
        agent_queue=agent_queue,
        quality_queue=quality_queue,
        training=training,
    )
    draft_eval_count = len(_load_draft_eval_suite().get("cases", []))
    return {
        "ok": True,
        "gaps": gaps,
        "feedback": feedback,
        "agent_queue": agent_queue,
        "answer_quality_queue": quality_queue,
        "repair_plan": plan,
        "training_summary": training.get("summary", {}),
        "training_diagnostics": training.get("diagnostics", {}),
        "draft_eval_count": draft_eval_count,
        "recent_queries": queries,
        "latest_audit": latest_audit,
        "latest_benchmark": latest_benchmark,
        "commands": {
            "eval": "./audio-too eval",
            "bench": "./audio-too bench",
            "audit": "./audio-too audit",
            "export_training": "./audio-too export-training",
        },
    }


def run_command(kind: str) -> dict:
    commands = {
        "eval": [python_cmd(), str(ROOT / "scripts" / "ableton_eval.py")],
        "bench": [python_cmd(), str(ROOT / "scripts" / "ableton_benchmark.py")],
        "audit": [python_cmd(), str(ROOT / "scripts" / "ableton_audit.py")],
        "export-training": [python_cmd(), str(ROOT / "scripts" / "export_kenn_training.py")],
    }
    cmd = commands.get(kind)
    if not cmd:
        return {"ok": False, "error": "Unknown LLM improvement command."}
    try:
        completed = subprocess.run(
            cmd,
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=180,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "command": kind,
            "returncode": None,
            "output": f"{kind} timed out after {exc.timeout} seconds.",
            "snapshot": snapshot(),
        }
    return {
        "ok": completed.returncode == 0,
        "command": kind,
        "returncode": completed.returncode,
        "output": ((completed.stdout or "") + (completed.stderr or "")).strip(),
        "snapshot": snapshot(),
    }
