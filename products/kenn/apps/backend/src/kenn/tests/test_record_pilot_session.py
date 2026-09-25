"""A supervised pilot session recorded with the helper counts at the release gate, and keeps no names."""

from __future__ import annotations

import builtins
import json
import sys

import pytest

from scripts import build_support_bundle, record_pilot_session
from scripts.evaluate_supervised_pilot import DEFAULT_MATRIX, evaluate

REVISION = "a" * 40


def _bundle(tmp_path, events):
    files = build_support_bundle.build_payload(
        diagnostics={"schema": "kenn.support_diagnostics.v1", "runtime": {}, "checks": {}, "features": {}, "ableton": {}},
        receipts={"receipts": [{"receipt": event} for event in events]}, revision=REVISION)
    path = tmp_path / "s01.zip"
    build_support_bundle.write_bundle(path, files)
    return path


def _answers(monkeypatch, answers):
    queue = iter(answers)
    monkeypatch.setattr(builtins, "input", lambda _prompt="": next(queue))


def test_a_clean_session_is_accepted_by_the_gate_evaluator(tmp_path, monkeypatch) -> None:
    events = [{"receipt_id": f"r{n}", "action": "set_volume", "status": "applied", "verified": True} for n in range(3)]
    bundle = _bundle(tmp_path, events)
    # 1 undo, it restored the value, six pre-flight yeses, five zero safety counts, passed, signed off.
    _answers(monkeypatch, ["1", "y", *["y"] * 6, *["0"] * 5, "y", "y"])
    monkeypatch.setattr(sys, "argv", ["record", "--bundle", str(bundle), "--project", "Song One", "--tester", "Tester A",
                                      "--started-at", "2026-09-25T10:00:00+01:00", "--requests", "4"])
    assert record_pilot_session.main() == 0
    log = json.loads(bundle.with_suffix(".json").read_text())
    assert log["operations"]["mutation_count"] == 2 and log["operations"]["undo_verified_count"] == 1
    assert "Song One" not in json.dumps(log) and "Tester A" not in json.dumps(log)
    assert evaluate([bundle.with_suffix(".json")], matrix_path=DEFAULT_MATRIX, source_revision=REVISION)["rows"][0]["passed"]


def test_a_missed_preflight_check_is_reported_before_the_gate(tmp_path, monkeypatch, capsys) -> None:
    events = [{"receipt_id": f"r{n}", "action": "set_pan", "status": "applied", "verified": True} for n in range(2)]
    bundle = _bundle(tmp_path, events)
    _answers(monkeypatch, ["1", "y", "n", *["y"] * 5, *["0"] * 5, "y", "y"])
    monkeypatch.setattr(sys, "argv", ["record", "--bundle", str(bundle), "--project", "p", "--tester", "t",
                                      "--started-at", "2026-09-25T10:00:00+01:00", "--requests", "2"])
    assert record_pilot_session.main() == 1
    assert "preflight" in capsys.readouterr().out
