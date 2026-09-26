#!/usr/bin/env python3
"""Qualify the named mix recipes on real Live: apply, verify, undo, exact restore (Stage 3 recipe gate).

Runs against a running companion on the demo set (Kick, Snare / Clap, Hi-Hats, Drum Bus, Bass, Synth, Lead Vocal,
FX Print; Compressor on Drum Bus and Lead Vocal; A-Reverb and B-Delay returns). Each recipe goes through the chat
route the app uses: the proposal must be a recipe, Apply must come back with a verified receipt, "Undo that" must
come back verified, and the mixer (volume, pan, mute, solo) must be exactly where it started. Sends and device values
are checked by the receipts' own readbacks. Recipes that need a starting point get one first (a panned bass for "make
the low end mono", sends for "dry up", solos for "clear the solos"), undone afterwards.

    qualify_recipes_live.py --endpoint http://127.0.0.1:8090 --output tooling/evaluation/results/KENN_RECIPE_QUALIFICATION.json

Stops before any change unless the open set is the demo set.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

DEMO_TRACKS = ["Kick", "Snare / Clap", "Hi-Hats", "Drum Bus", "Bass", "Synth", "Lead Vocal", "FX Print"]
# (recipe name, what the producer says, setup requests applied first and undone after)
RECIPES = [
    ("room_for_kick", "Make room for the kick", []),
    ("space", "Give the vocal some space", []),
    ("forward", "Bring the drums forward", []),
    ("push_back", "Push the synth back", []),
    ("behind", "Put the synth behind the vocal", []),
    ("dry_up", "Dry up the vocal", ["Give the vocal some space"]),
    ("tighten_drum_bus", "Tighten the drum bus", []),
    ("vocal_peaks", "Tame the vocal peaks", []),
    ("mono_low_end", "Make the low end mono", ["Pan the bass 30% left"]),
    ("rhythm_section", "Solo the rhythm section", []),
    ("snare_crack", "Make the snare crack", []),
    ("clear_solos", "Clear the solos", ["Solo the rhythm section"]),
    ("vocal_cut_through", "Make the vocal cut through", []),
    ("glue_drum_bus", "Glue the drum bus", []),
    ("fix_low_end_mud", "Fix the low-end mud", ["Set the synth to -4 dB"]),
]


class Companion:
    def __init__(self, endpoint: str):
        self.base = endpoint.rstrip("/")
        self.session = f"recipes-{uuid.uuid4().hex[:8]}"

    def call(self, path: str, payload: dict | None = None, timeout: int = 90) -> dict:
        # KENN allows 60 changing requests a minute; a full run asks more than that, so it waits when told to.
        for _attempt in range(6):
            request = urllib.request.Request(self.base + path, json.dumps(payload).encode() if payload is not None else None,
                                             {"Content-Type": "application/json"}, method="POST" if payload is not None else "GET")
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    return json.load(response)
            except urllib.error.HTTPError as exc:
                if exc.code != 429:
                    # A refused apply (409: stale or replayed proposal, say) is a result to record, not a crash.
                    body = exc.read().decode("utf-8", "replace")
                    try:
                        return {"http_status": exc.code, **json.loads(body)}
                    except ValueError:
                        return {"http_status": exc.code, "error": body[:300]}
                time.sleep(float(exc.headers.get("Retry-After") or 10) + 0.5)
        raise RuntimeError(f"{path}: still rate-limited after six waits")

    def ask(self, text: str) -> dict:
        return self.call("/kenn/api/ask", {"question": text, "session_id": self.session})

    def apply(self, proposal: dict) -> dict:
        return self.call("/api/ableton/command", {"session_id": self.session, "proposal": proposal,
                                                  "confirm_token": proposal.get("confirmation_token"),
                                                  "idempotency_key": proposal.get("action_id")})

    def mixer(self) -> list[tuple]:
        state = self.call("/api/ableton/osc/session")
        return [(t["name"], round(float(t.get("volume") or 0), 4), round(float(t.get("pan", t.get("panning")) or 0), 4),
                 bool(t.get("muted")), bool(t.get("soloed"))) for t in state.get("tracks", [])]

    def do(self, text: str) -> tuple[bool, str]:
        """Ask, apply whatever proposal comes back, and report whether the receipt verified."""
        answer = self.ask(text)
        proposal = answer.get("proposal") or {}
        if not proposal.get("confirmation_token"):
            return False, f"no proposal: {str(answer.get('answer'))[:160]}"
        applied = self.apply(proposal)
        receipt = applied.get("receipt") or {}
        if receipt.get("verified") is True:
            return True, str(receipt.get("receipt_id") or "")
        return False, str(applied.get("error") or applied.get("answer") or applied.get("status"))[:200]

    def undo(self) -> tuple[bool, str]:
        return self.do("Undo that")


def qualify_one(kenn: Companion, name: str, request: str, setup: list[str]) -> dict:
    row = {"recipe": name, "request": request, "passed": False}
    baseline = kenn.mixer()
    set_up = []
    for text in setup:
        ok, detail = kenn.do(text)
        if not ok:
            row["failure"] = f"setup '{text}' failed: {detail}"
            break
        set_up.append(text)
    if len(set_up) == len(setup):
        before = kenn.mixer()
        answer = kenn.ask(request)
        proposal = answer.get("proposal") or {}
        steps = proposal.get("steps") or []
        if "recipe" not in str(proposal.get("schema") or "") and not steps and "insertion" not in str(proposal.get("schema")):
            row["failure"] = f"not a recipe proposal: {str(answer.get('answer'))[:160]}"
        else:
            row["steps"] = [f"{s.get('action')} {s.get('track_name')} {s.get('return_track_name') or ''}".strip() for s in steps]
            applied = kenn.apply(proposal)
            receipt = applied.get("receipt") or {}
            row["applied_receipt"] = receipt.get("receipt_id")
            if receipt.get("verified") is not True:
                row["failure"] = f"apply not verified: {str(applied.get('error') or applied.get('answer') or receipt.get('status'))[:200]}"
            else:
                row["changed_mixer"] = kenn.mixer() != before
                ok, detail = kenn.undo()
                row["undo_receipt"] = detail
                if not ok:
                    row["failure"] = f"undo not verified: {detail}"
                elif kenn.mixer() != before:
                    row["failure"] = "undo did not restore the mixer exactly"
                else:
                    row["passed"] = True
    for _text in reversed(set_up):
        ok, detail = kenn.undo()
        if not ok:
            row["passed"] = False
            row["failure"] = f"could not undo setup: {detail}"
    row["restored_to_baseline"] = kenn.mixer() == baseline
    row["passed"] = row["passed"] and row["restored_to_baseline"]
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--endpoint", default="http://127.0.0.1:8090")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--only", action="append", default=[], help="recipe name to run (repeatable)")
    args = parser.parse_args()

    kenn = Companion(args.endpoint)
    names = [t["name"] for t in kenn.call("/api/ableton/osc/session").get("tracks", [])]
    if names != DEMO_TRACKS:
        print(f"Not the demo set ({names}); stopping before any change.")
        return 2
    started = time.time()
    rows = []
    for name, request, setup in RECIPES:
        if args.only and name not in args.only:
            continue
        row = qualify_one(kenn, name, request, setup)
        rows.append(row)
        print(("PASS " if row["passed"] else "FAIL ") + f"{name:18} {request:34} {' / '.join(row.get('steps', []))}"
              + ("" if row["passed"] else f" | {row.get('failure')}"), flush=True)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    report = {"schema": "kenn.recipe_qualification.v1", "generated_at": datetime.now(timezone.utc).isoformat(),
              "source_git_commit": commit, "endpoint": args.endpoint, "seconds": round(time.time() - started, 1),
              "passed": sum(r["passed"] for r in rows), "total": len(rows), "rows": rows,
              "qualified": bool(rows) and all(r["passed"] for r in rows)}
    args.output.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(f"\n{report['passed']}/{report['total']} recipes qualified; mixer back at the start: "
          f"{all(r['restored_to_baseline'] for r in rows)}")
    return 0 if report["qualified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
