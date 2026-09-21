from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path


from kenn.core.lm_identity import APP_NAME, APP_TAGLINE

from kenn.core.chat_constants import (
    CHAT_DIR,
    SYSTEM_NOTE,
)

from kenn.core.chat_answer import (
    answer_payload,
)


def save_chat(question: str, answer: str) -> Path:
    CHAT_DIR.mkdir(parents=True, exist_ok=True)
    path = CHAT_DIR / f"{datetime.now().strftime('%Y-%m-%d')}.md"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"## {datetime.now().strftime('%H:%M:%S')}\n\n")
        handle.write(f"Q: {question}\n\n{answer}\n\n")
    return path


import json
import urllib.request
import urllib.error
from kenn.core.chat_answer import answer_payload_stream


def _query_companion_if_online(
    question: str,
    limit: int = 5,
    history: list | None = None,
    session_id: str = "",
) -> dict | None:
    """Connect to the running local companion daemon for instant sub-millisecond response."""
    try:
        req_data = json.dumps({
            "question": question,
            "limit": limit,
            "history": history or [],
            "session_id": session_id,
            "stream": False,
        }).encode("utf-8")
        req = urllib.request.Request(
            "http://127.0.0.1:8090/api/ask",
            data=req_data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode("utf-8"))
    except Exception:
        pass
    return None


def _stream_query(
    question: str,
    limit: int = 5,
    history: list | None = None,
    session_id: str = "",
) -> tuple[str, dict]:
    """Stream response tokens to stdout in real-time, returning (full_answer, metadata)."""
    # 1. Try companion HTTP SSE stream
    try:
        req_data = json.dumps({
            "question": question,
            "limit": limit,
            "history": history or [],
            "session_id": session_id,
            "stream": True,
        }).encode("utf-8")
        req = urllib.request.Request(
            "http://127.0.0.1:8090/api/ask",
            data=req_data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            if resp.status == 200:
                accumulated = []
                meta = {}
                for line in resp:
                    line_str = line.decode("utf-8").strip()
                    if not line_str or not line_str.startswith("data: "):
                        continue
                    payload = json.loads(line_str[6:])
                    event = payload.get("event")
                    if event == "token":
                        tok = payload.get("token", "")
                        sys.stdout.write(tok)
                        sys.stdout.flush()
                        accumulated.append(tok)
                    elif event == "metadata":
                        meta = payload.get("data", {})
                    elif event == "done":
                        break
                ans = "".join(accumulated) or meta.get("answer", "")
                return ans, meta
    except Exception:
        pass

    # 2. Fallback to in-process stream
    try:
        accumulated = []
        meta = {}
        for chunk in answer_payload_stream(question, limit=limit, history=history or [], session_id=session_id):
            event = chunk.get("event")
            if event == "token":
                tok = chunk.get("token", "")
                sys.stdout.write(tok)
                sys.stdout.flush()
                accumulated.append(tok)
            elif event == "metadata":
                meta = chunk.get("data", {})
            elif event == "done":
                break
        ans = "".join(accumulated) or meta.get("answer", "")
        return ans, meta
    except Exception:
        # Non-streaming fallback
        payload = answer_payload(question, limit=limit, history=history, session_id=session_id)
        ans = payload.get("answer", "")
        sys.stdout.write(ans)
        sys.stdout.flush()
        return ans, payload


def ask_once(
    question: str,
    limit: int = 5,
    save: bool = False,
    history: list | None = None,
    session_id: str = "",
    stream: bool = False,
) -> str:
    if stream:
        ans, _ = _stream_query(question, limit=limit, history=history, session_id=session_id)
        print()
    else:
        payload = _query_companion_if_online(question, limit=limit, history=history, session_id=session_id)
        if payload is None:
            payload = answer_payload(question, limit=limit, history=history, session_id=session_id)
        ans = payload.get("answer", "")
    if save:
        path = save_chat(question, ans)
        ans += f"\n\nSaved chat: {path}"
    return ans


def interactive(limit: int = 5, save: bool = False) -> int:
    session_history: list[dict] = []
    from kenn.llm.llm_rewrite import status_message

    print(f"{APP_NAME} — {APP_TAGLINE}")
    print(SYSTEM_NOTE)
    print(status_message())
    print("Type 'quit' to exit.\n")
    while True:
        try:
            question = input("Ableton> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            return 0
        if question.lower() in {"q", "quit", "exit"}:
            return 0
        if not question:
            continue
        print()
        ans, _ = _stream_query(question, limit=limit, history=session_history)
        print("\n")
        session_history.append({"role": "user", "content": question})
        session_history.append({"role": "assistant", "content": ans})
        if save:
            save_chat(question, ans)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ask questions against the local Ableton PDF knowledge base"
    )
    parser.add_argument("question", nargs="*", help="Question to ask. Omit for interactive chat.")
    parser.add_argument("--limit", type=int, default=5, help="Number of source chunks to retrieve")
    parser.add_argument("--save", action="store_true", help="Save Q&A to chats/YYYY-MM-DD.md")
    parser.add_argument("--session-id", default="", help="Reuse a named session instead of creating one")
    args = parser.parse_args()

    question = " ".join(args.question).strip()
    if question:
        print(ask_once(question, limit=args.limit, save=args.save, session_id=args.session_id))
        return 0
    return interactive(limit=args.limit, save=args.save)


if __name__ == "__main__":
    raise SystemExit(main())
