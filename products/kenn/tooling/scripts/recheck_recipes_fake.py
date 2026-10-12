#!/usr/bin/env python3
"""Recheck the existing 15 recipe commands and exact restoration without contacting Live."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

KENN_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(KENN_ROOT / "apps/backend/src"))

from qualify_recipes_live import Companion, RECIPES, qualify_one


def recheck() -> dict:
    """Reuse recipe cases with real command/Apply handlers and an isolated FakeLiveBackend."""
    from kenn.core import live_command, live_receipt_journal, session_memory
    from kenn.core.fake_live import DEFAULT_FIXTURE, FakeLiveBackend
    from kenn.core.live_action_service import LiveActionService
    from kenn.routes import daw_command_handler, daw_routes

    class FakeCompanion(Companion):
        def __init__(self, service):
            self.service = service
            super().__init__("unused-fake-endpoint")

        def call(self, path, payload=None, timeout=90):
            # The superclass may name network routes, but this adapter has no network fallback.
            if path == "/kenn/api/ask":
                return live_command.handle_command(payload["question"], session_id=self.session,
                                                   service=self.service, allow_llm=False)
            if path == "/api/ableton/command":
                return daw_routes.handle_live_command({"command": "Apply that", **payload, "deterministic_only": True},
                                                      pending_proposals={})[1]
            raise ValueError(f"Unsupported fake recipe route: {path}")

        def mixer(self):
            # The older runner compared only mixer values; include device parameters and insertions here.
            return copy.deepcopy({"session": self.service.snapshot(), "devices": self.service.client._devices})

    rows = []
    with tempfile.TemporaryDirectory(prefix="kenn-recipe-recheck-") as directory:
        with patch.dict("os.environ", {"KENN_ALLOW_DAW_CONTROL": "1", "KENN_LIVE_BACKEND": "fake"}), \
             patch.object(live_receipt_journal, "JOURNAL_PATH", Path(directory) / "receipts.jsonl"), \
             patch.object(session_memory, "DB_PATH", Path(directory) / "memory.db"):
            for name, request, setup in RECIPES:
                backend = FakeLiveBackend()
                # The demo set has no Glue Compressor to insert. Supply its recorded reset template explicitly.
                zoo = json.loads(DEFAULT_FIXTURE.with_name("device_zoo_wave1.json").read_text())
                backend._templates.update({row["device_name"]: backend._with_recorded_displays(row) for row in zoo["devices"].values()})
                service = LiveActionService(backend)
                companion = FakeCompanion(service)
                def command(text, **kwargs):
                    return live_command.handle_command(text, service=service, **kwargs)
                with patch.object(daw_command_handler, "_get_handle_command", return_value=command):
                    row = qualify_one(companion, name, request, setup)
                row.update(fake_writes=len(backend.writes), real_live_qualified=False,
                           fixture_provenance="investor demo plus recorded device_zoo_wave1 insertion templates")
                rows.append(row)
    return {"schema": "kenn.recipe_fake_recheck.v1", "evidence_kind": "synthetic", "live_writes": 0,
            "model_run": False, "total": len(rows), "passed": sum(row["passed"] for row in rows), "recipes": rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = recheck()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"{report['passed']}/{report['total']} fake recipe lifecycles passed; zero Live writes")
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
