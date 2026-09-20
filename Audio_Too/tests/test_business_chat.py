"""Tests for public business FAQ answers."""

from __future__ import annotations

import sys
from pathlib import Path

WEBSITE = Path(__file__).resolve().parent.parent / "server" / "app"
sys.path.insert(0, str(WEBSITE))

from business_chat import answer_question, public_catalog, validate_question  # noqa: E402


def test_mixing_price_question() -> None:
    result = answer_question("How much does mixing cost?")
    assert result["confidence"] in {"medium", "high"}
    assert "mix" in result["answer"].lower()
    assert "£" in result["answer"]
    assert result["disclaimer"]


def test_stems_faq() -> None:
    result = answer_question("How should I send stems for a mix?")
    assert "stem" in result["answer"].lower() or "wav" in result["answer"].lower()
    assert result["sources"]


def test_unknown_question_low_confidence() -> None:
    result = answer_question("xyzzy plugh")
    assert result["confidence"] == "low"
    assert "enquiry" in result["answer"].lower()


def test_validate_question_length() -> None:
    assert validate_question({"question": "mix price?"}) == "mix price?"


def test_catalog_has_offerings() -> None:
    catalog = public_catalog()
    assert catalog["ok"] is True
    assert len(catalog["offerings"]) >= 4
    assert catalog["suggested_questions"]
