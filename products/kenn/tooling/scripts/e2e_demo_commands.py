#!/usr/bin/env python3
"""Run test commands end to end through KENN's command gateway on the demo backend.

For every command: propose (and check nothing was written yet), confirm with
the proposal's own token, check KENN's readback verified the write, then undo
and check the set is back exactly as it was. Uses the recorded demo set
(FakeLiveBackend), never real Live, and keeps receipts, logs and sessions in a
temporary folder so KENN's real journal is untouched. Input is the review
page's exported `tests` collection (JSON files) or a JSONL file.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

KENN_ROOT = Path(__file__).resolve().parents[2]


def isolate_state() -> Path:
    """Point every durable KENN path at a temp folder before KENN is imported."""
    temp = Path(tempfile.mkdtemp(prefix="kenn-e2e-"))
    os.environ.update({
        "KENN_LIVE_RECEIPT_JOURNAL": str(temp / "receipts.jsonl"),
        "KENN_LIVE_LLM_SHADOW_LOG": str(temp / "shadow.jsonl"),
        "KENN_DB_PATH": str(temp / "kenn.db"),
        "KENN_SESSION_FILE": str(temp / "session.json"),
        "KENN_CHATS_DIR": str(temp / "chats"),
        "KENN_ALLOW_DAW_CONTROL": "1",
    })
    for name in ("KENN_LIVE_LLM_ENABLED", "KENN_LLM_ENABLED", "KENN_LLM_ENABLED_COMMAND"):
        os.environ.pop(name, None)  # deterministic path only
    return temp


def load_tests(source: Path, kind: str) -> list[dict[str, Any]]:
    if source.is_dir():
        docs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(source.rglob("*.json"))]
        rows = [doc.get("data", doc) for doc in docs]
    else:
        rows = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [r for r in rows if r.get("source", "owner_written") == kind and r.get("query")]


def _value(result: Any) -> Any:
    return result.get("value") if isinstance(result, dict) else result


def state_of(fake: Any) -> dict[str, Any]:
    snapshot = fake.query_session_state()
    tracks = {t["index"]: {k: t.get(k) for k in ("name", "volume", "pan", "muted", "soloed", "armed")}
              for t in snapshot.get("tracks", [])}
    return {"tracks": tracks, "track_count": len(snapshot.get("tracks", [])),
            "playing": snapshot.get("is_playing"), "selected": snapshot.get("selected_track_index"),
            "sends": {i: [_value(fake.get_track_send(i, r)) for r in (0, 1)] for i in tracks}
            if hasattr(fake, "get_track_send") else {},
            "devices": {i: [p.get("value") for p in (fake.get_device_parameters(i, 0).get("parameters") or [])]
                        for i in tracks}}


def diff(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    changes = []
    for key in ("track_count", "playing", "selected"):
        if before[key] != after[key]:
            changes.append(f"{key}: {before[key]} -> {after[key]}")
    for index, fields in after["tracks"].items():
        old = before["tracks"].get(index, {})
        for field, value in fields.items():
            if old.get(field) != value:
                shown = (lambda v: f"{v:.3f}" if isinstance(v, float) else repr(v))
                changes.append(f"{fields.get('name') or old.get('name')} {field}: {shown(old.get(field))} -> {shown(value)}")
    for group in ("sends", "devices"):
        for index, values in after[group].items():
            if before[group].get(index) != values:
                changes.append(f"{after['tracks'][index]['name']} {group[:-1]} values changed")
    return changes


def confirm(handle: Any, command: str, session: str, service: Any, planned: dict[str, Any]) -> dict[str, Any]:
    proposal = planned["proposal"]
    return handle(command, session_id=session, service=service, proposal=proposal,
                  confirm_token=proposal.get("confirmation_token", ""), idempotency_key=proposal.get("action_id", ""))


def run_one(command: str, number: int) -> dict[str, Any]:
    from kenn.core.fake_live import FakeLiveBackend
    from kenn.core.live_action_service import LiveActionService
    from kenn.core.live_command import handle_command

    fake = FakeLiveBackend()  # fresh demo set per command
    service = LiveActionService(fake)
    session = f"e2e-{number}"
    before = state_of(fake)
    planned = handle_command(command, session_id=session, service=service)
    row: dict[str, Any] = {"command": command, "planned": planned.get("status"),
                           "answer": str(planned.get("answer") or "")[:160],
                           "action": (planned.get("intent") or {}).get("action")}
    if planned.get("status") != "confirmation_required" or not isinstance(planned.get("proposal"), dict):
        row["outcome"] = "asked" if planned.get("status") in {"clarification_required", "refused"} else planned.get("status")
        row["untouched"] = not diff(before, state_of(fake))
        return row
    row["untouched_before_apply"] = not diff(before, state_of(fake))
    applied = confirm(handle_command, command, session, service, planned)
    if isinstance(applied.get("receipt"), dict):
        # The web server records receipts after an Apply (server.py); do the same so undo can find it.
        from kenn.core.live_receipt_journal import record_receipt

        record_receipt(applied["receipt"], session_id=session)
    after = state_of(fake)
    row.update(applied=applied.get("status"), verified=bool((applied.get("receipt") or {}).get("verified")),
               changes=diff(before, after))
    undo = handle_command("undo that", session_id=session, service=service)
    if undo.get("status") == "confirmation_required" and isinstance(undo.get("proposal"), dict):
        undo = confirm(handle_command, "undo that", session, service, undo)
    row.update(undo=undo.get("status"), restored=not diff(before, state_of(fake)),
               undo_answer=str(undo.get("answer") or "")[:120])
    row["outcome"] = ("pass" if row["untouched_before_apply"] and row["applied"] == "applied" and row["verified"]
                      and row["restored"] else "check")
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source_path", type=Path)
    parser.add_argument("--source", default="owner_written")
    args = parser.parse_args()
    temp = isolate_state()
    sys.path.insert(0, str(KENN_ROOT / "apps" / "backend" / "src"))
    tests = load_tests(args.source_path, args.source)
    rows = [run_one(t["query"], i) for i, t in enumerate(tests, 1)]
    for t, row in zip(tests, rows):
        print(f"\n“{row['command']}”  (expected: {t['expected_action']})")
        if row["outcome"] == "asked" or "applied" not in row:
            print(f"  KENN {row['outcome']}: {row['answer']}  | set untouched: {row['untouched']}")
            continue
        print(f"  proposed {row['action']} (nothing written before Apply: {row['untouched_before_apply']})")
        print(f"  applied: {row['applied']}, Live readback verified: {row['verified']}; changed: {'; '.join(row['changes']) or 'nothing'}")
        print(f"  undo: {row['undo']}; set restored exactly: {row['restored']}" + ("" if row["restored"] else f" ({row['undo_answer']})"))
    acted = [r for r in rows if "applied" in r]
    print(f"\n{len(acted)} executed: {sum(r['outcome'] == 'pass' for r in acted)} passed apply → verify → undo; "
          f"{len(rows) - len(acted)} asked or answered without writing. State kept in {temp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
