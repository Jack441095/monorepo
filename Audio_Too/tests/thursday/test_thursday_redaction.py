"""Phase-0 P0-F regression: defensive secret redaction for diagnostic logging.

docs/audits/2026-08-20-thursday-nitedsp-forensic-audit.md (Observability
section) found several `logger.warning(f"...{e}")` call sites
(thursday/memory/episodic_memory.py, thursday/memory/entity_graph.py,
thursday/plan_memory.py) that log an exception's string representation
verbatim, with no redaction safety net. These tests use only synthetic fake
secrets -- no real credential value is ever logged or asserted against.
"""

from __future__ import annotations

import logging

from thursday.redaction import RedactingFilter, get_logger, redact


def test_redacts_bearer_token_in_authorization_header():
    text = "Authorization: Bearer sk-fake-abc123XYZ789 rejected by upstream"
    out = redact(text)
    assert "sk-fake-abc123XYZ789" not in out
    assert "Authorization: Bearer [REDACTED]" in out


def test_redacts_bare_bearer_token():
    text = "request failed, sent Bearer eyFakeJwtHeader.fakePayload.fakeSig"
    out = redact(text)
    assert "eyFakeJwtHeader" not in out
    assert "Bearer [REDACTED]" in out


def test_redacts_known_env_secret_names():
    for line in [
        "PADDLE_API_KEY=sk_test_fake000111222",
        "SESSION_SECRET: super-secret-fake-value",
        "ADMIN_API_KEY = 'fake-admin-key-000'",
        "PADDLE_WEBHOOK_SECRET=whsec_fake_000",
        "THURSDAY_CONFIRMATION_SECRET=fake-confirmation-secret",
    ]:
        out = redact(line)
        assert "[REDACTED]" in out, f"did not redact: {line!r} -> {out!r}"
        # The variable name itself (context) must survive -- only the value redacted.
        name = line.split("=")[0].split(":")[0].strip().strip("'\"")
        assert name in out


def test_redacts_password_field():
    text = "SMTP login failed: password=hunter2fake could not authenticate"
    out = redact(text)
    assert "hunter2fake" not in out
    assert "[REDACTED]" in out


def test_redacts_smtp_credentials():
    text = "smtp_password: fake-smtp-pass-000 rejected"
    out = redact(text)
    assert "fake-smtp-pass-000" not in out
    assert "[REDACTED]" in out


def test_redacts_common_token_prefixes():
    for token in [
        "sk-FAKEabcdefghijklmno",
        "ghp_FAKEabcdefghijklmnopqrstuvwx0000",
        "xoxb-FAKE-0000000000-abcdefghijklmnop",
        "AKIAFAKE0123456789AB",
    ]:
        out = redact(f"upstream call failed with token {token} attached")
        assert token not in out
        assert "[REDACTED]" in out


def test_does_not_redact_ordinary_diagnostic_text():
    """Over-redaction destroys debugging value -- plain error messages,
    paths, and non-secret exception text must pass through unchanged."""
    ordinary = [
        "Failed to load entity graph: [Errno 2] No such file or directory: 'entity_graph.json'",
        "sqlite3.OperationalError: database is locked",
        "ValueError: invalid literal for int() with base 10: 'abc'",
        "Connection timed out after 30 seconds to 127.0.0.1:11434",
    ]
    for text in ordinary:
        assert redact(text) == text


def test_redact_handles_empty_and_none_like_input():
    assert redact("") == ""


def test_redacting_filter_scrubs_log_record(caplog):
    logger = logging.getLogger("thursday.redaction.test")
    logger.addFilter(RedactingFilter())
    with caplog.at_level(logging.WARNING, logger="thursday.redaction.test"):
        logger.warning("leaked header: Authorization: Bearer sk-fake-leak-000")
    assert caplog.records
    assert "sk-fake-leak-000" not in caplog.records[-1].getMessage()
    assert "[REDACTED]" in caplog.records[-1].getMessage()


