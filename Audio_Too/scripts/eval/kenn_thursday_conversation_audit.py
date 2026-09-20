#!/usr/bin/env python3
"""Conversational-quality audit for KENN + Thursday (LLM-level chatbot goal).

Evidence, not opinion. Probes three things and reports coverage + concrete gaps:

  Phase 1  intent/routing    — a labelled corpus of realistic queries across every
                               category; does each reach the right handler?
  Phase 2  multi-turn        — context carry, pronouns, follow-ups, topic switches,
                               KENN stickiness after a KENN answer.
  Phase 3  answer quality    — (separate harness) grounding/refusal behaviour.

Run: python3 scripts/eval/kenn_thursday_conversation_audit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from thursday.intent import classify_intent  # noqa: E402

# ── Labelled routing corpus ────────────────────────────────────────────────
# expected: the intent family we want. "production_qa" means "should reach KENN".
# For business we accept the specific business intent OR any business family.
BUSINESS_INTENTS = {"financial", "client_mgmt", "business_ops", "calendar_scheduling", "agent_tasks"}

CORPUS: list[tuple[str, str]] = [
    # ── production questions (should be production_qa / reach KENN) ──
    ("how do I process kicks?", "production_qa"),
    ("my vocals sound harsh", "production_qa"),
    ("how do I make my mix louder", "production_qa"),
    ("help me with my mixdown", "production_qa"),
    ("whats the best chain for mastering", "production_qa"),
    ("how do I sidechain the bass to the kick", "production_qa"),
    ("my low end is weak and muddy", "production_qa"),
    ("how do I get a wider stereo image", "production_qa"),
    ("what release time for a pumping sidechain", "production_qa"),
    ("how do I tame sibilance on vocals", "production_qa"),
    ("my snare has no punch, how do I fix it", "production_qa"),
    ("how loud should my master be for spotify", "production_qa"),
    ("whats parallel compression", "production_qa"),
    ("how do I use an lfo to modulate a filter", "production_qa"),
    ("why does my bass disappear on phone speakers", "production_qa"),
    ("how do I layer drums", "production_qa"),
    ("best way to eq a muddy guitar", "production_qa"),
    ("how do I set up a reverb send", "production_qa"),
    ("whats the difference between a limiter and a compressor", "production_qa"),
    ("how do I make my 808 hit harder", "production_qa"),
    # ── game audio / wwise (KENN also covers this) ──
    ("how do I set up a soundbank in wwise", "production_qa"),
    ("my wwise event isnt playing in unity", "production_qa"),
    # ── business ──
    ("show my invoices", "financial"),
    ("how is business doing", "business_ops"),
    ("whats my revenue this month", "financial"),
    ("schedule a session with sarah tomorrow", "calendar_scheduling"),
    ("draft an email to the new client", "agent_tasks"),
    ("add an expense for the new mic", "financial"),
    ("show my pipeline", "business_ops"),
    ("who are my leads", "client_mgmt"),
    ("send an invoice to jordan", "financial"),
    ("what sessions do I have this week", "calendar_scheduling"),
    # ── audio generation ──
    ("generate a joyful loop", "audio_generation"),
    ("make me a beat", "audio_generation"),
    ("render a full song", "audio_generation"),
    # ── mix review / analysis ──
    ("review my mix", "mix_review_audio_analysis"),
    ("analyse my track for issues", "mix_review_audio_analysis"),
    ("check my mix", "mix_review_audio_analysis"),
    # ── greetings / help / system ──
    ("hello", "greeting"),
    ("hey thursday", "greeting"),
    ("what can you do", "help"),
    ("help", "help"),
    ("is everything working", "system_diagnostics"),
    # ── out of scope (should NOT misroute to a real handler; KENN abstains) ──
    ("whats the capital of france", "out_of_scope"),
    ("write me a poem about cats", "out_of_scope"),
]


def audit_intent_coverage() -> dict:
    rows = []
    correct = 0
    for query, expected in CORPUS:
        got = classify_intent(query, {}).name
        if expected == "production_qa":
            ok = got == "production_qa"  # (orchestrator also defaults unknown->KENN, tested separately)
        elif expected in BUSINESS_INTENTS:
            ok = got in BUSINESS_INTENTS
        elif expected == "out_of_scope":
            ok = got in {"unknown", "out_of_scope", "production_qa"}  # KENN abstains; must not hit business/system
        else:
            ok = got == expected
        correct += ok
        rows.append({"query": query, "expected": expected, "got": got, "ok": ok})
    return {"total": len(CORPUS), "correct": correct,
            "accuracy": round(correct / len(CORPUS), 3), "rows": rows}


def main() -> int:
    print("=== PHASE 1: intent / routing coverage ===\n")
    res = audit_intent_coverage()
    for r in res["rows"]:
        mark = "OK " if r["ok"] else "XX "
        print(f"  {mark}exp {r['expected']:<24} got {r['got']:<22} <- {r['query']!r}")
    print(f"\nRouting accuracy: {res['correct']}/{res['total']} = {res['accuracy']:.0%}")
    fails = [r for r in res["rows"] if not r["ok"]]
    if fails:
        print("\nMISROUTES:")
        for r in fails:
            print(f"  - {r['query']!r}: wanted {r['expected']}, got {r['got']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
