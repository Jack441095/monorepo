"""Weekly job to cluster unanswered queries and synthesize suggested notes."""

import json
import re
import sys
import uuid
from pathlib import Path

# Setup paths
CURRENT_DIR = Path(__file__).resolve().parent
KENN_DIR = CURRENT_DIR.parent.parent  # parent of the importable ``kenn`` package
REPO_ROOT = Path(__file__).resolve().parents[4]
WEBSITE_DIR = REPO_ROOT / "business" / "app"

for path in [str(REPO_ROOT), str(KENN_DIR), str(WEBSITE_DIR)]:
    if path not in sys.path:
        sys.path.insert(0, path)


def fetch_query_signals() -> list[dict]:
    """Retrieve weak questions with frequency and source evidence.

    Unlike the legacy query list, this preserves repeated occurrences across
    feedback, demo, gap, and session stores so prioritisation is evidence-led.
    """
    signals: dict[str, dict] = {}

    def add(question: str, source: str, *, severity: int = 1) -> None:
        clean = re.sub(r"\s+", " ", str(question or "").strip())
        normalized = clean.lower()
        if not normalized:
            return
        item = signals.setdefault(
            normalized,
            {"question": clean, "normalized": normalized, "occurrences": 0, "severity": 1, "sources": []},
        )
        item["occurrences"] += 1
        item["severity"] = max(item["severity"], max(1, int(severity)))
        if source not in item["sources"]:
            item["sources"].append(source)

    # 1. From tips_gaps in audio_too.db (open status)
    try:
        from db import connect
        with connect() as conn:
            cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tips_gaps'")
            if cur.fetchone():
                rows = conn.execute("SELECT question FROM tips_gaps WHERE status = 'open'").fetchall()
                for r in rows:
                    if r["question"]:
                        add(r["question"], "tips_gaps", severity=2)
    except Exception as e:
        print(f"Error fetching from tips_gaps: {e}", file=sys.stderr)

    # 2. From sessions in kenn.db (low confidence)
    try:
        import sqlite3
        kenn_db_path = KENN_DIR / "chats" / "kenn.db"
        if kenn_db_path.exists():
            with sqlite3.connect(kenn_db_path) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'")
                if cur.fetchone():
                    rows = conn.execute("SELECT state FROM sessions").fetchall()
                    for r in rows:
                        try:
                            state = json.loads(r["state"])
                            if state.get("last_confidence") == "low" and state.get("last_question"):
                                add(state["last_question"], "kenn_sessions", severity=2)
                        except Exception:
                            pass
    except Exception as e:
        print(f"Error fetching from sessions: {e}", file=sys.stderr)

    # 3. From demo_questions (low confidence/source quality)
    try:
        from db import connect
        with connect() as conn:
            cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='demo_questions'")
            if cur.fetchone():
                rows = conn.execute(
                    "SELECT question FROM demo_questions WHERE confidence = 'low' OR source_quality = 'low'"
                ).fetchall()
                for r in rows:
                    if r["question"]:
                        add(r["question"], "demo_questions", severity=2)
    except Exception as e:
        print(f"Error fetching from demo_questions: {e}", file=sys.stderr)

    # 4. From demo_feedback (poor ratings/confidence)
    try:
        from db import connect
        with connect() as conn:
            cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='demo_feedback'")
            if cur.fetchone():
                rows = conn.execute(
                    "SELECT question, rating FROM demo_feedback WHERE confidence = 'low' OR source_quality = 'low' OR rating = 'not_useful'"
                ).fetchall()
                for r in rows:
                    if r["question"]:
                        add(r["question"], "demo_feedback", severity=3 if r["rating"] == "not_useful" else 2)
    except Exception as e:
        print(f"Error fetching from demo_feedback: {e}", file=sys.stderr)

    # KENN_DIR is the parent of the importable ``kenn`` package; the package itself lives one level deeper
    _KENN_PKG = KENN_DIR / "kenn"

    # 5. From knowledge_upgrade_cases.json (explicitly flagged known gaps)
    try:
        upgrade_path = _KENN_PKG / "evals" / "knowledge_upgrade_cases.json"
        if upgrade_path.exists():
            data = json.loads(upgrade_path.read_text(encoding="utf-8"))
            for case in data.get("cases", []):
                q = case.get("question", "")
                if q:
                    add(q, "knowledge_upgrade_cases", severity=3)
    except Exception as e:
        print(f"Error fetching from knowledge_upgrade_cases: {e}", file=sys.stderr)

    # 6. From benchmark audit failures (questions that failed eval runs, adversarial excluded)
    try:
        audits_dir = _KENN_PKG / "artifacts" / "audits"
        _evals_path = _KENN_PKG / "evals" / "questions.json"
        _adversarial_ids: set[str] = set()
        if _evals_path.exists():
            _evals = json.loads(_evals_path.read_text(encoding="utf-8"))
            _adversarial_ids = {
                c.get("question", "").lower()
                for c in _evals.get("cases", [])
                if c.get("id", "").startswith("adversarial")
            }
        if audits_dir.exists():
            import glob as _glob
            seen_failures: set[str] = set()
            for af in _glob.glob(str(audits_dir / "*.json")):
                try:
                    audit = json.loads(Path(af).read_text(encoding="utf-8"))
                    for fail in audit.get("benchmark", {}).get("failures", []):
                        q = fail.get("question", "")
                        if q and q not in seen_failures and q.lower() not in _adversarial_ids:
                            seen_failures.add(q)
                            add(q, "benchmark_failures", severity=3)
                except Exception:
                    pass
    except Exception as e:
        print(f"Error fetching from benchmark audits: {e}", file=sys.stderr)

    # 7. From kenn.db sessions with unknown route (unroutable questions)
    try:
        import sqlite3 as _sqlite3
        kenn_db_path = _KENN_PKG / "chats" / "kenn.db"
        if kenn_db_path.exists():
            with _sqlite3.connect(kenn_db_path) as conn:
                conn.row_factory = _sqlite3.Row
                rows = conn.execute("SELECT state FROM sessions").fetchall()
                for r in rows:
                    try:
                        state = json.loads(r["state"])
                        if state.get("last_route") == "unknown" and state.get("last_question"):
                            add(state["last_question"], "unknown_route_sessions", severity=1)
                    except Exception:
                        pass
    except Exception as e:
        print(f"Error fetching unknown-route sessions: {e}", file=sys.stderr)

    return sorted(
        signals.values(),
        key=lambda item: (-item["severity"], -item["occurrences"], item["normalized"]),
    )


