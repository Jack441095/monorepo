"""Creative Lab: repair functions.

Split out of creative_lab.py (was 1,261 lines) — see docs/BACKLOG.md.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


from .constants import (
    CREATIVE_DRAFT_EVAL_PATH,
    KENN_NOTES_DIR,
    KENN_ROOT,
    MAIN_EVAL_PATH,
    PYTHON,
    REPO_ROOT,
)

from .storage import (
    _display_path,
    _load,
    _save,
    _slug,
    now,
)
from .metrics import (
    _repair_terms,
    repair_recommendations,
)
from .eval import (
    _draft_eval_case,
    _draft_eval_suite,
    _load_eval_suite,
    _save_draft_eval_suite,
    _save_eval_suite,
)


def _repair_note_template(item: dict, note_id: str, eval_case_id: str) -> str:
    question = str(item.get("question") or "").strip()
    answer = str(item.get("answer") or "").strip() or "No failed answer was captured."
    comment = str(item.get("comment") or "").strip() or "No comment was captured."
    terms = ", ".join(_repair_terms(item) or ["audio", "workflow", "repair"])
    title = re.sub(r"\s+", " ", question.rstrip("?"))[:70].title() or "Creative Lab Repair"
    return f"""# {title}

Type: Production workflow
Tags: {terms}, creative lab, repair
Status: Draft
Source title: Creative Lab repair queue
Source creator:
Source URL:
Source ID: {item.get("id", "")}

Short answer:
Write the corrected practical answer to: {question}

Try this:
1. Write the first concrete move in Ableton or the mix workflow.
2. Add device names, starting settings, routing details, or listening checks.
3. Explain how to avoid the mistake shown in the failed answer.

Why it matters:
Explain why the corrected answer is safer, more relevant, or better sourced.

Repair context:
Repair note ID: {note_id}
Draft eval ID: {eval_case_id}
Creative Lab feedback: {item.get("rating", "")}
Feedback target: {item.get("target", "")}
Tester comment: {comment}

Failed answer:
{answer}

Personal notes:
Review this draft, replace placeholders with your own verified advice, then change Status to Approved and rebuild KENN.

