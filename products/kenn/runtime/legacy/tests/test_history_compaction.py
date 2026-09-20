from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT / "studio" / "kenn") not in sys.path:
    sys.path.insert(0, str(ROOT / "studio" / "kenn"))

import pytest
from unittest.mock import MagicMock, patch
from kenn.core.chat_answer import compact_history

def test_compact_history_under_limit() -> None:
    history = [
        {"role": "user", "content": "How do I fix the high end?"},
        {"role": "assistant", "content": "Use a high shelf EQ cut."}
    ]
    # Under limit (e.g. 8 turns), should be returned unchanged
    result = compact_history(history, limit=8)
    assert result == history

def test_compact_history_none_or_empty() -> None:
    assert compact_history(None) is None
    assert compact_history([]) == []

@patch("nite_core.model_runtime.DEFAULT_LLM.generate")
def test_compact_history_over_limit(mock_generate) -> None:
    # Set up mock response for LLM generate
    mock_response = MagicMock()
    mock_response.content = "Jack asked about vocal EQ and KENN recommended a cut at 2.5kHz."
    mock_generate.return_value = mock_response

    # Create history with 10 turns (5 turns of user/assistant exchange)
    history = [
        {"role": "user", "content": "Hello KENN"},
        {"role": "assistant", "content": "Hello Jack"},
        {"role": "user", "content": "I have vocal harshness"},
        {"role": "assistant", "content": "Cut 2.5kHz"},
        {"role": "user", "content": "What about the low shelf?"},
        {"role": "assistant", "content": "Boost 100Hz"},
        # Last 4 turns
        {"role": "user", "content": "How about compression?"},
        {"role": "assistant", "content": "Use a 4:1 ratio"},
        {"role": "user", "content": "Is that too fast?"},
        {"role": "assistant", "content": "No, it is fine"}
    ]

    # Compact history with a limit of 6
    result = compact_history(history, limit=6)

    # 1. Verification of length (1 summary + 4 last turns = 5 turns)
    assert len(result) == 5
    
    # 2. Verification that the summary is injected as the first message
    assert result[0]["role"] == "user"
    assert "Prior context summary:" in result[0]["content"]
    assert "vocal EQ" in result[0]["content"]

    # 3. Verification that the last 4 turns are untouched
    assert result[1:] == history[-4:]
    
    # 4. Assert LLM generate was called with formatted older turns
    mock_generate.assert_called_once()
    prompt = mock_generate.call_args[0][0][0]["content"]
    assert "Jack: Hello KENN" in prompt
    assert "KENN: Hello Jack" in prompt
    assert "Jack: I have vocal harshness" in prompt
    assert "KENN: Cut 2.5kHz" in prompt
    # The last 4 turns should NOT be in the prompt to the LLM for summarization
    assert "How about compression?" not in prompt
