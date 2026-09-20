#!/usr/bin/env python3
"""Simulation of Task 1: Multi-turn interactive CLI session."""

from __future__ import annotations
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "apps", "backend", "src")))

from kenn.core.chat_answer import answer_payload
from kenn.core.lm_identity import APP_NAME, APP_TAGLINE
from kenn.core.chat_constants import SYSTEM_NOTE
from kenn.llm.llm_rewrite import status_message

def run_interactive_simulation() -> None:
    print(f"=== {APP_NAME} — {APP_TAGLINE} ===")
    print(SYSTEM_NOTE)
    print(status_message())
    print("\nStarting 5-turn interactive session...\n")

    turns = [
        "How do I set up sidechain compression on bass in Ableton Live?",
        "What frequency is best to cut for mud in electric guitar?",
        "Show my session and tracks",
        "Mute track 1",
        "Hey KENN, ready to mix?",
    ]

    session_history: list[dict] = []

    for i, question in enumerate(turns, 1):
        print(f"\n--- [Turn {i}/5] User: \"{question}\" ---")
        t0 = time.perf_counter()
        payload = answer_payload(question, limit=4, history=session_history)
        dt_ms = (time.perf_counter() - t0) * 1000
        answer = payload["answer"]
        route = payload.get("route", "unknown")
        confidence = payload.get("confidence", "unknown")


        print(f"KENN ({dt_ms:.1f}ms | Route: {route} | Confidence: {confidence}):")
        lines = [l for l in answer.strip().split("\n") if l.strip()]
        for l in lines[:6]:
            print(f"  {l}")
        if len(lines) > 6:
            print(f"  ... [{len(lines)-6} more lines]")

        session_history.append({"role": "user", "content": question})
        session_history.append({"role": "assistant", "content": answer})

    print("\n=== Task 1 Interactive Simulation Complete ===")

if __name__ == "__main__":
    run_interactive_simulation()
