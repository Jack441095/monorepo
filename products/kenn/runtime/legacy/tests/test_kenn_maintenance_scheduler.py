"""Tests for studio/kenn/kenn/knowledge/maintenance_scheduler.py — Stage G
(docs/AUDIO_MVP_MASTER_PLAN.md) autonomous KENN knowledge-base maintenance.

The most important test in this file is
test_autonomous_path_never_calls_gated_operations: it asserts that running
the full autonomous scheduler never invokes resolve_contradiction(),
_deprecate_note(), approve_suggested_note(), or any trust-score write —
exactly the operations the plan doc's Stage G explicitly keeps human-gated.
"""

from __future__ import annotations

import sqlite3
import tempfile
import uuid
from pathlib import Path

import pytest

from kenn.knowledge.reasoning import init_db, save_reasoning_trace
from kenn.knowledge import contradictions as contradictions_mod
from kenn.knowledge import maintenance_scheduler as sched


@pytest.fixture
def temp_env(monkeypatch):
    """Isolate KENN's sqlite DB and notes directory in a temp dir, and give
    gap-clustering nothing to chew on so G2 is a fast, deterministic no-op
    unless a test explicitly wants otherwise."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "kenn.db"
        notes_dir = Path(tmpdir) / "notes"
        notes_dir.mkdir()
        monkeypatch.setenv("KENN_DB_PATH", str(db_path))
        monkeypatch.setenv("KENN_CHATS_DIR", tmpdir)
        yield db_path, notes_dir


def test_maintenance_runs_table_initializes(temp_env):
    sched.init_maintenance_db()
    db_path, _ = temp_env
    conn = sqlite3.connect(str(db_path))
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    assert "knowledge_maintenance_runs" in tables


def test_g1_contradiction_scan_writes_receipt_and_detection_rows(temp_env):
    """G1: scan_for_contradictions() + propose_maintenance() should run,
    write detection rows to knowledge_contradictions, and produce a durable
    receipt in knowledge_maintenance_runs."""
    _, notes_dir = temp_env

    note_a = (
            "# Mix Bus Glue\n\nType: Note\nTags: compression, glue\nStatus: Approved\n"
            "Contradiction-Key: mix-bus-threshold\n\n"
        "Set the Glue Compressor threshold to -6 dB."
    )
    note_b = (
            "# Light Bus Comp\n\nType: Note\nTags: compression, glue\nStatus: Approved\n"
            "Contradiction-Key: mix-bus-threshold\n\n"
        "Set the compressor threshold to -12 dB."
    )
    (notes_dir / "note_a.md").write_text(note_a, encoding="utf-8")
    (notes_dir / "note_b.md").write_text(note_b, encoding="utf-8")

    result = sched.run_contradiction_scan_job(notes_dir=notes_dir, force=True)

    assert result["ok"] is True
    assert result["contradictions_detected"] == 1

    from kenn.knowledge.contradictions import list_contradictions
    assert len(list_contradictions()) == 1

    runs = sched.list_maintenance_runs()
    assert any(r["job"] == sched.JOB_G1 and r["status"] == "ok" for r in runs)


def test_rate_cap_skips_second_run_within_interval(temp_env):
    """The rate cap is the documented kill-switch-adjacent safeguard: a
    second run within the interval must be skipped (still receipted), and
    force=True must bypass it."""
    _, notes_dir = temp_env

    first = sched.run_contradiction_scan_job(notes_dir=notes_dir, force=True)
    assert first["ok"] is True
    assert first.get("skipped", False) is False

    second = sched.run_contradiction_scan_job(notes_dir=notes_dir, force=False)
    assert second["ok"] is True
    assert second["skipped"] is True
    assert second["reason"] == "rate_cap"

    forced = sched.run_contradiction_scan_job(notes_dir=notes_dir, force=True)
    assert forced["ok"] is True
    assert forced.get("skipped", False) is False

    runs = sched.list_maintenance_runs()
    statuses = [r["status"] for r in runs if r["job"] == sched.JOB_G1]
    assert statuses.count("skipped") == 1
    assert statuses.count("ok") == 2


def test_g2_gap_clustering_only_writes_pending_drafts(temp_env, monkeypatch):
    """G2 must never write anything except a 'pending' suggested_notes row —
    it must not touch the canonical notes directory at all."""
    _, notes_dir = temp_env

    def fake_run_clustering() -> int:
        return 3

    monkeypatch.setattr(
        "kenn.adaptive.gap_clustering.run_clustering", fake_run_clustering
    )

    result = sched.run_gap_clustering_job(force=True)
    assert result["ok"] is True
    assert result["suggested_notes_drafted"] == 3

    # Canonical notes dir must remain untouched by the autonomous job.
    assert list(notes_dir.glob("*.md")) == []

    runs = sched.list_maintenance_runs()
    assert any(r["job"] == sched.JOB_G2 and r["status"] == "ok" for r in runs)


def test_g3_retrospective_sweep_is_log_only_and_finds_cross_trace_mismatch(temp_env):
    """G3 must detect a cross-trace measurement mismatch, write it to
    knowledge_contradictions (the same table G1 uses — no new review
    surface), and must never alter the stored reasoning traces themselves."""
    init_db()
    trace_a_id = save_reasoning_trace(
        query="What threshold for vocal compressor?",
        route="production",
        evidence_ids=[],
        conclusion="Use a -6 dB threshold.",
        confidence="high",
        tags=["vocals"],
        trace_id=str(uuid.uuid4()),
    )
    trace_b_id = save_reasoning_trace(
        query="What threshold for vocal compressor take two?",
        route="production",
        evidence_ids=[],
        conclusion="Use a -12 dB threshold.",
        confidence="high",
        tags=["vocals"],
        trace_id=str(uuid.uuid4()),
    )

    from kenn.knowledge.reasoning import get_reasoning_trace
    before_a = dict(get_reasoning_trace(trace_a_id))
    before_b = dict(get_reasoning_trace(trace_b_id))

    result = sched.run_retrospective_critique_job(force=True)

    assert result["ok"] is True
    assert result["cross_trace_contradictions_found"] >= 1

    from kenn.knowledge.contradictions import list_contradictions
    found_types = [c["type"] for c in list_contradictions()]
    assert "cross_trace_measurement_mismatch" in found_types

    after_a = dict(get_reasoning_trace(trace_a_id))
    after_b = dict(get_reasoning_trace(trace_b_id))
    assert after_a == before_a, "G3 must never mutate a stored reasoning trace"
    assert after_b == before_b, "G3 must never mutate a stored reasoning trace"


def test_run_scheduled_maintenance_runs_all_three_jobs(temp_env, monkeypatch):
    _, notes_dir = temp_env
    monkeypatch.setattr(
        "kenn.adaptive.gap_clustering.run_clustering", lambda: 0
    )
    # notes_dir passed via chat_constants.NOTES_DIR default resolution is a
    # real repo path; point it at the isolated temp dir for this test.
    from kenn.core import chat_constants
    monkeypatch.setattr(chat_constants, "NOTES_DIR", notes_dir)

    result = sched.run_scheduled_maintenance(force=True)
    assert result["ok"] is True
    assert set(result.keys()) >= {"ok", sched.JOB_G1, sched.JOB_G2, sched.JOB_G3}

    runs = sched.list_maintenance_runs()
    jobs_ran = {r["job"] for r in runs}
    assert jobs_ran == {sched.JOB_G1, sched.JOB_G2, sched.JOB_G3}


def test_autonomous_path_never_calls_gated_operations(temp_env, monkeypatch):
    """The most important test in this file.

    docs/AUDIO_MVP_MASTER_PLAN.md Stage G is explicit that resolution/
    approval/trust-score-writing must NEVER become autonomous, no matter how
    safe the detection logic is. This test runs the full autonomous
    scheduler end to end and asserts that resolve_contradiction(),
    _deprecate_note(), approve_suggested_note(), and every trust-score write
    function are never invoked.
    """
    _, notes_dir = temp_env

    calls: list[str] = []

    def _forbidden(name):
        def _raise(*args, **kwargs):
            calls.append(name)
            raise AssertionError(f"gated operation '{name}' must never be called by the autonomous path")
        return _raise

    # Patch every gated operation at its source module so any import path
    # (direct, via kenn.knowledge, or via business/app) hits the guard.
    monkeypatch.setattr(
        contradictions_mod, "resolve_contradiction", _forbidden("resolve_contradiction")
    )
    monkeypatch.setattr(
        contradictions_mod, "_deprecate_note", _forbidden("_deprecate_note")
    )

    from server.app import suggested_notes_ops  # noqa: E402
    monkeypatch.setattr(
        suggested_notes_ops, "approve_suggested_note", _forbidden("approve_suggested_note")
    )

    from kenn.knowledge import trust_scores as trust_scores_mod
    monkeypatch.setattr(
        trust_scores_mod, "record_correction", _forbidden("record_correction")
    )
    monkeypatch.setattr(
        trust_scores_mod, "set_source_trust", _forbidden("set_source_trust")
    )

    from kenn.knowledge import reflection as reflection_mod
    monkeypatch.setattr(
        reflection_mod, "ingest_correction", _forbidden("ingest_correction")
    )

    from kenn.core import chat_constants
    monkeypatch.setattr(chat_constants, "NOTES_DIR", notes_dir)

    # Give G2 something small and deterministic to do without needing a
    # real embedder/DB fixture, so this test stays fast and focused on the
    # gating behavior rather than clustering internals.
    monkeypatch.setattr("kenn.adaptive.gap_clustering.run_clustering", lambda: 1)

    # Seed a real contradiction and a real cross-trace mismatch so G1/G3
    # have genuine work to do -- if any gated function were reachable from
    # this path, this is exactly the scenario that would trigger it.
    (notes_dir / "note_a.md").write_text(
            "# A\n\nType: Note\nTags: compression, glue\nStatus: Approved\n"
            "Contradiction-Key: mix-bus-threshold\n\n"
        "Set threshold to -6 dB.",
        encoding="utf-8",
    )
    (notes_dir / "note_b.md").write_text(
            "# B\n\nType: Note\nTags: compression, glue\nStatus: Approved\n"
            "Contradiction-Key: mix-bus-threshold\n\n"
        "Set threshold to -12 dB.",
        encoding="utf-8",
    )
    init_db()
    save_reasoning_trace(
        query="threshold?", route="production", evidence_ids=[],
        conclusion="Use -6 dB.", confidence="high", tags=["vocals"],
        trace_id=str(uuid.uuid4()),
    )
    save_reasoning_trace(
        query="threshold again?", route="production", evidence_ids=[],
        conclusion="Use -12 dB.", confidence="high", tags=["vocals"],
        trace_id=str(uuid.uuid4()),
    )

    result = sched.run_scheduled_maintenance(force=True)

    assert result["ok"] is True
    assert calls == [], f"gated operations were called: {calls}"

    # Sanity check the run actually did real detection work (proving the
    # absence of calls isn't just because nothing ran).
    assert result[sched.JOB_G1]["contradictions_detected"] >= 1
    assert result[sched.JOB_G3]["cross_trace_contradictions_found"] >= 1
    assert result[sched.JOB_G2]["suggested_notes_drafted"] == 1

    # Notes directory must remain exactly as seeded -- no Status: header
    # rewrites, no new files.
    a_content = (notes_dir / "note_a.md").read_text(encoding="utf-8")
    b_content = (notes_dir / "note_b.md").read_text(encoding="utf-8")
    assert "Status: Approved" in a_content
    assert "Status: Approved" in b_content
    assert sorted(p.name for p in notes_dir.glob("*.md")) == ["note_a.md", "note_b.md"]
