"""Recent response times for support diagnostics: numbers only, kept in memory, never the request."""

from __future__ import annotations

from collections import deque
from threading import Lock

MAX_SAMPLES = 200
_SAMPLES: dict[str, deque[float]] = {}
_LOCK = Lock()


def record(kind: str, milliseconds: float) -> None:
    with _LOCK:
        _SAMPLES.setdefault(kind, deque(maxlen=MAX_SAMPLES)).append(float(milliseconds))


def _percentile(ordered: list[float], fraction: float) -> float:
    return ordered[min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1))))]


def summary() -> dict[str, dict[str, float | int]]:
    """Per kind: how many recent samples, median, 95th percentile and slowest, in ms."""
    with _LOCK:
        snapshot = {kind: sorted(values) for kind, values in _SAMPLES.items() if values}
    return {kind: {"count": len(values), "p50_ms": round(_percentile(values, 0.5), 1),
                   "p95_ms": round(_percentile(values, 0.95), 1), "max_ms": round(values[-1], 1)}
            for kind, values in snapshot.items()}


def reset() -> None:
    with _LOCK:
        _SAMPLES.clear()


__all__ = ["MAX_SAMPLES", "record", "summary", "reset"]
