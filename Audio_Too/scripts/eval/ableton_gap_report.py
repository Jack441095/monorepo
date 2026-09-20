#!/usr/bin/env python3
"""Report retrieval confidence for a set of questions — find knowledge gaps."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
ABLETON = ROOT / "studio" / "kenn" / "kenn"

# Edit this list as you discover weak answers in real use.
PROBE_QUESTIONS = [
    "how do I use compressor on vocals",
    "how do I saturate sub bass",
    "clip automation in session view",
    "ableton cpu overload",
    "operator fm bass sound design",
    "arrangement view shortcuts",
    "how do I freeze and flatten",
    "podcast noise reduction",
    "sidechain bass to kick",
    "what LUFS for streaming",
    "how do I use return tracks for delay",
    "midi quantization groove pool",
    "export mp3 for client preview",
]


def main() -> int:
    # See the matching note in ableton_benchmark.py: without ROOT itself on
    # sys.path, answer_payload()'s embedder silently falls back to BM25-only.
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ABLETON.parent))
    from kenn.core.chat import answer_payload  # noqa: E402

    low = 0
    print("Audio Tips LLM — gap report\n")
    for question in PROBE_QUESTIONS:
        payload = answer_payload(question)
        confidence = payload.get("confidence", "low")
        sources = payload.get("sources") or []
        top = sources[0]["label"] if sources else "none"
        if confidence == "low":
            low += 1
            flag = "LOW "
        else:
            flag = "ok  "
        print(f"{flag} [{confidence:6}] {question}")
        print(f"       top: {top}")

    print(f"\n{low} low-confidence of {len(PROBE_QUESTIONS)} probes.")
    if low:
        print("Next: add/approve a note, ./ableton build, re-run this script and ./audio-too eval")
        return 1
    print("All probes returned medium or high confidence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
