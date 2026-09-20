"""Tests for stem_separation_tokens.py -- mirrors test coverage style of
the existing mix_report_tokens/podcast_report_tokens signed-link schemes."""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server" / "app"))

import stem_separation_tokens as tokens  # noqa: E402


def test_round_trip_token_verifies():
    token = tokens.make_job_token("job-123")
    assert tokens.verify_job_token("job-123", token) is True


def test_token_does_not_verify_for_a_different_job_id():
    token = tokens.make_job_token("job-123")
    assert tokens.verify_job_token("job-456", token) is False


def test_tampered_token_is_rejected():
    token = tokens.make_job_token("job-123")
    tampered = token[:-2] + ("aa" if token[-2:] != "aa" else "bb")
    assert tokens.verify_job_token("job-123", tampered) is False


def test_expired_token_is_rejected(monkeypatch):
    token = tokens.make_job_token("job-123", ttl_seconds=1)
    future = time.time() + 10
    monkeypatch.setattr(time, "time", lambda: future)
    assert tokens.verify_job_token("job-123", token) is False


def test_empty_token_is_rejected():
    assert tokens.verify_job_token("job-123", "") is False


def test_garbage_token_is_rejected_not_raised():
    assert tokens.verify_job_token("job-123", "not-a-real-token!!") is False
