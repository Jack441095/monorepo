# Ableton Live Test Procedure

This procedure requires Ableton Live 12, the KENN companion process, and a disposable copy of a Live set. Do not use an original project.

1. Start KENN with `PYTHONPATH=source python3 apps/backend/src/kenn/server.py` and enable `AUDIO_TOO_ALLOW_DAW_CONTROL=1` only for the disposable test session.
2. Install the pinned upstream `AbletonOSC` Remote Script using
   `docs/ABLETONOSC_ROUTE.md`. Restart Live, choose `AbletonOSC` in Control
   Surfaces, and confirm the Live log reports OSC listening on UDP 11000 with
   replies on UDP 11001. Keep `KENN_Bridge` installed only as a rollback path.
3. Run a read-only `query_session_state()` and save the JSON. Confirm track indices, names, volume, pan, mute/solo/arm, devices, tempo, transport, and session timestamp are real values.
4. Inspect the target device parameters. Record device name, parameter name/index, value, min/max.
5. Create one proposal. Confirm the plug-in's Live proposal panel shows exact before/after, unit, range, reason, evidence, confidence, risk, timestamp, and undo information.
6. Press **Confirm Live Proposal** once. Verify the executor performs one write, reads the value back, and returns a verified receipt. Repeat the same token and confirm it is rejected.
7. Change the parameter manually in Live before confirming a second proposal. Confirm the stale proposal is rejected.
8. Press **Undo Last Live Change**, inspect the reverse proposal, then confirm it once. Verify Live readback equals the captured previous value. Test a failed readback and a batch partial failure with rollback.
9. After every plug-in rebuild, fully quit and reopen Ableton Live before testing; reopening only the plug-in editor may keep the old binary loaded. Close/reopen the disposable set and confirm no KENN mutation was made without confirmation.

## Current KENN EQ-band pilot case

Use the disposable set with the existing `EQ Eight` on user track 4
(`4-Audio`). In the plug-in's **Control Live** command box, enter:

```text
reduce amplitude by 3 dB at 200 Hz on track 4 band 1B
```

The expected proposal is:

```text
4-Audio -> EQ Eight -> band 1B -> approximately 200 Hz
1 Gain B: 0 dB -> -3 dB
```

Before pressing **Confirm Live Proposal**, confirm that the proposal says
nothing has changed. Press it once, then record the verified readback and
receipt ID.
Repeat the same confirmation only to prove replay rejection; it must not
produce a second write. Use the receipt's undo action and record the final
readback at 0 dB. If the band is absent, ambiguous, or no longer tuned to
200 Hz, stop and record a clarification instead of retuning a band.

Record Live version, OS, set hash, Remote Script log, OSC address, local
exchange ID, latency, readback, receipt IDs, and any failure. A mock cannot
satisfy this procedure.

## Next supervised milestone: two-step recipe

The repeatable recipe runner is proposal-only unless `--apply` is explicitly
provided. First prepare the exact current target without changing Live:

```bash
PYTHONPATH=source python3 scripts/qualify_ableton_live_recipe.py \
  --track-index 3 --device-index 0 --parameter-name "1 Gain A" \
  --device-value -1 --pan-value 0.1 --session-id recipe-proposal-check
```

For a disposable set only, rerun with `--apply` after confirming the proposal
target. The runner must return a verified two-step receipt, reject the exact
replay, apply a fresh inverse recipe, and finish with both original values
read back. A failed or uncertain result must stop further writes and be
recorded as qualification failure; do not retry the same confirmation token.
If a failure leaves a value changed, inspect the receipt and create a fresh
recovery proposal from the current Live snapshot before doing anything else.
