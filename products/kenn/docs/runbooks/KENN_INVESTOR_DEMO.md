# KENN Investor Demo Runbook

This is the canonical operator script for the investor demo. It preserves
KENN's proposal, confirmation, readback, receipt, and exact-undo boundary.
Do not improvise mutation commands during a live showing.

Review `KENN_INVESTOR_FAQ.md` before the showing and use its shipped-versus-
roadmap answers for audience discussion. Do not type off-script mutation
requests into the live demo.

## Qualification status

The checked-in topology fixture, full preflight, and a bounded two-step Live
recipe are qualified. The complete script below is **not yet qualified**. Do
not claim a ten-run investor-demo pass until the audio fixture, projector run,
recovery drill, and all twenty steps have passed ten consecutive rehearsals.

The checked-in `assets/demo/KENN_Live12_Demo.als` is a topology reset point,
not a finished musical production. The repository now includes a deterministic
generator for the original `Neon Proof` demo composition, but the complete
script remains unqualified until its stems are imported into a disposable Live
copy and the full run passes the rehearsal gate.

### Release gate checklist (updated 2026-09-23)

- [x] Stems rendered, hash-bound manifest written
- [x] Disposable rehearsal copy opened in Live (not the tracked fixture)
- [x] Atomic-EQ qualifier `--apply` passed on the disposable set
- [x] Kick and Synth replaced by same-name audio tracks; eight stems placed at
      bar 1 and read back (`prepare_investor_demo_rehearsal_set.py --stem-dir
      "KENN Demo Audio" --apply`; the `.runtime` Place is hidden from Live's
      Browser, so the hash-verified visible copy is used)
- [x] Drum Bus and its Compressor selected
- [x] Mutating preflight 11/11 on the stem-loaded set
- [x] Operator saved the disposable set. Live saves a loose `.als` into a new
      Project folder: the qualified set is
      `.runtime/investor-demo-audio/KENN_Live12_Demo_Rehearsal-1 Project/`. The
      read-only per-run reset point is `KENN_Live12_Demo_RESET Project/` (same
      SHA-256). Ignore the earlier `KENN_Live12_Demo_Rehearsal Project/`; it
      holds the abandoned hand-edited attempt with wrong names and missing devices.
- [x] Ten-run non-mutating script gate: 10/10 on the saved stem-loaded set, slowest 398.6 ms
- [ ] Ten consecutive complete 20-step rehearsals (record each in
      `docs/evidence/KENN_INVESTOR_DEMO_REHEARSAL_LOG.md`)

## Before the room opens

1. Render the rights-clear audio fixture with `python3
   tooling/scripts/build_investor_demo_audio.py --out-dir
   .runtime/investor-demo-audio`.
2. Open a disposable copy of `assets/demo/KENN_Live12_Demo.als` in Live 12 and
   import the eight generated stems at bar 1 in manifest track order. Do not
   overwrite the tracked reset fixture. **Kick and Synth are MIDI tracks in the
   fixture and cannot hold audio.** For each of them: select it, press Cmd-T to
   add an audio track directly after it, drop the stem at bar 1, delete the
   MIDI track, and rename the new track to exactly `Kick` / `Synth` (neither
   MIDI track carries devices). Drop the other six stems onto the existing
   lanes in Arrangement view, never into the empty area below the tracks,
   because that creates new file-named tracks and breaks the fixture contract.
   Save, then keep an untouched copy of this file as the per-run reset point.
3. Export the two manifest analysis paths before starting KENN:
   `KENN_LIVE_AUDIO_CAPTURE_PATH=.runtime/investor-demo-audio/KENN_Demo_Mix_Analysis.wav`
   and `KENN_LIVE_VOCAL_CAPTURE_PATH=.runtime/investor-demo-audio/KENN_Demo_Lead_Vocal_Analysis.wav`.
4. Select Drum Bus and its Compressor. This gives the device-focus action an
   exact starting selection; a selected return track is not treated as an
   implicit regular-track target.
5. Start the **full KENN companion** (not `run_ux_backend.py`, which skips the
   Mixing Doctor loop that feeds the Live status panel), from `products/kenn`
   with the step-3 variables and `KENN_ALLOW_DAW_CONTROL=1` exported:
   `PYTHONPATH=apps/backend/src:tooling python3 apps/backend/src/kenn/server.py`.
   The UI is **http://127.0.0.1:8090/** (the `/kenn/` prefix is API-only and
   renders a blank page). Confirm the panel shows "Live connected" and 8 tracks.
6. Run `tooling/scripts/demo_preflight.py` without mutations. Its audio check
   must verify both hashes against the actual chat-analysis responses, detect
   the low-end and isolated-vocal clipping cues, and warm the bounded analysis
   cache used by steps 12–13.
7. Run it again with `--allow-mutations` only on the disposable copy.
8. Confirm 11/11 checks pass, then reset and reselect Drum Bus before rehearsing.
9. Run `python3 tooling/scripts/demo_script_gate.py --runs 10`. This exercises
   the 13 non-mutating scripted prompt contracts and latency budgets. It cannot
   confirm proposals or qualify the seven manual UI/mutation/presentation steps,
   so a pass is supporting evidence rather than a complete rehearsal.

## Twenty-step script

Only text in `code` is typed into KENN. Lines that say Show, Explain or narrate
are spoken to the audience; never type them into the chat.

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
17. Ask: `Pan the Synth hard right.` Do **not** apply it. Explain that the token
    is bound to this exact action and current state, then click **Dismiss**.
    (Synth is already hard left after step 7, so a hard-left prompt would show a
    no-op L100 → L100 card.)
18. Do not type anything. Scroll to the step-6 card (Output 0 → 3 dB, "Readback
    Verified") and the step-11 history, and narrate them aloud.
19. Click **Undo on the step-6 Compressor card** (not step 9: step 10 already
    reverted that one and KENN will refuse it as stale). Expect "Restored to
    Original State" and Lead Vocal Compressor Output back at 0 dB in Live.

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
