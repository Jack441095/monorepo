#!/usr/bin/env python3
"""Friendly entry point for KENN."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent.parent.parent
sys.path.insert(0, str(ROOT.parent))
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT))
from repo_python import python_executable  # noqa: E402



def python_cmd() -> str:
    return python_executable()


def print_help() -> None:
    print(
        "KENN — Kernel Engineering Neural Network (KENN folder)\n\n"
        "Usage:\n"
        "  python main.py build\n"
        "  python main.py ask <question>\n"
        "  python main.py chat\n"
        "  python main.py web\n"
        "  python main.py add-source <url> [title: ...] [creator: ...]\n"
        "  python main.py new-note <title> [source: <id>]\n"
        "  python main.py import-transcript <file> [title: ...] [source: <id>]\n"
        "  python main.py paraphrase-transcript <file> [title: ...] [source: <id>]\n"
        "  python main.py paraphrase-all-transcripts [creator: ...] [tags: ...]\n"
        "  python main.py transcripts\n"
        "  python main.py approve-note <note>\n"
        "  python main.py sources\n"
        "  python main.py fetch-web <url> [title: ...] [creator: ...] [tags: ...]\n"
        "  python main.py list-web-pack\n"
        "  python main.py import-web-pack [limit: 5] [force: yes] [suggested: yes]\n"
        "  python main.py train-chatbot [force: yes] [approve: yes] [build: yes]\n"
        "  python main.py research-topic <topic>\n"
        "  python main.py suggest-sources <topic>\n"
        "  python main.py list-pdf-catalog\n"
        "  python main.py download-pdfs [--essential] [--force] [--category standards]\n"
        "  python main.py build-checklist\n"
        "  python main.py reasoning-history [query]\n"
        "  python main.py show-reasoning <trace_id>\n"
        "  python main.py corrections\n"
        "  python main.py lessons\n"
        "  python main.py trust-scores\n"
        "  python main.py correct <trace_id> <correction_text>\n"
        "  python main.py propose-maintenance\n"
        "  python main.py run-maintenance-scan [force]\n"
        "  python main.py maintenance-log\n"
        "  python main.py\n\n"
        "Examples:\n"
        "  python main.py build\n"
        "  python main.py ask \"How do I freeze and flatten a track?\"\n"
        "  python main.py chat\n"
        "  python main.py web\n"
        "  python main.py add-source https://youtube.com/watch?v=... \"title: Sound Design Tip\" \"creator: Virtual Riot\"\n"
        "  python main.py new-note \"Resampling Bass Sound Design\" \"source: <id>\"\n"
        "  python main.py import-transcript ./my-transcript.txt \"title: Resampling Notes\" \"source: <id>\"\n"
        "  python main.py paraphrase-transcript ./my-transcript.txt \"title: Formal Resampling Lesson\" \"source: <id>\"\n"
        "  python main.py paraphrase-all-transcripts \"creator: Virtual Riot\" \"tags: sound design, drums, ableton\"\n"
        "  python main.py approve-note virtual-riot-delay-fade-mode.md\n"
    )

def run(script: str, args: list[str]) -> int:
    modules = {
        "chat.py": "kenn.core.chat",
        "build_index.py": "kenn.retrieval.build_index",
        "research.py": "kenn.training.research",
        "server.py": "kenn.server",
    }
    module = modules.get(script)
    # This subprocess does not inherit the parent's sys.path.insert() calls
    # (only environment variables cross the process boundary), so `audio_too`
    # (a top-level package at REPO_ROOT, needed by the ONNX embedder) must be
    # added explicitly via PYTHONPATH or it silently falls back to BM25-only.
    child_env = dict(os.environ)
    existing_pythonpath = child_env.get("PYTHONPATH", "")
    pythonpath_parts = [str(ROOT.parent), str(REPO_ROOT)]
    if existing_pythonpath:
        pythonpath_parts.append(existing_pythonpath)
    child_env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
    if module:
        return subprocess.run(
            [python_cmd(), "-m", module, *args],
            cwd=ROOT.parent,
            env=child_env,
            check=False,
        ).returncode
    return subprocess.run(
        [python_cmd(), str(ROOT / script), *args], cwd=ROOT, env=child_env, check=False
    ).returncode


def main() -> int:
    args = sys.argv[1:]
    if not args:
        return run("chat.py", [])
    command = args[0].lower()
    rest = args[1:]
    if command in {"help", "-h", "--help"}:
        print_help()
        return 0
    if command == "build":
        return run("build_index.py", rest)
    if command == "download-pdfs":
        return subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "setup" / "download_training_pdfs.py"), *rest],
            cwd=REPO_ROOT,
            check=False,
        ).returncode
    if command == "build-checklist":
        return subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "build_audio_too_checklist.py"), *rest],
            cwd=REPO_ROOT,
            check=False,
        ).returncode
    if command == "reasoning-history":
        query_text = " ".join(rest).strip()
        from kenn.knowledge import list_reasoning_history
        history = list_reasoning_history(query_text)
        if not history:
            print("No past reasoning traces found.")
            return 0
        print(f"{'Trace ID':<10} | {'Created At':<20} | {'Confidence':<10} | {'Query/Conclusion':<60}")
        print("-" * 110)
        for trace in history:
            query_disp = trace["query"][:28] + ("..." if len(trace["query"]) > 28 else "")
            conclusion_disp = trace["conclusion"][:28] + ("..." if len(trace["conclusion"]) > 28 else "")
            q_and_c = f"Q: {query_disp} / C: {conclusion_disp}"
            print(f"{trace['trace_id'][:8]:<10} | {trace['created_at']:<20} | {trace['confidence']:<10} | {q_and_c:<60}")
        return 0
    if command == "show-reasoning":
        if not rest:
            print("Use: python main.py show-reasoning <trace_id>")
            return 1
        trace_id = rest[0].strip()
        from kenn.knowledge import get_reasoning_trace
        trace = get_reasoning_trace(trace_id)
        if not trace and len(trace_id) < 36:
            from kenn.knowledge import list_reasoning_history
            all_history = list_reasoning_history()
            candidates = [t for t in all_history if t["trace_id"].startswith(trace_id)]
            if len(candidates) == 1:
                trace = candidates[0]
            elif len(candidates) > 1:
                print(f"Multiple traces match short ID '{trace_id}': {[c['trace_id'] for c in candidates]}")
                return 1
        if not trace:
            print(f"Reasoning trace not found: {trace_id}")
            return 1
        import json
        print(json.dumps(trace, indent=2))
        return 0
    if command == "corrections":
        from kenn.knowledge import list_corrections
        corrections = list_corrections()
        if not corrections:
            print("No user corrections found.")
            return 0
        print(f"{'Trace ID':<10} | {'Created At':<20} | {'Query':<30} | {'Correction':<40}")
        print("-" * 110)
        for c in corrections:
            q_disp = c["query"][:28] + ("..." if len(c["query"]) > 28 else "")
            corr_disp = c["correction"][:38] + ("..." if len(c["correction"]) > 38 else "")
            print(f"{c['trace_id'][:8]:<10} | {c['created_at']:<20} | {q_disp:<30} | {corr_disp:<40}")
        return 0
    if command == "lessons":
        from kenn.knowledge import list_lessons
        lessons = list_lessons()
        if not lessons:
            print("No lessons learned found.")
            return 0
        print(f"{'Topic/Tags':<25} | {'Lesson':<80}")
        print("-" * 110)
        for lesson_item in lessons:
            topic_disp = lesson_item["topic"][:23] + ("..." if len(lesson_item["topic"]) > 23 else "")
            lesson_disp = lesson_item["lesson"][:78] + ("..." if len(lesson_item["lesson"]) > 78 else "")
            print(f"{topic_disp:<25} | {lesson_disp:<80}")
        return 0
    if command in ("trust-scores", "trust-sources"):
        from kenn.knowledge import list_source_trust
        scores = list_source_trust()
        if not scores:
            print("No dynamic source trust scores found.")
            return 0
        print(f"{'Source Name':<50} | {'Trust Score':<12} | {'Citations':<10} | {'Corrections':<12}")
        print("-" * 90)
        for s in scores:
            name_disp = s["source_name"][:48] + ("..." if len(s["source_name"]) > 48 else "")
            print(f"{name_disp:<50} | {s['trust_score']:<12.3f} | {s['citations_count']:<10} | {s['corrections_count']:<12}")
        return 0
    if command == "set-trust":
        if len(rest) < 2:
            print("Use: python main.py set-trust <source_name> <trust_score>")
            return 1
        source_name = rest[0].strip()
        try:
            score = float(rest[1].strip())
        except ValueError:
            print("Error: trust_score must be a float.")
            return 1
        from kenn.knowledge import set_source_trust
        set_source_trust(source_name, score)
        print(f"Trust score for '{source_name}' successfully set to {score:.3f}")
        return 0
    if command == "correct":
        if len(rest) < 2:
            print("Use: python main.py correct <trace_id> <correction_text>")
            return 1
        trace_id = rest[0].strip()
        correction_text = " ".join(rest[1:]).strip()
        from kenn.knowledge import ingest_correction, list_reasoning_history
        if len(trace_id) < 36:
            all_history = list_reasoning_history()
            candidates = [t for t in all_history if t["trace_id"].startswith(trace_id)]
            if len(candidates) == 1:
                trace_id = candidates[0]["trace_id"]
            elif len(candidates) > 1:
                print(f"Multiple traces match short ID '{trace_id}': {[c['trace_id'] for c in candidates]}")
                return 1
            else:
                print(f"No reasoning trace matches ID prefix '{trace_id}'")
                return 1
        result = ingest_correction(trace_id, correction_text)
        if result:
            print("Correction successfully recorded and dynamic weights adjusted!")
            print(f"Generated Lesson: {result['lesson']}")
            for p in result["penalized_sources"]:
                print(f"Penalized source '{p['source']}': new trust = {p['new_trust']:.3f}")
        else:
            print(f"Failed to record correction for trace {trace_id}")
            return 1
        return 0
    if command == "contradictions":
        from kenn.knowledge import list_contradictions
        contradictions = list_contradictions()
        if not contradictions:
            print("No open contradictions found in the registry.")
            return 0
        print(f"{'ID':<10} | {'Type':<25} | {'Source A':<25} | {'Source B':<25} | {'Description':<50}")
        print("-" * 140)
        for c in contradictions:
            desc_disp = c["description"][:48] + ("..." if len(c["description"]) > 48 else "")
            print(f"{c['contradiction_id'][:8]:<10} | {c['type']:<25} | {c['source_a'][:23]:<25} | {c['source_b'][:23]:<25} | {desc_disp:<50}")
        return 0
    if command == "resolve-contradiction":
        if len(rest) < 2:
            print("Use: python main.py resolve-contradiction <contradiction_id> primary_a|primary_b|merged")
            return 1
        cid = rest[0].strip()
        strategy = rest[1].strip().lower()
        from kenn.knowledge import resolve_contradiction
        from kenn.core.chat_constants import NOTES_DIR
        success = resolve_contradiction(cid, strategy, NOTES_DIR)
        if success:
            print(f"Contradiction {cid} successfully resolved using strategy '{strategy}'.")
            return 0
        else:
            print(f"Failed to resolve contradiction {cid}.")
            return 1
    if command == "propose-maintenance":
        from kenn.knowledge import propose_maintenance
        proposals = propose_maintenance()
        if not proposals:
            print("No maintenance proposals found.")
            return 0
        print(f"{'Type':<15} | {'Source':<30} | {'Description':<60}")
        print("-" * 110)
        for p in proposals:
            src_disp = p["source"][:28] + ("..." if len(p["source"]) > 28 else "")
            desc_disp = p["description"][:58] + ("..." if len(p["description"]) > 58 else "")
            print(f"{p['type']:<15} | {src_disp:<30} | {desc_disp:<60}")
        return 0
    if command == "run-maintenance-scan":
        # Stage G autonomous entry point (docs/AUDIO_MVP_MASTER_PLAN.md).
        # Runs only the read-only/reversible/receipt-producing jobs G1-G3;
        # never calls resolve_contradiction(), _deprecate_note(),
        # approve_suggested_note(), or any trust-score write.
        force = "force" in [r.strip().lower() for r in rest] or "--force" in rest
        from kenn.knowledge.maintenance_scheduler import run_scheduled_maintenance
        import json
        result = run_scheduled_maintenance(force=force)
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1
    if command == "maintenance-log":
        import json
        from kenn.knowledge.maintenance_scheduler import list_maintenance_runs
        runs = list_maintenance_runs()
        if not runs:
            print("No maintenance runs recorded yet.")
            return 0
        print(f"{'Job':<22} | {'Started At':<26} | {'Status':<10} | {'Summary':<50}")
        print("-" * 115)
        for r in runs:
            summary_disp = json.dumps(r["summary"])[:48]
            print(f"{r['job']:<22} | {r['started_at']:<26} | {r['status']:<10} | {summary_disp:<50}")
        return 0
    if command == "ask":
        if not rest:
            print("Use: python main.py ask <question>")
            return 1
        return run("chat.py", rest)
    if command == "chat":
        return run("chat.py", rest)
    if command == "web":
        return run("server.py", rest)
    if command in {
        "add-source",
        "new-note",
        "import-transcript",
        "paraphrase-transcript",
        "paraphrase-all-transcripts",
        "approve-note",
        "transcripts",
        "sources",
        "fetch-web",
        "list-web-pack",
        "import-web-pack",
        "train-chatbot",
        "research-topic",
        "suggest-sources",
        "list-pdf-catalog",
    }:
        return run("research.py", [command, *rest])
    return run("chat.py", args)


if __name__ == "__main__":
    raise SystemExit(main())
