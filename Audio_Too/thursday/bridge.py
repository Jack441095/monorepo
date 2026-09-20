"""Thursday API Bridge — called by Website/server.py for /api/thursday/ask.

Runs the Thursday orchestrator in-process, returning structured results
that include both the answer text and any navigation suggestions.
"""

from __future__ import annotations

import logging
import sys as _sys
from pathlib import Path

logger = logging.getLogger(__name__)

BUSINESS_ROOT = Path(__file__).resolve().parent.parent
AGENTS_ROOT = BUSINESS_ROOT / "business" / "agents"

if str(AGENTS_ROOT) not in _sys.path:
    _sys.path.insert(0, str(AGENTS_ROOT))
if str(BUSINESS_ROOT) not in _sys.path:
    _sys.path.insert(0, str(BUSINESS_ROOT))
if str(BUSINESS_ROOT / "studio" / "kenn") not in _sys.path:
    _sys.path.insert(0, str(BUSINESS_ROOT / "studio" / "kenn"))


def ask(
    question: str,
    session_id: str = "",
    profile_id: str = "",
    request_id: str = "",
) -> dict:
    """Run Thursday on a user question and return a structured response.

    Args:
        question: The user's question.
        session_id: Optional session ID for continuity.
        profile_id: Optional user profile ID for personalization.

    Returns:
        dict with:
          - ``answer``: formatted response text
          - ``intent``: detected intent name
          - ``service``: matched service name (if any)
          - ``navigate_url``: URL to redirect to, or None
          - ``navigate_label``: human label for the navigation link
          - ``suggestions``: list of follow-up suggestions [{label, url}, ...]
          - ``session_id``: current session ID
          - ``greeting``: personalized greeting (for UI display)
    """
    from thursday.orchestrator import classify_request, handle  # noqa: E402
    from thursday.session_manager import get_or_create_session, update_context  # noqa: E402
    from thursday.personality import get_greeting  # noqa: E402
    import thursday.user_profile as user_profile  # noqa: E402
    from thursday.command_gateway import (  # noqa: E402
        assistant_response_for,
        command_for_text,
        execute_command,
        result_for_response,
    )

    # Get or create session
    session = get_or_create_session(session_id)
    current_session_id = session["session_id"]

    # Set profile if specified
    if profile_id:
        update_context(session, {"profile_id": profile_id})
    profile_id = session.get("context", {}).get("profile_id", "default")

    # Detect mood from question
    mood = user_profile.detect_mood(question)
    if mood:
        user_profile.set_mood(mood, profile_id)
        session["context"]["_mood"] = mood

    command = command_for_text(
        question,
        actor_id="dashboard",
        correlation_id=request_id,
    )
    command_result = execute_command(command, session=session, handle_fn=handle)
    if command_result.error is not None:
        answer_text = command_result.error.message
    else:
        answer_text = str(command_result.result.get("answer") or "")
    semantic_result = command_result.result if command_result.error is None else {}

    # Use the persisted resolved turn so contextual follow-ups expose the same
    # intent and service that the orchestrator actually selected.
    last_user_turn = next(
        (turn for turn in reversed(session.get("turns", [])) if turn.get("role") == "user"),
        {},
    )
    fallback_intent = classify_request(question, session).intent
    intent_name = last_user_turn.get("intent") or fallback_intent.name
    service = last_user_turn.get("service_used") if last_user_turn.get("text") == question else None

    # Determine navigation based on answer content
    navigate_url = None
    navigate_label = None
    suggestions = _suggestions_from_answer(answer_text, question)

    lower = question.lower()

    # ── Navigation routing ──────────────────────────────────────────
    # AudioGen / Creative Lab
    if any(w in lower for w in ["audiogen", "audio gen", "creative lab", "generate loop",
                                 "generate beat", "make a song", "make a beat", "render song",
                                 "creative", "generat"]):
        navigate_url = "/audiogen"
        navigate_label = "Open AudioGen Lab"

    # Audio Analysis / Mix Review / File Scan
    elif any(w in lower for w in ["audio analysis", "audio scan", "scan audio", "analyze audio",
                                   "analyse audio", "analyse mix", "analyze mix", "scan my",
                                   "mix analysis", "mix review", "audio diagnostics",
                                   "audio analysis tool", "scan files", "scan folder",
                                   "scan audio files", "analyze my mix", "analyse my mix",
                                   "audio file diagnostics"]):
        navigate_url = "/audio-analysis"
        navigate_label = "Open Audio Analysis"

    # KENN Knowledge
    elif any(w in lower for w in ["kenn", "knowledge", "production question", "mixing advice",
                                   "ableton question", "load kenn"]):
        navigate_url = "http://127.0.0.1:8090"
        navigate_label = "Open KENN Chat"

    # Calendar / Agenda
    elif any(w in lower for w in ["calendar", "agenda", "schedule", "what's on", "my day", "my week"]):
        navigate_url = "/dashboard?tab=calendar"
        navigate_label = "View Calendar"

    # Business ops / Dashboard
    elif (
        service in {"business_status", "weekly_review", "week_ahead", "pipeline", "reminders", "monthly_report", "dashboard", "business_insights"}
        or any(w in lower for w in ["dashboard", "admin", "control panel"])
    ):
        navigate_url = "/dashboard"
        navigate_label = "Open Dashboard"

    # Hub / Home
    elif any(w in lower for w in ["hub", "home", "main page"]):
        navigate_url = "/hub"
        navigate_label = "Open Hub"

    # Portfolio
    elif any(w in lower for w in ["portfolio", "showcase", "my work"]):
        navigate_url = "/portfolio"
        navigate_label = "Open Portfolio"

    # Studio Tips (general)
    elif any(w in lower for w in ["tips", "studio tips", "production tip"]):
        navigate_url = "/tips"
        navigate_label = "Open Studio Tips"

    # Stem Upload
    elif any(w in lower for w in ["upload", "stem", "file"]):
        navigate_url = "/stem-upload"
        navigate_label = "Open Stem Upload"

    # Invoices
    elif service in {"invoices", "drafts"} or any(w in lower for w in ["invoice", "invoices"]):
        navigate_url = "/dashboard?tab=invoices"
        navigate_label = "View Invoices"

    # CRM / Clients
    elif intent_name == "client_mgmt" or any(w in lower for w in ["client", "clients", "leads"]):
        navigate_url = "/dashboard?tab=crm"
        navigate_label = "View CRM"

    # Enquiries
    elif any(w in lower for w in ["enquir", "contact form"]):
        navigate_url = "/dashboard?tab=enquiries"
        navigate_label = "View Enquiries"

    # Financials
    elif intent_name == "financial" or any(w in lower for w in ["expense", "profit", "financial", "money"]):
        navigate_url = "/dashboard?tab=financial"
        navigate_label = "View Financials"

    # Get personalized greeting
    profile = user_profile.get_profile(profile_id) if profile_id != "default" else None
    greeting = get_greeting(profile, session.get("context", {})) if not service else ""

    legacy_response = {
        "answer": answer_text,
        "session_id": current_session_id,
        "intent": intent_name,
        "service": service,
        "navigate_url": navigate_url,
        "navigate_label": navigate_label,
        "suggestions": list(semantic_result.get("suggestions") or suggestions),
        "greeting": greeting,
        "route": str(semantic_result.get("route") or ""),
        "confidence": str(semantic_result.get("confidence") or "unknown"),
        "grounding": dict(semantic_result.get("grounding") or {}),
        "sources": list(semantic_result.get("sources") or ()),
        "metadata": dict(semantic_result.get("metadata") or {}),
        "requires_confirmation": bool(
            semantic_result.get("requires_confirmation", False)
        ),
        "confirmation_token": str(
            semantic_result.get("confirmation_token") or ""
        ),
    }
    if command_result.error is not None:
        return {
            **legacy_response,
            "schema_version": command_result.schema_version,
            "request_id": command_result.command_id,
            "correlation_id": command_result.correlation_id,
            "status": command_result.status.value,
            "error_code": command_result.error.code,
            "envelope": command_result.to_dict(),
        }

    assistant_response = assistant_response_for(legacy_response, session=session)
    final_result = result_for_response(command, assistant_response)
    last_turn_ts = session["turns"][-1]["timestamp"] if session.get("turns") else ""
    return {
        **legacy_response,
        "schema_version": final_result.schema_version,
        "request_id": final_result.command_id,
        "correlation_id": final_result.correlation_id,
        "status": final_result.status.value,
        "error_code": "",
        "requires_confirmation": assistant_response.requires_confirmation,
        "confirmation_token": assistant_response.confirmation_token,
        "envelope": final_result.to_dict(),
        "turn_id": last_turn_ts,
    }


