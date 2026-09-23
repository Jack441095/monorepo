# KENN Investor Demo — Rehearsal Log

Gate: **ten consecutive** runs of all 20 steps in `docs/runbooks/KENN_INVESTOR_DEMO.md`,
each 8–12 minutes, no raw errors, no stale or failed readback. Any failed run
resets the count to zero; keep the failed row and note the cause.

Reset point: `.runtime/investor-demo-audio/KENN_Live12_Demo_RESET Project/`
(read-only). Rehearse in `KENN_Live12_Demo_Rehearsal-1 Project/`.

UI: **http://127.0.0.1:8090/**. KENN's panel must read "Live connected" with 8 tracks before step 1.

## Runs

| # | Date | Start | End | Mins | Steps passed /20 | Failed step + cause | Recovery drill | Projector | Pass |
|---|------|-------|-----|------|------------------|---------------------|----------------|-----------|------|
| 1 | 2026-09-23 | 09:28:35 | 09:37:46 | 9.2 | 20/20 | Operator slips only: typed the step-18 talk line into KENN (off-topic answer, no Live change); clicked Undo on the step-9 card first (KENN correctly refused the stale undo). | — | — | [x] |
| 2 | 2026-09-23 | 09:47:52 | 09:54:44 | 6.9 | 20/20 (KENN correct) | Not counted: typed the "Try this" card label at step 14; applied the step-17 pan instead of dismissing; under 8 min. | — | — | [ ] not counted |
| 3 |  |  |  |  |  |  |  |  | [ ] |
| 4 |  |  |  |  |  |  |  |  | [ ] |
| 5 |  |  |  |  |  |  |  |  | [ ] |
| 6 |  |  |  |  |  |  |  |  | [ ] |
| 7 |  |  |  |  |  |  |  |  | [ ] |
| 8 |  |  |  |  |  |  |  |  | [ ] |
| 9 |  |  |  |  |  |  |  |  | [ ] |
| 10 |  |  |  |  |  |  |  |  | [ ] |

At least one of the ten runs must include the recovery drill, and at least one
must be on the actual projector or large display.

## Recovery drill (do once, inside a run)

Between steps 7 and 8, stop the KENN companion (Ctrl-C in its terminal), ask
`What's selected?`, and confirm KENN shows a plain-English connection message
with no stack trace. Restart the companion, run `demo_preflight.py`, then
continue from step 8. Note the seconds from restart to usable.

## Step checklist (copy per run if useful)

- [ ] 1 Live set + KENN connected status shown
- [ ] 2 Track count · [ ] 3 Selected (Drum Bus) · [ ] 4 Describe · [ ] 5 Duplicates
- [ ] 6 Compressor Output +3 dB on track 7, confirmed, readback shown
- [ ] 7 Synth hard left, confirmed
- [ ] 8 Focus EQ Eight on track 5, confirmed
- [ ] 9 +3 dB at 200 Hz, band 2A, confirmed
- [ ] 10 Undo, exact value restored
- [ ] 11 "What did you change?" history shown
- [ ] 12 Low end · [ ] 13 Vocal clipping · [ ] 14 Advice panel shown
- [ ] 15 Delete refused · [ ] 16 Master max refused (not confirmed)
- [ ] 17 Pending proposal token explained · [ ] 18 Receipt journal shown
- [ ] 19 Receipt Undo + readback verified
- [ ] 20 Roadmap narration (labelled as roadmap)

## Notes

**Attempt before run 1 (failed at step 6, not counted), 2026-09-23.** Two defects that only the real UI path exposed. Codex's
10/10 script gate calls `/api/ableton/command` directly, bypassing both.
1. Confirmation tokens hashed `before`/`after` as Python text (`0.0`, `-1.0`), while the browser's
   `JSON.stringify` echoes `0`/`-1`, so every numeric Apply was rejected as tampered. Fixed by
   canonicalising numbers in `confirmation._request_hash`.
2. `/kenn/api/ask` never sent steps 6, 8, 9, 10, 15 or 16 to the Live gateway (they got a knowledge
   article, "need more direction", or a session dump). Fixed by routing imperative Live phrasing
   through `handle_command` and keeping only proposals, refusals, and undo outcomes.
Also: "What did you change?" now lists only the current session's receipts.
Verified afterwards through the UI's own request shapes: steps 6–11, 15, 16 and the step-19 receipt
undo all pass with verified readback.
