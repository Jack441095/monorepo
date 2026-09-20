"""validate_startup_secrets() must warn (not silently say nothing) when
upload/invoice/demo signing keys fall back to the dashboard password
(P1 fix, 2026-07-13 -- see docs/codebase_scan_12_07.md §4.1)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server" / "app"))

import server_config  # noqa: E402


def _valid_env(monkeypatch) -> None:
    monkeypatch.setenv("AUDIO_TOO_DEV", "0")
    monkeypatch.setenv("AUDIO_TOO_DASHBOARD_PASSWORD", "a-real-non-default-password")
    monkeypatch.setenv("AUDIO_TOO_SESSION_SECRET", "x" * 32)


def test_warns_when_signing_keys_are_unset(monkeypatch, capsys) -> None:
    _valid_env(monkeypatch)
    monkeypatch.delenv("AUDIO_TOO_UPLOAD_SIGNING_KEY", raising=False)
    monkeypatch.delenv("AUDIO_TOO_INVOICE_SIGNING_KEY", raising=False)
    monkeypatch.delenv("AUDIO_TOO_DEMO_SESSION_SECRET", raising=False)

    server_config.validate_startup_secrets()

    out = capsys.readouterr().out
    assert "AUDIO_TOO_UPLOAD_SIGNING_KEY" in out
    assert "AUDIO_TOO_INVOICE_SIGNING_KEY" in out
    assert "AUDIO_TOO_DEMO_SESSION_SECRET" in out
    assert "Warning" in out


def test_no_warning_when_signing_keys_are_set(monkeypatch, capsys) -> None:
    _valid_env(monkeypatch)
    monkeypatch.setenv("AUDIO_TOO_UPLOAD_SIGNING_KEY", "x" * 32)
    monkeypatch.setenv("AUDIO_TOO_INVOICE_SIGNING_KEY", "y" * 32)
    monkeypatch.setenv("AUDIO_TOO_DEMO_SESSION_SECRET", "z" * 32)

    server_config.validate_startup_secrets()

    out = capsys.readouterr().out
    assert "SIGNING_KEY" not in out
    assert "DEMO_SESSION_SECRET" not in out


def test_missing_signing_keys_does_not_block_startup(monkeypatch) -> None:
    """The warning must not raise -- a hard fail here would risk an
    unattended startup refusal, unlike the dashboard-password/session-secret
    checks which correctly do fail closed."""
    _valid_env(monkeypatch)
    monkeypatch.delenv("AUDIO_TOO_UPLOAD_SIGNING_KEY", raising=False)
    monkeypatch.delenv("AUDIO_TOO_INVOICE_SIGNING_KEY", raising=False)
    monkeypatch.delenv("AUDIO_TOO_DEMO_SESSION_SECRET", raising=False)

    server_config.validate_startup_secrets()  # must not raise


def test_still_fails_closed_on_missing_dashboard_password(monkeypatch) -> None:
    monkeypatch.setenv("AUDIO_TOO_DEV", "0")
    monkeypatch.delenv("AUDIO_TOO_DASHBOARD_PASSWORD", raising=False)

    try:
        server_config.validate_startup_secrets()
        assert False, "expected SystemExit"
    except SystemExit as exc:
        assert exc.code == 1
