#!/usr/bin/env python3
"""Export KENN session history and logged feedback queries as ML-ready training records."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

from kenn.paths import PACKAGE_ROOT, PRODUCT_ROOT

# Setup paths relative to script location
KENN_DIR = PACKAGE_ROOT
REPO_ROOT = PRODUCT_ROOT
DB_PATH_KENN = KENN_DIR / "chats" / "kenn.db"
DB_PATH_BUSINESS = REPO_ROOT / "data" / "audio_too.db"
EVAL_QUESTIONS = KENN_DIR / "evals" / "questions.json"
CONVERSATION_PROMPTS = KENN_DIR / "training" / "conversation_prompts.json"
SUPPLEMENTAL_PROMPTS = KENN_DIR / "training" / "supplemental_prompts.json"
NOTES_DIR = KENN_DIR / "Training_Data_Notes"
DEFAULT_OUT = KENN_DIR / "artifacts" / "training" / "kenn_session_training.jsonl"


def get_sqlite_questions() -> set[str]:
    questions = set()

    # 1. KENN sessions database
    if DB_PATH_KENN.exists():
        try:
            conn = sqlite3.connect(str(DB_PATH_KENN))
            cursor = conn.execute("SELECT state FROM sessions")
            for row in cursor.fetchall():
                try:
                    state = json.loads(row[0])
                    q = state.get("last_question")
                    if q and isinstance(q, str) and q.strip():
                        questions.add(q.strip())
                except Exception:
                    pass
            conn.close()
        except sqlite3.Error as e:
            print(f"Warning reading {DB_PATH_KENN}: {e}")

    # 2. Business database
    if DB_PATH_BUSINESS.exists():
        try:
            conn = sqlite3.connect(str(DB_PATH_BUSINESS))


            # tips_queries
            try:
                cursor = conn.execute("SELECT question FROM tips_queries")
                for row in cursor.fetchall():
                    if row[0] and isinstance(row[0], str) and row[0].strip():
                        questions.add(row[0].strip())
            except sqlite3.Error:
                pass

            # demo_feedback
            try:
                cursor = conn.execute("SELECT question FROM demo_feedback")
                for row in cursor.fetchall():
                    if row[0] and isinstance(row[0], str) and row[0].strip():
                        questions.add(row[0].strip())
            except sqlite3.Error:
                pass

            # demo_questions
            try:
                cursor = conn.execute("SELECT question FROM demo_questions")
                for row in cursor.fetchall():
                    if row[0] and isinstance(row[0], str) and row[0].strip():
                        questions.add(row[0].strip())
            except sqlite3.Error:
                pass

            conn.close()
        except sqlite3.Error as e:
            print(f"Warning reading {DB_PATH_BUSINESS}: {e}")

    return questions


def get_eval_questions() -> set[str]:
    questions = set()
    if EVAL_QUESTIONS.exists():
        try:
            data = json.loads(EVAL_QUESTIONS.read_text(encoding="utf-8"))
            cases = data.get("cases") or []
            for case in cases:
                q = case.get("question")
                if q and isinstance(q, str) and q.strip():
                    questions.add(q.strip())
        except Exception as e:
            print(f"Warning reading {EVAL_QUESTIONS}: {e}")
    return questions


def get_approved_note_questions() -> set[str]:
    """Collect author-curated questions from approved knowledge notes.

    Every approved note contributes its title as a direct question and every
    bullet under ``Related questions``. Draft notes are deliberately excluded.
    """
    questions: set[str] = set()
    if not NOTES_DIR.exists():
        return questions

    for path in sorted(NOTES_DIR.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if not re.search(r"^Status:\s*Approved\s*$", text, re.MULTILINE | re.IGNORECASE):
            continue

        title_match = re.search(r"^#\s+(.+?)\s*$", text, re.MULTILINE)
        if title_match:
            title = title_match.group(1).strip()
            questions.add(f"How do I handle {title.lower()}?")

        related_match = re.search(
            r"^Related questions:\s*\n(?P<body>(?:\s*-\s+.+(?:\n|$))+)",
            text,
            re.MULTILINE | re.IGNORECASE,
        )
        if related_match:
            for item in re.findall(r"^\s*-\s+(.+?)\s*$", related_match.group("body"), re.MULTILINE):
                question = item.strip()
                if question:
                    questions.add(question)
    return questions


def get_conversation_prompts(path: Path = CONVERSATION_PROMPTS) -> list[dict]:
    """Load curated multi-turn prompts kept separate from held-out eval cases."""
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = data.get("cases") if isinstance(data, dict) else None
    prompts: list[dict] = []
    for row in rows if isinstance(rows, list) else []:
        question = str(row.get("question", "")).strip() if isinstance(row, dict) else ""
        history = row.get("history") if isinstance(row, dict) else None
        if question and isinstance(history, list) and history:
            prompts.append({"question": question, "history": history})
    return prompts


def get_supplemental_questions(path: Path = SUPPLEMENTAL_PROMPTS) -> set[str]:
    """Load reviewed diagnostic/contrast prompts that are not evaluation cases."""
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    rows = data.get("questions") if isinstance(data, dict) else None
    return {str(question).strip() for question in rows if str(question).strip()} if isinstance(rows, list) else set()


def main() -> int:
    parser = argparse.ArgumentParser(description="Export training dataset from kenn logs and questions.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT, help="Path to write the training JSONL file.")
    parser.add_argument("--min-confidence", default="medium", choices=["low", "medium", "high"], help="Min confidence filter.")
    parser.add_argument("--limit", type=int, default=10000, help="Max number of samples to generate.")
    parser.add_argument(
        "--include-private-data",
        action="store_true",
        help="Include session/demo questions after completing a privacy review.",
    )
    parser.add_argument(
        "--confirm-anonymized",
        action="store_true",
        help="Confirm private questions were reviewed and anonymized before export.",
    )
    parser.add_argument(
        "--include-eval-questions",
        action="store_true",
        help="Include held-out eval prompts (not recommended for a final training dataset).",
    )
    args = parser.parse_args()
    if args.include_private_data and not args.confirm_anonymized:
        parser.error("--include-private-data requires --confirm-anonymized")
    if args.confirm_anonymized and not args.include_private_data:
        parser.error("--confirm-anonymized is only valid with --include-private-data")

    # Ensure paths are in sys.path to load KENN modules
    sys.path.insert(0, str(KENN_DIR.parent))
    from kenn.core.chat import answer_payload, warm_index

    print("Warming KENN index...")
    warm_index()

    print("Gathering prompts from approved notes, curated training files, and reviewed databases...")
    sqlite_qs = get_sqlite_questions() if args.include_private_data else set()
    eval_qs = get_eval_questions() if args.include_eval_questions else set()
    note_qs = get_approved_note_questions()
    conversation_prompts = get_conversation_prompts()
    supplemental_qs = get_supplemental_questions()


    all_inputs = [
        {"question": question, "history": None}
        for question in sorted(sqlite_qs | eval_qs | note_qs | supplemental_qs)
    ]
    all_inputs.extend(conversation_prompts)
    print(
        f"Found {len(note_qs)} approved-note questions, {len(sqlite_qs)} reviewed "
        f"private questions, {len(supplemental_qs)} supplemental questions, "
        f"{len(eval_qs)} explicitly included eval questions, and "
        f"{len(conversation_prompts)} curated multi-turn prompts."
    )
    print(f"Total training prompts collected: {len(all_inputs)}")

    # Map confidence levels to numerical/comparative scores
    conf_scores = {"low": 1, "medium": 2, "high": 3}
    min_score = conf_scores.get(args.min_confidence, 2)

    records = []
    processed = 0

    print("Running retrieval and generating template answers for training set...")
    for item in all_inputs:
        if processed >= args.limit:
            break
        q = item["question"]
        history = item.get("history")


        # We query answer_payload with allow_llm=False to get the exact template-generated answers and retrieved notes.
        try:
            payload = answer_payload(q, history=history, limit=8, allow_llm=False)
        except Exception as e:
            print(f"Error querying question '{q}': {e}")
            continue

        conf = str(payload.get("confidence", "low")).lower()
        score = conf_scores.get(conf, 1)

        # Filter out low confidence answers
        if score < min_score:
            continue

        # Filter out questions that have default fallback answers
        if payload.get("weak_match") or payload.get("conversation_only"):
            continue

        sources = payload.get("sources") or []
        if not sources:
            continue

        # Build context from source notes
        chunks_texts = []
        for src in sources:
            text = src.get("text", "")
            if text and isinstance(text, str):
                chunks_texts.append(text.strip())


        context = "\n\n".join(chunks_texts)
        answer = payload.get("answer", "")
        route = payload.get("route", "")

        if not context or not answer:
            continue

        record = {
            "question": q,
            "context": context,
            "answer": answer,
            "route": route,
            "confidence": conf
        }
        if history:
            record["history"] = history
        records.append(record)
        processed += 1

    # Write output
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"Successfully exported {len(records)} records to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