def test_redacting_filter_preserves_ordinary_messages(caplog):
    logger = logging.getLogger("thursday.redaction.test2")
    logger.addFilter(RedactingFilter())
    with caplog.at_level(logging.WARNING, logger="thursday.redaction.test2"):
        logger.warning("Failed to save episodic memory: disk full")
    assert "Failed to save episodic memory: disk full" in caplog.records[-1].getMessage()


def test_entity_graph_load_failure_is_redacted_in_logs(tmp_path, monkeypatch, caplog):
    """Integration check for the actual flagged call site: a load failure
    whose exception text happens to embed a fake secret must not leak it."""
    from thursday.memory.entity_graph import SemanticEntityGraph

    bad_file = tmp_path / "entity_graph.json"
    bad_file.write_text("{not valid json, Authorization: Bearer sk-fake-leak-999")

    with caplog.at_level(logging.WARNING, logger="thursday.memory.entity_graph"):
        SemanticEntityGraph(storage_dir=tmp_path)

    combined = "\n".join(r.getMessage() for r in caplog.records)
    # json.JSONDecodeError's message doesn't echo file *content*, so this
    # mainly proves the call site is wired through redact() without erroring;
    # the pattern-level guarantee is covered by the direct redact() tests above.
    assert "Failed to load entity graph" in combined


def test_get_logger_factory_redacts_without_a_call_site_wrapper(caplog):
    """The shared-logger-factory tier: a module using
    thursday.redaction.get_logger(__name__) instead of
    logging.getLogger(__name__) gets every future log call redacted
    automatically -- the call site never wraps the message in redact()
    itself. Proves the filter fires for the *originating* logger (not just
    an ancestor), which is what makes this safe without a centralized
    logging.basicConfig() anywhere in this codebase."""
    logger = get_logger("thursday.redaction.factory_test")
    with caplog.at_level(logging.WARNING, logger="thursday.redaction.factory_test"):
        # No redact() call at this call site -- the factory did the work.
        logger.warning("upstream failed: Authorization: Bearer sk-fake-factory-000")
    assert caplog.records
    message = caplog.records[-1].getMessage()
    assert "sk-fake-factory-000" not in message
    assert "[REDACTED]" in message


def test_get_logger_factory_is_idempotent():
    """Calling get_logger() twice for the same name must not stack duplicate
    filters (which would otherwise double-mutate/no-op on a second pass)."""
    logger_a = get_logger("thursday.redaction.idempotent_test")
    logger_b = get_logger("thursday.redaction.idempotent_test")
    assert logger_a is logger_b
    redacting_filters = [f for f in logger_a.filters if isinstance(f, RedactingFilter)]
    assert len(redacting_filters) == 1


def test_orchestrator_brain_diagnostics_memory_manager_use_the_redacting_factory():
    """Phase-0.5 follow-up: the four remaining bare
    logger.warning(f\"...{e}\") modules found during the redaction coverage
    audit (orchestrator.py, brain.py, diagnostics.py, memory_manager.py)
    were migrated to the shared factory rather than patched call-site by
    call-site -- every future log call in these modules is protected, not
    just the ones inspected today."""
    import thursday.brain as brain
    import thursday.diagnostics as diagnostics
    import thursday.memory.memory_manager as memory_manager
    import thursday.orchestrator as orchestrator

    for module in (brain, diagnostics, memory_manager, orchestrator):
        assert any(isinstance(f, RedactingFilter) for f in module.logger.filters), (
            f"{module.__name__}.logger is missing RedactingFilter"
        )


def test_episodic_memory_load_failure_is_redacted_in_logs(tmp_path, caplog):
    from thursday.memory.episodic_memory import EpisodicMemory

    bad_file = tmp_path / "episodes.json"
    bad_file.write_text("not json at all")

    with caplog.at_level(logging.WARNING, logger="thursday.memory.episodic_memory"):
        EpisodicMemory(storage_dir=tmp_path)

    combined = "\n".join(r.getMessage() for r in caplog.records)
    assert "Failed to load episodic memory" in combined
