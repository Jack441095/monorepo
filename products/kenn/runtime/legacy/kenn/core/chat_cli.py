from __future__ import annotations

import argparse
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


def ask_once(
    question: str,
    limit: int = 5,
    save: bool = False,
    history: list | None = None,
    session_id: str = "",
) -> str:
    payload = answer_payload(question, limit=limit, history=history, session_id=session_id)
    answer = payload["answer"]
    if save:
        path = save_chat(question, answer)
        answer += f"\n\nSaved chat: {path}"
    return answer


def interactive(limit: int = 5, save: bool = False) -> int:
    session_history: list[dict] = []
    from kenn.llm.llm_rewrite import status_message

    print(f"{APP_NAME} — {APP_TAGLINE}")
    print(SYSTEM_NOTE)
    print(status_message())
    print("Type 'quit' to exit.\n")
    while True:
        question = input("Ableton> ").strip()
        if question.lower() in {"q", "quit", "exit"}:
            return 0
        if not question:
            continue
        payload = answer_payload(question, limit=limit, history=session_history)
        answer = payload["answer"]
        print("\n" + answer + "\n")
        session_history.append({"role": "user", "content": question})
        session_history.append({"role": "assistant", "content": answer})
        if save:
            save_chat(question, answer)


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