def fetch_queries() -> list[str]:
    """Backward-compatible list of unique unanswered/low-confidence questions."""
    return [item["question"] for item in fetch_query_signals()]


def cluster_queries(queries: list[str], *, eps: float = 0.45, min_samples: int = 2) -> dict[int, list[str]]:
    """Cluster queries using DBSCAN semantic embeddings.

    Already uses the torch-free OnnxEmbedder (not sentence_transformers/torch
    — that ABI break was fixed here before this review). The reason this job
    produced zero clusters despite 5,221 sessions / 504 feedback rows of real
    data wasn't a broken import: verified end-to-end against the live
    databases and the previous thresholds (eps=0.35, min_samples=3) were
    calibrated for a much busier, more repetitive question stream than what
    actually exists once deduplicated to real low-confidence signals (66
    distinct questions today). Swept eps/min_samples against the live data:
    0.35/3 finds 0 clusters, 0.45/2 finds 7 semantically coherent ones (e.g.
    "boxy vocals" + "vocals wide without mud"; three genuinely related snare
    layering/transient questions). Defaults updated to match current real
    volume — revisit upward as more data accumulates.
    """
    if len(queries) < min_samples:
        return {}

    try:
        from kenn.retrieval.onnx_embedder import OnnxEmbedder
        from sklearn.cluster import DBSCAN
    except ImportError:
        print("Required ML libraries are not available. Skipping clustering.", file=sys.stderr)
        return {}

    try:
        model = OnnxEmbedder()
        embeddings = model.encode(queries)
    except Exception as exc:
        # ONNX model loading or tokenization might fail if models are not fetched
        print(f"ML libraries failed to run ({exc}). Skipping clustering.", file=sys.stderr)
        return {}

    clustering = DBSCAN(eps=eps, min_samples=min_samples, metric="cosine")
    clustering.fit(embeddings)
    labels = clustering.labels_

    clusters = {}
    for i, label in enumerate(labels):
        if label == -1:
            continue  # Noise
        label_int = int(label)
        if label_int not in clusters:
            clusters[label_int] = []
        clusters[label_int].append(queries[i])

    return clusters


