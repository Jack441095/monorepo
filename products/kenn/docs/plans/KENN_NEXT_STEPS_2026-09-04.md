# KENN next steps — 2026-09-04

## Current position

KENN now has a verified, supervised Ableton control path for a bounded set of
track, transport, EQ Eight, Compressor, and Utility operations. The disposable
Live test set now has `EQ Eight`, `Glue Compressor`, and `Saturator` on
`4-Audio`, plus `Auto Filter` and `Drum Buss` on `3-Audio`; AbletonOSC is
answering read-only requests; and the repository test suite passes 298 tests.

The latest real-Live qualification evidence is stronger than the original EQ
smoke test: `EQ Eight` band `2A` was retuned from 200 Hz / 0 dB to 250 Hz /
-3 dB and read back successfully. `Glue Compressor` was then inserted through
the confirmation-bound path, its `Threshold` was tested at 0 -> -6 -> 0, both
writes were read back, the replay was rejected, and the inverse receipt restored
the original value. The same first-control qualification pattern now passes
for Saturator (`Drive` 0.5 -> 0.65 -> 0), Auto Filter (`Resonance` 0 ->
0.25 -> 0), and Drum Buss (`Drive` 0.2 -> 0.35 -> 0). These families remain
candidates until broader parameter profiles and independent review are complete.

The latest command-path change separates fast topology/device identity reads
from the full mixer/transport inspector. Measured on this machine, a
topology-only read is about 2.0 seconds, a full read about 5.5 seconds, a
duplicate-device proposal about 1.5 seconds, and an EQ parameter proposal
about 3.0 seconds. These are responsiveness measurements, not a claim that
all Live devices or arbitrary language are qualified.

The local LLM shadow gate is not yet a control path: the available 7B model
returned 0/3 validator-accepted plans in a read-only probe and then timed out
on an isolated retry. KENN now permits one bounded structural repair retry and
rejects active plans that disagree with the deterministic interpretation, but
the deterministic parser remains authoritative until a model passes
exact-identity, typed-plan, latency, and human-review gates.

The natural-language command gateway now resolves device parameters by exact
name after identifying the device from the current Live topology. For example,
`set Saturator Drive to 0.65 on track 4` produces a confirmation-only proposal
with the Live-reported `Drive` index and range; no write occurs until the user
confirms that exact proposal. This removes the former hard-coded parser list
without allowing arbitrary or invented parameter names through the gateway.

## Upgrade order

1. **Make product state unambiguous.** Show connection, Live snapshot age,
   target identity, proposal status, apply status, readback status, and
   failure reason in the plug-in. Add stage-specific timeouts and a refresh
   action so “checking” cannot look like success.

   **Progress:** the native editor now serializes Live requests, exposes
   explicit inspection/proposal/apply/verified/offline/readback-failed/timeout
   labels, and warns against retrying a request that has timed out locally.
   The command contract now also carries the topology snapshot timestamp,
   snapshot age, read duration, target identity, and readback verification
   stage. The rebuilt VST3 is installed; Live must be fully restarted to load
   it.

2. **Expand the device matrix one family at a time.** Start with Glue
   Compressor, Saturator, Auto Filter, and Drum Buss. For every parameter,
   record exact Live identity, discovery name, type, range, unit, write,
   readback, stale rejection, replay rejection, and inverse undo evidence.

   **Progress:** `GET /api/ableton/device-matrix` now performs the read-only
   inventory and labels observed families as `qualified`, `candidate`, or
   `unqualified`. The current set contains qualified `EQ Eight` plus observed
   `Glue Compressor`, `Saturator`, `Auto Filter`, and `Drum Buss` candidates.
   Native candidate insertion is now
   allowlisted for `Glue Compressor`, `Saturator`, `Auto Filter`, and `Drum
   Buss`, while retaining append-only insertion and the existing confirmation,
   stale-state, readback, receipt, and undo boundary. First real parameter
   qualifications have passed for all four candidates; their
   family profiles are intentionally not promoted until the broader matrix is
   complete.

3. **Productize the command state machine.** Make the visible lifecycle
   explicit: `inspecting -> proposal ready -> awaiting confirmation ->
   applying -> verified`. Also expose `offline`, `stale`, `readback failed`,
   and `rolled back`. Keep recipes bounded to three reversible operations.
   **Progress:** the rebuilt C++ editor now has a read-only **Show Live
   Controls** action. It loads the current exact track/device/parameter/range
   inventory from KENN without writing to Live; command entry still goes
   through the same proposal and readback boundary.

4. **Close persistence and recovery.** Test dirty-set handling, intentional
   save only, reopen/hash comparison, Live loss during each stage, and
   companion restart. Never silently save, overwrite, or claim persistence.

5. **Complete independent human review.** Run the prepared packet with two
   independent reviewers, adjudicate disagreements, and keep the qualified
   profile gated until the reviewed source snapshot is fixed.

## Non-negotiables

- No direct LLM-to-OSC path.
- No write without exact target identity, confirmation, stale checks,
  readback, and a receipt.
