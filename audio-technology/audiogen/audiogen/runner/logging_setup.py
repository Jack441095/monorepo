from __future__ import annotations

import logging
import sys
from pathlib import Path


class _ConsoleQuietFilter(logging.Filter):
    """
    Hide repetitive real-time / buffer diagnostics on the console.

    The file log keeps DEBUG so full detail (telemetry, stream status, etc.) is preserved there;
    the console stays at INFO and applies this filter for a few noisy WARNING substrings.
    """

    _SUBSTRINGS = (
        "Slow bar render",
        "Attempting audio stream recovery",
        "BUFFER UNDERRUN",
        "PortAudio output_underflow",
        "Unexpected audio shape",
        "Dropped stale pre-generated section",
        "Pre-generation produced no events",
    )

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        return not any(s in msg for s in self._SUBSTRINGS)


class _ConsoleNoWarningsFilter(logging.Filter):
    """
    Keep the terminal clean by hiding WARNING-level log records.

    Errors (ERROR/CRITICAL) still surface on the console so real failures are visible.
    Warnings are still captured in file logs.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            lvl = int(getattr(record, "levelno", 0) or 0)
        except Exception:
            return True
        return lvl != logging.WARNING


class _WarningsOnlyFilter(logging.Filter):
    """Allow only WARNING-level log records (not ERROR/CRITICAL)."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            lvl = int(getattr(record, "levelno", 0) or 0)
        except Exception:
            return False
        return lvl == logging.WARNING


def setup_logging(*, verbose: bool = False, quiet: bool = False, logs_dir: Path | None = None) -> None:
    """
    Configure root logging handlers in a runner-friendly way.

    Safe to call multiple times within one process (no duplicate handlers).
    """

    root = logging.getLogger()
    if root.handlers:
        return

    if logs_dir is None:
        logs_dir = Path(__file__).resolve().parent.parent / "logs"
    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        logs_dir = None

    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root.setLevel(logging.DEBUG)

    console = logging.StreamHandler(stream=sys.stdout)
    if bool(quiet):
        console.setLevel(logging.ERROR)
    elif bool(verbose):
        console.setLevel(logging.DEBUG)
    else:
        console.setLevel(logging.INFO)
    console.setFormatter(fmt)

    if not bool(verbose):
        console.addFilter(_ConsoleQuietFilter())
        console.addFilter(_ConsoleNoWarningsFilter())
    root.addHandler(console)

    if logs_dir is not None:
        log_path = logs_dir / "runtime.log"
        fileh = logging.FileHandler(str(log_path), encoding="utf-8")
        fileh.setLevel(logging.DEBUG)
        fileh.setFormatter(fmt)
        root.addHandler(fileh)

        warnings_path = logs_dir / "warnings.log"
        warnh = logging.FileHandler(str(warnings_path), encoding="utf-8")
        warnh.setLevel(logging.WARNING)
        warnh.setFormatter(fmt)
        warnh.addFilter(_WarningsOnlyFilter())
        root.addHandler(warnh)

