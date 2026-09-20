"""Bridge between the website control panel and KENN."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import audiogen_bridge

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ABLETON_ROOT = REPO_ROOT / "studio" / "kenn" / "kenn"
NOTES_DIR = ABLETON_ROOT / "Training_Data_Notes"

if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
from repo_python import python_executable  # noqa: E402

# ``kenn`` is imported as a package, so Python needs the package's parent
# (``studio/kenn``) on the import path.  ``server.py`` is launched from
# business/app/ and does not get it on sys.path automatically.
if str(REPO_ROOT / "studio" / "kenn") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "studio" / "kenn"))

from kenn.training.research import (  # noqa: E402
    NOTES_DIR as _NOTES_DIR,
    TRANSCRIPTS_DIR,
    create_note_from_question,
    find_note_for_transcript,
    load_transcript_meta,
    note_status,
    paraphrase_all_transcripts,
    set_note_status,
    title_from_transcript,
)
from kenn.core.chat import answer_payload  # noqa: E402
from kenn.core.mix_revision_intent import is_mix_revision_request, strip_revision_phrasing  # noqa: E402
from kenn.core.session_memory import (  # noqa: E402
    get_remembered_automix_project,
    remember_automix_project,
    remember_pending_automix_job,
)

ABLETON_WEB_HOST = "127.0.0.1"
ABLETON_WEB_PORT = 8090


def _frontmatter_value(text: str, key: str) -> str:
    prefix = f"{key.lower()}:"
    for line in text.splitlines()[:30]:
        if line.lower().startswith(prefix):
            return line.split(":", 1)[1].strip()
    return ""


def list_notes(*, status: str = "", query: str = "", limit: int = 300) -> list[dict]:
    """List training notes for the Knowledge Admin dashboard."""
    if not NOTES_DIR.exists():
        return []
    status_filter = str(status or "").strip().lower()
    query_filter = str(query or "").strip().lower()
    items: list[dict] = []
    for path in sorted(NOTES_DIR.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            stat = path.stat()
        except OSError:
            continue
        current_status = note_status(path)
        if status_filter and status_filter != "all" and current_status.lower() != status_filter:
            continue
        title = text.splitlines()[0].lstrip("# ").strip() if text.splitlines() else path.stem.replace("-", " ").title()
        tags = _frontmatter_value(text, "Tags")
        if query_filter:
            haystack = f"{path.name} {title} {tags} {text[:2000]}".lower()
            if query_filter not in haystack:
                continue
        items.append(
            {
                "name": path.name,
                "title": title or path.stem.replace("-", " ").title(),
                "status": current_status,
                "tags": tags,
                "size_bytes": stat.st_size,
                "updated_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
    return items[: max(1, min(1000, int(limit or 300)))]


def python_cmd() -> str:
    return python_executable()


def list_transcript_items() -> list[dict]:
    records = {item.get("file"): item for item in load_transcript_meta()}
    items: list[dict] = []
    transcript_files = sorted(
        path for path in TRANSCRIPTS_DIR.glob("*") if path.suffix.lower() in {".txt", ".vtt", ".md"}
    )
    for transcript in transcript_files:
        note = find_note_for_transcript(transcript.name)
        record = records.get(transcript.name, {})
        status = note_status(note) if note else record.get("status", "Unprocessed")
        items.append(
            {
                "transcript": transcript.name,
                "title": record.get("title") or title_from_transcript(transcript),
                "creator": record.get("creator", ""),
                "status": status,
                "note": note.name if note else "",
                "updated_at": record.get("updated_at", ""),
            }
        )

    if _NOTES_DIR.exists():
        linked = {item["note"] for item in items if item.get("note")}
        for note in sorted(_NOTES_DIR.glob("*.md")):
            if note.name in linked:
                continue
            status = note_status(note)
            if status.lower() not in {"draft", "unmarked"}:
                continue
            items.append(
                {
                    "transcript": "",
                    "title": note.stem.replace("-", " ").title(),
                    "creator": "",
                    "status": status,
                    "note": note.name,
                    "updated_at": "",
                }
            )
    return items


def resolve_note(name: str) -> Path:
    candidate = Path(name)
    options = [candidate, NOTES_DIR / name, NOTES_DIR / f"{name}.md"]
    for path in options:
        resolved = path.resolve()
        if str(resolved).startswith(str(NOTES_DIR.resolve())) and resolved.exists():
            return resolved
    raise FileNotFoundError(f"Note not found: {name}")


def read_note(name: str) -> dict:
    path = resolve_note(name)
    return {"name": path.name, "content": path.read_text(encoding="utf-8"), "status": note_status(path)}


def write_note(name: str, content: str) -> dict:
    path = resolve_note(name)
    path.write_text(content, encoding="utf-8")
    return {"name": path.name, "status": note_status(path)}


def approve_note(name: str) -> dict:
    path = resolve_note(name)
    import sys
    kenn_parent = REPO_ROOT / "studio" / "kenn"
    if str(kenn_parent) not in sys.path:
        sys.path.insert(0, str(kenn_parent))
    from kenn.training.note_quality import validate_note_for_approval

    validation = validate_note_for_approval(path.read_text(encoding="utf-8"))
    if not validation["ok"]:
        return {"ok": False, "name": path.name, "status": note_status(path), **validation}
    path = set_note_status(path, "Approved")
    return {"ok": True, "name": path.name, "status": "Approved", "warnings": validation["warnings"]}


def build_index() -> dict:
    # Run full index rebuild (BM25 terms + chunks)
    script = ABLETON_ROOT / "retrieval" / "build_index.py"
    try:
        completed = subprocess.run(
            [python_cmd(), str(script)],
            cwd=ABLETON_ROOT,
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
            [python_cmd(), str(ABLETON_ROOT / "retrieval" / "update_embedding_index.py")],
            cwd=ABLETON_ROOT,
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
        "output": output or ("Index built." if completed.returncode == 0 else "Build failed."),
    }


def suggest_questions(query: str = "", *, limit: int = 8, include_dashboard_extra: bool = False) -> dict:
    if str(ABLETON_ROOT.parent) not in sys.path:
        sys.path.insert(0, str(ABLETON_ROOT.parent))
    from kenn.core.suggestions import catalog_payload, typeahead

    extra: list[str] = []
    if include_dashboard_extra:
        try:
            import lm_gaps
            import tips_queries

            for gap in lm_gaps.list_gaps_filtered(status="open", limit=5):
                q = str(gap.get("question", "")).strip()
                if q:
                    extra.append(q)
            for row in tips_queries.list_queries(limit=10):
                q = str(row.get("question", "")).strip()
                if q:
                    extra.append(q)
        except OSError:
            pass
    return {
        "ok": True,
        "query": query,
        "suggestions": typeahead(query, limit=limit),
        "starters": catalog_payload(extra=extra or None)["starters"],
    }


def _revision_payload(
    question: str,
    *,
    answer: str,
    found: bool,
    confidence: str,
    automix_revision: dict | None = None,
    related_questions: list[str] | None = None,
    revision_history_id: int | None = None,
) -> dict:
    """Shared response shape for the mix-revision branch below -- matches
    the schema every other ask() payload uses (found/confidence/topics/
    route/grounding_mode/...) so callers don't need a special case."""
    return {
        "question": question,
        "answer": answer,
        "sources": (
            [{"label": "AutoMix revision job", "source": automix_revision.get("job_id", ""),
              "kind": "automix_revision", "score": 1.0}]
            if automix_revision else []
        ),
        "found": found,
        "confidence": confidence,
        "source_quality": "generated" if found else "not_needed",
        "topics": ["automix", "revision"],
        "related_questions": related_questions or [],
        "used_history": False,
        "llm_enhanced": False,
        "llm_available": False,
        "intent": "revise_mix",
        "route": "automix_revision",
        "weak_match": not found,
        "grounding_mode": "not_needed",
        **({"automix_revision": automix_revision} if automix_revision else {}),
        **({"revision_history_id": revision_history_id} if revision_history_id else {}),
    }


