# KENN Investor Demo Runbook

This is the canonical operator script for the investor demo. It preserves
KENN's proposal, confirmation, readback, receipt, and exact-undo boundary.
Do not improvise mutation commands during a live showing.

Jack requested a five-minute maximum walkthrough on 12 October. Use the timed
showcase below for the audience and backup recording. The full twenty-step
sequence remains the internal qualification exercise.

Review `KENN_INVESTOR_FAQ.md` before the showing and use its shipped-versus-
roadmap answers for audience discussion. Do not type off-script mutation
requests into the live demo.

## Qualification status

The Wednesday 14 October candidate is **not yet qualified with real Live**.
The topology fixture, preflight and bounded recipe have September evidence;
that evidence does not qualify the new Stage 2/3 control path. Follow D1–D6 in
[KENN_PLAN.md](../../KENN_PLAN.md) and start a new candidate section in the
rehearsal log. Do not claim a ten-run investor-demo pass until the current
build, audio fixture, projector run, recovery drill and all twenty steps have
passed ten consecutive rehearsals.

Tuesday's owner-supervised session starts at 20:00 London time. The candidate
adds `abletonosc/parameter_target.py`, which is outside AbletonOSC's hot-reload
list. Deploy it in that session and restart Live before qualification; verify
the running bundle hash afterwards. Do not count a hot reload alone as loading
the new module.

The checked-in `assets/demo/KENN_Live12_Demo.als` is a topology reset point,
not a finished musical production. The repository now includes a deterministic
generator for the original `Neon Proof` demo composition, but the complete
script remains unqualified until its stems are imported into a disposable Live
copy and the full run passes the rehearsal gate.

### Historical release gate checklist (2026-09-23)

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
9. Run `python3 tooling/scripts/demo_script_gate.py --route ask --runs 10 --json`.
   This uses the chat endpoint reached by the web UI and exercises
   the 13 non-mutating scripted prompt contracts and latency budgets. It cannot
   confirm proposals or qualify the seven manual UI/mutation/presentation steps,
   so a pass is supporting evidence rather than a complete rehearsal.

## Five-minute Ableton showcase

Run this after the current fixes, review and supervised Live qualification are
finished. Use the same qualified candidate, generated audio, disposable reset
set and connected web UI. Warm the analysis through preflight before starting
the clock. Target **4 min 45 s**, leaving 15 s of margin; stop at **5 min**.
The clock includes responses, navigation, listening and Undo. Take questions
afterwards. Use the existing presentation timing budgets without promising an
instant answer.

| Time | Action | Visible or audible proof |
|------|--------|--------------------------|
| 0:00–0:30 | Show Live and KENN's connected panel. Ask `Describe this session.` | The answer identifies the loaded demo session. |
| 0:30–1:40 | Play the demo and show Lead Vocal's Compressor on track 7. Ask `Set Compressor Threshold to -4 dB on track 7.` Inspect the proposal and click Apply. | Live shows 0 → -4 dB, the card reports verified readback, and the audience hears the change. |
| 1:40–2:15 | Click Undo on that Compressor card. | Live returns to 0 dB and the card reports the observed before-state restored. |
| 2:15–3:30 | Show Bass's existing EQ Eight on track 5. Ask `Boost amplitude by 3 dB at 200 Hz on track 5 band 2A.` Inspect and Apply, then ask `Undo that.` Inspect and Apply its inverse. | The named band changes from 0 → +3 dB and returns to its original gain, with verified readback for both actions. |
| 3:30–4:15 | Ask `How does my low end sound?` and show its measured evidence. | Explain that this analysis uses the demo's rendered WAV, with its capture source shown. |
| 4:15–4:45 | Ask `Delete track 3.` Show the refusal, then close with the demonstrated capabilities. | The track remains present. Label any mentioned future capability as roadmap work. |
| 4:45–5:00 | Reserved for normal response/navigation variation. | Finish within 300 s. |

