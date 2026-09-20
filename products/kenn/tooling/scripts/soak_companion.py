#!/usr/bin/env python3
"""Bounded reliability sampler for an already-running KENN companion."""

from __future__ import annotations

import argparse, hashlib, json, os, platform, statistics, subprocess, time, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Any

SCHEMA = "kenn.companion_soak.v1"

def runner_sha256() -> str:
    return hashlib.sha256(Path(__file__).resolve().read_bytes()).hexdigest()

def write_checkpoint(path: Path, result: dict[str, Any]) -> None:
    destination = path.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    payload = (json.dumps(result, indent=2, sort_keys=True) + "\n").encode("utf-8")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, destination); os.chmod(destination, 0o600)
    finally:
        try: temporary.unlink()
        except FileNotFoundError: pass

def source_revision() -> str:
    """Return the source binding, while allowing sanitized archives to test."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[2], text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        # A release qualification still needs a real Git-bound revision. An
        # isolated source archive has no .git directory, but its diagnostic
        # soak tests should still run and remain visibly unbound.
        return "unavailable"

def fetch(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as response:
        value = json.loads(response.read())
    if not isinstance(value, dict): raise ValueError("endpoint did not return an object")
    return value

def process_stats(pid: int) -> dict:
    rss = subprocess.check_output(["ps", "-o", "rss=", "-p", str(pid)], text=True).strip()
    if not rss: raise RuntimeError(f"process {pid} is unavailable")
    if platform.system() == "Darwin":
        lines = subprocess.check_output(["ps", "-M", "-p", str(pid)], text=True).splitlines()
        threads = max(0, len(lines) - 1)
    else:
        threads_text = subprocess.check_output(["ps", "-o", "nlwp=", "-p", str(pid)], text=True).strip()
        threads = int(threads_text)
    return {"rss_bytes": int(rss) * 1024, "thread_count": threads}

def run(*, endpoint: str, pid: int, samples: int, interval: float,
        min_ableton_reconnects: int = 0,
        max_ableton_outage_seconds: float | None = None,
        require_ableton_connected_end: bool = False,
        max_thread_growth: int = 8,
        fetcher: Callable[[str], dict] = fetch,
        stat_reader: Callable[[int], dict] = process_stats,
        sleeper: Callable[[float], None] = time.sleep,
        revision: str | None = None,
        checkpoint: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
    rows = []
    bound_revision = revision or source_revision()
    for index in range(samples):
        started = time.perf_counter()
        error = None; health = {}; stats = {}
        try: health = fetcher(endpoint.rstrip("/") + "/api/health")
        except Exception as exc: error = f"{type(exc).__name__}: {exc}"[:256]
        try: stats = stat_reader(pid)
        except Exception as exc: error = error or f"{type(exc).__name__}: {exc}"[:256]
        rows.append({"index": index, "captured_at": datetime.now(timezone.utc).isoformat(),
                     "latency_ms": round((time.perf_counter()-started)*1000, 3),
                     "health_ok": health.get("ok") is True, "ableton_status": (health.get("subsystems", {}).get("abletonosc", {}).get("status")),
                     "runtime_state": health.get("subsystems", {}).get("runtime_state"),
                     **stats, "error": error})
        if checkpoint is not None:
            checkpoint({
                "schema": SCHEMA,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "source_git_commit": bound_revision,
                "runner_sha256": runner_sha256(),
                "endpoint": endpoint,
                "pid": pid,
                "sample_count": len(rows),
                "expected_sample_count": samples,
                "interval_seconds": interval,
                "progress": {
                    "status": "running", "complete": False,
                    "completed_sample_count": len(rows), "expected_sample_count": samples,
                },
                "qualified": False,
                "samples": list(rows),
                "limitations": ["Partial checkpoint only; never qualification evidence."],
            })
        if index + 1 < samples: sleeper(interval)
    rss = [r["rss_bytes"] for r in rows if "rss_bytes" in r]
    latency = [r["latency_ms"] for r in rows]
    errors = sum(bool(r["error"]) or not r["health_ok"] for r in rows)
    growth = rss[-1] - rss[0] if len(rss) > 1 else 0
    peak_rss = max(rss) if rss else None
    peak_growth = peak_rss - rss[0] if peak_rss is not None and rss else None
    thread_counts = [r["thread_count"] for r in rows if "thread_count" in r]
    peak_thread_growth = max(thread_counts) - thread_counts[0] if thread_counts else None
    statuses = [str(row.get("ableton_status") or "unknown") for row in rows]
    disconnects = sum(
        previous == "connected" and current != "connected"
        for previous, current in zip(statuses, statuses[1:])
    )
    reconnects = sum(
        previous != "connected" and current == "connected"
        for previous, current in zip(statuses, statuses[1:])
    )
    longest_outage_samples = 0
    current_outage_samples = 0
    for status in statuses:
        if status == "connected":
            current_outage_samples = 0
        else:
            current_outage_samples += 1
            longest_outage_samples = max(longest_outage_samples, current_outage_samples)
    longest_outage_seconds = longest_outage_samples * interval
    connected_at_end = bool(statuses and statuses[-1] == "connected")
    state_rows = [row.get("runtime_state") for row in rows]
    state_available = all(isinstance(state, dict) and state.get("available") is not False for state in state_rows)
    state_summary: dict[str, Any] = {"available_all_samples": state_available}
    state_within_limits = state_available
    for field in ("pending_proposals", "action_receipts", "mix_reviews"):
        values = [int(state.get(field, 0)) for state in state_rows if isinstance(state, dict)]
        limits = [int(state.get(f"{field}_limit", 0)) for state in state_rows if isinstance(state, dict)]
        state_summary[field] = {
            "start": values[0] if values else None, "end": values[-1] if values else None,
            "growth": values[-1] - values[0] if values else None, "maximum": max(values) if values else None,
            "limit": min(limits) if limits else None,
        }
        state_within_limits = state_within_limits and bool(values and limits and max(values) <= min(limits))
    reconnect_gate = reconnects >= max(0, int(min_ableton_reconnects))
    outage_gate = max_ableton_outage_seconds is None or longest_outage_seconds <= max_ableton_outage_seconds
    connected_end_gate = not require_ableton_connected_end or connected_at_end
    qualified = (
        errors == 0
        and growth <= 128 * 1024 * 1024
        and peak_growth is not None and peak_growth <= 128 * 1024 * 1024
        and peak_thread_growth is not None and peak_thread_growth <= max_thread_growth
        and state_within_limits and reconnect_gate and outage_gate and connected_end_gate
    )
    return {"schema": SCHEMA, "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_git_commit": bound_revision, "runner_sha256": runner_sha256(),
            "endpoint": endpoint, "pid": pid, "sample_count": samples,
            "expected_sample_count": samples,
            "progress": {"status": "complete", "complete": True,
                         "completed_sample_count": samples, "expected_sample_count": samples},
            "interval_seconds": interval, "summary": {"error_samples": errors,
            "rss_start_bytes": rss[0] if rss else None, "rss_end_bytes": rss[-1] if rss else None,
            "rss_growth_bytes": growth if rss else None, "rss_peak_bytes": peak_rss,
            "rss_peak_growth_bytes": peak_growth,
            "thread_start_count": thread_counts[0] if thread_counts else None,
            "thread_end_count": thread_counts[-1] if thread_counts else None,
            "max_thread_count": max(thread_counts) if thread_counts else None,
            "peak_thread_growth": peak_thread_growth,
            "latency_median_ms": round(statistics.median(latency),3), "latency_max_ms": max(latency),
            "ableton_disconnect_events": disconnects, "ableton_reconnect_events": reconnects,
            "longest_ableton_outage_seconds": longest_outage_seconds,
            "ableton_connected_at_end": connected_at_end, "runtime_state": state_summary},
            "thresholds": {"error_samples": 0, "max_rss_growth_bytes": 128 * 1024 * 1024,
            "min_ableton_reconnects": max(0, int(min_ableton_reconnects)),
            "max_thread_growth": max_thread_growth,
            "max_ableton_outage_seconds": max_ableton_outage_seconds,
            "require_ableton_connected_end": require_ableton_connected_end},
            "qualified": qualified, "samples": rows,
            "limitations": ["Resource and observed reconnect evidence only; this does not inject failures, mutate Live, or qualify musical output."]}

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default="http://127.0.0.1:8090")
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--duration-seconds", type=float, default=86400)
    parser.add_argument("--interval-seconds", type=float, default=60)
    parser.add_argument("--min-ableton-reconnects", type=int, default=0)
    parser.add_argument("--max-ableton-outage-seconds", type=float)
    parser.add_argument("--require-ableton-connected-end", action="store_true")
    parser.add_argument("--max-thread-growth", type=int, default=8)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.duration_seconds < 0 or args.interval_seconds <= 0: parser.error("duration must be non-negative and interval positive")
    if args.min_ableton_reconnects < 0: parser.error("minimum reconnects must be non-negative")
    if args.max_ableton_outage_seconds is not None and args.max_ableton_outage_seconds < 0: parser.error("maximum outage must be non-negative")
    if args.max_thread_growth < 0: parser.error("maximum thread growth must be non-negative")
    samples = max(1, int(args.duration_seconds / args.interval_seconds) + 1)
    destination = args.output.expanduser().resolve()
    result = run(endpoint=args.endpoint, pid=args.pid, samples=samples, interval=args.interval_seconds,
                 min_ableton_reconnects=args.min_ableton_reconnects,
                 max_ableton_outage_seconds=args.max_ableton_outage_seconds,
                 require_ableton_connected_end=args.require_ableton_connected_end,
                 max_thread_growth=args.max_thread_growth,
                 checkpoint=lambda partial: write_checkpoint(destination, partial))
    write_checkpoint(destination, result)
    print(json.dumps(result["summary"], indent=2, sort_keys=True))
    return 0 if result["qualified"] else 1

if __name__ == "__main__": raise SystemExit(main())