def _handle_mix_revision(question: str, *, session_id: str, project_id: str) -> dict:
    """A KENN chat message detected as a mix-revision request
    (kenn.core.mix_revision_intent.is_mix_revision_request) -- queue a
    real automix_jobs.queue_revision() job. This stays here, not in
    kenn.core, because it crosses into the Business domain's job queue;
    mirrors how audiogen_bridge.enqueue_full_song_render() is called from
    this same function for AudioGen requests, just below. The actual DSP
    APPLICATION (magnitude words, reverb targeting, compound multi-topic
    feedback) is System A's already-tested apply_revision_feedback(), run
    by automix_worker.py when the job is claimed -- nothing here
    reimplements that application logic.

    2026-08-06 (D1.5, docs/KENN_FUTURE_PLAN.md Phase 1): this docstring
    previously claimed apply_revision_feedback() already handled
    "multi-topic feedback" -- checked the actual function body and it
    didn't; a compound comment like "vocals louder, bass louder too" only
    ever applied the first matched change, silently dropping the rest
    (locked in as an explicit, deliberately-tested limitation at the
    time). Fixed in mix_intent.py/mix_decision_engine.py; this claim is
    now actually true.

    The chat reply below DOES call parse_mix_intents() (the same parser
    apply_revision_feedback() itself calls internally) purely to describe
    what's about to happen -- so the explanation is guaranteed to describe
    the same DSP changes System A will actually apply, not a second,
    independent guess at them.
    """
    resolved_project_id = project_id.strip() or get_remembered_automix_project(session_id)
    display_text = strip_revision_phrasing(question)

    if not resolved_project_id:
        return _revision_payload(
            question,
            answer=(
                "I can do that, but I don't know which project's mix you mean yet.\n\n"
                "Short answer:\n"
                "Tell me the project, or open it on the AutoMix dashboard first so I know "
                "which one you're working on.\n\n"
                "Try this:\n"
                "1. Say the project name along with your request.\n"
                "2. Or open the project on the dashboard, then ask again here."
            ),
            found=False,
            confidence="medium",
        )

    from api_schemas import AutomixRevisionRequest, SchemaValidationError
    import automix_jobs

    try:
        _status, response = automix_jobs.queue_revision(
            AutomixRevisionRequest.from_payload({"project_id": resolved_project_id, "feedback": question})
        )
    except automix_jobs.NoCompletedMix:
        return _revision_payload(
            question,
            answer=(
                f'I understood "{display_text}" as a mix change, but there\'s no completed mix '
                "for this project yet to revise.\n\n"
                "Short answer:\n"
                "Render a first mix before asking for a revision.\n\n"
                "Try this:\n"
                "1. Start a mix on the AutoMix dashboard for this project.\n"
                "2. Once it completes, ask me for changes here."
            ),
            found=False,
            confidence="medium",
        )
    except (SchemaValidationError, ValueError) as exc:
        return _revision_payload(question, answer=f"I couldn't queue that revision: {exc}", found=False, confidence="low")
    except Exception as exc:  # pragma: no cover - defensive chat-facing boundary
        return _revision_payload(
            question, answer=f"Something went wrong queuing that revision: {exc}", found=False, confidence="low",
        )

    remember_automix_project(session_id, resolved_project_id)
    job_id = response.get("job_id", "")
    if job_id:
        remember_pending_automix_job(session_id, job_id)

    revision_history_id = None
    try:
        from song_projects import record_revision_request

        revision_history_id = record_revision_request(resolved_project_id, question)
    except Exception:
        # D2.2 storage is a memory nicety, not the revision itself -- the
        # job above already queued successfully, same boundary philosophy
        # as the dsp_description try/except below.
        pass

    try:
        from audio_analysis.integration.mix_intent import describe_mix_intents, parse_mix_intents

        intents = parse_mix_intents(question, {})
        dsp_description = describe_mix_intents(intents)
    except Exception:
        # Chat-facing boundary, same philosophy as the queueing try/except
        # above: the revision job already queued successfully by this point
        # (the thing that actually matters) -- a failure describing it must
        # never surface as an error about the job itself.
        dsp_description = "apply that change"

    return _revision_payload(
        question,
        answer=(
            f'Got it -- re-rendering the mix now with: "{display_text}".\n\n'
            "Short answer:\n"
            f"I'll {dsp_description}. This runs in the background as a new, separate "
            "version -- your current mix stays untouched.\n\n"
            "Try this:\n"
            "1. Watch the AutoMix dashboard for the revision job to complete.\n"
            "2. Ask me for another change here once you've heard it."
        ),
        found=True,
        confidence="high",
        automix_revision={"ok": True, "job_id": job_id, "project_id": resolved_project_id, "status": response.get("status", "")},
        revision_history_id=revision_history_id,
        related_questions=[
            "Make it brighter",
            "Add a bit more reverb on the vocal",
            "Check the status of my revision",
        ],
    )


