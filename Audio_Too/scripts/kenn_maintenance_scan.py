#!/usr/bin/env python3
"""Scheduled entry point for KENN's Stage G autonomous maintenance jobs.

Runs only the read-only/reversible/receipt-producing jobs described in
docs/AUDIO_MVP_MASTER_PLAN.md's Stage G:
  * G1 — daily contradiction + low-trust/coverage-gap scan (detection only)
  * G2 — weekly gap-clustering / suggested-note draft generation
  * G3 — retrospective, log-only cross-trace critique sweep

This is what `audio-too kenn-maintenance` and the launchd job in
docs/launchd/com.audio-too.kenn-maintenance.plist call. It never invokes
resolve_contradiction(), _deprecate_note(), approve_suggested_note(), or any
autonomous trust-score write — see
studio/kenn/kenn/knowledge/maintenance_scheduler.py for the full guardrail
rationale.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KENN_PARENT = ROOT / "studio" / "kenn"
APP = ROOT / "business" / "app"
for value in (ROOT, KENN_PARENT, APP):
    if str(value) not in sys.path:
        sys.path.insert(0, str(value))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kenn_maintenance_scan")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass each job's rate cap (for manual/admin invocation and testing).",
    )
    parsed = parser.parse_args(argv)

    from kenn.knowledge.maintenance_scheduler import run_scheduled_maintenance

    result = run_scheduled_maintenance(force=parsed.force)
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
