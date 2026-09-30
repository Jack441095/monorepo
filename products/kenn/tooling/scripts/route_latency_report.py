#!/usr/bin/env python3
"""Per-route request counts and p50/p95 latency from KENN's route log (Stage 1 gate: p95 answer latency <= 4 s)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "backend" / "src"))


def main() -> int:
    from kenn.core import route_log

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--log", type=Path, default=route_log.LOG)
    args = parser.parse_args()
    report = route_log.summary(args.log)
    print(json.dumps(report, indent=1))
    slow = [route for route, row in report.items() if row["p95_ms"] > 4000]
    print(f"{sum(r['requests'] for r in report.values())} requests; routes over the 4 s p95 target: {slow or 'none'}")
    upgrades = route_log.upgrade_summary(args.log)
    if upgrades["attempts"]:
        rate = f"{upgrades['accepted_rate']:.0%}"
        print(f"model answers (upgrades): {upgrades['attempts']} started, {upgrades['accepted']} accepted ({rate}), "
              f"{upgrades['rejected']} rejected, {upgrades['error']} failed, {upgrades['busy']} skipped because the model was busy; "
              f"accepted ones took a median {upgrades['accepted_p50_s']} s, p95 {upgrades['accepted_p95_s']} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
