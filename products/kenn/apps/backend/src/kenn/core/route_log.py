"""Which path answered each chat request and how long it took (Stage 1: one router, every route timed).

Only the route name, the time, whether the local brain wrote the answer and whether a Live proposal came back are
kept, never the question or the answer. The log is trimmed to the last MAX_LINES requests.
"""

from __future__ import annotations

import json
import os
import statistics
import time
from pathlib import Path
from threading import Lock
from typing import Any

from kenn.paths import RUNTIME_ROOT

LOG = Path(os.environ.get("KENN_ROUTE_LOG", str(RUNTIME_ROOT / "logs" / "routes.jsonl"))).expanduser()
MAX_LINES = 5000
_LOCK = Lock()


def record(route: str, milliseconds: float, *, brain: bool, proposal: bool, path: Path | None = None) -> None:
    from kenn.core import timing_stats

    timing_stats.record(f"route:{route}", milliseconds)
    target = path or LOG
    line = json.dumps({"at": round(time.time(), 1), "route": route[:64], "ms": round(milliseconds, 1),
                       "brain": brain, "proposal": proposal}) + "\n"
    with _LOCK:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(line)
        if target.stat().st_size > MAX_LINES * 120:  # roughly MAX_LINES lines; trim to the newest
            lines = target.read_text(encoding="utf-8").splitlines(keepends=True)[-MAX_LINES:]
            target.write_text("".join(lines), encoding="utf-8")


def summary(path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Per route: requests, p50 and p95 in ms, and how many the brain answered."""
    target = path or LOG
    rows = [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines() if line.strip()] if target.exists() else []
    by_route: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_route.setdefault(str(row.get("route")), []).append(row)
    report = {}
    for route, items in sorted(by_route.items()):
        times = sorted(float(item["ms"]) for item in items)
        report[route] = {"requests": len(items), "p50_ms": round(statistics.median(times), 1),
                         "p95_ms": round(times[int(0.95 * (len(times) - 1))], 1),
                         "brain": sum(bool(item.get("brain")) for item in items)}
    return report


__all__ = ["LOG", "MAX_LINES", "record", "summary"]
