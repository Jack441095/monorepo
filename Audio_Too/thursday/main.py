#!/usr/bin/env python3
"""Thursday — Audio_Too's orchestration agent.

Usage:
    ./audio-too thursday "<your request>"
    ./audio-too thursday --session <session_id> "<your request>"
    ./audio-too thursday --new-session "<your request>"
    ./audio-too thursday --voice              (continuous listening mode)
    ./audio-too thursday --repl               (interactive chat, stays warm between turns)
    ./audio-too thursday --user <profile_id> "<your request>"
    ./audio-too thursday --diagnostics        (system health report)
    ./audio-too thursday plan-history "<query>"   (past plan traces, FTS-matched)
    ./agent thursday "<your request>"

Thursday routes natural language requests to the right agent or module.
Now with persistent session memory, intent classification, compound requests,
disambiguation, personality, user profile, and proactive alerts.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Add repo root to path so imports work
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "business" / "agents"))

# Load .env so action_policy / LLM config env vars are available
_env_file = ROOT / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

from thursday.orchestrator import handle, help_text
from thursday.session_manager import get_or_create_session, new_session, list_sessions
from thursday.diagnostics import check_all_systems, format_health_report
from thursday.command_gateway import command_for_text, execute_command


def execute_cli_request(text: str, session: dict):
    """Execute a CLI request through the shared command/result boundary."""
    command = command_for_text(text, actor_id="cli")
    return execute_command(command, session=session, handle_fn=handle)


def _run_repl(session: dict) -> int:
    """Interactive chat loop — one warm process, same session across turns.

    Each one-shot ``thursday "..."`` CLI call pays ~2s of import/model-load cost
    per message; this keeps that cost paid once so back-and-forth conversation
    doesn't lag. Type 'exit'/'quit' or Ctrl-C/Ctrl-D to leave.
    """
    print(f"Thursday — chatting (session {session['session_id']}). Type 'exit' to quit.\n")
    while True:
        try:
            text = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not text:
            continue
        if text.lower() in ("exit", "quit", "bye", "q"):
            print("Thursday: Talk soon.")
            return 0
        try:
            result = execute_cli_request(text, session)
        except Exception as e:  # noqa: BLE001 - keep the REPL alive on a bad turn
            print(f"Thursday: (error) {e}\n")
            continue
        if result.error is not None:
            print(f"Thursday: {result.error.message}\n")
            continue
        print(f"Thursday: {result.result['answer']}\n")


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(help_text())
        return 0

    if args[0].lower() == "plan-history":
        query_text = " ".join(args[1:]).strip()
        from thursday.plan_memory import list_plan_history, query_similar_plans
        history = query_similar_plans(query_text, limit=20) if query_text else list_plan_history()
        if not history:
            print("No past plan traces found.")
            return 0
        print(f"{'Plan ID':<10} | {'Created At':<22} | {'Status':<8} | {'Request/Plan'}")
        print("-" * 100)
        for trace in history:
            query_disp = trace["query"][:28] + ("..." if len(trace["query"]) > 28 else "")
            abstract_disp = trace["abstract"][:28] + ("..." if len(trace["abstract"]) > 28 else "")
            q_and_a = f"Q: {query_disp} / Plan: {abstract_disp}"
            print(f"{trace['plan_id'][:8]:<10} | {trace['created_at']:<22} | {trace['status']:<8} | {q_and_a}")
            if trace.get("lesson"):
                print(f"{'':<10} | {'':<22} | {'':<8} | Lesson: {trace['lesson']}")
        return 0

    # Parse flags
    session_id = None
    force_new_session = False
    list_all_sessions = False
    voice_mode = False
    repl_mode = False
    server_mode = False
    server_port = None
    watch_mode = False
    watch_dir = None
    run_briefing = False
    profile_id = None
    run_diagnostics = False
    text_parts = []

    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--session" and i + 1 < len(args):
            session_id = args[i + 1]
            i += 2
        elif arg == "--new-session":
            force_new_session = True
            i += 1
        elif arg == "--list-sessions":
            list_all_sessions = True
            i += 1
        elif arg == "--voice":
            voice_mode = True
            i += 1
        elif arg in ("--repl", "--chat"):
            repl_mode = True
            i += 1
        elif arg == "--server":
            server_mode = True
            i += 1
        elif arg == "--watch":
            watch_mode = True
            if i + 1 < len(args) and not args[i + 1].startswith("--"):
                watch_dir = args[i + 1]
                i += 2
            else:
                i += 1
        elif arg == "--briefing":
            run_briefing = True
            i += 1
        elif arg == "--port" and i + 1 < len(args):
            server_port = int(args[i + 1])
            i += 2
        elif arg == "--user" and i + 1 < len(args):
            profile_id = args[i + 1]
            i += 2
        elif arg == "--diagnostics" or arg == "--health":
            run_diagnostics = True
            i += 1
        else:
            text_parts.append(arg)
            i += 1

    text = " ".join(text_parts).strip() if text_parts else ""

    # Handle special commands
    if list_all_sessions:
        sessions = list_sessions()
        if not sessions:
            print("No sessions found.")
            return 0
        print(f"{'Session ID':<16} {'Created':<22} {'Updated':<22} {'Turns':<6}")
        print("-" * 66)
        for s in sessions:
            print(f"{s.get('session_id', '?'):<16} {str(s.get('created_at', ''))[:20]:<22} {str(s.get('updated_at', ''))[:20]:<22} {s.get('num_turns', 0):<6}")
        return 0

    if text.lower() in ("help", "-h", "--help", "?"):
        print(help_text())
        return 0

    # Diagnostics mode
    if run_diagnostics:
        health = check_all_systems()
        print(format_health_report(health))
        return 0

    # Daily briefing
    if run_briefing:
        from thursday.watcher import daily_briefing
        print(daily_briefing(speak=True))
        return 0

    # File watcher
    if watch_mode:
        from thursday.watcher import watch
        watch(directory=watch_dir)
        return 0

    # Server mode
    if server_mode:
        from thursday.server import start
        from thursday.server import DEFAULT_PORT
        port = server_port or DEFAULT_PORT
        start(port=port)
        return 0

    # REPL / chat mode — one warm process, one session, loop over stdin.
    if repl_mode:
        session = get_or_create_session(session_id) if not force_new_session else new_session()
        return _run_repl(session)

    # Voice mode
    if voice_mode:
        from thursday.voice import continuous_mode
        print("🔊 Thursday voice mode activated. Say 'Thursday' followed by your request.")
        print("Press Ctrl+C to exit.")
        continuous_mode(handle, wake_word="thursday")
        return 0

    # Load or create session
    if force_new_session:
        session = new_session()
        print(f"(New session: {session['session_id']})")
    else:
        session = get_or_create_session(session_id)
        if session_id is None:
            print(f"(Session: {session['session_id']})")

    # If a user profile was specified, set it in the session context
    if profile_id:
        from thursday.session_manager import update_context
        update_context(session, {"profile_id": profile_id})
        from thursday.user_profile import get_profile
        profile = get_profile(profile_id)
        user_name = profile.get("user_name", profile_id)
        print(f"(User: {user_name})")

    # Route the request
    result = execute_cli_request(text, session)
    if result.error is not None:
        print(result.error.message, file=sys.stderr)
        return 1
    print(result.result["answer"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