Related questions:
- What follow-up would a producer ask after this?
- What source or approved note should support this answer?
"""


def create_repair_artifacts(feedback_id: str) -> dict:
    data = _load()
    clean_id = str(feedback_id or "").strip()
    item = next((row for row in data["feedback"] if row.get("id") == clean_id), None)
    if not item:
        return {"ok": False, "error": "Creative Lab feedback item was not found."}
    if item.get("rating") not in {"wrong_direction", "bad_source"}:
        return {"ok": False, "error": "Only repair feedback can create repair artifacts."}
    question = str(item.get("question") or "").strip()
    if not question:
        return {"ok": False, "error": "Feedback item has no KENN question to repair."}
    if item.get("repair_status") == "drafted" and item.get("repair_note") and item.get("eval_case_id"):
        return {
            "ok": True,
            "already_exists": True,
            "note": item["repair_note"],
            "eval_case_id": item["eval_case_id"],
            "message": "Repair artifacts already exist for this feedback item.",
        }

    title = re.sub(r"\s+", " ", question.rstrip("?"))[:70].title() or "Creative Lab Repair"
    note_id = f"{_slug(title)}-creative-repair"
    note_path = KENN_NOTES_DIR / f"{note_id}.md"
    suffix = 2
    while note_path.exists():
        note_id = f"{_slug(title)}-creative-repair-{suffix}"
        note_path = KENN_NOTES_DIR / f"{note_id}.md"
        suffix += 1

    eval_case_id = f"creative-{clean_id}-{_slug(question)}"
    KENN_NOTES_DIR.mkdir(parents=True, exist_ok=True)
    note_path.write_text(_repair_note_template(item, note_id, eval_case_id), encoding="utf-8")

    suite = _draft_eval_suite()
    case = {
        "id": eval_case_id,
        "question": question,
        "min_confidence": "medium",
        "min_source_quality": "high",
        "source_kinds_any": ["note"],
        "answer_must_include": _repair_terms(item),
        "source_must_include": [note_path.stem],
        "creative_lab_feedback": {
            "id": clean_id,
            "rating": item.get("rating", ""),
            "target": item.get("target", ""),
            "comment": str(item.get("comment", ""))[:500],
            "failed_answer": str(item.get("answer", ""))[:1000],
            "repair_note": note_path.name,
        },
    }
    cases = [existing for existing in suite["cases"] if existing.get("id") != eval_case_id]
    cases.append(case)
    suite["cases"] = sorted(cases, key=lambda row: str(row.get("id", "")))
    _save_draft_eval_suite(suite)

    item["repair_status"] = "drafted"
    item["repair_note"] = note_path.name
    item["eval_case_id"] = eval_case_id
    item["repair_created_at"] = now()
    _save(data)
    return {
        "ok": True,
        "feedback": item,
        "note": note_path.name,
        "note_path": _display_path(note_path),
        "eval_case_id": eval_case_id,
        "eval_path": _display_path(CREATIVE_DRAFT_EVAL_PATH),
        "case": case,
        "message": f"Created draft repair note {note_path.name} and eval case {eval_case_id}.",
    }


def _python_cmd() -> str:
    return str(PYTHON) if PYTHON.exists() else "python3"


def _resolve_repair_note(name: str) -> Path | None:
    filename = Path(str(name or "")).name
    if not filename:
        return None
    target = (KENN_NOTES_DIR / filename).resolve()
    try:
        target.relative_to(KENN_NOTES_DIR.resolve())
    except ValueError:
        return None
    return target if target.exists() else None


def _approve_note(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    import sys
    kenn_parent = REPO_ROOT / "studio" / "kenn"
    if str(kenn_parent) not in sys.path:
        sys.path.insert(0, str(kenn_parent))
    from kenn.training.note_quality import validate_note_for_approval

    validation = validate_note_for_approval(text)
    if not validation["ok"]:
        return {"ok": False, "name": path.name, "status": "Draft", **validation}
    if re.search(r"^Status:\s*.+$", text, flags=re.MULTILINE):
        updated = re.sub(r"^Status:\s*.+$", "Status: Approved", text, count=1, flags=re.MULTILINE)
    else:
        updated = text.rstrip() + "\nStatus: Approved\n"
    path.write_text(updated, encoding="utf-8")
    return {"ok": True, "name": path.name, "status": "Approved", "warnings": validation["warnings"]}


def _build_index() -> dict:
    try:
        completed = subprocess.run(
            [_python_cmd(), str(KENN_ROOT / "retrieval" / "build_index.py")],
            cwd=KENN_ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "returncode": None,
            "output": "Index build timed out after 300s (build_index.py did not finish).",
        }
    output = (completed.stdout or "") + (completed.stderr or "")
    # Incrementally update the embedding index for any new chunks
    try:
        update_result = subprocess.run(
            [_python_cmd(), str(KENN_ROOT / "retrieval" / "update_embedding_index.py")],
            cwd=KENN_ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=180,
        )
        emb_output = (update_result.stdout or "") + (update_result.stderr or "")
        output = (output + "\n" + emb_output).strip()
    except subprocess.TimeoutExpired:
        output = (output + "\n  Embedding update timed out after 180s, skipped.").strip()
    except Exception as exc:
        output = (output + f"\n  Embedding update skipped ({exc})").strip()
    return {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "output": output.strip() or ("Index built." if completed.returncode == 0 else "Build failed."),
    }


def _evaluate_repair_case(case: dict) -> dict:
    for path in (REPO_ROOT / "scripts" / "eval", REPO_ROOT / "studio" / "kenn"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    from ableton_eval import evaluate_case  # noqa: PLC0415
    from kenn.core.chat import answer_payload  # noqa: PLC0415

    question = str(case.get("question") or "").strip()
    if not question:
        return {"ok": False, "passed": False, "failures": ["Eval case has no question."], "payload": {}}
    payload = answer_payload(question, limit=8, allow_llm=False)
    failures = evaluate_case(case, payload)
    sources = []
    for source in payload.get("sources") or []:
        if not isinstance(source, dict):
            continue
        sources.append(
            {
                "label": source.get("label") or source.get("title") or source.get("source") or "",
                "kind": source.get("kind", ""),
                "score": source.get("score"),
            }
        )
    return {
        "ok": True,
        "passed": not failures,
        "failures": failures,
        "answer": payload.get("answer", ""),
        "confidence": payload.get("confidence", ""),
        "source_quality": payload.get("source_quality", ""),
        "topics": payload.get("topics", []),
        "sources": sources,
    }


def _source_ranking_report(repair_note: str, sources: list[dict]) -> dict:
    note_stem = Path(str(repair_note or "")).stem.lower()
    source_rows = sources if isinstance(sources, list) else []
    repair_rank = None
    repair_source = None
    top = source_rows[0] if source_rows else {}
    for index, source in enumerate(source_rows, start=1):
        label = str(source.get("label") or "").lower()
        if note_stem and note_stem in label:
            repair_rank = index
            repair_source = source
            break
    return {
        "repair_note": repair_note,
        "repair_note_rank": repair_rank,
        "repair_note_in_top_three": repair_rank is not None and repair_rank <= 3,
        "repair_note_found": repair_rank is not None,
        "repair_source": repair_source or {},
        "top_source": top,
        "top_source_is_note": str(top.get("kind", "")).lower() == "note" if top else False,
        "source_count": len(source_rows),
    }


def promote_repair(feedback_id: str) -> dict:
    data = _load()
    clean_id = str(feedback_id or "").strip()
    item = next((row for row in data["feedback"] if row.get("id") == clean_id), None)
    if not item:
        return {"ok": False, "error": "Creative Lab feedback item was not found."}
    note_name = str(item.get("repair_note") or "").strip()
    eval_case_id = str(item.get("eval_case_id") or "").strip()
    if not note_name or not eval_case_id:
        return {"ok": False, "error": "Create repair artifacts before promoting this feedback item."}
    note_path = _resolve_repair_note(note_name)
    if not note_path:
        return {"ok": False, "error": f"Repair note was not found: {note_name}"}
    case = _draft_eval_case(eval_case_id)
    if not case:
        return {"ok": False, "error": f"Draft eval case was not found: {eval_case_id}"}

    approved = _approve_note(note_path)
    if not approved.get("ok"):
        return {
            "ok": False,
            "error": "Repair note is not ready for approval.",
            "approval": approved,
        }
    build = _build_index()
    eval_result = {"ok": False, "passed": False, "failures": ["Index build failed."], "answer": ""}
    if build.get("ok"):
        eval_result = _evaluate_repair_case(case)
    passed = bool(eval_result.get("passed"))
    run = {
        "created_at": now(),
        "note": note_path.name,
        "eval_case_id": eval_case_id,
        "build_ok": bool(build.get("ok")),
        "eval_passed": passed,
        "failures": eval_result.get("failures", []),
        "answer": str(eval_result.get("answer", ""))[:5000],
        "confidence": eval_result.get("confidence", ""),
        "source_quality": eval_result.get("source_quality", ""),
        "sources": eval_result.get("sources", []),
    }
    run["source_ranking"] = _source_ranking_report(note_path.name, run["sources"])
    history = item.get("repair_history")
    if not isinstance(history, list):
        history = []
    history.append(run)
    item["repair_history"] = history[-20:]
    item["repair_status"] = "promoted_passed" if passed else "promoted_failed"
    item["promoted_at"] = run["created_at"]
    item["last_eval_passed"] = passed
    item["last_eval_at"] = run["created_at"]
    item["last_eval_failures"] = eval_result.get("failures", [])
    item["last_eval_answer"] = str(eval_result.get("answer", ""))[:5000]
    _save(data)
    return {
        "ok": True,
        "feedback": item,
        "note": approved,
        "build": build,
        "eval": eval_result,
        "run": run,
        "message": "Repair promoted and eval passed." if passed else "Repair promoted, but the eval still needs work.",
    }


def promote_repair_eval_case(feedback_id: str) -> dict:
    data = _load()
    clean_id = str(feedback_id or "").strip()
    item = next((row for row in data["feedback"] if row.get("id") == clean_id), None)
    if not item:
        return {"ok": False, "error": "Creative Lab feedback item was not found."}
    if item.get("last_eval_passed") is not True:
        return {"ok": False, "error": "Only passing repair evals can be promoted into the main suite."}
    eval_case_id = str(item.get("eval_case_id") or "").strip()
    case = _draft_eval_case(eval_case_id)
    if not case:
        return {"ok": False, "error": f"Draft eval case was not found: {eval_case_id}"}
    main_case_id = str(item.get("main_eval_case_id") or case.get("id") or eval_case_id).strip()
    promoted = {
        key: value
        for key, value in case.items()
        if key not in {"creative_lab_feedback"}
    }
    promoted["id"] = main_case_id
    promoted["creative_lab_repair"] = {
        "feedback_id": clean_id,
        "repair_note": item.get("repair_note", ""),
        "promoted_at": now(),
    }
    suite = _load_eval_suite(
        MAIN_EVAL_PATH,
        "Regression checks for Audio Tips LLM retrieval and answer quality.",
    )
    cases = [existing for existing in suite["cases"] if existing.get("id") != main_case_id]
    cases.append(promoted)
    suite["cases"] = sorted(cases, key=lambda row: str(row.get("id", "")))
    _save_eval_suite(MAIN_EVAL_PATH, suite)
    item["main_eval_case_id"] = main_case_id
    item["main_eval_promoted_at"] = promoted["creative_lab_repair"]["promoted_at"]
    item["repair_status"] = "regression_added"
    _save(data)
    return {
        "ok": True,
        "case": promoted,
        "path": _display_path(MAIN_EVAL_PATH),
        "feedback": item,
        "message": f"Promoted {main_case_id} into KENN/evals/questions.json.",
    }


def run_repair_recommendation(feedback_id: str) -> dict:
    clean_id = str(feedback_id or "").strip()
    if not clean_id:
        return {"ok": False, "error": "Missing feedback id."}
    data = _load()
    rec = next((item for item in repair_recommendations(data, limit=50) if item.get("feedback_id") == clean_id), None)
    if not rec:
        return {"ok": False, "error": "No actionable recommendation was found for this feedback item."}
    kind = rec.get("kind")
    if kind == "create_draft":
        result = create_repair_artifacts(clean_id)
    elif kind == "promote_repair":
        result = promote_repair(clean_id)
    elif kind == "promote_eval":
        result = promote_repair_eval_case(clean_id)
    elif kind in {"manual_fix", "improve_source_rank"}:
        return {
            "ok": False,
            "manual_required": True,
            "feedback_id": clean_id,
            "recommendation": rec,
            "error": rec.get("action") or "Manual repair work is required before this can be automated.",
        }
    else:
        return {"ok": False, "error": f"Unsupported recommendation kind: {kind}"}
    result["recommendation"] = rec
    result["workflow_kind"] = kind
    return result