def ask_stream(
    question: str,
    session_id: str = "",
    profile_id: str = "",
    request_id: str = "",
):
    """Run Thursday on a user question and yield stream events.

    Delegates to KENN streaming if the query has production QA intent.
    Otherwise, handles synchronously and yields the complete response.
    """
    from thursday.session_manager import get_or_create_session, update_context, add_turn, save_session
    from thursday.orchestrator import classify_request, normalize_request_text
    from thursday.personality import get_greeting
    from thursday.formatter import format_response
    from thursday.command_gateway import (
        assistant_response_for,
        command_for_text,
        result_for_response,
    )
    import thursday.user_profile as user_profile
    from kenn.core.chat import answer_payload_stream

    session = get_or_create_session(session_id)
    current_session_id = session["session_id"]

    if profile_id:
        update_context(session, {"profile_id": profile_id})
    profile_id = session.get("context", {}).get("profile_id", "default")

    mood = user_profile.detect_mood(question)
    if mood:
        user_profile.set_mood(mood, profile_id)
        session["context"]["_mood"] = mood

    normalized_question = normalize_request_text(question, profile_id)
    decision = classify_request(normalized_question, session)
    command = command_for_text(
        question,
        actor_id="dashboard.stream",
        correlation_id=request_id,
    )

    if decision.execution_target == "kenn_stream":
        accumulated_answer = ""
        kenn_metadata = {}
        thursday_history = []
        for turn in session.get("turns", []):
            role = "user" if turn.get("role") == "user" else "assistant"
            thursday_history.append({"role": role, "content": turn.get("text", "")})

        for chunk in answer_payload_stream(
            decision.resolved_text,
            limit=4,
            history=thursday_history,
            session_id=current_session_id,
        ):
            if chunk.get("event") == "token":
                token = chunk.get("token", "")
                accumulated_answer += token
                yield {
                    "event": "token",
                    "token": token,
                    "schema_version": command.schema_version,
                    "request_id": command.command_id,
                    "correlation_id": command.correlation_id,
                }
            elif chunk.get("event") == "metadata":
                kenn_metadata = dict(chunk.get("data") or {})

        # KENN emits metadata before streamed tokens. Persist and publish only
        # after the stream finishes so session memory contains the real answer.
        if not accumulated_answer:
            accumulated_answer = str(kenn_metadata.get("answer") or "").strip()
        formatted_answer = format_response(
            accumulated_answer,
            "KENN Knowledge Base",
            "kenn",
            session.get("context", {}),
        )
        add_turn(session, "user", question, "production_qa", "kenn", {})
        add_turn(session, "thursday", formatted_answer, "production_qa", "kenn", {})
        try:
            save_session(session)
        except Exception:
            logger.warning("save_session failed for session %s", session.get("session_id"), exc_info=True)

        suggestions = _suggestions_from_answer(accumulated_answer, question)
        profile_obj = user_profile.get_profile(profile_id) if profile_id != "default" else None
        greeting = get_greeting(profile_obj, session.get("context", {}))
        thursday_metadata = {
            **kenn_metadata,
            "answer": accumulated_answer,
            "session_id": current_session_id,
            "intent": "production_qa",
            "service": "kenn",
            "navigate_url": "http://127.0.0.1:8090" if "kenn" in question.lower() else None,
            "navigate_label": "Open KENN Chat" if "kenn" in question.lower() else None,
            "suggestions": suggestions,
            "greeting": greeting,
        }
        assistant_response = assistant_response_for(thursday_metadata, session=session)
        final_result = result_for_response(command, assistant_response)
        last_turn_ts = session["turns"][-1]["timestamp"] if session.get("turns") else ""
        thursday_metadata.update({
            "schema_version": final_result.schema_version,
            "request_id": final_result.command_id,
            "correlation_id": final_result.correlation_id,
            "status": final_result.status.value,
            "error_code": "",
            "requires_confirmation": assistant_response.requires_confirmation,
            "confirmation_token": assistant_response.confirmation_token,
            "envelope": final_result.to_dict(),
            "turn_id": last_turn_ts,
        })
        yield {"event": "metadata", "data": thursday_metadata}
        yield {
            "event": "done",
            "schema_version": final_result.schema_version,
            "request_id": final_result.command_id,
            "correlation_id": final_result.correlation_id,
        }
    else:
        response = ask(
            question,
            session_id=current_session_id,
            profile_id=profile_id,
            request_id=command.correlation_id,
        )
        yield {
            "event": "token",
            "token": response["answer"],
            "schema_version": response["schema_version"],
            "request_id": response["request_id"],
            "correlation_id": response["correlation_id"],
        }
        yield {"event": "metadata", "data": response}
        yield {
            "event": "done",
            "schema_version": response["schema_version"],
            "request_id": response["request_id"],
            "correlation_id": response["correlation_id"],
        }