Use the first short run as a supervised bug-finding exercise. Stop at the first
wrong target, refused intended action, missing readback, failed restoration,
incorrect answer or time overrun. Preserve the failed attempt in the rehearsal
log: build, exact prompt, card/receipt reference, expected and actual values,
elapsed time and whether the reset set was restored. Keep captures outside git
and queue fixes in `KENN_PLAN.md`. Reproduce a software break against fake Live,
add and mutation-check its regression, fix and review it, then requalify the
changed candidate before a clean take. A failed attempt cannot count as the
backup recording; do not edit away errors or waiting to manufacture a pass.

Record a complete successful take only after the sequence passes. Verify video
playback, readable proposals and Live values, audible before/after and the
five-minute limit. Reopen the reset set afterwards.

### Record the video

Jack clarified on 12 October that the immediate deliverable is a video and a
bug-finding walkthrough. The SaaS expansion report supplies the positioning:
grounded advice, inspected Live changes and exact Undo. Account/billing,
cloud processing, collaboration and other DAWs remain roadmap claims. The
video demonstrates the local web UI and Ableton path that actually passes.

During the supervised session, arrange the web UI and Live side by side with
proposal targets, receipts and Live values readable. Set `KENN_CAPTURE_DIR` to
an absolute local directory outside every Git checkout. Use a new take name
each time. The recorder captures the screen and audio; the operator performs
every command, Apply and Undo in the browser.

First record a ten-second sound check while playing the demo and speaking:

```sh
python3 tooling/scripts/record_demo_live.py \
  --out-dir "$KENN_CAPTURE_DIR/sound-check-01" --seconds 10 --microphone
```

Play back `showcase.mp4` and verify both Live's playback and narration are
audible, without feedback or clipping. The system-audio and microphone flags
request both sources; combined audio routing on this Mac still requires that
playback check. If either source is missing, fix the capture setup before a
full take. Do not change the producer's audio routing unattended.

For the qualified showcase, run the same recorder with a fresh output directory
and `--seconds 285 --microphone`. Start the operator script as recording starts;
the requested 285 s includes response waits, listening and Undo. A run that has
not finished when recording stops fails. Preserve it and try again after fixing
the cause; do not shorten the video to hide waiting or errors.

Each directory retains `raw.mov`, the complete encoded `showcase.mp4`, and
`capture.json` with durations, audio streams and file hashes. The MP4 mixes all
captured audio into one playback track, preserving each source's start time so
Live and narration stay aligned; the raw file retains the original streams.
An audio-free or over-300 s movie fails media checks. A media-valid receipt is
**unreviewed**: it does not prove audible sound, correct answers, successful Live
writes or restoration. Link the take to its exact qualified build in the rehearsal log,
watch it end to end, and record those human checks before accepting the video.
The older `record_demo_video.py` filename uses this same passive recorder.

## Twenty-step qualification script

Only text in `code` is typed into KENN. Lines that say Show, Explain or narrate
are spoken to the audience; never type them into the chat.

### Act 1 — KENN knows the session

1. Show the loaded Live set and KENN's connected status.
2. Ask: `How many tracks do I have?`
3. Ask: `What's selected?`
4. Ask: `Describe this session.`
5. Ask: `Any duplicate track names?`

### Act 2 — KENN controls Live safely

6. Ask: `Set Compressor Threshold to -4 dB on track 7.` Explain that this is an
   exact, profile-backed vocal compression control. Review the proposal, confirm it,
   and point out the verified readback.
7. Ask: `Pan the Synth hard left.` Review and confirm the exact proposal.
8. Ask: `Focus EQ Eight on track 5.` Review and confirm the device-focus proposal (Bass, EQ Eight).
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
18. Do not type anything. Scroll to the step-6 card (Threshold 0 → -4 dB, "Readback
    Verified") and the step-11 history, and narrate them aloud.
19. Click **Undo on the step-6 Compressor card** (not step 9: step 10 already
    reverted that one and KENN will refuse it as stale). Expect "Restored to
    Original State" and Lead Vocal Compressor Threshold back at 0 dB in Live.

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
