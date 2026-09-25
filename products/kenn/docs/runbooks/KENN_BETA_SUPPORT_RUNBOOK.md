# KENN private beta: support runbook

For whoever answers tester reports. Testers follow `docs/BETA_TESTER_GUIDE.md`, which the app also shows at
**Setup & Support → Read the tester guide**. Updated 2026-09-25 for the `KENN.app` beta (the old Mix Review CLI beta
is gone).

## What's in the beta

Session questions, Live control through proposal → **Apply** → readback → **Undo** (mixer, device focus, the measured
device parameters, inserting the 10 allowlisted audio effects), cited answers from KENN's notes, and Mix Review of an
exported WAV. The AI planner, AutoMix, audio generation and voice are off. A report about those is "not in this beta",
not a support case.

## First reply to any report

Ask for three things:

1. What they asked, what they expected, and what happened (the exact wording they typed matters).
2. The diagnostics file: **Setup & Support → Save diagnostics for support**, saved in
   `~/Library/Application Support/KENN/diagnostics`. It holds counts and timings only: kinds of changes and how they
   ended, answer times, versions, knowledge index. No track names, values, questions, audio or paths.
3. Their Live version and macOS version.

Only ask for the full logs (`~/Library/Logs/KENN Desktop Companion/server.log`,
`~/Library/Application Support/KENN/runtime/logs/kenn.log`) if the above doesn't explain it. They are fuller, so the
tester should look through them before sending.

## Common reports

| Report | What it usually is | What to do |
|---|---|---|
| "Live is connected" never ticks | AbletonOSC not selected as a Control Surface, or Live was open during the install | Settings → Link, Tempo & MIDI → a free slot → **AbletonOSC**, Input/Output **None**; quit and reopen Live; **Check again** |
| Connected, then KENN says Live is offline | Another OSC/KENN script in a second Control Surface slot (they share port 11000), or Live busy | Leave only AbletonOSC selected. Since 24 Sept KENN retries a quiet connection every 5 s; if it stays offline for more than a minute, get the diagnostics file |
| "KENN didn't do what I asked" | Wording KENN doesn't handle, or it asked a question instead | Normal: it asks rather than guesses. Log the exact phrasing for the parser backlog; it is not a defect unless KENN **applied** the wrong change |
| KENN applied the wrong change | A wrong plan: the most serious report | Get the exact wording and diagnostics the same day; the tester can **Undo** it. Add the phrasing to `tooling/data/adversarial_mixer_phrasings.jsonl` and fix it with a regression test before the next build |
| An answer cites a source that doesn't support it | Retrieval or note problem | File with the exact question and the cited sources; check the note itself |
| An answer shows code names (`generate_mix_plan()` and similar) | An internal AutoMix note reached an everyday answer (fixed 24 Sept) | Get the question; add it to the retrieval fixtures |
| Mix Review rejects a file | Not 16/24-bit PCM WAV, not mono/stereo, too short, or corrupt | Expected. Ask for a 16- or 24-bit WAV export |
| Mix Review's findings seem wrong on a real mix | Calibration, not a crash | Log against the finding's `fault_family` as real-mix evidence; don't patch it away from one example |
| App won't open the first time | Unsigned beta build (Gatekeeper) | Right-click KENN in Applications → **Open** → **Open** |
| KENN seems stuck | Companion hung or crashed | Quit and reopen KENN; nothing in Live changes without Apply, so restarting is always safe |

## Things KENN must never do

Escalate straight away, same day, if a tester reports any of these. They are safety defects, not support cases:

- a change reached Live without the tester pressing **Apply**;
- a receipt says "verified" but Live shows something else;
- **Undo** did not put the exact previous value back;
- KENN changed the master level, deleted or overwrote anything;
- anything was sent off the Mac (this build has no hosted AI and telemetry is off).

Ask for the diagnostics file, the Live set if they're willing to share it, and the exact steps. Stop inviting new
testers until it's understood.

## Data handling

Audio loaded for a review is analysed on the tester's Mac and not kept: each review records
`audio_retained: false` and keeps only its measurements (`storage: "metadata_only"`). Receipts and
diagnostics contain hashes and counts, not audio, so they are safe to store with the ticket. Don't ask testers for
their stems or projects unless a defect can't be reproduced otherwise, and then only with explicit consent.

## Fixing and shipping

1. Reproduce with the demo set or a synthetic case; add a regression test named for the behaviour it protects.
2. Run the suite (`tooling/scripts/run_tests_on_box.py` runs it on the GPU box in about 2 minutes).
3. For Live control changes, re-run the tester-guide walkthrough on real Live and the real-Live assistant test.
4. Rebuild the app (`tooling/scripts/build_kenn_app.py --dmg`; it smoke-tests the bundle) and send the new DMG with
   a one-line changelog.

## Rollback

Keep the previous DMG. A tester replaces KENN in Applications with the previous version; settings and history in
`~/Library/Application Support/KENN` are kept. The knowledge index keeps its previous version on disk
(`data/index/PREVIOUS`); `index_store.rollback_index()` switches back. See `docs/plans/ABLETON_ASSISTANT_ROLLBACK_PLAN.md`.
