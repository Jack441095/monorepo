"""Which path answered each chat request and how long it took (Stage 1: one router, every route timed).

Kept per request: the route name, the time, whether the local brain wrote the answer, whether a Live proposal
came back, and optionally a `detail` list of values the caller already extracted. Never the question or the
answer. The log is trimmed to the last MAX_LINES requests.
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


def record(
    route: str,
    milliseconds: float,
    *,
    brain: bool,
    proposal: bool,
    detail: list[str] | None = None,
    path: Path | None = None,
) -> None:
    from kenn.core import timing_stats

    timing_stats.record(f"route:{route}", milliseconds)
    target = path or LOG
    row: dict[str, Any] = {
        "at": round(time.time(), 1),
        "route": route[:64],
        "ms": round(milliseconds, 1),
        "brain": brain,
        "proposal": proposal,
    }
    # Detail is a separate field, never folded into the route: routes are truncated at 64 chars and the report
    # groups by them, so a measurement in the name would split one reason into thousands of routes. Callers pass
    # regex-extracted values like "500 hz", which cannot carry prose, so this keeps to the rule in the docstring.
    if detail:
        row["detail"] = [str(d)[:80] for d in detail[:8]]
    line = json.dumps(row) + "\n"
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


def upgrade_summary(path: Path | None = None) -> dict[str, Any]:
    """How often the model's answer arrived and was accepted, and how long it took (from the answer_upgrade:* rows)."""
    target = path or LOG
    rows = [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines() if line.strip()] if target.exists() else []
    counts: dict[str, int] = {}
    accepted_ms: list[float] = []
    for row in rows:
        route = str(row.get("route", ""))
        if route.startswith("answer_upgrade:"):
            outcome = route.split(":", 1)[1]
            counts[outcome] = counts.get(outcome, 0) + 1
            if outcome == "accepted":
                accepted_ms.append(float(row["ms"]))
    attempts = sum(counts.values())
    accepted_ms.sort()
    return {
        "attempts": attempts,
        "accepted": counts.get("accepted", 0), "rejected": counts.get("rejected", 0),
        "error": counts.get("error", 0), "busy": counts.get("busy", 0),
        "accepted_rate": round(counts.get("accepted", 0) / attempts, 3) if attempts else None,
        "accepted_p50_s": round(statistics.median(accepted_ms) / 1000, 1) if accepted_ms else None,
        "accepted_p95_s": round(accepted_ms[int(0.95 * (len(accepted_ms) - 1))] / 1000, 1) if accepted_ms else None,
    }


__all__ = ["LOG", "MAX_LINES", "record", "summary", "upgrade_summary"]