- No destructive or silent project save.
- No blocking or network work on the audio thread.
- No release claim based only on mocks, one command, or one Live set.

## Immediate manual smoke test

Before using the rebuilt native editor, fully quit and reopen Ableton Live so
Live unloads the previously installed VST3 binary. The KENN companion and
AbletonOSC are currently healthy; the latest read-only matrix reports
qualified `EQ Eight` plus observed candidate `Glue Compressor`, `Saturator`,
`Auto Filter`, and `Drum Buss` devices.

With Ableton Live open and `4-Audio` selected, enter:

`set EQ Eight 2 Gain A to -3 dB on track 4`

Click **Control Live**, inspect the exact proposal, then click **Confirm Live
Proposal**. Verify the parameter changes in Live, then use **Undo Last Live
Change** and confirm the inverse proposal. This path has now also been tested
directly through the running companion and AbletonOSC with verified readback.
It remains a supervised test; no autonomous write is enabled by this plan.

## Next device-qualification action

The first qualification pass is now complete for Glue Compressor, Saturator,
Auto Filter, and Drum Buss. Candidate insertion is available only for those
exact allowlisted names and still requires confirmation. For the next pass,
repeat the same proposal-only → explicit `--apply` workflow for additional
parameters and record each exact Live name, sparse index, range, readback,
replay rejection, and inverse restoration:

```bash
PYTHONPATH=source python3 scripts/qualify_ableton_live_device.py \
  --track-index <track-index> \
  --device-index <device-index> \
  --parameter-name "<exact Live parameter name>" \
  --value <distinct in-range-value> \
  --session-id next-device-parameter
```

The command above is proposal-only and must report `changed: false`. After
reviewing the exact target, rerun it with the same inspected values and add
`--apply`. The applied run must finish with verified write, replay rejection,
identity-bound inverse undo, and restored readback. If any stage is
uncertain, stop and record the failure; do not repeat the same confirmation
token.

## Current implementation delta

The deterministic parser and LLM-plan validator now share the same native
device insertion allowlist. Natural-language requests such as `add Glue
Compressor on track 4` create the same exact confirmation-bound proposal as
EQ Eight insertion; unsupported devices and duplicate devices still stop
without writing. This is a command-surface expansion only: it does not turn on
LLM-controlled Live writes, and the deterministic interpretation remains
authoritative. The insertion executor also reconciles a fresh Live topology
readback when the browser extension mutates Live but loses its OSC
acknowledgment, preventing a dangerous retry after an ambiguous timeout.
The parser also accepts exact device-parameter names discovered at runtime;
the real `set Saturator Drive to 0.65 on track 4` request now reaches a
confirmation-bound proposal with `changed=false` and a Live-verified range.
Device-parameter execution now applies the same one-readback reconciliation:
an unacknowledged write observed at the requested value becomes a verified
receipt marked `unacknowledged_write_reconciled`, with no automatic retry.
The MCP facade also exposes a typed `live_parameter_profile` read that joins
raw/range/quantization metadata with Ableton's displayed value string. This
evidence path now enables only the two reversible `%` mappings proven in Live:
Auto Filter Resonance and Drum Buss Drive. Glue, Saturator, and other
unqualified display units remain raw-only or clarification-gated; KENN never
guesses a display-to-raw conversion.
LLM track-control plans now also require normalized volume/pan values and
reject user-facing dB units before proposal creation.

The latest Glue probes found an important device-specific boundary: Live's raw
parameter values do not always equal the displayed units. Glue `Attack` raw
`3.0` displays `1`, and `Ratio` raw `1.0` displays `4`. Decimal raw writes
were rejected safely, while a discrete raw Attack step passed and restored.
KENN should add display-unit mapping before exposing user-facing Glue ratio or
time commands; the generic raw-value path must not guess.

The MCP decision and implementation are recorded in
[`KENN_ABLETON_MCP_INTEGRATION_PLAN.md`](KENN_ABLETON_MCP_INTEGRATION_PLAN.md):
KENN now exposes a local stdio MCP facade with typed reads, proposals, exact
confirmed apply, identity-bound undo, and redacted receipt recovery. The real
MCP operation matrix passed for pan, EQ, compound EQ, insertion/removal, and
Glue Attack, with replay rejection and restoration. The current AbletonOSC
route remains the backend; the external-client connection sequence is in
[`docs/KENN_MCP_CLIENT_SETUP.md`](docs/KENN_MCP_CLIENT_SETUP.md).

## Status update — 2026-09-05

The next engineering gates are deliberately ordered:

1. Run a controlled real ambiguous-write qualification only when a disposable
   Live set and an interruption method are available; simulated transport
   coverage already returns `transport_uncertain` and forbids automatic retry.
2. Add more typed LLM command fixtures and keep deterministic identity
   validation authoritative; do not enable the current local model for Live
   writes until its held-out acceptance rate improves.
3. Evaluate Ableton Extensions SDK as a separate optional backend in a beta
   Live set, never by replacing the working AbletonOSC route in place.

## Engineering status

The current working-tree changes are not committed. Any future commit must
use ordinary project commit messages with no AI tags or attribution.