def ask(
    question: str,
    limit: int = 5,
    history: list | None = None,
    *,
    allow_llm: bool = True,
    channel: str | None = None,
    session_id: str = "",
    allow_generation: bool = True,
    project_id: str = "",
) -> dict:
    if is_mix_revision_request(question):
        payload = _handle_mix_revision(question, session_id=session_id, project_id=project_id)
        if channel:
            import tips_queries

            tips_queries.record_query(question, payload, channel=channel)
        return payload
    if audiogen_bridge.prompt_requests_generation(question):
        if not allow_generation:
            return {
                "question": question,
                "answer": "Audio generation is unavailable on this public chat. Use the authenticated Creative Lab instead.",
                "sources": [],
                "found": False,
                "confidence": "high",
                "source_quality": "not_needed",
                "topics": ["audiogen"],
                "related_questions": ["How should I arrange a generated song?"],
                "used_history": False,
                "llm_enhanced": False,
                "conversation_only": True,
                "weak_match": False,
            }
        generation_kind = audiogen_bridge.generation_request_kind(question)
        if generation_kind == "clarify":
            emotion = audiogen_bridge.infer_emotion(question)
            return {
                "question": question,
                "answer": (
                    f"I can make that in the {emotion} emotion mode. Do you want a short loop/chorus idea, "
                    "or a full-song render?\n\n"
                    "Short answer:\n"
                    "Say either `generate a loop` or `generate a full song`, and I will route it to AudioGen.\n\n"
                    "Try this:\n"
                    f"1. Generate a {emotion} loop.\n"
                    f"2. Generate a full {emotion} song.\n"
                    "3. After it renders, ask me how to arrange or mix it."
                ),
                "sources": [],
                "found": False,
                "confidence": "medium",
                "source_quality": "not_needed",
                "topics": ["audiogen", "composition"],
                "related_questions": [
                    f"Generate a {emotion} loop",
                    f"Generate a full {emotion} song",
                    "How should I mix the generated idea?",
                ],
                "used_history": False,
                "llm_enhanced": False,
                "llm_available": False,
                "intent": "generate",
                "route": "audiogen",
                "weak_match": False,
                "grounding_mode": "strong",
                "audiogen": {"ok": True, "emotion": emotion, "kind": "clarify"},
            }
        if generation_kind == "full_song":
            job = audiogen_bridge.enqueue_full_song_render(
                emotion=audiogen_bridge.infer_emotion(question),
                bars=4,
                k=1,
                publish=True,
            )
            if job.get("ok"):
                queued = job.get("job") or {}
                emotion = queued.get("emotion", "joy")
                return {
                    "question": question,
                    "answer": (
                        f"Done. I queued a full AudioGen song with the {emotion} emotion profile.\n\n"
                        "Short answer:\n"
                        "The render is running in the background, so the chat stays usable while AudioGen works.\n\n"
                        "Try this:\n"
                        "1. Open the dashboard AudioGen tab and watch the render queue.\n"
                        "2. When the job completes, load it into the player or open the WAV from the portfolio audio list.\n"
                        "3. Ask me to review the generated song structure or suggest mix changes."
                    ),
                    "sources": [
                        {
                            "label": "LLM_AudioGen render queue",
                            "source": queued.get("id", ""),
                            "kind": "audiogen_queue",
                            "score": 1.0,
                        }
                    ],
                    "found": True,
                    "confidence": "high",
                    "source_quality": "generated",
                    "topics": ["audiogen", "composition"],
                    "related_questions": [
                        "Check my latest AudioGen render",
                        "How should I arrange this generated song?",
                        "How should I mix the generated song?",
                    ],
                    "used_history": False,
                    "llm_enhanced": False,
                    "llm_available": False,
                    "intent": "generate",
                    "route": "audiogen",
                    "weak_match": False,
                    "grounding_mode": "strong",
                    "audiogen": job,
                }
            generation = job
        else:
            generation = audiogen_bridge.generate_for_kenn(question)
        if generation.get("ok"):
            entry = generation.get("portfolio_entry") or {}
            wav_path = generation.get("wav_path", "")
            answer = (
                f"Done. I generated an AudioGen chorus with the {generation.get('emotion', 'joy')} profile.\n\n"
                "Short answer:\n"
                "The WAV has been rendered locally and published to the portfolio audio list.\n\n"
                "Try this:\n"
                "1. Open the portfolio and play the generated audio example.\n"
                "2. If the feel is close, ask for a new seed, different emotion, or longer render.\n"
                "3. If you want a complete arrangement, use `./audio-too audiogen render --emotion "
                f"{generation.get('emotion', 'joy')}`.\n\n"
                "Sources:\n"
                f"- LLM_AudioGen local generator ({wav_path})"
            )
            if entry.get("src"):
                answer += f"\n- Portfolio entry: {entry.get('title', 'AudioGen render')} ({entry.get('src')})"
            payload = {
                "question": question,
                "answer": answer,
                "sources": [
                    {
                        "label": "LLM_AudioGen local generator",
                        "source": wav_path,
                        "kind": "audiogen",
                        "score": 1.0,
                    }
                ],
                "found": True,
                "confidence": "high",
                "source_quality": "generated",
                "topics": ["audiogen", "composition"],
                "related_questions": [
                    "Generate a love chorus with a different seed",
                    "Render a full AudioGen song",
                    "How should I mix this generated chorus?",
                ],
                "used_history": False,
                "llm_enhanced": False,
                "llm_available": False,
                "intent": "generate",
                "route": "audiogen",
                "weak_match": False,
                "grounding_mode": "strong",
                "grounding": {
                    "score": 100,
                    "top_source_trust": 1.0,
                    "approved_note": False,
                    "source_topic_match": True,
                    "answered_intent": True,
                    "route_known": True,
                    "warnings": [],
                },
                "audiogen": generation,
            }
        else:
            payload = {
                "question": question,
                "answer": (
                    "I understood this as an AudioGen request, but local generation failed.\n\n"
                    "Short answer:\n"
                    f"{generation.get('error', 'AudioGen did not return a usable result.')}\n\n"
                    "Try this:\n"
                    "1. Run `./audio-too audiogen status`.\n"
                    "2. Then run `./audio-too audiogen phrase --emotion joy --bars 8`.\n"
                    "3. If that fails, run `./audio-too audiogen test` and check the reported error."
                ),
                "sources": [],
                "found": False,
                "confidence": "low",
                "source_quality": "low",
                "topics": ["audiogen"],
                "related_questions": [],
                "used_history": False,
                "llm_enhanced": False,
                "llm_available": False,
                "intent": "generate",
                "route": "audiogen",
                "weak_match": True,
                "grounding_mode": "weak",
                "grounding": {"score": 0, "warnings": ["AudioGen generation failed"]},
                "audiogen": generation,
            }
        if channel:
            import tips_queries

            tips_queries.record_query(question, payload, channel=channel)
        return payload

    payload = answer_payload(question, limit=limit, history=history, allow_llm=allow_llm, session_id=session_id)
    if channel:
        import lm_gaps
        import tips_queries

        tips_queries.record_query(question, payload, channel=channel)
        if not payload.get("conversation_only") and payload.get("route") != "audiogen":
            lm_gaps.record_gap(question, payload, channel=channel)
    return payload