def synthesize_note(cluster_queries: list[str]) -> dict | None:
    """Query context chunks and generate a synthesized note draft via LLM."""
    from kenn.core.chat import answer_payload

    # Retrieve context excerpts
    excerpts = {}
    for q in cluster_queries:
        try:
            res = answer_payload(q, limit=5, allow_llm=False)
            for src in res.get("sources", []):
                label = src.get("label") or src.get("title")
                text = src.get("text")
                if label and text:
                    excerpts[label] = text.strip()
        except Exception as e:
            print(f"Error retrieving search sources: {e}", file=sys.stderr)

    context = ""
    for label, text in list(excerpts.items())[:6]:
        context += f"Source note: {label}\n{text}\n\n"

    system_prompt = """You are an expert audio engineering knowledge base curator for Audio_Too.
Your task is to synthesize a single comprehensive knowledge base note (in Markdown) that answers a cluster of related user queries, based on the provided source excerpts.

Requirements:
1. Title: Create a concise, descriptive title (e.g., "# Fixing Muddy Vocals").
2. Content: Write a clear explanation of the topic, followed by actionable steps (e.g., specific EQ or compression moves in Ableton), and why it works.
3. Formatting: Output the note in clean Markdown. The note must start with a `# Title` header. Include tags at the bottom in the format `Tags: tag1, tag2`.
4. Excerpt Grounding: Use ONLY facts, parameters, and details supported by the provided source excerpts. Do not invent fictitious plugins, DAW shortcuts, or parameters.
"""

    user_message = f"""Here are the related user queries that we could not answer adequately:
{chr(10).join(f'- {q}' for q in cluster_queries)}

Here are the relevant existing source notes in the workspace:
{context}

Please synthesize a new markdown note to cover these questions. Ensure it starts with a '# Title' header and ends with 'Tags: tag1, tag2'.
"""

    draft_content = ""

    # Try local fine-tuned model first
    try:
        from kenn.llm.kenn_lm import KennLM
        lm = KennLM()
        if lm.available:
            rep_query = f"Synthesize a note to answer: {', '.join(cluster_queries)}"
            draft_content = lm.generate(rep_query, context, self_correct=True)
            if draft_content:
                print("Generated note draft using local KENN LM.")
    except Exception as e:
        print(f"Local KENN LM generation failed: {e}", file=sys.stderr)

    # Try cloud/Ollama LLM fallback
    if not draft_content:
        try:
            from kenn.llm.llm_rewrite import chat_completion, is_enabled
            if is_enabled():
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ]
                draft_content = chat_completion(messages, task="rewrite")
                print("Generated note draft using cloud LLM fallback.")
        except Exception as e:
            print(f"Cloud LLM synthesis fallback failed: {e}", file=sys.stderr)

    # Static template fallback if all LLMs are disabled/fail
    if not draft_content:
        title = f"Suggested Note: {cluster_queries[0]}"
        draft_content = f"""# {title}

This note was generated from a cluster of unanswered user queries:
{chr(10).join(f'- {q}' for q in cluster_queries)}

## Action Plan
- Detail EQ, compression, or routing adjustments needed.
- Focus on resolving the issues described in the user queries.

## Context Sources
{context}

Tags: suggested, draft, {cluster_queries[0].lower().split()[0] if cluster_queries[0].split() else 'audio'}
"""
        print("Generated note draft using static fallback template.")

    # Parse title from first line
    title = ""
    lines = draft_content.strip().splitlines()
    if lines and lines[0].startswith("#"):
        title = lines[0].lstrip("#").strip()
    else:
        title = f"Suggested Note: {cluster_queries[0]}"

    return {
        "title": title,
        "content": draft_content,
        "source_cluster_queries": json.dumps(cluster_queries),
    }


def clean_pending_drafts() -> None:
    """Clear previously generated pending drafts to keep the database fresh."""
    from db import connect
    try:
        with connect() as conn:
            conn.execute("DELETE FROM suggested_notes WHERE status = 'pending'")
            conn.commit()
    except Exception as e:
        print(f"Error cleaning pending suggested notes: {e}", file=sys.stderr)


def run_clustering() -> int:
    """Fetch, cluster, synthesize notes, and save them."""
    print("Starting KENN gap clustering weekly job...")
    queries = fetch_queries()
    print(f"Fetched {len(queries)} unique open/low-confidence queries.")

    if len(queries) < 2:
        print("Not enough queries to run DBSCAN clustering (minimum 2 required). Exiting.")
        return 0

    clusters = cluster_queries(queries)
    print(f"Identified {len(clusters)} query clusters of size >= 2.")

    if not clusters:
        return 0

    # Fresh start for pending suggestions
    clean_pending_drafts()

    from db import upsert_record, now

    count = 0
    for cluster_id, cluster_qs in clusters.items():
        print(f"Processing cluster {cluster_id} with {len(cluster_qs)} queries...")
        note = synthesize_note(cluster_qs)
        if note:
            record = {
                "id": str(uuid.uuid4())[:8],
                "title": note["title"],
                "content": note["content"],
                "source_cluster_queries": note["source_cluster_queries"],
                "status": "pending",
                "created_at": now(),
                "updated_at": now(),
            }
            try:
                upsert_record("suggested_notes", record)
                count += 1
                print(f"Upserted suggested note draft: '{note['title']}'")
            except Exception as e:
                print(f"Error saving suggested note to DB: {e}", file=sys.stderr)

    print(f"Clustering job finished. Generated {count} suggested note(s).")
    return count


if __name__ == "__main__":
    run_clustering()
