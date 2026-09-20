"""Tests for public studio tips API layer."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

WEBSITE = Path(__file__).resolve().parent.parent / "server" / "app"
sys.path.insert(0, str(WEBSITE))

from studio_tips import ask_public, public_catalog  # noqa: E402


def test_public_catalog() -> None:
    data = public_catalog()
    assert data["retrieval_only"] is True
    assert len(data["suggested_questions"]) >= 4


def test_ask_public_sidechain() -> None:
    result = ask_public("how do I sidechain bass to the kick")
    assert result["retrieval_only"] is True
    assert result["llm_enhanced"] is False
    assert result["confidence"] in {"medium", "high"}
    assert "sidechain" in result["answer"].lower()
    assert all(set(source) <= {"label", "kind"} for source in result["sources"])


def test_public_chat_cannot_trigger_audio_generation(monkeypatch) -> None:
    import studio_tips

    monkeypatch.setattr(
        studio_tips.ableton_bridge.audiogen_bridge,
        "generate_for_kenn",
        lambda *_args, **_kwargs: pytest.fail("public chat attempted generation"),
    )
    result = studio_tips.ask_public("generate a joyful chorus")
    assert result["conversation_only"] is True
    assert "authenticated Creative Lab" in result["answer"]