def create_note_from_question_api(question: str, topics: list | None = None) -> dict:
    q = str(question).strip()
    if len(q) < 3:
        return {"ok": False, "error": "Question must be at least 3 characters."}
    topic_list = topics if isinstance(topics, list) else []
    path = create_note_from_question(q, topic_list)
    return {
        "ok": True,
        "note": path.name,
        "message": f"Draft note created: {path.name}. Edit, approve, then ./ableton build.",
    }


def create_note_from_gap(gap_id: str) -> dict:
    import tips_gaps

    gap = tips_gaps.get_gap(gap_id)
    if not gap:
        return {"ok": False, "error": "Gap not found."}
    if gap.get("status") != "open":
        return {"ok": False, "error": f"Gap status is {gap.get('status')}, not open."}
    topics = gap.get("topics") if isinstance(gap.get("topics"), list) else []
    path = create_note_from_question(str(gap.get("question", "")), topics)
    tips_gaps.link_gap_note(gap_id, path.name)
    return {
        "ok": True,
        "note": path.name,
        "message": f"Draft note created: {path.name}. Edit in Transcript Review, approve, then ./ableton build.",
    }


def llm_status() -> dict:
    from kenn.llm.llm_rewrite import public_status

    return public_status()


def polish_note(name: str) -> dict:
    from kenn.training.research import TRANSCRIPTS_DIR, maybe_llm_polish_note, resolve_note_path

    try:
        from kenn.llm.llm_rewrite import is_enabled, public_status
    except ImportError:
        return {"ok": False, "error": "LLM module not available."}

    if not is_enabled():
        status = public_status()
        return {"ok": False, "error": status.get("message", "LLM is not configured.")}

    path = resolve_note_path(name)
    draft = path.read_text(encoding="utf-8", errors="replace")
    transcript_path = None
    for line in draft.splitlines()[:30]:
        if line.lower().startswith("transcript file:"):
            transcript_name = line.split(":", 1)[1].strip()
            if transcript_name:
                candidate = TRANSCRIPTS_DIR / transcript_name
                if candidate.exists():
                    transcript_path = candidate
            break
    if transcript_path is None:
        return {"ok": False, "error": "No linked transcript file found in this note."}

    if not maybe_llm_polish_note(path, transcript_path, title=path.stem.replace("-", " ").title()):
        return {
            "ok": False,
            "error": "LLM polish failed or returned an invalid structure. Keep editing manually.",
        }
    content = path.read_text(encoding="utf-8")
    return {
        "ok": True,
        "name": path.name,
        "content": content,
        "status": note_status(path),
        "llm_enhanced": True,
        "message": "Note polished with LLM. Review before approving.",
    }


