"""Tests for session_memory's AutoMix project linkage helpers."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "studio" / "kenn"))

from kenn.core import session_memory  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_session_db(tmp_path, monkeypatch):
    monkeypatch.setattr(session_memory, "DB_PATH", tmp_path / "kenn.db")
    yield


def test_get_remembered_project_is_empty_for_an_unknown_session():
    assert session_memory.get_remembered_automix_project("never-seen") == ""


def test_remember_then_get_round_trips():
    session_memory.remember_automix_project("s1", "proj-42")
    assert session_memory.get_remembered_automix_project("s1") == "proj-42"


def test_remember_overwrites_a_previous_project_for_the_same_session():
    session_memory.remember_automix_project("s1", "proj-1")
    session_memory.remember_automix_project("s1", "proj-2")
    assert session_memory.get_remembered_automix_project("s1") == "proj-2"


def test_remember_is_a_no_op_for_empty_session_id_or_project_id():
    session_memory.remember_automix_project("", "proj-1")
    session_memory.remember_automix_project("s1", "")
    assert session_memory.get_remembered_automix_project("s1") == ""


def test_different_sessions_do_not_share_project_state():
    session_memory.remember_automix_project("s1", "proj-1")
    session_memory.remember_automix_project("s2", "proj-2")
    assert session_memory.get_remembered_automix_project("s1") == "proj-1"
    assert session_memory.get_remembered_automix_project("s2") == "proj-2"


def test_get_pending_automix_jobs_is_empty_for_an_unknown_session():
    assert session_memory.get_pending_automix_jobs("never-seen") == []


def test_remember_pending_job_round_trips():
    session_memory.remember_pending_automix_job("s1", "job-1")
    assert session_memory.get_pending_automix_jobs("s1") == ["job-1"]


def test_remember_pending_job_accumulates_without_duplicating():
    session_memory.remember_pending_automix_job("s1", "job-1")
    session_memory.remember_pending_automix_job("s1", "job-2")
    session_memory.remember_pending_automix_job("s1", "job-1")
    assert session_memory.get_pending_automix_jobs("s1") == ["job-1", "job-2"]


def test_remember_pending_job_is_a_no_op_for_empty_session_id_or_job_id():
    session_memory.remember_pending_automix_job("", "job-1")
    session_memory.remember_pending_automix_job("s1", "")
    assert session_memory.get_pending_automix_jobs("s1") == []


def test_clear_pending_job_removes_only_that_job():
    session_memory.remember_pending_automix_job("s1", "job-1")
    session_memory.remember_pending_automix_job("s1", "job-2")
    session_memory.clear_pending_automix_job("s1", "job-1")
    assert session_memory.get_pending_automix_jobs("s1") == ["job-2"]


def test_clear_pending_job_is_a_no_op_when_job_not_present():
    session_memory.remember_pending_automix_job("s1", "job-1")
    session_memory.clear_pending_automix_job("s1", "job-does-not-exist")
    assert session_memory.get_pending_automix_jobs("s1") == ["job-1"]


def test_get_pending_checkpoint_is_none_for_an_unknown_session():
    assert session_memory.get_pending_checkpoint("never-seen") is None


def test_remember_then_get_checkpoint_round_trips():
    session_memory.remember_pending_checkpoint("s1", "the suggested EQ move")
    checkpoint = session_memory.get_pending_checkpoint("s1")
    assert checkpoint["description"] == "the suggested EQ move"
    assert "created_at" in checkpoint


def test_remember_checkpoint_overwrites_a_previous_one():
    session_memory.remember_pending_checkpoint("s1", "first change")
    session_memory.remember_pending_checkpoint("s1", "second change")
    assert session_memory.get_pending_checkpoint("s1")["description"] == "second change"


def test_clear_pending_checkpoint_removes_it():
    session_memory.remember_pending_checkpoint("s1", "the suggested EQ move")
    session_memory.clear_pending_checkpoint("s1")
    assert session_memory.get_pending_checkpoint("s1") is None


def test_remember_checkpoint_is_a_no_op_for_empty_session_id_or_description():
    session_memory.remember_pending_checkpoint("", "a change")
    session_memory.remember_pending_checkpoint("s1", "")
    assert session_memory.get_pending_checkpoint("s1") is None
