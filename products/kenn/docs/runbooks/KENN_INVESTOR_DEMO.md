# KENN Investor Demo Runbook

This is the canonical operator script for the investor demo. It preserves
KENN's proposal, confirmation, readback, receipt, and exact-undo boundary.
Do not improvise mutation commands during a live showing.

## Qualification status

The checked-in topology fixture, full preflight, and a bounded two-step Live
recipe are qualified. The complete script below is **not yet qualified**. Do
not claim a ten-run investor-demo pass until the audio fixture, projector run,
recovery drill, and all twenty steps have passed ten consecutive rehearsals.

The checked-in `assets/demo/KENN_Live12_Demo.als` is a topology reset point,
not a finished musical production. Acts 3 and 4 require a disposable rehearsal
copy containing original or royalty-free audio with known, documented issues.

## Before the room opens

1. Open a disposable copy of `assets/demo/KENN_Live12_Demo.als` in Live 12.
2. Select Drum Bus and its Compressor. This gives the device-focus action an
   exact starting selection; a selected return track is not treated as an
   implicit regular-track target.
3. Start AbletonOSC, the KENN backend, and the frontend.
4. Run `tooling/scripts/demo_preflight.py` without mutations.
5. Run it again with `--allow-mutations` only on the disposable copy.
6. Confirm 11/11 checks pass, then reset and reselect Drum Bus before rehearsing.

## Twenty-step script

### Act 1 — KENN knows the session

1. Show the loaded Live set and KENN's connected status.
2. Ask: `How many tracks do I have?`
3. Ask: `What's selected?`
4. Ask: `Describe this session.`
5. Ask: `Any duplicate track names?`

### Act 2 — KENN controls Live safely

6. Ask: `Set Compressor Output to 3 dB on track 7.` Explain that this is an
   exact, profile-backed vocal gain control. Review the proposal, confirm it,
   and point out the verified readback.
7. Ask: `Pan the Synth hard left.` Review and confirm the exact proposal.
8. Ask: `Focus EQ Eight on track 5.` Review and confirm the selection proposal.
   The Bass EQ is intentionally preloaded; inserting a second EQ would violate
   the fixture contract and make the next command ambiguous.
9. Ask: `Boost amplitude by 3 dB at 200 Hz on track 5 band 2A.` Review and
   confirm. The explicit band is required because more than one EQ Eight band
   can share the same frequency.
10. Ask: `Undo that.` Verify the gain returns exactly to its prior value.
11. Ask: `What did you change?` Show the receipt-backed history.

### Act 3 — KENN understands audio

12. Ask: `How does my low end sound?` Show the measured evidence, severity,
    confidence, and suggested listening test.
13. Ask: `Check the vocals for clipping.` Keep the answer tied to the rendered
    or uploaded audio evidence.
14. Show the same findings in the frontend advice panel; do not present the
    empty topology fixture as proof of audible mix quality.

### Act 4 — The safety model

15. Ask: `Delete track 3.` Show the clear refusal of an unsupported destructive
    request.
16. Ask: `Set the master volume to maximum.` Show the safe-range warning or
    exact confirmation gate; do not confirm a hazardous proposal.
17. Open a benign pending proposal and explain that the token is bound to its
    exact action and current state.
18. Show the receipt journal and its before/after values.
19. Use the receipt's Undo control and verify the independent Live readback.

### Act 5 — The path forward

20. Explain shadow-mode learning, the evidence-based device qualification
    pipeline, local-model fine-tuning, and preview/approve/insert generative
    features. Clearly label these as roadmap items where they are not shipped.

## Reset and failure policy

- Stop on the first failed, ambiguous, or stale readback. Never count a partial
  run as a pass.
- If Live disconnects, show the English connection error, restore the control
  path, rerun preflight, and restart the rehearsal count.
- Reopen the reset fixture after every run; do not rely on a chain of undos as
  the only reset mechanism.
- Record elapsed time, each failed step, recovery behavior, and final fixture
  hash. A qualified run is 20/20 steps in 8–12 minutes with no raw errors.
