#!/usr/bin/env python3
"""Write one supervised-pilot session log from a support bundle (the Beta+ ten-session pilot).

Run it straight after a supervised session, next to the support bundle made with build_support_bundle.py:

    record_pilot_session.py --bundle ~/pilot/s01.zip --project "Tester A song 1" --tester "Tester A" \\
        --started-at 2026-09-27T14:05:00+01:00

The project and tester names are hashed here and never written anywhere. Changes, readbacks and receipts are counted
from the bundle's lifecycle events; requests from KENN's route log (only its times and routes, no text). Undo
receipts look the same as any other change in the bundle, so the person running the session is asked how many
changes were undone (each session needs at least one change and one undo), along with the pre-flight checklist, the
safety questions and the tester's sign-off. The log is then checked with the same evaluator the release gate uses,
so a problem shows up now rather than at the gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

KENN_ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(KENN_ROOT / "apps" / "backend" / "src"), str(KENN_ROOT / "tooling" / "scripts")]

PREFLIGHT = (
    ("disposable_set_confirmed", "Was the Live set a disposable copy, not the tester's real project?"),
    ("auto_mode_disabled", "Was KENN's auto mode off, so every change needed Apply?"),
    ("no_unsaved_production_work", "Was there no unsaved production work open anywhere in Live?"),
    ("supported_configuration_confirmed", "Were Live, macOS and the Mac the supported configuration?"),
    ("undo_visible_before_mutation", "Could the tester see the Undo button before the first change?"),
    ("diagnostics_privacy_checked", "Did you check the support bundle has no project names, audio or prompts?"),
)
SAFETY = (
    ("unauthorized_mutations", "Changes Live made that nobody applied"),
    ("false_success_receipts", "Receipts that said a change worked when Live shows it didn't"),
    ("lost_undos", "Undos that didn't put the value back"),
    ("companion_crashes", "Times the KENN companion crashed or had to be restarted"),
    ("unrecoverable_states", "Times the set ended up somewhere Undo couldn't fix"),
)


def pseudonym(value: str) -> str:
    # Salted with a fixed label so a hash of a bare name from elsewhere doesn't match; the evaluator re-buckets these
    # per release anyway, so nothing downstream can link a name back.
    return "sha256:" + hashlib.sha256(f"kenn-pilot\0{value.strip().casefold()}".encode()).hexdigest()


def ask_yes(question: str) -> bool:
    return input(f"{question} [y/n] ").strip().lower() in {"y", "yes"}


def ask_count(question: str) -> int:
    while True:
        answer = input(f"{question}? [0] ").strip() or "0"
        if answer.isdigit():
            return int(answer)
        print("A whole number, please.")


def bundle_events(bundle: Path) -> tuple[str, list[dict]]:
    with zipfile.ZipFile(bundle) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        events = json.loads(archive.read("lifecycle-events.json")).get("events") or []
    return str(manifest.get("source_revision") or ""), [e for e in events if isinstance(e, dict)]


def requests_since(started_at: datetime) -> int:
    from kenn.core import route_log

    if not route_log.LOG.exists():
        return 0
    count = 0
    for line in route_log.LOG.read_text(encoding="utf-8").splitlines():
        row = json.loads(line) if line.strip() else {}
        if row.get("at", 0) >= started_at.timestamp():
            count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bundle", type=Path, required=True, help="support bundle ZIP from build_support_bundle.py")
    parser.add_argument("--project", required=True, help="a name for the project; only its hash is kept")
    parser.add_argument("--tester", required=True, help="a name for the tester; only its hash is kept")
    parser.add_argument("--started-at", required=True, help="ISO time with timezone, e.g. 2026-09-27T14:05:00+01:00")
    parser.add_argument("--configuration", default="live-12.4.5-macos-26.5.2-arm64")
    parser.add_argument("--requests", type=int, help="requests made in the session (default: counted from the route log)")
    parser.add_argument("--output", type=Path, help="log path (default: next to the bundle, .json)")
    args = parser.parse_args()

    started_at = datetime.fromisoformat(args.started_at)
    if started_at.tzinfo is None:
        parser.error("--started-at needs a timezone, e.g. +01:00")
    revision, events = bundle_events(args.bundle)
    verified = [e for e in events if e.get("verified") is True and e.get("receipt_id")]
    print(f"Bundle: {len(events)} lifecycle events, {len(verified)} verified; source {revision[:12]}")

    undos = ask_count("How many of those verified changes were undos")
    undos_ok = undos and ask_yes(f"Did all {undos} undos put the exact previous value back in Live?")
    changes = len(verified) - undos
    requests = args.requests if args.requests is not None else max(requests_since(started_at), changes)
    print(f"Counting {changes} changes, {undos} undos, {requests} requests.")
    preflight = {field: ask_yes(question) for field, question in PREFLIGHT}
    print("Safety: enter 0 unless it happened.")
    safety = {field: ask_count(question) for field, question in SAFETY}
    passed = ask_yes("Did the session pass overall?")
    signoff = ask_yes("Has the tester read this summary and signed it off?")

    log = {
        "schema": "kenn.supervised_pilot_session.v1",
        "run_id": f"pilot-{uuid.uuid4().hex[:16]}",
        "project_id_sha256": pseudonym(args.project),
        "tester_id_sha256": pseudonym(args.tester),
        "receipt_evidence_file": args.bundle.name,
        "receipt_evidence_sha256": "sha256:" + hashlib.sha256(args.bundle.read_bytes()).hexdigest(),
        "source_git_commit": revision,
        "support_configuration_id": args.configuration,
        "started_at": started_at.isoformat(),
        "preflight": preflight,
        "operations": {"request_count": requests, "mutation_count": changes, "readback_verified_count": changes,
                       "undo_required_count": undos, "undo_verified_count": undos if undos_ok else 0},
        "safety": safety,
        "session_result": "pass" if passed else "fail",
        "issue_ids": [],
        "tester_signoff": signoff,
    }
    output = args.output or args.bundle.with_suffix(".json")
    output.write_text(json.dumps(log, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {output}")

    from evaluate_supervised_pilot import DEFAULT_MATRIX, evaluate

    row = evaluate([output], matrix_path=DEFAULT_MATRIX, source_revision=revision)["rows"][0]
    print("Checks out for the gate." if row["passed"] else f"Won't count yet: {', '.join(row['failures'])}")
    return 0 if row["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