def feedback(turn_id: str, rating: int, session_id: str = "") -> dict:
    """Record explicit feedback (thumbs up/down) for a prior response.

    Args:
        turn_id: The turn ID or turn timestamp string from the session.
        rating: +1 for thumbs up, -1 for thumbs down.
        session_id: The session the turn belongs to.

    Returns:
        dict with success status.
    """
    from thursday.feedback import record_feedback
    from thursday.session_manager import load_session

    session = load_session(session_id) if session_id else None

    # Try to find the service/intent from the turn
    service_id = ""
    intent_name = ""
    response_text = ""
    if session:
        for turn in session.get("turns", []):
            if turn.get("timestamp") == turn_id or turn.get("turn_id") == turn_id:
                if turn.get("role") == "thursday":
                    service_id = turn.get("service_used", "")
                    intent_name = turn.get("intent", "")
                    response_text = turn.get("text", "")
                break

    record_feedback(
        turn_id=turn_id,
        session_id=session_id,
        service_id=service_id,
        intent_name=intent_name,
        explicit_rating=rating,
        response_text=response_text,
    )

    return {"ok": True, "rating": rating}


def _suggestions_from_answer(answer: str, question: str) -> list[dict]:
    """Generate contextual navigation suggestions based on the answer."""
    suggestions = []
    lower = answer.lower() + " " + question.lower()

    if "kenn" in lower or "studio tips" in lower or "production" in lower:
        suggestions.append({"label": "Open KENN Chat", "url": "http://127.0.0.1:8090"})
    if "audiogen" in lower or "creative" in lower or "generate" in lower:
        suggestions.append({"label": "Open AudioGen Lab", "url": "/audiogen"})
    if "scan" in lower or "analy" in lower or "mix review" in lower:
        suggestions.append({"label": "Open Audio Analysis", "url": "/audio-analysis"})
    if "status" in lower or "business" in lower:
        suggestions.append({"label": "Open Dashboard", "url": "/dashboard"})
        suggestions.append({"label": "View Pipeline", "url": "/dashboard?tab=pipeline"})
    if "reminder" in lower or "due" in lower:
        suggestions.append({"label": "View Reminders", "url": "/dashboard?tab=reminders"})
    if "invoic" in lower:
        suggestions.append({"label": "View Invoices", "url": "/dashboard?tab=invoices"})
    if "client" in lower:
        suggestions.append({"label": "View CRM", "url": "/dashboard?tab=crm"})
    if "search" in lower or "find" in lower:
        suggestions.append({"label": "Search Records", "url": "/dashboard?tab=search"})
    if "expense" in lower or "spent" in lower or "profit" in lower:
        suggestions.append({"label": "View Financials", "url": "/dashboard?tab=financial"})

    if not suggestions:
        suggestions.append({"label": "Go to Hub", "url": "/hub"})

    return suggestions
