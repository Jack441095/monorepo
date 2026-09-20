"""Persistent in-process agent dispatch tests.

Covers the fast path (no subprocess per call), honest fallback to
subprocess when in-process loading fails, output equivalence, and the
db-init fast-path guard (rollback clears it).
"""

from __future__ import annotations

import io
import sys
from unittest.mock import patch

import pytest

from thursday import client


@pytest.fixture(autouse=True)
def _inprocess_enabled(monkeypatch):
    monkeypatch.delenv("AUDIO_TOO_BUSINESS_INPROCESS", raising=False)
    # Reset cached module so each test starts from a clean dispatch state.
    monkeypatch.setattr(client, "_AGENT_MODULE", None)


def test_inprocess_output_matches_subprocess(monkeypatch):
    """The persistent path must return byte-identical CLI output."""
    monkeypatch.setenv("AUDIO_TOO_BUSINESS_INPROCESS", "0")
    subprocess_out = client.business_status()

    monkeypatch.setenv("AUDIO_TOO_BUSINESS_INPROCESS", "1")
    monkeypatch.setattr(client, "_AGENT_MODULE", None)
    inprocess_out = client.business_status()

    assert inprocess_out == subprocess_out
    assert "Clients:" in inprocess_out


def test_module_loaded_once_only():
    client._load_agent_module()
    first = client._AGENT_MODULE
    again = client._load_agent_module()
    assert first is again  # cache hit, no reload


def test_fallback_to_subprocess_when_loader_fails(monkeypatch):
    def broken_loader():
        raise ImportError("boom")

    monkeypatch.setattr(client, "_load_agent_module", broken_loader)
    out = client._cli_cmd("status")
    # Honest degradation: still returns real status via subprocess.
    assert "Clients:" in out or "service_unavailable" in out.lower()


def test_env_flag_disables_inprocess(monkeypatch):
    called = {"inprocess": False}

    def trap(*a, **k):
        called["inprocess"] = True
        return "x"

    monkeypatch.setenv("AUDIO_TOO_BUSINESS_INPROCESS", "0")
    monkeypatch.setattr(client, "_cli_cmd_inprocess", trap)
    out = client._cli_cmd("status")
    assert called["inprocess"] is False
    assert out != "x"


def test_inprocess_failure_contract_on_command_error(monkeypatch):
    """A failing command mirrors the subprocess failure contract."""
    module = client._load_agent_module()

    def failing_main():
        print("partial output before crash")
        return 1

    monkeypatch.setattr(module, "main", failing_main)
    out = client._cli_cmd_inprocess("status")
    assert out == "Service command failed (error code: service_unavailable)."


def test_db_init_fast_path_and_rollback_clears_it(tmp_path, monkeypatch):
    """init_db runs its migration scan once per process; rollback invalidates."""
    import server.app.db as db

    # Hermetic: point at a throwaway database without reloading the module
    # (a reload would corrupt other suites' references to this shared module).
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "fastpath.db")
    monkeypatch.setattr(db, "_migration_done", True)
    monkeypatch.setattr(
        db, "migrate_json_to_sqlite_if_needed", lambda: scan_calls.append(1)
    )

    scan_calls: list[int] = []
    previous_flag = getattr(db.init_db, "_completed", False)
    db.init_db._completed = False
    try:
        db.init_db()
        assert scan_calls == [1]
        db.init_db()  # fast path
        db.init_db()
        assert scan_calls == [1], "fast path did not skip the rescan"

        db.rollback_db(1)
        assert db.init_db._completed is False
    finally:
        db.init_db._completed = previous_flag
