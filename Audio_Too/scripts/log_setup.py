"""Shared console + rotating-file logging setup for long-running servers.

Thursday and KENN are both meant to run unattended for an entire studio
session. Both already call ``logging.getLogger(__name__)``/
``logging.getLogger("thursday.X")``/``logging.getLogger("kenn.X")``
throughout their modules, but nothing ever attaches a handler to the
"thursday" or "kenn" namespace logger -- every record silently falls back to
Python's stderr-only "handler of last resort" with no persistence. If the
terminal isn't being watched (or stdout isn't redirected), every warning and
error is lost forever. This module fixes that at the two server entry
points without touching the ~70 individual ``logger = ...`` call sites.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

_CONFIGURED: set[str] = set()


def setup_server_logging(
    namespace: str, logs_dir: Path, *, level: int = logging.INFO
) -> logging.Logger:
    """Attach console + rotating-file handlers to the ``namespace`` logger.

    All of that namespace's child loggers (``thursday.brain``, ``kenn.server``,
    etc.) propagate up to this one by default, so this single call captures
    the whole subsystem's existing logging calls. Idempotent per namespace so
    a server that re-execs or reloads in-process doesn't stack duplicate
    handlers.
    """
    logger = logging.getLogger(namespace)
    if namespace in _CONFIGURED:
        return logger

    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    console = logging.StreamHandler(stream=sys.stdout)
    console.setLevel(level)
    console.setFormatter(fmt)
    logger.addHandler(console)

    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
        # 10MB x 5 backups per namespace -- bounded, unlike a plain
        # FileHandler, so this can't grow unboundedly over a long-lived
        # server's lifetime.
        file_handler = logging.handlers.RotatingFileHandler(
            str(logs_dir / f"{namespace}.log"),
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
    except OSError as exc:
        logger.warning(
            "Could not create rotating file handler in %s (%s); file logging disabled, console only.",
            logs_dir,
            exc,
        )

    _CONFIGURED.add(namespace)
    return logger
