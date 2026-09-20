"""scripts/log_setup.py: Thursday/KENN must persist logs to a rotating file
instead of silently falling back to Python's stderr-only lastResort handler
when nobody configures the root logger (P0 fix, 2026-07-12)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import log_setup  # noqa: E402


def _fresh_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    log_setup._CONFIGURED.discard(name)
    return logger


def test_setup_server_logging_creates_rotating_file_and_writes_records(tmp_path) -> None:
    namespace = "test_thursday_ns"
    _fresh_logger(namespace)

    logger = log_setup.setup_server_logging(namespace, tmp_path)
    logger.warning("something went wrong")

    log_file = tmp_path / f"{namespace}.log"
    assert log_file.exists()
    assert "something went wrong" in log_file.read_text(encoding="utf-8")


def test_child_loggers_propagate_into_the_namespace_handlers(tmp_path) -> None:
    """thursday.brain / kenn.server style child loggers must be captured by
    the single namespace-level setup call, not require per-module wiring."""
    namespace = "test_kenn_ns"
    _fresh_logger(namespace)
    _fresh_logger(f"{namespace}.child_module")

    log_setup.setup_server_logging(namespace, tmp_path)
    child = logging.getLogger(f"{namespace}.child_module")
    child.error("child module failure")

    log_file = tmp_path / f"{namespace}.log"
    assert "child module failure" in log_file.read_text(encoding="utf-8")


def test_setup_server_logging_is_idempotent(tmp_path) -> None:
    namespace = "test_idempotent_ns"
    _fresh_logger(namespace)

    logger_a = log_setup.setup_server_logging(namespace, tmp_path)
    handler_count_after_first = len(logger_a.handlers)
    logger_b = log_setup.setup_server_logging(namespace, tmp_path)

    assert logger_a is logger_b
    assert len(logger_b.handlers) == handler_count_after_first


def test_setup_server_logging_degrades_gracefully_when_dir_unwritable(tmp_path, monkeypatch) -> None:
    namespace = "test_unwritable_ns"
    _fresh_logger(namespace)

    unwritable = tmp_path / "no_such_parent_because_mkdir_fails"

    def boom(*args, **kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "mkdir", boom)

    logger = log_setup.setup_server_logging(namespace, unwritable)
    # Should not raise -- console handler still attached, file handler skipped.
    assert any(isinstance(h, logging.StreamHandler) for h in logger.handlers)
