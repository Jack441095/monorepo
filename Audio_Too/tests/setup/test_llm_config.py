#!/usr/bin/env python3
"""Test optional LLM rewrite settings (OpenAI-compatible or Ollama)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
ABLETON = ROOT / "studio" / "kenn" / "kenn"
sys.path.insert(0, str(ABLETON.parent))

from kenn.llm.llm_rewrite import chat_completion, config, is_enabled, status_message  # noqa: E402


def main() -> int:
    print(status_message())
    cfg = config()
    print(f"Provider: {cfg['provider']}")
    print(f"Model: {cfg['model']}")
    print(f"Base URL: {cfg['base_url']}")
    if not is_enabled():
        print("\nEnable in .env:")
        print("  AUDIO_TOO_LLM_ENABLED=1")
        print("  AUDIO_TOO_LLM_API_KEY=sk-...   # or use Ollama below")
        print("Or local Ollama:")
        print("  AUDIO_TOO_LLM_ENABLED=1")
        print("  AUDIO_TOO_LLM_PROVIDER=ollama")
        print("  AUDIO_TOO_LLM_MODEL=llama3.2")
        return 1
    try:
        reply = chat_completion(
            [
                {"role": "system", "content": "Reply in one short sentence."},
                {"role": "user", "content": "Say OK if you can hear me."},
            ]
        )
        print(f"\nLLM test reply: {reply[:200]}")
        print("\nLLM connection OK. Restart ./start.sh and ask a question on :8090.")
        return 0
    except Exception as exc:
        print(f"\nLLM test failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
