"""Defensive secret redaction for diagnostic logging.

docs/audits/2026-08-20-thursday-nitedsp-forensic-audit.md (Observability
section) found several ``logger.warning(f"...{e}")`` call sites
(episodic_memory.py, entity_graph.py, plan_memory.py) that log an exception's
string representation verbatim, with no redaction safety net if that
exception ever embedded a credential (e.g. an HTTP client library including
request headers in an error message). No active leak was observed, but
nothing would catch one if it happened.

This is deliberately NOT a complete secrets-management redesign -- it is a
small, defensive pattern-matching layer that catches the common shapes a
secret takes in a log line (an ``Authorization: Bearer`` header, a
``PADDLE_API_KEY=...``-style env assignment, a handful of well-known token
prefixes) and replaces the secret portion with ``[REDACTED]`` while leaving
the surrounding diagnostic context intact.

Usage:
    from thursday.redaction import redact
    logger.warning(f"Could not save episode: {redact(str(exc))}")

For a caller with real ``logging`` handler configuration (this codebase has
no centralized ``logging.basicConfig()`` call today -- see
docs/thursday/PHASE_0_HARDENING_REPORT.md), ``RedactingFilter`` can be
attached to a handler or logger so every record passing through it is
redacted without touching each call site individually.
"""

from __future__ import annotations

import logging
import re

_REDACTED = "[REDACTED]"

# Each pattern captures the *label* (if any) in group 1 and must NOT capture
# the secret itself in a way that survives substitution -- the whole match is
# replaced, with any captured label preserved via a callback so we don't
# clobber legitimate surrounding text (e.g. keep "Authorization: Bearer "
# and only blank the token that follows it).

_PATTERNS: list[tuple[re.Pattern, str]] = [
    # "Authorization: Bearer <token>" / "Authorization: Basic <blob>"
    (
        re.compile(r"(?i)\b(authorization\s*:\s*(?:bearer|basic)\s+)(\S+)"),
        r"\1" + _REDACTED,
    ),
    # A bare "Bearer <token>" outside a formal header line.
    (
        re.compile(r"(?i)\bbearer\s+([A-Za-z0-9._\-]{8,})"),
        "Bearer " + _REDACTED,
    ),
    # KEY=value / KEY: value / KEY="value" style assignments where KEY looks
    # like a secret name (env-var-style: SESSION_SECRET, PADDLE_API_KEY,
    # ADMIN_API_KEY, PADDLE_WEBHOOK_SECRET, SMTP_PASSWORD,
    # THURSDAY_CONFIRMATION_SECRET, *_TOKEN, *_PASSWORD, etc).
    (
        re.compile(
            r"(?i)\b([A-Z][A-Z0-9_]*(?:API[_-]?KEY|SECRET|PASSWORD|PASSWD|"
            r"WEBHOOK[_-]?SECRET|ACCESS[_-]?TOKEN|AUTH[_-]?TOKEN|TOKEN)[A-Z0-9_]*)"
            r"\s*[:=]\s*[\"']?([^\s\"']+)[\"']?"
        ),
        r"\1=" + _REDACTED,
    ),
    # Lowercase/free-text equivalents: "password: hunter2", "api key = sk-..."
    (
        re.compile(
            r"(?i)\b(password|passwd|api[_ -]?key|session[_ -]?secret|"
            r"webhook[_ -]?secret|smtp[_ -]?(?:user|pass|password))"
            r"\s*[:=]\s*[\"']?(\S+)[\"']?"
        ),
        r"\1: " + _REDACTED,
    ),
    # Well-known secret-token prefixes, wherever they appear (OpenAI-style
    # sk-..., GitHub ghp_..., Slack xox[baprs]-..., AWS AKIA...).
    (
        re.compile(
            r"\b(sk-[A-Za-z0-9]{10,}|ghp_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{12,})\b"
        ),
        _REDACTED,
    ),
]


def redact(text: str) -> str:
    """Replace common secret shapes in ``text`` with ``[REDACTED]``.

    Deliberately conservative: only matches patterns that look like a
    credential (a header, a KEY=value assignment naming a known secret
    category, or a well-known token prefix), so ordinary diagnostic text
    (file paths, plain error messages, stack traces without embedded
    credentials) passes through unchanged -- over-redaction would destroy
    the debugging value this is meant to preserve.
    """
    if not text:
        return text
    redacted = text
    for pattern, replacement in _PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


class RedactingFilter(logging.Filter):
    """A `logging.Filter` that redacts secrets from a record's rendered message.

    Attach to a specific logger or handler:

        logging.getLogger("thursday").addFilter(RedactingFilter())

    Note: per Python's `logging` propagation model, a filter attached to a
    *logger* only runs for records originating on that exact logger object,
    not on its children (each module's `logging.getLogger(__name__)` is a
    distinct child logger) -- attach to the actual `logging.Handler`(s) an
    application configures (e.g. via `logging.basicConfig()`) for coverage
    across every `thursday.*` submodule logger. This codebase has no
    centralized logging setup today (no `logging.basicConfig()`/handler
    configuration exists anywhere under `thursday/` or `main.py`), so this
    filter is provided as ready-to-use infrastructure for whenever one is
    added, rather than assumed to already be wired in everywhere.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = redact(record.getMessage())
            record.args = ()
        except Exception:
            # Never let a redaction bug block a log record from being emitted.
            pass
        return True


def get_logger(name: str) -> logging.Logger:
    """Shared logger factory: `logging.getLogger(name)` with `RedactingFilter`
    already attached.

    This is the safe middle tier between "leave every call site to remember
    `redact()` manually" and "a fully centralized logging config this
    codebase doesn't have" (see `RedactingFilter`'s docstring on why a
    filter attached to an *ancestor* logger doesn't cover child loggers).

    A filter attached directly to the *originating* logger (the one
    `logger.warning(...)` is actually called on) DOES run for every record
    that logger emits -- `Logger.handle()` checks its own `.filters` before
    a record is even considered for propagation to any handler. So a module
    that does::

        logger = thursday.redaction.get_logger(__name__)

    instead of::

        logger = logging.getLogger(__name__)

    gets every future `logger.warning(...)`/`.error(...)`/etc. call in that
    module redacted automatically -- new call sites don't need to remember
    to wrap their message in `redact()` by hand. Safe to call once per
    module at import time (idempotent: does not add a duplicate filter if
    called again for the same logger name).
    """
    logger = logging.getLogger(name)
    if not any(isinstance(f, RedactingFilter) for f in logger.filters):
        logger.addFilter(RedactingFilter())
    return logger


def install_thursday_log_redaction() -> None:
    """Best-effort central installation point.

    Attaches `RedactingFilter` to the `"thursday"` package logger (covers
    anything logged directly via `logging.getLogger("thursday")`) and to any
    handlers already attached to the root logger at call time (covers the
    common case where an application calls `logging.basicConfig()` before
    importing Thursday, since root handlers' filters run for every
    propagated record regardless of which submodule logger originated it).
    Safe to call more than once -- does not add a duplicate filter instance.
    """
    thursday_logger = logging.getLogger("thursday")
    if not any(isinstance(f, RedactingFilter) for f in thursday_logger.filters):
        thursday_logger.addFilter(RedactingFilter())
    for handler in logging.getLogger().handlers:
        if not any(isinstance(f, RedactingFilter) for f in handler.filters):
            handler.addFilter(RedactingFilter())