def paraphrase_all(fields: dict[str, str] | None = None) -> dict:
    payload = {key: str(value) for key, value in (fields or {}).items() if value is not None}
    if payload.get("force") in (True, "true", "yes", "1"):
        payload["force"] = "yes"
    if payload.get("llm") in (True, "true", "yes", "1"):
        payload["llm"] = "yes"
    use_llm = payload.get("llm") == "yes"
    created = paraphrase_all_transcripts(payload)
    items = [
        {
            "note": path.name,
            "title": path.stem.replace("-", " ").title(),
        }
        for path in created
    ]
    base = (
        f"Created {len(items)} draft note(s)."
        if items
        else "No new drafts were created (existing notes were skipped)."
    )
    if use_llm and items:
        base += " LLM polish applied where configured."
    return {
        "ok": True,
        "count": len(items),
        "created": items,
        "llm": use_llm,
        "message": base,
    }


def web_chat_url() -> str:
    return f"http://{ABLETON_WEB_HOST}:{ABLETON_WEB_PORT}"


def fetch_web(url: str, fields: dict[str, str] | None = None) -> dict:
    from kenn.retrieval.web_ingest import fetch_web_article

    payload = fields or {}
    return fetch_web_article(
        url,
        payload.get("title", ""),
        payload.get("creator", ""),
        payload.get("tags", ""),
        force=str(payload.get("force", "")).lower() in {"yes", "true", "1"},
    )


def import_web_pack(limit: int | None = None, force: bool = False, include_suggested: bool = False) -> dict:
    from kenn.retrieval.web_ingest import import_web_pack as run_import

    return run_import(limit=limit, force=force, include_suggested=include_suggested)


def train_chatbot(approve: bool = False, build: bool = False, force: bool = False, use_llm: bool = False) -> dict:
    from kenn.training.research import train_chatbot as run_train

    return run_train(approve=approve, build=build, force=force, use_llm=use_llm)


def list_web_pack() -> list[dict]:
    from kenn.retrieval.web_ingest import list_web_pack_entries

    return list_web_pack_entries()


def web_health() -> dict:
    import urllib.error
    import urllib.request

    url = f"{web_chat_url()}/api/health"
    try:
        with urllib.request.urlopen(url, timeout=1.5) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return {"ok": True, "running": True, "url": web_chat_url(), "app": payload.get("app", "KENN")}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return {
            "ok": True,
            "running": False,
            "url": web_chat_url(),
            "hint": "Start the standalone chat with: python main.py ableton web",
        }


def save_mix_version(session_id: str, version_label: str, metrics: dict, repair_chain: dict) -> dict:
    if str(ABLETON_ROOT.parent) not in sys.path:
        sys.path.insert(0, str(ABLETON_ROOT.parent))
    from kenn.core import session_memory
    session_memory.save_mix_version(session_id, version_label, metrics, repair_chain)
    return {"ok": True}


def list_mix_versions(session_id: str) -> dict:
    if str(ABLETON_ROOT.parent) not in sys.path:
        sys.path.insert(0, str(ABLETON_ROOT.parent))
    from kenn.core import session_memory
    versions = session_memory.list_mix_versions(session_id)
    return {"ok": True, "versions": versions}
